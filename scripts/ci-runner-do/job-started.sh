#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Job-started hook inside every job container (ACTIONS_RUNNER_HOOK_JOB_STARTED). Fails CLOSED: the job runs
# only if the event file and repository are known, the event is on the allow-list (push, schedule,
# workflow_dispatch, merge_group, pull_request; a called workflow sees its caller's event) and, for a pull
# request, its head repository is this repository (not a fork, not gone). The workflows' runs-on expression
# already keeps fork PRs on GitHub-hosted runners, but a fork PR runs its own copy of the workflow files and
# could hard-code this runner's labels; this check runs on the machine itself, so the PR cannot change it.
# Same policy as scripts/ci-runner-kvm/job-started.sh. It prints what it checked, so every job log shows it ran.
set -eu
python3 -I - "${GITHUB_EVENT_PATH:-}" "${GITHUB_REPOSITORY:-}" "${GITHUB_EVENT_NAME:-}" <<'PY'
import json, sys
path, repo, name = sys.argv[1], sys.argv[2], sys.argv[3]
def refuse(why):
    print(f"onemind-do guard: REFUSED ({why})", file=sys.stderr)
    sys.exit(1)
if not path or not repo:
    refuse("GITHUB_EVENT_PATH or GITHUB_REPOSITORY not set")
try:
    with open(path) as f:
        ev = json.load(f)
except (OSError, ValueError) as e:
    refuse(f"cannot read the event file: {e}")
ALLOWED = {"push", "schedule", "workflow_dispatch", "merge_group", "pull_request"}
if name not in ALLOWED:
    refuse(f"event {name!r} is not on the allow-list {sorted(ALLOWED)}")
pr = ev.get("pull_request")
if name == "pull_request" and pr is None:
    refuse("pull_request event without a pull_request payload")
if pr is not None:
    head = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    if head != repo:
        refuse(f"pull request from a fork or a deleted repository: head {head!r}, repository {repo!r}")
print(f"onemind-do guard: ok (event {name}, repository {repo}, allow-list and fork check passed)")
PY
