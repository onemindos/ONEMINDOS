# SPDX-License-Identifier: Apache-2.0
"""Fail-fast detector for the QEMU boot harnesses (firstboot.py, cloudboot.py, installer.py).

Pure functions, no VM needed (unit-tested in test/unit/test_qemu_failfast.py). The harnesses wait for
a gate line or for /healthz; when the guest has already shown a fatal sign, waiting out the full timeout
only delays the same FAIL. This module decides "is the result already known to be a failure?". It never
changes what counts as pass or fail (the CRITERIA files are untouched): a run that would have timed out
now stops early with the cause in the log.

Opt-in per harness (VM.failfast = True): the T-battery (run-tests.py) provokes kernel panics and
failed units on purpose (T6, T7), so it must not use it.
"""
import re

GATEWAY_UNIT = "onemind-gateway.service"
RESTART_LIMIT = 5            # a unit restarted this often is in a crash loop (RestartSec=3s: ~15 s of failing)

_UNIT = r"onemind[\w@.\\-]*"
# (name, regex). Searched in console/journal text, reported in this order.
FATAL = [
    ("kernel-panic", re.compile(r"Kernel panic - not syncing")),
    ("emergency-mode", re.compile(r"(?i)(?:Welcome to|You are in|Entering|Started) emergency (?:mode|shell)|"
                                  r"Cannot open access to console, the root account is locked")),
    ("unit-failed-to-start", re.compile(rf"Failed to start [^\n]*?{_UNIT}|"
                                        rf"{_UNIT}\.service: Failed with result '(?!success)")),
    ("unit-restart-loop", re.compile(rf"{_UNIT}\.service: Scheduled restart job, restart counter is at (\d+)")),
]
_TRACE = re.compile(r"Traceback \(most recent call last\):")


def scan(text):
    """Return a short reason string for the first fatal sign in `text`, or None."""
    for name, rx in FATAL:
        for m in rx.finditer(text):
            if name == "unit-restart-loop" and int(m.group(1)) < RESTART_LIMIT:
                continue
            return f"{name}: {m.group(0).strip()[:160]}"
    for m in _TRACE.finditer(text):
        # A Python traceback counts only when it belongs to a OneMind unit: its frames (file paths) or the
        # journal prefix mention onemind. cloud-init and other guest software print tracebacks too.
        ctx = text[text.rfind("\n", 0, m.start()) + 1:m.end() + 1500]     # this line's prefix + the frames after it
        if re.search(r"onemind", ctx, re.I):
            return "python-traceback: " + ctx[ctx.find("Traceback"):][:160].replace("\n", " | ")
    return None


def restarts_exceeded(n_restarts):
    """True when a unit's systemd NRestarts counter shows a crash loop."""
    try:
        return int(n_restarts) >= RESTART_LIMIT
    except (TypeError, ValueError):
        return False


def dump_cmd(unit=GATEWAY_UNIT, lines=200):
    """Shell command that prints the evidence for a unit that never came up (journal tail + state)."""
    return (f"echo '--- journal {unit}'; journalctl -u {unit} -u onemind-firstboot.service -n {lines} --no-pager 2>&1 | tail -{lines}; "
            f"echo '--- state'; systemctl show -p ActiveState,SubState,Result,NRestarts,ExecMainStatus {unit} 2>&1; "
            "systemctl --failed --no-legend --no-pager 2>&1 | head -20")


class Watch:
    """Incremental scanner: feed it the growing log, it rescans only the new tail (plus an overlap so a
    pattern split across two reads is still seen)."""
    OVERLAP = 2000

    def __init__(self):
        self.pos = 0

    def check(self, buf):
        if self.pos > len(buf):          # the harness cleared its buffer (VM restart)
            self.pos = 0
        start = max(0, self.pos - self.OVERLAP)
        self.pos = len(buf)
        return scan(buf[start:])
