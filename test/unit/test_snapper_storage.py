# SPDX-License-Identifier: Apache-2.0
"""Plan PR 6 (#152): snapper keeps timeline snapshots of the owner's files (the @storage subvolume at /data/storage)
and btrfsmaintenance scrubs /data monthly. Configs are baked into /etc (read-only root). The boot proof is
test/qemu/dataenc.py E8 (CRITERIA-SNAPPER.md); these tests pin the files that make it work."""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join("os", "rootfs", "layers", "base")


def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def sysconfig(text):
    """The KEY="value" lines of a snapper or btrfsmaintenance file (shell syntax, no expansion)."""
    return dict(re.findall(r'^([A-Z_0-9]+)="(.*)"\s*$', text, re.M))


class SnapperConfig(unittest.TestCase):
    def test_one_config_and_it_snapshots_storage_only(self):
        cfgs = sysconfig(rd(BASE, "etc/default/snapper"))
        self.assertEqual(cfgs["SNAPPER_CONFIGS"], "storage")          # libsnapper lists configs from here
        files = os.listdir(os.path.join(ROOT, BASE, "etc/snapper/configs"))
        self.assertEqual(files, ["storage"])                           # none for / (read-only) or /data (k3s, databases)
        c = sysconfig(rd(BASE, "etc/snapper/configs/storage"))
        self.assertEqual((c["SUBVOLUME"], c["FSTYPE"]), ("/data/storage", "btrfs"))
        self.assertEqual(c["TIMELINE_CREATE"], "yes")
        self.assertEqual(c["TIMELINE_CLEANUP"], "yes")

    def test_the_subvolume_matches_what_data_encrypt_makes_and_mounts(self):
        enc = rd(BASE, "usr/lib/onemind/data_encrypt.py")
        self.assertIn('SNAPSHOTS_SUBVOL = "@storage/.snapshots"', enc)   # snapper expects SUBVOLUME/.snapshots
        unit = rd(BASE, "usr/lib/systemd/system/data-storage.mount")
        self.assertIn("Where=/data/storage", unit)
        self.assertEqual(sysconfig(rd(BASE, "etc/snapper/configs/storage"))["SUBVOLUME"], "/data/storage")

    def test_retention_is_bounded_so_snapshots_cannot_fill_the_disk(self):
        c = sysconfig(rd(BASE, "etc/snapper/configs/storage"))
        total = sum(int(c[f"TIMELINE_LIMIT_{k}"]) for k in ("HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY"))
        self.assertTrue(0 < total <= 60, total)
        self.assertEqual(c["BACKGROUND_COMPARISON"], "no")
        self.assertGreaterEqual(float(c["FREE_LIMIT"]), 0.1)

    def test_the_root_is_never_snapshotted_and_apt_hooks_are_off(self):
        self.assertEqual(sysconfig(rd(BASE, "etc/default/snapper"))["DISABLE_APT_SNAPSHOT"], "yes")
        self.assertFalse(os.path.exists(os.path.join(ROOT, BASE, "etc/snapper/configs/root")))


class Units(unittest.TestCase):
    def test_timers_are_enabled_on_the_debian_leg_and_the_refresh_machinery_is_masked(self):
        cf = rd("os/rootfs/Containerfile")
        m = re.search(r"if \[ \"\$\{LEG\}\" = debian \]; then \\\n(.*?)\n    fi;", cf, re.S)
        self.assertIsNotNone(m)
        block = m.group(1)
        for unit in ("snapper-timeline.timer", "snapper-cleanup.timer", "btrfs-scrub.timer"):
            self.assertRegex(block, rf"systemctl enable [^\n]*{re.escape(unit)}")
        masked = block[block.index("systemctl mask"):]
        for unit in ("snapper-boot.timer", "btrfs-balance.timer", "btrfs-defrag.timer", "btrfs-trim.timer",
                     "btrfsmaintenance-refresh.path", "btrfsmaintenance-refresh.service"):
            self.assertIn(unit, masked)
        self.assertNotIn("snapper-timeline.timer", masked)

    def test_every_run_is_skipped_unless_storage_is_mounted_with_its_snapshots_inside(self):
        """An ext4 box has no /data/storage/.snapshots: the services skip (a condition), they never fail: a failed unit
        is fatal to the health gate."""
        for unit in ("snapper-timeline", "snapper-cleanup", "btrfs-scrub"):
            d = rd(BASE, f"usr/lib/systemd/system/{unit}.service.d/onemind.conf")
            self.assertIn("ConditionPathExists=/data/storage/.snapshots", d, unit)
            self.assertIn("After=data-storage.mount", d, unit)
            self.assertNotRegex(re.sub(r"(?m)^#.*$", "", d), r"(?m)^(Requires|Requisite|BindsTo)=", unit)

    def test_the_scrub_is_monthly_on_data_and_nothing_else_is_scheduled(self):
        c = sysconfig(rd(BASE, "etc/default/btrfsmaintenance"))
        self.assertEqual(c["BTRFS_SCRUB_MOUNTPOINTS"], "/data")
        self.assertEqual(c["BTRFS_SCRUB_PERIOD"], "monthly")
        self.assertEqual(c["BTRFS_SCRUB_PRIORITY"], "idle")
        for k in ("DEFRAG", "BALANCE", "TRIM"):
            self.assertEqual(c[f"BTRFS_{k}_PERIOD"], "none", k)

    def test_the_packages_are_in_the_debian_list(self):
        words = {w for line in rd("os/rootfs/packages/debian-common.txt").splitlines() for w in line.split("#")[0].split()}
        self.assertLessEqual({"snapper", "btrfsmaintenance", "btrfs-progs"}, words)

    def test_the_scheduler_of_pr_833_is_not_used(self):
        """Plan decision: snapshots come from snapper, not from the onemind-snapshots service of #833."""
        base = os.path.join(ROOT, "os", "rootfs", "layers")
        for dirpath, _, files in os.walk(base):
            for f in files:
                self.assertNotIn("onemind-snapshots", f)
        self.assertNotIn("onemind-snapshots", rd("os/rootfs/Containerfile"))


if __name__ == "__main__":
    unittest.main()
