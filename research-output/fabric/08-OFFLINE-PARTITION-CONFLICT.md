<!-- SPDX-License-Identifier: Apache-2.0 -->
# 08 · Offline, partition and conflict (FB-7): what every machine does when the hub or the internet is gone

**Date:** 2026-11-12 · **Workstream:** FB-7 (Tier A) · **Labs:** fb3-mesh-nat T3 (30-minute total hub outage, 1,200/1,200 in order) PASS; fb4-fleet-rings T6 (site offline during a release), see `05-…`.
**Serves requirements:** N-6, N-5, M-1, F-6, F-13, UX-4, R-2, AI-5 · builds on context/02 §10 (offline-first rules)

> **Explain it like I'm the founder.** OneMind is built so that losing the internet is boring. Every site keeps running on its own; every machine keeps its own diary of what happened and hands it over when the link is back, in order, nothing lost and nothing doubled (the lab cut the hub off for 30 minutes and got all 1,200 events back in 44 seconds). Screens never pretend: anything not fresh is shown with its age. And two rules keep things safe when a field kit comes back: **every piece of data has exactly one owner who may change it**, and **a command that was not executed in time is thrown away, never replayed later**, because "open the valve" an hour late is a different command.

## 1. Per-class behaviour when the link is gone

| Class (`02-…`) | Hub or internet gone: what keeps working | What is buffered | What stops | On reconnect |
|---|---|---|---|---|
| Site hub (home box, cloud hub) | everything local: apps, dashboard on the LAN, automations, approvals for people on the LAN or mesh | its own events (it *is* the store) | links to the fleet hub; remote phones without the mesh relay | the site's leaf link to the fleet hub re-sources (lag → 0) |
| Worker (k3s agent) at the hub's site | running pods | node events in its outbox (7 days / 256 MiB) | rescheduling, new installs | outbox drains; Kubernetes reconciles |
| Leaf (Pi, laptop, field kit) | its local services, its local NATS, local automations | outbox (JetStream domain `node-<id>`) | jobs from the hub (held on the hub, dropped if late) | **1,200/1,200 after 30 min, in order, 44 s** [C-LAB-fb3-mesh-nat-006]; 600/600 in mission 01 (C-W8-050) |
| Robot / drone companion | local autonomy within limits the owner set; telemetry logging | outbox + local recordings | any new mission or `actuate` approval | outbox drains; no stale command runs |
| Vehicle / flight controller | **its own failsafes** (OneMind is not in that loop): PX4 leaves Offboard and lands or runs `COM_OBL_RC_ACT` when the 2 Hz proof-of-life stops [C-FB9-001] | — | — | — |
| Sensors / MCUs | their own firmware loops (ESPHome rule: keep the control loop on the node, W8-R9) | adapter buffers into the node's outbox | — | — |
| Managed-K8s site | its workloads | site outbox | fleet-hub-driven changes | re-sources |
| Phone / laptop | cached state labelled with its age (MOB-B2); approvals queue nothing: an approval needs the gateway | captures (photos, notes) per context/02 §10 | approvals while unreachable | push catch-up; cached views refresh |

## 2. Conflict rules when a field kit or site rejoins

These extend context/02 §10 ("one writer authority per resource or site"; "device control: never blind replay"; "permissions/config: online only") to the fabric:

| Data | Owner (single writer) | Rule on rejoin |
|---|---|---|
| Node events, telemetry | the producing node | append-only; dedup by stream sequence (lab: no duplicates [C-LAB-fb3-mesh-nat-006]) |
| Node state (heartbeat) | the node | last value wins; never shown as live when stale (contract §3) |
| Site desired state (apps, revisions, settings) | **the site hub** | the fleet hub's changes are *proposals*; a site applies a newer fleet release only through its own action (rings, `05-…`); if both changed the same app, the site shows both and asks its owner |
| Fleet releases and rings | the fleet hub | sites pull; a site that was offline during a release converges when back (Fleet T6 tests this pattern) |
| Jobs and commands | the issuing gateway | each carries `expires_at`; a late job is **dropped and reported, never run** (FABRIC §5.3–§5.4, W8-R2 rule 3) |
| Approvals | the person who approved | bound to exact parameters and expiry (D-B9.6); an approval that expired offline is void |
| Identity, permissions, grants | the site hub | changes need the hub (online only); revocations made while a node is offline take effect when its certificate fails to renew (≤ 30 days) or at once on reconnect via the deny-list |

## 3. Bounded autonomy for robots and vehicles while disconnected

| Allowed while offline | Not allowed while offline |
|---|---|
| finishing a mission the owner approved before the link dropped, inside its geofence and expiry | starting any new `actuate` action |
| the flight or safety controller's own failsafes (return, land, stop) | OneMind overriding those failsafes |
| logging, perception, local alerts (sound, light) | an AI-initiated action of any kind |

The owner sets the limits per robot (mission expiry, geofence, max duration); the default is **zero autonomy beyond the current approved mission** (`10-…`).

## 4. Detecting "offline" honestly

- Screens use heartbeats on the hub's clock: `stale` after 30 s, `offline` after 120 s (contract §3); alerts only on `offline` (FABRIC §6.3).
- NATS's own link detection is slow by default: 194 s (leaf) and 405 s (hub) to notice a silently dead link [C-LAB-fb3-mesh-nat-007]; tune `ping_interval`/`ping_max` (values UNVERIFIED; NT lab) so `leaf_link: down` matches the UI.
- After a reconnect the node shows "syncing (N pending)" until its outbox lag is 0 (FABRIC §10).

## 5. What competitors do (constraint-matched)

| System | Offline limit | Constraint fit | Take |
|---|---|---|---|
| Azure IoT Operations | "operate offline for a maximum of 72 hours. Degradation might occur" [C-FB11-009] | Low (cloud authority) | OneMind has **no** offline limit: the site is the authority |
| Viam | config cached locally, runs up to 60 days offline (C-TD-tier-c-robotics-048) | Medium | A time limit for cached *config* only is reasonable; not for the site |
| KubeEdge / OpenYurt | "edge autonomy" with a central control plane [C-FB4-013, C-FB4-014] | Low (cloud control plane) | The site-hub model avoids the problem |
| Fleet | agents "not assumed to have an always on connection" [C-FB4-003] | High | Pull + converge on return |
| Formant | buffer on device, upload on demand (C-TD-tier-c-robotics-006) | Medium | Same outbox idea |

## 6. Open items

- Proposed **F-20**: "a site keeps full local operation with no time limit when every external link is down; this is tested by a 24-hour WAN-cut lab before any release" (build path P2 gate).
- UNVERIFIED and to test: days-long outages, a full disk on a leaf (outbox limit behaviour), flapping links (fb3 fidelity limits).

## Glossary

| Term | Meaning |
|---|---|
| Outbox | A small message store on each machine that keeps events until the hub has them |
| Partition | Part of the system can't reach the rest |
| Single writer | Only one place may change a given piece of data; everyone else proposes |
| Failsafe | What a vehicle's own controller does when it loses its commander (land, return, stop) |
