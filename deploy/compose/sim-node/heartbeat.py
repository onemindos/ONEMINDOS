#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Simulated OneMind node: publishes fake heartbeats so the dashboard shows
several machines while we only have a Mac (contract section 2).

It speaks the NATS text protocol directly (CONNECT / PUB / PING / PONG) with the
standard library only, so the container needs nothing but Python.

Environment:
  ONEMIND_NATS_URL   nats://[token@]host:4222    (default nats://nats:4222)
  SIM_NAME           hostname shown in the UI   (also seeds the stable node id)
  SIM_BOARD          rpi5 | jetson-orin | vm | x86_64-efi | ...
  SIM_ROLE           hub | node                 (default node)
  SIM_INTERVAL       seconds between heartbeats (default 10, contract section 1)
  SIM_HTTP_PORT      serve GET /api/v1/node here (default 7480; 0 disables)
  SIM_ONCE           1 = publish one heartbeat and exit (for tests)

Every value is fake and marked as simulated in agent_version; nothing about the
host (serials, MACs, IPs, user names) is read or sent.
"""

import hashlib
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

BOARDS = {
    "rpi5": dict(arch="arm64", cpu_model="Cortex-A76 (simulated)", cpus=4, mem=8064, disk=117.0, gpu=None,
                 os={"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
                 kernel="6.12.47+rpt-rpi-2712", secure_boot="unsupported"),
    "jetson-orin": dict(arch="arm64", cpu_model="Cortex-A78AE (simulated)", cpus=6, mem=7620, disk=234.0, gpu="Orin (simulated)",
                        os={"id": "ubuntu", "version_id": "22.04", "pretty": "Ubuntu 22.04.5 LTS (L4T, simulated)"},
                        kernel="5.15.148-tegra", secure_boot="unsupported"),
    "x86_64-efi": dict(arch="amd64", cpu_model="x86_64 (simulated)", cpus=4, mem=7800, disk=238.0, gpu=None,
                       os={"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
                       kernel="6.12.0-amd64", secure_boot="disabled"),
    "vm": dict(arch="arm64", cpu_model="Apple silicon VM (simulated)", cpus=4, mem=7900, disk=60.0, gpu=None,
               os={"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
               kernel="6.12.0-cloud-arm64", secure_boot="unknown"),
}
BOARDS["vm-do"] = dict(BOARDS["x86_64-efi"], cpu_model="DO droplet (simulated)", secure_boot="unsupported")


def node_id_for(seed):
    """Stable 12-hex id, same shape as onemindd's sha256(machine-id)[:12]."""
    return hashlib.sha256(("onemind-sim:" + seed).encode()).hexdigest()[:12]


