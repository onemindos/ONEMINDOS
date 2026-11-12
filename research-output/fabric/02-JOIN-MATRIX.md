<!-- SPDX-License-Identifier: Apache-2.0 -->
# 02 · Join matrix (FB-1): how every kind of machine joins OneMind

**Date:** 2026-11-12 · **Workstream:** FB-1 (Tier A) · **Status:** complete for every class in brief §2; hardware rows are `blocked: founder-hardware` where only a real device can answer.
**Serves requirements:** N-1, N-2, N-3, N-4, N-5, N-7, P-6, P-7, P-9, F-3, F-6, F-11, F-14, UX-5, UX-6, UX-8, AI-7
**Claim IDs** resolve in `evidence/claims/FB*.csv` (this folder) and in `../evidence/claims/*.csv` (mission 01 and lab ledgers).

> **Explain it like I'm the founder.** Every machine you own ends up in one of three places. **Machines that run OneMind** (your mini PC, a Pi, a cloud server, a robot's computer) get the OneMind agent and talk on the OneMind bus. **Machines that can't** (a temperature sensor, an ESP32, a factory controller) never run OneMind; a nearby OneMind machine "speaks their language" and translates. **Screens** (phone, laptop, headset) are windows into all of it; they are not part of the machinery. What differs between classes is only *how* a machine joins and *who looks after its updates*. Everything after that (names, approvals, alerts, backups, the Nodes list) is the same.

## 1. The answer in one table

Legend: **image** = OneMind's own read-only image (Debian 13 base, D-007; RAUC A/B). **agent** = `onemindd` + a local NATS leaf (+ k3s agent when the machine is a worker). **adapter** = a OneMind plugin on a nearby node that bridges a protocol. **client** = the one web app, wrapped per platform.

