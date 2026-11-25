# SPDX-License-Identifier: Apache-2.0
"""The PR and rescan selectors include container built-ins and isolate their artifacts."""
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from applib import selection


class SystemAppSelectionTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.repo = Path(work.name)

    def manifest(self, directory, spec):
        root = self.repo / "apps" / directory
        root.mkdir(parents=True)
        (root / "onemind.app.yaml").write_text(f"spec:\n{spec}", encoding="utf-8")

    def test_inventory_and_pr_diff_include_only_container_built_ins(self):
        self.manifest("passwords", "  manifests: manifests\n")
        self.manifest("_system/passwords", "  runtime: container\n  manifests: manifests\n")
        self.manifest("_system/work", "  runtime: module\n")
        self.manifest("_intake/ignored", "  manifests: manifests\n")
        keys = selection.inventory(self.repo / "apps")
        self.assertEqual(keys, ["passwords", "system.passwords"])
        self.assertEqual(selection.changed_apps(keys, "apps/_system/passwords/manifests/deployment.yml\n"
                                                      "apps/_system/work/README.md\n"), ["system.passwords"])
        self.assertEqual(selection.app_path("system.passwords").as_posix(), "apps/_system/passwords")
        with self.assertRaises(ValueError):
            selection.app_path("system../passwords")

    def test_publish_updates_only_the_builtin_result(self):
        self.manifest("passwords", "  manifests: manifests\n")
        self.manifest("_system/passwords", "  runtime: container\n")
        archive = self.repo / "apps.tar"
        path = "apps/_system/passwords/scan.json"

        def prepare(*entries):
            with tarfile.open(archive, "w") as tar:
                for name in entries:
                    info = tarfile.TarInfo(name)
                    info.size = len(b"{}\n")
                    tar.addfile(info, io.BytesIO(b"{}\n"))

        prepare(path, "apps/passwords/scan.json")
        with self.assertRaises(ValueError):
            selection.apply_scan("system.passwords", path + "\n", archive, self.repo)
        self.assertFalse((self.repo / path).exists())
        prepare(path)
        with self.assertRaises(ValueError):
            selection.apply_scan("passwords", path + "\n", archive, self.repo)
        selection.apply_scan("system.passwords", path + "\n", archive, self.repo)
        self.assertEqual((self.repo / path).read_bytes(), b"{}\n")
        self.assertFalse((self.repo / "apps/passwords/scan.json").exists())
