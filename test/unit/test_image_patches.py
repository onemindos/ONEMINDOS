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


class CatalogSyncInertWithoutRoot(unittest.TestCase):
    """The signed catalog sync is shipped but inert: it needs the catalog channel's own TUF root and is never
    enabled by the image. Its gateway wiring points at the directory the sync writes."""
    def test_units_need_the_catalog_root_and_are_not_enabled(self):
        d = ("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system")
        svc, tm = rd(*d, "onemind-catalog.service"), rd(*d, "onemind-catalog.timer")
        self.assertIn("ConditionPathExists=/usr/lib/onemind/tuf/catalog/root.json", svc)
        self.assertIn("ExecStart=/usr/bin/onemind catalog sync", svc)
        self.assertIn("ReadWritePaths=/data/onemind/catalog", svc)
        # the dir must exist before the sandbox is built (226/NAMESPACE otherwise)
        self.assertIn("ExecStartPre=+/bin/mkdir -p /data/onemind/catalog", svc)
        self.assertNotIn("[Install]", svc + tm)
        self.assertIn("Unit=onemind-catalog.service", tm)

    def test_gateway_reads_what_the_sync_writes(self):
        self.assertIn("ONEMIND_CATALOG_DIR=/data/onemind/catalog",
                      rd("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind_firstboot.py"))
        self.assertIn('c.StateDir = "/data/onemind/catalog"', rd("internal", "update", "config.go"))
        self.assertIn("channel=catalog", rd("os", "rootfs", "layers", "base", "etc", "onemind", "catalog.conf"))


class BrandBootSplash(unittest.TestCase):
    """The brand Plymouth theme is in the image and its initramfs; the splash never touches the serial console."""
    def test_theme_is_installed_before_the_initramfs_is_built(self):
        cf = rd("os", "rootfs", "Containerfile")
        self.assertIn("COPY brand/generated/os/plymouth/onemind/ /usr/share/plymouth/themes/onemind/", cf)
        self.assertLess(cf.index("plymouth-set-default-theme onemind"), cf.index("update-initramfs -u"))
        # the initramfs hook needs the label plugin and fontconfig, or update-initramfs fails
        self.assertIn("\nplymouth plymouth-label fontconfig fonts-dejavu-core\n", rd("os", "rootfs", "packages", "debian-common.txt"))
        logo = re.search(r'ONEMIND_BRAND_BOOT_LOGO="([^"]+)"', rd("brand", "generated", "os", "brand.env")).group(1)
        for p in ("!brand/generated/os/", "!" + os.path.dirname(logo) + "/"):
            self.assertIn(p, rd(".dockerignore"))

    def test_logo_is_the_one_the_brand_names(self):
        env = rd("brand", "generated", "os", "brand.env")
        logo = re.search(r'ONEMIND_BRAND_BOOT_LOGO="([^"]+)"', env).group(1)
        self.assertIn(f"COPY {logo} /usr/share/plymouth/themes/onemind/logo.png", rd("os", "rootfs", "Containerfile"))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, *logo.split("/"))))
        self.assertIn("ImageDir=/usr/share/plymouth/themes/onemind", rd("brand", "generated", "os", "plymouth", "onemind", "onemind.plymouth"))

    def test_splash_is_the_atlas_boot_screen(self):
        """Design-v2 final screen 12 (#763): the colour mark on black, the wordmark, a thin bar, boot steps, footer."""
        script = rd("brand", "generated", "os", "plymouth", "onemind", "onemind.script")
        self.assertIn("on-dark", re.search(r'ONEMIND_BRAND_BOOT_LOGO="([^"]+)"', rd("brand", "generated", "os", "brand.env")).group(1))
        for hook in ("SetBootProgressFunction", "SetUpdateStatusFunction", "SetMessageFunction",
                     "SetDisplayPasswordFunction", "SetDisplayQuestionFunction", "SetDisplayNormalFunction"):
            self.assertIn(f"Plymouth.{hook}(", script)    # the disk's recovery-key prompt must be drawn
        self.assertIn('Image.Text("OneMind"', script)
        self.assertIn('Image("track.png")', script)
        self.assertIn('Image("fill.png")', script)
        # every boot step names a unit the image really ships
        units = re.findall(r'step\.unit\[\d\] = "([^"]+)"', script)
        self.assertEqual(len(units), 4)
        shipped = {os.path.basename(f) for d, _, fs in os.walk(os.path.join(ROOT, "os")) for f in fs
                   for f in [os.path.join(d, f)] if f.endswith(".service")}
        self.assertEqual([u for u in units if u not in shipped], [])
        self.assertNotIn("\\u", script)                  # glyphs are UTF-8, Plymouth strings have no \u escapes

    def test_progress_bar_is_not_the_logo_red(self):
        """The logo red (#FF333A) is reserved for the logo files; the bar uses the button red (DESIGN-GAP §6.4)."""
        import json, struct, zlib
        def colour(name):
            data = open(os.path.join(BRAND, "plymouth", "onemind", name), "rb").read()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            n = struct.unpack(">I", data[33:37])[0]
            self.assertEqual(data[37:41], b"IDAT")
            px = zlib.decompress(data[41:41 + n])
            return "#%02x%02x%02x" % tuple(px[1:4])
        b = json.loads(rd("brand", "brand.json"))
        self.assertEqual(colour("fill.png"), b["os"]["boot"]["progress"].lower())
        self.assertEqual(colour("track.png"), b["os"]["boot"]["track"].lower())
        self.assertNotEqual(colour("fill.png"), b["colors"]["red"]["hex"].lower())

    def test_kernel_command_line_splash_keeps_serial_output(self):
        g = rd("os", "assemble", "grub.cfg.in")
        line = re.search(r'^CMDLINE="([^"]+)"', g, re.M).group(1)
        self.assertIn("splash", line.split())
        self.assertIn("plymouth.ignore-serial-consoles", line.split())
        self.assertNotIn("quiet", line.split())        # the battery reads the serial console


