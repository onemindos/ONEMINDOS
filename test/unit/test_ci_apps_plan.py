# SPDX-License-Identifier: Apache-2.0
"""ci-apps gates only the apps a pull request changes, and every app where it counts.

Founder decision 2026-11-25: a pull request into release/next queued ~80 app gate jobs on the free
runners even when it changed no app (a go.mod or CLI change re-gated everything). The plan
(sdk/tools/app-select plan, logic in sdk/tools/applib/selection.py) now gates:
  - on a pull request: only the apps whose apps/<id>/ files it changes (plus licence-matrix rows),
    every app when a shared gate input changes, none when no app changes;
  - on a pull request into main (a landing), the merge queue, the nightly schedule and a manual run:
    every app.
Validation of every manifest stays on every run. These tests run the plan through the four PR
scenarios (no app change, one app change, a shared input change, base main), end to end through git,
and lock the workflow wiring so nobody silently drops the full runs.
"""
from __future__ import annotations

import ast
import fnmatch
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci-apps.yml"
sys.path.insert(0, str(ROOT / "sdk" / "tools"))
from applib import selection  # noqa: E402

KEYS = ["alpha", "beta", "gamma"]
PR = "pull_request"


def no_matrix() -> list[str]:
    raise AssertionError("the licence matrix did not change; its rows must not be read")


def plan(changed, event=PR, base="release/next", matrix=no_matrix):
    return selection.plan(event, base, changed, KEYS, matrix)[0]


def load_workflow() -> tuple[dict, dict]:
    d = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return d, d.get(True) or d["on"]  # PyYAML reads the bare key `on` as True


