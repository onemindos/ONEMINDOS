# SPDX-License-Identifier: Apache-2.0
"""G1 power-pull harness (lab-kits/G1/g1-power.py, #215): cycle logic, verdicts, backends and credential
handling against fakes. No hardware, no network: this proves the harness, not G1."""
import argparse, importlib.util, json, os, tempfile, unittest, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("g1power", os.path.join(ROOT, "lab-kits", "G1", "g1-power.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

RAUC_GOOD = json.dumps({"booted": "A", "slots": [{"rootfs.0": {"bootname": "A", "state": "booted", "boot_status": "good"}},
                                                  {"rootfs.1": {"bootname": "B", "state": "inactive", "boot_status": "bad"}}]})
GATE_OK = "HEALTH-GATE: t RESULT committed-boot slot=A version=1\n"


class FakePower(g.Power):
    name = "fake"

    def __init__(self, box):
        self.box, self.calls = box, []

    def off(self): self.calls.append("off"); self.box.up = False
    def on(self): self.calls.append("on"); self.box.up = True


class FakeBox:
    """A box that answers the harness's ssh commands. `after_pull` decides what the probe says after a pull."""
    def __init__(self, rauc=RAUC_GOOD, gate=GATE_OK, pending="", install_rc=0):
        self.reboot_returns = False
        self.up, self.rauc, self.gate, self.pending, self.install_rc = True, rauc, gate, pending, install_rc
        self.log = []

    def ssh(self, cmd, timeout=20):
        self.log.append(cmd)
        if not self.up:
            return 255, "no route"
        if cmd.startswith("rauc status"): return 0, self.rauc
        if cmd.startswith("cat /data/onemind/pending"): return 0, self.pending
        if cmd.startswith("tail"): return 0, self.gate
        if cmd.startswith("cat /run/g1-power-install.log"): return 0, f"installed\nrc={self.install_rc}\n"
        if cmd == "systemctl reboot":
            self.up = self.reboot_returns   # a clean reboot comes back by itself; during a pull cycle power decides
            return 0, ""
        if cmd.startswith("rauc install"): return 0 if self.install_rc == 0 else 1, "ok"
        return 0, ""


class Clock:
    def __init__(self): self.t = 0.0
    def sleep(self, s): self.t += s
    def time(self): return self.t


def args(**kw):
    d = dict(bundle="/b/good.raucb", health_url=None, write_start=1, write_mid=2, reboot_delay=1, trial_delay=1, hold_off=1,
             settle=60, poll=5, install_timeout=30, reinstall_check=False)
    d.update(kw)
    return argparse.Namespace(**d)


def harness(box, **kw):
    c = Clock()
    return g.Harness(FakePower(box), ssh=box.ssh, http=kw.pop("http", lambda u: True), sleep=c.sleep, clock=c.time, a=args(**kw)), c


class Parse(unittest.TestCase):
    def test_rauc_json(self):
        self.assertEqual(g.parse_rauc(RAUC_GOOD), ("A", "good"))
        self.assertEqual(g.parse_rauc("not json"), (None, None))

    def test_last_gate(self):
        self.assertEqual(g.last_gate("x\nHEALTH-GATE: a RESULT mark-bad slot=B version=2\n" + GATE_OK), ("committed-boot", "A"))
        self.assertEqual(g.last_gate("nothing"), (None, None))

    def test_phases_cover_each_once_then_random(self):
        import random
        p = g.phases_for(20, random.Random(3))
        self.assertEqual(p[:5], g.PHASES)
        self.assertEqual(len(p), 20)
        self.assertTrue(set(p) <= set(g.PHASES))


class Cycle(unittest.TestCase):
    def test_every_phase_passes_on_a_healthy_box(self):
        for ph in g.PHASES:
            box = FakeBox()
            h, _ = harness(box)
            r = h.cycle(1, ph)
            self.assertEqual(r["verdict"], "PASS", (ph, r))
            self.assertEqual(h.power.calls, ["off", "on"])

    def test_unhealthy_after_pull_is_a_fail(self):
        box = FakeBox()
        h, _ = harness(box)
        orig = h.power.on
        def on():  # after the pull the gate shows the slot never committed
            orig(); box.pending = "B 9"
        h.power.on = on
        r = h.cycle(2, "write-mid")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("trial still pending", r["detail"])

    def test_box_never_returns_is_a_fail(self):
        box = FakeBox()
        h, _ = harness(box, settle=30)
        h.power.on = lambda: h.power.calls.append("on")   # power-on does nothing: box stays down
        r = h.cycle(1, "write-start")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["detail"], "unreachable")

    def test_unhealthy_before_pull_aborts_without_cutting_power(self):
        box = FakeBox(pending="B 9")
        h, _ = harness(box)
        r = h.cycle(1, "write-start")
        self.assertEqual(r["verdict"], "ABORT")
        self.assertEqual(h.power.calls, [])

    def test_failed_install_is_not_counted_as_a_pull_result(self):
        box = FakeBox(install_rc=1)
        h, _ = harness(box)
        r = h.cycle(1, "write-done")
        self.assertEqual(r["verdict"], "ABORT")
        self.assertEqual(h.power.calls, ["on"])   # power restored, nothing counted

    def test_health_url_failure_fails(self):
        box = FakeBox()
        h, _ = harness(box, http=lambda u: False, health_url="http://x/healthz", settle=20)
        self.assertEqual(h.cycle(1, "write-start")["verdict"], "ABORT")  # pre-check already sees it

    def test_reinstall_check(self):
        box = FakeBox()
        h, _ = harness(box, reinstall_check=True)
        orig = box.ssh
        def ssh(cmd, timeout=20):
            if cmd.startswith("rauc install /b"):
                box.reboot_returns = True   # after the re-install a normal reboot brings the box back
            return orig(cmd, timeout)
        h.ssh = ssh
        r = h.cycle(1, "write-start")
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["reinstall_rc"], 0)
        self.assertIn("systemctl reboot", box.log)


