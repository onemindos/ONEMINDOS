# SPDX-License-Identifier: Apache-2.0
"""Root keys on hardware tokens and the root rotation (REL-02, #272), tested with SoftHSM.

SoftHSM is a software PKCS#11 token: three throwaway tokens are made in a temp directory, each with
an ECDSA P-256 key, and a version-1 root (three ed25519 file keys, 2-of-3) is rotated to a version-2
root held by the three token keys. No real key is involved and nothing here ever signs a real root.

Needs the pinned python-tuf and python-pkcs11 (os/update/requirements-tuf.txt) and SoftHSM
(apt-get install softhsm2); skipped when any is missing. CI installs all three
(.github/workflows/security-nightly.yml, job unit)."""
import contextlib, copy, io, os, shutil, subprocess, sys, tempfile, unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import UPDATE, load  # noqa: E402
from test_tuf_repo import release  # noqa: E402

try:
    tr = load("tuf-repo")
    import pkcs11, pkcs11.util.ec  # noqa: E401
except ImportError:               # pragma: no cover
    tr = pkcs11 = None

REPO = os.path.normpath(os.path.join(UPDATE, "..", ".."))
SCRIPT = os.path.join(REPO, "scripts", "tuf-bootstrap-root.sh")
SOFTHSM_UTIL = os.environ.get("SOFTHSM2_UTIL") or shutil.which("softhsm2-util")
LIB_CANDIDATES = [os.environ.get("SOFTHSM2_LIB", ""), "/usr/lib/softhsm/libsofthsm2.so",
                  "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so", "/usr/lib/aarch64-linux-gnu/softhsm/libsofthsm2.so",
                  "/usr/local/lib/softhsm/libsofthsm2.so", "/opt/homebrew/lib/softhsm/libsofthsm2.so"]
SOFTHSM_LIB = next((p for p in LIB_CANDIDATES if p and os.path.exists(p)), None)
WHY = ("python-tuf, python-pkcs11 and SoftHSM are needed (pip install --require-hashes -r "
       "os/update/requirements-tuf.txt; apt-get install softhsm2)")
PIN, SO_PIN, PASS = "123456", "654321", "throwaway-test-passphrase"      # throwaway, tests only
KEY_ID = 2                                                                 # PIV slot 9c, securesystemslib's default
LABELS = {h: f"onemind-test-{h}" for h in "abc"}


def spec(holder):
    return f"hsm:{KEY_ID}?label={LABELS[holder]}"


def init_token(label):
    subprocess.run([SOFTHSM_UTIL, "--module", SOFTHSM_LIB, "--init-token", "--free", "--label", label, "--so-pin", SO_PIN, "--pin", PIN],
                   check=True, capture_output=True)


def make_key(label):
    """An ECDSA P-256 key made ON the token, not extractable: the private key can never be read out
    (what the runbook asks of a YubiKey too)."""
    token = pkcs11.lib(SOFTHSM_LIB).get_token(token_label=label)
    with token.open(rw=True, user_pin=PIN) as session:
        params = session.create_domain_parameters(
            pkcs11.KeyType.EC, {pkcs11.Attribute.EC_PARAMS: pkcs11.util.ec.encode_named_curve_parameters("secp256r1")},
            local=True)
        params.generate_keypair(store=True, id=pkcs11.util.biginteger(KEY_ID), label="onemind-root",
                                private_template={pkcs11.Attribute.EXTRACTABLE: False, pkcs11.Attribute.SENSITIVE: True})


def script_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ("CI", "GITHUB_ACTIONS", "ONEMIND_TUF_PASSPHRASE")}
    env["PYTHON"] = sys.executable
    env.update(extra)
    return env


