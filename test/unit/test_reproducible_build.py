# SPDX-License-Identifier: Apache-2.0
"""Step 2 PR 8 (reproducible build): the root filesystem's identity comes from the commit, not from the build run."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
sys.path.insert(0, os.path.join(ROOT, "os", "rootfs"))
import assemble  # noqa: E402
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("sde", os.path.join(ROOT, "os", "rootfs", "source-date-epoch.py"))
sde = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sde)


class Epoch(unittest.TestCase):
    def test_snapshot_to_epoch(self):
        self.assertEqual(sde.epoch("20261111T000000Z"), 1794355200)
        self.assertEqual(sde.epoch("20261111T000001Z"), 1794355201)

    def test_no_snapshot_no_epoch(self):
        self.assertIsNone(sde.epoch("none"))
        self.assertIsNone(sde.epoch(""))

    def test_the_pinned_snapshot_has_one(self):
        snap = next(l.split("=", 1)[1].strip() for l in open(os.path.join(ROOT, "os/rootfs/debian.args")) if l.startswith("SNAPSHOT="))
        self.assertIsNotNone(sde.epoch(snap))

    def test_env_parse(self):
        self.assertIsNone(assemble.source_date_epoch({}))
        self.assertIsNone(assemble.source_date_epoch({"SOURCE_DATE_EPOCH": ""}))
        self.assertEqual(assemble.source_date_epoch({"SOURCE_DATE_EPOCH": "1794355200"}), 1794355200)
        with self.assertRaises(SystemExit):
            assemble.source_date_epoch({"SOURCE_DATE_EPOCH": "yesterday"})

    def test_make_hands_the_epoch_to_build_and_assembler(self):
        r = subprocess.run(["make", "-n", "rootfs", "image", "BOARD=x86_64-efi"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--build-arg SOURCE_DATE_EPOCH=1794355200", r.stdout)
        self.assertIn("rewrite-timestamp=true", r.stdout)
        self.assertIn("-e SOURCE_DATE_EPOCH=1794355200", r.stdout)


class RootFsIdentity(unittest.TestCase):
    def test_uuid_is_stable_and_specific(self):
        a = assemble.root_fs_uuid("x86_64-efi", "1.0", 1794355200)
        self.assertEqual(a, assemble.root_fs_uuid("x86_64-efi", "1.0", 1794355200))
        self.assertNotEqual(a, assemble.root_fs_uuid("x86_64-efi", "1.0-next", 1794355200))   # slot A vs slot B
        self.assertNotEqual(a, assemble.root_fs_uuid("arm64-efi", "1.0", 1794355200))
        self.assertNotEqual(a, assemble.root_fs_uuid("x86_64-efi", "1.0", 1794355201))

    def test_mke2fs_fixes_uuid_and_hash_seed_with_an_epoch(self):
        u = assemble.root_fs_uuid("b", "v", 5)
        cmd = assemble.mke2fs_root_cmd("/t", "/o.ext4", 64, 5, u)
        self.assertEqual(cmd[cmd.index("-U") + 1], u)
        self.assertEqual(cmd[cmd.index("-E") + 1], f"root_owner=0:0,hash_seed={u}")

    def test_mke2fs_without_epoch_is_the_old_call(self):
        cmd = assemble.mke2fs_root_cmd("/t", "/o.ext4", 64, None, "ignored")
        self.assertNotIn("-U", cmd)
        self.assertEqual(cmd[cmd.index("-E") + 1], "root_owner=0:0")

    def test_tree_release_keys(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "usr/lib"))
            open(os.path.join(d, "usr/lib/os-release"), "w").write('ID=debian\nONEMIND_VERSION="1.2"\nONEMIND_BOARD="vm"\n')
            self.assertEqual(assemble.tree_release_keys(d), ("vm", "1.2"))

    @unittest.skipUnless(sys.platform.startswith("linux") and subprocess.run(["which", "mke2fs"], capture_output=True).returncode == 0,
                         "needs Linux mke2fs and GNU du: it runs on the build workers, in the tools image, and in make repro-check")
    def test_two_runs_same_bytes(self):
        import hashlib
        import time

        epoch = 1794355200
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"SOURCE_DATE_EPOCH": str(epoch)}):
            tree = Path(d) / "tree"
            (tree / "usr/lib").mkdir(parents=True)
            (tree / "etc").mkdir()
            (tree / "usr/lib/os-release").write_text('ONEMIND_VERSION="t"\nONEMIND_BOARD="b"\n')
            for i in range(50):
                (tree / "etc" / f"f{i}").write_text("x" * i)
            source = tree / "etc/f1"
            mtime_ns = source.stat().st_mtime_ns
            hashes = []
            for n in (1, 2):
                # A host read can advance an input inode's atime between builds. Set two distinct
                # atimes after the epoch so this always exercises the assembler tool's clamping.
                os.utime(source, ns=((epoch + n) * 10**9, mtime_ns))
                out = Path(d) / f"r{n}.ext4"
                assemble.cmd_ext4(type("A", (), {"work": d, "out": out, "size_mib": 16})())
                hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
                time.sleep(1.1)  # the second run starts at a different second
            version = subprocess.run(["mke2fs", "-V"], check=True, capture_output=True, text=True).stderr.splitlines()[0]
            self.assertEqual(hashes[0], hashes[1], version)


if __name__ == "__main__":
    unittest.main()
