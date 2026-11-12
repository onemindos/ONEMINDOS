# SPDX-License-Identifier: Apache-2.0
"""os/ patches from the other streams, applied by the image line (HANDOFF B2): brand, k3s hardening,
NATS TLS unit, and the rule that no TUF root or signing key is committed (founder item F-27)."""
import os, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "os", "assemble"))
import assemble  # noqa: E402

BRAND = os.path.join(ROOT, "brand", "generated", "os")
DEBIAN_OSR = 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nNAME="Debian GNU/Linux"\nVERSION_ID="13"\nID=debian\nHOME_URL="https://www.debian.org/"\nONEMIND_VERSION="x"\n'


def rd(*p):
    return open(os.path.join(ROOT, *p)).read()


class Brand(unittest.TestCase):
    def test_os_release_keeps_debian_ids_and_takes_brand_names(self):
        out = assemble.brand_os_release(DEBIAN_OSR, open(os.path.join(BRAND, "os-release")).read())
        self.assertIn('NAME="OneMind OS"', out)
        self.assertIn("ID=debian", out)
        self.assertIn('VERSION_ID="13"', out)
        self.assertNotIn("Debian GNU/Linux", out)
        self.assertNotIn("debian.org", out)
        self.assertEqual(out.count("NAME="), 2)          # NAME and PRETTY_NAME, nothing doubled
        self.assertIn('ONEMIND_VERSION="x"', out)

    def test_apply_brand_writes_os_release_and_motd(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "usr/lib")); os.makedirs(os.path.join(t, "etc"))
            open(os.path.join(t, "usr/lib/os-release"), "w").write(DEBIAN_OSR)
            assemble.apply_brand(t)
            self.assertIn("OneMind OS", open(os.path.join(t, "etc/motd")).read())
            out = open(os.path.join(t, "usr/lib/os-release")).read()
            self.assertIn('PRETTY_NAME="OneMind OS"', out)
            self.assertIn('ONEMIND_VERSION="x"', out)      # the health gate reads this; losing it broke T1 in CI
            self.assertIn("ID=debian", out)

    def test_no_generated_files_changes_nothing(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as empty:
            os.makedirs(os.path.join(t, "usr/lib"))
            open(os.path.join(t, "usr/lib/os-release"), "w").write(DEBIAN_OSR)
            assemble.apply_brand(t, empty)
            self.assertEqual(open(os.path.join(t, "usr/lib/os-release")).read(), DEBIAN_OSR)
            self.assertEqual(assemble.brand_grub(empty), "")

    def test_grub_gets_colours_only(self):
        g = assemble.brand_grub()
        self.assertIn("set color_highlight=", g)
        self.assertNotIn("#", g)
        self.assertIn("@BRAND@", rd("os", "assemble", "grub.cfg.in"))


class K3s(unittest.TestCase):
    def test_service_has_secrets_encryption_and_psa(self):
        u = rd("os", "rootfs", "layers", "base", "usr", "lib", "systemd", "system", "k3s.service")
        self.assertIn("--secrets-encryption", u)
        self.assertIn("admission-control-config-file=/etc/rancher/k3s/psa.yaml", u)

    def test_image_psa_is_the_deploy_psa(self):
        self.assertEqual(rd("os", "rootfs", "layers", "base", "etc", "rancher", "k3s", "psa.yaml"), rd("deploy", "k8s", "psa.yaml"))


class NatsUnit(unittest.TestCase):
    def test_tls_files_reach_the_throwaway_user_without_credentials_glob(self):
        u = rd("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-nats.service")
        self.assertIn("RuntimeDirectory=onemind-nats", u)
        self.assertIn("$$f", u)          # systemd would expand a bare $f
        self.assertIn("%%u", u)          # and a bare %u is a specifier


class NoSigningMaterial(unittest.TestCase):
    """F-27: signing keys and the TUF root are the founder's; the repo ships only the documented place."""
    def test_no_tuf_root_or_private_key_committed_under_os(self):
        files = subprocess.run(["git", "ls-files", "os"], cwd=ROOT, capture_output=True, text=True).stdout.split()
        self.assertEqual([f for f in files if os.path.basename(f) == "root.json"], [])
        for f in files:
            if f.endswith((".pem", ".key")):
                self.assertNotIn("PRIVATE KEY", rd(f), f)

    def test_placeholder_location_is_documented(self):
        self.assertIn("root.json", rd("os", "rootfs", "layers", "base", "usr", "lib", "onemind", "tuf", "README.md"))


if __name__ == "__main__":
    unittest.main()
