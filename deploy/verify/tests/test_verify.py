# SPDX-License-Identifier: Apache-2.0
"""Tests for deploy/verify (ported from PR #27, adapted to main's verify.sh and NATS auth).

verify.sh runs against mock_gateway.py (an imitation hub with a tiny NATS): a correct hub passes
with nothing skipped, and every broken hub fails on the right line. natscheck.py runs against the
mock NATS (no auth, token, nkey) and, when Docker is available, a real nats-server with a token
and TLS (certificates generated at test time).

  python3 -I deploy/verify/tests/test_verify.py -v
"""

import concurrent.futures
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFY_DIR = os.path.dirname(HERE)
VERIFY = os.path.join(VERIFY_DIR, "verify.sh")
NATSCHECK = os.path.join(VERIFY_DIR, "natscheck.py")
MOCK = os.path.join(HERE, "mock_gateway.py")
OWNER = "owner-test-" + os.urandom(8).hex()   # made at test time, never real
AGENT = "agent-test-" + os.urandom(8).hex()
NATS_IMAGE = "docker.io/library/nats:2.15.2-alpine@sha256:afae2fdbe2e326c65e1246cb83b9d05d319188734f3bd577ac8072daae78a10f"

# bug -> the verify.sh line that must FAIL (regex)
EXPECT = {
    "no-auth": r"FAIL  §3 no token -> 401 unauthenticated",
    "agent-can-approve": r"FAIL  §3 agent approve -> 403 permission_denied",
    "no-expiry": r"FAIL  §3 approving after expires_at -> 409 expired",
    "deny-not-cancelled": r"FAIL  §3 owner deny -> cancelled",
    "no-idempotency": r"FAIL  §3 same idempotency key -> 200, same action",
    "params-changed": r"FAIL  §3 GET /v1/actions/\{id\} shows the exact params",
    "install-fails": r"FAIL  §3 owner approve ended in 'failed'",
    "no-online-node": r"FAIL  §3 at least one node is online",
    "leak-ip": r"FAIL  §2 no MAC, serial, IP, user name or machine-id in node data",
    "bad-board": r"FAIL  §2 board and secure_boot use the contract values",
    "owner-on-mcp": r"FAIL  §11.3 /mcp with an owner token should be 403",
    "mcp-approve-tool": r"FAIL  §11.3 no approve or deny tool",
    "bad-audit-chain": r"FAIL  §3 \d+ audit lines on NATS onemind.audit",
    "bad-heartbeat": r"FAIL  §1/§2 heartbeat on onemind\.node\.<node_id>\.status",
    "no-dashboard": r"FAIL  §3 dashboard at /",
}


