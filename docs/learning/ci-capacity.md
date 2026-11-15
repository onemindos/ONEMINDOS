<!-- SPDX-License-Identifier: Apache-2.0 -->
# CI capacity: why CI queues, and what we changed (CI-09)

**Ties to:** issue [#298](https://github.com/onemindos/ONEMINDOS/issues/298) (CI-09), and [#299](https://github.com/onemindos/ONEMINDOS/issues/299) (CI-10, a local runner) which builds on it. Changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md).

## The short version
CI is the bottleneck for every wave. We used to start most of our 25 pull-request workflows on every push to every PR, drafts included, and never stopped the runs a newer push had made useless. Now a draft runs only four cheap checks, a new push cancels the old run, and the heavy jobs start when a PR is marked ready. Same safety on `main`, fewer wasted jobs.

## What a runner is, and why 20 is the limit
- A **job** is one box of steps in a workflow (for example "run the core tests").
- A **runner** is the machine that executes one job. GitHub lends us hosted runners; each job gets a fresh one and gives it back when it finishes.
- A **concurrency limit** is how many jobs may run at the same moment. The `onemindos` organisation is on GitHub Free: **20 jobs at once** for the whole org, per [GitHub's limits page](https://docs.github.com/en/actions/reference/limits). Job 21 waits in a queue. (GitHub Team would raise that to 60; that is the founder's call, not part of this change.)

On 2026-11-15 the gate measured 88 runs queued and 10 running; an approved PR waited 35+ minutes in the merge queue for a free runner. Six seats push PRs, and a PR can push many times before it is ready.

## What changed

| Change | What it saves |
|---|---|
| **Drafts run only the cheap checks:** `dco`, `hygiene`, `lint`, `unit` (plus the change-fragment check in `ci`). Every other job has `if: ${{ !github.event.pull_request.draft }}` and is skipped. A skipped job takes no runner. | Every push to a draft PR used to start every workflow whose paths matched: core tests, image build, QEMU battery, dashboard, mobile, e2e. Now four small jobs. |
| **`ready_for_review` starts the full set.** Each PR workflow listens to `opened`, `synchronize`, `reopened` and `ready_for_review`. | The heavy jobs run once when the PR is ready, not on every WIP push. |
| **A newer push cancels the older run of the same PR.** Every PR workflow has a `concurrency` group per PR with `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`. | A push 5 minutes after the last one no longer leaves a 60-minute image battery running for code that is already out of date. |
| **Nothing is cancelled on `main`, in the merge queue, nightly or by hand.** Those runs get a group of their own (their run id), and `cancel-in-progress` is false for them. | Before, `ci`, `e2e`, `api-fuzz`, `ci-mobile` and others shared one group per ref with cancel switched on for every event, so two quick merges to `main` could cancel the first one's checks. |

Numbers to hold us to (the issue asks for them over one working day): runs queued before and after. They are posted on [#298](https://github.com/onemindos/ONEMINDOS/issues/298).

## Why a skipped job is safe: how merge-gate works now
`merge-gate` ([`.github/workflows/gate.yml`](../../.github/workflows/gate.yml), [`scripts/ci-gate.py`](../../scripts/ci-gate.py)) is the one required check on `main`. It waits for every workflow GitHub started for the same commit and fails if one failed. A skipped run counts as passing, so two things must hold:

1. **A draft cannot merge.** GitHub does not let a draft PR into the merge queue. A green gate on a draft only means "the cheap checks passed".
2. **Marking ready starts a new gate that waits for the heavy workflows.** The gate also listens to `ready_for_review`. The old runs of the same commit, made while it was a draft, are ignored: the gate only counts runs created within five minutes before itself. Without that window a gate that looked a moment too early would see only the draft's "skipped" runs and pass before the heavy ones had started.

In the merge queue (`merge_group`), no job is a draft, so every job runs and the gate waits for all of it. Tests: `test/unit/test_ci_gate.py` (a ready PR waits for every workflow, old skipped runs do not count) and `test/unit/test_ci_draft_policy.py` (every PR workflow listens to `ready_for_review`, guards its heavy jobs and cancels only PR runs; a new workflow that forgets fails the unit job).

## For agents and people
- Open PRs as **draft** while you work; push as often as you like. Mark **ready** when the work is done.
- Do not open a PR ready and then keep pushing: each push restarts the full set (the older run is cancelled, but the new one costs the same).
- Writing a new PR workflow? Copy the pattern from `ci-sdk.yml`: `types` with `ready_for_review`, a `concurrency` block, and `if: ${{ !github.event.pull_request.draft }}` on every job that is not a cheap check. The policy test tells you if you missed one.
- `ci-core.yml` follows the same pattern in a follow-up commit once [#264](https://github.com/onemindos/ONEMINDOS/pull/264), which changes that file, has merged.
