# SPDX-License-Identifier: Apache-2.0
"""Host firewall (finish audit 07, item 2): default-deny input in host.nft, loaded by onemind-firewall.service.
Static checks always; the real port scan (test/net/host_firewall_scan.py) runs when this is root on Linux with nft."""
import os, re, shutil, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES = "os/rootfs/layers/onemind/usr/lib/onemind/host.nft"
UNIT = "os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-firewall.service"


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def lan_chain():
    return re.search(r"chain lan \{(.*?)\n  \}", rd(RULES), re.S).group(1)


class HostFirewall(unittest.TestCase):
    def test_input_is_default_deny(self):
        r = rd(RULES)
        self.assertRegex(r, r"hook input priority filter; policy drop;")
        self.assertNotIn("policy accept", r)

    def test_lan_chain_has_only_the_allowed_ports(self):
        self.assertEqual(re.findall(r"tcp dport \{ ([\d, ]+) \}", lan_chain()), ["443, 8443, 8444, 7443"])
        self.assertEqual(re.findall(r"udp dport \{ ([\d, ]+) \}", lan_chain()), ["5353, 3478, 41641"])

    def test_k3s_ports_are_never_open_to_the_lan(self):
        for port in ("6443", "10250", "8472"):
            self.assertNotIn(port, lan_chain())
        for line in rd(RULES).splitlines():
            if re.search(r"\b(6443|10250|8472)\b", line) and not line.lstrip().startswith("#"):
                self.assertRegex(line, r'iifname "(tailscale0|flannel\*|cni0)"', line)

    def test_unit_loads_before_network_and_is_enabled(self):
        u = rd(UNIT)
        self.assertIn("Before=network-pre.target", u)
        self.assertIn("DefaultDependencies=no", u)
        self.assertIn("ExecStart=/usr/sbin/nft -f /usr/lib/onemind/host.nft", u)
        self.assertIn("ExecStartPre=/usr/sbin/nft -c -f /usr/lib/onemind/host.nft", u)
        self.assertRegex(rd("os/rootfs/Containerfile"), r"systemctl enable onemind-firstboot\.service onemind-firewall\.service")

    @unittest.skipUnless(sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0
                         and shutil.which("nft") and shutil.which("ip"), "needs root, ip and nft on Linux")
    def test_port_scan_from_second_machine(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "test/net/host_firewall_scan.py")],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
