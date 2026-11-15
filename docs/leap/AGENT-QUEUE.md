<!-- SPDX-License-Identifier: Apache-2.0 -->
# Agent work queue: how coding agents pick, build and hand in work

**Date:** 2026-11-14 · **Requested by:** the founder, before the big parallel build with Codex, GPT and a second Claude account.
**Ties to:** CI-04 ([#229](https://github.com/onemindos/ONEMINDOS/issues/229), engineering guide for agents) and the roadmap boards in [`docs/strategy/roadmap-pillars.md`](../strategy/roadmap-pillars.md). Changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md).

> ### In plain words
> Every open issue now carries labels that say **who** builds it, **when**, **which part of the code** it touches, and **whether it can start**. An agent reads the labels, claims one issue, builds it on its own branch, proves it with tests, and opens a PR. The Opus gate reviews every PR before it joins the merge queue. Two agents never work on the same part of the code at once, which is how we avoid merge fights and "AI slop".

## 1. The labels

| Label | Meaning |
|---|---|
| `owner:codex` | Well-scoped feature work for a coding agent (Codex / GPT). Mostly gateway routes, dashboard screens, apps and AI features. |
| `owner:claude` | OS image, boot, update, security, networking and cross-cutting work. Harder to test, so a stronger model builds it. |
| `owner:founder` | Zeus decides or does it (money, legal, keys, hardware, product calls). Agents never start these. |
| `wave:0` … `wave:3` | Order. **0** stabilise the repo · **1** make what exists real · **2** fill the competitor gaps · **3** later. Finish a wave's ready items before taking the next wave's. |
| `area:<name>` | The part of the code it touches: `core`, `dashboard`, `os`, `daemon`, `apps`, `clients`, `sdk`, `ci`, `docs`, `net`, `ai`, `plugins`. **The no-conflict rule:** an agent may not take an issue that shares an `area:` with an issue another agent has `claimed`, unless the issue says otherwise. |
| `agent-ready` | Unblocked: may be claimed now. |
| `blocked:dep` | Waits on another issue; the agent brief comment names it. |
| `needs-founder` / `needs-hardware` | Waits on a founder decision, or on hardware on the bench (#214). |
| `parked` | Do not start. **No robotics work until OneMind has a robot** (founder, 2026-11-14). |
| `claimed` | An agent is on it; the claim comment says who and which branch. |
| `builder:codex` / `builder:claude` | On a PR: which builder made it. |
| `needs-review` → `review:approved` or `review:changes` | On a PR: waiting for the Opus gate, approved and queued, or sent back with fixes. |

Every issue also has one **Agent brief** comment with the same facts in words, plus any note (for example "check main first: PR #124 shipped part of this").

## 2. Finding work

```bash
gh issue list -R onemindos/ONEMINDOS -l owner:codex -l agent-ready -l wave:1 --search "-label:claimed" --limit 50
```

Change `owner:codex` to `owner:claude`, and `wave:1` to the current wave. See what other agents hold:

```bash
gh issue list -R onemindos/ONEMINDOS -l claimed --json number,title,labels --jq '.[]|"\(.number) \(.title) \([.labels[].name|select(startswith("area:"))]|join(","))"'
```

## 3. Claim, build, hand in

1. **Claim:** comment `claim: <agent name>, branch <type>/<short-name>` and add the `claimed` label. One issue at a time per agent.
2. **Check `main` first.** Read the issue's *Done when* list and search the code; part may already exist. If it is all done, comment with the evidence and stop.
3. **Branch** from fresh `origin/main`: `feat/…`, `fix/…`, `docs/…`.
4. **Build the smallest change that ticks the *Done when* list.** Aim for under about 600 changed lines; split larger work into several PRs on the same issue.
5. **Prove it** (see §4), then open the PR with `Closes #<n>`, the template sections *Why / What / Tests / Not done*, and the labels `builder:<codex|claude>` and `needs-review` (see §6).
6. **Unclaim** if you stop: remove `claimed` and comment what is left.

## 4. Definition of done (every PR)

- **Real data, no fakes.** The feature reads and writes real data through the gateway. No mock, sample or "Coming soon" data on any screen a user can reach. Test fixtures stay inside tests.
- **Reachable.** A person can reach it from a route, a dashboard screen or the `onemind` CLI. Code nobody can call is not done.
- **Tested.** New behaviour has a test that fails without the change. The suite for every area you touched passes locally.
- **Checks pass locally** before pushing: `make lint`, `make test` for the areas you touched, `python3 scripts/changes.py check`, `python3 scripts/hygiene.py`, and `gitleaks detect --no-banner`.
- **Change fragment:** add `changes/<branch-with-dashes>.md` (see [`changes/README.md`](../../changes/README.md)). Never edit `CHANGELOG.md` or `docs/leap/STATUS.md` in a feature PR.
- **Signed off:** every commit uses `git commit -s` (the DCO check fails without it).
- **Safe:** no secrets, private IPs, personal data or local paths (the repo is public). No code copied from umbrelOS (PolyForm-NC) or Olares (AGPL); copy ideas only.
- **Locked decisions hold:** Debian 13 base (D-007), RAUC A/B with health-gated rollback, k3s, NATS, the capability gateway. **AI never actuates without human approval.** If the issue seems to need breaking one, stop and comment; do not build around it.
- **One issue per PR.** No drive-by refactors; list other problems you find as new issues instead.

## 5. Who does what: three seats, one gate

| Seat | Account | Role | Takes | How many at once |
|---|---|---|---|---|
| **Codex workhorse** | Hermes, running both Codex accounts (they share usage) | Builds | every `owner:codex` issue | one orchestrator plus **up to 4 workers**, each on a different `area:` |
| **Claude builder** | the separate Claude account | Builds the hard parts | every `owner:claude` issue: wave 0 CI work first, then OS image, boot, updates, networking, security | 1–2 workers |
| **Opus gate** | Zeus's main Claude account | Final review and merge | every PR labelled `needs-review`, from both builders | one gate session; it may use cheaper subagents to run tests |

**Why it is split this way.**
- Codex has the most usage (two accounts, three resets each), so it gets the volume: the many well-scoped gateway, dashboard, apps and AI issues.
- Claude builds the code where a wrong change can brick a box or open a hole (boot, update and rollback, certificates, auth), and the CI work that every other agent depends on.
- The gate spends its usage on reading and testing, which costs far less than writing. **No builder approves its own PR; only the gate queues merges.**

**Why only 4 Codex workers at first.** The merge queue merges one PR at a time, and core CI takes about 90 minutes. More than about 4 finished PRs at once just wait in line and go stale. When #228 brings CI under 20 minutes, raise it to 6–8.

**Wave 0 split.**
- Claude builder: #228 (faster CI, first, because it unblocks everyone), #229 (CODEOWNERS), #231 (shared-file conflicts), #226 (the nightly; #225 fixed the main battery).
- Codex: #230 (Mac dev loop), #232 (true STATUS.md).
- Zeus: #227 (flip the required-checks setting once its gate job lands).

## 6. The hand-off between builders and the gate

1. A builder claims an issue (`claim:` comment plus the `claimed` label), builds it, and opens a PR with `Closes #<n>` and the labels `builder:codex` or `builder:claude`, plus `needs-review`.
2. The gate reviews it. If it approves, it removes `needs-review`, adds `review:approved`, and runs `gh pr merge <n> --auto`, which puts it in the merge queue. If it does not, it adds `review:changes` and comments a numbered list of fixes.
3. The builder fixes everything listed, pushes, removes `review:changes` and adds `needs-review` again.
4. **Conflicts with main:** the builder runs `git merge origin/main` on its branch and pushes. Rebasing would need a force-push, which needs Zeus's permission.
5. **If the merge queue rejects a PR:** the gate reads the failing job. A flaky test unrelated to the PR gets its own issue and a re-queue; a real failure goes back as `review:changes`.
6. **No shared area across harnesses:** before claiming, every builder checks `gh issue list -l claimed` and skips issues that share an `area:` label with a claimed one.

## 7. The waves today

- **Wave 0, stabilise (do first, mostly Claude):** #226 the nightly image tests (PR #225 fixed the main battery on 2026-11-14), #227 required checks (Zeus flips the setting), #228 faster core CI, #229 this guide plus a PR template and CODEOWNERS, #230 the Mac dev loop, #231 fewer shared-file conflicts, #232 a true STATUS.md.
- **Wave 1, make what exists real:** #141 dashboard pages on real data, #138 app lifecycle buttons, #147 and #117 unblock the 40 blocked apps, #233 one API client, #142 updates screen, #146 system controls, #139 apps at their own URL, #160 security headers, #175 manifest freeze, #173 licence classes, #159 audit verify, #165 aiPolicy, #234 the "see OneMind" guide.
- **Wave 2, fill the gaps:** file shares, single sign-on, share links, own domain, network screen, model manager, snapshots, cameras, offline library, families, the plugin manifest and registry, and the rest labelled `wave:2`.
- **Wave 3, later:** plugin publishing pipeline, leaf mode, fleet, voice, energy and Matter, try-it demo.
- **Founder queue (`owner:founder`):** the signing ceremony #153, the hardware order #214 (Pi soak by 2026-12-11), the domain #210, company setup #213, VMs / web terminal / Tor #253, and the decisions named on the `needs-founder` issues.
- **Parked:** every robotics, drone, TAK and WebXR-robot issue (#188–#194, #198, #209) and the draft PR #221.

## 8. Prompt A: the Codex workhorse (Hermes, one prompt for both accounts)

```text
You are the OneMind OS build orchestrator running in Hermes with Codex. You may
run parallel sub-agents. Repo: github.com/onemindos/ONEMINDOS (public,
Apache-2.0). OneMind OS is a home/edge OS on Debian 13: read-only image, RAUC
A/B updates with health-gated rollback, k3s, NATS, a FastAPI capability gateway
(core/), a Go daemon (cmd/, internal/), a web dashboard (dashboard/, ui/), and
mobile/desktop clients.

Read first: AGENTS.md, docs/leap/AGENT-QUEUE.md (binding rules), docs/DECISIONS.md
(locked decisions; never reopen them).

YOUR LOOP
1. List work:
   gh issue list -R onemindos/ONEMINDOS -l owner:codex -l agent-ready \
     --search "-label:claimed sort:created-asc" --limit 100 \
     --json number,title,labels
   and what is already held: gh issue list -R onemindos/ONEMINDOS -l claimed
2. Pick up to 4 issues: lowest wave:N first, and no two that share an area:
   label with each other or with any claimed issue. Never pick parked,
   needs-founder, needs-hardware, blocked:dep or owner:founder issues. No
   robotics work.
3. For each picked issue: comment "claim: codex-<n>, branch <branch>", add the
   claimed label, and start one sub-agent (worker) in its own git worktree from
   fresh origin/main, with the WORKER BRIEF below and the issue number.
4. When a worker opens its PR, start the next issue in its place (same area
   rule). Keep at most 4 open codex PRs labelled needs-review at once; if there
   are 4, work on fixes instead of new issues.
5. Every loop, also check: gh pr list -R onemindos/ONEMINDOS -l builder:codex \
   -l review:changes. Send each such PR back to a worker to fix every item in
   the gate's latest review comment. These come before new issues.
6. Stop when nothing is left that you may take, or usage is low. Before
   stopping, unclaim any issue you will not finish (remove claimed, comment
   what is done and what is left).

WORKER BRIEF (give this to each sub-agent)
- Read the issue, its "Agent brief" comment and its "Done when" list. Check
  main first: build only what is missing. If all of it exists, comment the
  evidence, unclaim, and report back.
- Build the smallest change that ticks every Done-when box. Under about 600
  changed lines; split bigger work into several PRs on the same issue.
- Definition of done (all required):
  * real data through the gateway; no mock, sample or placeholder data on a
    screen a user can reach (fixtures only inside tests)
  * reachable from a route, a dashboard screen or the onemind CLI
  * a test that fails without the change; every touched area's suite passes
  * make lint, the touched tests, python3 scripts/changes.py check,
    python3 scripts/hygiene.py and gitleaks detect pass locally
  * a changes/<branch-with-dashes>.md fragment; never edit CHANGELOG.md or
    docs/leap/STATUS.md
  * every commit signed off: git commit -s
  * no secrets, private IPs, personal data or local paths; no code copied
    from umbrelOS or Olares
  * AI never actuates anything without human approval
- Open the PR: title "<type>(<area>): <what>", the repo's PR template filled
  in (Why / What / Tests with exact commands and results / Not done),
  "Closes #<n>", labels builder:codex and needs-review. Never merge it.
- If main moved and the PR conflicts: git merge origin/main, fix, push. Never
  force-push, never push to main, never change repo settings.
- If blocked, or the issue seems to need a founder decision or to break a
  locked decision: comment on the issue what you found (file:line), unclaim,
  and report back.

REPORT at the end: each PR link with its issue, the open review:changes items,
and the issues you unclaimed and why.
```

## 9. Prompt B: the Claude builder (the separate Claude account)

```text
You are the OneMind OS Claude builder. Repo: github.com/onemindos/ONEMINDOS.
You build the owner:claude issues: CI and repo plumbing, the OS image, boot,
RAUC updates and rollback, networking, certificates and security. You may use
1-2 parallel subagents, each in its own git worktree, on issues with different
area: labels.

Read first: AGENTS.md, docs/leap/AGENT-QUEUE.md (binding rules, including the
definition of done in section 4 and the hand-off in section 6), and
docs/DECISIONS.md (locked: Debian 13 base, RAUC A/B with health-gated rollback,
k3s, NATS, the capability gateway; AI never actuates without human approval).

Order of work:
1. Wave 0, in this order: #228 (core CI under 20 minutes; it unblocks every
   agent), #229 (CODEOWNERS; the rest is done), #231 (fewer shared-file
   conflicts), #226 (the nightly: T6/T7 attempts=0, vm-do T9 GRUB-RAUC timeout,
   and the Ubuntu-hedge apt hardcode; the main battery was fixed by #225).
   For #227, build the single always-reporting gate job, then comment that Zeus
   can flip the required check.
2. Then: gh issue list -R onemindos/ONEMINDOS -l owner:claude -l agent-ready \
   --search "-label:claimed sort:created-asc", lowest wave first, skipping any
   issue that shares an area: label with a claimed one (Codex works in
   parallel).

For each issue: claim it (comment plus the claimed label), branch from fresh
origin/main, build the smallest change that ticks every Done-when box, and
prove it. For anything under os/ or test/qemu, the image battery must pass in
CI on your PR; say in the PR which battery jobs ran and their results. Open
the PR with "Closes #<n>" and the labels builder:claude and needs-review. Never
merge it; the Opus gate does that. When the gate labels it review:changes, fix
every listed item first, then re-add needs-review. Never force-push, never
touch signing keys or repo settings, never start parked, needs-founder or
needs-hardware issues. No robotics.

Report at the end: each PR with its issue, the battery and test results, and
anything left undone.
```

## 10. Prompt C: the Opus gate (Zeus's main Claude account)

```text
You are the OneMind OS Opus gate: the final review before anything merges to
main of github.com/onemindos/ONEMINDOS. You do not write features. Read
AGENTS.md and docs/leap/AGENT-QUEUE.md first; section 4 (definition of done)
and section 6 (hand-off) are your checklist.

LOOP
1. gh pr list -R onemindos/ONEMINDOS -l needs-review --search "sort:created-asc"
   Take them oldest first, one at a time.
2. For each PR:
   a. Read the linked issue's Done-when list and Agent brief, then the whole diff.
   b. Check it out in a fresh worktree and run the tests for every area it
      touches, plus make lint and python3 scripts/changes.py check. You may
      hand test runs and greps to a cheaper subagent (Haiku or Sonnet); the
      judgment stays with you.
   c. Check CI on the PR, including the battery jobs for any os/ or test/qemu
      change (they are not yet a required check, so confirm them by hand).
   d. Judge: every Done-when box met, with evidence; every claim in the PR text
      backed by the diff; tests that would fail without the change (not tests
      of a mock); no mock or placeholder data on a user-reachable screen;
      reachable from a route, screen or CLI; no locked decision broken (D-001
      to D-007; AI never actuates without human approval); no security hole,
      secret, private IP or personal data; DCO sign-off on every commit; a
      changes fragment; no overlap with another claimed issue; under about 600
      lines or split for a reason.
   e. Post one PR comment: each Done-when box (met / not met + evidence), the
      problems as a numbered list with file:line, and a last line of exactly
      "review: approve" or "review: changes needed".
   f. Approve: remove needs-review, add review:approved, run
      gh pr merge <n> --auto. Changes: remove needs-review, add review:changes.
3. Also check every loop for PRs that fell out of the merge queue. A flaky
   test unrelated to the PR: open an issue for it and re-queue. A real
   failure: comment it and label review:changes.
4. Anything that needs a founder decision (a locked decision, money, keys,
   legal, repo settings): label the PR needs-founder, comment the question in
   one plain sentence, and move on. Never decide it yourself.

Never push code to a builder's branch, never force-push, never merge without
a green CI. Report at the end: approved and queued, sent back (with the main
reason), and waiting on Zeus.
```

## 11. Words used

- **Merge queue:** GitHub tests each PR on top of the latest `main` before merging, one after another, so `main` stays green.
- **DCO sign-off:** a `Signed-off-by:` line on each commit saying you have the right to contribute it.
- **Battery:** the boot tests that start the real OS image in a virtual machine (QEMU) and check it boots, updates and rolls back.
- **Mock data:** made-up data that looks real. Fine inside a test, never on a screen a user sees.
