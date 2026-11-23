# SPDX-License-Identifier: Apache-2.0
"""BAK-02 (#163): the pure core of the whole-box restore drill. No VM, no network, no clock of its own.

The drill (drill.py + in-vm.sh) prints marker lines while it runs:

    DRILL-PHASE <name> start <epoch-seconds>
    DRILL-PHASE <name> end <epoch-seconds>
    PASS  <check text>            /  FAIL  <check text>
    DRILL-INFO <key>=<value>

This module turns that text into a verdict. The rule the year-1 exit criterion sets: the restore
clock (install on the clean box + restore + verify) must be 3600 s or less AND every check must pass
AND every phase of the restore clock must have finished. A run that did not reach a phase is a FAIL,
never a pass: nothing is counted that did not run.
"""
import json
import re

BUDGET_SECONDS = 3600

# Phases in the order they happen. SOURCE phases build the box being protected and are not on the
# clock; RESTORE phases are the clock the exit criterion measures (a fresh machine to a verified box).
SOURCE_PHASES = ("seed",)
RESTORE_PHASES = ("install", "restore", "verify")

# A PASS must include a passing check for each of these (a substring of the check text printed by in-vm.sh): the
# system snapshot is restored onto the new box and read back, not just found in the repository. A run whose script
# lost one of these checks cannot go green by silence.
REQUIRED_CHECKS = (
    "k3s runs from the old box's datastore",
    "gateway database is the old box's",
    "audit log is back",
)

_PHASE = re.compile(r"^DRILL-PHASE (?P<name>[a-z][a-z0-9_-]*) (?P<edge>start|end) (?P<t>\d+(?:\.\d+)?)\s*$")
_CHECK = re.compile(r"^(?P<res>PASS|FAIL) {1,2}(?P<text>.+?)\s*$")
_INFO = re.compile(r"^DRILL-INFO (?P<k>[a-z_]+)=(?P<v>.*?)\s*$")


def parse(text):
    """Return (phases, checks, info) from the combined output of the in-VM script.

    phases: {name: {"start": float|None, "end": float|None}} (a repeated edge keeps the first start and the last end)
    checks: [{"result": "PASS"|"FAIL", "text": str}]
    info:   {key: value}
    """
    phases, checks, info = {}, [], {}
    for line in text.splitlines():
        line = line.rstrip("\r")
        m = _PHASE.match(line)
        if m:
            p = phases.setdefault(m["name"], {"start": None, "end": None})
            t = float(m["t"])
            if m["edge"] == "start":
                p["start"] = t if p["start"] is None else min(p["start"], t)
            else:
                p["end"] = t if p["end"] is None else max(p["end"], t)
            continue
        m = _CHECK.match(line)
        if m:
            checks.append({"result": m["res"], "text": m["text"]})
            continue
        m = _INFO.match(line)
        if m:
            info[m["k"]] = m["v"]
    return phases, checks, info


def durations(phases):
    """Seconds per finished phase. A phase with a missing edge, or an end before its start, is None."""
    out = {}
    for name, p in phases.items():
        s, e = p["start"], p["end"]
        out[name] = None if s is None or e is None or e < s else round(e - s, 1)
    return out


def restore_clock(phases):
    """Seconds from the first restore phase start to the last restore phase end (wall clock, so gaps between
    phases count), or None when any restore phase is missing or unfinished."""
    starts, ends = [], []
    for name in RESTORE_PHASES:
        p = phases.get(name)
        if not p or p["start"] is None or p["end"] is None or p["end"] < p["start"]:
            return None
        starts.append(p["start"])
        ends.append(p["end"])
    return round(max(ends) - min(starts), 1)


def evaluate(text, budget_s=BUDGET_SECONDS, boot_seconds=None, abort=None, restore_mode=None):
    """Judge one drill run. Returns a JSON-able dict with `verdict` in PASS, OVER_BUDGET or FAIL.

    boot_seconds is the host-measured time to boot the clean VM (not on the clock: the criterion starts
    when the new hardware is up). abort is the reason the harness stopped early, if it did.
    """
    phases, checks, info = parse(text)
    dur = durations(phases)
    clock = restore_clock(phases)
    failed = [c["text"] for c in checks if c["result"] == "FAIL"]
    missing = [n for n in RESTORE_PHASES if n not in phases or dur.get(n) is None]
    reasons = []
    if abort:
        reasons.append(f"harness stopped early: {abort}")
    if failed:
        reasons.append(f"{len(failed)} check(s) failed")
    if missing:
        reasons.append("restore phase not finished: " + ", ".join(missing))
    if not any(c["result"] == "PASS" for c in checks):
        reasons.append("no check passed")
    absent = [r for r in REQUIRED_CHECKS if not any(c["result"] == "PASS" and r in c["text"] for c in checks)]
    if absent and not abort and not failed:
        reasons.append("required check did not pass: " + "; ".join(absent))
    over = clock is not None and clock > budget_s
    if reasons:
        verdict = "FAIL"
    elif over:
        verdict = "OVER_BUDGET"
        reasons.append(f"restore took {clock:.0f} s, budget {budget_s} s")
    else:
        verdict = "PASS"
    return {
        "suite": "restore-drill", "criterion": "BAK-02", "verdict": verdict, "reasons": reasons,
        "budget_seconds": budget_s, "restore_seconds": clock, "boot_seconds": boot_seconds,
        "phases": dur, "checks_passed": sum(c["result"] == "PASS" for c in checks),
        "checks_failed": failed, "restore_mode": restore_mode or info.get("restore_mode", "unknown"),
        "info": info,
    }


def exit_code(result):
    """0 only for PASS. Over budget and failed both fail CI (the issue: fails CI if over 60 minutes)."""
    return 0 if result["verdict"] == "PASS" else 1


def summary_markdown(result):
    """GitHub step-summary text for one run."""
    r = result
    secs = r["restore_seconds"]
    head = f"### restore-drill: {r['verdict']}"
    if secs is not None:
        head += f" ({secs / 60:.1f} of {r['budget_seconds'] / 60:.0f} min)"
    lines = [head, "", f"Restore path: `{r['restore_mode']}`.", "", "| Phase | Seconds |", "|---|---|"]
    for name in SOURCE_PHASES + RESTORE_PHASES:
        v = r["phases"].get(name)
        lines.append(f"| {name}{'' if name in RESTORE_PHASES else ' (not on the clock)'} | {'-' if v is None else v} |")
    if r.get("boot_seconds") is not None:
        lines.append(f"| clean VM boot (not on the clock) | {r['boot_seconds']} |")
    for why in r["reasons"]:
        lines.append(f"\n- {why}")
    for f in r["checks_failed"]:
        lines.append(f"- failed check: {f}")
    return "\n".join(lines) + "\n"


def dumps(result):
    return json.dumps(result, indent=2, sort_keys=True) + "\n"
