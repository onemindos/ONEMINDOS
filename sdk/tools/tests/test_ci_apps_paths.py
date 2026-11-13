# SPDX-License-Identifier: Apache-2.0
"""Regression coverage for ci-apps triggers and its actual Changed apps shell.

The git-diff boundary supplies explicit changed-path fixtures; the workflow's
selection code, existing manifest checks and jq serialization run unchanged.
No registry, cluster, scan or filesystem cleanup is performed by these tests.
"""
from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "sdk/tools"))
from applib import common  # noqa: E402
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/ci-apps.yml").read_text())
# PyYAML's YAML 1.1 loader treats the Actions key `on` as True.
TRIGGERS = WORKFLOW.get("on", WORKFLOW.get(True))
CHANGED = next(step["run"] for step in WORKFLOW["jobs"]["validate"]["steps"]
               if step.get("id") == "changed")
MATRIX = ROOT / "research-output/evidence/license-matrix.csv"
MATRIX_PATH = "research-output/evidence/license-matrix.csv"
APPS = sorted(p.name for p in (ROOT / "apps").iterdir()
              if not p.name.startswith(("_", ".")) and (p / "onemind.app.yaml").is_file())


class CiAppsPathsTests(unittest.TestCase):
    # `git diff` lists CHANGED_FILES; `git show <rev>:<path>` prints the old or new matrix fixture.
    GIT_STUB = ('git() { case "$1" in\n'
                '  diff) printf "%s\\n" "$CHANGED_FILES" ;;\n'
                '  show) case "$2" in fixture-base:*) cat "$OLD_CSV" ;; fixture-head:*) cat "$NEW_CSV" ;; esac ;;\n'
                'esac; }\n')

    def selected(self, *paths: str, event: str = "pull_request",
                 old_csv: Path | None = None, new_csv: Path | None = None) -> list[str]:
        env = dict(os.environ, CHANGED_FILES="\n".join(paths),
                   BASE_SHA="fixture-base", HEAD_SHA="fixture-head",
                   GITHUB_EVENT_NAME=event, GITHUB_OUTPUT="/dev/stdout",
                   OLD_CSV=str(old_csv or MATRIX), NEW_CSV=str(new_csv or MATRIX))
        result = subprocess.run(
            ["bash", "-c", self.GIT_STUB + CHANGED],
            cwd=ROOT, env=env, text=True, capture_output=True, check=True,
        )
        outputs = [line.removeprefix("apps=") for line in result.stdout.splitlines()
                   if line.startswith("apps=")]
        self.assertEqual(len(outputs), 1, result.stdout)
        return json.loads(outputs[0])

    def triggered(self, path: str) -> bool:
        return any(fnmatch.fnmatchcase(path, pattern)
                   for pattern in TRIGGERS["pull_request"]["paths"])

    def test_gate_inputs_trigger_and_select_every_app(self):
        self.assertTrue(APPS, "full re-gate must not pass with an empty app inventory")
        for path in (
            "sdk/tools/app-gate", "sdk/tools/validate-apps",
            "sdk/tools/applib/common.py", "sdk/tools/applib/readme.py",
            "sdk/tools/requirements.txt", "sdk/tools/ci/install-tools.sh",
            "sdk/schema/onemind.app.schema.json",
            ".github/workflows/ci-apps.yml",
        ):
            with self.subTest(path=path):
                self.assertTrue(self.triggered(path))
                self.assertEqual(self.selected(path), APPS)

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
        paths += paths[:1] + ["apps/no-such-app/onemind.app.yaml", "apps/_intake/queue.yaml",
                            "apps/.hidden/README.md", "sdk/tools/tests/test_app_tools.py"]
        self.assertEqual(self.selected(*paths), APPS[:2])
        for path in paths:
            self.assertTrue(self.triggered(path))

    def test_gate_input_wins_over_changed_app_subset(self):
        self.assertEqual(self.selected(f"apps/{APPS[0]}/README.md", "sdk/tools/app-gate"), APPS)

    def test_dispatch_selects_every_app_without_a_pr_diff(self):
        self.assertIn("workflow_dispatch", TRIGGERS)
        self.assertEqual(self.selected(event="workflow_dispatch"), APPS)

    def test_empty_diff_selects_no_apps(self):
        self.assertEqual(self.selected(), [])


if __name__ == "__main__":
    unittest.main()
