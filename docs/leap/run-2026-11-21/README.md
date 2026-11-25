<!-- SPDX-License-Identifier: Apache-2.0 -->
# The hardware-ready sprint (2026-11-21): record of the run

**Requested by:** the founder, 2026-11-21 ("keep track and update the repo so we can keep track of this run and work as well").
**Builds on:** [run-2026-11-19](../run-2026-11-19/README.md) (the leap run), [AGENT-QUEUE.md](../AGENT-QUEUE.md) and the 180-day plan. Changes no decision in [`docs/DECISIONS.md`](../../DECISIONS.md).
**Goal:** reach gate **G1 on 2026-12-13**, the first gate on real hardware, with a tested image, a lab cycle behind it and no open security blockers.

> ### In plain words
> A sprint is a short, fixed push. This one has one aim: get OneMind OS ready to run on real machines. First we unblock the pipeline (S0). Then we close the pile of open PRs (S1). Then we build the missing pieces in waves (S2), test them together on the lab server (S3), and move to real hardware at G1 (S4).
> This folder is the written record. Each wave has a file in [progress/](progress/) with the PRs, what review said, what the lab and security checks found, and what is still open. Anything still running says **in progress** so a later update can fill it in.

## The five phases

| Phase | Dates | What happens |
|---|---|---|
| **S0 Unblock** | 11-21 to 11-22 | Restart the automation, land the lab-server build runner, fix the red CI on main, pass gate G0 (due 11-22). |
| **S1 Close out** | 11-23 to 11-27 | Take the open PRs from 55 to under 10. No new features. |
| **S2 Build** | 11-28 to 12-10 | The waves below, grouped by the nine OS parts. |
| **S3 Integrate and lab test** | 12-08 to 12-13 | Full battery on the lab server, acceptance tests, a restore drill, a signed release. |
| **S4 Real hardware** | from 12-13 (G1) | Mini PC, laptop and Pi 5 kits. RAUC rollback 10 of 10 and power pulls 20 of 20. |

In practice the early waves already ran on 2026-11-21 (see the table below), so S1 and S2 overlap.

## The nine parts

The founder groups the work in nine parts. Every wave maps to them.

1. **Plugin platform:** sockets E1 to E10, signed install, grants, revocation.
2. **Apps and marketplace:** the Market, the app gate, tiers, rescans.
3. **Core features:** gateway, identity, backup, family, approvals.
4. **Real hardware:** lab kits for the mini PC, laptop, Pi 5 and the power-pull harness.
5. **OS and image:** the read-only image, RAUC, boot tests, updates.
6. **Founder:** decisions and hardware only the founder can do.
7. **AI features:** agent principals, budgets, the tainted-input rule, MCP.
8. **Networking:** fabric, domains, Tor, firewall and exposure.
9. **Clients, site, docs and CI:** dashboard, phone app, desktop app, release lanes, pipeline.

## Waves and where each is recorded

| Wave | File | State |
|---|---|---|
| Wave 1: close-out and core builds | [wave-1-closeout.md](progress/wave-1-closeout.md) | done, merge decisions pending |
| Wave 2: network, AI, clients, OS | [wave-2-build.md](progress/wave-2-build.md) | done, in review |
| Wave 3: kits, lab cycle, security re-review | [wave-3-kits-lab-security.md](progress/wave-3-kits-lab-security.md) | done, fixes in progress |
| Clients wave | [clients-wave.md](progress/clients-wave.md) | done, in review |
| UI and experience review | [ui-experience-review.md](progress/ui-experience-review.md) | done, issues to file |
| Beyond-umbrelOS benchmark | [beyond-umbrelos.md](progress/beyond-umbrelos.md) | done, issues to file |
| Front door (D-018) | [front-door.md](progress/front-door.md) | spec done, founder decision pending |
| Cluster replacement | [cluster-replacement.md](progress/cluster-replacement.md) | plan done, founder answers pending |
| Wave 4: must-fix | [wave-4-must-fix.md](progress/wave-4-must-fix.md) | in progress |

## How the automation works

- **Merge train.** One gate session is the only one that merges. It lands approved PRs one at a time through the merge queue, refreshes branches that fall behind main and re-runs flaky jobs. Builders push drafts and never merge.
- **Ready-feeder.** Drafts run only the cheap CI. A PR is marked ready one or two at a time, because the Free GitHub plan gives about 20 CI jobs at once.
- **Integration branch.** A throwaway branch that merges every open PR together, test only, never merged. It shows conflicts between PRs early. The first one went stale on 11-20 and a fresh one replaces it.
- **Tracker.** Gate board [#276](https://github.com/onemindos/ONEMINDOS/issues/276) lists every PR with its state and its next step.
- **The lab server and `om-remote`.** A 16-core build machine in the lab. `om-remote <worktree> '<command>'` copies a worktree there and runs heavy checks (Go, Node, Python, Docker). Its Python `cryptography` is version 41, like GitHub's hosted runners, which is how the old-cryptography unit failures were caught.
- **Merge-queue pool.** The lab server also runs a pool of KVM job VMs for the image, smoke, battery and installer jobs (PRs [#424](https://github.com/onemindos/ONEMINDOS/pull/424) and [#470](https://github.com/onemindos/ONEMINDOS/pull/470)). The QEMU battery and the full app gate still run in CI only.
- **Builder rules** (from AGENT-QUEUE section 4): real data only, tests that fail without the change, reachable from a route, screen or the CLI, one change fragment per PR, `Refs #N` never `Closes`, push once when the work is done. Review uses a separate agent. Security PRs get an independent Opus review.

## Verdict words used in these files

- **APPROVE:** reviewer found no blocker.
- **CHANGES:** reviewer found at least one blocker. The fix round follows.
- **Verified / refuted:** for security findings, a second agent tried to reproduce each one. "Refuted" means it could not be exploited on main, so the severity was lowered (the finding may still be a design note).

## Where the sources are

The raw agent outputs are kept privately by the founder. These files hold the public, sanitised result. PR numbers were checked against GitHub on 2026-11-21.
