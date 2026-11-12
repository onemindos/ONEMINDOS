<!-- SPDX-License-Identifier: Apache-2.0 -->
# 06 · One namespace for every machine, sensor, capability and event (FB-5)

**Date:** 2026-11-12 · **Workstream:** FB-5 (Tier A; no lab could run, see `fb-bridges`) · **Status:** proposal for contract work (C12) and the adapter SDK; nothing here edits the contract.
**Serves requirements:** N-1, N-3, AI-1, AI-3, AI-7, UX-4, UX-6, UX-7, F-11, M-2, N-10

> **Explain it like I'm the founder.** If a thousand machines each name things their own way, neither you nor your AI can find anything. So every *thing* OneMind knows gets one address that reads like a postal address: **site → machine → device → what it can do**. "Home, the greenhouse Pi, soil sensor 3, read moisture." The bus subjects, the API, the Nodes app and the AI tools all use that same address. Industrial standards (OPC UA, the Asset Administration Shell, the W3C "Thing Description") are not replaced; OneMind *maps* to them, so a factory customer can export its machines in the format its tools expect.

## 1. The proposal

### 1.1 Identifiers (stable, never reused)

| Level | ID | Who assigns it | Example |
|---|---|---|---|
| Site | `site_id`: 12 hex from the site hub's CA public key hash; plus an owner-chosen name | site hub at first boot | `a41c09e2f7b3` ("home") |
| Node | `node_id`: unchanged, contract §1 (12 hex of `/etc/machine-id`) | `onemindd` | `3f9c2a1b7d4e` |
| Device (behind an adapter, or a robot part) | `device_id`: `<adapter>-<local id>`, lower-case `[a-z0-9-]`, unique per node; the adapter keeps a stable mapping table | the adapter, approved by the owner | `modbus-plc1`, `sparkplug-cell3-press`, `mavlink-1` |
| Capability | `<domain>.<kind>.<verb>` with an **effect** `read`, `write` or `actuate` (B12: `robot.arm.move`, `effect: actuate`) | adapter manifest; registered by the gateway (E6) | `climate.soil.moisture` (read), `irrigation.valve.open` (actuate) |

**Canonical reference** used by the API, MCP and audit: `<site_id>/<node_id>/<device_id>/<capability>`; the dashboard shows names, never raw IDs. No IP, MAC or serial appears in an identifier (contract §12.10).

### 1.2 Subjects: inside the existing grammar, no new top-level pattern

| What | Subject (site-local) | Rule |
|---|---|---|
| OS events and status | `onemind.node.<node_id>.{status,event.>,jobresult.>}` | contract §12.9, unchanged |
| Device attached / detached | `evt.sys.device.<device_id>.attached` | B12 step 2, unchanged |
| Telemetry from a device | `tel.<node_id>-<device_id>.<class>.<metric>` | the `{node}` token of `tel.{node}.{class}.{metric}` becomes the *producer*; for a device behind an adapter that is node + device |
| Semantic events | `evt.<domain>.<node_id>-<device_id>.<event>` | `evt.{domain}.{entity}.{event}` |
| Fused entity state | `ent.<type>.<node_id>-<device_id>.state` | `ent.{entity_type}.{entity_id}.state` |
| Commands | `cmd.<domain>.<node_id>-<device_id>.<action>` | **published only by the gateway**, after the action is approved; adapters subscribe; agents never publish `cmd.` directly |
| Across sites (fleet hub only) | `onemind.site.<site_id>.<original subject>` | added by the fleet hub's import mapping on the site's leaf link; stays inside the OS-owned `onemind.>` space (contract §12.9) |

The fleet-level prefix is a **proposal** (it adds a sub-pattern under `onemind.>`); it needs the contract owner's approval before anyone uses it (`14-…` ZF-05).

### 1.3 Capability descriptions: shaped like a W3C Thing Description

The W3C WoT Thing Description is a Recommendation (2023-12-05) that describes a thing's **properties**, **actions** and **events** in JSON-LD [C-FB5-001]. OneMind's capability registry already needs exactly those three (read → property, actuate/write → action, evt → event). Proposal: the adapter manifest uses OneMind's own JSON schema (contract-owned), and the gateway can **export** a valid TD per device. That buys interoperability without making a JSON-LD processor part of the core.

## 2. Digital-twin and asset models: adopt, map or avoid

