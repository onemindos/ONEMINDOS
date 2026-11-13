<!-- SPDX-License-Identifier: Apache-2.0 -->
# 13 · Build path (FB-12): from "one cloud hub + one Pi 5" to "multi-site fleet with robots and vehicles"

**Date:** 2026-11-12 · **Workstream:** FB-12 (Tier A) · **Status:** phased plan with gates; maps to `20-PLAN-180-DAYS.md` (P1–P6, G0–G7), `21-ROADMAP-5-10-YEARS.md` (M6 multi-site) and the leap board (`docs/leap/`, sprints S1–S4). Amendments to `30-…` are **proposals only**.
**Serves requirements:** F-9, M-6, N-1, N-5, N-6, P-4, UX-6, R-1

> **Explain it like I'm the founder.** Five steps, each with a test that must pass before the next starts. **F1:** your box and one Pi join each other properly (approved join, private network, the bus with an outbox), plus one cloud server in "installer mode". **F2:** a field node and the first device translators (MQTT, Modbus), with "actuate" gated. **F3:** two sites under a fleet hub, releases in rings, and the multi-site Nodes view. **F4:** a robot or drone companion on Jetson. **F5:** scale tests by simulation and zero-touch for OneMind-built boxes. Most of F1 is already on the board (CORE-NET, CORE-FABRIC); F3 needs a new "multi-cluster" epic.

## 1. Phases and gates

