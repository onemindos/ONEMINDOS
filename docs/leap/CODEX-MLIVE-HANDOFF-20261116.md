<!-- SPDX-License-Identifier: Apache-2.0 -->
# Codex M-LIVE continuation checkpoint — 2026-11-16

Owner-requested preservation for [#276](https://github.com/onemindos/ONEMINDOS/issues/276),
not a new feature claim, approval or readiness change. Ties to M-LIVE, CI-04,
CORE-SEC-9 (#160), AIG-01 (#165), APPS-01 (#173) and dashboard #141.
Locked D-001–D-014 stand; AI never actuates without human approval.

Read `AGENTS.md`, `docs/leap/AGENT-QUEUE.md`, `docs/DECISIONS.md`, then the
**current** #276 body AND comments before resuming. Later #276 comments supersede
its older lane table: #251, #239, #232, #146 and #206 moved to the DO seat.
This handoff neither claims them nor changes issue/PR labels. No issue is closed.

## Durable source and evidence

[The JSON ledger](codex-mlive-handoff-20261116.json) pins source heads, merged
commits, branch availability, current PR labels, and public check URLs. Its CI
observations are a point-in-time read, not a promise about the next run. PR
comments hold signed-off source and retained execution evidence. Historical
local PASS is **not** current CI PASS, Opus approval, merge, deployment or full
parent-issue completion. This preservation PR runs only documentation checks;
it does not re-execute the retained feature suites or build images.

From a clone, these commands create a new isolated diagnostic checkout without
switching or editing anyone else's worktree (choose an unused relative directory):

```sh
git fetch origin
# Example: Backups. Substitute the ledger branch and exact head for another slice.
git fetch origin refs/heads/feat/141-backups-dashboard
git worktree add --detach ../mlive-backups-checkpoint 58126d2b2fab3c97b59a6af48a81140c7ba152fc
git -C ../mlive-backups-checkpoint rev-parse HEAD
# If a named source branch is later removed, fetch its preserved PR head instead:
git fetch origin refs/pull/280/head
git worktree add --detach ../mlive-backups-pr FETCH_HEAD
```

Check fetched SHA against the ledger before trusting it. For merged slices,
fetch main and detach at the pinned source head (not the merge commit) to replay
source evidence. Retained baseline-only local branch names may not exist remotely;
the ledger marks them explicitly and their commits are already ancestors of main
or an existing source branch. Do not invent a remote branch or treat a baseline
name such as `feat/159-agent-kill-switch` as a built feature.

For actual continuation, check current ownership/file reservations, then create
one issue worktree. Integrate main via **normal merge**, never rebase/force-push.
Never export `GIT_DIR`/`GIT_WORK_TREE` or change shared Git config. Use `git -C`.
The original #160 checkout contains unrelated historical contamination from a
shared worktree redirect; do not stage, clean, reset or delete that dirt or its
backup. Recover #288 from its public head/clean recovery instead. Other local
commit/dirt auditing is separate; this is not certification of every foreign file.

## What to continue, in dependency order

- **#280 Backups / #141:** open, `review:changes`. Final independent source/evidence
  precheck PASS at the ledger head: one-line `applied.current = seq` failure fence
  in `dashboard/src/lib/hooks.ts` plus actual deferred-reordering Backups regressions.
  Retained evidence: 132 dashboard, 12 focused and 230 root tests, lint, typecheck,
  build, hygiene and scans. The normal #270 integration and dashboard image-target /
  installer-relative packaging builds are historical; **no fresh container build**
  for the last correction. Current merge-gate is red; inspect its exact public job,
  do not call this merge-ready. The old comment saying four slots are full is stale:
  #310 and #311 merged. Re-read capacity and obtain gate action; no relabel here.
- **#282 Storage / #141:** unchanged, `review:changes`. **Wait for actual #280 merge**,
  then normal `git merge origin/main`, inspect that the duplicate hook hunk drops
  out, rerun dashboard/root checks and packaging/CI, and batch one push. Old image
  failures include missing `@onemind/sdk`; #270 is merged, but do not copy its fix
  or skip the #280 dependency. Automation, Files, Network and other #141 acceptance
  remain outside these two slices; see current issue/ownership before starting.
- **#288 headers / #160:** open `needs-review`, header-only source. Its unchanged
  exact-head checks currently contain no failures/pending jobs. Read the full
  current rollup before handback; this is not approval. Does not deliver body limits.
- **#312 body limits / #160:** **draft, failing**, not accepted. Existing oracle
  `tests/security/test_injection_traversal.py::test_oversized_chunked_bodies_are_413`
  expects 413 but gets 412 on `PATCH /v1/files/uploads/upl_0123456789abcdef`.
  Public [core job](https://github.com/onemindos/ONEMINDOS/actions/runs/43764182072/job/132965466740):
  1 failed, 4226 passed, 599 skipped, 57 xfailed. Receive-only counting misses routes
  responding before reading. Retained ASGI diagnostic: 81 routes, 26 non-413 with
  zero reads, 10 successes including mutations. ASGI scope is **not wire HTTP/2 proof**.
  A reproducible diagnostic uses the exact head, over-cap framed/chunked request,
  real route and receive-call counter; contrast the pre-change framed cap. Do not
  weaken the oracle to accept 412/2xx. Claude/security owner must resolve universal
  413-before-action versus explicitly approved equivalent ingress guarantees on #276.
  Preserve 256 KiB **per PATCH**, route-owned photo timeout, disconnect/resume tests;
  require byte/time/concurrency/backpressure/disconnect proof. Photo/full-core final
  acceptance is not established. No eager-buffering contract change authorized here.
- **#290 MCP catalog / #165:** open `needs-review`, partial. Retained exact-head
  six-file run: 116 passed (three dependency warnings); attempted deselections
  excluded nothing, so it was not a proven safe partition. Current checks contain
  no failures/pending jobs, not gate approval. **#310 agent REST boundary is merged**,
  not a completed provider/model-data policy. Preserve owner display, trusted-manifest
  policy and default restrictions; broader model/provider-data acceptance remains #165.
- **#291 / #159:** merged audit-output honesty only. Global agent revocation still
  spans static tokens, identity tokens, app-agent ledger and proxy auth. An identity-only
  switch is not global. Security-owner reservation/decision on #276 is required;
  signed checkpoints/key lifecycle also remain. Never touch production keys/grants.
- **#289 / #117:** merged honest app-gate diagnostics, not every app repaired or full
  amd64/arm64 acceptance. Missing exit status cannot become PASS. Replay real public
  artifacts referenced in that PR; inspect latest attempts rather than old summaries.
- **#311 / #173:** merged malformed SPDX-expression fix, not the entire licence-class
  issue. Preserve fail-closed WITH parsing; review remaining parent acceptance.
- **#147:** upstream vulnerability block remains; no passing replacement and no local
  source changes. Do not unblock apps or rerun expensive known-red gates as a substitute
  for fixed, pinned images and real per-architecture scan evidence.
- **#262 / #230 and #270 / #138:** merged. Keep Mac isolated-environment setup and
  SDK packaging/visual-baseline fixes. Neither merge proves full M-LIVE readiness.

## Archived original #165 diagnostic — not an accepted test

[`test_ai_policy_boundary.py.snapshot`](archive/codex-mlive-20261116/test_ai_policy_boundary.py.snapshot)
is the byte-exact, previously uncommitted original diagnostic. The ledger records
its SHA-256, byte and line counts. It is **obsolete/unaccepted**, not run by this
handoff and not claimed passing. `.snapshot` under `docs/leap/archive/` is outside
active pytest discovery; do not rename or automatically execute it.

It imports `conftest`, `yaml` and the gateway and computes the manifest schema
relative to the original `core/tests/test_ai_policy_boundary.py` layout. The
archived location breaks that layout by design. Only after checking #165 ownership,
current accepted #290/#310 coverage and any overlapping reservations may a future
owner copy it back to that original repo-relative location, inspect/update its
assumptions and run the relevant RED/GREEN tests. Never overwrite an existing test.
The original source is retained untouched. Archiving adds no runtime behavior.

## Verification of this handoff

Validate JSON parsing, unique PRs/branches, full-length SHAs, repo-relative snapshot
paths and checksum, Markdown relative links and the archived test's non-discovery.
Run `make lint`, `python3 -I scripts/changes.py check`,
`python3 -I scripts/hygiene.py`, `gitleaks detect --no-banner --redact` for candidate
history and `gitleaks dir --no-banner --redact .` for current files, plus
`git diff --check`. Exact executions/exits are in the preservation PR, not implied
feature acceptance. No install, ignore-list changes, merge or queue action is needed.
