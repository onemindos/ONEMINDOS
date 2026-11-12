#!/usr/bin/env python3
"""LAB-minimal-image-dc20: split grype results into kernel vs userspace, unique CVE IDs by
severity and fix state; count SBOM components by kind. Usage: python3 -I split.py <measure-dir>..."""
import json, sys, pathlib, collections
KERNEL = {"linux-kernel", "linux", "linux-headers"}
SEV = ["Critical", "High", "Medium", "Low", "Negligible", "Unknown"]
ORDER = {s: i for i, s in enumerate(SEV)}
RES = set()
def uniq(ms):
    ids = {}
    for m in ms:
        v = m["vulnerability"]; s = v.get("severity", "Unknown")
        if v["id"] not in ids or ORDER.get(s, 9) < ORDER.get(ids[v["id"]], 9): ids[v["id"]] = s
    c = collections.Counter(ids.values())
    return len(ids), c.get("Critical", 0) + c.get("High", 0), {s: c.get(s, 0) for s in SEV}
def row(name, ms):
    k = [m for m in ms if m["artifact"]["name"] in KERNEL or m["artifact"]["type"] == "linux-kernel"]
    u = [m for m in ms if m not in k]
    fs = collections.Counter(); seen = set()
    for m in u:
        if m["vulnerability"]["id"] not in seen:
            seen.add(m["vulnerability"]["id"]); fs[m["vulnerability"].get("fix", {}).get("state", "?")] += 1
    a, ah, _ = uniq(ms); kk, kh, _ = uniq(k); uu, uh, us = uniq(u)
    print(f"| {name} | {a} | {ah} | {kk} | {kh} | {uu} | {uh} | {dict(fs)} |")
print("| scan | all unique IDs | all C+H | kernel IDs | kernel C+H | userspace IDs | userspace C+H | userspace fix states |")
print("|---|---|---|---|---|---|---|---|")
for d in map(pathlib.Path, sys.argv[1:]):
    cdx = d / "buildroot.cdx.json"
    if cdx.exists():
        RES.clear()
        for v in json.load(open(cdx)).get("vulnerabilities", []):
            for a in v.get("affects", []): RES.add((v["id"], a["ref"]))
    for f in sorted(d.glob("grype-*.json")):
        ms = json.load(open(f))["matches"]
        row(f"{d.name}/{f.stem}", ms)
        if "buildroot" in f.stem:
            row(f"{d.name}/{f.stem} minus BR-resolved", [m for m in ms if (m["vulnerability"]["id"], m["artifact"]["name"]) not in RES])
for d in map(pathlib.Path, sys.argv[1:]):
    s = d / "syft-rootfs-nok3s.json"
    if s.exists():
        arts = json.load(open(s))["artifacts"]
        debs = [a for a in arts if a["type"] == "deb"]
        src = {(a.get("metadata", {}).get("source") or a["name"]) for a in debs}
        print(f"{d.name}: deb binary packages {len(debs)}, deb source packages {len(src)}")
    t = d / "buildroot-target.cdx.json"
    if t.exists():
        comps = json.load(open(t))["components"]
        print(f"{d.name}: Buildroot target components {len(comps)}: {sorted(c['name'] for c in comps)}")