| Model | What it is | Decision | Why (constraint fit) |
|---|---|---|---|
| W3C WoT TD 1.1 | device description: properties, actions, events [C-FB5-001] | **Map** (export) | Open W3C standard, small; matches the capability model |
| OPC UA information model | the address space of an OPC UA server (IEC 62541; standard text not opened: UNVERIFIED beyond the general description) | **Map** (read through an adapter built on open62541, MPL-2.0 [C-FB11-003]) | Factories already expose it; OneMind should read it, not re-model it |
| Asset Administration Shell (IDTA; Eclipse BaSyx) | industrial digital twin; specs CC-BY-4.0, BaSyx server SDK MIT [C-FB11-015] | **Map** (export for industrial buyers, year 2) | Required by some EU industrial buyers; too heavy for a home |
| Eclipse Ditto | a cloud-scale twin service (EPL-2.0, 3.9.8 [C-FB11-002]) | **Avoid** in core | Duplicates the gateway's registry and policy; a separate service with its own data store; footprint on a Pi UNVERIFIED |
| Sparkplug B | MQTT topic namespace + birth/death state [C-FB3-005] | **Map** (Sparkplug metrics → telemetry; NBIRTH/DBIRTH → device attached) | Common in industrial MQTT |
| Home Assistant entities | `domain.object_id` entities in HA | **Map** (HA adapter, D-B9.9) | HA stays an app (W8-R3) |
| Viam resource names | typed APIs like `rdk:component:arm` (C-TD-tier-c-robotics-055) | Pattern | Typed capability names that tools can list at runtime: same idea as `/v1/capabilities` |

## 3. Time series, retention and what syncs

| Data | Where it lives | Default retention | Syncs up to the site hub? | Syncs to the fleet hub? |
|---|---|---|---|---|
| Node heartbeat | not stored (last value wins) | — | live | summary only |
| Node events, job results | node outbox → site hub `ONEMIND_EVENTS` | outbox 7 days / 256 MiB; hub 7 days / 1 GiB (contract §12.9) | yes, store-and-forward | alerts and summaries |
| Audit | site hub `ONEMIND_AUDIT` | 1 year / 2 GiB, no delete (contract §12.9) | — | read-only mirror (proposal, `07-…`) |
| Device telemetry (high rate) | the node that owns the adapter | owner setting; default 24 h ring (proposal) | downsampled (proposal: 1/min) | no, unless the owner asks |
| Robot recordings (MCAP, video) | robot or site storage | owner setting | on demand | on demand (as Foxglove Edge Sites keep recordings on-site until imported, C-TD-tier-c-robotics-023) |
| Long-term metrics | an app (Prometheus-class) on the site | app setting | — | no |

The rule behind the table: **raw data stays where it was made; meaning travels.** Bandwidth, privacy (M-2) and offline operation (N-6) all point the same way.

## 4. What competitors do (constraint-matched)

| System | Naming | Constraint fit | Take |
|---|---|---|---|
| Azure IoT Operations | assets in the cloud Device Registry, organised by namespaces [C-FB11-009] | Low: cloud is the registry | OneMind's registry lives on the site hub |
| AWS Greengrass | things and thing groups in the AWS IoT registry [C-FB11-006] | Low (cloud) | Groups → OneMind labels |
| Sparkplug B | `spBv1.0/group/type/edge_node/device` [C-FB3-005] | High for industrial MQTT | Map |
| Viam | typed resource APIs, listable at runtime | Medium (AGPL, cloud) | Same runtime listing idea |
| KubeEdge / Akri | devices as Kubernetes custom resources [C-FB4-012, C-FB4-014] | Medium | The registry is the gateway's, not Kubernetes CRDs, because leaves have no Kubernetes |

## 5. Open items

- **ZF-05** approve the fleet prefix `onemind.site.<site_id>.` and the `<node_id>-<device_id>` producer token.
- Proposed **F-18**: "every device and capability has one stable address used by the bus, the API, MCP, audit and the UI".
- UNVERIFIED: NATS subject-mapping cost at the fleet hub with thousands of site imports (what would verify it: a simulated 1,000-leaf tree, build path P4).

## Glossary

| Term | Meaning |
|---|---|
| Capability | One thing a device can do or report, with an effect: read, write or actuate |
| Digital twin | A software copy of a machine's state and description |
| Thing Description | W3C's JSON-LD format for describing a device's properties, actions and events |
| Asset Administration Shell | The German/EU industrial standard for a machine's digital twin |