| Class | What runs on it | Role(s) | Discovered by | Enrolled by | Identity | Updated by | Observed by | Controlled by | Min. hardware | Arch | Hypothesis (brief §2) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1. Mini PC, home server, hub box, Pi 5** | image | hub, worker or leaf | mDNS on the LAN (`onemind.local`), or the join QR | owner-approved join: ticket + pairing code (FABRIC §4); FDO for OneMind-sold boxes (§3) | node Ed25519 key + box-CA cert + NATS nkey (FABRIC §3) | RAUC A/B bundle, health-gated (mission 01) | heartbeat every 10 s on its leaf | gateway jobs (signed) | worker: ≥ 4 GB + SSD; leaf: 1-2 GB | amd64, arm64 | **Confirmed** |
| **2a. Cloud VM, OneMind image** | image | hub (cloud hub) or worker | none needed: the owner starts it with a join code in cloud-init | same ticket, delivered as user data (late binding, as Flight Control does [C-FB11-004]) | same | RAUC (if the cloud boots a custom image) | same | same | 2 vCPU / 4 GB | amd64, arm64 | **Confirmed, with a caveat**: image upload per cloud; UNVERIFIED which clouds boot a RAUC A/B image unchanged |
| **2b. Cloud VM, stock Ubuntu/Debian** | agent on the stock OS ("installer mode") | worker or leaf | same | same | same | signed packages for `onemindd`, NATS, k3s; **no OS rollback**, labelled in the UI | same | same | 2 vCPU / 2 GB (leaf) | amd64, arm64 | **Confirmed**; spike `fb-installer-mode` BLOCKED here (§5) |
| **2c. Managed Kubernetes (DOKS/EKS/GKE)** | OneMind gateway, NATS and apps as workloads; **no host agent** | a *site* (cluster), not a node | owner adds it as a site | site enrolment (agent-initiated, Fleet pattern [C-FB4-003, C-FB4-006]) | site certificate; per-site NATS leaf credentials | the provider upgrades nodes; OneMind upgrades its workloads | site summary from its gateway | gateway revisions only (no host jobs) | provider-defined | provider-defined | **Changed**: a managed cluster joins as a site with no host control, not as nodes (§4) |
| **3. Company or GPU server OneMind does not own** | agent on the unmodified OS | worker or leaf (GPU worker) | owner or admin runs the join | same ticket + approval; optionally the company's own PKI later | same | the company patches the OS; OneMind updates only its packages | same | same, minus host jobs the admin disallows | as class 2b | amd64, arm64 | **Confirmed** |
| **4. Robot or drone on Jetson** | NVIDIA L4T (Jetson Linux) + agent; k3s **agent only** (mission 01) | leaf (default) or worker | join QR on the robot's screen or a sticker | same ticket + approval; FDO voucher for OneMind-built robots | same; TPM/fTPM sealing later | NVIDIA image-based OTA (A/B) on L4T (mission 01); OneMind packages on top | heartbeat + robot telemetry through its leaf | gateway jobs; **motion only through `actuate` approval** | Orin Nano 8 GB and up (supply to 2032 [C-FB1-001]) | arm64 | **Confirmed for L4T + agent; Yocto meta-tegra image stays "later"** |
| **5. Vehicle (car, boat, UGV, aircraft)** | a **companion computer** running class 4 or class 1 | leaf | as class 4 | as class 4 | as class 4 | as class 4; **the safety controller is never updated by OneMind** | MAVLink/CAN read through an adapter on the companion | mission-level requests through `actuate` approval; brakes, steering and flight control stay on their own controller | as class 4 | arm64, amd64 | **Confirmed** (§6; `10-VEHICLES-AND-DRONES.md`) |
| **6. Sensors, MCUs, PLCs** (ESP32, Zigbee, Modbus, OPC UA, MQTT, CAN) | **nothing from OneMind**; their own firmware | none (they are *devices* behind an adapter) | by the adapter: MQTT/Sparkplug births, Modbus scan lists, OPC UA browse, Zigbee coordinator, Matter commissioning | owner approves the *adapter's* device list; Matter devices through a Matter controller app | the adapter's mapping (§3 of `06-…`); device certificates where the protocol has them (Matter DAC [C-FB2-004]) | MCUs: MCUboot / ESP-IDF OTA through the adapter, signed, test-then-confirm [C-FB8-001, C-FB8-002]; **PLCs: never automatically** | adapter publishes telemetry into the grammar | adapter writes only through `actuate` approval | n/a | n/a | **Confirmed** |
| **7. Phone, tablet, laptop, desktop, XR** | the client (one web app in native shells); the official Tailscale app for remote reach | client; a phone can also be a TAK EUD | the app finds the hub by mDNS or QR | owner or household sign-in (passkeys, Kanidm BD-03) | person identity, not node identity | app stores / the shell's updater | presence only (no heartbeat as a node) | approves actions; never actuates directly | any current phone or browser | any | **Confirmed**; phones are **not** k3s nodes (REC-W14-09) |

## 2. Why the roles matter more than the device type

