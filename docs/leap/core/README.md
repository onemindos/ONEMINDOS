<!-- SPDX-License-Identifier: Apache-2.0 -->
# Leap: core OS specs

**Date:** 2026-11-12 · **Status:** proposal for the founder. These specs change no decision in [`docs/DECISIONS.md`](../../DECISIONS.md) and no line of the contract [`sdk/contracts/poc-v0.md`](../../../sdk/contracts/poc-v0.md). Where a spec needs a contract change, it says so and that change goes in its own PR.
**Founder focus:** the core OS first, so the founder can replace his own self-run services with OneMind OS and use it daily, then open it to developers. Robotics, drones and TAK extensions come later.

> **Explain it like I am the founder**
> Each page below is one part of the core OS, written so a coding agent can build it without asking you anything except the decisions listed at the end.
> Every page follows one rule: **AI agents and plugins can only ask. You approve. The OS does it. Everything is written down.**
> Each page names the files it touches and which branch owns them, so parallel builders do not collide.

## The rule every spec keeps

| Who | May do | May never do |
|---|---|---|
| Agent or plugin principal | Read what its grant allows; **request** an action (`POST /v1/actions`, MCP `request_action`) | Approve, deny, change its own grant, reach the executor |
| Owner (person) | Approve or deny; **reduce** power at once (revoke a token, suspend an agent, disable an automation) | Skip the audit log |
| Standing approval (automation policy the owner created) | Accept a request **inside the bounds the owner set**, recorded as `approved_by: policy:<id>` | Cover a type whose risk is `sensitive` (grant-widening), `destructive` or `actuate` ([API.md](../dev/API.md) §5.11) |
| Gateway + executor | Carry out an accepted action; record every step in the hash-chained audit log | Act on anything that is not an accepted action |

**Reducing power is instant; adding power is an action.** That one line decides most edge cases in these pages.

## Index

| Spec | Area | Epic ids | Plan epics (90-day plan) | Deeper doc |
|---|---|---|---|---|
| [SANDBOX.md](SANDBOX.md) | Install sandbox: object allowlist, PSA restricted, RBAC, network | CORE-SANDBOX-1…6 | E0S | [`HARDENING-BACKLOG.md`](../../security/HARDENING-BACKLOG.md) H-01…H-04 |
| [SECURITY.md](SECURITY.md) | HTTPS on the LAN, passkeys, tokens, NATS auth, LUKS2, audit checkpoints | CORE-SEC-1…10 | E2, E3, E8 | [`HARDENING-BACKLOG.md`](../../security/HARDENING-BACKLOG.md), [`THREAT-MODEL.md`](../../security/THREAT-MODEL.md) |
| [FABRIC.md](FABRIC.md) | Nodes joining, identity, placement, leaves | CORE-FABRIC-1…6 | E12 | `docs/architecture/FABRIC.md` (architecture stream) |
| [BACKUPS.md](BACKUPS.md) | restic agent, three keys, restore, verified-restore badge | CORE-BACKUP-1…8 | E9 | `docs/architecture/BACKUPS.md` (architecture stream), research 06 |
| [DEPLOYMENTS.md](DEPLOYMENTS.md) | Running your own services, history, rollback, secrets | CORE-DEPLOY-1…6 | – (new) | `docs/architecture/DEPLOYMENTS.md` (architecture stream) |
| [AUTOMATION.md](AUTOMATION.md) | Schedules, triggers, standing approvals, dry run | CORE-AUTO-1…5 | E7 (policy part) | `docs/architecture/AUTOMATION.md` (architecture stream) |
| [NOTIFICATIONS.md](NOTIFICATIONS.md) | Alert centre, repairs, private push | CORE-NOTIFY-1…7 | E3 (push part) | `docs/architecture/NOTIFICATIONS.md` (architecture stream) |
| [UPDATES.md](UPDATES.md) | OS security pipeline, updater, app updates, rescue | CORE-UPDATE-1…9 | E0, E4, E10, E13 | `os/update/CHANNEL.md`, `internal/update/README.md` (in flight) |
| [DASHBOARD.md](DASHBOARD.md) | Redesign onto `ui/`, new screens | CORE-DASH-1…8 | E2, E3 | [`docs/DASHBOARD.md`](../../DASHBOARD.md), `docs/design/PLUGIN-UI.md` (design stream) |
| [MOBILE.md](MOBILE.md) | Android and iPhone shells to v1 | CORE-MOBILE-1…7 | E3 | `mobile/README.md` (in flight) |
| [WEBSITE.md](WEBSITE.md) | Astro + Starlight site, docs, blog, forum, hosting | CORE-WEB-1…6 | E17 | `site/` (in flight) |
| [DOGFOOD.md](DOGFOOD.md) | What it takes to run your own services on OneMind daily | CORE-DOGFOOD-1…6 | spans all | this folder |

