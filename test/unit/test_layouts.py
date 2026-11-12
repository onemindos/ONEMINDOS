# SPDX-License-Identifier: Apache-2.0
"""D-B2.2: every board's layout.yaml against the 01 §4.3 contract (labels, sizes, order)."""
import os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
import assemble  # noqa: E402

# 01 §4.3 / brief 30 §6 B2 table: x86 layout (labels are the contract; sizes per 01 §4.3).
X86 = [("onemind-esp", "1GiB", "esp"), ("onemind-boot-a", "512MiB", "esp"), ("onemind-boot-b", "512MiB", "esp"),
       ("onemind-system-a", "10GiB", "linux"), ("onemind-system-b", "10GiB", "linux"),
       ("onemind-recovery", "1GiB", "linux"), ("onemind-data", "rest", "linux")]


def board(name):
    return assemble.load_board(name)


class Layouts(unittest.TestCase):
    def rows(self, name):
        return [(p["label"], p["size"], p["type"]) for p in board(name)["layout_data"]["partitions"]]

    def test_x86_64_efi_is_01_layout(self):
        self.assertEqual(self.rows("x86_64-efi"), X86)

    def test_arm64_efi_same_as_x86(self):
        self.assertEqual(self.rows("arm64-efi"), X86)

    def test_vm_is_x86_layout_on_32GiB(self):
        self.assertEqual(self.rows("vm"), X86)
        self.assertEqual(board("vm")["layout_data"]["disk_size"], "32GiB")

    def test_vm_do_same_labels_bios_first_fits_25GB_droplet(self):
        rows = self.rows("vm-do")
        self.assertEqual(rows[0][2], "bios")
        self.assertEqual([r[0] for r in rows[1:]], [r[0] for r in X86])
        size_gib = assemble.mib(board("vm-do")["layout_data"]["disk_size"]) / 1024
        self.assertLessEqual(size_gib * 1.073741824, 25.0)   # GiB -> GB; DO's smallest droplet disk is 25 GB

    def test_system_slots_hold_a_rootfs_with_headroom(self):
        for name in ("x86_64-efi", "arm64-efi", "vm", "vm-do"):
            lay = board(name)["layout_data"]
            for s in ("onemind-system-a", "onemind-system-b"):
                self.assertGreaterEqual(assemble.mib(assemble.part(lay, s)["size"]), 4096, name)

    def test_partuuids_stable_and_distinct(self):
        lay = board("x86_64-efi")["layout_data"]
        uu = [p["partuuid"] for p in lay["partitions"]]
        self.assertEqual(len(set(uu)), len(uu))
        self.assertEqual(assemble.part(lay, "onemind-system-a")["partuuid"],
                         assemble.part(board("vm")["layout_data"], "onemind-system-a")["partuuid"])

    def test_esp_uuid_format(self):
        self.assertEqual(assemble.esp_fsuuid(board("x86_64-efi")["layout_data"]), "4F4E-454D")

    def test_grub_cfg_renders_every_placeholder(self):
        for name in ("x86_64-efi", "arm64-efi", "vm", "vm-do"):
            cfg = assemble.render_grub_cfg(board(name))
            self.assertIsNone(re.search(r"@[A-Z_]+@", cfg), name)
            self.assertIn("rauc.slot=A", cfg)
            self.assertIn("panic=10", cfg)

    def test_bad_layout_rejected(self):
        with self.assertRaises(AssertionError):
            assemble.validate_layout({"disk_size": "1GiB", "partitions": [
                {"label": "onemind-esp", "size": "1GiB", "type": "esp"}]})


if __name__ == "__main__":
    unittest.main()
