<!-- SPDX-License-Identifier: Apache-2.0 -->
# Lesson 17: Robots are first-class citizens, not a second OS product

**Founder-requested learning entry · 2026-11-14 · documentation target, not shipped robotics support.** Serves M-7, F-1, F-14, AI-5 and M-1 in [requirements](../REQUIREMENTS.md). The complete [research and acceptance addendum](../../research-output/fabric/15-FIRST-CLASS-ROBOTICS.md) preserves conversation points 3 and 4, sources, failure cases and build gates.

## 1. Does Debian leave robotics behind?

No: the product goal is one native OneMind experience on qualified hardware, not one identical Linux installation everywhere. [D-007](../DECISIONS.md) locks Debian 13 for the shipping image, Ubuntu 26.04 for a light CI hedge, and records NVIDIA L4T Ubuntu 24.04 for Jetson dev kits. That exception is not proof of vendor compatibility for a specific board or ROS release.

**User space** means the applications and libraries above the kernel. A robotics container can carry Ubuntu user space on a Debian host, but shares Debian's kernel. It cannot conjure a missing camera driver or NVIDIA board-support package. Qualify architecture, GPU, cameras, CAN, USB, networking and timing on each exact host/runtime combination; never solve compatibility by giving every container blanket privileged access.

The other path is a vendor-supported Ubuntu/L4T companion running OneMind node software and adapters on top. OneMind can manage its supported apps without claiming to update that vendor host. Neither path has a demonstrated end-to-end OneMind robot acceptance pass here. PX4 recommends ROS 2 Jazzy on Ubuntu 24.04; that is separate from both official ROS distro support and OneMind membership. See the [source ledger](../../research-output/fabric/evidence/first-class-robotics/README.md); the ROS installation page was bot-blocked, not successfully read.

## 2. Point 3: what makes a robot a first-class citizen?

Not just an SSH link or a map pin. It needs all seven [acceptance rows RC1–RC7](../../research-output/fabric/15-FIRST-CLASS-ROBOTICS.md#3-first-class-citizenship-acceptance-matrix-conversation-point-3):

- Unique approved identity and hardware/capability discovery, rejecting impersonation.
- Native telemetry and status with timestamps, freshness and disconnected labels.
- Consistent typed API, MCP (AI tool interface) and UI capabilities, each explicitly read, write or actuate; no hidden physical effects or protocol bypass. A basic/telemetry label is not proof of a passive connection: inspect and test constructors, connect, start, stop, calibration and teardown against unapproved motion before any live connection; potentially actuating hardware paths require specific authorization.
- Managed app versions, health and safe staged updates with honest rollback limits; vendor OS explicitly not updated unless separately supported. Controller safety firmware/settings stay outside OneMind updates.
- Bounded human-approved missions, signed for the exact target, plan hash and expiry, with audit and refusal evidence.
- Revocation, replay rejection, deduplication and idempotency: retrying must not perform a mission twice.
- Local/disconnected operation, bounded outbox retention and visible overflow, safe reconnect and expired-command rejection. An outbox is a local diary waiting to sync, not infinite storage or permission to execute later.

These are **documented targets, all NOT RUN**, not a shipped support matrix. The current source still says CORE-ROBOT-1…3 `todo`, simulation PLAN-E15 and actuation PLAN-E7-LAB `parked`. Existing node/gateway/leaf features do not prove robot integration. No status or phase is promoted.

## 3. Point 4: who is allowed to think, decide and move?

```text
Human owner + step-up
        |
OneMind gateway: plan, bounded authorization, audit
        | signed, target-bound, expiring approved plan hash
Onboard companion + validating adapter
        | perception, local planning, mission coordination
        | approved high-level mission only
Dedicated flight/safety controller
        | stabilization, interlocks, failsafes, manual override
     actuators
```

Cloud/WAN is outside this loop. Selected telemetry crosses the adapter; the raw ROS DDS/Zenoh control graph stays isolated on the vehicle, not on a shared tailnet. Video and high-rate sensor data have a separate data path from control and bus summaries. A private network is not permission: PX4 warns that its DDS transport is unauthenticated.

AI tools never send raw motor/offboard setpoints, disable controller failsafes or change controller safety firmware/settings. The companion can coordinate a bounded mission; it cannot override the dedicated controller. On loss of cloud or vehicle link, only the already approved local behavior or controller failsafe applies. No unsolicited mission starts later on reconnect.

For example, an inspect-perimeter proposal can show the exact target, surveyed route/geofence, duration, expiry, sensor scope, abort/return behavior and plan hash. Planning and telemetry are allowed; motion needs approval of that exact plan and a validating adapter. Leaving its envelope requires a safe response or new approval, not autonomous scope expansion. **No physical command was executed.**

Product approval remains owner + step-up; who may become a named operator is an unresolved question, not decided here. For Legacy, physical actions additionally require Zeus's specific `execute` or `override` for that action. Documentation changes authorize no motion.

## 4. What has to happen before support can be claimed?

Follow the [build/test checklist](../../research-output/fabric/15-FIRST-CLASS-ROBOTICS.md#5-buildtest-checklist-and-unresolved-work): simulation/read telemetry first; signed approval rejection tests; expiry/replay/revocation and update tests; cloud/link loss; then only a separately authorized safe hardware bench. Keep existing FAB/ADAPT/ROBOT gates and parked work unchanged. No SITL or bench acceptance ran for this lesson.

One architecture ambiguity must be resolved before building: the epic glossary says a leaf has no k3s, but CORE-ROBOT-1 says k3s agent only. This lesson flags it without choosing a new architecture. Provisional FB-R names are not new locked requirements or NATS subjects.

## Check yourself

1. Why can Ubuntu user space on Debian not guarantee camera or GPU compatibility?
2. Why does first-class membership need refusal/replay tests as well as a good telemetry screen?
3. Which computer keeps the vehicle stable if the internet disappears?
4. Why does approving one perimeter inspection not authorize a later inspection?
