<!-- SPDX-License-Identifier: Apache-2.0 -->
# Founder note 12: the universal connector, how the outside world plugs into OneMind

**For:** Zeus · **Date:** 2026-11-26
**Status:** founder-requested learning entry. It adds no decision and starts no work. Robotics stays **parked** (founder rule, 2026-11-14). "What next" is opinion; every "exists" row points at code on this branch.
**Feeds:** DC-16 plugin sockets E1–E10 ([`research-output/01-FOUNDATION-DECISION.md`](../../../research-output/01-FOUNDATION-DECISION.md) §4.8), the connector contract ([`sdk/contracts/connectors.md`](../../../sdk/contracts/connectors.md), #604/#610), D-022 (app tokens through the gateway), AI-5 (human approval), robotics acceptance RC1–RC7 ([lesson 17](../17-robotics-first-class-citizens.md)), physical-AI paths ([note 10](10-c2-and-physical-ai-paths.md)).

---

## The short answer

Yes, it is possible, and most of the universal connector **already exists**. It is not one giant adapter that speaks every protocol. It is **one contract**: every outside system (a SaaS API, an SDK, a sensor, a PLC, later a robot) comes in as an ordinary OneMind app with one manifest, and that manifest can only use five narrow doors that the gateway controls.

"Universal" comes from the contract, not from one program. A new SDK means a new small app that fits the contract, never a change to the OS.

## Terms

- **Manifest:** the `onemind.app.yaml` file that says what an app is and what it may touch ([schema](../../../sdk/schema/onemind.app.schema.json)).
- **Gateway:** the OneMind core (`core/`); the only thing that checks permissions, holds secrets and writes the audit log.
- **Adapter:** a small app that speaks one outside protocol (MQTT, ROS 2, MAVLink, OPC UA, Modbus) on one side and the OneMind contract on the other.
- **Datapoint:** the one shared shape for a reading (id, revision, time, value, unit, quality, position): [`onemind.datapoint.schema.json`](../../../sdk/schema/onemind.datapoint.schema.json).

## The five doors (all in the one manifest)

```text
 outside world                     OneMind box
 ─────────────                     ──────────────────────────────────────────
 SaaS / API / SDK ──┐
 sensor / PLC ──────┤   adapter app (container, sandboxed, signed)
 camera ────────────┤        │
 robot (parked) ────┘        │
                             ├─ 1 IN      bridge  → POST /v1/bridges/<id>/events → datapoints, map, NATS
                             ├─ 2 OUT     tools   ← gateway dispatch (signed, short-lived) ← approval
                             ├─ 3 ACCOUNT connector: gateway holds the OAuth / API key
                             ├─ 4 STREAM  videoSource + own NATS account (APP_<id>)
                             └─ 5 HARDWARE E2 host grant: one device node, GPU, RT, host net
                                           (owner approves, revocable)
 AI agents ── MCP ── gateway ── sees the app's tools typed read / write / actuate
```

| Door | What it is for | Status | Code |
|---|---|---|---|
| 1 In (`bridge`) | Outside data enters one way, rate-limited, deduped, licence stamped, paused after 20 bad events | **Built** | [`bridges.py`](../../../core/onemind_core/bridges.py) |
| 2 Out (`tools`) | The gateway calls the app with a signed, short-lived credential; changes are owner-approved actions | **Built**; `effect: actuate` is **refused** by the validator | [`plugins/dispatch.py`](../../../core/onemind_core/plugins/dispatch.py), [`plugins/tools.py`](../../../core/onemind_core/plugins/tools.py) |
| 3 Account (`connector`) | Owner connects an outside account; the gateway holds the key, the app never sees a raw token outside its grant | **Schema built** (auth: none, api-key, oauth-code, oauth-device) | schema `spec.extensions.connector`, D-022 |
| 4 Stream (`videoSource`, `nats`) | Cameras (frames never on the bus) and the app's own message subjects | **Schema built** | schema `spec.extensions.videoSource`, `.nats` |
| 5 Hardware (E2 broker) | USB, serial, CAN, GPU, real-time: one named device, owner approval only | **Built** | [`hostgrants/`](../../../core/onemind_core/hostgrants/) |
| Safety | One owner switch refuses every physical action | **Built** | [`physical.py`](../../../core/onemind_core/physical.py) (#723) |

Because of the contract, AI gets every integration for free: an adapter's tools appear to agents over MCP, typed read / write / actuate, and nothing physical runs without a person approving that exact action.

## The plugin system is the connector

The five doors are not a second system next to the plugin system: they **are** plugin sockets. A connector is plugin type 4 (device / protocol adapter) or type 5 (AI tool / MCP server) in [`research-output/29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`](../../../research-output/29-PLATFORM-ECOSYSTEM-MARKETPLACE.md).

| Door | Socket | Socket's job |
|---|---|---|
| Install, update, roll back the adapter | E1 Market controller | `onemind.app.yaml` + Helm |
| 5 Hardware | E2 capability broker | device, GPU, RT, host-network grants |
| udev rules, host binaries a driver needs | E3 sysext / confext | signed-only, already in the image (`os/rootfs/.../10-onemind-signed-only.conf`) |
| Kernel drivers (CAN, NPU, cameras) | E4 driver packs | per-kernel signed modules |
| Robot / sensor panels in the dashboard | E5 UI slot | sandboxed iframe widgets (#179) |
| 2 Out, AI tools | E6 capability registry + approval gateway | MCP / REST / CLI tools with read / write / actuate |
| 1 In, 4 Stream | E7 NATS grants | the app's own subjects only |
| "Greenhouse box", "TAK node" bundles | E8 profiles | confext + sysexts + app set |
| Signing, kill list | E9 trust root | publisher signature, countersignature, revocation (#182) |
| Boot overlays, firmware | E10 | release pipeline only |

The connector kit suggested below already has an issue: **#657 "Bridge SDK and the first keyless bridges"**, with #658 (datasets and local receivers), #666 (public video) and #733 (radio grant) after it.

## Is the plugin system native to Debian?

Partly. The layer that changes the OS uses Debian 13's own tools; the layer that connects outside systems is OneMind's code on top, because Debian has nothing that does that job.

**Native already:**

| Socket | Native tool |
|---|---|
| E3 host add-ons | `systemd-sysext` / `systemd-confext` from Debian 13's systemd 257, locked to signed images ([`10-onemind-signed-only.conf`](../../../os/rootfs/layers/base/usr/lib/systemd/system/systemd-sysext.service.d/10-onemind-signed-only.conf)) |
| E4 drivers | Plain signed kernel modules, `module.sig_enforce=1` |
| Device rules | udev, shipped through E3 |

This is already the most native way to extend a read-only Debian image; Flatcar and other image-based systems do the same.

**OneMind's own:** E1 Market, E2 hardware grants, E6 tools and approvals, E7 NATS channels, in the gateway and k3s. Debian has no "this app may use this one USB device after the owner approves, and AI calls its tools only with approval". That layer is what makes OneMind more than Debian.

**Debian-native options set aside:**

| Option | Why not as the plugin path |
|---|---|
| apt / `.deb` | Writes into the read-only `/usr`; the next A/B update wipes it |
| DKMS (drivers built on the box) | Unsigned modules, refused under Secure Boot; NVIDIA's DKMS build broke on routine Debian kernels ([`01-FOUNDATION-DECISION.md`](../../../research-output/01-FOUNDATION-DECISION.md) DC-13), so drivers are built and signed once in CI |
| Flatpak | Desktop apps only; no device grants or approvals |

**Worth researching (UNVERIFIED, not in the research yet):** systemd **portable services** (`portablectl`) run a small service directly on the host under systemd's own sandbox (`DeviceAllow=`, `DynamicUser=`), with no container and no k3s. It could fit tiny hardware adapters (a serial or CAN reader on a Pi) where a k3s pod is heavy. Trade-off: a second way to run plugins next to k3s. Zeus's call; it reopens no decision.

## How an outside SDK becomes an integration (the recipe)

1. `onemind app scaffold <image|compose|repo>` or `onemind plugin init --kind app` makes the folder (CLI plan: [`docs/leap/dev/CLI.md`](../../leap/dev/CLI.md)).
2. Wrap the vendor SDK in a small service in that container. It posts readings to door 1 and answers tool calls on door 2.
3. Fill the manifest: provider and terms, hosts (default-deny egress), data class, emits, tools, secrets by name only.
4. `onemind plugin validate` and the app gate; then signed publish to the Market (E1, E9 signing and kill list).
5. Owner installs, sees the plan (hosts, devices, tools), approves. A later version that widens anything needs a new approval (`widens_grants`).

## Protocol adapters: the real "universal" layer

Instead of one connector per vendor, build one adapter per **protocol**. Most of the world speaks a handful:

| Adapter (Market app) | Covers | Door(s) | Notes |
|---|---|---|---|
| MQTT bridge | ESPHome, Zigbee2MQTT, Tasmota, most IoT | 1, 2 | Mosquitto is already in the Market |
| Webhook / HTTP poll | Most SaaS APIs | 1, 3 | Generic; config per provider |
| Modbus / OPC UA / Sparkplug B | PLCs, factories (Industrial, year 2) | 1, 2 | Researched (doc 09 P0-2, P0-4) |
| Matter / Home Assistant | Homes | 1, 2 | Home Assistant is in the Market |
| MCP server wrapper | Any tool that ships an MCP server | 2, 3 | See the flag below |
| ROS 2 bridge | Robots | 1, 2, 5 | **Parked**; read telemetry first, actuate never through this until RC1–RC7 pass |
| MAVLink bridge | Drones (PX4/ArduPilot) | 1, 2, 5 | **Parked**; the flight controller stays in charge |

## Robotics and physical AI: what changes

The contract already reserves the pieces: the event kind `robot` is reserved, `effect: actuate` is refused, and the motion lockout exists. When OneMind has a robot, the only new parts are:

1. **Allow `actuate` only as a bounded mission**, never a raw motor command: a signed plan bound to one target, a plan hash and an expiry, approved by the owner with step-up (lesson 17, §3).
2. **Robot identity and discovery** (RC1) through fabric join.
3. **The three-brain rule stays:** OneMind is the thinking brain; the body brain and the reflex chip (e-stop, failsafes) never depend on OneMind, the cloud or an approval.

So the robot path is an extension of the same five doors, not a second system.

## Flag for Zeus (not decided here)

[`docs/leap/dev/MCP.md`](../../leap/dev/MCP.md) says "agents calling outside MCP servers through OneMind" is **not planned** (token passthrough forbidden). A **wrapper app** for an outside MCP server (door 3 holds the credential, door 2 exposes its tools as typed, approved OneMind tools) would not pass tokens through, and it would fit D-022. That would make thousands of existing MCP integrations installable. This is a product choice for Zeus.

## What next (opinion, after M-LIVE)

1. **Connector kit (#657):** a template in Python, Go and TypeScript that already speaks door 1 and door 2, so wrapping an SDK takes an afternoon. Then the MQTT bridge as its first user (greenhouse P1, go-box C1).
2. **Webhook / HTTP generic adapter** for SaaS.
3. **"Integrations" screen** in the dashboard: connected accounts, bridges, health, pause/resume (CLI already has `onemind bridge list|status|resume`).
4. Robotics adapters stay parked until there is a robot.

---

## Check yourself
1. Why is "universal" a contract and not one big program?
2. Which door does a temperature sensor use, and which one would a "turn on pump" button use?
3. What stops an adapter from posting data as if it were another app?
4. What must change before a robot can move on OneMind's request, and what never changes?
