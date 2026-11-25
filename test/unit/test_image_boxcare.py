# SPDX-License-Identifier: Apache-2.0
"""Step 2b, box care for a 24/7 machine: static checks on the files that put fwupd, fstrim, lm-sensors, thermald,
udisks2, the watchdog setting and rasdaemon on the image, with their state on /data. Stdlib only. The booted proof
is first-boot check F24 (test/qemu/CRITERIA-FIRSTBOOT.md section 18)."""
import hashlib, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = "os/rootfs/layers/base"
BINDS = {"var-lib-fwupd": "/var/lib/fwupd", "var-cache-fwupd": "/var/cache/fwupd",
         "var-lib-rasdaemon": "/var/lib/rasdaemon", "var-lib-udisks2": "/var/lib/udisks2"}


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def words(path):
    return set(re.sub(r"#.*", "", rd(path)).split())


class Packages(unittest.TestCase):
    def test_common_lists_carry_the_box_care_packages(self):
        for leg in ("debian", "ubuntu"):
            self.assertTrue({"fwupd", "lm-sensors", "rasdaemon", "udisks2"} <= words(f"os/rootfs/packages/{leg}-common.txt"), leg)

    def test_x86_only_packages_are_not_in_the_common_or_arm_lists(self):
        for leg in ("debian", "ubuntu"):
            self.assertTrue({"thermald", "fwupd-signed"} <= words(f"os/rootfs/packages/{leg}-amd64.txt"), leg)
            self.assertFalse({"thermald", "fwupd-signed"} & words(f"os/rootfs/packages/{leg}-common.txt"), leg)
        self.assertFalse({"thermald", "fwupd-signed"} & words("os/rootfs/packages/debian-arm64.txt"))

    def test_no_polkit_and_no_automounting_desktop_helpers(self):
        # Recommends are off; these must never be named. polkitd absent means only root (the host helper)
        # is authorised by udisks2 and fwupd; gvfs and udiskie are what would automount a plugged-in drive.
        names = set()
        for f in os.listdir(os.path.join(ROOT, "os/rootfs/packages")):
            names |= words("os/rootfs/packages/" + f)
        self.assertFalse(names & {"polkitd", "policykit-1", "gvfs", "gvfs-backends", "udiskie", "udisks2-udiskie", "usbmount"})


class Containerfile(unittest.TestCase):
    c = rd("os/rootfs/Containerfile")

    def test_no_automatic_firmware_refresh(self):
        self.assertIn("systemctl mask fwupd-refresh.timer fwupd-refresh.service", self.c)

    def test_trim_timer_is_enabled(self):
        self.assertIn("systemctl enable fstrim.timer", self.c)

    def test_build_checks_the_commands(self):
        self.assertIn("for t in fwupdmgr sensors ras-mc-ctl udisksctl", self.c)
        self.assertRegex(self.c, r'\[ "\$\{TARGETARCH\}" = amd64 \]; then command -v thermald')

    def test_mount_points_exist_in_the_image(self):
        for dst in BINDS.values():
            self.assertIn(dst, self.c, dst)


class State(unittest.TestCase):
    FSTABS = [BASE + "/etc/fstab", "os/boards/rpi5/rootfs/etc/fstab"]

    def test_each_state_dir_is_bound_from_data_on_every_board_with_a_fstab(self):
        for f in self.FSTABS:
            fstab = rd(f)
            for src, dst in BINDS.items():
                self.assertRegex(fstab, r"(?m)^/data/state/%s\s+%s\s+none bind,nofail,x-systemd\.requires=onemind-data-layout\.service 0 0$"
                                 % (re.escape(src), re.escape(dst)), f"{f} {dst}")

    def test_layout_creates_the_sources(self):
        layout = rd(BASE + "/usr/lib/systemd/system/onemind-data-layout.service")
        for src in BINDS:
            self.assertRegex(layout, r"for d in [^;]*\b%s\b[^;]*; do mkdir -p" % re.escape(src))

    def test_recovery_check_waits_for_the_new_mounts(self):
        after = re.search(r"(?m)^After=(.*)$", rd("os/recovery/onemind-data-check.service")).group(1).split()
        for dst in BINDS.values():
            self.assertIn(dst.strip("/").replace("-", "\\x2d").replace("/", "-") + ".mount", after, dst)


class Settings(unittest.TestCase):
    def test_trim_unit_touches_only_data(self):
        t = rd(BASE + "/usr/lib/systemd/system/fstrim.service.d/10-onemind-data-only.conf")
        self.assertRegex(t, r"(?m)^ExecStart=$")      # clears Debian's "every filesystem in fstab" line
        self.assertRegex(t, r"(?m)^ExecStart=/sbin/fstrim --verbose --quiet-unsupported /data$")

    def test_udisks_never_automounts(self):
        r = rd(BASE + "/usr/lib/udev/rules.d/60-onemind-udisks-noautomount.rules")
        self.assertIn('SUBSYSTEM=="block", ENV{UDISKS_AUTO}="0"', r)
        self.assertLess("60-onemind-udisks-noautomount.rules", "80-udisks2.rules")   # runs first

    def test_owner_mounts_land_on_the_run_tmpfs_not_the_read_only_root(self):
        self.assertRegex(rd(BASE + "/usr/lib/tmpfiles.d/onemind-udisks-media.conf"), r"(?m)^d /run/media 0755 root root -$")
        self.assertIn("rmdir /media && ln -s /run/media /media", rd("os/rootfs/Containerfile"))

    def test_watchdog_is_set_on_x86_and_rpi5(self):
        self.assertIn("RuntimeWatchdogSec=30s", rd(BASE + "/etc/systemd/system.conf.d/onemind-watchdog.conf"))
        self.assertIn("RuntimeWatchdogSec=10s", rd("os/boards/rpi5/rootfs/etc/systemd/system.conf.d/onemind-watchdog.conf"))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "os/boards/x86_64-efi/rootfs/etc/systemd/system.conf.d/onemind-watchdog.conf")))


class Battery(unittest.TestCase):
    def test_f24_is_preregistered_and_implemented(self):
        crit = rd("test/qemu/CRITERIA-FIRSTBOOT.md")
        for tid in ("F24", "F24b", "F24c"):
            self.assertIn("| %s |" % tid, crit)
        h = hashlib.sha256(crit.encode()).hexdigest()
        self.assertIn(h + "  CRITERIA-FIRSTBOOT.md", rd("test/qemu/PREREGISTRATION.sha256"))
        fb = rd("test/qemu/firstboot.py")
        for tid in ("F24", "F24b", "F24c"):
            self.assertIn('"%s"' % tid, fb)
        self.assertIn("def f24(", fb)


if __name__ == "__main__":
    unittest.main()
