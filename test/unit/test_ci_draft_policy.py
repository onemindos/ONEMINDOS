# SPDX-License-Identifier: Apache-2.0
"""CI-09 (issue 298): drafts run only the cheap checks; superseded PR runs are cancelled, nothing else is.

Reads every .github/workflows/*.yml and checks the rules that keep CI capacity free, so a new workflow
that forgets them fails here instead of silently queueing jobs nobody needs.
"""
import unittest
from pathlib import Path

import yaml

WF = Path(__file__).resolve().parents[2] / ".github" / "workflows"
# The jobs a draft PR still runs: dco, hygiene, lint, unit (and the change-fragment check beside them).
CHEAP = {"ci.yml": {"lint", "unit", "changes", "dco"}, "hygiene.yml": {"hygiene"}}
# Own, hand-written concurrency: the gate keys on the PR number, security-nightly serialises PR runs.
OWN_CONCURRENCY = {"gate.yml", "security-nightly.yml"}
# ci-core.yml is being changed by #264 (merge queue); it joins this policy once that lands.
PENDING = {"ci-core.yml"}


def load():
    for p in sorted(WF.glob("*.yml")):
        d = yaml.safe_load(p.read_text())
        on = d.get(True) or d.get("on")  # PyYAML reads the bare key `on` as True
        yield p.name, d, (on if isinstance(on, dict) else {})


class DraftPolicy(unittest.TestCase):
    def test_pr_workflows_listen_to_ready_for_review(self):
        for name, d, on in load():
            if "pull_request" in on and name not in PENDING:
                types = (on["pull_request"] or {}).get("types", [])
                self.assertIn("ready_for_review", types, name)
                self.assertIn("synchronize", types, name)

    def test_heavy_jobs_skip_on_drafts(self):
        for name, d, on in load():
            if "pull_request" not in on or name in PENDING or name == "gate.yml":
                continue
            for job, spec in d["jobs"].items():
                if job in CHEAP.get(name, ()):
                    self.assertNotIn("pull_request.draft", str(spec.get("if", "")), f"{name}:{job} is cheap")
                    continue
                cond = str(spec.get("if", ""))
                # A job that only `needs` a guarded job is skipped with it, unless its own condition
                # (always(), !cancelled()) would run it anyway.
                inherits = spec.get("needs") and not any(k in cond for k in ("always()", "cancelled()"))
                never_on_pr = "github.event.schedule ==" in cond or "event_name != 'pull_request'" in cond
                self.assertTrue("pull_request.draft" in cond or inherits or never_on_pr,
                                f"{name}:{job} runs on drafts")

    def test_gate_job_runs_on_drafts_and_waits_for_the_set(self):
        d = yaml.safe_load((WF / "gate.yml").read_text())
        self.assertNotIn("if", d["jobs"]["merge-gate"])  # always reports; a skipped check would pass
        self.assertIn("merge_group", d.get(True) or d["on"])


class Concurrency(unittest.TestCase):
    def test_every_pr_workflow_cancels_only_superseded_pr_runs(self):
        for name, d, on in load():
            if "pull_request" not in on or name in PENDING or name == "security-nightly.yml":
                continue
            c = d.get("concurrency")
            self.assertIsNotNone(c, f"{name} has no concurrency group")
            cancel = str(c["cancel-in-progress"])
            self.assertIn("github.event_name == 'pull_request'", cancel, name)
            if name not in OWN_CONCURRENCY:
                # Non-PR runs (main, merge_group, nightly, manual) get a group of their own: nothing cancels them.
                self.assertIn("github.run_id", c["group"], name)

    def test_gate_concurrency_is_per_pr_or_per_queue_entry(self):
        c = yaml.safe_load((WF / "gate.yml").read_text())["concurrency"]
        self.assertIn("pull_request.number", c["group"])
        self.assertIn("github.sha", c["group"])

    def test_nothing_cancels_unconditionally(self):
        for name, d, on in load():
            c = d.get("concurrency") or {}
            self.assertIsNot(c.get("cancel-in-progress"), True, f"{name} cancels main/merge_group runs too")


if __name__ == "__main__":
    unittest.main()
