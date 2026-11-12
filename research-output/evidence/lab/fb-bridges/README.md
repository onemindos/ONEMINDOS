# Lab spike LAB-fb-bridges: an MQTT/Sparkplug B device and a Modbus TCP simulator as OneMind capabilities

**Status:** BLOCKED (product dependency), design pre-registered so it can run unchanged when the pieces exist.

**Serves:** fabric mission 02 §5 lab spike 4 and workstreams FB-3 (bridges), FB-5 (naming) and FB-6 (approval routing); contract §12.3 (`actuate` risk class).

> **Explain it like I'm the founder.** Sensors and factory controllers will never run OneMind. They talk MQTT or Modbus, and a OneMind node "translates" them. This test would show a fake MQTT sensor and a fake Modbus controller appearing in OneMind with proper names, readable at once, and a "switch it" request that waits for your approval. It cannot run yet, because the translator and the "actuate" approval type are not built; running it with stand-in scripts would test the scripts, not OneMind.

## 1. Why it is blocked (checked 2026-11-12 on `main` at `1c278f5`)

| Needed | State on `main` |
|---|---|
| A bridge (adapter) that maps MQTT/Sparkplug B and Modbus points to OneMind capabilities and events | Not present: no adapter module under `internal/`, `core/onemind_core/` or `apps/`; plugin socket E-points for device adapters are specified in brief 30 B8 but not built |
| An `actuate` action type that the gateway gates on approval | Contract §12.3 reserves the `actuate` risk class "lab-only until LT-VM-18 passes (reserved, no type in v1)" |
| The unified capability naming (FB-5 of this mission) | Proposed in `research-output/fabric/06-DATA-AND-NAMING.md`; not in the contract |

This task is research and documentation only; building those pieces is out of scope. The spike moves to build-path phase P2 (`research-output/fabric/13-BUILD-PATH.md`).

## 2. Pass / fail criteria (frozen now, to run later)

| ID | Test | PASS if |
|---|---|---|
| T0 | Pins | Mosquitto (Debian 13 package), a Sparkplug B edge-node simulator and a Modbus TCP simulator at pinned versions with recorded hashes, inside a disposable VM |
| T1 | Discovery and naming | Within 60 s of start, the Sparkplug device's metrics and the Modbus holding/input registers configured in the adapter appear as capabilities named per `06-DATA-AND-NAMING.md` (`<site>/<node>/<adapter>/<device>/<point>`), each with unit, type and `access: read` or `read_write` |
| T2 | Reads | 100 consecutive reads of each point match the simulator's value (Sparkplug: DDATA; Modbus: register value), with `observed_at` and source timestamps |
| T3 | Actuation is gated | A write to a `read_write` point by an agent principal creates an action of risk `actuate` in `awaiting_approval`; **no** write frame reaches the simulator (packet capture and simulator log) until the owner approves with step-up; after approval exactly one write arrives; a denied or expired request never writes |
| T4 | No bypass | The adapter's MQTT and Modbus credentials are not readable by apps or agents; a direct MQTT publish to the device's command topic by an app principal is refused by the broker ACL |

## 3. Fidelity limits

Simulators only (no real PLC, no OPC UA server, no safety PLC). Sparkplug B state handling (birth/death certificates, sequence numbers) is checked only as far as the simulator emits it.
