# SPDX-License-Identifier: Apache-2.0
"""FILES-SHARE-01 (#235, D-017): Samba ships in the image, off until an owner approves a share.

The config renderer and the host calls are tested in Go (internal/smb, internal/host); this pins how the image
carries Samba: the packages, the masked Debian units, the one unit that starts only while a config exists, the
kernel-level LAN-and-mesh-only rule matching the Go list, and the places that must live on /data.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAYER = os.path.join(ROOT, "os", "rootfs", "layers", "onemind")


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


UNIT = read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-smb.service")
CONTAINERFILE = read("os", "rootfs", "Containerfile")


class SmbImage(unittest.TestCase):
    def test_samba_and_its_helpers_are_in_both_legs(self):
        for leg in ("debian", "ubuntu"):
            pkgs = re.sub(r"#.*", "", read("os", "rootfs", "packages", f"{leg}-common.txt")).split()
            for p in ("samba", "samba-vfs-modules", "libnss-extrausers"):  # vfs_fruit is Time Machine
                self.assertIn(p, pkgs, f"{leg} lacks {p}")

    def test_the_debian_units_are_masked_and_only_ours_is_enabled(self):
        m = re.search(r"systemctl mask ([^;>]*)", CONTAINERFILE.split("avahi-daemon.service")[1])
        masked = m.group(1).split()
        for u in ("smbd.service", "nmbd.service", "winbind.service", "samba-ad-dc.service"):
            self.assertIn(u, masked)
        self.assertIn("systemctl enable onemind-smb.service", CONTAINERFILE)

    def test_off_until_a_config_exists_and_lives_on_data(self):
        self.assertIn("ConditionPathExists=/data/onemind/samba/smb.conf", UNIT)
        self.assertIn("RequiresMountsFor=/data", UNIT)
        self.assertIn("--configfile=/data/onemind/samba/smb.conf", UNIT)
        self.assertIn("ReadWritePaths=/data/onemind/samba /data/onemind/files", UNIT)
        self.assertIn("ProtectSystem=strict", UNIT)

    def test_kernel_rule_matches_the_renderers_list(self):
        go = read("internal", "smb", "smb.go")
        nets = re.search(r"AllowedNets = \[\]string\{(.*?)\}", go, re.S).group(1)
        want = re.findall(r'"([^"]+)"', nets)
        allow = re.search(r"(?m)^IPAddressAllow=(.*)$", UNIT).group(1).split()
        self.assertEqual(allow, want)
        self.assertIn("IPAddressDeny=any", UNIT)  # no outbound traffic beyond those peers: default-deny egress holds
        self.assertNotIn("0.0.0.0/0", UNIT)

    def test_unix_accounts_and_mdns_record_are_on_data(self):
        self.assertIn("L+ /var/lib/extrausers - - - - /data/onemind/samba/extrausers",
                      read("os", "rootfs", "layers", "onemind", "usr", "lib", "tmpfiles.d", "onemind-smb.conf"))
        link = os.path.join(LAYER, "etc", "avahi", "services", "onemind-smb.service")
        self.assertEqual(os.readlink(link), "/data/onemind/samba/avahi.service")
        self.assertIn("extrausers", CONTAINERFILE)
        for db in ("passwd", "group", "shadow"):
            self.assertIn(db, CONTAINERFILE.split("for db in")[1].split("done")[0])

    def test_host_service_still_never_enabled_at_build(self):
        for line in re.findall(r"systemctl enable [^;]*", CONTAINERFILE):
            self.assertNotIn("onemind-host", line)


if __name__ == "__main__":
    unittest.main()
