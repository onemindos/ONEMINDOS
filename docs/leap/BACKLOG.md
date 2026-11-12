<!-- SPDX-License-Identifier: Apache-2.0 -->
# Leap backlog: every epic, in build order

**Date:** 2026-11-12 · Part of [the leap](README.md). State per epic: [STATUS.md](STATUS.md). Owners and hotspots: [WORKSTREAMS.md](WORKSTREAMS.md).

> **Explain it like I am the founder**
> This is the whole to-do list in one place, in the order it can be built. Nothing appears before the things it depends on.
> Sprints: **S0** lands what is already half-done; **S1** lays the plumbing (contract §12, sandbox, security, SDK/CLI/MCP foundations); **S2** builds fabric, backups, notifications, the new dashboard and phone apps; **S3** adds automation, plugin SDK v0, the website launch and moving your own services over; **S4+** is phase 2 and the parked items.
> Each row says when it counts as done (acceptance). The detail behind each row is in the linked spec.

**Effort:** S ≤ 1 day, M 2–4 days, L 1–2 weeks, for one builder with an agent. **Sprint dates** assume the 90-day plan (Day 1 = 2026-11-16) and about 23 build hours a week: S0 weeks 0–2, S1 weeks 1–5, S2 weeks 5–9, S3 weeks 9–13, S4+ after 2027-02-14. Sprints overlap at the edges; dependencies, not dates, decide what starts.

