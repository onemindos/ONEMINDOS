# SPDX-License-Identifier: Apache-2.0
"""Checks .github/workflows/api-fuzz.yml runs after Schemathesis has fuzzed the gateway.

Schemathesis checks each response on its own (no 5xx, documented status codes and bodies). These
checks look at what the whole run left behind, which is where "AI never actuates without human
approval" shows:

  --phase prepare before fuzzing: the agent requests one install per catalog app, and a
                  Schemathesis config (--config) points path.action_id at those real actions and
                  body.params.app_id at real apps, so approve and deny are tried on actions that
                  exist instead of only answering 404
  --phase agent   after fuzzing with only the agent token: every action is still awaiting_approval
                  or expired (and there are some), no decision and no dispatch in the audit log,
                  every authz.denied entry is the agent's
  --phase owner   after fuzzing with the owner token too: every approval and denial in the audit
                  log is a person with role owner, and every dispatch follows an approval
  both            the audit chain verifies, and the gateway log has no traceback

  python tests/api_fuzz_check.py --phase prepare --config FILE --gateway URL
  python tests/api_fuzz_check.py --phase agent|owner --audit FILE --log FILE --gateway URL
  (tokens come from OWNER_TOKEN and AGENT_TOKEN in the environment, never from the command line)

How to run the whole fuzz job locally: docs/testing/PROPERTY-AND-FUZZ.md.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from onemind_core.audit import verify

UNDECIDED = {"awaiting_approval", "expired"}


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def call(gateway: str, token: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{gateway}{path}", data=data, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (loopback URL from the workflow)
        return json.load(resp)


def actions(gateway: str, token: str) -> list[dict]:
    return call(gateway, token, "/v1/actions")


def decision_problems(recs: list[dict], listed: list[dict]) -> list[str]:
    """Independent temporal and ledger/audit oracle, also exercised by negative controls."""
    problems = []
    decisions, decision_kinds, outcomes = {}, {}, {}
    approved, dispatched = set(), set()
    terminal_events = {"action.succeeded", "action.failed", "action.outcome_unknown", "action.expired"}
    for r in recs:
        event, action_id = r["event"], r.get("action_id")
        if event in ("action.approved", "action.denied"):
            principal = r.get("principal") or {}
            if (principal.get("kind"), principal.get("role")) != ("person", "owner"):
                problems.append(f"seq {r['seq']}: decision by a non-owner")
            if action_id in decisions:
                problems.append(f"seq {r['seq']}: duplicate decision")
            decisions[action_id] = principal
            decision_kinds[action_id] = event
            if event == "action.approved":
                approved.add(action_id)
        if event == "action.dispatched":
            if action_id in outcomes:
                problems.append(f"seq {r['seq']}: dispatch after terminal outcome")
            if action_id not in approved:
                problems.append(f"seq {r['seq']}: dispatched without an earlier approval")
            if action_id in dispatched:
                problems.append(f"seq {r['seq']}: duplicate dispatch")
            dispatched.add(action_id)
        if event in terminal_events:
            if action_id in outcomes:
                problems.append(f"seq {r['seq']}: duplicate outcome")
            outcomes[action_id] = event
            if event in {"action.succeeded", "action.failed"} and action_id not in dispatched:
                problems.append(f"seq {r['seq']}: outcome without earlier dispatch")
            if event == "action.outcome_unknown" and action_id not in approved:
                problems.append(f"seq {r['seq']}: unknown outcome without earlier approval")
    ledger = {a["id"]: a for a in listed}
    approved_states = {"accepted", "dispatched", "succeeded", "failed", "outcome_unknown"}
    for action_id in decisions.keys() | ledger.keys() | dispatched | outcomes.keys():
        action = ledger.get(action_id, {})
        decider, state = action.get("decided_by"), action.get("state")
        if decisions.get(action_id) != decider or action_id not in ledger:
            problems.append(f"action {action_id}: ledger/audit decider mismatch")
        expected_kind = ("action.approved" if state in approved_states else
                         "action.denied" if state == "cancelled" else None)
        if decision_kinds.get(action_id) != expected_kind:
            problems.append(f"action {action_id}: ledger state/decision kind mismatch")
        if state in {"dispatched", "succeeded", "failed"} and action_id not in dispatched:
            problems.append(f"action {action_id}: ledger state requires dispatch")
        if state not in approved_states and action_id in dispatched:
            problems.append(f"action {action_id}: dispatch incompatible with ledger state")
        expected_outcome = "action." + state if state in {"succeeded", "failed", "outcome_unknown", "expired"} else None
        if outcomes.get(action_id) != expected_outcome:
            problems.append(f"action {action_id}: ledger state/outcome mismatch")
    return problems


def prepare(gateway: str, config: Path) -> int:
    apps = [a["id"] for a in call(gateway, os.environ["OWNER_TOKEN"], "/v1/apps")]
    expires = (datetime.now(UTC) + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    ids = []
    for app_id in apps:
        a = call(gateway, os.environ["AGENT_TOKEN"], "/v1/actions", {
            "type": "app.install", "params": {"app_id": app_id},
            "idempotency_key": f"fuzz-seed-{app_id}", "expires_at": expires})
        ids.append(a["id"])
    if not ids:
        print("FAIL: the catalog is empty, nothing to aim the fuzzers at", file=sys.stderr)
        return 1
    q = lambda xs: ", ".join(json.dumps(x) for x in xs)  # noqa: E731 (JSON strings are TOML strings)
    config.write_text(
        "# Written by tests/api_fuzz_check.py --phase prepare for one api-fuzz.yml run.\n"
        f"[dictionaries.apps]\nvalues = [{q(apps)}]\n\n"
        f"[dictionaries.actions]\nvalues = [{q(ids)}]\n\n"
        "[parameters]\n"
        '"path.action_id" = { dictionary = "actions", probability = 0.8 }\n'
        '"body.params.app_id" = { dictionary = "apps", probability = 0.6 }\n'
        # Absolute metrics windows depend on wall time, which OpenAPI cannot bound.
        # Pin only this parameter; deterministic protocol tests retain syntax/range refusals.
        '\n[[operations]]\ninclude-operation-id = "nodes.metrics"\n'
        '[operations.parameters]\n"query.window" = "3600"\n'
        # Schemathesis 4.33.1 omits 413 from its negative-data defaults, and a generated body of schema-valid
        # or schema-invalid arrays can exceed the gateway's 256 KiB guard on any operation. 413 is therefore
        # expected everywhere, and genuine_payload_rejection (api_fuzz_hooks.py) independently fails every
        # 413 that is not either over the real wire-byte budget or a declared upload size or space limit.
        # A schema-valid request may also be refused 422 where only the server can judge the value (a
        # name's Unicode rules, an opaque cursor, a time zone); semantic_refusal_names_its_reason fails
        # such a 422 unless it carries one of the closed set of reasons. No check is disabled.
        '\n[checks.negative_data_rejection]\n'
        'expected-statuses = [400, 401, 403, 404, 405, 406, 409, 413, 415, 422, 428, 429, "5xx"]\n'
        '\n[checks.positive_data_acceptance]\n'
        'expected-statuses = ["2xx", "3xx", 401, 403, 404, 409, 413, 422, 429, "5xx"]\n'
        # The backup routes answer 503 `unavailable` when the feature is off or its agent is down (§12.2),
        # which is documented. unavailable_is_the_documented_envelope pins the exact envelope and the
        # routes, so any other 5xx anywhere, and any 503 elsewhere, still fails.
        '\n[[operations]]\ninclude-path-regex = "^/v1/(backups|restores)"\n'
        '[operations.checks.not_a_server_error]\n'
        'expected-statuses = ["2xx", "3xx", "4xx", 503]\n'
        # tus: a missing or wrong Tus-Resumable is the protocol's 412 (and a wrong PATCH content type its
        # 415), as the schema's required Tus-Resumable header promises.
        '\n[[operations]]\ninclude-path-regex = "^/v1/files/uploads"\n'
        '[operations.checks.negative_data_rejection]\n'
        'expected-statuses = [400, 401, 403, 404, 405, 406, 409, 412, 413, 415, 422, 428, 429, "5xx"]\n'
        '[operations.checks.missing_required_header]\n'
        'expected-statuses = [400, 401, 403, 406, 412, 415, 422]\n'
    )
    print(f"prepare: the agent requested {len(ids)} installs; config aims the fuzzers at them")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("prepare", "agent", "owner"), required=True)
    ap.add_argument("--audit", type=Path)
    ap.add_argument("--log", type=Path)
    ap.add_argument("--config", type=Path)
    ap.add_argument("--gateway", default="http://127.0.0.1:8080")
    a = ap.parse_args()
    if a.phase == "prepare":
        return prepare(a.gateway, a.config)
    problems: list[str] = []

    if not a.audit.is_file() or not a.log.is_file():
        print("FAIL: both audit and gateway log evidence files are required", file=sys.stderr)
        return 1
    ok, n, reason = verify(a.audit)
    if not ok:
        problems.append(f"audit chain broken after {n} lines: {reason}")
    recs = records(a.audit) if a.audit.exists() else []
    counts = collections.Counter(r["event"] for r in recs)
    listed = actions(a.gateway, os.environ["OWNER_TOKEN"])
    problems.extend(decision_problems(recs, listed))
    if not recs:
        problems.append("no audit records were produced")

    def principal(r: dict) -> tuple:
        p = r.get("principal") or {}
        return p.get("kind"), p.get("role")

    for r in recs:
        if r["event"] in ("action.approved", "action.denied") and principal(r) != ("person", "owner"):
            problems.append(f"seq {r['seq']}: {r['event']} by {r.get('principal')}")


    if a.phase == "agent":
        for event in ("action.approved", "action.denied", "action.dispatched"):
            if counts[event]:
                problems.append(f"{counts[event]} {event} entries after an agent-only run")
        for r in recs:
            if r["event"] == "authz.denied" and principal(r) != ("agent", "agent"):
                problems.append(f"seq {r['seq']}: authz.denied for {r.get('principal')} in an agent-only run")

        if not listed:
            problems.append("no action exists, so nothing tested that the agent cannot decide one")
        moved = [x for x in listed if x["state"] not in UNDECIDED or x.get("decided_by")]
        problems += [f"action {x['id']} is {x['state']} after an agent-only run" for x in moved]
        print(f"agent run: the agent requested {len(listed)} actions; {len(listed) - len(moved)} are undecided")
    else:
        for event in ("action.approved", "action.denied", "action.dispatched"):
            if not counts[event]:
                problems.append(f"owner run never exercised {event}")

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
