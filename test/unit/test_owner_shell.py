# SPDX-License-Identifier: Apache-2.0
"""Owner shell (Debian-bones step 2): openssh-server, sudo and libpam-systemd, key-only SSH that starts with the
first owner key, a console login whose password lives on /data, no password baked into the image. The booted proof
is test/qemu F15 (CRITERIA-FIRSTBOOT.md section 11); these are the static parts that need no VM."""
import os, re, subprocess, tempfile, unittest
from contextlib import contextmanager

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
        # Run the real script unprivileged with all of its writable paths in the fixture.
        t = rd(f"{L}/usr/lib/onemind/onemind-owner")
        self.assertIn("ONEMIND_OWNER_TEST_ROOT", t)
        with owner_fixture() as d:
            home = os.path.join(d, "home"); os.makedirs(os.path.join(home, ".ssh"))
            target = os.path.join(d, "shadow")
            with open(target, "w") as f:
                f.write("root:!:::\n")
            os.symlink(target, os.path.join(home, ".ssh", "authorized_keys"))
            key = os.path.join(d, "k.pub")
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key[:-4]], check=True)
            r = run_owner(d, "key-add", key)
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("symlink", r.stderr)
            with open(target) as f:
                self.assertEqual(f.read(), "root:!:::\n")

    def test_key_add_plain_case_writes_a_private_file(self):
        with owner_fixture() as d:
            key = os.path.join(d, "k")
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
            for _ in range(2):                      # twice: the second must not duplicate the line
                r = run_owner(d, "key-add", key + ".pub")
                self.assertEqual(r.returncode, 0, r.stderr)
            kf = os.path.join(d, "home", ".ssh", "authorized_keys")
            with open(kf) as f:
                self.assertEqual(len(f.read().splitlines()), 1)
            self.assertEqual(os.stat(kf).st_mode & 0o777, 0o600)

    def test_key_add_refuses_options(self):
        t = rd(f"{L}/usr/lib/onemind/onemind-owner")
        self.assertIn("ssh-*|ecdsa-*|sk-*", t)


OWNER = f"{L}/usr/lib/onemind/onemind-owner"


@contextmanager
def owner_fixture():
    # Root's TMPDIR or the checkout can be inaccessible to the unprivileged subprocess.
    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        if os.geteuid() == 0:
            uid, gid = unprivileged_ids()
            os.chown(d, uid, gid)
        path = os.path.join(d, "onemind-owner")
        with open(path, "w", encoding="utf-8") as script:
            script.write(rd(OWNER))
        os.chmod(path, 0o555)  # apply-job calls this same script again via $0
        yield d


def unprivileged_ids():
    import pwd
    user = pwd.getpwnam("nobody")
    return user.pw_uid, user.pw_gid


def run_owner(d, *args, stdin=None):
    """Run the helper with the unprivileged test hook even when the suite runs as root."""
    env = dict(os.environ, ONEMIND_OWNER_TEST_ROOT=d, TMPDIR=d)
    credentials = {}
    if os.geteuid() == 0:
        uid, gid = unprivileged_ids()
        credentials = {"user": uid, "group": gid, "extra_groups": []}
    return subprocess.run(["sh", os.path.join(d, "onemind-owner"), *args],
                          env=env, input=stdin, capture_output=True, text=True, **credentials)


def make_key(d, name, comment):
    import subprocess
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", os.path.join(d, name)], check=True)
    import subprocess as sp
    fp = sp.run(["ssh-keygen", "-l", "-f", os.path.join(d, name + ".pub")], capture_output=True, text=True, check=True).stdout.split()[1]
    return os.path.join(d, name + ".pub"), fp


