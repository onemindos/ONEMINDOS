# SPDX-License-Identifier: Apache-2.0
"""LT-X86-07459 pre-install check (lab-kits/LT-X86-07459/preinstall-check.sh) against a fake /proc and /sys.
Proves the script's decisions (x86-64 level, SSD vs HDD, UEFI, Secure Boot, Ethernet), not the Dell."""
import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIT = os.path.join(ROOT, "lab-kits", "LT-X86-07459", "preinstall-check.sh")
V2 = "fpu lm cx16 lahf_lm popcnt sse4_1 sse4_2 ssse3 pni vmx"
V3 = V2 + " avx avx2 bmi1 bmi2 f16c fma abm movbe xsave"
V1 = "fpu lm sse3 pni"


def put(root, rel, text, binary=False):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb" if binary else "w") as f:
        f.write(text)


def fake(flags=V3, mem_kb=32000000, rot="0", gib=900, efi=True, secure=0, link="1", disk="sda"):
    d = tempfile.mkdtemp()
    put(d, "proc/cpuinfo", f"model name\t: Test CPU\nflags\t\t: {flags}\n")
    put(d, "proc/meminfo", f"MemTotal:       {mem_kb} kB\n")
    put(d, f"sys/block/{disk}/size", str(gib * 1024 * 1024 * 2))
    put(d, f"sys/block/{disk}/removable", "0")
    put(d, f"sys/block/{disk}/queue/rotational", rot)
    put(d, "sys/block/sdb/size", str(8 * 1024 * 1024 * 2))   # the live stick
    put(d, "sys/block/sdb/removable", "1")
    if efi:
        put(d, "sys/firmware/efi/efivars/SecureBoot-8be4df61", bytes([6, 0, 0, 0, secure]), binary=True)
    os.makedirs(os.path.join(d, "sys/class/tpm/tpm0"))
    put(d, "sys/class/net/eno1/carrier", link)
    put(d, "sys/class/net/wlp2s0/carrier", "1")
    os.makedirs(os.path.join(d, "sys/class/net/wlp2s0/wireless"))
    return d


def run(root):
    r = subprocess.run(["sh", KIT], env=dict(os.environ, ONEMIND_CHECK_ROOT=root), capture_output=True, text=True)
    return r.returncode, r.stdout


class Check(unittest.TestCase):
    def test_good_box_is_ready(self):
        rc, out = run(fake())
        self.assertEqual(rc, 0, out)
        self.assertIn("x86-64-v3", out)
        self.assertTrue(out.strip().endswith("READY"), out)
        self.assertNotIn("sdb", out)  # the removable stick is skipped

    def test_v2_cpu_passes_v1_fails(self):
        rc, out = run(fake(flags=V2))
        self.assertEqual(rc, 0)
        self.assertIn("x86-64-v2", out)
        rc, out = run(fake(flags=V1))
        self.assertEqual(rc, 1)
        self.assertIn("below x86-64-v2", out)

    def test_hard_disk_warns_and_nvme_passes(self):
        rc, out = run(fake(rot="1"))
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"Disk sda\s+WARN\s+HDD")
        rc, out = run(fake(disk="nvme0n1"))
        self.assertRegex(out, r"Disk nvme0n1\s+PASS\s+NVMe")

    def test_small_disk_fails(self):
        rc, out = run(fake(gib=16))
        self.assertEqual(rc, 1)
        self.assertIn("32 GiB", out)

    def test_legacy_boot_fails_and_secure_boot_on_fails(self):
        rc, out = run(fake(efi=False))
        self.assertEqual(rc, 1)
        self.assertIn("Legacy", out)
        rc, out = run(fake(secure=1))
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"Secure Boot\s+FAIL")

    def test_no_cable_warns_and_wifi_alone_is_not_wired(self):
        rc, out = run(fake(link="0"))
        self.assertRegex(out, r"Ethernet\s+WARN")

    def test_small_memory_warns(self):
        rc, out = run(fake(mem_kb=8000000))
        self.assertRegex(out, r"Memory\s+WARN")


if __name__ == "__main__":
    unittest.main()
