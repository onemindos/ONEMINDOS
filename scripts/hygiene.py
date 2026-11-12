#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Public-repo hygiene greps (brief 30 §2 rule 9; research-output/evidence/hygiene-log.md §1/§6).

Scans every tracked or new (not ignored) file for host home paths, private IPv4 (RFC1918 and
100.64/10), tailnet names, e-mail-shaped strings and irreversible-fusing commands (SB-8).
research-output/ was reviewed by the research run (hygiene-log.md); only files changed there
since the base ref are scanned. Every allowed hit is a reviewed false positive in
scripts/hygiene-allow.tsv, documented in handbook/hygiene.md. Exit 1 on any other hit.

  python3 -I scripts/hygiene.py [--base origin/main] [--root DIR]
"""
import argparse, fnmatch, os, re, subprocess, sys

PATTERNS = {
    "home-path": r"/Users/[a-z][A-Za-z0-9._-]*|/home/[a-z][A-Za-z0-9._-]*",
    "private-ipv4": r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\.\d{1,3}\.\d{1,3}\b",
    "tailnet": r"[A-Za-z0-9.-]+\.ts\.net\b",
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}",
    "irreversible-fuse": r"rpi-otp-private-key|odmfuse|\bvcgencmd\s+otp_dump\b.*program",
}


def files(root, base):
    git = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True).stdout
    allf = [f for f in git("ls-files", "-co", "--exclude-standard").splitlines() if f]
    changed = set(git("diff", "--name-only", f"{base}...HEAD").splitlines()) | set(
        git("ls-files", "-mo", "--exclude-standard").splitlines())
    return [f for f in allf if not f.startswith("research-output/") or f in changed]


def load_allow(root):
    allow = []
    p = os.path.join(root, "scripts", "hygiene-allow.tsv")
    for line in open(p):
        if line.strip() and not line.startswith("#"):
            glob, rx, fp = line.rstrip("\n").split("\t")
            allow.append((glob, re.compile(rx), fp))
    return allow


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    allow, hits = load_allow(a.root), []
    for f in files(a.root, a.base):
        path = os.path.join(a.root, f)
        if not os.path.isfile(path) or os.path.getsize(path) > 5 << 20:
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for kind, rx in PATTERNS.items():
                if kind == "irreversible-fuse" and f.endswith(".md"):
                    continue    # docs may name the forbidden commands; scripts may not (SB-8)
                for m in re.finditer(rx, line):
                    if not any(fnmatch.fnmatch(f, g) and r.fullmatch(m.group(0)) for g, r, _ in allow):
                        hits.append(f"{f}:{n}: [{kind}] {m.group(0)}")
    for h in hits:
        print(h)
    print(f"hygiene greps: {len(hits)} unreviewed hit(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
