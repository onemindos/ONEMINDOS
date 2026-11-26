# SPDX-License-Identifier: Apache-2.0
"""RC1's verdict logic (test/qemu/recoveryconsole.py, CRITERIA-RECOVERY.md), fed canned guest output. No VM."""
import contextlib, hashlib, importlib.util, io, os, unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QEMU = os.path.join(ROOT, "test", "qemu")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(QEMU, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GOOD = ("EN=enabled\nACT=active\nNR=0\nMENU1=1\nMENU2=1\nG3=inactive/inactive\nNAUTO=2\nRESV=0\n"
        "G2EN=enabled\nG2ACT=active\nLOGIN2=1\nG4=inactive/inactive\nLOGIN4=0\nRCDONE=1\n")


class FakeVM:
    def __init__(self, out):
        self.out, self.cmds = out, []

    def run(self, cmd, timeout=None):
        self.cmds.append(cmd)
        return 0, self.out


class RC1(unittest.TestCase):
    def setUp(self):
        self.rc = load("recoveryconsole")

    def verdict(self, out):
        got = []
        with contextlib.redirect_stdout(io.StringIO()):
            self.rc.rc1(FakeVM(out), lambda tid, ok, detail: got.append((tid, ok, detail)))
        return got[0]

    def test_a_good_box_passes(self):
        tid, ok, detail = self.verdict(GOOD)
        self.assertEqual(tid, "RC1")
        self.assertTrue(ok, detail)

    def test_each_failure_fails(self):
        for good, bad, key in [
            ("EN=enabled", "EN=disabled", "unit_enabled"),
            ("ACT=active", "ACT=activating", "unit_active"),
            ("NR=0", "NR=7", "no_crash_loop"),
            ("MENU1=1", "MENU1=0", "menu_on_tty3"),
            ("G3=inactive/inactive", "G3=active/inactive", "no_getty_tty3"),
            ("G3=inactive/inactive", "G3=", "no_getty_tty3"),
            ("NAUTO=2", "NAUTO=6", "logind_vts"),
            ("RESV=0", "RESV=6", "logind_vts"),
            ("G2ACT=active", "G2ACT=inactive", "tty2_getty"),
            ("LOGIN2=1", "LOGIN2=0", "tty2_login_prompt"),
            ("G4=inactive/inactive", "G4=inactive/active", "no_login_tty4"),
            ("LOGIN4=0", "LOGIN4=1", "no_login_tty4"),
            ("RCDONE=1", "", "finished"),
        ]:
            with self.subTest(bad=bad):
                c = self.rc.rc1_judge(GOOD.replace(good, bad))
                self.assertFalse(c[key], bad)

    def test_it_types_nothing_and_returns_to_tty1(self):
        vm = FakeVM(GOOD)
        with contextlib.redirect_stdout(io.StringIO()):
            self.rc.rc1(vm, lambda *a: None)
        cmd = vm.cmds[0]
        self.assertNotIn("TIOCSTI", cmd)
        self.assertNotIn("> /dev/tty", cmd)
        self.assertTrue(cmd.rstrip().endswith("chvt 1; echo RCDONE=1"))

    def test_firstboot_runs_rc1_after_f15(self):
        src = Path(QEMU, "firstboot.py").read_text()
        self.assertLess(src.index("f15(vm)"), src.index("recoveryconsole.rc1(vm, record)"))
        self.assertLess(src.index("recoveryconsole.rc1(vm, record)"), src.index('vm.mark("F3 reboot keeps state")'))

    def test_criteria_are_preregistered(self):
        data = Path(QEMU, "CRITERIA-RECOVERY.md").read_bytes()
        log = Path(QEMU, "PREREGISTRATION.sha256").read_text()
        self.assertIn(hashlib.sha256(data).hexdigest() + "  CRITERIA-RECOVERY.md", log)
        self.assertIn("| RC1 |", data.decode())


if __name__ == "__main__":
    unittest.main()
