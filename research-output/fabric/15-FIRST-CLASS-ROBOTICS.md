<!-- SPDX-License-Identifier: Apache-2.0 -->
# 15 · First-class robotics: Debian, Ubuntu and the autonomy boundary

**Founder-requested research and acceptance addendum · 2026-11-14.** Documentation only; not a new founder decision, implementation, schedule change, deployment or authority to actuate. Serves M-7, F-1, F-14, AI-5 and M-1 in [REQUIREMENTS](../../docs/REQUIREMENTS.md). [Lesson 17](../../docs/learning/17-robotics-first-class-citizens.md) gives the plain-language explanation.

## 1. Decision and evidence baseline

[D-007](../../docs/DECISIONS.md) remains final: Debian 13 ships the OneMind image; Ubuntu 26.04 is a light CI hedge. Jetson's NVIDIA L4T Ubuntu 24.04 **dev-kit** exception is recorded there, with Z-01 still needed. This is not an independently verified claim that any particular Jetson board, BSP (board-support package), ROS release or vendor driver combination is supported. Machines OneMind does not own retain their unmodified host OS. No frozen research score is changed.

Rechecked at source **5d898d06d0ef542d8038b8ef5c0688d78ce21300**, following the earlier review at `13372ae1d04bece9b184ef210708ab1a7eeecefb`: [STATUS at reviewed source](https://github.com/onemindos/ONEMINDOS/blob/5d898d06d0ef542d8038b8ef5c0688d78ce21300/docs/leap/STATUS.md) still marks CORE-ROBOT-1…3 `todo`, PLAN-E15 (robot simulation) `parked`, and PLAN-E7-LAB (typed actuation) `parked`. Generic node detection, heartbeat, gateway approvals and leaf networking are foundations, **not proof of a complete robot path**. No simulation, bench, flight or physical command was run for this research.

### Sources versus inference

Primary sources accessed **2026-11-14**; short exact excerpts, source URLs and SHA256 hashes are saved in the [evidence ledger](evidence/first-class-robotics/README.md). These are upstream descriptions, not OneMind test results:

- [PX4 ROS 2 guide](https://docs.px4.io/main/en/ros2/user_guide.html): recommends ROS 2 Jazzy LTS on Ubuntu 24.04. This does not establish official ROS distro support for Debian or prove a Debian-hosted container configuration.
- [Docker container explanation](https://docs.docker.com/learn/content/what-is-a-container/): containers share the host kernel. An Ubuntu user space does not replace Debian's kernel, firmware or drivers.
- [PX4 DDS bridge](https://docs.px4.io/main/en/middleware/uxrce_dds): unauthenticated DDS reaches uORB directly and must be isolated. A private mesh or direct cable alone is not authorization.
- [PX4 companion pattern](https://docs.px4.io/main/en/companion_computer/): supports the controller/companion distinction, not permission for an AI tool to control actuators.

The ROS Jazzy installation page returned a bot wall, not documentation. It was **not successfully read** and is not evidence here. Upstream `main` pages can change; saved excerpts identify what was actually reviewed, not a frozen upstream release certification.

## 2. Two qualification paths, one product experience

First-class means **native OneMind identity, capabilities, lifecycle, API/MCP/UI and authorization**, not the same Linux distribution everywhere. MCP is the AI tool interface, not a second control plane. Official ROS distribution support and OneMind product integration are separate support claims.

| Path | Qualification required before calling it supported | Explicit limit today |
|---|---|---|
| Debian 13 host with qualified Ubuntu-user-space robotics containers | Record host kernel, CPU architecture, pinned runtime image, ROS/middleware versions, hardware and driver/BSP matrix; test GPU, cameras, CAN, USB, device access, networking, timing and restart behavior per target | Shared kernel; no missing driver/BSP or real-time guarantee supplied by the container. No universal compatibility and no proven deployment |
| Vendor-supported Ubuntu/L4T companion plus OneMind node software and adapters | Verify selected vendor board/BSP/OS/runtime support; qualify enrollment, adapter isolation, application lifecycle and local failures on that exact combination | D-007's Jetson dev-kit record is not vendor compatibility evidence. Vendor host remains vendor-managed unless separately supported |

Use least-privilege device access, explicit mounts and network boundaries, pinned images and resource requests/limits when implementation is authorized. **No blanket privileged-container bypass.** A successful package install is not hardware or safety qualification. The older lesson 03 statement that ROS runs in containers on every base is historical shorthand, not a compatibility guarantee; this qualification rule governs robotics acceptance without changing the old scorecard.

**Documented first-class target versus shipped support matrix:** both paths are design/qualification candidates, **UNVERIFIED for an end-to-end OneMind robot**. A future support row must name board, host/kernel/BSP, architecture, runtime/ROS/middleware, adapter version, controller/firmware, update owner, date and immutable test evidence. Do not promote a machine class to supported from docs inspection alone.

## 3. First-class citizenship acceptance matrix (conversation point 3)

All rows below are **NOT RUN** acceptance work, not claims of existing behavior. RC identifiers are local checklist labels, not new API or requirement contracts. FB-R1…FB-R7 remain **provisional** names; no new NATS subjects, endpoints or capability names are defined. Exact wire contracts must follow the locked grammar and existing contract review process.

| ID | Required acceptance and negative tests | Existing requirement | Existing epic/gate | Result |
|---|---|---|---|---|
| RC1 | Owner-approved enrollment yields one unique stable node/device identity. Discover hardware and capabilities with provenance; reject unauthenticated enrollment, wrong-owner/device binding, reused enrollment and node A claiming B | M-7, F-14, AI-5 | CORE-ROBOT-1; CORE-FABRIC-1/2; FAB-2; FG1 | NOT RUN |
| RC2 | Native telemetry/status in Nodes and device views carries timestamps, age, freshness, units and disconnected/stale labels. Reconnect must not present old data as live; only scoped selected telemetry crosses the adapter | M-7, F-1, M-1 | CORE-ROBOT-2/3; CORE-ADAPT-4; FG4 | NOT RUN |
| RC3 | Same typed identity, schema, validation and authorization through API, MCP, UI and audit. Every capability declares read/write/actuate effect; a physical effect is never hidden behind read or harmless-looking write. Review and test constructors, connect, start, stop, calibration and teardown for unapproved actuation; a basic/telemetry label does not establish a passive path. Reject unknown capability/effect and direct-protocol bypass | F-14, AI-5 | CORE-ADAPT-1/4; FAB-1/5; CORE-ROBOT-2/3; FG2/FG4 | NOT RUN |
| RC4 | Managed apps expose version, health, dependencies and restart/update state. Test signed/pinned staged update, unhealthy release rejection/rollback and interrupted update while safely idle. Show rollback coverage and data-migration limits; never update in a way that disrupts an active mission. Vendor host explicitly says not updated by OneMind unless separately supported; controller firmware/settings excluded | F-1, F-14, AI-5 | CORE-ROBOT-1; FAB-4; provisional FB-R6; FG1/FG4 | NOT RUN |
| RC5 | Bounded mission approval shows target, plan hash, scope, expiry, safety limits and human identity. Adapter checks gateway signature, target binding, approved plan hash and expiry at execution. Reject missing/forged approval, changed plan, wrong target, unauthenticated/direct MAVLink or DDS bypass and agent self-approval; audit request/approval/refusal/outcome | AI-5, M-7 | CORE-ROBOT-2; CORE-ADAPT-1; FAB-5; LT-VM-18; FG2/FG4 | NOT RUN |
| RC6 | Revoke node, adapter and acting principal grants; deny revoked credentials even after reconnect. Deduplicate mission IDs, reject replay, make retries idempotent across restart and retain auditable outcomes without executing twice. Never let transport retry grant fresh authority | AI-5, M-1 | CORE-ROBOT-2; CORE-ADAPT-1; FAB-2/5/6; FG2/FG4 | NOT RUN |
| RC7 | Local authorized operation survives cloud/WAN loss; vehicle link loss invokes only approved local behavior or controller failsafe. Configure bounded outbox byte/time retention, overflow/drop visibility and safe ordered/deduplicated drain. Reject expired queued commands at execution/reconnect; reconnect never launches an unsolicited later mission | M-1, AI-5 | CORE-FABRIC-5; FAB-3/6; CORE-ROBOT-1/2; FG2/FG4 | NOT RUN |

The numeric freshness, outbox retention and mission safety limits must be specified per qualified profile before tests; they are not invented here. Local-first does not mean infinite storage or stale actuation authority. These rows clarify existing gates, not bypass their dependencies.

## 4. OneMind / companion / controller boundary (conversation point 4)

```text
Human owner + step-up (named-operator question remains open)
              |
              v
OneMind site gateway: plan -> authorize bounded request -> audit
              |
              | signed mission: target + expiry + approved plan hash
              v
Onboard companion: OneMind node + validating capability adapter
  perception / local planning / mission coordination / bounded outbox
              |
              | only approved high-level mission within controller limits
              v
Dedicated flight / safety controller
  real-time stabilization / interlocks / failsafes / manual override
              |
           actuators

Selected scoped telemetry <- adapter -> API / MCP / UI projections
Camera/video/high-rate data -> separate bounded data path, not control bus
Cloud/WAN: optional summaries/planning; OUTSIDE the control loop
ROS DDS / Zenoh graph: isolated on vehicle, NOT shared tailnet control
```

The gateway is the plan/authorization/audit boundary; the onboard companion performs perception, planning and mission coordination. The dedicated controller owns real-time stabilization, hardware interlocks, failsafes and manual override. OneMind never disables controller failsafes, changes its safety firmware/settings or offers raw motor/offboard setpoint AI tools. Middleware isolation must prevent an unauthenticated local writer from circumventing the adapter; mesh reachability alone never authorizes control. Only selected scoped telemetry and capabilities cross the adapter, not the whole ROS graph. Video/high-rate sensor streams use a separate data plane with explicit access and retention, not command subjects or unbounded bus projection.

**Approval is bounded, not general autonomy.** Product baseline remains owner + step-up. The named-operator proposal in ZF-07 is unresolved; this document does not settle it. For Legacy's operational authority, physical actions require Zeus's specific `execute` or `override` authorization for that action, in addition to product approval and runtime safety checks. Saving these docs grants no actuation authority. A disconnected site must enforce authorization locally or fail closed; cloud absence does not waive approval. Revocation propagation and locally cached grant limits need explicit tests, not assumptions.

**Example — inspect a perimeter:** planning may propose a surveyed bounded route, vehicle identity, geofence, duration, sensor use, expiry, abort/return behavior and approved plan hash. Telemetry and a preview can be read without issuing motion. The human reviews that exact request; only a separately authorized adapter may pass the approved mission to the controller. Obstacles outside the approved envelope require a safe stop/return or a newly approved plan, never an enlarged mission. On cloud/link loss only preapproved local behavior/controller failsafe continues. Reconnection does not revive an expired request or start a new inspection. **This example executed no physical command.**

## 5. Build/test checklist and unresolved work

Keep [existing EPICS phases and gates](../../docs/leap/fabric/EPICS.md) unchanged. CORE-ROBOT-1 owns companion integration, CORE-ROBOT-2 owns the MAVLink mission adapter, and CORE-ROBOT-3 owns the scoped ROS bridge; each must satisfy its mapped RC rows. Required evidence sequence:

1. Qualify host/runtime/device isolation; simulation plus read-only telemetry and identity/schema checks (RC1–RC3). Before the first live connection, inspect the exact constructor/connect/start/stop/calibration/teardown path and exercise it with simulated drivers or intercepted command sinks; assert that none issues unapproved physical commands. A basic, visualizer or telemetry blueprint is not presumed passive. Any hardware connection whose lifecycle may actuate requires separate specific authorization and the controlled bench gate below. PLAN-E15 remains parked until its existing prerequisites/authorization are satisfied. No SITL run is claimed.
2. In simulation, exercise signed approval and rejection, wrong-target/changed-plan/direct-protocol negatives (RC3, RC5); record audit chain and controller refusal behavior.
3. Test expiry, replay, deduplication, idempotency, revocation and safe staged app updates, including restarts (RC4–RC6).
4. Inject cloud/WAN and vehicle-link loss, outbox overflow, stale telemetry and reconnect with queued expired requests (RC2, RC7). FAB-6 and controller failsafe evidence are separate from happy-path simulation.
5. Only after existing gates and specific human authorization, run a controlled hardware bench (props off or equivalent actuator-safe setup), then any separately authorized hardware qualification. A simulation pass is not flight readiness or regulatory certification.

Record target versions, test command, expected and observed output, negative outcomes, artifacts and source SHA for every row. **All RC acceptance: NOT RUN. Source/document validation only for this change.**

Unresolved: §1 glossary of EPICS says leaf has **no k3s**, while CORE-ROBOT-1 says **k3s agent only**. Flagged architecture ambiguity: do not silently choose either or claim a deployable topology. Resolve in the existing architecture/decision process before implementing that epic. ZF-07 operator authority, ZF-09/10 vehicle scope and safety questions, provisional FB-R naming, target support matrices, legal/vendor redistribution questions (Z-01) and numeric acceptance bounds remain open. No new founder decision or roadmap reprioritization is recorded here.
