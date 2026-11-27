# SPDX-License-Identifier: Apache-2.0
"""`make image KEYRING=<public RAUC CA cert>` (Step 5, os/update/STEP5-SIGNED-UPDATE.md): the image trusts that CA, no
signing key is made or read and no bundle is written; without KEYRING nothing changes. os/assemble/dev-image.sh runs
here against a stand-in assembler that records its arguments (no Docker, no image). Needs openssl."""
import os, shutil, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STUB = """#!/usr/bin/env python3
import sys, os
open(os.environ["STUB_LOG"], "w").write("\\n".join(sys.argv[1:]))
a = sys.argv[1:]
d = a[a.index("--out-dir") + 1]
os.makedirs(d, exist_ok=True)
open(os.path.join(d, "onemind-x-1.img"), "w").write("img")
"""


@unittest.skipUnless(shutil.which("openssl") and shutil.which("sh"), "needs openssl and sh")
class Keyring(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        src = os.path.join(self.d, "src")                           # a copy of the script beside a stand-in board
        os.makedirs(os.path.join(src, "os", "assemble"))
        os.makedirs(os.path.join(src, "os", "boards", "stub"))
        shutil.copy(os.path.join(ROOT, "os", "assemble", "dev-image.sh"), os.path.join(src, "os", "assemble"))
        shutil.copy(os.path.join(ROOT, "os", "assemble", "signer.ext"), os.path.join(src, "os", "assemble"))
        open(os.path.join(src, "os", "boards", "stub", "board.yaml"), "w").write("assembler: stub-asm.py\n")
        open(os.path.join(src, "stub-asm.py"), "w").write(STUB)
        self.script = os.path.join(src, "os", "assemble", "dev-image.sh")
        self.ca = os.path.join(self.d, "ca.pem")                    # a throwaway CA certificate
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=test-ca",
                        "-keyout", os.path.join(self.d, "ca.key"), "-out", self.ca], check=True, capture_output=True)
        self.log = os.path.join(self.d, "args")

    def run_script(self, out, **env):
        e = {k: v for k, v in os.environ.items() if k not in ("KEYRING", "SECUREBOOT")}
        e.update(BOARD="stub", ROOTFS="/nonexistent.tar", VERSION="0.1.0", STUB_LOG=self.log, **env)
        return subprocess.run(["sh", self.script, out], env=e, capture_output=True, text=True)

    def test_keyring_is_trusted_and_no_key_or_bundle_is_made(self):
        out = os.path.join(self.d, "out")
        r = self.run_script(out, KEYRING=self.ca)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = open(self.log).read().split("\n")
        self.assertEqual(args[args.index("--keyring") + 1], self.ca)
        self.assertNotIn("--cert", args)
        self.assertNotIn("--key", args)
        self.assertEqual(open(os.path.join(out, "keyring.cert.pem")).read(), open(self.ca).read())
        self.assertFalse(os.path.exists(os.path.join(out, "dev-ca.cert.pem")))
        self.assertIn("trusts the RAUC CA", r.stdout)

    def test_refusals(self):
        key = os.path.join(self.d, "ca.key")
        r = self.run_script(os.path.join(self.d, "o1"), KEYRING=key)
        self.assertEqual(r.returncode, 2)
        both = os.path.join(self.d, "both.pem")
        open(both, "w").write(open(self.ca).read() + open(key).read())
        r = self.run_script(os.path.join(self.d, "o2"), KEYRING=both)
        self.assertEqual(r.returncode, 2)
        self.assertIn("public CA certificate only", r.stderr)
        r = self.run_script(os.path.join(self.d, "o3"), KEYRING=self.ca, SECUREBOOT="1")
        self.assertEqual(r.returncode, 2)

    def test_without_keyring_the_throwaway_path_is_unchanged(self):
        out = os.path.join(self.d, "out")
        r = self.run_script(out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = open(self.log).read().split("\n")
        self.assertIn("--cert", args)
        self.assertIn("--key", args)
        self.assertTrue(os.path.exists(os.path.join(out, "dev-ca.cert.pem")))

    def test_make_passes_only_the_public_cert_into_the_container(self):
        mk = open(os.path.join(ROOT, "Makefile")).read()
        self.assertIn('$(if $(KEYRING),-v "$(abspath $(KEYRING))":/keyring.pem:ro -e KEYRING=/keyring.pem)', mk)


if __name__ == "__main__":
    unittest.main()