The same Pi 5 can be a **hub** (k3s server, the box's NATS, gateway), a **worker** (k3s agent) or a **leaf** (no k3s, just `onemindd` + a NATS leaf). FABRIC.md §2 defines the three roles; this mission adds the rule for *which* role a class gets by default:

| If the machine is… | Default role | Why |
|---|---|---|
| always on, ≥ 4 GB, SSD, same site as the hub | worker | k3s needs ≥ 4 GB + SSD to be safe (mission 01) |
| small (< 4 GB), on battery, or often offline | leaf | a leaf costs about 60 MiB and under 0.5 % of a core, and keeps its events through a 30-minute outage [C-LAB-fb3-mesh-nat-006, -011] |
| at **another site** (another house, a field kit, a vehicle) | leaf, or the hub of its own site | a k3s agent at another site loses its control plane whenever the WAN drops; k3s says "all servers should be in the same location" [C-FB4-001] (`05-…` §2) |
| a cloud VM that is always online | worker of the home cluster, or a cloud site | the only cross-site worker that is reasonable (always connected); otherwise a site of its own |
| a robot or vehicle computer | leaf (k3s agent optional, never server) | mission 01: agent-only on robots; real-time and safety stay on their own controllers |

## 3. Evidence per class (what was checked, what fails today)

**Class 1, image nodes.** The image, RAUC and the health gate are mission 01's decisions (D-007; `01` rev. 4.1) and are not reopened. The join and identity design is `docs/architecture/FABRIC.md` §3–§4. What fails today: the join flow (CORE-FABRIC-1) is not built, `install.sh --role node` still uses a long-lived token (`docs/leap/core/FABRIC.md` §2), and no real Pi 5 has run the stack (`blocked: founder-hardware`, LT-PI5 tests in `22-…`).

**Class 2, cloud.** Three modes, decided by who owns the operating system:
- **2a (image as a cloud VM).** Works where the cloud boots a custom disk image. Whether RAUC's A/B layout survives each provider's image import is UNVERIFIED (what would verify it: import the image on DigitalOcean and one hyperscaler and run the mission 01 gate test).
- **2b (installer mode on stock Ubuntu/Debian).** The pattern every fleet product uses for machines it does not image: Flight Control injects its enrollment config through cloud-init ("late binding") [C-FB11-004]; Greengrass runs its core software on stock Linux [C-FB11-006]; Viam's agent installs with a one-line script on Debian, Ubuntu, Raspberry Pi OS and RHEL-family [C-TD-tier-c-robotics-050, -057]. OneMind's difference is that the join still needs the owner's approval with a pairing code.
- **2c (managed Kubernetes).** OneMind cannot run `onemindd` on nodes it does not own (no host access, no RAUC, no host jobs). Mission 01 found the founder's DOKS conversion is 13 dependencies, not three (`05-…` P0-10, C-W4-063). The fabric answer: a managed cluster joins **as a site**, the way Fleet and Open Cluster Management register a whole cluster through an agent that dials the hub [C-FB4-003, C-FB4-009], and is shown in the Nodes view as one site with its own node list read from its Kubernetes API.

**Class 3, other people's servers.** Same as 2b. The honest label is "installer mode: OneMind updates its own parts; the operating system belongs to <owner>". Host jobs (backup of host paths, OS rollback) are refused on these nodes unless the admin grants them.

**Class 4, Jetson robots and drones.** L4T + agent is mission 01's decision (RR-01: Jetson software ends before the robot). NVIDIA sells the Orin modules through January 2032 and gives at least 8 months' notice of last shipment [C-FB1-001]; software support is shorter and per JetPack branch (mission 01, C-REF-W7L-001). balena's Jetson Orin OS is built from OE4T meta-tegra, which is the documented exit if L4T support ends (C-TD-balenaos-042). Competitor agents install on the stock robot OS too: Formant's agent on Ubuntu 22.04/24.04 with ROS 2 (C-TD-tier-c-robotics-002), Viam's on Jetson AGX/Orin Nano (C-TD-tier-c-robotics-057). What fails today: no Jetson has run `onemindd` (`blocked: founder-hardware`).

**Class 5, vehicles.** A companion computer only. PX4's offboard mode warns that generic offboard control "bypass[es] all internal PX4 control loops and should be used with great care", and needs a 2 Hz proof-of-life stream or it triggers its own failsafe [C-FB9-001]. Auterion's Skynode, a shipping product, splits exactly this way: PX4 on the flight controller, a managed OS with sandboxed apps on the mission computer [C-FB9-005]. Details and regulation: `10-VEHICLES-AND-DRONES.md`.

**Class 6, sensors, MCUs and PLCs.** They never run OneMind. AWS Greengrass draws the same line: client devices "connect to and communicate with a Greengrass core device over MQTT" [C-FB11-006]; Akri exposes "leaf devices" that are "too small to run Kubernetes themselves" as resources of a cluster [C-FB4-012]. MCUs update through their own bootloaders (MCUboot test-then-confirm with revert, ESP-IDF pending-verify rollback and one-way eFuse anti-rollback) [C-FB8-001, C-FB8-002]. PLCs are never auto-updated: OT guidance puts their "unique performance, reliability, and safety requirements" first [C-FB8-003]; OneMind reads their firmware version and raises an advisory, nothing more.

**Class 7, clients.** Builds on research 12 and 15 without change: one web app, native shells, phone not a k3s node (REC-W11-01, REC-W11-09, REC-W14-09). A phone running ATAK is a TAK end-user device that reaches OneMind through TAK Server, not as a OneMind node (research 09, W8-R8). See `11-CLIENTS.md`.

## 4. What competitors do (constraint-matched)

| Product | Join model | Runs on the device | Constraint fit for OneMind | Take |
|---|---|---|---|---|
| Flight Control (Red Hat-led, Apache-2.0) | agent calls home, enrollment request approved by an operator (`flightctl approve`), TPM-bound key optional [C-FB11-004] | agent on bootc/RHEL-family image or package mode | **High** on pattern (owner approval, pull, TPM), low on OS (RHEL family) | Approval of an enrollment request is the same idea as FABRIC's `node.join`; confirms the design |
| balena | fleet provisioning key in `config.json`, device registers itself (C-TD-balenaos-035) | balenaOS image | Medium: one shared key per fleet, no per-device approval | Do **not** copy the shared key; copy "the image knows its fleet" for OneMind-sold boxes via FDO |
| Viam | one-line installer embedding a machine API key (C-TD-tier-c-robotics-050) | `viam-agent` (AGPL-3.0) on stock OS | Low (cloud account, AGPL) | Installer mode is normal; the key-in-a-URL pattern is not |
| AWS Greengrass | core device = AWS IoT thing; client devices connect over MQTT [C-FB11-006] | nucleus on stock Linux | Low (cloud-bound), high on the core/client split | The core/client split is OneMind's node/adapter split |
| Akri (CNCF Sandbox) | discovers leaf devices and advertises them as cluster resources [C-FB4-012] | nothing on the device | Medium | Pattern for adapters advertising capabilities; not adopted as a dependency (`05-…`) |
| Olares | `olares-cli node add/join`, k3s workers (FABRIC §4.2) | Olares on stock Ubuntu/Debian | Medium (AGPL, home focus) | A first-class CLI join, as OneMind already plans |
| Home Assistant | no multi-machine model; remote access via Home Assistant Cloud or a VPN such as Tailscale [C-FB11-014] | HAOS or HA Container | Low for fabric | OneMind runs HA as an app on a node (W8-R3) |

## 5. Lab status for this workstream

| Spike | Result |
|---|---|
| fb3-mesh-nat (hub + leaves across two NATs) | **PASS** (`../evidence/lab/fb3-mesh-nat/`): one-time keys, direct path through both NATs, relay fallback, 1,200/1,200 events after a 30-minute outage, about 60 MiB per leaf |
| fb2-fdo-enroll (zero-touch enrollment) | **PASS** (`../evidence/lab/fb2-fdo-enroll/`); see `03-IDENTITY-AND-ENROLLMENT.md` |
| fb4-fleet-rings (multi-cluster) | see `05-MULTI-CLUSTER-AND-FLEET.md` |
| fb-installer-mode (stock Ubuntu + stock Debian + image node) | **BLOCKED**: needs three machines at once (this run may start one VM) and the owner-approved join (CORE-FABRIC-1), which is not built. Pre-registered for CORE-NET-9 (`../evidence/lab/fb-installer-mode/`) |
| fb-bridges (MQTT/Sparkplug + Modbus as capabilities) | **BLOCKED**: no adapter and no `actuate` action type exist yet (`../evidence/lab/fb-bridges/`) |

## 6. Open items from this file (in `14-OPEN-QUESTIONS-FOR-ZEUS.md`)

- **ZF-02** cross-site workers: allow only always-online cloud workers; everything else is a site or a leaf.
- **ZF-06** managed Kubernetes as a site (no host control) versus not supporting it.
- Proposed requirement **F-16** (join matrix as an acceptance list: every class in §1 must have a passing join test before it is called "supported").

## Glossary

| Term | Meaning |
|---|---|
| Installer mode | OneMind installed on an operating system it did not build; no OS rollback |
| Leaf | A OneMind machine without Kubernetes: the agent plus a small local NATS server that buffers |
| Site | One location with its own hub (one k3s cluster or a single box) |
| Adapter | A OneMind plugin on a node that translates a device protocol (MQTT, Modbus, OPC UA, CAN, MAVLink) into OneMind capabilities |
| Late binding | The machine learns who owns it at first boot, not at the factory |
