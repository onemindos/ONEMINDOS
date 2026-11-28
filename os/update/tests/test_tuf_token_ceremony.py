# SPDX-License-Identifier: Apache-2.0
"""The FIRST root ceremony on hardware keys (three YubiKeys, 2-of-3), rehearsed on SoftHSM.

What is tested, all with throwaway keys made in a temp directory (no real key, PIN or device anywhere):
- os/update/piv-attest.py: a YubiKey PIV attestation is accepted only when it chains to the device
  certificate (and the CA), attests the exact public key, and carries the asked PIN and touch policy.
  Synthetic certificates in the documented layout stand in for a real YubiKey.
- tuf-repo.py's token signer: a key whose PIN policy is "always" (CKA_ALWAYS_AUTHENTICATE, YubiKey slot
  9c's default) signs, which securesystemslib's plain HSMSigner cannot do; a wrong PIN signs nothing;
  hsm:2?yubikey=<serial> and a label with "#" name the right token.
- scripts/tuf-bootstrap-root.sh rehearse-tokens: the whole ceremony on three SoftHSM tokens.
- scripts/tuf-bootstrap-root.sh yubikey-key with a stand-in `ykman` whose keys live on SoftHSM: the
  command order, the refusals, the attestation check and the public key handed over.
- scripts/ceremony-guide.py --yubikey --rehearsal end to end.
- The box's own verifier (go-tuf, internal/update) accepts a channel whose FIRST root is held by tokens.

Needs the pinned python-tuf and python-pkcs11 (os/update/requirements-tuf.txt) and SoftHSM; the token
parts skip without them (CI sets ONEMIND_TUF_REQUIRE_HSM so they cannot skip there)."""
import datetime, importlib.util, io, json, os, shutil, stat, subprocess, sys, tempfile, textwrap, unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import UPDATE, load  # noqa: E402

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    att = load("piv-attest")
except ImportError:               # pragma: no cover
    att = None
try:
    tr = load("tuf-repo")
    import pkcs11, pkcs11.util.ec  # noqa: E401
except ImportError:               # pragma: no cover
    tr = pkcs11 = None

REPO = os.path.normpath(os.path.join(UPDATE, "..", ".."))
SCRIPT = os.path.join(REPO, "scripts", "tuf-bootstrap-root.sh")
GUIDE = os.path.join(REPO, "scripts", "ceremony-guide.py")
SOFTHSM_UTIL = os.environ.get("SOFTHSM2_UTIL") or shutil.which("softhsm2-util")
LIB_CANDIDATES = [os.environ.get("SOFTHSM2_LIB", ""), "/usr/lib/softhsm/libsofthsm2.so",
                  "/usr/lib/x86_64-linux-gnu/softhsm/libsofthsm2.so", "/usr/lib/aarch64-linux-gnu/softhsm/libsofthsm2.so",
                  "/usr/local/lib/softhsm/libsofthsm2.so", "/opt/homebrew/lib/softhsm/libsofthsm2.so"]
SOFTHSM_LIB = next((p for p in LIB_CANDIDATES if p and os.path.exists(p)), None)
HAVE_HSM = tr is not None and bool(SOFTHSM_UTIL) and bool(SOFTHSM_LIB)
WHY = "python-tuf, python-pkcs11 and SoftHSM are needed (requirements-tuf.txt; apt-get install softhsm2)"
PIN, SO_PIN = "123456", "87654321"                                      # throwaway, tests only


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ("CI", "GITHUB_ACTIONS", "ONEMIND_TUF_PASSPHRASE", "ONEMIND_TUF_PIN", "SOFTHSM2_CONF", "PYKCS11LIB")}
    env["PYTHON"] = sys.executable
    if SOFTHSM_LIB:
        env["SOFTHSM2_LIB"] = SOFTHSM_LIB
    env.update(extra)
    return env


def run_script(*args, **env):
    return subprocess.run(["sh", SCRIPT, *args], env=clean_env(**env), capture_output=True, text=True)


# ---------------------------------------------------------------- synthetic YubiKey attestation
def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject, pub, issuer_name, issuer_key, exts=(), ca=False):
    now = datetime.datetime.now(datetime.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(_name(subject)).issuer_name(issuer_name).public_key(pub)
         .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
         .not_valid_after(now + datetime.timedelta(days=30)))
    if ca:
        b = b.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    for oid, raw in exts:
        b = b.add_extension(x509.UnrecognizedExtension(oid, raw), critical=False)
    return b.sign(issuer_key, hashes.SHA256())


def pem(c):
    return c.public_bytes(serialization.Encoding.PEM)


