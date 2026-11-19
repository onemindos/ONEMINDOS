#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The visual verdict of .github/workflows/ui-quality.yml (CI-17): does this PR change how a screen looks?

Why: the screenshots used to be committed PNGs. Every dashboard PR that touched a shared screen carried
new PNGs, so as soon as one merged the others were stale and PRs had to land one at a time. Now each PR
is compared with its base (main), rendered in the same job on the same runner, and nothing is committed.
A difference is not wrong in itself, so a person looks at the diff report and adds the PR label
`visual:accepted` (LABEL) when the change is intended.

Subcommands (standard library only, like scripts/ci-gate.py):
  changes <playwright.json> <out.txt>  list the visual tests that did not match the base (one title per line)
  find-run                             label event: wait for the newest full ui-quality run of this commit,
                                       check that its build and browser jobs passed, print its run id
  verdict <dir>                        read <dir>/visual-changes-<browser>/changes.txt for every browser,
                                       read the PR's timeline now, write the step summary; exit 1 if
                                       screens differ and LABEL was not added after the newest commit
Environment: GH_TOKEN, REPO (owner/name); find-run: RUN_ID, HEAD_SHA, GITHUB_OUTPUT;
verdict: PR (number), GITHUB_STEP_SUMMARY (optional), REPORT_HINT (optional, where the diffs are).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

LABEL = "visual:accepted"
BROWSERS = ("chromium", "firefox", "webkit")
# A labeled/unlabeled run has this run-name (ui-quality.yml `run-name:`), for people reading the run list.
# find-run tells runs apart by their jobs (run_kind), never by name.
RECHECK_PREFIX = "ui-quality: label re-check"
# The jobs of a full run that must have passed (axe, flows and the builds); `visual` is re-decided here.
FULL_RUN_JOBS = ("build",) + BROWSERS


def _api(path: str, token: str):
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "onemind-ui-visual-verdict",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _api_list(path: str, token: str) -> list:
    """Every page of a list endpoint (the PR timeline can be long)."""
    out, page = [], 1
    sep = "&" if "?" in path else "?"
    while True:
        batch = _api(f"{path}{sep}per_page=100&page={page}", token)
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def changed_tests(report: dict) -> list[str]:
    """Titles of the tests that did not pass, from Playwright's JSON reporter.

    A skipped test (the WebKit-only WK-1 skips) is neither a change nor a run: if every test was skipped,
    nothing was compared, and that is refused rather than reported as "no change".
    """
    if report.get("errors"):
        # A global error (web server did not start, config broken) is not "no change": refuse.
        raise ValueError("playwright reported errors: " + "; ".join(
            str(e.get("message", e))[:200] for e in report["errors"]))
    ran, out = 0, []

    def walk(suite: dict) -> None:
        nonlocal ran
        for spec in suite.get("specs", []):
            for t in spec.get("tests", []):
                if t.get("status") == "skipped":
                    continue
                ran += 1
                if t.get("status") != "expected":
                    out.append(spec["title"])
        for s in suite.get("suites", []):
            walk(s)

    for s in report.get("suites", []):
        walk(s)
    if ran == 0:
        raise ValueError("no visual tests ran: check the --grep @visual filter")
    return sorted(set(out))


def run_kind(jobs: list[dict]) -> str:
    """'full' (it rendered or is rendering the screens), 'other' (a label re-check or a draft run, whose
    build job was skipped) or 'unknown' (just queued, jobs not listed yet). Decided from the jobs, not the
    run's name: a PR title can say anything."""
    by_name = {j["name"]: j for j in jobs}
    build = by_name.get("build")
    if build is None:
        return "unknown"
    if build.get("conclusion") == "skipped":
        return "other"
    recheck = by_name.get("visual-recheck")
    if recheck is not None and recheck.get("conclusion") not in (None, "skipped"):
        return "other"
    return "full"


def pick_full_run(runs: list[dict], self_id: int, jobs_of) -> dict | None | str:
    """The newest full run of this commit other than this one; 'unknown' if a newer run cannot be classified yet."""
    for r in sorted((r for r in runs if r["id"] != self_id), key=lambda r: r["id"], reverse=True):
        kind = run_kind(jobs_of(r["id"]))
        if kind == "full":
            return r
        if kind == "unknown":
            return "unknown"
    return None


def full_run_problems(jobs: list[dict]) -> list[str]:
    """Why a full run cannot be re-used: a required job that is missing or did not succeed."""
    by_name = {j["name"]: j.get("conclusion") for j in jobs}
    return [f"{n}={by_name.get(n, 'missing')}" for n in FULL_RUN_JOBS if by_name.get(n) != "success"]


def read_changes(root: Path) -> dict[str, list[str]]:
    out = {}
    for b in BROWSERS:
        f = root / f"visual-changes-{b}" / "changes.txt"
        if not f.is_file():
            raise FileNotFoundError(f"{f} is missing: the {b} visual comparison did not finish")
        out[b] = [line.strip() for line in f.read_text().splitlines() if line.strip()]
    return out


def _ts(value: str | None) -> float:
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() if value else 0.0


