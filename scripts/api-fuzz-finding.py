#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write the "api-fuzz nightly finding" issue body after a fuzz run (.github/workflows/api-fuzz.yml).

The nightly and manual api-fuzz runs explore with a fresh random seed. When one finds something,
the workflow's `report` job opens (or comments on) ONE issue titled TITLE with what this script
writes: the seed, every failing endpoint with its check, which role was fuzzing, and the commands
that replay exactly that run.

  python3 -I scripts/api-fuzz-finding.py --fuzz-dir fuzz-run --seed N --examples N \
      --sha SHA --ref REF --run-url URL --outcomes "fuzz-agent=failure,check-agent=skipped,..." > finding.md

Inputs are the JUnit reports Schemathesis writes (fuzz-run/report-<role>/*.xml) and the logs the
audit checks leave (fuzz-run/check-<phase>.log). Stdlib only: it runs on a bare runner.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
import xml.etree.ElementTree as ET  # noqa: S405 (our own run's report, never third-party input)
from pathlib import Path

TITLE = "api-fuzz nightly finding"
# Report directory suffix -> who was fuzzing and how (mirrors the fuzz steps in api-fuzz.yml).
ROLES = {
    "agent": ("agent", "AGENT_TOKEN", ["--checks", "all", "--exclude-path", "/mcp"]),
    "owner": ("owner", "OWNER_TOKEN", ["--checks", "all", "--exclude-path", "/mcp"]),
    "mcp-agent": ("agent", "AGENT_TOKEN", ["--include-path", "/mcp", "--checks", "not_a_server_error"]),
    "mcp-owner": ("owner", "OWNER_TOKEN", ["--include-path", "/mcp", "--checks", "not_a_server_error"]),
}
CHECK_LINE = re.compile(r"^\s*- (ST\d+ .+)$")
CASE_ID = re.compile(r"Test Case ID: (\S+)")
MAX_FINDINGS = 40
ZWSP = "\u200b"
# "@name" would ping someone and "#123" would cross-link an issue or PR; generated data and log
# lines can contain either, so a zero-width space breaks the pattern without changing what it reads.
QUIET = re.compile(r"([@#])(?=[\w-])")
MAX_BODY = 60000  # GitHub caps an issue body or comment at 65536 characters


def quiet(text: str) -> str:
    """Generated data and log lines, safe to paste into an issue: no mentions, no cross-links."""
    return QUIET.sub(lambda m: m.group(1) + ZWSP, text)


def findings(fuzz_dir: Path) -> list[dict]:
    """Every failing test case in the JUnit reports, one entry per (report, endpoint)."""
    out = []
    for report in sorted(fuzz_dir.glob("report-*/*.xml")):
        kind = report.parent.name.removeprefix("report-")
        for case in ET.parse(report).getroot().iter("testcase"):  # noqa: S314 (see the import)
            for failure in [*case.iter("failure"), *case.iter("error")]:
                text = "\n".join(filter(None, (failure.get("message"), failure.text)))
                checks = list(dict.fromkeys(m.group(1).strip() for m in map(CHECK_LINE.match, text.splitlines()) if m))
                if not checks:  # not a Schemathesis check failure (an error while testing): its first line
                    first = text.strip().splitlines()[0][:200] if text.strip() else ""
                    checks = [f"{failure.get('type') or failure.tag}: {first}".rstrip(": ")]
                out.append({
                    "kind": kind,
                    "endpoint": case.get("name", "?"),
                    "checks": [quiet(c) for c in checks],
                    "case_ids": CASE_ID.findall(text),
                })
    return out


def reproduce(f: dict, seed: str, examples: str) -> str:
    """The local command that replays one finding: same seed and budget, only this operation."""
    _, token, scope = ROLES.get(f["kind"], ROLES["agent"])
    method, _, path = f["endpoint"].partition(" ")
    cmd = [".venv/bin/schemathesis", "--config-file", "$FUZZ/schemathesis.toml", "run",
           "http://127.0.0.1:8080/openapi.json", "-H", f"Authorization: Bearer ${token}", *scope]
    if path and path != "/mcp":
        cmd += ["--include-path", path, "--include-method", method]
    cmd += ["--max-examples", examples, "--seed", seed, "--workers", "1", "--generation-database", "none"]
    # Only the two words this script writes with $FUZZ or $*_TOKEN stay expandable (in double quotes);
    # every other word, the endpoint path included, is quoted literally.
    expandable = {"$FUZZ/schemathesis.toml", f"Authorization: Bearer ${token}"}
    return " ".join(f'"{c}"' if c in expandable else shlex.quote(c) for c in cmd)


def failed_checks(fuzz_dir: Path) -> list[str]:
    """The FAIL lines the audit checks (core/tests/api_fuzz_check.py) printed."""
    lines = []
    for log in sorted(fuzz_dir.glob("check-*.log")):
        phase = log.stem.removeprefix("check-")
        lines += [f"{phase}: {quiet(ln.strip())}" for ln in log.read_text(errors="replace").splitlines() if ln.startswith("FAIL")]
    return lines


def body(fuzz_dir: Path, seed: str, examples: str, sha: str, ref: str, run_url: str, outcomes: str) -> str:
    found = findings(fuzz_dir)
    checks = failed_checks(fuzz_dir)
    failed_steps = [s for s, _, o in (x.partition("=") for x in outcomes.split(",") if x) if o == "failure"]
    out = [
        f"The api-fuzz nightly (random seed) found something on `{sha[:12]}`.",
        "",
        f"- **Seed:** `{seed}`",
        f"- **Examples per operation:** {examples}",
        f"- **Run:** {run_url}",
        f"- **Failed steps:** {', '.join(failed_steps) or 'none recorded (see the run)'}",
        "",
        "**Replay the whole run in CI** (same seed and budget; it comments here again if it still fails):",
        "",
        "```sh",
        f"gh workflow run api-fuzz.yml --ref {shlex.quote(ref)} -f seed={seed}",
        "```",
        "",
    ]
    if found:
        out += [f"### Findings ({len(found)})", ""]
        for f in found[:MAX_FINDINGS]:
            role = ROLES.get(f["kind"], (f["kind"],))[0]
            out += [f"- **`{f['endpoint']}`** as the {role}" + (" (/mcp run)" if f["kind"].startswith("mcp") else "")]
            out += [f"  - check: {c}" for c in f["checks"]]
            if f["case_ids"]:
                out += [f"  - test case: {', '.join(f['case_ids'])}"]
        if len(found) > MAX_FINDINGS:
            out += [f"- ... and {len(found) - MAX_FINDINGS} more in the JUnit reports of the run's artifact"]
        out += ["", "**Reproduce one finding locally** (gateway started as in api-fuzz.yml, see "
                "docs/testing/PROPERTY-AND-FUZZ.md; the coverage and fuzzing phases draw the same inputs for one "
                "operation, the stateful phase needs the whole run):", "", "```sh", "cd core"]
        out += [reproduce(f, seed, examples) for f in found[:3]]
        out += ["```", ""]
    if checks:
        out += ["### Audit checks (core/tests/api_fuzz_check.py)", ""]
        out += [f"- {c}" for c in checks[:MAX_FINDINGS]] + [""]
    if not found and not checks:
        out += ["No JUnit failure or audit FAIL line was recorded: the job failed in another step "
                "(timeout, gateway start, install). Open the run for the log.", ""]
    out += ["The JUnit reports, the gateway log and the audit log are in the run's artifact (14 days)."]
    text = "\n".join(out) + "\n"
    return text if len(text) <= MAX_BODY else text[:MAX_BODY] + "\n\n(truncated; the rest is in the run)\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fuzz-dir", type=Path, required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--examples", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--outcomes", default="")
    a = ap.parse_args()
    if not a.seed.isdigit() or not a.examples.isdigit():
        print("FAIL: --seed and --examples must be whole numbers", file=sys.stderr)
        return 2
    sys.stdout.write(body(a.fuzz_dir, a.seed, a.examples, a.sha, a.ref, a.run_url, a.outcomes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
