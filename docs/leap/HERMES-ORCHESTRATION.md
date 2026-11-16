<!-- SPDX-License-Identifier: Apache-2.0 -->
# The leap: Hermes orchestrates, GitHub Projects tracks, the Opus gate merges

**Date:** 2026-11-16 · **Requested by:** the founder ("lets take the leap but we need to do this properly").
**Ties to:** M-LIVE (GitHub milestone #1: OneMind running live), the agent protocol in [AGENT-QUEUE.md](AGENT-QUEUE.md), and CI-04 (#229). It changes no decision in [`docs/DECISIONS.md`](../DECISIONS.md). AI still never actuates without human approval, and nothing merges without a gate approval.

> ### In plain words
> Until now, the Opus gate session coordinated by hand: it handed issues to builders, reviewed their PRs and fed the merge queue. That one session is the bottleneck. From here on, **Hermes** (running on the founder's Mac) runs the loop. It picks ready issues, starts a coding agent for each one (Claude Code, Codex or a DigitalOcean model), and hands the finished PRs to the **Opus gate** for review. **GitHub Projects** is the screen where Zeus watches it all live. Linear can replace the board later, and the labels below map onto Linear one for one.

## 1. Is GitHub Projects enough? Yes, for this leap

- **It is already wired up.** Issues, PRs, labels, milestones, the merge queue and CI all live on GitHub. Linear would add a sync layer before it adds any value.
- **Labels are the machine interface; the board is the human view.** Agents read and write labels (`agent-ready`, `claimed`, `owner:*`, `area:*`, `wave:*`). Board fields (`Status`, `Horizon`, `Lane`) are derived from those labels by a sync script, so the two never disagree.
- **One board to watch: [OneMind OS Roadmap](https://github.com/orgs/onemindos/projects/2)**, filtered to `milestone:"M-LIVE: OneMind running live"` and grouped by `Status`. The 13 pillar boards (projects 3 to 15) stay as they are.
- **When to move to Linear:** when more than one human plans work, or when cycles and estimates matter. Not before M-LIVE.

## 2. The roles

| Role | Who | Model | Does | Never does |
|---|---|---|---|---|
| **Orchestrator** | Hermes, as a meta agent on the Mac (`~/.local/bin/hermes`, not the cluster function) | **Kimi K2.6** (DigitalOcean serverless), with GLM 5.3 as fallback | Picks issues, claims them, starts workers, watches their PRs, syncs the board, re-runs flaky CI once, escalates | Writes product code, approves or merges PRs, edits founder decisions |
| **Builders** | `claude -p` (Claude Code), `codex exec` (Codex), Hermes profiles `do-deepseek` / `do-glm` | Claude Sonnet 5.5 for `owner:claude`; Codex for `owner:codex`; **DeepSeek V4.1 Flash** for `owner:do` | One issue → one branch → one PR, with tests and DCO sign-off | Touch an `area:` another builder holds; force-push; edit `docs/`, `CHANGELOG.md`, `STATUS.md` |
| **Gate** | One Claude Code session on Opus 5.5 | Opus 5.5 | Reviews every PR (Done-when boxes, tests, the full core suite for `core/` changes), posts `review: approve` or `review: changes needed`, feeds the merge queue | Builds features in the loop's areas while it is gating |
| **Founder** | Zeus | | Decisions (`owner:founder`), keys, hardware, merges of anything marked `needs-founder` | |

### Why Kimi K2.6 for orchestration
- **Orchestration is little text and a lot of judgment.** It means a few hundred decisions a day ("is this issue ready?", "does this PR's area clash with a claim?", "is this CI failure a flake?"). Speed and cost per token matter little here. Reliable tool calls and long-context reasoning matter a lot. Kimi K2.6 is built for long agent runs with many tool calls.
- **It was slow at coding** (29 to 206 s per task in our bake-off), which is why it is **not** a builder. One decision every few minutes hides that slowness.
- **UNVERIFIED for this job.** Our bake-off (2026-11-16) scored coding and one tool call, not orchestration. The first step in §5 is a 30-minute orchestration trial of Kimi K2.6 against GLM 5.3 on 10 real issues. Keep whichever routes more of them correctly.
- **Why not DeepSeek V4.1 Flash as orchestrator?** It is the best *coder* we tested (9/9, 1 to 10 s, about $0.004 a round), so it goes where volume is, building. Routing errors cost more than routing tokens.
- **Why not Opus as orchestrator?** Opus is the scarcest seat. It earns most as the gate, where one missed bug costs a day. The gate stays on Opus.

## 3. The loop Hermes runs (every 5 minutes)

1. **Pick.** Open issues in milestone M-LIVE with `agent-ready`, without `claimed`, `parked`, `blocked:dep`, `blocked:upstream`, `needs-founder` or `needs-hardware`. Lowest `wave:` first, then lowest issue number.
2. **No-clash check.** Skip an issue if any `claimed` issue shares an `area:` label with it (AGENT-QUEUE.md §1).
3. **Route by owner label.** `owner:claude` → Claude Code; `owner:codex` → Codex; `owner:do` / `seat:do` → DeepSeek V4.1 Flash, and GLM 5.3 on a second failed attempt.
4. **Claim.** Add `claimed`, and comment `claimed by <seat> on branch <branch>`.
5. **Start the worker** in its **own git worktree** (`git worktree add …/wt-<issue> -b <type>/<issue>-<slug> origin/main`). Give it the issue body, the Agent brief comment, AGENT-QUEUE.md §4 (definition of done), and the rule to run `scripts/git-guard.sh` before every commit.
6. **Watch.** When the PR opens, add `needs-review` and move the item to *In Progress*. If no PR appears within 3 hours, or the worker stops, release the claim with a comment saying why.
7. **Hand to the gate.** Post the PR number into the gate's queue file (`docs/leap/dev/gate-queue.txt` locally, not committed) or message the gate session.
8. **Flakes.** If only `merge-gate` timed out, or a known flake failed (#324 TD3, a network 503), re-run it **once**. Anything else goes back to the builder.
9. **Sync the board** (the `proj_status` logic: closed → Done; claimed or has an open PR → In Progress; else Todo).

**Concurrency:** at most **7 builders** at once (Hermes' `max_concurrent_children`), and at most **1 per `area:`**. The gate reviews in the order PRs turn green.

## 4. Guard rails (unchanged, now enforced by the orchestrator)
- Nothing merges without `review: approve` from the gate. Hermes never runs `gh pr merge`.
- No force-push without the founder's explicit word. No edits to `docs/` or `context/` except founder-requested ones.
- One issue per PR, tests in the same PR, about 600 changed lines unless labelled `large`, plus one `changes/<branch>.md` fragment.
- Before every commit, check that `git rev-parse --show-toplevel` is the worker's own worktree (the shared `core.worktree` hazard; `scripts/git-guard.sh`).
- Secrets live in local `~/.hermes/.env` only. The DigitalOcean key is rotated after the sprint.

## 5. Start-up steps (founder runs these in a fresh chat)
1. **Trial the orchestrator (30 min).** Give Kimi K2.6 and GLM 5.3 the same 10 open M-LIVE issues and ask each for: pick-or-skip, owner seat, area clash, and a one-line reason. Compare against the labels. Keep the better one as Hermes' orchestrator profile.
2. **Dry run.** One loop pass with workers disabled. Hermes prints what it *would* claim and start. Check it against the board.
3. **Pilot.** Two workers (one `owner:do`, one `owner:claude`) on two `area:`-disjoint issues. The gate reviews both PRs.
4. **Scale.** Raise to 7 builders once both pilot PRs pass review without a second round.
5. **Watch** project 2 filtered to M-LIVE. Expect PRs to turn up within 1 to 3 hours of a claim.

## 6. Kickoff prompt for the new chat (Hermes orchestrator)

```
You are the OneMind OS orchestrator, running in local Hermes on the founder's Mac (never the
cluster). Repo: github.com/onemindos/ONEMINDOS. Read, in order: CLAUDE.md,
docs/leap/AGENT-QUEUE.md, docs/leap/HERMES-ORCHESTRATION.md.

Goal: milestone "M-LIVE: OneMind running live". Run the loop in §3 of HERMES-ORCHESTRATION.md
every 5 minutes. Route owner:claude to `claude -p` (Sonnet), owner:codex to `codex exec`,
owner:do to the do-deepseek profile. Each worker gets its own git worktree off origin/main.

Hard rules: you never write product code, never approve or merge a PR, never force-push,
never start parked / needs-founder / needs-hardware issues, and never let two workers hold
the same area: label. Re-run a failed CI job at most once, and only for a merge-gate timeout or
a known flake. Every PR goes to the Opus gate for review.

Start with §5 step 1 (orchestrator trial), then step 2 (dry run), and report to Zeus before
starting any worker. Give times in New York time (ET).
```
