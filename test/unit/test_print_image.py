# SPDX-License-Identifier: Apache-2.0
"""Printing (Step 3, claude/s3-printing): CUPS and ipp-usb ship in the image, locked down, with every file they write
on /data. The live proof is test/qemu (FP1-FP3 in firstboot.py, FWP1 in firewall.py); this pins how the image carries it:
the packages in both legs, no cups-browsed, the cupsd.conf defaults, the bind mounts and their seeding, the firewall
rule for 631 (LAN and mesh only), and that the criteria are pre-registered and wired into the harnesses."""
import hashlib
import os
from pathlib import Path
import re
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAYER = "os/rootfs/layers/onemind"


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def pkgs(leg):
    return re.sub(r"#.*", "", rd(f"os/rootfs/packages/{leg}-common.txt")).split()


CONF = rd(f"{LAYER}/usr/lib/onemind/cupsd.conf.onemind")
CONTAINERFILE = rd("os/rootfs/Containerfile")
FSTAB = rd("os/rootfs/layers/base/etc/fstab")
HOST = rd(f"{LAYER}/usr/lib/onemind/host.nft")
DROPIN = rd(f"{LAYER}/usr/lib/systemd/system/onemind-data-layout.service.d/print.conf")


def directives(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


class Packages(unittest.TestCase):
    NEEDED = ("cups", "cups-client", "cups-daemon", "cups-filters", "cups-ipp-utils", "ipp-usb")

    def test_in_both_legs(self):
        for leg in ("debian", "ubuntu"):
            for p in self.NEEDED:
                self.assertIn(p, pkgs(leg), f"{leg} lacks {p}")

    def test_no_browsed_anywhere(self):
        # cups-browsed makes a queue for every printer it sees: adding a printer is an owner action.
        for leg in ("debian", "ubuntu"):
            self.assertNotIn("cups-browsed", pkgs(leg))
        self.assertIn("cups-browsed must not be installed", CONTAINERFILE)

    def test_lists_stay_sorted_inside_the_new_line(self):
        line = [l for l in rd("os/rootfs/packages/debian-common.txt").splitlines() if l.startswith("cups ")][0].split()
        self.assertEqual(line, sorted(line))

    def test_package_generated_certificate_is_removed_in_the_install_layer(self):
        scrub = "os/rootfs/sources/strip-build-ssl-cert.sh"
        self.assertRegex(CONTAINERFILE, r"apt-get install -y \$\(cat /tmp/onemind/pkgs\); \\\n"
                         r"\s+sh /tmp/onemind/strip-build-ssl-cert\.sh /; \\")
        with tempfile.TemporaryDirectory() as tmp:
            ssl = Path(tmp) / "etc/ssl"
            certs = ssl / "certs"
            certs.mkdir(parents=True)
            (ssl / "private").mkdir()
            bad = certs / "ssl-cert-snakeoil.pem"
            key = ssl / "private/ssl-cert-snakeoil.key"
            alias = certs / "abcd1234.0"
            bad.touch()
            key.touch()
            alias.symlink_to(bad.name)
            good = certs / "other-ca.pem"
            good.touch()
            other = certs / "abcd1234.1"
            other.symlink_to(good.name)
            subprocess.run(["sh", os.path.join(ROOT, scrub), tmp], check=True)
            self.assertFalse(bad.exists())
            self.assertFalse(key.exists())
            self.assertFalse(alias.is_symlink())
            self.assertTrue(other.is_file())


class Boards(unittest.TestCase):
    """A cloud server has no printers and its private ranges are the provider's network: both cloud-family boards mask CUPS."""
    UNITS = ("cups.service", "cups.socket", "cups.path", "ipp-usb.service")

    def test_cloud_boards_mask_every_print_unit(self):
        for board in ("cloud", "vm-do"):
            s = rd(f"os/boards/{board}/post-install.sh")
            m = re.search(r"(?m)^systemctl mask (.+?) >/dev/null$", s)
            self.assertIsNotNone(m, board)
            self.assertEqual(sorted(m.group(1).split()), sorted(self.UNITS), board)
            self.assertIn("readlink /etc/systemd/system/$u", s)   # the build proves the mask is a link to /dev/null

    def test_masking_runs_after_the_units_are_enabled(self):
        # post-install.sh runs after the print RUN step that enables the units; masking first would fail the enable.
        self.assertLess(CONTAINERFILE.index("systemctl enable cups.service"), CONTAINERFILE.index("/tmp/onemind/board/post-install.sh"))

    def test_other_boards_do_not_mask(self):
        for board in sorted(os.listdir(os.path.join(ROOT, "os/boards"))):
            if board in ("cloud", "vm-do") or not os.path.isdir(os.path.join(ROOT, "os/boards", board)):
                continue
            p = os.path.join(ROOT, "os/boards", board, "post-install.sh")
            if os.path.exists(p):
                self.assertNotIn("cups", rd(os.path.relpath(p, ROOT)), board)


class Config(unittest.TestCase):
    def test_mesh_clients_are_allowed_on_root_but_never_on_admin(self):
        # CUPS's @LOCAL leaves out point-to-point interfaces; tailscale0 is one, so it is named.
        blocks = dict(re.findall(r"<Location (\S+)>(.*?)</Location>", CONF, re.S))
        self.assertIn("Allow @IF(tailscale0)", blocks["/"])
        for p in ("/admin", "/admin/conf", "/admin/log"):
            self.assertNotIn("@IF(", blocks[p], p)
            self.assertNotIn("@LOCAL", blocks[p], p)

    def test_off_by_default(self):
        d = directives(CONF)
        for want in ("Browsing No", "BrowseLocalProtocols none", "DefaultShared No", "WebInterface Yes", "IdleExitTimeout 0"):
            self.assertIn(want, d)
        self.assertNotIn("Browsing Yes", d)
        self.assertNotIn("DefaultShared Yes", d)

    def test_remote_admin_is_localhost_only(self):
        for loc in ("/admin", "/admin/conf", "/admin/log"):
            block = re.search(r"<Location %s>(.*?)</Location>" % re.escape(loc), CONF, re.S).group(1)
            self.assertIn("Require user @SYSTEM", block)
            self.assertIn("Allow localhost", block)
            self.assertNotIn("@LOCAL", block)
            self.assertNotRegex(block, r"Allow (all|\*)")

    def test_lan_can_read_ipp_but_the_root_location_names_no_public_allow(self):
        block = re.search(r"<Location />(.*?)</Location>", CONF, re.S).group(1)
        self.assertIn("Allow @LOCAL", block)
        self.assertNotRegex(block, r"Allow (all|\*)")

    def test_adding_a_printer_needs_an_administrator(self):
        pol = re.search(r"<Policy default>(.*)</Policy>", CONF, re.S).group(1)
        m = re.search(r"<Limit ([^>]*CUPS-Add-Modify-Printer[^>]*)>(.*?)</Limit>", pol, re.S)
        self.assertIn("CUPS-Delete-Printer", m.group(1))
        self.assertIn("Require user @SYSTEM", m.group(2))
        self.assertIn("AuthType Default", m.group(2))

    def test_listens_on_the_socket_and_631(self):
        d = directives(CONF)
        self.assertIn("Listen /run/cups/cups.sock", d)
        self.assertIn("Listen *:631", d)

    def test_only_local_gateway_identity_can_submit_or_release_jobs(self):
        policy = re.search(r"<Policy default>(.*?)</Policy>", CONF, re.S).group(1)
        limits = {op: directives(rule) for operations, rule in re.findall(r"<Limit ([^>]+)>(.*?)</Limit>", policy, re.S)
                  for op in operations.split()}
        self.assertEqual(limits.get("Get-Printer-Attributes"), ["Order deny,allow"])
        for op in ("Print-Job", "Create-Job", "Send-Document", "Release-Job"):
            with self.subTest(op=op):
                self.assertEqual(limits.get(op),
                                 ["AuthType Basic", "Require user onemind", "Order allow,deny", "Allow localhost"])
        for op in ("Print-URI", "Send-URI", "CUPS-Move-Job", "Hold-New-Jobs",
                   "Set-Job-Attributes", "Restart-Job", "CUPS-Authenticate-Job", "Release-Held-New-Jobs",
                   "CUPS-Create-Local-Printer", "All"):
            with self.subTest(op=op):
                self.assertEqual(limits.get(op, limits["All"]),
                                 ["AuthType Basic", "Require user onemind-print-disabled", "Order allow,deny", "Deny all"])


class State(unittest.TestCase):
    BINDS = {"etc-cups": "/etc/cups", "var-spool-cups": "/var/spool/cups", "var-cache-cups": "/var/cache/cups",
             "var-lib-ipp-usb": "/var/lib/ipp-usb"}

    def test_every_write_path_is_a_bind_from_data(self):
        for src, dst in self.BINDS.items():
            self.assertRegex(FSTAB, r"(?m)^/data/state/%s\s+%s\s+none bind,nofail,x-systemd\.requires=onemind-data-layout\.service 0 0$"
                             % (re.escape(src), re.escape(dst)))
            self.assertIn(f"/data/state/{src}", DROPIN)            # the source folder is made before the bind runs

    def test_boards_with_their_own_fstab_carry_the_same_binds(self):
        for f in ("os/boards/rpi5/rootfs/etc/fstab",):   # Jetson runs L4T with its own layer: out of scope
            for src, dst in self.BINDS.items():
                self.assertRegex(rd(f), r"(?m)^/data/state/%s\s+%s\s+none bind," % (re.escape(src), re.escape(dst)), f)

    def test_recovery_check_waits_for_the_new_mounts(self):
        after = re.search(r"(?m)^After=(.*)$", rd("os/recovery/onemind-data-check.service")).group(1).split()
        for m in ("etc-cups.mount", "var-spool-cups.mount", "var-cache-cups.mount", "var-lib-ipp\\x2dusb.mount"):
            self.assertIn(m, after)

    def test_mount_points_exist_in_the_image(self):
        # The build itself fails if a bind-mount point is missing from the built rootfs (a real check, not a text search).
        self.assertIn("test -d /etc/cups -a -d /var/spool/cups -a -d /var/cache/cups -a -d /var/lib/ipp-usb", CONTAINERFILE)
        self.assertIn("mkdir -p /usr/lib/onemind/cups-default /var/lib/ipp-usb", CONTAINERFILE)

    def test_etc_cups_is_seeded_once_and_never_overwritten(self):
        self.assertIn("[ -f /data/state/etc-cups/cupsd.conf ] || cp -a /usr/lib/onemind/cups-default/. /data/state/etc-cups/", DROPIN)
        self.assertIn("install -m 0640 -o root -g lp /usr/lib/onemind/cupsd.conf.onemind /etc/cups/cupsd.conf", CONTAINERFILE)
        self.assertIn("cp -a /etc/cups/. /usr/lib/onemind/cups-default/", CONTAINERFILE)
        self.assertLess(CONTAINERFILE.index("install -m 0640 -o root -g lp /usr/lib/onemind/cupsd.conf.onemind"),
                        CONTAINERFILE.index("cp -a /etc/cups/. /usr/lib/onemind/cups-default/"))   # the seed is OneMind's config

    def test_spool_and_cache_are_owned_for_cupsd(self):
        for needle in ("chown 0:7 /data/state/var-spool-cups /data/state/var-cache-cups", "chmod 0710 /data/state/var-spool-cups",
                       "chmod 0771 /data/state/var-cache-cups"):
            self.assertIn(needle, DROPIN)

    def test_log_folder_is_made_on_the_data_backed_var_log(self):
        self.assertIn("d /var/log/cups 0755 root lp -", rd(f"{LAYER}/usr/lib/tmpfiles.d/onemind-print.conf"))
        self.assertRegex(FSTAB, r"(?m)^/data/state/var-log\s+/var/log\s")

    def test_unit_waits_for_the_binds_and_is_enabled(self):
        u = rd(f"{LAYER}/usr/lib/systemd/system/cups.service.d/10-onemind.conf")
        self.assertRegex(u, r"(?m)^RequiresMountsFor=/data /etc/cups /var/spool/cups /var/cache/cups$")
        self.assertIn("systemctl enable cups.service cups.socket cups.path", CONTAINERFILE)

    def test_an_upgrade_installs_managed_policy_and_quarantines_old_jobs(self):
        helper = f"{LAYER}/usr/lib/onemind/onemind-print-policy.py"
        unit = rd(f"{LAYER}/usr/lib/systemd/system/cups.service.d/10-onemind.conf")
        self.assertIn("ExecStartPre=/usr/lib/onemind/gateway/venv/bin/python3 -I /usr/lib/onemind/onemind-print-policy.py ", unit)
        enforce = runpy.run_path(os.path.join(ROOT, helper))["enforce"]
        with tempfile.TemporaryDirectory() as tmp:
            cups = Path(tmp)
            seed = Path(ROOT, LAYER, "usr/lib/onemind/cupsd.conf.onemind")
            config = cups / "cupsd.conf"
            config.write_text("LogLevel info\nDefaultPolicy legacy\n<Policy legacy>\n"
                              "<Limit All>\nOrder deny,allow\n</Limit>\n</Policy>\n")
            printers = cups / "printers.conf"
            printers.write_text("Info Owner printer\n")
            spool = cups / "spool"
            spool.mkdir()
            job = spool / "c00001"
            payload = spool / "d00001-001"
            job.write_text("pre-upgrade job")
            payload.write_text("pre-upgrade payload")
            with patch("os.fchown"), patch("grp.getgrnam"):
                enforce(seed, config, spool)
                new_job = spool / "c00002"
                new_job.touch()
                enforce(seed, config, spool)
            self.assertTrue(new_job.is_file())
            self.assertEqual(printers.read_text(), "Info Owner printer\n")
            self.assertIn("LogLevel info", config.read_text())
            self.assertNotIn("legacy", config.read_text())
            self.assertIn("<Policy default>", config.read_text())
            self.assertFalse(job.exists())
            self.assertFalse(payload.exists())
            self.assertEqual((spool / ".pre-owner-release" / job.name).read_text(), "pre-upgrade job")
            self.assertEqual((spool / ".pre-owner-release" / payload.name).read_text(), "pre-upgrade payload")


class Firewall(unittest.TestCase):
    def lan(self):
        return re.search(r"chain lan \{(.*?)\n  \}", HOST, re.S).group(1)

    def test_631_is_open_from_the_lan_and_the_mesh_only(self):
        self.assertIn("tcp dport 631 accept", self.lan())
        self.assertIn('iifname "tailscale0" tcp dport 631 accept', HOST)
        inp = re.search(r"chain input \{(.*?)\n  \}", HOST, re.S).group(1)
        for line in inp.splitlines():
            if re.search(r"\b631\b", line):
                self.assertRegex(line, r'iifname "tailscale0"')   # the input chain names 631 only for the mesh interface
        for p in ("os/boards/cloud/rootfs/etc/onemind/host.d/10-cloud.nft", "os/boards/vm-do/rootfs/etc/onemind/host.d/10-cloud.nft"):
            self.assertNotRegex(rd(p), r"\b631\b")             # a cloud box never offers printing to the internet


class Wired(unittest.TestCase):
    QEMU = "test/qemu"

    def test_criteria_are_preregistered(self):
        reg = rd(f"{self.QEMU}/PREREGISTRATION.sha256")
        for f in ("CRITERIA-FIRSTBOOT.md", "CRITERIA-FIREWALL.md"):
            with open(os.path.join(ROOT, self.QEMU, f), "rb") as fh:
                h = hashlib.sha256(fh.read()).hexdigest()
            self.assertIn(f"{h}  {f}", reg)
        self.assertIn("| FP1 |", rd(f"{self.QEMU}/CRITERIA-FIRSTBOOT.md"))
        self.assertIn("| FWP1 |", rd(f"{self.QEMU}/CRITERIA-FIREWALL.md"))

    def test_firstboot_runs_the_proof_three_times(self):
        fb = rd(f"{self.QEMU}/firstboot.py")
        main = fb[fb.index("def main("):]
        for tid, mode in (("FP1", "baseline"), ("FP2", "again"), ("FP3", "again")):
            self.assertIn(f'printing(vm, "{tid}", "{mode}")', main)
        self.assertLess(main.index('printing(vm, "FP1"'), main.index('vm.mark("F3 reboot keeps state")'))
        self.assertLess(main.index('record("F3"'), main.index('printing(vm, "FP2"'))
        self.assertLess(main.index('record("F4"'), main.index('printing(vm, "FP3"'))

    def test_proof_script_covers_the_criteria(self):
        sh = rd(f"{self.QEMU}/print-proof.sh")
        for needle in ("cups-ipp-utils", "cups-browsed", "findmnt", "remote_admin|remote_any|share_printers", "HTTP_ADMIN", "runuser -u nobody -- lpadmin",
                       "default-testpage.pdf", "FILEDEV_AFTER", "DESC=", "systemctl restart cups.service"):
            self.assertIn(needle, sh)

    def test_firewall_scans_631_and_checks_remote_admin(self):
        fw = rd(f"{self.QEMU}/firewall.py")
        self.assertRegex(fw, r"TCP = \[[^\]]*\b631\b")
        self.assertIn('(443, 631, 7443, 8443, 8444)', fw)
        for needle in ('record("FWP1"', '"/admin/conf"', '== "403"', 'pub == "000"'):
            self.assertIn(needle, fw)


if __name__ == "__main__":
    unittest.main()
