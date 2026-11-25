# SPDX-License-Identifier: Apache-2.0
"""An installed box must be able to take an OS update (#234, D-010): bundle selection per board and
N to N+1 compatibility of the dev release (scripts/release/dev-release.py), and the wiring in image.yml."""
import base64, importlib.util, json, os, re, subprocess, sys, tempfile, unittest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("dev_release", os.path.join(ROOT, "scripts", "release", "dev-release.py"))
dr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dr)
read = lambda *p: open(os.path.join(ROOT, *p)).read()
pem = lambda b: "-----BEGIN CERTIFICATE-----\n" + base64.b64encode(b).decode() + "\n-----END CERTIFICATE-----\n"


def box(**kw):
    r = {"board": "x86_64-efi", "compatible": "onemind-x86_64-efi", "version": "0.1.0-dev.7",
         "min_from_version": "", "ca_sha256": "aa"}
    r.update(kw)
    return r


class Versions(unittest.TestCase):
    def test_same_order_as_the_box(self):
        c = dr.compare_versions
        self.assertEqual(c("0.1.0-dev.7-next", "0.1.0-dev.7"), 1)
        self.assertEqual(c("0.1.0-dev.583", "0.1.0-dev.582"), 1)
        self.assertEqual(c("0.1.0-dev.9", "0.1.0-dev.10"), -1)
        self.assertEqual(c("0.1.0", "0.1.0-dev.99"), 1)
        self.assertEqual(c("0.1.20261112025704", "0.1.20261111025704"), 1)
        self.assertEqual(c("0.1", "0.1.0"), 0)
        with self.assertRaises(ValueError):
            c("0.x", "0.1")


class NToNPlusOne(unittest.TestCase):
    def test_the_next_release_is_accepted(self):
        self.assertEqual(dr.accepts(box(), box(version="0.1.0-dev.7-next")), "")
        self.assertEqual(dr.accepts(box(version="0.1.20261112025704"), box(version="0.1.20261113025704")), "")

    def test_refusals_say_why(self):
        self.assertIn("not newer", dr.accepts(box(), box()))
        self.assertIn("not newer", dr.accepts(box(version="0.1.0-dev.8"), box()))
        self.assertIn("board", dr.accepts(box(), box(board="vm-do")))
        self.assertIn("compatible", dr.accepts(box(), box(version="9", compatible="onemind-vm-do")))
        self.assertIn("different CA", dr.accepts(box(), box(version="0.1.0-dev.8", ca_sha256="bb")))
        self.assertIn("needs at least", dr.accepts(box(), box(version="0.2.0", min_from_version="0.1.5")))

    def test_ca_fingerprint_is_the_der_hash_and_refuses_keys(self):
        self.assertEqual(len(dr.ca_fingerprint(pem(b"x"))), 64)
        self.assertNotEqual(dr.ca_fingerprint(pem(b"x")), dr.ca_fingerprint(pem(b"y")))
        for bad in ("junk", pem(b"x") + pem(b"y"), pem(b"x") + "-----BEGIN PRIVATE KEY-----\n"):
            with self.assertRaises(SystemExit):
                dr.ca_fingerprint(bad)

    def test_compat_record_for_the_installer_board(self):
        r = dr.compat_record("x86_64-efi", "o/onemind-x86_64-efi-0.1.0-dev.7.raucb",
                             "o/onemind-x86_64-efi-0.1.0-dev.7-next.raucb", pem(b"ca"))
        self.assertEqual((r["compatible"], r["version"], r["next_version"]), ("onemind-x86_64-efi", "0.1.0-dev.7", "0.1.0-dev.7-next"))
        self.assertEqual(r["installs"], [{"from": "0.1.0-dev.7", "to": "0.1.0-dev.7-next"}])
        self.assertEqual(r["signing"], "dev-throwaway")
        self.assertNotIn("PRIVATE", json.dumps(r))

    def test_a_next_bundle_of_another_build_is_refused(self):
        with self.assertRaises(SystemExit):
            dr.compat_record("x86_64-efi", "o/onemind-x86_64-efi-0.1.0-dev.7.raucb",
                             "o/onemind-x86_64-efi-0.1.0-dev.8-next.raucb", pem(b"ca"))

    def test_compatible_string_comes_from_the_board_file(self):
        self.assertEqual(dr.board_field("x86_64-efi", "compatible"), "onemind-x86_64-efi")
        self.assertEqual(dr.board_field("vm-do", "compatible"), read_board("vm-do")["compatible"])


def read_board(b):
    return yaml.safe_load(read("os", "boards", b, "board.yaml"))


