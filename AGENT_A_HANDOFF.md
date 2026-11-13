# Agent A — verified source handoff

Prepared November 13, 2026. Repository: `onemindos/ONEMINDOS`.

## Start here

Take over Agent A's existing seven workstreams. Recover retained work; do not rebuild it from scratch. No outgoing implementation workers remain active. The implementation cards are blocked and must not be automatically restarted into a competing writer. Read `CLAUDE.md`, `docs/leap/CONTINUE.md`, `changes/README.md`, `docs/quality/slop-audit-2-docs.md`, `docs/quality/slop-audit-2-drift.md`, and `apps/_intake/UNBLOCK.md` before editing. Recheck current remote/main and other agents' ownership before acting.

**The handoff is backed up; the features are NOT all complete.** Below are source-transfer branches, NOT approved release candidates. Do not merge these checkpoint branches or use their parentage as proof that integration finished. They preserve interrupted code, including unresolved conflict markers where noted. Hygiene and redacted gitleaks scans passed on every exported checkpoint; that does not establish functional acceptance.

## Published checkpoints

All five heads were pushed and verified by `git ls-remote` on November 13, 2026. Each contains `HERMES_HANDOFF_STATE.json` with original feature branch/HEAD, attempted merge target, conflict paths, staged blob versions, and working-source digests. Paths in the manifest are component arrays, joined with `/`. The parent checkpoint preserves staged source independently of later working-tree edits. Original local indexes and source were verified unchanged during export. Dependencies, environment links, credentials, caches, and raw execution logs were deliberately NOT published.

| Lane | Remote transfer branch | Exact checkpoint commit |
|---|---|---|
| First-run settings | `handoff/hermes-first-run-20261113t064930z` | `4fcfff8f0eba2d8b3f59e556fe4b9e60a2f96665` |
| PR55 property/fuzz | `handoff/hermes-pr55-20261113t064930z` | `014577be8285574927d15ba1edb81f405bdbc584` |
| PR56 security | `handoff/hermes-pr56-20261113t064930z` | `64d500724ad81772684132640fb192f365fd103b` |
| PR93 contract drift | `handoff/hermes-pr93-20261113t064930z` | `7e8a98b40b975c611aa9ec68f4fcf0584b4554dd` |
| Hermetic notify | `handoff/hermes-notify-20261113t064930z` | `9f783290fe0bc3adce8a6ad1d1f003b8afa8038b` |

The transfer exporter recorded an unnecessary empty index checkpoint for the clean notify lane before adding its handoff metadata. It is backup-only history, not a feature fix; do not merge/cherry-pick those transfer commits. Its actual feature commit is listed below. Do not rewrite or delete the published backup to conceal this.

## Original feature/PR state at 06:35 UTC

Reverify before editing or publishing; other owners may have moved main since this read.

- **PR55**, `feat/test-property-fuzz`, OPEN, published feature head `d41c48670b0e25c736dc1cb8bcc263b02454a261`. Interrupted merge target `ab3560556a4d3c4fe54e0d78c9dda0a9598b6855`. Unresolved: `core/onemind_core/actions.py`, generated Go/Python/TS schemas, and `sdk/ts/test/live.test.ts`. Preserve both sides; regenerate generated files rather than hand-merging them. No check rollup on the published head is NOT green CI.
- **PR56**, `feat/test-security`, OPEN, published feature head `0c9a80c5c3bbcef2a4af0558c329de8296b9de96`. Same interrupted merge target. Unresolved: `CHANGELOG.md` and `sdk/ts/test/live.test.ts`. Do not author new changelog changes; preserve the incoming main changelog when completing the real integration. No check rollup is NOT green CI.
- **PR92**, `docs/stale-readmes`, OPEN at `1bf9b3453a637ac95626fe5b287b782e945447fb`, **14 successful checks** at the read. Narrow README/comment corrections and fragment; previously source-reviewed. Recheck exact head and owner merge authority. Do not rewrite it merely to restart CI.
- **PR93**, `fix/contract-drift-2`, OPEN, published head `b8a68ee50e704e3e9957c617e616cea38bad6cff`. Original local feature HEAD advanced to `f0f0c7e8b5bea186108cbcb18c335b55c9c3defc`; that commit is now reachable through the transfer branch. Same attempted main merge. At export, no unmerged index entries remained, but the merge was not committed and its current source was not fully accepted. No rollup on the published PR head is NOT green CI.
- **Notify**, `fix/notify-test-hermetic`, actual feature commit `8f47821f2cf8174fc1874e2811766cfcd6197348`, no PR. This commit is now reachable through its transfer branch. Earlier independent review preserved all 145 assertion ASTs and passed bounded safe DNS/ownership controls. Full SQLite/PostgreSQL acceptance is still missing. Do not treat an ancestor-only scan of the transfer metadata as a full rescan of this feature commit.
- **First-run**, `feat/first-run-settings`, no PR, original HEAD `0105435b240aec1000f35f7af569ed47179aa8aa`; 22 changed/new source files preserved. Includes contract, onboarding module/router, app registration, owner authorization tests, SDK exports and dashboard wiring. Partial implementation, NOT a tested feature. The last recovery record reported UI checks passed but dashboard integration failed around `src/wiring.test.tsx` sign-in/first-run setup/wizard/starter installs. Reproduce, keep existing assertions, and fix the actual wiring. Full required backend/SDK/UI acceptance is not established.
- **Apps**, `apps/fix-unready-apps`, no implementation PR. Diagnosis only. OpenClaw probe mismatch was identified; do not invent proven runtime causes for the other apps. Retrieve authenticated ci-apps/daily-rescan logs, fix manifests, and let the real gate assign tiers. Original diagnosis remains on the outgoing persistent volume; remote source checkpoints do not contain its raw runtime evidence.

