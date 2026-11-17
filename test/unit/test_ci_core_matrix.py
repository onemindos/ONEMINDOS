# SPDX-License-Identifier: Apache-2.0
"""scripts/ci-core-matrix.py: which ci-core shards run per event (CI-03, issue 228)."""
import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci_core_matrix", ROOT / "scripts" / "ci-core-matrix.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)


def backends(include):
    return sorted({j["backend"] for j in include}), len(include)


class Shards(unittest.TestCase):
    def test_pr_runs_only_the_three_sqlite_shards(self):
        self.assertEqual(backends(cm.shards("pull_request")), (["sqlite"], 3))

    def test_merge_queue_runs_the_four_postgres_shards_for_a_core_change(self):
        self.assertEqual(backends(cm.shards("merge_group", ["core/onemind_core/app.py"])), (["postgresql"], 4))
        self.assertEqual(len(cm.shards("merge_group", ["sdk/python/x.py"])), 4)
        self.assertEqual(len(cm.shards("merge_group", [".github/workflows/ci-core.yml"])), 4)

    def test_merge_queue_skips_a_change_outside_core(self):
        self.assertEqual(cm.shards("merge_group", ["docs/README.md", "os/rootfs/Containerfile"]), [])
        self.assertEqual(cm.shards("merge_group", ["score/x"]), [])  # prefix match, not substring

    def test_merge_queue_runs_when_the_change_list_is_unknown_or_truncated(self):
        self.assertEqual(len(cm.shards("merge_group", None)), 4)
        self.assertEqual(len(cm.shards("merge_group", ["docs/x"] * cm.COMPARE_LIMIT)), 4)

    def test_main_and_manual_runs_run_all_seven(self):
        for ev in ("push", "workflow_dispatch"):
            self.assertEqual(backends(cm.shards(ev)), (["postgresql", "sqlite"], 7))

    def test_shards_cover_what_the_suite_splits_into(self):
        # conftest.py splits by ONEMIND_TEST_SHARD=k/n; every k from 1..n must be present once.
        for backend, n in (("sqlite", 3), ("postgresql", 4)):
            got = sorted(j["shard"] for j in cm.shards("push") if j["backend"] == backend)
            self.assertEqual(got, [f"{k}/{n}" for k in range(1, n + 1)])


class Main(unittest.TestCase):
    def run_main(self, env, files=None):
        with tempfile.NamedTemporaryFile("r", delete=False, suffix=".out") as f:
            path = f.name
        try:
            with mock.patch.dict(os.environ, {**env, "GITHUB_OUTPUT": path}, clear=True), \
                 mock.patch.object(cm, "changed_files", return_value=files), \
                 mock.patch("sys.stdout"):
                self.assertEqual(cm.main(), 0)
            return dict(line.split("=", 1) for line in Path(path).read_text().splitlines())
        finally:
            os.unlink(path)

    def test_writes_matrix_and_run_flag(self):
        out = self.run_main({"EVENT": "pull_request"})
        self.assertEqual(out["run"], "true")
        self.assertEqual(len(json.loads(out["matrix"])["include"]), 3)

    def test_docs_only_merge_skips_the_test_job(self):
        out = self.run_main({"EVENT": "merge_group", "REPO": "o/r", "BASE_SHA": "a", "HEAD_SHA": "b",
                             "GH_TOKEN": "t"}, files=["docs/x.md"])
        self.assertEqual(out["run"], "false")
        self.assertEqual(json.loads(out["matrix"]), {"include": []})


class Workflow(unittest.TestCase):
    def test_workflow_uses_the_plan_job(self):
        wf = (ROOT / ".github" / "workflows" / "ci-core.yml").read_text(encoding="utf-8")
        self.assertIn("merge_group:", wf)
        self.assertIn("scripts/ci-core-matrix.py", wf)
        self.assertRegex(wf, r"matrix: \$\{\{ fromJSON\(needs\.plan\.outputs\.matrix\) \}\}")
        self.assertIsNone(re.search(r"backend: postgresql, shard", wf), "shards live in the script now")


if __name__ == "__main__":
    unittest.main()
