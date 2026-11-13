# SPDX-License-Identifier: Apache-2.0
"""Licence gate (contract §9.4 check 2): map an SPDX expression to a Market licence class.

Classes come from research-output/13-apps-market-plugins.md §4: L1 permissive, L2 copyleft.
L3 (source-available, fair-code) and L4 (proprietary, no licence) are both `blocked` for the
Market, as are unknown and non-commercial licences (contract §9.4).
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

L1 = {
    "0BSD", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "BSD-3-Clause-Clear", "BSL-1.0",
    "CC0-1.0", "EPL-1.0", "EPL-2.0", "ISC", "MIT", "MIT-0", "MPL-2.0", "PostgreSQL",
    "Python-2.0", "Unlicense", "X11", "Zlib", "blessing",
}
L2 = {
    "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later", "CDDL-1.0", "EUPL-1.2",
    "GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later",
    "LGPL-2.1", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0", "LGPL-3.0-only",
    "LGPL-3.0-or-later",
}
# Explicitly denied (documented so a reviewer sees why); anything not in L1/L2 is blocked anyway.
DENIED_PREFIXES = ("BUSL-", "SSPL-", "Elastic-", "PolyForm-", "FSL-", "CC-BY-NC", "Commons-Clause",
                   "LicenseRef-", "NOASSERTION", "NONE", "UNVERIFIED")
# License exceptions that keep the base licence's class.
KNOWN_EXCEPTIONS = {"Linux-syscall-note", "Classpath-exception-2.0", "LLVM-exception",
                    "GCC-exception-3.1", "OpenSSL-exception"}

RANK = {"L1": 0, "L2": 1, "blocked": 2}
TOKEN_RE = re.compile(r"\(|\)|[A-Za-z0-9][A-Za-z0-9.+:-]*")


def class_of_id(spdx_id: str) -> str:
    if spdx_id in L1:
        return "L1"
    if spdx_id in L2:
        return "L2"
    return "blocked"


def classify(expr: str) -> str:
    """Return L1, L2 or blocked for an SPDX expression (OR takes the best, AND the worst)."""
    tokens = TOKEN_RE.findall(expr or "")
    if not tokens:
        return "blocked"
    pos = 0

    def parse_or() -> str:
        nonlocal pos
        best = parse_and()
        while pos < len(tokens) and tokens[pos].upper() == "OR":
            pos += 1
            other = parse_and()
            best = min(best, other, key=RANK.get)
        return best

    def parse_and() -> str:
        nonlocal pos
        worst = parse_with()
        while pos < len(tokens) and tokens[pos].upper() == "AND":
            pos += 1
            worst = max(worst, parse_with(), key=RANK.get)
        return worst

    def parse_with() -> str:
        nonlocal pos
        cls = parse_atom()
        if pos < len(tokens) and tokens[pos].upper() == "WITH":
            pos += 1
            exc = tokens[pos] if pos < len(tokens) else ""
            pos += 1
            if exc not in KNOWN_EXCEPTIONS:
                return "blocked"
        return cls

    def parse_atom() -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise ValueError("unexpected end")
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            cls = parse_or()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError("missing )")
            pos += 1
            return cls
        if tok == ")" or tok.upper() in ("AND", "OR", "WITH"):
            raise ValueError(f"unexpected {tok}")
        return class_of_id(tok)

    try:
        result = parse_or()
    except (ValueError, IndexError):
        return "blocked"
    return result if pos == len(tokens) else "blocked"


def ids_in(expr: str) -> set[str]:
    return {t for t in TOKEN_RE.findall(expr or "")
            if t not in ("(", ")") and t.upper() not in ("AND", "OR", "WITH")}


def normalise(expr: str) -> str:
    """Drop parenthetical notes the research matrix adds, e.g. 'MIT (test data)'."""
    expr = re.sub(r"\s*\((?![A-Za-z0-9.+-]+ (?:AND|OR|WITH) )[^()]*\)", "", expr or "")
    # The Eclipse Distribution License 1.0 is the BSD-3-Clause text; SPDX has no separate id for it
    # (https://www.eclipse.org/org/documents/edl-v10.php), so research rows written "EDL-1.0" match it.
    expr = re.sub(r"\bEDL-1\.0\b", "BSD-3-Clause", expr)
    return " ".join(expr.split())


def matrix_rows(matrix_csv: Path, owner_repo: str) -> list[dict]:
    """Rows of research-output/evidence/license-matrix.csv that cite github.com/<owner>/<repo>."""
    return matrix_rows_from_text(matrix_csv.read_text(encoding="utf-8"), owner_repo)


def matrix_rows_from_text(text: str, owner_repo: str) -> list[dict]:
    """Same as matrix_rows, from CSV text (used to compare two revisions of the matrix)."""
    needle = f"github.com/{owner_repo}".lower()
    rows = []
    for row in csv.DictReader(io.StringIO(text, newline="")):
        cited = (row.get("license_file_permalink", "") + " " + row.get("source", "")).lower()
        if re.search(re.escape(needle) + r"(?:[/@ ]|$)", cited):
            rows.append(row)
    return rows


def gate(manifest_licence: str, github_spdx: str | None, rows: list[dict]) -> tuple[str, list[str]]:
    """Return (class, notes). The manifest licence counts only if a primary source confirms it:
    GitHub's detected SPDX id is one of its terms, or a research-matrix row has the same expression."""
    notes: list[str] = []
    cls = classify(manifest_licence)
    by_matrix = False
    for row in rows:
        if normalise(row["SPDX"]) == normalise(manifest_licence):
            by_matrix = True
            notes.append(f"research licence matrix row '{row['component']}' ({row['version']}) matches")
            break
    by_github = False
    if github_spdx and github_spdx not in ("NOASSERTION", "NONE"):
        if github_spdx in ids_in(manifest_licence):
            by_github = True
            notes.append(f"GitHub licence {github_spdx} matches the manifest")
        else:
            notes.append(f"GitHub licence {github_spdx} is not a term of the manifest's {manifest_licence}")
    if not rows:
        notes.append("no research licence-matrix row: not preinstallable on sold boxes until one is added (brief 30 B10)")
    if not (by_matrix or by_github):
        notes.append("licence not confirmed by GitHub or the research matrix")
        return "blocked", notes
    if not by_matrix:
        # GitHub confirms only its one detected term. Without a matrix row for the whole expression,
        # the class is never better than that term's, so "MIT OR <github's licence>" in the manifest
        # cannot lift a source-available or unknown licence to L1.
        gh_cls = classify(github_spdx)
        if RANK[gh_cls] > RANK[cls]:
            notes.append(f"class limited to {gh_cls} (GitHub's {github_spdx}): only the research matrix "
                         f"can confirm the other terms of {manifest_licence}")
            cls = gh_cls
    return cls, notes
