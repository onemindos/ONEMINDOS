#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind update channel: TUF repository tool (spec 1.0, python-tuf). Interface: os/update/CHANNEL.md.

TUF ("The Update Framework") splits trust over four signed roles so that one stolen online key
cannot push a malicious update: root (certifies the other keys; offline), targets (lists the files
and their hashes), snapshot (pins the current targets version), timestamp (short-lived "this is
fresh" signature). A box trusts only the root.json baked into its image.

Keys are ed25519, PEM (PKCS#8 private, SubjectPublicKeyInfo public). A key argument is a file path
or env:NAME (read from that environment variable, so CI secrets never touch the disk).

  keygen    --out-dir D [--roles root,targets,snapshot,timestamp] [--encrypt]
                                       new keys; never overwrites; --encrypt asks for a passphrase
  inspect   --root root.json [--expect-threshold N] [--expect-root-keys N]
                                       read a root as a box would trust it; exit 1 on any problem
  init-root --root-key K [--root-key K2 ...] [--root-pub P ...] --threshold N
            --targets-pub P --snapshot-pub P --timestamp-pub P --out DIR [--expires-days 365]
            [--version 1]          offline only: writes DIR/<version>.root.json and DIR/root.json
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
import argparse, datetime, functools, getpass, hashlib, http.server, json, os, re, shutil, sys, tempfile, threading

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


def load_signer(spec):
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
        md.sign(s, append=True)
    md.verify_delegate(Root.type, md)            # threshold met by the signatures just made
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


def inspect_root(root_path, expect_threshold=None, expect_root_keys=None):
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
    if os.environ.get("GITHUB_ACTIONS") == "true" and a.cmd in ("init-root", "renew-root") and not os.environ.get("ONEMIND_TUF_EPHEMERAL"):
        raise SystemExit(f"{a.cmd} makes a ROOT of trust: run it offline (scripts/tuf-bootstrap-root.sh), never in CI")
    if a.cmd == "keygen":
        keygen(a.out_dir, a.roles.split(","), a.encrypt)
    elif a.cmd == "inspect":
        lines, problems = inspect_root(a.root, a.expect_threshold, a.expect_root_keys)
        print("\n".join(lines))
        for p in problems:
            print("FAIL " + p)
        return 1 if problems else 0
    elif a.cmd == "init-root":
        md = init_root(a.root_key, a.root_pub, a.threshold, a.targets_pub, a.snapshot_pub, a.timestamp_pub,
                       a.out, a.expires_days, a.version)
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