def label_is_current(timeline: list[dict]) -> tuple[bool, str]:
    """Is LABEL on the PR, and was it added after the newest commit or force-push? (current, why)

    A label added before a push approved the old screens, not the new ones, so it does not count.
    """
    on, labeled_at, head_at = False, 0.0, 0.0
    for e in timeline:
        ev = e.get("event")
        if ev in ("labeled", "unlabeled") and (e.get("label") or {}).get("name") == LABEL:
            on = ev == "labeled"
            if on:
                labeled_at = max(labeled_at, _ts(e.get("created_at")))
        elif ev == "committed":
            head_at = max(head_at, _ts((e.get("committer") or {}).get("date")))
        elif ev == "head_ref_force_pushed":
            head_at = max(head_at, _ts(e.get("created_at")))
    if not on:
        return False, f"The PR does not carry the `{LABEL}` label."
    if labeled_at <= head_at:
        return False, (f"The `{LABEL}` label was added before the newest commit, so it approved older screens. "
                       f"Look at the new diffs, then remove the label and add it again.")
    return True, f"Accepted: the `{LABEL}` label was added after the newest commit."


def decide(changes: dict[str, list[str]], accepted: bool, why: str = "") -> tuple[bool, str]:
    """(passes, step summary in Markdown)."""
    differ = {b: c for b, c in changes.items() if c}
    if not differ:
        return True, "### Visual check: no screen differs from main\n"
    lines = ["### Visual check: screens that differ from main", ""]
    for b, names in differ.items():
        lines.append(f"- **{b}** ({len(names)}): " + ", ".join(names))
    lines.append("")
    hint = os.environ.get("REPORT_HINT", "")
    if accepted:
        lines.append(f"{why or 'Accepted.'} {hint}".strip())
    else:
        lines.append(f"Not accepted yet. {why} Look at expected, actual and diff for each screen, then add the "
                     f"`{LABEL}` label if the change is intended (ui/test/README.md). {hint}".replace("  ", " ").strip())
    return accepted, "\n".join(lines) + "\n"


def cmd_changes(src: str, dst: str) -> int:
    names = changed_tests(json.loads(Path(src).read_text()))
    Path(dst).write_text("".join(n + "\n" for n in names))
    print(f"{len(names)} screen(s) differ from the base" + (": " + ", ".join(names) if names else ""))
    return 0


def cmd_find_run() -> int:
    env = os.environ
    repo, token, sha, self_id = env["REPO"], env["GH_TOKEN"], env["HEAD_SHA"], int(env["RUN_ID"])
    start = time.time()
    deadline = start + int(env.get("RECHECK_TIMEOUT_S", "3900"))
    wid = _api(f"repos/{repo}/actions/runs/{self_id}", token)["workflow_id"]
    q = urllib.parse.urlencode({"head_sha": sha, "event": "pull_request", "per_page": 100})

    def jobs_of(run_id: int) -> list[dict]:
        return _api(f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100", token)["jobs"]

    while True:
        run = pick_full_run(_api(f"repos/{repo}/actions/workflows/{wid}/runs?{q}", token)["workflow_runs"],
                            self_id, jobs_of)
        if run == "unknown":  # a newer run is still queued; wait until its jobs say what it is
            if time.time() > deadline:
                print("::error::a newer ui-quality run never started")
                return 1
            time.sleep(20)
            continue
        if run is None:
            # A PR opened with a label sends `opened` and `labeled` together; the full run may appear a moment later.
            if time.time() < start + 180:
                time.sleep(20)
                continue
            print(f"::error::no full ui-quality run for {sha}; push again or re-run the workflow")
            return 1
        if run["status"] == "completed":
            break
        if time.time() > deadline:
            print(f"::error::run {run['id']} did not finish in time")
            return 1
        print(f"waiting for run {run['id']} ({run['status']})")
        time.sleep(30)
    jobs = jobs_of(run["id"])
    problems = full_run_problems(jobs)
    if problems:
        print(f"::error::run {run['id']} did not pass its builds, axe or flows: {', '.join(problems)} "
              f"({run.get('html_url', '')}). The label changes nothing until they pass.")
        return 1
    print(f"re-using the screenshots of run {run['id']} ({run.get('html_url', '')})")
    with open(env["GITHUB_OUTPUT"], "a") as fh:
        fh.write(f"run_id={run['id']}\n")
    return 0


def cmd_verdict(root: str) -> int:
    env = os.environ
    changes = read_changes(Path(root))
    # The labels now, not at event time, and only if added after the newest commit (label_is_current).
    timeline = _api_list(f"repos/{env['REPO']}/issues/{int(env['PR'])}/timeline", env["GH_TOKEN"])
    ok, summary = decide(changes, *label_is_current(timeline))
    print(summary)
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(summary)
    if not ok:
        print(f"::error::screens differ from main; review the diff report, then add the {LABEL} label")
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["changes"] and len(argv) == 3:
        return cmd_changes(argv[1], argv[2])
    if argv == ["find-run"]:
        return cmd_find_run()
    if argv[:1] == ["verdict"] and len(argv) == 2:
        return cmd_verdict(argv[1])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
