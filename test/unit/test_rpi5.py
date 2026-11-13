# SPDX-License-Identifier: Apache-2.0
"""Board rpi5 (brief 30 D-B2.2, BD-07): MBR layout, boot configuration, tryboot backend state machine
(the F-PI5 kit's desk check P-e, with a faked firmware device tree), pins and the Imager entry.
QEMU cannot boot the Pi firmware, so these plus os/boards/rpi5/check-image.py are the CI evidence."""
import json, lzma, os, re, shutil, subprocess, sys, tempfile, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BD = os.path.join(ROOT, "os", "boards", "rpi5")
sys.path.insert(0, BD)
import rpi5_boot as R  # noqa: E402
import assemble_rpi5 as AR  # noqa: E402
import imager_json  # noqa: E402

BOARD = yaml.safe_load(open(os.path.join(BD, "board.yaml")))
LAYOUT = yaml.safe_load(open(os.path.join(BD, "layout.yaml")))
LOCK = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))
read = lambda *p: open(os.path.join(ROOT, *p)).read()


class Layout(unittest.TestCase):
    def test_bd07_labels_sizes_numbers(self):
        rows = [(p["number"], p["label"], p["size"]) for p in LAYOUT["partitions"]]
        self.assertEqual(rows, [(1, "onemind-autoboot", "64MiB"), (2, "onemind-boot-a", "512MiB"),
                                (3, "onemind-boot-b", "512MiB"), (4, "onemind-extended", "rest"),
                                (5, "onemind-system-a", "8GiB"), (6, "onemind-system-b", "8GiB"),
                                (7, "onemind-data", "rest")])
        self.assertEqual(LAYOUT["table"], "mbr")

    def test_plan_geometry(self):
        g = R.plan(LAYOUT)
        P = g["parts"]
        self.assertEqual(g["total"], 20 * 1024 * 2048)
        self.assertEqual(P[1][2:], (2048, 64 * 2048))
        self.assertEqual(P[2][2], 2048 + 64 * 2048)
        self.assertEqual(P[4][2], P[3][2] + P[3][3])                     # extended right after boot B
        self.assertEqual(P[4][2] + P[4][3], g["total"])                  # ... to the end of the disk
        self.assertEqual(P[5][2], P[4][2] + 2048)                        # first EBR at the extended start
        self.assertEqual(P[6][2], P[5][2] + P[5][3] + 2048)
        self.assertEqual(P[7][2] + P[7][3], g["total"])
        self.assertGreaterEqual(P[7][3] * 512 >> 30, 2)                  # >=2 GiB data before growing
        for n in P:
            self.assertEqual(P[n][2] % 2048, 0, f"p{n} not 1 MiB aligned")

    def test_mbr_roundtrip(self):
        secs = R.mbr_sectors(LAYOUT, BOARD["disk_id"])
        got = R.parse_mbr(lambda lba: secs.get(lba, bytes(512)))
        self.assertEqual(got["disk_id"], "4f4d5035")
        want = {n: (R.MBR_TYPES[t], s, c) for n, (_, t, s, c) in R.plan(LAYOUT)["parts"].items()}
        self.assertEqual(got["parts"], want)
        self.assertEqual(secs[0][0x1FE:], b"\x55\xaa")

    def test_bad_layouts_rejected(self):
        bad = {"disk_size": "1GiB", "partitions": [dict(p) for p in LAYOUT["partitions"]]}
        with self.assertRaises(AssertionError):
            R.plan(bad)                                                    # 17 GiB of slots in 1 GiB
        swapped = {"disk_size": "20GiB", "partitions": [LAYOUT["partitions"][1], LAYOUT["partitions"][0]] + LAYOUT["partitions"][2:]}
        with self.assertRaises(AssertionError):
            R.plan(swapped)


