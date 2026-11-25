# SPDX-License-Identifier: Apache-2.0
"""onemind-firstboot and the setup wizard (docs/leap/core/IMAGES.md §3, IMG-MESH-01), against a temp root.

The hub tests use the gateway's own box CA and NATS key code (core/onemind_core: ca.py, natsconf.py),
which needs the `cryptography` package: run them with core's venv, as CI's `unit` job does
(`uv sync --project core`, then core/.venv/bin/python -I -m unittest ...). Without it they are skipped.
"""
import contextlib, io, json, os, re, shutil, stat, subprocess, sys, tempfile, threading, unittest, urllib.error, urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
sys.path.insert(1, os.path.join(ROOT, "core"))     # onemind_core, as the gateway venv has it
import onemind_firstboot as fb  # noqa: E402
import onemind_setup as setup  # noqa: E402
import onemind_setup_helper as setup_helper  # noqa: E402

try:
    from cryptography import x509 as _x509
    from onemind_core import ca as core_ca  # noqa: F401
    # A distribution's older cryptography (no *_utc accessors) is not what the gateway venv pins.
    HAVE_CORE = hasattr(_x509.Certificate, "not_valid_after_utc")
except ImportError:
    HAVE_CORE = False
needs_core = unittest.skipUnless(HAVE_CORE, "needs onemind_core and cryptography (core's venv)")

CA_SHA = "ab" * 32
JOIN = f"onemind-join:v1?code=7KQ4-M2XP-9D3F&ca={CA_SHA}&role=worker&hub=https%3A%2F%2Fhome-box.local"
LEAF_JOIN = JOIN.replace("role=worker", "role=leaf")
LAN = "192.0.2.10"            # TEST-NET-1 (RFC 5737)
MESH_IP = "100.64.0.1"
PREAUTH = "hskey-auth-" + "5" * 40
APIKEY = "hskey-api-" + "7" * 40


