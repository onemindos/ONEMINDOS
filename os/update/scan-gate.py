#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pass/fail gate over one rootfs's scans (poc-v0 §10.1; brief 30 D-B1.5).

Fails (exit 1) when:
  - ClamAV found anything ("Infected files: N" with N > 0, or a FOUND line), or its log is
    missing or has no scan summary (a scan that did not run is not a pass);
  - Trivy reports a CRITICAL vulnerability whose status is "fixed", i.e. Debian has a fixed
    version the image does not carry: the rebuild did not pick the fix up.
Reports, without failing: files ClamAV could not open, other fixable findings, and the
post-rebuild check-security.py report (sources still behind an archive fix, e.g. base-image
packages the build does not upgrade).

  python3 -I os/update/scan-gate.py --trivy trivy.json --clamav clamav.log \
      [--check check-after.json] [--board x86_64-efi] --out gate.json
"""
import argparse, json, re, sys


def clamav_verdict(log_text):
    m = re.search(r"(?m)^Infected files:\s*(\d+)\s*$", log_text or "")
    found = re.findall(r"(?m)^(.+?):\s+(\S+)\s+FOUND$", log_text or "")
    unread = re.findall(r"(?m)^WARNING: Can't open file (.+?): ", log_text or "")
    e = re.search(r"(?m)^Total errors:\s*(\d+)\s*$", log_text or "")
    if not m:
        return {"ran": False, "infected": None, "hits": [], "errors": None, "unscanned": unread, "pass": False}
    n = int(m.group(1))
    # Errors (e.g. files the scanner could not open) are reported, not failed: under rootless Docker
    # root-only files such as /etc/shadow are unreadable; CI runs rootful Docker, where it should be empty.
    return {"ran": True, "infected": n, "hits": [{"file": f, "signature": s} for f, s in found],
            "errors": int(e.group(1)) if e else 0, "unscanned": unread, "pass": n == 0 and not found}


def trivy_findings(trivy):
    out = []
    for res in trivy.get("Results") or []:
        for v in res.get("Vulnerabilities") or []:
            out.append({"id": v.get("VulnerabilityID"), "pkg": v.get("PkgName"),
                        "installed": v.get("InstalledVersion"), "fixed": v.get("FixedVersion") or "",
                        "severity": v.get("Severity"), "status": v.get("Status", "")})
    return out


def gate(trivy, clamav_log, check=None, board=""):
    fnd = trivy_findings(trivy)
    fixable = [f for f in fnd if f["status"] == "fixed" and f["fixed"]]
    blocking = [f for f in fixable if f["severity"] == "CRITICAL"]
    sev = {}
    for f in fnd:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1
    clam = clamav_verdict(clamav_log)
    behind = [{"source": f["source"], "installed": f["installed"], "fixed_version": f["fixed_version"],
               "cves": [c["id"] for c in f["cves"]]}
              for f in (check or {}).get("fixes", []) if f.get("available")]
    reasons = []
    if not clam["pass"]:
        reasons.append("clamav: " + ("did not run" if not clam["ran"] else f"{clam['infected']} infected file(s)"))
    if blocking:
        reasons.append(f"trivy: {len(blocking)} CRITICAL finding(s) with a Debian fix the image lacks")
    return {"schema": "onemind.scan-gate/v1", "board": board, "pass": not reasons, "reasons": reasons,
            "clamav": clam, "trivy": {"total": len(fnd), "by_severity": dict(sorted(sev.items())),
                                      "fixable": len(fixable), "blocking": blocking},
            "sources_behind_archive_fix": behind}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trivy", required=True)
    ap.add_argument("--clamav", required=True)
    ap.add_argument("--check")
    ap.add_argument("--board", default="")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    trivy = json.load(open(a.trivy, encoding="utf-8"))
    try:
        clam = open(a.clamav, encoding="utf-8", errors="replace").read()
    except OSError:
        clam = ""
    check = json.load(open(a.check, encoding="utf-8")) if a.check else None
    g = gate(trivy, clam, check, a.board)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(g, f, indent=2)
        f.write("\n")
    print(f"scan-gate {a.board}: {'PASS' if g['pass'] else 'FAIL'} {g['reasons']}; trivy {g['trivy']['by_severity']}, "
          f"fixable {g['trivy']['fixable']}; sources behind an archive fix: "
          f"{[b['source'] for b in g['sources_behind_archive_fix']]}", file=sys.stderr)
    return 0 if g["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
