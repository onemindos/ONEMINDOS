#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OpenVEX (v0.2.0) from the Debian security tracker, for the packages in one OneMind rootfs.

Brief 30 D-B1.5 / REC-DEC-41: the CVE scan uses the distribution's own tracker states as VEX
("Vulnerability Exploitability eXchange": a signed-off statement of whether a product is affected).
A generic scanner only knows "this version is below upstream's fix"; Debian's security team knows
more (a CVE never applied to Debian's build, or was triaged as minor). Mapping, per installed
source package and CVE, for the release (default trixie):

  tracker state                                   OpenVEX status   effect in Trivy
  resolved, fixed_version "0" (never affected)    not_affected     suppressed (justification:
                                                                   vulnerable_code_not_present)
  resolved, installed >= fixed_version            fixed            suppressed
  no-dsa / ignored / postponed (nodsa set)        affected         reported; action_statement carries
                                                                   Debian's reason (informational)
  anything else                                   no statement     Trivy decides alone

Products are package URLs per installed binary, e.g. pkg:deb/debian/zlib1g@1:1.3...?arch=arm64
(purl-spec deb type; Trivy matches VEX products on the purl name and version).

  python3 -I os/update/debian-vex.py --tracker tracker.json --status rootfs/var/lib/dpkg/status \
      [--release trixie] [--timestamp 2026-11-12T00:00:00Z] [--id-suffix x86_64-efi] --out vex.json
"""
import argparse, datetime, hashlib, importlib.util, json, os, sys
from urllib.parse import quote

_spec = importlib.util.spec_from_file_location(
    "check_security", os.path.join(os.path.dirname(os.path.abspath(__file__)), "check-security.py"))
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

CONTEXT = "https://openvex.dev/ns/v0.2.0"
AUTHOR = "OneMind OS security pipeline (from the Debian security tracker)"


def purl(binary, version, arch):
    """purl-spec "deb" type: the epoch goes in an epoch= qualifier, not in the version."""
    epoch, _, ver = version.partition(":") if ":" in version else ("", "", version)
    q = [f"arch={quote(arch, safe='')}"] if arch else []
    if epoch and epoch != "0":
        q.append(f"epoch={epoch}")
    return f"pkg:deb/debian/{binary}@{quote(ver, safe='~')}" + ("?" + "&".join(q) if q else "")


def statements(status, tracker, release="trixie"):
    """Status from parse_status() -> sorted list of OpenVEX statements."""
    by_src = {}
    for b, s in status.items():
        by_src.setdefault(s["source"], []).append((b, s))
    out = []
    for src in sorted(by_src):
        bins = sorted(by_src[src])
        inst = cs.vmax(s["source_version"] for _, s in bins)
        products = [{"@id": purl(b, s["version"], s["arch"])} for b, s in bins]
        for cve, data in sorted(tracker.get(src, {}).items()):
            if not cve.startswith("CVE-"):
                continue       # TEMP-* ids are tracker-internal; scanners never report them
            rel = data.get("releases", {}).get(release)
            if not rel:
                continue
            st = {"vulnerability": {"name": cve}, "products": products}
            fixed = rel.get("fixed_version")
            if rel.get("status") == "resolved" and fixed == "0":
                st.update(status="not_affected", justification="vulnerable_code_not_present",
                          impact_statement=f"Debian security tracker: {release} never shipped the vulnerable code "
                                           f"(source {src}, fixed_version 0)")
            elif rel.get("status") == "resolved" and fixed and cs.vercmp(inst, fixed) >= 0:
                st.update(status="fixed",
                          status_notes=f"Debian security tracker: fixed in {src} {fixed}; installed {inst}")
            elif rel.get("nodsa") is not None:
                reason = rel.get("nodsa_reason") or "no-dsa"
                st.update(status="affected",
                          action_statement=f"Debian security team: {reason} for {release} "
                                           f"({rel.get('nodsa') or 'minor issue'}); no DSA planned, "
                                           f"a fix may come through a point release")
            else:
                continue
            out.append(st)
    return out


def document(stmts, timestamp, id_suffix=""):
    body = json.dumps(stmts, sort_keys=True).encode()
    doc_id = "https://onemind.io/vex/debian-tracker/" + hashlib.sha256(body).hexdigest()[:16]
    if id_suffix:
        doc_id += "-" + id_suffix
    return {"@context": CONTEXT, "@id": doc_id, "author": AUTHOR, "role": "Document Creator",
            "timestamp": timestamp, "version": 1, "tooling": "os/update/debian-vex.py",
            "statements": [dict(s, timestamp=timestamp) for s in stmts]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tracker", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--release", default="trixie")
    ap.add_argument("--timestamp")
    ap.add_argument("--id-suffix", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ts = a.timestamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(a.tracker, encoding="utf-8") as f:
        tracker = json.load(f)
    status = cs.parse_status(open(a.status, encoding="utf-8").read())
    stmts = statements(status, tracker, a.release)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(document(stmts, ts, a.id_suffix), f, indent=1)
        f.write("\n")
    counts = {}
    for s in stmts:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    print(f"debian-vex: {len(stmts)} statement(s) {counts} for {len(status)} installed binaries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
