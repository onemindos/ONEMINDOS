<!-- SPDX-License-Identifier: Apache-2.0 -->
# 14 · Open questions for Zeus (fabric mission)

**Date:** 2026-11-12 · Each item: options, the recommendation, what it blocks. The run could not ask you (brief header), so every recommendation below is the assumption the other files use until you rule. Proposed new requirement IDs are at the end; `docs/` is not edited.

> **Explain it like I'm the founder.** These are the forks in the road this research found. For each one there is a recommended path and the reason. None of them reopens mission 01 (base OS, RAUC, k3s, restic, E1–E10). Most can wait until the epic that needs them starts; the first four shape work already on the board.

| ID | Question | Options | Recommendation | Blocks | Evidence |
|---|---|---|---|---|---|
| **ZF-01** | What runs multi-site rollouts? | (a) OneMind's own rings over signed NATS jobs (extends CORE-UPDATE-9); (b) Rancher Fleet in core; (c) Open Cluster Management | **(a)**, with Fleet as an optional engine for Kubernetes-heavy enterprise sites (year 2+) | MULTI-CLUSTER-3 | lab fb4: Fleet's partition rule counts a not-yet-updated cluster as unavailable, so `maxUnavailable: 0` never starts an update [C-FB4-016]; Fleet advisories in registration [C-FBREF-011]; Fleet works offline-tolerant and pull-based [C-FB4-003] |
| **ZF-02** | Can a k3s worker live at another site? | (a) only always-online cloud workers; (b) any site over the mesh; (c) never | **(a)** | NETWORKING §8 wording, CORE-NET-11 | k3s: "all servers should be in the same location"; high latency "could also impact the health of the cluster" [C-FB4-001]; `05-…` |
| **ZF-03** | One mesh for everything or one per site? | (a) Headscale per site, sites linked by NATS leaf over TLS; (b) one global Headscale; (c) a larger coordinator (NetBird, Nebula, hosted Tailscale) for multi-site | **(a)** now; revisit (c) only if site-to-site traffic is needed | MULTI-CLUSTER-1, F-32 follow-up | Headscale's single-tailnet scope [C-FB3-006]; O(N²) report [C-FBREF-006] |
| **ZF-04** | Zero-touch for OneMind-built hardware | (a) FDO front end + OneMind voucher store, rendezvous run by OneMind *and* optionally by the owner; (b) IDevID + a OneMind enrolment service, no FDO; (c) ticket + approval only | **(a)** behind an interface, keeping (c) as the universal path; add **scan-to-confirm** and **batch tickets** (count + expiry) | CORE-FDO-1, hardware line (H-1) | lab fb2 PASS; go-fdo maturity [C-FBREF-010, C-G4U-006]; pairing UX risk [C-FBREF-009] |
| **ZF-05** | Naming across sites | (a) `onemind.site.<site_id>.` prefix at the fleet hub + `<node_id>-<device_id>` producer token; (b) site id inside every subject at the source; (c) no cross-site subjects (API only) | **(a)** (stays inside the OS-owned `onemind.>` space) | C12 naming PR, MULTI-CLUSTER-2 | `06-…`; contract §12.9 |
| **ZF-06** | Managed Kubernetes (DOKS/EKS/GKE) | (a) supported as a *site* with no host control; (b) not supported | **(a)**, labelled honestly | founder's DOKS migration plan (`05-…` §9) | `02-…` row 2c; [C-FB4-003] |
| **ZF-07** | Who approves in a site with several owners? | (a) any owner; (b) all owners for `destructive`/`actuate`; (c) a named operator role per site | **(a)** for `sensitive`, **(c)** for `actuate` (one named operator per site, set by an owner) | `07-…` A5, NOTIFICATIONS routing | contract §12.3, §12.6 |
| **ZF-08** | Who hosts the fleet hub, and what may it read by default? | (a) the owner's own cloud VM, summaries only; (b) OneMind-hosted service; (c) no fleet hub | **(a)** (M-1 local-first; the cloud is "an optional node") | MULTI-CLUSTER-1 | brief §2 sovereignty |
| **ZF-09** | Vehicle scope in year 1 | (a) drones and rovers in SITL and on the bench; (b) plus road vehicles; (c) none | **(a)**; road vehicles only after counsel on UN R155/R156 | CORE-ROBOT | `10-…` §4 (standards not opened) |
| **ZF-10** | May agents ever send setpoints to a vehicle? | (a) never (missions only, approved); (b) with a teleop safety review later | **(a)** now; (b) is a separate future decision | B12, MAVLink adapter | PX4 offboard warnings [C-FB9-001] |
| **ZF-11** | NATS isolation model per node | (a) top-level config users with permissions (tested); (b) one account per node; (c) operator/JWT | **(a)** until 7-day soak or NT-6 says otherwise; **(c)** at F5 scale | CORE-NET-4, CORE-FABRIC-2 | [C-FB3-001]; [C-FBREF-001, -002] |
| **ZF-12** | Default rings | sizes and success thresholds | ring 0 = one canary per hardware class; ring 1 ≈ 10 %; ring 2 = rest; 100 % success in ring 0, 95 % after | MULTI-CLUSTER-3, CORE-UPDATE-9 | Flight Control success thresholds [C-FB11-005] |
| **ZF-13** | ID clash | the brief asks for new requirement IDs "F-16…", but `docs/leap/DECISIONS-NEEDED.md` already uses F-1…F-60 for founder decisions | keep the brief's numbering below but always write "REQ F-n" in prose until you pick a prefix (suggestion: `FB-R1…`) | docs/REQUIREMENTS.md edit | — |
| **ZF-14** | Refuters were not blind | (a) accept; (b) re-run DC-F1…F3 refuters with separate agents | **(b)** before the MULTI-CLUSTER epics start | confidence of DC-F1…F3 | `evidence/refuters/README.md` |
| **ZF-15** | Legal texts not read | counsel or a human reads EU 2019/947, 2019/945, 14 CFR 89/107, UN R155/R156, ISO 26262 family | do it before any vehicle or drone product claim | ZF-09 | [C-FB9-004] |

## Proposed new requirement IDs (to add to `docs/REQUIREMENTS.md` if you agree)

| ID | Requirement | Source file |
|---|---|---|
| **REQ F-16** | Every machine class in the join matrix has a passing join test before it is called "supported" | `02-…` |
| **REQ F-17** | No machine receives credentials without an owner approval it can be matched to (pairing code, scan, or approved voucher) | `03-…` |
| **REQ F-18** | Every device and capability has one stable address used by the bus, API, MCP, audit and UI | `06-…` |
| **REQ F-19** | No device actuation path bypasses the site gateway's approval; a negative test per adapter proves it | `07-…` |
| **REQ F-20** | A site keeps full local operation with no time limit when every external link is down (tested by a 24-hour WAN-cut lab) | `08-…` |
| **REQ F-21** | Every class has a documented update engine and rollback path, or an explicit "never updated by OneMind" label | `09-…` |
| **REQ F-22** | Multi-site views work from site summaries alone; an unreachable site shows its last summary and age | `11-…` |
