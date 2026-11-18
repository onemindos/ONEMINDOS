# SPDX-License-Identifier: Apache-2.0
"""scripts/ci-gate.py: the one always-reporting merge gate (CI-02, issue 227)."""
import importlib.util
import os
import re
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci_gate", ROOT / "scripts" / "ci-gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

SELF = 999


def run(rid, name, status="completed", conclusion="success", wid=None):
    return {"id": rid, "name": name, "status": status, "conclusion": conclusion,
            "workflow_id": wid if wid is not None else hash(name) % 10_000, "html_url": f"https://x/{rid}"}


class Verdict(unittest.TestCase):
    def test_docs_only_pr_passes_on_the_quick_workflows(self):
        v = gate.verdict([run(1, "ci"), run(2, "hygiene"), run(SELF, "gate", "in_progress", None)], SELF)
        self.assertEqual((v["failed"], v["pending"], sorted(v["passed"])), ([], [], ["ci", "hygiene"]))

    def test_red_core_or_battery_fails_the_gate(self):
        for name in ("ci-core", "image"):
            v = gate.verdict([run(1, "ci"), run(2, name, conclusion="failure")], SELF)
            self.assertEqual(len(v["failed"]), 1)
            self.assertTrue(v["failed"][0].startswith(f"{name}=failure"))

    def test_cancelled_and_timed_out_block(self):
        v = gate.verdict([run(1, "ci-core", conclusion="cancelled"), run(2, "image", conclusion="timed_out")], SELF)
        self.assertEqual(len(v["failed"]), 2)

    def test_running_workflows_keep_it_pending(self):
        v = gate.verdict([run(1, "ci"), run(2, "image", "in_progress", None), run(3, "ci-core", "queued", None)], SELF)
        self.assertEqual((v["failed"], sorted(v["pending"])), ([], ["ci-core", "image"]))

    def test_informational_workflows_never_block(self):
        v = gate.verdict([run(1, "api-fuzz", conclusion="failure"), run(2, "net-2vm", "in_progress", None)], SELF)
        self.assertEqual((v["failed"], v["pending"]), ([], []))
        self.assertEqual(len(v["informational"]), 2)

    def test_skipped_and_neutral_pass(self):
        v = gate.verdict([run(1, "ci-ui", conclusion="skipped"), run(2, "ci-ux", conclusion="neutral")], SELF)
        self.assertEqual(v["failed"], [])

    def test_newest_run_of_a_workflow_wins(self):
        v = gate.verdict([run(1, "ci-core", conclusion="failure", wid=7), run(5, "ci-core", wid=7)], SELF)
        self.assertEqual((v["failed"], v["passed"]), ([], ["ci-core"]))

    def test_a_new_workflow_blocks_by_default(self):
        v = gate.verdict([run(1, "ci-something-new", conclusion="failure")], SELF)
        self.assertEqual(len(v["failed"]), 1)


def at(r, t):
    """Give a run a created_at, `t` seconds after 2026-11-15T10:00:00Z."""
    from datetime import datetime, timedelta, timezone
    r["created_at"] = (datetime(2026, 11, 15, 10, tzinfo=timezone.utc) + timedelta(seconds=t)).isoformat()
    return r


