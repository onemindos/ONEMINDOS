#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Licence and pin check for an npm project (brief 30 §2 rule 2: pinned deps with a licence check).

Reads package-lock.json (lockfile v2/v3) only, so it needs no install and no network:
  * every package's "license" must be an SPDX id in --allow, or an SPDX expression that an
    allowed choice satisfies ("A OR B" needs one allowed, "A AND B" needs both);
  * every direct dependency in package.json must be an exact version (no ^, ~, ranges or tags).

  python3 -I scripts/npm-licence-check.py <dir with package.json + package-lock.json> --allow MIT Apache-2.0 ...
Exit 0 when clean, 1 with one line per problem, 2 on unreadable input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

EXACT = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def satisfied(expr: str, allow: set[str]) -> bool:
    """True if the SPDX expression can be met with allowed licences (no WITH exceptions supported)."""
    tokens = re.findall(r"\(|\)|[A-Za-z0-9.+-]+", expr)
    pos = 0

    def parse_or() -> bool:
        nonlocal pos
        ok = parse_and()
        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1
            ok = parse_and() or ok
        return ok

    def parse_and() -> bool:
        nonlocal pos
        ok = parse_atom()
        while pos < len(tokens) and tokens[pos].upper() == "AND":
            pos += 1
            ok = parse_atom() and ok
        return ok

    def parse_atom() -> bool:
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError(f"truncated licence expression {expr!r}")
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            ok = parse_or()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError(f"unbalanced licence expression {expr!r}")
            pos += 1
            return ok
        if tok.upper() in ("AND", "OR", "WITH", ")"):
            raise ValueError(f"bad licence expression {expr!r}")
        return tok in allow

    ok = parse_or()
    if pos != len(tokens):
        raise ValueError(f"bad licence expression {expr!r}")
    return ok


def check(project: Path, allow: set[str]) -> list[str]:
    pkg = json.loads((project / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((project / "package-lock.json").read_text(encoding="utf-8"))
    problems = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, spec in (pkg.get(section) or {}).items():
            if not EXACT.match(str(spec)):
                problems.append(f"package.json {section}.{name}: '{spec}' is not an exact version")
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("package-lock.json has no 'packages' map (lockfileVersion 2 or 3 needed)")
    for path, meta in sorted(packages.items()):
        if not path or meta.get("link"):
            continue  # the project itself, or a workspace link
        name = path.rsplit("node_modules/", 1)[-1]
        lic = meta.get("license")
        where = f"{name}@{meta.get('version', '?')}"
        if not isinstance(lic, str) or not lic.strip():
            problems.append(f"{where}: no licence in package-lock.json")
            continue
        try:
            if not satisfied(lic, allow):
                problems.append(f"{where}: licence '{lic}' is not allowed")
        except ValueError as exc:
            problems.append(f"{where}: {exc}")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", type=Path, help="directory with package.json and package-lock.json")
    ap.add_argument("--allow", nargs="+", required=True, help="allowed SPDX licence ids")
    a = ap.parse_args(argv)
    try:
        problems = check(a.project, set(a.allow))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for p in problems:
        print(f"FAIL {p}")
    count = len(json.loads((a.project / "package-lock.json").read_text(encoding="utf-8"))["packages"]) - 1
    print(f"{'FAILED' if problems else 'ok'}: {a.project}: {count} packages, allowed {' '.join(sorted(a.allow))}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
