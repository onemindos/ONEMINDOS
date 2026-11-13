# SPDX-License-Identifier: Apache-2.0
"""scripts/release/check-signed.py: refuses unsigned, tampered or unlisted artefacts. Keys are throwaway,
made in a temp dir and never committed."""
import hashlib, os, shutil, subprocess, sys, tempfile, unittest

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


COLLECT = os.path.join(ROOT, "scripts", "release", "collect.py")
ONE_OF_EACH = ["onemind-x86_64-efi-0.1.0.img.xz", "onemind-vm-0.1.0.qcow2", "x86_64-efi-0.1.0.raucb",
               "onemind-installer-x86_64-0.1.0.img.xz", "onemind-cloud-aws-0.1.0.raw.xz",
               "onemind-cloud-gcp-0.1.0.tar.gz", "onemind-cloud-azure-0.1.0.vhd.xz",
               "onemind-cloud-hetzner-0.1.0.raw.xz", "onemind-cloud-proxmox-0.1.0.qcow2"]


def collect(dl, out):
    return subprocess.run([sys.executable, "-I", COLLECT, "--dl", dl, "--out", out], capture_output=True, text=True)


class Collect(unittest.TestCase):
    """Every artefact class is collected (so it is signed and checked) or the release is refused."""
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.dl, self.out = os.path.join(self.t.name, "dl"), os.path.join(self.t.name, "rel")

    def put(self, art, name, data=b"x"):
        d = os.path.join(self.dl, art)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)

    def fill(self, names=ONE_OF_EACH):
        for i, n in enumerate(names):
            self.put(f"a{i}", n)
            self.put(f"a{i}", "SHA256SUMS")          # per-artifact lists are skipped, never released

    def test_every_class_is_collected_and_checksum_lists_are_not(self):
        self.fill()
        r = collect(self.dl, self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(os.listdir(self.out)), sorted(ONE_OF_EACH))

    def test_unknown_file_refuses(self):
        self.fill()
        self.put("a0", "mystery.bin")
        r = collect(self.dl, self.out)
        self.assertEqual(r.returncode, 2)
        self.assertIn("mystery.bin", r.stderr)

    def test_dev_build_refuses(self):
        self.fill(ONE_OF_EACH[:-1] + ["onemind-cloud-proxmox-0.1.0-dev.7.qcow2"])
        self.assertEqual(collect(self.dl, self.out).returncode, 2)

    def test_missing_class_refuses(self):
        for cls_drop in ("installer", "raucb", "cloud"):
            with self.subTest(cls_drop):
                shutil.rmtree(self.dl, ignore_errors=True)
                self.fill([n for n in ONE_OF_EACH if cls_drop not in n])
                self.assertEqual(collect(self.dl, self.out).returncode, 2)

    def test_collision_refuses(self):
        self.fill()
        self.put("other", ONE_OF_EACH[0])
        self.assertEqual(collect(self.dl, self.out).returncode, 2)

    def test_unsigned_release_of_every_class_is_refused_and_signed_passes(self):
        self.fill()
        self.assertEqual(collect(self.dl, self.out).returncode, 0)
        key, pub = keypair(os.path.join(self.t.name, "k"))
        sums = os.path.join(self.out, "SHA256SUMS")
        names = sorted(os.listdir(self.out))
        with open(sums, "w") as f:
            for n in names:
                f.write(f"{hashlib.sha256(b'x').hexdigest()}  {n}\n")
        self.assertEqual(run(self.out, pub).returncode, 2)         # no .sig: all nine refused
        subprocess.run(["openssl", "dgst", "-sha256", "-sign", key, "-out", sums + ".sig", sums], check=True, capture_output=True)
        r = run(self.out, pub); self.assertEqual(r.returncode, 0, r.stderr)
        for n in ONE_OF_EACH:                                       # tampering with any class is caught
            with self.subTest(n):
                p = os.path.join(self.out, n)
                with open(p, "wb") as f:
                    f.write(b"evil")
                self.assertEqual(run(self.out, pub).returncode, 2)
                with open(p, "wb") as f:
                    f.write(b"x")

    def test_downloads_page_lists_every_artefact_class(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("collect", COLLECT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        page = open(os.path.join(ROOT, "site", "src", "pages", "downloads.astro"), encoding="utf-8").read()
        for kind, _ in mod.KINDS:
            self.assertIn(f"['{kind}',", page, kind)
        self.assertIn("r.signed === true", page.replace("(r) => r.signed === true", "r.signed === true"))  # unsigned is never listed

    def test_workflow_order_collect_sign_verify_then_publish(self):
        w = open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8").read()
        order = [w.index(s) for s in ("collect.py", "openssl dgst -sha256 -sign", "check-signed.py", "gh release create")]
        self.assertEqual(order, sorted(order))
        self.assertEqual(w.count("gh release create"), 1)
        self.assertIn("needs: gate", w)
        self.assertIn("rel/*", w.split("gh release create")[1])     # only the verified directory is published
        self.assertNotIn("-name '*.xz'", w)                         # no ad-hoc find that could miss a class


if __name__ == "__main__":
    unittest.main()
