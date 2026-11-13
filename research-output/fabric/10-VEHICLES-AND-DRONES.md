<!-- SPDX-License-Identifier: Apache-2.0 -->
# 10 · Vehicles and drones (FB-9): the companion-computer pattern, what OneMind may and may not do

**Date:** 2026-11-12 · **Workstream:** FB-9 (Tier B: primary sources; no lab) · **Status:** pattern confirmed; standards identified, several not opened (blocked to automated reading, labelled).
**Serves requirements:** M-7, N-7, F-1, F-3, AI-5, AI-7 · safety line from mission 01 (AI never actuates without human approval; safety stays on dedicated controllers)

> **Explain it like I'm the founder.** On a drone, a rover, a boat or a car there are two computers. The **flight (or safety) controller** keeps the vehicle stable and safe many times a second; it has its own failsafes, its own certification story, and OneMind never replaces it, never updates it and is never inside its loop. The **companion computer** (a Jetson or a Pi) does the "thinking" work: cameras, maps, logging, talking to the outside world. OneMind runs only on the companion, as a leaf. It can read everything, record everything and propose missions; a human approves any mission before it is sent, and the flight controller can always refuse or fall back to landing on its own.

## 1. The pattern, as shipping products do it

| Evidence | What it shows |
|---|---|
| PX4 Offboard mode: setpoints come from "a companion computer" over MAVLink/MAVSDK or ROS 2 (uXRCE-DDS or Zenoh); a 2 Hz proof-of-life is required; on loss PX4 leaves Offboard and lands or runs `COM_OBL_RC_ACT`; generic offboard "bypass[es] all internal PX4 control loops and should be used with great care"; PX4 cannot tell ROS 2 messages from internal ones, so conflicting writes can be "possibly catastrophic" [C-FB9-001] | The flight controller owns the failsafe; low-level setpoint control from outside is dangerous and must not be an AI tool |
| ArduPilot: companion computers "interface and communicate with ArduPilot on a flight controller using the MAVLink protocol", pre-process sensors and make in-flight decisions; listed boards include Raspberry Pi, Pixhawk Jetson and CM4/CM5 baseboards, ModalAI VOXL2 [C-FB9-002] | Same split in the other big open autopilot |
| Auterion Skynode: one device, but PX4 on the flight controller and a managed OS with sandboxed add-ons on the mission computer; "The OS is managed by Auterion in production" [C-FB9-005] | A commercial product doing exactly the OneMind split |
| Licences: PX4 BSD-3-Clause, ArduPilot GPL-3.0 (C-LIC-047); MAVLink generator output MIT (C-LIC-045); mavlink-router Apache-2.0 [C-FB11-003] | OneMind can ship a MAVLink adapter and router without copyleft in the core |

## 2. What the companion (OneMind leaf) may and may not do

| May (default) | May only with an approved `actuate` action | Never |
|---|---|---|
| read MAVLink/CAN telemetry and publish it to the bus | upload a mission (waypoints, geofence, return point) | send generic offboard setpoints from an AI agent |
| record video, logs, MCAP | arm / disarm, take off, start mission | change flight-controller firmware or safety parameters from OneMind |
| run perception and propose missions | change mode within the autopilot's allowed set | disable or override the flight controller's failsafes |
| raise alerts and show the vehicle on a map | — | act during a link loss beyond the mission already approved (`08-…` §3) |

Teleoperation by a **human** with a live video link is a separate, later feature (research 12 REC-W11-14) with its own latency and safety review.

## 3. Bus and adapters on a vehicle

- `mavlink-router` on the companion splits the flight controller's MAVLink stream between the ground station, the OneMind MAVLink adapter and other consumers.
- The **MAVLink adapter** publishes `tel.<node>-mavlink-1.<class>.<metric>` and accepts only gateway-signed, expiring mission commands (`06-…`, `07-…` A7).
- ROS 2 stays inside the vehicle on DDS or Zenoh; one bridge at the companion (`04-…`).
- The companion is a **leaf**: its outbox keeps everything while the vehicle is out of range (`08-…`).

## 4. Safety and regulatory standards to plan for (identified; not summarised beyond what was opened)

| Domain | Standard or rule | Status of our reading |
|---|---|---|
| EU drones | EASA open/specific/certified categories; open-category subcategories A1–A3; class labels C0–C4; 120 m altitude; remote identification required for open-category drones with limited exceptions [C-FB9-003] | PRIMARY (EASA page) |
| EU drones (legal text) | Implementing Regulation (EU) 2019/947 and Delegated Regulation (EU) 2019/945 | **not opened** (EUR-Lex returns empty pages to automated reading; mission 01 hit the same, C-STEEL-cra-nb-018) |
| US drones | 14 CFR Part 107 (small UAS) and Part 89 (Remote ID) | **not opened** (eCFR redirected to a bot wall; not bypassed) [C-FB9-004] |
| Road vehicles: cyber and updates | UN Regulations No. 155 (cyber security management system) and No. 156 (software update management system) | **not opened** (unece.org 403) [C-FB9-004]; R156 matters directly to OTA on cars |
| Road vehicles: safety | ISO 26262 (functional safety), ISO 21448 (SOTIF, June 2022, confirmed only via resellers), ISO/SAE 21434 (cybersecurity), ISO 24089 (software update engineering) | catalogue pages **blocked** (iso.org 403) [C-FB9-004] |
| Industrial robots and AMRs | ISO 10218 (industrial robots), ISO 3691-4 (driverless industrial trucks) | **blocked** (iso.org 403) |
| Generic | IEC 61508 functional safety | not opened |

**What would verify these:** a human reading the official texts (EUR-Lex, eCFR, UNECE, ISO OBP) and recording clause numbers and application dates in this ledger. Until then, every product decision that depends on them is `blocked: founder-decision` (counsel), listed in `14-…`.

## 5. What competitors do (constraint-matched)

| Product | Companion OS | Who owns flight safety | Constraint fit | Take |
|---|---|---|---|---|
| Auterion (Skynode) | managed AuterionOS, sandboxed add-ons [C-FB9-005] | PX4 on the flight controller | High pattern, proprietary OS | The split; app sandbox on the companion |
| ModalAI VOXL2 | companion with its own OS (listed by ArduPilot [C-FB9-002]) | flight controller | Medium | — |
| Formant, Foxglove | agent/bridge on the robot computer; WebRTC teleop through vendor services (C-TD-tier-c-robotics-007, -022) | the robot's controller | Low (cloud) | Outbound-only links |
| Anduril Lattice | entities and tasks APIs; gRPC for high-rate telemetry from drones and robots [C-FB11-011] | per platform | Low (proprietary, defence) | Vocabulary only |

## 6. Open items

- **ZF-10** confirm: OneMind never exposes setpoint-level control to agents; missions only, approved by a human.
- **ZF-09** vehicle scope for year 1 (drones and rovers in a lab with SITL first; road vehicles later and only with counsel on UN R155/R156).
- Founder kit (build path P3): Jetson Orin Nano + a Pixhawk-class controller in PX4 SITL first, then on the bench with props off.

## Glossary

| Term | Meaning |
|---|---|
| Flight controller | The small real-time computer that keeps a drone stable (runs PX4 or ArduPilot) |
| Companion computer | A bigger computer on the vehicle for cameras, AI and links |
| Offboard mode | PX4 following setpoints sent from outside the flight stack |
| SITL | Software in the loop: the autopilot running in a simulator |
| MAVLink | The message protocol between autopilots, companions and ground stations |
