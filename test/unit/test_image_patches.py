# SPDX-License-Identifier: Apache-2.0
"""os/ patches from the other streams, applied by the image line (HANDOFF B2): brand, k3s hardening,
NATS TLS unit, and the rule that no TUF root or signing key is committed (founder item F-27)."""
import os, re, subprocess, sys, tempfile, unittest

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


class GatewaySandboxRules(unittest.TestCase):
    """core's kubernetes executor needs sdk/policy/app-objects.yaml at start; without it the gateway
    exits and every firstboot/installer/cloud battery sees healthz=000."""
    def test_rules_ship_in_the_image_and_the_build_context(self):
        self.assertIn("COPY sdk/policy/app-objects.yaml /usr/lib/onemind/sdk/policy/app-objects.yaml", rd("os", "rootfs", "Containerfile"))
        self.assertIn("!sdk/policy/", rd(".dockerignore"))
        self.assertIn("sdk/policy/app-objects.yaml", rd("os", "boards", "jetson-orin", "make-layer.sh"))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "sdk", "policy", "app-objects.yaml")))


class UpdaterInertWithoutRoot(unittest.TestCase):
    """The image ships the place for each channel's TUF root, never a root (F-27). Without one the update
    service does not start (and `onemindd update` refuses: internal/update TestNoRootRefusesEveryMode)."""
    def test_unit_needs_a_root_and_is_not_enabled(self):
        u = rd("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-update.service")
        self.assertIn("ConditionPathExistsGlob=/usr/lib/onemind/tuf/*/root.json", u)
        self.assertIn("ConditionPathExists=/etc/onemind/update.conf", u)
        self.assertNotIn("[Install]", u)          # never enabled by the image; first boot decides

    def test_place_is_documented_and_the_updater_reads_only_it(self):
        d = os.path.join(ROOT, "os", "rootfs", "layers", "base", "usr", "lib", "onemind", "tuf")
        self.assertEqual(sorted(os.listdir(d)), ["README.md"])      # the place, no root.json, no key
        self.assertIn('TUFRootDir:        "/usr/lib/onemind/tuf"', rd("internal", "update", "config.go"))
        self.assertIn('filepath.Join(c.TUFRootDir, c.Channel, "root.json")', rd("internal", "update", "tuf.go"))


class BrandBootSplash(unittest.TestCase):
    """The brand Plymouth theme is in the image and its initramfs; the splash never touches the serial console."""
    def test_theme_is_installed_before_the_initramfs_is_built(self):
        cf = rd("os", "rootfs", "Containerfile")
        self.assertIn("COPY brand/generated/os/plymouth/onemind/ /usr/share/plymouth/themes/onemind/", cf)
        self.assertLess(cf.index("plymouth-set-default-theme onemind"), cf.index("update-initramfs -u"))
        # the initramfs hook needs the label plugin and fontconfig, or update-initramfs fails
        self.assertIn("\nplymouth plymouth-label fontconfig fonts-dejavu-core\n", rd("os", "rootfs", "packages", "debian-common.txt"))
        for p in ("!brand/generated/os/", "!brand/logo/png/white/"):
            self.assertIn(p, rd(".dockerignore"))

    def test_logo_is_the_one_the_brand_names(self):
        env = rd("brand", "generated", "os", "brand.env")
        logo = re.search(r'ONEMIND_BRAND_BOOT_LOGO="([^"]+)"', env).group(1)
        self.assertIn(f"COPY {logo} /usr/share/plymouth/themes/onemind/logo.png", rd("os", "rootfs", "Containerfile"))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, *logo.split("/"))))
        self.assertIn("ImageDir=/usr/share/plymouth/themes/onemind", rd("brand", "generated", "os", "plymouth", "onemind", "onemind.plymouth"))

    def test_kernel_command_line_splash_keeps_serial_output(self):
        g = rd("os", "assemble", "grub.cfg.in")
        line = re.search(r'^CMDLINE="([^"]+)"', g, re.M).group(1)
        self.assertIn("splash", line.split())
        self.assertIn("plymouth.ignore-serial-consoles", line.split())
        self.assertNotIn("quiet", line.split())        # the battery reads the serial console


class DashboardUiSource(unittest.TestCase):
    """The dashboard imports @onemind/ui from source (../ui/src, see dashboard/vite.config.ts); the image's
    dashboard stage must have ui/src beside dashboard/ or `npm run build` fails with TS2307."""
    def test_ui_src_reaches_the_dashboard_stage(self):
        cf = rd("os", "rootfs", "Containerfile")
        stage = cf[cf.index("AS onemind-dashboard"):cf.index("AS onemind-pyprep")]
        self.assertIn("COPY ui/src/ /src/ui/src/", stage)
        self.assertLess(stage.index("COPY ui/src/"), stage.index("npm run build"))
        self.assertIn("!ui/src/", rd(".dockerignore"))
        self.assertIn("../ui/src", rd("dashboard", "tsconfig.json"))


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
