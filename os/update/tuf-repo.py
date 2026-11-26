#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind update channel: TUF repository tool (spec 1.0, python-tuf). Interface: os/update/CHANNEL.md.

TUF ("The Update Framework") splits trust over four signed roles so that one stolen online key
cannot push a malicious update: root (certifies the other keys; offline), targets (lists the files
and their hashes), snapshot (pins the current targets version), timestamp (short-lived "this is
fresh" signature). A box trusts only the root.json baked into its image.

Keys are ed25519, PEM (PKCS#8 private, SubjectPublicKeyInfo public). A key argument is a file path,
env:NAME (read from that environment variable, so CI secrets never touch the disk) or, for a ROOT key
on a hardware token (a YubiKey, or SoftHSM in tests), hsm:<id>[?label=<token label>]: an ECDSA P-256
key that never leaves the token, reached through the PKCS#11 module named by $PYKCS11LIB. The token's
PIN is typed at a no-echo prompt (or $ONEMIND_TUF_PIN, SoftHSM rehearsals and tests only: refused with
any other PKCS#11 module), never given as an argument.
A YubiKey can be named by its serial, hsm:2?yubikey=<serial> (its PKCS#11 token label is
"YubiKey PIV #<serial>"); a key whose PIN policy is "always" (CKA_ALWAYS_AUTHENTICATE, YubiKey slot
9c) gets the PIN again for every signature, and a touch policy makes the device wait for a touch.

  keygen    --out-dir D [--roles root,targets,snapshot,timestamp] [--encrypt]
                                       new keys; never overwrites; --encrypt asks for a passphrase
  inspect   --root root.json [--expect-threshold N] [--expect-root-keys N] [--prev OLD/root.json]
                                       read a root as a box would trust it; exit 1 on any problem;
                                       --prev also checks that the previous root's keys signed it (a rotation)
  token-pub --key hsm:<id>[?label=L] --out FILE.pub
                                       export a token key's public part (the private key stays on the token)
  token-keygen --key hsm:<id>?label=L [--pin-always]
                                       make an ECDSA P-256 key ON a PKCS#11 token, never extractable
                                       (SoftHSM rehearsals and generic tokens; a YubiKey uses ykman, which
                                       also sets its PIN and touch policy: scripts/tuf-bootstrap-root.sh yubikey-key)
  init-root --root-key K [--root-key K2 ...] [--root-pub P ...] --threshold N
            --targets-pub P --snapshot-pub P --timestamp-pub P --out DIR [--expires-days 365]
            [--version 1]          offline only: writes DIR/<version>.root.json and DIR/root.json
  rotate-root --root CURRENT/root.json --old-key K [--old-key K2 ...] --new-key K [--new-key K2 ...]
            [--new-pub P ...] --threshold N --out DIR [--targets-pub P ...] [--expires-days 365]
            offline only: writes DIR/<N+1>.root.json and DIR/root.json with a new set of root keys,
            signed by a threshold of the OLD root keys AND a threshold of the NEW ones (TUF spec 5.3.4)
  renew-root --current root.json --root-key K [--root-key K2 ...] --out DIR [--expires-days 365]
                                       offline only: root version N+1 with a new expiry and the SAME keys,
                                       signed by the threshold of the current root keys; checks a box
                                       holding version N accepts it; writes DIR/<N+1>.root.json and root.json
  build     --repo OUT --root root.json [--prev DIR] --release release-<board>.json ...
            --targets-key K --snapshot-key K --timestamp-key K [--keep 3]
            new targets/snapshot/timestamp versions on top of the previous channel metadata
  refresh   --repo DIR --timestamp-key K [--snapshot-key K] [--targets-key K]
            re-sign the roles that are near expiry (the daily timestamp job)
  verify    --repo DIR --root root.json [--metadata-only] [--allow-absent]
            a python-tuf client (ngclient) refreshes from the repo over HTTP on 127.0.0.1 and
            downloads + hash-checks every target, as a box would

Repo layout is flat (CHANNEL.md §3): <N>.root.json, root.json, timestamp.json, snapshot.json,
targets.json and each target file under the basename of its target path.
"""
import argparse, copy, datetime, functools, getpass, hashlib, http.server, json, os, re, shutil, sys, tempfile, threading
from urllib import parse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from securesystemslib.signer import CryptoSigner, SSlibKey
from tuf.api.metadata import (Metadata, MetaFile, Root, Snapshot, TargetFile, Targets, Timestamp)
from tuf.api.serialization.json import JSONSerializer

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = json.load(open(os.path.join(HERE, "channel.json")))
EXPIRY = CONF["expiry_days"]
REFRESH = CONF["refresh_within_days"]
SER = JSONSerializer(compact=False)
SPEC = "1.0.31"
BUNDLE_FIELDS = ("board", "version", "compatible", "min_from_version", "security",
                 "built_from_snapshot", "sbom", "cve_report")


def now():
    fixed = os.environ.get("ONEMIND_TUF_NOW")          # tests only: a fixed clock
    t = datetime.datetime.fromisoformat(fixed) if fixed else datetime.datetime.now(datetime.timezone.utc)
    return t.replace(microsecond=0)


def expires(role, base=None):
    return (base or now()) + datetime.timedelta(days=EXPIRY[role])


# ------------------------------------------------------------------ keys
def _read(spec):
    if spec.startswith("env:"):
        v = os.environ.get(spec[4:], "")
        if not v.strip():
            raise SystemExit(f"key {spec}: environment variable is empty")
        return v.encode()
    return open(spec, "rb").read()


PASSPHRASE_ENV = "ONEMIND_TUF_PASSPHRASE"     # rehearsals and tests; a real ceremony types the passphrase
MIN_PASSPHRASE = 12


def _passphrase(label, confirm=False):
    """A key's passphrase: $ONEMIND_TUF_PASSPHRASE (rehearsal, tests) or typed at the terminal."""
    pw = os.environ.get(PASSPHRASE_ENV)
    if pw is None:
        pw = getpass.getpass(f"passphrase for {label}: ")
        if confirm and getpass.getpass("again: ") != pw:
            raise SystemExit("the two passphrases differ; nothing was written")
    if confirm and len(pw) < MIN_PASSPHRASE:
        raise SystemExit(f"use a passphrase of at least {MIN_PASSPHRASE} characters; nothing was written")
    return pw.encode()


HSM_PREFIX = "hsm:"
PIN_ENV = "ONEMIND_TUF_PIN"                   # tests only; a real ceremony types the PIN at a no-echo prompt


def _env_pin():
    """$ONEMIND_TUF_PIN, but only for a SoftHSM token (rehearsals and tests). With any other PKCS#11 module
    (a YubiKey's libykcs11, a real HSM) a PIN in the environment is refused: a real PIN is typed at a
    no-echo prompt, never kept where every child process and a shell history can see it."""
    pin = os.environ.get(PIN_ENV)
    if not pin:
        return None
    if not os.path.basename(os.environ.get("PYKCS11LIB", "")).startswith("libsofthsm2"):
        raise SystemExit(f"refusing: {PIN_ENV} is for SoftHSM rehearsals and tests only. A real token's PIN is typed "
                         f"at the prompt: unset {PIN_ENV} and run again.")
    return pin


YUBIKEY_LABEL = "YubiKey PIV #{}"          # the token label Yubico's PKCS#11 module (ykcs11) gives each device


def _hsm_ref(spec):
    """(key id or None, token label or None) of hsm:<id>[?label=L | ?yubikey=<serial>]. The query is read
    without fragment handling, so a label such as "YubiKey PIV #123" keeps its "#"."""
    u = parse.urlparse(spec, allow_fragments=False)
    q = dict(parse.parse_qsl(u.query, keep_blank_values=True))
    label = q.get("label")
    if q.get("yubikey"):
        if label or not q["yubikey"].isdigit():
            raise SystemExit(f"key {spec}: give either label=<token label> or yubikey=<serial digits>, not both")
        label = YUBIKEY_LABEL.format(q["yubikey"])
    try:
        return (int(u.path) if u.path else None), label
    except ValueError:
        raise SystemExit(f"key {spec}: the key id after hsm: must be a number (YubiKey slot 9c is 2)")


def _token_signer_class():
    """securesystemslib's HSMSigner, plus a context login before each signature when the key asks for one
    (CKA_ALWAYS_AUTHENTICATE: a YubiKey PIV key with PIN policy "always", which is slot 9c's default).
    The plain HSMSigner does not do that login, so such a key would refuse every signature."""
    import pkcs11, pkcs11.util.ec
    from securesystemslib.signer import HSMSigner, Signature

    class TokenSigner(HSMSigner):
        def sign(self, payload):
            hasher = hashlib.new(name=f"sha{self.public_key.scheme[-3:]}")
            hasher.update(payload)
            pin = self.pin_handler(self.SECRETS_HANDLER_MSG)
            token = self._find_token(self.token_label)
            with token.open(user_pin=pin) as session:
                key = self._find_signing_key(session, self.hsm_keyid)
                try:
                    again = bool(key[pkcs11.Attribute.ALWAYS_AUTHENTICATE])
                except Exception:                 # a module that does not know the attribute: no context login
                    again = False
                raw = key.sign(hasher.digest(), mechanism=pkcs11.Mechanism.ECDSA, pin=pin if again else None)
            return Signature(self.public_key.keyid, pkcs11.util.ec.encode_ecdsa_signature(raw).hex())

    return TokenSigner


def _hsm(spec):
    """(signer, public key) of a token key: spec hsm:<id>[?label=<token label>] (securesystemslib's
    HSMSigner, python-pkcs11). The key is ECDSA P-256; the private part never leaves the token."""
    if not os.environ.get("PYKCS11LIB"):
        raise SystemExit(f"key {spec}: set PYKCS11LIB to the token's PKCS#11 module "
                         f"(YubiKey: libykcs11.so; tests: libsofthsm2.so)")
    try:
        from securesystemslib.signer import HSMSigner
        signer_class = _token_signer_class()
    except ImportError as e:                      # pragma: no cover
        raise SystemExit(f"key {spec}: PKCS#11 support is missing ({e}); install os/update/requirements-tuf.txt")
    keyid, label = _hsm_ref(spec)
    pin = []

    def pin_handler(_what):                       # typed once per key, however often it signs
        if not pin:
            pin.append(_env_pin() or getpass.getpass(f"PIN for token key {spec}: "))
        return pin[0]

    try:
        uri, pub = HSMSigner.import_(keyid, label, pin_handler)
        return signer_class.from_priv_key_uri(uri, pub, pin_handler), pub
    except Exception as e:                        # the token, the module or the key is not as named
        raise SystemExit(f"key {spec}: {e}")


def token_keygen(spec, pin_always=False):
    """Make an ECDSA P-256 key ON a PKCS#11 token: generated inside it, never extractable, sensitive. For
    SoftHSM rehearsals and generic tokens. A YubiKey is refused here: ykman makes its key, because only
    ykman sets the PIN and touch policy and gives the attestation (scripts/tuf-bootstrap-root.sh yubikey-key).
    pin_always marks the key CKA_ALWAYS_AUTHENTICATE (the PIN for every signature), like YubiKey slot 9c."""
    lib = os.environ.get("PYKCS11LIB", "")
    if not lib:
        raise SystemExit("set PYKCS11LIB to the token's PKCS#11 module")
    if "ykcs11" in os.path.basename(lib):
        raise SystemExit("a YubiKey's key is made with ykman (PIN and touch policy, attestation): "
                         "scripts/tuf-bootstrap-root.sh yubikey-key")
    keyid, label = _hsm_ref(spec)
    if keyid is None or not label:
        raise SystemExit(f"key {spec}: name the key id and the token, hsm:<id>?label=<token label>")
    import pkcs11, pkcs11.util.ec
    try:
        token = pkcs11.lib(lib).get_token(token_label=label)
    except Exception as e:
        raise SystemExit(f"token {label!r}: {e}")
    pin = _env_pin() or getpass.getpass(f"PIN for token {label}: ")
    cid = pkcs11.util.biginteger(keyid)
    with token.open(rw=True, user_pin=pin) as session:
        if list(session.get_objects({pkcs11.Attribute.ID: cid})):
            raise SystemExit(f"token {label!r} already holds a key with id {keyid}; refusing to replace a key")
        params = session.create_domain_parameters(
            pkcs11.KeyType.EC, {pkcs11.Attribute.EC_PARAMS: pkcs11.util.ec.encode_named_curve_parameters("secp256r1")},
            local=True)
        params.generate_keypair(store=True, id=cid, label="onemind-root", private_template={
            pkcs11.Attribute.EXTRACTABLE: False, pkcs11.Attribute.SENSITIVE: True,
            pkcs11.Attribute.ALWAYS_AUTHENTICATE: bool(pin_always)})
    return _hsm(spec)[1]


def sign_with(md, signer, label):
    try:
        md.sign(signer, append=True)
    except Exception as e:                        # e.g. a wrong PIN (three wrong ones lock a real token)
        raise SystemExit(f"signing with {label} failed: {e.__cause__ or e}")


def load_signer(spec):
    if spec.startswith(HSM_PREFIX):
        return _hsm(spec)[0]
    data = _read(spec)
    password = None
    if b"ENCRYPTED PRIVATE KEY" in data:           # PKCS#8 with a passphrase (an offline root key)
        password = _passphrase(spec)
    try:
        priv = serialization.load_pem_private_key(data, password=password)
    except ValueError as e:
        raise SystemExit(f"key {spec}: cannot be read ({'wrong passphrase' if password else e})")
    if not isinstance(priv, ed25519.Ed25519PrivateKey):
        raise SystemExit(f"key {spec}: not an ed25519 private key")
    return CryptoSigner(priv)


def load_pub(spec):
    if spec.startswith(HSM_PREFIX):
        return _hsm(spec)[1]
    data = _read(spec)
    if b"PRIVATE KEY" in data:
        return load_signer(spec).public_key
    return SSlibKey.from_crypto(serialization.load_pem_public_key(data))


def keygen(out_dir, roles, encrypt=False):
    """Make one ed25519 key per role. Never overwrites a key; --encrypt protects it with a passphrase."""
    os.makedirs(out_dir, exist_ok=True)
    for r in roles:
        if os.path.exists(os.path.join(out_dir, f"{r}.key")):
            raise SystemExit(f"{out_dir}/{r}.key already exists; refusing to overwrite a key")
    for r in roles:
        k = ed25519.Ed25519PrivateKey.generate()
        p = os.path.join(out_dir, f"{r}.key")
        enc = (serialization.BestAvailableEncryption(_passphrase(p, confirm=True)) if encrypt
               else serialization.NoEncryption())
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc))
        with open(os.path.join(out_dir, f"{r}.pub"), "wb") as f:
            f.write(k.public_key().public_bytes(serialization.Encoding.PEM,
                                                serialization.PublicFormat.SubjectPublicKeyInfo))


def token_pub(spec, out):
    """Write a token key's PUBLIC key (PEM) so its holder can hand it over. Never overwrites."""
    pub = _hsm(spec)[1]
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; refusing to overwrite it")
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(pub.keyval["public"])
    return pub


# ------------------------------------------------------------------ root (offline)
def init_root(root_keys, root_pubs, threshold, targets_pub, snapshot_pub, timestamp_pub, out,
              expires_days=None, version=1):
    if os.path.exists(os.path.join(out, "root.json")) or os.path.exists(os.path.join(out, f"{version}.root.json")):
        raise SystemExit(f"{out} already holds a root.json; refusing to overwrite it (use a new directory)")
    signers = [load_signer(k) for k in root_keys]
    pubs = [s.public_key for s in signers] + [load_pub(p) for p in root_pubs]
    if len({k.keyid for k in pubs}) < threshold or len(signers) < threshold:
        raise SystemExit(f"need at least {threshold} distinct root keys, {threshold} of them to sign")
    root = Root(expires=now() + datetime.timedelta(days=expires_days or EXPIRY["root"]),
                consistent_snapshot=False, spec_version=SPEC, version=version)
    for k in pubs:
        root.add_key(k, Root.type)
    root.roles[Root.type].threshold = threshold
    for role, p in ((Targets.type, targets_pub), (Snapshot.type, snapshot_pub), (Timestamp.type, timestamp_pub)):
        root.add_key(load_pub(p), role)
    md = Metadata(root)
    for s in signers:
        sign_with(md, s, s.public_key.keyid[:12])
    md.verify_delegate(Root.type, md)            # threshold met by the signatures just made
    os.makedirs(out, exist_ok=True)
    md.to_file(os.path.join(out, f"{version}.root.json"), SER)
    md.to_file(os.path.join(out, "root.json"), SER)
    return md


def rotate_root(old_root_path, old_keys, new_keys, new_pubs, threshold, out, expires_days=None, online_pubs=None):
    """The next root.json: new root keys and threshold, version + 1, online keys kept unless
    online_pubs ({"targets": P, ...}) replaces them. A client that trusts only the OLD root accepts it
    when a threshold of the OLD root keys AND a threshold of the NEW root keys signed it (TUF spec
    5.3.4), so both are required here and nothing is written otherwise. Offline only."""
    old_md = Metadata[Root].from_file(old_root_path)
    old = old_md.signed
    try:
        old_md.verify_delegate(Root.type, old_md)
    except Exception as e:
        raise SystemExit(f"{old_root_path} does not verify against its own keys ({e}); not rotating from it")
    version = old.version + 1
    for name in (f"{version}.root.json", "root.json"):
        if os.path.exists(os.path.join(out, name)):
            raise SystemExit(f"{out}/{name} exists; refusing to overwrite it (use a new directory)")
    old_signers = [load_signer(k) for k in old_keys]
    old_role = old.roles[Root.type]
    old_have = {s.public_key.keyid for s in old_signers}
    stray = [k[:12] for k in old_have if k not in old_role.keyids]
    if stray:
        raise SystemExit(f"old key(s) {stray} are not root keys of {old_root_path}")
    if len(old_have) < old_role.threshold:
        raise SystemExit(f"the current root needs {old_role.threshold} of its {len(old_role.keyids)} root keys "
                         f"to sign the rotation; {len(old_have)} given")
    new_signers = [load_signer(k) for k in new_keys]
    new_have = {s.public_key.keyid for s in new_signers}
    new_pubs = {k.keyid: k for k in [s.public_key for s in new_signers] + [load_pub(p) for p in new_pubs]}
    if threshold < 1 or len(new_pubs) < threshold:
        raise SystemExit(f"a new threshold of {threshold} needs at least that many distinct new root keys "
                         f"({len(new_pubs)} given)")
    if len(new_have) < threshold:
        raise SystemExit(f"the new root keys must sign too: {threshold} of them are needed, {len(new_have)} given")
    root = Root.from_dict(copy.deepcopy(old.to_dict()))
    root.version, root.expires = version, now() + datetime.timedelta(days=expires_days or EXPIRY["root"])
    for role in (online_pubs or {}):
        root.roles[role].keyids.clear()
        root.add_key(load_pub(online_pubs[role]), role)
    root.roles[Root.type].keyids.clear()
    for k in new_pubs.values():
        root.add_key(k, Root.type)
    root.roles[Root.type].threshold = threshold
    root.keys = {kid: k for kid, k in root.keys.items() if any(kid in r.keyids for r in root.roles.values())}
    online = [root.roles[r].keyids for r in (Targets.type, Snapshot.type, Timestamp.type)]
    if len(set().union(*online)) != 3 or set().union(*online) & set(new_pubs):
        raise SystemExit("targets, snapshot, timestamp and root must each use their own key")
    md = Metadata(root)
    for s in {s.public_key.keyid: s for s in old_signers + new_signers}.values():   # a key in both signs once
        sign_with(md, s, s.public_key.keyid[:12])
    try:
        old_md.verify_delegate(Root.type, md)    # what a box that trusts only the old root checks first...
        md.verify_delegate(Root.type, md)        # ...then the new root against its own keys
    except Exception as e:
        raise SystemExit(f"the rotated root does not verify under both key sets ({e}); nothing was written")
    os.makedirs(out, exist_ok=True)
    md.to_file(os.path.join(out, f"{version}.root.json"), SER)
    md.to_file(os.path.join(out, "root.json"), SER)
    return md


def box_accepts(old_md, new_md):
    """Would a box holding root `old_md` accept `new_md` as its next root? Returns the problems (empty: yes).

    The TUF client rule (spec 5.3): the next root is exactly version N+1, signed by the threshold of the
    keys the OLD root trusts and by the threshold of the keys the NEW root trusts, and not expired.
    """
    problems = []
    if new_md.signed.version != old_md.signed.version + 1:
        problems.append(f"version {new_md.signed.version} does not follow {old_md.signed.version}")
    for who, md in (("the old root's keys", old_md), ("the new root's keys", new_md)):
        try:
            md.verify_delegate(Root.type, new_md)
        except Exception as e:
            problems.append(f"signatures do not meet the threshold of {who}: {e}")
    if new_md.signed.expires <= now():
        problems.append("the new root is already expired")
    return problems


def renew_root(current, root_keys, out, expires_days=None):
    """Root version N+1: same keys and thresholds, new expiry, signed by the current root keys. OFFLINE ONLY.

    Not a key rotation: the keys do not change, so the box needs nothing but the new file (served as
    <N+1>.root.json next to the older ones; it walks the chain). Refuses unless the threshold of the
    CURRENT root's keys signs, and checks the result the way a box would before writing anything.
    """
    old = Metadata[Root].from_file(current)
    try:
        old.verify_delegate(Root.type, old)
    except Exception as e:
        raise SystemExit(f"{current} is not validly signed by its own root keys; renew from the real current root ({e})")
    n = old.signed.version + 1
    if os.path.exists(os.path.join(out, "root.json")) or os.path.exists(os.path.join(out, f"{n}.root.json")):
        raise SystemExit(f"{out} already holds a root.json; refusing to overwrite it (use a new directory)")
    signers = [load_signer(k) for k in root_keys]
    ids = [s.public_key.keyid for s in signers]
    trusted = set(old.signed.roles[Root.type].keyids)
    if len(set(ids)) != len(ids):
        raise SystemExit("the same root key was given twice; every signer must be a different holder")
    stranger = [i[:12] for i in ids if i not in trusted]
    if stranger:
        raise SystemExit(f"key(s) {stranger} are not root keys of {current}; nothing was written")
    need = old.signed.roles[Root.type].threshold
    if len(signers) < need:
        raise SystemExit(f"need {need} of the root keys to sign a renewal, got {len(signers)}; nothing was written")
    new = Root.from_dict(old.signed.to_dict())
    new.version = n
    new.expires = now() + datetime.timedelta(days=expires_days or EXPIRY["root"])
    md = Metadata(new)
    for sg in signers:
        md.sign(sg, append=True)
    problems = box_accepts(old, md)
    if problems:
        raise SystemExit("the renewed root would be refused by a box: " + "; ".join(problems))
    os.makedirs(out, exist_ok=True)
    md.to_file(os.path.join(out, f"{n}.root.json"), SER)
    md.to_file(os.path.join(out, "root.json"), SER)
    return md


def inspect_root(root_path, expect_threshold=None, expect_root_keys=None, prev=None):
    """Read a root.json the way a box would trust it: every signature checked, the numbers shown.

    Returns (lines to print, problems). The ceremony ends with this, so what is committed is what
    was meant: 2-of-3 on the root, one key each for the online roles, and enough time left.
    """
    md = Metadata[Root].from_file(root_path)
    root, problems, lines = md.signed, [], []
    try:
        md.verify_delegate(Root.type, md)
    except Exception as e:
        problems.append(f"the root's own signatures do not meet its threshold: {e}")
    good = {k for k in root.roles[Root.type].keyids if k in md.signatures}
    lines.append(f"root.json version {root.version}, spec {root.spec_version}, expires {root.expires.isoformat()} "
                 f"({(root.expires - now()).days} days left)")
    with open(root_path, "rb") as f:
        lines.append(f"sha256 {hashlib.sha256(f.read()).hexdigest()}")
    for name in (Root.type, Targets.type, Snapshot.type, Timestamp.type):
        role = root.roles[name]
        lines.append(f"{name:<9} threshold {role.threshold} of {len(role.keyids)}; keyids " +
                     ", ".join(k[:16] for k in sorted(role.keyids)))
    lines.append(f"root signatures on file: {len(md.signatures)} (valid and trusted: {len(good)})")
    if expect_threshold is not None and root.roles[Root.type].threshold != expect_threshold:
        problems.append(f"root threshold is {root.roles[Root.type].threshold}, expected {expect_threshold}")
    if expect_root_keys is not None and len(root.roles[Root.type].keyids) != expect_root_keys:
        problems.append(f"root has {len(root.roles[Root.type].keyids)} keys, expected {expect_root_keys}")
    online = [set(root.roles[r].keyids) for r in (Targets.type, Snapshot.type, Timestamp.type)]
    if len(set().union(*online)) != 3 or set().union(*online) & set(root.roles[Root.type].keyids):
        problems.append("targets, snapshot, timestamp and root must each use their own key")
    if len(good) < root.roles[Root.type].threshold:
        problems.append("fewer valid root signatures than the threshold")
    if prev:                                     # a rotation: a box that trusts only the previous root checks this
        old = Metadata[Root].from_file(prev)
        try:
            old.verify_delegate(Root.type, md)
            lines.append(f"previous root v{old.signed.version}: {old.signed.roles[Root.type].threshold} of its keys "
                         f"signed this root too")
        except Exception as e:
            problems.append(f"the previous root's keys (threshold {old.signed.roles[Root.type].threshold}) did not "
                            f"sign this root: {e}")
        if root.version != old.signed.version + 1:
            problems.append(f"version {root.version} does not follow the previous root's version {old.signed.version}")
    return lines, problems


# ------------------------------------------------------------------ helpers
def _vkey(v):
    """Release versions <base>.<YYYYMMDDHHMMSS> (and dev strings) -> sortable tuple."""
    return tuple((0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"[.\-+]", v))


def _check_signer(root, role, signer):
    if signer.public_key.keyid not in root.roles[role].keyids:
        raise SystemExit(f"the {role} key (keyid {signer.public_key.keyid[:12]}…) is not trusted by root.json; "
                         f"re-run the offline root ceremony (scripts/tuf-bootstrap-root.sh) or use the right key")


def _write(md, repo, name):
    p = os.path.join(repo, name)
    md.to_file(p, SER)
    return p


def _load(path):
    return Metadata.from_file(path) if os.path.exists(path) else None


def _meta_for(path, version):
    data = open(path, "rb").read()
    return MetaFile(version=version, length=len(data), hashes={"sha256": hashlib.sha256(data).hexdigest()})


def verify_existing(root_md, tmd, smd, xmd, snapshot_path):
    """Signatures and cross-references of channel metadata we are about to build on or re-sign,
    against the TRUSTED root (the committed one), ignoring expiry (an expired channel must still be
    recoverable). The files come from the hosting (release assets): never re-sign what we cannot
    verify, or a planted targets.json would be laundered into a validly signed one."""
    try:
        root_md.verify_delegate(Targets.type, tmd)
        root_md.verify_delegate(Snapshot.type, smd)
        root_md.verify_delegate(Timestamp.type, xmd)
    except Exception as e:
        raise SystemExit(f"existing channel metadata does not verify against the trusted root ({e}); refusing "
                         f"to build on it (after an online-key rotation, rebuild the channel by hand)")
    if smd.signed.meta.get("targets.json") is None or smd.signed.meta["targets.json"].version != tmd.signed.version:
        raise SystemExit("existing snapshot.json does not reference this targets.json version")
    sm = xmd.signed.snapshot_meta
    have = _meta_for(snapshot_path, smd.signed.version)
    if sm.version != smd.signed.version or (sm.hashes and sm.hashes != have.hashes) or \
            (sm.length is not None and sm.length != have.length):
        raise SystemExit("existing timestamp.json does not match snapshot.json")


def copy_roots(src, dst, root_md):
    if src:
        for f in os.listdir(src):
            if re.fullmatch(r"\d+\.root\.json", f) and not os.path.exists(os.path.join(dst, f)):
                shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
    root_md.to_file(os.path.join(dst, f"{root_md.signed.version}.root.json"), SER)
    root_md.to_file(os.path.join(dst, "root.json"), SER)


# ------------------------------------------------------------------ build
def build(repo, root_path, prev, releases, tk, sk, xk, keep=None, allow_dry_run=False):
    keep = keep or CONF["keep_versions_per_board"]
    os.makedirs(repo, exist_ok=True)
    root_md = Metadata[Root].from_file(root_path)
    root = root_md.signed
    tsig, ssig, xsig = load_signer(tk), load_signer(sk), load_signer(xk)
    _check_signer(root, Targets.type, tsig)
    _check_signer(root, Snapshot.type, ssig)
    _check_signer(root, Timestamp.type, xsig)
    old_t = _load(os.path.join(prev, "targets.json")) if prev else None
    old_s = _load(os.path.join(prev, "snapshot.json")) if prev else None
    old_x = _load(os.path.join(prev, "timestamp.json")) if prev else None
    if old_t or old_s or old_x:
        if not (old_t and old_s and old_x):
            raise SystemExit(f"{prev}: incomplete channel metadata (need targets, snapshot and timestamp.json)")
        verify_existing(root_md, old_t, old_s, old_x, os.path.join(prev, "snapshot.json"))
    for rel_path in releases:
        if json.load(open(rel_path)).get("dry_run") is not False and not allow_dry_run:
            raise SystemExit(f"{rel_path}: a dry-run (throwaway-key) bundle or no dry_run field; "
                             f"only --allow-dry-run (throwaway TUF keys) may list it")
    t = Targets(version=(old_t.signed.version + 1) if old_t else 1, spec_version=SPEC, expires=expires("targets"),
                targets=dict(old_t.signed.targets) if old_t else {})
    for rel_path in releases:
        rel = json.load(open(rel_path))
        d = os.path.dirname(os.path.abspath(rel_path))
        board, ver = rel["board"], rel["version"]
        prefix = f"{board}/{ver}/"
        newer = [p for p, tf in t.targets.items() if p.endswith(".raucb") and tf.custom.get("board") == board
                 and _vkey(tf.custom.get("version", "")) >= _vkey(ver)]
        if newer:
            raise SystemExit(f"{board} {ver}: the channel already lists {newer}; versions must increase (anti-rollback)")
        files = rel["files"]
        paths = {k: prefix + os.path.basename(files[k]) for k in ("bundle", "sbom", "cve_report")}
        for kind, fname in files.items():
            local = os.path.join(d, fname)
            tpath = prefix + os.path.basename(fname)
            tf = TargetFile.from_file(tpath, local, ["sha256"])
            if kind == "bundle":
                tf.unrecognized_fields["custom"] = {
                    "board": board, "version": ver, "compatible": rel["compatible"],
                    "min_from_version": rel.get("min_from_version", CONF["min_from_version"]),
                    "security": bool(rel.get("security", True)), "built_from_snapshot": rel["snapshot"],
                    "sbom": paths["sbom"], "cve_report": paths["cve_report"]}
            else:
                tf.unrecognized_fields["custom"] = {"board": board, "version": ver, "kind": kind}
            t.targets[tpath] = tf
            shutil.copyfile(local, os.path.join(repo, os.path.basename(tpath)))
    # keep the newest N versions per board (a box several releases behind still finds one)
    by_board = {}
    for p, tf in t.targets.items():
        if p.endswith(".raucb"):
            by_board.setdefault(tf.custom.get("board"), []).append(tf.custom.get("version", ""))
    keep_dirs = {f"{b}/{v}/" for b, vs in by_board.items() for v in sorted(vs, key=_vkey)[-keep:]}
    t.targets = {p: tf for p, tf in sorted(t.targets.items()) if p[:p.rfind("/") + 1] in keep_dirs}
    tmd = Metadata(t)
    tmd.sign(tsig)
    tp = _write(tmd, repo, "targets.json")
    s = Snapshot(version=(old_s.signed.version + 1) if old_s else 1, spec_version=SPEC, expires=expires("snapshot"),
                 meta={"targets.json": MetaFile(version=t.version)})
    smd = Metadata(s)
    smd.sign(ssig)
    sp = _write(smd, repo, "snapshot.json")
    x = Timestamp(version=(old_x.signed.version + 1) if old_x else 1, spec_version=SPEC,
                  expires=expires("timestamp"), snapshot_meta=_meta_for(sp, s.version))
    xmd = Metadata(x)
    xmd.sign(xsig)
    _write(xmd, repo, "timestamp.json")
    copy_roots(prev, repo, root_md)
    return {"targets": t.version, "snapshot": s.version, "timestamp": x.version, "files": sorted(t.targets)}


# ------------------------------------------------------------------ refresh (daily job)
def refresh(repo, xk, sk=None, tk=None, force=False, root_path=None):
    """root_path: the TRUSTED root (committed); defaults to the repo's copy (local use only)."""
    root_md = Metadata[Root].from_file(root_path or os.path.join(repo, "root.json"))
    root = root_md.signed
    tmd = Metadata[Targets].from_file(os.path.join(repo, "targets.json"))
    smd = Metadata[Snapshot].from_file(os.path.join(repo, "snapshot.json"))
    xmd = Metadata[Timestamp].from_file(os.path.join(repo, "timestamp.json"))
    verify_existing(root_md, tmd, smd, xmd, os.path.join(repo, "snapshot.json"))
    soon = lambda md, role: md.signed.expires - now() <= datetime.timedelta(days=REFRESH[role])
    done = []
    if tk and (force or soon(tmd, "targets")):
        sig = load_signer(tk); _check_signer(root, Targets.type, sig)
        tmd.signed.version += 1; tmd.signed.expires = expires("targets"); tmd.signatures.clear(); tmd.sign(sig)
        _write(tmd, repo, "targets.json"); done.append("targets")
    if "targets" in done or (sk and (force or soon(smd, "snapshot"))):
        if not sk:
            raise SystemExit("targets changed: the snapshot key is needed too")
        sig = load_signer(sk); _check_signer(root, Snapshot.type, sig)
        smd.signed.version += 1; smd.signed.expires = expires("snapshot")
        smd.signed.meta["targets.json"] = MetaFile(version=tmd.signed.version)
        smd.signatures.clear(); smd.sign(sig); _write(smd, repo, "snapshot.json"); done.append("snapshot")
    sig = load_signer(xk); _check_signer(root, Timestamp.type, sig)
    xmd.signed.version += 1; xmd.signed.expires = expires("timestamp")
    xmd.signed.snapshot_meta = _meta_for(os.path.join(repo, "snapshot.json"), smd.signed.version)
    xmd.signatures.clear(); xmd.sign(sig); _write(xmd, repo, "timestamp.json"); done.append("timestamp")
    return done


# ------------------------------------------------------------------ verify (a client's view)
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def verify(repo, root_path, metadata_only=False, allow_absent=False):
    from tuf.ngclient import Updater
    import urllib.request
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=repo))
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    work = tempfile.mkdtemp(prefix="tuf-verify-")
    problems, checked = [], []
    try:
        trusted = open(root_path, "rb").read()      # the root.json a box ships (CHANNEL.md §2)
        up = Updater(metadata_dir=work, metadata_base_url=base, target_dir=work, target_base_url=base,
                     bootstrap=trusted)
        up.refresh()                                   # root chain, expiry, rollback, signatures
        targets = Metadata[Targets].from_file(os.path.join(work, "targets.json")).signed.targets
        for path in sorted(targets):
            info = up.get_targetinfo(path)
            if info is None:
                problems.append(f"{path}: not resolvable")
                continue
            if path.endswith(".raucb"):
                c = info.custom
                miss = [f for f in BUNDLE_FIELDS if f not in c]
                if miss:
                    problems.append(f"{path}: custom metadata lacks {miss}")
                b, v = c.get("board"), c.get("version")
                if path != f"{b}/{v}/onemind-{b}-{v}.raucb":
                    problems.append(f"{path}: path does not match board/version {b}/{v}")
                for ref in ("sbom", "cve_report"):
                    if c.get(ref) not in targets:
                        problems.append(f"{path}: {ref} {c.get(ref)} is not a target")
            local = os.path.join(repo, os.path.basename(path))
            if allow_absent and not os.path.exists(local):
                continue                               # an older build's file, already on the channel
            if not metadata_only:
                try:
                    with urllib.request.urlopen(base + os.path.basename(path)) as r:   # flat layout
                        info.verify_length_and_hashes(r.read())
                except Exception as e:
                    problems.append(f"{path}: {e}")
                    continue
            checked.append(path)
    finally:
        srv.shutdown()
        shutil.rmtree(work, ignore_errors=True)
    return checked, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("keygen"); g.add_argument("--out-dir", required=True)
    g.add_argument("--roles", default="root,targets,snapshot,timestamp")
    g.add_argument("--encrypt", action="store_true", help="protect each private key with a passphrase")
    i = sub.add_parser("inspect"); i.add_argument("--root", required=True)
    i.add_argument("--expect-threshold", type=int); i.add_argument("--expect-root-keys", type=int)
    i.add_argument("--prev", help="the previous root.json: check that its keys signed this root (a rotation)")
    t = sub.add_parser("token-pub"); t.add_argument("--key", required=True); t.add_argument("--out", required=True)
    tk = sub.add_parser("token-keygen"); tk.add_argument("--key", required=True)
    tk.add_argument("--pin-always", action="store_true", help="the PIN for every signature (like YubiKey slot 9c)")
    o = sub.add_parser("rotate-root"); o.add_argument("--root", required=True)
    o.add_argument("--old-key", action="append", required=True)
    o.add_argument("--new-key", action="append", default=[]); o.add_argument("--new-pub", action="append", default=[])
    o.add_argument("--threshold", type=int, required=True); o.add_argument("--out", required=True)
    o.add_argument("--expires-days", type=int)
    for role in ("targets", "snapshot", "timestamp"):
        o.add_argument(f"--{role}-pub", help=f"replace the {role} key (default: keep the current one)")
    r = sub.add_parser("init-root")
    r.add_argument("--root-key", action="append", required=True)
    r.add_argument("--root-pub", action="append", default=[])
    r.add_argument("--threshold", type=int, default=1)
    for role in ("targets", "snapshot", "timestamp"):
        r.add_argument(f"--{role}-pub", required=True)
    r.add_argument("--out", required=True); r.add_argument("--expires-days", type=int)
    r.add_argument("--version", type=int, default=1)
    n = sub.add_parser("renew-root")
    n.add_argument("--current", required=True); n.add_argument("--root-key", action="append", required=True)
    n.add_argument("--out", required=True); n.add_argument("--expires-days", type=int)
    b = sub.add_parser("build")
    b.add_argument("--repo", required=True); b.add_argument("--root", required=True); b.add_argument("--prev")
    b.add_argument("--release", action="append", required=True)
    for role in ("targets", "snapshot", "timestamp"):
        b.add_argument(f"--{role}-key", required=True)
    b.add_argument("--keep", type=int)
    b.add_argument("--allow-dry-run", action="store_true", help="accept dry_run releases (throwaway keys only)")
    f = sub.add_parser("refresh"); f.add_argument("--repo", required=True)
    f.add_argument("--root", help="trusted root.json (default: the repo's copy)")
    f.add_argument("--timestamp-key", required=True); f.add_argument("--snapshot-key"); f.add_argument("--targets-key")
    f.add_argument("--force", action="store_true")
    v = sub.add_parser("verify"); v.add_argument("--repo", required=True); v.add_argument("--root", required=True)
    v.add_argument("--metadata-only", action="store_true")
    v.add_argument("--allow-absent", action="store_true", help="skip targets whose file is not in --repo")
    a = ap.parse_args(argv)
    if os.environ.get("GITHUB_ACTIONS") == "true" and a.cmd in ("init-root", "renew-root", "rotate-root") and not os.environ.get("ONEMIND_TUF_EPHEMERAL"):
        raise SystemExit(f"{a.cmd} makes a ROOT of trust: run it offline (scripts/tuf-bootstrap-root.sh), never in CI")
    if a.cmd == "keygen":
        keygen(a.out_dir, a.roles.split(","), a.encrypt)
    elif a.cmd == "inspect":
        lines, problems = inspect_root(a.root, a.expect_threshold, a.expect_root_keys, a.prev)
        print("\n".join(lines))
        for p in problems:
            print("FAIL " + p)
        return 1 if problems else 0
    elif a.cmd == "init-root":
        md = init_root(a.root_key, a.root_pub, a.threshold, a.targets_pub, a.snapshot_pub, a.timestamp_pub,
                       a.out, a.expires_days, a.version)
        print(f"root v{md.signed.version}: {len(md.signed.roles['root'].keyids)} root key(s), threshold "
              f"{md.signed.roles['root'].threshold}, expires {md.signed.expires.isoformat()}", file=sys.stderr)
    elif a.cmd == "token-keygen":
        pub = token_keygen(a.key, a.pin_always)
        print(f"made on the token: {pub.scheme} key, keyid {pub.keyid} (the private key cannot leave it)", file=sys.stderr)
    elif a.cmd == "token-pub":
        pub = token_pub(a.key, a.out)
        print(f"wrote {a.out}: {pub.scheme} public key, keyid {pub.keyid}", file=sys.stderr)
    elif a.cmd == "rotate-root":
        online = {r: getattr(a, f"{r}_pub") for r in ("targets", "snapshot", "timestamp") if getattr(a, f"{r}_pub")}
        md = rotate_root(a.root, a.old_key, a.new_key, a.new_pub, a.threshold, a.out, a.expires_days, online)
        print(f"root v{md.signed.version}: {len(md.signed.roles['root'].keyids)} root key(s), threshold "
              f"{md.signed.roles['root'].threshold}, expires {md.signed.expires.isoformat()}", file=sys.stderr)
    elif a.cmd == "renew-root":
        md = renew_root(a.current, a.root_key, a.out, a.expires_days)
        print(f"root v{md.signed.version}: same keys, signed by {len(md.signatures)}, expires "
              f"{md.signed.expires.isoformat()}; a box holding v{md.signed.version - 1} accepts it", file=sys.stderr)
    elif a.cmd == "build":
        res = build(a.repo, a.root, a.prev, a.release, a.targets_key, a.snapshot_key, a.timestamp_key, a.keep,
                    a.allow_dry_run)
        print(json.dumps(res, indent=1))
    elif a.cmd == "refresh":
        print("re-signed: " + ", ".join(refresh(a.repo, a.timestamp_key, a.snapshot_key, a.targets_key, a.force,
                                                a.root)))
    elif a.cmd == "verify":
        checked, problems = verify(a.repo, a.root, a.metadata_only, a.allow_absent)
        for p in problems:
            print("FAIL " + p)
        print(f"tuf verify: {len(checked)} target(s) checked, {len(problems)} problem(s)")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