class Mock:
    """mock_gateway.py in a subprocess; .http and .nats are its ports."""

    def __init__(self, *args):
        self.p = subprocess.Popen([sys.executable, "-I", MOCK, "--owner", OWNER, "--agent", AGENT, *args],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        line = self.p.stdout.readline()
        m = re.match(r"ready http=(\d+) nats=(\d+)", line)
        if not m:
            self.stop()
            raise RuntimeError("mock did not start: %r" % line)
        self.http, self.nats = int(m.group(1)), int(m.group(2))

    def stop(self):
        self.p.terminate()
        self.p.wait(10)
        self.p.stdout.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


def run_verify(mock, *extra, owner=True, agent=True, env=None, nats=True):
    with tempfile.TemporaryDirectory() as d:
        args = ["bash", VERIFY, "http://127.0.0.1:%d" % mock.http]
        for name, tok, flag in (("o", OWNER, owner), ("a", AGENT, agent)):
            if flag:
                path = os.path.join(d, name + ".token")
                with open(path, "w") as f:
                    f.write(tok)
                os.chmod(path, 0o600)
                args += ["--token-file" if name == "o" else "--agent-token-file", path]
        args += ["--nats", "nats://127.0.0.1:%d" % mock.nats if nats else "none", *extra]
        p = subprocess.run(args, capture_output=True, text=True, timeout=300, env=dict(os.environ, **(env or {})))
        return p.returncode, p.stdout + p.stderr


class VerifyAgainstMock(unittest.TestCase):
    def test_correct_hub_passes_with_nothing_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            audit = os.path.join(d, "audit.jsonl")
            with Mock("--audit-file", audit) as m:
                code, out = run_verify(m, "--strict", "--audit-file", audit)
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"Summary: \d+ passed, 0 failed, 0 skipped")
        for line in ("PASS  §3 agent approve -> 403 permission_denied", "PASS  §11.3 no approve or deny tool",
                     "PASS  §3 app.remove approved -> succeeded", "PASS  §3 audit file hash chain intact"):
            self.assertIn(line, out)

    def test_rerun_on_the_same_hub_passes(self):
        """verify.sh removes its test app again, so a second run starts from the same state."""
        with Mock() as m:
            for _ in range(2):
                code, out = run_verify(m)
                self.assertEqual(code, 0, out)

    def test_without_token_only_open_checks_run(self):
        with Mock() as m:
            code, out = run_verify(m, owner=False, agent=False)
        self.assertEqual(code, 0, out)
        self.assertIn("SKIP  authenticated checks (no --token)", out)
        self.assertIn("PASS  §3 no token -> 401 unauthenticated", out)

    def test_agent_token_from_environment(self):
        with Mock() as m:
            code, out = run_verify(m, agent=False, env={"ONEMIND_AGENT_TOKEN": AGENT})
        self.assertEqual(code, 0, out)
        self.assertIn("PASS  §3 agent deny -> 403 permission_denied", out)

    def test_each_broken_hub_is_caught(self):
        def one(bug):
            with Mock("--bug", bug) as m:
                return bug, run_verify(m)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(one, sorted(EXPECT)))
        for bug, (code, out) in results:
            with self.subTest(bug=bug):
                self.assertEqual(code, 1, out)
                self.assertRegex(out, EXPECT[bug])

    def test_hostile_ids_from_the_hub_are_never_run(self):
        """#26/#27 review: a hub-supplied id pasted into eval() ran code. It must stay data."""
        with tempfile.TemporaryDirectory() as d:
            marker = os.path.join(d, "pwned")
            with Mock("--bug", "hostile-ids", "--marker", marker) as m:
                code, out = run_verify(m)
            self.assertFalse(os.path.exists(marker), "verify.sh ran code supplied by the hub:\n" + out)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL  §3 first node id is not a valid node id", out)

    def test_tokens_never_reach_a_command_line(self):
        real = shutil.which("curl")
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "argv.log")
            shim = os.path.join(d, "curl")
            with open(shim, "w") as f:
                f.write('#!/bin/sh\nprintf "%%s\\n" "$*" >> "%s"\nexec "%s" "$@"\n' % (log, real))
            os.chmod(shim, stat.S_IRWXU)
            with Mock() as m:
                code, out = run_verify(m, env={"PATH": d + os.pathsep + os.environ["PATH"]})
            with open(log) as f:
                argv = f.read()
        self.assertEqual(code, 0, out)
        self.assertIn("/v1/actions", argv)
        self.assertNotIn(OWNER, argv)
        self.assertNotIn(AGENT, argv)

    def test_usage_errors(self):
        self.assertEqual(subprocess.run(["bash", VERIFY], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run(["bash", VERIFY, "http://127.0.0.1:1", "--app", "Bad;App"],
                                        capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run(["bash", VERIFY, "http://127.0.0.1:1", "--token-file", "/nonexistent"],
                                        capture_output=True).returncode, 2)

    def test_unreachable_hub_fails(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        p = subprocess.run(["bash", VERIFY, "http://127.0.0.1:%d" % port, "--nats", "none"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 1, p.stdout)


def natscheck(*args, timeout=60):
    p = subprocess.run([sys.executable, "-I", NATSCHECK, *args], capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


class NatscheckAgainstMock(unittest.TestCase):
    def test_ping_reports_no_auth(self):
        with Mock() as m:
            code, out = natscheck("ping", "nats://127.0.0.1:%d" % m.nats)
        self.assertEqual(code, 0, out)
        self.assertIn("auth_required=False", out)

    def test_token_auth_and_no_credentials_in_output(self):
        tok = "nats-test-" + os.urandom(6).hex()
        with Mock("--nats-token", tok) as m, tempfile.TemporaryDirectory() as d:
            code, out = natscheck("ping", "nats://%s@127.0.0.1:%d" % (tok, m.nats))
            self.assertEqual(code, 0, out)
            self.assertIn("auth_required=True", out)
            self.assertNotIn(tok, out)
            code, out = natscheck("ping", "nats://wrong-%s@127.0.0.1:%d" % (tok, m.nats))
            self.assertEqual(code, 1, out)
            self.assertIn("Authorization Violation", out)
            self.assertNotIn(tok, out)
            env = os.path.join(d, "onemindd.env")
            with open(env, "w") as f:
                f.write("# test\nONEMIND_NATS_URL=nats://%s@127.0.0.1:%d\nONEMIND_NODE_ROLE=node\n" % (tok, m.nats))
            code, out = natscheck("ping", "--env-file", env)
            self.assertEqual(code, 0, out)

    def test_nkey_server_is_explained(self):
        with Mock("--nats-nkey") as m:
            code, out = natscheck("ping", "nats://127.0.0.1:%d" % m.nats)
        self.assertEqual(code, 1, out)
        self.assertIn("nkey", out)

    def test_watch_counts_valid_heartbeats(self):
        with Mock() as m:
            code, out = natscheck("watch", "nats://127.0.0.1:%d" % m.nats, "--count", "2", "--timeout", "10")
        self.assertEqual(code, 0, out)
        self.assertIn("rpi5", out)

    def test_watch_rejects_heartbeats_for_another_node(self):
        with Mock("--bug", "bad-heartbeat") as m:
            code, out = natscheck("watch", "nats://127.0.0.1:%d" % m.nats, "--timeout", "3")
        self.assertEqual(code, 1, out)
        self.assertIn("invalid heartbeat", out)

    def test_leafz(self):
        state = {"n": 1}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                body = json.dumps({"leafnodes": state["n"], "leafs": [{"name": "hub"}] * state["n"]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            mon = "127.0.0.1:%d" % srv.server_address[1]
            code, out = natscheck("leafz", "--monitor", mon)
            self.assertEqual(code, 0, out)
            state["n"] = 0
            code, out = natscheck("leafz", "--monitor", mon)
            self.assertEqual(code, 1, out)
        finally:
            srv.shutdown()
            srv.server_close()


def docker_ok():
    return shutil.which("docker") and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def wait_port(port, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


@unittest.skipUnless(docker_ok() and shutil.which("openssl"), "needs Docker and openssl")
class NatscheckAgainstRealNats(unittest.TestCase):
    """nats-server 2.15.2 (the pinned compose image) with a token and TLS from a throwaway CA."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        os.chmod(cls.dir, 0o755)
        cls.token = "nats-test-" + os.urandom(8).hex()
        sh = lambda *a: subprocess.run(a, cwd=cls.dir, check=True, capture_output=True)
        sh("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.pem", "-days", "1",
           "-subj", "/CN=onemind-test-ca", "-addext", "basicConstraints=critical,CA:TRUE",
           "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        sh("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "srv.key", "-out", "srv.csr", "-subj", "/CN=127.0.0.1")
        with open(os.path.join(cls.dir, "ext.cnf"), "w") as f:
            f.write("subjectAltName=IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                    "extendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n")
        sh("openssl", "x509", "-req", "-in", "srv.csr", "-CA", "ca.pem", "-CAkey", "ca.key", "-CAcreateserial",
           "-out", "srv.pem", "-days", "1", "-extfile", "ext.cnf")
        with open(os.path.join(cls.dir, "nats.conf"), "w") as f:
            f.write('listen: 0.0.0.0:4222\nauthorization { token: "%s" }\n'
                    'tls { cert_file: "/conf/srv.pem", key_file: "/conf/srv.key" }\n' % cls.token)
        for name in os.listdir(cls.dir):
            os.chmod(os.path.join(cls.dir, name), 0o644)
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        cls.name = "onemind-natscheck-test-%d" % cls.port
        subprocess.run(["docker", "run", "-d", "--rm", "--name", cls.name, "-p", "127.0.0.1:%d:4222" % cls.port,
                        "-v", cls.dir + ":/conf:ro", NATS_IMAGE, "-c", "/conf/nats.conf"], check=True, capture_output=True)
        if not wait_port(cls.port):
            raise RuntimeError("nats did not start")
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        subprocess.run(["docker", "rm", "-f", cls.name], capture_output=True)
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_tls_and_token(self):
        ca = os.path.join(self.dir, "ca.pem")
        code, out = natscheck("ping", "tls://%s@127.0.0.1:%d" % (self.token, self.port), "--ca", ca)
        self.assertEqual(code, 0, out)
        self.assertIn("tls=True, auth_required=True", out)
        self.assertNotIn(self.token, out)
        # nats:// to a server that requires TLS: natscheck upgrades, as NATS clients do.
        code, out = natscheck("ping", "nats://%s@127.0.0.1:%d" % (self.token, self.port), "--ca", ca)
        self.assertEqual(code, 0, out)

    def test_wrong_token_and_unknown_ca_fail(self):
        ca = os.path.join(self.dir, "ca.pem")
        code, out = natscheck("ping", "tls://wrong@127.0.0.1:%d" % self.port, "--ca", ca)
        self.assertEqual(code, 1, out)
        self.assertIn("Authorization", out)
        code, out = natscheck("ping", "tls://%s@127.0.0.1:%d" % (self.token, self.port))
        self.assertEqual(code, 1, out)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", out)


if __name__ == "__main__":
    unittest.main()