| Phase | Builds | Board epics (existing → proposed) | 180-day plan | Gate (must pass to leave the phase) | Founder kit |
|---|---|---|---|---|---|
| **F1 · one site, three join modes** | owner-approved join (ticket, pairing code, custodian), per-node identity and NATS permissions, leaf mode, mesh (Headscale + DERP), NATS leaf over the mesh, installer mode on a stock cloud VM | CORE-NET-1…13, CORE-FABRIC-1…5, DEV-CLI-8 (all on the board) | P2–P3 (weeks 5–13) | **FG1:** FABRIC FT-1…FT-11 and NETWORKING NT-1…NT-8 pass; `fb-installer-mode` T0–T5 pass (spike pre-registered); **7-day leaf soak with the production NATS permission set** and request/reply over a leaf (new, from DC-F1 refuters); NT-6 records the `$JS` sourcing subjects | Beelink or Dell as hub, Pi 5 (8 GB) as worker/leaf, one DigitalOcean droplet (stock Debian) |
| **F2 · field node and first bridges** | leaf profile for a field kit; adapter SDK (plugin socket) with MQTT/Sparkplug and Modbus TCP adapters; capability registry + naming (`06-…`); `actuate` action type in the lab only | CORE-FABRIC-5 (leaf), **proposed CORE-ADAPT-1…4**, contract C12 naming PR | P4 (weeks 14–17), with G5 | **FG2:** `fb-bridges` T0–T4 pass; 24-hour WAN-cut lab (proposed F-20); LT-VM-18 (AI actuation) passes before any `actuate` leaves the lab | Pi 5 + Modbus simulator + an ESP32 with MQTT |
| **F3 · many sites, one fleet hub** | fleet hub (owner's cloud VM), site summaries, Sites view, rings for app revisions and OS updates, gateway-to-gateway grants | CORE-UPDATE-9 (fleet-staged updates), CORE-FABRIC-6 (fleet view), **proposed MULTI-CLUSTER-1…5** | after P6 / year 1 (21 M6) | **FG3:** the pre-registered `fb4-fleet-rings` sequence (T1–T6) passes **against OneMind's own engine** (two sites + one box, a bad release halts in ring 0, rollback, an offline site converges); a site keeps full local operation through a 24-hour fleet-hub outage | the F1 kit + a second home box (or a second VM site) |
| **F4 · robots and vehicles** | Jetson companion as a leaf (L4T + agent), MAVLink adapter (read first), mission upload behind `actuate` approval, Zenoh/ROS 2 bridge at the companion | B12 robot onboarding, **proposed CORE-ROBOT-1…3** | year 1 (G6 Jetson base lab first) | **FG4:** PX4 SITL: telemetry flows, an agent's mission request waits for approval, link loss → PX4 failsafe, no OneMind command after expiry; B12 "done when" | Jetson Orin Nano + Pixhawk-class controller, props off; SO-101 arm (LT-PI5-13j) |
| **F5 · scale and zero-touch** | 1,000-leaf simulated tree (NATS), region rings, optional hawkBit for OS releases, FDO for OneMind-built boxes, NATS JWT/accounts if config users stop scaling | proposed MULTI-CLUSTER-6…8, **proposed CORE-FDO-1** | year 1–2 (21 M6, W8-R11 "prove 10k by simulation") | **FG5:** 1,000 simulated leaves under 10 site hubs and one fleet hub: summaries current within 60 s, a release through three rings, a site partition recovers; `fb2-fdo-enroll` re-run against OneMind's voucher store | CI runners only |

## 2. Mapping to the 180-day plan (`20-…`)

| `20` phase / gate | Fabric content added | Change to `20` (proposal) |
|---|---|---|
| P2 (weeks 5–8) | F1 join + identity (CORE-FABRIC-1/2) on the image | none: already in P2 "Identity, agent identity, capability gateway" |
| P3 (weeks 9–13), G4 | F1 mesh + leaf, installer mode; LT-VM-18 stays the actuation gate | add `fb-installer-mode` and the 7-day leaf soak to G4 evidence |
| P4 (weeks 14–17), G5 | F2 field node and bridges | add `fb-bridges` to G5 (beside LT-VM-15/16/17) |
| P5 (weeks 18–21) | QR join on metal (already listed) | none |
| P6 (weeks 22–26), G7 | nothing new: multi-site stays outside the 180 days, as `20` §1 already says ("Blueprint M6 … is not in the 180 days") | none |
| Year 1 (`21` M6) | F3 and F4 | `21` gains the FG3/FG4 gates as the definition of M6 "multi-site" done |

## 3. Proposed amendments to `30-…` (proposals only; nothing edited)

| # | Proposal | Why (evidence) |
|---|---|---|
| A-30-1 | Add to B6 (k3s): "**One cluster per site.** A k3s agent at another site is allowed only for always-online cloud workers; field kits and vehicles are leaves or their own site." | k3s says "all servers should be in the same location" and warns about latency [C-FB4-001]; `05-…` |
| A-30-2 | Add to B9 (gateway): rules A1–A10 of `07-…` (one AI door per site, audience-bound tokens, no passthrough, approvals routed to the target's owner) | MCP 2026-07-28 authorization [C-FB6-001]; OWASP LLM01 [C-FB6-002] |
| A-30-3 | Add to B8 (sockets): an **adapter** socket profile: adapters advertise capabilities with an effect (read/write/actuate), subscribe to gateway-signed `cmd.` only | `06-…`; B12 step 8 |
| A-30-4 | Add to B12: MAVLink adapter rules (`10-…` §2): missions only, never setpoints from agents | PX4 offboard warnings [C-FB9-001] |
| A-30-5 | Add an optional **FDO front end** for OneMind-built hardware (go-fdo, Apache-2.0) behind an interface; voucher store owned by OneMind (no upstream delete API) | lab fb2-fdo-enroll; [C-LAB-fb2-fdo-enroll-010] |
| A-30-6 | Add a fleet-hub component (year 1) that holds desired state and rings only, never acting credentials; releases verified per site against OneMind's TUF keys | DC-F2 security refuter; [C-FBREF-011] |

## 4. Proposed board epics (for the leap; nothing on the board is edited here)

| Epic | Scope | Depends on |
|---|---|---|
| MULTI-CLUSTER-1 | Site identity (`site_id`), site enrolment to a fleet hub (agent-initiated, one-time token, approval) | CORE-FABRIC-2 |
| MULTI-CLUSTER-2 | Site summaries over the site's NATS leaf to the fleet hub (`onemind.site.<site_id>.` prefix, contract PR) | MULTI-CLUSTER-1, C12 naming |
| MULTI-CLUSTER-3 | Rings: release objects, ring membership from enrolment records, gate on the previous ring's measured health | CORE-UPDATE-9 |
| MULTI-CLUSTER-4 | Sites view on dashboard and phone (summaries only; drill-down asks the site) | MULTI-CLUSTER-2, CORE-FABRIC-6 |
| MULTI-CLUSTER-5 | Gateway-to-gateway grants (fleet principal on a site, owner-approved) | DEV-MCP, CORE-SEC |
| MULTI-CLUSTER-6…8 | 1,000-leaf simulation harness; region rings; optional Fleet/hawkBit integration for enterprise | MULTI-CLUSTER-3 |
| CORE-ADAPT-1…4 | Adapter SDK, MQTT/Sparkplug, Modbus, capability registry export (WoT TD) | B8 sockets |
| CORE-ROBOT-1…3 | Jetson companion leaf, MAVLink adapter, ROS 2/Zenoh bridge | B12, CORE-ADAPT-1 |
| CORE-FDO-1 | FDO front end and voucher store for OneMind-built boxes | CORE-FABRIC-1 |

## 5. Founder kits (hardware needed beyond the board's current kits)

| Kit | Contents | First used in |
|---|---|---|
| FK-1 | One DigitalOcean droplet (stock Debian 13), deleted after the test | FG1 (`fb-installer-mode`) |
| FK-2 | Pi 5 + Modbus TCP simulator on a laptop + one ESP32 dev board | FG2 |
| FK-3 | Second site: any spare x86 box or a second home Pi 5 cluster | FG3 |
| FK-4 | Jetson Orin Nano Super + a Pixhawk-class controller (bench, props off) | FG4 |

## Glossary

| Term | Meaning |
|---|---|
| Gate | A test list that must pass before the next phase starts |
| Fleet hub | The owner's central OneMind (usually a cloud VM) that holds releases and rings for many sites |
| Founder kit | Hardware the founder buys and runs a written test on |
