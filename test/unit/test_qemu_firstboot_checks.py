# SPDX-License-Identifier: Apache-2.0
"""The first-boot battery's F0 and F10 verdict logic (test/qemu/firstboot.py), fed canned guest output.

No VM: a fake `vm.run` returns what the booted image prints, so these tests pin how F0 and F10 read it.
F0 must take the NATS version from os/versions.lock.yaml (the pin the image build downloads), not a
hard-coded string, and F10 must accept the rescue console started at runtime but not enabled.
"""
import contextlib, importlib.util, io, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_firstboot():
    spec = importlib.util.spec_from_file_location("firstboot", os.path.join(ROOT, "test", "qemu", "firstboot.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeVM:
    def __init__(self, out):
        self.out = out

    def run(self, cmd, timeout=None):
        return 0, self.out


def quiet(fn, *args):
    """Run a check without its ===> line on the test output (the verdict is read from RESULTS)."""
    with contextlib.redirect_stdout(io.StringIO()):
        fn(*args)


class F0NatsVersion(unittest.TestCase):
    def setUp(self):
        import yaml
        self.fb = load_firstboot()
        self.fb.RESULTS.clear()
        nats = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))["onemind_layer"]["nats_server"]
        self.version, self.sha = str(nats["version"]), nats["amd64"]["binary"]

    def guest(self, nats_line):
        units = "".join(f"UNIT {u} {'enabled' if u == 'onemind-firstboot' else 'disabled'}\n" for u in self.fb.UNITS)
        return (f"onemindd v0.0.0\nonemind v0.0.0\n{nats_line}\r\nNATSSHA={self.sha}\nGATEWAY-IMPORT ok\n"
                f"DASH ok\nTUF ok\n{units}")

    def test_pinned_version_passes(self):
        quiet(self.fb.f0, FakeVM(self.guest(f"nats-server: {self.version}")), "x86_64-efi")
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "PASS", self.fb.RESULTS[-1]["detail"])

    def test_other_version_fails(self):
        quiet(self.fb.f0, FakeVM(self.guest("nats-server: v0.0.1")), "x86_64-efi")
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "FAIL")
        self.assertIn("nats_server_runs=False", self.fb.RESULTS[-1]["detail"])

    def test_version_prefix_is_not_enough(self):
        # v2.15.3 must not match v2.15.30: the version is anchored at the end of the line.
        quiet(self.fb.f0, FakeVM(self.guest(f"nats-server: {self.version}0")), "x86_64-efi")
        self.assertEqual(self.fb.RESULTS[-1]["verdict"], "FAIL")

    def test_no_hard_coded_nats_version(self):
        src = open(os.path.join(ROOT, "test", "qemu", "firstboot.py")).read()
        self.assertNotIn(r"nats-server: v2\.", src)


class F10RescueRuntimeStarted(unittest.TestCase):
    def setUp(self):
        self.fb = load_firstboot()
        self.fb.RESULTS.clear()

    def run_f10(self, enabled):
        out = (f"ENABLED={enabled}\nACTIVE=active\nK3S=inactive\nNOAUTH=401\nWITH=200\nJSON=200\n"
               "JSONOK=yes\nAFTER=active\n")
        quiet(self.fb.f10, FakeVM(out), "0" * 64)
        return self.fb.RESULTS[-1]

    def test_not_enabled_but_active_passes(self):
        r = self.run_f10("disabled")
        self.assertEqual(r["verdict"], "PASS", r["detail"])

    def test_enabled_in_etc_fails(self):
        # The image never enables it (F0); an enabled unit means the image changed and F0/F10 disagree.
        self.assertEqual(self.run_f10("enabled")["verdict"], "FAIL")

    def test_missing_or_masked_unit_fails(self):
        for state in ("not-found", "masked", ""):
            with self.subTest(state=state):
                self.assertEqual(self.run_f10(state)["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
