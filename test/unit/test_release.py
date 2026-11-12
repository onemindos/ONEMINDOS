# SPDX-License-Identifier: Apache-2.0
"""scripts/release/check-signed.py: refuses unsigned, tampered or unlisted artefacts. Keys are throwaway,
made in a temp dir and never committed."""
import hashlib, os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "release", "check-signed.py")


def run(d, pub):
    return subprocess.run([sys.executable, "-I", SCRIPT, "--dir", d, "--pubkey", pub], capture_output=True, text=True)


def keypair(base):
    key, pub = base + "-k.pem", base + "-p.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", key],
                   check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", key, "-pubout", "-out", pub], check=True, capture_output=True)
    return key, pub


class CheckSigned(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.d = os.path.join(self.t.name, "rel")
        os.makedirs(self.d)
        self.key, self.pub = keypair(os.path.join(self.t.name, "a"))
        with open(os.path.join(self.d, "a.img.xz"), "wb") as f:
            f.write(b"image")
        s = os.path.join(self.d, "SHA256SUMS")
        with open(s, "w") as f:
            f.write(f"{hashlib.sha256(b'image').hexdigest()}  a.img.xz\n")
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", self.key, "-out", s + ".sig", s],
                       check=True, capture_output=True)

    def test_signed_passes(self):
        r = run(self.d, self.pub)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_public_key_refuses(self):
        self.assertEqual(run(self.d, os.path.join(self.t.name, "none.pem")).returncode, 2)

    def test_unsigned_refuses(self):
        os.remove(os.path.join(self.d, "SHA256SUMS.sig"))
        r = run(self.d, self.pub)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unsigned", r.stderr)

    def test_wrong_key_refuses(self):
        _, other_pub = keypair(os.path.join(self.t.name, "b"))
        self.assertEqual(run(self.d, other_pub).returncode, 2)

    def test_tampered_file_refuses(self):
        with open(os.path.join(self.d, "a.img.xz"), "wb") as f:
            f.write(b"evil")
        self.assertEqual(run(self.d, self.pub).returncode, 2)

    def test_unlisted_file_refuses(self):
        with open(os.path.join(self.d, "extra.img"), "wb") as f:
            f.write(b"x")
        self.assertEqual(run(self.d, self.pub).returncode, 2)

    def test_workflow_gates_on_the_public_key(self):
        w = open(os.path.join(ROOT, ".github", "workflows", "release.yml")).read()
        self.assertIn("os/release/release-pubkey.pem", w)
        self.assertIn("check-signed.py", w)
        self.assertNotIn("pull_request", w)
        self.assertFalse(os.path.exists(os.path.join(ROOT, "os", "release", "release-pubkey.pem")))  # F-27 is the founder's


if __name__ == "__main__":
    unittest.main()
