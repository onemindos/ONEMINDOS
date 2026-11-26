#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when an onemind CLI binary in a release archive still holds a path from the machine that built it (#882).

  check-cli-paths.py [--forbid <dir>]... [--expect N] <archive.tar.gz>...

Why: `go build` without -trimpath writes the source folder, the module cache and GOROOT into the binary (file names
in panics and debug info). That leaks the builder's user name and folders and makes two builds of the same commit
differ. scripts/release/build-cli-packages.sh builds with -trimpath -buildvcs=false -ldflags "-s -w -buildid=";
this check proves it worked.

Two kinds of finding, read from the printable strings of each binary (like `strings`):
  1. any --forbid directory, as a literal (CI passes the checkout, $HOME, GOROOT, GOPATH, the module cache, the
     runner temp folder: the exact places a leak would point to);
  2. a string that STARTS an absolute path under /home/, /Users/, /runner/ or /work/. "Starts" means the slash is
     not glued to a letter, digit, '.', '_' or '-' before it, so a gateway route such as "/v1/work/tasks" (the
     `onemind work` commands) is not a build path, while a Go source path under a home folder is.
"""
import argparse, re, sys, tarfile

PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")
PATH_ROOT = re.compile(rb"(?<![A-Za-z0-9_.\-])/(?:home|Users|runner|work)/[A-Za-z0-9_.\-]")


def findings(data, forbid):
    out = []
    for m in PRINTABLE.finditer(data):
        s = m.group()
        for d in forbid:
            if d in s:
                out.append(f"build folder {d.decode()!r} in {s[:200].decode()!r}")
        p = PATH_ROOT.search(s)
        if p:
            out.append(f"absolute path in {s[max(0, p.start() - 40):p.start() + 120].decode()!r}")
    return out


def binaries(archive):
    with tarfile.open(archive) as t:
        found = [m for m in t.getmembers() if m.isfile() and m.name.endswith("/bin/onemind")]
        if len(found) != 1:
            raise SystemExit(f"{archive}: expected one */bin/onemind, found {len(found)}")
        data = t.extractfile(found[0]).read()
        if not data:
            raise SystemExit(f"{archive}: */bin/onemind is empty")
        return data


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--forbid", action="append", default=[], help="a build folder that must not appear (repeatable)")
    ap.add_argument("--expect", type=int, help="the exact number of archives to check")
    ap.add_argument("archives", nargs="+")
    a = ap.parse_args(argv)
    forbid = sorted({d.rstrip("/").encode() for d in a.forbid if d.strip("/")})
    if a.expect is not None and len(a.archives) != a.expect:
        raise SystemExit(f"expected {a.expect} archives, got {len(a.archives)}")
    bad = 0
    for f in a.archives:
        hits = findings(binaries(f), forbid)
        for h in hits:
            print(f"{f}: {h}")
        bad += bool(hits)
        if not hits:
            print(f"{f}: no build machine paths")
    if bad:
        print(f"path leaked in {bad} of {len(a.archives)} archives", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
