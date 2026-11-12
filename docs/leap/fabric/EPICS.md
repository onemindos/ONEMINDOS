<!-- SPDX-License-Identifier: Apache-2.0 -->
# Fabric follow-through: epics (FAB, MULTI-CLUSTER, ADAPT, ROBOT, FDO)

**Date:** 2026-11-12 · **Status:** proposal (Wave G #8, [NEXT-WAVE.md](../NEXT-WAVE.md) §2) · **Source:** mission 02, [`research-output/fabric/`](../../../research-output/fabric/00-FABRIC-SUMMARY.md) (answers FB-1…FB-12, build path in [13](../../../research-output/fabric/13-BUILD-PATH.md), questions in [14](../../../research-output/fabric/14-OPEN-QUESTIONS-FOR-ZEUS.md)) · **Builds on:** [core/FABRIC.md](../core/FABRIC.md) (CORE-FABRIC-1…6), [core/NETWORKING.md](../core/NETWORKING.md) (CORE-NET-1…15) · **First stream, ready to build:** [STREAM-1.md](STREAM-1.md) · **Plan:** [`research-output/20-PLAN-180-DAYS.md`](../../../research-output/20-PLAN-180-DAYS.md), [`21-ROADMAP-5-10-YEARS.md`](../../../research-output/21-ROADMAP-5-10-YEARS.md)

> **Explain it like I am the founder**
> The research answered "how does every machine become one OneMind?" in five steps, F1 to F5. **F1 (one site: your box, a Pi, a cloud VM) is already on the board** as CORE-FABRIC and CORE-NET, and most of its code exists on `main` and in `feat/net-part2`. What the research adds is: (1) **proof**: a list of tests a machine class must pass before we call it "supported"; (2) a few **new rules** (one mesh per site, one cluster per site, rollout rings that never wait for an offline site); (3) the **later steps** (field devices, many sites, robots, zero-touch boxes), written as epics with gates so nothing starts before the step under it is proven.
> Nothing here changes a founder decision. Where the research disagrees with something, §6 says so and leaves the choice to you. Questions only you can answer are in §7.

## 1. Terms
| Term | Plain meaning |
|---|---|
| Site | One place with one OneMind box (home, greenhouse, factory). One k3s cluster, one mesh, one gateway per site. |
| Node | A machine that runs the OneMind agent (`onemindd`). Roles: hub, worker (runs apps), leaf (no k3s; keeps working alone). |
| Device | Something that does not run OneMind (sensor, PLC, flight controller). An adapter on a nearby node speaks for it. |
| Fleet hub | The owner's own central OneMind (usually a cloud VM) that knows many sites. It holds summaries and rollout rules, never credentials that can act. |
| Ring | A group of sites that get a release together. Ring 0 is a canary; the next ring starts only if the previous one stayed healthy. |
| Gate (FG1…FG5) | A list of tests that must pass before the next phase starts. |

## 2. Requirement IDs used
The research proposes seven new requirements. Their `REQ F-16…F-22` names **collide** with founder-decision IDs F-16…F-22 in [DECISIONS-NEEDED.md](../DECISIONS-NEEDED.md) (research ZF-13), so this plan calls them **FB-R1…FB-R7** until Zeus picks a prefix. `docs/REQUIREMENTS.md` is not edited here (repo rule).

| Here | Research name | Requirement (short) |
|---|---|---|
| FB-R1 | REQ F-16 | A machine class is "supported" only with a passing join test |
| FB-R2 | REQ F-17 | No credentials without an owner approval the machine can be matched to |
| FB-R3 | REQ F-18 | One stable address per device and capability, used by bus, API, MCP, audit and UI |
| FB-R4 | REQ F-19 | No actuation path bypasses the site gateway's approval; a negative test per adapter |
| FB-R5 | REQ F-20 | A site keeps full local operation, with no time limit, when every external link is down (24-hour WAN-cut lab) |
| FB-R6 | REQ F-21 | Every class has an update engine and rollback path, or an explicit "never updated by OneMind" label |
| FB-R7 | REQ F-22 | Multi-site views work from site summaries; an unreachable site shows its last summary and its age |

Existing requirements served: N-1 (everything is a node), N-5, N-6 (native mesh), M-1 (local-first), M-2 (privacy, own keys), M-6 (one developer needs guard rails), M-7 and F-1 (robots, drones), F-11 (IIoT), F-14 (one OS at every scale), UX-6 (many machines, one interface), AI-5 (human approval), R-1 (user-controlled safe updates), P-4 (Federation surface).

## 3. Epics

Effort: S ≤ 3 days, M ≈ 1 to 2 weeks, L ≈ 3 to 6 weeks (one builder). "Plan" = milestone in the 180-day plan (P1…P6, G0…G7) or the roadmap (M6 = multi-site, year 1). State of the existing CORE-* rows is in [STATUS.md](../STATUS.md); the NET and FABRIC rows there still say `todo` while `main` and `feat/net-part2` hold most of the code (see STREAM-1 §2).

### Phase F1: one site, three join modes (plan P2 to P3, gate G4; FG1)

| Epic | Title and scope | Reqs, decisions | Plan | Depends on | Size | Acceptance tests |
|---|---|---|---|---|---|---|
| CORE-FABRIC-1…5 | Join, node identity, remove/drain, placement, leaf (existing; specs in [core/FABRIC.md](../core/FABRIC.md)) | FB-R1, FB-R2, N-1, M-2; D-007 | P2 to P3 | CORE-SEC-1/2/4 | existing | FABRIC FT-1…FT-11 ([architecture/FABRIC.md](../../architecture/FABRIC.md) test plan) |
| CORE-NET-1…14 | Mesh (Headscale + DERP), NATS leaf over the mesh, k3s on the mesh (existing; [core/NETWORKING.md](../core/NETWORKING.md)) | N-6, U-5, M-1; Z-34, F-32 (open) | P3 | CORE-SEC-1 | existing | NETWORKING NT-1…NT-17 |
| **FAB-1** | **Fabric contract PR** (the board's C12-B): `site_id`, heartbeat `fabric` object (`role`, `site_id`), reserved subject prefix `onemind.site.<site_id>.`, address grammar `site/node/device/capability`, `node.join`/`node.remove` action types. Additive only. | FB-R3; ZF-05 (needs Zeus) | P2 | CORE-NET-10 | S | OpenAPI and contract tests green; old heartbeats still parse; golden file for the new fields; no existing subject changes |
| **FAB-2** | **F1 conformance suite**: one runnable list proving each machine class joins (FT-1…FT-11, NT-1…NT-8, join-matrix rows 1, 2a, 2b, 3 as VM tests), plus **negative** tests: no approval means no credentials; an agent cannot join a node; node A cannot speak as node B. | FB-R1, FB-R2; H-06 | P3 | CORE-FABRIC-1/2, CORE-NET-9 | M | Runs in CI (VM tier) and in Lima; every class row has a pass/fail line in `docs/testing/TEST-REGISTER.md`; FG1 list below |
| **FAB-3** | **Leaf soak**: 7 days with the production NATS permission set, request/reply over a leaf, and a recorded list of the `$JS` subjects JetStream sourcing needs (NT-6 extension). Answers whether config-mode users (ZF-11 option a) are enough. | FB-R5; ZF-11; H-06 | P3 (G4 evidence) | CORE-NET-4, FAB-2 | M | 7 days, zero permission violations from legitimate traffic, zero lost events; sourcing works under the permissions or the gap is written as an ADR |
| **FAB-4** | **Installer mode on stock Debian 13 and Ubuntu 26.04 VMs** (spike `fb-installer-mode`): signed packages for `onemindd`, NATS, k3s agent; "no OS rollback" label; package downgrade only. | FB-R1, FB-R6; D-007 (machines OneMind does not own get OneMind on top of their OS) | P3 (G4) | CORE-NET-11, CORE-FABRIC-1 | M | Spike T0 to T5 pass on three VMs; Nodes screen shows the grey label; join under 2 minutes |
| CORE-FABRIC-6 | Read-only fleet view (existing) | UX-6, FB-R7 | P5 | CORE-FABRIC-1, UPDATE-3, BACKUP-7 | S | FT-privacy: no IP, MAC or serial on screen |
| **FAB-5** | **AI-door rules into the gateway** (research 07 rules A1 to A10): audience-bound tokens, no token passthrough, approval card routed to the owner of the target site, agent free text shown as untrusted, device data labelled as data in prompts. Mostly tests plus small gateway changes. | AI-5, FB-R4; AI never actuates without approval | P3 | DEV-MCP-12 (OAuth façade), CORE-SEC-2 | M | A token minted for site A is refused by site B and by an adapter; an agent cannot self-approve; card shows `plan_sha256`; injection fixtures never become tool arguments |

**FG1 (leave F1):** FABRIC FT-1…FT-11 and NETWORKING NT-1…NT-8 pass; `fb-installer-mode` T0 to T5 pass; FAB-3 soak done. Founder kit FK-1 (one stock Debian droplet), Beelink or Dell as hub, Pi 5 as worker/leaf.

### Phase F2: field node and first device bridges (plan P4, gate G5; FG2)

| Epic | Title and scope | Reqs, decisions | Plan | Depends on | Size | Acceptance tests |
|---|---|---|---|---|---|---|
| FAB-6 | **WAN-cut lab, 24 hours**: a field leaf and the hub, uplink cut; capture, local apps and local approvals keep working; outbox drains; late commands are dropped, not replayed. | FB-R5; F-11 | P4 | CORE-FABRIC-5, FAB-3 | M | 24 h pass; 1,200/1,200 events after reconnect; a command older than its `expires_at` is dropped and reported |
| CORE-ADAPT-1 | Adapter socket profile: adapters advertise capabilities with an effect (`read`/`write`/`actuate`) and execute only gateway-signed, unexpired commands | FB-R3, FB-R4; sockets E1 to E10 | P4 | plugin sockets (PLUGIN-SDK) | L | A command not signed by the gateway is refused; a signed unexpired one runs |
| CORE-ADAPT-2 | MQTT/Sparkplug adapter (NATS terminates MQTT 3.1.1; Sparkplug births map to "device attached") | N-1, F-11 | P4 | CORE-ADAPT-1 | M | `fb-bridges` T0 to T2 |
| CORE-ADAPT-3 | Modbus TCP adapter (read first; writes are `actuate`) | F-11 | P4 | CORE-ADAPT-1 | M | Simulator test; a write waits for approval |
| CORE-ADAPT-4 | Capability registry and WoT Thing Description export | FB-R3 | P4 | CORE-ADAPT-1, FAB-1 | M | Each device has one address across bus, API, MCP, audit, UI |

**FG2:** `fb-bridges` T0 to T4; FAB-6; LT-VM-18 (AI actuation test) passes before any `actuate` leaves the lab (PLAN-E7-LAB stays parked until then). Kit FK-2.

### Phase F3: many sites, one fleet hub (roadmap M6, year 1; FG3)

| Epic | Title and scope | Reqs, decisions | Plan | Depends on | Size | Acceptance tests |
|---|---|---|---|---|---|---|
| MULTI-CLUSTER-1 | Site identity and enrolment to a fleet hub (site-initiated, one-time token, owner approval; managed Kubernetes can join as a site) | FB-R2, M-1; ZF-03, ZF-06, ZF-08 | M6 | CORE-FABRIC-2, FAB-1 | L | Forged or reused token refused; ring membership comes from the enrolment record, never from labels a site reports |
| MULTI-CLUSTER-2 | Site summaries over each site's NATS leaf into the fleet hub (`onemind.site.<site_id>.`) | FB-R7; ZF-05 | M6 | MC-1, FAB-1 | M | Summaries current in 60 s; fleet hub cannot publish into a site |
| MULTI-CLUSTER-3 | Rings: release objects, gate on the previous ring's **updated** nodes, never wait for offline sites; folds into CORE-UPDATE-9 | R-1, FB-R6; ZF-01, ZF-12 | M6 | CORE-UPDATE-9 | L | Pre-registered `fb4-fleet-rings` T1 to T6 pass on OneMind's own engine; a bad release halts in ring 0 and rolls back; an offline ring-1 site does not hold up ring 2 |
| MULTI-CLUSTER-4 | Sites view on dashboard and phone (summaries only; drill-down asks the site) | UX-6, FB-R7 | M6 | MC-2, CORE-FABRIC-6 | M | Unreachable site shows last summary and its age |
| MULTI-CLUSTER-5 | Gateway-to-gateway grants (fleet principal on a site, owner-approved) | AI-5, M-2; ZF-07 | M6 | DEV-MCP, CORE-SEC | M | A fleet agent's action on a site needs that site owner's approval; fleet hub holds no acting credentials |
| FAB-7 | Re-run the three research refuters with separate agents before MULTI-CLUSTER-1 starts (ZF-14) | process | before M6 | – | S | Written verdicts in `research-output/fabric/evidence/refuters/` |

**FG3:** `fb4-fleet-rings` T1 to T6 on OneMind's engine; a site keeps full local operation through a 24-hour fleet-hub outage. Kit FK-3.

### Phase F4 and F5 (year 1 to 2; FG4, FG5; parked until the F3 gate)

| Epic | Title and scope | Reqs, decisions | Plan | Depends on | Size | Acceptance tests |
|---|---|---|---|---|---|---|
| CORE-ROBOT-1 | Jetson companion as a leaf (L4T + agent, k3s agent only) | M-7, F-1; D-007 (Jetson stays on L4T) | year 1 (G6 Jetson lab first) | CORE-FABRIC-5, PLAN-E15 | L | Joins by QR; heartbeat shows `leaf` |
| CORE-ROBOT-2 | MAVLink adapter: telemetry read; **missions only**, behind approval, never setpoints from agents | FB-R4; ZF-09, ZF-10 | year 1 | CORE-ADAPT-1, CORE-ROBOT-1 | L | PX4 SITL: mission request waits for approval; link loss gives PX4 failsafe; no OneMind command after expiry |
| CORE-ROBOT-3 | ROS 2 / Zenoh bridge at the companion | M-7 | year 1 | CORE-ROBOT-1 | M | Topics visible as capabilities |
| CORE-FDO-1 | FIDO Device Onboard front end for OneMind-built boxes, behind an interface, OneMind-owned voucher store; ticket plus approval stays the universal path | FB-R2; ZF-04 | year 1 to 2 | CORE-FABRIC-1 | L | `fb2-fdo-enroll` re-run: nothing until approval, other owner refused, deleted voucher stops onboarding |
| MULTI-CLUSTER-6…8 | 1,000-leaf simulation harness; region rings; optional Fleet/hawkBit adapter for enterprise | M-4; ZF-01 | year 1 to 2 | MC-3 | L | FG5: 1,000 simulated leaves under 10 site hubs: summaries in 60 s; a release through three rings; a partition recovers |

Gates: FG4 (PX4 SITL plus B12 "done when"), FG5 (above). Kit FK-4 (Jetson and a Pixhawk-class controller, props off).

## 4. How this lines up with the 180-day plan
| Plan item | Fabric content | Change proposed to the plan (Zeus decides) |
|---|---|---|
| P2 (weeks 5 to 8) | CORE-FABRIC-1/2, FAB-1 | none |
| P3 (weeks 9 to 13), G4 | CORE-NET, FAB-2, FAB-3, FAB-4, FAB-5 | add the installer-mode spike and the 7-day leaf soak to G4 evidence |
| P4 (weeks 14 to 17), G5 | FAB-6, CORE-ADAPT-1…4 | add `fb-bridges` and the 24-hour WAN-cut lab to G5 |
| P5, P6 | QR join on metal (already listed); nothing new | none |
| Year 1 (roadmap M6) | F3, F4 | make FG3 and FG4 the definition of M6 "multi-site" done |

Rule kept from the 180-day plan: multi-site is **outside** the 180 days.

## 5. The "why" behind the new rules
- **One cluster and one mesh per site.** k3s says its servers should sit in one place, and Headscale describes itself as one small network. Stretching either across sites makes a slow link look like a broken machine. Sites link by NATS over TLS instead.
- **Sites pull; hubs never hold acting power.** Registration is where pull-based fleets get attacked, so ring membership comes from the owner's approval, not from what a site says about itself.
- **Rings judge the previous ring's updated nodes.** The lab showed Fleet's strictest setting never starts an update, and a looser one let one offline site stall everyone behind it. OneMind's rule: never wait on an offline site.
- **Every machine keeps a diary (outbox).** Losing the internet is boring: the site works, the diary syncs later, and late commands are dropped, never replayed.
- **Actuation is a human tap.** Agents may request; only the target site's owner (with a passkey step-up) approves; commands are published only by the gateway and signed with an expiry.

## 6. Flags: research versus locked decisions (not resolved here)
Nothing in the research contradicts D-001 to D-007 outright. These need Zeus's eye:
1. **Z-34 / F-32 (hosted Tailscale vs Headscale) is still open**, yet the research (04, 11) and CORE-NET already assume Headscale and the official Tailscale apps. Not locked, but the build treats it as decided. Confirm F-32.
2. **ZF-07 recommends a named operator role approving `actuate`**, while research 07 rule A4 says `actuate` is "owner + step-up". Both are human approval (AI-5 holds), but they differ on who. It also touches contract rule P1 ("only an owner approves"; compare F-35).
3. **Optional hawkBit (EPL-2.0) and Rancher Fleet (Apache-2.0)** appear as enterprise integrations (09, ZF-01). D-001 bans copying non-Apache-compatible code, not running a separate service, but EPL-2.0 needs a licence review before anything ships.
4. **Proposed amendments A-30-1…A-30-6 edit brief 30**, which has a founder override box. They stay proposals; nothing here edits that brief.
5. **ID clash ZF-13:** `REQ F-16…F-22` collide with decision IDs F-16…F-22.
6. **Stale board:** STATUS.md shows CORE-NET and CORE-FABRIC as `todo`, but `internal/mesh` and `internal/leaf` are on `main` and `feat/net-part2` (no PR open when checked) holds the join. Correct the board when that branch lands.

## 7. Decisions needed (Zeus)
Research recommendation first; each blocks the epic named.
| # | Question | Recommendation | Blocks |
|---|---|---|---|
| 1 | ZF-13: prefix for the new requirement IDs | `FB-R` | adding FB-R1…R7 to REQUIREMENTS.md |
| 2 | F-32 / Z-34: Headscale per site as default | yes | CORE-NET, MC-1 |
| 3 | ZF-11: NATS isolation by config users now, JWT at F5 | yes, unless FAB-3 says otherwise | CORE-FABRIC-2 hardening |
| 4 | ZF-02: remote k3s workers only if always-online cloud workers | yes | CORE-NET-11 wording |
| 5 | ZF-05: `onemind.site.<site_id>.` prefix at the fleet hub | yes | FAB-1 (naming part) |
| 6 | ZF-07: who approves `actuate` in multi-owner sites | named operator per site, set by an owner | FAB-5, MC-5 |
| 7 | ZF-01 and ZF-12: OneMind's own rings; 1 canary per hardware class, then 10 %, then the rest; 100 % success in ring 0, 95 % after | yes | MC-3, CORE-UPDATE-9 |
| 8 | ZF-08: fleet hub is the owner's own VM, summaries only | yes | MC-1 |
| 9 | ZF-04: FDO as optional zero-touch front end for OneMind-built hardware | yes, year 1 to 2 | CORE-FDO-1 |
| 10 | ZF-14: re-run refuters with separate agents | yes (FAB-7) | MC-1 start |
| 11 | ZF-09, ZF-10, ZF-15: vehicle scope, never agent setpoints, counsel on drone and vehicle law | missions only; counsel before any product claim | CORE-ROBOT |
| 12 | Extra hardware kits FK-1 (droplet), FK-2, FK-3, FK-4 beyond F-25's list | buy as each gate nears | FG1 to FG4 |

## 8. Where each epic's files live
`FAB-1`: `docs/architecture/CONTRACT-12-DRAFT.md`, `sdk/contracts/`. `FAB-2/3/4`: test code and `research-output/evidence/lab/` only (no product code). `FAB-5`: `core/onemind_core/mcp/`, `auth.py`. MULTI-CLUSTER, ADAPT, ROBOT, FDO: new modules; hotspots stay serialized per [NEXT-WAVE.md](../NEXT-WAVE.md) §1.
