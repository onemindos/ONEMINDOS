# SPDX-License-Identifier: Apache-2.0
"""BAK-04 (#241): Files uses the shipped timeline without breaking older /data layouts."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ROOT / "os/rootfs/layers"
sys.path.insert(0, str(LAYERS / "onemind/usr/lib/onemind"))
sys.path.insert(1, str(ROOT / "core"))
import onemind_firstboot as fb


class SnapshotUnits(unittest.TestCase):
    def test_timeline_waits_for_files_placement_and_creates_traversable_entries(self):
        dropin = LAYERS / "base/usr/lib/systemd/system/snapper-timeline.service.d/onemind.conf"
        svc = dropin.read_text()
        self.assertIn("After=onemind-firstboot.service", svc)
        self.assertIn("ConditionPathExists=/data/storage/.snapshots", svc)
        self.assertIn("UMask=0022", svc)
        gateway = LAYERS / "onemind/usr/lib/systemd/system/onemind-gateway.service"
        self.assertIn("Environment=ONEMIND_FILES_SNAPSHOTS_DIR=/data/storage/.snapshots", gateway.read_text())

    def test_migrate_legacy_files_before_bind_and_keep_their_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = fb.Paths(tmp)
            storage = Path(tmp) / "data/storage"
            history = storage / ".snapshots"
            history.mkdir(parents=True)
            legacy = Path(p.files)
            legacy.mkdir(parents=True)
            item = legacy / "old.txt"
            item.write_bytes(b"household file")
            item.chmod(0o640)
            (legacy / "link").symlink_to("old.txt")

            def command(argv, *, check):
                self.assertTrue(check)
                if argv[0] == "cp":
                    self.assertIn("--reflink=always", argv)
                    shutil.copytree(argv[-2], argv[-1], symlinks=True)
                if argv[0] == "mount":
                    self.assertEqual(argv, ["mount", "--bind", str(storage / "files"), p.files])
                    self.assertEqual(list(legacy.iterdir()), [])
                    self.assertEqual((Path(p.files + ".before-snapper") / "old.txt").read_bytes(), b"household file")

            with patch.object(fb.os.path, "ismount", return_value=True), patch.object(fb.subprocess, "run", command):
                fb.ensure_files_root(p)
            saved = storage / "files/old.txt"
            self.assertEqual(saved.read_bytes(), b"household file")
            self.assertEqual(saved.stat().st_mode & 0o777, 0o640)
            self.assertEqual((storage / "files/link").readlink(), Path("old.txt"))
            self.assertEqual(history.stat().st_mode & 0o777, 0o750)
            self.assertFalse(Path(p.files + ".before-snapper").exists())
            with patch.object(fb.os.path, "ismount", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "did not mount"):
                    fb.ensure_files_root(p)

    def test_no_unused_copy_in_the_deploy_bundle(self):
        for name in ("onemind-snapshots.service", "onemind-snapshots.timer"):
            self.assertFalse((ROOT / "deploy/systemd" / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
