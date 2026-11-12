<!-- SPDX-License-Identifier: Apache-2.0 -->
# The leap: OneMind OS core and developer surface

**Date:** 2026-11-12 · **Status:** proposal for the founder. Nothing here changes [`docs/DECISIONS.md`](../DECISIONS.md) or the contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md). Where a spec needs a contract change, that change goes in its own contract PR first.

> **Explain it like I am the founder**
> The leap is the plan to go from "the proof of concept works" to "I run my own services on OneMind every day, and other developers can build on it".
> It has two halves: the **core OS** (security, fabric, backups, deployments, automation, notifications, updates, dashboard, phone apps, website) and the **developer surface** (API, SDKs, CLI, MCP, plugin SDK).
> Every page keeps one rule: **AI agents and plugins can only ask. You approve. The OS does it. Everything is written down.**
> Start with [BACKLOG.md](BACKLOG.md) for the order, [STATUS.md](STATUS.md) for where things are, and [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md) for what only you can decide.

## 1. Positioning

**OneMind is the self-hosted OS where AI agents can only ask. The gateway, not the prompt, makes them wait for your tap.**

Others limit *what* an agent can touch (Home Assistant's MCP server exposes only chosen entities; umbrelOS 2.0 has per-agent scopes). OneMind adds a step: every change an agent or plugin wants is a **request**; the owner approves it, with a passkey on the phone once passkeys land; the OS carries it out; every step goes on a hash-chained record you can check. The gateway enforces this today (`core/onemind_core/actions.py`, `auth.py`, `audit.py`; contract §3 and §11).

> **Tagline:** *Your AI asks. You decide. The box remembers.*

Honest scope today: the only actions are `app.install` and `app.remove`; every OS-level claim was proven in emulation only (QEMU battery). No update claim before metal gate G1, no actuation claim before LT-VM-18 passes at G4.

## 2. What the leap is

| Goal | How we know it is reached |
|---|---|
| The founder replaces his own self-run cluster with OneMind OS | [core/DOGFOOD.md](core/DOGFOOD.md): 30 consecutive days of daily services on OneMind with no manual SSH fix |
| It is safe to hand to an AI agent | Agents and plugins can request but never approve (403 on every path, tested in REST, MCP, CLI and SDKs); approvals bind to the exact plan; the audit chain verifies and is checkpointed off the box |
| Developers can build on it | One OpenAPI spec generates the TypeScript, Python and Go SDKs; the CLI and MCP bridge are thin layers over the same calls; a third party can build the Hello plugin from the website alone |
| It is pleasant to use every day | Redesigned dashboard on `ui/`, phone apps with push and passkey approvals, docs, blog and forum |

**Not in the leap (parked to S4+):** robotics, drones, TAK extensions, the desktop shell, XR, local AI as a core feature, federation, a paid tier. Actuation stays lab-only until LT-VM-18 passes.

## 3. Reading order

1. This page, then [WORKSTREAMS.md](WORKSTREAMS.md) (who owns which files) and [BACKLOG.md](BACKLOG.md) (the order).
2. [core/README.md](core/README.md), then [core/SANDBOX.md](core/SANDBOX.md) and [core/SECURITY.md](core/SECURITY.md): they gate everything else.
3. [dev/API.md](dev/API.md): every other developer spec builds on its routes, errors, scopes and events.
4. The rest in any order. [STATUS.md](STATUS.md) shows live state; [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md) lists open choices.
5. The record of everything merged is the repo-root [CHANGELOG.md](../../CHANGELOG.md).

## 4. Every spec

| Spec | Area | Epic ids |
|---|---|---|
| [core/README.md](core/README.md) | Index of the core OS specs, critical path, no-collision rules | – |
| [core/SANDBOX.md](core/SANDBOX.md) | Install sandbox: object allowlist, PSA restricted, RBAC, default-deny network, approval bound to `plan_sha256` | CORE-SANDBOX-1…6 |
| [core/SECURITY.md](core/SECURITY.md) | HTTPS per box, passkeys and signed approvals, tokens, NATS auth, LUKS2, audit checkpoints, kill switch, identity floor | CORE-SEC-1…10 |
| [core/FABRIC.md](core/FABRIC.md) | Owner-approved node join, per-node identity, drain and remove, placement, leaf nodes, fleet view | CORE-FABRIC-1…6 |
| [core/BACKUPS.md](core/BACKUPS.md) | restic agent, three keys, destinations, app hooks, approval-gated restore, verified-restore badge | CORE-BACKUP-1…8 |
| [core/DEPLOYMENTS.md](core/DEPLOYMENTS.md) | Your own services as private apps, on-box scan, revisions and rollback, write-only secrets, migration kit | CORE-DEPLOY-1…6 |
| [core/AUTOMATION.md](core/AUTOMATION.md) | Risk classes, triggers that create actions, standing approvals, dry run | CORE-AUTO-1…5 |
| [core/NOTIFICATIONS.md](core/NOTIFICATIONS.md) | Alert centre, content-free push, repairs, channels | CORE-NOTIFY-1…7 |
| [core/UPDATES.md](core/UPDATES.md) | OS security pipeline, updater, `/v1/os`, app updates, rescue console, fleet staging | CORE-UPDATE-1…9 |
| [core/DASHBOARD.md](core/DASHBOARD.md) | Dashboard redesign onto `@onemind/ui`, plan card, new screens, PWA | CORE-DASH-1…8 |
| [core/MOBILE.md](core/MOBILE.md) | Android and iPhone shells to v1: pairing, passkey approvals, push | CORE-MOBILE-1…7 |
| [core/WEBSITE.md](core/WEBSITE.md) | Website with docs, generated references, apps catalog, blog, forum | CORE-WEB-1…6 |
| [core/DOGFOOD.md](core/DOGFOOD.md) | Capability checklist and migration waves for the founder's own services | CORE-DOGFOOD-1…6 |
| [dev/API.md](dev/API.md) | Gateway REST API v1: conventions, errors, pagination, scopes, actions v1, events, audit, phase-B routes | DEV-API-1…14 |
| [dev/SDK.md](dev/SDK.md) | TypeScript, Python and Go SDKs generated from OpenAPI, conformance, publishing | DEV-SDK-1…10 |
| [dev/CLI.md](dev/CLI.md) | The `onemind` CLI: command tree, output and exit codes, contexts, every command | DEV-CLI-1…14 |
| [dev/MCP.md](dev/MCP.md) | The agent door: MCP catalogue, scopes and grants, limits, injection defences, stdio bridge | DEV-MCP-1…12 |
| [dev/PLUGIN-SDK.md](dev/PLUGIN-SDK.md) | Plugins for third parties: manifest, permissions, widgets, agent tools, signing, dev loop, tutorial | DEV-PLG-1…16 |
| [WORKSTREAMS.md](WORKSTREAMS.md) | Every stream and branch, owned paths, hotspots, merge order, how to claim a stream | – |
| [BACKLOG.md](BACKLOG.md) | All epics in one dependency-ordered table, grouped into sprints S0–S4+ | – |
| [STATUS.md](STATUS.md) | State, branch and PR of every epic | – |
| [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md) | Founder decisions with proposed defaults, and points the contract owner must settle | – |

## 5. Shared rules every spec follows

These names were reconciled across the specs on 2026-11-12. If a spec and this table disagree, this table wins until the contract PR settles the point; once a contract PR merges, the contract wins.

| Topic | The one rule | Defined in |
|---|---|---|
| Who may approve | Only a person with role `owner`, or a standing approval the owner made, inside its limits. Agents, plugins, automations and nodes request only | [core/README.md](core/README.md), contract §3 |
| Approval binding | One field, `plan_sha256`: the SHA-256 of the gateway's canonical plan (params, target, objects and effects). It appears on the action, in the MCP `preview_action` output, in the passkey challenge and in the approve body. A stale value returns `409 stale_precondition` | [core/SANDBOX.md](core/SANDBOX.md) §3.2, [dev/API.md](dev/API.md) §5.11 |
| Approve with a passkey | `POST /v1/actions/{id}/approve-options` returns a challenge; `POST /v1/actions/{id}/approve` takes `{"plan_sha256", "webauthn": {…}}` | [core/SECURITY.md](core/SECURITY.md) §3.2 |
| Risk classes | Five: `read`, `write`, `sensitive` (also called grant-widening: credentials, grants, `app.install`, `node.join`), `destructive`, `actuate`. Standing approvals may cover only `read` and `write` | [dev/API.md](dev/API.md) §5.11, [core/AUTOMATION.md](core/AUTOMATION.md) §3.2 |
| Pending cap | At most **10** `awaiting_approval` actions per requesting principal; the 11th gets `429 rate_limited` with `Retry-After` (REST) or a `rate_limited` tool error (MCP) | [dev/API.md](dev/API.md) §9, [dev/MCP.md](dev/MCP.md) §5.4 |
| Who am I | `GET /v1/me`, served by DEV-API-5. MCP exposes it as the `whoami` tool | [dev/API.md](dev/API.md) §5.8 |
| Live events | `GET /v1/events` (SSE), `?types=`, `Last-Event-ID` resume, `stream.reset`, `: keepalive` every 15 s. Events carry ids and states only | [dev/API.md](dev/API.md) §10 |
| Node join | Owner makes a ticket (`onemind fabric qr`, `POST /v1/fabric/join-tickets`); the node files a request with the code (`onemind fabric join <code>`); the owner approves the `node.join` action | [dev/API.md](dev/API.md) §5.1 |
| CLI commands | One tree, [dev/CLI.md](dev/CLI.md) §3. Command files live in `cmd/onemind/cli/<group>.go`, one registration line each in `cmd/onemind/cli/root.go` | [dev/CLI.md](dev/CLI.md) §11 |
| MCP code | `core/onemind_core/mcp.py` becomes the package `core/onemind_core/mcp/` in DEV-MCP-1; plugin tool projection goes through `mcp/catalog.py` | [dev/MCP.md](dev/MCP.md) §11 |
| SDK packages | `@onemind/sdk` (npm), `onemind-sdk` / `onemind_sdk` (PyPI), Go module under `sdk/go`. SDK.md owns generators and layout; DEV-API-14 is superseded by DEV-SDK-1…10 | [dev/SDK.md](dev/SDK.md) |
| Phase-B route modules | The API spec defines route shapes; the core spec's epic owns the module (`fabric.py`, `backups.py`, `notify/`, `automation.py`, `policies.py`, `os_updates.py`) | [WORKSTREAMS.md](WORKSTREAMS.md) §3 |

The architecture stream's contract §12 draft (`docs/architecture/CONTRACT-12-DRAFT.md`, branch `docs/core-architecture`, not merged) still uses some different names. The differences are listed in [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md) §2 for the contract owner.

## 6. Where the 90-day plan's epics went

The founder's 90-day plan (2026-11-12, Day 1 = 2026-11-16) numbered its epics E0–E17. Specs still cite them as "plan E<n>".

| Plan epic | Now covered by |
|---|---|
| E0 Land wave 2 | S0 rows in [BACKLOG.md](BACKLOG.md) (W2-*, OS-*), CORE-UPDATE-1 |
| E0S Install sandbox | CORE-SANDBOX-1…6 |
| E1 Workbench (G0) and gate re-sync | PLAN-E1 |
| E2 Governed Agents demo | CORE-SEC-6, CORE-DASH-4, DEV-MCP-5, DEV-CLI-5, W2-HERMES |
| E3 Phone approvals over HTTPS | CORE-SEC-1, -2, -7, CORE-NOTIFY-3, CORE-MOBILE-2…4, CORE-DASH-3 |
| E4 Update engine on metal (G1) | CORE-UPDATE-2…4 |
| E5 App factory and trust cards | W2-PIPE, W2-SEEDS, PLAN-E5 |
| E6 Manifest v1 freeze | PLAN-E6 |
| E7 Typed capabilities and risk policy | CORE-AUTO-1 (policy); PLAN-E7-LAB (actuation, parked) |
| E8 Identity floor | CORE-SEC-10 |
| E9 Backups and badge | CORE-BACKUP-1…8 |
| E10 Pi 5 image (G2) | PLAN-E10 |
| E11 Jetson and platform floor (G3) | PLAN-E11 |
| E12 Fabric v0 | CORE-FABRIC-1…6 |
| E13 Remote access and rescue | CORE-DOGFOOD-3, CORE-UPDATE-8 |
| E14 TAK field kit preview | PLAN-E14 (parked to S4+ by the founder focus) |
| E15 Robot simulation | PLAN-E15 (parked) |
| E17 Launch program | CORE-WEB-5 |

Gate dates are unchanged: G0 2026-11-22, G1 2026-12-13, G2 2026-12-27, G3 2027-01-10, G4 2027-02-14.

## 7. Founder decisions (summary)

The full list, with the epics each one blocks, is [DECISIONS-NEEDED.md](DECISIONS-NEEDED.md). The ones that block sprint S1:

| # | Question | Proposed default |
|---|---|---|
| F-1 | Phone HTTPS: per-box CA or Tailscale certificate first? | Per-box CA; Tailscale certificate when remote access is on |
| F-2 | Passkey on every approval, or only on risky types? | Every approval, once passkeys exist |
| F-8 | Accept `cobra` as the CLI library? | Yes |
| F-10 | Hermes licence: confirm from the pinned release's LICENSE file | Ship only after it is confirmed |
| F-11 | Risk policy | Reads allowed; writes ask and can be remembered; sensitive, destructive and actuate always ask |
| F-17 | npm scope and PyPI owner for the SDKs | `@onemind/sdk` if the org can be created, else `@onemindos/sdk`; org-owned PyPI with trusted publishing |
