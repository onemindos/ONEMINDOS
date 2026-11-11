# 🧭 RESEARCH MISSION 02: The One Mind Fabric: how every machine joins one OneMind

> **You are the research lead for mission 02.** This file is your complete, one-shot brief. **You cannot ask the founder anything during this run.** Follow every rule in [`RESEARCH-MISSION.md`](RESEARCH-MISSION.md) §2–§3 (cite primary sources, archive load-bearing ones, pin code citations to a SHA, label UNVERIFIED, adversarial refuters, no secrets or personal data: **this repo is public**). Everything you produce goes in `research-output/fabric/`. Being wrong costs more than tokens.

**Commissioned by:** Zeus Delacruz, founder · **Written:** 2026-11-11 · **Repo:** https://github.com/onemindos/ONEMINDOS (public). Base branch `main`. Never force-push.
**Builds on:** mission 01's output on branch `research/ultracode-foundation` (PR #1). Read it there if PR #1 is not merged yet. Founder notes: [`docs/learning/03`–`05`](docs/learning/) (PR #2).
**Reviewer:** Zeus, who is learning OS and platform engineering. Every file opens with an "Explain it like I'm the founder" box and defines its terms.

---

## 0. The mission in one paragraph

The founder's thesis: **"create the connections of the world and make it into one mind."** OneMind is one unified layer across **every kind of machine**: cloud servers, company servers, PCs, home hubs, Raspberry Pis, robots, drones, vehicles, sensors and industrial controllers. **Phones, laptops and XR headsets are the clients** to see and control all of it. Mission 01 decided the *floor*: OneMind's own read-only image with A/B updates (RAUC), k3s, NATS, restic, plugin sockets E1–E10, and a capability gateway with human approval for physical actions. **Mission 02 designs and evidences the *fabric*:** exactly how each class of machine **joins, is identified, talks, is updated, is observed, is controlled by humans and AI, and stays safe**, including offline and across clouds. Output: a researched architecture, a per-device "join matrix", competitor teardowns of fleet and edge platforms, lab spikes, and a **build path** (phased, with gates) that plugs into the 180-day plan and the build brief (`30-…`) **without reopening mission 01's decisions**.

**North star:** *"I plug in or power on any machine → it appears in OneMind on my phone → I (or my AI, with my approval) can use it."*

---

## 1. Read first, in this order

1. `research-output/00-EXECUTIVE-SUMMARY.md` and `01-FOUNDATION-DECISION.md` §1, §4 (rev. 4.1)
2. `research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md` §4 (frozen decisions), B6 (k3s), B8 (E1–E10), B9 (Core: identity, gateway, ledger), B11 (dashboard), B12 (robot onboarding)
3. `research-output/05-…` (k3s, DOKS conversion, NVIDIA), `08-…` (robotics, drones, real time, ROS 2/Zenoh), `09-…` (IoT/IIoT, mesh, off-grid, TAK), `10-…` (AI capability layer), `11-…` (hardware line), `12-…` (dashboard, clients, XR, multi-node "Nodes app"), `15-…` (phones and field devices), `29-…` (plugin ecosystem)
4. `research-output/02-competitors/MATRIX.md`, plus `olares.md`, `robotics-formant.md`, `robotics-viam.md`, `robotics-foxglove.md`, `robotics-balena.md`
5. `docs/REQUIREMENTS.md` (especially F-1…F-15, N-*, AI-*, UX-*) and `docs/learning/04-install-modes-and-cloud.md`, `05-official-route-and-why-not-fedora-arch.md`

---

## 2. Founder framing to preserve (do not dilute)

- **One mind, many bodies.** The same management layer, AI gateway, Market, alerts, backups and messaging everywhere. Only *how a machine joins* differs.
- **Machine classes and their expected join method.** These are **hypotheses to verify or overturn with evidence**:

| Class | Hypothesis |
|---|---|
| Mini PCs, hubs, home servers, Pi 5 | OneMind image (Debian 13 leg / base per Z-38) |
| Cloud servers | (1) OneMind image as a cloud VM; (2) install on the cloud's stock Ubuntu/Debian; (3) on managed Kubernetes (DOKS/EKS/GKE) |
| Company and GPU servers OneMind does not own | Install on top of their unmodified OS |
| Robots and drones (Jetson) | NVIDIA L4T + OneMind agent (k3s agent + NATS); later a OneMind Jetson image via Yocto meta-tegra |
| Vehicles | A OneMind companion computer; brakes, steering and flight control stay on their own safety controller |
| Sensors, MCUs, PLCs (ESP32, Zigbee, Modbus, OPC UA, MQTT) | Connect *to* a OneMind node; never run the OS |
| Phones, tablets, laptops, desktops, XR | Clients (one web app wrapped per platform); phones may also be field sensors and nodes (TAK/EUD) |

