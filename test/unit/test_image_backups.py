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
        for path in ("/data/onemind", "/var/lib/rancher/k3s/storage", "/run/onemind/backup",
                     "/var/lib/rancher/k3s/server/db"):
            self.assertIn("-" + path, d)

    def test_tmpfiles_creates_every_writable_folder(self):
        d = rd("os/rootfs/layers/onemind/usr/lib/systemd/system/onemindd.service.d/backup.conf")
        t = rd("os/rootfs/layers/onemind/usr/lib/tmpfiles.d/onemind-backup.conf")
        for path in re.findall(r"-(/run/onemind/backup|/var/lib/rancher/k3s/storage)\b", d):
            self.assertRegex(t, r"(?m)^d %s " % re.escape(path))
        self.assertRegex(t, r"(?m)^d /data/onemind/backup 0700 ")


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


if __name__ == "__main__":
    unittest.main()
