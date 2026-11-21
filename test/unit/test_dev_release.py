# SPDX-License-Identifier: Apache-2.0
"""DEV-SEE-01 (#234): the arm64 qcow2, the nightly dev-build pre-release, and the "see OneMind" guides."""
import os, re, shutil, subprocess, sys, tempfile, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "release", "dev-release.py")
read = lambda *p: open(os.path.join(ROOT, *p)).read()


def run(*args):
    return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True)


class Downloads(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.dl, self.out = os.path.join(self.t.name, "dl"), os.path.join(self.t.name, "rel")
        for d, name in (("image-debian-arm64-efi", "onemind-arm64-efi-0.1.0-dev.7.qcow2"),
                        ("image-debian-vm-do", "onemind-vm-do-0.1.0-dev.7.qcow2"),
                        ("installer-debian-x86_64", "onemind-installer-amd64-0.1.0-dev.7.img.xz")):
            os.makedirs(os.path.join(self.dl, d))
            with open(os.path.join(self.dl, d, name), "wb") as f:
                f.write(name.encode())
            if d == "image-debian-vm-do":
                for extra in ("onemind-vm-do-0.1.0-dev.7.raucb", "onemind-vm-do-0.1.0-dev.7-next.raucb", "dev-ca.cert.pem"):
                    with open(os.path.join(self.dl, d, extra), "wb") as f:
                        f.write(extra.encode())
            if d == "image-debian-arm64-efi":   # dev-image.sh copies the CA into every board's folder
                with open(os.path.join(self.dl, d, "dev-ca.cert.pem"), "wb") as f:
                    f.write(b"arm64 copy")
            with open(os.path.join(self.dl, d, "SHA256SUMS"), "w") as f:
                f.write("ignored\n")

    def go(self, sha="abcdef1234567", date="20261115"):
        return run("--dl", self.dl, "--out", self.out, "--sha", sha, "--date", date)

    def test_picks_the_three_downloads_and_tags_by_date_and_commit(self):
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "dev-20261115-abcdef1")
        self.assertEqual(sorted(os.listdir(self.out)), [
            "NOTES.md", "SHA256SUMS", "dev-ca.cert.pem", "onemind-arm64-efi-0.1.0-dev.7.qcow2",
            "onemind-installer-amd64-0.1.0-dev.7.img.xz", "onemind-vm-do-0.1.0-dev.7-next.raucb",
            "onemind-vm-do-0.1.0-dev.7.qcow2", "onemind-vm-do-0.1.0-dev.7.raucb"])
        sums = read_out(self.out, "SHA256SUMS")
        self.assertEqual(len(sums.strip().splitlines()), 6)
        self.assertNotIn("ignored", sums)

    def test_notes_start_with_the_warning(self):
        self.go()
        notes = read_out(self.out, "NOTES.md")
        self.assertTrue(notes.startswith("# DEVELOPMENT BUILD. NOT FOR PRODUCTION."), notes[:80])
        self.assertIn("throwaway", notes)
        self.assertIn("docs/see-onemind/", notes)

    def test_bundles_are_attached_with_the_throwaway_key_caveat(self):
        self.go()
        notes = read_out(self.out, "NOTES.md")
        self.assertIn("onemind-vm-do-0.1.0-dev.7.raucb", notes)
        self.assertIn("-next.raucb", notes)
        self.assertIn("#153", notes)
        self.assertNotIn("PRIVATE KEY", "".join(read_out(self.out, n) for n in os.listdir(self.out) if n.endswith(".pem")))

    def test_a_missing_bundle_publishes_nothing(self):
        os.remove(os.path.join(self.dl, "image-debian-vm-do", "onemind-vm-do-0.1.0-dev.7-next.raucb"))
        r = self.go()
        self.assertEqual(r.returncode, 2)
        self.assertIn("update-next download", r.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_a_missing_download_publishes_nothing(self):
        shutil.rmtree(os.path.join(self.dl, "image-debian-arm64-efi"))
        r = self.go()
        self.assertEqual(r.returncode, 2)
        self.assertIn("mac download", r.stderr)
        self.assertFalse(os.path.exists(self.out))

    def test_two_files_for_one_download_are_refused(self):
        with open(os.path.join(self.dl, "image-debian-vm-do", "onemind-vm-do-0.1.0-dev.8.qcow2"), "wb") as f:
            f.write(b"x")
        self.assertEqual(self.go().returncode, 2)

    def test_bad_sha_and_date_are_refused(self):
        self.assertEqual(self.go(sha="not-a-sha").returncode, 2)
        self.assertEqual(self.go(date="2026-11-15").returncode, 2)

    def test_a_file_over_the_asset_limit_is_refused(self):
        big = os.path.join(self.dl, "image-debian-arm64-efi", "onemind-arm64-efi-0.1.0-dev.7.qcow2")
        with open(big, "wb") as f:
            f.truncate(2 * 1024**3)          # sparse: costs no disk
        r = self.go()
        self.assertEqual(r.returncode, 2)
        self.assertIn("2 GiB", r.stderr)


def read_out(d, name):
    with open(os.path.join(d, name)) as f:
        return f.read()


class Workflow(unittest.TestCase):
    def setUp(self):
        self.text = read(".github", "workflows", "dev-build.yml")
        self.wf = yaml.safe_load(self.text)

    def test_runs_nightly_and_by_hand_never_on_a_pull_request(self):
        on = self.wf.get("on", self.wf.get(True))
        self.assertEqual(sorted(on), ["schedule", "workflow_dispatch"])

    def test_write_access_only_where_it_publishes_and_only_on_this_repo(self):
        self.assertEqual(self.wf["permissions"], {"contents": "read"})
        job = self.wf["jobs"]["publish"]
        self.assertEqual(job["permissions"], {"contents": "write", "actions": "read"})
        self.assertIn("github.repository == 'onemindos/ONEMINDOS'", job["if"])

    def test_makes_no_keys_and_uses_no_secrets(self):
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("environment:", self.text)
        self.assertNotRegex(self.text, r"openssl|gpg|cosign|rauc|tuf")

    def test_every_release_is_a_labelled_prerelease(self):
        self.assertIn("--prerelease", self.text)
        self.assertIn("not for production", self.text)
        self.assertIn('startswith("dev-")', self.text)      # pruning never touches a real release

    def test_downloads_what_the_picker_wants(self):
        image = read(".github", "workflows", "image.yml")
        self.assertIn("name: image-debian-${{ matrix.board }}", image)
        for board in ("arm64-efi", "vm-do"):
            self.assertRegex(image, r"board: %s," % board)
            self.assertIn("image-debian-" + board, self.text)
        self.assertIn("name: installer-debian-x86_64", image)
        self.assertIn("installer-debian-x86_64", self.text)


class Arm64Qcow2(unittest.TestCase):
    def test_board_lists_qcow2_and_convert_makes_it(self):
        board = yaml.safe_load(read("os", "boards", "arm64-efi", "board.yaml"))
        self.assertIn("qcow2", board["outputs"])
        conv = read("os", "assemble", "convert.sh")
        self.assertRegex(conv, r'arm64-efi\) FORMATS="qcow2"')

    @unittest.skipUnless(shutil.which("qemu-img") and shutil.which("xz") and shutil.which("sha256sum"), "needs qemu-img, xz, sha256sum")
    def test_convert_runs_on_an_arm64_board_dir(self):
        with tempfile.TemporaryDirectory() as t:
            d = os.path.join(t, "image-arm64-efi")
            os.makedirs(d)
            with open(os.path.join(d, "onemind-arm64-efi-0.0.0.img"), "wb") as f:
                f.truncate(8 * 1024 * 1024)
            r = subprocess.run(["sh", os.path.join(ROOT, "os", "assemble", "convert.sh"), d], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.exists(os.path.join(d, "onemind-arm64-efi-0.0.0.qcow2")))
            self.assertIn("qcow2", read_out(d, "SHA256SUMS"))


class Guides(unittest.TestCase):
    GUIDES = ("README.md", "mac-utm.md", "beelink-usb.md", "digitalocean.md")

    def test_guides_exist_and_are_linked_from_the_index(self):
        index = read("docs", "see-onemind", "README.md")
        for g in self.GUIDES[1:]:
            self.assertTrue(os.path.exists(os.path.join(ROOT, "docs", "see-onemind", g)), g)
            self.assertIn(g, index)

    def test_every_guide_says_what_it_cannot_prove_and_names_the_download(self):
        for g in self.GUIDES[1:]:
            text = read("docs", "see-onemind", g)
            self.assertIn("UNVERIFIED", text, g)
            self.assertRegex(text, r"dev-\*|DEV BUILD|dev build", g)

    def test_beelink_guide_states_the_small_box_limits(self):
        text = read("docs", "see-onemind", "beelink-usb.md")
        self.assertRegex(text, r"2 cores")
        self.assertRegex(text, r"8 GB")
        self.assertRegex(text, r"can(not|'t)")

    def test_droplet_kit_gives_the_hub_role_and_closes_the_cluster_ports(self):
        text = read("lab-kits", "LT-DO-01", "README.md")
        self.assertNotIn("no user data", text)
        self.assertIn("role: hub", text)
        self.assertRegex(text, r"Cloud Firewall")
        for port in ("4222", "6443", "10250", "8472"):
            self.assertIn(port, text)


if __name__ == "__main__":
    unittest.main()
