<!-- SPDX-License-Identifier: Apache-2.0 -->
# DC-F1 refuter, robotics-fit lens

**Claim given:** as DC-F1, in particular "Zenoh/ROS 2 is a bridge". **Cited:** C-FB3-007, C-REF-W2-robotics-003, C-FB9-001.

**Strongest counter-argument.** M-7 says robotics is the main moat. The robotics world chose DDS and Zenoh: Zenoh became a Tier 1 ROS 2 middleware in Kilted (2025) [C-FBREF-008], PX4 now offers a direct Zenoh interface [C-FB9-001], and zenoh-pico runs on microcontrollers [C-FB3-007]. Making NATS "the one bus" forces a bridge in every robot and every high-rate stream.

**New sources:** C-FBREF-008 (ROS 2 Kilted/Lyrical middleware status), C-FB9-001 (PX4 Zenoh interface).

**Verdict: upheld.** The claim already keeps Zenoh/DDS *inside* robots and bridges one level up; OneMind's bus carries meaning across sites, not 1 kHz joint states. Fast DDS is still ROS 2's default [C-FBREF-008], so even Zenoh is not the robotics bus yet.

**What would flip it:** OneMind needing robot-to-robot coordination across sites at ROS message rates (then a site-level Zenoh router mesh becomes a second, robot-only bus, still bridged to NATS for the OS).
