#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Job-started hook inside every job VM (CI-14; ACTIONS_RUNNER_HOOK_JOB_STARTED in the runner's .env).
# Refuses any job triggered by a pull request whose head repository is not this repository (a fork),
# or whose head repository is gone. The workflows' runs-on expression already keeps fork PRs on
# GitHub-hosted runners, but a fork PR runs its own copy of the workflow files and could hard-code
# this runner's labels; this check runs on the machine itself, so the PR cannot change it.
set -eu
python3 -I - "${GITHUB_EVENT_PATH:-/nonexistent}" "${GITHUB_REPOSITORY:-}" <<'PY'
import json, sys
path, repo = sys.argv[1], sys.argv[2]
try:
    ev = json.load(open(path))
except OSError:
    sys.exit(0)  # no event file: not a pull request event
pr = ev.get("pull_request")
if pr is None:
    sys.exit(0)
head = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
if head != repo:
    print(f"onemind-kvm refuses pull requests from forks (head {head!r}, repository {repo!r})", file=sys.stderr)
    sys.exit(1)
PY
