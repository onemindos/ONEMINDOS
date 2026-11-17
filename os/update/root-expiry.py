#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Warn before a committed TUF root expires (REL-03, #302). Standard library only.

A box refuses an expired root, so no box could install an update, security fixes included. The root
is renewed offline by the key holders (scripts/tuf-bootstrap-root.sh renew; os/update/CEREMONY.md
"Renewing the root"), which takes days to arrange, so the nightly fails 60 days ahead.

  root-expiry.py [--warn-days 60] [ROOT.json ...]
      With no files: every os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/root.json in the repo.
      Exit 1 when a root expires within --warn-days (or has expired); exit 0 otherwise, also when no
      root is committed yet (the channel cannot publish without one).
Test clock: ONEMIND_TUF_NOW (ISO time), like tuf-repo.py.
"""
import argparse, datetime, glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTS = os.path.join(HERE, "..", "rootfs", "layers", "base", "usr", "lib", "onemind", "tuf", "*", "root.json")


def now():
    fixed = os.environ.get("ONEMIND_TUF_NOW")
    t = datetime.datetime.fromisoformat(fixed) if fixed else datetime.datetime.now(datetime.timezone.utc)
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def days_left(path):
    signed = json.load(open(path))["signed"]
    exp = datetime.datetime.strptime(signed["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    return signed["version"], (exp - now()).days, signed["expires"]


def check(paths, warn_days):
    """Returns (report lines, problems)."""
    lines, problems = [], []
    for p in paths:
        version, left, exp = days_left(p)
        name = os.path.relpath(p, os.path.join(HERE, "..", ".."))
        lines.append(f"{name}: version {version} expires {exp} ({left} days left)")
        if left < 0:
            problems.append(f"{name} EXPIRED {-left} days ago: every box refuses updates until a renewed root is published")
        elif left <= warn_days:
            problems.append(f"{name} expires in {left} days (warning at {warn_days}): renew it now "
                            f"(scripts/tuf-bootstrap-root.sh renew; os/update/CEREMONY.md, Renewing the root)")
    return lines, problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--warn-days", type=int, default=60)
    ap.add_argument("roots", nargs="*")
    a = ap.parse_args(argv)
    paths = a.roots or sorted(glob.glob(ROOTS))
    if not paths:
        print("no root.json committed yet: nothing to check (the channel cannot publish without one)")
        return 0
    lines, problems = check(paths, a.warn_days)
    print("\n".join(lines))
    for p in problems:
        print(f"::error::{p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
