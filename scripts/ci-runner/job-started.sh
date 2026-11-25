#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Job-started hook for the Mac runner VMs (CI-10, issue 299; ACTIONS_RUNNER_HOOK_JOB_STARTED in each
# runner's .env). Fails CLOSED: the job runs only if the event file and repository are known and, for a
# pull request, its head repository is this repository (not a fork, not a deleted one). The workflows'
# runs-on expression already keeps fork PRs on GitHub-hosted runners, but a fork PR runs its own copy of
# the workflow files and could hard-code this runner's labels; this check runs on the machine itself, so
# the PR cannot change it. It prints what it checked, so every job log shows the guard ran.
set -eu
python3 -I - "${GITHUB_EVENT_PATH:-}" "${GITHUB_REPOSITORY:-}" <<'PY'
import json, sys
path, repo = sys.argv[1], sys.argv[2]
def refuse(why):
    print(f"onemind-local guard: REFUSED ({why})", file=sys.stderr)
    sys.exit(1)
if not path or not repo:
    refuse("GITHUB_EVENT_PATH or GITHUB_REPOSITORY not set")
try:
    with open(path) as f:
        ev = json.load(f)
except (OSError, ValueError) as e:
    refuse(f"cannot read the event file: {e}")
pr = ev.get("pull_request") if isinstance(ev, dict) else None
if pr is not None:
    head = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    if head != repo:
        refuse(f"pull request from a fork or a deleted repository: head {head!r}, repository {repo!r}")
print(f"onemind-local guard: ok (repository {repo}, fork check passed)")
PY