class BootConfig(unittest.TestCase):
    def test_cmdline_per_slot(self):
        for slot, root in (("A", "05"), ("B", "06")):
            c = R.cmdline(BOARD, slot)
            self.assertIn(f"root=PARTUUID=4f4d5035-{root} ", c)
            self.assertIn(f"rauc.slot={slot}", c)
            for flag in ("panic=10", " ro ", "rootwait", "cgroup_enable=memory", "console=tty1"):
                self.assertIn(flag, c)
            self.assertNotIn(" rw", c)
            self.assertEqual(c.count("\n"), 1)

    def test_config_txt(self):
        c = R.config_txt(BOARD)
        for line in ("kernel=kernel_2712.img", "initramfs initramfs_2712 followkernel", "force_eeprom_read=0",
                     "camera_auto_detect=0", "display_auto_detect=0", "arm_64bit=1"):
            self.assertIn(line + "\n", c)
        self.assertRegex(c, r"\[boot_partition=2\]\ncmdline=cmdline_a.txt\n\[boot_partition=3\]\ncmdline=cmdline_b.txt\n\[all\]\n$")
        self.assertNotRegex(c, r"(?m)^os_prefix=")                                # E10: overlays from this slot only
        self.assertIn("kernel=kernel8.img", R.config_txt(dict(BOARD, kernel="v8")))

    def test_autoboot(self):
        self.assertEqual(R.autoboot_txt("A"), "[all]\ntryboot_a_b=1\nboot_partition=2\n[tryboot]\nboot_partition=3\n")
        self.assertIn("[all]\ntryboot_a_b=1\nboot_partition=3\n[tryboot]\nboot_partition=2", R.autoboot_txt("B"))

    def test_system_conf(self):
        c = AR.system_conf(BOARD)
        self.assertIsNone(re.search(r"@[A-Z_]+@", c))
        for s in ("compatible=onemind-rpi5", "bootloader=custom", "bundle-formats=verity",
                  "bootloader-custom-backend=/usr/lib/onemind/rpi-tryboot-ab.sh", "pre-install=/usr/lib/onemind/rauc-pre-install",
                  "device=/dev/disk/by-partuuid/4f4d5035-02\ntype=vfat\nbootname=A",
                  "device=/dev/disk/by-partuuid/4f4d5035-06\ntype=ext4\nparent=boot.1"):
            self.assertIn(s, c)

    def test_fstab_matches_board_and_base_binds(self):
        f = read("os/boards/rpi5/rootfs/etc/fstab")
        self.assertIn(f"PARTUUID={BOARD['disk_id']}-01  /boot/efi  vfat", f)
        self.assertIn(f"PARTUUID={BOARD['disk_id']}-07  /data      ext4", f)
        binds = lambda t: [l for l in t.splitlines() if l.startswith("/data/state/")]
        self.assertEqual(binds(f), binds(read("os/rootfs/layers/base/etc/fstab")))
        self.assertIn(BOARD["disk_id"], read("os/boards/rpi5/rootfs/usr/lib/onemind/rpi5-grow"))


