<!-- SPDX-License-Identifier: Apache-2.0 -->
# Hand-off: everything left, who does it, and the prompts

**Written:** 2026-11-12, when the build session on the founder's Mac ended. Nothing depends on that Mac any more: all work is on GitHub (merged, open PR, or pushed branch).
**Read with:** [CONTINUE.md](CONTINUE.md) (order and rules), [NEXT-WAVE.md](NEXT-WAVE.md) (Wave G), [STATUS.md](STATUS.md) (board), [BACKLOG.md](BACKLOG.md), [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md), [../testing/TEST-REGISTER.md](../testing/TEST-REGISTER.md), [PLAN-90-DAYS-2026-11-12.md](PLAN-90-DAYS-2026-11-12.md).

> **Explain it like I am the founder**
> Two AIs finish the job. **Agent A (GPT via Hermes)** lands everything that is already built: it merges, fixes conflicts and makes CI green. **Agent B (Claude)** does the heavy engineering and the work that was never started. They split the work by branch so they never edit the same thing, and they claim each item on the board before starting it.

**Private material:** the founder's private cluster migration map and the build session's notes live in the private repo `onemindos/onemind-private` (org members only). Never copy anything from it into this public repo.

## 1. State at hand-off
- **On main (merged):** PRs #1–#26, #28–#41, #44–#46, #48, #50–#54, #59, #60. Highlights: the OS image and A/B updates, the OS security pipeline and updater, the gateway (approvals, audit, MCP, scan gate, install sandbox, identity/passkeys, notifications/monitoring, plumbing, contract §11–§12), node agent + CLI, SDKs, the app pipeline and 9 apps, the design system and UI leap, the website and guides, phone and desktop shells, branding, the test register, the golden-path e2e, fabric research, networking modules (#37).
- **Rules that stay in force:** the repo is public (no secrets, private IPs, host paths, emails, tailnet names; `scripts/hygiene.py` + gitleaks before every push); never force-push; merge only when every check is green (`scripts/merge/merge-when-green.sh`); umbrelOS is PolyForm-NC (study only, never copy); AI never actuates without human approval; nothing is installed on the founder's computer; each merged item gets its CHANGELOG entry and STATUS row in the same PR.

## 2. Agent A (GPT via Hermes): land what is built — in this order
| # | Item | Where | What is left |
|---|---|---|---|
| A1 | Cloud hand-off docs | PR #64 | Merge when green (this file) |
| A2 | Property/fuzz tests | PR #55 | Merge when green |
| A3 | CI test matrix | PR #42 | Merge when green |
| A4 | Phone app v1 | PR #63 | Merge when green (already matched to the hub's routes; 142 tests) |
| A5 | Security attack suite | PR #56 | WIP pushed (fixes 2 real SSRF holes, audits refusals, MCP crash). Run full core suite on SQLite + PostgreSQL, lint, unit, gitleaks; STATUS + CHANGELOG; update PR body; merge |
| A6 | Market batch 1 | PR #61 | Wait for app gates; failing apps → `tier: blocked` + reason in README (`sdk/tools/app-readme`); merge |
| A7 | Market batches 2–3 | PR #49 | 10 apps failed vuln/secret scans (audiobookshelf, calibre-web, code-server, esphome, freshrss, ghost, karakeep, photoprism, prowlarr, radarr) → mark blocked with reasons; calibre-web/homebox WIP fix is committed — verify it; check openclaw and sonarr results; merge |
| A8 | Market batches 4–5 | PR #62 | Same as A6 |
| A9 | Dashboard v2 | branch `feat/dashboard-v2` | main already merged in and building; run lint.sh, hygiene, gitleaks; STATUS (CORE-DASH-2) + CHANGELOG; open PR; merge |
| A10 | Automation | `feat/automation` | Merge main, test (SQLite + PostgreSQL), PR, merge |
| A11 | Files | `feat/files` | Same |
| A12 | App secrets (owner override OFF, pending F-7) | `feat/app-secrets` | Same |
| A13 | Photos server | `feat/photos-server` | Same |
| A14 | Migration kit | `feat/migrate-kit` | Same (never run against a real cluster) |
| A15 | Ports from Zeus's #27 | `feat/deploy-port27` | Merge main (keep #40's install.sh changes), test, PR, merge; then comment on #27 and leave it to Zeus |
| A16 | Backups on + shared Postgres | `feat/backups-on` | Merge main, test, PR, merge |
| A17 | Storage actions + LUKS2 | `feat/storage-actions` | Same |
| A18 | App store depth | PR #47 (contract) then PR #57 (code) | Resolve conflicts, test, merge in that order |
| A19 | Board + record | PRs #43, #58 | Last: redo both against the final main (or close and replace) |

## 3. Agent B (Claude): heavy and not-yet-started — in this order
Start with B1–B2 (no overlap with Agent A); start B3 only after A10–A18 have merged (it touches install.sh, gateway and onemindd).

