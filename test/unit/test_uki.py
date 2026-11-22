# SPDX-License-Identifier: Apache-2.0
"""S-13 first slice: signed UKI helpers and the per-slot UKI layout (os/assemble/uki.py, assemble.py)."""
import os, re, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
import assemble  # noqa: E402
import uki  # noqa: E402


class Cmdline(unittest.TestCase):
    def test_tail_equals_grub_cfg_in(self):
        t = open(os.path.join(ROOT, "os", "assemble", "grub.cfg.in")).read()
        m = re.search(r'^CMDLINE="@CONSOLE@ (.*)"$', t, re.M)
        self.assertEqual(m.group(1), uki.CMDLINE_TAIL)

    def test_names_root_and_slot_and_is_read_only(self):
        c = uki.cmdline("console=ttyS0", "1234", "B")
        self.assertIn("root=PARTUUID=1234", c)
        self.assertIn("rauc.slot=B", c)
        self.assertRegex(c, r"\bro\b")
        self.assertNotIn("init=", c)

    def test_bad_slot_refused(self):
        with self.assertRaises(ValueError):
            uki.cmdline("console=ttyS0", "1", "C")


class Commands(unittest.TestCase):
    def test_ukify_signs_with_sbsign_and_embeds_cmdline(self):
        c = uki.ukify_cmd("k", "i", "root=x", "osr", "out.efi", "key", "crt")
        self.assertEqual(c[:2], ["ukify", "build"])
        for want in ("--linux=k", "--initrd=i", "--cmdline=root=x", "--os-release=@osr", "--signtool=sbsign",
                     "--secureboot-private-key=key", "--secureboot-certificate=crt", "--output=out.efi"):
            self.assertIn(want, c)

    def test_enroll_has_no_microsoft_keys_and_turns_secure_boot_on(self):
        c = uki.enroll_cmd("in.fd", "out.fd", "/k")
        self.assertIn("--set-pk", c)
        self.assertIn("--secure-boot", c)
        self.assertFalse([x for x in c if "microsoft" in x.lower()])

    def test_missing_key_stops_before_any_tool_runs(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "f")
            open(f, "w").write("x")
            with self.assertRaises(SystemExit):
                uki.sign_efi(f, f + ".s", os.path.join(d, "no.key"), os.path.join(d, "no.crt"))
            with self.assertRaises(SystemExit):
                uki.build_uki(f, f, "c", f, f + ".o", "", "")


class Layout(unittest.TestCase):
    def test_default_image_still_uses_grub(self):
        board = assemble.load_board("x86_64-efi")
        t = assemble.render_grub_cfg(board)
        self.assertIn("linux ($disk,gpt", t)
        self.assertNotIn("chainloader", t)

    def test_one_signed_uki_per_slot_in_its_own_boot_partition(self):
        board = assemble.load_board("x86_64-efi")
        calls = []
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "boot")); os.makedirs(os.path.join(d, "usr/lib"))
            for n in ("vmlinuz-1", "initrd.img-1"):
                open(os.path.join(d, "boot", n), "w").close()
            orig = uki.build_uki
            uki.build_uki = lambda k, i, c, o, out, key, cert, **kw: calls.append((c, out)) or out
            try:
                files = assemble.build_ukis(board, d, d, "key", "crt")
            finally:
                uki.build_uki = orig
        self.assertEqual(sorted(files), ["onemind-boot-a", "onemind-boot-b"])
        lay = board["layout_data"]
        for (cmd, _), slot in zip(calls, "AB"):
            self.assertIn("root=PARTUUID=" + assemble.part(lay, f"onemind-system-{slot.lower()}")["partuuid"], cmd)
            self.assertIn(f"rauc.slot={slot}", cmd)

    def test_two_kernels_refused(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "boot"))
            for n in ("vmlinuz-1", "vmlinuz-2", "initrd.img-1"):
                open(os.path.join(d, "boot", n), "w").close()
            with self.assertRaises(SystemExit):
                assemble.find_kernel(d)


class Disk(unittest.TestCase):
    def test_half_a_key_pair_is_refused(self):
        import argparse
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            assemble.cmd_disk(argparse.Namespace(board="x86_64-efi", work=d, system="x", out="y",
                                                 sb_key="k", sb_cert=None))

    def test_bios_board_refused(self):
        import argparse
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            assemble.cmd_disk(argparse.Namespace(board="vm-do", work=d, system="x", out="y",
                                                 sb_key="k", sb_cert="c"))


if __name__ == "__main__":
    unittest.main()
