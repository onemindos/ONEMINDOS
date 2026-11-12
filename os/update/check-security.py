#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Which packages in a OneMind image have a Debian security fix newer than the installed version?

debsecan-style matching (poc-v0 §10.1, brief 30 D-B1.5): installed *source* packages are compared
with the Debian security tracker's per-release state. A CVE counts when the tracker marks it
`resolved` for the release with a real fixed version (not "0" = never affected) and the installed
source version sorts before it under dpkg's version rules.

Inputs:
  --packages  /usr/lib/onemind/packages.txt from the image ("<binary> <version> <arch>" per line)
  --status    optional var/lib/dpkg/status from the same rootfs: maps binaries to their source
              package and source version (packages.txt alone cannot; without it the binary name and
              its version minus a binNMU "+bN" suffix stand in for the source)
  --tracker   https://security-tracker.debian.org/tracker/data/json (a local copy)
Output (stdout or --out): JSON, schema onemind.security-check/v1. Exit 0 always, unless --fail-on-fix
is given and at least one fix is available in the archive (then 3).

  python3 -I os/update/check-security.py --packages packages.txt --status status \
      --tracker tracker.json [--release trixie] [--out report.json] [--fail-on-fix]

Stdlib only, so it runs with `python3 -I` on any runner. Other scripts in os/update/ load this file
for vercmp() and the parsers.
"""
import argparse, datetime, json, re, sys

SCHEMA = "onemind.security-check/v1"


# ------------------------------------------------------------------ dpkg version comparison
def _order(c):
    """dpkg's lexical order: '~' sorts before everything, even the end; letters before non-letters."""
    if c == "~":
        return -1
    if c.isdigit():
        return 0
    if not c:
        return 0
    if c.isalpha():
        return ord(c)
    return ord(c) + 256


def _cmp_part(a, b):
    i = j = 0
    while i < len(a) or j < len(b):
        diff = 0
        while (i < len(a) and not a[i].isdigit()) or (j < len(b) and not b[j].isdigit()):
            ac = _order(a[i]) if i < len(a) else 0
            bc = _order(b[j]) if j < len(b) else 0
            if ac != bc:
                return ac - bc
            i += 1
            j += 1
        while i < len(a) and a[i] == "0":
            i += 1
        while j < len(b) and b[j] == "0":
            j += 1
        while i < len(a) and a[i].isdigit() and j < len(b) and b[j].isdigit():
            if not diff:
                diff = ord(a[i]) - ord(b[j])
            i += 1
            j += 1
        if i < len(a) and a[i].isdigit():
            return 1
        if j < len(b) and b[j].isdigit():
            return -1
        if diff:
            return diff
    return 0


def _split(v):
    v = v.strip()
    epoch, _, rest = v.rpartition(":") if ":" in v else ("0", "", v)
    upstream, _, rev = rest.rpartition("-") if "-" in rest else (rest, "", "0")
    return int(epoch or 0), upstream, rev


def vercmp(a, b):
    """Compare two Debian versions: <0, 0, >0 like dpkg --compare-versions (deb-version(7))."""
    ea, ua, ra = _split(a)
    eb, ub, rb = _split(b)
    if ea != eb:
        return ea - eb
    return _cmp_part(ua, ub) or _cmp_part(ra, rb)


def vmax(versions):
    best = None
    for v in versions:
        if v and (best is None or vercmp(v, best) > 0):
            best = v
    return best


# ------------------------------------------------------------------ inputs
def parse_packages_txt(text):
    """packages.txt -> {binary: (version, arch)}; arch-qualified duplicates keep the first."""
    out = {}
    for line in text.splitlines():
        f = line.split()
        if len(f) >= 2 and not line.startswith("#"):
            out.setdefault(f[0], (f[1], f[2] if len(f) > 2 else ""))
    return out


def parse_deb822(text):
    """Paragraphs of a dpkg status or Packages file -> list of {Field: value} (first line only)."""
    paras, cur = [], {}
    for line in text.splitlines():
        if not line.strip():
            if cur:
                paras.append(cur)
            cur = {}
        elif line[0] in " \t":
            continue
        elif ":" in line:
            k, _, v = line.partition(":")
            cur[k.strip()] = v.strip()
    if cur:
        paras.append(cur)
    return paras


SRC_RX = re.compile(r"^(\S+)(?:\s+\((\S+)\))?$")


