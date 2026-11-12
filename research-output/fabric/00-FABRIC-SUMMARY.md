<!-- SPDX-License-Identifier: Apache-2.0 -->
# 00 · The One Mind fabric: summary for Zeus

**Date:** 2026-11-12 · **Mission:** `RESEARCH-MISSION-02-ONE-MIND-FABRIC.md` (FB-1…FB-12) · **Status:** every workstream delivered; 3 of 5 lab spikes ran (spike 1 earlier, spikes 2 and 3 in this run), 2 blocked with reasons and pre-registered criteria. Not done: §6.
**Read next:** `01-FABRIC-ARCHITECTURE.md`, then `02-JOIN-MATRIX.md` and `14-OPEN-QUESTIONS-FOR-ZEUS.md`.

> **Explain it like I'm the founder.** "Plug in any machine and it appears in OneMind on my phone" works like this. Every machine that *can* run OneMind gets a small agent and joins your site after you approve it on your phone (a 6-digit code, or for boxes OneMind sells, a voucher that lets them find you by themselves). Machines that can't (sensors, PLCs, flight controllers) never run OneMind; a nearby OneMind machine translates for them. Inside a site everything speaks one language (NATS) over your own private network, and every machine keeps a diary so nothing is lost when the link drops. Many sites hang under your own fleet hub, which sends updates in rings but can never make a site act on its own. Your AI goes through the same door as you, and anything that moves needs your tap.

## 1. The answer per question, mapped to the board

**Board epics:** CORE-NET (mesh + bus transport, `docs/leap/STATUS.md` rows CORE-NET-1…15), CORE-FABRIC (join, identity, leaf, placement, fleet view, CORE-FABRIC-1…6), and **multi-cluster** (not on the board yet; nearest items CORE-UPDATE-9 and the year-1 M6 milestone; proposed as MULTI-CLUSTER-1…8 in `13-…` §4).

| # | Question | Answer (one line) | Evidence | CORE-NET | CORE-FABRIC | Multi-cluster |
|---|---|---|---|---|---|---|
| FB-1 | How does each class join? | 7 classes, 3 outcomes: image or installer-mode **agent**, **adapter** for devices, **client** for screens; managed Kubernetes joins as a *site* | `02-…`; competitors' agents | NET-11 (installer wiring) | FABRIC-1, -5 | MC-1 (site enrolment) |
| FB-2 | Identity and enrollment | Owner-approved ticket + pairing code stays universal; **FDO** works as a zero-touch front end (**lab PASS**: nothing until approval, 18 s after it, other owner refused); TPM sealing later | lab fb2; [C-FB11-004] | NET-12 (join bundle `mesh`) | FABRIC-1, -2; proposed CORE-FDO-1 | MC-1 |
| FB-3 | Which is the one bus? | **NATS**; mesh is the underlay; MQTT/Sparkplug direct, OPC UA/Modbus/CAN/MAVLink/Zenoh via adapters; per-node permissions on leaf logins **work** (repo test) but sourcing under them is still UNVERIFIED | lab fb3 PASS; [C-FB3-001…007] | NET-1…4, -9 | FABRIC-2 | MC-2 (site leaf to fleet hub) |
| FB-4 | One cluster or many? | **Many clusters with a hub**; one cluster per site; no stretched clusters except always-online cloud workers; sites pull | lab fb4 (verdict FAIL at T3, a ring-setting lesson); [C-FB4-001, -016] | NET-11 (k3s on mesh; ZF-02) | — | MC-1…5 |
| FB-5 | One namespace | `site/node/device/capability` addresses; subjects inside the existing grammar; WoT TD export; map OPC UA/AAS/Sparkplug, avoid Ditto | `06-…`; [C-FB5-001] | — | FABRIC-4 (capability labels) | MC-2 (fleet prefix, ZF-05) |
| FB-6 | AI over the fabric | one AI door per site; audience-bound tokens, no passthrough; `actuate` = target owner's step-up approval; commands only from the gateway, signed | `07-…`; [C-FB6-001, -002] | NET-8 (gateway routes) | FABRIC-2 (node permissions) | MC-5 (gateway-to-gateway grants) |
| FB-7 | Offline and conflict | site has no offline time limit; outbox on every node (1,200/1,200 after 30 min); single writer per data type; late commands dropped, never replayed | `08-…`; lab fb3 T3 | NET-4 (leaf) | FABRIC-5 | MC-3 (offline sites converge) |
| FB-8 | Updates across classes | one signed release contract, five engines (RAUC, NVIDIA A/B, packages, MCUboot/ESP-IDF, none for PLCs); rings gated on the previous ring's measured health | `09-…`; [C-FB8-001…003, C-FB11-005] | — | — | MC-3, CORE-UPDATE-9 |
| FB-9 | Vehicles and drones | OneMind on the companion only; missions behind approval, never setpoints from agents; standards identified, several not opened | `10-…`; [C-FB9-001…005] | — | FABRIC-5 (companion leaf) | — |
| FB-10 | Clients | one web app; no client on NATS; Sites view from summaries; approvals routed to the target site's owners | `11-…` | NET-13 (Network page) | FABRIC-6 (fleet view) | MC-4 (Sites view) |
| FB-11 | Competitors | Flight Control is the closest constraint match (approved enrollment, success-threshold batches); nobody gates AI actuation in the gateway | `12-…`, `competitors/` | — | — | — |
| FB-12 | Build path | F1 one site (on the board) → F2 field + bridges → F3 many sites → F4 robots → F5 scale/zero-touch, each with a gate | `13-…` | NET-9 lab, NET-14 | FABRIC-1…6 | MULTI-CLUSTER-1…8 (proposed) |

