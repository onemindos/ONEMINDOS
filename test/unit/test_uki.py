# SPDX-License-Identifier: Apache-2.0
"""S-13 first slice: signed UKI helpers and the per-slot UKI layout (os/assemble/uki.py, assemble.py)."""
import argparse, configparser, json, os, re, shutil, subprocess, sys, tempfile, unittest

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

    def test_one_signed_uki_per_slot_with_its_own_root_and_slot(self):
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
        # One boot-partition image holds both UKIs (a bundle's efi image is written to whichever slot is the target);
        # each slot's firmware entry loads its own file.
        self.assertEqual(sorted(files), ["EFI/Linux/onemind-A.efi", "EFI/Linux/onemind-B.efi"])
        lay = board["layout_data"]
        for (cmd, out), slot in zip(calls, "AB"):
            self.assertIn("root=PARTUUID=" + assemble.part(lay, f"onemind-system-{slot.lower()}")["partuuid"], cmd)
            self.assertIn(f"rauc.slot={slot}", cmd)
            self.assertEqual(files[f"EFI/Linux/onemind-{slot}.efi"], out)

    def test_fresh_disk_has_ukis_on_boot_a_only(self):
        # Slot B's root is empty until the first update, so its boot partition stays empty too: a stale or hand-picked
        # firmware entry "B" then fails to load and the firmware moves on, instead of starting a kernel with no root.
        files = {"EFI/Linux/onemind-A.efi": "a", "EFI/Linux/onemind-B.efi": "b"}
        self.assertEqual(assemble.boot_partition_files(files), {"onemind-boot-a": files})

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


def wr(path, text):
    with open(path, "w") as f:
        f.write(text)


def rd(path):
    with open(path) as f:
        return f.read()


def ini(text):
    c = configparser.ConfigParser(interpolation=None)
    c.read_string(text)
    return c


def tree_with_conf(d, text):
    os.makedirs(os.path.join(d, "tree", "etc", "rauc"), exist_ok=True)
    wr(os.path.join(d, "tree", "etc", "rauc", "system.conf"), text)


class EfiRoute(unittest.TestCase):
    """#148 slice 1: under Secure Boot the slot is chosen by RAUC's efi backend (firmware boot entries), not GRUB."""

    def setUp(self):
        self.board = assemble.load_board("x86_64-efi")

    def test_grub_config_is_unchanged(self):
        c = assemble.render_rauc_conf(self.board, "grub")
        self.assertRegex(c, r"(?m)^bootloader=grub$")
        self.assertRegex(c, r"(?m)^grubenv=")
        self.assertNotIn("[slot.efi.", c)

    def test_efi_config_switches_firmware_entries_and_writes_each_slots_uki(self):
        c = ini(assemble.render_rauc_conf(self.board, "efi"))
        self.assertEqual(c["system"]["bootloader"], "efi")
        self.assertNotIn("grubenv", c["system"])
        self.assertEqual(c["system"]["efi-use-bootnext"], "true")      # one trial boot, then the firmware falls back
        self.assertEqual(c["system"]["bundle-formats"], "verity")
        self.assertEqual(c["handlers"]["pre-install"], "/usr/lib/onemind/rauc-pre-install")   # the gate's trial marker
        for n, s in ((0, "a"), (1, "b")):
            self.assertEqual(dict(c[f"slot.efi.{n}"]), {"device": f"/dev/disk/by-partlabel/onemind-boot-{s}",
                                                        "type": "vfat", "parent": f"rootfs.{n}"})
            # bootname = firmware entry label = rauc.slot= in the signed command line = the gate's slot letter
            self.assertEqual(c[f"slot.rootfs.{n}"]["bootname"], "AB"[n])

    def test_efi_route_needs_an_efi_board(self):
        with self.assertRaises(SystemExit):
            assemble.render_rauc_conf(assemble.load_board("vm-do"), "efi")

    def test_tree_bootloader_is_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            tree_with_conf(d, assemble.render_rauc_conf(self.board, "efi"))
            self.assertEqual(assemble.tree_bootloader(os.path.join(d, "tree")), "efi")
            tree_with_conf(d, assemble.render_rauc_conf(self.board, "grub"))
            self.assertEqual(assemble.tree_bootloader(os.path.join(d, "tree")), "grub")

    def test_efi_tree_gets_the_entries_unit_and_the_gate_env(self):
        with tempfile.TemporaryDirectory() as d:
            assemble.install_efi_route(d)
            j = lambda p: os.path.join(d, p)
            self.assertTrue(os.access(j("usr/lib/onemind/onemind-efi-entries"), os.X_OK))
            unit = rd(j("usr/lib/systemd/system/onemind-efi-entries.service"))
            self.assertIn("Before=onemind-health-gate.service", unit)   # the gate's commit needs the slot's entry
            self.assertEqual(os.readlink(j("etc/systemd/system/multi-user.target.wants/onemind-efi-entries.service")),
                             "/usr/lib/systemd/system/onemind-efi-entries.service")
            self.assertIn("envget()", rd(j("usr/lib/onemind/gate-slot-env")))

    def test_the_efi_backends_tool_is_in_the_x86_image(self):
        # RAUC's efi backend runs efibootmgr for every switch (rauc v1.15.2 src/bootloaders/efi.c, EFIBOOTMGR_NAME).
        for leg in ("debian", "ubuntu"):
            words = {w for l in rd(os.path.join(ROOT, "os", "rootfs", "packages", f"{leg}-amd64.txt")).splitlines()
                     for w in l.split("#")[0].split()}
            self.assertIn("efibootmgr", words, leg)

    def test_secure_boot_disk_refuses_a_grub_tree(self):
        with tempfile.TemporaryDirectory() as d:
            tree_with_conf(d, assemble.render_rauc_conf(self.board, "grub"))
            with self.assertRaisesRegex(SystemExit, "--boot efi"):
                assemble.cmd_disk(argparse.Namespace(board="x86_64-efi", work=d, system="x", out="y",
                                                     sb_key="k", sb_cert="c"))


