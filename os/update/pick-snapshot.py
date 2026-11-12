#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Choose the snapshot.debian.org timestamp for a security rebuild, and write it into the build.

Why a snapshot: the build installs from snapshot.debian.org/archive/<archive>/<TIMESTAMP>/, a frozen
copy of the Debian archive, so the same commit always builds the same packages (brief 30 §2 rule 2).
A security rebuild therefore means "move the pinned timestamp forward", as a reviewed change.

  pick     --report check-*.json ... [--current TS] [--archs amd64,arm64] [--out pick.json]
           Reads the newest debian and debian-security import times from the snapshot API
           (/mr/timestamp/), takes the later one, downloads that snapshot's Packages indexes for
           trixie, trixie-updates and trixie-security per arch, and checks that every fix the
           check reports as available is there. Also checks the CURRENT snapshot: a fix already in
           it but not in the image means the rebuild alone will not pick it up (reported as
           "not_picked_by_build"; scan-gate.py fails the run only if one of them is CRITICAL in Trivy).
  apply    --snapshot TS [--root .]    rewrite SNAPSHOT= in os/rootfs/debian.args and
           base.debian.snapshot in os/versions.lock.yaml (the generated change; both must agree,
           test/unit/test_versions_lock.py)
  version  [--root .]                  print the release version for the committed snapshot:
           <base_version>.<YYYYMMDDHHMMSS> (os/update/channel.json), monotonic with the snapshot

  python3 -I os/update/pick-snapshot.py pick --report out/check-x86_64-efi.json --out pick.json
"""
import argparse, importlib.util, json, lzma, os, re, sys, urllib.request

_spec = importlib.util.spec_from_file_location(
    "check_security", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check-security.py"))
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

SNAPSHOT = "https://snapshot.debian.org"
TS_RX = re.compile(r"^\d{8}T\d{6}Z$")
SUITES = (("debian", "trixie"), ("debian", "trixie-updates"), ("debian-security", "trixie-security"))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def http_get(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "onemind-os-build"})
    with urllib.request.urlopen(req, timeout=timeout) as r:     # follows snapshot's /file/ redirects
        return r.read()


def latest_timestamp(ts_json, archives=("debian", "debian-security")):
    """/mr/timestamp/ JSON -> the newest import time across the archives the build uses."""
    res = ts_json["result"]
    return max(res[a][-1] for a in archives)


def source_versions(packages_text):
    """A Packages index -> {source: highest source version present}."""
    out = {}
    for p in cs.parse_deb822(packages_text):
        if "Package" not in p or "Version" not in p:
            continue
        src, ver = cs.source_of(p)
        if src not in out or cs.vercmp(ver, out[src]) > 0:
            out[src] = ver
    return out


def snapshot_sources(ts, archs, fetch=http_get, base=SNAPSHOT):
    """{arch: {source: version}} for trixie + trixie-updates + trixie-security at timestamp ts."""
    res = {}
    for arch in archs:
        merged = {}
        for archive, suite in SUITES:
            url = f"{base}/archive/{archive}/{ts}/dists/{suite}/main/binary-{arch}/Packages.xz"
            try:
                text = lzma.decompress(fetch(url)).decode("utf-8", "replace")
            except Exception as e:      # a suite can be empty (trixie-updates) -> no index
                print(f"pick-snapshot: no index {archive}/{suite}/{arch} at {ts}: {e}", file=sys.stderr)
                continue
            for s, v in source_versions(text).items():
                if s not in merged or cs.vercmp(v, merged[s]) > 0:
                    merged[s] = v
        res[arch] = merged
    return res


def needed_fixes(reports):
    """{source: fixed_version} over all boards' check reports (fixes the archive has)."""
    need = {}
    for r in reports:
        for f in r["fixes"]:
            if f["available"] and (f["source"] not in need or cs.vercmp(f["fixed_version"], need[f["source"]]) > 0):
                need[f["source"]] = f["fixed_version"]
    return need


