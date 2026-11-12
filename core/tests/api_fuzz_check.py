# SPDX-License-Identifier: Apache-2.0
"""Checks .github/workflows/api-fuzz.yml runs after Schemathesis has fuzzed the gateway.

Schemathesis checks each response on its own (no 5xx, documented status codes and bodies). These
checks look at what the whole run left behind, which is where "AI never actuates without human
approval" shows:

  --phase agent   after fuzzing with only the agent token: no action left awaiting_approval or
                  expired, no decision and no dispatch in the audit log, every authz.denied entry
                  is the agent's
  --phase owner   after fuzzing with the owner token too: every approval and denial in the audit
                  log is a person with role owner, and every dispatch follows an approval
  both            the audit chain verifies, and the gateway log has no traceback

  python tests/api_fuzz_check.py --phase agent|owner --audit FILE --log FILE --gateway URL
  (the owner token is read from the OWNER_TOKEN environment variable, never from the command line)

How to run the whole fuzz job locally: docs/testing/PROPERTY-AND-FUZZ.md.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.request
from pathlib import Path

from onemind_core.audit import verify

UNDECIDED = {"awaiting_approval", "expired"}


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def actions(gateway: str, token: str) -> list[dict]:
    req = urllib.request.Request(f"{gateway}/v1/actions", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (loopback URL from the workflow)
        return json.load(resp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("agent", "owner"), required=True)
    ap.add_argument("--audit", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--gateway", default="http://127.0.0.1:8080")
    a = ap.parse_args()
    problems: list[str] = []

    ok, n, reason = verify(a.audit)
    if not ok:
        problems.append(f"audit chain broken after {n} lines: {reason}")
    recs = records(a.audit) if a.audit.exists() else []
    counts = collections.Counter(r["event"] for r in recs)

    def principal(r: dict) -> tuple:
        p = r.get("principal") or {}
        return p.get("kind"), p.get("role")

    for r in recs:
        if r["event"] in ("action.approved", "action.denied") and principal(r) != ("person", "owner"):
            problems.append(f"seq {r['seq']}: {r['event']} by {r.get('principal')}")
    approved = {r["action_id"] for r in recs if r["event"] == "action.approved"}
    for r in recs:
        if r["event"] == "action.dispatched" and r["action_id"] not in approved:
            problems.append(f"seq {r['seq']}: dispatched without an approval")

    if a.phase == "agent":
        for event in ("action.approved", "action.denied", "action.dispatched"):
            if counts[event]:
                problems.append(f"{counts[event]} {event} entries after an agent-only run")
        for r in recs:
            if r["event"] == "authz.denied" and principal(r) != ("agent", "agent"):
                problems.append(f"seq {r['seq']}: authz.denied for {r.get('principal')} in an agent-only run")
        listed = actions(a.gateway, os.environ["OWNER_TOKEN"])
        moved = [x for x in listed if x["state"] not in UNDECIDED or x.get("decided_by")]
        problems += [f"action {x['id']} is {x['state']} after an agent-only run" for x in moved]
        print(f"agent run: the agent requested {len(listed)} actions; {len(listed) - len(moved)} are undecided")

    log = a.log.read_text(encoding="utf-8", errors="replace") if a.log.exists() else ""
    if "Traceback (most recent call last)" in log:
        problems.append(f"gateway log has a traceback (see {a.log.name})")

    summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    print(f"{a.phase} phase: audit {n} lines ({summary})")
    for p in problems:
        print(f"FAIL: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