## Build order across specs (critical path)

```
SANDBOX-1..3 ─► SEC-1 (HTTPS) ─► SEC-2 (passkey) ─► NOTIFY-1..3 ─► MOBILE-2..4 (phone approvals, L1 wk 5)
UPDATE-1 (land) ─► UPDATE-4 (metal, G1) ─► UPDATE-3/5 ─► BACKUP-1..4 ─► BACKUP-7 (badge)
SEC-4 (NATS auth) ─► FABRIC-1 (approved join) ─► FABRIC-4 (placement) ─► DOGFOOD gates
DEPLOY-1..3 ─► DOGFOOD-2 (migration kit)      AUTO-1..3 after NOTIFY-1
DASH-1 (ui/ tokens) runs in parallel from week 1; WEB-1..3 in parallel from week 1
```

## No-collision rules (all specs)

| Rule | Detail |
|---|---|
| One module per feature | Gateway features live in their own file under `core/onemind_core/` (`policy.py`, `tls.py`, `passkeys.py`, `tokens.py`, `backups.py`, `deploys.py`, `automation.py`, `alerts.py`, `fabric.py`, `os_updates.py`). Node-agent features live in `internal/<feature>/` (`internal/backup`, `internal/join`, `internal/rescue`, `internal/update`). |
| Serialized hotspots | `core/onemind_core/app.py` (route registration; after DEV-API-1 a feature adds one line to `core/onemind_core/routes.py` instead), `cmd/onemindd/main.go` (subcommand wiring), `sdk/contracts/poc-v0.md`, `os/versions.lock.yaml`, `sdk/schema/onemind.app.schema.json`. Each feature PR adds **one** registration line or block; the contract and the lock file change in their own small PRs, merged one at a time. |
| Links to in-flight docs | `docs/security/*` (branch `docs/security-threat-model`), `docs/architecture/FABRIC.md` and siblings (branch `docs/core-architecture`) and `docs/design/PLUGIN-UI.md` (branch `feat/design-system`) resolve once those branches merge. |
| Contract first | New routes, action types, error codes or manifest fields go into a contract PR before the feature PR that uses them. The architecture stream's `docs/architecture/CONTRACT-12-DRAFT.md` collects them; where a spec here differs from the merged contract, the contract wins. |
| No private details | Specs and fixtures use `onemind.local`, `<box>`, `example.org` and `om_*_EXAMPLE` tokens. No real addresses, names, tailnets or host paths. |

## Decisions only the founder can make (collected)

The full list across all leap specs, with proposed defaults, is [DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md); shared names (approval digest, risk classes, caps, routes) are fixed in [../README.md](../README.md#shared-rules-every-spec-follows).

| # | Question | Default these specs assume | Spec |
|---|---|---|---|
| F-1 | Phone HTTPS: per-box CA or Tailscale certificate first? | Per-box CA by default; Tailscale certificate when remote access is on | SECURITY, MOBILE |
| F-2 | Step-up (passkey) on every approval, or only on risky types? | Every approval | SECURITY, MOBILE |
| F-3 | Mobile shell: Expo/React Native (built) or Capacitor (research 12)? | Keep Expo; share code through `sdk/ts` | MOBILE |
| F-4 | When to run the iOS APNs relay (needs an Apple developer account)? | After Android push works (week 8+) | NOTIFICATIONS, MOBILE |
| F-5 | Website domain and host | GitHub Pages now, self-hosted on a OneMind box later | WEBSITE |
| F-6 | Standing approvals: allowed for app patch updates? | Yes, for `verified` apps with a passing scan, inside the window | AUTOMATION, UPDATES |
| F-7 | Private deployments: may the owner install an image that failed a scan, with a typed confirmation? | No in v0; yes later with a red "owner override" mark in the audit | DEPLOYMENTS |
