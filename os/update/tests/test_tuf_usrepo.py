# SPDX-License-Identifier: Apache-2.0
"""test/qemu/usrepo.py: the throwaway root and channels of the signed-update QEMU test (CRITERIA-UPDATE-SIGNED.md).

Built here from small stand-in bundles, then checked twice: with python-tuf's metadata API, and with the box's
own verifier (go-tuf, internal/update TestSignedChannelSequence) walking C1, CK, C2, C1 again and CO with one state
directory, as the box does in US0-US5. Needs the pinned python-tuf (os/update/requirements-tuf.txt); skipped
without it. The Go part runs where Go is installed (CI has it)."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import UPDATE, load  # noqa: E402

REPO = os.path.normpath(os.path.join(UPDATE, "..", ".."))
USREPO = os.path.join(REPO, "test", "qemu", "usrepo.py")
try:
    tr = load("tuf-repo")
except ImportError:               # pragma: no cover
    tr = None


@unittest.skipIf(tr is None, "python-tuf not installed (pip install --require-hashes -r os/update/requirements-tuf.txt)")
class Channels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        b = os.path.join(cls.d, "bundles")
        os.makedirs(b)
        for i, f in enumerate(("good", "us-wrongca", "us-old")):
            open(os.path.join(b, f + ".raucb"), "wb").write(bytes([i]) * 4096)
        env = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS")}
        for args in (["keys", os.path.join(cls.d, "us")], ["channels", os.path.join(cls.d, "us"), b, "x86_64-efi"]):
            r = subprocess.run([sys.executable, "-I", USREPO, *args], capture_output=True, text=True, env=env)
            if r.returncode:
                raise AssertionError(r.stdout + r.stderr)
        cls.ch = os.path.join(cls.d, "us", "channels")
        cls.summary = json.load(open(os.path.join(cls.ch, "summary.json")))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, True)

    def md(self, ch, role):
        return tr.Metadata.from_file(os.path.join(self.ch, ch, role + ".json"))

    def test_the_root_has_the_ceremony_shape_and_goes_into_the_image(self):
        root = os.path.join(self.d, "us", "root", "root.json")
        self.assertEqual(tr.inspect_root(root, 2, 3)[1], [])
        img = os.path.join(self.d, "us", "overlay", "usr", "lib", "onemind", "tuf", "security", "root.json")
        self.assertEqual(open(img, "rb").read(), open(root, "rb").read())
        self.assertEqual(len(tr.Metadata.from_file(root).signatures), 2)          # two of three signed

    def test_the_private_keys_are_gone(self):
        self.assertFalse(os.path.exists(os.path.join(self.d, "us", "keys")))
        for dirpath, _, files in os.walk(os.path.join(self.d, "us")):
            for f in files:
                self.assertFalse(f.endswith(".key"), os.path.join(dirpath, f))

    def test_versions_and_listings(self):
        v = self.summary["channels"]
        self.assertEqual((v["C1"]["timestamp"], v["C2"]["timestamp"], v["CK"]["timestamp"], v["CO"]["timestamp"]), (1, 2, 2, 3))
        listed = lambda ch: sorted(p for p in self.md(ch, "targets").signed.targets if p.endswith(".raucb"))
        self.assertEqual(listed("C1"), ["x86_64-efi/2/onemind-x86_64-efi-2.raucb"])
        self.assertEqual(listed("C2"), ["x86_64-efi/2/onemind-x86_64-efi-2.raucb", "x86_64-efi/3/onemind-x86_64-efi-3.raucb"])
        self.assertEqual(listed("CO"), ["x86_64-efi/1/onemind-x86_64-efi-1.raucb"])
        self.assertTrue(self.summary["publisher_refused_old"], self.summary["publisher_message"])
        self.assertIn("versions must increase", self.summary["publisher_message"])
        for f in self.summary["bundles"].values():                                # every target file once
            self.assertTrue(os.path.exists(os.path.join(self.ch, "files", f)))
        self.assertFalse(any(f.endswith(".raucb") for c in ("C1", "C2", "CK", "CO") for f in os.listdir(os.path.join(self.ch, c))))

    def test_ck_is_signed_by_keys_the_root_does_not_trust_and_co_by_the_real_ones(self):
        root_md = tr.Metadata.from_file(os.path.join(self.ch, "C1", "root.json"))
        root = root_md.signed
        for role in ("targets", "snapshot", "timestamp"):
            self.assertFalse(set(self.md("CK", role).signatures) & set(root.roles[role].keyids), role)
            self.assertTrue(set(self.md("CO", role).signatures) <= set(root.roles[role].keyids), role)
            root_md.verify_delegate(role, self.md("CO", role))                     # the real online keys signed CO

    def test_the_box_verifier_walks_the_sequence(self):
        go = shutil.which("go")
        if not go or not os.path.exists(os.path.join(REPO, "go.mod")):
            self.skipTest("Go is not installed (CI has it)")
        compat = re.search(r"^compatible:\s*(\S+)", open(os.path.join(REPO, "os/boards/x86_64-efi/board.yaml")).read(), re.M).group(1)
        env = dict(os.environ, ONEMIND_US_CHANNELS=self.ch, ONEMIND_US_COMPATIBLE=compat)
        r = subprocess.run([go, "test", "./internal/update", "-run", "TestSignedChannelSequence", "-count=1", "-v"],
                           cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--- PASS: TestSignedChannelSequence", r.stdout)


if __name__ == "__main__":
    unittest.main()
