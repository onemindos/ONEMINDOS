# SPDX-License-Identifier: Apache-2.0
"""IMG-BACKUP-01 (#163, #145): the OS image ships restic and the backup agent wiring, so a booted hub can
back up and restore. Static checks on the files that do it. Stdlib only. The first-boot behaviour is in
test_firstboot.py (Hub.test_backup_*)."""
import json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib")
sys.path.insert(0, os.path.join(LIB, "onemind"))
import onemind_firstboot as fb  # noqa: E402


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def go_pin(arch, group):
    m = re.search(r'\{"restic", "([0-9.]+)", "%s",\s*"[^"]+",\s*"([0-9a-f]{64})",\s*"([0-9a-f]{64})"' % arch,
                  rd("internal", "backup", "pins.go"))
    assert m, arch
    return {"version": m.group(1), "archive": m.group(2), "binary": m.group(3)}[group]


class Pins(unittest.TestCase):
    def test_restic_pins_agree_with_the_agent(self):
        fetch, lock = rd("os/rootfs/fetch-onemind.sh"), rd("os/versions.lock.yaml")
        self.assertIn("RESTIC_VERSION=" + go_pin("amd64", "version"), fetch)
        self.assertIn("version: " + go_pin("amd64", "version"), lock[lock.index("  restic:"):])
        for arch in ("amd64", "arm64"):
            for group in ("archive", "binary"):
                h = go_pin(arch, group)
                self.assertIn(h, fetch, (arch, group))
                self.assertIn(h, lock, (arch, group))
            self.assertRegex(fetch, r"(?m)^restic-%s\)" % arch)

    def test_fetch_checks_the_binary_not_only_the_archive(self):
        fetch = rd("os/rootfs/fetch-onemind.sh")
        self.assertIn('bunzip2 -c "$T/a.dl" > "$T/restic"', fetch)
        self.assertIn('echo "$BIN_SHA  $T/restic" | sha256sum -c -', fetch)


class Image(unittest.TestCase):
    def test_containerfile_ships_restic_and_sqlite(self):
        cf = rd("os", "rootfs", "Containerfile")
        self.assertIn('fetch-onemind restic "$TARGETARCH" /opt/restic', cf)
        self.assertIn("COPY --from=onemind-fetch /opt/restic/restic /usr/lib/onemind/restic", cf)
        self.assertRegex(cf, r"apt-get install -y ca-certificates curl bzip2")
        for leg in ("debian", "ubuntu"):
            self.assertRegex(rd("os", "rootfs", "packages", leg + "-common.txt"), r"(?m)^sqlite3$")

    def test_dropin_grants_only_what_a_restore_needs(self):
        d = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemindd.service.d/backup.conf")
        self.assertIn("CapabilityBoundingSet=CAP_DAC_READ_SEARCH CAP_DAC_OVERRIDE CAP_CHOWN CAP_FOWNER\n", d)
        self.assertIn("ExecStartPre=-/usr/bin/onemindd backup-init\n", d)
        self.assertNotIn("/usr/local/bin", d)
        self.assertNotIn("CacheDirectory", d)            # /var/cache is on the read-only root
        for path in ("/data/onemind", "/data/k3s/storage", "/run/onemind/backup",
                     "/data/k3s/server/db"):
            self.assertIn("-" + path, d)

    def test_tmpfiles_creates_every_writable_folder(self):
        d = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemindd.service.d/backup.conf")
        t = rd("os/rootfs/layers/onemind/usr/lib/tmpfiles.d/onemind-backup.conf")
        for path in re.findall(r"-(/run/onemind/backup|/data/k3s/storage)\b", d):
            self.assertRegex(t, r"(?m)^d %s " % re.escape(path))
        self.assertRegex(t, r"(?m)^d /data/onemind/backup 0700 ")


class K3sPaths(unittest.TestCase):
    """The image runs k3s with --data-dir, so every backup path must live under it (not /var/lib/rancher/k3s)."""

    def data_dir(self):
        unit = rd("os/rootfs/layers/base/usr/lib/systemd/system/k3s.service")
        m = re.search(r"k3s server .*?--data-dir (\S+)", unit)
        self.assertTrue(m)
        return m.group(1).rstrip("/")

    def test_agent_conf_paths_follow_the_data_dir(self):
        dd, c = self.data_dir(), fb.backup_agent_conf(fb.Paths("/"), "0123456789ab")
        k3s = c["units"]["k3s"]
        self.assertIn(dd + "/storage", c["storage_roots"])
        self.assertEqual(k3s["state_db"], dd + "/server/db/state.db")
        for p in list(c["storage_roots"]) + k3s["paths"] + [k3s["state_db"]]:
            self.assertTrue(p.startswith(dd + "/"), p)
            self.assertNotIn("/var/lib/rancher", p)

    def test_sandbox_and_tmpfiles_follow_the_data_dir(self):
        dd = self.data_dir()
        d = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemindd.service.d/backup.conf")
        t = rd("os/rootfs/layers/onemind/usr/lib/tmpfiles.d/onemind-backup.conf")
        for path in (dd + "/storage", dd + "/server/db"):
            self.assertIn("-" + path, d)
        self.assertRegex(t, r"(?m)^d %s/storage " % re.escape(dd))
        self.assertNotIn("/var/lib/rancher", d + t)


