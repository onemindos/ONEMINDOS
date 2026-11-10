# OneMind OS: IoT and Industrial IoT (IIoT) Landscape and Requirements

Date: 2026-11-10. Scope: what OneMind OS must support to stay credible for IoT and IIoT over 5 to 10 years (greenhouses, farms, water and energy, warehouses, factories, public safety).

**Method and evidence rules**
- Every claim is tagged with a source number `[S#]` from the Sources section. Sources were opened via WebFetch or WebSearch on 2026-11-10.
- WebFetch returns a small-model summary of the page, not raw text. Figures worth betting on (dates, levels, versions) should be re-read on the cited page before they go into a contract, a datasheet or a compliance claim.
- `(search)` = the fact came from a search-result snippet or answer, not from a page I opened. `(secondary)` = press, blog or vendor-reseller text.
- **UNVERIFIED** = I could not confirm it from a source I opened. Items from my own background knowledge are labelled "background, UNVERIFIED". Nothing UNVERIFIED should be treated as fact.
- This file builds on `docs/ADR-001-foundation.md` (Debian 13 core, Rugix A/B, k3s plus RKE2, NATS) and `research/platform/base-os-and-orchestration.md`. A separate Fedora IoT / Red Hat deep dive is referenced by ADR-001 and is not re-done here.

---

## 0. Executive summary

1. **OneMind should supervise, not control.** Hard real-time loops (motion, interlocks, safety) belong on PLCs, RTOS/MCU controllers, and certified safety controllers. Linux (PREEMPT_RT is mainline since 6.12 on x86, arm64, RISC-V [S1]) is good for soft real-time and supervision, and can run a soft PLC (Schneider runs a Linux soft dPAC [S34]) but that is a product decision with certification consequences, not a default.
2. **The integration layer is already decided by the industry:** OPC UA for information models and client/server, MQTT plus Sparkplug B for the edge-to-plant-to-cloud data plane (Sparkplug 3.0 = ISO/IEC 20237, equivalence stated by Eclipse [S3]), Modbus and BACnet for legacy and building gear, fieldbus (EtherCAT, PROFINET, EtherNet/IP, CANopen, IO-Link) stays below the PLC. The commercial platforms (Azure IoT Operations, Litmus, HighByte, Ignition) converge on an MQTT-based Unified Namespace [S21, S35, S36].
3. **NATS and MQTT 5 do not line up.** NATS server's MQTT listener implements MQTT 3.1.1 only and rejects MQTT 5 clients [S37]. OneMind needs an explicit answer (see section 9).
4. **Base OS:** keep Debian 13 plus Rugix as the default image for the consumer, prosumer and light-industrial tiers. For regulated industrial deployments, add a hardened "Industrial" profile and plan a second track on a Linux with 10 to 15 year vendor-backed support and a 62443-4-2 precedent: Debian-based CIP (10-year SLTS kernels, 62443-4-1 and 4-2 assessments reported) [S10, S11], or RHEL image mode / Fedora bootc lineage (RHEL 9.6 and MicroShift 4.21 certified SL-C 2 [S9]). No OS can be "62443-4-2 certified" in the abstract: certification attaches to a product (device plus OS plus configuration) [S9, S12, S13].
5. **Regulation is now live:** EU CRA reporting duties (24 h early warning, 72 h notification) apply since 2026-09-11, remaining obligations from 2027-12-11 [S14, S15]. SBOM, vulnerability handling and a documented support period are not optional for devices OneMind sells or ships.
6. **Scale:** ADR-001 notes 3 k3s servers with embedded etcd handle about 1,200 agents (from E2, not re-verified here). A 10k-device fleet is therefore not "one cluster". It is many site clusters plus a hub-and-spoke control plane (NATS leaf nodes, OTA fleet manager, onboarding service).

---

## 1. Protocols and data models

### 1.1 Where each is used and what OneMind needs

| Protocol / standard | What it is (verified) | Where used | OneMind need | Source |
|---|---|---|---|---|
| **OPC UA** (IEC 62541) | Client/server plus PubSub (Part 14, current doc release 1.05.06, 2025-10-22). Information models via companion specs. | Machines, PLCs, MES/SCADA integration, vendor-neutral semantic model | Client and server in the platform; Part 14 PubSub over MQTT for uplink | S4, S5 |
| OPC UA PubSub / over MQTT | open62541 marks UADP and JSON NetworkMessage encodings and the MQTT transport as supported | Machine-to-cloud, broker-based UNS | Prefer JSON-over-MQTT for IT-friendliness; UADP for TSN/UDP later | S6 |
| OPC UA companion specs | OPC Foundation runs Joint Working Groups that create them (the page I opened names no specific domains) | Machinery, robotics, packaging etc. (domain list UNVERIFIED from page) | Model-loader support (NodeSet import) | S5, UNVERIFIED list |
| **MQTT 5.0** | OASIS Standard 2019-03-07. Adds shared subscriptions, user properties, session expiry, reason codes | Telemetry transport everywhere | Need an MQTT 5-capable broker | S16 |
| **Sparkplug B (Eclipse Sparkplug 3.0)** | Stateful semantics on MQTT: birth/death certificates, metrics with templates, datasets, aliases, historical data. 3.0 is ISO/IEC 20237 and equivalent to the Eclipse spec; 4.0 in progress | Ignition ecosystem, SCADA-to-IT, UNS | Bridge to NATS; Tahu reference libs | S2, S3, S7 |
| **Modbus TCP/RTU** | Modbus application protocol V1.1b3 (2012-04-26); Modbus/TCP Security spec v3.6 (2021-07-30) layers TLS with X.509 on port 802 | Meters, drives, sensors, legacy PLCs | Driver (PLC4X or Telegraf); secure-by-default policy because base Modbus has no auth | S17 (search) |
| **BACnet** | ANSI/ASHRAE 135-2024 published 2024-12-31; protocol-revision 30 adds an energy services interface | HVAC and building automation, greenhouses climate gear | BACnet/IP client; BACnet/SC not confirmed on the page I opened | S18 |
| **EtherCAT** | IEC 61158 protocol, IEC 61784-3 safety; targets cycles of 100 us or less, jitter of 1 us or less via distributed clocks; master needs only a standard Ethernet port | Motion, high-speed I/O | Out of scope for Linux supervision. Master on a PLC/IPC if needed | S19 |
| **PROFINET** | PI standard; cycle times to 31.25 us with fast forwarding etc.; security classes; OPC UA as an information model | Siemens-centric plants | Read via OPC UA or gateway, do not run RT PROFINET controller | S20 |
| **EtherNet/IP (CIP)** | ODVA. TCP/IP plus UDP; CIP covers control, safety, security, energy; CIP Security said to help with IEC 62443 and the CRA; supports DLR topology | Rockwell-centric plants (Rockwell membership in Margo noted in S8) | Read via PLC4X or vendor OPC UA; no RT role | S21b |
| **CAN / CANopen** | Not confirmed from a source I opened (CiA page returned 404) | Mobile machinery, drives, robotics | Driver via SocketCAN (background, UNVERIFIED) | UNVERIFIED |
| **IO-Link** (IEC 61131-9) | Not confirmed from a source I opened (page returned 404) | Sensor/actuator last meter | IO-Link master with Ethernet gateway; read via OPC UA/MQTT (background, UNVERIFIED) | UNVERIFIED |
| **LwM2M** (OMA SpecWorks) | OMA's "lightweight, scalable, secure" device management; version and transports not confirmed from the page | Constrained cellular/LPWAN devices | Device-management option for battery sensors; check v1.2/2.0 before committing | S22; version UNVERIFIED |
| **CoAP** (RFC 7252) | Not opened | Constrained networks, LwM2M transport | Background, UNVERIFIED | UNVERIFIED |
| **DDS** (OMG) | Data-centric pub/sub middleware with QoS, DDS Security (authentication, access control, encryption), DDS-RPC, XTypes. RTPS/ROS 2 link not confirmed on page | Robotics (ROS 2), defense, mission-critical | Needed for robots and drones; bridge to NATS | S23 |
| **Matter** | Matter 1.5 released 2025-11-20: cameras, closures, soil sensors, energy tariff/price clusters, TCP. Spec and SDK are CSA-members-only | Consumer and light commercial buildings (30+ device types per CSA) | Controller via Home Assistant; not an industrial protocol | S24, S25 (search) |
| **TSN** (IEEE 802.1) | 802.1AS-2025 published; Qbv (scheduled traffic), Qbu (preemption), Qci in 802.1Q-2018; 802.1CB-2017 (redundancy); IEC/IEEE 60802 industrial profile listed (status not stated) | Converged deterministic Ethernet for new plants | Hardware/NIC feature. Linux needs PTP + qdisc support (background, UNVERIFIED). Design for it later, not now | S26 |

