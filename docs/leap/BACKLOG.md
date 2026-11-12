<!-- SPDX-License-Identifier: Apache-2.0 -->
# Leap backlog: every epic, in build order

**Date:** 2026-11-12 · Part of [the leap](README.md). State per epic: [STATUS.md](STATUS.md). Owners and hotspots: [WORKSTREAMS.md](WORKSTREAMS.md).

> **Explain it like I am the founder**
> This is the whole to-do list in one place, in the order it can be built. Nothing appears before the things it depends on.
> Sprints: **S0** lands what is already half-done; **S1** lays the plumbing (contract §12, sandbox, security, SDK/CLI/MCP foundations); **S2** builds fabric, backups, notifications, the new dashboard and phone apps; **S3** adds automation, plugin SDK v0, the website launch and moving your own services over; **S4+** is phase 2 and the parked items.
> Each row says when it counts as done (acceptance). The detail behind each row is in the linked spec.

**Effort:** S ≤ 1 day, M 2–4 days, L 1–2 weeks, for one builder with an agent. **Sprint dates** assume the 90-day plan (Day 1 = 2026-11-16) and about 23 build hours a week: S0 weeks 0–2, S1 weeks 1–5, S2 weeks 5–9, S3 weeks 9–13, S4+ after 2027-02-14. Sprints overlap at the edges; dependencies, not dates, decide what starts.

