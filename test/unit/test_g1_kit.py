# SPDX-License-Identifier: Apache-2.0
"""G1-on-metal kit (lab-kits/G1/g1-run.py, #215): the sequencing, resume and verdict logic against a fake
`rauc` and `systemctl` on PATH. No real hardware: this proves the kit, not G1."""
import json, os, stat, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIT = os.path.join(ROOT, "lab-kits", "G1", "g1-run.py")
FAKE_RAUC = """#!/bin/sh
# fake rauc: `install` fails for wrong-key/plain-good, else writes the trial marker for the other slot.
case "$1" in
  --version) echo "rauc 1.15.2"; exit 0;;
  install) case "$2" in
    *wrong-key*) echo "Signature verification failed" >&2; exit 1;;
    *plain-good*) echo "Bundle format 'plain' not allowed" >&2; exit 1;;
    esac
    s=$(sed -n 's/.*rauc\\.slot=\\([A-Z]\\).*/\\1/p' "$ONEMIND_CMDLINE"); o=A; [ "$s" = A ] && o=B
    echo "$o 9" > "$ONEMIND_PENDING"; echo installed; exit 0;;
esac
exit 0
"""
FAKE_SYSTEMCTL = "#!/bin/sh\necho \"$@\" >> \"$FAKE_LOG\"\nexit 0\n"


def wr(path, text, mode="w"):
    with open(path, mode) as f:
        f.write(text)


def rd(path):
    with open(path) as f:
        return f.read()


