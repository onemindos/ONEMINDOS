# SPDX-License-Identifier: Apache-2.0
"""Static checks of the image's kernel and service hardening (no VM needed).

Covers: the sysctl baseline, the k3s protect-kernel-defaults pairing, the kernel command line (AppArmor is
named explicitly and enforced), the apparmor packages, and the sandbox drop-ins. The booted checks
(`aa-status`, `sysctl -n`) need the QEMU battery; this test keeps the files they read from drifting.
"""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, "os", "rootfs", "layers", "base")
ONE = os.path.join(ROOT, "os", "rootfs", "layers", "onemind")


def rd(*p):
    with open(os.path.join(*p)) as f:
        return f.read()


def sysctls(text):
    return dict(re.findall(r"(?m)^([a-z0-9_.]+) = (\S+)$", text))


class Sysctl(unittest.TestCase):
    def test_kspp_baseline_values(self):
        s = sysctls(rd(BASE, "etc/sysctl.d/91-onemind-hardening.conf"))
        for k, v in {"kernel.kptr_restrict": "2", "kernel.dmesg_restrict": "1", "kernel.unprivileged_bpf_disabled": "1",
                     "kernel.perf_event_paranoid": "3", "kernel.kexec_load_disabled": "1", "kernel.yama.ptrace_scope": "1",
                     "fs.protected_symlinks": "1", "fs.protected_hardlinks": "1", "fs.protected_fifos": "2",
                     "fs.protected_regular": "2", "net.ipv4.conf.all.accept_redirects": "0",
                     "net.ipv4.tcp_syncookies": "1", "net.core.bpf_jit_harden": "2"}.items():
            self.assertEqual(s.get(k), v, k)

    def test_rp_filter_is_loose_for_the_mesh(self):
        # strict (1) drops Tailscale and flannel replies that return on another interface
        s = sysctls(rd(BASE, "etc/sysctl.d/91-onemind-hardening.conf"))
        self.assertEqual(s["net.ipv4.conf.all.rp_filter"], "2")
        self.assertEqual(s["net.ipv4.conf.default.rp_filter"], "2")

    def test_no_file_sets_a_key_twice_to_different_values(self):
        seen = {}
        d = os.path.join(BASE, "etc/sysctl.d")
        for f in sorted(os.listdir(d)):
            for k, v in sysctls(rd(d, f)).items():
                self.assertEqual(seen.setdefault(k, (v, f))[0], v, "%s set differently in %s and %s" % (k, seen[k][1], f))

    def test_k3s_protect_kernel_defaults_is_paired_with_the_sysctls(self):
        self.assertRegex(rd(BASE, "etc/rancher/k3s/config.yaml.d/20-onemind-hardening.yaml"),
                         r"(?m)^protect-kernel-defaults: true$")
        s = sysctls(rd(BASE, "etc/sysctl.d/92-onemind-k3s.conf"))
        # the exact values the kubelet checks (https://docs.k3s.io/security/hardening-guide)
        self.assertEqual({k: s.get(k) for k in ("vm.panic_on_oom", "vm.overcommit_memory", "kernel.panic", "kernel.panic_on_oops")},
                         {"vm.panic_on_oom": "0", "vm.overcommit_memory": "1", "kernel.panic": "10", "kernel.panic_on_oops": "1"})
        self.assertEqual(s["kernel.keys.root_maxkeys"], "1000000")
        self.assertEqual(s["kernel.keys.root_maxbytes"], "25000000")


class CommandLine(unittest.TestCase):
    def cmdline(self):
        t = rd(ROOT, "os/assemble/grub.cfg.in")
        parts = re.findall(r'(?m)^CMDLINE="([^"]*)"$', t)
        self.assertGreaterEqual(len(parts), 2, "base and hardening CMDLINE lines")
        return " ".join(p.replace("$CMDLINE", "") for p in parts)

    def test_apparmor_is_named_and_the_hardening_flags_are_present(self):
        c = self.cmdline().split()
        for flag in ("apparmor=1", "security=apparmor", "slab_nomerge", "page_alloc.shuffle=1",
                     "randomize_kstack_offset=on", "debugfs=off", "panic=10", "ro"):
            self.assertIn(flag, c)

    def test_every_boot_entry_uses_the_variable(self):
        t = rd(ROOT, "os/assemble/grub.cfg.in")
        entries = re.findall(r"(?m)^\s+linux .*$", t)
        self.assertEqual(len(entries), 3)
        for e in entries:
            self.assertIn("$CMDLINE", e)

    def test_apparmor_userland_is_installed(self):
        pk = rd(ROOT, "os/rootfs/packages/debian-common.txt").split()
        self.assertIn("apparmor", pk)


class Sandboxes(unittest.TestCase):
    def dropin(self, layer, unit):
        return rd(layer, "usr/lib/systemd/system", unit + ".service.d", "20-onemind-hardening.conf")

    def test_tailscaled_keeps_only_network_capabilities(self):
        t = self.dropin(ONE, "tailscaled")
        self.assertRegex(t, r"CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW CAP_NET_BIND_SERVICE")
        self.assertNotIn("CAP_SYS_ADMIN", t)
        self.assertIn("NoNewPrivileges=yes", t)

    def test_local_api_is_not_root_and_loopback_only(self):
        t = self.dropin(BASE, "onemind-local-api")
        for want in ("DynamicUser=yes", "CapabilityBoundingSet=", "IPAddressAllow=localhost", "IPAddressDeny=any"):
            self.assertIn(want, t)

    def test_root_oneshots_cannot_touch_modules_clock_or_namespaces(self):
        for u in ("onemind-firstboot", "onemind-mesh-setup", "onemind-fabric-join"):
            t = self.dropin(ONE, u)
            for want in ("ProtectKernelModules=yes", "ProtectClock=yes", "RestrictNamespaces=yes", "ProtectKernelLogs=yes"):
                self.assertIn(want, t, u)


if __name__ == "__main__":
    unittest.main()