@unittest.skipUnless(shutil.which("sh") and shutil.which("od"), "needs sh and od")
class TrybootBackend(unittest.TestCase):
    """rpi-tryboot-ab.sh against a temp autoboot dir and a faked /proc/device-tree (kit check P-e)."""
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.ab, self.dt, self.param = (os.path.join(self.d, x) for x in ("ab", "dt", "run/reboot-param"))
        os.makedirs(self.ab); os.makedirs(self.dt)
        open(os.path.join(self.ab, "autoboot.txt"), "w").write(R.autoboot_txt("A"))
        open(os.path.join(self.ab, "slot-A.good"), "w").close()
        self.boot(tryboot=0, partition=2)

    def tearDown(self):
        shutil.rmtree(self.d)

    def boot(self, tryboot, partition):
        if os.path.exists(self.param):
            os.remove(self.param)                                         # /run is empty after a reboot
        for k, v in (("tryboot", tryboot), ("partition", partition)):
            open(os.path.join(self.dt, k), "wb").write(v.to_bytes(4, "big"))

    def be(self, *args):
        env = dict(os.environ, ONEMIND_AB=self.ab, ONEMIND_DT=self.dt, ONEMIND_REBOOT_PARAM=self.param)
        r = subprocess.run(["sh", os.path.join(BD, "rootfs/usr/lib/onemind/rpi-tryboot-ab.sh"), *args],
                           env=env, capture_output=True, text=True)
        return r.returncode, r.stdout.strip()

    def autoboot(self):
        return open(os.path.join(self.ab, "autoboot.txt")).read()

    def test_update_commit_and_rollback(self):
        self.assertEqual(self.be("get-current"), (0, "A"))
        self.assertEqual(self.be("get-primary"), (0, "A"))
        # rauc install into B: mark target bad, write, then make it primary -> one-shot tryboot armed
        self.assertEqual(self.be("set-state", "B", "bad")[0], 0)
        self.assertEqual(self.be("set-primary", "B")[0], 0)
        self.assertIn("tryboot", open(self.param).read())
        self.assertEqual(self.be("get-primary"), (0, "B"))
        self.assertEqual(self.autoboot(), R.autoboot_txt("A"))           # install never touches autoboot.txt
        # the trial boot: firmware booted p3 via tryboot; the gate commits
        self.boot(tryboot=1, partition=3)
        self.assertEqual(self.be("get-current"), (0, "B"))
        self.assertEqual(self.be("set-state", "B", "good")[0], 0)
        self.assertEqual(self.autoboot(), R.autoboot_txt("B"))
        self.assertEqual(self.be("get-state", "B"), (0, "good"))
        # later normal boots from p3: B is primary; A cannot be marked good without a tryboot into it
        self.boot(tryboot=0, partition=3)
        self.assertEqual(self.be("get-primary"), (0, "B"))
        self.assertEqual(self.be("set-state", "A", "good")[0], 1)
        self.assertEqual(self.be("set-state", "A", "bad")[0], 0)
        self.assertEqual(self.be("get-state", "A"), (0, "bad"))
        self.assertFalse(os.path.exists(os.path.join(self.ab, "slot-A.good")))

    def test_failed_trial_never_commits(self):
        self.be("set-state", "B", "bad"); self.be("set-primary", "B")
        self.boot(tryboot=0, partition=2)                                 # trial crashed: firmware fell back to A
        self.assertEqual(self.be("set-state", "B", "good")[0], 1)         # not booted from B via tryboot
        self.assertEqual(self.autoboot(), R.autoboot_txt("A"))
        self.assertEqual(self.be("set-state", "B", "bad")[0], 0)          # gate: fell-back -> mark-bad other
        self.assertEqual(self.be("get-primary"), (0, "A"))

    def test_cancel_and_mark_bad_disarm(self):
        self.be("set-primary", "B")
        self.assertEqual(self.be("set-primary", "A")[0], 0)              # back to committed: cancels the tryboot
        self.assertFalse(os.path.exists(self.param))
        self.be("set-primary", "B")
        self.be("set-state", "B", "bad")                                  # a failed install disarms too
        self.assertFalse(os.path.exists(self.param))

    def test_set_primary_fails_loudly(self):
        self.param = "/nonexistent-dir-for-test/x/reboot-param"
        self.assertEqual(self.be("set-primary", "B")[0], 1)

    def test_gate_env(self):
        env = os.path.join(BD, "rootfs/usr/lib/onemind/gate-slot-env")
        out = subprocess.run(["bash", "-c", f'. "{env}"; AB="{self.ab}"; echo $(envget A_OK) $(envget B_OK) $(envget A_TRY)'],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual(out, ["1", "0", "n/a"])
        self.assertIn(". /usr/lib/onemind/gate-slot-env", read("os/gate/onemind-health-gate"))


class Pins(unittest.TestCase):
    def test_rpi_kernel_debs_match_lock(self):
        s = read("os/boards/rpi5/fetch-rpi.sh")
        L = LOCK["rpi5"]
        self.assertIn(f"RPI_KERNEL={L['kernel']['version']}", s)
        for deb in L["kernel"]["debs"]:
            self.assertIn(f"{deb['path']} {deb['sha256']}", s)
        self.assertEqual(len(re.findall(r"^pool/\S+ [0-9a-f]{64}$", s, re.M)), len(L["kernel"]["debs"]))

    def test_archive_key_and_eeprom(self):
        L = LOCK["rpi5"]
        p = read("os/boards/rpi5/pin-rpi.sh")
        self.assertIn(f"FPR={L['archive']['key_fingerprint']}", p)
        self.assertIn(f"KEYRING_SHA={L['archive']['keyring_deb_sha256']}", p)
        self.assertIn(f"EEPROM_MIN_TS={L['eeprom']['build_timestamp']}", read("os/boards/rpi5/rootfs/etc/default/onemind-rpi5"))
        self.assertEqual(str(BOARD["eeprom_min"]), L["eeprom"]["release"])


class Imager(unittest.TestCase):
    def test_entry(self):
        d = tempfile.mkdtemp()
        try:
            img = os.path.join(d, "onemind-rpi5-0.1.0.img"); xz = img + ".xz"
            open(img, "wb").write(os.urandom(4096))
            with lzma.open(xz, "wb") as f:
                f.write(open(img, "rb").read())
            out = os.path.join(d, "os_list.json")
            imager_json.main(["--img", img, "--xz", xz, "--url-base", "https://example.invalid/r/", "--date", "2026-11-12", "--out", out])
            e = json.load(open(out))["os_list"][0]
            self.assertEqual(e["url"], "https://example.invalid/r/onemind-rpi5-0.1.0.img.xz")
            self.assertEqual(e["extract_size"], 4096)
            self.assertEqual(e["extract_sha256"], imager_json.sha256(img))
            self.assertEqual(e["image_download_sha256"], imager_json.sha256(xz))
            self.assertEqual(e["devices"], ["pi5-64bit"])
            self.assertIn("0.1.0", e["name"])
            self.assertNotIn("init_format", e)
            with self.assertRaises(SystemExit):
                imager_json.main(["--img", img, "--xz", xz, "--url-base", "http://x"])
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