def make_ca():
    """A throwaway stand-in for Yubico's PIV root CA: (certificate, private key)."""
    key = ec.generate_private_key(ec.SECP256R1())
    return _cert("Test PIV Root CA", key.public_key(), _name("Test PIV Root CA"), key, ca=True), key


def write_ca(d):
    """Write a throwaway CA as <d>/ca.pem (certificate) and <d>/ca.key (its key, for the stand-in ykman)."""
    cert, key = make_ca()
    open(os.path.join(d, "ca.pem"), "wb").write(pem(cert))
    open(os.path.join(d, "ca.key"), "wb").write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                                  serialization.NoEncryption()))
    return os.path.join(d, "ca.pem")


def read_ca(d):
    return (x509.load_pem_x509_certificate(open(os.path.join(d, "ca.pem"), "rb").read()),
            serialization.load_pem_private_key(open(os.path.join(d, "ca.key"), "rb").read(), None))


def write_attestation(d, holder_pub, pin=3, touch=2, serial=12345678, policy=True, signer="f9", ca=None, serial_ext=True):
    """Write <d>/ca.pem, f9.pem, attest.pem as a YubiKey would (Yubico's documented layout), attesting
    holder_pub (a cryptography public key). ca=(certificate, key) reuses a CA (else a new one). Returns the paths."""
    ca, ca_key = ca or make_ca()
    f9_key, other_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(2))
    f9 = _cert("Test PIV Attestation", f9_key.public_key(), ca.subject, ca_key, ca=True)
    exts = [(att.OID_FIRMWARE, bytes([5, 7, 1]))]
    if serial_ext:
        exts.append((att.OID_SERIAL, b"\x02\x04" + serial.to_bytes(4, "big")))
    if policy:
        exts.append((att.OID_POLICY, bytes([pin, touch])))
    sign_key = f9_key if signer == "f9" else other_key
    a = _cert("YubiKey PIV Attestation 9c", holder_pub, f9.subject, sign_key, exts)
    paths = {}
    for n, c in (("ca", ca), ("f9", f9), ("attest", a)):
        paths[n] = os.path.join(d, n + ".pem")
        open(paths[n], "wb").write(pem(c))
    return paths