### 1.2 What this means

- **Three layers, three protocol families.** Field level (fieldbus, Modbus, CAN, IO-Link) is owned by PLCs and gateways. Plant level (OPC UA, Sparkplug) is the interoperability layer OneMind must speak. Enterprise/cloud level (MQTT, Kafka, HTTP) is where NATS and the Market app ecosystem sit.
- **The base protocol list for v1:** OPC UA client+server, MQTT 3.1.1/5 broker, Sparkplug B bridge, Modbus TCP/RTU, BACnet/IP, plus Home Assistant for Matter/Zigbee. Everything else (EtherCAT, PROFINET, EtherNet/IP, CANopen, IO-Link) is reached through a PLC or protocol gateway, not by OneMind directly.
- **Security reality:** Modbus has an optional TLS profile on port 802 [S17], PROFINET and EtherNet/IP have their own security classes [S20, S21b]. OneMind's adapters should default to "segment and gate" (network policy plus broker ACLs) because many deployed devices will have none.

---

## 2. Open-source IIoT and edge stacks

License notes come from the repo READMEs I opened. Where the README did not name a license, the license is **UNVERIFIED** (my background belief is in brackets).

| Project | Role | License (verified?) | Maturity / status evidence | Use for OneMind | Src |
|---|---|---|---|---|---|
| **open62541** | C OPC UA (IEC 62541) client/server | MPL-2.0 (plugins/examples CC0 or MPL) verified. | v1.4 example server certified "Standard Server 2017 Profile" by OPC Foundation; project aims at zero CTT errors per release. PubSub UADP/JSON/MQTT supported; history access only partial. | Embedded OPC UA server/client. MPL-2.0 is file-level copyleft and combinable with proprietary code | S6, S27 |
| **Eclipse Milo** | Java OPC UA stack plus client/server SDKs | Not stated on README (UNVERIFIED; background: EPL-2.0) | Targets OPC UA 1.05, SDKs 1.1.6, JDK 17+ | Alternative to open62541 if JVM is acceptable | S28 |
| **Apache PLC4X** | Protocol drivers to PLCs (Siemens S7, Modbus, ADS etc.) | Apache-2.0 verified | Java usable (Java 21+); Go listed usable; C and Python "not ready"; C# WIP; README names only Modbus TCP/RTU and S7 for C# | PLC read/write adapter in Java or Go. Do not assume C/Python bindings | S29 |
| **Eclipse Kura** | Java/OSGi edge gateway framework with web UI, drivers, cloud connectors | Not stated (UNVERIFIED; background: EPL-2.0) | Debian APT repo for x86-64 and arm64; Docker image; Java 21 compatible | Reference pattern; heavy JVM runtime. Optional Market app | S30 |
| **Eclipse Kapua** | IoT device registry, management, messaging, data services | Not stated (UNVERIFIED) | README mentions releases 1.6.x; Docker Hub images are unofficial | Skip unless needed for multi-tenant device management ideas | S31 |
| **Eclipse Ditto** | Digital twin framework (things, features, HTTP API, connectivity service) | EPL-2.0 (badge link) | Listed in good standing; "2025.11 Progress Review" Successful (search); JDK 25 required to build | Candidate device-twin layer. JVM-heavy, plan resource budget | S32, S33 (search) |
| **Eclipse Hono** | Device connectivity (MQTT/AMQP/HTTP) | README fetch 404 (UNVERIFIED) | Listed in good standing (search) | Skip: NATS plus a bridge covers it | S33 (search) |
| **Eclipse Tahu** | Sparkplug reference client libs | Not stated | README links Sparkplug 3.0.0 | Use for Sparkplug B encode/decode | S7 |
| **Eclipse Sparkplug** | Spec and TCK | Eclipse spec | 3.0 = ISO/IEC 20237; 4.0 in development | Compliance target for the bridge | S2, S3 |
| **EdgeX Foundry (LF Edge)** | Microservice edge data platform with device services | Apache-2.0 | Odesa (4.0, 2025-03-14) is LTS with support to March 2027; Palau = 4.0.2 dated 2026-06-25; LF Edge stage review in 2025 filed as Stage 3, graduation not found (search) | Optional Market app; short LTS window (24 months) | S34b, S35b (search) |
| **Node-RED** | Flow-based wiring | Apache-2.0, OpenJS Foundation | Active | Low-code adapter glue; Market app | S36b |
| **ThingsBoard** | IoT platform | **BUSL 1.1 from 4.4** (earlier versions Apache-2.0); each release converts to Apache-2.0 after 4 years | Production use free within Additional Use Grant limits | **License risk** for a product that resells. Avoid as a bundled dependency | S37b |
| **Telegraf** | Metrics collector, 300+ plugins incl. OPC UA, Modbus, MQTT consumer | MIT | 1,200+ contributors | Default scraper for adapters | S38 |
| **TimescaleDB** | Time-series on Postgres | Not stated on README. (Background: Apache-2 core plus Timescale License parts. UNVERIFIED) | Hypertables, continuous aggregates, columnar compression 90%+ claim | Edge historian candidate; verify license split before bundling | S39 |
| **InfluxDB** | Time-series DB | Not opened. UNVERIFIED | - | - | UNVERIFIED |
| **Grafana** | Dashboards | AGPL-3.0-only (some components Apache-2.0) | - | AGPL: fine as a separate Market app, careful if embedded in a proprietary distribution | S40 |
| **OpenPLC v3** | Soft PLC (IEC 61131-3) | Not read | **Repo says v3 is end-of-life, successor is v4** | Do not build on v3. Evaluate v4 only for hobby/education | S41 |
| **Eclipse 4diac FORTE** | IEC 61499 C++ runtime | EPL-2.0 | Builds on Linux, Windows, macOS, FreeRTOS, Zephyr, ThreadX; protocols not stated | IEC 61499 option; same lineage as Schneider/UAO runtime idea (UAO is IEC 61499-based, S34) | S42, S34 |
| **Margo** | Interoperable orchestration of edge apps and devices (open spec, reference implementation, compliance toolkit) | License not stated on pages I opened (UNVERIFIED) | LF-governed; **Preview Release 3 available (page updated 2026-09-18)**; PR3 adds identity and authorization framework, OCI-based Compose, RFC 9457, capabilities instead of roles; members include ABB, Siemens, Schneider, Rockwell, Microsoft, Red Hat, SUSE, Dell, Yokogawa | Watch and align the Market app packaging with Margo; not GA | S8, S8b |
| **Akri** | K8s discovery of leaf devices; handlers ONVIF, udev, OPC UA, debug-echo | Apache-2.0; CNCF Sandbox | Microsoft Azure IoT Operations also uses "Akri connectors" [S21] | Good fit for discovering OPC UA servers and cameras on k3s | S43, S21 |
| **KubeEdge** | K8s at the edge; DeviceController and DeviceTwin; MQTT EventBus | Apache-2.0; CNCF graduated | Device mappers and DMI not covered on the README I opened | Alternative to k3s hub-and-spoke if cloud-to-edge K8s management is needed. Heavier fit than NATS leafnodes | S44 |

