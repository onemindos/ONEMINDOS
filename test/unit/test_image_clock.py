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

    def test_node_check_still_reads_ntp(self):
        self.assertIn("NTPSynchronized", rd("deploy/verify/node-check.sh"))


if __name__ == "__main__":
    unittest.main()