class EfiBundle(unittest.TestCase):
    """The update bundle carries the signed UKIs, written to the target slot's boot partition (parent=rootfs.N)."""

    def setUp(self):
        self.board = assemble.load_board("x86_64-efi")

    def test_manifest_carries_the_efi_image(self):
        m = ini(assemble.bundle_manifest(self.board, "2", "verity", efi=True))
        self.assertEqual(m["update"]["compatible"], self.board["compatible"])
        self.assertEqual(m["update"]["version"], "2")
        self.assertEqual(m["image.rootfs"]["filename"], "rootfs.ext4")
        self.assertEqual(m["image.efi"]["filename"], "efi.vfat")

    def test_plain_manifest_has_no_efi_image(self):
        m = ini(assemble.bundle_manifest(self.board, "2", "verity"))
        self.assertNotIn("image.efi", m)

    def test_efi_bundle_needs_the_tree_and_both_key_halves(self):
        base = dict(board="x86_64-efi", system="x", version="2", cert="c", key="k", out="o.raucb", format="verity")
        for extra in (dict(sb_key="k", sb_cert="c", work=None), dict(sb_key="k", sb_cert=None, work="w")):
            with self.assertRaises(SystemExit):
                assemble.cmd_bundle(argparse.Namespace(**base, **extra))

    def test_efi_image_size_fits_the_boot_partition(self):
        self.assertGreaterEqual(assemble.efi_vfat_mib(120 << 20, 512), 132)
        self.assertLessEqual(assemble.efi_vfat_mib(120 << 20, 512), 512)
        self.assertEqual(assemble.efi_vfat_mib(1 << 20, 512) % 8, 0)
        with self.assertRaises(SystemExit):
            assemble.efi_vfat_mib(500 << 20, 512)


FAKE_EFIBOOTMGR = r"""#!PYTHON
# Test double for efibootmgr: state in $FAKE_EFI/state.json, every call appended to $FAKE_EFI/calls.
import json, os, sys
d = os.environ["FAKE_EFI"]; p = os.path.join(d, "state.json"); s = json.load(open(p))
a = [x for x in sys.argv[1:] if x not in ("-q", "--quiet", "-v")]
open(os.path.join(d, "calls"), "a").write(json.dumps(a) + "\n")
if not a:
    print("BootCurrent: " + s["current"])
    if s.get("next"):
        print("BootNext: " + s["next"])
    print("Timeout: 0 seconds")
    print("BootOrder: " + ",".join(s["order"]))
    for n, (label, path) in sorted(s["entries"].items()):
        print("Boot%s* %s\t%s" % (n, label, path))
    sys.exit(0)
opt = {}
i = 0
while i < len(a):
    if a[i] in ("-C", "--create-only", "-c", "--create"):
        opt["create"] = a[i]; i += 1
    else:
        opt[a[i]] = a[i + 1]; i += 2
if "create" in opt:
    n = "%04X" % (max([int(k, 16) for k in s["entries"]] + [0]) + 1)
    s["entries"][n] = [opt["--label"], "HD(%s,GPT,x)/%s on %s" % (opt["--part"], opt["--loader"], opt["--disk"])]
    if opt["create"] in ("-c", "--create"):
        s["order"].insert(0, n)
elif "--bootorder" in opt or "-o" in opt:
    s["order"] = (opt.get("--bootorder") or opt["-o"]).split(",")
elif "--bootnext" in opt or "-n" in opt:
    s["next"] = opt.get("--bootnext") or opt["-n"]
else:
    sys.exit("fake efibootmgr: unknown call %r" % a)
json.dump(s, open(p, "w"))
"""


