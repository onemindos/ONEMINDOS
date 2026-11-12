# SPDX-License-Identifier: Apache-2.0
"""vm-do (BD-DO-1): the BIOS boot-sector patch matches what grub-bios-setup writes."""
import os, struct, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
import assemble  # noqa: E402


class BiosBoot(unittest.TestCase):
    def test_patch(self):
        with tempfile.TemporaryDirectory() as d:
            boot = bytearray(512); boot[0x1B8:0x1BC] = b"SIGN"; boot[0x1FE:0x200] = b"\x55\xaa"
            open(os.path.join(d, "boot.img"), "wb").write(bytes(512))
            open(os.path.join(d, "core.img"), "wb").write(b"\x11" * 700)       # 2 sectors
            disk = os.path.join(d, "disk.img")
            with open(disk, "wb") as f:
                f.write(boot); f.truncate(4096 * 512)
            assemble.install_bios_boot(disk, d, core_lba=2048, max_sectors=4096)
            raw = open(disk, "rb").read()
            self.assertEqual(struct.unpack_from("<Q", raw, 0x5C)[0], 2048)    # kernel sector
            self.assertEqual(raw[0x64], 0xFF)
            self.assertEqual(raw[0x66:0x68], b"\x90\x90")
            self.assertEqual(raw[0x1B8:0x1BC], b"SIGN")                          # disk signature kept
            self.assertEqual(raw[0x1FE:0x200], b"\x55\xaa")                      # MBR table area kept
            start, length, seg = struct.unpack_from("<QHH", raw, 2048 * 512 + 0x200 - 12)
            self.assertEqual((start, length, seg), (2049, 1, 0x820))

    def test_core_too_big(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "boot.img"), "wb").write(bytes(512))
            open(os.path.join(d, "core.img"), "wb").write(bytes(3 * 512))
            disk = os.path.join(d, "disk.img"); open(disk, "wb").truncate(1 << 20)
            with self.assertRaises(AssertionError):
                assemble.install_bios_boot(disk, d, core_lba=34, max_sectors=2)


if __name__ == "__main__":
    unittest.main()
