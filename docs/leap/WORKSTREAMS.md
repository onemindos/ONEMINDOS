<!-- SPDX-License-Identifier: Apache-2.0 -->
# Workstreams, branches and file ownership

**Date:** 2026-11-12 · Part of [the leap](README.md). Live state per epic is in [STATUS.md](STATUS.md).

> **Explain it like I am the founder**
> Many builders (people or agents) work at once, each on its own branch. This page says which branch owns which files, so two builders never edit the same file at the same time.
> A few files are shared by everyone ("hotspots"). Those change in small, separate PRs, one at a time, in the order below.
> A new session reads this page, picks a free epic whose dependencies are done, claims it with a draft PR, and works only in its owned paths.

## 1. Active streams (branches that exist today)

| Stream | Branch | State on 2026-11-12 | Owns (paths) | Epics |
|---|---|---|---|---|
| Leap docs (this) | `docs/leap` | Committed here, not pushed | `docs/leap/**`, `CHANGELOG.md` (creation) | LEAP-DOCS |
| Gateway agent and MCP | `feat/gateway-agent-mcp` | 3 commits, no PR | `core/onemind_core/{scan,mcp}.py`, agent principals in `auth.py`, catalog fields, `dashboard` app page (§11.4) | W2-GW |
| App pipeline | `feat/app-pipeline` | 4 commits, `renovate.json` uncommitted, no PR | `sdk/tools/{app-gate,app-scaffold,app-readme}`, `sdk/schema/onemind.app.schema.json` (§9.3, §11.2 fields), `.github/workflows/ci-apps.yml`, `renovate.json` | W2-PIPE |
| Hermes app | `feat/app-hermes` | Empty (behind `main`) | `apps/hermes-agent/**` | W2-HERMES |
| Wave-2 seed apps | `feat/apps-wave2` | Empty (behind `main`) | `apps/<new-id>/**` | W2-SEEDS |
| Developer install | `feat/deploy-v0` | 6 commits, no PR | `deploy/**` (install.sh, pins, systemd units, compose hub, verify.sh) and its CI | W2-DEPLOY |
| OS security pipeline | `feat/os-security-pipeline` | **PR #14 open** | `os/update/**`, `scripts/tuf-bootstrap-root.sh`, `.github/workflows/security-nightly.yml`, `os/rootfs/Containerfile` upgrade step | OS-SECPIPE |
| onemindd updater | `feat/onemindd-updater` | **Merged, PR #15** (retire the worktree) | `internal/update/**`, `cmd/onemind/update.go`, `deploy/systemd/onemind-update.service` | OS-UPDATER |
| Architecture and alignment | `docs/core-architecture` | 2 commits (`docs/strategy/core-alignment.md`, then `docs/architecture/**` with the §12 draft), no PR | `docs/architecture/**`, `docs/strategy/**` | PA-ALIGN, PA-ARCH |
| Design system | `feat/design-system` | 2 commits, no PR | `ui/**`, `docs/design/**` | PA-UI |
| Threat model | `docs/security-threat-model` | 1 commit, no PR | `docs/security/**` | PA-THREAT |
| Mobile shells | `feat/mobile-shell` | 1 commit, no PR | `mobile/**` | PA-MOBILE |
| Website | `feat/website` | 1 commit, no PR | `site/**` | PA-SITE |
| Image and hardware | new branches from `main` (`build/core-v0` merged as #10) | – | `os/**` except `os/update/**`, `test/qemu/**`, `lab-kits/**` | PLAN-E1, -E10, -E11, CORE-SEC-5 image part |

## 2. Planned streams (branches cut when their epics start)

Branch names come from the specs. Cut each from current `main`; one epic (or a tight group) per branch.

| Stream | Branches | Owns (paths) | Specs |
|---|---|---|---|
| Contract owner | `contract/12-a` … `contract/12-h`, `contract/12-plugins` | `sdk/contracts/poc-v0.md` (hotspot) | All |
| Gateway core | `feat/api-<n>-<slug>` (e.g. `feat/api-7-actions-v1`), `feat/sdk-spec` | `core/onemind_core/{routes,errors,limits,listing,idempotency,scopes,action_types,events,audit_api,openapi}.py`, `auth.py`, `actions.py`, `ledger.py` migrations, `sdk/openapi/compat/`, `.github/workflows/api-compat.yml` | API, SDK-1 |
| Install sandbox | `feat/install-sandbox` | `sdk/policy/**`, `core/onemind_core/policy.py`, `executors.py` (`plan`, `run`) | SANDBOX |
| Security and identity | `feat/gateway-tls`, `feat/passkeys`, `feat/tokens`, `feat/nats-auth`, `feat/audit-verify`, `feat/security-headers`, `feat/identity` | `core/onemind_core/{tls,passkeys,sessions,tokens,agents,bus}.py`, `audit.py` checkpoints, `dashboard/src/pages/SignIn.tsx` | SECURITY, API-6, API-9 |
| SDKs | `feat/sdk-gen`, `feat/sdk-ts`, `feat/sdk-python`, `feat/sdk-go`, `feat/sdk-conformance`, `feat/sdk-release` | `sdk/{openapi,ts,python,go,conformance}/**`, `sdk/Makefile`, `.github/workflows/{ci-sdk,sdk-release}.yml` | SDK |
| CLI | `feat/cli-<n>-<slug>` | `cmd/onemind/**` (`cli/root.go` and `main.go` are hotspots), `docs/cli/**`, `sdk/testdata/**` | CLI |
| MCP | `feat/mcp-<slug>`, `feat/cli-mcp` | `core/onemind_core/mcp/**`, `grants.py`, `ratelimit.py`, `internal/mcpbridge/**`, `cmd/onemind/cli/mcp.go`, `test/mcp-conformance/**` | MCP |
| Plugins | `feat/plugins-core`, `feat/plugins-sdk`, `feat/plugins-sdk-go`, `feat/plugins-ui` | `core/onemind_core/{plugins,plugin_events}.py`, `sdk/plugin-*/**`, `sdk/templates/**`, `internal/plugin/**`, `cmd/onemind/cli/plugin.go`, `dashboard/src/plugins/**`, `.github/workflows/ci-plugins.yml` | PLUGIN-SDK |
| Fabric | `feat/fabric-join`, `feat/placement`, `feat/leaf-node` | `core/onemind_core/fabric.py`, `internal/{join,leaf}/**`, capabilities in `internal/detect/` | FABRIC, API-10 |
| Backups | `feat/backup-agent`, `feat/backup-api` | `internal/backup/**`, `core/onemind_core/backups.py`, `dashboard/src/pages/Backups.tsx` | BACKUPS, API-11 |
| Deployments | `feat/deploy-own`, `feat/onbox-scan`, `feat/migrate-kit` | `core/onemind_core/{deploys,scanjob}.py`, `sdk/tools/compose-import/**` | DEPLOYMENTS |
| Automation | `feat/automation` | `core/onemind_core/{automation,policies}.py`, `dashboard/src/pages/Automations.tsx` | AUTOMATION, API-13 (rules) |
| Notifications | `feat/notifications`, `feat/repairs`, `feat/push-relay` | `core/onemind_core/{alerts,repairs}.py`, `core/onemind_core/notify/**`, `relay/**`, `dashboard/src/pages/Alerts.tsx` | NOTIFICATIONS, API-12 |
| Updates | `feat/os-api`, `feat/app-updates`, `feat/rescue` | `core/onemind_core/{os_updates,app_updates}.py`, `internal/update/api.go`, `internal/rescue/**` | UPDATES, API-13 (OS) |
| Dashboard | `feat/dashboard-redesign`, `feat/dashboard-sdk` | `dashboard/src/{components,api}/**`, the five existing pages and the pages no other stream names, `dashboard/package.json` (feature pages listed in other rows belong to that row's stream, §3) | DASHBOARD, SDK-4 |
| Mobile | `feat/mobile-shell` (continues), `feat/mobile-sdk` | `mobile/**` | MOBILE, SDK-4 |
| Website | `feat/website` (continues), `feat/site-gen`, `feat/site-api-docs` | `site/**`, `.github/workflows/site.yml` | WEBSITE, SDK-10 |
| Dogfood | `feat/doctor`, `feat/remote-access`, `feat/gpu`, `feat/app-metrics` | `internal/doctor/**`, `core/onemind_core/{exposure,metrics}.py`, `apps/tailscale` or `apps/headscale` | DOGFOOD |

## 3. Shared files: who writes them

| File or area | Rule |
|---|---|
| Phase-B route modules | The API spec (DEV-API-10…13) defines the route shapes; the core epic owns the file: `fabric.py` CORE-FABRIC-1, `backups.py` CORE-BACKUP-8, `notify/` and `alerts.py` CORE-NOTIFY-1, `automation.py` CORE-AUTO-2, `policies.py` CORE-AUTO-3, `os_updates.py` CORE-UPDATE-2 |
| `tokens.py` | CORE-SEC-3 creates it (token lifecycle); DEV-API-6 adds plugin tokens and scopes afterwards |
| `actions.py` approve path | One hook per feature, serialized through the gateway-core owner, in this order: CORE-SANDBOX-2 (plan check) → DEV-API-7 and CORE-AUTO-1 (risk, binding, cap) → CORE-SEC-2 (passkey) → CORE-AUTO-3 (standing approvals) → DEV-MCP-3 (withdraw, preview) |
| `onemind` command files | All live in `cmd/onemind/cli/<group>.go`. Groups CLI.md builds (`audit`, `backup`, `restore`, `fabric`, `notify`, `tokens`, `update`): the CLI epic writes the file, the core branch provides the gateway side. `mcp` is built by DEV-MCP-7, `plugin` by DEV-PLG-7/8/14. Groups only a core spec defines (`alerts`, `auto`, `policy`, `tls`, `deploy`, `secret`, `migrate`, `doctor`): the core branch writes the file |
| `onemind app` developer commands | DEV-CLI-10, with one validator shared with the Python gate (`sdk/testdata/manifests/`) |
| `sdk/openapi/onemind-v1.json` | Generated by DEV-SDK-1's export, never edited by hand; on a conflict, rebase and regenerate |
| `core/onemind_core/executors.py` | Install sandbox owns it (CORE-SANDBOX-2, -5). CORE-FABRIC-4 (node affinity) and CORE-DEPLOY-1 add one hook each, after SANDBOX-2 merges, through the sandbox owner |
| Approval plan and `plan_sha256` (`policy.py`; MCP calls it `effects`) | Install sandbox (CORE-SANDBOX-2) computes it; DEV-API-7, DEV-MCP-3 and the dashboard only read it |
| `internal/detect/**` | Fabric owns capability labels (CORE-FABRIC-4); CORE-DOGFOOD-5 (GPU) edits it only after FABRIC-4 merges |
| `core/onemind_core/mcp/catalog.py` | MCP stream owns it; DEV-PLG-4 adds plugin tool projection in one PR agreed with the MCP owner |
| Feature pages in `dashboard/src/pages/` | `SignIn.tsx` security, `Backups.tsx` backups, `Alerts.tsx` notifications, `Automations.tsx` automation, `Updates.tsx` updates, `Settings*.tsx` dashboard (DEV-PLG-6 adds the plugin panel under `dashboard/src/plugins/`), `Market.tsx` dashboard (FABRIC-4 verdict and PLG-14 tier filter as one-hook PRs). Each new page adds its route line to `App.tsx` (hotspot) |
| `site/**` | Website stream owns it; DEV-SDK-10 writes only `site/src/content/docs/api/**` and DEV-PLG-16 only the plugin docs section |
| `os/**` pieces from other specs | Image stream merges them: PSA and nftables files (CORE-SANDBOX-3, -5), LUKS2 (CORE-SEC-5), StorageClass (CORE-BACKUP-1), GPU (CORE-DOGFOOD-5) |

## 4. Hotspot rules (serialized files)

A hotspot changes only in a small PR that does nothing else, merged one at a time. Rebase on `main` right before merging.

| Hotspot | Rule |
|---|---|
| `sdk/contracts/poc-v0.md` | Contract PRs only, in the order of [BACKLOG.md](BACKLOG.md) S1 (12-a first). A feature PR never edits the contract; it adopts a merged contract PR |
| `core/onemind_core/app.py` | Route registration is the `ROUTERS` list (shipped in #38): each feature adds `routers/<feature>.py` and one line there |
| `cmd/onemindd/main.go` | One line per feature in `cmd/onemindd/registry.go` (`subcommands` or `optionalServices`) |
| `cmd/onemind/main.go`, `cmd/onemind/cli/root.go` | `main.go` already only calls `cli.Run`; each command group adds one line to `groups` in `root.go` |
| `os/versions.lock.yaml` | Add-only pins (generators, cobra, cosign, restic, scanners, GPU parts), one commit per stream |
| `sdk/schema/onemind.app.schema.json` | Changes ship with the matching contract PR (manifest v1 freeze PLAN-E6, `spec.agent.scopes`, `spec.backup`, `spec.network`, `extensions`) |
| `core/onemind_core/ledger.py` | One migration file per epic, numbered when merged |
| `dashboard/src/App.tsx`, `dashboard/src/api/types.ts` | One route line per page; `types.ts` stays until DEV-SDK-4 replaces it |
| `mobile/app.json` | Native config changes one at a time |
| `go.mod` | SDK, updater and plugin streams coordinate; one PR at a time |
| Existing `.github/workflows/*.yml` | New streams add new workflow files; edits to existing ones are serialized with their owner. Every action pinned by commit as in `os/versions.lock.yaml` |
| `CHANGELOG.md` | Every PR adds its own entry at the top of "Unreleased". On a conflict keep both entries; the merger moves the entry under the merge date |

## 5. Merge order

**S0 (land what exists):**
1. PR #14 `feat/os-security-pipeline` (the updater, #15, is already merged).
2. `feat/gateway-agent-mcp` (contract §11 is already merged as #12).
3. `feat/app-pipeline`, then `feat/deploy-v0`.
4. `feat/app-hermes`, then `feat/apps-wave2` (both still empty; they may slip into S1).
5. Docs and independent trees, in any order: `docs/security-threat-model`, `docs/core-architecture`, `docs/leap`, `feat/design-system`, `feat/website`, `feat/mobile-shell`.

**S1 onward:** contract PR first, then the feature PRs that adopt it, in [BACKLOG.md](BACKLOG.md) order. Within a sprint, a PR merges only when every epic in its "Depends on" column is `done` in [STATUS.md](STATUS.md).

**Every merge:** CI green, gitleaks clean, a CHANGELOG entry, and the epic's row in STATUS.md set to `done` with the PR number.

## 6. How a new session claims a stream

1. Read [README.md](README.md), this page, [BACKLOG.md](BACKLOG.md) and [STATUS.md](STATUS.md). Read the epic's spec section.
2. Pick a `todo` epic whose dependencies are all `done` (or `in-review` when the spec says a stub is fine).
3. Check nobody holds it: `gh pr list -R onemindos/ONEMINDOS --state open --search "<EPIC-ID>"`.
4. Cut the branch from `main` with the name in §2, in its own git worktree, and open a **draft PR** whose title starts with the epic id, for example `DEV-API-7: actions v1`. The draft PR is the claim.
5. Work only in the owned paths. If a hotspot or another stream's file must change, stop and open a separate small PR, or ask that owner.
6. Before marking ready: tests from the spec's acceptance column pass, gitleaks is clean, CHANGELOG has an entry, and the STATUS.md row is updated in the same PR.
7. A claim with no push for 3 days is free again; say so in the draft PR before taking it over.
