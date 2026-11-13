<!-- SPDX-License-Identifier: Apache-2.0 -->
# Continue here: finishing the started waves

**Written:** 2026-11-12, at a hand-off between sessions. **Plan:** [NEXT-WAVE.md](NEXT-WAVE.md) (merge ownership + Wave G) · **Board:** [STATUS.md](STATUS.md) · **Record:** [CHANGELOG.md](../../CHANGELOG.md)

> **Explain it like I am the founder**
> Every piece of work built so far is saved on GitHub: either merged, or an open PR, or a pushed branch. This page lists what is left to finish, sorted by effort, and the order to do it in. Quick wins first, then medium items one at a time, and the heavy items last.

## How to resume (any session)
1. `git fetch` and read this page, then [NEXT-WAVE.md](NEXT-WAVE.md).
2. Work **one item at a time**: merge `origin/main` into the branch, resolve conflicts keeping both sides' registrations and rows, run the full checks (core pytest on SQLite and PostgreSQL, `go vet` + `go test ./...`, ui/dashboard/mobile tests where touched, `sh scripts/lint.sh`, unit tests, `python3 -I scripts/hygiene.py`, gitleaks), push, open or update the PR, merge only when every check is green.
3. After each merge wait until GitHub shows the next PR's mergeable state (not `UNKNOWN`) before merging it.
4. Each merged item gets its CHANGELOG entry and STATUS row.
5. Rules that stay in force: nothing is installed on the founder's Mac (tooling runs in VMs or CI); the repo is public (no secrets, private IPs, host paths, emails); never force-push.

## Quick wins (minutes each)
| Item | Branch / PR | What is left |
|---|---|---|
| Property and fuzz tests | #55 | Wait for checks, merge |
| Security attack suite | #56 | Small conflict |
| CI test matrix | #42 | Small conflict |
| Market batch 1 (10 apps) | `feat/market-batch-1` | Open PR; CI app gate decides each tier; blocked apps stay marked blocked |
| Market batches 4–5 | `feat/market-batch-4-5` | Same as batch 1 |
| Market batches 2–3 | #49 | 7 scan failures: mark those apps blocked (3 are licence-blocked), merge the rest |

## Medium (15–45 minutes each, one at a time, in this order)
| Order | Item | Branch / PR | Why medium |
|---|---|---|---|
| 1 | Automation | `feat/automation` | Gateway module; registration conflicts only |
| 2 | Files | `feat/files` | Gateway module |
| 3 | Secrets (owner override off, pending F-7) | `feat/app-secrets` | Gateway module |
| 4 | Photos server | `feat/photos-server` | Gateway module |
| 5 | Migration kit | `feat/migrate-kit` | CLI + gateway |
| 6 | Phone app v1 | `feat/mobile-v1` | Merged in #63 (2026-11-12) |
| 7 | Dashboard v2 | `feat/dashboard-v2` | Merged in #73 (2026-11-12) |
| 8 | Ports from #27 | `feat/deploy-port27` | `deploy/install.sh` changed under it |
| 9 | Backups switched on + shared Postgres | `feat/backups-on` | Gateway + onemindd wiring |
| 10 | Storage actions + LUKS2 | `feat/storage-actions` | Gateway + onemindd wiring |
| 11 | App store depth | #47 (contract) + #57 (code) | Contract + gateway conflicts |

## Heavy (hours; do last or in a fresh session)
| Item | Branch | Why heavy |
|---|---|---|
| Mesh, HTTPS and join wired in | `feat/net-part2` | install.sh, gateway and onemindd all moved underneath it; needs a 2-VM test |
| Image line | `feat/image-line` | USB installer unfinished; slow boot battery; wire the other streams' os/ patches |
| Slop fixes | `docs/slop-audit` | Pass 1 merged in #67; pass 2 reports are `docs/quality/slop-audit-2-*.md` |
| Not started | — | App lifecycle (PD-03..07), dashboard wiring pass. Pi perf budget (#68) and the Machines spike (#70) are merged |
| Last of all | #43, #58 | Redo the board refresh and CHANGELOG catch-up once everything above has landed |

## Cloud handoff (an agent with only GitHub access)
Everything needed is on GitHub: merged work on `main`, open PRs, and pushed branches for the rest. Nothing depends on the founder's Mac.
1. Clone the repo, read this page and [NEXT-WAVE.md](NEXT-WAVE.md). Work the lists above in order: quick, then medium; heavy last.
2. Per item: `git merge origin/main` into the branch; for append-style files (CHANGELOG.md, docs/leap/STATUS.md, scripts/hygiene-allow.tsv) use `python3 -I scripts/merge/keepboth.py <files>`; resolve code conflicts by hand keeping both features.
3. Run the checks for what changed (core pytest on SQLite and PostgreSQL, `go vet` + `go test ./...`, `npm test` in ui/ dashboard/ mobile/ desktop/ where touched, `sh scripts/lint.sh`, `python3 -I scripts/hygiene.py`, gitleaks). CI runs the heavy ones (app gate, QEMU battery, browsers).
4. Push, open or update the PR, then `scripts/merge/merge-when-green.sh <pr>`: it merges only when every check passed. Wait for GitHub to compute the next PR's mergeable state before the next merge. Never force-push; never disable checks.
5. App PRs: if an app fails its scan or licence check, set its tier to `blocked` with the reason in its README; do not drop it silently.
6. Each merged item: CHANGELOG entry + STATUS row in the same PR. When a list here is done, update this page.
7. The repo is public: no secrets, private IPs, host paths, emails or tailnet names (hygiene + gitleaks enforce it).

Work-in-progress branch saved at handoff (not ready to merge): `feat/image-line` (USB installer unfinished). `feat/perf-budget` and `spike/machines` have merged (#68, #70).

## Founder decisions that unblock more
F-25 hardware order · F-27 signing-key ceremony · F-7 owner override for blocked apps · F-5 website hosting · the default accent red vs the danger red (brand PR #52 note).
