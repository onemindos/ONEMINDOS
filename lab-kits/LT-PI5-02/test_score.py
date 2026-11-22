# SPDX-License-Identifier: Apache-2.0
"""Run: python3 -I -m unittest discover -s lab-kits/LT-PI5-02 -v"""
import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import score  # noqa: E402

GOOD = dict(h1_booted_and_healthy=True, bad_image_auto_rollback=True, console_or_manual_step_used=False,
            power_pull_commit="automatic", greenboot_219_fixed=True)


class Classify(unittest.TestCase):
    def k(self, **kw):
        return score.classify(dict(GOOD, **kw))[0]

    def test_pass_fixed_auto(self):
        self.assertEqual(self.k(), "pass-fixed-auto")

    def test_pass_open_when_219_open(self):
        self.assertEqual(self.k(greenboot_219_fixed=False), "pass-open")

    def test_pass_open_when_commit_manual_or_silent(self):
        self.assertEqual(self.k(power_pull_commit="manual"), "pass-open")
        self.assertEqual(self.k(power_pull_commit="silent-downgrade"), "pass-open")

    def test_fail_when_no_auto_rollback_or_console_needed(self):
        self.assertEqual(self.k(bad_image_auto_rollback=False), "fail")
        self.assertEqual(self.k(console_or_manual_step_used=True), "fail")
        self.assertEqual(self.k(h1_booted_and_healthy=False), "fail")

    def test_early_fail_needs_no_later_answers(self):
        r = dict(GOOD, bad_image_auto_rollback=False, power_pull_commit=None, greenboot_219_fixed=None)
        self.assertEqual(score.classify(r)[0], "fail")

    def test_incomplete_lists_missing(self):
        key, missing = score.classify(dict(GOOD, power_pull_commit=None))
        self.assertIsNone(key)
        self.assertEqual(missing, ["power_pull_commit"])
        self.assertIsNone(score.classify(score.TEMPLATE)[0])

    def test_bad_commit_value_rejected(self):
        with self.assertRaises(ValueError):
            score.classify(dict(GOOD, power_pull_commit="yes"))


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", os.path.join(HERE, "score.py"), *args],
                              capture_output=True, text=True)

    def test_template_round_trips_to_incomplete(self):
        t = self.run_cli("--template")
        self.assertEqual(t.returncode, 0)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(t.stdout)
        try:
            p = self.run_cli(f.name)
            self.assertEqual(p.returncode, 1)
            self.assertIn("INCOMPLETE", p.stdout)
        finally:
            os.unlink(f.name)

    def test_report_names_all_four_d012_rules(self):
        code, text = score.report(dict(GOOD))
        self.assertEqual(code, 0)
        for n in "1234":
            self.assertIn("Rule " + n, text)
        self.assertIn("Zeus", text)

    def test_missing_file_is_usage_error(self):
        self.assertEqual(self.run_cli("/nonexistent/result.json").returncode, 2)


if __name__ == "__main__":
    unittest.main()
