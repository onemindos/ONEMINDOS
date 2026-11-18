# SPDX-License-Identifier: Apache-2.0
"""IMG-MESH-01 (#292): the mesh in the OS image. Static checks on the files that make the image run
Tailscale everywhere and Headscale on the hub: pins, users, writable state, units. Stdlib only."""
import os, re, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNITS = "os/rootfs/layers/onemind/usr/lib/systemd/system"


def rd(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def lock_block(name):
    """The text of one onemind_layer entry in os/versions.lock.yaml (up to the next sibling key)."""
    s = rd("os", "versions.lock.yaml")
    m = re.search(r"^  %s:.*?(?=^  \w[\w-]*:|^\w)" % name, s, re.M | re.S)
    assert m, name
    return m.group(0)


def pins_env(key):
    m = re.search(r'^%s="([^"]*)"' % key, rd("deploy", "pins.env"), re.M)
    assert m, key
    return m.group(1)


class Pins(unittest.TestCase):
    def test_tailscale_pins_agree(self):
        fetch, lock = rd("os/rootfs/fetch-onemind.sh"), lock_block("tailscale")
        v = pins_env("TAILSCALE_VERSION")
        self.assertIn("TAILSCALE_VERSION=" + v, fetch)
        self.assertIn("version: " + v, lock)
        for arch in ("amd64", "arm64"):
            tar = pins_env("TAILSCALE_SHA256_" + arch)
            self.assertIn(tar, fetch)
            self.assertIn(tar, lock)
            m = re.search(r"%s: \{tarball: (\w+), tailscale: (\w+), tailscaled: (\w+)\}" % arch, lock)
            self.assertTrue(m, arch)
            self.assertEqual(m.group(1), tar)
            for h in m.group(2, 3):
                self.assertRegex(h, r"^[0-9a-f]{64}$")
                self.assertIn(h, fetch)

    def test_headscale_pins_agree(self):
        fetch, lock = rd("os/rootfs/fetch-onemind.sh"), lock_block("headscale")
        v = pins_env("HEADSCALE_VERSION")
        self.assertIn("HEADSCALE_VERSION=" + v, fetch)
        self.assertIn("version: " + v, lock)
        for arch in ("amd64", "arm64"):
            h = pins_env("HEADSCALE_SHA256_" + arch)
            self.assertIn(h, fetch)
            self.assertIn("%s: %s" % (arch, h), lock)

    def test_fetch_has_every_case(self):
        fetch = rd("os/rootfs/fetch-onemind.sh")
        for what in ("tailscale", "headscale"):
            for arch in ("amd64", "arm64"):
                self.assertRegex(fetch, r"(?m)^%s-%s\)" % (what, arch))
        self.assertIn("BIN2_SHA", fetch)

    def test_image_installs_binaries_and_prints_versions(self):
        c = rd("os/rootfs/Containerfile")
        for src, dst in (("/opt/tailscale/tailscale", "/usr/bin/tailscale"),
                         ("/opt/tailscale/tailscaled", "/usr/sbin/tailscaled"),
                         ("/opt/headscale/headscale", "/usr/bin/headscale")):
            self.assertIn("COPY --from=onemind-fetch %s %s" % (src, dst), c)
        self.assertIn('fetch-onemind tailscale "$TARGETARCH"', c)
        self.assertIn('fetch-onemind headscale "$TARGETARCH"', c)
        self.assertIn("/usr/sbin/tailscaled --version", c)
        self.assertIn("/usr/bin/headscale version", c)

    def test_nftables_is_in_every_package_list(self):
        for leg in ("debian", "ubuntu"):
            self.assertRegex(rd("os/rootfs/packages/%s-common.txt" % leg), r"(?m)^[^#\n]*\bnftables\b")


class Users(unittest.TestCase):
    def test_static_users_with_fixed_ids(self):
        c = rd("os/rootfs/Containerfile")
        for name, uid in (("onemind-nats", 962), ("onemind-headscale", 963)):
            self.assertIn("groupadd --system --gid %d %s" % (uid, name), c)
            self.assertRegex(c, r"useradd --system --uid %d --gid %s --no-create-home" % (uid, name))
            self.assertRegex(c, r"useradd --system --uid %d [^;]*?/usr/sbin/nologin %s" % (uid, name), name)


class State(unittest.TestCase):
    BINDS = {"var-lib-tailscale": "/var/lib/tailscale",
             "var-lib-onemind-headscale": "/var/lib/onemind-headscale",
             "var-lib-onemind-nats-leaf": "/var/lib/onemind-nats-leaf",
             "etc-hosts": "/etc/hosts"}

    def test_each_bind_has_a_layout_dir_and_a_mount_point(self):
        fstab = rd("os/rootfs/layers/base/etc/fstab")
        layout = rd("os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-layout.service")
        cont = rd("os/rootfs/Containerfile")
        for src, dst in self.BINDS.items():
            self.assertRegex(fstab, r"(?m)^/data/state/%s\s+%s\s+none bind,nofail,x-systemd\.requires=onemind-data-layout\.service 0 0$"
                             % (re.escape(src), re.escape(dst)))
            if src == "etc-hosts":
                continue
            self.assertRegex(layout, r"for d in [^;]*\b%s\b[^;]*; do mkdir -p" % re.escape(src))
            self.assertIn(dst, cont)   # the mkdir -p of mount points in the Containerfile

    def test_state_ownership(self):
        layout = rd("os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-layout.service")
        self.assertIn("chown 963:963 /data/state/var-lib-onemind-headscale", layout)
        self.assertIn("chmod 0700 /data/state/var-lib-onemind-headscale", layout)
        self.assertIn("chown 962:962 /data/state/var-lib-onemind-nats-leaf", layout)
        self.assertIn("chmod 0700 /data/state/var-lib-onemind-nats-leaf", layout)

    def test_hosts_is_seeded_from_a_pristine_copy(self):
        layout = rd("os/rootfs/layers/base/usr/lib/systemd/system/onemind-data-layout.service")
        self.assertIn("[ -f /data/state/etc-hosts ] || install -m 0644 /usr/lib/onemind/hosts.default /data/state/etc-hosts", layout)
        self.assertEqual(rd("os/rootfs/layers/base/usr/lib/onemind/hosts.default"), rd("os/rootfs/layers/base/etc/hosts"))


class Units(unittest.TestCase):
    CASES = {
        "tailscaled.service": ("/data /var/lib/tailscale", "/data/onemind/identity/ca.pem"),
        "onemind-headscale.service": ("/data /var/lib/onemind-headscale", "/data/onemind/etc/headscale/config.yaml"),
        "onemind-nats-leaf.service": ("/data /var/lib/onemind-nats-leaf", "/data/onemind/etc/nats/leaf.conf"),
    }

    def test_conditions_and_mounts(self):
        for unit, (mounts, cond) in self.CASES.items():
            u = rd(UNITS, unit)
            self.assertIn("RequiresMountsFor=" + mounts, u, unit)
            self.assertIn("ConditionPathExists=" + cond, u, unit)

    def test_units_are_not_enabled_in_the_containerfile(self):
        c = rd("os/rootfs/Containerfile")
        for unit in self.CASES:
            for m in re.finditer(r"systemctl\s+(?:--\S+\s+)*(?:enable|preset)\b[^;]*", c):
                self.assertNotIn(unit.replace(".service", ""), m.group(0), unit)
            self.assertNotIn(chr(10) + "[Install]", rd(UNITS, unit), unit)

    def test_tailscaled_never_sends_logs(self):
        u = rd(UNITS, "tailscaled.service")
        self.assertIn("--no-logs-no-support", u)
        self.assertIn("Environment=TS_NO_LOGS_NO_SUPPORT=true", u)
        self.assertIn("Environment=SSL_CERT_FILE=/data/onemind/identity/ca.pem", u)
        self.assertIn("--state=/var/lib/tailscale/tailscaled.state", u)
        self.assertIn("--socket=/run/tailscale/tailscaled.sock", u)
        self.assertIn("--port=41641", u)

    def test_flannel_guard_matches_install_sh(self):
        u = rd(UNITS, "tailscaled.service")
        self.assertIn("ExecStartPre=/usr/sbin/nft -f /usr/lib/onemind/mesh-guard.nft", u)
        self.assertIn("ExecStopPost=-/usr/sbin/nft delete table inet onemind_mesh_guard", u)
        rules = [l for l in rd("os/rootfs/layers/onemind/usr/lib/onemind/mesh-guard.nft").splitlines() if l.strip() and not l.startswith("#")]
        inst = rd("deploy/install.sh")
        m = re.search(r"cat > \"\$ETC/mesh-guard\.nft\" <<'EOF'\n(.*?)\nEOF", inst, re.S)
        self.assertTrue(m)
        want = [l for l in m.group(1).splitlines() if l.strip() and not l.startswith("#")]
        self.assertEqual(rules, want)

    def test_headscale_unit(self):
        u = rd(UNITS, "onemind-headscale.service")
        for line in ("User=onemind-headscale", "Group=onemind-headscale", "RuntimeDirectory=onemind-headscale",
                     "RuntimeDirectoryMode=0750", "ReadWritePaths=/var/lib/onemind-headscale",
                     "ExecStart=/usr/bin/headscale serve -c /data/onemind/etc/headscale/config.yaml",
                     "ProtectSystem=strict"):
            self.assertIn(line, u)
        self.assertNotRegex(u, r"(?m)^DynamicUser=")
        self.assertNotRegex(u, r"(?m)^StateDirectory=")
        self.assertIn("/data/onemind/gateway/tls/control.crt", u)
        self.assertIn("/data/onemind/gateway/tls/control.key", u)

    def test_nats_leaf_unit(self):
        u = rd(UNITS, "onemind-nats-leaf.service")
        for line in ("User=onemind-nats", "ExecStart=/usr/bin/nats-server -c /data/onemind/etc/nats/leaf.conf",
                     "ReadWritePaths=/var/lib/onemind-nats-leaf"):
            self.assertIn(line, u)
        self.assertNotRegex(u, r"(?m)^StateDirectory=")


LEGACY_HUB_CONF = (  # the pre-mesh hub config (old nats_conf())
    "server_name: hub\nlisten: 0.0.0.0:4222\n"
    'leafnodes { listen: 0.0.0.0:7422, authorization { user: "node", password: "x" } }\n')
LEGACY_LEAF_CONF = 'server_name: leaf\nleafnodes { remotes = [ { url: "nats://192.0.2.1:7422" } ] }\n'


class NatsMeshWait(unittest.TestCase):
    """onemind-nats.service waits for the mesh address only for the mesh leaf listener, never for the
    `leafnodes {` block of a box set up before IMG-MESH-01 (it has no tailscaled and would never start)."""

    @staticmethod
    def waits(conf_text):
        u = rd(UNITS, "onemind-nats.service")
        m = re.search(r"^ExecStartPre=\+/bin/sh -c '(if grep [^']*)'$", u, re.M)
        assert m, "wait-ip ExecStartPre not found"
        script = m.group(1).replace("/run/onemind-nats/nats.conf", "\"$1\"").replace(
            "exec /usr/bin/onemindd mesh wait-ip --timeout 120s", "echo WAIT")
        with tempfile.NamedTemporaryFile("w", suffix=".conf") as f:
            f.write(conf_text)
            f.flush()
            r = subprocess.run(["/bin/sh", "-c", script, "sh", f.name], capture_output=True, text=True)
        return "WAIT" in r.stdout

    def test_legacy_confs_do_not_wait(self):
        self.assertFalse(self.waits(LEGACY_HUB_CONF))
        self.assertFalse(self.waits(LEGACY_LEAF_CONF))

    def test_mesh_conf_waits_and_hub_without_mesh_does_not(self):
        sys.path.insert(0, os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind"))
        try:
            import onemind_firstboot as fb
        finally:
            sys.path.pop(0)
        self.assertTrue(self.waits(fb.hub_nats_conf("192.0.2.1")))
        self.assertFalse(self.waits(fb.hub_nats_conf(None)))


class JetsonLayer(unittest.TestCase):
    """The Jetson layer copies a few base files by name: everything they reference under /usr/lib/onemind
    must ship too, or a unit fails and (with a required bind) the box drops to emergency mode."""

    def test_make_layer_ships_what_copied_units_reference(self):
        mk = rd("os", "boards", "jetson-orin", "make-layer.sh")
        m = re.search(r"for f in (.*?); do", mk, re.S)
        copied = re.findall(r"\S+", m.group(1).replace("\\\n", " "))
        shipped_dirs = [("os", "rootfs", "layers", "onemind"), ("os", "boards", "jetson-orin", "rootfs")]
        for f in copied:
            if not f.startswith("usr/lib/systemd/system/"):
                continue
            unit = rd("os", "rootfs", "layers", "base", f)
            for ref in set(re.findall(r"/usr/lib/onemind/[\w./-]+", unit)):
                rel = ref.lstrip("/")
                # k3s-airgap-images is staged by the shared fetch script, not copied from the repo.
                ok = rel in copied or os.path.basename(rel) in rd("os", "rootfs", "fetch-k3s.sh") or any(os.path.exists(os.path.join(ROOT, *d, rel)) for d in shipped_dirs)
                self.assertTrue(ok, "%s references %s, which make-layer.sh does not ship" % (f, ref))
        self.assertIn("usr/lib/onemind/hosts.default", copied)

    def test_jetson_fstab_has_no_mesh_binds(self):
        fstab = rd("os", "boards", "jetson-orin", "rootfs", "etc", "onemind", "jetson-fstab")
        for needle in ("/etc/hosts", "tailscale", "headscale", "nats-leaf"):
            self.assertNotIn(needle, fstab)


if __name__ == "__main__":
    unittest.main()
