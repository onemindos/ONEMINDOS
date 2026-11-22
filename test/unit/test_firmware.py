# SPDX-License-Identifier: Apache-2.0
"""Firmware layer (os/rootfs/firmware/README.md): package lists, licence record, the open-image switch."""
import os, subprocess, tempfile, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FW = os.path.join(ROOT, "os", "rootfs", "firmware")
BOARD = os.path.join(ROOT, "os", "boards", "x86_64-efi", "packages-firmware-debian.txt")
LOCK = yaml.safe_load(open(os.path.join(ROOT, "os", "versions.lock.yaml")))
read = lambda p: open(os.path.join(ROOT, p)).read()


def resolve(fw, arch="amd64", board=BOARD, leg="debian"):
    r = subprocess.run(["sh", os.path.join(FW, "resolve.sh"), leg, arch, fw, board],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.split(), r.stderr


def licence_rows():
    rows = {}
    for line in open(os.path.join(FW, "licences.txt")):
        if line.strip() and not line.startswith("#"):
            p, kind, lic, src = line.rstrip("\n").split("|")
            rows[p] = (kind, lic, src)
    return rows


class Switch(unittest.TestCase):
    def test_both_variants_resolve(self):
        rc, pkgs, _ = resolve("yes")
        self.assertEqual(rc, 0)
        for p in ("intel-microcode", "amd64-microcode", "firmware-iwlwifi", "firmware-realtek",
                  "firmware-misc-nonfree"):
            self.assertIn(p, pkgs)
        self.assertEqual(pkgs, sorted(set(pkgs)))
        rc, pkgs, _ = resolve("no")
        self.assertEqual((rc, pkgs), (0, []))

    def test_bad_switch_value_fails(self):
        rc, _, err = resolve("maybe")
        self.assertNotEqual(rc, 0)
        self.assertIn("yes or no", err)

    def test_arch_without_list_has_no_firmware_layer(self):
        self.assertEqual(resolve("yes", arch="arm64")[:2], (0, []))

    def test_board_file_adds_a_package(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as f:
            f.write("firmware-realtek  # duplicate is fine\n")
            f.flush()
            rc, pkgs, _ = resolve("yes", board=f.name)
        self.assertEqual(rc, 0)
        self.assertEqual(pkgs.count("firmware-realtek"), 1)

    def test_package_without_licence_row_is_refused(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as f:
            f.write("firmware-unrecorded\n")
            f.flush()
            rc, _, err = resolve("yes", board=f.name)
        self.assertNotEqual(rc, 0)
        self.assertIn("firmware-unrecorded", err)


class Lists(unittest.TestCase):
    def test_only_firmware_and_microcode(self):
        rows = licence_rows()
        self.assertTrue(rows)
        for p, (kind, lic, src) in rows.items():
            self.assertIn(kind, ("firmware", "microcode"), p)
            self.assertTrue(p.startswith("firmware-") or p.endswith("microcode"), p)
            self.assertTrue(lic and src, p)

    def test_every_listed_package_has_a_licence(self):
        _, pkgs, _ = resolve("yes")
        self.assertFalse(set(pkgs) - set(licence_rows()))

    def test_pinned_snapshot_matches_the_base(self):
        self.assertEqual(LOCK["image_firmware"]["snapshot"], LOCK["base"]["debian"]["snapshot"])
        self.assertEqual(LOCK["image_firmware"]["component"], "non-free-firmware")


class Wiring(unittest.TestCase):
    def apt(self, *args):
        """Run configure-apt.sh with /etc/apt redirected into a temp dir."""
        with tempfile.TemporaryDirectory() as d:
            src = read("os/rootfs/sources/configure-apt.sh").replace("/etc/apt", d + "/apt")
            os.makedirs(d + "/apt/apt.conf.d"); os.makedirs(d + "/apt/sources.list.d")
            r = subprocess.run(["sh", "-c", src, "sh", *args], capture_output=True, text=True)
            out = ""
            f = d + "/apt/sources.list.d/onemind-snapshot.sources"
            if os.path.exists(f):
                out = open(f).read()
            return r.returncode, out

    def test_component_follows_the_switch(self):
        for args, want in ((("debian", "20261111T000000Z"), True), (("debian", "20261111T000000Z", "yes"), True),
                           (("debian", "20261111T000000Z", "no"), False)):
            rc, out = self.apt(*args)
            self.assertEqual(rc, 0)
            self.assertEqual(out.count("Components: main non-free-firmware"), 2 if want else 0, args)
            self.assertEqual(out.count("Components: main\n"), 0 if want else 2, args)
        self.assertNotEqual(self.apt("debian", "20261111T000000Z", "maybe")[0], 0)

    def test_containerfile_and_make_use_the_switch(self):
        c = read("os/rootfs/Containerfile")
        self.assertIn('onemind-configure-apt "$LEG" "$SNAPSHOT" "$FIRMWARE"', c)
        self.assertIn("firmware/resolve.sh", c)
        self.assertIn("FIRMWARE=no image", c)
        self.assertIn("firmware=%s", c)
        self.assertIn("--build-arg FIRMWARE=$(FIRMWARE)", read("Makefile"))


if __name__ == "__main__":
    unittest.main()