**Spec keys:** SANDBOX, SEC, FABRIC, BACKUP, DEPLOY, AUTO, NOTIFY, UPDATE, DASH, MOBILE, WEB, DOGFOOD are in [`core/`](core/README.md); API, SDK, CLI, MCP, PLG are in [`dev/`](README.md#4-every-spec). Ids without a prefix in "Depends on" refer to the same spec family (for example `SEC-2` = CORE-SEC-2). "F-n" are founder decisions in [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md). `UMB-<area>-n` rows come from the umbrelOS 2 studies in [`docs/umbrel2/`](../umbrel2/README.md) and are listed in their own section at the end, by sprint. Rows added on 2026-11-12 for streams that started without a row, and for gaps found in merged work, are in [their own section](#added-2026-11-12-streams-and-epics-missing-from-the-board) just before the UMB rows.

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
| DEV-API-8 | Events stream over SSE with resume and scope filtering (+ UMB-SYS-3) | M | API-5, API-7 | `events.py` | `Last-Event-ID` resume without gap or duplicate, also in a 1,000-event burst; owner sees `onemind.os.*` within 1 s; guests never get `audit.*`; `stream.reset` beyond the buffer |
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
| DEV-MCP-2 | Per-agent scopes and grants, filtered `tools/list`, pause, pause-all and revoke on `/mcp`; rights = owning person ∩ grant (+ UMB-AGT-2) | M | MCP-1, SEC-3, C12-H | `grants.py`, `mcp/**`, `agents.py` and `tokens.py` via security | Reader sees no `request_action`; revoke → 401, pause → 403; pause-all keeps pending requests visible; adults see only their own agents; tokens stored as sha256 only |
| DEV-MCP-4 | Rate limits per principal and the pending cap | S | MCP-2 | `ratelimit.py` | 61st read/min → `rate_limited`; 11th pending → `rate_limited`; 121st message/min → HTTP 429 |
| DEV-MCP-7 | `onemind mcp` stdio bridge with login (keychain, CA pin), `doctor`, client configs | M | MCP-1, SEC-1 | `internal/mcpbridge/**`, `cli/mcp.go` | 1,000 messages in order; 401 → JSON-RPC error and stderr hint; token never logged |
| DEV-CLI-12 | `onemind mcp` acceptance (built as DEV-MCP-7) | – | MCP-7 | – | Official MCP SDK client over stdio sees the principal's tools; person credential exits 4 |
| CORE-DASH-1 | `ui/` components v0 and dark mode | M | PA-UI | `ui/**` | axe 0 serious/critical in light and dark |
| CORE-DASH-3 | Approvals plan card with passkey approve | M | DASH-1, SANDBOX-2, SEC-2 | `dashboard/src/pages/Approvals.tsx`, components | Plan changed between load and approve → refresh prompt; agent reason in the labelled block |
| CORE-DASH-4 | Activity (audit) and Agents (suspend) screens | S | DASH-1, SEC-6 | `dashboard/src/pages/{Activity,Agents}.tsx` | Suspend from the screen → next MCP call 401 |
| DEV-MCP-5 | Prompt-injection defences: `<untrusted>` marking, `AgentNote` on the approval card, fixtures | M | MCP-1, DASH-3 | `mcp/untrusted.py`, `AgentNote.tsx` (dashboard owner) | Injected description and reason stay pending and render as "not checked"; `</untrusted>` and bidi cannot escape |
| CORE-UPDATE-2 | Local socket, `/v1/os/*`, `os.update` and `os.rollback` actions (+ UMB-SYS-1) | M | UPDATE-1, SEC-2 | `os_updates.py`, `internal/update/api.go` | Stable update under `policy notify` waits for approval; nothing installs before it; UMB-SYS-1: apply with a `target_digest` that no longer matches the selected TUF target → 409 `stale_precondition`, nothing installed |
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
| CORE-SEC-5 | LUKS2 data as btrfs (`@`, `@storage`, `@snapshots`), k3s secrets encryption, WireGuard pod traffic (+ UMB-STOR-1) | M | image stream, UMB-STOR-0 | `os/boards/*`, `os/assemble/**`, `os/rootfs/packages/*` | Data partition encrypted on every board; QEMU: `/data` is btrfs on dm-crypt with the three subvolumes and TPM2 plus recovery key slots; secrets encrypted at rest in k3s |
| CORE-SEC-10 | Identity floor: on-box IdP (Kanidm host service), roles, sessions, retire v0 tokens (+ UMB-ACCT-3) | L | SEC-1, SEC-2, UMB-ACCT-1, UMB-ACCT-2 | `core/onemind_core/{identity,sessions}.py`, one migration | Denied → 403 and an audit line; offline login works with k3s stopped; guest cannot approve; login after a concurrent credential reset fails; 6th failed login in 15 min delayed; revoked session's WebSocket closed within 1 s |
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
| CORE-BACKUP-6 | Restore file, app or box, approval-gated; restore at onboarding; move to new hardware (+ UMB-SYS-9) | M | BACKUP-2, BACKUP-3, API-7, UMB-CLIENT-1 | `internal/backup/**`, `backups.py` | Fresh-VM restore with identical data; an agent restore stays `awaiting_approval`; hub identity restored and nodes re-find the hub by mDNS and the pinned CA |
| CORE-BACKUP-7 | Verified-restore badge (daily check, weekly scratch restore) | M | BACKUP-6 | `internal/backup/**` | Clock +7 days without a verified restore → badge red and one alert |
| CORE-NOTIFY-1 | Alert record and store, `/v1/alerts`, NATS subjects, in-app inbox (includes DEV-API-12) | M | API-5, C12-E | `alerts.py`, `notify/**` | One alert each for a pending approval, an offline node and a stale backup; dedupe holds |
| DEV-API-12 | Notifications route shapes (built inside NOTIFY-1) | – | NOTIFY-1 | – | Plugin send limited to `plugin.<app-id>` topics; channel secrets never returned |
| CORE-BACKUP-8 | Backups API, screen and alerts (includes DEV-API-11) | S | BACKUP-2, DASH-1, NOTIFY-1, C12-D | `backups.py`, `Backups.tsx` | No credentials in any response |
| DEV-API-11 | Backups and restores route shapes (built inside BACKUP-8) | – | BACKUP-8 | – | Agent can request run/verify/restore, never approve |
| DEV-CLI-7 | `backup status/list/now/verify` and `restore` | M | BACKUP-8 | `cli/backup.go` | `restore` needs typed confirmation and owner approval; safety snapshot id printed |
| CORE-NOTIFY-2 | Sources: approvals, nodes, updates, backups, scans, audit (H-28) (+ UMB-SYS-4) | S | NOTIFY-1 | `alerts.py`, emitters, `internal/update/**` | Expired TUF timestamp + 48 h → one alert; forced rollback → one `os.rolled_back` naming the check; check failing 48 h → `os.check_failing` |
| CORE-NOTIFY-3 | Web Push and Android UnifiedPush via the box's ntfy; push registrations | M | NOTIFY-1, SEC-1 | `notify/**` | Push payloads hold only `alert_id` and `box_id` |
| CORE-NOTIFY-4 | iOS APNs relay (built with MOBILE-5) | M | NOTIFY-3, C12-G, F-4 | `relay/**` | Apple payload holds ids only |
| CORE-NOTIFY-5 | Repairs with fix actions | M | NOTIFY-1 | `repairs.py` | Each fix is a request; nothing changes without approval |
| CORE-NOTIFY-6 | Email, webhook, Matrix, Telegram channels; routing and quiet hours | S | NOTIFY-1 | `notify/**` | `notify test` reports per-channel delivery |
| CORE-UPDATE-3 | Updates screen and "What's new" from signed release notes (+ UMB-SYS-2, UMB-DESK-15) | S | UPDATE-2, DASH-1 | `Updates.tsx`, `os/update/build-release.sh` (notes as a TUF target) | Shows rollback reason after a failed trial; tampered notes hidden while the update still installs; What's new shown once per person per version (`seen.whats_new`) |
| CORE-UPDATE-5 | App updates through approval (catalog diff, `app.update`) | M | SANDBOX-2 | `app_updates.py` | An update that widens grants needs a fresh approval |
| CORE-UPDATE-6 | Health-gated app updates with snapshot and revert (+ UMB-APP-6) | M | UPDATE-5, BACKUP-2 | `app_updates.py`, app-gate probes | Failing probe reverts to the previous digests, restores the snapshot, alert names the probe; widened egress needs a new approval |
| CORE-UPDATE-7 | Offline grace and USB/LAN mirror installs (+ UMB-SYS-12) | M | UPDATE-1 | `internal/update/**` | Install from a USB mirror verifies with TUF offline; `onemind update apply --from <file>` accepts an expired timestamp inside the grace only for a target newer than installed |
| CORE-UPDATE-8 | Rescue console in onemindd | M | SEC-1 | `internal/rescue/**` | With k3s stopped, the rescue page lists slots and rolls back |
| CORE-DASH-2 | Move the 5 existing screens onto `@onemind/ui` | S | DASH-1 | `dashboard/src/pages/*` | Existing dashboard tests pass |
| CORE-DASH-5 | Alerts, Updates and Backups screens | M | NOTIFY-1, UPDATE-2, BACKUP-8 | one page file each | Stale data never shown as live |
| CORE-DASH-7 | PWA and per-app subdomain launcher | M | SEC-1, NOTIFY-3 | `dashboard/**` | Installs on Android Chrome over HTTPS with the box CA; Web Push received |
| CORE-DASH-8 | Typed widgets on Home with a widget data route; "show the equivalent call" toggle (+ UMB-DESK-5) | M | DASH-1, UMB-DESK-0, F-37 | `dashboard/**`, `ui/src/components/widgets/**`, `core/onemind_core/widgets.py` (with DEV-PLG) | Each shown CLI/API call creates the same action; invalid payload renders `invalid` with the reason; older than 2 × refresh renders `stale` with its age; HTML in strings renders as text; system widgets for usage, last backup and waiting approvals |
| DEV-SDK-4 | Dashboard and mobile moved onto `@onemind/sdk` | M | SDK-3, PA-MOBILE | `dashboard/src/api/**`, `mobile/src/api/**` | Both test suites pass with the hand-written clients deleted |
| DEV-SDK-7 | SSE in all three SDKs, polling fallback, React Native transport | L | SDK-3, SDK-5, SDK-6, API-8 | `sdk/*/events*`, `sdk/openapi/events-v1.json` | Resume loses no events; 45 s without keepalive reconnects; reset surfaced |
| CORE-MOBILE-1 | Shell on the generated `sdk/ts`; icon and splash | S | PA-MOBILE, SDK-3 | `mobile/**` | Builds for Android and iOS |
| CORE-MOBILE-2 | QR pairing with CA pinning, HTTPS only | M | MOBILE-1, SEC-1 | `mobile/**` | A box with a different CA at the same URL is refused |
| CORE-MOBILE-3 | Passkey sign-in and signed approvals; plan card | M | MOBILE-2, SEC-2, SANDBOX-2 | `mobile/**` | Approve under 10 s on a real Android phone; replayed link fails |
| CORE-MOBILE-4 | Android UnifiedPush | M | NOTIFY-3 | `mobile/**` | Push arrives with the app closed in < 5 s on the LAN |
| CORE-MOBILE-5 | iOS service extension and relay registration (with NOTIFY-4) | M | NOTIFY-4, F-4 | `mobile/**` | Extension shows fetched text; payload holds ids only |
| CORE-MOBILE-6 | Alerts and Activity tabs, offline cache, checkpoint store | M | NOTIFY-1, SEC-6 | `mobile/**` | Offline view labelled with its age; approve disabled offline |
| CORE-NOTIFY-7 | Actionable notifications open the approval card | S | NOTIFY-3, MOBILE-3 | `notify/**`, mobile | Tap → card → passkey approve under 10 s |
| DEV-MCP-3 | Request-only writes: `withdraw_request`, `preview_action`, `plan_sha256`, never-requestable list; `get_app` (+ UMB-APP-15) | M | MCP-2, SANDBOX-2 | `mcp/**` | No path from `/mcp` to approve, deny, delete app data, expose or change sources; stale `plan_sha256` → 409 |
| DEV-MCP-6 | MCP audit entries, read summaries, trace context, audit tools | S | SEC-6, MCP-1 | `mcp/**` | Each request, withdraw and denial is one chained entry |
| DEV-MCP-8 | Conformance CI with official TS, Python, Go clients and the bridge | M | MCP-1, MCP-7 | `test/mcp-conformance/**` | All three clients pass direct and via the bridge |
| DEV-MCP-9 | MCP revision 2025-11-25 and the `versions.py` adapter split | S | MCP-8 | `mcp/versions.py` | Negotiates 2025-11-25; unknown version handled per spec |
| DEV-MCP-11 | Prompts, `onemind://docs`, `llms.txt`, `search_docs`, status tools | S | MCP-1 | `mcp/catalog.py` | Every gateway error code has a docs page |
| CORE-WEB-2 | Generated references: CLI, API, schema, errors | M | SDK-1, CLI-13 | `site/scripts/gen-*.mjs` | References rebuild from the spec with no hand edits |
| CORE-WEB-3 | Apps catalog with scan history, from the signed catalog (+ UMB-APP-16) | S | W2-PIPE, UMB-APP-2 | `site/**` | Changing a `scan.json` changes that app's page on the next build; each page shows version, compatibility, developer, licence, scan, permissions, notes, related |
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
| CORE-DEPLOY-4 | Write-only secrets and generated app credentials (+ UMB-APP-11) | S | SEC-5, SEC-2 | `deploys.py`, `cli/secret.go` | No route returns a secret value except the owner reveal route with a passkey; agent gets 403 on `secret set` and reveal; log scan finds no secret |
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
| CORE-DOGFOOD-5 | GPU enablement (toolkit, device plugin, placement, detection breadth) (+ UMB-STOR-11) | M | FABRIC-4, image stream | `os/**`, `internal/detect/**` | A GPU app lands only on a GPU node; `lspci` 0300/0380, AMD `/dev/kfd` and NVIDIA fixtures label correctly |
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

## Added 2026-11-12: streams and epics missing from the board

Streams that started without a row, merged PRs that had none, and gaps found in merged work. State per row: [STATUS.md](STATUS.md#added-2026-11-12-streams-and-epics-that-were-missing-from-the-board). **Scope marked "proposed"** was written from the stream's name and brief because the branch has no commits yet; the stream's first PR confirms or corrects it here. Sprint is the earliest sprint the dependencies allow.

### Merged work that had no row (done)

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| CORE-PLUMB | Core plumbing (PR #38) | M | – | `core/onemind_core/{routers,store,sections}.py`, `cmd/onemind/cli/`, `cmd/onemindd/registry.go`, `internal/service/` | Done: OpenAPI and CLI output identical before and after; guide in [`core/PLUMBING.md`](core/PLUMBING.md) |
| UMB-STUDY | umbrelOS 2 deep dive and UMB backlog (PR #30) | M | – | `docs/umbrel2/**` | Done: 10 area studies; UMB rows below |
| BRAND-0 | OneMind logo, SVG and PNG, 4 variants (PR #36) | S | – | brand assets | Done |

### Image line, S1–S2 (`feat/image-line`)

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| IMG-1 | OneMind baked into the image: onemindd, NATS, gateway and dashboard installed and enabled; first boot lands in OneMind | M | image stream (#10), W2-DEPLOY (#26) | `os/**`, `test/qemu/**`, `test/unit/test_firstboot.py`, `docs/IMAGES.md`, `Makefile` | QEMU first-boot battery F0–F4 (pre-registered on the branch) passes on x86_64 EFI and arm64; `/healthz` answers and the dashboard loads with no manual step |
| IMG-2 | Raspberry Pi 5 board image | M | IMG-1 | `os/boards/rpi5/**`, `test/unit/test_rpi5.py` | Image builds in CI; unit tests pass; the hardware run is PLAN-E10 (needs F-25) |
| IMG-3 | Jetson Orin board image on NVIDIA L4T (D-007) | M | IMG-1 | `os/boards/jetson-orin/**` | Image builds in CI; the hardware run is PLAN-E11 (needs F-25) |
| IMG-4 | USB installer for x86_64 that writes OneMind to the internal disk | M | IMG-1 | `os/boards/installer-x86_64/**`, `test/qemu/installer.py`, `test/unit/test_installer.py` | QEMU criteria I1–I5 (pre-registered) pass |
| IMG-5 | Cloud images: generic, AWS, Azure, GCP, Hetzner, Proxmox | M | IMG-1, BD-DO-1 (`vm-do`, #10) | `os/boards/cloud*/**`, `os/cloud/**` | QEMU criteria C0–C6 (pre-registered) pass for each image |
| IMG-6 | Releases and downloads: signed images with checksums on GitHub Releases; a downloads page | M | IMG-1…5, OS-SECPIPE, F-27, F-5 | release workflow, `site/**` downloads page | Every asset has a checksum and a verifiable signature; the page lists only images whose battery passed |

### Brand, S1

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| BRAND-1 | One brand source: `brand.json` and `brand-sync`; ui, dashboard and site take name, logo, favicon, manifest and accent from it | M | BRAND-0 | `brand/**`, `ui/src/{tokens,customize,shell}/**`, `dashboard/public/brand/**`, `dashboard/src/**`, `site/public/**`, one CI workflow | Changing `brand.json` and running the sync updates every consumer; CI fails when a generated file drifts |
| MOBILE-V1-1 | Phone app restyle from `brand.json`: icon, splash, colours, logo | S | BRAND-1, PA-MOBILE (#21) | `mobile/**` | Android and iOS builds show the brand assets; the drift check covers `mobile/` |

### Testing and quality, S1

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| E2E-GOLDEN | Golden-path e2e: `install.sh` hub in a VM (Lima, QEMU/KVM), Playwright through dashboard, MCP agent request, owner approval and audit; `verify.sh` | M | W2-DEPLOY, W2-GW | `tests/e2e/**`, `.github/workflows/e2e.yml` | Green on PRs and nightly; agent approve → 403 on the real hub; no owner token in uploaded artifacts |
| TEST-REG-1 | Test register: every suite with owner and run command, a results log, a test-result issue form, `test-all` workflow | S | – | `docs/testing/**`, `.github/ISSUE_TEMPLATE/test-result.yml`, `.github/workflows/**` (one line each), `scripts/` | `test-all` runs every registered suite; a suite missing from the register fails the check |
| TEST-SEC-1 | Security test suite against the threat model's attack paths (proposed: approval bypass, token scope, sandbox escape, secret leakage) | M | PA-THREAT, SEC-P0 (#40) | `tests/security/**` (proposed) | Each H-id marked fixed has a test that fails on the old code; runs on every PR |
| TEST-PROP-1 | Property-based and fuzz tests (proposed: manifest validator, sandbox checker, heartbeat parser, path confinement) | M | – | test directories of each component (proposed) | Bounded run on PRs, longer run nightly; every crash found is kept as a fixture |
| TEST-CI-1 | CI matrix across operating systems and architectures (proposed: amd64 and arm64, Debian 13 and the Ubuntu hedge, macOS for the developer path) | M | – | `.github/workflows/**` | Matrix green on `main`; every action pinned by SHA from `os/versions.lock.yaml`; run time recorded |
| QUAL-SLOP-1 | Slop audit: unverified claims, filler, stale or duplicated text in docs and comments, ranked with file:line | S | – | audit report under `docs/` (proposed) | Every finding has file:line, a class and a fix |
| QUAL-SLOP-2 | Slop fixer: apply the audit's fixes as `fix(docs):` commits with evidence | M | QUAL-SLOP-1 | files the audit names | Each finding fixed or recorded as won't-fix with a reason; hygiene and gitleaks clean |

### Market, apps and secrets, S1–S3

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| MKT-BATCH-1 | Market batch 1: Nextcloud, Immich, Syncthing, Paperless-ngx, Gitea, Grafana, Ollama, LibreChat, SearXNG, AdGuard Home (tier community until CI scans) | M | W2-PIPE (#25), MKT-CANDIDATES (#22) | `apps/<id>/**` | Each app passes app-gate and the k3d smoke test in CI and has a `scan.json` |
| MKT-BATCH-2-3 | Market batches 2 and 3: the next 20 apps from `CANDIDATES.md` | L | MKT-BATCH-1 | `apps/<id>/**` | As MKT-BATCH-1 |
| MKT-BATCH-4 | Market batch 4 | M | MKT-BATCH-2-3 | `apps/<id>/**` | As MKT-BATCH-1 |
| MKT-BATCH-5 | Market batch 5 | M | MKT-BATCH-4 | `apps/<id>/**` | As MKT-BATCH-1 |
| CORE-SECRETS-1 | Owner-entered app secrets: the install review asks for the secrets an app declares (for example the Hermes model key); stored encrypted on the box; given to the app only as a Kubernetes Secret | M | CORE-SEC-2, CORE-SEC-5 (k3s secrets encryption, #40), C12-C (#39) | `core/onemind_core/` secrets module, install review in `dashboard/**` | Installing `hermes-agent` asks for the model key; no route, log or MCP tool returns the value; agents get 403 on set; the value survives a backup restore |
| DB-SHARED-1 | Shared PostgreSQL for apps: one managed PostgreSQL; an app that declares it gets its own database and role | L | CORE-SANDBOX-2, CORE-BACKUP-5, a contract amendment for the manifest field | system app `apps/postgres` (proposed), schema via the contract owner | Two apps get separate databases and credentials and cannot read each other's; backups use the manifest `backup:` hook; remove keeps the database until a data delete |
| APP-OVERRIDE-1 | Owner override for an app or image the scan blocked: typed confirmation, red "owner override" mark in the audit and on the app page | S | F-7, CORE-SEC-2, CORE-DEPLOY-2 | approve path in `core/onemind_core/`, dashboard plan card | Only with a passkey step-up; never by an agent or a standing approval; audit and app page show the override |

### Core gaps found in merged work, S2–S3

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| BACKUP-WIRE-1 | Wire `internal/backup` (#32): onemindd service and loopback API, heartbeat `backup`, the updater's pre-update snapshot, image pins (steps 1–4 of "Wiring still needed" in `internal/backup/README.md`); then the gateway backups router and the Backups screen (delivers CORE-BACKUP-8) | M | #32, C12-D (#39), CORE-PLUMB (#38) | `cmd/onemindd/registry.go`, `internal/heartbeat/**`, `internal/update/**`, `os/versions.lock.yaml` (add-only), `core/onemind_core/routers/`, `dashboard/src/pages/Backups.tsx` | QEMU: a configured box takes its hourly snapshot; heartbeat carries `backup`; the updater's snapshot goes through the agent; the Backups screen shows last run and last verified restore with no credentials |
| STORAGE-ACT-1 | Mirror create, add disk and replace disk as approved `storage.*` actions that execute #31's dry-run plans (first slice of UMB-STOR-4 and -5) | L | UMB-STOR-3 (#31), UMB-STOR-0, CORE-SEC-2, DEV-API-7 | `internal/storage/**`, `core/onemind_core/storage.py` | Plan names model, size and serial tail; agents can request, never approve; wiping steps need a passkey step-up; a power cut mid-operation resumes or rolls back in QEMU |
| PHOTOS-SRV-1 | Box side of the phone photo backup (#34): built-in receiver (UMB-PHOTO-1…3) or Immich (UMB-PHOTO-13), by founder decision | L | founder decision (Immich vs built-in, F-47) | per the decision | #34's client uploads 1,000 photos to a real box, resumes after a drop, dedupes by hash and gets a receipt per file |
| CORE-MON-1 | Monitoring: app health, restarts, logs, app and node metrics, thresholds (contract §12.15) | M | C12 (#39), CORE-NOTIFY-1 | `core/onemind_core/monitoring/**`, `internal/detect/**`, heartbeat metrics | A failing app raises one alert that resolves by itself; the heartbeat carries CPU, load and temperature; thresholds configurable |
| DOGFOOD-MIGRATE-1 | Import from an existing Kubernetes cluster: read workloads, config and volumes (read-only on the source), turn them into private OneMind apps, copy the data, cut over | L | CORE-DEPLOY-1, CORE-DEPLOY-6, CORE-BACKUP-2 | `cmd/onemind/cli/`, `internal/migrate/**` (proposed) | A generic fixture cluster (k3d) imports with identical data; the source is never written; each app passes the sandbox checker or is listed as refused with the reason |

### Developer surface and website, S1–S3

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| DEV-PLG-0 | Plugin SDK v0: first runnable slice ahead of DEV-PLG-1…8 (proposed: hello plugin, mock hub, write call that waits for approval) | M | C12-PLG | `sdk/plugin-*/**`, `sdk/templates/plugin-hello/` (proposed) | Hello plugin runs against a mock hub; its write call creates an action that waits for owner approval |
| CORE-WEB-G | Website user guides for owners (proposed: install per target, first steps, apps, approvals, backups, phone app) | M | PA-SITE (#19) | `site/src/content/docs/**` | Each guide's commands match current `main`; link check and axe clean; no claim without a test or doc link |

### Deploy kit parts of PR #27, S1

PR #27 is open and overlaps #26 (merged). Port these parts onto `main`'s `deploy/`, then close #27.

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| DEPLOY-PORT27-1 | `deploy/bundle.sh --arch amd64\|arm64` (onemindd, gateway image tar, dashboard dist, `SHA256SUMS`) and `install.sh --bundle` | M | W2-DEPLOY (#26) | `deploy/bundle.sh`, `deploy/install.sh` | `--bundle` refuses a bundle whose `SHA256SUMS` does not match; an offline hub install from a bundle reaches `/healthz` |
| DEPLOY-PORT27-2 | `install.sh --target debian13\|rpi5\|jetson\|do` and `--dry-run`; Pi 5 memory cgroup; DigitalOcean firewall reminder | S | #26 | `deploy/install.sh` | Dry run for hub and node on all 4 targets exits 0 and changes nothing; on rpi5 the memory cgroup is on before k3s starts |
| DEPLOY-PORT27-3 | Hashed tokens throughout: join, owner and agent tokens printed once, only sha256 on disk | S | #26 | `deploy/install.sh` | After an install and a re-run, no raw token is found under the install's state directory |
| DEPLOY-PORT27-4 | NATS token auth for nodes on the developer install (step before nkeys, CORE-SEC-4) | S | #26 | `deploy/install.sh`, `deploy/systemd/onemind-nats.service` | Anonymous NATS connect refused; node heartbeats still arrive |
| DEPLOY-PORT27-5 | `deploy/verify/node-check.sh` and `natscheck.py` (standard library only) | S | #26 | `deploy/verify/**` | Passes on hub and node; fails with a named check when NATS is down |
| DEPLOY-PORT27-6 | Mock gateway for the `verify.sh` tests; e2e-systemd harness (real `install.sh` and bundle on two Debian 13 systemd containers) | M | DEPLOY-PORT27-1, -5 | `deploy/verify/tests/**`, `.github/workflows/ci-deploy.yml` | Verify tests catch the 7 broken-hub cases; e2e-systemd: 2 k3s nodes Ready, owner-approved ntfy Available |
| DEPLOY-PORT27-7 | Simulated rpi5 and jetson-orin nodes in the compose dev hub | S | #26 | `deploy/compose/**` | `up.sh` shows 3 online machines; their heartbeats validate against §2 |

### UI parity, S1–S2 (from [`docs/strategy/umbrel-parity.md`](../strategy/umbrel-parity.md))

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| PU-31 | PWA: manifest, icons, accent theme colour, installable over HTTPS, offline "last known" view labelled with its age (first slice of CORE-DASH-7, no Web Push) | S | CORE-SEC-1, BRAND-1 | `dashboard/public/**`, service worker in `dashboard/src/**` | Installs on Android Chrome over HTTPS with the box CA; the offline view shows its age; approve disabled offline |
| PU-09 | Login UI: passkey sign-in, TOTP fallback, first-run owner setup (UI side of CORE-SEC-2) | M | CORE-SEC-2 | `dashboard/src/pages/SignIn*.tsx`, onboarding in `ui/**` | Owner enrols a passkey at first run; TOTP fallback works; repeated wrong codes are rate-limited; axe clean |
| PU-20 | i18n scaffolding: string catalog, locale switch, English as source | M | CORE-DASH-2 | `ui/**`, `dashboard/**` | A lint rule finds no hard-coded user-facing string in dashboard pages; a pseudo-locale renders without truncation |

### Founder blockers

| Id | Decision | Blocks | Acceptance |
|---|---|---|---|
| F-25 | Day-1 hardware (Pi 5 16 GB + NVMe, 4 GB Pi 5 for the soak, Jetson Orin Nano Super) | CORE-UPDATE-4, CORE-NET-14, PLAN-E10, PLAN-E11, IMG-2 and IMG-3 hardware runs | Hardware on the bench; Pi soak started by 2026-12-11 |
| F-27 | Offline TUF root ceremony and signing secrets | OS-SECPIPE publishing, CORE-SEC-8, IMG-6 | Root signed offline; secrets only in protected GitHub environments |
| F-7 | Owner override for scan-failed installs | APP-OVERRIDE-1 | Answer recorded in `docs/DECISIONS.md` |
| F-5 | Website domain and host | CORE-WEB-1, CORE-WEB-4, IMG-6 downloads page | Answer recorded; deploy target set |

### Stream ids that map onto existing rows

No second row; the existing row's acceptance applies, with the additions noted.

| Stream id | Existing row(s) | Adds to that row's acceptance |
|---|---|---|
| MKT-B1, MKT-B23, MKT-B4, MKT-B5 | MKT-BATCH-1, MKT-BATCH-2-3, MKT-BATCH-4, MKT-BATCH-5 | – (ids used on the branches) |
| SEC-P0 (PR #40) | CORE-SANDBOX-1…5, CORE-SEC-9, k3s part of CORE-SEC-5 | – |
| APP-LIFE-1 (PD-03) | UMB-APP-4 | – |
| APP-LIFE-2 (PD-04) | UMB-APP-3 | – |
| APP-LIFE-3 (PD-05) | CORE-UPDATE-5, CORE-UPDATE-6 | Release notes shown before the update |
| APP-LIFE-4 (PD-06) | UMB-APP-5 | – |
| APP-LIFE-5 (PD-07) | CORE-DEPLOY-4 (includes UMB-APP-11) | – |
| MOBILE-V1-2 | CORE-MOBILE-2, CORE-MOBILE-3, UMB-ACCT-11 | – |
| MOBILE-V1-3 | CORE-MOBILE-4, CORE-MOBILE-5 | – |
| MOBILE-V1-4 | CORE-MOBILE-6, CORE-NOTIFY-7 | – |
| NET-P2-1…4 | CORE-NET-10, -11, -12 (with the rest of CORE-NET-8), -13 | – |
| FILES-1, -2, -4, -6 | UMB-FILES-1, -2, -4, -6 | – |
| STORAGE-LUKS-1 (H-11) | CORE-SEC-5 (LUKS part, includes UMB-STOR-1) | Recovery key shown once at install; unlock by passphrase on boards without a TPM |
| DESKTOP-FILES-1 | UMB-CLIENT-9; server side UMB-FILES-5 | A WebDAV mount as an option next to SMB |

## UMB: umbrelOS 2 study epics

From the ten area studies in [`docs/umbrel2/`](../umbrel2/README.md), 2026-11-12. `UMB-<area>-n` is epic `n` of that area's study (README there gives the map). Rows are placed in the sprint where every dependency is already scheduled; within a sprint, nothing appears before what it depends on. Sizes follow the studies (S ≤ 2 days, M ≤ 1 week, L > 1 week); photos sizes are estimates. Owner paths follow [WORKSTREAMS.md](WORKSTREAMS.md); the studies propose five new streams (Storage `feat/onemindd-storage`, Files `feat/files-*`, Clients `feat/client-*` and `feat/desktop-client`, Photos `feat/photos-*`, Machines `feat/machines-*`), which still need their WORKSTREAMS §2 rows. Hotspots (contract, schema, `routes.py`, `ledger.py`, `App.tsx`, `root.go`, `cmd/onemindd/main.go`, `executors.py`, `mcp/catalog.py`, `os/versions.lock.yaml`) change only in their own small PRs through their owners. Licence rule for every row: umbrelOS (PolyForm Noncommercial) is read and described, never copied.

### UMB merged into existing epics

These study epics duplicated an existing epic and were folded into it; the target row's acceptance now includes them. No separate row exists for them.

| Study epic | Merged into | What it adds |
|---|---|---|
| UMB-SYS-1 (bind apply to the checked target) | CORE-UPDATE-2 | Apply with a stale `target_digest` → 409 `stale_precondition`, nothing installed |
| UMB-SYS-2, UMB-DESK-15 (signed release notes, What's new) | CORE-UPDATE-3 | Notes are a TUF target; tampered notes hidden, update still installs; shown once per person per version |
| UMB-SYS-3 (SSE event stream) | DEV-API-8 | `onemind.os.*` events within 1 s; 1,000-event burst resumes without loss |
| UMB-SYS-4 (OS and network alert sources) | CORE-NOTIFY-2 | `os.rolled_back` names the check; `os.check_failing` after 48 h |
| UMB-SYS-5 (live usage and system widgets) | UMB-DESK-12 | One live-usage epic; collector ≤ 1 % of one Pi 5 core |
| UMB-SYS-7 (LAN discovery, CA bootstrap) | UMB-CLIENT-1 | Same `_onemind._tcp` advert and `/v1/discovery`; id changes after factory reset |
| UMB-SYS-9 (move to new hardware) | CORE-BACKUP-6 | Box restore at onboarding brings back hub identity; nodes re-find the hub by mDNS and the pinned CA |
| UMB-SYS-11 (desktop companion) | UMB-CLIENT-8 | One desktop app (Tauri) |
| UMB-SYS-12 (offline and mirror installs) | CORE-UPDATE-7 | `onemind update apply --from <file>`; expired timestamp accepted inside the grace only for a newer target |
| UMB-APP-6 (health-gated update, re-approval on widening) | CORE-UPDATE-6 | Failing probe restores data and digests; widened egress needs a new approval |
| UMB-APP-7, UMB-APP-8 (edge routes with forward-auth; name-constrained CA, `onemind tls trust`) | CORE-NET-P1 (`feat/core-net`) | Signed-out 302, guest 403, WebSocket kept; a leaf for a foreign name is rejected; renewal 14 days ahead |
| UMB-APP-11 (generated credentials) | CORE-DEPLOY-4 | Owner reveal with passkey; agents 403; secrets masked in logs |
| UMB-APP-15 (MCP `get_app`, never-requestable list) | DEV-MCP-3 | Adds `get_app`; no MCP path to approve, delete data, expose or change sources |
| UMB-APP-16 (public app pages) | CORE-WEB-3 | Pages built from the signed catalog (UMB-APP-2) |
| UMB-AGT-2 (agents registry, pause-all, person ∩ grant) | DEV-MCP-2 | Pause-all keeps pending requests; adults see only their agents; tokens stored as sha256 |
| UMB-AGT-7 (app lifecycle request types) | UMB-APP-4, UMB-APP-5 | One set of lifecycle types; data delete needs passkey step-up |
| UMB-ACCT-3 (identity module on Kanidm) | CORE-SEC-10 | Sign-in works with k3s stopped; concurrent credential reset kills older sessions; revoked WebSocket closed within 1 s |
| UMB-STOR-1 (LUKS2 + btrfs data volume) | CORE-SEC-5 | `/data` is btrfs on dm-crypt with `@`, `@storage`, `@snapshots`; TPM2 and recovery key slots |
| UMB-STOR-11 (GPU detection breadth) | CORE-DOGFOOD-5 | `lspci` 0300/0380, AMD `/dev/kfd`, NVIDIA fixtures |
| Files study STOR-1 disk inventory and SMART part | UMB-STOR-3 | One inventory; USB disks become UMB-STOR-13 |
| UMB-DESK-2, -3, -4, -8 (wallpapers, glass and motion tokens, launcher/dock/context menu, command palette) | UI-LEAP (`feat/ui-leap`) | Before UI-LEAP merges: contrast test for every wallpaper × accent × theme, hash check that no umbrelOS asset is present, reduced-transparency and reduced-motion tests, keyboard grid and dock, Alt+letter rules |
| UMB-DESK-5 (widget templates and data route) | CORE-DASH-8 | Schema-checked payloads, `stale` after 2 × refresh, system widgets for usage, last backup, waiting approvals |
| UMB-CLIENT-4 (photo ingest on the box) | UMB-PHOTO-3 | `Content-Digest` checked before a receipt |
| UMB-CLIENT-5 (receipts with backup level) | UMB-PHOTO-8 | `in_verified_backup` only after a verified restore covers the file |
| UMB-CLIENT-6, -7, UMB-FILES-11 (Android, iOS and Files-side phone photo backup) | UMB-PHOTO-4 | One phone backup; iOS PhotoKit-over-HTTPS spike; landing place is F-47 |
| UMB-CLIENT-9 server side (Samba, per-device SMB users) | UMB-FILES-5 | UMB-CLIENT-9 keeps the desktop mounts |
| UMB-PHOTO-14 (desktop folder sync) | UMB-CLIENT-11 | Photo folders back up through the UMB-PHOTO-3 protocol |

### UMB in S1

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| UMB-STOR-0 | Contract: storage reads, `storage.*` action types, heartbeat `storage`, `storage:*` scopes; decision record (btrfs, no ZFS in v1) | S | C12-A, F-60 | `sdk/contracts/poc-v0.md` (contract owner), `docs/DECISIONS.md` | Contract merged; OpenAPI lists the routes; heartbeat validates with and without `storage` |
| UMB-STOR-3 | onemindd storage inventory and health collector (lsblk, smartctl, nvme) | M | UMB-STOR-0 | `internal/storage/{inventory,health}/**`, one line in `cmd/onemindd/main.go`, `cmd/onemind/cli/storage.go` | Recorded NVMe, SATA and USB-SAT fixtures parse; system and foreign roles correct; QEMU heartbeat shows `storage.state=unprotected` |
| UMB-FILES-0 | Contract 12-files: roots, file API, action types, MCP tools, manifest `spec.folders` | S | C12-A, F-39, F-40 | contract, `sdk/schema/onemind.app.schema.json` (contract owner) | Schema accepts `spec.folders`, rejects an unknown `access` |
| UMB-ACCT-1 | Kanidm spike: host service, offline first boot, groups, OIDC client, reset link, expiry, TOTP replay, backup and restore | M | F-34 | `research-output/evidence/lab/acct-kanidm/**` | Owner passkey enrolled with the network unplugged; restored box accepts the same passkey; reused TOTP refused |
| UMB-ACCT-2 | Contract: role `child`, `access:*` and `sessions:self` scopes, `access.*` action types, forward-auth headers, manifest `spec.auth` | S | C12-A | contract, schema (one PR) | Schema tests pass with `spec.auth.mode` `oidc`, `headers`, `gate-only` |
| UMB-ACCT-13 | Lab: passkey across LAN and mesh names; hybrid sign-in from a TV browser | S | UMB-ACCT-1, CORE-NET-P1 | `research-output/evidence/lab/acct-domain/**` | Pre-registered result settles F-33 before the first owner enrols |
| UMB-AGT-1 | Contract: agents, pairings, new request types, `request_access`, `troubleshooter` bundle, `authorization_pending` | S | C12-H | contract, schema (contract owner) | Schema validates `spec.agent.scopes` with the new bundle; no feature code in the PR |
| UMB-AGT-3 | Agent pairing (device-code shape): `/v1/agent-pairings*`, limits, passkey approval, audit | M | UMB-AGT-1, DEV-MCP-2, CORE-SEC-2, F-52 | `core/onemind_core/agents.py` (security), approve hook via gateway core | No token in stdout, stderr, chat fixture or client config; 21st attempt/min → 429; expired code → 410; approver cannot grant above own rights |
| UMB-AGT-4 | Persistent MCP client identity, capped `agent_clients`, `agent.identity_changed` alert | S | DEV-MCP-1, DEV-MCP-2 | `core/onemind_core/mcp/transport.py` | A key used by client A then B raises one alert; 11th name drops the oldest; survives restart |
| UMB-APP-0 | Contract: app lifecycle action types, `/v1/apps/{id}` detail, `/plan`, `/revisions`, `/logs`, `/v1/sources`, `source.*`, never-requestable list | S | C12-A | contract (contract owner) | Merged before any UMB-APP feature PR; every route and type has an error table |
| UMB-APP-2 | Signed catalog: CI builds `catalog.json` with a cosign signature; gateway verifies and serves a cached copy offline | M | W2-PIPE | `.github/workflows/ci-apps.yml`, `core/onemind_core/catalog.py` | Tampered catalog refused with audit `catalog.signature_invalid`; unplugged network still lists apps |
| UMB-APP-12 | Logs endpoint, redacted | S | UMB-APP-0, DEV-API-1 | `core/onemind_core/logs.py`, one line in `routes.py` | Owner/adult 200 with tail; guest and agent 403; known token patterns masked |
| UMB-APP-3 | Plan endpoint with dependency resolution, alternatives and dependants check | M | CORE-SANDBOX-2, UMB-APP-0 | `policy.py`, `executors.py` (install sandbox) | Plan lists deps, folders, GPU, host ports, egress; removing a dependency → 409 naming dependants; hash changes with any input |
| UMB-APP-18 | Schema: `tagline`, `category`, `tags`, `developer`, `gallery`, `related`, `spec.os.min`, dependency alternatives, `provides`, `permissions`, `credentials`, `web.auth`, `web.websocket` | S | W2-PIPE, PLAN-E6, UMB-APP-0 | `sdk/schema/onemind.app.schema.json` (hotspot) | All apps validate; non-semver version or unknown permission fails |
| UMB-CLIENT-0 | Contract 12-clients: discovery, devices, photo sources, shares, event topics | S | CORE-SEC-1, CORE-SEC-2 | contract (contract owner) | Merged alone; OpenAPI export diff reviewed |
| UMB-CLIENT-1 | Discovery: `_onemind._tcp` advert and `GET /v1/discovery` with the CA (includes UMB-SYS-7) | S | UMB-CLIENT-0, CORE-SEC-1 | `core/onemind_core/discovery.py`; avahi file via the image stream | TXT holds only `id` and `v`; route < 50 ms, no auth, no person names; rate limit 429; id changes after factory reset |
| UMB-CLIENT-3 | Client kit (TypeScript and Rust) with shared test vectors | M | UMB-CLIENT-0 | `sdk/clientkit/**` | ≥ 30 vectors pass identically in TS and Rust; CA mismatch always ends "refused", never a new pin |
| UMB-PHOTO-0 | Photos licence rows and contract §12-p | S | C12-A | `research-output/evidence/license-matrix.csv` (add-only), contract (contract owner) | Every component has SPDX, pinned commit and use; every model's licence and training terms read, non-commercial ones excluded; §12-p merged |
| UMB-DESK-0 | Contract: `/v1/me/home`, `/v1/wallpapers`, shortcut preview, widget data, `/v1/usage`, events `action.progress` and `home.updated`, `home.change`, `home.schema.json` | S | C12-A, DEV-API-5 | contract, `sdk/schema/home.schema.json` | Schema rejects 9 dock items, 7 widgets, unknown id prefix, non-http(s) shortcut |
| UMB-DESK-1 | Home document store and routes (per person, ETag) | M | UMB-DESK-0, DEV-API-1 | `core/onemind_core/home.py`, one `routes.py` line, one migration | No `If-Match` → 428, stale → 412; another person cannot read it; unshared app disappears without a write; each `PUT` audited and emits `home.updated` |
| UMB-DESK-7 | `Sheet`, `ImmersiveDialog`, `TargetPicker` | M | UI-LEAP | `ui/src/components/**` (design system) | Focus enters and returns; Escape closes after the exit animation; scroll restored; target in URL opens directly |
| UMB-SYS-13 | Yank a published OS release | S | CORE-UPDATE-1 | `os/update/**`, `internal/update/**` | Signed `yanked` entry; boxes pending reboot cancel the trial; committed boxes get an alert |

### UMB in S2

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| UMB-CLIENT-2 | Device registry, `device.add` action, DPoP tokens, revoke | M | UMB-CLIENT-0, CORE-SEC-2, CORE-SEC-3 | `core/onemind_core/devices.py`, one migration, `cmd/onemind/cli/devices.go` | Device request is pending; agent 403 on all `/v1/devices`; proof from another key 401; revoke stops refresh at once |
| UMB-STOR-2 | Initrd assembly and recovery mode markers | M | CORE-SEC-5 | image stream: `os/rootfs/layers/base/**`, `internal/storage/token/**` | QEMU: both members normal; one missing boots degraded with an alert; both missing boots to the recovery screen with k3s off; re-attach scrubs and leaves no `single` chunks |
| UMB-STOR-4 | Storage operation engine: protect, add, replace, remove, scrub, separate volume; journal, lock, resume | L | UMB-STOR-2, UMB-STOR-3 | `internal/storage/ops/**`, `internal/storage/socket.go` | Power cut at every step resumes or rolls back with the test corpus intact; second operation refused; scrub during balance deferred |
| UMB-STOR-5 | Gateway storage API and action executor | M | UMB-STOR-0, UMB-STOR-4, DEV-API-7 | `core/onemind_core/storage.py`, one `routes.py` line, one migration | Plan names the disk serial tail; disk changed → 409 `stale_precondition`; agent approve 403; destructive without step-up 401 |
| UMB-STOR-6 | Scrub scheduler and health alerts | M | UMB-STOR-3, CORE-NOTIFY-1 | `internal/storage/schedule/**` | Monthly scrub survives restarts; injected corruption repaired and reported; SMART-fail and wear alerts raised exactly once |
| UMB-STOR-7 | App snapshots: one subvolume per PV, snapshot before app and OS updates, prune | M | CORE-SEC-5, CORE-BACKUP-1 | `internal/storage/snapshot/**`; provisioner scripts via the image stream | `app.update` leaves a read-only snapshot; revert is byte-for-byte; restic reads from the snapshot |
| UMB-STOR-8 | Storage page, disk detail, protect flow, recovery screen, node-card pill | L | UMB-STOR-5, PA-UI | `dashboard/src/pages/Storage.tsx`, `dashboard/src/pages/storage/**` | Every state renders (protected, unprotected, degraded, repairing, unavailable); wipe plan shows model, size, serial tail |
| UMB-STOR-9 | Storage CLI and MCP tools | S | UMB-STOR-5, DEV-CLI-1, DEV-MCP-3 | `cmd/onemind/cli/storage.go`; MCP entries via the MCP owner | `status --json` equals the API; wipes need the typed serial tail; `request_action storage.protect` files an action |
| UMB-STOR-13 | External USB disks: auto-mount by filesystem UUID as `usb:<uuid>` roots; unmount guard; format is a critical action | M | UMB-STOR-3, UMB-STOR-5, UMB-FILES-0 | `internal/storage/**`, `core/onemind_core/storage.py` | Re-plug in another port keeps the root; format needs owner approval; unmount refused while an app grant uses it |
| UMB-FILES-1 | Node file server: confined operations, trash, resumable (tus) uploads, signed tokens, archives | L | UMB-FILES-0 | `internal/files/**`, one line in `cmd/onemindd/main.go` | Symlink and `..` fuzz: zero escapes; 5 GiB upload resumes at 50 % with matching sha256; wrong token 403; restore keeps mtime |
| UMB-FILES-2 | Gateway file API, roots, shares; data plane vs action split | M | UMB-FILES-1, CORE-SEC-10 | `core/onemind_core/{files,file_shares}.py`, one `routes.py` line, one migration | A cannot list `home:B`; a share is an action; revoke refuses the next token; every share change audited |
| UMB-FILES-3 | File index, search, thumbnails and previews in a sandbox | M | UMB-FILES-1 | `internal/files/{index,thumbs}/**` | Rename found by search within 5 s; a malformed image crashes only its sandbox (no network, memory-capped) |
| UMB-FILES-4 | Files page (list, grid, upload queue, preview, search, trash) | L | UMB-FILES-2, UMB-FILES-3, CORE-DASH-1 | `dashboard/src/pages/Files.tsx`, `dashboard/src/files/**` | Playwright at 390 and 1440 px without horizontal scroll; upload resumes after a drop; axe clean |
| UMB-FILES-6 | Folder grants for apps and agents | M | UMB-FILES-2, CORE-SANDBOX-2, DEV-MCP-3 | `core/onemind_core/grants.py` (with the MCP owner), executor hook via the sandbox owner | Plan shows folder and access; container sees only that folder; `files_request_access` files an action; outside grants 403 |
| UMB-FILES-7 | Rewind: restore points per path, `files.restore` with undo | M | CORE-BACKUP-2, CORE-BACKUP-6, UMB-FILES-2 | `internal/backup/**` units (backups), Rewind routes in `files.py`, `dashboard/src/files/rewind/**` | Restore matches content and mtime; Undo brings back the replaced version; no Rewind of another person's Home; agents 403 |
| UMB-PHOTO-1 | Photos service skeleton and catalog | M | UMB-PHOTO-0, CORE-BACKUP-1, F-47 | `cmd/onemind-photos/**`, `internal/photos/catalog/**`, `apps/photos/**` | Expand/contract migrations readable by the previous release; lists p95 < 150 ms at 100k assets; projection rebuild while old one serves |
| UMB-PHOTO-2 | Photo ingest and indexer | L | UMB-PHOTO-1 | `internal/photos/ingest/**` | Golden corpus (HEIC, RAW+JPEG, Live Photo, motion photo, video rotation) gives the right kind, date and GPS; decoders sandboxed; crashing file quarantined |
| UMB-PHOTO-3 | Photo backup protocol server, receipts with digest check (includes UMB-CLIENT-4) | L | UMB-PHOTO-1, UMB-CLIENT-2 | `internal/photos/backup/**` | `check` answers only for the asking person; 4 GB upload survives three disconnects; restored phone continues without re-upload; shared bytes stored once without revealing who has them |
| UMB-PHOTO-4 | Phone photo backup, iOS and Android (includes UMB-CLIENT-6, -7, UMB-FILES-11) | L | UMB-PHOTO-3, UMB-CLIENT-3, CORE-MOBILE-2, F-46, F-48 | `mobile/src/photos/**`, `mobile/modules/photo-backup/**` (`feat/mobile-photos`, mobile owner review) | 20k items in the background; metered rules kept; resume not restart; no plain HTTP ever (proxy capture); "free up space" lists only verified items |
| UMB-PHOTO-5 | Dashboard Photos (timeline, viewer, albums, favourites, Trash) | L | UMB-PHOTO-1, UMB-PHOTO-2, UMB-PHOTO-3, F-50 | `dashboard/src/pages/photos/**`, one `App.tsx` line | 60 fps at 50k items; keyboard and screen reader work, axe clean; browser upload reports added vs present |
| UMB-PHOTO-8 | Photos storage safety and backups (includes UMB-CLIENT-5) | M | UMB-PHOTO-1, CORE-BACKUP-5, CORE-BACKUP-7 | `internal/photos/safety/**`, `apps/photos/` backup block | Restore keeps albums and receipts, phones do not re-upload; `verified` only after a verified restore; weekly rehash catches a flipped byte; one-release rollback stays readable |
| UMB-ACCT-4 | People API: `/v1/users`, enrolment links, disable, tombstoned delete, last-owner rule | M | CORE-SEC-10 | `core/onemind_core/users.py`, one migration | Owner never receives a credential; deleting the last owner 409; interrupted delete resumes; ids never reused |
| UMB-ACCT-5 | App access and forward-auth policy | M | CORE-SEC-10, CORE-NET-P1 | `core/onemind_core/access.py`; one hook in `forward_auth.py` via the net stream | Guest on adults-only app 403; client-sent identity header stripped; access removed cuts streams within 1 s; agent token on an app host 401 |
| UMB-ACCT-6 | OIDC clients for apps at install; header mapping for header apps | M | UMB-ACCT-5, CORE-SANDBOX-2 | `core/onemind_core/oidc_clients.py`; executor hook via the sandbox owner | Two people in the same OIDC app see separate libraries; removing the app deletes its client |
| UMB-ACCT-7 | Child policy and access requests | M | UMB-ACCT-5, UMB-ACCT-2, F-35 | `core/onemind_core/household.py`, one migration | Outside a window 403 with the next time; no non-allowed app even by URL; 6th request a day 429; request shows in Approvals |
| UMB-ACCT-8 | CLI groups `users`, `access`, `sessions` | S | UMB-ACCT-4, UMB-ACCT-5, DEV-CLI-1 | `cmd/onemind/cli/{users,access,sessions}.go` | Golden output; step-up opens the browser; secrets printed once |
| UMB-ACCT-9 | MCP tools for people and access requests | S | UMB-ACCT-5, DEV-MCP-2 | `core/onemind_core/mcp/**` | An adult's agent cannot request beyond that adult; no tool returns sessions or credentials |
| UMB-ACCT-10 | Dashboard: sign-in, first boot, People, Access card, child Home, My account | L | UMB-ACCT-4, UMB-ACCT-5, UMB-ACCT-7, UMB-DESK-1 | `SignIn.tsx` (security), `Settings*.tsx`, `AppDetail.tsx` (dashboard), `ui/**` | Invite → enrol on a second profile with a virtual authenticator → app opens; child Home hides other apps; axe clean |
| UMB-ACCT-11 | Phone: OIDC sign-in in the system browser, secure refresh token, child Home | M | UMB-ACCT-10, CORE-MOBILE-3 | `mobile/**` | Revoked session signs out on next refresh; token never in logs or plain storage |
| UMB-ACCT-12 | Identity in backups and restore | S | UMB-ACCT-1, CORE-BACKUP-8 | `backups.py` hook (backups owner), `internal/backup/**` | Clean-box restore: people and passkeys work, sessions invalid, restore audited |
| UMB-APP-1 | App gate computes install size, archs, release notes, gallery checks | M | UMB-APP-18 | `sdk/tools/{app-gate,app-scaffold,app-readme}` | Size, archs and notes written to `scan.json`; hot-linked gallery URL rejected |
| UMB-APP-4 | Lifecycle actions start, stop, restart, update, configure with progress events (includes UMB-AGT-7) | M | UMB-APP-0, UMB-AGT-1, CORE-SANDBOX-2 | `executors.py` (sandbox), `events.py`, `action_types.py` (gateway core) | ≥ 4 steps with rising percent; stop/start round trip on k3d; from MCP each type waits for approval |
| UMB-APP-5 | Remove keeps data; separate owner-only data delete with typed confirmation and final snapshot | S | UMB-APP-0, CORE-BACKUP-1, CORE-SEC-2 | `executors.py` (install sandbox) | PVC stays Bound after remove; reinstall reattaches; data delete needs passkey; agent request 403 |
| UMB-APP-9 | Host ports with conflict check in the plan; avahi name per app | S | UMB-APP-3, CORE-NET-P1 | `policy.py` (sandbox), net stream edge files | Two apps on 53/udp: second plan shows the conflict and approve → 409; name removed with the app |
| UMB-APP-13 | App page and Market polish: facts band, permissions, notes, related apps, revisions, Sources | M | UMB-APP-1, UMB-APP-3, UI-LEAP | `dashboard/src/pages/{Market,AppDetail}.tsx`, components from `ui/**` | Licence, tier, scan date, size, archs, permissions, notes shown; Install disabled with a reason when incompatible or stale |
| UMB-AGT-5 | `onemind mcp pair` and `onemind mcp setup <client>`; keychain; config writer with backup | M | UMB-AGT-3, DEV-MCP-7, CORE-NET-P1 | `internal/mcpbridge/**`, `cmd/onemind/cli/mcp.go` | Configs hold no secret; bridge refuses a hub outside the pinned CA |
| UMB-AGT-6 | Troubleshooting tools: app status and logs, node logs, system health; redaction; `troubleshooter` bundle | M | DEV-MCP-1, DEV-MCP-5, UMB-APP-12 | `mcp/catalog.py`, `mcp/untrusted.py` | Planted secrets never appear; lines in `<untrusted>`; 600 lines → 500 with `truncated` |
| UMB-AGT-10 | Agents page, Connect wizard, pairing card, agent activity, "Agent at work" strip (dashboard and phone) | L | DEV-MCP-2, UMB-AGT-3, CORE-DASH-4, PA-UI, F-53, F-55 | `dashboard/src/pages/SettingsAgents.tsx`, `dashboard/src/components/{PairingCard,AgentStrip}.tsx`, `mobile/src/screens/AgentsScreen.tsx` | Wizard reaches "Connected" with no secret in the DOM; card caps scopes; strip within 5 s; axe clean |
| UMB-AGT-9 | `request_access` deep links and the access landing | S | DEV-MCP-2, UMB-AGT-10 | `mcp/catalog.py`, `SettingsAgents.tsx` | Changes no grant and files no action; link expires in 24 h; widening without passkey 403 |
| UMB-AGT-11 | Agent tokens wiped on restore; conformance for pairing and new tools | S | DEV-MCP-2, CORE-BACKUP-6, DEV-MCP-8 | restore path in `internal/backup/**`, `test/mcp-conformance/**` | After a restore drill personal and static tokens 401, app principal works with a new token |
| UMB-CLIENT-8 | Desktop app v1 (Tauri): tray, discovery, pairing, status, open in browser (includes UMB-SYS-11) | M | UMB-CLIENT-2, UMB-CLIENT-3, F-44 | `desktop/**`, `.github/workflows/ci-desktop.yml` | macOS, Windows and Ubuntu builds in CI; `active` only after owner approval; wrong CA refused; installer < 25 MB; idle RAM < 120 MB |
| UMB-CLIENT-10 | Desktop approvals, alerts and events | S | UMB-CLIENT-8, CORE-NOTIFY-1, CORE-SEC-2, DEV-API-8 | `desktop/src/approvals/**`, `desktop/src-tauri/src/events.rs` | New pending action shown in < 5 s; notification click opens the card, never approves |
| UMB-CLIENT-13 | MCP read tools `list_devices`, `photo_backup_status` | S | UMB-CLIENT-2, UMB-PHOTO-3, DEV-MCP-1 | `core/onemind_core/mcp/**` (MCP owner) | No key material or SMB user names; device and share writes 403 for agents |
| UMB-CLIENT-14 | Dashboard Devices page | S | UMB-CLIENT-2 | `dashboard/src/pages/SettingsDevices.tsx` | Pending device is an approval card; key-storage badge; revoke audited |
| UMB-DESK-6 | Jobs tray bound to `action.progress` | M | UMB-DESK-0, UMB-APP-4, UI-LEAP | `ui/src/components/JobsTray.tsx`; executor progress via the sandbox owner | Entry within 1 s of `dispatched`; restored after reload; failed job links to its audit entry |
| UMB-DESK-9 | Home and Edit Home wired to the hub | M | UMB-DESK-1, CORE-DASH-8, CORE-DASH-2, UI-LEAP, F-36 | `dashboard/src/pages/{Home,HomeEdit}.tsx`, `dashboard/src/api/**` | Wallpaper change shows in a second browser within 2 s; dock order kept after reload; both layouts pass axe; offline Home labelled "last known" |
| UMB-DESK-10 | Shortcuts with a fenced icon fetch | S | UMB-DESK-1 | `core/onemind_core/shortcuts.py`, `Tile.tsx` shortcut variant | Loopback, link-local, private and redirect-to-private → 422; 2 MiB page cut at 512 KiB; icon stored as PNG ≤ 128 px |
| UMB-DESK-11 | Welcome tips on a new Home | S | UMB-DESK-9 | `dashboard/src/pages/Home.tsx`, `ui/src/components/TipCard.tsx` | Closing all tips is remembered; our own copy; reduced motion stops animation |
| UMB-DESK-16 | Rendered accessibility and performance gate for Home | S | UMB-DESK-9 | `ui/tests/e2e/**`, `.github/workflows/ui-e2e.yml` | Zero axe violations across layouts, themes and three wallpapers; initial JS > 200 KB gzip fails |
| UMB-SYS-6 | Wi-Fi and static IP with automatic revert | M | CORE-UPDATE-2, CORE-SEC-2 | `internal/netcfg/**`, `cmd/onemind/cli/net.go`; NetworkManager via the image stream | Unconfirmed wrong gateway reverts within 60 s with an alert; confirmed change survives reboot; refused during an OS trial |
| UMB-SYS-8 | Factory reset as a critical action | M | CORE-UPDATE-8, CORE-SEC-2, CORE-BACKUP-2 | `internal/rescue/**`, `os_updates.py` (updates) | Needs passkey and typed name; offers and verifies a final backup; off-box repositories untouched; agent 403 |
| UMB-SYS-10 | Restart and shut down a node | S | CORE-UPDATE-2 | `os_updates.py` (updates), `Settings*.tsx` (dashboard) | Request lists affected apps; refused during an OS trial; requester and approver audited |
| UMB-MACH-1 | Machines lab kit and feasibility (LT-MACH-1…3) | M | – | `lab-kits/machines/**`, `research-output/evidence/lab/machines/` | Results recorded; F-56 confirmed or reopened |

### UMB in S3

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| UMB-STOR-10 | Raspberry Pi 5 storage lab: dual-NVMe and NVMe + USB mirror, power-cut loop | M | UMB-STOR-4 | `lab-kits/**`, report in `docs/umbrel2/` | 100 power cuts during writes and `replace`: zero uncorrectable errors; MB/s and USB bridge list recorded |
| UMB-STOR-12 | Decision: HDD + SSD acceleration and a ZFS "NAS tier" licence review | S | UMB-STOR-10 | `docs/DECISIONS.md`, `docs/umbrel2/` | Written decision with HDD measurements; no code until accepted |
| UMB-STOR-14 | NAS mounts in: SMB with mDNS discovery and NFS; credentials sealed | M | UMB-STOR-13, CORE-SEC-5 | `internal/storage/netmount/**`, `storage.py` | Password never in ledger, logs or process list; server down → `failing` and an alert, recovers by itself |
| UMB-FILES-5 | SMB and WebDAV out, per-person and per-device users (includes UMB-CLIENT-9 server side) | M | UMB-FILES-2, F-45 | `internal/files/{smb,webdav}/**`; Samba packaging per F-45 | Mac and Windows mount `home:<person>` with that person's credentials only; guest refused; SMB1 refused; WebDAV over the box CA |
| UMB-FILES-8 | Cloud import with rclone: Google Drive, Dropbox, OneDrive, WebDAV; iCloud experimental | L | UMB-FILES-2, CORE-SEC-5, CORE-MOBILE-1, F-41, F-42 | `internal/cloudimport/**`, `cloud_imports.py`, `cmd/onemind/cli/cloud.go` | Resumable after reboot; upstream delete lands in Trash; no token outside the secret store; expired token → `reauth` and one alert |
| UMB-FILES-9 | Cloud account as a backup target (restic `rclone:` backend; extends CORE-BACKUP-4) | S | CORE-BACKUP-4, UMB-FILES-8 | `internal/backup/**` | Repository opens with plain restic + rclone and the owner key alone; counts as the off-site copy |
| UMB-FILES-10 | Migrate files in from a NAS, old server or another self-hosted OS | M | UMB-STOR-14, UMB-FILES-8 | `internal/cloudimport/migrate/**`, `cmd/onemind/cli/migrate.go` (with CORE-DEPLOY-6) | Dry run lists counts and bytes; 50k files over SMB survive a reboot mid-way; 1 % checksum sample matches |
| UMB-PHOTO-6 | Household photo sharing | M | UMB-PHOTO-5, CORE-SEC-10 | `internal/photos/share/**`, `dashboard/src/pages/photos/sharing/**` | Another adult gets 404 on private assets; contributor additions without a byte copy; child library visible only to parents |
| UMB-PHOTO-7 | Map and places, offline | M | UMB-PHOTO-2 | `internal/photos/places/**`, `dashboard/src/pages/photos/map/**` | Tiles and place names load with the network unplugged; no outbound request while browsing; OSM attribution shown |
| UMB-PHOTO-9 | Photos MCP tools and request-only actions | M | UMB-PHOTO-1, DEV-MCP-2, DEV-PLG-4 | `internal/photos/agent/**`; catalog via the projection PR | Tools only with `photos:read`; no tool reaches purge or a child's library; EXIF injection stays inert |
| UMB-PHOTO-10 | Photos CLI | S | UMB-PHOTO-1, DEV-CLI-1 | `cmd/onemind/cli/photos.go` | Golden output; `import` creates an action |
| UMB-PHOTO-11 | Importers: USB and SD card, folder, Google Takeout, iCloud Photos export | M | UMB-PHOTO-2 | `internal/photos/importers/**` | Folder names as albums on request; Takeout dates and places applied; Live Photo pairs kept |
| UMB-PHOTO-13 | Immich Market app with read-only attach to the OneMind library | M | UMB-PHOTO-1, W2-PIPE | `apps/immich/**` (app pipeline) | Gate passes with notices; Immich cannot write the library; uninstall leaves it intact; ML off after install |
| UMB-APP-10 | Community sources pinned to a commit, `source.*` actions, on-box scan for first install | M | UMB-APP-2, CORE-DEPLOY-2 | `core/onemind_core/{catalog,scanjob}.py` | Adding a source needs approval; upstream push changes nothing; failing scan cannot be approved |
| UMB-APP-14 | CLI `onemind app` lifecycle verbs and `onemind source` (extends DEV-CLI-4) | M | UMB-APP-0, DEV-CLI-4, UMB-APP-10 | `cmd/onemind/cli/{app,source}.go` | Each write prints the action id; `app plan` hash equals the REST plan |
| UMB-APP-17 | Image cleanup on nodes after update and remove | S | CORE-UPDATE-6 | `internal/agent/**` (onemindd owner) | Old digest gone within one cycle; running digests never removed |
| UMB-AGT-8 | Files read tools and `files.apply_plan` with snapshot and Undo | L | UMB-AGT-1, UMB-FILES-6, UMB-FILES-7, F-54 | `mcp/catalog.py`, `files.py` (files owner), snapshot via `internal/backup/**` | 200-op plan is one card; stale `plan_sha256` 409; Undo restores every path byte-for-byte; no overwrite; symlink escape refused |
| UMB-CLIENT-9 | Desktop mounts of SMB shares with per-device credentials | M | UMB-CLIENT-8, UMB-FILES-5 | `desktop/src-tauri/src/mount/**` | Mounts on macOS, Windows and Linux; revoked device fails the next operation; a child device cannot list the owner's share |
| UMB-CLIENT-11 | Laptop folder backup with restic to the box (includes UMB-PHOTO-14) | M | UMB-CLIENT-8, CORE-BACKUP-4 | `desktop/src-tauri/src/backup/**` | 10 GB backed up; deleted file restored from the tray; pauses on battery < 20 % and metered networks |
| UMB-CLIENT-12 | Desktop release: signing, notarization, MSIX, DMG, AppImage, signed updater | S | UMB-CLIENT-8, F-59 | `.github/workflows/desktop-release.yml`, `desktop/release/**` | Notarized DMG; MSIX installs on clean Windows 11; tampered or downgraded update rejected; keys only in a GitHub environment |
| UMB-DESK-12 | Live usage across fleet, node and app (includes UMB-SYS-5) | M | UMB-DESK-0, CORE-DOGFOOD-4 | `core/onemind_core/metrics.py` (dogfood), `dashboard/src/pages/Usage.tsx` | Every number has `measured_at`; silent node shows stale, not zero; adults see only shared apps; collector ≤ 1 % of a Pi 5 core |
| UMB-DESK-13 | CLI `onemind home` and `onemind usage` | S | UMB-DESK-1, UMB-DESK-12, DEV-CLI-1 | `cmd/onemind/cli/home.go` | Golden table and JSON; stale etag retries once then exits with the conflict code |
| UMB-DESK-14 | MCP `get_usage` and `home.change` requests | S | UMB-DESK-1, UMB-DESK-12, DEV-MCP-1, F-38 | `core/onemind_core/mcp/**`, action type registry | `home.change` waits for approval by the Home's person; audit names the agent as requester |
| UMB-MACH-0 | Contract: machine routes, scopes, action types, events | S | C12-A, F-57 | contract (`contract/12-machines`) | Merged; API.md scope and risk tables list the entries |
| UMB-MACH-2 | KubeVirt + CDI as a signed OS extension; `kvm` and `iommu` capabilities | M | UMB-MACH-1, CORE-FABRIC-4, OS-SECPIPE, F-56, F-58 | `os/rootfs/layers/machines/**`, add-only pins, `internal/detect/**` after FABRIC-4 | Enable/disable idempotent; pinned by digest with licence; heartbeat shows `kvm` on metal, not in a VM without nested virt |
| UMB-MACH-3 | Gateway machines module: records, render, executor hook, health gate | L | UMB-MACH-0, UMB-MACH-2, CORE-SANDBOX-2, DEV-API-1 | `core/onemind_core/machines/**`, one migration, one `routes.py` line | Pure golden-tested render; plan hash changes with any resource; failed install cleans up; agent approve 403 |
| UMB-MACH-4 | Console broker and dashboard console (noVNC) | M | UMB-MACH-3, CORE-SEC-1 | `machines/console.py`, `dashboard/src/machines/console/**`, noVNC pin with the dashboard owner | Ticket reuse and expiry refused; view-only input dropped; slow client cut at the buffer cap |
| UMB-MACH-5 | Machine template catalog and image import or upload | M | UMB-MACH-3 | `sdk/machines/catalog.yaml`, `sdk/schema/onemind.machine-template.schema.json`, `machines-catalog.yml` | Weekly URL and SHA-256 check; wrong checksum leaves no PVC; upload from Files resumes |
| UMB-MACH-13 | Machines dashboard: list, wizard, plan card, settings, Home tile | M | UMB-MACH-3, CORE-DASH-1 | `dashboard/src/pages/Machines*.tsx`, `dashboard/src/machines/**` | Screens render from fixtures; plan card complete; no umbrelOS asset or string |

### UMB in S4+

| Id | Title | Size | Depends on | Owner paths | Acceptance |
|---|---|---|---|---|---|
| UMB-PHOTO-12 | Opt-in semantic search and face grouping on the box | L | UMB-PHOTO-0, UMB-PHOTO-5, F-49, F-51 | `internal/photos/ml/**`, `dashboard/src/pages/photos/people/**` | Only allowed models load (hash pinned); pauses when busy; deleting a face cluster deletes its embeddings; nothing leaves the box |
| UMB-CLIENT-15 | macOS File Provider and Windows Cloud Files instead of SMB | L | UMB-CLIENT-9 | `desktop/native/**` | Decision record first: only if SMB proves unreliable over the mesh (measured) |
| UMB-MACH-6 | Windows guests: TPM, secure boot, own answer-file generator, virtio drivers | M | UMB-MACH-5 | `machines/windows/**` | LT-MACH-4 passes; product key never in a `GET` or log |
| UMB-MACH-7 | Machine networking: NAT with forwards, NetworkPolicy, wired LAN bridge | M | UMB-MACH-3, CORE-NET-P1 | `machines/network.py`; bridge unit via the image stream | NAT machines isolated from each other and box services; LAN mode refused on Wi-Fi-only nodes |
| UMB-MACH-8 | USB passthrough (applied on restart) | S | UMB-MACH-3, UMB-MACH-2 | `machines/devices.py` | Host-used device refused until confirmed; plan shows vendor, product, serial |
| UMB-MACH-9 | GPU passthrough (VFIO) on the Pro box | M | UMB-MACH-8, CORE-DOGFOOD-5 | `machines/devices.py`, IOMMU detection in `internal/detect/**` | Shared IOMMU group refused with the group listed; GPU returns to the host after stop |
| UMB-MACH-10 | Machine backups with guest freeze and a restore that boots | M | UMB-MACH-3, CORE-BACKUP-5, CORE-BACKUP-7 | hook in `internal/backup/**`, `machines/backup.py` | Freeze/thaw around the snapshot; badge green only after a boot check |
| UMB-MACH-11 | MCP machine tools and the agent control lease | M | UMB-MACH-4, DEV-MCP-3, CORE-SEC-2 | `core/onemind_core/mcp/**` (with the MCP owner), `machines/control.py` | Screen without a lease → `lease_required`; owner tap ends the lease within 1 s; inputs audited without typed text |
| UMB-MACH-12 | Machine quotas and sharing for the household | S | UMB-MACH-3, CORE-SEC-10 | `machines/quotas.py` | Over-quota plan refused; guest console only if shared |
| UMB-MACH-14 | Machine desktop extras: clipboard, sound, virgl, touch console | L | UMB-MACH-4 | `machines/sidecar/**`, `dashboard/src/machines/console/**` | Per KubeVirt pin the hook test passes or the feature is off |
| UMB-MACH-15 | CLI `onemind machines` | S | UMB-MACH-3, DEV-CLI-1 | `cmd/onemind/cli/machines.go` | Golden output; stable `--json` |
| UMB-MACH-16 | Android template (Linux guest + Waydroid, own provisioning) | S | UMB-MACH-5, UMB-MACH-14 | `sdk/machines/provision/android/**` | Boots to the launcher on x86; Pi result recorded as experimental |
