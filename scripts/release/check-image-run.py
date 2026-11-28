#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Trust an image.yml run before the release builds from its commit (release.yml android job; issue #880).

  gh api repos/OWNER/NAME/actions/runs/ID > run.json
  check-image-run.py --run-json run.json --run-id ID --repo OWNER/NAME --git DIR

DIR is a full clone of the workflow's own ref (actions/checkout with fetch-depth: 0), so it has origin/main and
origin/release/next. Prints the run's commit on success. Refuses (exit 2) unless every check holds:
  - the run ID is a number and the JSON is that run;
  - the run is .github/workflows/image.yml (named "image") of this repository, not a fork's;
  - it was started by a push or a manual dispatch: image.yml also runs on pull requests, fork PRs included, and
    the android job holds the Android upload-key secrets, so a PR run's code must never be built there;
  - it finished, and succeeded;
  - its commit is a full SHA reachable from origin/main or origin/release/next (git merge-base --is-ancestor), so
    the release builds and tags only reviewed code.
NOTE (issue #1110): a push or nightly run builds tier 1 + 2 only; tier 3 artifacts exist only in a full dispatch run.
This script does not see artifacts, so release.yml checks that the tier 3 artifacts exist before it downloads anything.
This script reads only the run's metadata and the clone; it never sees a secret.
"""
import argparse, json, os, re, subprocess, sys

WORKFLOW = ".github/workflows/image.yml"
NAME = "image"
EVENTS = ("push", "workflow_dispatch")
BRANCHES = ("main", "release/next")
SHA = re.compile(r"^[0-9a-f]{40}$")


def refuse(msg):
    print(f"check-image-run: REFUSED: {msg}", file=sys.stderr)
    return 2


def reachable(git_dir, sha, branch):
    # GIT_DIR / GIT_WORK_TREE from a caller would point git at another checkout; never inherit them.
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    r = subprocess.run(["git", "-C", git_dir, "merge-base", "--is-ancestor", sha, f"refs/remotes/origin/{branch}"],
                       env=env, capture_output=True)
    return r.returncode == 0       # 1: not an ancestor; 128: unknown commit (a fork's) or no such branch


def check(run, run_id, repo, git_dir):
    """Returns (sha, None) when the run can be trusted, else (None, reason)."""
    if not re.fullmatch(r"[1-9][0-9]*", run_id or ""):
        return None, f"image run ID {run_id!r} is not a number"
    if not isinstance(run, dict) or str(run.get("id")) != run_id:
        return None, f"the run details are not for run {run_id}"
    path = str(run.get("path") or "").split("@", 1)[0]
    if path != WORKFLOW or run.get("name") != NAME:
        return None, f"run {run_id} is {run.get('name')!r} ({path or 'no path'}), not the image workflow ({WORKFLOW})"
    head_repo = ((run.get("head_repository") or {}).get("full_name") or "")
    if head_repo.lower() != repo.lower():
        return None, f"run {run_id} built code from {head_repo or 'an unknown repository'}, not {repo}"
    if run.get("event") not in EVENTS:
        return None, f"run {run_id} was started by {run.get('event')!r}; only a push or a manual dispatch is released"
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return None, f"run {run_id} is {run.get('status')}/{run.get('conclusion')}, not completed/success"
    sha = run.get("head_sha") or ""
    if not SHA.match(sha):
        return None, f"run {run_id} has no full commit ({sha!r})"
    if not any(reachable(git_dir, sha, b) for b in BRANCHES):
        return None, f"commit {sha} is not on origin/{' or origin/'.join(BRANCHES)}; only reviewed code is released"
    return sha, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-json", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--git", required=True, help="a full clone of the workflow's own ref")
    a = ap.parse_args(argv)
    try:
        with open(a.run_json, encoding="utf-8") as f:
            run = json.load(f)
    except (OSError, ValueError) as e:
        return refuse(f"cannot read the run details: {e}")
    sha, why = check(run, a.run_id, a.repo, a.git)
    if why:
        return refuse(why)
    print(sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