def matches(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return fnmatch.fnmatchcase(path, pattern) if "*" in pattern else path == pattern


class PullRequestScenarios(unittest.TestCase):
    """The four scenarios of the decision, on the plan logic itself."""

    def test_no_app_change_gates_nothing(self):
        self.assertEqual(plan(["core/onemind_core/server.py", "docs/learning/x.md", "changes/x.md"]), [])
        self.assertEqual(plan([]), [])

    def test_one_app_change_gates_that_app_only(self):
        self.assertEqual(plan(["apps/beta/manifests/deployment.yaml", "changes/x.md"]), ["beta"])
        self.assertEqual(plan(["apps/gamma/README.md", "apps/alpha/onemind.app.yaml"]), ["alpha", "gamma"])

    def test_a_shared_input_change_gates_every_app(self):
        for entry in selection.SHARED_GATE_INPUTS:
            path = entry + "anything.py" if entry.endswith("/") else entry
            with self.subTest(path=path):
                self.assertEqual(plan([path]), KEYS)
                # Every app, the touched one first (its result comes back first at max-parallel 4).
                self.assertEqual(plan([path, "apps/beta/README.md"]), ["beta", "alpha", "gamma"])

    def test_a_pull_request_into_main_gates_every_app(self):
        self.assertEqual(plan([], base="main"), KEYS)
        self.assertEqual(plan(["docs/x.md"], base="main"), KEYS)


class OtherEvents(unittest.TestCase):
    def test_merge_queue_nightly_manual_and_unknown_events_gate_every_app(self):
        for event in ("merge_group", "schedule", "workflow_dispatch", "push", ""):
            with self.subTest(event=event):
                self.assertEqual(plan([], event=event, base=""), KEYS)


class Boundaries(unittest.TestCase):
    def test_validate_only_inputs_do_not_regate_every_app(self):
        """These change only validate-apps' verdict, which the validate job gives for every app."""
        for path in ("go.mod", "go.sum", "cmd/onemind/plugin.go", "internal/plugin/validate/validate.go",
                     "core/onemind_core/catalog.py", "sdk/policy/app-objects.yaml", "renovate.json",
                     "sdk/schema/onemind.event.schema.json", "sdk/tools/app-factory", "sdk/tools/ci/gate_summary.py"):
            with self.subTest(path=path):
                self.assertEqual(plan([path]), [])

    def test_lookalike_paths_are_not_shared_inputs(self):
        for path in ("sdk/tools/app-gate.bak", "sdk/tools/applibx/common.py", "x/sdk/tools/app-gate",
                     "sdk/tools/validate-apps-old", ".github/workflows/ci-apps.yml.orig"):
            self.assertFalse(selection.is_shared_gate_input(path), path)

    def test_licence_matrix_gates_the_apps_whose_rows_changed(self):
        self.assertEqual(plan([selection.LICENCE_MATRIX], matrix=lambda: ["gamma"]), ["gamma"])
        self.assertEqual(plan([selection.LICENCE_MATRIX, "apps/alpha/x"], matrix=lambda: []), ["alpha"])

    def test_licence_matrix_that_cannot_be_compared_gates_every_app(self):
        def broken():
            raise ValueError("header is not the expected one")
        self.assertEqual(plan([selection.LICENCE_MATRIX], matrix=broken), KEYS)

    def test_apps_outside_the_inventory_are_never_planned(self):
        self.assertEqual(plan(["apps/_intake/queue/x.yaml", "apps/deleted/README.md", "apps/README.md"]), [])


class EndToEnd(unittest.TestCase):
    """The plan command the workflow runs, against a real git history."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        # Never inherit GIT_DIR / GIT_WORK_TREE (a hook or an agent shell): they would redirect every git call.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        tools = self.repo / "sdk" / "tools"
        shutil.copytree(ROOT / "sdk/tools/applib", tools / "applib", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(ROOT / "sdk/tools/app-select", tools / "app-select")
        (tools / "app-gate").write_text("# gate\n")
        for app in ("alpha", "beta"):
            self.write(f"apps/{app}/onemind.app.yaml", f"metadata:\n  id: {app}\nspec: {{}}\n")
        self.write("docs/readme.md", "docs\n")
        self.git("init", "-q", "-b", "release/next")
        self.base = self.commit("base")

    def write(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def git(self, *args) -> str:
        return subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                               "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                              check=True, capture_output=True, text=True, env=self.env).stdout.strip()

    def commit(self, message) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def run_plan(self, head, event=PR, base_ref="release/next", base=None):
        proc = subprocess.run([sys.executable, "-I", str(self.repo / "sdk/tools/app-select"), "plan",
                               "--event", event, "--base-ref", base_ref, "--base-sha", base or self.base,
                               "--head-sha", head, "--apps-dir", str(self.repo / "apps"), "--repo", str(self.repo)],
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def branch(self, name):
        self.git("checkout", "-q", "-b", name, self.base)

    def test_no_app_change(self):
        self.branch("feature")
        self.write("docs/readme.md", "more docs\n")
        self.assertEqual(self.run_plan(self.commit("docs")), [])

    def test_one_app_change(self):
        self.branch("feature")
        self.write("apps/beta/README.md", "beta\n")
        self.assertEqual(self.run_plan(self.commit("beta")), ["beta"])

    def test_shared_input_change(self):
        self.branch("feature")
        self.write("sdk/tools/app-gate", "# gate v2\n")
        self.assertEqual(self.run_plan(self.commit("gate")), ["alpha", "beta"])

    def test_base_main(self):
        self.branch("landing")
        self.write("docs/readme.md", "landing\n")
        self.assertEqual(self.run_plan(self.commit("landing"), base_ref="main"), ["alpha", "beta"])

    def test_full_events_need_no_diff(self):
        for event in ("merge_group", "schedule", "workflow_dispatch"):
            self.assertEqual(self.run_plan("", event=event, base_ref="", base=""), ["alpha", "beta"])

    def test_base_branch_moving_on_is_not_the_pull_requests_change(self):
        self.branch("feature")
        self.write("docs/readme.md", "feature\n")
        head = self.commit("feature")
        self.git("checkout", "-q", "release/next")
        self.write("apps/alpha/README.md", "landed meanwhile\n")
        moved = self.commit("alpha on the base")
        self.assertEqual(self.run_plan(head, base=moved), [])

    def test_a_moved_file_gates_both_apps(self):
        self.write("apps/alpha/extra.yaml", "x: 1\n")
        self.base = self.commit("extra")
        self.branch("feature")
        self.git("mv", "apps/alpha/extra.yaml", "apps/beta/extra.yaml")
        self.assertEqual(self.run_plan(self.commit("move")), ["alpha", "beta"])

    def test_a_plan_error_fails_loudly(self):
        proc = subprocess.run([sys.executable, "-I", str(self.repo / "sdk/tools/app-select"), "plan",
                               "--event", PR, "--base-ref", "release/next", "--base-sha", "0" * 40,
                               "--head-sha", self.base, "--apps-dir", str(self.repo / "apps"), "--repo", str(self.repo)],
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, "")


class Wiring(unittest.TestCase):
    """The workflow keeps the full runs and uses the plan; nobody drops them silently."""

    @classmethod
    def setUpClass(cls):
        cls.wf, cls.on = load_workflow()
        cls.jobs = cls.wf["jobs"]

    def test_full_run_triggers_stay(self):
        self.assertIn("workflow_dispatch", self.on)
        self.assertIn("merge_group", self.on)
        crons = [entry["cron"] for entry in self.on.get("schedule") or []]
        self.assertEqual(len(crons), 1, "ci-apps needs its nightly schedule")
        self.assertEqual(crons[0].split()[2:], ["*", "*", "*"], "the schedule must run every day")
        self.assertIn("synchronize", self.on[PR]["types"])

    def test_plan_step_runs_the_tested_command(self):
        step = next(s for s in self.jobs["plan"]["steps"] if s.get("id") == "changed")
        self.assertEqual(self.jobs["plan"]["outputs"]["apps"], "${{ steps.changed.outputs.apps }}")
        run = step["run"]
        self.assertIn("-I sdk/tools/app-select)", run)
        self.assertIn('"${selector[@]}" plan', run)
        for flag in ('--event "$GITHUB_EVENT_NAME"', '--base-ref "$BASE_REF"', '--base-sha "$BASE_SHA"',
                     '--head-sha "$HEAD_SHA"'):
            self.assertIn(flag, run)
        self.assertEqual(step["env"]["BASE_REF"], "${{ github.event.pull_request.base.ref }}")
        self.assertIn("set -euo pipefail", run)
        self.assertNotIn("|| true", run)

    def test_gate_matrix_is_the_plan_and_an_empty_plan_skips_it(self):
        gate = self.jobs["gate"]
        self.assertEqual(gate["needs"], "plan")
        self.assertEqual(gate["strategy"]["matrix"]["app"], "${{ fromJSON(needs.plan.outputs.apps) }}")
        self.assertIn("needs.plan.outputs.apps != '[]'", gate["if"])
        self.assertIs(gate["strategy"]["fail-fast"], False)

    def test_validate_checks_every_manifest_on_every_run(self):
        validate = self.jobs["validate"]
        self.assertNotIn("needs", validate)
        self.assertEqual(validate["if"].replace(" ", ""), "${{!github.event.pull_request.draft}}")
        step = next(s for s in validate["steps"] if s.get("name") == "Validate apps")
        self.assertEqual(step["run"].split(), ["python3", "-I", "sdk/tools/validate-apps",
                                               "--plugin-validator", '"$ONEMIND_PLUGIN_VALIDATOR"'],
                         "validate-apps must check every app (no app ids)")

    def test_nightly_checks_out_release_next(self):
        expr = "${{ github.event_name == 'schedule' && 'release/next' || '' }}"
        for name, job in self.jobs.items():
            for step in job["steps"]:
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    self.assertEqual(step["with"].get("ref"), expr, f"{name}: nightly would test main")

    def test_merge_gate_counts_a_skipped_gate_as_passed_and_ci_apps_as_blocking(self):
        spec = importlib.util.spec_from_file_location("ci_gate", ROOT / "scripts" / "ci-gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        self.assertIn("skipped", gate.PASSING)
        self.assertNotIn(self.wf["name"], gate.INFORMATIONAL)
        runs = [{"id": 2, "workflow_id": 20, "name": self.wf["name"], "status": "completed",
                 "conclusion": "success", "created_at": "2026-11-25T12:00:00Z"},
                {"id": 1, "workflow_id": 10, "name": "merge-gate", "status": "in_progress",
                 "conclusion": None, "created_at": "2026-11-25T12:00:00Z"}]
        self.assertEqual(gate.verdict(runs, 1)["passed"], [self.wf["name"]])


class SharedInputs(unittest.TestCase):
    """The shared input list is complete for the gate job, and every input triggers the workflow."""

    @classmethod
    def setUpClass(cls):
        cls.wf, cls.on = load_workflow()
        cls.paths = cls.on[PR]["paths"]

    def triggers(self, path: str) -> bool:
        return any(matches(p, path) for p in self.paths)

    def test_every_sdk_tools_path_the_gate_job_runs_is_a_shared_input(self):
        runs = "\n".join(s.get("run", "") for s in self.wf["jobs"]["gate"]["steps"])
        named = set(re.findall(r"sdk/tools/[\w./-]+", runs))
        self.assertTrue(named, "the gate job names no sdk/tools path")
        for path in named:
            self.assertTrue(selection.is_shared_gate_input(path), f"{path} is used by the gate job but not shared")

    def test_app_gate_imports_only_shared_library_code(self):
        tree = ast.parse((ROOT / "sdk/tools/app-gate").read_text(encoding="utf-8"))
        local = {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        local = {m for m in local if (ROOT / "sdk/tools" / m).is_dir()}
        self.assertEqual(local, {"applib"})
        for module in local:
            self.assertTrue(selection.is_shared_gate_input(f"sdk/tools/{module}/common.py"), module)

    def test_every_shared_input_exists_and_triggers_the_workflow(self):
        for entry in selection.SHARED_GATE_INPUTS:
            path = ROOT / entry
            self.assertTrue(path.is_dir() if entry.endswith("/") else path.is_file(), f"stale entry {entry}")
            probe = entry + "x.py" if entry.endswith("/") else entry
            self.assertTrue(self.triggers(probe), f"a change to {entry} does not start ci-apps")
        self.assertTrue(self.triggers(selection.LICENCE_MATRIX))
        self.assertTrue(self.triggers("apps/beta/onemind.app.yaml"))

    def test_everything_validate_apps_loads_triggers_the_workflow(self):
        """Validation of every manifest runs whenever something validate-apps reads changes."""
        source = (ROOT / "sdk/tools/validate-apps").read_text(encoding="utf-8")
        missing = [str(f.relative_to(ROOT)) for f in core_closure(source) if not self.triggers(str(f.relative_to(ROOT)))]
        self.assertEqual(missing, [], "add these to ci-apps pull_request paths")
        data = ["/".join(re.findall(r'"([^"]+)"', m)) for m in re.findall(r'REPO_ROOT((?:\s*/\s*"[^"]+")+)', source)]
        files = [d for d in data if (ROOT / d).is_file()]
        self.assertGreaterEqual(len(files), 4, data)
        self.assertEqual([d for d in files if not self.triggers(d)], [], "add these to ci-apps pull_request paths")


def core_closure(source: str) -> set[Path]:
    """core/onemind_core files imported at module load, following imports (incl. try/if blocks)."""
    core = ROOT / "core"

    def module_file(name: str) -> Path | None:
        base = core.joinpath(*name.split("."))
        for f in (base.with_suffix(".py"), base / "__init__.py"):
            if f.is_file():
                return f
        return None

    def top_level(nodes):
        for n in nodes:
            yield n
            for field in ("body", "orelse", "finalbody"):
                if isinstance(n, (ast.Try, ast.If)):
                    yield from top_level(getattr(n, field, []))
            for h in getattr(n, "handlers", []) if isinstance(n, ast.Try) else []:
                yield from top_level(h.body)

    def imports(text: str, package: str) -> set[str]:
        out = set()
        for n in top_level(ast.parse(text).body):
            if isinstance(n, ast.Import):
                out |= {a.name for a in n.names}
            elif isinstance(n, ast.ImportFrom):
                parts = package.split(".")
                mod = ".".join(parts[:len(parts) - n.level + 1] + ([n.module] if n.module else [])) if n.level else n.module
                out.add(mod)
                out |= {f"{mod}.{a.name}" for a in n.names}
        return {m for m in out if m and m.split(".")[0] == "onemind_core"}

    seen: dict[str, Path] = {}
    todo = list(imports(source, ""))
    while todo:
        parts = todo.pop().split(".")
        for i in range(1, len(parts) + 1):
            name = ".".join(parts[:i])
            f = module_file(name)
            if f is None or name in seen:
                continue
            seen[name] = f
            package = name if f.name == "__init__.py" else name.rpartition(".")[0]
            todo += imports(f.read_text(encoding="utf-8"), package)
    if not seen:
        raise AssertionError("validate-apps imports no onemind_core module: the closure check is broken")
    return set(seen.values())


if __name__ == "__main__":
    unittest.main()