def heartbeat(name, board, role, started):
    b = BOARDS.get(board, BOARDS["vm"])
    t = time.time()
    # gentle fake load so the numbers move a little
    wobble = int((t // 10) % 7) * 37
    return {
        "schema": "onemind.node.status/v1",
        "node_id": node_id_for(name),
        "hostname": name,
        "role": role,
        "board": board if board in BOARDS else "unknown",
        "arch": b["arch"],
        "os": b["os"],
        "kernel": b["kernel"],
        "cpu_model": b["cpu_model"],
        "cpus": b["cpus"],
        "mem_total_mb": b["mem"],
        "mem_available_mb": max(256, b["mem"] // 2 - wobble),
        "disk_total_gb": b["disk"],
        "disk_free_gb": round(b["disk"] * 0.7, 1),
        "tpm2": False,
        "secure_boot": b["secure_boot"],
        "k3s": {"present": True, "role": "server" if role == "hub" else "agent", "ready": True},
        "rauc": {"present": False, "booted_slot": None, "slots": []},
        "gpu": {"nvidia": b["gpu"] is not None, "model": b["gpu"]},
        "uptime_s": int(t - started),
        "agent_version": "0.1.0-sim",
        "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


class NatsPublisher:
    def __init__(self, url, name):
        u = urlsplit(url)
        if u.scheme not in ("nats", ""):
            raise ValueError("only nats:// URLs are supported, got %r" % url)
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 4222
        self.user = u.username
        self.password = u.password
        self.name = name
        self.sock = None
        self.buf = b""

    def connect(self):
        s = socket.create_connection((self.host, self.port), timeout=5)
        self.sock = s
        self.buf = b""
        info = self._readline()
        if not info.startswith(b"INFO "):
            raise ConnectionError("unexpected greeting from NATS: %r" % info[:80])
        opts = {"verbose": False, "pedantic": False, "name": "onemind-sim-" + self.name,
                "lang": "python-stdlib", "version": "0.1.0", "protocol": 1, "headers": False}
        if self.user and self.password is not None:
            opts.update(user=self.user, **{"pass": self.password})
        elif self.user:
            opts["auth_token"] = self.user
        s.sendall(b"CONNECT " + json.dumps(opts).encode() + b"\r\nPING\r\n")
        while True:
            line = self._readline()
            if line == b"PONG":
                return
            if line.startswith(b"-ERR"):
                raise ConnectionError(line.decode(errors="replace"))

    def _readline(self):
        while b"\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("NATS closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\r\n", 1)
        return line

    def _drain(self):
        """Answer server PINGs and surface errors without blocking."""
        self.sock.setblocking(False)
        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("NATS closed the connection")
                self.buf += chunk
        except BlockingIOError:
            pass
        finally:
            self.sock.setblocking(True)
            self.sock.settimeout(5)
        while b"\r\n" in self.buf:
            line, self.buf = self.buf.split(b"\r\n", 1)
            if line == b"PING":
                self.sock.sendall(b"PONG\r\n")
            elif line.startswith(b"-ERR"):
                raise ConnectionError(line.decode(errors="replace"))

    def publish(self, subject, payload):
        if self.sock is None:
            self.connect()
        self._drain()
        self.sock.sendall(b"PUB %s %d\r\n%s\r\nPING\r\n" % (subject.encode(), len(payload), payload))
        # wait for our PONG so a failed publish is noticed now, not later
        while True:
            line = self._readline()
            if line == b"PONG":
                return
            if line == b"PING":
                self.sock.sendall(b"PONG\r\n")
            elif line.startswith(b"-ERR"):
                raise ConnectionError(line.decode(errors="replace"))

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None


def serve_http(port, state):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.rstrip("/") == "/api/v1/node" and state.get("last"):
                body = json.dumps(state["last"]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
            else:
                body = b'{"error": "not_found", "message": "try /api/v1/node"}'
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    url = os.environ.get("ONEMIND_NATS_URL", "nats://nats:4222")
    name = os.environ.get("SIM_NAME", socket.gethostname())
    board = os.environ.get("SIM_BOARD", "vm")
    role = os.environ.get("SIM_ROLE", "node")
    interval = float(os.environ.get("SIM_INTERVAL", "10"))
    http_port = int(os.environ.get("SIM_HTTP_PORT", "7480"))
    once = os.environ.get("SIM_ONCE") == "1"
    started = time.time() - 3600  # pretend we booted an hour ago
    state = {}
    if http_port and not once:
        serve_http(http_port, state)
    pub = NatsPublisher(url, name)
    subject = "onemind.node.%s.status" % node_id_for(name)
    print("sim-node %s board=%s role=%s -> %s every %ss" % (name, board, role, subject, interval), flush=True)
    backoff = 1
    while True:
        hb = heartbeat(name, board, role, started)
        state["last"] = hb
        try:
            pub.publish(subject, json.dumps(hb, separators=(",", ":")).encode())
            backoff = 1
            if once:
                pub.close()
                return 0
        except (OSError, ConnectionError) as e:
            print("publish failed (%s); retrying in %ss" % (e, backoff), file=sys.stderr, flush=True)
            pub.close()
            if once:
                return 1
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
            continue
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
