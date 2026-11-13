# SPDX-License-Identifier: Apache-2.0
"""onemind-firstboot and the setup wizard (docs/leap/core/IMAGES.md §3), against a temp root."""
import json, os, re, shutil, stat, subprocess, sys, tempfile, threading, unittest, urllib.error, urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "os", "rootfs", "layers", "onemind", "usr", "lib", "onemind")
sys.path.insert(0, LIB)
import onemind_firstboot as fb  # noqa: E402
import onemind_setup as setup  # noqa: E402

JOIN = "a" * 64
REAL_MAKE_CA = fb.make_ca


def fake_ca(p):
    os.makedirs(p.identity, exist_ok=True)
    open(os.path.join(p.identity, "ca.pem"), "w").write("CA")
    return "created"


class Box(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = fb.Paths(self.tmp.name)
        os.makedirs(os.path.join(self.tmp.name, "dev"))
        open(self.p.console, "w").close()
        self.started = []
        patches = [mock.patch.object(fb, "systemctl", lambda *a: self.started.append(a)),
                   mock.patch.object(fb, "make_ca", fake_ca),
                   mock.patch.object(fb, "find_seed_device", lambda: None),
                   mock.patch.object(fb.time, "sleep", lambda s: None)]
        for pt in patches:
            pt.start()
            self.addCleanup(pt.stop)

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


class Parsing(unittest.TestCase):
    def test_conf_lines_comments_quotes(self):
        self.assertEqual(fb.parse_conf("# c\nrole = hub  # inline\nname = \"My box\"\n\n"),
                         {"role": "hub", "name": "My box"})

    def test_conf_rejects_unknown_key_and_garbage(self):
        with self.assertRaises(fb.ConfigError):
            fb.parse_conf("rolle = hub\n")
        with self.assertRaises(fb.ConfigError):
            fb.parse_conf("role hub\n")

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

    def test_validate(self):
        self.assertEqual(fb.validate({"role": "HUB"}), {"role": "hub", "name": "OneMind"})
        w = fb.validate({"role": "worker", "hub": "http://hub.local:8080/x", "join_token": JOIN})
        self.assertEqual((w["hub"], w["join_token"]), ("hub.local", JOIN))
        self.assertEqual(fb.validate({"role": "leaf", "hub": "[fd00::1]:7422", "join_token": JOIN})["hub"], "[fd00::1]")
        for bad in ({"role": "master"}, {"role": "worker", "join_token": JOIN},
                    {"role": "worker", "hub": "h", "join_token": "short"},
                    {"role": "leaf", "hub": "bad host!", "join_token": JOIN},
                    {"role": "hub", "name": 'say "hi"'}):
            with self.assertRaises(fb.ConfigError, msg=bad):
                fb.validate(bad)


class Apply(Box):
    def test_nocloud_seed_wins_over_esp(self):
        self.put("var/lib/cloud/instance/user-data.txt", "#cloud-config\nonemind:\n  role: hub\n")
        self.put("boot/efi/onemind.conf", f"role = worker\nhub = h\njoin_token = {JOIN}\n")
        self.assertEqual(fb.apply(self.p), 0)
        st = json.load(open(self.p.state))
        self.assertEqual((st["role"], st["source"]), ("hub", "nocloud"))
        self.assertTrue(os.path.exists(self.p.esp_conf))      # untouched: the seed won

    def test_first_boot_hub_then_reboot(self):
        self.put("boot/efi/onemind.conf", "role = hub\nname = Home\n")
        fb.apply(self.p)
        con = self.console()
        self.assertIn("ONEMIND-FIRSTBOOT: configured role=hub source=esp", con)
        toks = re.findall(r"ONEMIND OWNER TOKEN: ([0-9a-f]{64})$", con, re.M)
        self.assertEqual(len(toks), 1)
        tokens = self.read(os.path.join(self.p.gateway, "tokens.yaml"))
        self.assertNotIn(toks[0], tokens)                     # only the hash is stored
        import hashlib
        self.assertIn("sha256:" + hashlib.sha256(toks[0].encode()).hexdigest(), tokens)
        self.assertFalse(os.path.exists(self.p.esp_conf))
        self.assertTrue(os.path.exists(self.p.esp_conf + ".applied"))
        st = json.load(open(self.p.state))
        node_id = self.read(os.path.join(self.p.etc, "node-id")).strip()
        self.assertEqual(st["node_id"], node_id)
        self.assertRegex(node_id, r"^[0-9a-f]{12}$")
        env = self.read(os.path.join(self.p.etc, "gateway.env"))
        self.assertIn(f"ONEMIND_NODE_ID={node_id}", env)
        self.assertIn("ONEMIND_INSTANCE_NAME=Home", env)
        # the kubernetes executor refuses to start without the install sandbox rules (healthz would never answer)
        self.assertIn("ONEMIND_SANDBOX_RULES=/usr/lib/onemind/sdk/policy/app-objects.yaml", env)
        self.assertIn(f"ONEMIND_NODE_ID={node_id}", self.read(os.path.join(self.p.etc, "onemindd.env")))
        for f in ("gateway.env", "onemindd.env", "nats.conf"):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.p.etc, f)).st_mode), 0o600, f)
        self.assertEqual(stat.S_IMODE(os.stat(self.p.secrets).st_mode), 0o700)
        conf = self.read(os.path.join(self.p.etc, "nats.conf"))
        join = self.read(os.path.join(self.p.secrets, "join-token")).strip()
        self.assertIn(json.dumps(join), conf)
        self.assertIn("leafnodes", conf)
        self.assertEqual(self.started[-1][:2], ("start", "--no-block"))
        self.assertIn("onemind-gateway.service", self.started[-1])
        before = {f: self.read(os.path.join(self.p.etc, f)) for f in os.listdir(self.p.etc)}
        # reboot: nothing regenerated, no new token, same units started
        open(self.p.console, "w").close(); self.started.clear()
        fb.apply(self.p)
        self.assertIn("already configured role=hub", self.console())
        self.assertNotIn("OWNER TOKEN", self.console())
        self.assertEqual(before, {f: self.read(os.path.join(self.p.etc, f)) for f in os.listdir(self.p.etc)})
        self.assertIn("onemind-gateway.service", self.started[-1])

    def test_worker_uses_hub_nats(self):
        self.put("boot/efi/onemind.conf", f"role = worker\nhub = hub.local\njoin_token = {JOIN}\n")
        fb.apply(self.p)
        env = self.read(os.path.join(self.p.etc, "onemindd.env"))
        self.assertIn(f"ONEMIND_NATS_URL=nats://node:{JOIN}@hub.local:4222", env)
        self.assertIn("ONEMIND_NODE_ROLE=node", env)
        self.assertFalse(os.path.exists(os.path.join(self.p.etc, "nats.conf")))
        self.assertFalse(os.path.exists(os.path.join(self.p.etc, "gateway.env")))
        self.assertNotIn("OWNER TOKEN", self.console())
        self.assertEqual(self.started[-1], ("start", "--no-block", "onemindd.service"))

    def test_leaf_forwards_to_hub(self):
        self.put("boot/efi/onemind.conf", f"role = leaf\nhub = hub.local\njoin_token = {JOIN}\n")
        fb.apply(self.p)
        conf = self.read(os.path.join(self.p.etc, "nats.conf"))
        self.assertIn(f'"nats-leaf://node:{JOIN}@hub.local:7422"', conf)
        self.assertIn("listen: 127.0.0.1:4222", conf)
        self.assertIn("nats://onemindd:", self.read(os.path.join(self.p.etc, "onemindd.env")))

    def test_nothing_configured_starts_wizard(self):
        fb.apply(self.p)
        self.assertIn("waiting for the setup wizard", self.console())
        self.assertEqual(self.started, [("start", "--no-block", "onemind-setup.service")])
        self.assertFalse(os.path.exists(self.p.state))

    def test_invalid_settings_start_wizard_and_write_nothing(self):
        self.put("boot/efi/onemind.conf", "role = worker\n")
        fb.apply(self.p)
        self.assertIn("invalid settings", self.console())
        self.assertFalse(os.path.exists(self.p.etc))

    def test_existing_ca_is_kept(self):
        os.makedirs(self.p.identity)
        open(os.path.join(self.p.identity, "ca.pem"), "w").write("from the CA module")
        self.assertEqual(REAL_MAKE_CA(self.p), "kept")