## Correct recovery, not another freshness merge

Prefer the original retained worktree if available. It still has the actual interrupted index and merge state. Otherwise fetch a checkpoint and inspect its manifest, working tree and parent staged checkpoint in a separate worktree. Start integration from the recorded ORIGINAL feature HEAD and preserve the recorded incoming main side. Apply recovered authored source while resolving that existing integration; do not blindly merge the WIP checkpoint as a finished feature or repeatedly merge newer main. Keep the handoff metadata out of final product PRs. Verify exact final source identity before tests and one real-fix push.

## Runtime failure: confirmed, not guessed

The outgoing Hermes Kubernetes container was **OOMKilled**, exit 137, at **06:29:17 UTC** on November 13, 2026, under a **3 GiB container memory limit**. It restarted at 06:29:18 UTC and interrupted all three native lanes. This caused missing workers and lifecycle/protocol alerts. A worker's clean wrapper exit is not completion. Do not restart all workers or heavy suites concurrently in this container. Use one implementation worker and one foreground test/compiler process at a time, serial Go packages and supported single-worker JS test options, without dropping tests or weakening thresholds. Check current memory/headroom; a restarted cgroup's zero OOM counter does not disprove the previous pod termination record. Infrastructure changes, if needed, require the normal GitOps/owner route, not live patches.

## Acceptance and scope constraints

1. Never force-push, rewrite history, forge DCO trailers, push empty commits, weaken/skip checks, or push to main. Push once per real fix. Preserve all source, worktrees and evidence. Deletions require Zeus's specific `execute` or `override` authority.
2. Historical unsigned non-merge commits still block DCO: PR55 `864e161`, `7d4a46a`, `988d0d3`, `040d6c2`, `779d008`; PR56 `9a1c52f`, `880e710`, `bcf54fd`. New signoffs do not repair old messages. Obtain a compliant owner decision rather than bypassing DCO or making replacement PRs to hide it.
3. No founder decisions. No physical/financial actuation. Never publish credentials, private host paths, private addresses or personal records. Use existing scoped publication access; child auth failure does not authorize copying credentials, changing grants or initiating login.
4. Do not touch PR86 or its branch. First-run may READ/REUSE its already-merged backup service and routes, including `/v1/backups/destinations`; do not build a second backup path. Respect other owners of #75/#87/#77/#76/#78, #66 and `feat/net-part2`; recheck current coordination. Leave #27, #68, #73 and other excluded branches alone.
5. Do not edit `CHANGELOG.md` or `docs/leap/STATUS.md`. First-run must not touch `deploy/install.sh`, `deploy/pins.env`, `ci-apps.yml`, or `apps-rescan.yml`. Shared actions/app registration/authz/generated SDK edits stay small and additive. Add one correctly formatted `changes/<branch-with-slashes-as-dashes>.md` per feature; run `python3 -I scripts/changes.py check`.
6. First-run must save box name, timezone and backup choice through owner-only, audited gateway routes, wire the existing dashboard wizard, and enumerate routes correctly in `core/tests/test_route_authz.py`. Contract first, then code and generated SDKs. Run `make -C sdk gen` and `make -C sdk check-stale`; never hand-merge generated files.
7. Required first-run checks: core pytest on SQLite AND PostgreSQL (only the expressly permitted DNS test exception, if still applicable), `go vet ./...` and `go test ./...`, UI/dashboard tests where touched, `sh scripts/lint.sh`, `python3 -I scripts/hygiene.py`, gitleaks and fragment validation. Full backend fixtures can perform destructive resets: use specifically authorized disposable test state, never real data, and obtain required specific deletion authority. Preserve per-command exit/timestamps/source hashes. `make validate` was absent, and skipped TS live tests are not passes.
8. PR93's earlier bounded source acceptance at `b8a68ee` included 233 selected core tests and 24 independent focused tests, NOT full SQLite/PostgreSQL/current-head CI acceptance. Preserve the foreign-action event privacy repair: app visibility alone must never expose another agent's embedded `action_id`, including live/replay and audit fallback. Preserve atomic `approved_by`, legacy nullable migration and denial `decided_by` semantics. The changed local successor must be re-reviewed.
9. Final merge/auto-merge remains owner-gated under the outgoing agent's authority. Do not infer merge authority from this handoff. Report exact current PR number/head/state, remaining failures and evidence; do not call backups, investigations or partial test runs delivered features.

Finish the source repairs, independent review and exact-head checks; publish honest PR bodies; give Zeus a precise remaining owner-decision list. Prioritize actual recoverable code and publication over building more orchestration.
