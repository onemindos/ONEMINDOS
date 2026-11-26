# SPDX-License-Identifier: Apache-2.0
"""Step 2 PR 3: NetworkManager on the hardware boards, networkd everywhere else.

The booted proof is NW1-NW4 (first-boot battery) and FW5 (firewall battery), criteria in
test/qemu/CRITERIA-NETWORK.md; Wi-Fi association cannot be tested in QEMU. This pins what the build must contain
so a dropped package, a lost bind mount or a cloud board that drifted to NetworkManager fails without booting."""
import hashlib
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QEMU = os.path.join(ROOT, "test", "qemu")
LAYER = os.path.join("os", "rootfs", "layers", "networkmanager")
NM_BOARDS = ("x86_64-efi", "x86_64-efi-nvidia", "arm64-efi", "rpi5", "vm")
NETWORKD_BOARDS = ("cloud", "cloud-aws", "cloud-azure", "cloud-gcp", "cloud-hetzner", "cloud-proxmox", "vm-do", "installer-x86_64")


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


def keys(text):
    return {k: v for k, v in re.findall(r"^(\w+):\s*([^#\n]*?)\s*(?:#.*)?$", text, re.M)}


def ini(text):
    out, sec = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"\[(.+)\]$", line)
        if m:
            sec = m.group(1)
            out[sec] = {}
        elif sec and "=" in line:
            k, v = line.split("=", 1)
            out[sec][k] = v
    return out


class Boards(unittest.TestCase):
    def test_hardware_boards_opt_in(self):
        for b in NM_BOARDS:
            self.assertEqual(keys(read("os", "boards", b, "board.yaml")).get("network"), "networkmanager", b)

    def test_cloud_boards_installer_and_recovery_keep_networkd(self):
        for b in NETWORKD_BOARDS:
            if os.path.exists(os.path.join(ROOT, "os", "boards", b, "board.yaml")):
                self.assertNotIn("network", keys(read("os", "boards", b, "board.yaml")), b)
        self.assertIn("systemd-networkd", read("os", "boards", "installer-x86_64", "Containerfile"))
        target = read("os", "recovery", "onemind-recovery.target")
        wants = [l for l in target.splitlines() if l.startswith("Wants=")][0].split("=", 1)[1].split()
        self.assertIn("systemd-networkd.service", wants)
        self.assertNotIn("NetworkManager.service", wants)
        conflicts = [l for l in target.splitlines() if l.startswith("Conflicts=")][0].split("=", 1)[1].split()
        self.assertIn("NetworkManager.service", conflicts)

    def test_networkd_dhcp_file_stays_for_recovery_and_cloud(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, "os/rootfs/layers/base/usr/lib/systemd/network/50-onemind-dhcp.network")))


class Packages(unittest.TestCase):
    def test_package_list(self):
        words = re.sub(r"#.*", "", read("os", "rootfs", "packages", "networkmanager.txt")).split()
        self.assertEqual(sorted(words), sorted(["network-manager", "wpasupplicant", "wireless-regdb", "iw", "rfkill"]))

    def test_only_nm_boards_get_the_packages_and_layer(self):
        c = read("os", "rootfs", "Containerfile")
        self.assertEqual(c.count("^network:[[:space:]]*networkmanager"), 2)   # package list and layer/enable step
        self.assertIn("packages/networkmanager.txt", c)
        self.assertRegex(c, r"systemctl enable NetworkManager\.service NetworkManager-wait-online\.service systemd-resolved\.service")
        self.assertRegex(c, r"else systemctl enable systemd-networkd\.service systemd-resolved\.service")
        self.assertIn("grep -qx enabled", c)    # the build fails if networkd is also enabled on a NetworkManager board


