# SPDX-License-Identifier: Apache-2.0
"""Tests for deploy/verify: verify.sh against a mock gateway, natscheck and the sim node.

Run: python3 -I deploy/verify/tests/test_verify.py -v
NATS tests need Docker (they start a throwaway nats container) and are skipped without it.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY_DIR = os.path.dirname(HERE)
DEPLOY = os.path.dirname(VERIFY_DIR)
VERIFY = os.path.join(VERIFY_DIR, "verify.sh")
NATSCHECK = os.path.join(VERIFY_DIR, "natscheck.py")
SIM = os.path.join(DEPLOY, "compose", "sim-node", "heartbeat.py")
MOCK = os.path.join(HERE, "mock_gateway.py")
OWNER = "owner-test-token-0001"
AGENT = "agent-test-token-0002"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_port(port, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.1)
    return False


class VerifyAgainstMock(unittest.TestCase):
    def run_verify(self, bug, agent=AGENT):
        port = free_port()
        mock = subprocess.Popen([sys.executable, "-I", MOCK, "--port", str(port), "--owner", OWNER, "--agent", AGENT, "--bug", bug],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(wait_port(port), "mock did not start")
            args = ["bash", VERIFY, "http://127.0.0.1:%d" % port, OWNER] + ([agent] if agent else [])
            env = dict(os.environ, VERIFY_TIMEOUT="20")
            p = subprocess.run(args, capture_output=True, text=True, timeout=120, env=env)
            return p.returncode, p.stdout + p.stderr
        finally:
            mock.terminate()
            mock.wait(5)

    def test_correct_hub_passes(self):
        code, out = self.run_verify("none")
        self.assertEqual(code, 0, out)
        self.assertIn("failed 0, skipped 0", out)
        self.assertIn("PASS  | agent approve -> 403 permission_denied", out)
        self.assertIn("PASS  | cleanup: app.remove -> succeeded", out)

    def test_rerun_on_same_hub_passes(self):
        """verify.sh removes its test app again, so a second run starts from the same state."""
        port = free_port()
        mock = subprocess.Popen([sys.executable, "-I", MOCK, "--port", str(port), "--owner", OWNER, "--agent", AGENT],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(wait_port(port), "mock did not start")
            for _ in range(2):
                p = subprocess.run(["bash", VERIFY, "http://127.0.0.1:%d" % port, OWNER, AGENT],
                                   capture_output=True, text=True, timeout=120)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        finally:
            mock.terminate()
            mock.wait(5)

    def test_agent_token_from_env(self):
        port = free_port()
        mock = subprocess.Popen([sys.executable, "-I", MOCK, "--port", str(port), "--owner", OWNER, "--agent", AGENT],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(wait_port(port), "mock did not start")
            p = subprocess.run(["bash", VERIFY, "http://127.0.0.1:%d" % port, OWNER], capture_output=True, text=True,
                               timeout=120, env=dict(os.environ, VERIFY_AGENT_TOKEN=AGENT))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        finally:
            mock.terminate()
            mock.wait(5)

    def test_missing_agent_token_is_incomplete(self):
        code, out = self.run_verify("none", agent=None)
        self.assertEqual(code, 3, out)
        self.assertIn("SKIP  | agent approve -> 403", out)

    def test_each_bug_is_caught(self):
        expect = {
            "agent-can-approve": "FAIL  | agent approve -> 403 permission_denied",
            "no-auth": "FAIL  | no token -> 401 unauthenticated",
            "no-expiry": "FAIL  | approve after expires_at -> 409 expired",
            "no-online-node": "FAIL  | GET /v1/nodes has >= 1 online node",
            "leak-ip": "FAIL  | nodes carry no serial/MAC/IP/user fields",
            "install-fails": "FAIL  | owner approve -> succeeded",
            "double-install": "FAIL  | install of an installed app -> 409 stale_precondition",
        }
        for bug, line in expect.items():
            with self.subTest(bug=bug):
                code, out = self.run_verify(bug)
                self.assertEqual(code, 1, out)
                self.assertIn(line, out)

    def test_usage(self):
        p = subprocess.run(["bash", VERIFY], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_unreachable_hub_fails(self):
        p = subprocess.run(["bash", VERIFY, "http://127.0.0.1:%d" % free_port(), OWNER, AGENT],
                           capture_output=True, text=True, timeout=120, env=dict(os.environ, VERIFY_TIMEOUT="2"))
        self.assertEqual(p.returncode, 1, p.stdout)


def docker_ok():
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


NATS_IMAGE = "nats:2.15.2-alpine@sha256:afae2fdbe2e326c65e1246cb83b9d05d319188734f3bd577ac8072daae78a10f"


@unittest.skipUnless(docker_ok(), "Docker not available")
class NatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.name = "onemind-verify-test-nats-%d" % cls.port
        subprocess.run(["docker", "run", "-d", "--rm", "--name", cls.name, "-p", "127.0.0.1:%d:4222" % cls.port,
                        NATS_IMAGE, "--auth", "s3cr3t-test-token"], check=True, capture_output=True)
        if not wait_port(cls.port, 30):
            raise RuntimeError("nats did not start")
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "rm", "-f", cls.name], capture_output=True)

    def nc(self, *args, timeout=60):
        return subprocess.run([sys.executable, "-I", NATSCHECK] + list(args), capture_output=True, text=True, timeout=timeout)

    def test_ping_with_and_without_token(self):
        ok = self.nc("ping", "nats://s3cr3t-test-token@127.0.0.1:%d" % self.port)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("auth_required=True", ok.stdout)
        bad = self.nc("ping", "nats://wrong@127.0.0.1:%d" % self.port)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("Authorization", bad.stderr)

    def test_sim_heartbeat_reaches_watcher(self):
        url = "nats://s3cr3t-test-token@127.0.0.1:%d" % self.port
        watcher = subprocess.Popen([sys.executable, "-I", NATSCHECK, "watch", url, "--count", "2", "--timeout", "20"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(1.0)
        for name, board in (("t-pi5", "rpi5"), ("t-jetson", "jetson-orin")):
            env = dict(os.environ, ONEMIND_NATS_URL=url, SIM_NAME=name, SIM_BOARD=board, SIM_ONCE="1", SIM_HTTP_PORT="0")
            p = subprocess.run([sys.executable, "-I", SIM], env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(p.returncode, 0, p.stderr)
        out, err = watcher.communicate(timeout=30)
        self.assertEqual(watcher.returncode, 0, out + err)
        self.assertIn("rpi5", out)
        self.assertIn("jetson-orin", out)


class SimHeartbeatShape(unittest.TestCase):
    def test_heartbeat_matches_contract_section_2(self):
        sys.path.insert(0, os.path.dirname(SIM))
        import heartbeat  # noqa
        keys = ["schema", "node_id", "hostname", "role", "board", "arch", "os", "kernel", "cpu_model", "cpus",
                "mem_total_mb", "mem_available_mb", "disk_total_gb", "disk_free_gb", "tpm2", "secure_boot", "k3s",
                "rauc", "gpu", "uptime_s", "agent_version", "observed_at"]
        for board in ("rpi5", "jetson-orin", "vm", "vm-do", "x86_64-efi"):
            hb = heartbeat.heartbeat("n1", board, "node", time.time() - 5)
            self.assertEqual(list(hb.keys()), keys)
            self.assertEqual(hb["schema"], "onemind.node.status/v1")
            self.assertEqual(len(hb["node_id"]), 12)
            self.assertIn(hb["secure_boot"], ("enabled", "disabled", "unsupported", "unknown"))
            self.assertIn(hb["board"], ("x86_64-efi", "arm64-efi", "rpi5", "jetson-orin", "vm", "vm-do", "unknown"))
            self.assertEqual(set(hb["os"]), {"id", "version_id", "pretty"})
        self.assertEqual(heartbeat.node_id_for("a"), heartbeat.node_id_for("a"))
        self.assertNotEqual(heartbeat.node_id_for("a"), heartbeat.node_id_for("b"))


if __name__ == "__main__":
    unittest.main()
