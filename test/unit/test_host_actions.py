# SPDX-License-Identifier: Apache-2.0
"""#146 / #142: the host action service (onemindd host serve) ships in the image and runs on hubs only.

The service itself is tested in Go (internal/host); this pins how the image starts it.
"""
import os, re, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
import onemind_firstboot as fb  # noqa: E402

UNIT = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                         "onemind-host.service")).read()
CONTAINERFILE = open(os.path.join(ROOT, "os", "rootfs", "Containerfile")).read()


class HostService(unittest.TestCase):
    def test_hub_starts_it_and_other_roles_do_not(self):
        # Only the hub runs the gateway that approves actions; a worker has nothing to call it.
        for units in (fb.ROLE_UNITS, fb.LEGACY_ROLE_UNITS):
            self.assertIn("onemind-host.service", units["hub"])
            self.assertNotIn("onemind-host.service", units["worker"] + units["leaf"])

    def test_not_enabled_in_the_image(self):
        # Like every role unit it starts from onemind-firstboot once the box has a role, never at build time.
        for line in re.findall(r"systemctl enable [^;]*", CONTAINERFILE):
            self.assertNotIn("onemind-host", line)

    def test_waits_for_first_boot_and_the_data_partition(self):
        self.assertIn("ConditionPathExists=/data/onemind/firstboot/state.json", UNIT)
        self.assertIn("RequiresMountsFor=/data", UNIT)
        self.assertRegex(UNIT, r"(?m)^After=.*onemind-firstboot\.service")

    def test_systemd_makes_the_socket(self):
        # The service's filter forbids chown, so systemd owns the socket's group and mode.
        sock = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                                 "onemind-host.socket")).read()
        for line in ("ListenStream=/run/onemind/host.sock", "SocketGroup=onemind", "SocketMode=0660"):
            self.assertIn(line, sock)
        self.assertIn("Requires=onemind-host.socket", UNIT)
        self.assertNotIn("CAP_CHOWN", UNIT)

    def test_the_gateway_can_reach_the_socket_folder(self):
        # DirectoryMode= only applies when systemd creates /run/onemind; first boot may make it earlier.
        sock = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                                 "onemind-host.socket")).read()
        self.assertIn("ExecStartPre=/bin/sh -c 'mkdir -p /run/onemind && chmod go+x /run/onemind'", sock)
        src = open(os.path.join(LIB, "onemind_firstboot.py")).read()
        self.assertNotRegex(src, r"makedirs\(p\.run, mode=0o700")
        with tempfile.TemporaryDirectory() as d:
            p = fb.Paths(d)
            os.makedirs(p.run, mode=0o700)
            os.chmod(p.run, 0o700)              # what an older first boot left
            fb.run_dir(p)
            self.assertEqual(os.stat(p.run).st_mode & 0o777, 0o711)
            fb.write(os.path.join(p.run, "owner-token"), "x\n")
            self.assertEqual(os.stat(os.path.join(p.run, "owner-token")).st_mode & 0o777, 0o600)

    def test_never_installs_with_rauc_directly(self):
        # An OS install goes through the update engine (snapshot + health gate), never a raw rauc call.
        self.assertNotIn("rauc install", UNIT)
        go = open(os.path.join(ROOT, "internal", "host", "update.go")).read()
        self.assertNotRegex(go, r'"rauc"|rauc install"')


if __name__ == "__main__":
    unittest.main()
