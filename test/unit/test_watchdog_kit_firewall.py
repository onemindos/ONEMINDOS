# SPDX-License-Identifier: Apache-2.0
"""The hub watchdog's LAN push (#687) needs UDP 7481. The image firewall keeps it closed by default; the lab
kit opens it for the LAN only through a host.d drop-in. These checks keep both true."""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


class WatchdogFirewall(unittest.TestCase):
    def test_image_keeps_the_alert_port_closed_by_default(self):
        rules = [l for l in rd("os/rootfs/layers/onemind/usr/lib/onemind/host.nft").splitlines() if not l.lstrip().startswith("#")]
        self.assertFalse([l for l in rules if "7481" in l])

    def test_kit_opens_it_on_the_lan_chain_only(self):
        kit = rd("internal/watchdog/LAB-KIT.md")
        lines = re.findall(r"echo '(add rule inet onemind_host [^']*7481[^']*)'", kit)
        self.assertEqual(lines, ["add rule inet onemind_host lan udp dport 7481 accept"])
        self.assertIn("/etc/onemind/host.d/20-watchdog.nft", kit)
        self.assertIn("chain lan {", rd("os/rootfs/layers/onemind/usr/lib/onemind/host.nft"))
        self.assertIn("3 minutes", kit)

    def test_default_port_matches(self):
        self.assertIn("DefaultPort = 7481", re.sub(r"\s+", " ", rd("internal/watchdog/lan.go")).replace("DefaultPort  =", "DefaultPort ="))


if __name__ == "__main__":
    unittest.main()
