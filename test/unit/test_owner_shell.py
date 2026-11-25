# SPDX-License-Identifier: Apache-2.0
"""Owner shell (Debian-bones step 2): openssh-server, sudo and libpam-systemd, key-only SSH that starts with the
first owner key, a console login whose password lives on /data, no password baked into the image. The booted proof
is test/qemu F15 (CRITERIA-FIRSTBOOT.md section 11); these are the static parts that need no VM."""
import os, re, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
L = "os/rootfs/layers/onemind"
SYS = f"{L}/usr/lib/systemd/system"


def rd(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def exists(p):
    return os.path.exists(os.path.join(ROOT, p))


class Packages(unittest.TestCase):
    def test_debian_and_ubuntu_legs_list_the_three_packages(self):
        for leg in ("debian", "ubuntu"):
            txt = "\n".join(l.split("#")[0] for l in rd(f"os/rootfs/packages/{leg}-common.txt").splitlines())
            for p in ("openssh-server", "sudo", "libpam-systemd"):
                self.assertRegex(txt, rf"(^|\s){p}(\s|$)", f"{leg}: {p}")


class SshdPolicy(unittest.TestCase):
    CONF = rd(f"{L}/etc/ssh/sshd_config.d/00-onemind.conf")

    def test_public_key_only_for_admin_only(self):
        lines = [l.strip() for l in self.CONF.splitlines() if l.strip() and not l.startswith("#")]
        for want in ("AllowUsers admin", "AuthenticationMethods publickey", "PasswordAuthentication no",
                     "KbdInteractiveAuthentication no", "PermitRootLogin no", "PermitEmptyPasswords no"):
            self.assertIn(want, lines)

    def test_host_keys_live_on_data(self):
        hk = re.findall(r"^HostKey (\S+)", self.CONF, re.M)
        self.assertTrue(hk)
        for k in hk:
            self.assertTrue(k.startswith("/data/onemind/ssh/"), k)

    def test_the_cloud_boards_use_the_shared_files_not_copies(self):
        for b in ("cloud", "vm-do"):
            for f in ("etc/ssh/sshd_config.d/00-onemind.conf", "usr/lib/systemd/system/onemind-ssh-hostkeys.service",
                      "usr/lib/systemd/system/ssh.service.d/onemind-hostkeys.conf"):
                self.assertFalse(exists(f"os/boards/{b}/rootfs/{f}"), f"{b} still ships its own {f}")
        self.assertTrue(exists(f"{SYS}/onemind-ssh-hostkeys.service"))
        self.assertIn("Requires=onemind-ssh-hostkeys.service", rd(f"{SYS}/ssh.service.d/onemind-hostkeys.conf"))


class StartsOnlyWithAnOwnerKey(unittest.TestCase):
    def test_ssh_service_is_conditional_on_the_key_file(self):
        d = rd(f"{SYS}/ssh.service.d/20-onemind-owner-key.conf")
        self.assertIn("ConditionFileNotEmpty=/home/admin/.ssh/authorized_keys", d)
        self.assertIn("onemind-owner ensure", d)

    def test_condition_is_checked_after_home_is_mounted(self):
        d = rd(f"{SYS}/ssh.service.d/20-onemind-owner-key.conf")
        unit = d.split("[Service]")[0]
        self.assertRegex(unit, r"(?m)^RequiresMountsFor=/home/admin$")

    def test_path_unit_starts_ssh_when_the_key_file_changes(self):
        u = rd(f"{SYS}/onemind-ssh-owner-key.path")
        self.assertIn("PathChanged=/home/admin/.ssh/authorized_keys", u)
        self.assertIn("Unit=ssh.service", u)
        self.assertNotIn("PathExists", u)        # an empty file would re-trigger it in a loop

    def test_containerfile_enables_it_on_hardware_and_cloud_drops_the_condition(self):
        c = rd("os/rootfs/Containerfile")
        self.assertIn("systemctl enable ssh.service onemind-ssh-owner-key.path getty@tty2.service", c)
        self.assertIn("rm -f /usr/lib/systemd/system/ssh.service.d/20-onemind-owner-key.conf", c)
        self.assertIn("systemctl mask ssh.socket", c)       # socket activation would listen without a key
        self.assertIn("rm -f /etc/ssh/ssh_host_*", c)       # no shared host keys in the slot

    def test_the_firewall_chain_is_filled_by_sshd_not_by_the_ruleset(self):
        # details are in test_host_firewall.py; here, only that the unit drop-in exists
        self.assertTrue(exists(f"{SYS}/ssh.service.d/30-onemind-firewall.conf"))


class NoPasswordIsBaked(unittest.TestCase):
    C = rd("os/rootfs/Containerfile")

    def test_admin_account_has_no_shadow_line_and_no_chpasswd(self):
        self.assertIn("sed -i '/^admin:/d' /etc/shadow", self.C)
        self.assertNotRegex(self.C, r"chpasswd|usermod[^\n]*-p|useradd[^\n]*(-p |--password)|openssl passwd")
        self.assertNotIn("admin:$", self.C)

    def test_owner_password_goes_to_extrausers_shadow_on_data(self):
        t = rd(f"{L}/usr/lib/onemind/onemind-owner")
        self.assertIn("/var/lib/extrausers", t)
        self.assertIn("openssl passwd -6 -stdin", t)          # the password is never an argument (ps would show it)
        self.assertIn("/var/lib/extrausers - - - - /data/onemind/samba/extrausers", rd(f"{L}/usr/lib/tmpfiles.d/onemind-smb.conf"))
        # /var/lib is on the read-only root, so tmpfiles cannot link it at boot: the image carries the link (F15 root cause)
        self.assertIn("ln -s /data/onemind/samba/extrausers /var/lib/extrausers", rd("os/rootfs/Containerfile"))
        self.assertIn("admin ALL=(ALL) ALL", rd(f"{L}/etc/sudoers.d/admin"))
        self.assertNotIn("NOPASSWD", rd(f"{L}/etc/sudoers.d/admin"))

    def test_key_add_never_follows_a_symlink_as_root(self):
        # The admin owns /home/admin, so a key-only admin could point .ssh or authorized_keys at the shadow file.
        # key-add refuses symlinks and does the writing as admin, so even a race cannot reach a root-only file.
        t = rd(f"{L}/usr/lib/onemind/onemind-owner")
        key_add = t.split("key-add)")[1].split("key-list)")[0]
        self.assertIn('[ -L "$HOMEDIR" ]', t)
        self.assertIn('[ -L "$SSHDIR" ]', t)
        self.assertIn('[ -L "$KEYS" ]', t)
        self.assertIn("runuser -u", t)
        self.assertIn("as_owner sh -c", key_add)
        self.assertNotRegex(key_add, r"chown[^\n]*\$KEYS|chmod[^\n]*\$KEYS|>>\s*\"\$KEYS\"")
        self.assertNotRegex(key_add, r"install -d[^\n]*SSHDIR")
        self.assertNotRegex(key_add, r"chown")

    def test_key_add_symlink_attack_is_refused(self):
        # Behavioural: run the real script as the current user with the paths pointed into a temp dir.
        import subprocess, tempfile
        t = rd(f"{L}/usr/lib/onemind/onemind-owner")
        self.assertIn("ONEMIND_OWNER_TEST_ROOT", t)
        with tempfile.TemporaryDirectory() as d:
            home = os.path.join(d, "home"); os.makedirs(os.path.join(home, ".ssh"))
            target = os.path.join(d, "shadow")
            with open(target, "w") as f:
                f.write("root:!:::\n")
            os.symlink(target, os.path.join(home, ".ssh", "authorized_keys"))
            key = os.path.join(d, "k.pub")
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key[:-4]], check=True)
            env = dict(os.environ, ONEMIND_OWNER_TEST_ROOT=d)
            r = subprocess.run(["sh", os.path.join(ROOT, L, "usr/lib/onemind/onemind-owner"), "key-add", key],
                               env=env, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("symlink", r.stderr)
            with open(target) as f:
                self.assertEqual(f.read(), "root:!:::\n")

    def test_key_add_plain_case_writes_a_private_file(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            key = os.path.join(d, "k")
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
            env = dict(os.environ, ONEMIND_OWNER_TEST_ROOT=d)
            for _ in range(2):                      # twice: the second must not duplicate the line
                r = subprocess.run(["sh", os.path.join(ROOT, L, "usr/lib/onemind/onemind-owner"), "key-add", key + ".pub"],
                                   env=env, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
            kf = os.path.join(d, "home", ".ssh", "authorized_keys")
            with open(kf) as f:
                self.assertEqual(len(f.read().splitlines()), 1)
            self.assertEqual(os.stat(kf).st_mode & 0o777, 0o600)

    def test_key_add_refuses_options(self):
        t = rd(f"{L}/usr/lib/onemind/onemind-owner")
        self.assertIn("ssh-*|ecdsa-*|sk-*", t)


class KioskUserExistsInTheImage(unittest.TestCase):
    def test_kiosk_user_is_created_at_build_time(self):
        # F15 first run: onemind-kiosk.service failed with 217/USER. The user came only from sysusers.d, which needs a
        # writable /etc at boot; the root is read-only, so the account must be in the image like the other users.
        c = rd("os/rootfs/Containerfile")
        self.assertRegex(c, r"useradd --system[^\n]*\\\n[^\n]*onemind-kiosk;")


class SmbDoesNotClobberTheOwner(unittest.TestCase):
    def test_samba_keeps_foreign_shadow_lines(self):
        self.assertIn("var keep bytes.Buffer", rd("internal/smb/manager.go"))


if __name__ == "__main__":
    unittest.main()
