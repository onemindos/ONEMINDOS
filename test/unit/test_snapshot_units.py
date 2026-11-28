# SPDX-License-Identifier: Apache-2.0
"""BAK-04 (#241): Files uses the shipped timeline without breaking older /data layouts."""
import subprocess
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
        plugin = LAYERS / "base/usr/lib/snapper/plugins/50-onemind-files"
        self.assertTrue(plugin.stat().st_mode & 0o111)
        gateway = LAYERS / "onemind/usr/lib/systemd/system/onemind-gateway.service"
        self.assertIn("Environment=ONEMIND_FILES_SNAPSHOTS_DIR=/data/storage/.snapshots", gateway.read_text())

    def test_no_unused_copy_in_the_deploy_bundle(self):
        for name in ("onemind-snapshots.service", "onemind-snapshots.timer"):
            self.assertFalse((ROOT / "deploy/systemd" / name).exists(), name)

    def test_upgrade_rollback_read_and_write_then_upgrade_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = fb.Paths(tmp)
            legacy = Path(p.files)
            storage = Path(tmp) / "data/storage"
            (storage / ".snapshots").mkdir(parents=True)
            subvolumes = set()
            run = subprocess.run

            def old_slot_boot():
                # The pre-#241 first boot only made and chmodded this directory.
                legacy.mkdir(mode=0o750, parents=True, exist_ok=True)
                legacy.chmod(0o750)

            def command(argv, *, check):
                self.assertTrue(check)
                source, target = map(Path, argv[-2:])
                if argv[:3] == ["btrfs", "subvolume", "create"]:
                    target.mkdir()
                    subvolumes.add(target.stat().st_ino)
                elif argv[0] == "cp":
                    self.assertIn("--reflink=always", argv)
                    run([arg for arg in argv if arg != "--reflink=always"], check=True)
                elif argv[0] == "mv":
                    self.assertEqual(argv[1:-2], ["--exchange", "--no-copy", "-T", "--"])
                    interim = source.with_name("exchange-interim")
                    target.rename(interim)
                    source.rename(target)
                    interim.rename(source)
                else:
                    # Bind mounts, if any, disappear when switching slots.
                    self.assertIn(argv[0], ("sync", "mount"))

            old_slot_boot()
            item = legacy / "old.txt"
            item.write_bytes(b"household file")
            item.chmod(0o640)
            (legacy / "hardlink").hardlink_to(item)
            (legacy / "link").symlink_to("old.txt")
            with (patch.object(fb.os.path, "ismount", return_value=True),
                  patch.object(fb, "onemind_ids", return_value=None),
                  patch.object(fb, "is_btrfs_subvolume", lambda path: Path(path).stat().st_ino in subvolumes,
                               create=True),
                  patch.object(fb.subprocess, "run", command)):
                fb.ensure_files_root(p)
                old_slot_boot()
                self.assertEqual(item.read_bytes(), b"household file")
                item.write_bytes(b"edited on the old slot")
                (legacy / "rollback.txt").write_bytes(b"created on the old slot")
                fb.ensure_files_root(p)

            self.assertEqual(item.read_bytes(), b"edited on the old slot")
            self.assertEqual((legacy / "rollback.txt").read_bytes(), b"created on the old slot")
            self.assertEqual(item.stat().st_mode & 0o777, 0o640)
            self.assertEqual((legacy / "hardlink").stat().st_ino, item.stat().st_ino)
            self.assertEqual((legacy / "link").readlink(), Path("old.txt"))
            self.assertEqual((storage / ".snapshots").stat().st_mode & 0o777, 0o750)
            self.assertFalse(Path(p.files + ".snapshot-stage").exists())
            self.assertFalse((storage / "files").exists())
            with patch.object(fb.os.path, "ismount", return_value=False):
                fb.ensure_files_root(p)
            self.assertEqual(item.read_bytes(), b"edited on the old slot")


if __name__ == "__main__":
    unittest.main()