class Kit(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.t = t.name
        j = lambda *p: os.path.join(self.t, *p)
        os.makedirs(j("bin")), os.makedirs(j("bundles")), os.makedirs(j("units")), os.makedirs(j("proc"))
        for n, body in (("rauc", FAKE_RAUC), ("systemctl", FAKE_SYSTEMCTL)):
            wr(j("bin", n), body)
            os.chmod(j("bin", n), 0o755)
        for b in ("good", "wrong-key", "plain-good", "bad-k3s", "bad-noagent", "bad-boot", "bad-hang"):
            wr(j("bundles", b + ".raucb"), "x")
        self.cmd, self.gate, self.pend, self.log = j("cmdline"), j("gate.log"), j("pending"), j("calls.log")
        wr(j("proc", "meminfo"), "MemTotal: 3984000 kB\nMemAvailable: 2900000 kB\n")
        wr(j("proc", "diskstats"), "259 0 nvme0n1 1 0 2 0 3 0 2048000 0 0 0 0\n")
        self.env = dict(os.environ, PATH=j("bin") + os.pathsep + os.environ["PATH"], ONEMIND_LAB_NOROOT="1",
                        ONEMIND_LAB_ROOT=j("lab"), ONEMIND_GATE_LOG=self.gate, ONEMIND_PENDING=self.pend,
                        ONEMIND_CMDLINE=self.cmd, ONEMIND_PROC=j("proc"), ONEMIND_UNIT_DIR=j("units"),
                        ONEMIND_HEALTHZ_URL="http://127.0.0.1:9/healthz", FAKE_LOG=self.log)
        self.boot("A", "RESULT committed-boot slot=A version=1")
        self.bundles, self.lab = j("bundles"), j("lab")

    def boot(self, slot, *gate):
        """What a reboot does on the real box: new cmdline, the gate appends its verdict, trial marker cleared."""
        wr(self.cmd, f"root=x rauc.slot={slot} quiet\n")
        with open(self.gate, "a") as f:
            for g in gate:
                f.write(f"HEALTH-GATE: 12:00:00 {g}\n")
        if gate and not gate[-1].startswith("RESULT fell-back") or gate:
            open(self.pend, "w").close()

    def kit(self, *a):
        return subprocess.run([sys.executable, "-I", KIT, *a, "--bundles", self.bundles], capture_output=True, text=True, env=self.env)

    def result(self):
        return json.loads(rd(os.path.join(self.lab, "result.json")))

    def reboots(self):
        return rd(self.log).count("reboot") if os.path.exists(self.log) else 0

    def test_dry_run_changes_nothing(self):
        r = self.kit("run", "--dry-run", "--rounds", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("rauc install", r.stdout)
        self.assertIn("rollback-02", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.lab, "result.json")))
        self.assertEqual(self.reboots(), 0)

    def test_preflight_refuses_missing_bundle(self):
        os.remove(os.path.join(self.bundles, "bad-hang.raucb"))
        r = self.kit("run")
        self.assertEqual(r.returncode, 2)
        self.assertIn("bundle_bad-hang", r.stderr)
        self.assertEqual(self.reboots(), 0)

    def test_full_sequence_passes_and_never_claims_g1(self):
        r = self.kit("run", "--rounds", "2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.reboots(), 1)                       # refusals done, good installed, rebooting
        self.assertEqual(self.result()["steps"][0]["verdict"], "PASS")
        self.assertEqual(self.kit("run").returncode, 3)           # not rebooted yet: still waiting, no second install
        self.boot("B", "RESULT mark-good slot=B version=9 after 41s")
        self.assertEqual(self.kit("run", "--rounds", "2").returncode, 0)   # good ok; confirm step reboots
        self.boot("B", "RESULT committed-boot slot=B version=9")
        for slot_new, kind in (("A", "markbad"), ("A", "markbad"), ("A", "fellback"), ("A", "fellback"), ("A", "markbad"), ("A", "markbad")):
            self.assertEqual(self.kit("run").returncode, 0)       # installs the next bundle, reboots
            if kind == "markbad":
                self.boot(slot_new, f"RESULT mark-bad slot={slot_new} version=9 verdict=image-bad after 300s")
                self.boot("B", "RESULT committed-boot slot=B version=9")
            else:
                self.boot("B", "RESULT fell-back slot=B version=9; slot A (v9) marked bad verdict=image-bad, never retried")
        r = self.kit("run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.result()
        self.assertEqual([s["verdict"] for s in res["steps"]], ["PASS"] * 10)
        self.assertTrue(res["summary"]["all_automated_checks_passed"])
        self.assertIn("NOT ASSERTED", res["summary"]["g1_verdict"])
        self.assertIn("after 41s", res["steps"][2]["detail"])
        rep = self.kit("report")
        self.assertEqual(rep.returncode, 0, rep.stderr)
        text = rd(os.path.join(self.lab, "G1-RECORD.md"))
        self.assertIn("FOUNDER: PASS / FAIL / BLOCKED", text)
        self.assertNotIn("{{", text)

    def test_committing_a_bad_slot_fails_the_run(self):
        self.assertEqual(self.kit("run", "--rounds", "1").returncode, 0)
        self.boot("B", "RESULT mark-good slot=B version=9 after 41s")
        self.kit("run", "--rounds", "1"), self.boot("B", "RESULT committed-boot slot=B version=9")
        self.assertEqual(self.kit("run", "--rounds", "1").returncode, 0)          # bad-k3s installed
        self.boot("A", "RESULT mark-good slot=A version=9 after 5s")              # the gate wrongly commits it
        r = self.kit("run", "--rounds", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("COMMITTED A BAD SLOT", r.stdout)
        res = self.result()
        self.assertEqual(res["steps"][4]["verdict"], "FAIL")
        self.assertFalse(res["summary"]["all_automated_checks_passed"])

    def test_wrong_key_that_installs_is_a_failure(self):
        wr(os.path.join(self.t, "bin", "rauc"), FAKE_RAUC.replace("*wrong-key*) echo", "*zzz*) echo"))
        r = self.kit("run", "--rounds", "1")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.result()["steps"][0]["verdict"], "FAIL")

    def test_soak_start_records_and_arms_timer_once(self):
        r = self.kit("soak-start")
        self.assertEqual(r.returncode, 0, r.stderr)
        start = json.loads(rd(os.path.join(self.lab, "soak-start.json")))
        self.assertTrue(start["is_4gb_board"])
        sample = json.loads(rd(os.path.join(self.lab, "soak.jsonl")).splitlines()[0])
        self.assertEqual((sample["mem_available_mib"], sample["mib_written"]), (2832, 1000))
        self.assertTrue(os.path.exists(os.path.join(self.t, "units", "onemind-g1-soak.timer")))
        self.assertIn("enable --now onemind-g1-soak.timer", rd(self.log))
        self.assertEqual(self.kit("soak-start").returncode, 1)     # never restarts the 30 days
        self.assertEqual(self.kit("soak-sample").returncode, 0)
        self.assertEqual(len(rd(os.path.join(self.lab, "soak.jsonl")).splitlines()), 2)

    def test_soak_warns_on_non_4gb_board(self):
        wr(os.path.join(self.t, "proc", "meminfo"), "MemTotal: 16000000 kB\nMemAvailable: 9000000 kB\n")
        r = self.kit("soak-start")
        self.assertIn("not a 4 GB Pi", r.stderr)
        self.assertFalse(json.loads(rd(os.path.join(self.lab, "soak-start.json")))["is_4gb_board"])


if __name__ == "__main__":
    unittest.main()
