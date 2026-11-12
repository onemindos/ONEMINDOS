#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OneMind update channel: TUF repository tool (spec 1.0, python-tuf). Interface: os/update/CHANNEL.md.

TUF ("The Update Framework") splits trust over four signed roles so that one stolen online key
cannot push a malicious update: root (certifies the other keys; offline), targets (lists the files
and their hashes), snapshot (pins the current targets version), timestamp (short-lived "this is
fresh" signature). A box trusts only the root.json baked into its image.

Keys are ed25519, PEM (PKCS#8 private, SubjectPublicKeyInfo public). A key argument is a file path
or env:NAME (read from that environment variable, so CI secrets never touch the disk).

  keygen    --out-dir D [--roles root,targets,snapshot,timestamp]      throwaway keys (dev / tests)
  init-root --root-key K [--root-key K2 ...] [--root-pub P ...] --threshold N
            --targets-pub P --snapshot-pub P --timestamp-pub P --out DIR [--expires-days 365]
            [--version 1]          offline only: writes DIR/<version>.root.json and DIR/root.json
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
import argparse, datetime, functools, hashlib, http.server, json, os, re, shutil, sys, tempfile, threading

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


def load_signer(spec):
    priv = serialization.load_pem_private_key(_read(spec), password=None)
    if not isinstance(priv, ed25519.Ed25519PrivateKey):
        raise SystemExit(f"key {spec}: not an ed25519 private key")
    return CryptoSigner(priv)


def load_pub(spec):
    data = _read(spec)
    if b"PRIVATE KEY" in data:
        return load_signer(spec).public_key
    return SSlibKey.from_crypto(serialization.load_pem_public_key(data))


def keygen(out_dir, roles):
    os.makedirs(out_dir, exist_ok=True)
    for r in roles:
        k = ed25519.Ed25519PrivateKey.generate()
        p = os.path.join(out_dir, f"{r}.key")
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()))
        with open(os.path.join(out_dir, f"{r}.pub"), "wb") as f:
            f.write(k.public_key().public_bytes(serialization.Encoding.PEM,
                                                serialization.PublicFormat.SubjectPublicKeyInfo))


# ------------------------------------------------------------------ root (offline)
def init_root(root_keys, root_pubs, threshold, targets_pub, snapshot_pub, timestamp_pub, out,
              expires_days=None, version=1):
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


def copy_roots(src, dst, root_md):
    if src:
        for f in os.listdir(src):
            if re.fullmatch(r"\d+\.root\.json", f) and not os.path.exists(os.path.join(dst, f)):
                shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
    root_md.to_file(os.path.join(dst, f"{root_md.signed.version}.root.json"), SER)
    root_md.to_file(os.path.join(dst, "root.json"), SER)


# ------------------------------------------------------------------ build
def build(repo, root_path, prev, releases, tk, sk, xk, keep=None):
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
def refresh(repo, xk, sk=None, tk=None, force=False):
    root = Metadata[Root].from_file(os.path.join(repo, "root.json")).signed
    tmd = Metadata[Targets].from_file(os.path.join(repo, "targets.json"))
    smd = Metadata[Snapshot].from_file(os.path.join(repo, "snapshot.json"))
    xmd = Metadata[Timestamp].from_file(os.path.join(repo, "timestamp.json"))
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
    r = sub.add_parser("init-root")
    r.add_argument("--root-key", action="append", required=True)
    r.add_argument("--root-pub", action="append", default=[])
    r.add_argument("--threshold", type=int, default=1)
    for role in ("targets", "snapshot", "timestamp"):
        r.add_argument(f"--{role}-pub", required=True)
    r.add_argument("--out", required=True); r.add_argument("--expires-days", type=int)
    r.add_argument("--version", type=int, default=1)
    b = sub.add_parser("build")
    b.add_argument("--repo", required=True); b.add_argument("--root", required=True); b.add_argument("--prev")
    b.add_argument("--release", action="append", required=True)
    for role in ("targets", "snapshot", "timestamp"):
        b.add_argument(f"--{role}-key", required=True)
    b.add_argument("--keep", type=int)
    f = sub.add_parser("refresh"); f.add_argument("--repo", required=True)
    f.add_argument("--timestamp-key", required=True); f.add_argument("--snapshot-key"); f.add_argument("--targets-key")
    f.add_argument("--force", action="store_true")
    v = sub.add_parser("verify"); v.add_argument("--repo", required=True); v.add_argument("--root", required=True)
    v.add_argument("--metadata-only", action="store_true")
    v.add_argument("--allow-absent", action="store_true", help="skip targets whose file is not in --repo")
    a = ap.parse_args(argv)
    if os.environ.get("GITHUB_ACTIONS") == "true" and a.cmd == "init-root" and not os.environ.get("ONEMIND_TUF_EPHEMERAL"):
        raise SystemExit("init-root makes a ROOT of trust: run it offline (scripts/tuf-bootstrap-root.sh), never in CI")
    if a.cmd == "keygen":
        keygen(a.out_dir, a.roles.split(","))
    elif a.cmd == "init-root":
        md = init_root(a.root_key, a.root_pub, a.threshold, a.targets_pub, a.snapshot_pub, a.timestamp_pub,
                       a.out, a.expires_days, a.version)
        print(f"root v{md.signed.version}: {len(md.signed.roles['root'].keyids)} root key(s), threshold "
              f"{md.signed.roles['root'].threshold}, expires {md.signed.expires.isoformat()}", file=sys.stderr)
    elif a.cmd == "build":
        res = build(a.repo, a.root, a.prev, a.release, a.targets_key, a.snapshot_key, a.timestamp_key, a.keep)
        print(json.dumps(res, indent=1))
    elif a.cmd == "refresh":
        print("re-signed: " + ", ".join(refresh(a.repo, a.timestamp_key, a.snapshot_key, a.targets_key, a.force)))
    elif a.cmd == "verify":
        checked, problems = verify(a.repo, a.root, a.metadata_only, a.allow_absent)
        for p in problems:
            print("FAIL " + p)
        print(f"tuf verify: {len(checked)} target(s) checked, {len(problems)} problem(s)")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