@unittest.skipIf(att is None, "cryptography is needed (os/update/requirements-tuf.txt)")
class Attestation(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.pub = os.path.join(self.d, "a.pub")
        open(self.pub, "wb").write(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    def check(self, want_serial=None, **kw):
        p = write_attestation(self.d, kw.pop("attested", self.key.public_key()), **kw)
        return att.check(self.pub, p["attest"], [p["f9"]], p["ca"], serial=want_serial)

    def test_a_key_made_on_the_device_with_both_policies_passes(self):
        lines, problems = self.check()
        self.assertEqual(problems, [], lines)
        text = "\n".join(lines)
        self.assertIn("device serial 12345678, firmware 5.7.1", text)
        self.assertIn("PIN policy always, touch policy always", text)
        self.assertIn("chain ends at the CA", text)

    def test_the_cli_exit_code_and_verdict(self):
        p = write_attestation(self.d, self.key.public_key())
        with unittest.mock.patch("sys.stdout"):
            self.assertEqual(att.main(["--pub", self.pub, "--attestation", p["attest"], "--chain", p["f9"], "--ca", p["ca"]]), 0)
            self.assertEqual(att.main(["--pub", self.pub, "--attestation", p["attest"], "--chain", p["f9"], "--ca", p["ca"],
                                       "--touch-policy", "cached"]), 1)

    def test_no_ca_fails_closed_and_only_the_spare_trial_may_skip_it_out_loud(self):
        p = write_attestation(self.d, self.key.public_key())
        lines, problems = att.check(self.pub, p["attest"], [p["f9"]], None)
        self.assertTrue(any("no Yubico PIV CA given" in x for x in problems), problems)
        lines, problems = att.check(self.pub, p["attest"], [p["f9"]], None, allow_no_ca=True)
        self.assertEqual(problems, [])
        self.assertIn("SPARE TRIAL ONLY", "\n".join(lines))
        base = ["--pub", self.pub, "--attestation", p["attest"], "--chain", p["f9"]]
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(att.main(base), 1)
            self.assertIn("attestation FAILED", out.getvalue())
        with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(att.main(base + ["--no-ca-spare-trial"]), 0)
            self.assertIn("WITHOUT Yubico's CA (spare trial only)", out.getvalue())
            self.assertNotIn("cannot leave it", out.getvalue())
        with unittest.mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            att.main(base + ["--no-ca-spare-trial", "--ca", p["ca"]])

    def test_the_attestation_must_name_the_yubikey_that_was_meant(self):
        self.assertEqual(self.check(want_serial=12345678)[1], [])
        _, problems = self.check(want_serial=87654321)
        self.assertTrue(any("from YubiKey 12345678, not the YubiKey 87654321" in p for p in problems), problems)
        _, problems = self.check(want_serial=12345678, serial_ext=False)
        self.assertTrue(any("no device serial" in p for p in problems), problems)

    def test_an_attestation_of_another_key_fails(self):
        _, problems = self.check(attested=ec.generate_private_key(ec.SECP256R1()).public_key())
        self.assertTrue(any("NOT the key" in p for p in problems), problems)

    def test_weaker_policies_fail(self):
        for pin, touch, word in ((2, 2, "PIN policy is once"), (1, 2, "PIN policy is never"),
                                 (3, 1, "touch policy is never"), (3, 3, "touch policy is cached")):
            _, problems = self.check(pin=pin, touch=touch)
            self.assertTrue(any(word in p for p in problems), (pin, touch, problems))

    def test_no_policy_extension_fails(self):
        _, problems = self.check(policy=False)
        self.assertTrue(any("no PIN/touch policy" in p for p in problems), problems)

    def test_an_attestation_not_signed_by_the_device_certificate_fails(self):
        _, problems = self.check(signer="other")
        self.assertTrue(any("is not signed by" in p for p in problems), problems)

    def test_a_chain_to_another_ca_fails(self):
        p = write_attestation(self.d, self.key.public_key())
        other = os.path.join(self.d, "other")
        os.makedirs(other)
        q = write_attestation(other, self.key.public_key())
        _, problems = att.check(self.pub, p["attest"], [p["f9"]], q["ca"])
        self.assertTrue(any("does not end at the CA" in x for x in problems), problems)


# ---------------------------------------------------------------- tokens (SoftHSM)
class Installed(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("ONEMIND_TUF_REQUIRE_HSM"), "CI sets ONEMIND_TUF_REQUIRE_HSM")
    def test_the_token_tools_are_there_so_the_tests_below_do_not_skip_in_ci(self):
        self.assertTrue(HAVE_HSM and att is not None, WHY)


CHILD = "ONEMIND_TOKEN_TESTS_CHILD"


@unittest.skipUnless(HAVE_HSM, WHY)
class Tokens(unittest.TestCase):
    def test_in_a_fresh_process(self):
        """SoftHSM reads its configuration once per process, and test_tuf_hsm.py loads it first with its own:
        the in-process token tests below run in a child process with theirs."""
        r = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-v", "-s", os.path.dirname(os.path.abspath(__file__)),
                            "-p", "test_tuf_token_ceremony.py", "-k", "TokensInProcess"], env=dict(os.environ, **{CHILD: "1"}),
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("skipped", r.stderr)
        self.assertIn("Ran 4 tests", r.stderr)


@unittest.skipUnless(HAVE_HSM and os.environ.get(CHILD), "run by Tokens.test_in_a_fresh_process")
class TokensInProcess(unittest.TestCase):
    """One SoftHSM store for the class; every test makes its own tokens in it."""
    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.d, "tokens"))
        cls.conf = os.path.join(cls.d, "softhsm2.conf")
        with open(cls.conf, "w") as f:
            f.write(f"directories.tokendir = {os.path.join(cls.d, 'tokens')}\nobjectstore.backend = file\nlog.level = ERROR\n")
        labels = ["onemind-t-aa", "onemind-t-plain", "YubiKey PIV #12345678", "onemind-t-dup", "onemind-t-sig"]
        for label in labels:                       # all tokens first: SoftHSM lists its slots when it is loaded
            subprocess.run([SOFTHSM_UTIL, "--module", SOFTHSM_LIB, "--init-token", "--free", "--label", label,
                            "--so-pin", SO_PIN, "--pin", PIN], check=True, capture_output=True, env=dict(os.environ, SOFTHSM2_CONF=cls.conf))
        cls.env = unittest.mock.patch.dict(os.environ, {"SOFTHSM2_CONF": cls.conf, "PYKCS11LIB": SOFTHSM_LIB, tr.PIN_ENV: PIN})
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        shutil.rmtree(cls.d, True)

    def test_a_pin_always_key_signs_with_the_token_signer_and_not_with_the_plain_one(self):
        from securesystemslib.signer import HSMSigner
        pub = tr.token_keygen("hsm:2?label=onemind-t-aa", pin_always=True)
        token = pkcs11.lib(SOFTHSM_LIB).get_token(token_label="onemind-t-aa")
        with token.open(user_pin=PIN) as s:
            k = s.get_key(pkcs11.ObjectClass.PRIVATE_KEY, pkcs11.KeyType.EC, id=pkcs11.util.biginteger(2))
            self.assertTrue(k[pkcs11.Attribute.ALWAYS_AUTHENTICATE])
            self.assertFalse(k[pkcs11.Attribute.EXTRACTABLE])
            self.assertTrue(k[pkcs11.Attribute.SENSITIVE])
        signer = tr.load_signer("hsm:2?label=onemind-t-aa")
        pub.verify_signature(signer.sign(b"payload"), b"payload")
        uri, _ = HSMSigner.import_(2, "onemind-t-aa", lambda _: PIN)
        with self.assertRaises(Exception):                       # what the rotation would have hit on a YubiKey 9c key
            HSMSigner.from_priv_key_uri(uri, pub, lambda _: PIN).sign(b"payload")
        with unittest.mock.patch.dict(os.environ, {tr.PIN_ENV: "000000"}):
            with self.assertRaises(Exception):
                tr.load_signer("hsm:2?label=onemind-t-aa").sign(b"payload")

    def test_a_plain_key_still_signs(self):
        pub = tr.token_keygen("hsm:2?label=onemind-t-plain")
        pub.verify_signature(tr.load_signer("hsm:2?label=onemind-t-plain").sign(b"x"), b"x")

    def test_a_yubikey_is_named_by_serial_and_a_label_keeps_its_hash_sign(self):
        pub = tr.token_keygen("hsm:2?label=YubiKey PIV #12345678")
        self.assertEqual(tr.load_pub("hsm:2?yubikey=12345678").keyid, pub.keyid)
        self.assertEqual(tr.load_pub("hsm:2?label=YubiKey%20PIV%20%2312345678").keyid, pub.keyid)
        for bad in ("hsm:2?yubikey=12ab", "hsm:2?yubikey=1&label=x", "hsm:x?label=a"):
            with self.assertRaises(SystemExit, msg=bad):
                tr._hsm_ref(bad)

    def test_keygen_never_replaces_a_key_and_leaves_yubikeys_to_ykman(self):
        tr.token_keygen("hsm:2?label=onemind-t-dup")
        with self.assertRaises(SystemExit) as e:
            tr.token_keygen("hsm:2?label=onemind-t-dup")
        self.assertIn("refusing to replace", str(e.exception))
        with unittest.mock.patch.dict(os.environ, {"PYKCS11LIB": "/usr/lib/libykcs11.so"}):
            with self.assertRaises(SystemExit) as e:
                tr.token_keygen("hsm:2?label=x")
            self.assertIn("ykman", str(e.exception))
        with self.assertRaises(SystemExit):
            tr.token_keygen("hsm:2")                              # no token named


