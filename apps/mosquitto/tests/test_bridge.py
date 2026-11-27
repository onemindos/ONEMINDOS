# SPDX-License-Identifier: Apache-2.0
"""Tests for the Mosquitto -> NATS bridge (issue #199, FLD-02; apps/mosquitto/README.md "Bridge to NATS").

Two parts:
- StartScriptTest runs manifests/start.sh with a fake `mosquitto` and checks the config it writes:
  bridge off by default, the bridge lines when a host is set, and refusal of values that could add
  their own config lines. Needs only a POSIX `sh`.
- BridgeRoundTripTest starts the pinned NATS and Mosquitto images in Docker, the way the app runs
  (start.sh as the command, UID 1883, read-only root, runtime config in a tmpfs), and checks that
  1. an MQTT 5 client is refused by NATS's own MQTT listener (the gap this bridge closes), and
  2. an MQTT 5 client round-trips a message: it publishes to Mosquitto, the message reaches the NATS
     bus as subject mqtt.up.<topic>, a NATS client sends it back on mqtt.down.<topic>, and the same
     MQTT 5 client receives it from Mosquitto.
  Without Docker it is skipped, unless MOSQUITTO_BRIDGE_E2E=required (set in CI), where it fails.

The MQTT and NATS clients below are minimal, stdlib-only implementations of the packets this test
needs (MQTT 5.0 and 3.1.1 CONNECT/SUBSCRIBE/PUBLISH/PUBACK, NATS CONNECT/SUB/PUB/MSG), so the test
needs no third-party package and states exactly which protocol level it speaks.
Run: python3 -I -m unittest discover -s apps/mosquitto/tests -v
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
START_SH = APP / "manifests" / "start.sh"
# Same pins as apps/mosquitto/manifests/deployment.yaml and deploy/compose/compose.yaml (digests
# re-read from registry-1.docker.io /v2/library/<name>/manifests/<tag> on 2026-11-19).
MOSQUITTO_IMAGE = ("docker.io/library/eclipse-mosquitto:2.1.2-alpine@sha256:"
                   "75d6662dee52c947dc9dd9c29f1d8d7ffef78ddaf38001caa09755681e8bbc98")
NATS_IMAGE = ("docker.io/library/nats:2.15.3-alpine@sha256:"
              "558394a23dd3c36f2d3a64b51865fd09908010e80a542cea5e75c2af543ed62a")


# --- minimal MQTT client ---------------------------------------------------------------------------
def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _str(s: str | bytes) -> bytes:
    b = s.encode() if isinstance(s, str) else s
    return struct.pack("!H", len(b)) + b


class MQTTRefused(Exception):
    """The broker refused the CONNECT (bad CONNACK or closed the connection)."""


class MQTT:
    def __init__(self, host: str, port: int, client_id: str, version: int = 5, timeout: float = 10.0):
        self.v5 = version == 5
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.next_id = 1
        flags = 0x02  # clean start / clean session
        var = _str("MQTT") + bytes([version, flags]) + struct.pack("!H", 30)
        if self.v5:
            var += _varint(0)  # no CONNECT properties
        self._send(0x10, var + _str(client_id))
        try:
            ptype, body = self._read()
        except (ConnectionError, OSError) as e:
            raise MQTTRefused(f"connection closed before CONNACK: {e}") from e
        if ptype != 0x20 or len(body) < 2 or body[1] != 0:
            raise MQTTRefused(f"CONNACK refused: type 0x{ptype:02x}, body {body.hex()}")

    def _send(self, header: int, body: bytes) -> None:
        self.sock.sendall(bytes([header]) + _varint(len(body)) + body)

    def _exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("connection closed")
            buf += chunk
        return buf

    def _read(self) -> tuple[int, bytes]:
        header = self._exact(1)[0]
        length, mult = 0, 1
        while True:
            b = self._exact(1)[0]
            length += (b & 0x7F) * mult
            mult *= 128
            if not b & 0x80:
                break
        return header, self._exact(length)

    def _props(self, body: bytes, i: int) -> int:
        """Skip an MQTT 5 property block at body[i:], return the index after it."""
        length, mult = 0, 1
        while True:
            b = body[i]
            i += 1
            length += (b & 0x7F) * mult
            mult *= 128
            if not b & 0x80:
                return i + length

    def _pid(self) -> int:
        pid, self.next_id = self.next_id, self.next_id % 65535 + 1
        return pid

    def subscribe(self, topic: str, qos: int = 1) -> None:
        body = struct.pack("!H", self._pid()) + (_varint(0) if self.v5 else b"") + _str(topic) + bytes([qos])
        self._send(0x82, body)
        while True:
            ptype, resp = self._read()
            if ptype & 0xF0 == 0x90:
                i = self._props(resp, 2) if self.v5 else 2
                if resp[i] >= 0x80:
                    raise AssertionError(f"SUBACK refused {topic}: 0x{resp[i]:02x}")
                return

    def publish(self, topic: str, payload: bytes, qos: int = 1) -> None:
        body = _str(topic)
        if qos:
            body += struct.pack("!H", self._pid())
        if self.v5:
            body += _varint(0)
        self._send(0x30 | (qos << 1), body + payload)
        while qos:
            ptype, _ = self._read()
            if ptype & 0xF0 == 0x40:  # PUBACK
                return

    def receive(self, timeout: float) -> tuple[str, bytes] | None:
        """Next PUBLISH within timeout, as (topic, payload); None on timeout."""
        self.sock.settimeout(timeout)
        try:
            while True:
                ptype, body = self._read()
                if ptype & 0xF0 != 0x30:
                    continue
                qos = (ptype >> 1) & 3
                tlen = struct.unpack("!H", body[:2])[0]
                topic, i = body[2:2 + tlen].decode(), 2 + tlen
                if qos:
                    pid = body[i:i + 2]
                    i += 2
                    self._send(0x40, pid + (b"\x00" + _varint(0) if self.v5 else b""))
                if self.v5:
                    i = self._props(body, i)
                return topic, body[i:]
        except socket.timeout:
            return None
        finally:
            self.sock.settimeout(10.0)

    def close(self) -> None:
        try:
            self._send(0xE0, b"\x00" + _varint(0) if self.v5 else b"")
        except OSError:
            pass
        self.sock.close()


# --- minimal NATS core client ----------------------------------------------------------------------
class NATS:
    def __init__(self, host: str, port: int, user: str, password: str, timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.buf = b""
        if not self._line().startswith(b"INFO "):
            raise AssertionError("NATS sent no INFO")
        opts = {"verbose": False, "pedantic": False, "user": user, "pass": password, "name": "bridge-test"}
        self.sock.sendall(b"CONNECT " + json.dumps(opts).encode() + b"\r\nPING\r\n")
        line = self._line()
        if line != b"PONG":
            raise AssertionError(f"NATS CONNECT failed: {line!r}")

    def _line(self) -> bytes:
        while b"\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("NATS closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\r\n", 1)
        return line

    def _exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("NATS closed the connection")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def sub(self, subject: str, sid: int) -> None:
        self.sock.sendall(f"SUB {subject} {sid}\r\nPING\r\n".encode())
        while self._line() != b"PONG":
            pass

    def pub(self, subject: str, payload: bytes) -> None:
        self.sock.sendall(f"PUB {subject} {len(payload)}\r\n".encode() + payload + b"\r\n")

    def next_msg(self, timeout: float) -> tuple[str, bytes] | None:
        self.sock.settimeout(timeout)
        try:
            while True:
                line = self._line()
                if line == b"PING":
                    self.sock.sendall(b"PONG\r\n")
                elif line.startswith(b"MSG "):  # MSG <subject> <sid> [reply] <bytes>
                    parts = line.split()
                    return parts[1].decode(), self._exact(int(parts[-1]) + 2)[:-2]
                elif line.startswith(b"HMSG "):  # HMSG <subject> <sid> [reply] <header bytes> <total bytes>
                    parts = line.split()
                    data = self._exact(int(parts[-1]) + 2)[:-2]
                    return parts[1].decode(), data[int(parts[-2]):]
                elif line.startswith(b"-ERR"):
                    raise AssertionError(f"NATS error: {line!r}")
        except socket.timeout:
            return None
        finally:
            self.sock.settimeout(10.0)

    def close(self) -> None:
        self.sock.close()


# --- start.sh ---------------------------------------------------------------------------------------
@unittest.skipUnless(shutil.which("sh"), "needs a POSIX sh")
class StartScriptTest(unittest.TestCase):
    def run_start(self, **env: str) -> tuple[subprocess.CompletedProcess, str]:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        (d / "base.conf").write_text("listener 1883\nallow_anonymous false\n", encoding="utf-8")
        bindir = d / "bin"
        bindir.mkdir()
        fake = bindir / "mosquitto"  # stands in for the broker: prints the config it was given
        fake.write_text('#!/bin/sh\n[ "$1" = -c ] && cat "$2"\n', encoding="utf-8", newline="\n")
        fake.chmod(0o755)
        e = {k: v for k, v in os.environ.items() if not k.startswith(("NATS_", "MOSQUITTO_"))}
        e.update({"PATH": str(bindir) + os.pathsep + e.get("PATH", ""),
                  "MOSQUITTO_BASE_CONF": str(d / "base.conf"), "MOSQUITTO_RUN_DIR": str(d / "run")})
        e.update(env)
        proc = subprocess.run(["sh", str(START_SH)], env=e, capture_output=True, text=True, timeout=30)
        return proc, proc.stdout

    def test_no_host_means_no_bridge(self):
        proc, conf = self.run_start()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("allow_anonymous false", conf)
        self.assertNotIn("connection ", conf)

    def test_bridge_lines(self):
        proc, conf = self.run_start(NATS_MQTT_HOST="nats.onemind-system.svc", NATS_MQTT_PORT="1884",
                                    NATS_MQTT_USERNAME="mosquitto-bridge", NATS_MQTT_PASSWORD="test-only")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = conf.splitlines()
        for want in ("connection onemind-nats", "address nats.onemind-system.svc:1884",
                     "bridge_protocol_version mqttv311", "try_private false", "notifications false",
                     "remote_username mosquitto-bridge", "remote_password test-only",
                     'topic # out 1 "" mqtt/up/'):
            self.assertIn(want, lines)
        self.assertFalse([ln for ln in lines if ln.startswith("topic # in")], "down direction is off by default")
        log = proc.stderr + "\n".join(ln for ln in lines if ln.startswith("start.sh:"))
        self.assertNotIn("test-only", log, "the password must not be logged")

    def test_down_direction(self):
        proc, conf = self.run_start(NATS_MQTT_HOST="nats", NATS_BRIDGE_DOWN="true")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('topic # in 1 "" mqtt/down/', conf.splitlines())
        self.assertNotIn("remote_username", conf)

    def test_refuses_values_that_add_config_lines(self):
        for env in ({"NATS_MQTT_HOST": "nats\nallow_anonymous true"},
                    {"NATS_MQTT_HOST": "nats:1"},
                    {"NATS_MQTT_HOST": "nats", "NATS_MQTT_PORT": "1883\nlistener 9"},
                    {"NATS_MQTT_HOST": "nats", "NATS_MQTT_PORT": "70000"},
                    {"NATS_MQTT_HOST": "nats", "NATS_MQTT_USERNAME": "u\nallow_anonymous true"},
                    {"NATS_MQTT_HOST": "nats", "NATS_MQTT_USERNAME": "u", "NATS_MQTT_PASSWORD": "p w"},
                    {"NATS_MQTT_HOST": "nats", "NATS_MQTT_PASSWORD": "lonely"},
                    {"NATS_MQTT_HOST": "nats", "NATS_BRIDGE_DOWN": "yes"}):
            with self.subTest(env=env):
                proc, conf = self.run_start(**env)
                self.assertEqual(proc.returncode, 64, proc.stderr)
                self.assertEqual(conf, "")


# --- end to end in Docker ----------------------------------------------------------------------------
def _docker_ok() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "info"], capture_output=True, timeout=60).returncode == 0


def _docker(*args: str, env: dict | None = None) -> str:
    proc = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=300, env=env)
    if proc.returncode != 0:
        raise AssertionError(f"docker {' '.join(args[:2])} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _host_port(container: str, port: str) -> int:
    return int(_docker("port", container, port).splitlines()[0].rsplit(":", 1)[1])


class BridgeRoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _docker_ok():
            if os.environ.get("MOSQUITTO_BRIDGE_E2E") == "required":
                raise AssertionError("MOSQUITTO_BRIDGE_E2E=required but Docker is not available")
            raise unittest.SkipTest("needs Docker (CI runs it: .github/workflows/ci.yml, job mqtt-bridge)")
        tag = secrets.token_hex(4)
        cls.net, cls.nats, cls.mosq = f"mqtt-bridge-{tag}", f"mqtt-bridge-nats-{tag}", f"mqtt-bridge-mosq-{tag}"
        cls.password = secrets.token_hex(16)  # throwaway, lives only for this test
        cls.dir = tempfile.mkdtemp()
        d = Path(cls.dir)
        # NATS's MQTT listener needs JetStream and (standalone) works without server_name; set one anyway.
        (d / "nats.conf").write_text(
            "server_name: bridge-test\nlisten: 0.0.0.0:4222\n"
            'jetstream { store_dir: "/tmp/nats-js" }\n'
            "mqtt { port: 1883 }\n"
            f'authorization {{ users: [ {{ user: bridge, password: "{cls.password}" }} ] }}\n',
            encoding="utf-8")
        # The shipped mosquitto.conf needs Dynamic Security users made on first start; the bridge does
        # not depend on them (bridges skip ACL checks: src/plugin_acl_check.c at v2.1.2), so the test
        # base config only opens the listener to the test client.
        (d / "base.conf").write_text("listener 1883\nallow_anonymous true\nlog_dest stdout\n", encoding="utf-8")
        shutil.copy(START_SH, d / "start.sh")
        os.chmod(d, 0o755)
        for f in d.iterdir():
            os.chmod(f, 0o644)
        try:
            _docker("network", "create", cls.net)
            _docker("run", "-d", "--name", cls.nats, "--network", cls.net, "--network-alias", "nats",
                    "-p", "127.0.0.1::4222", "-p", "127.0.0.1::1883", "-v", f"{cls.dir}:/conf:ro",
                    NATS_IMAGE, "-c", "/conf/nats.conf")
            env = dict(os.environ, NATS_MQTT_PASSWORD=cls.password)  # passed by name: not on the command line
            _docker("run", "-d", "--name", cls.mosq, "--network", cls.net,
                    "--user", "1883:1883", "--read-only", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges",
                    "--tmpfs", "/mosquitto/run:size=1m,mode=0700,uid=1883,gid=1883",
                    "-v", f"{cls.dir}:/conf:ro", "-p", "127.0.0.1::1883",
                    "-e", "MOSQUITTO_BASE_CONF=/conf/base.conf", "-e", "NATS_MQTT_HOST=nats",
                    "-e", "NATS_MQTT_PORT=1883", "-e", "NATS_MQTT_USERNAME=bridge", "-e", "NATS_MQTT_PASSWORD",
                    "-e", "NATS_BRIDGE_DOWN=true",
                    "--entrypoint", "/bin/sh", MOSQUITTO_IMAGE, "/conf/start.sh", env=env)
            cls.nats_port = _host_port(cls.nats, "4222/tcp")
            cls.nats_mqtt_port = _host_port(cls.nats, "1883/tcp")
            cls.mosq_port = _host_port(cls.mosq, "1883/tcp")
            cls._wait_tcp(cls.nats_port)
            cls._wait_tcp(cls.mosq_port)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        for name in (getattr(cls, "mosq", None), getattr(cls, "nats", None)):
            if name:
                if os.environ.get("MOSQUITTO_BRIDGE_E2E_LOGS"):
                    print(subprocess.run(["docker", "logs", name], capture_output=True, text=True).stdout)
                subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        if getattr(cls, "net", None):
            subprocess.run(["docker", "network", "rm", cls.net], capture_output=True)
        if getattr(cls, "dir", None):
            shutil.rmtree(cls.dir, True)

    @staticmethod
    def _wait_tcp(port: int, deadline: float = 60.0) -> None:
        end = time.monotonic() + deadline
        while time.monotonic() < end:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=2).close()
                return
            except OSError:
                time.sleep(0.5)
        raise AssertionError(f"port {port} never opened")

    def test_nats_refuses_mqtt5(self):
        """The gap: NATS's MQTT listener accepts protocol level 4 (3.1.1) only (server/mqtt.go v2.15.2)."""
        self._wait_tcp(self.nats_mqtt_port)
        with self.assertRaises(MQTTRefused):
            MQTT("127.0.0.1", self.nats_mqtt_port, "direct-v5", version=5).close()
        # ...while 3.1.1 is accepted (with the NATS user), so the listener itself is up.
        c = MQTT.__new__(MQTT)  # 3.1.1 with credentials: build the CONNECT by hand
        c.v5, c.next_id = False, 1
        c.sock = socket.create_connection(("127.0.0.1", self.nats_mqtt_port), timeout=10)
        flags = 0x02 | 0x80 | 0x40
        c._send(0x10, _str("MQTT") + bytes([4, flags]) + struct.pack("!H", 30)
                + _str("direct-v311") + _str("bridge") + _str(self.password))
        ptype, body = c._read()
        self.assertEqual((ptype, body[1]), (0x20, 0), "NATS should accept an MQTT 3.1.1 client")
        c.close()

    def test_mqtt5_round_trip_through_nats(self):
        """MQTT 5 -> Mosquitto -> bridge -> NATS subject -> NATS client -> bridge -> Mosquitto -> MQTT 5."""
        nats = NATS("127.0.0.1", self.nats_port, "bridge", self.password)
        self.addCleanup(nats.close)
        nats.sub("mqtt.up.>", 1)
        dev = MQTT("127.0.0.1", self.mosq_port, "mqtt5-device", version=5)
        self.addCleanup(dev.close)
        dev.subscribe("commands/#", qos=1)

        # Up: retry until the bridge has connected to NATS (its first connect can take a few seconds).
        token = secrets.token_hex(8).encode()
        got = None
        end = time.monotonic() + 60
        while got is None and time.monotonic() < end:
            dev.publish("sensors/kitchen/temp", b"21.5 " + token, qos=1)
            msg = nats.next_msg(timeout=1.0)
            while msg is not None and not msg[1].endswith(token):
                msg = nats.next_msg(timeout=0.2)
            got = msg
        self.assertIsNotNone(got, "the MQTT 5 message never reached NATS through the bridge")
        self.assertEqual(got, ("mqtt.up.sensors.kitchen.temp", b"21.5 " + token))

        # Down: the NATS side answers on mqtt.down.<topic>; the MQTT 5 client receives it as <topic>.
        back = None
        end = time.monotonic() + 60
        while back is None and time.monotonic() < end:
            nats.pub("mqtt.down.commands.kitchen.fan", b"on " + token)
            msg = dev.receive(timeout=1.0)
            while msg is not None and not msg[1].endswith(token):
                msg = dev.receive(timeout=0.2)
            back = msg
        self.assertIsNotNone(back, "the reply on NATS never reached the MQTT 5 client through the bridge")
        self.assertEqual(back, ("commands/kitchen/fan", b"on " + token))

        # No loop: the reply came in over the bridge, so it must not go back out to NATS as mqtt.up.*.
        echo = nats.next_msg(timeout=2.0)
        while echo is not None and not echo[1].startswith(b"on "):
            echo = nats.next_msg(timeout=0.5)
        self.assertIsNone(echo, f"a bridged-in message was sent back to NATS: {echo}")


if __name__ == "__main__":
    unittest.main()
