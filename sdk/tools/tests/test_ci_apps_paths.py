# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for ci-apps triggers and its gate plan (sdk/tools/app-select plan).

The plan runs on the real app inventory with explicit changed-path fixtures (the git diff boundary;
test/unit/test_ci_apps_plan.py runs the command end to end through git). No registry, cluster, scan
or filesystem cleanup is performed by these tests.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk/tools"))
from applib import common, selection  # noqa: E402
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/ci-apps.yml").read_text())
# PyYAML's YAML 1.1 loader treats the Actions key `on` as True.
TRIGGERS = WORKFLOW.get("on", WORKFLOW.get(True))
MATRIX = ROOT / "research-output/evidence/license-matrix.csv"
MATRIX_PATH = "research-output/evidence/license-matrix.csv"
APPS = sorted(p.name for p in (ROOT / "apps").iterdir()
              if not p.name.startswith(("_", ".")) and (p / "onemind.app.yaml").is_file())


class CiAppsPathsTests(unittest.TestCase):
    def selected(self, *paths: str, event: str = "pull_request", base_ref: str = "release/next",
                 old_csv: Path | None = None, new_csv: Path | None = None) -> list[str]:
        keys = selection.inventory(common.APPS_DIR)

        def matrix_apps() -> list[str]:
            return selection.apps_with_changed_rows((old_csv or MATRIX).read_text(), (new_csv or MATRIX).read_text(),
                                                    selection.app_repos(common.APPS_DIR))

        return selection.plan(event, base_ref, paths, keys, matrix_apps)[0]

    def triggered(self, path: str) -> bool:
        return any(fnmatch.fnmatchcase(path, pattern)
                   for pattern in TRIGGERS["pull_request"]["paths"])

    def test_gate_inputs_trigger_and_select_every_app(self):
        self.assertTrue(APPS, "full re-gate must not pass with an empty app inventory")
        for path in (
            "sdk/tools/app-gate", "sdk/tools/validate-apps", "sdk/tools/app-select",
            "sdk/tools/applib/common.py", "sdk/tools/applib/readme.py",
            "sdk/tools/requirements.txt", "sdk/tools/ci/install-tools.sh",
            "sdk/schema/onemind.app.schema.json",
            ".github/workflows/ci-apps.yml",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.triggered(path))
                self.assertEqual(self.selected(path), APPS)

    def test_validator_inputs_trigger_validation_of_every_app_but_no_scans(self):
        """Founder decision 2026-11-25: these change only validate-apps' verdict. The validate job runs
        validate-apps over every app on every run, so they need no ~80-job re-gate on a pull request
        (a landing into main, the merge queue and the nightly still gate every app)."""
        for path in (
            "core/onemind_core/catalog.py", "core/onemind_core/manifest_convert.py",
            "core/onemind_core/ai_policy.py", "core/onemind_core/scan.py",
            "core/onemind_core/appsecrets/__init__.py", "core/onemind_core/appsecrets/spec.py",
            "core/onemind_core/machine_needs.py", "sdk/policy/host-ports.yaml",
            "internal/plugin/validate/validate.go", "cmd/onemind/cli/plugin.go",
            "go.mod", "go.sum",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.triggered(path))
                self.assertEqual(self.selected(path), [])
                self.assertEqual(self.selected(path, base_ref="main"), APPS)

    def matrix_fixture(self, tmp: str, extra_rows: str) -> Path:
        out = Path(tmp) / "new.csv"
        out.write_text(MATRIX.read_text() + extra_rows)
        return out

    def test_matrix_change_gates_only_apps_whose_rows_changed(self):
        repo = common.owner_repo(common.load_manifest(ROOT / "apps" / APPS[0]))
        self.assertTrue(repo)
        row = f"Fixture,v1,MIT,https://github.com/{repo}/blob/abc/LICENSE,github.com/{repo}@abc,y,n,n,y,n,x\n"
        with tempfile.TemporaryDirectory() as tmp:
            new = self.matrix_fixture(tmp, row)
            self.assertTrue(self.triggered(MATRIX_PATH))
            self.assertEqual(self.selected(MATRIX_PATH, new_csv=new), [APPS[0]])
            # plus the apps whose own files changed
            self.assertEqual(self.selected(MATRIX_PATH, f"apps/{APPS[1]}/README.md", new_csv=new),
                             sorted([APPS[0], APPS[1]]))

    def test_matrix_rows_about_no_app_gate_nothing(self):
        row = "Some kernel,v1,MIT,https://github.com/nobody/nothing/blob/abc/LICENSE,github.com/nobody/nothing@abc,y,n,n,y,n,x\n"
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.selected(MATRIX_PATH, new_csv=self.matrix_fixture(tmp, row)), [])

    def test_unreadable_matrix_gates_every_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text("not,the,header\n1,2,3\n")
            self.assertEqual(self.selected(MATRIX_PATH, new_csv=bad), APPS)

    def test_matrix_with_a_real_gate_input_gates_every_app(self):
        self.assertEqual(self.selected(MATRIX_PATH, "sdk/tools/app-gate"), APPS)

    def test_validation_only_paths_do_not_start_scans(self):
        for path in ("sdk/tools/tests/test_app_tools.py", "sdk/tools/app-readme",
                     "sdk/tools/app-scaffold", "renovate.json"):
            with self.subTest(path=path):
                self.assertTrue(self.triggered(path))
                self.assertEqual(self.selected(path), [])

    def test_gate_input_filenames_have_exact_boundaries(self):
        for path in ("sdk/tools/app-gate.md", "sdk/tools/validate-apps-notes",
                     "sdk/tools/requirements.txt.notes", "sdk/tools/ci/install-tools.sh.notes"):
            with self.subTest(path=path):
                self.assertTrue(self.triggered(path))
                self.assertEqual(self.selected(path), [])

    def test_unrelated_sdk_and_core_paths_do_not_trigger(self):
        for path in ("sdk/go/client.go", "sdk/python/client.py", "sdk/openapi.json",
                     "sdk/contracts/poc-v0.md", "core/onemind_core/app.py",
                     "docs/leap/STATUS.md", "CHANGELOG.md"):
            with self.subTest(path=path):
                self.assertFalse(self.triggered(path))
                self.assertEqual(self.selected(path), [])

    def test_changed_apps_are_deduplicated_sorted_and_checked_for_existence(self):
        paths = [f"apps/{app}/manifests/deployment.yaml" for app in reversed(APPS[:2])]
        paths += paths[:1] + ["apps/no-such-app/onemind.app.yaml", "apps/_intake/queue/a--b.yaml",
                            "apps/.hidden/README.md", "sdk/tools/tests/test_app_tools.py"]
        self.assertEqual(self.selected(*paths), APPS[:2])
        for path in paths:
            self.assertTrue(self.triggered(path))

    def test_gate_input_wins_over_changed_app_subset(self):
        self.assertEqual(self.selected(f"apps/{APPS[0]}/README.md", "sdk/tools/app-gate"), APPS)

    def test_full_gate_prioritizes_changed_apps_then_keeps_the_full_inventory(self):
        changed = APPS[-1]
        selected = self.selected(f"apps/{changed}/manifests/deployment.yaml", "sdk/tools/app-gate")
        self.assertEqual(selected, [changed, *APPS[:-1]])

    def test_scan_artifacts_do_not_depend_on_validation(self):
        jobs = WORKFLOW["jobs"]
        self.assertEqual(jobs["gate"]["needs"], "plan")
        self.assertNotIn("needs", jobs["plan"])

    def test_dispatch_selects_every_app_without_a_pr_diff(self):
        for event in ("workflow_dispatch", "schedule", "merge_group"):
            with self.subTest(event=event):
                self.assertIn(event, TRIGGERS)
                self.assertEqual(self.selected(event=event, base_ref=""), APPS)

    def test_empty_diff_selects_no_apps(self):
        self.assertEqual(self.selected(), [])


if __name__ == "__main__":
    unittest.main()