@unittest.skipUnless(HAVE_HSM, WHY)
class Rehearsal(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_rehearse_tokens_end_to_end_and_the_box_accepts_the_token_root(self):
        D = os.path.join(self.d, "r")
        r = run_script("rehearse-tokens", D)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("REHEARSAL PASSED", r.stderr)
        root = json.load(open(os.path.join(D, "out", "root.json")))
        signed = root["signed"]
        self.assertEqual(signed["roles"]["root"]["threshold"], 2)
        self.assertEqual({signed["keys"][k]["keytype"] for k in signed["roles"]["root"]["keyids"]}, {"ecdsa"})
        self.assertEqual(len(root["signatures"]), 2)              # two tokens signed, the third is trusted only
        for h in "abc":
            self.assertNotIn(b"PRIVATE", open(os.path.join(D, "pubs", h + ".pub"), "rb").read())
        renewed = json.load(open(os.path.join(D, "renewed", "root.json")))["signed"]
        self.assertEqual((renewed["version"], renewed["roles"]["root"]["keyids"]), (2, signed["roles"]["root"]["keyids"]))
        self.assertFalse(os.path.exists(os.path.join(D, "refused", "root.json")))
        self.go_box_check(os.path.join(D, "channel"), os.path.join(D, "out", "root.json"))
        again = run_script("rehearse-tokens", D)
        self.assertEqual(again.returncode, 2)
        self.assertIn("refusing", again.stderr)

    def test_refused_in_ci(self):
        for var in ("CI", "GITHUB_ACTIONS"):
            r = run_script("rehearse-tokens", os.path.join(self.d, var), **{var: "true"})
            self.assertEqual(r.returncode, 1)
            self.assertIn("never in CI", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(self.d, var)))

    def go_box_check(self, repo, trusted):
        go = shutil.which("go")
        if not go or not os.path.exists(os.path.join(REPO, "go.mod")):
            return                                                # not checked without Go; CI has it
        env = dict(os.environ, ONEMIND_TUF_REPO=repo, ONEMIND_TUF_TRUSTED_ROOT=trusted)
        r = subprocess.run([go, "test", "./internal/update", "-run", "TestRotatedECDSARootAccepted", "-count=1", "-v"],
                           cwd=REPO, env=env, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("--- PASS: TestRotatedECDSARootAccepted", r.stdout)


# A stand-in for ykman: its "YubiKey" is a SoftHSM token labelled "YubiKey PIV #<serial>" (the label Yubico's
# PKCS#11 module gives a device), so the script's whole path runs: generate ON the token, attest, export f9,
# token-pub over PKCS#11, piv-attest. The attestation is signed by a throwaway "device" key made here.
FAKE_YKMAN = textwrap.dedent('''\
    #!PYTHON
    import datetime, json, os, sys
    sys.path.insert(0, os.environ["FAKE_YK_TESTDIR"])
    import pkcs11, pkcs11.util.ec
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    log = os.environ["FAKE_YK_LOG"]
    a = sys.argv[1:]
    open(log, "a").write(" ".join(a) + "\\n")
    if a[:2] == ["list", "--serials"]:
        print(os.environ["FAKE_YK_SERIALS"].replace(",", "\\n")); sys.exit(0)
    assert a[0] == "--device"
    serial, a = a[1], a[2:]
    label = "YubiKey PIV #" + serial
    tok = pkcs11.lib(os.environ["PYKCS11LIB"]).get_token(token_label=label)
    state = os.path.join(os.environ["FAKE_YK_STATE"], serial + ".json")
    st = json.load(open(state)) if os.path.exists(state) else {}
    def pub_pem():
        with tok.open(user_pin=os.environ["FAKE_YK_PIN"]) as s:
            k = s.get_key(pkcs11.ObjectClass.PUBLIC_KEY, pkcs11.KeyType.EC, id=b"\\x02")
            der = pkcs11.util.ec.encode_ec_public_key(k)
        return serialization.load_der_public_key(der)
    if a[:3] == ["piv", "keys", "info"]:
        bad = os.environ.get("FAKE_YK_BAD", "")
        if bad == "infoerror":                                # an unexpected failure: neither "key" nor "no key"
            sys.exit("Error: Failed to connect to the YubiKey (smart card service not running)")
        if st.get("key"):
            sys.exit(0)
        sys.exit("Error: No key stored in slot 9C.")
    if a[:2] == ["piv", "info"]:
        if os.environ.get("FAKE_YK_BAD", "") == "pivinfoerror":
            sys.exit("Error: piv info failed")
        print("PIV version: 5.4.3")
        if st.get("key") or os.environ.get("FAKE_YK_BAD", "") == "pivinfo9c":   # keys info said empty, piv info disagrees
            print("Slot 9C (SIGNATURE):\\n  Algorithm: ECCP256")
        sys.exit(0)
    if a[:3] == ["piv", "keys", "generate"]:
        pp, tp = a[a.index("--pin-policy") + 1], a[a.index("--touch-policy") + 1]
        with tok.open(rw=True, user_pin=os.environ["FAKE_YK_PIN"]) as s:
            params = s.create_domain_parameters(pkcs11.KeyType.EC, {pkcs11.Attribute.EC_PARAMS:
                     pkcs11.util.ec.encode_named_curve_parameters("secp256r1")}, local=True)
            params.generate_keypair(store=True, id=b"\\x02", label="9c", private_template={pkcs11.Attribute.EXTRACTABLE: False,
                                    pkcs11.Attribute.SENSITIVE: True, pkcs11.Attribute.ALWAYS_AUTHENTICATE: pp == "ALWAYS"})
        st.update(key=True, pin=pp, touch=tp); json.dump(st, open(state, "w"))
        open(a[-1], "wb").write(pub_pem().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        sys.exit(0)
    if a[:3] == ["piv", "certificates", "generate"]:
        sys.exit(0)
    if a[:3] == ["piv", "keys", "attest"] or a[:3] == ["piv", "certificates", "export"]:
        from test_tuf_token_ceremony import write_attestation
        d = os.path.join(os.environ["FAKE_YK_STATE"], serial)
        if not os.path.exists(os.path.join(d, "attest.pem")):
            from test_tuf_token_ceremony import read_ca
            os.makedirs(d, exist_ok=True)
            bad = os.environ.get("FAKE_YK_BAD", "")          # a device that answers wrongly: another key, another serial
            attested = ec.generate_private_key(ec.SECP256R1()).public_key() if bad == "otherkey" else pub_pem()
            write_attestation(d, attested, pin={"ALWAYS": 3, "ONCE": 2}[st["pin"]], touch={"ALWAYS": 2, "CACHED": 3}[st["touch"]],
                              serial=99999999 if bad == "serial" else int(serial), ca=read_ca(os.environ["FAKE_YK_STATE"]))
        src = "attest.pem" if a[2] == "attest" else "f9.pem"
        open(a[-1], "wb").write(open(os.path.join(d, src), "rb").read()); sys.exit(0)
    sys.exit("fake ykman: unexpected " + " ".join(a))
    ''')


@unittest.skipUnless(HAVE_HSM, WHY)
class YubikeyKeyScript(unittest.TestCase):
    SERIALS = ("11111111", "22222222", "33333333")

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "tokens")); os.makedirs(os.path.join(self.d, "state")); os.makedirs(os.path.join(self.d, "bin"))
        self.conf = os.path.join(self.d, "softhsm2.conf")
        open(self.conf, "w").write(f"directories.tokendir = {os.path.join(self.d, 'tokens')}\nobjectstore.backend = file\nlog.level = ERROR\n")
        for s in self.SERIALS:
            subprocess.run([SOFTHSM_UTIL, "--module", SOFTHSM_LIB, "--init-token", "--free", "--label", f"YubiKey PIV #{s}",
                            "--so-pin", SO_PIN, "--pin", PIN], check=True, capture_output=True, env=dict(os.environ, SOFTHSM2_CONF=self.conf))
        yk = os.path.join(self.d, "bin", "ykman")
        open(yk, "w").write(FAKE_YKMAN.replace("PYTHON", sys.executable, 1))
        os.chmod(yk, os.stat(yk).st_mode | stat.S_IEXEC)
        self.log = os.path.join(self.d, "ykman.log")
        self.ca = write_ca(os.path.join(self.d, "state"))           # the stand-in for Yubico's PIV CA

    def env(self, serials=None, **extra):
        e = dict(SOFTHSM2_CONF=self.conf, PYKCS11LIB=SOFTHSM_LIB, ONEMIND_TUF_PIN=PIN, FAKE_YK_PIN=PIN, YUBICO_PIV_CA=self.ca,
                 FAKE_YK_LOG=self.log, FAKE_YK_STATE=os.path.join(self.d, "state"),
                 FAKE_YK_SERIALS=",".join(serials or self.SERIALS[:1]), FAKE_YK_TESTDIR=os.path.dirname(os.path.abspath(__file__)),
                 PATH=os.path.join(self.d, "bin") + os.pathsep + os.environ.get("PATH", ""))
        e.update(extra)
        return e

    def test_one_holder_key_made_on_the_yubikey_attested_and_handed_over(self):
        out = os.path.join(self.d, "pubs")
        r = run_script("yubikey-key", out, "a", **self.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("attestation OK", r.stdout)
        self.assertIn("PIN policy always, touch policy always", r.stdout)
        calls = open(self.log).read()
        self.assertIn("piv keys generate --algorithm ECCP256 --pin-policy ALWAYS --touch-policy ALWAYS 9c", calls)
        self.assertNotIn(PIN, calls)                               # never a PIN on a command line
        pub = os.path.join(out, "a.pub")
        self.assertNotIn(b"PRIVATE", open(pub, "rb").read())
        again_pub = os.path.join(self.d, "again.pub")                # in a subprocess: SoftHSM reads its config once per process
        self.assertEqual(run_script("token-pub", f"hsm:2?yubikey={self.SERIALS[0]}", again_pub, **self.env()).returncode, 0)
        self.assertEqual(open(again_pub).read(), open(pub).read())
        # a second run: the outputs exist, and the slot is taken
        again = run_script("yubikey-key", out, "a", **self.env())
        self.assertEqual(again.returncode, 2)
        self.assertIn("refusing to overwrite", again.stderr)
        other = run_script("yubikey-key", os.path.join(self.d, "pubs2"), "a", **self.env())
        self.assertEqual(other.returncode, 2)
        self.assertIn("already holds a key in slot 9c", other.stderr)

    def test_the_slot_check_fails_closed(self):
        for bad, word in (("infoerror", "could not tell whether slot 9c"),
                          ("pivinfoerror", "'ykman piv info' failed"),
                          ("pivinfo9c", "lists something in slot 9c")):
            out = os.path.join(self.d, "pubs-" + bad)
            r = run_script("yubikey-key", out, "a", **self.env(FAKE_YK_BAD=bad))
            self.assertEqual(r.returncode, 2, bad + r.stdout + r.stderr)
            self.assertIn(word, r.stderr)
            self.assertNotIn("piv keys generate", open(self.log).read())      # nothing was generated

    def test_a_failed_attestation_leaves_no_public_key(self):
        for ser, bad, word in ((self.SERIALS[0], "otherkey", "NOT the key"),
                               (self.SERIALS[1], "serial", f"from YubiKey 99999999, not the YubiKey {self.SERIALS[1]}")):
            out = os.path.join(self.d, "pubs-" + bad)
            r = run_script("yubikey-key", out, "a", ser, **self.env(FAKE_YK_BAD=bad))
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn(word, r.stdout)
            self.assertIn("attestation FAILED", r.stdout)
            self.assertIn("No " + os.path.join(out, "a.pub") + " was written", r.stderr)
            self.assertEqual(sorted(os.listdir(out)), ["a-attestation-FAILED"], bad)    # no a.pub, no temp file
            self.assertEqual(sorted(os.listdir(os.path.join(out, "a-attestation-FAILED"))),
                             ["a-attest.pem", "a-f9.pem", "a-ykman.pub"])
            again = run_script("yubikey-key", out, "a", ser, **self.env())
            self.assertEqual(again.returncode, 2)
            self.assertIn("refusing to overwrite", again.stderr)
            self.assertFalse(os.path.exists(os.path.join(out, "a.pub")))

    def test_no_yubico_ca_is_refused_before_the_device_is_touched(self):
        out = os.path.join(self.d, "pubs")
        r = run_script("yubikey-key", out, "a", **self.env(YUBICO_PIV_CA=""))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("set YUBICO_PIV_CA", r.stderr)
        r = run_script("yubikey-key", out, "a", **self.env(YUBICO_PIV_CA=os.path.join(self.d, "missing.pem")))
        self.assertEqual(r.returncode, 2)
        r = run_script("yubikey-key", out, "a", **self.env(YUBICO_PIV_CA="", ONEMIND_ATTEST_WITHOUT_CA="spare-trial"))
        self.assertEqual(r.returncode, 2)                          # the bypass is for the key named "spare" only
        self.assertNotIn("piv keys generate", open(self.log).read() if os.path.exists(self.log) else "")
        self.assertFalse(os.path.exists(out))

    def test_the_spare_trial_may_skip_the_ca_and_it_is_recorded(self):
        out = os.path.join(self.d, "spare-trial")
        r = run_script("yubikey-key", out, "spare", **self.env(YUBICO_PIV_CA="", ONEMIND_ATTEST_WITHOUT_CA="spare-trial"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WITHOUT Yubico's CA (spare trial only)", r.stdout)
        self.assertIn("SPARE TRIAL ONLY", r.stdout)
        record = open(os.path.join(out, "spare-NO-CA-RECORD.txt")).read()
        self.assertIn(self.SERIALS[0], record)
        self.assertIn("must never go into a real root", record)

    def test_a_pin_in_the_environment_is_refused_for_a_real_token(self):
        r = run_script("token-pub", f"hsm:2?yubikey={self.SERIALS[0]}", os.path.join(self.d, "x.pub"),
                       **self.env(PYKCS11LIB="/usr/lib/x86_64-linux-gnu/libykcs11.so"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("ONEMIND_TUF_PIN is set, but it is for SoftHSM", r.stderr)
        with unittest.mock.patch.dict(os.environ, {tr.PIN_ENV: PIN, "PYKCS11LIB": "/usr/lib/libykcs11.so"}):
            with self.assertRaises(SystemExit) as e:
                tr._env_pin()
            self.assertIn("SoftHSM rehearsals and tests only", str(e.exception))
        with unittest.mock.patch.dict(os.environ, {tr.PIN_ENV: PIN, "PYKCS11LIB": SOFTHSM_LIB}):
            self.assertEqual(tr._env_pin(), PIN)

    def test_exactly_one_yubikey_and_the_tools_must_be_there(self):
        r = run_script("yubikey-key", os.path.join(self.d, "p"), "a", **self.env(serials=self.SERIALS[:2]))
        self.assertEqual(r.returncode, 2)
        self.assertIn("exactly ONE YubiKey", r.stderr)
        r = run_script("yubikey-key", os.path.join(self.d, "p"), "a", "12ab", **self.env())
        self.assertEqual(r.returncode, 2)
        r = run_script("yubikey-key", os.path.join(self.d, "p"), "a", **self.env(PYKCS11LIB="", ONEMIND_TUF_PIN=""))
        self.assertEqual(r.returncode, 1)
        self.assertIn("PYKCS11LIB", r.stderr)
        r = run_script("yubikey-key", os.path.join(self.d, "p"), "a", **self.env(PATH="/usr/bin:/bin"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("ykman", r.stderr)

    def test_three_yubikeys_sign_a_root_with_the_real_commands(self):
        pubs = os.path.join(self.d, "pubs")
        for h, s in zip("abc", self.SERIALS):
            r = run_script("yubikey-key", pubs, h, s, **self.env())
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with unittest.mock.patch.dict(os.environ, {tr.PASSPHRASE_ENV: "unused-throwaway-passphrase"}):
            tr.keygen(os.path.join(self.d, "online"), ["targets", "snapshot", "timestamp"])
        o = lambda r: os.path.join(self.d, "online", r + ".pub")
        r = run_script("create", os.path.join(self.d, "out"), "security", "2", f"hsm:2?yubikey={self.SERIALS[0]}",
                       f"hsm:2?yubikey={self.SERIALS[1]}", os.path.join(pubs, "c.pub"), "--", o("targets"), o("snapshot"),
                       o("timestamp"), **self.env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(run_script("check", os.path.join(self.d, "out"), "2", "3", **self.env()).returncode, 0)


@unittest.skipUnless(HAVE_HSM, WHY)
class Guide(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)

    def guide(self, *args, **env):
        return subprocess.run([sys.executable, GUIDE, *args], env=clean_env(**env), capture_output=True, text=True,
                              stdin=subprocess.DEVNULL)

    def test_the_guided_yubikey_rehearsal_end_to_end(self):
        work = os.path.join(self.d, "work")
        r = self.guide("--yubikey", "--rehearsal", "--work", work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("REHEARSAL PASSED: guided 3-holder walk (yubikey)", r.stdout)
        self.assertIn("YubiKey ceremony", r.stdout)
        self.assertIn("D-031 (2026-11-25): the first ceremony runs on the founder's three YubiKeys.", r.stdout)
        self.assertNotIn("differs from D-010", r.stdout + r.stderr)
        self.assertNotIn("trusted person", r.stdout)                          # sole holder, 2026-11-27
        self.assertIn("three different places", r.stdout)
        root = json.load(open(os.path.join(work, "out-security", "root.json")))["signed"]
        self.assertEqual({root["keys"][k]["keytype"] for k in root["roles"]["root"]["keyids"]}, {"ecdsa"})
        self.assertEqual(root["roles"]["root"]["threshold"], 2)
        self.assertFalse(os.path.exists(os.path.join(work, "sticks")))      # no key files anywhere
        log = open(os.path.join(work, "guide.log")).read()
        self.assertNotIn("ONEMIND_TUF_PIN", log)
        resumed = self.guide("--rehearsal", "--work", work)                  # a stick-mode resume of a YubiKey run
        self.assertEqual(resumed.returncode, 1)
        self.assertIn("different mode", resumed.stderr)

    def test_refusals(self):
        r = self.guide("--yubikey", "--solo-differs-from-d010", "--work", os.path.join(self.d, "w1"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("already a one-person ceremony", r.stderr)               # no solo flag: --yubikey is one person
        r = self.guide("--yubikey", "--work", os.path.join(self.d, "w2"), ONEMIND_TUF_PIN="123456")
        self.assertEqual(r.returncode, 1)
        self.assertIn("never kept in the environment", r.stderr)

    def test_the_real_yubikey_path_needs_yubicos_ca(self):
        spec = importlib.util.spec_from_file_location("ceremony_guide", GUIDE)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        ca = os.path.join(self.d, "ca.pem")
        open(ca, "w").write("-----BEGIN CERTIFICATE-----\n")
        self.assertEqual(g.yubico_ca({"YUBICO_PIV_CA": ca}), ca)
        for env, word in (({}, "set YUBICO_PIV_CA"), ({"YUBICO_PIV_CA": os.path.join(self.d, "none.pem")}, "set YUBICO_PIV_CA"),
                          ({"YUBICO_PIV_CA": ca, "ONEMIND_ATTEST_WITHOUT_CA": "spare-trial"}, "spare trial only")):
            with self.assertRaises(g.Stop) as e:
                g.yubico_ca(env)
            self.assertIn(word, str(e.exception))


if __name__ == "__main__":
    unittest.main()