def coverage(need, srcs):
    """Which needed fixes the snapshot carries for every arch that ships the source."""
    covered, missing = [], []
    for src, fixed in sorted(need.items()):
        have = [srcs[a].get(src) for a in srcs if srcs[a].get(src)]
        ok = bool(have) and all(cs.vercmp(v, fixed) >= 0 for v in have)
        (covered if ok else missing).append({"source": src, "fixed_version": fixed,
                                             "snapshot_versions": {a: srcs[a].get(src) for a in srcs}})
    return covered, missing


def pick(reports, current, archs, ts_json=None, override=None, fetch=http_get):
    need = needed_fixes(reports)
    if override:
        ts = override
    else:
        ts_json = ts_json or json.loads(fetch(f"{SNAPSHOT}/mr/timestamp/"))
        ts = latest_timestamp(ts_json)
    if not TS_RX.match(ts):
        raise ValueError(f"bad snapshot timestamp {ts!r}")
    if current and ts < current:
        ts = current
    covered, missing = coverage(need, snapshot_sources(ts, archs, fetch)) if need else ([], [])
    stale = []
    if need and current:
        c_cov, _ = coverage(need, snapshot_sources(current, archs, fetch))
        stale = [c["source"] for c in c_cov]
    new = [c["source"] for c in covered if c["source"] not in stale]
    return {"schema": "onemind.snapshot-pick/v1", "snapshot": ts, "previous": current,
            "needed": need, "covered": covered, "missing": missing,
            "not_picked_by_build": stale, "new_fixes": new,
            "rebuild_useful": bool(new) and ts != current}


# ------------------------------------------------------------------ the generated change
def apply(ts, root=ROOT):
    if not TS_RX.match(ts):
        raise ValueError(f"bad snapshot timestamp {ts!r}")
    args = os.path.join(root, "os", "rootfs", "debian.args")
    with open(args) as f:
        t = f.read()
    t2, n = re.subn(r"(?m)^SNAPSHOT=\S+$", f"SNAPSHOT={ts}", t)
    if n != 1:
        raise SystemExit("debian.args: expected exactly one SNAPSHOT= line")
    open(args, "w").write(t2)
    lock = os.path.join(root, "os", "versions.lock.yaml")
    with open(lock) as f:
        lt = f.read()
    lt2, n = re.subn(r'(?m)(^  debian:\n(?:    .*\n)*?    snapshot: )"\d{8}T\d{6}Z"', rf'\g<1>"{ts}"', lt)
    if n != 1:
        raise SystemExit("versions.lock.yaml: expected base.debian.snapshot")
    open(lock, "w").write(lt2)
    return t != t2 or lt != lt2


def current_snapshot(root=ROOT):
    m = re.search(r"(?m)^SNAPSHOT=(\S+)$", open(os.path.join(root, "os", "rootfs", "debian.args")).read())
    return m.group(1)


def release_version(root=ROOT):
    conf = json.load(open(os.path.join(root, "os", "update", "channel.json")))
    ts = current_snapshot(root)
    return f"{conf['base_version']}.{ts[:8]}{ts[9:15]}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick")
    p.add_argument("--report", action="append", required=True)
    p.add_argument("--current")
    p.add_argument("--archs", default="amd64,arm64")
    p.add_argument("--timestamp", help="use this timestamp instead of the newest (re-runs, tests)")
    p.add_argument("--out")
    s = sub.add_parser("apply")
    s.add_argument("--snapshot", required=True)
    s.add_argument("--root", default=ROOT)
    v = sub.add_parser("version")
    v.add_argument("--root", default=ROOT)
    a = ap.parse_args(argv)
    if a.cmd == "apply":
        changed = apply(a.snapshot, a.root)
        print(f"snapshot {a.snapshot}: {'written' if changed else 'unchanged'}", file=sys.stderr)
        return 0
    if a.cmd == "version":
        print(release_version(a.root))
        return 0
    reports = [json.load(open(r)) for r in a.report]
    res = pick(reports, a.current or current_snapshot(), a.archs.split(","), override=a.timestamp)
    text = json.dumps(res, indent=2) + "\n"
    open(a.out, "w").write(text) if a.out else sys.stdout.write(text)
    print(f"pick-snapshot: {res['snapshot']} (was {res['previous']}); new fixes {res['new_fixes']}; "
          f"missing {[m['source'] for m in res['missing']]}; already in the old snapshot but not in the image "
          f"{res['not_picked_by_build']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