class SshKeysAndSwitch(unittest.TestCase):
    """P-06: key-rm, the on/off switch and the job runner of onemind-owner, and the unit files around them."""

    def test_ssh_state_reads_the_fixture_even_if_the_suite_runs_as_root(self):
        with owner_fixture() as d:
            self.assertEqual(run_owner(d, "ssh-state").stdout.strip(), "enabled=true")
            state = os.path.join(d, "sshstate")
            os.mkdir(state)
            with open(os.path.join(state, "disabled"), "w"):
                pass
            self.assertEqual(run_owner(d, "ssh-state").stdout.strip(), "enabled=false")

    def test_key_rm_removes_exactly_one_key_and_publishes_the_list(self):
        with owner_fixture() as d:
            a, fa = make_key(d, "a", "first"); b, fb = make_key(d, "b", "second")
            for k in (a, b):
                self.assertEqual(run_owner(d, "key-add", k).returncode, 0)
            listed = open(os.path.join(d, "sshstate", "keys.list")).read()
            self.assertIn(fa, listed); self.assertIn(fb, listed)
            r = run_owner(d, "key-rm", fa)
            self.assertEqual(r.returncode, 0, r.stderr)
            kf = os.path.join(d, "home", ".ssh", "authorized_keys")
            self.assertEqual(len(open(kf).read().splitlines()), 1)
            self.assertEqual(os.stat(kf).st_mode & 0o777, 0o600)
            listed = open(os.path.join(d, "sshstate", "keys.list")).read()
            self.assertNotIn(fa, listed); self.assertIn(fb, listed)
            self.assertFalse(os.path.exists(os.path.join(d, "systemctl.log")), "one key is left: sshd keeps running")
            self.assertEqual(run_owner(d, "key-rm", fa).returncode, 4)          # already gone: "no such key"

    def test_removing_the_last_key_stops_sshd(self):
        with owner_fixture() as d:
            a, fa = make_key(d, "a", "only")
            run_owner(d, "key-add", a)
            self.assertEqual(run_owner(d, "key-rm", fa).returncode, 0)
            self.assertIn("stop ssh.service", open(os.path.join(d, "systemctl.log")).read())
            self.assertEqual(open(os.path.join(d, "sshstate", "keys.list")).read(), "")

    def test_key_rm_refuses_anything_that_is_not_a_fingerprint(self):
        with owner_fixture() as d:
            a, _ = make_key(d, "a", "x"); run_owner(d, "key-add", a)
            for bad in ("", "x", "MD5:aa:bb", "SHA256:short", "SHA256:" + "A" * 42 + "/../etc", ".*"):
                self.assertEqual(run_owner(d, "key-rm", bad).returncode, 2, bad)
            self.assertEqual(len(open(os.path.join(d, "home", ".ssh", "authorized_keys")).read().splitlines()), 1)

    def test_key_rm_never_follows_a_symlink_as_root(self):
        with owner_fixture() as d:
            a, fa = make_key(d, "a", "x"); run_owner(d, "key-add", a)
            target = os.path.join(d, "shadow")
            open(target, "w").write("root:!:::\n")
            kf = os.path.join(d, "home", ".ssh", "authorized_keys")
            os.remove(kf); os.symlink(target, kf)
            r = run_owner(d, "key-rm", fa)
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertIn("symlink", r.stderr)
            self.assertEqual(open(target).read(), "root:!:::\n")

    def test_key_rm_keeps_comments_and_other_lines_intact(self):
        with owner_fixture() as d:
            a, fa = make_key(d, "a", "x"); b, fb = make_key(d, "b", "y")
            run_owner(d, "key-add", a); run_owner(d, "key-add", b)
            kf = os.path.join(d, "home", ".ssh", "authorized_keys")
            lines = open(kf).read().splitlines()
            open(kf, "w").write("# my own note\n" + "\n".join(lines) + "\n")
            self.assertEqual(run_owner(d, "key-rm", fa).returncode, 0)
            left = open(kf).read().splitlines()
            self.assertEqual(left[0], "# my own note"); self.assertEqual(len(left), 2); self.assertIn(open(b).read().split()[1], left[1])

    def test_a_file_left_with_only_comments_counts_as_no_key(self):
        with owner_fixture() as d:
            a, fa = make_key(d, "a", "x")
            run_owner(d, "key-add", a)
            kf = os.path.join(d, "home", ".ssh", "authorized_keys")
            body = open(kf).read()
            open(kf, "w").write("# my own note\n\n" + body)
            self.assertEqual(run_owner(d, "key-rm", fa).returncode, 0)
            self.assertIn("stop ssh.service", open(os.path.join(d, "systemctl.log")).read())   # no key can log in: stop

    def test_the_switch_is_a_flag_file_on_data_and_survives(self):
        with owner_fixture() as d:
            self.assertIn("enabled=true", run_owner(d, "ssh-state").stdout)
            self.assertEqual(run_owner(d, "ssh-off").returncode, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "sshstate", "disabled")))
            self.assertIn("enabled=false", run_owner(d, "ssh-state").stdout)
            self.assertIn("stop ssh.service", open(os.path.join(d, "systemctl.log")).read())
            self.assertEqual(run_owner(d, "ssh-on").returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(d, "sshstate", "disabled")))
            self.assertIn("start ssh.service", open(os.path.join(d, "systemctl.log")).read())
        t = rd(OWNER)
        self.assertIn("STATEDIR=/data/onemind/ssh", t)           # the real path is on the data partition

    def test_ssh_service_honours_the_flag_on_every_board(self):
        d = rd(f"{SYS}/ssh.service.d/40-onemind-ssh-toggle.conf")
        self.assertIn("ConditionPathExists=!/data/onemind/ssh/disabled", d)
        self.assertRegex(d, r"(?m)^RequiresMountsFor=/data/onemind/ssh$")
        self.assertIn("STATEDIR=/data/onemind/ssh", rd(OWNER))
        self.assertIn("OFF=$STATEDIR/disabled", rd(OWNER))          # the same file the unit condition tests
        # the cloud boards delete 20-onemind-owner-key.conf; the switch lives in its own file so it stays
        self.assertNotIn("40-onemind-ssh-toggle", rd("os/rootfs/Containerfile"))
        self.assertTrue(exists(f"{SYS}/ssh.service.d/40-onemind-ssh-toggle.conf"))

    def test_job_runner_applies_one_filed_job_and_leaves_a_result(self):
        with owner_fixture() as d:
            a, fa = make_key(d, "a", "via job")
            self.assertEqual(run_owner(d, "apply-job").returncode, 0)  # create the fixture state directory
            job = os.path.join(d, "sshstate", "job")
            open(job, "w").write("key-add\n" + open(a).read())
            self.assertEqual(run_owner(d, "apply-job").returncode, 0)
            self.assertFalse(os.path.exists(job), "a done job is not left behind")
            self.assertTrue(open(os.path.join(d, "sshstate", "result")).read().startswith("rc=0\n"))
            self.assertIn(fa, open(os.path.join(d, "sshstate", "keys.list")).read())
            open(job, "w").write("key-rm\n" + fa + "\n")
            run_owner(d, "apply-job")
            self.assertEqual(open(os.path.join(d, "sshstate", "keys.list")).read(), "")
            open(job, "w").write("key-rm\n" + fa + "\n")
            run_owner(d, "apply-job")
            self.assertTrue(open(os.path.join(d, "sshstate", "result")).read().startswith("rc=4\n"))
            open(job, "w").write("key-add\ncommand=\"id\" ssh-ed25519 AAAA x\n")
            run_owner(d, "apply-job")
            self.assertTrue(open(os.path.join(d, "sshstate", "result")).read().startswith("rc=2\n"))
            open(job, "w").write("ssh\noff\n")
            run_owner(d, "apply-job")
            self.assertTrue(os.path.exists(os.path.join(d, "sshstate", "disabled")))
            open(job, "w").write("rm-rf\n/\n")
            run_owner(d, "apply-job")
            self.assertTrue(open(os.path.join(d, "sshstate", "result")).read().startswith("rc=64\n"))
            os.remove(os.path.join(d, "sshstate", "result"))
            run_owner(d, "apply-job")                                          # no job: only publishes the list
            self.assertFalse(os.path.exists(os.path.join(d, "sshstate", "result")))

    def test_the_apply_unit_is_a_root_oneshot_that_nothing_enables(self):
        u = rd(f"{SYS}/onemind-ssh-apply.service")
        self.assertIn("Type=oneshot", u)
        self.assertIn("ExecStart=/usr/lib/onemind/onemind-owner apply-job", u)
        self.assertNotIn("[Install]", "\n".join(l for l in u.splitlines() if not l.startswith("#")))  # started by the host service only
        self.assertIn("onemind-ssh-apply.service", rd(f"{L}/usr/lib/onemind/services.yaml"))

    def test_the_host_service_never_gets_wider_to_do_this(self):
        # It is sandboxed (no /home, no capabilities to start sshd); the design files a job on /data instead.
        h = rd(f"{SYS}/onemind-host.service")
        self.assertIn("ProtectHome=yes", h)
        self.assertIn("ReadWritePaths=/data /boot/efi", h)       # /data is where the job and the result are filed

    def test_the_apply_job_runs_with_a_read_only_root_and_few_capabilities(self):
        a = rd(f"{SYS}/onemind-ssh-apply.service")
        self.assertIn("ProtectSystem=strict", a)
        self.assertIn("ReadWritePaths=/data", a)
        self.assertRegex(a, r"CapabilityBoundingSet=CAP_")
        self.assertNotIn("CAP_SYS_ADMIN", a)
        for line in ("SystemCallFilter=@system-service", "PrivateDevices=yes", "IPAddressDeny=any", "RestrictNamespaces=yes",
                     "ProtectHome=read-only", "MemoryDenyWriteExecute=yes"):
            self.assertIn(line, a)                                # the score gate (test_unit_security.py) needs 5.0 or better

    def test_rate_limit_and_accept_are_in_the_ssh_chain_in_that_order(self):
        d = rd(f"{SYS}/ssh.service.d/30-onemind-firewall.conf")
        v4, v6, acc = (d.index(x) for x in ("update @ssh_new_v4", "update @ssh_new_v6", "tcp dport 22 accept"))
        self.assertLess(v4, acc); self.assertLess(v6, acc)
        self.assertEqual(d.count("limit rate over 6/minute burst 6 packets"), 2)
        self.assertEqual(d.count("ct state new"), 2)             # only new connections are counted
        self.assertIn("ip saddr", d); self.assertIn("ip6 saddr", d)

    def test_a_steady_guesser_keeps_its_counter(self):
        # "update" restarts a source's timeout on every new connection, so the limiter persists while it keeps trying;
        # "add" let it expire a minute after the first try and handed out a fresh burst (about 12 a minute, not 6).
        d = rd(f"{SYS}/ssh.service.d/30-onemind-firewall.conf")
        rules = [l for l in d.splitlines() if l.startswith("ExecStartPost") and "limit rate over" in l]
        self.assertEqual(len(rules), 2)
        for l in rules:
            self.assertIn(" update @ssh_new_v", l)
            self.assertNotIn(" add @ssh_new_v", l)

    def test_limit_survives_a_second_start_of_sshd(self):
        # A "meter" statement creates a named set per start; the second start (SSH off, then on) is refused and the
        # limit is lost. The sets are declared once in host.nft and the rules only "update @set"; a limit rule that
        # fails must show in the journal, so it has no "-" prefix.
        d = rd(f"{SYS}/ssh.service.d/30-onemind-firewall.conf")
        self.assertNotIn("meter", [w for l in d.splitlines() if l.startswith("ExecStartPost") for w in l.split()])
        n = rd(f"{L}/usr/lib/onemind/host.nft")
        for fam in ("ipv4", "ipv6"):
            self.assertRegex(n, rf"set ssh_new_v{fam[-1]} \{{ type {fam}_addr; flags dynamic,timeout;")
        for l in d.splitlines():
            if l.startswith("ExecStartPost") and "limit rate over" in l:
                self.assertTrue(l.startswith("ExecStartPost=+"), l)


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
