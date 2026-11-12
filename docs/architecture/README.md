<!-- SPDX-License-Identifier: Apache-2.0 -->
# Core architecture, phase B

**Date:** 2026-11-12 · **Status:** design for build agents. It proposes contract changes in [`CONTRACT-12-DRAFT.md`](CONTRACT-12-DRAFT.md); nothing here is binding until each part of that draft is merged into [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) as §12.
**Serves:** the founder focus of 2026-11-12 (replace the founder's own Kubernetes cluster with OneMind OS and use it daily) and the ranked backlog in [`docs/strategy/core-alignment.md`](../strategy/core-alignment.md) §5.
**Changes no decision** in [`docs/DECISIONS.md`](../DECISIONS.md). Where a design choice needs the founder, the doc says **FOUNDER CALL**.

## The documents

| Doc | What it decides | Backlog items (core-alignment §5) |
|---|---|---|
| [FABRIC.md](FABRIC.md) | Hub, worker and leaf roles; join by QR code and one-time ticket; node keys and certificates; NATS leaf topology and auth; k3s join; health and stale states; failure modes; how it replaces a 3-node cluster | 15, 16, 23 (FAB-P1…P3, FAB-B1, FAB-B3, OSU-B1) |
| [BACKUPS.md](BACKUPS.md) | What is backed up, schedules, retention, targets, the three keys and the emergency kit, pre-update snapshots, verified restores and the badge, restore flows | 3, 4, 5, 6 (BAK-*, ONB-B2, ONB-P3) |
| [DEPLOYMENTS.md](DEPLOYMENTS.md) | How core services and apps are deployed and updated; revisions, drift and rollback; health-gated app updates; your own services; the migration kit | 11, 12, 13, 14 (APP-P1…P4, APP-B1, DEP-P1, DEP-P2, DEP-B2) |
| [AUTOMATION.md](AUTOMATION.md) | Schedules, event rules and webhooks that create actions; approval policies with limits; maintenance windows; dry run | 21 (AUT-*), parts of 10 and 20 |
| [NOTIFICATIONS.md](NOTIFICATIONS.md) | Event catalogue, alerts and repairs, routing per person, quiet hours, channels (in-app, Web Push, ntfy/UnifiedPush, iOS relay, email, webhook, Telegram, Matrix), approval deep links | 8, 18, 19, 20 (NOT-*, MOB-P2, MOB-B1, SEC-B2) |
| [CONTRACT-12-DRAFT.md](CONTRACT-12-DRAFT.md) | The proposed §12: REST paths, NATS subjects, payloads and errors for all of the above, in the style of §3 and §11 | all |

Identity (backlog item 1, SEC-P1) and HTTPS (item 2, SEC-P2) are **prerequisites**, not part of this set. These docs assume they exist as described in the core-alignment page and the hardening backlog on branch `docs/security-threat-model` (`docs/security/HARDENING-BACKLOG.md`, items H-05 and H-09). Where an item here needs them, its build step says so.

## The rule every design here keeps

**AI never actuates without human approval** (contract header). Concretely:
- Every change to the system is an **action** in the ledger (contract §3). That covers installs, updates, restores, node joins, automation and policy changes.
- A person, agent, automation or node may **request** an action. Only an **owner** approves it, or an **approval policy** that an owner created, signed and can see (AUTOMATION.md). Some action types can never be approved by a policy (the list is in CONTRACT-12-DRAFT §12.2).
- Agents never approve, never create policies, and never restore or delete backups (research W5-R13).
- Every decision goes to the hash-chained audit log (contract §3 "Audit").

## Where each piece runs

```
                          HUB node (the box, or the first box)
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ systemd (host, inside the read-only A/B image; updated only by RAUC)           │
 │   onemind-gateway  REST + dashboard + MCP + scheduler + notifier + reconciler  │
 │   onemind-nats     NATS hub: client :4222, leaf :7422, JetStream (core streams)│
 │   onemindd         heartbeat, local API :7480, updater, backup agent,          │
 │                    key custodian (box CA, NATS signing key)                    │
 │   k3s server       SQLite datastore (kine)                                     │
 ├───────────────────────────────────────────────────────────────────────────────┤
 │ k3s workloads: platform layer (storage class, ingress, policies) + app-<id>    │
 └───────────────────────────────────────────────────────────────────────────────┘
          ▲ k3s agent join (6443)            ▲ NATS leaf (7422, TLS + node creds)
          │                                  │
 WORKER node: k3s agent + onemindd + local NATS leaf     LEAF node: onemindd + local NATS leaf (no k3s)
```

**Why the core is not inside Kubernetes:** the gateway, NATS and `onemindd` must work when k3s is broken, because they are what repairs, restores and updates k3s. They ship inside the signed OS image, so an OS update replaces them atomically and the health gate can roll them back together (`os/gate/`). DEPLOYMENTS.md §2 gives the full reasoning.

**Why workers hold no Kubernetes credentials:** brief 30 D-B6.2 says agent nodes keep no datastore and no admin kubeconfig, and `feat/deploy-v0` tests exactly that. So **all Kubernetes work happens in the gateway**, and node agents only do host-level work (files, restic, host checks) through signed **jobs** on NATS (FABRIC.md §5.4).

## Shared conventions

- **Reserved NATS namespace:** the OS owns `onemind.>` (contract §1 already uses `onemind.node.<id>.status` and `onemind.audit`). Apps never publish there; brief 30 E7 grants apps only subjects in the locked grammar (`evt.`, `cmd.`, `tel.`, `svc.` …). This keeps OS subjects and app subjects from colliding and lets one permission rule protect the OS.
- **Event envelope:** `onemind.event.v1`, from `context/02-prior-planning.md` §8 (CONTRACT-12-DRAFT §12.3).
- **Freshness:** a value is shown as live only when it was observed recently; age is computed on the hub's clock (`dashboard/README.md`). Every new screen here follows that rule ("last verified N ago", never a cached green).
- **One-time outputs:** secrets the owner must see once (a recovery key, a node's join ticket) are returned only in the HTTP response that created them, never stored in clear, never logged, never put in the audit log.
- **IDs:** action ids as today (`core/onemind_core/ledger.py`); other new ids are prefixed ULIDs (`job_…`, `snap_…`, `alrt_…`, `auto_…`, `pol_…`), so a log line says what kind of thing it names.
- **Effort:** S = up to 3 days, M = 1 to 2 weeks, L = 3 weeks or more, for one founder plus coding agents (as in core-alignment §1).
- **Code reuse:** patterns from any project; code only from MIT, BSD or Apache-2.0 sources at a named commit, with a `NOTICE` entry. These docs copy **no code**. The competitor sources they cite were read in shallow clones outside the repository; the licence of each is given where it is cited.

## In-flight work these docs build on (not merged on 2026-11-12)

| Branch | What it adds that these docs use |
|---|---|
| `feat/deploy-v0` | `deploy/install.sh --role hub|node`, separate k3s agent token, gateway ServiceAccount, NATS unit (no auth yet) |
| `feat/onemindd-updater` | `internal/update/`: TUF client, channels, window, postpone, pre-update restic snapshot, heartbeat `update` object |
| `feat/os-security-pipeline` | `os/update/`: signed channels, scan gate, Debian VEX |
| `feat/gateway-agent-mcp` | scan gate (§11.1), app agent principals (§11.2), `POST /mcp` (§11.3), catalog fields, app page |
| `feat/app-pipeline` | manifest schema additions, `sdk/tools/app-gate`, `app-scaffold` |
| `docs/security-threat-model` | `docs/security/THREAT-MODEL.md` and `HARDENING-BACKLOG.md` (H-01…H-30) |

Research mission 02 ("the One Mind fabric", `RESEARCH-MISSION-02-ONE-MIND-FABRIC.md`) has not produced output yet. FABRIC.md is the core-OS slice the founder needs now (his own machines, one site). When mission 02 lands, reconcile the two; mission 02 wins on anything wider (many sites, fleets, robots).
