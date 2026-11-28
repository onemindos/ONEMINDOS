# SPDX-License-Identifier: Apache-2.0
"""Static checks that the image keeps a clock (Step 2 PR 1): systemd-timesyncd, tzdata and LANG=C.UTF-8.

apt runs with recommends off, so a package that only another package recommends is never installed; that is how the
image shipped without an NTP client while deploy/verify/node-check.sh reads NTPSynchronized. The booted proof is F17
in test/qemu/firstboot.py; this test keeps the files it reads from drifting.
"""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOTFS = os.path.join(ROOT, "os", "rootfs")


def rd(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def pkgs(path):
    text = re.sub(r"#.*", "", rd(path))
    return set(text.split())


class Clock(unittest.TestCase):
    def test_packages_are_listed_by_name(self):
        for leg in ("debian", "ubuntu"):
            got = pkgs(f"os/rootfs/packages/{leg}-common.txt")
            self.assertIn("systemd-timesyncd", got, leg)
            self.assertIn("tzdata", got, leg)

    def test_timesyncd_is_enabled_in_the_image(self):
        cf = rd("os/rootfs/Containerfile")
        # every `systemctl enable` after the board hook: the NetworkManager boards enable their own stack first
        enables = re.findall(r"systemctl enable ([^;]*?);", cf[cf.index("post-install.sh"):], re.S)
        self.assertTrue(enables)
        self.assertTrue(any("systemd-timesyncd.service" in e for e in enables), enables)

    def test_locale_is_c_utf8(self):
        lines = [l for l in rd("os/rootfs/layers/base/etc/locale.conf").splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["LANG=C.UTF-8"])

    def test_the_booted_check_exists(self):
        fb = rd("test/qemu/firstboot.py")
        self.assertIn("def f17(", fb)
        self.assertIn("f17(vm)", fb)
        self.assertIn("| F17 |", rd("test/qemu/CRITERIA-FIRSTBOOT.md"))

    def test_zone_lives_on_data_because_the_root_is_read_only(self):
        # P-04: /etc/localtime is a symlink to /data/state/localtime; onemind-data-layout seeds it as UTC and the
        # host service swaps it. The host unit may write /data and nothing else on the root.
        self.assertIn("ln -sfn /data/state/localtime /etc/localtime", rd("os/rootfs/Containerfile"))
        layout = rd("os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-layout.service")
        self.assertIn("[ -L /data/state/localtime ] || ln -s /usr/share/zoneinfo/UTC /data/state/localtime", layout)
        unit = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-host.service")
        self.assertIn("ReadWritePaths=/data", unit)
        go = rd("internal/host/timezone.go")
        self.assertIn('DefaultZoneLink = "/data/state/localtime"', go)

    def test_the_booted_zone_checks_exist(self):
        fb = rd("test/qemu/firstboot.py")
        self.assertIn("def f18(", fb)
        self.assertIn("def f19(", fb)
        crit = rd("test/qemu/CRITERIA-FIRSTBOOT.md")
        self.assertIn("| F18 |", crit)
        self.assertIn("| F19 |", crit)

    def test_node_check_still_reads_ntp(self):
        self.assertIn("NTPSynchronized", rd("deploy/verify/node-check.sh"))


if __name__ == "__main__":
    unittest.main()