**Takeaways**
- The healthy, license-clean core for OneMind is: open62541 or Milo, PLC4X, Telegraf, Node-RED, a Sparkplug-capable MQTT broker, a time-series store, Grafana (separate app), plus Akri for discovery.
- **License traps:** ThingsBoard (BUSL from 4.4) [S37b], Grafana (AGPL) [S40], TimescaleDB (needs license check) [S39]. Decide the commercial model (DECISIONS.md "pro vs open" ADR) before bundling any of these.
- **Dead end:** OpenPLC v3 is end of life [S41].

---

## 3. Commercial industrial edge platforms

| Platform | Runs on / OS | Pattern | Evidence | Src |
|---|---|---|---|---|
| **Siemens Industrial Edge** | Docker-based apps on edge devices (SIMATIC IPCs, HMI panels). Management via Industrial Edge Management (IEM): on-prem virtual, Kubernetes-based IEM Pro, SaaS IEM Cloud. | Closed app store, central fleet mgmt, containers | Device OS **not stated** in sources I opened. Siemens says the architecture supports IEC 62443-4-2; a formal certificate for the device was not found. | S45 (search) |
| **Red Hat Device Edge** | RHEL plus MicroShift (lightweight Kubernetes); Image Mode for RHEL; greenboot rollback on failed health check; rpm-ostree delta updates. Image mode GA in MicroShift 4.19 (search). | Image-based OS plus K8s | RHEL 9.6, OpenShift 4.20 and MicroShift 4.21 each have IEC 62443-4-2 **SL-C 2** by TUV Rheinland (page gives no date) | S9, S46, S47 (search) |
| **Ubuntu Core (Canonical)** | Immutable snap-based OS; amd64, arm64, armhf; Core 26 released May 2026; install guides for AMD Kria, MediaTek Genio, Renesas RZ/G2L, NVIDIA Jetson; FDE, secure onboarding, rollback | Appliance OS | 10 yrs standard security maintenance; +5 yrs "Legacy" add-on via Ubuntu Pro (Core 22: Jun 2032/2037; Core 24: Jun 2034/2039; Core 26: May 2036/2041). "12-year LTS" appears in launch marketing but the official table is 10+5. Eurotech ReliaCOR 40-13 and 54-13 (Ubuntu 22.04) hold ISASecure CSA Level 2 | S12, S48 (search), S49 |
| **Balena / balenaOS** | Yocto-based, A/B rootfs, container host (from `base-os-and-orchestration.md`; not re-opened) | Fleet via balenaCloud | See base-os doc | repo doc |
| **Azure IoT Operations** | Kubernetes-native on Azure Arc-enabled clusters: edge MQTT broker, Akri connectors, OPC UA connector, data flows; offline max 72 h with degradation; local install on Ubuntu or Windows with AKS Edge Essentials | UNS-like with MQTT broker, cloud-managed | Needs Azure Arc for management; asset registry lives in Azure Device Registry | S21 |
| **Azure IoT Edge** | Container modules via moby-engine; Tier 1 OS: Debian 12, RHEL 8/9, Ubuntu 22.04/24.04, Ubuntu Core, Windows; Yocto kirkstone/scarthgap tier 2. **1.5 LTS support ends 2026-11-10 (today); 1.6 LTS to 2028-11-14** | Legacy module model; strategic push is IoT Operations | Direct evidence of how fast cloud-vendor edge runtimes churn | S50 |
| **AWS IoT Greengrass v2** | Nucleus runtime; "nucleus lite" since 2.14.0 for constrained devices; components deployed and restarted on nucleus change | Cloud-managed components | Supported OS list not extracted (UNVERIFIED) | S51 |
| **Litmus Edge** | Deploys as VM (VMware, Hyper-V), Docker, Docker Compose, K3s, Kubernetes Operator; Litmus Unify = UNS layer on MQTT pub/sub with ISA-95 mapping; has Sparkplug edge node | Industrial DataOps | Official OS requirements not found | S35 (search) |
| **HighByte Intelligence Hub** | Software or Docker image, from SBCs to servers; built-in broker for a local UNS; Kubernetes via community tutorial | DataOps/modelling hub | Official OS requirements not found | S36 (search) |
| **Inductive Automation Ignition** | Docs URL returned 404. Background: Java platform, Sparkplug via Cirrus Link modules | Dominant SCADA with Sparkplug | **UNVERIFIED** | UNVERIFIED |
| **Bosch / Schneider EcoStruxure** | Schneider EcoStruxure Automation Expert is IEC 61499 based and conforms to UniversalAutomation.org (UAO) runtime. Soft dPAC controller runs on any Linux meeting baseline specs, plus pre-installed Edge Controller offers; 500+ deployments claimed. "EcoStruxure Edge" by that name not found. Bosch: not researched | Software-defined automation | Secondary/search only | S34 (search) |
| **Moxa gateways** | UC-8200 with Moxa Industrial Linux 3 (MIL3), IEC 62443-4-2 **SL2** (ISASecure CSA), Bureau Veritas, 2023-01-31; TPM 2.0, OTP fuse, secure boot; **MIL3 10-year LTS incl. security patches** | Vendor Linux on hardware | Vendor press release | S13 |
| **Advantech** | Fetch redirected; OS options not confirmed | - | **UNVERIFIED** | UNVERIFIED |
| **Opto 22 groov EPIC** | Page 404. Background: Linux-based controller with Node-RED, Ignition Edge, CODESYS | - | **UNVERIFIED** | UNVERIFIED |
| **Eurotech** (ISASecure listings) | ReliaGATE gateways and ReliaCOR servers on ESF/EL stacks and Ubuntu; ISASecure CSA Level 2 listings through 2026-08-26 | Certified gateway vendor | OS named only for ReliaCOR (Ubuntu 22.04.x) and Wartsila (RHEL 8.10, Level 1) | S12 |

