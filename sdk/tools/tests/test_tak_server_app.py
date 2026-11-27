# SPDX-License-Identifier: Apache-2.0
"""TAK Server app (#1268 review): config guard, no password refresh claim, disk requirement."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parents[3] / "apps" / "tak-server"
GUARD = APP / "build" / "onemind-tak-check-config.sh"

SAFE = """<Configuration>
  <network>
    <!-- <input _name="stdtcp" protocol="tcp" port="8087"/> -->
    <input _name="stdssl" protocol="tls" port="8089"/>
    <connector port="8443" _name="https" tls="true"/>
  </network>
</Configuration>
"""


@unittest.skipUnless(shutil.which("perl") and shutil.which("bash"), "needs perl and bash")
class ConfigGuard(unittest.TestCase):
    def run_guard(self, xml):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "CoreConfig.xml"
            p.write_text(xml)
            return subprocess.run(["bash", str(GUARD), str(p)], capture_output=True, text=True)

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


class Manifest(unittest.TestCase):
    def test_requires_disk_space(self):
        m = yaml.safe_load((APP / "onemind.app.yaml").read_text())
        self.assertEqual(m["spec"]["requires"]["storageFreeGb"], 40)

    def test_start_script_uses_guard_and_does_not_refresh_db_password(self):
        s = (APP / "build" / "onemind-tak-start.sh").read_text()
        self.assertIn("onemind-tak-check-config.sh", s)
        self.assertNotIn("is refreshed on every start", s)
        self.assertEqual(s.count("password=\\\""), 1, "db password is written once, at CoreConfig creation")

    def test_dockerfile_ships_guard(self):
        d = (APP / "build" / "Dockerfile").read_text()
        self.assertGreaterEqual(d.count("onemind-tak-check-config.sh"), 2)

    def test_readme_does_not_claim_db_rotation_works(self):
        self.assertNotIn("picked up at the next start", (APP / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
