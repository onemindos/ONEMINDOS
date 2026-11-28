#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pick which ci-core shards run for this event (CI-03, issue 228). Run by .github/workflows/ci-core.yml.

Why: the org shares 20 concurrent GitHub-hosted jobs (Free plan), and all seven shards on every PR
push left runs queued for up to 85 minutes. Founder choice (2026-11-15): each PR push runs only the
6 SQLite shards (fast feedback; 3 until 2026-11-28); the 4 PostgreSQL + NATS shards run once per merge, in the merge
queue, where the `merge-gate` check holds the merge until they pass. Pushes to main and manual runs
still run all seven.

  pull_request  -> 6 SQLite shards
  merge_group   -> 4 PostgreSQL shards, only if the queued change touches core/, sdk/ or this
                   workflow (merge_group events have no `paths:` filter, so we filter here)
  push, workflow_dispatch -> all 10

CI-13 (issue 299): the SQLite shards need no Docker services, so they may run on the Mac's local
runner; the PostgreSQL shards need the postgres and nats service containers and stay GitHub-hosted.
So the workflow has one job per backend, and this script also writes each backend's own matrix.

Environment: EVENT; for merge_group also GH_TOKEN, REPO, BASE_SHA, HEAD_SHA.
Writes `matrix=<json>` and `run=true|false` (all shards), plus `sqlite=<json>`, `run_sqlite=`,
`postgresql=<json>` and `run_postgresql=` (one backend each) to $GITHUB_OUTPUT (or stdout without it).
Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

SQLITE = [{"backend": "sqlite", "shard": f"{i}/6"} for i in range(1, 7)]  # 6 since 2026-11-28 (was 3)
POSTGRES = [{"backend": "postgresql", "shard": f"{i}/4"} for i in (1, 2, 3, 4)]
WATCHED = ("core/", "sdk/", ".github/workflows/ci-core.yml", "scripts/ci-core-matrix.py")
COMPARE_LIMIT = 300  # the compare API lists at most 300 files; past that, assume core changed


def touches_core(files: list[str]) -> bool:
    return any(f.startswith(WATCHED) for f in files)


def shards(event: str, files: list[str] | None = None) -> list[dict]:
    if event == "pull_request":
        return SQLITE
    if event == "merge_group":
        if files is None or len(files) >= COMPARE_LIMIT or touches_core(files):
            return POSTGRES
        return []
    return SQLITE + POSTGRES


def changed_files(repo: str, base: str, head: str, token: str) -> list[str] | None:
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/compare/{base}...{head}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "onemind-ci-core-matrix",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return [f["filename"] for f in json.load(resp).get("files", [])]
    except OSError as e:  # can't tell what changed: run the shards rather than skip them
        print(f"compare failed ({e}); running all PostgreSQL shards", file=sys.stderr)
        return None


def main() -> int:
    env = os.environ
    event = env["EVENT"]
    files = None
    if event == "merge_group":
        files = changed_files(env["REPO"], env["BASE_SHA"], env["HEAD_SHA"], env["GH_TOKEN"])
    include = shards(event, files)
    lines = [f"matrix={json.dumps({'include': include})}", f"run={'true' if include else 'false'}"]
    for backend in ("sqlite", "postgresql"):
        part = [j for j in include if j["backend"] == backend]
        lines += [f"{backend}={json.dumps({'include': part})}", f"run_{backend}={'true' if part else 'false'}"]
    print("\n".join(lines))
    if out := env.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