class DraftToReady(unittest.TestCase):
    """CI-09 (issue 298): a draft push skips the heavy workflows; marking ready must wait for all of them."""

    def test_a_ready_pr_waits_for_every_workflow_not_the_drafts_skipped_runs(self):
        draft_time = [at(run(1, "ci-core", conclusion="skipped"), 0), at(run(2, "image", conclusion="skipped"), 0),
                      at(run(3, "ci"), 0)]
        ready_time = [at(run(10, "ci", "in_progress", None), 3600), at(run(SELF, "merge-gate", "in_progress", None), 3601)]
        v = gate.verdict(draft_time + ready_time, SELF)
        # ci-core and image have not started yet for the ready event: they must not count as green.
        self.assertEqual(v["pending"], ["ci"])
        self.assertNotIn("ci-core", v["passed"])
        self.assertNotIn("image", v["passed"])

    def test_an_earlier_cancelled_gate_run_of_the_same_commit_is_ignored(self):
        # The draft's gate was cancelled by concurrency when the PR was marked ready (CI-09 bug on #301).
        old_gate = at(run(5, "merge-gate", conclusion="cancelled", wid=77), 3590)
        v = gate.verdict([old_gate, at(run(10, "ci"), 3600), at(run(SELF, "merge-gate", "in_progress", None, wid=77), 3601)], SELF)
        self.assertEqual(v["failed"], [])
        self.assertEqual(v["passed"], ["ci"])
        # also by name when the workflow id is unknown, and for a failed or pending earlier gate
        for conc, st in (("failure", "completed"), (None, "in_progress")):
            g = at(run(6, "merge-gate", st, conc, wid=78), 3595)
            v = gate.verdict([g, at(run(10, "ci"), 3600), at(run(SELF, "merge-gate", "in_progress", None, wid=77), 3601)], SELF)
            self.assertEqual((v["failed"], v["pending"]), ([], []))

    def test_ready_pr_waits_for_the_new_heavy_runs_then_passes(self):
        runs = [at(run(1, "ci-core", conclusion="skipped"), 0), at(run(SELF, "merge-gate", "in_progress", None), 3600),
                at(run(10, "ci-core", "in_progress", None, wid=hash("ci-core") % 10_000), 3599)]
        runs[0]["workflow_id"] = runs[2]["workflow_id"]
        self.assertEqual(gate.verdict(runs, SELF)["pending"], ["ci-core"])
        runs[2].update(status="completed", conclusion="success")
        v = gate.verdict(runs, SELF)
        self.assertEqual((v["pending"], v["failed"], v["passed"]), ([], [], ["ci-core"]))

    def test_runs_of_the_same_push_are_all_counted(self):
        runs = [at(run(SELF, "merge-gate", "in_progress", None), 5), at(run(1, "ci-core", conclusion="failure"), 0),
                at(run(2, "ci"), 8)]
        self.assertEqual(len(gate.verdict(runs, SELF)["failed"]), 1)

    def test_draft_gate_logs_that_heavy_checks_skipped(self):
        env = dict(Loop.ENV, DRAFT="true")
        printed = []
        with mock.patch.dict(os.environ, env), mock.patch.object(gate, "fetch_runs", lambda *a: [run(1, "ci")]), \
                mock.patch.object(gate.time, "sleep", lambda s: None), \
                mock.patch("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a)))):
            self.assertEqual(gate.main(), 0)
        self.assertTrue(any("draft" in line for line in printed))


class Loop(unittest.TestCase):
    ENV = {"REPO": "o/r", "HEAD_SHA": "abc", "EVENT": "pull_request", "GH_TOKEN": "t", "RUN_ID": str(SELF),
           "GATE_SETTLE_S": "0", "GATE_POLL_S": "0", "GATE_TIMEOUT_S": "60"}

    def main(self, *answers):
        calls = iter(answers)
        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(gate, "fetch_runs", lambda *a: next(calls)), \
                mock.patch.object(gate.time, "sleep", lambda s: None), mock.patch("builtins.print"):
            return gate.main()

    def test_waits_then_passes(self):
        self.assertEqual(self.main([run(1, "ci-core", "in_progress", None)], [run(1, "ci-core")]), 0)

    def test_fails_as_soon_as_one_fails(self):
        self.assertEqual(self.main([run(1, "ci-core", "in_progress", None), run(2, "ci", conclusion="failure")]), 1)

    def test_api_error_is_retried(self):
        answers = iter([OSError("503"), [run(1, "ci")]])

        def fetch(*a):
            a = next(answers)
            if isinstance(a, Exception):
                raise a
            return a
        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(gate, "fetch_runs", fetch), \
                mock.patch.object(gate.time, "sleep", lambda s: None), mock.patch("builtins.print"):
            self.assertEqual(gate.main(), 0)


class Workflow(unittest.TestCase):
    def test_gate_workflow_always_runs_on_prs_and_the_merge_queue(self):
        wf = (ROOT / ".github" / "workflows" / "gate.yml").read_text()
        on = wf[wf.index("\non:"):wf.index("\npermissions:")]
        self.assertIn("pull_request:", on)
        self.assertIn("merge_group:", on)
        self.assertIn("ready_for_review", on)  # marking a draft ready starts a fresh gate (CI-09)
        self.assertNotIn("paths", on)          # a path filter would make it stop reporting
        self.assertIn("actions: read", wf)
        self.assertIn("python3 -I scripts/ci-gate.py", wf)

    def test_informational_names_are_real_workflows(self):
        names = {re.search(r"^name: *(\S+)", p.read_text(), re.M).group(1)
                 for p in (ROOT / ".github" / "workflows").glob("*.yml")}
        self.assertLessEqual(set(gate.INFORMATIONAL), names)
        self.assertNotIn("merge-gate", gate.INFORMATIONAL)

    def test_check_name_is_unique(self):
        # A required check is matched by name; three other workflows have a job called `gate`.
        jobs = []
        for p in (ROOT / ".github" / "workflows").glob("*.yml"):
            jobs += re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", p.read_text().split("\njobs:", 1)[-1], re.M)
        self.assertEqual(jobs.count("merge-gate"), 1)


if __name__ == "__main__":
    unittest.main()
