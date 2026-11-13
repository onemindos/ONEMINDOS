#!/usr/bin/env -S python3 -I
# SPDX-License-Identifier: Apache-2.0
"""Summarise an apps-gate-all run (.github/workflows/apps-gate-all.yml) as one Markdown issue body.

Input: a directory with one folder per gate job, as actions/download-artifact writes them
(apps-gate-<app>-<arch>/), each holding status.json ({"app", "arch", "runner", "rc"}), the
app-gate --report JSON (report.json) and the gate's output (gate.log).
Every expected (app, arch) pair gets a cell: pass, FAIL (failing checks), ERROR (app-gate exit 2:
tool or network error; "setup" when the job stopped before app-gate finished) or NO RESULT (no
artifact: the job was cancelled, timed out or never ran).

  python3 -I sdk/tools/ci/gate_summary.py <dir> --apps a b --archs amd64 arm64 \\
      [--run-url URL] [--sha SHA] [--out body.md]
Prints "problems=<n>" (cells that are not pass) for $GITHUB_OUTPUT. Exit 2 on bad input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MARKER = "<!-- apps-gate-all -->"
MAX_BODY = 60_000          # GitHub caps an issue body at 65,536 characters
MAX_NOTE = 400
MAX_NOTES_PER_CHECK = 6
LOG_TAIL = 15
IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def clean(text: str, limit: int = MAX_NOTE) -> str:
    """Public issue text: no ANSI colours, no IP addresses (pod and node IPs of the throwaway
    cluster), no fence breaks, bounded length."""
    text = ANSI.sub("", text)
    text = IPV4.sub("<ip>", text)
    text = text.replace("```", "'''")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_cell(folder: Path) -> dict | None:
    try:
        status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cell = {"app": status.get("app"), "arch": status.get("arch"), "runner": status.get("runner", ""),
            "rc": status.get("rc")}
    try:
        reports = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        cell["report"] = reports[0] if isinstance(reports, list) and reports else None
    except (OSError, ValueError):
        cell["report"] = None
    try:
        lines = (folder / "gate.log").read_text(encoding="utf-8", errors="replace").splitlines()
        cell["log_tail"] = lines[-LOG_TAIL:]
    except OSError:
        cell["log_tail"] = []
    return cell


def classify(cell: dict | None) -> str:
    if cell is None:
        return "missing"
    rc, report = cell.get("rc"), cell.get("report")
    if rc == 0 and report and report.get("result") == "pass":
        return "pass"
    if rc in (0, 1) and report:
        return "fail"
    return "error"


def failing_checks(report: dict) -> list[tuple[str, list[str]]]:
    out = []
    for name, c in (report.get("checks") or {}).items():
        if not c.get("ok", True):
            notes = [n for n in c.get("notes", []) if n.startswith("FAIL") or name == "tier"] or c.get("notes", [])
            out.append((name, notes))
    return out


def render(cells: dict[tuple[str, str], dict | None], apps: list[str], archs: list[str],
           run_url: str = "", sha: str = "") -> tuple[str, int]:
    kinds = {k: classify(v) for k, v in cells.items()}
    problems = sum(1 for k in kinds.values() if k != "pass")
    head = [MARKER, f"## App gate on every app: {problems} of {len(kinds)} runs not passing", ""]
    meta = []
    if run_url:
        meta.append(f"Run: {run_url}")
    if sha:
        meta.append(f"commit `{sha[:12]}`")
    if meta:
        head += [" · ".join(meta), ""]
    head += ["`sdk/tools/app-gate <app> --smoke --tier check --no-write` on a throwaway k3d cluster, "
             "on `ubuntu-24.04` (amd64) and `ubuntu-24.04-arm` (arm64). Reports: the run's `apps-gate-*` artifacts. "
             "This issue is rewritten by every run of `.github/workflows/apps-gate-all.yml` and closed when all pass.", ""]

    table = ["| App | " + " | ".join(archs) + " |", "|---|" + "---|" * len(archs)]
    for app in apps:
        row = []
        for arch in archs:
            cell, kind = cells.get((app, arch)), kinds[(app, arch)]
            if kind == "pass":
                row.append(f"pass ({cell['report'].get('computed_tier', '?')})")
            elif kind == "fail":
                names = ", ".join(n for n, _ in failing_checks(cell["report"])) or "see report"
                row.append(f"**FAIL**: {names} (tier {cell['report'].get('computed_tier', '?')})")
            elif kind == "error":
                row.append("**ERROR** (setup)" if cell.get("rc") is None else f"**ERROR** (exit {cell.get('rc')})")
            else:
                row.append("**NO RESULT**")
        table.append(f"| `{app}` | " + " | ".join(row) + " |")

    details = []
    for app in apps:
        for arch in archs:
            cell, kind = cells.get((app, arch)), kinds[(app, arch)]
            if kind == "pass":
                continue
            details.append(f"### `{app}` on {arch}")
            if kind == "missing":
                details.append("No artifact: the job was cancelled, timed out or never started.")
            elif kind == "error" and cell.get("rc") is None:
                details.append("The job stopped before app-gate finished (tool install, ClamAV signatures or the "
                               "k3d cluster); see the job's log in the run.")
            elif kind == "error":
                details.append(f"app-gate exited {cell.get('rc')} (tool, network or input error), last lines of its output:")
                details += ["```", *[clean(x, 300) for x in cell.get("log_tail", [])], "```"]
            else:
                for name, notes in failing_checks(cell["report"]):
                    details.append(f"- **{name}**")
                    shown = notes[:MAX_NOTES_PER_CHECK]
                    details += ["  ```", *[f"  {clean(n)}" for n in shown], "  ```"]
                    if len(notes) > len(shown):
                        details.append(f"  ({len(notes) - len(shown)} more in the report)")
            details.append("")

    body = "\n".join(head + table + ([""] + ["## Details", ""] + details if details else []))
    if len(body) > MAX_BODY:
        body = body[: MAX_BODY - 200].rsplit("\n", 1)[0] + "\n\n(Truncated: the full findings are in the run's artifacts.)\n"
    return body + ("\n" if not body.endswith("\n") else ""), problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir", type=Path)
    ap.add_argument("--apps", nargs="+", required=True)
    ap.add_argument("--archs", nargs="+", default=["amd64", "arm64"])
    ap.add_argument("--run-url", default="")
    ap.add_argument("--sha", default="")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if not a.dir.is_dir():
        print(f"error: {a.dir} is not a directory", file=sys.stderr)
        return 2
    cells: dict[tuple[str, str], dict | None] = {(app, arch): None for app in a.apps for arch in a.archs}
    for folder in sorted(p for p in a.dir.iterdir() if p.is_dir()):
        cell = load_cell(folder)
        if cell and (cell["app"], cell["arch"]) in cells:
            cells[(cell["app"], cell["arch"])] = cell
    body, problems = render(cells, a.apps, a.archs, a.run_url, a.sha)
    if a.out:
        a.out.write_text(body, encoding="utf-8")
    else:
        sys.stdout.write(body)
    print(f"problems={problems}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