class Wizard(Box):
    def test_wizard_configures_hub_and_shows_token_once(self):
        setup.Wizard.paths = self.p
        setup.Wizard.done = threading.Event()
        srv = setup.ThreadingHTTPServer(("127.0.0.1", 0), setup.Wizard)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.assertIn("Set up this OneMind box", urllib.request.urlopen(base + "/").read().decode())
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/setup", data=b"role=worker&hub=h")
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


class NatsTls(unittest.TestCase):
    """NATS leaf-node TLS (SECURITY CORE-SEC-4): off by default, on when cfg nats_tls is set."""
    PW = {"gateway": "g", "onemindd": "o", "node": "n"}

    def test_off_by_default_changes_nothing(self):
        c = fb.nats_conf("hub", self.PW, {})
        self.assertNotIn("tls {", c)
        self.assertIn("leaf-node TLS off", c)

    def test_hub_tls_uses_cert_and_key_of_the_unit(self):
        c = fb.nats_conf("hub", self.PW, {}, tls=True)
        self.assertIn('/run/onemind-nats/nats-server.pem', c)
        self.assertIn('/run/onemind-nats/nats-server.key', c)
        self.assertIn("listen: 0.0.0.0:7422, tls", c)

    def test_leaf_trusts_only_the_hub_ca(self):
        c = fb.nats_conf("leaf", self.PW, {"join_token": "t" * 32, "hub": "hub.local"}, tls=True)
        self.assertIn('ca_file: "/run/onemind-nats/nats-ca.pem"', c)

    def test_validate_reads_the_switch(self):
        self.assertTrue(fb.validate({"role": "hub", "nats_tls": "yes"}).get("nats_tls"))
        self.assertNotIn("nats_tls", fb.validate({"role": "hub"}))

    @unittest.skipUnless(shutil.which("openssl"), "openssl missing")
    def test_issue_cert_is_signed_by_the_box_ca_and_key_is_private(self):
        with tempfile.TemporaryDirectory() as d:
            p = fb.Paths(d)
            os.makedirs(p.etc)
            fb.make_ca(p)
            fb.issue_nats_cert(p, "box")
            self.assertEqual(os.stat(os.path.join(p.etc, "nats-server.key")).st_mode & 0o777, 0o600)
            r = subprocess.run(["openssl", "verify", "-CAfile", os.path.join(p.identity, "ca.pem"),
                                os.path.join(p.etc, "nats-server.pem")], capture_output=True, text=True)
            self.assertIn("OK", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(p.etc, "nats-server.csr")))


if __name__ == "__main__":
    unittest.main()