class Installed(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ONEMIND_TUF_REQUIRE_HSM"), "CI sets ONEMIND_TUF_REQUIRE_HSM")
    def test_the_token_tools_are_there_so_the_tests_below_do_not_skip_in_ci(self):
        self.assertTrue(tr is not None and SOFTHSM_UTIL and SOFTHSM_LIB, WHY)


@unittest.skipIf(tr is None or not SOFTHSM_UTIL or not SOFTHSM_LIB, WHY)
class TokenRoot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        cls.env = None
        try:
            os.makedirs(os.path.join(cls.d, "tokens"))
            conf = os.path.join(cls.d, "softhsm2.conf")
            with open(conf, "w") as f:
                f.write(f"directories.tokendir = {os.path.join(cls.d, 'tokens')}\nobjectstore.backend = file\n"
                        "log.level = ERROR\n")
            cls.env = unittest.mock.patch.dict(os.environ, {"SOFTHSM2_CONF": conf, "PYKCS11LIB": SOFTHSM_LIB,
                                                            tr.PIN_ENV: PIN, tr.PASSPHRASE_ENV: PASS})
            cls.env.start()                   # before the PKCS#11 library is first loaded in this process
            for h in "abc":                   # all tokens first: SoftHSM lists its slots when it is loaded
                init_token(LABELS[h])
            for h in "abc":
                make_key(LABELS[h])
            # version 1: what the image ships today: three encrypted file keys, 2-of-3, holder C absent
            for h in "abc":
                tr.keygen(cls.p("sticks", h), ["root"], encrypt=True)
            tr.keygen(cls.p("online"), ["targets", "snapshot", "timestamp"])
            cls.stick = {h: cls.p("sticks", h, "root.key") for h in "abc"}
            tr.init_root([cls.stick["a"], cls.stick["b"]], [cls.p("sticks", "c", "root.pub")], 2,
                         cls.p("online", "targets.pub"), cls.p("online", "snapshot.pub"),
                         cls.p("online", "timestamp.pub"), cls.p("v1"))
            cls.v1 = cls.p("v1", "root.json")
            os.makedirs(cls.p("rel"))
            os.makedirs(cls.p("pub"))
            for h in "abc":                   # what each token holder hands over
                tr.token_pub(spec(h), cls.p("pub", h + ".pub"))
            cls.build(cls.p("chan1"), cls.v1, None, release(cls.p("rel"), "vm", "0.1.1"))
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if cls.env:
            cls.env.stop()
        shutil.rmtree(cls.d, True)

    @classmethod
    def p(cls, *a):
        return os.path.join(cls.d, *a)

    @classmethod
    def build(cls, repo, root, prev, rel):
        key = lambda r: cls.p("online", r + ".key")
        with contextlib.redirect_stdout(io.StringIO()):
            return tr.build(repo, root, prev, [rel], key("targets"), key("snapshot"), key("timestamp"))

    def setUp(self):
        self.out = tempfile.mkdtemp()                 # this test's own outputs
        self.addCleanup(shutil.rmtree, self.out, True)

    def t(self, *a):
        return os.path.join(self.out, *a)

    def chan2(self, root):
        """The channel on top of `root` (the rotated root): chain 1.root.json, 2.root.json, release 0.1.2."""
        self.build(self.t("chan2"), root, self.p("chan1"), release(self.p("rel"), "vm", "0.1.2"))
        return self.t("chan2")

    def rotate(self, out="v2", old="ab", new="ab", pubs="c", threshold=2, **kw):
        """v1 -> v2: the `old` sticks sign, the `new` token keys sign, the `pubs` token keys are trusted only."""
        return tr.rotate_root(self.v1, [self.stick[h] for h in old], [spec(h) for h in new],
                              [self.p("pub", h + ".pub") for h in pubs], threshold, self.t(out), **kw)

    def sigs_kept(self, md, old, new):
        """The root with only `old` signatures of old-root keys and `new` of new-root keys left."""
        v1 = tr.Metadata.from_file(self.v1).signed.roles["root"].keyids
        keep = [k for k in md.signatures if k in v1][:old] + [k for k in md.signatures if k not in v1][:new]
        out = copy.deepcopy(md)
        out.signatures = {k: v for k, v in md.signatures.items() if k in keep}
        return out

    def channel_with(self, name, root_md):
        """A copy of chan2 (chain 1.root.json, 2.root.json) whose version-2 root is root_md."""
        shutil.copytree(self.t("chan2"), self.t(name))
        for f in ("2.root.json", "root.json"):
            root_md.to_file(self.t(name, f), tr.SER)
        return self.t(name)

    # ---- the token key
    def test_the_key_is_made_on_the_token_and_cannot_be_read_out(self):
        token = pkcs11.lib(SOFTHSM_LIB).get_token(token_label=LABELS["a"])
        with token.open(user_pin=PIN) as s:
            priv = s.get_key(pkcs11.ObjectClass.PRIVATE_KEY, pkcs11.KeyType.EC, id=pkcs11.util.biginteger(KEY_ID))
            self.assertFalse(priv[pkcs11.Attribute.EXTRACTABLE])
            self.assertTrue(priv[pkcs11.Attribute.SENSITIVE])

    def test_token_pub_exports_the_public_key_and_signatures_verify(self):
        out = os.path.join(self.out, "a.pub")
        pub = tr.token_pub(spec("a"), out)
        pem = open(out).read()
        self.assertTrue(pem.startswith("-----BEGIN PUBLIC KEY-----"))
        self.assertNotIn("PRIVATE", pem)
        self.assertEqual((pub.keytype, pub.scheme), ("ecdsa", "ecdsa-sha2-nistp256"))
        self.assertEqual(tr.load_pub(out).keyid, pub.keyid)                 # the file and the token agree
        self.assertEqual(tr.load_pub(spec("a")).keyid, pub.keyid)
        self.assertNotEqual(tr.load_pub(spec("b")).keyid, pub.keyid)
        pub.verify_signature(tr.load_signer(spec("a")).sign(b"payload"), b"payload")
        with self.assertRaises(SystemExit):                            # never overwrites
            tr.token_pub(spec("a"), out)

    def test_the_pin_is_prompted_without_echo_once_per_key(self):
        signer = tr.load_signer(spec("c"))
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop(tr.PIN_ENV)
            with unittest.mock.patch("getpass.getpass", return_value=PIN) as gp:
                signer.sign(b"one")
                signer.sign(b"two")
        self.assertEqual(gp.call_count, 1)
        self.assertIn("PIN", gp.call_args[0][0])

    def test_a_wrong_pin_signs_nothing(self):
        with unittest.mock.patch.dict(os.environ, {tr.PIN_ENV: "000000"}):
            with self.assertRaises(SystemExit) as e:
                self.rotate("badpin")
        self.assertIn("signing", str(e.exception))
        self.assertFalse(os.path.exists(self.t("badpin", "root.json")))

    def test_no_module_no_token_or_no_key_is_a_clear_refusal(self):
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("PYKCS11LIB")
            with self.assertRaises(SystemExit) as e:
                tr.load_pub(spec("a"))
            self.assertIn("PYKCS11LIB", str(e.exception))
        with self.assertRaises(SystemExit):
            tr.load_pub(f"hsm:{KEY_ID}?label=no-such-token")
        with self.assertRaises(SystemExit):
            tr.load_pub("hsm:9?label=" + LABELS["a"])                       # no key with that id on the token

    # ---- the rotation
    def test_rotate_v1_file_keys_to_v2_token_keys_and_a_v1_client_follows(self):
        md = self.rotate("v2")
        root = md.signed
        self.assertEqual((root.version, root.roles["root"].threshold, len(root.roles["root"].keyids)), (2, 2, 3))
        self.assertEqual({root.keys[k].keytype for k in root.roles["root"].keyids}, {"ecdsa"})
        self.assertEqual(len(md.signatures), 4)               # 2 old stick keys + 2 token keys; holder C only trusted
        lines, problems = tr.inspect_root(self.t("v2", "root.json"), 2, 3)
        self.assertEqual(problems, [], lines)
        lines, problems = tr.inspect_root(self.t("v2", "root.json"), 2, 3, prev=self.v1)   # the old keys signed it too
        self.assertEqual(problems, [], lines)
        self.assertIn("previous root v1: 2 of its keys signed this root too", "\n".join(lines))
        new_only = self.sigs_kept(md, 0, 2)                                # a v2 the old keys did not sign
        new_only.to_file(self.t("new-only.json"), tr.SER)
        self.assertEqual(tr.inspect_root(self.t("new-only.json"), 2, 3)[1], [])        # fine on its own...
        self.assertTrue(tr.inspect_root(self.t("new-only.json"), 2, 3, prev=self.v1)[1])   # ...not as a rotation
        v1 = tr.Metadata.from_file(self.v1).signed
        for r in ("targets", "snapshot", "timestamp"):        # the online keys stay
            self.assertEqual(root.roles[r].keyids, v1.roles[r].keyids)
        # the channel on top of the new root: the online keys sign a release; the chain is 1, 2
        chan = self.chan2(self.t("v2", "root.json"))
        self.assertTrue(os.path.exists(self.t("chan2", "1.root.json")) and os.path.exists(self.t("chan2", "2.root.json")))
        checked, problems = tr.verify(chan, self.v1, allow_absent=True)   # a client that trusts ONLY version 1
        self.assertEqual(problems, [])
        self.assertEqual(len(checked), 3)                                 # release 0.1.2: bundle, sbom, cve report
        self.assertEqual(tr.verify(chan, self.t("v2", "root.json"), allow_absent=True)[1], [])   # and one that ships v2
        self.go_box_check(chan)
        with self.assertRaises(SystemExit):                               # a second rotation never overwrites
            self.rotate("v2")

    def test_the_client_needs_both_key_sets(self):
        md = self.rotate("v2")
        self.chan2(self.t("v2", "root.json"))
        ok = self.channel_with("ok", self.sigs_kept(md, 2, 2))
        self.assertEqual(tr.verify(ok, self.v1, allow_absent=True)[1], [])    # control: the same files pass
        for n, (old, new) in enumerate([(0, 2), (2, 0), (1, 2), (2, 1), (1, 1)]):
            repo = self.channel_with(f"bad{n}", self.sigs_kept(md, old, new))
            with self.assertRaises(Exception, msg=f"{old} old + {new} new signatures must be refused"):
                tr.verify(repo, self.v1, allow_absent=True)

    def test_rotate_refuses_when_either_threshold_is_not_met(self):
        cases = {"one-new": dict(new="a"), "one-old": dict(old="a"), "no-old": dict(old=""), "no-new": dict(new="")}
        for name, kw in cases.items():
            with self.assertRaises(SystemExit, msg=name):
                self.rotate(name, **kw)
            self.assertFalse(os.path.exists(self.t(name, "root.json")), name)
        with self.assertRaises(SystemExit):                                # threshold above the keys that exist
            self.rotate("th4", threshold=4)
        with self.assertRaises(SystemExit) as e:                           # an "old" key that is not a root key of the current root
            tr.rotate_root(self.v1, [self.stick["a"], spec("a")], [spec("a"), spec("b")], [], 2, self.t("stray"))
        self.assertIn("not root keys", str(e.exception))
        self.assertFalse(os.path.exists(self.t("stray")))

    def test_rotate_can_replace_an_online_key(self):
        tr.keygen(self.t("online2"), ["targets"])
        md = self.rotate("v2b", old="bc", new="bc", pubs="a", online_pubs={"targets": self.t("online2", "targets.pub")})
        self.assertNotEqual(md.signed.roles["targets"].keyids,
                            tr.Metadata.from_file(self.v1).signed.roles["targets"].keyids)
        self.assertEqual(tr.inspect_root(self.t("v2b", "root.json"), 2, 3)[1], [])
        self.assertEqual(len(md.signed.keys), 6)                           # 3 root + 3 online; the old targets key is gone

    # ---- the offline script
    def run_script(self, *args, **env):
        return subprocess.run(["sh", SCRIPT, *args], env=script_env(**env), capture_output=True, text=True)

    def test_the_script_rotates_onto_token_keys_and_refuses_in_ci(self):
        env = {"ONEMIND_TUF_PASSPHRASE": PASS}
        r = self.run_script("token-pub", spec("c"), self.t("script-c.pub"), **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = ("rotate-root", self.v1, self.t("sv2"), "security", "2", self.stick["a"], self.stick["b"],
                "--", spec("a"), spec("b"), self.t("script-c.pub"))
        r = self.run_script(*argv, **env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("os/rootfs/layers/base/usr/lib/onemind/tuf/security/root.json", r.stdout)
        self.assertEqual(self.run_script("check", self.t("sv2"), "2", "3").returncode, 0)
        self.assertEqual(self.run_script("check", self.t("sv2"), "2", "3", self.v1).returncode, 0)
        again = self.run_script(*argv, **env)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("refusing to overwrite", again.stderr)
        one = self.run_script("rotate-root", self.v1, self.t("sv3"), "security", "2", self.stick["a"], self.stick["b"],
                              "--", spec("a"), self.p("pub", "b.pub"), self.p("pub", "c.pub"), **env)
        self.assertNotEqual(one.returncode, 0)                                # one new signer of two needed
        self.assertFalse(os.path.exists(self.p("sv3", "root.json")))
        for var in ("CI", "GITHUB_ACTIONS"):
            ci = self.run_script(*argv[:2], self.t("sv4"), *argv[3:], **env, **{var: "true"})
            self.assertEqual(ci.returncode, 1)
            self.assertIn("never in CI", ci.stderr)
            self.assertFalse(os.path.exists(self.t("sv4")))

    def test_the_cli_refuses_to_rotate_in_ci(self):
        with unittest.mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}):
            os.environ.pop("ONEMIND_TUF_EPHEMERAL", None)
            with self.assertRaises(SystemExit) as e:
                tr.main(["rotate-root", "--root", self.v1, "--old-key", self.stick["a"], "--old-key", self.stick["b"],
                         "--new-key", spec("a"), "--new-key", spec("b"), "--threshold", "2", "--out", self.t("ci")])
        self.assertIn("ROOT of trust", str(e.exception))
        self.assertFalse(os.path.exists(self.t("ci")))

    # ---- the box side (go-tuf v2)
    def go_box_check(self, repo):
        """The box's verifier (internal/update, go-tuf v2) follows v1 -> v2 (ECDSA root keys) to the release."""
        go = shutil.which("go")
        if not go or not os.path.exists(os.path.join(REPO, "go.mod")):
            return                            # not checked on a machine without Go; CI has it
        env = dict(os.environ, ONEMIND_TUF_REPO=repo, ONEMIND_TUF_TRUSTED_ROOT=self.v1)
        r = subprocess.run([go, "test", "./internal/update", "-run", "TestRotatedECDSARootAccepted", "-count=1", "-v"],
                           cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--- PASS: TestRotatedECDSARootAccepted", r.stdout)


if __name__ == "__main__":
    unittest.main()
