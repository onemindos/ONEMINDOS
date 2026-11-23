# SPDX-License-Identifier: Apache-2.0
"""#871 (nas-client-packages): the SMB and NFS client tools ship in the image, and nothing serves.

The booted proof is the battery's TN0-TN2 step (test/qemu/nasmount.py, CRITERIA-NAS.md); this pins what the build
must contain so a missing package, a re-enabled unit or a lost battery step fails without booting anything, and it
checks the step's own verdict logic.
"""
import hashlib
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QEMU = os.path.join(ROOT, "test", "qemu")


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def words(*p):
    return re.sub(r"#.*", "", read(*p)).split()


_spec = importlib.util.spec_from_file_location("nasmount", os.path.join(QEMU, "nasmount.py"))
nasmount = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nasmount)
CONTAINERFILE = read("os", "rootfs", "Containerfile")


class ImageContents(unittest.TestCase):
    def test_client_packages_in_both_legs(self):
        for leg in ("debian", "ubuntu"):
            pkgs = words("os", "rootfs", "packages", f"{leg}-common.txt")
            for p in ("cifs-utils", "nfs-common"):
                self.assertIn(p, pkgs, f"{leg} lacks {p}")

    def test_no_server_packages_anywhere(self):
        lists = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(ROOT, "os")) for f in fs
                 if f.endswith(".txt") and "packages" in f]
        self.assertTrue(lists)
        for path in lists:
            with open(path) as f:
                pkgs = re.sub(r"#.*", "", f.read()).split()
            for p in ("nfs-kernel-server", "ksmbd-tools"):
                self.assertNotIn(p, pkgs, os.path.relpath(path, ROOT))

    def test_units_nfs_common_enables_are_disabled_after_install(self):
        install = CONTAINERFILE.index("apt-get install -y $(cat /tmp/onemind/pkgs)")
        m = re.search(r"systemctl disable ([^;>]*)", CONTAINERFILE)
        self.assertIsNotNone(m)
        self.assertGreater(m.start(), install)
        for u in ("rpcbind.service", "rpcbind.socket", "nfs-client.target", "nfs-blkmap.service"):
            self.assertIn(u, m.group(1).split())
        for line in re.findall(r"systemctl enable [^;]*", CONTAINERFILE):
            self.assertNotRegex(line, r"rpcbind|nfs|rpc-")

    def test_manifest_records_installed_size(self):
        m = re.search(r"dpkg-query -W -f='([^']*)'[^;]*> /usr/lib/onemind/packages.txt", CONTAINERFILE)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).split()[:4], ["${Package}", "${Version}", "${Architecture}", "${Installed-Size}\\n"])

    def test_manifest_stays_readable_by_the_security_check(self):
        spec = importlib.util.spec_from_file_location("cs", os.path.join(ROOT, "os", "update", "check-security.py"))
        cs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cs)
        self.assertEqual(cs.parse_packages_txt("nfs-common 1:2.8.3-1 amd64 1145\n"),
                         {"nfs-common": ("1:2.8.3-1", "amd64")})


class BatteryStep(unittest.TestCase):
    def test_criteria_preregistered(self):
        with open(os.path.join(QEMU, "CRITERIA-NAS.md"), "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        self.assertIn(f"{h}  CRITERIA-NAS.md", read("test", "qemu", "PREREGISTRATION.sha256"))

    def test_run_tests_calls_the_step_for_t5_runs(self):
        rt = read("test", "qemu", "run-tests.py")
        self.assertIn('"nasmount.py"', rt)
        self.assertRegex(rt, r'if upto >= ORDER\.index\("T5"\):[^\n]*\n\s+try:\n\s+nasmount\.run\(vm, record, tag, a\.board\)')
        self.assertLess(rt.index("nasmount.run("), rt.index('vm.mark("T2 wrong-key bundle")'))

    def test_budget_is_the_slot_size_of_every_booted_board(self):
        for board, want in (("x86_64-efi", 10240), ("vm-do", 4096), ("arm64-efi", 10240), ("rpi5", 8192)):
            self.assertEqual(nasmount.slot_budget_mib(read("os", "boards", board, "layout.yaml")), want, board)
        with self.assertRaises(ValueError):
            nasmount.slot_budget_mib("partitions: []\n")

    def good_tags(self):
        t = {"PKG_cifs-utils": "1", "PKG_nfs-common": "1", "MAN_cifs-utils": "351", "MAN_nfs-common": "1145",
             "SRV_nfs-kernel-server": "0", "SRV_ksmbd-tools": "0", "MOD_cifs": "1", "MOD_nfs": "1", "MOD_nfsv4": "1",
             "UNITS_ENABLED": "0", "UNITS_ACTIVE": "0", "ROOT_USED_MIB": "3100"}
        return t

    def test_tn0_passes_only_when_every_condition_holds(self):
        ok, d = nasmount.tn0_verdict(self.good_tags(), 10240)
        self.assertTrue(ok, d)
        bad = {"PKG_nfs-common": "0", "SRV_nfs-kernel-server": "1", "MOD_cifs": "0", "MAN_cifs-utils": None,
               "UNITS_ENABLED": "1", "UNITS_ACTIVE": "2", "ROOT_USED_MIB": "10240"}
        for k, v in bad.items():
            t = self.good_tags()
            t[k] = v
            self.assertFalse(nasmount.tn0_verdict(t, 10240)[0], k)
        t = self.good_tags()
        t["ROOT_USED_MIB"] = None
        self.assertFalse(nasmount.tn0_verdict(t, 10240)[0])

    def test_guest_commands_serve_only_on_loopback_and_clean_up(self):
        nfs = " ".join(nasmount.nfs_commands())
        smb = " ".join(nasmount.smb_commands())
        self.assertIn("127.0.0.1:/", nfs)
        self.assertIn("mount -t nfs4", nfs)
        self.assertIn("'-2 -3' > /proc/fs/nfsd/versions", nfs)      # v4 only: no rpcbind needed
        self.assertIn(str(0x2401), nfs)                              # read-only, no subtree check, fsid
        self.assertIn("'interfaces = lo'", smb)
        self.assertIn("'bind interfaces only = yes'", smb)
        self.assertIn("'read only = yes'", smb)
        self.assertIn("//127.0.0.1/nastest", smb)
        self.assertNotIn("onemind-smb", smb)
        self.assertNotIn("systemctl", nfs + smb)                     # nothing is enabled or started as a unit
        self.assertIn("echo 0 > /proc/fs/nfsd/threads", nasmount.nfs_teardown())
        for td in (nasmount.nfs_teardown(), nasmount.smb_teardown()):
            self.assertIn(f"rm -rf {nasmount.D}/", td)


if __name__ == "__main__":
    unittest.main()
