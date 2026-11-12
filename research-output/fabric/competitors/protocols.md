<!-- SPDX-License-Identifier: Apache-2.0 -->
# Protocols and foundations (FB-11, group 5)

**Date:** 2026-11-12.

> **Explain it like I'm the founder.** These are not competitors; they are the languages and standards OneMind either speaks natively (NATS), bridges (MQTT, Sparkplug, OPC UA, Modbus, MAVLink, Zenoh, Matter) or borrows ideas from (FDO, SPIFFE).

| Protocol / foundation | Role in OneMind | Licence of the implementation OneMind would use | Status / maturity | Evidence |
|---|---|---|---|---|
| **NATS / Synadia** | **the one bus**; leaf on every node; JetStream domains; MQTT 3.1.1 built in | Apache-2.0, CNCF-hosted (C-W4-056) | nats-server v2.15.3 (2026-11-11) [C-FB11-001] | leaf trees, no inbound port [C-FB3-002]; gateways [C-FB3-003]; MQTT [C-FB3-004]; per-node permissions on leaf logins [C-FB3-001] |
| **Eclipse Zenoh** | robot-internal bus (ROS 2 via `rmw_zenoh`); bridged at the companion | Apache-2.0 or EPL-2.0 (C-LIC-051) | 1.10.2 [C-FB3-007]; `rmw_zenoh` wire break in Jazzy (C-REF-W2-robotics-003) | [C-FB3-007] |
| **MQTT 3.1.1 / Sparkplug B** | devices connect to NATS's MQTT directly; Sparkplug topics mapped to the grammar | NATS (Apache-2.0); Sparkplug spec EPL-2.0 | Sparkplug 3.0 (2022-10-21) [C-FB3-005] | [C-FB3-004, C-FB3-005] |
| **MQTT 5** | Mosquitto app, bridged | Mosquitto EPL-2.0 or EDL (BSD-3) (mission 01 W8-R1) | — | mission 01 P0-4 |
| **OPC UA** | adapter (read first) | open62541 MPL-2.0, v1.5.10 [C-FB11-003] | IEC 62541 (text not opened) | — |
| **Modbus TCP/RTU** | adapter | to choose (pymodbus BSD-3 or libmodbus LGPL; not re-checked) | stable | — |
| **CAN** | adapter over SocketCAN | Linux kernel | stable | — |
| **MAVLink** | adapter + `mavlink-router` on the companion | generator output MIT (C-LIC-045); mavlink-router Apache-2.0 [C-FB11-003] | stable | `10-…` |
| **FDO (FIDO Alliance)** | zero-touch front end for OneMind-built hardware | go-fdo-server/client Apache-2.0 (v1.0.2 / v1.0.0) | FDO 1.1 and 2.0 Proposed Standards 2026-04-02 (C-W8-042); go-fdo interop testing not complete (C-G4U-006); **lab PASS** | [C-FB2-003], `03-…` |
| **SPIFFE / SPIRE** | pattern for node and workload attestation; not a dependency | Apache-2.0, v1.16.0 | CNCF | [C-FB2-001, C-FB2-002] |
| **Matter / Thread** | home devices through a Matter controller app; phone scans `MT:` codes | connectedhomeip Apache-2.0, v1.6.1.0 | DAC attestation, revocation checks, multi-admin [C-FB2-004] | — |
| **W3C WoT Thing Description** | export format for capability descriptions | spec (W3C) | Recommendation 2023-12-05 [C-FB5-001] | `06-…` |
| **Asset Administration Shell** | industrial export (year 2) | specs CC-BY-4.0; Eclipse BaSyx server SDK MIT [C-FB11-015] | — | `06-…` |
| **Eclipse Ditto** | avoided in core | EPL-2.0, 3.9.8 [C-FB11-002] | active | `06-…` |