class FirmwareEntries(unittest.TestCase):
    """os/rauc/onemind-efi-entries and os/gate/gate-slot-env-efi against a fake efibootmgr."""

    def setUp(self):
        if not shutil.which("bash"):
            self.skipTest("needs bash")
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        b = os.path.join(self.d, "bin"); os.makedirs(b)
        f = os.path.join(b, "efibootmgr")
        wr(f, FAKE_EFIBOOTMGR.replace("PYTHON", sys.executable))
        os.chmod(f, 0o755)
        # A disk vda with the boot partitions at 2 and 3, as udev and sysfs show them.
        by = os.path.join(self.d, "by-partlabel"); sysb = os.path.join(self.d, "sys"); dev = os.path.join(self.d, "dev")
        for x in (by, sysb, dev):
            os.makedirs(x)
        for n, label in ((2, "onemind-boot-a"), (3, "onemind-boot-b")):
            real = os.path.join(self.d, "devices", "vda", f"vda{n}")
            os.makedirs(real)
            wr(os.path.join(real, "partition"), f"{n}\n")
            os.symlink(real, os.path.join(sysb, f"vda{n}"))
            wr(os.path.join(dev, f"vda{n}"), "")
            os.symlink(os.path.join(dev, f"vda{n}"), os.path.join(by, label))
        self.env = dict(os.environ, PATH=b + os.pathsep + os.environ.get("PATH", ""), FAKE_EFI=self.d,
                        ONEMIND_EFI_BYPARTLABEL=by, ONEMIND_EFI_SYSBLOCK=sysb)
        self.state({"current": "0001", "order": ["0001", "0000"],
                    "entries": {"0000": ["UiApp", "FvFile(x)"], "0001": ["UEFI Misc Device", "PciRoot(0x0)"]}})

    def state(self, s=None):
        p = os.path.join(self.d, "state.json")
        if s is not None:
            wr(p, json.dumps(s))
        return json.loads(rd(p))

    def calls(self):
        p = os.path.join(self.d, "calls")
        return [json.loads(l) for l in rd(p).splitlines()] if os.path.exists(p) else []

    def entries(self):
        p = os.path.join(ROOT, "os", "rauc", "onemind-efi-entries")
        return subprocess.run(["sh", p], env=self.env, capture_output=True, text=True)

    def num(self, label):
        return next(n for n, (l, _) in self.state()["entries"].items() if l == label)

    def test_first_boot_creates_one_entry_per_slot_and_puts_only_a_in_bootorder(self):
        r = self.entries()
        self.assertEqual(r.returncode, 0, r.stderr)
        creates = [c for c in self.calls() if "--create-only" in c]
        self.assertEqual(len(creates), 2)
        for c, (slot, part) in zip(creates, (("A", "2"), ("B", "3"))):
            opt = dict(zip(c[1::2], c[2::2]))
            self.assertEqual(opt, {"--disk": "/dev/vda", "--part": part, "--label": slot,
                                   "--loader": f"\\EFI\\Linux\\onemind-{slot}.efi"})
        # A first, the firmware's own entries after it; B stays out until RAUC installs it and the gate commits it.
        self.assertEqual(self.state()["order"], [self.num("A"), "0001", "0000"])
        self.assertIn("EFI-ENTRIES:", r.stdout)

    def test_second_boot_changes_nothing(self):
        self.entries()
        before = self.state()
        n = len(self.calls())
        r = self.entries()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state(), before)
        self.assertFalse([c for c in self.calls()[n:] if c])     # only listings, no writes

    def test_a_lost_b_entry_is_recreated_without_touching_bootorder(self):
        self.entries()
        s = self.state(); b = self.num("B"); del s["entries"][b]; s["order"] = [self.num("A"), "0001"]
        self.state(s)
        r = self.entries()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state()["order"], [self.num("A"), "0001"])
        self.assertIn("B", [l for l, _ in self.state()["entries"].values()])

    def test_missing_boot_partition_fails_loudly(self):
        os.remove(os.path.join(self.d, "by-partlabel", "onemind-boot-b"))
        r = self.entries()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("onemind-boot-b", r.stdout + r.stderr)

    def gate_env(self, *calls):
        env = os.path.join(ROOT, "os", "gate", "gate-slot-env-efi")
        script = f'set -u; . "{env}"; ' + "; ".join(calls)
        r = subprocess.run(["bash", "-c", script], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.split()

    def test_gate_reads_slot_state_from_firmware_variables(self):
        self.entries()
        a, b = self.num("A"), self.num("B")
        # After the first boot: A good, B not good, no trial.
        self.assertEqual(self.gate_env("envget A_OK", "envget B_OK", "envget A_TRY", "envget B_TRY"), ["1", "0", "0", "0"])
        # After `rauc install`: BootNext = B is B's one trial boot.
        s = self.state(); s["next"] = b; self.state(s)
        self.assertEqual(self.gate_env("envget B_OK", "envget B_TRY"), ["0", "1"])
        # After the gate's mark-good on B: B first in BootOrder, BootNext used up by the firmware.
        s = self.state(); s.pop("next"); s["current"] = b; s["order"] = [b, a, "0001", "0000"]; self.state(s)
        self.assertEqual(self.gate_env("envget A_OK", "envget B_OK", "envget B_TRY"), ["1", "1", "0"])
        dump = " ".join(self.gate_env("envdump"))
        self.assertIn(f"BootCurrent={b}", dump)
        self.assertIn(f"BootOrder={b},{a},0001,0000", dump)
        self.assertTrue(self.gate_env('[ -n "$GATE_FELLBACK_WHY" ] && echo set'))

    def test_gate_sees_no_slot_without_entries(self):
        self.assertEqual(self.gate_env("envget A_OK", "envget B_TRY"), ["0", "0"])


def sb_harness():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sb_harness", os.path.join(ROOT, "test", "qemu", "secureboot.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EFI_AFTER_INSTALL = ("BootCurrent: 0001\nBootNext: 0004\nTimeout: 0 seconds\nBootOrder: 0003,0001,0000\n"
                     "Boot0000* UiApp\tFvVol(7cb8bdc9)/FvFile(462caa21)\n"
                     "Boot0001* UEFI Misc Device\tPciRoot(0x0)/Pci(0x3,0x0)\n"
                     "Boot0003* A\tHD(2,GPT,1f,0x200800,0x100000)/\\EFI\\Linux\\onemind-A.efi\n"
                     "Boot0004* B\tHD(3,GPT,2e,0x300800,0x100000)/\\EFI\\Linux\\onemind-B.efi\n")
EFI_ON_B = ("BootCurrent: 0004\nTimeout: 0 seconds\nBootOrder: 0004,0003,0001,0000\n"
            + EFI_AFTER_INSTALL.split("BootOrder: 0003,0001,0000\n")[1])


class SlotBHarness(unittest.TestCase):
    """SB5's reading of efibootmgr and its PASS rule (test/qemu/secureboot.py, CRITERIA-SECUREBOOT.md section 4)."""

    @classmethod
    def setUpClass(cls):
        cls.sb = sb_harness()

    def test_reads_entries_by_label(self):
        st = self.sb.parse_efi(EFI_AFTER_INSTALL)
        self.assertEqual((st["A"], st["B"], st["BootNext"], st["BootCurrent"]), ("0003", "0004", "0004", "0001"))
        self.assertEqual(st["BootOrder"], ["0003", "0001", "0000"])
        self.assertIn("onemind-B.efi", st["B_line"])
        # A console that expands tabs: same reading; "UEFI Misc Device" is never taken for a slot.
        self.assertEqual(self.sb.parse_efi(EFI_AFTER_INSTALL.replace("\t", "        "))["B"], "0004")

    def test_pass_only_when_b_booted_its_own_uki_and_was_committed(self):
        sb, installed, after = self.sb, self.sb.parse_efi(EFI_AFTER_INSTALL), self.sb.parse_efi(EFI_ON_B)
        a_ok = ("committed-boot", "A", "1")
        self.assertTrue(sb.sb5_verdict(installed, a_ok, ("mark-good", "B", "2"), after))
        self.assertFalse(sb.sb5_verdict(installed, a_ok, ("fell-back", "A", "1"), after))       # trial failed
        self.assertFalse(sb.sb5_verdict(sb.parse_efi(EFI_AFTER_INSTALL.replace("BootNext: 0004\n", "")),
                                        a_ok, ("mark-good", "B", "2"), after))                    # no BootNext = B
        self.assertFalse(sb.sb5_verdict(installed, a_ok, ("mark-good", "B", "2"),
                                        sb.parse_efi(EFI_ON_B.replace("BootCurrent: 0004", "BootCurrent: 0003"))))
        self.assertFalse(sb.sb5_verdict(installed, a_ok, ("mark-good", "B", "2"),
                                        sb.parse_efi(EFI_ON_B.replace("BootOrder: 0004,0003", "BootOrder: 0003,0004"))))
        self.assertFalse(sb.sb5_verdict(installed, ("mark-good", "B", "1"), ("mark-good", "B", "2"), after))


if __name__ == "__main__":
    unittest.main()
