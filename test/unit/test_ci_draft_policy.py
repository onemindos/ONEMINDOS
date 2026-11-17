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


# CI-11 (issue 298): the informational workflows (scripts/ci-gate.py INFORMATIONAL) never decide a merge,
# so a PR runs one only when it changes the workflow's own harness. Everything else they watch is covered
# by the schedule, a push to main and a manual run. Value: the paths a PR may match.
INFORMATIONAL_PR_PATHS = {
    "api-fuzz.yml": {"core/tests/api_fuzz_check.py", ".github/workflows/api-fuzz.yml"},
    "go-fuzz.yml": {"internal/**/*fuzz*_test.go", ".github/workflows/go-fuzz.yml"},
    "perf-smoke.yml": {"test/perf/**", ".github/workflows/perf-smoke.yml"},
    "net-2vm.yml": {"test/net/**", ".github/workflows/net-2vm.yml"},
    "security-nightly.yml": {"os/update/**", ".github/workflows/security-nightly.yml"},
    "apps-gate-all.yml": {"sdk/tools/ci/**", ".github/workflows/apps-gate-all.yml"},
}


class InformationalWorkflows(unittest.TestCase):
    def test_list_matches_the_gate(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ci_gate", WF.parents[1] / "scripts" / "ci-gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        names = {d["name"] for _, d, _ in load()}
        self.assertEqual({n.removesuffix(".yml") for n in INFORMATIONAL_PR_PATHS}, set(gate.INFORMATIONAL))
        self.assertTrue(set(gate.INFORMATIONAL) <= names)

    def test_pull_requests_run_them_only_for_their_own_files(self):
        by_name = {n: on for n, _, on in load()}
        for name, allowed in INFORMATIONAL_PR_PATHS.items():
            pr = by_name[name].get("pull_request")
            if pr is None:
                continue
            paths = set(pr.get("paths") or [])
            self.assertTrue(paths, f"{name}: pull_request without a paths filter runs on every PR")
            self.assertLessEqual(paths, allowed, f"{name}: PR paths are broader than the harness")

    def test_they_still_run_on_schedule_main_or_by_hand(self):
        for name, on in {n: on for n, _, on in load()}.items():
            if name in INFORMATIONAL_PR_PATHS:
                self.assertTrue({"workflow_dispatch"} <= set(on), f"{name}: no manual run")
                self.assertTrue({"schedule", "push"} & set(on), f"{name}: no schedule or push to main")

    def test_net_2vm_is_strict_on_every_automatic_event(self):
        """Nothing is counted as passed that did not run: pushes to main are the only automatic
        coverage of the code net-2vm watches, so they must be strict like a pull request."""
        import re
        by_name = {n: (d, on) for n, d, on in load()}
        d, on = by_name["net-2vm.yml"]
        expr = None
        for job in d["jobs"].values():
            for step in job.get("steps", []):
                if "ONEMIND_NET_STRICT" in (step.get("env") or {}):
                    expr = step["env"]["ONEMIND_NET_STRICT"]
        self.assertIsNotNone(expr, "no ONEMIND_NET_STRICT env found")
        m = re.fullmatch(r"\$\{\{(.*)\}\}", expr.strip())
        self.assertIsNotNone(m, f"not a single expression: {expr}")

        def evaluate(body, event, strict_input):
            tokens = re.findall(r"github\.event_name|github\.event\.inputs\.strict|'[^']*'|==|!=|&&|\|\||\(|\)", body)
            rest = re.sub(r"github\.event_name|github\.event\.inputs\.strict|'[^']*'|==|!=|&&|\|\||\(|\)|\s+", "", body)
            self.assertEqual(rest, "", f"evaluator does not understand: {rest!r} in {body!r}")
            py = []
            for t in tokens:
                py.append({"github.event_name": repr(event), "github.event.inputs.strict": repr(strict_input),
                           "&&": " and ", "||": " or "}.get(t, t))
            return eval("".join(py), {"__builtins__": {}}, {})  # noqa: S307 (tokens validated above)

        events = set(on)
        self.assertIn("workflow_dispatch", events)
        for event in sorted(events - {"workflow_dispatch"}):
            self.assertEqual(evaluate(m.group(1), event, ""), "1", f"{event} must run strict")
        self.assertEqual(evaluate(m.group(1), "workflow_dispatch", ""), "0")
        self.assertEqual(evaluate(m.group(1), "workflow_dispatch", "true"), "1")


if __name__ == "__main__":
    unittest.main()
