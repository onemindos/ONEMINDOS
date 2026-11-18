#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one always-reporting merge gate (CI-02, issue 227). Run by .github/workflows/gate.yml.

Why: most workflows have `paths:` filters, so on a docs-only PR ci-core or image never starts and
never reports. A required check that never reports blocks the PR forever, so main could only
require the four checks that always run (dco, hygiene, lint, unit), and a PR with a red ci-core or
battery could still merge (#123). This gate always runs and always reports: it waits for every
other workflow run GitHub started for the same commit and event, and fails if any blocking one did
not succeed. A docs-only PR starts only the quick workflows, so the gate passes in minutes; a PR
that breaks core tests or the battery fails it. Main needs only one required check: `merge-gate`.

Blocking is the default, so a new workflow protects main without editing this file. The
INFORMATIONAL workflows below are reported but never block (fuzzers, scans, perf and multi-VM
smoke tests: useful signals, too slow or too noisy to hold every merge).

Environment: GH_TOKEN, REPO (owner/name), HEAD_SHA, EVENT (pull_request | merge_group), RUN_ID
(this run, skipped). Optional: DRAFT (true on a draft PR, for the log), GATE_SETTLE_S (default 45), GATE_POLL_S (30), GATE_TIMEOUT_S (10200).
No dependencies beyond the Python standard library.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

INFORMATIONAL = frozenset({
    "api-fuzz", "go-fuzz", "perf-smoke", "security-nightly", "net-2vm", "apps-gate-all",
})
PASSING = frozenset({"success", "skipped", "neutral"})
# Runs older than this, measured from the gate's own start, belong to an earlier event on the same
# commit and are ignored. Why (CI-09, issue 298): a draft push skips the heavy workflows, so the SHA
# already carries "skipped" runs. When the PR is marked ready, GitHub starts fresh runs and a fresh
# gate within seconds; without this window a gate that looked a moment too early would see only the
# old skipped runs and pass before the heavy workflows even started.
FRESH_WINDOW_S = 300
GATE_NAME = "merge-gate"


def _ts(value: str | None) -> float | None:
    if not value:
        return None
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def latest_per_workflow(runs: list[dict]) -> list[dict]:
    """One run per workflow: the newest (a re-run of a failed job keeps the same run id)."""
    best: dict[int, dict] = {}
    for r in runs:
        wid = r["workflow_id"]
        if wid not in best or r["id"] > best[wid]["id"]:
            best[wid] = r
    return sorted(best.values(), key=lambda r: r["name"])


def verdict(runs: list[dict], self_run_id: int) -> dict[str, list[str]]:
    """Sort the runs of one commit into failed / pending / passed / informational (by name)."""
    out: dict[str, list[str]] = {"failed": [], "pending": [], "passed": [], "informational": []}
    me = next((r for r in runs if r["id"] == self_run_id), None)
    anchor = _ts(me.get("created_at")) if me else None
    # The gate never waits on a gate: not this run, and not an earlier gate run of the same commit (a
    # draft push's gate, cancelled by concurrency when the PR was marked ready, would count as failed).
    me_wid = me["workflow_id"] if me else None
    others = [r for r in runs if r["id"] != self_run_id and r["name"] != GATE_NAME
              and (me_wid is None or r["workflow_id"] != me_wid)]
    if anchor is not None:
        others = [r for r in others if (_ts(r.get("created_at")) or anchor) >= anchor - FRESH_WINDOW_S]
    for r in latest_per_workflow(others):
        name = r["name"]
        if name in INFORMATIONAL:
            out["informational"].append(f"{name}={r.get('conclusion') or r['status']}")
        elif r["status"] != "completed":
            out["pending"].append(name)
        elif r.get("conclusion") in PASSING:
            out["passed"].append(name)
        else:
            out["failed"].append(f"{name}={r.get('conclusion')} {r.get('html_url', '')}".strip())
    return out


def fetch_runs(repo: str, sha: str, event: str, token: str) -> list[dict]:
    runs, page = [], 1
    while True:
        q = urllib.parse.urlencode({"head_sha": sha, "event": event, "per_page": 100, "page": page})
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/runs?{q}", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "onemind-ci-gate",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.load(resp)["workflow_runs"]
        runs += batch
        if len(batch) < 100:
            return runs
        page += 1


def main() -> int:
    env = os.environ
    repo, sha, event, token = env["REPO"], env["HEAD_SHA"], env["EVENT"], env["GH_TOKEN"]
    self_id = int(env["RUN_ID"])
    settle, poll = int(env.get("GATE_SETTLE_S", "45")), int(env.get("GATE_POLL_S", "30"))
    deadline = time.time() + int(env.get("GATE_TIMEOUT_S", "10200"))
    if env.get("DRAFT") == "true":
        print("gate: this PR is a draft, so only dco, hygiene, lint and unit run; the heavy workflows "
              "skip. Marking it ready starts a new gate that waits for all of them.")
    print(f"gate: {event} {sha}; waiting {settle}s for every workflow to start")
    time.sleep(settle)  # all runs of one event are created within seconds of each other
    last = None
    while True:
        try:
            v = verdict(fetch_runs(repo, sha, event, token), self_id)
        except OSError as exc:  # a GitHub API hiccup is not a verdict; try again next poll
            print(f"gate: API error ({exc}); retrying")
            time.sleep(poll)
            continue
        line = (f"passed={v['passed']} pending={v['pending']} failed={v['failed']} "
                f"informational={v['informational']}")
        if line != last:
            print(f"gate [{time.strftime('%H:%M:%S')}]: {line}", flush=True)
            last = line
        if v["failed"]:
            print("gate: FAILED. Fix the failing workflow(s) above; this gate re-runs on the next push.")
            return 1
        if not v["pending"]:
            print(f"gate: PASSED ({len(v['passed'])} blocking workflow(s) green)")
            return 0
        if time.time() > deadline:
            print(f"gate: TIMEOUT waiting for {v['pending']}")
            return 1
        time.sleep(poll)


if __name__ == "__main__":
    sys.exit(main())
