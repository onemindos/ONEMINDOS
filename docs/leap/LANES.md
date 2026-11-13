<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lanes: who finishes what (two Claude accounts)

**Written:** 2026-11-13, at founder request, after Hermes (Agent A) handed off and stopped.
**Main at writing:** `eb51419`. **Plan:** [NEXT-WAVE.md](NEXT-WAVE.md) · **Leftovers by effort:** [CONTINUE.md](CONTINUE.md)

> **Explain it like I am the founder**
> Every unfinished piece of OneMind OS is listed once below, with exactly one owner. The two Claude
> accounts each work only their own column. The owners never edit the same branch or file area at
> the same time, so their pushes do not collide. Anything that needs real hardware is listed at the end and
> waits until the software is done.

## Rules for both lanes
1. **One owner per row.** Only touch a branch or file area in your own lane. To hand a row over, edit this file in a PR.
2. **Merge `origin/main` once per branch.** Merge again only on a real conflict. Push once per fix.
   Never force-push, never push empty commits, never rewrite history, never push to `main`.
3. **Queue only when every check on the PR is green** and you have reviewed the diff, including security.
   Queue with auto-merge, merge method MERGE.
4. **Changelog:** `changes/<branch-with-dashes>.md`. Do not edit CHANGELOG.md or docs/leap/STATUS.md.
5. **Generated SDK files are never hand-merged.** Take main's side, then run `make -C sdk gen` and `make -C sdk check-stale`.
6. **No keys and no founder decisions.** AI never actuates without human approval.
   The repo is public: no secrets, private IPs, host paths or emails. Run gitleaks before every push.
7. **Hermes checkpoints** (`handoff/hermes-*`) are backups, not finished work:
   - Recover the authored code onto the original feature branch, keeping both sides of the recorded merge.
   - Never merge a checkpoint branch, and keep `HERMES_HANDOFF_STATE.json` out of product PRs.
   - Instructions: `git show origin/handoff/hermes-transfer-20261113t064930z:AGENT_A_HANDOFF.md`.
8. **Shared hot files:** `core/onemind_core/actions.py`, `core/onemind_core/app.py` (router
   registration), `core/tests/test_route_authz.py` and `sdk/`. Keep changes small and additive.
   If the other lane's PR lands first and you conflict, merge main once.

## Lane A: Claude account 1 (this session, heavy and security-sensitive)
| # | Item | Branch / PR | What is left |
|---|---|---|---|
| A1 | First-run settings | `feat/first-run-settings` (checkpoint `handoff/hermes-first-run-20261113t064930z`) | Recover 22 source files. Owner-only, audited routes for box name, time zone and backup choice, reusing #86's `/v1/backups/*` (no second backup path). Contract, SDK regen, dashboard wizard (fix the failing `src/wiring.test.tsx`), route-authz entries, PR. |
| A2 | Contract and event drift | #93 `fix/contract-drift-2` (checkpoint `handoff/hermes-pr93-20261113t064930z`, local successor `f0f0c7e`) | Finish the interrupted main merge. Re-review the newer successor. Keep the event-privacy fix: another agent's `action_id` is never exposed via live, replay or audit fallback. Keep atomic `approved_by` and the denial `decided_by` semantics. Full SQLite and PostgreSQL runs. |
| A3 | Property and fuzz tests | #55 `feat/test-property-fuzz` (checkpoint `handoff/hermes-pr55-…`) | Finish the interrupted merge: `actions.py`, regenerate the SDK schemas, `live.test.ts` from main. Fix the 4 failing checks. **DCO: founder decision D1.** |
| A4 | Security attack suite | #56 `feat/test-security` (checkpoint `handoff/hermes-pr56-…`) | Finish the interrupted merge (CHANGELOG: take main's; `live.test.ts`). One route-authz test, not two. Fix the 2 failing checks. **DCO: founder decision D1.** |
| A5 | Unready apps | `apps/fix-unready-apps` (diagnosis in the Hermes handoff supplement) | Pull the real CI and rescan logs for PhotoPrism, OpenClaw, Sonarr, Radarr, Prowlarr and qBittorrent. Fix the manifests from that evidence, and let the gate set the tiers. No gate weakening, no broad auth bypass. |
| A6 | App secrets | `feat/app-secrets` (no PR) | Merge main once and open the PR. The owner override for scan-blocked apps stays **off** (F-7). Security review: secrets never in logs, audit or events. |
| A7 | Storage actions and LUKS2 | `feat/storage-actions` (no PR) | Merge main once and open the PR. Destructive actions need owner approval plus passkey step-up. LUKS keys are never logged or committed. The key-handling parts wait on F-61/F-62. |
| A8 | App store depth | #47 (contract §12.22) then #57 (code) | Build on #72's §12.40 and don't renumber. Merge main once each, regenerate the SDKs, security review (Compose import, community sources, host ports). |
| A9 | Wave G #2: full CI run | on `main` | Run test-all, apps-gate-all, ui-quality, api-fuzz and perf-smoke on main. Each failure becomes a small fix PR. Update `docs/testing/TEST-REGISTER.md`. |
| A10 | Wave G #6: clients catch-up | `feat/clients-catchup` (new) | Mobile and desktop apps catch up with today's APIs: backups, automation, files, migrate, app lifecycle, first-run. |
| A11 | Wave G #7: Market part 2 and batch 6+ | `apps/market-unblock-2` (new), then batch branches | After A5, since it touches the same `apps/` files. Use verified fixed tags only, and `apps/_intake/CANDIDATES.md`. |