| # | Item | Where | What to do |
|---|---|---|---|
| B1 | Slop fixes | branch `docs/slop-audit` (3 reports in `docs/quality/`) | Re-verify each finding on current main; fix medium/high; resolution column; PR; merge |
| B2 | Image line | branch `feat/image-line` | Finish the USB installer board; apply the os/ patches from other streams (`docs/leap/core/*-os.patch.md`, `brand/generated/os/`, LUKS2, NATS TLS, updater + TUF root); first-boot + QEMU battery in CI; release.yml + downloads page; PR; merge |
| B3 | Mesh, HTTPS, join wired | branch `feat/net-part2` | Merge main (big conflicts with #40/#41/#44 and A10–A17); prove hub + node join, mesh, NATS leaf TLS, `https://<app>.<box>.local` via the proxy (2 VMs in CI or a cloud VM); PR; merge |
| B4 | App lifecycle P0 (never started) | new `feat/app-lifecycle` | umbrel-parity PD-03..07: start/stop/restart/update/configure/delete_data with progress, `/v1/apps/{id}/plan` bound via plan_sha256, health-gated updates with automatic revert, keep-data removal, sealed credentials |
| B5 | Dashboard wiring pass | new `feat/dashboard-wiring` | Pages for every API on main (passkey login, users, notifications, monitoring, automation, files, backups, secrets, network/QR, storage, updates, lifecycle), first-run wizard, PWA, i18n scaffold |
| B6 | Pi performance budget | branch `feat/perf-budget` (WIP) | Finish: measure on a Pi-sized VM, write budgets, `perf-smoke.yml` |
| B7 | Machines (VMs) spike | branch `spike/machines` (WIP) | Pre-registered spike KubeVirt vs QEMU+noVNC; recommendation only |
| B8 | Wave G | [NEXT-WAVE.md](NEXT-WAVE.md) §2 | Full CI run + fix PRs, security re-review, slop pass 2, parity re-score, clients catch-up, Market unblock + batches 6+, fabric follow-through (from research-output/fabric), alpha readiness |

## 4. Coordination between the two agents
- **Claim before you start:** set the item's row in [STATUS.md](STATUS.md) to `in-progress (agent A|B)` in a tiny PR or as the first commit of the item's PR.
- **One item at a time per agent.** After every merge, wait for GitHub to compute the next PR's mergeable state.
- **Never edit the other agent's branch.** If an item needs a change in the other's area, open an issue or a comment and wait.
- **Main must stay green.** If main's CI goes red, the agent whose merge caused it fixes it before anything else.

## 5. Waiting on the founder (do not decide these)
F-25 hardware order · F-27 TUF root ceremony + signing secrets · F-7 owner override for blocked apps (built, off) · F-5 website domain/hosting · the default red accent vs the danger red (PR #52) · Zeus's PR #27 (close or keep) · any GitHub Project board (needs `gh auth refresh -s read:project,project`).

## 6. The prompts
### Agent A — GPT via Hermes
```
You are finishing the OneMind OS build in the public repo onemindos/ONEMINDOS. Clone it and read, in order:
CLAUDE.md, docs/leap/HANDOFF.md, docs/leap/CONTINUE.md, docs/leap/core/PLUMBING.md.
You are "Agent A". Work through HANDOFF.md section 2 (A1…A19) strictly in order, one item at a time:
claim the item in docs/leap/STATUS.md, merge origin/main into its branch, resolve conflicts (append-style
files with scripts/merge/keepboth.py; code by hand keeping both features), run the checks for what changed
(core pytest on SQLite and PostgreSQL, go vet + go test ./..., npm test where touched, sh scripts/lint.sh,
python3 -I scripts/hygiene.py, gitleaks), add the CHANGELOG entry and STATUS row, push, open/update the PR,
then run scripts/merge/merge-when-green.sh <pr>. If CI fails, read the failing log, fix, push, re-run.
Rules: never force-push; never disable or skip checks; never commit secrets, private IPs, host paths, emails;
apps that fail their scan become tier: blocked with the reason — never hidden; do not touch Agent B's
branches (docs/slop-audit, feat/image-line, feat/net-part2, feat/app-lifecycle, feat/dashboard-wiring,
feat/perf-budget, spike/machines); do not make founder decisions (HANDOFF.md section 5).
If an item cannot go green with reasonable effort, leave the PR open with a comment saying exactly what
remains and move to the next. When A1–A19 are done, update docs/leap/CONTINUE.md and report every PR.
```

### Agent B — Claude (heavy work)
```
You are finishing the OneMind OS build in the public repo onemindos/ONEMINDOS. Clone it and read, in order:
CLAUDE.md, docs/leap/HANDOFF.md, docs/leap/CONTINUE.md, docs/leap/NEXT-WAVE.md, docs/leap/core/PLUMBING.md,
sdk/contracts/poc-v0.md, docs/security/THREAT-MODEL.md.
You are "Agent B". Work through HANDOFF.md section 3 (B1…B8) in order. Start B3 (feat/net-part2) only after
Agent A has merged A10–A18 (check gh pr list). For each item: claim it in docs/leap/STATUS.md; build with
tests; have an independent review pass (security first: authz, agents never approve, secrets, injection,
SSRF, data-loss paths); merge origin/main; run the full checks (core pytest on SQLite and PostgreSQL, go vet
+ go test ./..., npm test where touched, sh scripts/lint.sh, python3 -I scripts/hygiene.py, gitleaks); add
CHANGELOG + STATUS rows; push; PR with a clear body; scripts/merge/merge-when-green.sh <pr>. Heavy tests
(QEMU battery, 2-VM mesh proof, app gates, browsers) run in GitHub CI or a cloud VM.
Rules: never force-push; never disable checks; public repo hygiene; umbrelOS is PolyForm-NC (study only, never
copy); AI never actuates without human approval; do not touch Agent A's branches (HANDOFF.md section 2); do
not make founder decisions (section 5). Pre-register lab criteria before running any spike. When you finish
a list, update CONTINUE.md and STATUS.md and report every PR.
```

### Reasoning level
Use the model's **highest** reasoning / effort level for both agents: the work is long-running, multi-step and must not break `main`. If cost matters, Agent A can drop one level for the pure merge items (A1–A4, A6, A8) and go back to the highest for A5, A7 and A9–A19.
