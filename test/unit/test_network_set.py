# SPDX-License-Identifier: Apache-2.0
"""P-08: a wired address change with an automatic rollback.

The booted proof is NS1-NS3 (first-boot battery), criteria in test/qemu/CRITERIA-NETWORK-SET.md. This pins what the
build must keep so a dropped wiring or a weakened unit fails without booting, and runs the verdict logic of
netset.py against canned guest output so a wrong parse fails here, not in CI."""
import hashlib
import importlib.util
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QEMU = os.path.join(ROOT, "test", "qemu")


def read(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return f.read()


class Wiring(unittest.TestCase):
    CRIT = read("test", "qemu", "CRITERIA-NETWORK-SET.md")

    def test_criteria_hash_is_the_last_recorded_for_the_file(self):
        h = hashlib.sha256(self.CRIT.encode()).hexdigest()
        lines = [l.split() for l in read("test", "qemu", "PREREGISTRATION.sha256").splitlines() if "  CRITERIA-NETWORK-SET.md  " in l]
        self.assertEqual(lines[-1][0], h, "append the new hash when the criteria change")
        for t in ("NS1", "NS2", "NS3"):
            self.assertIn(f"| {t} |", self.CRIT)

    def test_first_boot_runs_ns1_ns3_before_the_reboot_and_ns2_after_it(self):
        fb = read("test", "qemu", "firstboot.py")
        main = fb[fb.index("def main("):]
        self.assertLess(main.index("netcheck.nw4_before("), main.index("netset.ns3("))
        self.assertLess(main.index("netset.ns3("), main.index("netset.ns1("))
        self.assertLess(main.index("netset.ns1("), main.index("netset.ns2_before("))
        self.assertLess(main.index("netset.ns2_before("), main.index('vm.mark("F3 reboot keeps state")'))
        self.assertLess(main.index('record("F3"'), main.index("netset.ns2_after(vm, record, ns2)"))

    def test_the_host_service_starts_the_manager_and_recovers_before_listening(self):
        host = read("cmd", "onemindd", "host.go")
        self.assertRegex(host, r"\n\s*Net:\s+nm\}")  # the Net field is the netset manager (gofmt aligns it with the other fields)
        self.assertLess(host.index("nm.Recover(ctx)"), host.index("host.ActivationListener"))

    def test_the_host_unit_still_cannot_change_the_network_itself(self):
        unit = read("os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system", "onemind-host.service")
        caps = re.search(r"^CapabilityBoundingSet=(.*)$", unit, re.M).group(1)
        self.assertNotIn("CAP_NET_ADMIN", caps, "NetworkManager makes the change, over D-Bus; this process gets no network capability")
        self.assertIn("AF_UNIX", unit)

    def test_the_tools_the_host_calls_ship_in_the_image(self):
        pk = read("os", "rootfs", "packages", "networkmanager.txt")
        self.assertIn("network-manager", pk.split())  # nmcli; busctl is systemd's, in the base


class Verdicts(unittest.TestCase):
    spec = importlib.util.spec_from_file_location("netset", os.path.join(QEMU, "netset.py"))
    ns = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ns)

    class VM:
        def __init__(self, *outs):
            self.outs, self.cmds = list(outs), []

        def run(self, cmd, timeout=0):
            self.cmds.append(cmd)
            return 0, self.outs.pop(0) if self.outs else ""

    WHERE = "DEV=enp0s3\nCON=Wired connection 1\nA0=198.51.100.15/24\nADDRS=198.51.100.15/24,\nMETHOD=auto\n"

    def run_ns(self, fn, *outs, **kw):
        got = []
        vm = self.VM(*outs)
        fn(vm, lambda t, ok, d: got.append((t, ok, d)), **kw)
        return got[-1] if got else None, vm

    def test_ns1_needs_the_address_back_and_the_profile_auto(self):
        during = "PCODE=200\nAPPLIED=1\nOLDGONE=0\nPENDING=enp0s3\nADDRS=192.0.2.50/24,\nMETHOD=manual\n"
        after = "STATIC_LEFT=0\nADDRS=198.51.100.15/24,\nMETHOD=auto\nCONADDRS=\nPENDING=none\nLAST=rolled_back\n"
        got, vm = self.run_ns(self.ns.ns1, self.WHERE, during, after)
        self.assertTrue(got[1], got)
        self.assertIn("/v1/network/enp0s3", vm.cmds[1])
        self.assertIn('"rollback_seconds":20', vm.cmds[1])
        self.assertNotIn("confirm", vm.cmds[1], "NS1 never confirms")
        for bad_after in (after.replace("STATIC_LEFT=0", "STATIC_LEFT=1"), after.replace("METHOD=auto", "METHOD=manual"),
                          after.replace("ADDRS=198.51.100.15/24,", "ADDRS=198.51.100.99/24,"), after.replace("LAST=rolled_back", "LAST=confirmed"),
                          after.replace("PENDING=none", "PENDING=enp0s3"), after.replace("CONADDRS=", "CONADDRS=192.0.2.50/24")):
            self.assertFalse(self.run_ns(self.ns.ns1, self.WHERE, during, bad_after)[0][1], bad_after)
        self.assertFalse(self.run_ns(self.ns.ns1, self.WHERE, during.replace("PCODE=200", "PCODE=409"), after)[0][1])
        self.assertFalse(self.run_ns(self.ns.ns1, "DEV=\nCON=\nA0=\n")[0][1])

    def ns2(self, before=None, after=None):
        before = before or ("PCODE=200\nCCODE=200\nPENDING=none\nLAST=confirmed\nADDRS=198.51.100.15/24,\nMETHOD=manual\nDNS=192.0.2.53\nMODE=600\n"
                            "PENDING=none\nLAST=confirmed\n")
        after = after or ("DEV2=enp0s3\nADDRS=198.51.100.15/24,\nMETHOD=manual\nDNS=192.0.2.53\nPCODE=200\nCCODE=200\nBACKADDRS=198.51.100.15/24,\n"
                          "BACKMETHOD=auto\nBACKCONADDRS=\nBACKDNS=\nPENDING=none\nLAST=confirmed\n")
        vm = self.VM(self.WHERE, before, after)
        got = []
        st = self.ns.ns2_before(vm, lambda t, ok, d: got.append((t, ok, d)))
        self.assertIsNotNone(st)
        self.ns.ns2_after(vm, lambda t, ok, d: got.append((t, ok, d)), st)
        return got[-1], vm

    def test_ns2_uses_addr0_itself_and_judges_static_after_the_window_and_the_reboot(self):
        got, vm = self.ns2()
        self.assertTrue(got[1], got)
        self.assertIn('"address":"198.51.100.15/24","gateway":"198.51.100.2"', vm.cmds[1])
        self.assertIn("sleep 30", vm.cmds[1], "longer than the 20 s window")
        self.assertIn('"mode":"dhcp"', vm.cmds[2])
        base_before = ("PCODE=200\nCCODE=200\nPENDING=none\nLAST=confirmed\nADDRS=198.51.100.15/24,\nMETHOD=manual\nDNS=192.0.2.53\nMODE=600\n"
                       "PENDING=none\nLAST=confirmed\n")
        for worse in (base_before.replace("METHOD=manual", "METHOD=auto"), base_before.replace("MODE=600", "MODE=644"),
                      base_before.replace("DNS=192.0.2.53", "DNS="), base_before.replace("CCODE=200", "CCODE=409")):
            self.assertFalse(self.ns2(before=worse)[0][1], worse)
        good_after = ("DEV2=enp0s3\nADDRS=198.51.100.15/24,\nMETHOD=manual\nDNS=192.0.2.53\nPCODE=200\nCCODE=200\nBACKADDRS=198.51.100.15/24,\n"
                      "BACKMETHOD=auto\nBACKCONADDRS=\nBACKDNS=\nPENDING=none\nLAST=confirmed\n")
        for worse in (good_after.replace("ADDRS=198.51.100.15/24,\nMETHOD=manual", "ADDRS=198.51.100.15/24,\nMETHOD=auto"),
                      good_after.replace("DNS=192.0.2.53", "DNS="), good_after.replace("BACKDNS=", "BACKDNS=192.0.2.53"),
                      good_after.replace("BACKCONADDRS=", "BACKCONADDRS=198.51.100.15/24"), good_after.replace("BACKMETHOD=auto", "BACKMETHOD=manual"),
                      good_after.replace("BACKADDRS=198.51.100.15/24,", "BACKADDRS=")):
            self.assertFalse(self.ns2(after=worse)[0][1], worse)

    def test_ns3_every_refusal_is_4xx_and_changes_nothing(self):
        ok = ("ADDRS=198.51.100.15/24,\nMETHOD=auto\nR0CODE=409\nR1CODE=409\nR2CODE=409\nR3CODE=409\nR4CODE=409\nREASON=no_pending_change\n"
              "AFTER\nADDRS2=198.51.100.15/24,\nMETHOD2=auto\n")
        got, vm = self.run_ns(self.ns.ns3, self.WHERE, ok)
        self.assertTrue(got[1], got)
        self.assertIn("/v1/network/lo", vm.cmds[1])
        for bad in (ok.replace("R2CODE=409", "R2CODE=200"), ok.replace("ADDRS2=198.51.100.15/24,", "ADDRS2=192.0.2.50/24,"),
                    ok.replace("REASON=no_pending_change", "REASON=None"), ok.replace("METHOD2=auto", "METHOD2=manual")):
            self.assertFalse(self.run_ns(self.ns.ns3, self.WHERE, bad)[0][1], bad)

    def test_every_command_is_valid_shell_once_the_harness_appends_its_marker(self):
        """The first real run died of `; ;`: vm.run appends `; echo __RC=...`, so a command ending in `;` is a syntax error."""
        import subprocess
        vms = []
        for fn in (self.ns.ns1, self.ns.ns3):
            vm = self.VM(self.WHERE)
            fn(vm, lambda *a: None)
            vms.append(vm)
        vm = self.VM(self.WHERE)
        st = self.ns.ns2_before(vm, lambda *a: None)
        self.ns.ns2_after(vm, lambda *a: None, st)
        vms.append(vm)
        for vm in vms:
            for cmd in vm.cmds:
                r = subprocess.run(["bash", "-n", "-c", cmd + "; echo __RC=$?__"], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr + cmd[:120])


if __name__ == "__main__":
    unittest.main()
