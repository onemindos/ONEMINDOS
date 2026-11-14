<!-- SPDX-License-Identifier: Apache-2.0 -->
# Agent work queue: how coding agents pick, build and hand in work

**Date:** 2026-11-14 · **Requested by:** the founder, before the big parallel build with Codex, GPT and a second Claude account.
**Ties to:** CI-04 ([#229](https://github.com/onemindos/ONEMINDOS/issues/229), engineering guide for agents) and the roadmap boards in [`docs/strategy/roadmap-pillars.md`](../strategy/roadmap-pillars.md). Changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md).

> ### In plain words
> Every open issue now carries labels that say **who** builds it, **when**, **which part of the code** it touches, and **whether it can start**. An agent reads the labels, claims one issue, builds it on its own branch, proves it with tests, and opens a PR. Opus reviews every PR before it joins the merge queue. Two agents never work on the same part of the code at once, which is how we avoid merge fights and "AI slop".

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
5. **Prove it** (see §4), then open the PR with `Closes #<n>` and the template sections *Why / What / Tests / Not done*.
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

## 5. Review before merge

Every PR gets an **Opus review** before it joins the merge queue: does it tick each *Done when* box, does every claim in the PR text match the diff, are the tests real (not asserting the mock), does it break a locked decision, does it overlap a claimed issue. The reviewer comments `review: approve` or a list of fixes. Only after `review: approve` and green CI does anyone run `gh pr merge <n> --auto`. Until CI-02 (#227) makes the image battery a required check, the reviewer also confirms the `battery` jobs are green by hand.

## 6. The waves today

- **Wave 0, stabilise (do first, mostly Claude):** #226 the red image tests (PR #225 is in the merge queue and fixes TD1), #227 required checks (Zeus flips the setting), #228 faster core CI, #229 this guide plus a PR template and CODEOWNERS, #230 the Mac dev loop, #231 fewer shared-file conflicts, #232 a true STATUS.md.
- **Wave 1, make what exists real:** #141 dashboard pages on real data, #138 app lifecycle buttons, #147 and #117 unblock the 40 blocked apps, #233 one API client, #142 updates screen, #146 system controls, #139 apps at their own URL, #160 security headers, #175 manifest freeze, #173 licence classes, #159 audit verify, #165 aiPolicy, #234 the "see OneMind" guide.
- **Wave 2, fill the gaps:** file shares, single sign-on, share links, own domain, network screen, model manager, snapshots, cameras, offline library, families, the plugin manifest and registry, and the rest labelled `wave:2`.
- **Wave 3, later:** plugin publishing pipeline, leaf mode, fleet, voice, energy and Matter, try-it demo.
- **Founder queue (`owner:founder`):** the signing ceremony #153, the hardware order #214 (Pi soak by 2026-12-11), the domain #210, company setup #213, VMs / web terminal / Tor #253, and the decisions named on the `needs-founder` issues.
- **Parked:** every robotics, drone, TAK and WebXR-robot issue (#188–#194, #198, #209) and the draft PR #221.

## 7. The prompt to give a coding agent (Codex / GPT)

Paste this as the agent's task. Replace `<AGENT NAME>` with a short name like `codex-1`, so two agents' claims can be told apart.

```text
You are <AGENT NAME>, a coding agent on OneMind OS, a public Apache-2.0 repo at
github.com/onemindos/ONEMINDOS. OneMind OS is a home/edge operating system on
Debian 13 with a read-only image, RAUC A/B updates with health-gated rollback,
k3s, NATS, a FastAPI capability gateway (core/), a Go daemon (cmd/, internal/),
a web dashboard (dashboard/, ui/), and mobile/desktop clients.

First read, in this order: AGENTS.md, docs/leap/AGENT-QUEUE.md (the rules you
must follow), docs/DECISIONS.md (locked decisions you must not reopen).

Your job: take ONE issue at a time from the queue and ship it as a reviewed PR.

1. Find work:
   gh issue list -R onemindos/ONEMINDOS -l owner:codex -l agent-ready \
     --search "-label:claimed sort:created-asc" --limit 50
   Take the lowest wave:N that still has items. Skip any issue whose area:
   labels overlap an issue another agent has claimed
   (gh issue list -R onemindos/ONEMINDOS -l claimed).
   Never take issues labelled parked, needs-founder, needs-hardware,
   blocked:dep or owner:founder. No robotics work at all.
2. Claim it: comment "claim: <AGENT NAME>, branch <branch>" and add the
   claimed label.
3. Read the issue body and its "Agent brief" comment. Check main first: if part
   is already built, build only what is missing; if all of it is, comment the
   evidence and pick another issue.
4. Branch from fresh origin/main. Build the smallest change that ticks every box
   in the issue's "Done when" list. Keep each PR under about 600 changed lines;
   split bigger work into several PRs.
5. Definition of done, all required:
   - real data through the gateway; no mock, sample or placeholder data on any
     screen a user can reach (fixtures only inside tests)
   - reachable from a route, a dashboard screen or the onemind CLI
   - a test that fails without your change; every touched area's suite passes
   - make lint, the touched areas' tests, python3 scripts/changes.py check,
     python3 scripts/hygiene.py and gitleaks detect pass locally
   - a changes/<branch-with-dashes>.md fragment; never edit CHANGELOG.md or
     docs/leap/STATUS.md
   - every commit signed off with git commit -s
   - no secrets, private IPs, personal data or local paths; no code copied from
     umbrelOS or Olares
   - AI never actuates anything without human approval
6. Open the PR: title "<type>(<area>): <what>", body sections Why / What /
   Tests (the exact commands you ran and their result) / Not done, and
   "Closes #<n>". Do not merge it yourself: it waits for an Opus review.
7. If you are blocked, or the issue seems to need a founder decision or to break
   a locked decision, stop, comment on the issue what you found with file and
   line references, remove claimed, and take another issue.
8. Never force-push to someone else's branch, never push to main, never change
   repo settings, never close issues you did not finish.

Report at the end: the PR link, which Done-when boxes you ticked, the tests you
ran, and anything left undone.
```

## 8. The prompt for the Opus reviewer

```text
Review PR #<n> on onemindos/ONEMINDOS against docs/leap/AGENT-QUEUE.md §4 and
the linked issue's "Done when" list. Check out the branch and run the tests for
the areas it touches. Report: each Done-when box (met / not met, with evidence),
any claim in the PR text the diff does not support, tests that only test mocks,
mock or placeholder data reachable by a user, any locked decision it breaks,
security problems, and overlap with other claimed issues. End with exactly
"review: approve" or "review: changes needed" and the list of fixes. Post it as
a PR comment. Do not merge.
```

## 9. Words used

- **Merge queue:** GitHub tests each PR on top of the latest `main` before merging, one after another, so `main` stays green.
- **DCO sign-off:** a `Signed-off-by:` line on each commit saying you have the right to contribute it.
- **Battery:** the boot tests that start the real OS image in a virtual machine (QEMU) and check it boots, updates and rolls back.
- **Mock data:** made-up data that looks real. Fine inside a test, never on a screen a user sees.
