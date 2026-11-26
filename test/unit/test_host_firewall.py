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

    def test_setup_wizard_port_is_opened_only_by_the_wizard_unit_and_only_from_the_lan(self):
        r = rd(RULES)
        self.assertIn("jump setup", lan_chain())
        self.assertRegex(r, r"chain setup \{\s*\}")          # empty in the ruleset: closed by default
        self.assertNotRegex(lan_chain(), r"\b8080\b")
        u = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-setup.service")
        self.assertIn("nft add rule inet onemind_host setup tcp dport 8080 accept", u)
        self.assertIn("ExecStopPost=-+/usr/sbin/nft flush chain inet onemind_host setup", u)   # "+": the web part is unprivileged (#578)
        self.assertIn("wizard-local-only", u)
        self.assertIn("After=onemind-firewall.service", u)

    def test_samba_port_is_opened_only_by_the_samba_unit_and_only_from_the_lan(self):
        # D-017: 445/tcp from the LAN ranges while onemind-smb runs (it runs only while a share is approved), never
        # from a public address, closed in the shipped ruleset. The namespace scan proves the same with real packets.
        r = rd(RULES)
        self.assertIn("jump samba", lan_chain())
        self.assertRegex(r, r"chain samba \{\s*\}")          # empty in the ruleset: closed by default
        for line in r.splitlines():
            if re.search(r"\b445\b", line):
                self.assertTrue(line.lstrip().startswith("#"), line)   # no rule in host.nft names 445
        self.assertNotIn("jump samba", re.search(r"chain input \{(.*?)\n  \}", r, re.S).group(1))
        u = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-smb.service")
        self.assertIn("ExecStartPre=-+/usr/sbin/nft add rule inet onemind_host samba tcp dport 445 accept", u)
        self.assertIn("ExecStartPre=-+/usr/sbin/nft flush chain inet onemind_host samba", u)
        self.assertIn("ExecStopPost=-+/usr/sbin/nft flush chain inet onemind_host samba", u)
        self.assertIn("ConditionPathExists=/data/onemind/samba/smb.conf", u)   # off while no share is approved
        self.assertRegex(u, r"(?m)^After=.*\bonemind-firewall\.service\b")
        self.assertIn("PartOf=onemind-firewall.service", u)
        # smbd's own sandbox has no CAP_NET_ADMIN: every nft line must run outside it ("+"), or the rule never lands.
        for line in re.findall(r"(?m)^Exec\w+=.*nft .*$", u):
            self.assertRegex(line, r"^Exec\w+=-?\+/usr/sbin/nft ", line)
        for b in ("cloud", "vm-do"):   # a cloud box never offers SMB to the internet
            self.assertNotRegex(rd(f"os/boards/{b}/rootfs/etc/onemind/host.d/10-cloud.nft"), r"\b445\b")

    def test_ssh_port_is_opened_only_by_sshd_and_only_from_the_lan_and_the_mesh(self):
        # Owner shell (Step 2): 22/tcp while sshd runs (it starts only once an owner key exists), never public.
        r = rd(RULES)
        self.assertIn("jump ssh", lan_chain())
        self.assertIn('iifname "tailscale0" jump ssh', r)
        self.assertRegex(r, r"chain ssh \{\s*\}")             # empty in the ruleset: closed by default
        for line in r.splitlines():
            if re.search(r"\b22\b", line):
                self.assertTrue(line.lstrip().startswith("#"), line)   # no rule in host.nft names 22
        self.assertNotIn("jump ssh", re.search(r"chain input \{(.*?)\n  \}", r, re.S).group(1).replace('iifname "tailscale0" jump ssh', ""))
        d = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/ssh.service.d/30-onemind-firewall.conf")
        self.assertIn("nft add rule inet onemind_host ssh tcp dport 22 accept", d)
        self.assertIn("ExecStopPost=-+/usr/sbin/nft flush chain inet onemind_host ssh", d)
        self.assertIn("PartOf=onemind-firewall.service", d)

    def test_cloud_boards_open_ssh_and_https_and_keep_the_wizard_local(self):
        for b in ("cloud", "vm-do"):
            d = f"os/boards/{b}/rootfs/etc/onemind"
            rules = [l for l in rd(f"{d}/host.d/10-cloud.nft").splitlines() if l.strip() and not l.startswith("#")]
            self.assertEqual(rules, ["add rule inet onemind_host input tcp dport 22 jump ssh",
                                     "add rule inet onemind_host input tcp dport { 443, 8443 } accept",
                                     "add rule inet onemind_host input udp dport 41641 accept"])
            self.assertTrue(os.path.exists(os.path.join(ROOT, d, "wizard-local-only")))
        self.assertIn("/etc/onemind/host.d/*.nft", rd(UNIT))

    def test_qemu_test_overlay_allows_only_the_slirp_gateway_for_ssh_and_wizard_http(self):
        rules = [l for l in rd("test/qemu/overlay/etc/onemind/host.d/90-qemu-test.nft").splitlines()
                 if l.strip() and not l.startswith("#")]
        self.assertEqual(rules, ["add rule inet onemind_host input ip saddr 10.0.2.2 tcp dport { 22, 8080 } accept"])

    def test_firewall_criteria_are_preregistered(self):
        import hashlib
        h = hashlib.sha256(open(os.path.join(ROOT, "test/qemu/CRITERIA-FIREWALL.md"), "rb").read()).hexdigest()
        self.assertIn(f"{h}  CRITERIA-FIREWALL.md", rd("test/qemu/PREREGISTRATION.sha256"))

    @unittest.skipUnless(sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0
                         and shutil.which("nft") and shutil.which("ip"), "needs root, ip and nft on Linux")
    def test_port_scan_from_second_machine(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "test/net/host_firewall_scan.py")],
                           capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
