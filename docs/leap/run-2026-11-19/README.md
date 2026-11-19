<!-- SPDX-License-Identifier: Apache-2.0 -->
# The leap run (from 2026-11-19): build a complete OneMind OS in one week

**Requested by:** the founder, 2026-11-19 ("I want a full and complete OS. M-LIVE is great but let's take the leap.")
**Builds on:** [AGENT-QUEUE.md](../AGENT-QUEUE.md) (labels, claims, definition of done) and [LANES.md](../LANES.md). Changes no decision in [`docs/DECISIONS.md`](../../DECISIONS.md).

> ### In plain words
> Two builders work at the same time on this Mac. **Claude finishes M-LIVE** (OneMind running live) **and runs every merge**. **Codex builds everything else** in five lanes: plugins, AI, core features, OS and network, and apps.
> Writing code is cheap; merging it safely is the slow part. So Codex writes **small draft PRs, pushed the same day**, in lanes that do not touch each other's files. Claude reviews them and lands them one lane at a time. Code that is written but not merged yet is not lost: it waits on its branch.

## Files in this folder

| File | What it holds |
|---|---|
| [LANES.md](LANES.md) | The six lanes, their issues in build order, and who owns each |
| [CODEX.md](CODEX.md) | The master prompt for Codex and one starter prompt per lane |
| [MERGE-GATE.md](MERGE-GATE.md) | How Claude lands PRs: the order, the checks, and the traps we hit on 2026-11-18 and how each is handled |

## Roles

| Who | Does | Does not |
|---|---|---|
| **Claude (Opus gate)** | Builds lane 1 (M-LIVE). Reviews every PR (an independent Opus review for security-relevant code). Keeps `main` green: merge queue, conflict refreshes, flaky re-runs, CI fixes. Writes Codex's next prompt as PRs land. | Build in a Codex lane. |
| **Codex (on this Mac)** | Builds lanes 2–6 in order, one small draft PR per issue slice, pushed the same day. Merges `main` into its branch before asking for review. | Merge to main. Work in lane 1. Touch Claude's worktrees or branches. |
| **Zeus** | Founder decisions and hardware: see the "Founder" list in [LANES.md](LANES.md). About 30 minutes this week unblocks several lanes. | — |

## Phases

1. **Day 1 (Claude): pipeline fixes.** These end the merge snowball before Codex's PRs arrive:
   - CI-13 on the Mac ([#360](https://github.com/onemindos/ONEMINDOS/pull/360)): merge-gates and light jobs run on the founder's Mac.
   - Stop committing generated SDK files; generate them in CI. They caused most of the conflicts on 2026-11-18.
   - Skip the 1–2 hour image and boot tests for PRs that do not touch the OS.
   - Refresh visual baselines automatically, so dashboard PRs stop breaking each other's screenshots.
   - Fix the flaky cloud boot test and [#324](https://github.com/onemindos/ONEMINDOS/issues/324).
2. **Days 1–7 (Codex): build lanes 2–6 in parallel,** at most one open PR per lane in review at a time and more as drafts. **Claude: build lane 1 and land everything.**
3. **End of the week:** every line Codex wrote is on GitHub, reviewed PRs are merged, and what remains is ordered for the next run.

## Rules that keep this from jamming (summary; details in [CODEX.md](CODEX.md) and [MERGE-GATE.md](MERGE-GATE.md))

- **One issue slice per PR,** under about 600 changed lines. The body says "Refs #N", never "Closes".
- **Lanes own areas.** Shared files (route policy `core/tests/sec_policy.py`, dashboard `App.tsx` and navigation, OpenAPI) take additive edits only.
- **Push every day.** Nothing lives only in a Codex session; when the usage ends, the code is already on GitHub.
- **Drafts first.** Drafts run only the cheap CI. Codex marks a PR ready with `needs-review` when its lane's previous PR has merged, at most one ready PR per lane.
- **Real data, tests, sign-off** (`git commit -s`), one `changes/` fragment per PR, no edits to `CHANGELOG.md` or `docs/leap/STATUS.md`. AI never actuates without owner approval.
- **Parked stays parked:** no robotics work.
