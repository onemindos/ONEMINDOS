# SPDX-License-Identifier: Apache-2.0
"""LT-DO-01 kit checks: firewall rules, hub role, no tokens. Run: python3 -I -m unittest discover -s lab-kits/LT-DO-01/tests"""
import os, re, subprocess, unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
REPO = KIT.parent.parent
CLOSED = ("4222", "6443", "10250", "8472")
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DRY_RUN": "1"}

def sh(script, *args, env=None):
    return subprocess.run(["sh", str(KIT / script), *args], capture_output=True, text=True, env=env or ENV)

class Firewall(unittest.TestCase):
    def test_only_ssh_and_gateway_from_one_ip(self):
        r = sh("do-firewall.sh", "203.0.113.7")
        self.assertEqual(r.returncode, 0, r.stderr)
        m = re.search(r'--inbound-rules (.*?) --outbound-rules', r.stdout.replace("\n", " "))
        rules = m.group(1).split()
        self.assertEqual(sorted(rules), sorted([
            "protocol:tcp,ports:22,address:203.0.113.7/32",
            "protocol:tcp,ports:8080,address:203.0.113.7/32"]))
        for p in CLOSED:
            self.assertNotIn(p, m.group(1))

    def test_tag_bound_and_created_first(self):
        out = sh("do-firewall.sh", "203.0.113.7").stdout
        self.assertLess(out.index("tag create"), out.index("firewall create"))
        self.assertIn("--tag-names onemind-lt-do-01", out)

    def test_rejects_open_or_bad_addresses(self):
        for bad in ("0.0.0.0", "0.0.0.0/0", "203.0.113.0/24", "256.1.1.1", "example.com", "::1"):
            self.assertNotEqual(sh("do-firewall.sh", bad).returncode, 0, bad)

    def test_requires_token_when_live(self):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        r = sh("do-firewall.sh", "203.0.113.7", env=env)
        self.assertNotEqual(r.returncode, 0)

class Droplet(unittest.TestCase):
    def test_dry_run_uses_hub_user_data_and_tag(self):
        r = sh("do-create-droplet.sh", "12345", "aa:bb:cc")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("user-data.hub.yaml", r.stdout)
        self.assertIn("--tag-name onemind-lt-do-01", r.stdout)

    def test_refuses_user_data_without_hub_role(self):
        p = KIT / "tests" / "_nohub.yaml"
        p.write_text("#cloud-config\nonemind:\n  role: worker\n")
        try:
            env = dict(ENV, USERDATA=str(p))
            self.assertNotEqual(sh("do-create-droplet.sh", "1", "k", env=env).returncode, 0)
        finally:
            p.unlink()

class Hygiene(unittest.TestCase):
    def test_no_tokens_in_kit(self):
        for f in KIT.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                t = f.read_text(errors="ignore")
                self.assertIsNone(re.search(r"dop_v1_[0-9a-f]{20}", t), f)
                self.assertIsNone(re.search(r"DIGITALOCEAN_ACCESS_TOKEN=['\"]?[A-Za-z0-9]{10}", t), f)

    def test_readme_names_closed_ports_and_scripts(self):
        t = (KIT / "README.md").read_text()
        for p in CLOSED:
            self.assertIn(p, t)
        self.assertIn("do-firewall.sh", t)

if __name__ == "__main__":
    unittest.main()
