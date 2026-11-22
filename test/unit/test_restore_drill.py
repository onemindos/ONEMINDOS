# SPDX-License-Identifier: Apache-2.0
"""BAK-02 (#163): the restore drill's judging core and its CI wiring.

The VM drill itself runs in CI on a KVM runner (.github/workflows/restore-drill.yml). Here: the rules that
decide pass or fail (60 minutes, every check, every phase), and that the workflow and scripts stay wired.
"""
import importlib.util
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DRILL = ROOT / "test" / "restore-drill"
spec = importlib.util.spec_from_file_location("drillcore", DRILL / "drillcore.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def run_text(install=(0, 300), restore=(300, 900), verify=(900, 1000), fails=0, seed=True, passes=5, extra=""):
    lines = []
    if seed:
        lines += ["DRILL-PHASE seed start 10", "DRILL-PHASE seed end 200"]
    for name, rng in (("install", install), ("restore", restore), ("verify", verify)):
        if rng:
            lines.append(f"DRILL-PHASE {name} start {1000 + rng[0]}")
            lines.append(f"DRILL-PHASE {name} end {1000 + rng[1]}")
    lines += ["DRILL-INFO restore_mode=restic-owner-key"]
    lines += [f"PASS  check {i}" for i in range(passes)]
    lines += [f"FAIL  broken {i}" for i in range(fails)]
    return "\n".join(lines) + "\n" + extra


class Parse(unittest.TestCase):
    def test_phases_checks_info(self):
        phases, checks, info = core.parse(run_text(fails=1))
        self.assertEqual(phases["restore"], {"start": 1300.0, "end": 1900.0})
        self.assertEqual([c["result"] for c in checks].count("FAIL"), 1)
        self.assertEqual(info, {"restore_mode": "restic-owner-key"})

    def test_ignores_noise_and_crlf(self):
        text = "random install log PASS something\r\nDRILL-PHASE verify start 5\r\nDRILL-PHASE verify end 9\r\n"
        phases, checks, _ = core.parse(text)
        self.assertEqual(core.durations(phases), {"verify": 4.0})
        self.assertEqual(checks, [])

    def test_end_before_start_is_unfinished(self):
        phases, _, _ = core.parse("DRILL-PHASE install start 50\nDRILL-PHASE install end 10\n")
        self.assertIsNone(core.durations(phases)["install"])


class Verdict(unittest.TestCase):
    def test_pass_inside_budget(self):
        r = core.evaluate(run_text())
        self.assertEqual((r["verdict"], r["restore_seconds"]), ("PASS", 1000.0))
        self.assertEqual(core.exit_code(r), 0)
        self.assertEqual(r["restore_mode"], "restic-owner-key")

    def test_exactly_sixty_minutes_passes_one_second_more_fails(self):
        self.assertEqual(core.evaluate(run_text(verify=(900, 3600)))["verdict"], "PASS")
        r = core.evaluate(run_text(verify=(900, 3601)))
        self.assertEqual(r["verdict"], "OVER_BUDGET")
        self.assertEqual(core.exit_code(r), 1)
        self.assertIn("3601 s", r["reasons"][0])

    def test_clock_is_wall_time_so_gaps_between_phases_count(self):
        r = core.evaluate(run_text(install=(0, 100), restore=(2000, 2100), verify=(2100, 2200)))
        self.assertEqual(r["restore_seconds"], 2200.0)
        self.assertEqual(r["phases"]["install"], 100.0)

    def test_seed_is_not_on_the_clock(self):
        text = run_text().replace("DRILL-PHASE seed end 200", "DRILL-PHASE seed end 99999")
        self.assertEqual(core.evaluate(text)["verdict"], "PASS")

    def test_custom_budget(self):
        self.assertEqual(core.evaluate(run_text(), budget_s=900)["verdict"], "OVER_BUDGET")

    def test_a_failed_check_fails_even_when_fast(self):
        r = core.evaluate(run_text(fails=1))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["checks_failed"], ["broken 0"])
        self.assertEqual(core.exit_code(r), 1)

    def test_failed_check_wins_over_over_budget(self):
        self.assertEqual(core.evaluate(run_text(verify=(900, 4000), fails=1))["verdict"], "FAIL")

    def test_missing_phase_fails_never_passes(self):
        r = core.evaluate(run_text(verify=None))
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIsNone(r["restore_seconds"])
        self.assertTrue(any("verify" in x for x in r["reasons"]))

    def test_no_checks_at_all_fails(self):
        self.assertEqual(core.evaluate(run_text(passes=0))["verdict"], "FAIL")
        self.assertEqual(core.evaluate("")["verdict"], "FAIL")

    def test_abort_fails_with_the_reason(self):
        r = core.evaluate(run_text(), abort="clean VM did not boot")
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("clean VM did not boot", r["reasons"][0])

    def test_summary_names_verdict_minutes_and_failures(self):
        md = core.summary_markdown(core.evaluate(run_text(verify=(900, 3601)), boot_seconds=42.0))
        self.assertIn("OVER_BUDGET (60.0 of 60 min)", md)
        self.assertIn("| restore | 600.0 |", md)
        self.assertIn("clean VM boot (not on the clock) | 42.0", md)
        self.assertIn("failed check: broken 0", core.summary_markdown(core.evaluate(run_text(fails=1))))


class Wiring(unittest.TestCase):
    """The pieces the drill needs exist and agree with each other."""

    def test_in_vm_script_prints_every_marker_the_core_judges(self):
        sh = (DRILL / "in-vm.sh").read_text()
        for name in core.SOURCE_PHASES + core.RESTORE_PHASES:
            self.assertIn(f"phase {name} start", sh)
            self.assertIn(f"phase {name} end", sh)
        self.assertIn("info restore_mode", sh)

    def test_in_vm_script_is_valid_bash(self):
        r = subprocess.run(["bash", "-n", str(DRILL / "in-vm.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_in_vm_script_never_prints_the_owner_key(self):
        sh = (DRILL / "in-vm.sh").read_text()
        for line in sh.splitlines():
            if "owner.key" in line and ("echo" in line or "printf" in line or "info " in line):
                self.assertIn("> /run/drill/owner.key", line, line)

    def test_workflow_runs_monthly_on_kvm_and_fails_over_budget(self):
        wf = yaml.safe_load((ROOT / ".github" / "workflows" / "restore-drill.yml").read_text())
        on = wf.get(True) or wf["on"]
        self.assertIn("schedule", on)
        self.assertEqual(len(on["schedule"]), 1)
        day_of_month = on["schedule"][0]["cron"].split()[2]
        self.assertTrue(day_of_month.isdigit(), "a monthly cron fixes the day of the month")
        self.assertIn("workflow_dispatch", on)
        job = wf["jobs"]["restore-drill"]
        self.assertGreaterEqual(job["timeout-minutes"], 150)   # two installs + the 60 minute clock, with room
        text = (ROOT / ".github" / "workflows" / "restore-drill.yml").read_text()
        self.assertIn("test/restore-drill/drill.py", text)
        self.assertIn("/dev/kvm", text)
        self.assertNotIn("continue-on-error", text)   # a red drill must be red

    def test_drill_script_compiles_and_uses_the_core(self):
        src = (DRILL / "drill.py").read_text()
        compile(src, "drill.py", "exec")
        self.assertIn("core.evaluate(", src)
        self.assertIn("core.exit_code(result)", src)


if __name__ == "__main__":
    unittest.main()
