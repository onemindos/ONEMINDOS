# SPDX-License-Identifier: Apache-2.0
"""Daily-driver gate kit (lab-kits/LT-X86-DD/dd-gate.py, #234): stage verdicts against a local HTTP stub,
a fake ssh/scp on PATH and local listening sockets. No box needed: this proves the kit, not the box."""
import importlib.util, json, os, socket, stat, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("ddgate", os.path.join(ROOT, "lab-kits", "LT-X86-DD", "dd-gate.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

OS_OK = 'ID=debian\nVERSION_ID="13"\n'
FAKE_SSH = """#!/bin/sh
for last; do :; done
[ -z "$FAKE_LOG" ] || printf '%s\\n' "$last" >> "$FAKE_LOG"
case "$last" in
  "cat /etc/os-release") printf '%s' "$FAKE_OS";;
  "findmnt -no OPTIONS /") echo "$FAKE_ROOT";;
  "rauc status") echo "    boot status: $FAKE_RAUC";;
  *perf.py\\ load*) [ "$FAKE_LOAD" = ok ] || { echo "p95 over" >&2; exit 1; };;
  *) ;;
esac
"""


class Stub(BaseHTTPRequestHandler):
    passkeys = []

    def do_GET(self):
        if self.path == "/healthz":
            body = b'{"ok":true}'
        elif self.path == "/v1/auth/passkeys" and self.headers.get("Authorization") == "Bearer tok":
            body = json.dumps(Stub.passkeys).encode()
        else:
            self.send_response(401), self.end_headers()
            return
        self.send_response(200), self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def args(**kw):
    d = dict(host="root@127.0.0.1", base_url=None, ca=None, token_file=None, scan_host="127.0.0.1", allow_ports=[22, 80, 443],
             g1_result=None, power_results=None, restore_results=None, cycles=20, ready_timeout=3, scan_timeout=0.3,
             load_timeout=30, label="t", stage=",".join(g.STAGES), out="x")
    d.update(kw)
    return type("A", (), d)()


class DD(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.t = t.name
        os.makedirs(self.t + "/bin")
        for n in ("ssh", "scp"):
            p = f"{self.t}/bin/{n}"
            with open(p, "w") as f:
                f.write(FAKE_SSH)
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        self.env = dict(PATH=self.t + "/bin:" + os.environ["PATH"], FAKE_OS=OS_OK, FAKE_ROOT="ro,relatime", FAKE_RAUC="good", FAKE_LOAD="ok")
        self.old = dict(os.environ)
        os.environ.update(self.env)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.old)))
        self.srv = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close), self.addCleanup(self.srv.shutdown)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        Stub.passkeys = []

    def w(self, name, obj, lines=False):
        p = f"{self.t}/{name}"
        with open(p, "w") as f:
            f.write("\n".join(json.dumps(o) for o in obj) + "\n" if lines else json.dumps(obj))
        return p

    def stage(self, fn, **kw):
        return fn(g.Ctx(args(base_url=self.url, **kw)))

    def test_install_pass_and_each_failure(self):
        self.assertEqual(self.stage(g.st_install)["verdict"], g.P)
        for k, v, frag in (("FAKE_OS", 'ID=ubuntu\nVERSION_ID="24.04"\n', "debian 13"), ("FAKE_ROOT", "rw,relatime", "read-only"), ("FAKE_RAUC", "bad", "RAUC")):
            os.environ[k] = v
            r = self.stage(g.st_install)
            self.assertEqual(r["verdict"], g.F, k)
            self.assertIn(frag, r["detail"])
            os.environ[k] = self.env[k]

    def test_install_down_is_fail_not_pass(self):
        r = g.st_install(g.Ctx(args(base_url="http://127.0.0.1:1", ready_timeout=1)))
        self.assertEqual(r["verdict"], g.F)

    def test_install_without_inputs_is_pending(self):
        self.assertEqual(g.st_install(g.Ctx(args(base_url=None, host=None)))["verdict"], g.W)

    def test_passkey(self):
        tf = self.w("tok", "tok")
        open(tf, "w").write("tok")
        self.assertEqual(self.stage(g.st_passkey, token_file=tf)["verdict"], g.W)
        Stub.passkeys = [{"id": "a"}]
        self.assertEqual(self.stage(g.st_passkey, token_file=tf)["verdict"], g.P)
        open(tf, "w").write("wrong")
        self.assertEqual(self.stage(g.st_passkey, token_file=tf)["verdict"], g.F)

    def test_rollback_from_g1_result(self):
        ok = self.w("a.json", dict(steps=[dict(id="good-commit", verdict="PASS"), dict(id="bad-k3s", verdict="PASS")]))
        self.assertEqual(self.stage(g.st_rollback, g1_result=ok)["verdict"], g.P)
        mid = self.w("b.json", dict(steps=[dict(id="a", verdict="PASS"), dict(id="b", verdict="PENDING")]))
        self.assertEqual(self.stage(g.st_rollback, g1_result=mid)["verdict"], g.W)
        bad = self.w("c.json", dict(steps=[dict(id="a", verdict="PASS"), dict(id="bad-hang", verdict="FAIL")]))
        r = self.stage(g.st_rollback, g1_result=bad)
        self.assertEqual(r["verdict"], g.F)
        self.assertIn("bad-hang", r["detail"])
        self.assertEqual(self.stage(g.st_rollback, g1_result=self.w("d.json", dict(steps=[])))["verdict"], g.W)

    def test_powerpull_counts(self):
        plan = dict(kind="plan", cycles=20)
        cyc = lambda n, v="PASS": [dict(phase="x", verdict=v) for _ in range(n)]
        self.assertEqual(self.stage(g.st_powerpull, power_results=self.w("p", [plan] + cyc(20), True))["verdict"], g.P)
        self.assertEqual(self.stage(g.st_powerpull, power_results=self.w("p", [plan] + cyc(12), True))["verdict"], g.W)
        self.assertEqual(self.stage(g.st_powerpull, power_results=self.w("p", [plan] + cyc(19) + cyc(1, "FAIL"), True))["verdict"], g.F)

    def test_scan_finds_only_listening_ports(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0)), s.listen()
        self.addCleanup(s.close)
        port = s.getsockname()[1]
        self.assertEqual(g.scan("127.0.0.1", [port, 1], 0.3), [port])

    def fake_scan(self, ports):
        orig = g.scan
        g.scan = lambda addr, probe, t, workers=128: [p for p in ports if p in probe]
        self.addCleanup(lambda: setattr(g, "scan", orig))

    def test_portscan_verdicts(self):
        self.fake_scan([22, 443])
        self.assertEqual(g.st_portscan(g.Ctx(args()))["verdict"], g.P)
        self.fake_scan([22, 443, 6443])
        r = g.st_portscan(g.Ctx(args()))
        self.assertEqual((r["verdict"], "6443" in r["detail"]), (g.F, True))
        self.fake_scan([22])
        r = g.st_portscan(g.Ctx(args()))
        self.assertEqual((r["verdict"], "443" in r["detail"]), (g.F, True))

    def test_restore_budget(self):
        mk = lambda v, s: self.w("r.json", dict(verdict=v, restore_seconds=s, reasons=[]))
        self.assertEqual(self.stage(g.st_restore, restore_results=mk("PASS", 1200))["verdict"], g.P)
        self.assertEqual(self.stage(g.st_restore, restore_results=mk("OVER_BUDGET", 3700))["verdict"], g.F)
        self.assertEqual(self.stage(g.st_restore, restore_results=mk("PASS", 3700))["verdict"], g.F)

    def test_load_via_ssh(self):
        self.assertEqual(self.stage(g.st_load)["verdict"], g.P)
        os.environ["FAKE_LOAD"] = "bad"
        self.assertEqual(self.stage(g.st_load)["verdict"], g.F)

    def test_load_removes_probe_principal_and_token_even_on_failure(self):
        for mode in ("ok", "bad"):
            log = f"{self.t}/log-{mode}"
            os.environ.update(FAKE_LOG=log, FAKE_LOAD=mode)
            self.stage(g.st_load)
            cmds = open(log).read().splitlines()
            self.assertIn("perf.py token", " ".join(cmds))
            self.assertEqual(cmds[-1], g.LOAD_CLEANUP)
            self.assertIn("perf-probe", g.LOAD_CLEANUP)
            self.assertIn("rm -rf /tmp/dd-gate", g.LOAD_CLEANUP)

    def test_scrub_masks_addresses(self):
        ip, mac, tn = ".".join(["10", "1", "2", "3"]), ":".join(["aa", "bb", "cc", "dd", "ee", "ff"]), "host." + "ts" + ".net"
        out = g.scrub(f"root@{ip} {mac} /" + "Users" + f"/someone/x {tn}", ip)
        for leak in (ip, "aa:bb", "someone", "ts.net"):
            self.assertNotIn(leak, out)

    def test_report_and_exit_codes(self):
        out = self.t + "/ev"
        rc = g.main(["run", "--host", "root@127.0.0.1", "--base-url", self.url, "--stage", "install", "--out", out, "--ready-timeout", "3"])
        self.assertEqual(rc, 0)
        doc = json.load(open(out + "/dd-gate.json"))
        self.assertTrue(doc["summary"]["all_passed"])
        self.assertIn("| install | PASS |", open(out + "/DD-GATE.md").read())
        rc = g.main(["run", "--stage", "powerpull", "--out", out])
        self.assertEqual(rc, 3)  # pending, never a pass
        self.assertFalse(json.load(open(out + "/dd-gate.json"))["summary"]["all_passed"])
        self.assertEqual(g.main(["run", "--stage", "nope", "--out", out]), 2)

    def test_crash_is_fail(self):
        g.RUN["install"], orig = (lambda c: 1 / 0), g.RUN["install"]
        self.addCleanup(lambda: g.RUN.__setitem__("install", orig))
        rows = g.run_all(args(), ["install"])
        self.assertEqual(rows[0]["verdict"], g.F)


if __name__ == "__main__":
    unittest.main()
