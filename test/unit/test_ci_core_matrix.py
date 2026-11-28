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

    def test_writes_one_matrix_per_backend(self):
        """CI-13: the SQLite job (may run on the Mac) and the PostgreSQL job (hosted) each get their own."""
        for event, want in (("pull_request", (3, 0)), ("push", (3, 4))):
            out = self.run_main({"EVENT": event})
            sq, pg = json.loads(out["sqlite"])["include"], json.loads(out["postgresql"])["include"]
            self.assertEqual((len(sq), len(pg)), want, event)
            self.assertEqual({j["backend"] for j in sq} | {"sqlite"}, {"sqlite"})
            self.assertEqual({j["backend"] for j in pg} | {"postgresql"}, {"postgresql"})
            self.assertEqual(out["run_sqlite"], "true")
            self.assertEqual(out["run_postgresql"], "true" if want[1] else "false")
        out = self.run_main({"EVENT": "merge_group", "REPO": "o/r", "BASE_SHA": "a", "HEAD_SHA": "b",
                             "GH_TOKEN": "t"}, files=["core/x.py"])
        self.assertEqual((out["run_sqlite"], out["run_postgresql"]), ("false", "true"))

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
        self.assertIsNone(re.search(r"backend: postgresql, shard", wf), "shards live in the script now")

    def test_each_backend_has_its_own_job_and_only_postgresql_has_services(self):
        """SQLite shards run without Docker; PostgreSQL keeps its services."""
        import yaml
        jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-core.yml").read_text(encoding="utf-8"))["jobs"]
        sq, pg = jobs["test"], jobs["test-postgresql"]
        self.assertEqual(sq["strategy"]["matrix"], "${{ fromJSON(needs.plan.outputs.sqlite) }}")
        self.assertEqual(pg["strategy"]["matrix"], "${{ fromJSON(needs.plan.outputs.postgresql) }}")
        self.assertIn("run_sqlite == 'true'", sq["if"])
        self.assertIn("run_postgresql == 'true'", pg["if"])
        self.assertNotIn("services", sq)
        self.assertEqual(set(pg["services"]), {"nats", "postgres"})
        self.assertEqual(pg["runs-on"], "ubuntu-24.04")
        self.assertEqual(sq["name"], pg["name"])  # check names unchanged: test (<backend> <k>/<n>)
        for out in ("sqlite", "run_sqlite", "postgresql", "run_postgresql"):
            self.assertIn(out, jobs["plan"]["outputs"])

    def test_shards_install_platform_pinned_nats_in_their_own_runner_space(self):
        import yaml
        jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci-core.yml").read_text(encoding="utf-8"))["jobs"]
        for job in (jobs["test"], jobs["test-postgresql"]):
            self.assertIn("bash sdk/tools/ci/install-nats.sh", [s.get("run") for s in job["steps"]])
        installer = (ROOT / "sdk/tools/ci/install-nats.sh").read_text(encoding="utf-8")
        self.assertIn('mktemp -d "${RUNNER_TEMP:?}/nats.XXXXXX"', installer)
        self.assertIn('case "$(uname -s)"', installer)
        self.assertIn('os=linux; sum_var="NATS_SHA256_${arch}"; checksum=(sha256sum)', installer)
        self.assertIn('os=darwin; sum_var="NATS_SHA256_darwin_${arch}"; checksum=(shasum -a 256)', installer)
        self.assertIn('"${checksum[@]}" -c -', installer)
        self.assertIn('"$bin/nats-server" --version', installer)


if __name__ == "__main__":
    unittest.main()