- **Safety line (from mission 01, non-negotiable):** AI never actuates without gateway-enforced human approval; hard real time and safety stay on dedicated controllers.
- **Sovereignty:** works offline and on a LAN with no OneMind cloud; the cloud is an optional node, not a dependency.

---

## 3. Workstreams (cover ALL; Tier A = primary sources + lab, Tier B = primary sources)

| ID | Workstream | Tier | Core questions |
|---|---|---|---|
| **FB-1** | **Join matrix** | A | For every class in §2: how it is discovered, enrolled, identified, updated, observed and controlled; what runs on it (image / agent / adapter / nothing); minimum hardware; supported architectures; what fails today. One row per class, with evidence |
| **FB-2** | **Identity and enrollment** | A | Zero-touch and QR onboarding: FIDO Device Onboard (FDO), TPM attestation, SPIFFE/SPIRE-style workload identity, Kanidm (build default BD-03), device certificates; how a phone approves a new machine; how identity survives reflash and transfer of ownership; revocation |
| **FB-3** | **Connectivity and topology** | A | NATS leaf nodes, gateways and JetStream across home ⇄ cloud ⇄ field; Tailscale vs self-hosted Headscale vs WireGuard; NAT traversal with no open ports; mesh and off-grid (09); Zenoh for ROS 2; the bridges MQTT/Sparkplug B, OPC UA, Modbus, CAN, MAVLink. **Which is the one bus, and which are bridges?** |
| **FB-4** | **Multi-cluster and fleet control** | A | One control plane across many k3s clusters and single boxes: compare k3s multi-cluster patterns, Rancher Fleet, Argo CD ApplicationSets, Open Cluster Management, KubeEdge, Akri (leaf devices), Cluster API. **Is OneMind one big cluster, many clusters with a hub, or both?** Scale targets: 1 → 10 → 1,000 → 100,000 nodes |
| **FB-5** | **Unified data and naming model** | A | One namespace for every machine, sensor, capability and event (extend the `evt.{domain}.{entity}.{event}` grammar from B12). Digital-twin and asset models (OPC UA information model, Eclipse Ditto, Asset Administration Shell): adopt, map or avoid? Time series, retention, what stays local vs syncs |
| **FB-6** | **AI over the fabric** | A | How MCP/CLI/API/MHS expose *all* nodes through one gateway without one giant attack surface: capability tokens, per-node policy, approval routing to the right human's phone, audit across nodes, prompt-injection containment (RR-06) |
| **FB-7** | **Offline, partition and conflict** | A | What every class does when the hub or internet is gone; store-and-forward (lab: NATS leaf 600/600 passed in 01); conflict rules when a field kit rejoins; bounded autonomy for robots and vehicles while disconnected |
| **FB-8** | **Updates across classes** | A | One release contract: image (RAUC), Jetson (NVIDIA A/B), installer mode (signed packages, no OS rollback), MCU firmware (OTA via adapter: MCUboot / ESP-IDF OTA?), PLCs (usually *never* auto-update). Staged rollouts and rings across thousands of nodes; CRA obligations per class |
| **FB-9** | **Vehicles and drones** | B | The companion-computer pattern (PX4/ArduPilot + MAVLink, CAN, ROS 2), what the companion may and may not do, the relevant safety and regulatory standards per region (identify them; don't summarise beyond sources), and real products using this split |
| **FB-10** | **Clients** | B | Phone, desktop, XR as clients; phone as a sensor/EUD node (ATAK); push alert routing per owner and role; one view of thousands of nodes (Nodes app, maps, infrastructure graph). Builds on 12 and 15 |
| **FB-11** | **Competitor and adjacent teardowns** | A/B | See §4 |
| **FB-12** | **Build path** | A | Phased plan with gates from "one cloud hub + one Pi 5" to "multi-site fleet with robots and vehicles", mapped to `20-PLAN-180-DAYS.md` and `21-ROADMAP…`, plus additions or amendments to `30-…` as *proposals* only |

---

## 4. Competitors and adjacent systems to study (verify each; none of these is a claim yet)

Copy patterns, never code from licences that aren't Apache-compatible. For each, record its join model, identity, transport, offline behaviour, update model, AI access, licence, scale evidence, pricing, and "fit for OneMind" with constraint matching.

| Group | Candidates |
|---|---|
| **Fleet, robotics and physical AI** | Formant, Viam, Foxglove, balena (already in 02; deepen on the join and fleet model), NVIDIA's fleet and robotics stack (Isaac, Jetson fleet tooling: identify what exists), Anduril Lattice (public docs only), Open-RMF |
| **Industrial edge** | Siemens Industrial Edge, Litmus Edge, Red Hat Device Edge / MicroShift + ACM, AWS IoT Greengrass, Azure IoT Operations/Edge, Eclipse ioFog/Kura (verify status) |
| **Kubernetes edge and multi-cluster** | KubeEdge, OpenYurt, Akri, Rancher Fleet, Open Cluster Management, Spectro Cloud Palette (Kairos), Talos Omni |
| **Home and self-hosted** | Home Assistant (multi-site and remote), Olares multi-node, Umbrel (none: confirm), Tailscale as a "fabric" product |
| **Protocols and foundations** | NATS/Synadia, Eclipse Zenoh, MQTT/Sparkplug B, OPC UA, FDO (FIDO Alliance), SPIFFE, Matter/Thread, MAVLink |

---

## 5. Mandatory lab spikes (VMs, Tier A; pre-register pass/fail before running, as in mission 01 `evidence/lab/PREREGISTRATION.md`)

1. **Hub + leaf across a NAT:** a cloud-side NATS hub and two "home" VMs behind separate NATs, with no inbound ports; leaf reconnect, buffering and replay after a 30-minute partition.
2. **Multi-cluster control:** one hub managing two k3s clusters and one single-node box with the chosen fleet tool; app rollout in rings, and rollback.
3. **Zero-touch enrollment:** FDO (or the best candidate from FB-2) onboarding a fresh VM to the hub, approved from a simulated phone step; then revoke it.
4. **Bridges:** an MQTT/Sparkplug B device and a Modbus TCP simulator surfaced as OneMind capabilities with the unified naming; read only, then an `actuate` request blocked until approval.
5. **Installer-mode node:** OneMind agent on a stock Ubuntu cloud VM and a stock Debian VM, joining the same hub as an image node, so both show in one Nodes view.

Lab rules: disposable VMs only; no real devices, no vendor accounts, no live cluster; mask any VM-internal addresses and host paths before committing.

---

## 6. Deliverables (all in `research-output/fabric/`)

| File | Content |
|---|---|
| `00-FABRIC-SUMMARY.md` | The answer in plain language, the top findings and the decisions for Zeus |
| `01-FABRIC-ARCHITECTURE.md` | The architecture with diagrams (Mermaid): layers, the bus, identity, gateway, clients, cloud and hub topology at 1 / 1k / 100k nodes |
| `02-JOIN-MATRIX.md` | FB-1: one row per machine class, with evidence |
| `03-…` to `11-…` | One file per workstream FB-2…FB-10 |
| `12-COMPETITORS.md` + `competitors/*.md` | FB-11 teardowns and a matrix |
| `13-BUILD-PATH.md` | FB-12: phases, gates, mapping to `20`/`21`, and proposed amendments to `30` (as proposals) |
| `14-OPEN-QUESTIONS-FOR-ZEUS.md` | IDs **ZF-01…**, each with options, a recommendation and what it blocks |
| `evidence/` | Claims ledger (`claims/FB-*.csv`, same columns as mission 01), sources, lab logs, refuters |

**Every recommendation maps to requirement IDs** in `docs/REQUIREMENTS.md`. Propose new IDs (F-16…) only in `14-…`; do not edit `docs/`.

---

## 7. Rules specific to this mission

1. **Do not reopen mission 01's decisions** (base OS, RAUC, k3s, restic, E1–E10). If evidence contradicts one, write it up as a flagged finding with a refuter, not a change.
2. **Real-world first:** every pattern cites what a shipping product actually does (docs or code at SHA), with constraint matching (team size, licence, hardware, scale).
3. **No guessing.** Unknown means UNVERIFIED, plus what would verify it.
4. **Safety:** no design in which AI actuates without human approval, or in which safety functions move off their dedicated controllers.
5. **Public repo:** no secrets, private IPs, personal data or host paths. Run gitleaks before every push.

---

## 8. Git workflow

1. Branch **`research/one-mind-fabric`** from `main`. If PR #1 isn't merged yet, read mission 01 from `research/ultracode-foundation`.
2. Commit per workstream (`research(fabric): …`), and push at the end of every wave so no work lives only on one machine.
3. Open **one** PR to `main`, *"Research: One Mind fabric"*, as a draft. Mark it ready only when §9 is met. Never force-push.

## 9. Definition of done

- Every workstream FB-1…FB-12 is delivered, or explicitly marked with what remains.
- The join matrix covers every class in §2 with evidence.
- All five lab spikes have run, or are documented as blocked with the reason.
- At least three refuters on each P0 conclusion; a completeness-critic pass finds no new S1/S2 gap.
- The build path maps onto `20`/`21`, with gates and founder kits for anything needing hardware.
- `14-OPEN-QUESTIONS-FOR-ZEUS.md` is complete; gitleaks is clean; the PR is open.