**Patterns to copy**
- **Unified Namespace (UNS):** a single broker-centered, real-time source of truth, hierarchy typically modelled on ISA-95 (Enterprise > Site > Area > Line > Cell), transport MQTT, payload Sparkplug or JSON. Coined/popularized by Walker Reynolds; sources are mostly vendor blogs (HiveMQ, Litmus, Inductive); no formal standard defines UNS [S52 (search, secondary)].
- **Industrial DataOps:** modelling and contextualisation layer between raw tags and consumers (HighByte, Litmus). OneMind's equivalent is an adapter plus schema registry in the NATS grammar.
- **Image-based OS plus Kubernetes plus central fleet manager:** Red Hat Device Edge, Siemens IEM Pro, Azure IoT Operations all do it. This validates ADR-001's direction (A/B image + k3s).
- **Vendor edge runtimes churn:** Azure IoT Edge 1.5 LTS ends today and 1.4 ended 2024-11-12 [S50]. Do not make OneMind depend on a cloud vendor's runtime.

---

## 4. Security and compliance

### 4.1 IEC 62443

| Part | What it covers (S53 ISA) | What it means for an edge-OS vendor |
|---|---|---|
| **62443-4-1** | Secure product development lifecycle (for product suppliers) | Process certification of OneMind itself: security requirements, threat modelling, secure design, SBOM, vulnerability handling, patch/update management, secure release. CIP reports the first open-source 4-1 assessment (Aug 2024) [S11 via search] |
| **62443-4-2** | Technical security requirements for IACS components (embedded devices, host devices, network devices, software applications) | Per-component technical controls. Red Hat page lists SL-C 2 domains as identification and authentication control, use control, system integrity, data confidentiality, timely response to events [S9]. For OneMind: authn for all interfaces, RBAC, signed updates, audit log, secure boot or integrity, crypto, session/DoS limits |
| **62443-3-3** | System security requirements and security levels (for system integrators and asset owners) | OneMind must supply controls an integrator can map: zone/conduit support, network policy, logging, SL-T evidence |
| Roles | asset owner, system integrator, product supplier | OneMind is a product supplier; the site installer is the integrator |

**Reality check on certifications** (all from pages I opened unless marked):
- Red Hat: RHEL 9.6, OpenShift 4.20, MicroShift 4.21 each SL-C 2 by TUV Rheinland [S9]. Date and conditions not on the page.
- Moxa UC-8200 + MIL3: SL2 CSA, Bureau Veritas, 2023 [S13].
- ISASecure listing includes Eurotech gateways and servers (Levels 1 and 2), Wartsila (RHEL 8.10, Level 1), others [S12]. It says nothing of Debian, Fedora, Ubuntu Core as OS-only certifications.
- CIP: reports 4-1 assessment (Aug 2024) and 4-2 (Feb 2026); the 4-2 certification was on Siemens Mobility M-COM hardware; CIP images are "62443-4-2 ready" with the right configuration; SL-2 tooling [S10, S11]. This is CIP/Siemens self-reporting; independent verification not found.
- Wind River VxWorks Cert Edition: GE Digital Achilles Level II "for compliance with IEC 62443 part 4-2" (search only, RTOS, not Linux) [S54 (search)].
- **Conclusion:** the realistic path is "OneMind hardware or reference configuration certified as a host device/embedded device", not "OneMind OS certified". Start with 4-1 process work (SBOM, CVE handling), which also feeds CRA compliance.

### 4.2 NIST SP 800-82 Rev 3

Guide to OT Security, final 2023-09-28, supersedes Rev 2 (2015); covers industrial control, building automation, transportation and physical access control; **Rev 4 initial public draft exists with comments due 2026-11-30** [S55]. Use as the architecture checklist for OneMind's reference design (segmentation, monitoring, safety-aware patching). Details of what changed from Rev 2 not extracted (UNVERIFIED).

### 4.3 EU Cyber Resilience Act (Regulation (EU) 2024/2847)

- **Since 2026-09-11:** manufacturers must report actively exploited vulnerabilities and severe incidents; early warning in **24 h**, fuller notification in **72 h**; final report 14 days after a fix (vulnerability) or one month after the 72 h notification (incident). Via ENISA's Single Reporting Platform (manual, EU Login MFA, no API yet) [S14]. Applies to in-scope products already on the market before 2027-12-11, even if unmodified (Art. 69(3)) [S14].
- **From 2027-12-11:** remaining obligations including essential cybersecurity requirements and conformity assessment for new products (law-firm sources) [S15 (search)].
- **Classification:** in the 2022 *proposal*, industrial automation control systems (PLC, DCS, CNC, SCADA) sit in Annex III Class I or Class II, and OSes for servers, desktops and mobile in Class II; I did **not** verify the adopted text [S56 (search)]. **UNVERIFIED:** whether OneMind hardware or software lands in default, Important Class I/II. This changes whether a third-party assessment is needed. Get counsel's read of the Official Journal text.
- ODVA says CIP Security can help users meet IEC 62443 and the CRA [S21b]. Rugix Ctrl appears in an EY "practical reference architecture for CRA compliance" (Nov 2025) but I could not read its content [S57 (search)].
- Open-source nuance (steward role, commercial activity) not researched. UNVERIFIED.

### 4.4 NERC CIP (energy)

- FERC approved **CIP-015-1** (internal network security monitoring, INSM) on 2025-06-26 (Order No. 907). Sources disagree on dates: law firms cite effective 2025-09-02, Dragos cites enforceable obligations from **2028-10-01**. FERC directed an extension to EACMS and PACS (NERC revisions due within 12 months of 2025-09-01 per NERC project page, i.e. around 2026-09, per search) [S58 (search)].
- CIP-003-11 filed 2024-12-20; approval not confirmed in sources found.
- **Implication:** edge devices in BES (bulk electric system) contexts need monitoring-friendly network design (mirror ports or taps, logging) and are typically deployed by utilities, not sold to them as consumer products. Treat NERC CIP as a later vertical; do not claim compliance.

### 4.5 Secure onboarding, identity, OTA

| Mechanism | Evidence | Use for OneMind |
|---|---|---|
| **FIDO Device Onboard (FDO)** | Protocol for automatic, zero-touch onboarding; Ownership Voucher ties a device to its owner; Rendezvous server directs the device to its owner; device-initiated connections; open-source implementations (Go, Rust, C), many in LF Edge's FDO project. Page says v1.1 fully released and v2.0 "close to full release" (another page implies v2.0 already available): **current version UNVERIFIED** | Strong fit for 10k-device fleets and manufacturing-time provisioning. Add as a provisioning option after Rugix/OTA works |
| **Matter commissioning** | Matter 1.5 (2025-11-20), CSA members-only specs/SDK [S24] | Home Assistant handles it; OneMind should not reimplement |
| **Wi-Fi DPP (Easy Connect)** | Not opened. **UNVERIFIED** | - |
| **IEEE 802.1AR IDevID with TPM** | Not opened. TCG "Securing FDO in TPM" draft exists (search) [S59 (search)]. **UNVERIFIED** details | Bind device identity to TPM 2.0 (Moxa UC-8200 uses TPM 2.0 for hardware root of trust [S13]) |
| **Industrial OTA** | Rugix: Bakery builds images and update bundles, Ctrl manages A/B slots and rollback; builds Debian and Alpine; also integrates with Yocto/Buildroot; verify the bundle-signature flag in docs before production (search) [S57 (search)]. Red Hat: greenboot rollback, rpm-ostree delta updates [S46]. Moxa MIL3: backup/restore/auto recovery [S13]. Ubuntu Core: automatic rollback [S49] | ADR-001 D3 stands. Add "health gate commits slot" and a signed-bundle policy. |

