# SPDX-License-Identifier: Apache-2.0
"""test/qemu/run-tests.py strip_escapes: Ubuntu 26.04's OSC 3008 marks must not hide command output (#283)."""
import importlib.util, os, re, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("run_tests", os.path.join(HERE, "..", "qemu", "run-tests.py"))
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)

# Captured from the ubuntu-hedge serial log of nightly run 44740692617 (T1), ids shortened.
OSC = "\x1b]3008;start=7ff3624e;type=command;user=root;hostname=onemind;pid=703;cwd=/root\x1b\\"


class StripEscapes(unittest.TestCase):
    def test_osc_3008_mark_no_longer_hides_the_rauc_version(self):
        raw = "A_OK=1\n" + OSC + "rauc v1.15.2\nbundle-formats=verity\n"
        self.assertIsNone(re.search(r"^rauc v?1\.15\.2\s*$", raw, re.M))  # the bug
        out = rt.strip_escapes(raw)
        self.assertIsNotNone(re.search(r"^rauc v?1\.15\.2\s*$", out, re.M))
        self.assertIn("bundle-formats=verity", out)

    def test_bel_terminated_osc(self):
        self.assertEqual(rt.strip_escapes("\x1b]3008;end=1\x07ACT_onemind-recovery=active"), "ACT_onemind-recovery=active")

    def test_envkv_ignores_the_mark(self):
        self.assertEqual(rt.envkv(OSC + "A_OK=1\nA_TRY=0\n"), ["A_OK=1", "A_TRY=0"])

    def test_plain_text_and_csi_unchanged(self):
        self.assertEqual(rt.strip_escapes("rauc v1.15.2\n"), "rauc v1.15.2\n")
        self.assertEqual(rt.strip_escapes("\x1b[?2004hx\x1b[0m"), "x")


if __name__ == "__main__":
    unittest.main()