class NightlyBattery(unittest.TestCase):
    """#226: the nightly T6/T7 markers, vm-do's GRUB-RAUC line and the Ubuntu hedge build."""
    def test_bad_image_markers_bypass_the_splash(self):
        # plymouth holds /dev/console while a bad slot's PID 1 runs; the kernel log reaches the
        # serial port. Level <2> stays under the loglevel=4 on the kernel command line.
        loglevel = int(re.search(r"\bloglevel=(\d)", rd("os", "assemble", "grub.cfg.in")).group(1))
        for name, mark in (("bad-boot-init", "BAD-BOOT: broken init exiting"),
                           ("bad-hang-init", "BAD-HANG: arming watchdog")):
            src = rd("test", "qemu", name)
            self.assertIn(mark, rd("test", "qemu", "run-tests.py"))
            m = re.search(r'echo "<(\d)>[^"]*' if name == "bad-boot-init" else r'echo "<(\d)>\$\*" > /dev/kmsg', src)
            self.assertIsNotNone(m, name)
            self.assertLess(int(m.group(1)), loglevel, name)
            self.assertIn("/dev/kmsg", src)
        self.assertIn('"$SRC/test/qemu/bad-boot-init" "$T/sbin/init"', rd("test", "qemu", "mkfixtures.sh"))

    def test_bios_grub_also_writes_to_serial(self):
        g = rd("os", "assemble", "grub.cfg.in")
        block = g[g.index('if [ "$grub_platform" = "pc" ]'):]
        block = block[:block.index("\nfi\n")]
        self.assertIn("serial --unit=0 --speed=115200", block)
        self.assertIn("terminal_output console serial", block)
        self.assertLess(g.index('if [ "$grub_platform" = "pc" ]'), g.index('echo "GRUB-RAUC:'))

    def test_build_base_configures_apt_for_its_own_leg(self):
        cf = rd("os", "rootfs", "Containerfile")
        stage = cf[cf.index("AS onemind-buildbase"):cf.index("AS onemind-fetch")]
        self.assertIn("ARG LEG=", stage)
        self.assertIn('onemind-configure-apt "$LEG" "$SNAPSHOT"', stage)
        self.assertNotIn("onemind-configure-apt debian", stage)


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

    def test_sdk_src_reaches_the_dashboard_stage(self):
        cf = rd("os", "rootfs", "Containerfile")
        stage = cf[cf.index("AS onemind-dashboard"):cf.index("AS onemind-pyprep")]
        self.assertIn("COPY sdk/ts/ /src/sdk/ts/", stage)
        self.assertLess(stage.index("COPY sdk/ts/"), stage.index("npm run build"))
        self.assertIn("!sdk/ts/", rd(".dockerignore"))
        self.assertIn("../sdk/ts/src", rd("dashboard", "tsconfig.json"))
        # CI-16: schema.ts is not committed, so the stage generates it from the spec before the build.
        self.assertIn("COPY sdk/openapi/ /src/sdk/openapi/", stage)
        self.assertLess(stage.index("gen-code.sh ts"), stage.index("npm run build"))

    def test_go_stage_generates_the_sdk_types_before_building(self):
        cf = rd("os", "rootfs", "Containerfile")
        stage = cf[cf.index("AS onemind-go"):cf.index("AS onemind-dashboard")]
        self.assertIn("COPY sdk/openapi/ sdk/openapi/", stage)
        self.assertLess(stage.index("gen-code.sh go"), stage.index("go build"))
        for path in ("!sdk/openapi/", "!sdk/scripts/"):
            self.assertIn(path, rd(".dockerignore"))


class NatsUnit(unittest.TestCase):
    def test_tls_files_reach_the_throwaway_user_without_credentials_glob(self):
        u = rd("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-nats.service")
        self.assertIn("RuntimeDirectory=onemind-nats", u)
        # The copy is a script (onemind-nats-files), so no shell variable or specifier sits in an Exec line,
        # where systemd would expand a bare $f or %u itself.
        self.assertIn("ExecStartPre=+/usr/lib/onemind/onemind-nats-files", u)
        for line in u.splitlines():
            if line.startswith("Exec"):
                self.assertNotRegex(line.replace("$MAINPID", ""), r"(?<!\$)\$(?!\$)|(?<!%)%(?!%)", line)
        script = rd("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "onemind-nats-files")
        self.assertIn("/data/onemind/gateway/tls/$f", script)


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