---

## 5. Real-time and determinism

### 5.1 Facts

- **PREEMPT_RT is in mainline** since Linux 6.12 (merged 2024-09-20 by Torvalds from Gleixner; released Nov 2024). Enabled on x86, x86_64, arm64, RISC-V; not "all architectures" (search, secondary) [S1]. The kernel's own real-time doc index exists, but my fetch showed only section titles [S1b]. Whether Debian 13's stock kernel ships an RT flavor is **UNVERIFIED**; RevPi ships Debian with an RT-patched kernel [S60].
- **Kubernetes CPU manager static policy** gives exclusive CPUs only to Guaranteed pods with integer CPU requests, requires a CPU reservation, and "improves cache affinity"; it does **not** claim hard real-time. Kernel isolation (`isolcpus`, `nohz_full`, IRQ affinity) is outside kubelet and not covered on that page [S61]. (The statement that kubelet pinning does not remove CPUs from kernel balancing is the fetch tool's general-knowledge remark, **UNVERIFIED**.)
- **Zephyr:** Apache-2.0; 3.7.0 is the marked LTS; docs have a Safety section (overview and requirements management) but I did not confirm any IEC 61508 certification status [S62, S63]. FreeRTOS, Xenomai, SIL claims: not researched. **UNVERIFIED**.
- **micro-ROS:** website moved to micro.vulcanexus.org; supported RTOS list and status **UNVERIFIED** [S64].
- **TSN:** 802.1AS-2025 published; Qbv, Qbu, Qci integrated in 802.1Q-2018 [S26].
- **EtherCAT** cycle target 100 us or less and 1 us jitter, which is beyond what a general Linux container host should be asked to guarantee [S19].
- **4diac FORTE** runs on FreeRTOS, Zephyr, ThreadX and Linux, so IEC 61499 logic can sit on an MCU [S42].

### 5.2 How OneMind should split control vs supervision

| Tier | Typical timing | Who owns it | Examples | OneMind role |
|---|---|---|---|---|
| Safety | Deterministic, certified | Safety PLC / safety relay, SIL-rated | E-stop, interlocks, valve trips | **Never in the loop.** Read status only. AI agents have no write path |
| Hard control | 50 us to 10 ms | PLC, motion controller, MCU/RTOS (Zephyr, FreeRTOS), fieldbus master | Servo axes, burner control, dosing pumps | Consume state; send setpoints, recipes, mode changes |
| Soft control | 10 ms to 1 s | Soft PLC (OpenPLC, 4diac, CODESYS: UNVERIFIED), Linux PREEMPT_RT with pinned cores, ESP32/MCU | Climate loops, irrigation, conveyor logic | Optional "Control runtime" Market app, explicit opt-in, no safety claims |
| Supervision | 1 s to hours | OneMind (Linux, k3s, NATS, agents) | Dashboards, anomaly detection, scheduling, AI recommendations | Core product |

Rules for the architecture:
1. **Fail-safe at the edge of the controller.** Every actuator must have a local watchdog and safe state if the supervisor dies or the link drops.
2. **Setpoints, not outputs.** AI and Market apps send bounded setpoints/commands to a controller; the controller validates ranges and rate limits.
3. **Permission model:** the MCP/capability gateway marks each tag as read, advisory-write, or control-write, with human approval and audit for control-write. Safety-classed tags are read-only.
4. **Soft real-time on k8s is possible but must be labelled:** isolated cores, RT kernel, Guaranteed QoS, and measured latency (cyclictest-style tests, background knowledge, UNVERIFIED). No guarantees promised in marketing.

---

## 6. Hardware

| Device | Verified facts | Notes | Src |
|---|---|---|---|
| **Revolution Pi Connect 5** | Raspberry Pi CM5 (quad Cortex-A76 2.4 GHz); Debian image based on Raspberry Pi OS with real-time kernel patch; custom images allowed; -25 to +55 C; CE and UKCA; EN 61131-2 and IEC 61000-6-2/-4 EMC; DIN rail images; CM5 availability stated "at least 2036" | UL not mentioned on the page. DIN-rail mounting details not on page | S60 |
| **Siemens SIMATIC IOT2050** | Page: TI ARM processors; **OS, temperature, certifications, lifecycle not stated on the page I opened** | Background: Debian-based example image, CIP-related. **UNVERIFIED** | S65 |
| **Moxa UC-8200** | Arm; Moxa Industrial Linux 3; TPM 2.0, OTP fuse, secure boot; SL2 certified; 10-year LTS | Closest "certified Linux gateway" reference | S13 |
| **Eurotech ReliaGATE / ReliaCOR** | ISASecure CSA Level 1-2 gateways and servers, ESF stack, Ubuntu 22.04.x on ReliaCOR | Competitor/partner reference | S12 |
| **Siemens SIMATIC IPCs** | Industrial Edge hardware | OS not stated | S45 (search) |
| Fanless x86 IPCs (Advantech, etc.), DIN-rail ARM, wide-temp ranges, ATEX etc. | Not confirmed from sources I opened | **UNVERIFIED** | - |

**Hardware criteria to adopt (derived, not from one source):** TPM 2.0 or equivalent secure element; secure boot with owner-controlled keys; wide-temp (-40 to +70 C) option; two or more Ethernet ports for IT/OT separation; isolated serial (RS-485) and CAN; hardware watchdog; long-life silicon (CM5 availability claim to 2036 from RevPi [S60]); eMMC/NVMe with A/B layout. Certification targets to track: CE/UKCA/FCC, IEC 61131-2 (PLC hardware, as RevPi claims), IEC 61000-6-2/-4 EMC, UL 61010 or similar (UNVERIFIED), 62443-4-2 at host-device level (Moxa precedent).

---

## 7. Base OS implications

### 7.1 What industrial vendors actually ship (evidence)

| Vendor/product | Base OS | Evidence |
|---|---|---|
| Moxa UC-8200 | Moxa Industrial Linux 3 (own distro), 10-year LTS | S13 |
| Red Hat Device Edge | RHEL + MicroShift, image mode | S9, S46 |
| Eurotech ReliaCOR | Ubuntu 22.04.x | S12 |
| Wartsila GEMS controller | RHEL 8.10 | S12 |
| Revolution Pi | Debian (Raspberry Pi OS based) + RT kernel | S60 |
| Schneider Soft dPAC | "Any Linux device meeting baseline" (distro not named) | S34 (search) |
| Azure IoT Edge tier 1 | Debian 12, RHEL 8/9, Ubuntu, Ubuntu Core (and Yocto tier 2) | S50 |
| CIP Core | Debian-based, built with Isar | S10 |
| Siemens Industrial Edge | Not stated | S45 |

### 7.2 Support-lifetime table

| OS | Support length (verified) | Fit for 10-15 yr industrial |
|---|---|---|
| Debian 13 | Regular to 2028-08-09, LTS to 2030-06-30, ELTS to 2035-06-30 (ELTS is paid) (from `base-os-and-orchestration.md`, S-doc) | 10 yr only with paid ELTS or own maintenance; fine as image base if OneMind owns patching |
| CIP SLTS kernels | 10 years per series (4.4, 4.19, 5.10, 6.1, 6.12 maintained; 4.4 about 2016-2027). Debian base via Isar; funds Debian LTS | Strongest "open" 10-year option. Exact end dates not verified here |
| RHEL 9 / 10 | RHEL 8/9/10 ten-year life cycle (5 full + 5 maintenance, plus extended phases); RHEL 9 end of standard support May 2032, RHEL 8 May 2029 [S50]. MicroShift lifecycle dates not found | Best commercial answer; subscription terms UNVERIFIED |
| Ubuntu Core | 10 years standard + 5 with Pro Legacy add-on (15 total) | Good, but ADR-001 flagged Ubuntu Pro costs |
| Moxa MIL3 | 10-year LTS | Vendor-only |
| Yocto LTS | **4 years** (Scarthgap to April 2028, Wrynose to April 2030) [S66] | You maintain the rest: build your own 10-year story |
| Fedora IoT | About 13 months per release (from base-os doc, UNVERIFIED there) | **Not** a 10-year base. Use RHEL image mode for that |

### 7.3 Options and verdict

| Option | Strengths | Weaknesses | Verdict |
|---|---|---|---|
| **Debian 13 + Rugix A/B (ADR-001 current)** | No per-device license, proven appliance path (Umbrel), Pi 5 path, same base as RevPi and CIP lineage | 10 years only by paying/maintaining; no vendor 62443-4-2 cert for the OS | **Keep as default** for consumer, prosumer, light industrial |
| **CIP Core / Debian + SLTS kernel (Isar)** | 10-year kernels, 62443-4-1 and 4-2 reported (self/Siemens-reported), Debian compatible, Siemens-backed | Fewer boards than mainstream Debian; Isar build pipeline; need to confirm 4-2 scope and arch support | **Best "Industrial" track candidate**. Spike it |
| **RHEL image mode (bootc) / MicroShift** | 62443-4-2 SL-C 2 precedent for RHEL 9.6 and MicroShift 4.21; 10-year life cycle; Device Edge pattern with greenboot | Commercial subscription (terms UNVERIFIED); MicroShift is not k3s; Pi 5 and Jetson story weak | **Offer as a certified-hardware SKU or partner path** |
| **Fedora IoT / CoreOS (bootc)** | Same technology lineage as RHEL image mode; OCI-image updates; bootable-container image type for Fedora 44 IoT (search) | Short Fedora lifecycle; FCOS/bootc unification still in flux (from base-os doc) | **Dev/community channel, not industrial LTS.** Do not promise 10 years |
| **Ubuntu Core** | 15-year story with Pro, Eurotech 62443 precedent, snaps | Snap lock-in, Pro per-device terms unpublished (ADR-001) | **Only Jetson/NVIDIA flavor** unless a customer demands it |
| **Yocto (own distro)** | Total control, small footprint, many silicon BSPs | 4-year LTS, high maintenance load | Use for MCU-class or very constrained SKUs only |

### 7.4 How OneMind serves both consumer IoT and IIoT without hitting limits

1. **One userland contract, multiple OS bases.** Apps are containers on k3s (RKE2 hardened) per ADR-001 D4, so Market apps do not care which host OS carries them. Define a "host profile" contract (kernel features, cgroup v2, SELinux/AppArmor, device nodes, RT option) rather than a distro.
2. **Profiles, not forks:** *Home* (Debian, HA integration, convenience), *Pro/Site* (Debian + hardened k3s, signed update channels, SBOM), *Industrial* (CIP or RHEL-image-mode track, RT kernel option, TPM-bound identity, 62443-4-1 process evidence, no auto-update, long support window).
3. **Separate the lifecycles:** OS image, k3s, Market apps and firmware update independently (ADR-001 D3). That is what makes a 10-year base OS plus modern apps possible.
4. **Own the patch pipeline:** Even on Debian, plan for the CRA clock: an SBOM per image, a CVE feed, a 24-hour triage path [S14]. This cost exists regardless of which OS wins.
5. **Re-open ADR-001 D2/D3 only as an additive "Industrial profile" decision**, not a replacement of Debian. The Fedora IoT / bootc question is routed to the separate deep dive.

---

## 8. Architecture implications for OneMind OS

### 8.1 Protocol adapters as Market apps

- Every protocol ships as a signed Market app (container + manifest) with capabilities declared: network reach (host:port), serial/CAN device access, tag read/write class. Alignment target: **Margo** app/workload description, currently **Preview Release 3** (OCI-based Compose, identity and authorization framework, capabilities) [S8].
- Starter adapters: OPC UA client/server (open62541), Modbus TCP/RTU (PLC4X or Telegraf), BACnet/IP, Sparkplug B bridge (Tahu), MQTT, Node-RED, Home Assistant (Matter, Zigbee). Discovery through **Akri** handlers (OPC UA, ONVIF, udev) [S43].
- Adapter contract: emits to the UNS in a normalized message (value, quality, timestamp, unit, source), receives commands only through a capability-checked command subject.

### 8.2 Unified Namespace on NATS and MQTT

- NATS maps MQTT topic `a/b/c` to subject `a.b.c`; MQTT sessions and retained messages live in JetStream; leaf nodes carry MQTT traffic [S37].
- **Blocking constraint:** NATS MQTT is **3.1.1 only; MQTT 5 clients are refused** [S37]. Options:
  1. Use NATS as the internal bus and run an **MQTT 5 broker** as a Market app for devices, bridged to NATS subjects (needs a broker choice; not researched, UNVERIFIED).
  2. Require 3.1.1 at the NATS MQTT port and accept losing 5.0 features (shared subscriptions, user properties).
  3. Native NATS clients for OneMind apps; MQTT only at the device edge.
- **Sparkplug:** the spec is built around MQTT with birth/death certificates and last-will messages [S2, S3]. Whether Sparkplug 3.0 works with MQTT 3.1.1 only brokers, and whether NATS's retained/QoS2 behavior satisfies the Sparkplug TCK, is **UNVERIFIED**. Run the Sparkplug TCK against whichever broker is chosen before claiming compatibility.
- **Namespace:** adopt an ISA-95-style hierarchy (Enterprise/Site/Area/Line/Cell/Equipment), mapped to NATS subjects, e.g. `onemind.<tenant>.<site>.<area>.<line>.<asset>.<metric>` (a design proposal, not a standard). Include a schema registry so AI agents get semantic context.

### 8.3 OPC UA server/client

- Ship an OPC UA **server** exposing OneMind's UNS (read-mostly), an OPC UA **client** adapter for PLCs, and PubSub over MQTT for uplink. open62541 (MPL-2.0) satisfies most needs but history access is only partial [S6], so the edge historian should provide history, not the OPC UA server.
- Security: use certificate-based trust lists and the Basic256Sha256 or stronger policies; open62541 lists Basic128Rsa15 and Basic256 as supported [S6] (deprecated policies should be disabled by default; deprecation status UNVERIFIED here).

### 8.4 Device twins

- Options: Eclipse Ditto (EPL-2.0, JVM), KubeEdge DeviceTwin (Apache-2.0, K8s-coupled) [S32, S44], or a lightweight OneMind twin = JetStream KV (desired/reported state) with a schema from OPC UA NodeSets / Sparkplug templates. The last avoids a JVM and keeps NATS as single bus. A choice for a spike.

### 8.5 Edge historian

- Telegraf (MIT) to a time-series store (TimescaleDB needs license check; ClickHouse already in the OneMind data plane per project notes, UNVERIFIED here) plus Grafana as a separate app (AGPL) [S38, S39, S40]. Store-and-forward via JetStream for offline periods (Azure IoT Operations tolerates only 72 h offline with degradation [S21]; a local-first OneMind should beat that).

### 8.6 Safety boundaries (hard requirements)

1. No agent or Market app can write to a safety-classed tag. Write path to controllers requires: capability grant, range/rate limits, optional human approval, audit trail.
2. Controllers must hold a safe state on supervisor loss.
3. Soft-control runtimes are labelled "non-safety"; any SIL claim requires separate certification (OpenPLC v3 is EOL [S41]; Zephyr safety certification status unconfirmed [S63]).
4. Time sync: PTP (802.1AS) where needed [S26].

### 8.7 Fleet management at 10k devices

- k3s numbers in ADR-001 (3 servers about 1,200 agents) mean a flat cluster is wrong at this scale. Use **site clusters** (one k3s per site or per tenant-site), with NATS leaf nodes to a hub (hub-and-spoke) [S37].
- Fleet plane needs: identity (TPM-bound, FDO ownership vouchers for zero-touch [S59]), signed OTA waves with health-gated commit (Rugix, Red Hat greenboot pattern [S46, S57]), staged rollouts and rollback, SBOM/CVE inventory per device for CRA [S14], remote attestation (UNVERIFIED).
- Cloud-vendor equivalents (Siemens IEM, Azure Arc, Greengrass deployments) show the pattern but lock you in; Margo is the vendor-neutral direction to watch [S8, S45, S21, S51].
- Alternative hub option: KubeEdge CloudCore/EdgeCore for cloud-managed K8s edge nodes [S44]. Scale limits not verified.

### 8.8 Multi-tenant sites

- Tenant = NATS account (isolated subject space, imports/exports for sharing), Kubernetes namespace plus network policy per tenant, separate OPC UA/Sparkplug trust lists, per-tenant backup keys.
- Zone/conduit mapping for IEC 62443-3-3: each tenant or area is a zone; adapters are conduits with explicit allow-lists [S53].

---

## 9. Recommended next steps (ordered)

1. **Decide the MQTT strategy** (section 8.2) and run the Sparkplug TCK on the chosen broker.
2. **Spike CIP Core (Debian/Isar) on x86 and Pi CM5** and read CIP's 4-1/4-2 certificates and scope; compare to RevPi's Debian + RT kernel.
3. **Spike NATS leafnode hub-and-spoke at 100 simulated sites**, then extrapolate; confirm k3s agent limits from E2.
4. **Counsel review of CRA classification** of OneMind hardware and software against the Official Journal text.
5. **Build the first three adapters as Market apps:** OPC UA client, Modbus, Sparkplug bridge. Package against Margo PR3 to test fit.
6. **Define the capability classes** (read, advisory-write, control-write, safety-read-only) in the MCP gateway before any control-write exists.
7. **Add 62443-4-1 process gap analysis** (SBOM, vulnerability handling, secure update) since it feeds CRA readiness.

---

## 10. UNVERIFIED list

Protocols and data models
- OPC UA companion spec domains list; open62541 Part 14 details beyond FEATURES.md.
- CAN/CANopen, IO-Link, CoAP (RFC 7252): not confirmed from opened sources.
- LwM2M current version and transports.
- Wi-Fi DPP, IEEE 802.1AR IDevID details.
- BACnet/SC and ISO 16484-5 relationship.
- Sparkplug 3.0 behavior on MQTT 3.1.1-only brokers; NATS conformance with the Sparkplug TCK.
- Linux TSN support details (PTP, qdisc).

Software stacks
- Licenses of Eclipse Kura, Kapua, Milo, Hono, Tahu, InfluxDB, TimescaleDB (split), OpenPLC v4, Margo spec.
- Hono maturity (README 404); Kapua status; EdgeX graduation status and device-service protocol list.
- Ignition, Opto 22 groov EPIC, Advantech, Bosch industrial edge, HighByte and Litmus official OS requirements.
- Siemens Industrial Edge device OS and any formal 62443 certificate.
- Greengrass supported OS list.
- Akri and KubeEdge scale limits; KubeEdge mappers/DMI maturity.
- Margo: where the spec repo lives; whether PR3 is stable; license.

Security and compliance
- Whether CIP's 4-2 certificate and SL-2 claims are independently verified and for what scope.
- RHEL/MicroShift 4-2 certificate dates and conditions; MicroShift life cycle dates.
- CRA: final adopted Annex III/IV classification for PLCs, IACS and OSes; open-source steward rules.
- NERC CIP-015 exact effective dates; CIP-003-11 approval status.
- FDO current version (1.1 vs 2.0).

Real time and hardware
- Zephyr and FreeRTOS safety certification status; Xenomai status; micro-ROS RTOS support.
- Whether Debian 13 ships an RT kernel flavor.
- SIMATIC IOT2050 OS, temperature range, certifications.
- Fanless x86 IPC vendors, wide-temp and hazardous-area certification specifics, UL status for RevPi.

Base OS
- RHEL subscription terms for embedded/OEM use; RHEL 10 image-mode details.
- Debian ELTS pricing and coverage for a device vendor; CIP SLTS end dates per kernel.
- Ubuntu Pro per-device pricing (already flagged in ADR-001).

---

## 11. Sources

All opened 2026-11-10. Notes: "(search)" = taken from search-result text only.

- S1 Real-time Linux mainline, Linux 6.12: https://phoronix.com/news/Linux-6.12-Does-Real-Time , https://lwn.net/Articles/992185/ (search)
- S1b Kernel real-time docs index: https://docs.kernel.org/core-api/real-time/index.html
- S2 Eclipse Sparkplug: https://sparkplug.eclipse.org/ ; spec repo https://raw.githubusercontent.com/eclipse-sparkplug/sparkplug/master/README.md
- S3 Sparkplug ISO/IEC 20237: https://newsroom.eclipse.org/node/39754 , https://blogs.eclipse.org/node/7442 (search)
- S4 OPC UA Part 14 (v1.05.06, 2025-10-22): https://reference.opcfoundation.org/Core/Part14/v105/docs/
- S5 OPC Foundation collaboration: https://opcfoundation.org/markets-collaboration/
- S6 open62541 README and FEATURES: https://raw.githubusercontent.com/open62541/open62541/master/README.md , https://raw.githubusercontent.com/open62541/open62541/master/FEATURES.md
- S7 Eclipse Tahu: https://raw.githubusercontent.com/eclipse-tahu/tahu/master/README.md
- S8 Margo: https://margo.org/ ; S8b https://docs.margo.org/
- S9 Red Hat IEC 62443-4-2: https://access.redhat.com/compliance/iec-62443-4-2
- S10 CIP 10 years blog: https://cip-project.org/blog/2026/05/12/ten-years-of-cip-project-from-a-vision-to-the-industrial-gold-standard
- S11 CIP SLTS and 4-1/4-2 (search results page above plus CIP/Siemens statements)
- S12 ISASecure certified components: https://isasecure.org/end-users/iec-62443-4-2-certified-components
- S13 Moxa UC-8200 release: https://www.moxa.com/en/about-us/news-events/news/2023/moxa-launches-worlds-first-industrial-computer-with-iec-62443-4-2-host-device-certification
- S14 CRA reporting guide (independent, not the regulation text): https://www.cyberresilienceact.eu/reporting.html
- S15 CRA dates (law-firm pages, search): https://www.mccannfitzgerald.com/knowledge/data-privacy-and-cyber-risk/cyber-resilience-act-reporting-obligations-apply-from-11-september-2026 , https://www.kirkland.com/publications/kirkland-alert/2026/09/the-eu-cyber-resilience-act
- S16 MQTT 5.0: https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html
- S17 Modbus: https://modbus.org/modbus-specifications , https://www.modbus.org/docs/MB-TCP-Security-v36_2021-07-30.pdf (search)
- S18 BACnet: https://www.bacnet.org/
- S19 EtherCAT: https://www.ethercat.org/en/technology.html
- S20 PROFINET: https://www.profibus.com/technologies/profinet
- S21 Azure IoT Operations: https://learn.microsoft.com/en-us/azure/iot-operations/overview-iot-operations
- S21b ODVA EtherNet/IP: https://www.odva.org/technology-standards/key-technologies/ethernet-ip/
- S22 OMA LwM2M: https://www.openmobilealliance.org/lwm2m
- S23 DDS Foundation: https://www.dds-foundation.org/what-is-dds-3/
- S24 CSA Matter: https://csa-iot.org/all-solutions/matter/
- S25 Matter 1.5 (search): https://csa-iot.org/newsroom/matter-1-5-introduces-cameras-closures-and-enhanced-energy-management-capabilities/
- S26 IEEE 802.1 TSN: https://1.ieee802.org/tsn/
- S27 open62541 (see S6)
- S28 Eclipse Milo: https://raw.githubusercontent.com/eclipse-milo/milo/main/README.md
- S29 Apache PLC4X: https://raw.githubusercontent.com/apache/plc4x/develop/README.md
- S30 Eclipse Kura: https://raw.githubusercontent.com/eclipse-kura/kura/develop/README.md
- S31 Eclipse Kapua: https://raw.githubusercontent.com/eclipse-kapua/kapua/develop/README.md
- S32 Eclipse Ditto: https://raw.githubusercontent.com/eclipse-ditto/ditto/master/README.md
- S33 Eclipse project standing (search): https://www.eclipse.org/projects/tools/goodstanding-releases.php , https://projects.eclipse.org/node/31622
- S34 Schneider EcoStruxure Automation Expert / UAO (search): https://community.se.com/t5/Industrial-Automation-Knowledge/EcoStruxure-Automation-Expert-How-to-Install-SoftdPAC-on-Linux/ta-p/474546
- S34b EdgeX README: https://raw.githubusercontent.com/edgexfoundry/edgex-go/main/README.md ; S35b EdgeX releases (search): https://www.edgexfoundry.org/software/releases/
- S35 Litmus (search): https://litmus.io/deployments , https://litmus.io/architecture-hub/industrial-dataops-and-uns
- S36 HighByte (search): https://www.novotek.com/de/en/solution/highbyte-intelligence-hub/
- S36b Node-RED: https://raw.githubusercontent.com/node-red/node-red/master/README.md
- S37 NATS MQTT: https://docs.nats.io/running-a-nats-service/configuration/mqtt
- S37b ThingsBoard: https://raw.githubusercontent.com/thingsboard/thingsboard/master/README.md
- S38 Telegraf: https://raw.githubusercontent.com/influxdata/telegraf/master/README.md
- S39 TimescaleDB: https://raw.githubusercontent.com/timescale/timescaledb/main/README.md
- S40 Grafana: https://raw.githubusercontent.com/grafana/grafana/main/README.md
- S41 OpenPLC v3: https://raw.githubusercontent.com/thiagoralves/OpenPLC_v3/master/README.md
- S42 4diac FORTE: https://raw.githubusercontent.com/eclipse-4diac/4diac-forte/develop/README.md
- S43 Akri: https://raw.githubusercontent.com/project-akri/akri/main/README.md
- S44 KubeEdge: https://raw.githubusercontent.com/kubeedge/kubeedge/master/README.md
- S45 Siemens Industrial Edge (search): https://www.siemens.com/en-us/products/industrial-edge/it-specialists/
- S46 Red Hat Device Edge: https://www.redhat.com/en/technologies/linux-platforms/enterprise-linux/edge-computing
- S47 MicroShift life cycle and image mode (search): https://access.redhat.com/node/7086005
- S48 Ubuntu Core 24 (search): https://canonical.com/blog/canonical-launches-ubuntu-core-24
- S49 Ubuntu Core docs and support duration: https://documentation.ubuntu.com/core/ , https://documentation.ubuntu.com/core/reference/support-duration/
- S50 Azure IoT Edge supported platforms: https://learn.microsoft.com/en-us/azure/iot-edge/support
- S51 Greengrass nucleus: https://docs.aws.amazon.com/greengrass/v2/developerguide/greengrass-nucleus-component.html
- S52 UNS (search, secondary): https://www.hivemq.com/blog/semantic-data-structuring-mqtt-sparkplug-unified-namespace-uns-smart-manufacturing/ , https://inductiveautomation.com/resources/article/uns-unified-namespace
- S53 ISA/IEC 62443: https://www.isa.org/standards-and-publications/isa-standards/isa-iec-62443-series-of-standards
- S54 Wind River standards (search): https://www.windriver.com/solutions/standards
- S55 NIST SP 800-82r3: https://csrc.nist.gov/pubs/sp/800/82/r3/final
- S56 CRA Annex III text from proposal (search): https://www.european-cyber-resilience-act.com/Cyber_Resilience_Act_Annex_3.html
- S57 Rugix (search): https://github.com/rugix/rugix
- S58 NERC CIP-015 (search): https://nerc.com/pa/Stand/Pages/Project202502InternalNetworkSecurityMonitoringStandardRevision.aspx , https://www.govinfo.gov/content/pkg/FR-2025-07-02/html/2025-12309.htm
- S59 FIDO Device Onboard (search): https://fidoalliance.org/device-onboarding/ , https://fidoalliance.org/specs/FDO/securing-fdo-in-tpm-v1.0-rd-20231010/securing-fdo-in-tpm-v1.0-rd-20231010.html
- S60 RevPi Connect 5: https://revolutionpi.com/en/revpi-connect-5
- S61 Kubernetes CPU management policies: https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/
- S62 Zephyr intro: https://docs.zephyrproject.org/latest/introduction/index.html
- S63 Zephyr safety: https://docs.zephyrproject.org/latest/safety/index.html
- S64 micro-ROS: https://micro.ros.org/
- S65 SIMATIC IOT2050: https://www.siemens.com/global/en/products/automation/pc-based/iot-gateways/simatic-iot2050.html
- S66 Yocto releases: https://wiki.yoctoproject.org/wiki/Releases
- Internal: `/Users/zeus/Desktop/ONEMINDOS/docs/ADR-001-foundation.md`, `/Users/zeus/Desktop/ONEMINDOS/research/platform/base-os-and-orchestration.md`
