#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Throwaway TUF keys and channels for the signed-update test (test/qemu/CRITERIA-UPDATE-SIGNED.md, US0-US6).

Runs on the build host with the pinned python-tuf (os/update/requirements-tuf.txt), never in the image:

  usrepo.py keys <dir>                      a root of the ceremony's shape (3 root keys, 2 sign, the third trusted
                                            by its public key) + online keys + untrusted "attacker" online keys;
                                            <dir>/overlay/usr/lib/onemind/tuf/security/root.json goes into the image
  usrepo.py channels <dir> <bundles> <board>
                                            the channels C1, C2, CK, CO from the fixture bundles (good.raucb V2,
                                            us-wrongca.raucb V3, us-old.raucb V1), then the PRIVATE keys are deleted

C1 and C2 come from os/update/tuf-repo.py `build`, the publisher the nightly uses. CK (signed by keys the root
does not trust) and CO (an older version listed on newer metadata) are refused by that publisher, so they are
written here with the python-tuf metadata API, in the same format, and the publisher's refusal to list V1 on top
of C2 is recorded in <dir>/channels/summary.json for US5. Every key is a throwaway made for this run.
"""
import argparse, hashlib, importlib.util, json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", ".."))
ROLES = ("targets", "snapshot", "timestamp")
BUNDLES = {"2": "good.raucb", "3": "us-wrongca.raucb", "1": "us-old.raucb"}     # version -> fixture file
ROOT_IN_IMAGE = os.path.join("usr", "lib", "onemind", "tuf", "security", "root.json")


def tuf_repo():
    spec = importlib.util.spec_from_file_location("tuf_repo", os.path.join(SRC, "os", "update", "tuf-repo.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


_COPYFILE = shutil.copyfile                            # the real one: channels() replaces shutil.copyfile below


def link_or_copy(src, dst, *a, **kw):
    """The publisher copies each target into the channel; hard links keep three ~1 GB bundles from being copied."""
    if os.path.lexists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
    except OSError:                                    # another owner (the fixtures are made as root) or another disk
        _COPYFILE(src, dst)
    return dst


def keys(d):
    tr = tuf_repo()
    if os.path.exists(os.path.join(d, "keys")):
        raise SystemExit(f"{d}/keys exists; use a new directory")
    k = lambda *p: os.path.join(d, "keys", *p)
    for h in "abc":
        tr.keygen(k(f"root-{h}"), ["root"])
    tr.keygen(k("online"), list(ROLES))
    tr.keygen(k("attacker"), list(ROLES))
    tr.init_root([k("root-a", "root.key"), k("root-b", "root.key")], [k("root-c", "root.pub")], 2,
                 *(k("online", f"{r}.pub") for r in ROLES), os.path.join(d, "root"))
    dst = os.path.join(d, "overlay", ROOT_IN_IMAGE)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(os.path.join(d, "root", "root.json"), dst)
    os.chmod(dst, 0o644)
    lines, problems = tr.inspect_root(os.path.join(d, "root", "root.json"), 2, 3)
    if problems:
        raise SystemExit("the rehearsal root is not 2-of-3: " + "; ".join(problems))
    print("\n".join(lines))


def compatible(board):
    m = re.search(r"^compatible:\s*(\S+)", open(os.path.join(SRC, "os", "boards", board, "board.yaml")).read(), re.M)
    return m.group(1)


def release(d, board, version, bundle):
    """A release-<board>.json as os/update/build-release.sh writes it, next to the bundle (hard-linked) and empty
    SBOM and CVE files. dry_run is true: the bundle is signed by the fixture's throwaway CA."""
    rel = os.path.join(d, "rel", version)
    os.makedirs(rel, exist_ok=True)
    name = f"onemind-{board}-{version}"
    link_or_copy(bundle, os.path.join(rel, name + ".raucb"))
    for ext in ("spdx.json", "cve-report.json"):
        open(os.path.join(rel, f"{name}.{ext}"), "w").write("{}")
    doc = {"schema": "onemind.release/v1", "board": board, "version": version, "compatible": compatible(board),
           "min_from_version": "0.1.0", "security": True, "snapshot": "20261125T000000Z", "dry_run": True,
           "files": {"bundle": name + ".raucb", "sbom": name + ".spdx.json", "cve_report": name + ".cve-report.json"}}
    p = os.path.join(rel, f"release-{board}.json")
    json.dump(doc, open(p, "w"), indent=1)
    return p


