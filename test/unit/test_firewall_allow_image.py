# SPDX-License-Identifier: Apache-2.0
"""Owner allow rules (P-09 part 2) in the image: host.nft has two empty owner lists, reached only from the right place,
and the one unit that loads them holds nothing but CAP_NET_ADMIN. Static checks, no root needed."""
import hashlib, os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RULES = "os/rootfs/layers/onemind/usr/lib/onemind/host.nft"
UNIT = "os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-firewall-owner.service"
HOST_UNIT = "os/rootfs/layers/onemind/usr/lib/systemd/system/onemind-host.service"


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def chain(name):
    return re.search(rf"chain {name} \{{(.*?)\n  \}}", rd(RULES), re.S).group(1)


def code(text):
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


class OwnerLists(unittest.TestCase):
    def test_both_lists_exist_and_are_empty_in_the_shipped_ruleset(self):
        for name in ("owner_lan", "owner_mesh"):
            self.assertEqual(code(chain(name)).strip(), "", f"{name} must ship empty: the host service fills it")

    def test_the_lan_list_is_reached_only_from_the_lan_chain(self):
        self.assertIn("jump owner_lan", chain("lan"))
        self.assertNotIn("jump owner_lan", chain("input"))
        self.assertNotIn("owner_mesh", chain("lan"))

    def test_the_mesh_list_is_reached_only_for_the_mesh_interface(self):
        jumps = [l.strip() for l in chain("input").splitlines() if "owner_mesh" in l]
        self.assertEqual(jumps, ['iifname "tailscale0" jump owner_mesh'])

    def test_nothing_reaches_a_list_from_a_public_source(self):
        r = code(rd(RULES))
        self.assertEqual(len(re.findall(r"jump owner_", r)), 2)
        # the lan chain is itself reached only by the private-range jumps at the end of input
        self.assertRegex(chain("input"), r"ip saddr @lan4 jump lan")

    def test_the_rules_the_host_writes_have_no_way_to_name_an_address(self):
        go = rd("internal/firewall/allow.go")
        self.assertIn('"add rule inet %s %s %s dport %d accept comment', go)
        self.assertNotIn("saddr", go.split("func (a *Allower) script")[1].split("func (a *Allower) apply")[0])


class LoaderUnit(unittest.TestCase):
    def test_it_holds_only_net_admin_and_reads_one_file(self):
        u = rd(UNIT)
        self.assertIn("CapabilityBoundingSet=CAP_NET_ADMIN\n", u)
        self.assertIn("ExecStartPre=/usr/sbin/nft -c -f /data/onemind/firewall/live.nft", u)
        self.assertIn("ExecStart=/usr/sbin/nft -f /data/onemind/firewall/live.nft", u)
        self.assertIn("ReadOnlyPaths=/data", u)
        self.assertIn("IPAddressDeny=any", u)
        self.assertIn("RestrictAddressFamilies=AF_NETLINK AF_UNIX", u)
        self.assertIn("NoNewPrivileges=yes", u)
        self.assertNotIn("[Install]", u, "never enabled: it starts when the host service asks")

    def test_it_comes_back_after_a_firewall_restart_and_waits_for_the_data_disk(self):
        u = rd(UNIT)
        self.assertIn("PartOf=onemind-firewall.service", u)
        self.assertIn("After=onemind-firewall.service", u)
        self.assertIn("RequiresMountsFor=/data", u)
        self.assertIn("ConditionPathExists=/data/onemind/firewall/live.nft", u)

    def test_the_host_service_itself_gains_no_network_privilege(self):
        h = rd(HOST_UNIT)
        caps = [l for l in h.splitlines() if l.startswith("CapabilityBoundingSet=")]
        self.assertEqual(caps, ["CapabilityBoundingSet=CAP_DAC_READ_SEARCH"])

    def test_the_unit_is_in_the_services_registry(self):
        self.assertIn("unit: onemind-firewall-owner.service", rd("os/rootfs/layers/onemind/usr/lib/onemind/services.yaml"))


class QemuCheck(unittest.TestCase):
    def test_criteria_are_preregistered_and_the_battery_judges_fw6_to_fw8(self):
        h = hashlib.sha256(open(os.path.join(ROOT, "test/qemu/CRITERIA-FIREWALL-ALLOW.md"), "rb").read()).hexdigest()
        self.assertIn(f"{h}  CRITERIA-FIREWALL-ALLOW.md", rd("test/qemu/PREREGISTRATION.sha256"))
        fw = rd("test/qemu/firewall.py")
        for tid in ("FW6", "FW7", "FW8"):  # pre-registered as FW5-FW7; netcheck.py owns FW5
            self.assertIn(f'record("{tid}"', fw)
            self.assertIn(f"| {tid} |", rd("test/qemu/CRITERIA-FIREWALL-ALLOW.md"))

    def test_the_unconfirmed_rule_check_waits_past_the_deadline(self):
        fw = rd("test/qemu/firewall.py")
        self.assertIn("time.sleep(ALLOW_TTL_S + 10)", fw)
        self.assertIn('ca[0] == 404', fw)


if __name__ == "__main__":
    unittest.main()
