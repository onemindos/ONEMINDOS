# SPDX-License-Identifier: Apache-2.0
"""TAK Server app (#1268 review): config guard, password persistence, disk requirement."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

import yaml

APP = Path(__file__).resolve().parents[3] / "apps" / "tak-server"
BUILD = APP / "build"
GUARD = BUILD / "onemind-tak-check-config.sh"
START = BUILD / "onemind-tak-start.sh"
CONFIG_NS = "http://bbn.com/marti/xml/config"

SAFE = f"""<Configuration xmlns="{CONFIG_NS}">
  <network>
    <!-- <input _name="stdtcp" protocol="tcp" port="8087"/> -->
    <input _name="stdssl" protocol="tls" port="8089"/>
    <connector port="8443" _name="https" tls="true"/>
  </network>
</Configuration>
"""


class ConfigGuard(unittest.TestCase):
    def run_guard(self, xml, *, parser_available=True):
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "CoreConfig.xml"
            if xml is not None:
                config.write_text(xml, encoding="utf-8")
            env = None if parser_available else {"PATH": d}
            return subprocess.run(
                ["/bin/bash", str(GUARD), str(config)],
                env=env, capture_output=True, text=True, timeout=10,
            )

    def test_default_tls_config_passes_even_with_commented_plain_input(self):
        r = self.run_guard(SAFE)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_active_plain_inputs_are_refused(self):
        for proto in ("quic", "tcp", "udp", "stcp"):
            with self.subTest(proto=proto):
                r = self.run_guard(SAFE.replace("</network>", f'<input _name="x" protocol="{proto}" port="1"/></network>'))
                self.assertEqual(r.returncode, 1)
                self.assertIn("refusing to start", r.stderr)

    def test_tls_false_is_refused(self):
        for tag in ("input", "connector"):
            with self.subTest(tag=tag):
                r = self.run_guard(SAFE.replace("</network>", f'<{tag} _name="x" tls="false"/></network>'))
                self.assertEqual(r.returncode, 1)

    def test_multiline_comment_is_ignored(self):
        xml = SAFE.replace("<network>", '<network><!--\n<input protocol="quic" port="1"/>\n-->')
        self.assertEqual(self.run_guard(xml).returncode, 0)

    def test_xml_formatting_does_not_change_listener_policy(self):
        for xml in (
            SAFE.replace('protocol="tls"', "protocol = 'tcp'"),
            SAFE.replace('protocol="tls"', '\n      protocol =\n      "udp"'),
            SAFE.replace('protocol="tls"', 'protocol="t&#99;p"'),
            SAFE.replace('tls="true"', 'tls=" 0 "'),
            f'<tak:Configuration xmlns:tak="{CONFIG_NS}"><tak:network>'
            '<tak:input _name="stream" protocol="stcp" port="8087"/>'
            '</tak:network></tak:Configuration>',
        ):
            with self.subTest(xml=xml):
                r = self.run_guard(xml)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("refusing to start", r.stderr)

    def test_datafeed_input_requires_tls(self):
        xml = SAFE.replace(
            '    <connector',
            '    <datafeed _name="feed" protocol="tcp" port="8087">'
            '<uuid>fixture</uuid><type>other</type><sync>false</sync></datafeed>\n'
            '    <connector',
        )
        r = self.run_guard(xml)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("refusing to start", r.stderr)

    def test_validation_errors_are_refused(self):
        for xml in (
            None,
            SAFE.removesuffix("</Configuration>\n"),
            SAFE.replace("<network>", "<unrecognized>").replace("</network>", "</unrecognized>"),
            SAFE.replace(f'xmlns="{CONFIG_NS}"', 'xmlns="urn:unrecognized"'),
            '<!DOCTYPE Configuration>\n' + SAFE,
            SAFE.replace('tls="true"', 'tls="invalid"'),
            SAFE.replace('protocol="tls"', 'protocol="invalid"'),
        ):
            with self.subTest(xml=xml):
                r = self.run_guard(xml)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("refusing to start", r.stderr)

    def test_missing_xml_parser_is_refused(self):
        r = self.run_guard(SAFE, parser_available=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("python3", r.stderr)


class Startup(unittest.TestCase):
    def test_saved_password_survives_restart_with_changed_secret(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tak = root / "tak"
            tak.mkdir()
            (tak / "CoreConfig.example.xml").write_text(
                SAFE.replace(
                    "</Configuration>",
                    '<repository><connection url="jdbc:postgresql://tak-database:5432/cot" '
                    'username="martiuser" password="template"/></repository>\n</Configuration>',
                ),
                encoding="utf-8",
            )
            certs = root / "data" / "certs" / "files"
            certs.mkdir(parents=True)
            (certs / "ca.pem").touch()
            bin_dir = root / "bin"
            bin_dir.mkdir()
            shutil.copy2(GUARD, bin_dir)

            # Stop at schema upgrade, after the real entrypoint has rendered and checked CoreConfig.
            java = bin_dir / "java"
            java.write_text('#!/bin/bash\nprintf "%s\\n" "$*"\nexit 42\n', encoding="utf-8")
            java.chmod(0o755)
            start = root / START.name
            start.write_text(
                START.read_text(encoding="utf-8")
                .replace("/opt/tak", "./tak")
                .replace("/data/", "./data/")
                .replace(f"/usr/local/bin/{GUARD.name}", f"./bin/{GUARD.name}"),
                encoding="utf-8",
            )
            config = root / "data" / "config" / "CoreConfig.xml"
            original_password = 'fixture-first&"|'
            env = {
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "TAK_CERT_PASSWORD": "fixture-cert",
            }
            for password in (original_password, "fixture-after-restart"):
                with self.subTest(input_password=password):
                    run = subprocess.run(
                        ["/bin/bash", str(start)], cwd=root,
                        env={**env, "TAK_DB_PASSWORD": password},
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(run.returncode, 42, run.stderr)
                    self.assertEqual(run.stdout.strip(), "-jar db-utils/SchemaManager.jar upgrade")
                    connection = ElementTree.parse(config).find(
                        "c:repository/c:connection", {"c": CONFIG_NS},
                    )
                    self.assertIsNotNone(connection)
                    self.assertEqual(connection.get("password"), original_password)


class Manifest(unittest.TestCase):
    def test_requires_disk_space(self):
        m = yaml.safe_load((APP / "onemind.app.yaml").read_text())
        self.assertEqual(m["spec"]["requires"]["storageFreeGb"], 40)

    def test_start_script_uses_guard_and_does_not_refresh_db_password(self):
        s = START.read_text()
        self.assertIn("onemind-tak-check-config.sh", s)
        self.assertNotIn("is refreshed on every start", s)

    def test_dockerfile_ships_guard(self):
        d = (BUILD / "Dockerfile").read_text()
        self.assertGreaterEqual(d.count("onemind-tak-check-config.sh"), 2)
        runtime = d.rsplit("\nFROM ", 1)[-1].replace("\\\n", "")
        self.assertRegex(runtime, r"apt-get install -y --no-install-recommends[^\n]*\bpython3\b")

    def test_readme_does_not_claim_db_rotation_works(self):
        self.assertNotIn("picked up at the next start", (APP / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