class Backends(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self.env)))

    def test_redfish_posts_force_off_and_on_with_basic_auth(self):
        os.environ.update(G1_BMC_HOST="bmc.invalid", G1_BMC_USER="root", G1_BMC_PASS="s3cretpw")
        seen = []
        def op(req):
            seen.append((req.full_url, json.loads(req.data), req.get_header("Authorization")))
            class R:
                def read(self): return b""
            return R()
        p = g.Redfish(opener=op)
        p.off(); p.on()
        self.assertEqual([s[1] for s in seen], [{"ResetType": "ForceOff"}, {"ResetType": "On"}])
        self.assertTrue(seen[0][0].endswith("/Systems/System.Embedded.1/Actions/ComputerSystem.Reset"))
        self.assertTrue(seen[0][2].startswith("Basic "))

    def test_redfish_error_does_not_leak_password_or_host(self):
        os.environ.update(G1_BMC_HOST="bmc.invalid", G1_BMC_USER="root", G1_BMC_PASS="s3cretpw")
        def op(req): raise urllib.error.URLError("failed talking to bmc.invalid with s3cretpw")
        with self.assertRaises(RuntimeError) as c:
            g.Redfish(opener=op).off()
        self.assertNotIn("s3cretpw", str(c.exception))
        self.assertNotIn("bmc.invalid", str(c.exception))

    def test_ipmi_uses_chassis_power_off_on(self):
        os.environ.update(G1_BMC_HOST="bmc.invalid", G1_BMC_USER="root", G1_BMC_PASS="s3cretpw")
        seen = []
        p = g.Ipmi(run=seen.append)
        p.off(); p.on()
        self.assertEqual(seen, ["off", "on"])   # never `soft`

    def test_hook_calls_urls_with_method(self):
        os.environ.update(G1_PLUG_OFF_URL="http://plug.invalid/off?k=tok123", G1_PLUG_ON_URL="http://plug.invalid/on?k=tok123", G1_PLUG_METHOD="post")
        seen = []
        def op(req):
            seen.append((req.full_url, req.get_method()))
            class R:
                def read(self): return b""
            return R()
        p = g.Hook(opener=op)
        p.off(); p.on()
        self.assertEqual([s[1] for s in seen], ["POST", "POST"])
        self.assertIn("/off", seen[0][0])

    def test_missing_env_is_a_clear_error(self):
        for k in ("G1_BMC_HOST", "G1_BMC_USER", "G1_BMC_PASS", "G1_PLUG_OFF_URL", "G1_PLUG_ON_URL"):
            os.environ.pop(k, None)
        for cls in (g.Redfish, g.Ipmi, g.Hook):
            with self.assertRaises(SystemExit):
                cls()

    def test_manual_prompts(self):
        asked = []
        m = g.Manual(ask=asked.append)
        m.off(); m.on()
        self.assertEqual(len(asked), 2)
        self.assertIn("PULL", asked[0])


class Cli(unittest.TestCase):
    def test_real_backend_needs_confirm(self):
        self.assertEqual(g.main(["run", "--power", "hook"]), 2)

    def test_plan_and_summary(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "r.jsonl")
            with open(p, "w") as f:
                for v in ("PASS", "PASS", "FAIL", "ABORT"):
                    f.write(json.dumps(dict(verdict=v)) + "\n")
            self.assertEqual(g.summary_line(g.load(p)), "Power pulls (g1-power.py, 3 counted, 1 aborted and not counted): bootable after 2 / 3")
            self.assertEqual(g.main(["plan", "--cycles", "3"]), 0)

    def test_results_file_holds_no_credentials(self):
        # the record keys are fixed; none carries an address or secret
        box = FakeBox()
        h, _ = harness(box)
        r = h.cycle(1, "write-start")
        self.assertNotIn("G1_", json.dumps(r))


if __name__ == "__main__":
    unittest.main()