def resign(tr, src, dst, version, tk, sk, xk, targets=None):
    """Copy channel `src` to `dst` with targets/snapshot/timestamp at `version`, signed by tk/sk/xk (key files).
    targets: replace the targets dict (CO). The root files are copied unchanged."""
    os.makedirs(dst)
    for f in os.listdir(src):
        if f.endswith("root.json"):
            shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
    t = tr.Metadata.from_file(os.path.join(src, "targets.json"))
    t.signed.version = version
    if targets is not None:
        t.signed.targets = targets
    t.signatures.clear()
    t.sign(tr.load_signer(tk))
    t.to_file(os.path.join(dst, "targets.json"), tr.SER)
    s = tr.Metadata.from_file(os.path.join(src, "snapshot.json"))
    s.signed.version = version
    s.signed.meta = {"targets.json": tr.MetaFile(version=version)}
    s.signatures.clear()
    s.sign(tr.load_signer(sk))
    sp = os.path.join(dst, "snapshot.json")
    s.to_file(sp, tr.SER)
    x = tr.Metadata.from_file(os.path.join(src, "timestamp.json"))
    x.signed.version = version
    x.signed.snapshot_meta = tr._meta_for(sp, version)
    x.signatures.clear()
    x.sign(tr.load_signer(xk))
    x.to_file(os.path.join(dst, "timestamp.json"), tr.SER)


def channels(d, bundles, board, keep_keys=False):
    tr = tuf_repo()
    shutil.copyfile = link_or_copy                     # the publisher's target copies become hard links
    k = lambda *p: os.path.join(d, "keys", *p)
    on = {r: k("online", f"{r}.key") for r in ROLES}
    bad = {r: k("attacker", f"{r}.key") for r in ROLES}
    root = os.path.join(d, "root", "root.json")
    ch = os.path.join(d, "channels")
    if os.path.exists(ch):
        shutil.rmtree(ch)
    os.makedirs(ch)
    rel = {v: release(d, board, v, os.path.join(bundles, f)) for v, f in BUNDLES.items()}
    build = lambda repo, prev, r: tr.build(os.path.join(ch, repo), root, prev and os.path.join(ch, prev), [r],
                                           on["targets"], on["snapshot"], on["timestamp"], allow_dry_run=True)
    build("C1", None, rel["2"])                        # metadata 1: V2
    build("C2", "C1", rel["3"])                        # metadata 2: V2 and V3 (wrong RAUC CA)
    resign(tr, os.path.join(ch, "C1"), os.path.join(ch, "CK"), 2, bad["targets"], bad["snapshot"], bad["timestamp"])
    build("old-alone", None, rel["1"])                 # only to get V1's signed target entries
    old_targets = tr.Metadata.from_file(os.path.join(ch, "old-alone", "targets.json")).signed.targets
    resign(tr, os.path.join(ch, "C2"), os.path.join(ch, "CO"), 3, on["targets"], on["snapshot"], on["timestamp"],
           targets=dict(old_targets))
    try:                                               # US5: the real publisher must refuse to list V1 after V2/V3
        build("refused", "C2", rel["1"])
        refused, why = False, "the publisher listed V1 on top of C2"
    except SystemExit as e:
        refused, why = True, str(e)
    files = os.path.join(ch, "files")                  # every target file once; the server falls back to it
    os.makedirs(files)
    for v in BUNDLES:
        for f in os.listdir(os.path.join(d, "rel", v)):
            if not f.startswith("release-"):
                link_or_copy(os.path.join(d, "rel", v, f), os.path.join(files, f))
    for repo in ("C1", "C2", "old-alone", "refused"):  # drop the per-channel copies: metadata only per channel
        p = os.path.join(ch, repo)
        for f in os.listdir(p) if os.path.isdir(p) else []:
            if not f.endswith(".json") or f.endswith((".spdx.json", ".cve-report.json")):
                os.remove(os.path.join(p, f))
    shutil.rmtree(os.path.join(ch, "old-alone"), True)
    shutil.rmtree(os.path.join(ch, "refused"), True)
    summary = {"board": board, "root_sha256": sha256(root),
               "bundles": {v: f"onemind-{board}-{v}.raucb" for v in BUNDLES},
               "publisher_refused_old": refused, "publisher_message": why,
               "channels": {c: {r: tr.Metadata.from_file(os.path.join(ch, c, f"{r}.json")).signed.version for r in ROLES}
                            for c in ("C1", "C2", "CK", "CO")}}
    json.dump(summary, open(os.path.join(ch, "summary.json"), "w"), indent=1)
    if not keep_keys:
        shutil.rmtree(os.path.join(d, "keys"))         # throwaway private keys: gone once the channels exist
    print(json.dumps(summary, indent=1))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keys"); k.add_argument("dir")
    c = sub.add_parser("channels"); c.add_argument("dir"); c.add_argument("bundles"); c.add_argument("board")
    c.add_argument("--keep-keys", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.cmd == "keys":
        keys(a.dir)
    else:
        channels(a.dir, a.bundles, a.board, a.keep_keys)
    return 0


if __name__ == "__main__":
    sys.exit(main())