## 2. Top findings

1. **FDO can sit in front of the owner-approved join** without changing it: approval = voucher import; the same device finished 18 s after approval; a voucher deleted before first boot stops it; but the owner's setup step is root on the device, and go-fdo-server has no delete API (lab fb2).
2. **Fleet's strictest ring setting never starts an update**: a not-yet-updated cluster counts as unavailable in Fleet's partition rule (lab fb4 T3 FAIL, source code [C-FB4-016]). One notch looser, Fleet halted a bad release at ring 0 and rolled back in one step, but **an offline ring-1 site held back ring 2** until it returned (E6). OneMind's ring rule must judge the previous ring's *updated* nodes and never wait on offline sites.
3. **Per-node isolation on NATS leaf links works with top-level users** (OneMind's own test, v2.15.3) — narrowing fb3's "needs accounts or JWT" — but open NATS defects sit in that code path and JetStream sourcing under those permissions is unproven [C-FB3-001, C-FBREF-001…002].
4. **One mesh per site, not one mesh for the world**: Headscale's own scope is one small tailnet, and a 2026 report shows it failing at thousands of clients [C-FB3-006, C-FBREF-006].
5. **No cluster stretched across sites**, except always-online cloud workers [C-FB4-001].
6. **Registration is where pull-based fleets get attacked** (three Fleet advisories in two months) [C-FBREF-011]; ring membership must not come from labels a site reports.
7. **No competitor gates AI actuation in the gateway**: Viam's MCP destructive tools act at once, Foxglove's MCP adds no approval (mission 01 claims).

## 3. Decisions for Zeus (details and options in `14-…`)

ZF-01 fleet engine (own rings, Fleet optional) · ZF-02 cross-site workers (cloud only) · ZF-03 mesh per site · ZF-04 FDO for the hardware line + scan-to-confirm + batch tickets · ZF-05 cross-site naming prefix · ZF-07 approvals in shared sites · ZF-11 NATS isolation model · ZF-13 requirement-ID clash · ZF-14 blind refuter re-run · ZF-15 legal texts for vehicles.

## 4. Lab status

| Spike | Verdict |
|---|---|
| 1 fb3-mesh-nat (hub + leaves across NATs) | **PASS** (earlier run) |
| 2 fb4-fleet-rings (multi-cluster rings) | **FAIL** at T3 (setting stalls updates; source-confirmed) + exploratory variants |
| 3 fb2-fdo-enroll (zero-touch, approval, revoke) | **PASS** (T5 uninformative; E6 is the real revocation test) |
| 4 fb-bridges (MQTT/Modbus as capabilities) | **BLOCKED**: adapter SDK and `actuate` type not built |
| 5 fb-installer-mode (stock Ubuntu + Debian + image) | **BLOCKED**: needs three VMs at once and CORE-FABRIC-1 |

## 5. Refuters

DC-F1 (NATS is the one bus): technical weakened, security weakened, longevity upheld, robotics upheld. DC-F2 (many clusters with a hub): technical weakened, security weakened, cost/longevity upheld. DC-F3 (ticket + approval universal, FDO optional): security weakened, longevity weakened, usability upheld. Each weakened verdict has a written response that changed the design (soak test, MQTT account split, ring rule, enrolment-based rings, scan-to-confirm, FDO behind an interface). **Not blind** (one agent wrote all of them; disclosed).

## 6. What remains (brief §9)

- Spikes 4 and 5 are blocked (above), pre-registered to run in phases F2 and F1.
- Refuters were not blind (ZF-14); "at least three refuters per P0 conclusion" is met in count only.
- A completeness-critic pass by a separate agent was not possible in this run; self-check: every FB has a file, every file maps to requirement IDs, every class in brief §2 has a join-matrix row.
- Several legal and standards texts could not be opened (EUR-Lex, eCFR, UNECE, ISO blocked to automated reading); listed as UNVERIFIED (ZF-15).
- NVIDIA's current Jetson fleet tooling was not identified (UNVERIFIED).