class Config(unittest.TestCase):
    CONF = ini(read(LAYER, "etc", "NetworkManager", "conf.d", "10-onemind.conf"))

    def test_dns_goes_to_resolved(self):
        self.assertEqual(self.CONF["main"]["dns"], "systemd-resolved")
        self.assertEqual(self.CONF["main"]["plugins"], "keyfile")

    def test_networkmanager_never_sets_the_host_name(self):
        # P-05: the owner's name is put back at boot from /data; NetworkManager would reset it to the image's
        # static name (found when #1143 met the NetworkManager boards in the round-2 integration, F22).
        self.assertEqual(self.CONF["main"]["hostname-mode"], "none")

    def test_cluster_and_mesh_links_are_unmanaged_and_cover_what_the_firewall_names(self):
        un = self.CONF["keyfile"]["unmanaged-devices"].split(";")
        for want in ("flannel*", "cni0", "veth*", "tailscale0"):
            self.assertIn(f"interface-name:{want}", un)
        # Every internal interface the host firewall trusts is one NetworkManager must not configure.
        nft = read("os", "rootfs", "layers", "onemind", "usr", "lib", "onemind", "host.nft")
        for name in set(re.findall(r'iifname "([^"]+)"', nft)) - {"lo"}:
            self.assertIn(f"interface-name:{name}", un, f"firewall trusts {name} but NetworkManager would manage it")

    def test_dhcp_identity_does_not_depend_on_the_transient_machine_id(self):
        c = self.CONF["connection"]
        self.assertEqual(c["ipv4.dhcp-client-id"], "mac")
        self.assertEqual(c["ipv6.dhcp-duid"], "ll")
        self.assertEqual(c["ipv6.addr-gen-mode"], "eui64")

    def test_k3s_waits_for_wait_online_and_an_extra_nic_cannot_hold_it(self):
        k = ini(read(LAYER, "usr", "lib", "systemd", "system", "k3s.service.d", "30-onemind-networkmanager.conf"))["Unit"]
        self.assertEqual(k["After"], "NetworkManager-wait-online.service")
        self.assertEqual(k["Wants"], "NetworkManager-wait-online.service")
        text = read(LAYER, "usr", "lib", "systemd", "system", "NetworkManager-wait-online.service.d", "10-onemind.conf")
        exec_lines = [l for l in text.splitlines() if l.startswith("ExecStart=")]
        self.assertEqual(exec_lines, ["ExecStart=", "ExecStart=/usr/lib/onemind/nm-wait-online"])   # one connected NIC is enough
        script = read(LAYER, "usr", "lib", "onemind", "nm-wait-online")
        self.assertIn("connected:(ethernet|wifi|bond|bridge|vlan)", script)
        self.assertNotIn("nm-online", re.sub(r"#.*", "", script))
        self.assertTrue(os.access(os.path.join(ROOT, LAYER, "usr", "lib", "onemind", "nm-wait-online"), os.X_OK))
        self.assertRegex(text, r"NM_ONLINE_TIMEOUT=\d+")

    def test_profiles_and_state_live_on_data(self):
        tab = read(LAYER, "usr", "lib", "onemind", "fstab.networkmanager")
        base = read("os", "rootfs", "layers", "base", "etc", "fstab")
        binds = [l.split() for l in tab.splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual({b[1] for b in binds}, {"/etc/NetworkManager/system-connections", "/var/lib/NetworkManager"})
        layout = read(LAYER, "usr", "lib", "systemd", "system", "onemind-data-layout.service.d", "10-networkmanager.conf")
        for src, _dst, *_ in binds:
            self.assertTrue(src.startswith("/data/state/"))
            self.assertIn(src, layout, "bind source is created by onemind-data-layout")
            self.assertNotIn(src, base, "the base fstab must stay free of NetworkManager (cloud boards)")
        self.assertIn("chmod 0700 /data/state/etc-NetworkManager-system-connections", layout)   # Wi-Fi passwords
        unit = ini(read(LAYER, "usr", "lib", "systemd", "system", "NetworkManager.service.d", "10-onemind.conf"))["Unit"]
        self.assertEqual(set(unit["RequiresMountsFor"].split()), {b[1] for b in binds})


class Battery(unittest.TestCase):
    CRIT = read("test", "qemu", "CRITERIA-NETWORK.md")

    def test_criteria_hash_is_the_last_recorded_for_the_file(self):
        h = hashlib.sha256(self.CRIT.encode()).hexdigest()
        lines = [l.split() for l in read("test", "qemu", "PREREGISTRATION.sha256").splitlines() if "  CRITERIA-NETWORK.md  " in l]
        self.assertEqual(lines[-1][0], h, "append the new hash when the criteria change")
        for t in ("NW1", "NW2", "NW3", "NW4", "FW5"):
            self.assertIn(f"| {t} |", self.CRIT)

    def test_first_boot_runs_nw1_to_nw3_before_the_reboot_and_nw4_after_it(self):
        fb = read("test", "qemu", "firstboot.py")
        main = fb[fb.index("def main("):]
        self.assertLess(main.index("f12(vm, token)"), main.index("netcheck.nw1("))
        self.assertLess(main.index("netcheck.nw3("), main.index("netcheck.nw4_before("))
        self.assertLess(main.index("netcheck.nw4_before("), main.index('vm.mark("F3 reboot keeps state")'))
        self.assertLess(main.index('record("F3"'), main.index("netcheck.nw4_after(vm, record, nw4)"))

    def test_firewall_battery_judges_the_second_nic(self):
        self.assertIn("fb.netcheck.fw5(box, record)", read("test", "qemu", "firewall.py"))


class Verdicts(unittest.TestCase):
    """The verdict logic of netcheck.py against canned guest output, so a wrong parse fails here, not in CI."""
    spec = importlib.util.spec_from_file_location("netcheck", os.path.join(QEMU, "netcheck.py"))
    nc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nc)

    class VM:
        def __init__(self, *outs):
            self.outs, self.cmds = list(outs), []

        def run(self, cmd, timeout=0):
            self.cmds.append(cmd)
            return 0, self.outs.pop(0) if self.outs else ""

    def verdict(self, fn, *outs, **kw):
        got = []
        fn(self.VM(*outs), lambda t, ok, d: got.append((t, ok, d)), **kw)
        return got[-1]

    NW1_OK = ("STACK=networkmanager\nNMEN=enabled\nWOEN=enabled\nNDACT=inactive\nNMACT=active\nETH=enp0s3\nIP4=198.51.100.15/24\n"
              "METHOD=auto\nLEASE=1\nDNSCONF=1\nDNSMODE=systemd-resolved\nRESOLVED=active\nRESOLV=../run/systemd/resolve/stub-resolv.conf\n"
              "WPA=wpa_supplicant v2.10\nIW=iw version 6.9\nRFKILL=0\nREGDB=install ok installed\nREGDBFILE=/lib/firmware/regulatory.db\n")

    def test_nw1(self):
        self.assertTrue(self.verdict(self.nc.nw1, self.NW1_OK)[1])
        for bad in ("NDACT=inactive", "STACK=networkmanager", "IP4=198.51.100.15/24", "LEASE=1", "METHOD=auto", "DNSMODE=systemd-resolved"):
            key = bad.split("=")[0]
            worse = self.NW1_OK.replace(bad, key + "=" + {"NDACT": "active", "STACK": "networkd", "IP4": "", "LEASE": "0", "METHOD": "manual", "DNSMODE": "none"}[key])
            self.assertFalse(self.verdict(self.nc.nw1, worse)[1], key)

    def test_nw2_needs_the_order_not_just_a_late_k3s(self):
        ok = ("AFTER=network-online.target NetworkManager-wait-online.service\nWANTS=NetworkManager-wait-online.service\n"
              "NMSTART=3000000\nWOEND=9500000\nK3SFIRST=9.800000\n")
        self.assertTrue(self.verdict(self.nc.nw2, ok)[1])
        self.assertFalse(self.verdict(self.nc.nw2, ok.replace("K3SFIRST=9.800000", "K3SFIRST=5.000000"))[1])
        self.assertFalse(self.verdict(self.nc.nw2, ok.replace("NetworkManager-wait-online.service\nWANTS", "x\nWANTS"))[1])
        self.assertFalse(self.verdict(self.nc.nw2, ok.replace("WOEND=9500000", "WOEND=0"))[1])

    def test_nw3_names_all_four(self):
        out = ("MADE_CNI=1\nMADE_TS=0\nST_flannelnw0=10 (unmanaged)\nST_cni0=10 (unmanaged)\nST_vethnw0=10 (unmanaged)\n"
               "ST_tailscale0=10 (unmanaged)\nCONF=unmanaged-devices=interface-name:flannel*;interface-name:cni0;"
               "interface-name:veth*;interface-name:tailscale0\n")
        self.assertTrue(self.verdict(self.nc.nw3, out, "")[1])
        self.assertFalse(self.verdict(self.nc.nw3, out.replace("ST_cni0=10 (unmanaged)", "ST_cni0=30 (disconnected)"), "")[1])
        self.assertFalse(self.verdict(self.nc.nw3, out.replace("interface-name:veth*;", ""), "")[1])

    def test_nw4(self):
        before = {"add_rc": "0", "mode": "600", "sha": "a" * 64, "bind1": True, "bind2": True}
        out = ("NAMES=,Wired connection 1,onemind-nw-probe,\nSHA=" + "a" * 64 + "\nMODE=600\nUP=1\nDEL_RC=0\nLEFT=0\n")
        self.assertTrue(self.verdict(self.nc.nw4_after, out, before=before)[1])
        self.assertFalse(self.verdict(self.nc.nw4_after, out.replace("onemind-nw-probe", "x"), before=before)[1])
        self.assertFalse(self.verdict(self.nc.nw4_after, out.replace("a" * 64, "b" * 64), before=before)[1])
        self.assertFalse(self.verdict(self.nc.nw4_after, out, before=dict(before, bind2=False))[1])

    def test_nw4_before_reads_the_binds_on_ext4_and_on_btrfs(self):
        class VM:
            def __init__(self, out): self.out = out
            def run(self, cmd, timeout=0): return 0, self.out
        def out(droot, sub):
            return ("ADD_RC=0\nMODE=600\nSHA=" + "a" * 64 + f"\nMNT1=/dev/vda3[{sub}/state/etc-NetworkManager-system-connections]\n"
                    f"MNT2=/dev/vda3[{sub}/state/var-lib-NetworkManager]\nDROOT={droot}\n")
        ok = self.nc.nw4_before(VM(out("/", "")))
        self.assertTrue(ok["bind1"] and ok["bind2"])
        ok = self.nc.nw4_before(VM(out("/@", "/@")))
        self.assertTrue(ok["bind1"] and ok["bind2"])
        bad = self.nc.nw4_before(VM(out("/@", "")))          # a bind that does not start at /data's own root
        self.assertFalse(bad["bind1"] or bad["bind2"])

    def test_fw5_fails_when_the_second_nic_held_online_back(self):
        ok = "NMSTART=4000000\nWOEND=12000000\nK3SFIRST=12.5\nNICS=2\n"
        self.assertTrue(self.verdict(self.nc.fw5, ok)[1])
        self.assertFalse(self.verdict(self.nc.fw5, ok.replace("WOEND=12000000", "WOEND=52000000").replace("K3SFIRST=12.5", "K3SFIRST=52.5"))[1])
        self.assertFalse(self.verdict(self.nc.fw5, ok.replace("NICS=2", "NICS=1"))[1])


if __name__ == "__main__":
    unittest.main()
