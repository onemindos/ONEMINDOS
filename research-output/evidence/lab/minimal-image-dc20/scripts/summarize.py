#!/usr/bin/env python3
"""LAB-minimal-image-dc20: summarise syft/grype JSON into counts. Usage:
python3 -I summarize.py <measure-dir> [...]   -> prints a markdown table per dir."""
import json, sys, collections, pathlib
SEV = ["Critical", "High", "Medium", "Low", "Negligible", "Unknown"]
def syft_counts(p):
    d = json.load(open(p)); arts = d.get("artifacts", [])
    return len(arts), collections.Counter(a.get("type", "?") for a in arts)
def cdx_counts(p):
    d = json.load(open(p)); comps = d.get("components", [])
    return len(comps), sum(1 for c in comps if c.get("cpe"))
RESOLVED = set()  # (CVE, bom-ref) pairs Buildroot's SBOM marks resolved (patched/ignored)
def load_resolved(cdx):
    for v in json.load(open(cdx)).get("vulnerabilities", []):
        for a in v.get("affects", []): RESOLVED.add((v["id"], a["ref"]))
def grype_counts(p, drop_resolved=False):
    d = json.load(open(p)); ms = d.get("matches", [])
    if drop_resolved:
        ms = [m for m in ms if (m["vulnerability"]["id"], m["artifact"]["name"]) not in RESOLVED
              and not any((r.get("id"), m["artifact"]["name"]) in RESOLVED for r in m.get("relatedVulnerabilities", []))]
    pairs = {(m["vulnerability"]["id"], m["artifact"]["name"], m["artifact"]["version"]) for m in ms}
    ids = {}
    order = {s: i for i, s in enumerate(SEV)}
    for m in ms:
        v = m["vulnerability"]; s = v.get("severity", "Unknown")
        if v["id"] not in ids or order.get(s, 9) < order.get(ids[v["id"]], 9): ids[v["id"]] = s
    sev = collections.Counter(ids.values())
    bypkg = collections.Counter(m["artifact"]["name"] for m in ms)
    cve_ids = {i for i in ids if i.startswith("CVE-")}
    db = d.get("descriptor", {}).get("db", {})
    return dict(matches=len(ms), pairs=len(pairs), ids=len(ids), cve_ids=len(cve_ids),
                sev={s: sev.get(s, 0) for s in SEV}, top=bypkg.most_common(8),
                db=db.get("status", db).get("built", db.get("built")) if isinstance(db, dict) else db)
for d in map(pathlib.Path, sys.argv[1:]):
    print(f"## {d.name}")
    for n in ["syft-rootfs", "syft-rootfs-nok3s"]:
        f = d / f"{n}.json"
        if f.exists():
            t, by = syft_counts(f); print(f"- {n}: {t} artifacts; by type {dict(by.most_common())}")
    f = d / "buildroot.cdx.json"
    if f.exists():
        t, c = cdx_counts(f); print(f"- buildroot.cdx.json: {t} components, {c} with a CPE")
    if (d / "buildroot.cdx.json").exists(): load_resolved(d / "buildroot.cdx.json")
    runs = [(f, False) for f in sorted(d.glob("grype-*.json"))]
    runs += [(f, True) for f in sorted(d.glob("grype-buildroot*.json"))]
    for f, dr in runs:
        g = grype_counts(f, dr)
        if dr: f = f.with_name(f.stem + "-minus-BR-resolved.json")
        print(f"- {f.stem}: matches {g['matches']}, unique (id,pkg,ver) {g['pairs']}, unique vuln IDs {g['ids']} (CVE {g['cve_ids']}); by severity {g['sev']}; db built {g['db']}")
        print(f"  top packages: {g['top']}")
    print()
