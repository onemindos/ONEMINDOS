# SPDX-License-Identifier: Apache-2.0
"""P-09 part 1: the firewall view must work on a real box without giving the host service CAP_NET_ADMIN.

The kernel checks CAP_NET_ADMIN on every nf_tables netlink message, reads included, so `nft list ruleset` fails
under onemind-host.service (bounding set CAP_DAC_READ_SEARCH only). The capability lives in a one-shot reader
behind a root-only socket instead. These tests pin that split in the unit files, because the Go and Python unit
tests fake the nft run and cannot catch a unit that is missing the capability or has too much of it.
"""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYSD = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system")


def read(name):
    with open(os.path.join(SYSD, name)) as f:
        return f.read()


def setting(text, key):
    return re.findall(r"^%s=(.*)$" % key, text, re.M)


class FirewallReadUnits(unittest.TestCase):
    def test_the_host_service_still_cannot_change_the_network(self):
        caps = setting(read("onemind-host.service"), "CapabilityBoundingSet")
        self.assertEqual(caps, ["CAP_DAC_READ_SEARCH"], "do not add CAP_NET_ADMIN to the host service (part 2 writes will live here)")

    def test_the_reader_holds_exactly_cap_net_admin_and_can_only_print(self):
        u = read("onemind-firewall-read@.service")
        self.assertEqual(setting(u, "CapabilityBoundingSet"), ["CAP_NET_ADMIN"])
        self.assertEqual(setting(u, "ExecStart"), ["/usr/sbin/nft -j list ruleset"], "fixed arguments, nothing from the caller")
        self.assertEqual(setting(u, "StandardInput"), ["null"])
        self.assertEqual(setting(u, "StandardOutput"), ["socket"])
        self.assertEqual(setting(u, "ProtectSystem"), ["strict"])
        self.assertEqual(setting(u, "NoNewPrivileges"), ["yes"])
        self.assertEqual(setting(u, "RestrictAddressFamilies"), ["AF_NETLINK AF_UNIX"])
        self.assertFalse(setting(u, "ReadWritePaths"), "the reader writes nothing")

    def test_the_socket_is_root_only_and_one_connection_per_run(self):
        s = read("onemind-firewall-read.socket")
        self.assertEqual(setting(s, "ListenStream"), ["/run/onemind/firewall-read.sock"])
        self.assertEqual(setting(s, "SocketMode"), ["0600"])
        self.assertEqual(setting(s, "SocketUser"), ["root"])
        self.assertEqual(setting(s, "Accept"), ["yes"])

    def test_the_host_service_starts_the_socket_and_the_go_side_reads_the_same_path(self):
        self.assertIn("onemind-firewall-read.socket", " ".join(setting(read("onemind-host.service"), "Wants")))
        with open(os.path.join(ROOT, "cmd", "onemindd", "host.go")) as f:
            self.assertIn('"/run/onemind/firewall-read.sock"', f.read())


if __name__ == "__main__":
    unittest.main()
