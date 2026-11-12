<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F1 steelman of the runner-up: Zenoh as the one bus

**Argued for Zenoh, as instructed.** Zenoh unifies pub/sub, storage and queries [C-FB3-007]; zenoh-pico reaches MCUs where NATS has no client of comparable size; it is a Tier 1 ROS 2 middleware [C-FBREF-008] and PX4 speaks it [C-FB9-001], so robots, drones and sensors would need no bridge; it is dual-licensed Apache-2.0/EPL-2.0 (C-LIC-051); its routers form geo-distributed meshes with peer-to-peer and client modes, which suits field kits. One protocol from the MCU to the cloud would remove a whole class of adapters.

**Why it still loses here.** OneMind's control plane (contract §12.9 streams, jobs, audit, outbox sourcing) is built and tested on NATS (fb3 T3, w8 lab, repo tests); Zenoh broke wire compatibility inside one ROS 2 distribution (C-REF-W2-robotics-003); and NATS gives per-node permissions and store-and-forward that the lab has measured. Switching would reopen a mission 01 decision (D-B6.5), which this mission may not do.

**What would make Zenoh win:** a measured need for MCU-native pub/sub that NATS's MQTT 3.1.1 path cannot serve, plus a Zenoh equivalent of the 30-minute outbox test passing.