def source_of(para):
    """(source, source_version) for a status/Packages paragraph (deb-control(5) Source field)."""
    pkg, ver = para.get("Package"), para.get("Version")
    m = SRC_RX.match(para.get("Source", "")) if para.get("Source") else None
    if m:
        return m.group(1), m.group(2) or ver
    return pkg, ver


def parse_status(text):
    """dpkg status -> {binary: {version, arch, source, source_version}} for installed packages."""
    out = {}
    for p in parse_deb822(text):
        if "Package" not in p or "Version" not in p:
            continue
        if p.get("Status", "install ok installed").split()[-1] != "installed":
            continue
        src, sver = source_of(p)
        out[p["Package"]] = {"version": p["Version"], "arch": p.get("Architecture", ""),
                             "source": src, "source_version": sver}
    return out


BINNMU = re.compile(r"\+b\d+$")


def installed_sources(packages, status=None):
    """-> {source: {"version": lowest installed source version, "binaries": {bin: binver}}}."""
    srcs = {}
    for binary, (ver, _arch) in sorted(packages.items()):
        if status and binary in status:
            src, sver = status[binary]["source"], status[binary]["source_version"]
        else:
            src, sver = binary, BINNMU.sub("", ver)
        e = srcs.setdefault(src, {"version": sver, "binaries": {}})
        if vercmp(sver, e["version"]) < 0:
            e["version"] = sver
        e["binaries"][binary] = ver
    return srcs


# ------------------------------------------------------------------ matching
def find_fixes(sources, tracker, release="trixie"):
    """Every installed source with at least one resolved CVE fixed in a newer version."""
    fixes = []
    for src in sorted(sources):
        inst = sources[src]["version"]
        cves, repos = [], {}
        for cve, data in sorted(tracker.get(src, {}).items()):
            rel = data.get("releases", {}).get(release)
            if not rel:
                continue
            repos.update(rel.get("repositories", {}))
            fixed = rel.get("fixed_version")
            if rel.get("status") != "resolved" or not fixed or fixed == "0":
                continue
            if vercmp(inst, fixed) < 0:
                cves.append({"id": cve, "fixed_version": fixed, "urgency": rel.get("urgency", ""),
                             "scope": data.get("scope", "")})
        if not cves:
            continue
        need = vmax(c["fixed_version"] for c in cves)
        avail = vmax(repos.values())
        fixes.append({
            "source": src, "installed": inst, "binaries": sorted(sources[src]["binaries"]),
            "fixed_version": need, "archive_version": avail, "repositories": dict(sorted(repos.items())),
            "available": bool(avail) and vercmp(avail, need) >= 0,
            "cves": cves,
        })
    return fixes


def report(packages, status, tracker, release="trixie", now=None):
    srcs = installed_sources(packages, status)
    fixes = find_fixes(srcs, tracker, release)
    now = now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema": SCHEMA, "release": release, "generated_at": now,
        "source_map": "dpkg-status" if status else "heuristic",
        "binaries_checked": len(packages), "sources_checked": len(srcs),
        "cves": sum(len(f["cves"]) for f in fixes),
        "needs_rebuild": any(f["available"] for f in fixes),
        "fixes": fixes,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--packages", required=True)
    ap.add_argument("--status")
    ap.add_argument("--tracker", required=True)
    ap.add_argument("--release", default="trixie")
    ap.add_argument("--out")
    ap.add_argument("--fail-on-fix", action="store_true")
    a = ap.parse_args(argv)
    pk = parse_packages_txt(open(a.packages, encoding="utf-8").read())
    st = parse_status(open(a.status, encoding="utf-8").read()) if a.status else None
    with open(a.tracker, encoding="utf-8") as f:
        tr = json.load(f)
    r = report(pk, st, tr, a.release)
    text = json.dumps(r, indent=2, sort_keys=False) + "\n"
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text)
    else:
        sys.stdout.write(text)
    n = sum(1 for f in r["fixes"] if f["available"])
    print(f"check-security: {len(r['fixes'])} source(s) behind a fix, {n} fixable from the archive, "
          f"{r['cves']} CVE(s); needs_rebuild={str(r['needs_rebuild']).lower()}", file=sys.stderr)
    return 3 if a.fail_on_fix and r["needs_rebuild"] else 0


if __name__ == "__main__":
    sys.exit(main())