**Spec keys:** SANDBOX, SEC, FABRIC, BACKUP, DEPLOY, AUTO, NOTIFY, UPDATE, DASH, MOBILE, WEB, DOGFOOD are in [`core/`](core/README.md); API, SDK, CLI, MCP, PLG are in [`dev/`](README.md#4-every-spec). Ids without a prefix in "Depends on" refer to the same spec family (for example `SEC-2` = CORE-SEC-2). "F-n" are founder decisions in [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md).

## S0: land the in-flight work (weeks 0–2)

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| OS-UPDATER | onemindd OS updater: TUF-verified, policy and window, restic pre-snapshot, health-gated (PR #15) | M | – | `internal/update/**`, `cmd/onemind/update.go`, `deploy/systemd/onemind-update.service` | Done: unit tests for wrong root, expiry, replay, wrong board, window, postpone, pending trial; integration install of a pipeline-built bundle |
| OS-SECPIPE | OS security pipeline: nightly Debian check, rebuild, SBOM/CVE+VEX/ClamAV, battery, RAUC+TUF (PR #14) | S | – | `os/update/**`, `.github/workflows/security-nightly.yml`, `os/rootfs/Containerfile` | CI green; dry-run chain build → sign → scan → TUF → verify passes; publishing stays off until keys and the root exist |
| CORE-UPDATE-1 | Land both update branches with CI green | S | OS-UPDATER, OS-SECPIPE | as above | Both on `main`; CI green |
| W2-GW | Gateway wave 2: scan gate, app agent principals, `/mcp` with 3 tools, catalog fields (contract §11) | S | contract §11 (#12, done) | `core/onemind_core/{scan,mcp}.py`, `auth.py`, dashboard app page | CI green; agent approve → 403; `/mcp` lists exactly 3 tools; stale scan → 409 |
| W2-PIPE | App pipeline: scaffolder, app-gate (§9.4), `scan.json` (§11.1), k3d smoke, daily rescan | S | #12 | `sdk/tools/app-{gate,scaffold,readme}`, schema fields, `ci-apps.yml`, `renovate.json` | Gate passes the 3 seed apps; EICAR fixture blocked; each app gets a `scan.json` |
| W2-DEPLOY | Developer install: `install.sh --role hub` or `node`, compose dev hub, `verify.sh` | S | – | `deploy/**` | `install.sh` on a fresh Debian 13 VM reaches `/healthz`; `verify.sh` passes over HTTP and NATS |
| W2-HERMES | Hermes packaged as `apps/hermes-agent`, an agent principal (contract §7) | M | W2-GW, W2-PIPE, F-10 | `apps/hermes-agent/**` | Passes app-gate; Hermes's install request stays `awaiting_approval`; its approve → 403 |
| W2-SEEDS | Wave-2 seed apps (contract §8) | M | W2-PIPE | `apps/<id>/**` | Each passes app-gate and the k3d smoke test |
| PA-ALIGN | Core alignment against the leading self-hosted OSes | S | – | `docs/strategy/**` | Merged; every claim cites a primary source |
| PA-ARCH | Phase-B architecture docs and `CONTRACT-12-DRAFT.md` | S | PA-ALIGN | `docs/architecture/**` | Merged; the naming differences in DECISIONS-NEEDED §2 settled or recorded |
| PA-THREAT | Threat model and ranked hardening backlog (H-ids) | S | – | `docs/security/**` | Merged; leap links to H-ids resolve |
| PA-UI | Design system `@onemind/ui`: tokens and components, light and dark | M | – | `ui/**`, `docs/design/**` | Committed; builds; demo page renders both themes |
| PA-SITE | Website (Astro + Starlight) committed | S | – | `site/**` | `npm run build` green |
| PA-MOBILE | Mobile shell (Expo) committed | S | – | `mobile/**` | Tests pass; Android debug build runs |
| PLAN-E1 | Workbench (G0) and gate content re-synced to D-007 | S | – | `lab-kits/**`; gate rows in research 20 (founder) | G0 passes on 2026-11-22; redaction hook blocks a test tailnet name |
| LEAP-DOCS | Leap specs, workstreams, backlog, status, decisions, CHANGELOG | S | – | `docs/leap/**`, `CHANGELOG.md` | Merged; gitleaks clean |

## S1: contract §12, plumbing, sandbox, SDK/CLI/MCP foundations (weeks 1–5)

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| C12-A | Contract §12-a: conventions, error codes (`rate_limited`, `policy_refused`, `unavailable`), risk classes, `plan_sha256` on approve, `/v1/me`, `/v1/events`, action-type registry, scopes | S | PA-ARCH; DECISIONS-NEEDED §2 | `sdk/contracts/poc-v0.md` (hotspot) | Merged before any S1 feature PR that uses these names |
| C12-H | Contract §12-h: MCP additions (scopes in `spec.agent`, preview, withdraw) and CLI verbs | S | C12-A | contract, schema (hotspots) | Merged before DEV-MCP-2 |
| DEV-API-1 | Route inventory, conventions, `routes.py` registration seam | S | – | `core/onemind_core/routes.py`; one serialized edit of `app.py` | Every route in `/openapi.json` listed in API.md; features register via `routes.py` only |
| DEV-API-3 | Error model v1: `request_id`, `details`, opt-in new codes, size limits | S | API-1, C12-A | `errors.py`, `limits.py` | v0 clients still get `conflict` on 422; with `OneMind-Errors: 2` they get `invalid_request`; bodies over 256 KiB → 413 |
| DEV-SDK-1 | Spec readiness: response models, stable operation ids, open enums, spec export, committed `sdk/openapi/onemind-v1.json` | M | W2-GW, API-1 | `app.py` (hotspot), `openapi.py`, `core/tests/test_openapi_sdk.py`, `sdk/openapi/onemind-v1.json` | Every route has an `operationId` and a typed 2xx schema; a test fails otherwise |
| DEV-API-2 | OpenAPI compat gate (oasdiff) and `x-onemind` extension linter | S | API-1, SDK-1 | `sdk/openapi/compat/`, `api-compat.yml`, Makefile target | A deliberate breaking `/v1` change fails CI; every operation has scope, errors and example |
| DEV-SDK-2 | Generation toolchain and CI staleness check | M | SDK-1 | `sdk/Makefile`, `os/versions.lock.yaml` (add-only), `ci-sdk.yml` | Changing an Action field without regenerating fails CI; generator pins match the lock |
| DEV-API-4 | Pagination (Link), filters, ETag/If-Match, `Idempotency-Key` header | M | API-1, C12-A | `listing.py`, `idempotency.py` | No duplicate actions under 20 concurrent retries; a 2,500-item walk returns each once; v0 lists still return arrays |
| DEV-API-5 | Scopes, role defaults, `/v1/me`, step-up hook | M | API-1, API-3, C12-A | `scopes.py`, `auth.py` | Scope matrix green for every route × kind × role; upgraded boxes keep v0 read behaviour until enabled |
| CORE-SANDBOX-1 | Rule file and pure-Python checker with fixtures | S | – | `sdk/policy/**` | Every `bad-*` fixture refused; 3 seed apps pass |
| CORE-SANDBOX-2 | Gateway renders, checks and stores the plan; `apply -f -` with the checked bytes; `policy_refused`; `plan_sha256` on approve | M | SANDBOX-1, C12-A, W2-GW | `policy.py`, `executors.py` | ClusterRoleBinding fixture refused at approve; manifest edited between request and approve → 409 with the new plan; kubectl never called for a refused app |
| CORE-SANDBOX-3 | PSA `restricted` in the image and `install.sh` | S | W2-DEPLOY | `deploy/k8s/psa.yaml`, `os/rootfs/.../psa.yaml` | A privileged pod in `app-test` is refused for each forbidden field |
| CORE-SANDBOX-4 | Gateway RBAC, `ValidatingAdmissionPolicy`, short-lived bound token | M | SANDBOX-3 | `deploy/k8s/gateway-rbac.yaml` | Gateway cannot create pods in `kube-system`; token `exp` ≤ 24 h |
| CORE-SANDBOX-5 | Default-deny NetworkPolicy per app, host nftables, `spec.network.egress` | M | SANDBOX-2 | `executors.py`, `os/.../onemind.nft` | From an app pod, node ports 4222, 8080, 10250 and other apps time out; DNS and public HTTPS work |
| CORE-SANDBOX-6 | app-gate uses the same checker; `scan.json` gains `policy_version`, `rendered_sha256` | S | SANDBOX-1, W2-PIPE | `sdk/tools/app-gate` | CI and gateway give the same verdict on every fixture |
| CORE-AUTO-1 | Risk classes on action types, enforced in the approve path | S | C12-A | `action_types.py` (with API-7), `actions.py` hook | A policy covering a `sensitive`, `destructive` or `actuate` type → 422 |
| DEV-API-7 | Actions v1: risk, `plan_sha256` binding, preview, cancel, action-type registry, pending cap | M | API-5, SANDBOX-2, AUTO-1 | `actions.py`, `action_types.py` | No self-approval by any non-person kind; stale digest → 409; 11th pending → 429 |
| CORE-SEC-1 | HTTPS with a per-box CA, loopback-only HTTP, pairing QR | M | W2-DEPLOY, F-1 | `tls.py`, `config.py`, gateway systemd unit | Plain HTTP refused from the LAN; phone pins the CA from the QR |
| CORE-SEC-2 | Owner passkey, sessions, passkey-signed approvals (`approve-options`) | M | SEC-1, API-5, F-2 | `passkeys.py`, `sessions.py`, `SignIn.tsx` | A replayed approval without a fresh assertion fails; a stolen session cookie cannot approve |
| CORE-SEC-3 | Token lifecycle: create, rotate, expire, revoke, CLI | M | W2-GW | `tokens.py`, `ledger.py` token table, `cmd/onemind/cli/tokens.go` | Rotated token fails on the next request; secret shown once |
| CORE-SEC-4 | NATS nkeys and TLS | M | SEC-1 | `bus.py`, `internal/agent/agent.go`, `install.sh` | Anonymous NATS connect refused; node publishes only its own subject |
| CORE-SEC-6 | `onemind audit verify`, signed checkpoints, agent kill switch | S | SEC-3 | `audit.py`, `agents.py` | One changed byte fails at that seq; full rewrite caught by checkpoint; suspend → next MCP call 401 |
| CORE-SEC-7 | Pending cap, plan card fields, "written by agent" label | S | SANDBOX-2, API-7 | `actions.py` hook, card fields | 11th pending → 429 `rate_limited`; agent reason always labelled |
| CORE-SEC-8 | Signing keys in GitHub environments, split jobs | S | OS-SECPIPE | `security-nightly.yml` | Publish jobs need the protected environment; no key in non-publish steps |
| CORE-SEC-9 | CSP and security headers, body and rate limits | S | API-3 | `limits.py`, middleware | Header test passes on every route |
| DEV-API-6 | Tokens API and per-plugin tokens from the manifest's `spec.plugin` and `spec.permissions` (PLUGIN-SDK §4) | M | API-5, SEC-3 | `tokens.py` (after SEC-3), `ledger.py` migration | Non-person tokens with forbidden scopes refused (403/422); plugin token revoked on `app.remove` |
| DEV-API-8 | Events stream over SSE with resume and scope filtering | M | API-5, API-7 | `events.py` | `Last-Event-ID` resume without gap or duplicate; guests never get `audit.*`; `stream.reset` beyond the buffer |
| DEV-API-9 | Audit read, verify and signed off-box checkpoints | M | API-5, SEC-6 | `audit_api.py`, `audit.py` | One tampered line → `ok:false` with the right `first_bad_seq`; checkpoint verifies with the public key alone |
| DEV-SDK-3 | TypeScript `@onemind/sdk` core: client, auth, typed errors, retries, idempotency, wait by polling | M | SDK-2 | `sdk/ts/**` | Conformance, idempotency, ambiguous-approve and token-hygiene cases pass; no runtime deps; ≤ 15 kB gzipped |
| DEV-SDK-5 | Go SDK module | M | SDK-2 | `sdk/go/**`, `go.mod` (coordinate) | `go test` passes; no third-party modules; `errors.Is` works for every code |
| DEV-SDK-6 | Python `onemind-sdk`, sync and async | M | SDK-2 | `sdk/python/**` | T3–T7 pass; `from_env` works with the §11.2 agent Secret variables; deps only httpx and pydantic |
| DEV-SDK-8 | Shared conformance suite and mock gateway | M | SDK-3 | `sdk/conformance/**` | ≥ 25 cases identical in TS, Python, Go; agent approve 403, owner approve succeeds against the real gateway |
| DEV-CLI-1 | CLI skeleton: command tree, global flags, `--json`, exit codes, config; existing commands ported | M | SDK-5 (or a stub), F-8 | `cmd/onemind/main.go`, `cli/root.go` (hotspots), `cli/{output,exit,config,tty,features}.go` | Today's `main_test.go` passes; every §3 command has `--help`; exit-code tests cover 0–14 |
| DEV-CLI-2 | `login`, `logout`, `context`; keychain and 0600 file store; TLS pin | M | CLI-1, API-5 | `cli/{login,context,credentials}.go` | No secret in `config.yaml`; changed certificate exits 8 |
| DEV-CLI-3 | Read commands: `status`, `nodes`, `apps`, `actions`, `version` | S | CLI-2 | `cli/{status,nodes,apps,actions}.go` | Golden table and JSON tests; `status` shows `null` sections on a v0 box |
| DEV-CLI-4 | Action flow: install/remove, approve/deny/watch, `--wait`, effects display | M | CLI-3, API-7 | `cli/{apps,actions}.go` | Agent-token approve exits 4; approve without TTY exits 2; control characters in agent reasons stripped |
| DEV-CLI-5 | `audit verify` (file, gateway, checkpoint) and `audit tail` | M | CLI-1, API-9 | `cli/audit.go`, `sdk/testdata/audit/` | Shared vectors pass in Go and Python; one changed byte fails at that seq with exit 8 |
| DEV-CLI-13 | Completion, generated reference and man pages, signed releases, image pin | M | CLI-1 | `cli/completion.go`, `docs/cli/`, lock (hotspot) | Completion loads in 4 shells; `docs/cli` regenerates with no diff; release has cosign signature, SBOM, checksums |
| DEV-MCP-1 | Read catalogue v1 and resources; `mcp.py` becomes the `mcp/` package; pagination and caps | M | W2-GW, API-5 | `core/onemind_core/mcp/**`, `core/tests/test_mcp.py` | Each read tool equals its REST body; zero secrets in any output |
| DEV-MCP-2 | Per-agent scopes and grants, filtered `tools/list`, pause and revoke on `/mcp` | M | MCP-1, SEC-3, C12-H | `grants.py`, `mcp/**` | Reader sees no `request_action`; revoke → 401, pause → 403 |
| DEV-MCP-4 | Rate limits per principal and the pending cap | S | MCP-2 | `ratelimit.py` | 61st read/min → `rate_limited`; 11th pending → `rate_limited`; 121st message/min → HTTP 429 |
| DEV-MCP-7 | `onemind mcp` stdio bridge with login (keychain, CA pin), `doctor`, client configs | M | MCP-1, SEC-1 | `internal/mcpbridge/**`, `cli/mcp.go` | 1,000 messages in order; 401 → JSON-RPC error and stderr hint; token never logged |
| DEV-CLI-12 | `onemind mcp` acceptance (built as DEV-MCP-7) | – | MCP-7 | – | Official MCP SDK client over stdio sees the principal's tools; person credential exits 4 |
| CORE-DASH-1 | `ui/` components v0 and dark mode | M | PA-UI | `ui/**` | axe 0 serious/critical in light and dark |
| CORE-DASH-3 | Approvals plan card with passkey approve | M | DASH-1, SANDBOX-2, SEC-2 | `dashboard/src/pages/Approvals.tsx`, components | Plan changed between load and approve → refresh prompt; agent reason in the labelled block |
| CORE-DASH-4 | Activity (audit) and Agents (suspend) screens | S | DASH-1, SEC-6 | `dashboard/src/pages/{Activity,Agents}.tsx` | Suspend from the screen → next MCP call 401 |
| DEV-MCP-5 | Prompt-injection defences: `<untrusted>` marking, `AgentNote` on the approval card, fixtures | M | MCP-1, DASH-3 | `mcp/untrusted.py`, `AgentNote.tsx` (dashboard owner) | Injected description and reason stay pending and render as "not checked"; `</untrusted>` and bidi cannot escape |
| CORE-UPDATE-2 | Local socket, `/v1/os/*`, `os.update` and `os.rollback` actions | M | UPDATE-1, SEC-2 | `os_updates.py`, `internal/update/api.go` | Stable update under `policy notify` waits for approval; nothing installs before it |
| CORE-UPDATE-4 | Metal runs for G1 on the x86 mini PC; start the Pi soak | L | UPDATE-1, PLAN-E1 | lab kits, `os/**` | LT-X86-01/02; rollback 10/10; 20/20 power pulls bootable; Pi soak started by 2026-12-11 |
| DEV-CLI-6 | `update status/check/apply` via the onemindd socket on the box, `os.update` action remotely | M | UPDATE-2 | `cli/update.go` (moved from `cmd/onemind/update.go`) | CLI no longer drives RAUC in-process; remote apply creates an `os.update` action |
| DEV-CLI-14 | Headless local context over the onemindd socket with peer-uid check | M | CLI-6 | `cli/local.go` | As root with k3s stopped, `status`, `update status`, `audit verify --file` work; non-root exits 4 |
| PLAN-E6 | Manifest v1 freeze: merge with research 29 §6, converter, one validator | M | W2-PIPE, SANDBOX-6 | schema (hotspot), `sdk/tools/**` | All apps validate; an update that widens grants is rejected |
| PLAN-E5 | App factory: 15 apps by week 6, 30 by week 13, trust cards | L | W2-PIPE, W2-SEEDS | `apps/**`, `sdk/tools/**` | Every verified app scanned in the last 7 days; EICAR and PolyForm-NC blocked |
| CORE-WEB-1 | Commit `site/`, CI build, link check, axe, deploy to GitHub Pages | S | PA-SITE, F-5 | `site/**`, `site.yml` | 0 broken links; axe clean; redaction grep clean |

## S2: fabric, backups, notifications, dashboard redesign, mobile v1 (weeks 5–9)

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| C12-B | Contract §12-b: fabric routes, heartbeat `fabric` | S | C12-A | contract (hotspot) | Merged before FABRIC-1 |
| C12-D | Contract §12-d: backups, manifest `backup:`, heartbeat `backup` | S | C12-A | contract, schema | Merged before BACKUP-5 and BACKUP-8 |
| C12-E | Contract §12-e: notifications, activity, repairs | S | C12-A | contract | Merged before NOTIFY-1 |
| C12-G | Contract §12-g: approval challenge and iOS relay contract | S | C12-A, SEC-2 | contract | Merged before NOTIFY-4 |
| CORE-SEC-5 | LUKS2 data, k3s secrets encryption, WireGuard pod traffic | M | image stream | `os/boards/*`, `os/assemble/**` | Data partition encrypted on every board; secrets encrypted at rest in k3s |
| CORE-SEC-10 | Identity floor: on-box IdP, roles, retire v0 tokens | L | SEC-2 | `core/onemind_core/**` identity modules | Denied → 403 and an audit line; offline login works; guest cannot approve |
| CORE-FABRIC-1 | `node.join` action, join tickets and requests, `onemind fabric join`, QR in the dashboard (includes DEV-API-10) | M | SEC-1, SEC-2, SEC-4, API-7, C12-B, W2-DEPLOY | `fabric.py`, `internal/join/**` | 3 machine classes join in under 2 min; expired or reused ticket refused; no credentials without approval |
| DEV-API-10 | Fabric route shapes (built inside FABRIC-1) | – | FABRIC-1 | – | Codes single-use, CA-bound, rate-limited |
| CORE-FABRIC-2 | Per-node identity (nkey, cert, principal) and revocation | M | FABRIC-1 | `internal/join/**`, `fabric.py` | Node A cannot publish as node B |
| CORE-FABRIC-3 | `node.remove` with drain | S | FABRIC-2 | `fabric.py` | Remove is `destructive`: owner tap and step-up |
| CORE-FABRIC-4 | Capability labels, affinity from `requires`, Market verdict | M | W2-GW | `internal/detect/**`, `executors.py`, `Market.tsx` | An amd64-only app is never placed on an arm64 node |
| CORE-FABRIC-5 | Leaf mode in onemindd (no k3s) | M | FABRIC-2 | `internal/leaf/**` | Hub offline 30 min → no loss of buffered leaf events |
| CORE-NET-1 | Headscale adapter (`Coordinator` interface) and config/DERP-map renderer (Part 1; may start in S1) | M | – | `internal/mesh/coord/**` | Golden configs have `derp.urls: []`; adapter passes against a fake `headscale` |
| CORE-NET-2 | Mesh policy generated from OneMind roles | S | – | `internal/mesh/policy/**` | Golden policies; leaf → hub 443/7422 only; devices → hub 443 only |
| CORE-NET-3 | Node mesh enrollment and LAN-first coordinator resolver | M | NET-1 | `internal/mesh/{enroll,resolve}/**` | Auth key read from a file and deleted; resolver picks the LAN hub only with the pinned CA |
| CORE-NET-4 | NATS hub users + leaf listener and node leaf config renderers | M | – | `internal/natsconf/**` | In-process nats-server: node A cannot publish as B; leaf without node cert refused |
| CORE-NET-5 | `onemind-edge`: SNI/host routes, forward-auth, upgrades, optional ACME | M | – | `internal/edge/**`, `cmd/onemind-edge/` | No session → sign-in redirect; unknown SNI closed; spoofed principal header stripped |
| CORE-NET-6 | LAN names: avahi hosts, conflict check, mesh extra records | S | – | `internal/lan/**` | Conflict on `onemind.local` falls back to `<box>.local` and raises `lan.name_conflict` |
| CORE-NET-7 | Relay: SNI router, setup endpoint, WireGuard link renderer, pinned derper build | M | – | `internal/relay/**`, `cmd/onemind-relay/`, `third_party/derper/` | Only allowed SNI names forwarded; derper runs with fail-open off |
| CORE-NET-8 | Gateway mesh routes, forward-auth endpoint, routes writer, `mesh.*` handlers (unregistered) | M | NET-2 | `core/onemind_core/{mesh,forward_auth}.py` | Unit tests; agent cannot request `mesh.device.add` |
| CORE-NET-9 | Lima lab NT-1…NT-8, NT-17 (preregistered) | M | NET-1…7 | `research-output/evidence/lab/net-mesh/` | Results committed with masked addresses; VMs deleted |
| CORE-NET-10 | Contract §12.16 networking PR | S | NET-9 | `sdk/contracts/poc-v0.md` | Merged; streams adopt |
| CORE-NET-11 | Installer and image wiring: pins, packages, units, hub bootstrap order, k3s on mesh + `wireguard-native`, NATS leaf | M | NET-10, W2-DEPLOY, SEC-1 | `deploy/**`, `os/**` | NT-1, NT-3, NT-8 pass on fresh Debian 13 VMs |
| CORE-NET-12 | Gateway + onemindd registration; join bundle `mesh`; remove/set_role hooks | M | NET-10, FABRIC-1, W2-GW | `app.py`, `actions.py`, `cmd/onemindd/main.go` | NT-3, NT-4, NT-16 pass |
| CORE-NET-13 | Dashboard Network page, Add a device, relay pairing, app links | M | NET-12 | `dashboard/**` | No IP shown by default; app links open `https://<app>.onemind.local` |
| CORE-NET-14 | Pi budget, pod throughput and phone/mDNS/CA matrix on hardware | S | NET-11, F-25 | lab evidence | NT-9…NT-14 recorded; budgets met or escalated |
| CORE-NET-15 | Public app exposure through the relay | – | CORE-DOGFOOD-3 | – | parked |
| DEV-CLI-8 | `fabric qr/join/leave/remove` and `node join` alias | M | FABRIC-1 | `cli/fabric.go` | A VM joins in under 2 min from `fabric qr`; QR has no network details beyond the hub name |
| CORE-BACKUP-1 | `onemind-local` Retain StorageClass as default | S | W2-DEPLOY | image, `install.sh` | Deleting a PVC keeps its data |
| CORE-BACKUP-2 | `internal/backup` agent: restic, schedule, three keys, emergency kit | L | BACKUP-1, SEC-5 | `internal/backup/**` | The printed owner key restores without the device key |
| CORE-BACKUP-3 | k3s datastore online backup with integrity gate | M | BACKUP-2 | `internal/backup/**` | Datastore restores and passes the integrity check |
| CORE-BACKUP-4 | Destinations: USB, another OneMind box (append-only), S3 | M | BACKUP-2 | `internal/backup/**` | The source box cannot forget snapshots off-site |
| CORE-BACKUP-5 | Manifest `backup:` hooks | M | BACKUP-2, C12-D, PLAN-E6 | schema (hotspot), `internal/backup/**` | Each seed app's hook produces a consistent dump |
| CORE-BACKUP-6 | Restore file, app or box, approval-gated; restore at onboarding | M | BACKUP-2, BACKUP-3, API-7 | `internal/backup/**`, `backups.py` | Fresh-VM restore with identical data; an agent restore stays `awaiting_approval` |
| CORE-BACKUP-7 | Verified-restore badge (daily check, weekly scratch restore) | M | BACKUP-6 | `internal/backup/**` | Clock +7 days without a verified restore → badge red and one alert |
| CORE-NOTIFY-1 | Alert record and store, `/v1/alerts`, NATS subjects, in-app inbox (includes DEV-API-12) | M | API-5, C12-E | `alerts.py`, `notify/**` | One alert each for a pending approval, an offline node and a stale backup; dedupe holds |
| DEV-API-12 | Notifications route shapes (built inside NOTIFY-1) | – | NOTIFY-1 | – | Plugin send limited to `plugin.<app-id>` topics; channel secrets never returned |
| CORE-BACKUP-8 | Backups API, screen and alerts (includes DEV-API-11) | S | BACKUP-2, DASH-1, NOTIFY-1, C12-D | `backups.py`, `Backups.tsx` | No credentials in any response |
| DEV-API-11 | Backups and restores route shapes (built inside BACKUP-8) | – | BACKUP-8 | – | Agent can request run/verify/restore, never approve |
| DEV-CLI-7 | `backup status/list/now/verify` and `restore` | M | BACKUP-8 | `cli/backup.go` | `restore` needs typed confirmation and owner approval; safety snapshot id printed |
| CORE-NOTIFY-2 | Sources: approvals, nodes, updates, backups, scans, audit (H-28) | S | NOTIFY-1 | `alerts.py`, emitters | Expired TUF timestamp + 48 h → one alert |
| CORE-NOTIFY-3 | Web Push and Android UnifiedPush via the box's ntfy; push registrations | M | NOTIFY-1, SEC-1 | `notify/**` | Push payloads hold only `alert_id` and `box_id` |
| CORE-NOTIFY-4 | iOS APNs relay (built with MOBILE-5) | M | NOTIFY-3, C12-G, F-4 | `relay/**` | Apple payload holds ids only |
| CORE-NOTIFY-5 | Repairs with fix actions | M | NOTIFY-1 | `repairs.py` | Each fix is a request; nothing changes without approval |
| CORE-NOTIFY-6 | Email, webhook, Matrix, Telegram channels; routing and quiet hours | S | NOTIFY-1 | `notify/**` | `notify test` reports per-channel delivery |
| CORE-UPDATE-3 | Updates screen and "What's new" | S | UPDATE-2, DASH-1 | `Updates.tsx` | Shows rollback reason after a failed trial |
| CORE-UPDATE-5 | App updates through approval (catalog diff, `app.update`) | M | SANDBOX-2 | `app_updates.py` | An update that widens grants needs a fresh approval |
| CORE-UPDATE-6 | Health-gated app updates with snapshot and revert | M | UPDATE-5, BACKUP-2 | `app_updates.py`, app-gate probes | Failing probe reverts, restores the snapshot, alert names the probe |
| CORE-UPDATE-7 | Offline grace and USB/LAN mirror installs | M | UPDATE-1 | `internal/update/**` | Install from a USB mirror verifies with TUF offline |
| CORE-UPDATE-8 | Rescue console in onemindd | M | SEC-1 | `internal/rescue/**` | With k3s stopped, the rescue page lists slots and rolls back |
| CORE-DASH-2 | Move the 5 existing screens onto `@onemind/ui` | S | DASH-1 | `dashboard/src/pages/*` | Existing dashboard tests pass |
| CORE-DASH-5 | Alerts, Updates and Backups screens | M | NOTIFY-1, UPDATE-2, BACKUP-8 | one page file each | Stale data never shown as live |
| CORE-DASH-7 | PWA and per-app subdomain launcher | M | SEC-1, NOTIFY-3 | `dashboard/**` | Installs on Android Chrome over HTTPS with the box CA; Web Push received |
| CORE-DASH-8 | Typed widgets on Home; "show the equivalent call" toggle | M | DASH-1 | `dashboard/**` | Each shown CLI/API call creates the same action |
| DEV-SDK-4 | Dashboard and mobile moved onto `@onemind/sdk` | M | SDK-3, PA-MOBILE | `dashboard/src/api/**`, `mobile/src/api/**` | Both test suites pass with the hand-written clients deleted |
| DEV-SDK-7 | SSE in all three SDKs, polling fallback, React Native transport | L | SDK-3, SDK-5, SDK-6, API-8 | `sdk/*/events*`, `sdk/openapi/events-v1.json` | Resume loses no events; 45 s without keepalive reconnects; reset surfaced |
| CORE-MOBILE-1 | Shell on the generated `sdk/ts`; icon and splash | S | PA-MOBILE, SDK-3 | `mobile/**` | Builds for Android and iOS |
| CORE-MOBILE-2 | QR pairing with CA pinning, HTTPS only | M | MOBILE-1, SEC-1 | `mobile/**` | A box with a different CA at the same URL is refused |
| CORE-MOBILE-3 | Passkey sign-in and signed approvals; plan card | M | MOBILE-2, SEC-2, SANDBOX-2 | `mobile/**` | Approve under 10 s on a real Android phone; replayed link fails |
| CORE-MOBILE-4 | Android UnifiedPush | M | NOTIFY-3 | `mobile/**` | Push arrives with the app closed in < 5 s on the LAN |
| CORE-MOBILE-5 | iOS service extension and relay registration (with NOTIFY-4) | M | NOTIFY-4, F-4 | `mobile/**` | Extension shows fetched text; payload holds ids only |
| CORE-MOBILE-6 | Alerts and Activity tabs, offline cache, checkpoint store | M | NOTIFY-1, SEC-6 | `mobile/**` | Offline view labelled with its age; approve disabled offline |
| CORE-NOTIFY-7 | Actionable notifications open the approval card | S | NOTIFY-3, MOBILE-3 | `notify/**`, mobile | Tap → card → passkey approve under 10 s |
| DEV-MCP-3 | Request-only writes: `withdraw_request`, `preview_action`, `plan_sha256`, never-requestable list | M | MCP-2, SANDBOX-2 | `mcp/**` | No path from `/mcp` to approve or deny; stale `plan_sha256` → 409 |
| DEV-MCP-6 | MCP audit entries, read summaries, trace context, audit tools | S | SEC-6, MCP-1 | `mcp/**` | Each request, withdraw and denial is one chained entry |
| DEV-MCP-8 | Conformance CI with official TS, Python, Go clients and the bridge | M | MCP-1, MCP-7 | `test/mcp-conformance/**` | All three clients pass direct and via the bridge |
| DEV-MCP-9 | MCP revision 2025-11-25 and the `versions.py` adapter split | S | MCP-8 | `mcp/versions.py` | Negotiates 2025-11-25; unknown version handled per spec |
| DEV-MCP-11 | Prompts, `onemind://docs`, `llms.txt`, `search_docs`, status tools | S | MCP-1 | `mcp/catalog.py` | Every gateway error code has a docs page |
| CORE-WEB-2 | Generated references: CLI, API, schema, errors | M | SDK-1, CLI-13 | `site/scripts/gen-*.mjs` | References rebuild from the spec with no hand edits |
| CORE-WEB-3 | Apps catalog with scan history | S | W2-PIPE | `site/**` | Changing a `scan.json` changes that app's page on the next build |
| PLAN-E10 | Pi 5 image (G2): RAUC + tryboot, signed image, wizard | L | PLAN-E1, UPDATE-4 | `os/**` | LT-PI5-01; flash to dashboard < 15 min; G2 on 2026-12-27 |

## S3: automation, plugin SDK v0, website launch, dogfood migration (weeks 9–13)

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| C12-C | Contract §12-c: deployments, manifest `health`, `settings`, `secrets`, `migrations` | S | C12-A | contract, schema | Merged before DEPLOY-1 |
| C12-F | Contract §12-f: automation | S | C12-A | contract | Merged before AUTO-2 |
| C12-PLG | Contract plugins amendment: `kind: plugin`, `plugin.invoke`, `plugin.configure`, manifest `extensions` | S | C12-A, PLAN-E6 | contract, schema | Merged before PLG-1 |
| CORE-AUTO-2 | Scheduler and event/webhook triggers that create actions (includes DEV-API-13 rules) | M | AUTO-1, NOTIFY-1, C12-F | `automation.py` | Bad webhook HMAC → 401; replay > 5 min → 401 |
| CORE-AUTO-3 | Standing approvals with ledger-counted limits | M | AUTO-1, SEC-2 | `policies.py` | 4th restart under a max-3 policy waits for approval; count survives a restart |
| CORE-AUTO-4 | Dry run, CLI (`auto`, `policy`) and Automations page | S | AUTO-2, AUTO-3 | `cli/{auto,policy}.go`, `Automations.tsx` | Dry-run output equals the first real firing |
| CORE-AUTO-5 | Failure and recovery notifications, repairs hook-up | S | AUTO-2, NOTIFY-5 | `automation.py` | A failing automation raises one alert with a fix |
| DEV-API-13 | Automation and OS update route shapes (built inside AUTO-2 and UPDATE-2) | – | AUTO-2, UPDATE-2 | – | Rules only request; destructive types rejected; `os.update.apply` reports the booted verdict |
| DEV-CLI-9 | `notify test`, `tokens list/create/revoke`, `rules` alias | M | NOTIFY-1, AUTO-2, SEC-3 | `cli/{notify,tokens}.go` | Token printed once, never listed; a rule that requests a `destructive` type refused (422) |
| CORE-DASH-6 | Settings (sessions, tokens, pairing) and Automations screens | M | SEC-2, SEC-3, AUTO-4 | `dashboard/src/pages/Settings*.tsx` | Revoke from Settings → that token fails at once |
| CORE-DEPLOY-1 | `onemind deploy` (kustomize, Helm, Compose) → private app | M | SANDBOX-2, C12-C | `deploys.py`, `cli/deploy.go` | Forbidden object in a private app refused like a Market app |
| CORE-DEPLOY-2 | On-box scan Job bound to digests | M | DEPLOY-1, W2-PIPE | `scanjob.py` | Approve of an unscanned private app → 409 |
| CORE-DEPLOY-3 | Revisions, history and rollback | M | DEPLOY-1 | `deploys.py` | r3 → r2 restores r2's digests; audit shows both actions |
| CORE-DEPLOY-4 | Write-only secrets | S | SEC-5 | `deploys.py`, `cli/secret.go` | No route returns a secret value; agent gets 403 on `secret set` |
| CORE-DEPLOY-5 | Watched Git source with a diff card | M | DEPLOY-3, AUTO-2 | `deploys.py` | A new commit creates one pending action with a non-empty diff |
| CORE-DEPLOY-6 | Migration kit (`onemind migrate check/import/pin`) | M | DEPLOY-1 | `cli/migrate.go` | Generic fixtures import on k3d |
| DEV-CLI-10 | `app scaffold/validate/gate/dev`, one validator shared with Python | L | W2-PIPE, PLAN-E6 | `cli/appdev.go`, `sdk/testdata/manifests/` | Go and Python validators agree on every fixture; `validate` < 10 s |
| DEV-PLG-1 | Manifest `extensions`, `permissions`, `plugin`, `compat` + Go validator | M | C12-PLG, PLAN-E6 | schema (hotspot), `internal/plugin/validate/` | Hello manifest validates; each P-rule has a failing fixture |
| DEV-PLG-2 | TypeScript `@onemind/plugin` (server and widget) | M | PLG-1 | `sdk/plugin-ts/` | Dispatch-token verification and write guard unit-tested |
| DEV-PLG-3 | Gateway plugin registry, `kind: plugin` principal, `/v1/plugins/*` | M | PLG-1, W2-GW, SANDBOX-2 | `plugins.py`, one `routes.py` line | A plugin write call yields `awaiting_approval` over REST |
| DEV-PLG-4 | Tool projection to `/mcp` and the CLI | S | PLG-3, MCP-1 | `mcp/catalog.py`, `cli/plugin.go` | Hermes write call over MCP → `awaiting_approval` |
| DEV-PLG-5 | Widget host: typed templates, sandboxed iframe, postMessage bridge, CSP | L | PLG-3, DASH-1 | `dashboard/src/plugins/**` | A widget cannot reach the gateway token or the parent DOM |
| DEV-PLG-6 | Settings panel (JSON Schema form) and secrets API | S | PLG-3, PLG-5 | `Settings.tsx`, `plugins.py` | Settings round-trip to backend and widget |
| DEV-PLG-7 | OCI pack, private-tier signing, install by digest, `plugin verify` | M | PLG-1 | `cli/plugin.go`, `internal/plugin/{oci,verify}/` | Tag, wrong digest, unsigned, wrong signer refused |
| DEV-PLG-8 | `onemind plugin dev` (mock hub, harness, hot reload) and `init` templates | M | PLG-2, PLG-5, PLG-7 | `internal/plugin/dev/`, `sdk/templates/plugin-hello/` | Hello widget working against `--mock` in < 15 min on a clean Mac |
| DEV-PLG-9 | Revocation list client (phase 1); TUF delegation and countersignature (phase 2) | L | PLG-7, OS-UPDATER | `internal/plugin/verify/` | Revoked plugin disabled within one fetch; calls rejected within 60 s |
| DEV-CLI-11 | `plugin init/dev/pack` acceptance (built as PLG-7, -8; `publish` is accepted with PLG-14 in S4+) | – | PLG-7, PLG-8 | – | `pack` output verifies with cosign; `init` to a working widget in < 15 min |
| CORE-UPDATE-9 | Fleet-staged updates | M | UPDATE-2, FABRIC-1 | `os_updates.py` | A failing first node halts the rollout |
| CORE-FABRIC-6 | Read-only fleet view | S | FABRIC-1, UPDATE-3, BACKUP-7 | dashboard | Screenshot holds no IP, MAC or serial |
| CORE-MOBILE-7 | Store releases (TestFlight, Play internal → public) with privacy labels | S | MOBILE-1…6, F-3 | `mobile/**` | Both store builds install from the store track |
| DEV-SDK-9 | Publish to npm, PyPI and the Go proxy with trusted publishing and provenance | S | SDK-3, SDK-5, SDK-6, SDK-8, SEC-1, F-17 | `sdk-release.yml` | Packages install in fresh Node 20, Python 3.11, Go containers; no long-lived registry tokens |
| DEV-SDK-10 | API reference and quickstarts on the website | S | SDK-9, WEB-2 | `site/src/content/docs/api/**` | From `npm install` to listing nodes in < 5 min using only the README |
| CORE-WEB-4 | GitHub Discussions and giscus (click-to-load) | S | WEB-1, F-5 | `site/**` | Comments load only after a click |
| CORE-WEB-5 | Blog and launch posts L1/L2/L3 | S | WEB-1 | `site/**` | Every landing claim links to a passing test |
| CORE-DOGFOOD-1 | `onemind doctor --wave N` gate checker | S | – | `cli/doctor.go`, `internal/doctor/**` | Prints pass/fail per gate row |
| CORE-DOGFOOD-2 | Migration fixtures and docs | M | DEPLOY-6 | `internal/doctor/**`, docs | Generic fixture migrations pass on k3d |
| CORE-DOGFOOD-3 | Remote access app and exposure review | M | SEC-1 | `apps/tailscale` or `apps/headscale`, `exposure.py` | Reach the box over LTE with no router changes |
| CORE-DOGFOOD-4 | Per-app metrics and logs; metrics stack as a Market app | M | DASH-1 | `metrics.py`, `AppDetail.tsx` | Logs tab shows the last 1,000 lines per app |
| CORE-DOGFOOD-5 | GPU enablement (toolkit, device plugin, placement) | M | FABRIC-4, image stream | `os/**`, `internal/detect/**` | A GPU app lands only on a GPU node |
| CORE-DOGFOOD-6 | Run migration waves 0–5; log gaps against the owning spec | L | all core epics per wave gate | issues, `docs/leap/core/DOGFOOD.md` | Each wave entered only when its gate passes; 30 days of daily use without a manual SSH fix |
| PLAN-E11 | Jetson and platform floor (G3) | L | PLAN-E10 | `os/**`, lab kits | LT-JET-01/02 or the fail branch; G3 on 2027-01-10 |

## S4+: phase 2 and parked

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| DEV-PLG-10 | Gateway-mediated plugin events, alerts with actions, automation triggers | M | PLG-3, NOTIFY-1, AUTO-2 | `plugin_events.py` | An alert action creates an action that needs approval |
| DEV-PLG-11 | Plugin data volume and backup hooks | S | PLG-3, BACKUP-5 | `plugins.py` install hook | Hello data restores onto a fresh VM |
| DEV-PLG-12 | Scan gate for plugin artifacts | M | PLG-7, W2-PIPE | app-gate extension, `ci-plugins.yml` | EICAR in a UI bundle blocked; stale scan → 409 |
| DEV-PLG-13 | Testing harness (TS, Python, Go) and `onemind plugin test` | M | PLG-2, PLG-8 | `sdk/plugin-*`, `internal/plugin/conformance/` | Hello passes conformance in all three languages |
| DEV-PLG-14 | Publish from CI (OIDC), public plugin index, review checklist, Market tiers | M | PLG-9, PLG-12 | `cli/plugin.go`, index repo, `Market.tsx` | A third-party test plugin goes from tag to installable in < 1 day; `onemind plugin publish` outside CI exits 4 (DEV-CLI-11) |
| DEV-PLG-15 | Mobile plugin cards (typed templates, native) | S | PLG-5, MOBILE-1, F-3 | `mobile/src/plugins/` | Cards render on Android and iPhone |
| DEV-PLG-16 | Plugin docs: tutorial, reference, bridge spec, also over MCP | S | PLG-8, PLG-13 | `site/**`, `dev/PLUGIN-SDK.md` | A new developer completes the Hello tutorial from the website alone |
| DEV-MCP-10 | MCP revision 2026-07-28: discover, stateless calls, tasks for approval waits | L | MCP-9 | `mcp/{versions,transport}.py` | Conformance passes for 2026-07-28; approval still only out of band |
| DEV-MCP-12 | OAuth façade: RFC 9728 metadata, audience-bound tokens, browser login in the bridge | L | SEC-10 | `mcp/transport.py`, `internal/mcpbridge/` | MCP conformance auth scenarios pass |
| CORE-WEB-6 | Self-host the site on OneMind; Discourse forum | M | DOGFOOD gates | `site/**`, an app | Site served from a OneMind box |
| PH2-DESKTOP | Desktop shell and module host (research 12, D-003) | L | DASH-8, PLG-5 | spec to be written | Spec merged first |
| PLAN-E7-LAB | Typed capabilities and actuation behind the lab flag | L | AUTO-1, PLAN-E6 | spec to be written | Release build refuses the lab flag; actuate never auto-approves; released only after LT-VM-18 |
| PLAN-E14 | TAK field kit preview | L | PLAN-E5, PLAN-E7-LAB, PLAN-E10 | parked by founder focus | – |
| PLAN-E15 | Robot in simulation | XL | PLAN-E7-LAB | parked | – |
| DEV-API-14 | Superseded by DEV-SDK-1…10 | – | – | – | – |