class AgentConf(unittest.TestCase):
    def test_generator_matches_the_fixture_the_agent_loads(self):
        # internal/backup/image_conf_test.go loads this file with the agent's own LoadConfig.
        got = fb.backup_agent_conf(fb.Paths("/"), "0123456789ab")
        want = json.loads(rd("internal", "backup", "testdata", "image-agent.json"))
        self.assertEqual(got, want)

    def test_same_keys_as_the_developer_install(self):
        sh = rd("deploy", "backup.sh")
        heredoc = sh[sh.index('<<EOF\n{') :]
        keys = set(re.findall(r'^  "(\w+)":', heredoc[: heredoc.index("\nEOF")], re.M))
        self.assertEqual(keys, set(fb.backup_agent_conf(fb.Paths("/"), "x").keys()))

    def test_k3s_version_follows_the_lock(self):
        m = re.search(r"(?m)^k3s:\n  version: (\S+)", rd("os", "versions.lock.yaml"))
        self.assertEqual(fb.K3S_BACKUP_VERSION, m.group(1).replace("+", "-"))

    def test_no_destination_and_loopback_only(self):
        c = fb.backup_agent_conf(fb.Paths("/"), "0123456789ab")
        self.assertEqual(c["targets"], [])
        self.assertTrue(c["listen"].startswith("127.0.0.1:"))



class StorageMount(unittest.TestCase):
    """#1148: the owner's files on a btrfs box are the @storage subvolume at /data/storage. The backup must carry that
    folder, from the one path firstboot knows, which must be where the mount unit, snapper and data_encrypt.py put it."""

    def test_one_storage_path_for_the_mount_snapper_and_the_backup(self):
        storage = fb.Paths("/").storage
        mount = rd("os/rootfs/layers/base/usr/lib/systemd/system/data-storage.mount")
        self.assertEqual(re.search(r"(?m)^Where=(\S+)$", mount).group(1), storage)
        self.assertRegex(mount, r"(?m)^Options=subvol=@storage\b")
        self.assertEqual(re.search(r'(?m)^SUBVOLUME="([^"]+)"$', rd("os/rootfs/layers/base/etc/snapper/configs/storage")).group(1),
                         storage)
        de = rd("os/rootfs/layers/base/usr/lib/onemind/data_encrypt.py")
        self.assertIn('SUBVOLS = ("@", "@storage")', de)
        self.assertIn("@storage the owner's files, mounted at " + storage, de)

    def test_the_system_unit_carries_the_storage_mount_without_its_snapshots(self):
        p = fb.Paths("/")
        self.assertIn(p.storage, fb.backup_system_paths(p, has_storage=True))
        self.assertEqual(fb.backup_system_excludes(p, has_storage=True), [p.storage + "/.snapshots"])
        # an ext4 box installed before #152 has no /data/storage; a missing source fails the whole unit
        self.assertNotIn(p.storage, fb.backup_system_paths(p, has_storage=False))
        self.assertEqual(fb.backup_system_excludes(p, has_storage=False), [])

    def test_a_hub_gets_the_storage_mount_in_its_agent_conf_new_or_upgraded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p = fb.Paths(t)
            os.makedirs(p.storage)
            system = fb.backup_agent_conf(p, "0123456789ab")["units"]["system"]
            self.assertIn(p.storage, system["paths"])
            self.assertEqual(system["excludes"], [os.path.join(p.storage, ".snapshots")])
            os.makedirs(os.path.dirname(p.backup_conf))
            old = fb.backup_agent_conf(p, "0123456789ab")
            old["units"]["system"]["paths"] = old["units"]["system"]["paths"][:-1]      # written before #1148
            del old["units"]["system"]["excludes"]
            with open(p.backup_conf, "w") as f:
                json.dump(old, f)
            fb.upgrade_agent_conf(p)
            fb.upgrade_agent_conf(p)                                                  # idempotent
            got = json.load(open(p.backup_conf))["units"]["system"]
            self.assertEqual(got["paths"].count(p.storage), 1)
            self.assertEqual(got["excludes"], [os.path.join(p.storage, ".snapshots")])

    def test_a_restore_may_write_the_storage_mount_and_nothing_creates_it_on_ext4(self):
        storage = fb.Paths("/").storage
        d = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemindd.service.d/backup.conf")
        self.assertRegex(d, r"(?m)^ReadWritePaths=.*-%s(\s|$)" % re.escape(storage))
        self.assertNotRegex(rd("os/rootfs/layers/onemind/usr/lib/tmpfiles.d/onemind-backup.conf"),
                            r"(?m)\s%s(\s|$)" % re.escape(storage))


if __name__ == "__main__":
    unittest.main()
