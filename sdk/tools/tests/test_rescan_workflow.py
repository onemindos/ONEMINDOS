# SPDX-License-Identifier: Apache-2.0
"""apps-rescan.yml: plan -> one matrix job per app -> publish. Checks the shape and runs the publish job's
"Collect" step against fixture artifacts (allow-list, regular-file check, newly-blocked, tool errors).
No network and no git; the step runs in a temporary directory."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/apps-rescan.yml").read_text())
JOBS = WORKFLOW["jobs"]
COLLECT = next(s["run"] for s in JOBS["publish"]["steps"] if s.get("id") == "collect")
MANIFEST = "metadata:\n  id: {id}\n  tier: {tier}\n"


class ShapeTests(unittest.TestCase):
    def test_matrix_runs_every_app_independently(self):
        job = JOBS["rescan"]
        self.assertEqual(job["needs"], "plan")
        self.assertIs(job["strategy"]["fail-fast"], False)
        self.assertEqual(job["strategy"]["max-parallel"], 8)
        self.assertIn("fromJSON(needs.plan.outputs.apps)", job["strategy"]["matrix"]["app"])
        gate = next(s["run"] for s in job["steps"] if s.get("name") == "Rescan the app")
        self.assertIn("--tier write", gate)
        self.assertIn("--smoke", gate)

    def test_only_publish_can_write(self):
        self.assertEqual(JOBS["rescan"]["permissions"], {"contents": "read"})
        self.assertEqual(JOBS["plan"]["permissions"], {"contents": "read"})
        self.assertEqual(JOBS["publish"]["permissions"]["contents"], "write")


class CollectTests(unittest.TestCase):
    def collect(self, apps: dict[str, dict], blocked_after: dict[str, str] | None = None):
        """apps: id -> {status, files:{path: bytes|None}, tier_before}. Returns (outputs, exit code, stderr, root)."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for id_, spec in apps.items():
            (root / "apps" / id_).mkdir(parents=True)
            (root / "apps" / id_ / "onemind.app.yaml").write_text(MANIFEST.format(id=id_, tier=spec["tier_before"]))
            d = root / "tmp" / "results" / f"apps-rescan-{id_}"
            d.mkdir(parents=True)
            if spec.get("status") is not None:
                (d / "status").write_text(f"{spec['status']}\n")
            files = spec.get("files") or {}
            if files:
                (d / "files.txt").write_text("".join(f"{p}\n" for p in files))
                with tarfile.open(d / "apps.tar", "w") as tar:
                    for p, data in files.items():
                        info = tarfile.TarInfo(p)
                        if data is None:  # a symlink instead of a regular file
                            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
                            tar.addfile(info)
                        else:
                            info.size = len(data)
                            tar.addfile(info, io.BytesIO(data))
        out = root / "gh-output"
        env = dict(os.environ, RUNNER_TEMP=str(root / "tmp"), GITHUB_OUTPUT=str(out),
                   PLANNED=json.dumps(list(apps)))
        proc = subprocess.run(["bash", "-c", COLLECT], cwd=root, env=env, text=True, capture_output=True)
        outputs = dict(ln.split("=", 1) for ln in out.read_text().splitlines()) if out.exists() else {}
        return outputs, proc.returncode, proc.stderr, root

    def files_for(self, id_: str, tier: str) -> dict:
        return {f"apps/{id_}/scan.json": b"{}\n", f"apps/{id_}/README.md": b"r\n",
                f"apps/{id_}/onemind.app.yaml": MANIFEST.format(id=id_, tier=tier).encode()}

    def test_blocked_app_does_not_stop_the_others(self):
        out, rc, err, root = self.collect({
            "aaa": {"status": 1, "tier_before": "verified", "files": self.files_for("aaa", "blocked")},
            "bbb": {"status": 0, "tier_before": "verified", "files": self.files_for("bbb", "verified")},
        })
        self.assertEqual(rc, 0, err)
        self.assertEqual(out["newly_blocked"], "aaa")
        self.assertEqual(out["errors"], "")
        self.assertTrue((root / "apps/bbb/scan.json").is_file())   # new file picked up
        self.assertIn("tier: blocked", (root / "apps/aaa/onemind.app.yaml").read_text())

    def test_already_blocked_is_not_newly_blocked(self):
        out, rc, _, _ = self.collect({"aaa": {"status": 1, "tier_before": "blocked",
                                              "files": self.files_for("aaa", "blocked")}})
        self.assertEqual((rc, out["newly_blocked"]), (0, ""))

    def test_tool_errors_and_missing_results_are_reported(self):
        out, rc, _, _ = self.collect({
            "aaa": {"status": 2, "tier_before": "verified"},
            "bbb": {"status": None, "tier_before": "verified"},
            "ccc": {"status": 0, "tier_before": "verified"},
        })
        self.assertEqual(rc, 0)
        self.assertEqual(out["errors"].split(), ["aaa", "bbb"])

    def test_files_outside_the_apps_own_allow_list_are_refused(self):
        for bad in ("apps/bbb/scan.json", "apps/aaa/manifests/x.yaml", "core/app.py", "apps/aaa/scan.json.sh"):
            with self.subTest(bad=bad):
                _, rc, err, root = self.collect({"aaa": {"status": 0, "tier_before": "verified",
                                                         "files": {bad: b"x"}},
                                                 "bbb": {"status": 0, "tier_before": "verified"}})
                self.assertNotEqual(rc, 0)
                self.assertFalse((root / "core").exists())

    def test_symlinks_are_refused(self):
        _, rc, err, _ = self.collect({"aaa": {"status": 0, "tier_before": "verified",
                                              "files": {"apps/aaa/scan.json": None}}})
        self.assertNotEqual(rc, 0)
        self.assertIn("not a regular file", err)


if __name__ == "__main__":
    unittest.main()