class Selection(unittest.TestCase):
    """Bundle selection per board: each board's bundles and CA come only from that board's artifact folder."""

    def make(self, files):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        for folder, name in files:
            os.makedirs(os.path.join(t.name, folder), exist_ok=True)
            with open(os.path.join(t.name, folder, name), "w") as f:
                f.write(pem(folder.encode()) if name.endswith(".pem") else name)
        return t.name

    BASE = [("image-debian-arm64-efi", "onemind-arm64-efi-1.qcow2"), ("image-debian-vm-do", "onemind-vm-do-1.qcow2"),
            ("installer-debian-x86_64", "onemind-installer-amd64-1.img.xz")]
    DO = [("image-debian-vm-do", n) for n in ("onemind-vm-do-0.1.0-dev.1.raucb", "onemind-vm-do-0.1.0-dev.1-next.raucb", "dev-ca.cert.pem")]
    X86 = [("installer-debian-x86_64", n) for n in ("onemind-x86_64-efi-0.1.0-dev.1.raucb", "onemind-x86_64-efi-0.1.0-dev.1-next.raucb", "dev-ca.cert.pem")]

    def test_each_board_gets_its_own_bundles_and_ca(self):
        found = dr.pick(self.make(self.BASE + self.DO + self.X86))
        self.assertTrue(found["update-bundle"].endswith("image-debian-vm-do/onemind-vm-do-0.1.0-dev.1.raucb"))
        self.assertTrue(found["update-next-x86_64-efi"].endswith("installer-debian-x86_64/onemind-x86_64-efi-0.1.0-dev.1-next.raucb"))
        self.assertIn("installer-debian-x86_64", found["dev-ca-x86_64-efi"])
        self.assertIn("image-debian-vm-do", found["dev-ca"])

    def test_installer_bundles_missing_publishes_nothing(self):
        with self.assertRaises(SystemExit):
            dr.pick(self.make(self.BASE + self.DO))

    def test_the_x86_64_efi_image_artifact_does_not_stand_in(self):
        # image.yml's matrix job also builds an x86_64-efi image, but with a different throwaway CA than the stick's.
        d = self.make(self.BASE + self.DO + [("image-debian-x86_64-efi", n) for n in
                      ("onemind-x86_64-efi-0.1.0-dev.1.raucb", "onemind-x86_64-efi-0.1.0-dev.1-next.raucb", "dev-ca.cert.pem")])
        with self.assertRaises(SystemExit):
            dr.pick(d)

    def test_release_writes_compat_with_the_installer_ca_under_its_own_name(self):
        dl = self.make(self.BASE + self.DO + self.X86)
        out = os.path.join(dl, "..", "rel-" + os.path.basename(dl))
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "scripts", "release", "dev-release.py"),
                            "--dl", dl, "--out", out, "--sha", "abcdef1", "--date", "20261121"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.load(open(os.path.join(out, "update-compat-x86_64-efi.json")))
        self.assertEqual(rec["ca_sha256"], dr.ca_fingerprint(read_pem(dl, "installer-debian-x86_64")))
        self.assertNotEqual(rec["ca_sha256"], json.load(open(os.path.join(out, "update-compat-vm-do.json")))["ca_sha256"])
        self.assertEqual(open(os.path.join(out, "dev-ca-x86_64-efi.cert.pem")).read(), read_pem(dl, "installer-debian-x86_64"))
        self.assertIn("update-compat-x86_64-efi.json", open(os.path.join(out, "SHA256SUMS")).read())


def read_pem(dl, folder):
    return open(os.path.join(dl, folder, "dev-ca.cert.pem")).read()


class Wiring(unittest.TestCase):
    def test_installer_job_keeps_the_bundles_of_the_stick_image(self):
        text = read(".github", "workflows", "image.yml")
        step = text[text.index("Keep the update bundles and the dev CA"):]
        step = step[:step.index("- name: Summary")]
        self.assertIn("out/image-x86_64-efi/onemind-x86_64-efi-*.raucb", step)
        self.assertIn("out/image-x86_64-efi/dev-ca.cert.pem", step)
        self.assertIn("out/installer-x86_64/", step)
        self.assertNotRegex(step, r"\.key\b|signer\.")

    def test_battery_covers_the_image_the_installer_writes(self):
        target = read_board("installer-x86_64")["target_board"]
        wf = yaml.safe_load(read(".github", "workflows", "image.yml"))
        rows = [m for j in wf["jobs"].values() for m in j.get("strategy", {}).get("matrix", {}).get("include", []) if "upto" in m]
        self.assertTrue(any(m["board"] == target and m["upto"] == "T5" for m in rows), (target, rows))

    def test_the_channel_already_signs_the_installer_target_with_release_keys(self):
        self.assertIn(read_board("installer-x86_64")["target_board"], json.loads(read("os", "update", "channel.json"))["boards"])
        sec = read(".github", "workflows", "security-nightly.yml")
        self.assertIn("secrets.ONEMIND_RAUC_SIGNING_KEY", sec)

    def test_dev_release_never_reads_a_key_or_signs(self):
        src = read("scripts", "release", "dev-release.py")
        self.assertNotRegex(src, r"subprocess|openssl|signer|\.key['\"]")

    def test_the_doc_states_ceremony_day_and_the_battery_rows(self):
        doc = read("os", "boards", "installer-x86_64", "UPDATES.md")
        for needle in ("root.json", "ONEMIND_RAUC_SIGNING_KEY", "T2", "T5", "I1-I5", "NOT done yet"):
            self.assertIn(needle, doc)


if __name__ == "__main__":
    unittest.main()
