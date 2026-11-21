# SPDX-License-Identifier: Apache-2.0
"""CORE-UPDATE-9 (#278): the rescue console is installed and started on real boxes.

Covers deploy/install.sh (hub), the image's unit and onemind-firstboot (hub role). The
live answers (401 on 127.0.0.1:7443, 200 with k3s stopped) need a booted box; see the PR.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
import onemind_firstboot as fb  # noqa: E402

INSTALL = open(os.path.join(ROOT, "deploy", "install.sh")).read()
DEPLOY_UNIT = open(os.path.join(ROOT, "deploy", "systemd", "onemind-rescue.service")).read()
IMAGE_UNIT = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                               "onemind-rescue.service")).read()


def keys(unit, *names):
    return [l for l in unit.splitlines() if l.split("=", 1)[0] in names]


class InstallSh(unittest.TestCase):
    def test_hub_installs_rescue_after_certs_and_tokens(self):
        hub = INSTALL[INSTALL.index("if [ \"$ROLE\" = hub ]; then\n  k3s_binary"):]
        order = [hub.index(n) for n in ("box_certs", "gateway_tokens", "rescue_install", "gateway_service")]
        self.assertEqual(order, sorted(order), "rescue_install must come after the CA pair and the tokens file")

    def test_rescue_install_enables_the_unit_and_checks_401(self):
        body = INSTALL[INSTALL.index("rescue_install() {"):INSTALL.index("# Before printing new tokens")]
        self.assertIn("systemctl enable onemind-rescue", body)
        self.assertIn("install -m0644 \"$SCRIPT_DIR/systemd/onemind-rescue.service\"", body)
        self.assertIn("https://127.0.0.1:7443/", body)
        self.assertIn('"$code" = 401', body)

    def test_summary_prints_rescue_url_and_uninstall_removes_unit(self):
        self.assertIn("https://$BOX.local:7443", INSTALL[INSTALL.index("hub ready:"):])
        self.assertRegex(INSTALL, r'local units="[^"]*\bonemind-rescue\b')

    def test_bash_syntax(self):
        r = subprocess.run(["bash", "-n", os.path.join(ROOT, "deploy", "install.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class Units(unittest.TestCase):
    def test_image_unit_reads_data_paths_and_runs_usr_bin(self):
        self.assertIn("ExecStart=/usr/bin/onemindd rescue", IMAGE_UNIT)
        self.assertIn("Environment=ONEMIND_TOKENS_FILE=/data/onemind/gateway/tokens.yaml", IMAGE_UNIT)
        self.assertIn("Environment=ONEMIND_NET_TLS_DIR=/data/onemind/tls", IMAGE_UNIT)
        self.assertIn("ConditionPathExists=/data/onemind/tls/https.crt", IMAGE_UNIT)
        self.assertIn("WantedBy=multi-user.target", IMAGE_UNIT)

    def test_both_units_keep_the_same_sandbox(self):
        names = ("User", "NoNewPrivileges", "CapabilityBoundingSet", "AmbientCapabilities", "ProtectSystem",
                 "SystemCallFilter", "RestrictAddressFamilies", "MemoryDenyWriteExecute", "UMask")
        self.assertEqual(keys(DEPLOY_UNIT, *names), keys(IMAGE_UNIT, *names))

    def test_root_can_read_the_gateway_users_files(self):
        # https.key and tokens.yaml belong to `onemind` (0600/0640); an empty bounding set would make
        # root unable to read them and the console would never start.
        for u in (DEPLOY_UNIT, IMAGE_UNIT):
            self.assertIn("CapabilityBoundingSet=CAP_DAC_READ_SEARCH", u)
            self.assertNotRegex(u, r"CAP_(DAC_OVERRIDE|SYS_ADMIN|CHOWN|NET_ADMIN)")


class FirstBoot(unittest.TestCase):
    def test_hub_starts_the_console_and_other_roles_do_not(self):
        self.assertIn("onemind-rescue.service", fb.ROLE_UNITS["hub"])
        self.assertNotIn("onemind-rescue.service", fb.ROLE_UNITS["worker"] + fb.ROLE_UNITS["leaf"])

    @unittest.skipUnless(shutil.which("openssl"), "openssl missing")
    def test_cert_is_signed_by_the_box_ca_private_and_kept(self):
        with tempfile.TemporaryDirectory() as d:
            p = fb.Paths(d)
            fb.make_ca(p, "box")             # IMG-MESH-01: the box CA lives in the gateway tls dir
            self.assertEqual(fb.issue_rescue_cert(p, "box"), "created")
            crt, key = (os.path.join(p.rescue_tls, f) for f in ("https.crt", "https.key"))
            self.assertEqual(os.stat(key).st_mode & 0o777, 0o600)
            r = subprocess.run(["openssl", "verify", "-CAfile", os.path.join(p.identity, "ca.pem"), crt],
                               capture_output=True, text=True)
            self.assertIn("OK", r.stdout)
            txt = subprocess.run(["openssl", "x509", "-in", crt, "-noout", "-ext", "subjectAltName"],
                                 capture_output=True, text=True).stdout
            for n in ("DNS:box.local", "DNS:onemind.local"):
                self.assertIn(n, txt)
            # Outside the box CA's name constraints: asking for them would void the whole certificate.
            for n in ("IP Address:127.0.0.1", "DNS:localhost", "DNS:box,"):
                self.assertNotIn(n, txt + ",")
            self.assertEqual(sorted(os.listdir(p.rescue_tls)), ["https.crt", "https.key"])
            with open(crt) as fh:
                before = fh.read()
            self.assertEqual(fb.issue_rescue_cert(p, "box"), "kept")
            with open(crt) as fh:
                self.assertEqual(fh.read(), before)

    @unittest.skipUnless(shutil.which("openssl"), "openssl missing")
    def test_a_box_set_up_before_the_mesh_signs_with_its_identity_ca(self):
        # A hub configured before IMG-MESH-01 keeps its CA in identity/ (ca.key, ca.pem); after an update
        # the rescue pair must still be made, signed by that CA.
        with tempfile.TemporaryDirectory() as d:
            p = fb.Paths(d)
            os.makedirs(p.identity)
            key, pem = os.path.join(p.identity, "ca.key"), os.path.join(p.identity, "ca.pem")
            subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:P-256",
                            "-nodes", "-subj", "/CN=old box CA", "-days", "30", "-keyout", key, "-out", pem],
                           check=True, capture_output=True)
            self.assertFalse(os.path.exists(os.path.join(p.tls, "ca.key")))
            self.assertEqual(fb.issue_rescue_cert(p, "box"), "created")
            r = subprocess.run(["openssl", "verify", "-CAfile", pem, os.path.join(p.rescue_tls, "https.crt")],
                               capture_output=True, text=True)
            self.assertIn("OK", r.stdout)

    def test_starting_a_hub_makes_the_pair_first_and_failure_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            p = fb.Paths(d)
            seen = []
            with mock.patch.object(fb, "issue_rescue_cert", lambda *a: seen.append(a)), \
                 mock.patch.object(fb, "systemctl", lambda *a: seen.append(a)):
                fb.start_units(p, {"role": "hub", "mesh": 1})
            self.assertEqual(seen[0][0], p)
            self.assertIn("onemind-rescue.service", seen[-1])
            with mock.patch.object(fb, "issue_rescue_cert", side_effect=subprocess.CalledProcessError(1, "openssl")), \
                 mock.patch.object(fb, "systemctl", lambda *a: seen.append(a)):
                fb.start_units(p, {"role": "hub", "mesh": 1})      # must not raise


class BatteryF10(unittest.TestCase):
    """The first-boot battery proves the live answers (CRITERIA-FIRSTBOOT.md section 6); here, only that it is
    pre-registered, hash-recorded and wired in. The QEMU run itself is CI's `image` and `battery` workflows."""
    QEMU = os.path.join(ROOT, "test", "qemu")
    FB = open(os.path.join(QEMU, "firstboot.py")).read()

    def test_criteria_hash_is_the_last_recorded_for_the_file(self):
        import hashlib
        crit = open(os.path.join(self.QEMU, "CRITERIA-FIRSTBOOT.md"), "rb").read()
        lines = [l.split() for l in open(os.path.join(self.QEMU, "PREREGISTRATION.sha256")) if "CRITERIA-FIRSTBOOT.md" in l]
        self.assertEqual(lines[-1][0], hashlib.sha256(crit).hexdigest(), "append the new hash when the criteria change")
        self.assertIn("| F10 |", crit.decode())

    def test_f10_runs_after_f9_with_k3s_stopped_and_judges_401_and_200(self):
        body = self.FB[self.FB.index("def f10("):self.FB.index("def main(")]
        for needle in ("systemctl stop k3s", "systemctl start k3s", ":7443", "Bearer", "/data/onemind/identity/ca.pem",
                       'g("NOAUTH") == "401"', 'g("WITH") == "200"', 'record("F10"'):
            self.assertIn(needle, body)
        main = self.FB[self.FB.index("def main("):]
        self.assertLess(main.index("f9(vm)"), main.index("f10(vm, token)"))
        self.assertLess(main.index("f10(vm, token)"), main.index('vm.mark("F3 reboot keeps state")'))


if __name__ == "__main__":
    unittest.main()