## Lane B: Claude account 2 (the other session, image, network and quick fixes)
| # | Item | Branch / PR | What is left |
|---|---|---|---|
| B1 | Image line | #66 `feat/image-line` | In progress. Main merge, plymouth rebuild, USB installer, boot battery, release refuses unsigned, H-01/H-12. LUKS2 waits on F-61/F-62. |
| B2 | Mesh, HTTPS and join | #88 `feat/net-part2` | In progress. H-05, H-34, CS2-06 and H-06, the re-applied commits, the strict 2-VM job. |
| B3 | Stale READMEs | #92 `docs/stale-readmes` | Recheck the head and checks (14 were green). Merge main once only on conflict. Queue when green. |
| B4 | Hermetic notify test | `fix/notify-test-hermetic` (feature commit `8f47821`, on `handoff/hermes-notify-20261113t064930z`) | Cherry-pick only `8f47821` onto a branch from main. Full SQLite and PostgreSQL runs, keep all 145 assertions, fragment, PR. |
| B5 | Docs: removed backup route | `fix/docs-backup-run-route` (new) | `fix(docs):` commit: BACKUPS.md §6.1 and §12.12, the CONTRACT-12 draft and poc-v0 still describe `POST /api/v1/backup/run`, which #91 removed. |
| B6 | Symlink-safe app restore | `fix/apprestore-safefs` (new) | `internal/backup/apprestore.go` `swapDir`/`swapFile`: use #91's `safefs_unix.go` helpers. Add a regression test. |
| B7 | Upload writes off the event loop | `fix/files-tus-threadpool` (new) | `tus_patch` writes chunks synchronously in the async handler. Move the writes to a thread and keep the free-space checks and offsets correct. Add a test. |
| B8 | Alpha checklist draft | `docs/alpha-checklist` (new) | `docs/leap/ALPHA-CHECKLIST.md` (Wave G #9): images, downloads page, signed releases, upgrade path, docs. Mark each item done, in progress or BLOCKED ON FOUNDER (name the decision). |
| B9 | Photos server | `feat/photos-server` (no PR) | Merge main once and open the PR. Path traversal and grant checks reuse #77's file confinement. |
| B10 | Board and changelog catch-up | #43, #58, then `docs/leap/CONTINUE.md` | Last of all, and only if the founder keeps #43 and #58 (D16). Redo them against final main, then mark finished rows in CONTINUE.md. |

**Lane B does not touch:** `.github/workflows/`, `apps/`, the generated SDK files, and every Lane A branch.
**Lane A does not touch:** `os/`, `deploy/install.sh`, `deploy/pins.env`, the mesh, proxy and NATS code, and every Lane B branch.

## Hardware testing later (not blocking the software)
- Real-board runs of the image (Raspberry Pi 5, Jetson, x86 USB install). These wait on **F-25 hardware order**. CI's QEMU battery covers the software meanwhile.
- 2 physical machines joining over the mesh (after #88's 2-VM CI proof).
- LUKS2 unlock on real disks and TPM (after F-61/F-62).
- Pi performance budget re-measure on a real Pi (#68 set the budget).

## Founder decisions (Zeus only)
| ID | Decision | Blocks |
|---|---|---|
| D1 | DCO on #55 and #56: 8 old unsigned commits (#55: `864e161` `7d4a46a` `988d0d3` `040d6c2` `779d008`; #56: `9a1c52f` `880e710` `bcf54fd`). (a) A retroactive sign-off commit by their author. (b) An approved, linked replacement PR. (c) Close both and rebuild. | A3, A4 |
| D2 | Merge authority: may Lane A queue the ex-Hermes items (A1–A5) when every check is green and they are reviewed? | A1–A5 |
| D3 | F-27 signing key and TUF root ceremony | B1 release, alpha |
| D4 | F-61 / F-62 LUKS2 design | B1, A7 |
| D5 | F-7 owner override for blocked apps | A6 |
| D6 | F-5 website hosting | downloads page, alpha |
| D7 | F-25 hardware order | hardware testing |
| D8 | Default accent red vs danger red (brand note, #52) | UI polish |
| D9 | Nextcloud 33 → 34 bump | A11 |
| D10 | TAXONOMY §5 sign-off (manifest tags and categories) | A8, A11 |
| D11 | Machines: KubeVirt or QEMU (#70) | Machines feature |
| D12 | ADR-001 wording: Rugix vs RAUC | docs |
| D13 | Contract D6/D8 text | contract |
| D14 | The install flow | first-run, alpha |
| D15 | PR #27 (yours): keep or close | none (excluded from both lanes) |
| D16 | #43 and #58: close, or redo last (B10) | B10 |
| D17 | Delete `wip/automation-merge-72` (fully merged in #75) | cleanup |
| D18 | Optional: `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` secrets for faster, steadier app scans | A5, A9, A11 speed |
| D19 | Later: delete the `handoff/hermes-*` checkpoint branches once A1–A4 and B4 have merged | cleanup |