class Box(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = fb.Paths(self.tmp.name)
        os.makedirs(os.path.join(self.tmp.name, "dev"))
        open(self.p.console, "w").close()
        self.started = []
        self.out = io.StringIO()
        patches = [mock.patch.object(fb, "systemctl", lambda *a: self.started.append(a) or 0),
                   mock.patch.object(fb, "find_seed_device", lambda: None),
                   mock.patch.object(fb.socket, "gethostname", lambda: "Home_Box"),
                   mock.patch.object(fb, "lan_addr", lambda: LAN),
                   mock.patch.object(fb.time, "sleep", lambda s: None),
                   # The fake box has its own data disk, independent of the runner's temp filesystem.
                   mock.patch("shutil.disk_usage", return_value=shutil._ntuple_diskusage(24 << 30, 0, 24 << 30))]
        for pt in patches:
            pt.start()
            self.addCleanup(pt.stop)
        redirect = contextlib.redirect_stdout(self.out)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, rel, text):
        path = os.path.join(self.tmp.name, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").write(text)
        return path

    def console(self):
        return open(self.p.console).read()

    def read(self, path):
        return open(path).read()

    def mode(self, path):
        return stat.S_IMODE(os.lstat(path).st_mode)

    def etc(self, name):
        return self.read(os.path.join(self.p.etc, name))


class Parsing(unittest.TestCase):
    def test_conf_lines_comments_quotes(self):
        self.assertEqual(fb.parse_conf("# c\nrole = hub  # inline\nname = \"My box\"\n\n"),
                         {"role": "hub", "name": "My box"})
        self.assertEqual(fb.parse_conf(f"role = worker\njoin_code = {JOIN}\nhub-addr = {LAN}\n"),
                         {"role": "worker", "join_code": JOIN, "hub_addr": LAN})

    def test_conf_rejects_unknown_key_and_garbage(self):
        for bad in ("rolle = hub\n", "role hub\n"):
            with self.assertRaises(fb.ConfigError):
                fb.parse_conf(bad)

    def test_old_keys_are_unknown_now(self):
        """The shared NATS password is gone: join_token, nats_tls and hub are refused, not ignored."""
        for key in ("join_token", "nats_tls", "hub"):
            with self.assertRaisesRegex(fb.ConfigError, "unknown key"):
                fb.parse_conf(f"role = worker\n{key} = x\n")
            with self.assertRaisesRegex(fb.ConfigError, "unknown key"):
                fb.parse_userdata(f"#cloud-config\nonemind:\n  role: worker\n  {key}: x\n")

    def test_template_on_esp_configures_nothing(self):
        text = open(os.path.join(ROOT, "os", "assemble", "onemind.conf.in")).read()
        self.assertEqual(fb.parse_conf(text), {})

    def test_userdata(self):
        self.assertEqual(fb.parse_userdata("#cloud-config\nonemind:\n  role: hub\n"), {"role": "hub"})
        self.assertIsNone(fb.parse_userdata("#cloud-config\nssh_authorized_keys: []\n"))
        self.assertIsNone(fb.parse_userdata("#!/bin/sh\necho hi\n"))
        with self.assertRaises(fb.ConfigError):
            fb.parse_userdata("#cloud-config\nonemind: hub\n")
        with self.assertRaises(fb.ConfigError):
            fb.parse_userdata("#cloud-config\nonemind: {bogus: 1}\n")

    def test_join_code_fields(self):
        t = fb.parse_join_code(JOIN)
        self.assertEqual(t, {"code": "7KQ4-M2XP-9D3F", "ca": CA_SHA, "role": "worker", "hub": "https://home-box.local"})
        self.assertEqual(fb.parse_join_code(JOIN.replace("&role=worker", ""))["role"], "")

    def test_join_code_refuses_anything_else(self):
        bad = [
            "", "7KQ4-M2XP-9D3F", JOIN.replace("onemind-join:v1", "onemind-join:v2"),
            JOIN.replace("7KQ4-M2XP-9D3F", "7KQ4-M2XP"),                       # short code
            JOIN.replace(CA_SHA, "ab" * 31),                                   # short fingerprint
            JOIN.replace("role=worker", "role=hub"),
            JOIN.replace("https%3A%2F%2F", "http%3A%2F%2F"),                   # not https
            JOIN.replace("home-box.local", "home-box.local%2Fpath"),           # a path
            JOIN.replace("home-box.local", "user%40home-box.local"),           # user info
            JOIN.replace("hub=https%3A%2F%2Fhome-box.local", ""),              # no hub
            JOIN + "&code=AAAA-BBBB-CCCC",                                     # repeated field
            JOIN + "&x=1",                                                     # unknown field
            JOIN + " extra", JOIN + "\nrole=hub", JOIN.replace("&", ";"),
            "onemind-join:v1?" + "a" * 700,
        ]
        for b in bad:
            with self.assertRaises(fb.ConfigError, msg=b):
                fb.parse_join_code(b)

    def test_validate(self):
        self.assertEqual(fb.validate({"role": "HUB"}), {"role": "hub", "name": "OneMind"})
        w = fb.validate({"role": "worker", "join_code": JOIN})
        self.assertEqual(w, {"role": "worker", "name": "OneMind", "join_code": JOIN})
        lf = fb.validate({"role": "leaf", "join_code": LEAF_JOIN, "hub_addr": LAN})
        self.assertEqual(lf["hub_addr"], LAN)
        for bad in ({"role": "master"}, {"role": "worker"}, {"role": "worker", "join_code": "nope"},
                    {"role": "leaf", "join_code": JOIN},                       # the code is for a worker
                    {"role": "worker", "join_code": JOIN, "hub_addr": "hub.local"},
                    {"role": "hub", "join_code": JOIN}, {"role": "hub", "hub_addr": LAN},
                    {"role": "hub", "name": 'say "hi"'}):
            with self.assertRaises(fb.ConfigError, msg=bad):
                fb.validate(bad)


class Files(unittest.TestCase):
    def test_hosts_block_like_install_sh(self):
        with tempfile.TemporaryDirectory() as d:
            h = os.path.join(d, "hosts")
            open(h, "w").write("127.0.0.1\tlocalhost\n")
            ino = os.stat(h).st_ino
            self.assertTrue(fb.set_hosts(h, "127.0.0.1"))
            want = ("127.0.0.1\tlocalhost\n# BEGIN onemind fabric (managed by onemind fabric join)\n"
                    "127.0.0.1 control.onemind.internal join.onemind.internal\n# END onemind fabric\n")
            self.assertEqual(open(h).read(), want)
            self.assertEqual(os.stat(h).st_ino, ino)        # rewritten in place: /etc/hosts is a bind mount
            self.assertFalse(fb.set_hosts(h, "127.0.0.1"))  # idempotent
            fb.set_hosts(h, LAN)                            # the block is replaced, never doubled
            self.assertEqual(open(h).read().count("BEGIN onemind fabric"), 1)
            self.assertIn(f"{LAN} control.onemind.internal", open(h).read())

    def test_headscale_config(self):
        c = fb.headscale_config(LAN)
        for line in ("server_url: https://control.onemind.internal:8444", "listen_addr: 0.0.0.0:8444",
                     "tls_cert_path: /run/onemind-headscale/tls.crt", "tls_key_path: /run/onemind-headscale/tls.key",
                     "private_key_path: /var/lib/onemind-headscale/noise_private.key",
                     "private_key_path: /var/lib/onemind-headscale/derp_server_private.key",
                     "path: /var/lib/onemind-headscale/db.sqlite", f"ipv4: {LAN}", "v4: 100.64.0.0/10",
                     "unix_socket: /run/onemind-headscale/headscale.sock", "disable_check_updates: true",
                     "grpc_allow_insecure: false"):
            self.assertIn(line, c)
        self.assertRegex(c, r"logtail:\n  enabled: false")
        import yaml
        doc = yaml.safe_load(c)
        self.assertEqual(doc["derp"]["server"]["ipv4"], LAN)
        self.assertEqual(doc["derp"]["urls"], [])            # no DERP map from Tailscale Inc (NETWORKING S12)

    def test_hub_nats_conf(self):
        for conf in (fb.hub_nats_conf(None), fb.hub_nats_conf(MESH_IP)):
            self.assertIn("listen: 127.0.0.1:4222", conf)
            self.assertIn("http: 127.0.0.1:8222", conf)
            self.assertIn('include "nats-accounts.conf"', conf)
            self.assertNotIn("password", conf)
            self.assertNotIn("0.0.0.0", conf)
        self.assertNotIn("leafnodes", fb.hub_nats_conf(None))
        c = fb.hub_nats_conf(MESH_IP)
        self.assertIn(f'listen: "{MESH_IP}:7422"', c)
        self.assertIn("verify: true", c)
        for f in ("nats.crt", "nats.key", "ca.crt"):
            self.assertIn(f'"/run/onemind-nats/{f}"', c)

    def test_hub_nats_conf_has_bounded_jetstream_on_the_data_disk(self):
        cap = 3 << 30
        for conf in (fb.hub_nats_conf(None, cap), fb.hub_nats_conf(MESH_IP, cap)):
            self.assertIn('store_dir: "/var/lib/onemind-nats/jetstream"', conf)
            self.assertIn(f"max_file_store: {cap}", conf)
            self.assertIn("max_memory_store: 0", conf)  # a restart must not lose events silently
        p = fb.Paths("/x")
        env = fb.gateway_env(p, {"box": "b", "node_id": "n1", "name": "n"}, js_max_bytes=cap)
        self.assertIn(f"ONEMIND_FABRIC_JETSTREAM_MAX_BYTES={cap}", env)
        self.assertIn("ONEMIND_FABRIC_JETSTREAM_PATH=/var/lib/onemind-nats\n", env)

    def test_jetstream_cap_is_a_share_of_the_data_disk_and_never_missing(self):
        # #601: the cap follows /data (10 %, clamped), not a fixed 4 GiB; nats.conf and gateway.env agree.
        GIB = 1 << 30
        usage = lambda total: mock.patch("shutil.disk_usage", return_value=shutil._ntuple_diskusage(total, 0, total))
        with tempfile.TemporaryDirectory() as d:
            p = fb.Paths(d)
            os.makedirs(os.path.join(d, "data"))
            with usage(24 * GIB):
                cap = fb.jetstream_max_bytes(p)
                env = fb.gateway_env(p, {"box": "b", "node_id": "n1", "name": "n"})
            self.assertEqual(cap, int(24 * GIB * 0.10))
            self.assertIn(f"ONEMIND_FABRIC_JETSTREAM_MAX_BYTES={cap}\n", env)
            with usage(2000 * GIB):
                self.assertEqual(fb.jetstream_max_bytes(p), 64 * GIB)       # the ceiling
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                fb.hub_nats_conf(None, bad)                                # JetStream without a cap is refused

    def test_jetstream_refuses_a_data_disk_below_its_minimum(self):
        from onemind_core.jetstream import JetStreamCapError

        total = 2 << 30  # 10% of 2 GiB is below the 256 MiB floor
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "data")
            os.mkdir(path)
            with mock.patch("shutil.disk_usage", return_value=shutil._ntuple_diskusage(total, 0, total)) as disk:
                with self.assertRaisesRegex(JetStreamCapError, "too small for JetStream"):
                    fb.jetstream_max_bytes(fb.Paths(root))
            disk.assert_called_once_with(path)

    def test_hub_nats_refuses_to_start_jetstream_without_a_cap(self):
        # #601: onemind-nats-files runs the check before every start and reload, after the copies (it reads
        # the include too); a refusal fails the unit. The wrapper runs the parser with the gateway venv.
        wrapper = os.path.join(LIB, "onemind-nats-capcheck")
        files = open(os.path.join(LIB, "onemind-nats-files")).read()
        self.assertIn('/usr/lib/onemind/onemind-nats-capcheck "$d/nats.conf"', files)
        self.assertLess(files.index("copy /data/onemind/gateway/nats/accounts.conf"),
                        files.index('/usr/lib/onemind/onemind-nats-capcheck "$d/nats.conf"'))
        self.assertTrue(os.access(wrapper, os.X_OK))
        self.assertIn("venv/bin/python3 -I /usr/lib/onemind/onemind_nats_capcheck.py", open(wrapper).read())
        from onemind_core import natsconf
        cap = 2 << 30
        good = fb.hub_nats_conf(MESH_IP, cap)
        blk = 'jetstream {\n  store_dir: "/var/lib/onemind-nats/jetstream"\n  max_file_store: %s\n  max_memory_store: 0\n}\n' % cap
        self.assertIn(blk, good)
        base = good.replace(blk, "")  # the rest of the rendered conf, includes and the leaf listener too
        js = lambda text: base + text  # noqa: E731
        cases = {
            "rendered": (good, 0),
            "no jetstream (old box)": ("server_name: hub\nlisten: 127.0.0.1:4222\n", 0),
            "no file cap": (good.replace(f"  max_file_store: {cap}\n", ""), 1),
            "zero file cap": (good.replace(f"max_file_store: {cap}", "max_file_store: 0"), 1),
            "negative file cap (dynamic)": (good.replace(f"max_file_store: {cap}", "max_file_store: -1"), 1),
            "no memory cap": (good.replace("  max_memory_store: 0\n", ""), 1),
            "memory store": (good.replace("max_memory_store: 0", "max_memory_store: 1GB"), 1),
            "negative memory (dynamic)": (good.replace("max_memory_store: 0", "max_memory_store: -1"), 1),
            "alias": (good.replace("max_memory_store: 0", "max_memory_store: 0\n  max_mem: 1G"), 1),
            "alias only": (good.replace("max_memory_store: 0", "max_mem: 0"), 1),
            # nats-server turns JetStream on for all of these (conf/parse.go itemBool, opts.go parseJetStream)
            "jetstream enabled": ("server_name: hub\njetstream: enabled\n", 1),
            **{f"jetstream: {w}": (js(f"jetstream: {w}\n"), 1) for w in ("on", "yes", "enable", "True", "ENABLED")},
            "jetstream = on, comment": (js("jetstream = on  # no cap\n"), 1),
            "jetstream true, space separator": (js("jetstream true\n"), 1),
            "quoted key": (js('"jetstream": enabled\n'), 1),
            # off is off: nats-server starts without JetStream
            **{f"jetstream: {w}": (js(f"jetstream: {w}\n"), 0) for w in ("off", "false", "NO", "disabled")},
            # NATS lowercases keys: the check does too
            "JetStream block, no cap": (js("JetStream {\n  store_dir: /x\n}\n"), 1),
            "upper-case keys, capped": (js("JETSTREAM {\n  MAX_FILE_STORE: 4GB\n  Max_Memory_Store: 0\n}\n"), 0),
            "upper-case memory store": (good.replace("max_memory_store: 0", "MAX_MEMORY_STORE: 1GB"), 1),
            "jetstream twice, cases differ": (good + "JetStream: on\n", 1),
            # the limits count only inside the block
            "stray memory cap outside": (js("max_memory_store: 0\njetstream {\n  max_file_store: 4GB\n"
                                            "  max_memory_store: 4GB\n}\n"), 1),
            "stray file cap outside": (js("max_file_store: 4GB\njetstream {\n  max_memory_store: 0\n}\n"), 1),
            "cap only in a comment": (good.replace("max_memory_store: 0", "max_memory_store: 1GB # max_memory_store: 0"), 1),
            "last same-case key wins": (good.replace("max_memory_store: 0", "max_memory_store: 0\n  max_memory_store: 1G"), 1),
            "later block wins": (good + "jetstream: on\n", 1),
            "later capped block wins": (js("jetstream: on\n") + blk, 0),
            "inline block, = and space": (js("jetstream {max_file_store = 1G, max_memory_store 0}\n"), 0),
            "quoted size": (js('jetstream: {max_file_store: "4G", max_memory_store: "0K"}\n'), 0),
            "overflowing size": (js("jetstream {max_file_store: 9223372036854775807G, max_memory_store: 0}\n"), 1),
            "variable": (js("CAP: 4GB\njetstream {max_file_store: $CAP, max_memory_store: 0}\n"), 1),
            "size nats-server cannot read": (good.replace("max_memory_store: 0", "max_memory_store: 0B"), 1),
            "jetstream in an include": (good + 'include "more.conf"\n', 1),
            "missing include": (good.replace('include "nats-accounts.conf"', 'include "gone.conf"'), 1),
            "parse error": (good + "jetstream {\n", 1),
        }
        with tempfile.TemporaryDirectory() as d:
            # the real include, as the gateway writes it: its account-level max_mem must not count
            with open(os.path.join(d, "nats-accounts.conf"), "w") as f:
                f.write(natsconf.render_accounts([], (), jetstream_max_bytes=cap // 2))
            with open(os.path.join(d, "more.conf"), "w") as f:
                f.write("jetstream: on\n")
            for name, (conf, want) in cases.items():
                path = os.path.join(d, "nats.conf")
                with open(path, "w") as f:
                    f.write(conf)
                r = subprocess.run([sys.executable, "-I", os.path.join(LIB, "onemind_nats_capcheck.py"), path],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, want, f"{name}: {r.stderr}")
                if want:
                    self.assertIn("(#601)", r.stderr)

    def test_jetstream_store_is_a_bind_from_the_data_disk_owned_for_the_nats_user(self):
        base = os.path.join(ROOT, "os", "rootfs", "layers")
        fstab = open(os.path.join(base, "base", "etc", "fstab")).read()
        self.assertIn("/data/state/var-lib-onemind-nats ", fstab)
        script = open(os.path.join(LIB, "onemind-nats-files")).read()
        self.assertIn("/var/lib/onemind-nats/jetstream", script)
        unit = open(os.path.join(base, "onemind", "usr", "lib", "systemd", "system", "onemind-nats.service")).read()
        self.assertIn("ReadWritePaths=-/var/lib/onemind-nats", unit)

    def test_nats_files_script_copies_what_the_conf_names(self):
        script = open(os.path.join(LIB, "onemind-nats-files")).read()
        unit = open(os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "systemd", "system",
                                 "onemind-nats.service")).read()
        self.assertIn("copy /data/onemind/gateway/nats/accounts.conf nats-accounts.conf", script)
        self.assertIn("/data/onemind/gateway/tls/$f", script)
        self.assertIn("ExecStart=/usr/bin/nats-server -c /run/onemind-nats/nats.conf", unit)
        self.assertIn("ExecReload=+/usr/lib/onemind/onemind-nats-files", unit)
        self.assertNotIn("LoadCredential=", unit)


@needs_core
class Hub(Box):
    def first_boot(self):
        self.put("boot/efi/onemind.conf", "role = hub\nname = Home\n")
        fb.apply(self.p)
        return json.load(open(self.p.state))

    def test_first_boot_hub_then_reboot(self):
        st = self.first_boot()
        con = self.console()
        self.assertIn("ONEMIND-FIRSTBOOT: configured role=hub source=esp", con)
        toks = re.findall(r"ONEMIND OWNER TOKEN: ([0-9a-f]{64})$", con, re.M)
        self.assertEqual(len(toks), 1)
        self.assertNotIn(toks[0], self.out.getvalue())                   # never in the journal
        tokens = self.read(os.path.join(self.p.gateway, "tokens.yaml"))
        self.assertNotIn(toks[0], tokens)
        import hashlib
        self.assertIn("sha256:" + hashlib.sha256(toks[0].encode()).hexdigest(), tokens)
        self.assertIn("retire_on_setup: true", tokens)   # the gateway retires it once an owner exists
        self.assertTrue(os.path.exists(self.p.esp_conf + ".applied"))
        self.assertEqual((st["box"], st["mesh"]), ("home-box", 1))
        self.assertEqual(st["node_id"], self.etc("node-id").strip())
        # the join line names the hub's LAN address and the new way to join
        self.assertIn("onemind fabric ticket", con)
        self.assertIn(f"hub_addr = {LAN}", con)
        self.assertEqual(self.etc("lan-addr").strip(), LAN)
        for f in ("gateway.env", "onemindd.env", "nats.conf"):
            self.assertEqual(self.mode(os.path.join(self.p.etc, f)), 0o600, f)
        self.assertEqual(self.mode(self.p.etc), 0o711)
        self.assertEqual(self.mode(self.p.secrets), 0o700)
        self.assertEqual(self.started[-1][:2], ("start", "--no-block"))
        for u in ("onemind-gateway.service", "onemind-nats.service", "onemind-nats-accounts.path",
                  "onemind-mesh-setup.service", "tailscaled.service", "onemind-headscale.service"):
            self.assertIn(u, self.started[-1])
        before = {f: self.etc(f) for f in os.listdir(self.p.etc) if os.path.isfile(os.path.join(self.p.etc, f))}
        ca_before = self.read(os.path.join(self.p.tls, "ca.crt"))
        # reboot: nothing regenerated, no new token, same units started
        open(self.p.console, "w").close(); self.started.clear()
        fb.apply(self.p)
        self.assertIn("already configured role=hub", self.console())
        self.assertNotIn("OWNER TOKEN", self.console())
        self.assertNotIn("before the mesh", self.console())
        self.assertEqual(before, {f: self.etc(f) for f in before})
        self.assertEqual(ca_before, self.read(os.path.join(self.p.tls, "ca.crt")))
        self.assertIn("onemind-mesh-setup.service", self.started[-1])

    def test_one_box_ca(self):
        """identity/ca.pem is the gateway's CA (tailscaled trusts it); no second CA, no CA key outside tls/."""
        st = self.first_boot()
        ca = self.read(os.path.join(self.p.tls, "ca.crt"))
        self.assertEqual(self.read(os.path.join(self.p.identity, "ca.pem")), ca)
        self.assertEqual(self.mode(os.path.join(self.p.identity, "ca.pem")), 0o644)
        self.assertEqual(sorted(os.listdir(self.p.identity)), ["ca.pem"])
        self.assertEqual(self.mode(os.path.join(self.p.tls, "ca.key")), 0o600)
        from cryptography import x509
        cert = x509.load_pem_x509_certificate(ca.encode())
        import hashlib
        from cryptography.hazmat.primitives.serialization import Encoding
        self.assertEqual(st["ca_sha256"], hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest())
        self.assertTrue(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        for name in ("https", "control"):
            leaf = x509.load_pem_x509_certificate(open(os.path.join(self.p.tls, f"{name}.crt"), "rb").read())
            self.assertEqual(leaf.issuer, cert.subject)
            leaf.verify_directly_issued_by(cert)
        ctl = x509.load_pem_x509_certificate(open(os.path.join(self.p.tls, "control.crt"), "rb").read())
        self.assertIn("control.onemind.internal",
                      ctl.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
        self.assertFalse(os.path.exists(os.path.join(self.p.tls, "nats.crt")))   # needs the mesh IP first

    def test_nats_keys_and_conf(self):
        self.first_boot()
        conf = self.etc("nats.conf")
        self.assertIn("listen: 127.0.0.1:4222", conf)
        self.assertIn('include "nats-accounts.conf"', conf)
        self.assertNotIn("leafnodes", conf)                  # until `mesh` knows the hub's mesh address
        self.assertNotIn("password", conf)
        for name in ("gateway", "onemindd"):
            self.assertEqual(self.mode(os.path.join(self.p.nats_keys, f"{name}.nk")), 0o600)
            pub = self.read(os.path.join(self.p.nats_keys, f"{name}.pub")).strip()
            self.assertRegex(pub, r"^U[A-Z2-7]{55}$")
            self.assertIn(pub, self.read(self.p.accounts))
        env = self.etc("onemindd.env")
        self.assertIn("ONEMIND_NATS_URL=nats://127.0.0.1:4222\n", env)
        self.assertIn(f"ONEMIND_NATS_NKEY_SEED={self.p.nats_keys}/onemindd.nk\n", env)
        self.assertIn("ONEMIND_NODE_ROLE=hub", env)

    def test_gateway_env(self):
        st = self.first_boot()
        env = self.etc("gateway.env")
        g = self.p.gateway
        for line in (f"ONEMIND_NODE_ID={st['node_id']}", "ONEMIND_INSTANCE_NAME=Home",
                     "ONEMIND_SANDBOX_RULES=/usr/lib/onemind/sdk/policy/app-objects.yaml",
                     "ONEMIND_NATS_URL=nats://127.0.0.1:4222", "ONEMIND_PORT=8080",
                     "ONEMIND_NET_BOX_NAME=home-box", f"ONEMIND_NET_LAN_ADDR={LAN}", "ONEMIND_NET_TLS=1",
                     f"ONEMIND_NET_TLS_DIR={g}/tls", "ONEMIND_NET_MDNS=1",
                     "ONEMIND_FABRIC_HUB_URL=https://home-box.local",
                     f"ONEMIND_FABRIC_NATS_ACCOUNTS_FILE={g}/nats/accounts.conf",
                     f"ONEMIND_FABRIC_NATS_SERVICE_KEYS={self.p.nats_keys}",
                     f"ONEMIND_FABRIC_NATS_NKEY_SEED={self.p.nats_keys}/gateway.nk"):
            self.assertIn(line + "\n", env)
        # the mesh lines come with `mesh` (MeshSettings.validate refuses ENABLED=1 without HUB_IP)
        self.assertNotIn("ONEMIND_MESH_", env)
        self.assertNotIn("ONEMIND_FABRIC_K3S=1", env)
        self.assertNotIn("nats://gateway:", env)             # no password in the URL any more
        self.assertNotIn("@", env)
        with_mesh = fb.gateway_env(self.p, st, MESH_IP)
        for line in ("ONEMIND_MESH_ENABLED=1", "ONEMIND_MESH_HEADSCALE_URL=https://127.0.0.1:8444",
                     "ONEMIND_MESH_CONTROL_URL=https://control.onemind.internal:8444",
                     f"ONEMIND_MESH_HEADSCALE_KEY_FILE={self.p.hs_key}", f"ONEMIND_MESH_HUB_IP={MESH_IP}"):
            self.assertIn(line + "\n", with_mesh)

    def test_backup_is_wired_on_a_new_hub(self):
        st = self.first_boot()
        self.assertEqual(self.mode(self.p.job_key), 0o600)
        pub = os.path.join(self.p.backup, "job.pub")
        self.assertEqual(self.read(pub), self.read(os.path.join(self.p.custodian, "job.pub")))
        conf = json.load(open(self.p.backup_conf))
        self.assertEqual(conf, fb.backup_agent_conf(self.p, st["node_id"]))
        self.assertEqual(conf["targets"], [])               # the owner adds and approves a destination
        self.assertIn(f"ONEMIND_BACKUP_CONF={self.p.backup_conf}\n", self.etc("onemindd.env"))
        gw = self.etc("gateway.env")
        self.assertIn("ONEMIND_BACKUPS_ENABLED=1\n", gw)
        self.assertIn(f"ONEMIND_BACKUPS_JOB_KEY_FILE={self.p.job_key}\n", gw)
        self.assertIn("ONEMIND_BACKUPS_ENABLED=1\n", fb.gateway_env(self.p, st, MESH_IP))   # `mesh` rewrites the file

    def test_backup_catches_up_on_a_hub_set_up_before_it_and_keeps_its_key(self):
        st = self.first_boot()
        key = self.read(self.p.job_key)
        os.unlink(self.p.backup_conf)
        for name, marker in (("onemindd.env", "ONEMIND_BACKUP_CONF"), ("gateway.env", "ONEMIND_BACKUPS")):
            text = "".join(l for l in self.etc(name).splitlines(True) if marker not in l and "Backups" not in l)
            open(os.path.join(self.p.etc, name), "w").write(text)
        fb.apply(self.p)                                    # a reboot of the old box
        self.assertTrue(os.path.exists(self.p.backup_conf))
        self.assertEqual(self.read(self.p.job_key), key)    # never a new key: old jobs stay valid
        self.assertIn("ONEMIND_BACKUP_CONF=", self.etc("onemindd.env"))
        self.assertEqual(self.etc("gateway.env").count("ONEMIND_BACKUPS_ENABLED=1"), 1)
        fb.apply(self.p)
        self.assertEqual(self.etc("gateway.env").count("ONEMIND_BACKUPS_ENABLED=1"), 1)
        self.assertEqual(json.load(open(self.p.backup_conf))["node_id"], st["node_id"])

    def test_built_in_data_is_in_the_system_unit_on_a_new_hub(self):
        # #616: the gateway writes the built-ins' table export into backup-export before each run, and the
        # agent's system unit copies it with the files root, so photos and files reach restic.
        st = self.first_boot()
        system = json.load(open(self.p.backup_conf))["units"]["system"]
        self.assertEqual(system["paths"][-2:], [self.p.backup_export, self.p.files])
        self.assertEqual(self.mode(self.p.backup_export), 0o700)
        for gw in (self.etc("gateway.env"), fb.gateway_env(self.p, st, MESH_IP)):
            self.assertIn(f"ONEMIND_BACKUPS_EXPORT_DIR={self.p.backup_export}\n", gw)
            self.assertIn("ONEMIND_BACKUPS_AGENT_DIRS=ONEMIND_FILES_ROOT\n", gw)
        self.assertEqual(self.etc("gateway.env").count("ONEMIND_BACKUPS_EXPORT_DIR="), 1)

    def test_a_hub_set_up_before_616_gets_the_built_in_paths_and_keeps_the_rest(self):
        self.first_boot()
        conf = json.load(open(self.p.backup_conf))
        conf["units"]["system"]["paths"] = [self.p.etc, self.p.tls, self.p.nats_keys]  # the old agent.json
        conf["retention"]["daily"] = 9                                               # an owner's own change
        open(self.p.backup_conf, "w").write(json.dumps(conf))
        text = "".join(l for l in self.etc("gateway.env").splitlines(True)
                       if "EXPORT_DIR" not in l and "AGENT_DIRS" not in l and "#616" not in l)
        open(os.path.join(self.p.etc, "gateway.env"), "w").write(text)
        fb.apply(self.p)                                    # the reboot after the update
        fb.apply(self.p)
        got = json.load(open(self.p.backup_conf))
        self.assertEqual(got["units"]["system"]["paths"], fb.backup_system_paths(self.p))
        self.assertEqual(got["retention"]["daily"], 9)
        self.assertEqual({k: v for k, v in got.items() if k != "units"}, {k: v for k, v in conf.items() if k != "units"})
        self.assertEqual(self.etc("gateway.env").count("ONEMIND_BACKUPS_EXPORT_DIR="), 1)
        self.assertEqual(self.etc("gateway.env").count("ONEMIND_BACKUPS_ENABLED=1"), 1)

    def test_a_failed_job_key_leaves_backups_off_but_the_box_boots(self):
        with mock.patch("onemind_core.backups.jobs.load_or_create_job_key", side_effect=OSError("disk full")):
            st = self.first_boot()
        self.assertEqual(st["role"], "hub")
        self.assertNotIn("ONEMIND_BACKUPS_ENABLED", self.etc("gateway.env"))
        self.assertFalse(os.path.exists(self.p.backup_conf))
        self.assertIn("backups not set up: disk full", self.out.getvalue())

    def test_workers_get_no_backup_files(self):
        fb.ensure_backup(self.p, {"role": "worker", "node_id": "abc"})
        self.assertFalse(os.path.exists(self.p.backup))

    def test_old_box_keeps_its_units_and_gets_a_note(self):
        os.makedirs(os.path.dirname(self.p.state))
        open(self.p.state, "w").write(json.dumps({"schema": fb.SCHEMA, "role": "leaf", "node_id": "abc"}))
        fb.apply(self.p)
        self.assertIn("set up before the mesh", self.console())
        self.assertIn("reinstall", self.console())
        self.assertEqual(self.started[-1], ("start", "--no-block", "onemind-nats.service", "onemindd.service"))
        self.assertEqual(fb.mesh(self.p), 0)                 # an old hub is not touched either


class FakeMesh:
    """Stands in for headscale, tailscale and `onemindd mesh wait-ip`; records every call."""

    def __init__(self, test, joined=False):
        self.t, self.calls, self.joined, self.users = test, [], joined, []

    def __call__(self, argv, env=None):
        self.calls.append(list(argv))
        ok = lambda out="": fb.subprocess.CompletedProcess(argv, 0, out, "")
        fail = lambda: fb.subprocess.CompletedProcess(argv, 1, "", "not yet")
        if argv[0] == fb.HEADSCALE:
            args = argv[3:]
            if args[:2] == ["users", "list"]:
                return ok(json.dumps(self.users))
            if args[:2] == ["users", "create"]:
                self.users.append({"id": 1, "name": args[2]})
                return ok("User created")
            if args[:2] == ["preauthkeys", "create"]:
                return ok(json.dumps({"key": PREAUTH, "reusable": False}))
            if args[:2] == ["apikeys", "create"]:
                return ok("Some banner\n" + APIKEY + "\n")
        if argv[0] == fb.TAILSCALE and argv[1] == "up":
            keyfile = argv[argv.index("--auth-key") + 1].removeprefix("file:")
            self.t.assertEqual(open(keyfile).read(), PREAUTH)
            self.t.assertEqual(stat.S_IMODE(os.stat(keyfile).st_mode), 0o600)
            self.joined = True
            return ok()
        if argv[:3] == [fb.ONEMINDD, "mesh", "wait-ip"]:
            return ok(MESH_IP + "\n") if self.joined else fail()
        raise AssertionError(f"unexpected command {argv}")

    def names(self):
        out = []
        for a in self.calls:
            if a[0] == fb.HEADSCALE:
                out.append("hs " + " ".join(a[3:5]))
            elif a[0] == fb.TAILSCALE:
                out.append("tailscale " + a[1])
            else:
                out.append("wait-ip " + a[-1])
        return out


@needs_core
class Mesh(Box):
    def setUp(self):
        super().setUp()
        self.put("boot/efi/onemind.conf", "role = hub\n")
        fb.apply(self.p)
        self.put("run/onemind-headscale/headscale.sock", "")      # Headscale's socket is there
        self.put("etc/hosts", "127.0.0.1\tlocalhost\n")            # seeded by onemind-data-layout
        self.started.clear()
        self.fake = FakeMesh(self)
        pt = mock.patch.object(fb, "run_cmd", self.fake)
        pt.start(); self.addCleanup(pt.stop)
        open(self.p.console, "w").close()
        self.out.truncate(0)

    def test_mesh_steps_in_order(self):
        self.assertEqual(fb.mesh(self.p), 0)
        names = self.fake.names()
        self.assertEqual(names, ["hs users list", "wait-ip 5s", "hs users list", "hs users create",
                                 "hs users list", "hs preauthkeys create", "tailscale up", "wait-ip 60s",
                                 "hs apikeys create"])
        self.assertEqual(self.started[0], ("restart", "onemind-headscale.service"))
        self.assertIn(("start", "tailscaled.service"), self.started)
        self.assertEqual(self.started[-1], ("try-restart", "onemind-nats.service", "onemind-gateway.service"))
        up = next(a for a in self.fake.calls if a[0] == fb.TAILSCALE)
        for flag in ("--reset", "--login-server", "https://control.onemind.internal:8444", "--hostname", "hub",
                     "--accept-routes=false", "--accept-dns=false", "--ssh=false", "60s"):
            self.assertIn(flag, up)
        pk = next(a for a in self.fake.calls if a[3:5] == ["preauthkeys", "create"])
        self.assertIn("tag:onemind-hub,tag:onemind-k3s", pk)
        self.assertEqual(pk[pk.index("--expiration") + 1], "10m")
        self.assertEqual(pk[pk.index("--user") + 1], "1")
        self.assertFalse(os.path.exists(os.path.join(self.p.run, "hub-authkey")))   # the key file is gone
        # what it wrote
        self.assertEqual(self.read(self.p.hs_conf), fb.headscale_config(LAN))
        self.assertEqual(self.mode(self.p.hs_conf), 0o640)
        self.assertIn("127.0.0.1 control.onemind.internal join.onemind.internal", self.read(self.p.hosts))
        self.assertEqual(self.read(self.p.hs_key), APIKEY + "\n")
        self.assertEqual(self.mode(self.p.hs_key), 0o600)
        conf = self.etc("nats.conf")
        self.assertIn(f'listen: "{MESH_IP}:7422"', conf)
        self.assertIn("verify: true", conf)
        self.assertNotIn("password", conf)
        env = self.etc("gateway.env")
        self.assertIn(f"ONEMIND_MESH_HUB_IP={MESH_IP}\n", env)
        self.assertIn("ONEMIND_MESH_ENABLED=1\n", env)
        from cryptography import x509
        nats = x509.load_pem_x509_certificate(open(os.path.join(self.p.tls, "nats.crt"), "rb").read())
        ips = nats.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
        self.assertEqual([str(i) for i in ips], [MESH_IP])
        self.assertIn(f"mesh up: hub {MESH_IP} on the mesh", self.console())

    def test_no_secret_in_journal_or_console(self):
        fb.mesh(self.p)
        for where in (self.out.getvalue(), self.console()):
            self.assertNotIn(PREAUTH, where)
            self.assertNotIn(APIKEY, where)
            self.assertNotIn("hskey", where)

    def test_idempotent_every_boot(self):
        fb.mesh(self.p)
        files = {f: self.read(f) for f in (self.p.hs_conf, self.p.hs_key, self.p.hosts,
                                           os.path.join(self.p.etc, "nats.conf"), os.path.join(self.p.etc, "gateway.env"))}
        self.fake.calls.clear(); self.started.clear()
        self.put("var/lib/tailscale/tailscaled.state", "{}")     # tailscaled remembers its login
        self.assertEqual(fb.mesh(self.p), 0)
        self.assertEqual(self.fake.names(), ["hs users list", "wait-ip 60s", "wait-ip 60s"])  # no new key, no API key
        self.assertEqual(self.started, [("start", "onemind-headscale.service"), ("start", "tailscaled.service")])
        self.assertEqual(files, {f: self.read(f) for f in files})

    def test_headscale_down_fails_clearly_and_mints_nothing(self):
        os.remove(self.p.hs_sock)
        self.assertEqual(fb.mesh(self.p), 1)
        self.assertIn("mesh setup failed: Headscale did not start", self.console())
        self.assertNotIn("hs preauthkeys create", self.fake.names())
        self.assertNotIn("ONEMIND_MESH_", self.etc("gateway.env"))

    def test_lan_address_without_a_router(self):
        # QEMU's restrict=on network (and an offline LAN) leases an address with no default route.
        out = ("2: enp0s1    inet " + LAN + "/24 metric 1024 brd 192.0.2.255 scope global dynamic enp0s1\\\n"
               "3: tailscale0    inet 100.64.0.1/32 scope global tailscale0\\\n"
               "4: flannel.1    inet 198.51.100.0/32 scope global flannel.1\\\n"
               "5: cni0    inet 198.51.100.1/24 brd 198.51.100.255 scope global cni0\\\n")
        self.assertEqual(fb.only_lan_addr(out), LAN)
        two = out + "6: enp0s2    inet 203.0.113.5/24 scope global enp0s2\\\n"
        self.assertIsNone(fb.only_lan_addr(two))           # two LANs: no guessing
        self.assertIsNone(fb.only_lan_addr(""))

    def test_waits_for_a_late_ipv4_lease(self):
        os.remove(self.p.lan_file)                         # first boot ran before the DHCPv4 lease
        answers = [None, None, LAN]
        with mock.patch.object(fb, "lan_addr", lambda: answers.pop(0)):
            self.assertEqual(fb.mesh(self.p, sleep=lambda s: None), 0)
        self.assertEqual(self.read(self.p.lan_file), LAN + "\n")
        self.assertIn("mesh up", self.console())

    def test_no_ipv4_route_fails_clearly_and_starts_nothing(self):
        os.remove(self.p.lan_file)
        naps = []
        with mock.patch.object(fb, "lan_addr", lambda: None):
            self.assertEqual(fb.mesh(self.p, sleep=naps.append), 1)
        self.assertEqual(len(naps), fb.LAN_WAIT_S)
        self.assertIn("no LAN IPv4 address in 60 s", self.console())
        self.assertEqual(self.started, [])
        self.assertEqual(self.fake.names(), [])

    def test_no_mesh_address_leaves_gateway_alone(self):
        class NeverUp(FakeMesh):
            def __call__(fake, argv, env=None):
                r = super().__call__(argv, env)
                fake.joined = False                        # tailscale up "worked", but no address comes
                return r
        with mock.patch.object(fb, "run_cmd", NeverUp(self)):
            self.assertEqual(fb.mesh(self.p), 1)
        self.assertIn("did not get a mesh address", self.console())
        self.assertNotIn("ONEMIND_MESH_", self.etc("gateway.env"))
        self.assertNotIn("leafnodes", self.etc("nats.conf"))


class Node(Box):
    def test_worker_configure(self):
        self.put("boot/efi/onemind.conf", f"role = worker\njoin_code = {JOIN}\nhub_addr = {LAN}\n")
        fb.apply(self.p)
        self.assertEqual(self.read(self.p.join_code), JOIN + "\n")
        self.assertEqual(self.mode(self.p.join_code), 0o600)
        self.assertEqual(self.mode(self.p.secrets), 0o700)
        self.assertEqual(self.mode(self.p.etc), 0o711)
        st = json.load(open(self.p.state))
        self.assertEqual((st["hub"], st["hub_addr"], st["mesh"]), ("https://home-box.local", LAN, 1))
        # tailscaled's CA file and the fabric installer's identity dir are one place
        self.assertTrue(os.path.islink(self.p.identity))
        self.assertEqual(os.readlink(self.p.identity), os.path.join("etc", "identity"))
        env = self.etc("onemindd.env")
        self.assertIn("ONEMIND_NODE_ROLE=node", env)
        self.assertNotIn("@", env)
        for f in ("nats.conf", "gateway.env"):
            self.assertFalse(os.path.exists(os.path.join(self.p.etc, f)))
        self.assertNotIn("OWNER TOKEN", self.console())
        self.assertNotIn(JOIN, self.console() + self.out.getvalue())
        self.assertEqual(self.started[-1], ("start", "--no-block", "tailscaled.service", "onemind-nats-leaf.service",
                                            "onemindd.service", "onemind-fabric-join.service"))

    def test_leaf_has_no_hub_nats(self):
        self.put("boot/efi/onemind.conf", f"role = leaf\njoin_code = {LEAF_JOIN}\n")
        fb.apply(self.p)
        self.assertNotIn("onemind-nats.service", self.started[-1])
        self.assertIn("onemind-nats-leaf.service", self.started[-1])
        self.assertNotIn("hub_addr", json.load(open(self.p.state)))

    def test_bad_code_writes_nothing_and_starts_wizard(self):
        for conf in ("role = worker\n", f"role = worker\njoin_code = {JOIN[:-3]}%ZZ\n",
                     f"role = worker\njoin_token = {'a' * 64}\n"):
            self.put("boot/efi/onemind.conf", conf)
            fb.apply(self.p)
            self.assertIn("invalid settings", self.console())
            self.assertFalse(os.path.exists(self.p.etc))
            self.assertFalse(os.path.exists(self.p.join_code))

    def configured(self, addr=True):
        self.put("boot/efi/onemind.conf", f"role = worker\njoin_code = {JOIN}\n" + (f"hub_addr = {LAN}\n" if addr else ""))
        fb.apply(self.p)
        open(self.p.console, "w").close()
        self.out.truncate(0)

    def test_join_runs_the_cli_and_removes_the_code(self):
        self.configured()
        seen = []

        def fake(argv, env, on_line):
            seen.append((argv, env))
            on_line("Code        K7-42   <- check this matches the card on your phone")
            return 0
        with mock.patch.object(fb, "run_stream", fake):
            self.assertEqual(fb.join(self.p), 0)
        argv, env = seen[0]
        # The code is read from its 0600 file, never passed where the process list shows it.
        self.assertEqual(argv[:5], [fb.ONEMIND_CLI, "fabric", "join", "--code-file", self.p.join_code])
        self.assertNotIn(JOIN, " ".join(argv))
        self.assertEqual(argv[argv.index("--hub-addr") + 1], LAN)
        self.assertEqual(argv[argv.index("--timeout") + 1], "20m")
        self.assertEqual(env["ONEMIND_ETC_DIR"], self.p.etc)
        self.assertFalse(os.path.exists(self.p.join_code))
        self.assertIn("K7-42", self.console())                      # the match code the owner compares
        self.assertIn("joined the hub", self.console())
        self.assertNotIn(JOIN, self.console() + self.out.getvalue())

    def test_join_failure_keeps_code_and_says_what_to_do(self):
        self.configured(addr=False)
        with mock.patch.object(fb, "run_stream", lambda argv, env, on_line: 1):
            self.assertEqual(fb.join(self.p), 1)
        self.assertTrue(os.path.exists(self.p.join_code))
        con = self.console()
        self.assertIn("did not finish", con)
        self.assertIn("onemind fabric ticket", con)
        self.assertIn("Approvals", con)

    def test_join_without_hub_addr_and_after_join(self):
        self.configured(addr=False)
        calls = []
        with mock.patch.object(fb, "run_stream", lambda argv, env, on_line: calls.append(argv) or 0):
            fb.join(self.p)
        self.assertNotIn("--hub-addr", calls[0])
        # once fabric.json exists, the join never runs again and a stale code is removed
        self.put("data/onemind/secrets/join-code", JOIN + "\n")
        self.put("data/onemind/etc/fabric.json", "{}")
        calls.clear()
        with mock.patch.object(fb, "run_stream", lambda argv, env, on_line: calls.append(argv) or 0):
            self.assertEqual(fb.join(self.p), 0)
        self.assertEqual(calls, [])
        self.assertFalse(os.path.exists(self.p.join_code))

    def test_hub_has_nothing_to_join(self):
        self.assertEqual(fb.join(self.p), 0)


def in_process_helper(p):
    """The web part's helper client, wired to the root helper's own handle() (the same JSON both ways)."""
    return setup.Helper(call=lambda req: json.loads(json.dumps(setup_helper.handle(p, json.dumps(req).encode()))))


class Wizard(Box):
    def serve(self):
        setup.Wizard.helper = in_process_helper(self.p)
        setup.Wizard.done = threading.Event()
        srv = setup.ThreadingHTTPServer(("127.0.0.1", 0), setup.Wizard)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def test_form_asks_for_the_join_code(self):
        page = urllib.request.urlopen(self.serve() + "/").read().decode()
        self.assertIn('name="join_code"', page)
        self.assertIn('name="hub_addr"', page)
        self.assertIn("onemind fabric ticket", page)
        self.assertNotIn("join_token", page)

    @needs_core
    def test_wizard_configures_hub_and_shows_token_once(self):
        base = self.serve()
        self.assertIn("Set up this OneMind box", urllib.request.urlopen(base + "/").read().decode())
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/setup", data=b"role=worker&join_code=x")
        self.assertEqual(e.exception.code, 400)
        body = urllib.request.urlopen(base + "/setup", data=b"role=hub&name=Lab").read().decode()
        tok = re.search(r"<code>([0-9a-f]{64})</code>", body).group(1)
        self.assertIn(f"ONEMIND OWNER TOKEN: {tok}", self.console())
        self.assertFalse(os.path.exists(os.path.join(self.p.run, "owner-token")))   # shown once
        self.assertTrue(setup.Wizard.done.is_set())
        self.assertEqual(json.load(open(self.p.state))["source"], "wizard")
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/setup", data=b"role=hub")
        self.assertEqual(e.exception.code, 409)

    def test_wizard_configures_a_worker_with_a_join_code(self):
        from urllib.parse import urlencode
        base = self.serve()
        body = urllib.request.urlopen(base + "/setup", data=urlencode(
            {"role": "worker", "join_code": JOIN, "hub_addr": LAN}).encode()).read().decode()
        self.assertIn("Approvals", body)
        self.assertEqual(self.read(self.p.join_code), JOIN + "\n")
        self.assertEqual(json.load(open(self.p.state))["hub_addr"], LAN)


class WizardLockdown(Box):
    """From a device on the LAN the wizard needs the one-time code; after setup it refuses the LAN."""

    def serve(self):
        setup.Wizard.helper = in_process_helper(self.p)
        setup.Wizard.done = threading.Event()
        srv = setup.ThreadingHTTPServer(("127.0.0.1", 0), setup.Wizard)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}"

    def lan(self):
        patcher = mock.patch.object(setup, "is_local", return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        setup.Wizard.gate = setup.Gate()
        return setup.Wizard.gate.new(in_process_helper(self.p).publish_code)

    def post(self, base, data):
        try:
            return urllib.request.urlopen(base + "/setup", data=data)
        except urllib.error.HTTPError as e:
            return e

    def test_lan_needs_the_code_and_the_screen_can_read_it(self):
        base = self.serve()
        code = self.lan()
        f = os.path.join(self.p.run, "setup-code")
        self.assertEqual(self.read(f).strip(), code)
        self.assertEqual(os.stat(f).st_mode & 0o777, 0o600)
        self.assertIn('name="code"', urllib.request.urlopen(base + "/").read().decode())
        self.assertEqual(self.post(base, b"role=hub&name=Lab").code, 403)
        wrong = "00000000" if code != "00000000" else "11111111"
        self.assertEqual(self.post(base, f"role=hub&name=Lab&code={wrong}".encode()).code, 403)
        self.assertFalse(os.path.exists(self.p.state))
        self.assertEqual(self.post(base, f"role=worker&code={code}".encode()).code, 400)  # code ok, form bad

    def test_wrong_codes_back_off_and_keep_the_code(self):
        base = self.serve()
        first = self.lan()
        self.assertEqual(len(first), setup.CODE_LEN)
        for _ in range(setup.MAX_WRONG):
            self.post(base, b"role=hub&code=x")
        f = os.path.join(self.p.run, "setup-code")
        self.assertEqual(self.read(f).strip(), first)      # not rotated: no fresh target for a guesser
        # locked out: even the right code is refused until the back-off ends
        self.assertEqual(self.post(base, f"role=worker&code={first}".encode()).code, 429)

    def test_gate_backoff_doubles_and_ends(self):
        now = [1000.0]
        g = setup.Gate(clock=lambda: now[0])
        g.new(in_process_helper(self.p).publish_code)
        right = g.code
        for _ in range(setup.MAX_WRONG):
            self.assertFalse(g.check("nope"))
        self.assertEqual(g.locked(), setup.LOCK_MIN_S)
        self.assertFalse(g.check(right))
        now[0] += setup.LOCK_MIN_S + 1
        for _ in range(setup.MAX_WRONG):
            self.assertFalse(g.check("nope"))
        self.assertEqual(g.locked(), setup.LOCK_MIN_S * 2)
        now[0] += setup.LOCK_MIN_S * 2 + 1
        self.assertTrue(g.check(right.lower()))            # owner can still get in after the wait

    def test_guess_rate_is_capped(self):
        now = [0.0]
        g = setup.Gate(clock=lambda: now[0])
        g.new(in_process_helper(self.p).publish_code)
        tries = 0
        for _ in range(100000):                            # a flood of guesses over one simulated hour
            now[0] += 3600 / 100000
            if g.locked() == 0:
                tries += 1
            g.check("AAAAAAAAAA")
        self.assertLess(tries, 50)   # unlimited would be 100000

    def test_lan_is_refused_after_the_owner_exists(self):
        base = self.serve()
        code = self.lan()
        self.put("data/onemind/firstboot/state.json", json.dumps({"role": "hub", "node_id": "n"}))
        self.assertEqual(self.post(base, f"role=hub&code={code}".encode()).code, 403)
        for path in ("/", "/healthz"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(base + path)
            self.assertEqual(e.exception.code, 403)

    def test_lan_cannot_probe_healthz_before_setup(self):
        base = self.serve()
        self.lan()
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/healthz")
        self.assertEqual(e.exception.code, 403)

    def test_the_box_itself_needs_no_code(self):
        base = self.serve()
        self.assertEqual(urllib.request.urlopen(base + "/healthz").read(), b"setup")
        self.assertNotIn('name="code"', urllib.request.urlopen(base + "/").read().decode())

    def test_is_local(self):
        for a in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            self.assertTrue(setup.is_local(a), a)
        for a in ("192.0.2.5", "fe80::1%eth0", "nonsense"):
            self.assertFalse(setup.is_local(a), a)


class WizardUnit(unittest.TestCase):
    UNIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "os", "rootfs", "layers",
                        "onemind", "usr", "lib", "systemd", "system", "onemind-setup.service")

    def test_directives(self):
        text = open(self.UNIT).read()
        for d in ("ProtectSystem=strict", "NoNewPrivileges=yes", "SystemCallFilter=@system-service",
                  "DynamicUser=yes", "MemoryDenyWriteExecute=yes",
                  "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX", "ProtectKernelLogs=yes"):
            self.assertIn(d, text)
        # #578: the web part holds no capability; the root helper (onemind-setup-helper@.service) holds the three
        self.assertRegex(text, r"(?m)^CapabilityBoundingSet=$")
        self.assertNotRegex(text, r"(?m)^[^#]*CAP_(CHOWN|DAC_OVERRIDE|FOWNER)")
        helper_unit = open(os.path.join(os.path.dirname(self.UNIT), "onemind-setup-helper@.service")).read()
        self.assertIn("CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE CAP_FOWNER", helper_unit)

    @unittest.skipUnless(shutil.which("systemd-analyze"), "needs systemd-analyze")
    def test_security_score_is_under_5(self):
        # --threshold is on the 0..100 exposure scale: 49 = under 5.0 on the 0..10 scale of the table
        r = subprocess.run(["systemd-analyze", "security", "--offline=true", "--threshold=49",
                            "--no-pager", self.UNIT], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


FIRSTBOOT_SRC = os.path.join(LIB, "onemind_firstboot.py")


class NoSharedSecret(unittest.TestCase):
    """CORE-SEC-5 (#274): the first-boot code holds no shared NATS password, no passwordless user, no
    `nats_tls` switch and no all-interfaces client port, anywhere, not only in the confs it writes."""

    def test_source_has_none_of_the_old_nats_config(self):
        src = open(FIRSTBOOT_SRC).read()
        self.assertNotIn("def nats_conf", src)               # the old password writer
        for needle in ("nats_tls", "join_token", "0.0.0.0:4222", "0.0.0.0:7422", 'user: "node"',
                       "authorization {", "authorization{"):
            self.assertNotIn(needle, src, needle)
        self.assertNotRegex(src, r"nats://(gateway|onemindd|node):")   # no password in a URL

    @needs_core
    def test_conf_never_lists_a_user_or_a_password(self):
        for conf in (fb.hub_nats_conf(None), fb.hub_nats_conf(MESH_IP)):
            self.assertNotRegex(conf, r"(?mi)^\s*(users?|password|pass|token|authorization)\b")
            self.assertNotIn("0.0.0.0", conf)
        # the client port is the loopback one, and it is the only non-leaf listener
        self.assertRegex(fb.hub_nats_conf(MESH_IP), r"(?m)^listen: 127\.0\.0\.1:4222$")


@needs_core
class LegacyHubAfterUpdate(Box):
    """A hub that ran the pre-mesh first boot (state.json has no "mesh", its own nats.conf with the old
    config) must keep running after an image update: first boot leaves its files alone, starts the units
    it had, and `mesh` does not rewrite its NATS config (the reinstall note says how to move it)."""
    LEGACY_CONF = LEGACY = ("server_name: hub\nlisten: 0.0.0.0:4222\n"
                            'leafnodes { listen: 0.0.0.0:7422, authorization { user: "node", password: "x" } }\n')

    def test_old_hub_is_left_as_it_is(self):
        os.makedirs(self.p.etc)
        self.put("data/onemind/etc/nats.conf", self.LEGACY_CONF)
        os.makedirs(os.path.dirname(self.p.state), exist_ok=True)
        open(self.p.state, "w").write(json.dumps({"schema": fb.SCHEMA, "role": "hub", "node_id": "abc"}))
        self.assertEqual(fb.apply(self.p), 0)
        self.assertEqual(self.etc("nats.conf"), self.LEGACY_CONF)
        self.assertIn("reinstall", self.console())
        # Assert the four legacy units as a subset, so other hub units main adds later
        # (rescue console, host serve) do not break this test.
        started = self.started[-1]
        self.assertEqual(started[:2], ("start", "--no-block"))
        for unit in ("onemind-nats.service", "onemindd.service",
                     "onemind-gateway.service", "onemind-gateway-kube.service"):
            self.assertIn(unit, started)
        self.assertEqual(fb.mesh(self.p), 0)
        self.assertEqual(self.etc("nats.conf"), self.LEGACY_CONF)    # `mesh` is a no-op for it too


@needs_core
class HubAccounts(Box):
    """The hub's first boot makes the pieces the image battery relies on: real service keys that the
    accounts file names, and a nats.conf that nats-server itself accepts."""

    def test_accounts_file_has_service_keys_and_per_node_accounts_are_separate(self):
        from pathlib import Path

        from onemind_core import natsconf
        self.put("boot/efi/onemind.conf", "role = hub\nname = Home\n")
        fb.apply(self.p)
        acc = self.read(self.p.accounts)
        for name in ("gateway", "onemindd"):
            self.assertIn(self.read(os.path.join(self.p.nats_keys, f"{name}.pub")).strip(), acc)
        # #620: the observer's key is in the SYS account, never in the hub account
        obs = self.read(os.path.join(self.p.nats_keys, "observer.pub")).strip()
        self.assertIn(obs, acc)
        self.assertIn("system_account: SYS", acc)
        self.assertNotIn(obs, acc.split("  SYS: {")[0])
        # adding two node accounts gives each its own account (no shared node user)
        a, b = natsconf.new_user_key()[1], natsconf.new_user_key()[1]
        out = natsconf.render_accounts([natsconf.NodeAccount("n1", a), natsconf.NodeAccount("n2", b)],
                                       natsconf.load_service_keys(Path(self.p.nats_keys)))
        self.assertIn(a, out)
        self.assertIn(b, out)
        self.assertIn("NODE_n1", out)
        self.assertIn("NODE_n2", out)                          # one account per node
        self.assertNotIn("password", out)

    def test_a_hub_set_up_before_the_observer_gets_its_key_at_the_next_boot(self):
        # #620: a box updated through RAUC never ran the first-boot key step again
        self.put("boot/efi/onemind.conf", "role = hub\nname = Home\n")
        fb.apply(self.p)
        seed, pub = (os.path.join(self.p.nats_keys, f"observer.{x}") for x in ("nk", "pub"))
        os.remove(seed)
        os.remove(pub)
        fb.apply(self.p)                       # an ordinary later boot
        self.assertTrue(os.path.isfile(seed) and os.path.isfile(pub))
        kept = self.read(pub)
        fb.apply(self.p)                       # and a third boot keeps it
        self.assertEqual(self.read(pub), kept)

    @unittest.skipUnless(__import__("shutil").which("nats-server"), "needs nats-server")
    def test_nats_server_accepts_the_hub_conf(self):
        import subprocess
        self.put("boot/efi/onemind.conf", "role = hub\nname = Home\n")
        fb.apply(self.p)
        d = os.path.join(self.tmp.name, "natsrun")
        os.makedirs(d)
        open(os.path.join(d, "nats.conf"), "w").write(self.etc("nats.conf"))
        open(os.path.join(d, "nats-accounts.conf"), "w").write(self.read(self.p.accounts))
        r = subprocess.run(["nats-server", "-t", "-c", os.path.join(d, "nats.conf")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class ChownTreeRace(unittest.TestCase):
    """Issue #391 (cloud C4): a file that vanishes while the tree is re-owned must not fail first boot."""

    def test_vanished_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("a", "gone", "z"):
                open(os.path.join(d, n), "w").close()
            seen = []

            def chown(path, uid, gid):
                if os.path.basename(path) == "gone":
                    raise FileNotFoundError(path)
                seen.append(os.path.basename(path))

            with mock.patch.object(fb.os, "chown", chown):
                fb.chown_tree(d, (961, 961))
            self.assertEqual(sorted(seen), sorted([os.path.basename(d), "a", "z"]))

    def test_other_errors_still_fail(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(fb.os, "chown", side_effect=PermissionError("no")):
                with self.assertRaises(PermissionError):
                    fb.chown_tree(d, (961, 961))


if __name__ == "__main__":
    unittest.main()
