# SPDX-License-Identifier: Apache-2.0
"""CI-17: ui-quality compares each PR with main rendered in the same job, never with committed screenshots.

Pins the contract of .github/workflows/ui-quality.yml and the logic of scripts/ui-visual-verdict.py, so a
later edit cannot quietly bring back committed baselines, a job that writes to the repository, or a
label run that hides a failed axe check.
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows" / "ui-quality.yml"
SCRIPT = ROOT / "scripts" / "ui-visual-verdict.py"

spec = importlib.util.spec_from_file_location("ui_visual_verdict", SCRIPT)
verdict = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verdict)


def workflow():
    d = yaml.safe_load(WF.read_text())
    return d, d.get(True) or d["on"]  # PyYAML reads the bare key `on` as True


def steps_text(job):
    return "\n".join(str(s.get("run", "")) + " " + str(s.get("if", "")) for s in job["steps"])


class WorkflowContract(unittest.TestCase):
    def test_label_events_trigger_a_re_check(self):
        _, on = workflow()
        types = on["pull_request"]["types"]
        for t in ("opened", "synchronize", "reopened", "ready_for_review", "labeled", "unlabeled"):
            self.assertIn(t, types)

    def test_no_job_can_write(self):
        d, _ = workflow()
        self.assertEqual(d["permissions"], {})
        for name, job in d["jobs"].items():
            for scope, level in (job.get("permissions") or {}).items():
                self.assertEqual(level, "read", f"{name}: {scope}: {level}")
        self.assertNotIn("commit-baseline", d["jobs"])
        self.assertNotIn("git push", WF.read_text())

    def test_pull_requests_read_only_where_labels_are_read(self):
        d, _ = workflow()
        for name, job in d["jobs"].items():
            perms = job.get("permissions") or {}
            self.assertEqual("pull-requests" in perms, name in {"visual", "visual-recheck"}, name)
            self.assertEqual("issues" in perms, name in {"visual", "visual-recheck"}, name)
            self.assertEqual("actions" in perms, name == "visual-recheck", name)

    def test_no_update_baseline_input(self):
        _, on = workflow()
        self.assertFalse((on.get("workflow_dispatch") or {}).get("inputs"))
        self.assertNotIn("update_baseline", WF.read_text())

    def test_label_name_and_recheck_prefix(self):
        self.assertEqual(verdict.LABEL, "visual:accepted")
        d, _ = workflow()
        self.assertIn(verdict.RECHECK_PREFIX, d["run-name"])
        self.assertIn("verdict", steps_text(d["jobs"]["visual"]))
        self.assertIn("find-run", steps_text(d["jobs"]["visual-recheck"]))

    def test_axe_and_flows_run_on_every_event_three_browsers(self):
        d, on = workflow()
        self.assertIn("push", on)
        self.assertIn("workflow_dispatch", on)
        b = d["jobs"]["browsers"]
        self.assertEqual(b["strategy"]["matrix"]["browser"], ["chromium", "firefox", "webkit"])
        axe = next(s for s in b["steps"] if "--grep-invert @visual" in str(s.get("run", "")))
        self.assertNotIn("if", axe)  # no condition: push, manual run and PR alike
        for job in ("build", "browsers"):
            cond = d["jobs"][job]["if"]
            self.assertNotIn("event_name == 'pull_request'", cond, job)  # still runs on push

    def test_visual_steps_compare_only_on_pull_requests(self):
        d, _ = workflow()
        self.assertIn("github.event_name == 'pull_request'", d["env"]["COMPARE"])
        b = d["jobs"]["browsers"]
        visual = [s for s in b["steps"] if "@visual" in str(s.get("run", "")) and "--grep-invert" not in s["run"]]
        self.assertEqual(len(visual), 2)  # draw from the base, compare the PR
        for s in visual:
            self.assertIn("env.COMPARE == 'true'", s["if"])
            self.assertIn("visual-base", s["env"]["VISUAL_DIR"])
        self.assertIn("--update-snapshots=all", visual[0]["run"])
        self.assertIn("_base/", visual[0]["env"]["UI_DIST"])
        self.assertIn("--update-snapshots=none", visual[1]["run"])
        base = next(s for s in d["jobs"]["build"]["steps"] if "_base" in str(s.get("run", "")))
        self.assertIn("HEAD^1", base["run"])
        self.assertIn("env.COMPARE == 'true'", base["if"])

    def test_label_runs_skip_the_browsers(self):
        d, _ = workflow()
        for job in ("build", "browsers", "visual"):
            self.assertIn("github.event.action != 'labeled'", d["jobs"][job]["if"], job)
        self.assertIn("github.event.action == 'labeled'", d["jobs"]["visual-recheck"]["if"])
        self.assertIn("github.run_id", d["concurrency"]["group"])  # a re-check never cancels a full run
        # find-run may wait RECHECK_TIMEOUT_S (65 min); the job must outlive it.
        self.assertGreaterEqual(d["jobs"]["visual-recheck"]["timeout-minutes"] * 60, 3900 + 300)
        self.assertIn('"RECHECK_TIMEOUT_S", "3900"', SCRIPT.read_text())

    def test_actions_stay_pinned_to_the_same_shas(self):
        pins = {"actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
                "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
                "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
                "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093"}
        d, _ = workflow()
        for job in d["jobs"].values():
            for s in job["steps"]:
                if "uses" in s and not s["uses"].startswith("./"):   # local actions (sdk-gen, CI-16) live in this repo
                    action, sha = s["uses"].split("@")
                    self.assertEqual(sha, pins[action], s["uses"])


class NothingCommitted(unittest.TestCase):
    def test_visual_dir_is_gitignored_and_untracked(self):
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "ui/test/visual"],
                                 capture_output=True, text=True, check=True).stdout
        self.assertEqual(tracked, "")
        self.assertIn("visual/", (ROOT / "ui/test/.gitignore").read_text().split())
        self.assertFalse((ROOT / "ui/test/accept-visual.sh").exists())

    def test_config_reads_the_reference_dir_from_the_environment(self):
        cfg = (ROOT / "ui/test/playwright.config.ts").read_text()
        self.assertIn("process.env.VISUAL_DIR", cfg)
        self.assertIn("${VISUAL_DIR}/{projectName}/{arg}{ext}", cfg)


T1, T2, T3 = "2026-11-19T10:00:00Z", "2026-11-19T11:00:00Z", "2026-11-19T12:00:00Z"
COMMIT = [{"event": "committed", "committer": {"date": "2026-11-19T10:30:00Z"}}]


def label(name, at, event="labeled"):
    return {"event": event, "label": {"name": name}, "created_at": at}


def report(*tests, errors=None):
    return {"errors": errors or [], "suites": [{"title": "visual.spec.ts", "specs": [], "suites": [
        {"title": "visual", "specs": [{"title": t, "tests": [{"status": st}]} for t, st in tests]}]}]}


class Changes(unittest.TestCase):
    def test_lists_only_failed_tests(self):
        r = report(("ui-home light", "expected"), ("dash-nodes light", "unexpected"), ("ui-store light", "skipped"))
        self.assertEqual(verdict.changed_tests(r), ["dash-nodes light"])

    def test_all_skipped_is_refused_but_wk1_skips_are_fine(self):
        r = report(("ui-home light", "skipped"), ("ui-store light", "skipped"), ("dash-home light", "expected"))
        self.assertEqual(verdict.changed_tests(r), [])  # WebKit: WK-1 screens skipped, the rest compared
        with self.assertRaises(ValueError):
            verdict.changed_tests(report(("ui-home light", "skipped"), ("dash-home light", "skipped")))

    def test_global_error_or_no_tests_is_refused(self):
        with self.assertRaises(ValueError):
            verdict.changed_tests(report(("a", "expected"), errors=[{"message": "web server failed"}]))
        with self.assertRaises(ValueError):
            verdict.changed_tests(report())


class Verdict(unittest.TestCase):
    def test_no_change_passes_without_label(self):
        ok, text = verdict.decide({b: [] for b in verdict.BROWSERS}, False)
        self.assertTrue(ok)
        self.assertIn("no screen differs", text)

    def test_change_fails_until_labelled(self):
        changes = {"chromium": ["dash-home light"], "firefox": [], "webkit": []}
        ok, text = verdict.decide(changes, *verdict.label_is_current(COMMIT + [label("owner:claude", T2)]))
        self.assertFalse(ok)
        self.assertIn("dash-home light", text)
        ok, text = verdict.decide(changes, *verdict.label_is_current(COMMIT + [label("visual:accepted", T2)]))
        self.assertTrue(ok)
        self.assertIn("dash-home light", text)  # still listed when accepted

    def test_label_added_before_the_newest_commit_does_not_count(self):
        changes = {"chromium": [], "firefox": ["dash-nodes light"], "webkit": []}
        stale = [label("visual:accepted", T1)] + COMMIT  # accepted, then a new commit was pushed
        self.assertEqual(verdict.label_is_current(stale)[0], False)
        ok, text = verdict.decide(changes, *verdict.label_is_current(stale))
        self.assertFalse(ok)
        self.assertIn("before the newest commit", text)
        forced = [label("visual:accepted", T2), {"event": "head_ref_force_pushed", "created_at": T3}]
        self.assertFalse(verdict.label_is_current(COMMIT + forced)[0])
        # Removed and added again after the push: counts.
        again = stale + [label("visual:accepted", T2, "unlabeled"), label("visual:accepted", T3)]
        self.assertTrue(verdict.label_is_current(again)[0])
        removed = COMMIT + [label("visual:accepted", T2), label("visual:accepted", T3, "unlabeled")]
        self.assertFalse(verdict.label_is_current(removed)[0])

    def test_missing_browser_result_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "visual-changes-chromium").mkdir()
            (Path(d) / "visual-changes-chromium" / "changes.txt").write_text("")
            with self.assertRaises(FileNotFoundError):
                verdict.read_changes(Path(d))

    def test_verdict_command_reads_live_labels(self):
        with tempfile.TemporaryDirectory() as d:
            for b in verdict.BROWSERS:
                (Path(d) / f"visual-changes-{b}").mkdir()
                (Path(d) / f"visual-changes-{b}" / "changes.txt").write_text("ui-home light\n" if b == "webkit" else "")
            env = {"REPO": "o/r", "PR": "7", "GH_TOKEN": "x", "GITHUB_STEP_SUMMARY": str(Path(d) / "s.md")}
            for timeline, code in ((COMMIT, 1), (COMMIT + [label("visual:accepted", T2)], 0),
                                   ([label("visual:accepted", T1)] + COMMIT, 1)):
                with mock.patch.dict(os.environ, env), \
                        mock.patch.object(verdict, "_api", return_value=timeline) as api:
                    self.assertEqual(verdict.cmd_verdict(d), code)
                    api.assert_called_once_with("repos/o/r/issues/7/timeline?per_page=100&page=1", "x")


class Recheck(unittest.TestCase):
    def test_picks_the_newest_full_run_by_its_jobs_not_its_name(self):
        full = [{"name": "build", "conclusion": "success"}, {"name": "visual-recheck", "conclusion": "skipped"}]
        recheck = [{"name": "build", "conclusion": "skipped"}, {"name": "visual-recheck", "conclusion": None}]
        # A PR titled like a re-check must not confuse it: names are ignored.
        runs = [{"id": 10, "display_title": "ui-quality: label re-check (a PR title)"}, {"id": 11}, {"id": 12}, {"id": 13}]
        jobs = {10: full, 11: full, 12: recheck, 13: recheck}
        self.assertEqual(verdict.pick_full_run(runs, 13, jobs.get)["id"], 11)
        self.assertEqual(verdict.pick_full_run(runs[:1] + runs[3:], 13, jobs.get)["id"], 10)
        self.assertIsNone(verdict.pick_full_run([runs[2]], 13, jobs.get))
        self.assertEqual(verdict.pick_full_run(runs, 13, {**jobs, 12: []}.get), "unknown")  # queued
        draft = [{"name": "build", "conclusion": "skipped"}, {"name": "visual-recheck", "conclusion": "skipped"}]
        self.assertEqual(verdict.run_kind(draft), "other")
        self.assertEqual(verdict.run_kind([{"name": "build", "conclusion": None}]), "full")  # still running

    def test_a_failed_axe_or_build_is_not_hidden_by_a_label(self):
        ok = [{"name": n, "conclusion": "success"} for n in verdict.FULL_RUN_JOBS]
        self.assertEqual(verdict.full_run_problems(ok + [{"name": "visual", "conclusion": "failure"}]), [])
        bad = [j if j["name"] != "firefox" else {"name": "firefox", "conclusion": "failure"} for j in ok]
        self.assertEqual(verdict.full_run_problems(bad), ["firefox=failure"])
        self.assertEqual(verdict.full_run_problems(ok[1:]), ["build=missing"])

    def test_cli_usage(self):
        self.assertEqual(verdict.main([]), 2)


if __name__ == "__main__":
    unittest.main()
