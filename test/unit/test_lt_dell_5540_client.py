# SPDX-License-Identifier: Apache-2.0
"""LT-X86-05540 client kit (lab-kits/LT-X86-05540/client-probe.sh): snapshot sections, redaction,
compare and wan-watch transitions against stub rfkill/curl on PATH. Proves the kit, not the laptop."""
import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KIT = os.path.join(ROOT, "lab-kits", "LT-X86-05540", "client-probe.sh")
FAKE_IP = ".".join(["192", "168", "1", "50"])  # built here so the repo has no literal private address
RFKILL = "#!/bin/sh\necho '0: phy0: Wireless LAN'\necho '\tSoft blocked: '$(cat \"$STATE/wifi\")\n"
CURL = "#!/bin/sh\nn=$(cat \"$STATE/n\" 2>/dev/null || echo 0); echo $((n+1)) > \"$STATE/n\"\n" \
       "# polls 1-2 up, 3-4 down, then up\n[ \"$n\" -ge 2 ] && [ \"$n\" -lt 4 ] && exit 22\nexit 0\n"


class Probe(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.bin = os.path.join(self.d, "bin"); os.mkdir(self.bin)
        for name, body in (("rfkill", RFKILL), ("curl", CURL)):
            p = os.path.join(self.bin, name)
            with open(p, "w") as f: f.write(body)
            os.chmod(p, 0o755)
        self.env = dict(os.environ, PATH=self.bin + ":" + os.environ["PATH"], STATE=self.d, OUT=self.d,
                        HUB="https://" + FAKE_IP + ":8443", INTERVAL="0", COUNT="6")
        self.setwifi("no")

    def setwifi(self, v):
        with open(os.path.join(self.d, "wifi"), "w") as f: f.write(v)

    def run_kit(self, *args):
        return subprocess.run(["sh", KIT, *args], env=self.env, capture_output=True, text=True)

    def snap(self, label):
        r = self.run_kit("snapshot", label)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(os.path.join(self.d, f"snap-{label}.txt")) as f: return f.read()

    def test_snapshot_sections_and_redaction(self):
        t = self.snap("a")
        for s in ("== radios", "== audio", "== camera", "== displays", "== power", "== sleep", "== hub"):
            self.assertIn(s, t)
        self.assertIn("hub: UP", t)
        self.assertNotIn(FAKE_IP, t)

    def test_bad_label_refused(self):
        self.assertEqual(self.run_kit("snapshot", "../x").returncode, 2)

    def test_compare_detects_radio_change(self):
        self.snap("on"); self.setwifi("yes"); self.snap("off")
        out = self.run_kit("compare", "on", "off").stdout
        self.assertIn("-\tSoft blocked: no", out); self.assertIn("+\tSoft blocked: yes", out)

    def test_compare_no_change_ignores_uptime(self):
        self.snap("a"); self.snap("b")
        self.assertIn("NO CHANGE", self.run_kit("compare", "a", "b").stdout)

    def test_wan_watch_logs_transitions_only(self):
        out = self.run_kit("wan-watch").stdout.splitlines()
        self.assertEqual(out, ["t+0s hub UP", "t+0s hub DOWN", "t+0s hub UP"])

    def test_wan_watch_needs_hub(self):
        env = {k: v for k, v in self.env.items() if k != "HUB"}
        r = subprocess.run(["sh", KIT, "wan-watch"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
