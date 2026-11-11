# W4 runner-up steelman: Docker + Compose without Kubernetes, the HAOS and Umbrel way

- **Role:** runner-up steelman (RESEARCH-MISSION.md §2 rule 7). This agent was told to argue **for** the runner-up. It is advocacy held to the evidence rules. Every fact below was opened on 2026-11-10, or is taken from this repo's claims ledger (cited by claim ID), or is labelled SECONDARY, vendor-stated or UNVERIFIED. The honest weaknesses are in §10.
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (Docker, Compose, k3s and Kubernetes facts: 6 months); 2027-11-10 (adoption counts and vendor commitments: 12 months)
- **Verdict:** `steelman`
- **Decision under test:** ADR-001 **D4** ("k3s on every tier; RKE2 for the hardened tier") as refined in `05-kubernetes-cluster-conversion-nvidia.md` (P0-1, P0-2, §1.4, §2.4). The runner-up argued here is **Docker Engine (Moby) + the Compose Specification as the only app runtime on every OneMind box**, with multi-box and multi-site coordination done by a OneMind controller over NATS. Kubernetes is offered only as an *export target* for customers who already run a cluster. It is not shipped inside the OS.
- **Serves requirements:** N-9, F-11, F-14, M-6, M-7, N-7, N-8, F-2, R-1, R-3, U-4, UX-6, P-9, D-001

> ### Explain it like I'm the founder
> Your box needs a way to run apps. There are two options. **Kubernetes (k3s)** is a small datacenter control system: an API server, a database of desired state, controllers that keep reconciling it, and certificates between all of them. **Docker + Compose** is a container engine plus one YAML file per app that says "run these containers, with these disks, ports and devices". Home Assistant (about 578,000 opted-in boxes) and Umbrel use the second. Olares uses the first and needs 8 GB of RAM.
> The case for Compose is simple. Our own lab measured k3s costing about **1 GB more RAM and about 39 times the disk writes** of a plain container engine running the same two apps. It has to be upgraded through **8 to 10 Kubernetes versions** before 2036, in order and without skipping, on boxes that may be offline. Its rollback needs a database snapshot. NVIDIA's robotics stack (Isaac ROS, Jetson containers) is documented on **Docker**, not Kubernetes. Industrial edge platforms (Siemens Industrial Edge, AWS Greengrass, balena) ship apps as **Compose files**. In those cases the fleets are managed by a fleet service, not by a cluster on each device.
> The catch, covered in §10, is real. Big GPU clusters, NVIDIA's data-centre AI tools and your existing Helm/Argo work are Kubernetes-native. With Compose, OneMind would have to write its own multi-machine scheduler, and that risks rebuilding Kubernetes badly.

---

## 1. The claim this steelman makes

> **For every box OneMind sells or installs (Edge, Lite, Pro, Robotics), Docker Engine + Compose is a better ten-year app runtime than k3s. It wins on IoT/IIoT device access and proven fleets (F-11), on reaching the true Pi end of "one OS" (F-14), on having no forced control-plane upgrade treadmill to 2036 (R-3), on fit with NVIDIA's robotics tooling (M-7, N-7), on attack surface (U-4) and on what one developer can operate (M-6). The ADR keeps Compose out with a single gate (G5), and the W4 draft has already broken G5's literal reading for itself.**

## 2. The W4 draft's own evidence already favours Compose on boxes

Every row below is from `05-kubernetes-cluster-conversion-nvidia.md` or its claims. Nothing here is new evidence. The point is what the draft's numbers say when you read them without the G5 gate.

| Draft fact | Where | What it means for the decision |
|---|---|---|
| With gate G5 relaxed, **Docker/Compose scores 64 and k3s 63**. Compose takes the only **5 in C4** (proven in production: HAOS + umbrelOS, constraint-matched, code-confirmed) | §2.2, §2.3 ("G5 (F-14) is the single gate that keeps Compose out") | On the frozen weights Compose is the **top-scoring option**. The whole decision rests on how G5 is read (§3). |
| Lab W4-1: same two apps, **Podman 3,513 MiB available vs k3s 2,557 MiB**. Writes **0.07 GB/day vs 2.75 GB/day**. k3s idle alone writes 1.89 GB/day | §1.3, C-W4-076, -077, -078 | About **0.95 GiB of RAM and about 39× the flash writes** go to the platform itself, not to apps. On a 4 GB Pi that is about 24% of RAM. |
| k3s docs: SD cards and eMMC "cannot handle the IO load"; an SSD is required on Pi/ARM | C-W4-002 | k3s **turns the cheapest Pi SKU (SD-only) into an unsupported platform node**. Docker on SD is what HAOS ships on Pi 3/4 (§5). |
| A 30 s SQLite checkpoint stall caused API-server timeouts on a 2 vCPU / 4 GB node | C-W4-069 | This failure mode doesn't exist without an API server and datastore. |
| **8–10 forced Kubernetes minor upgrades** per box to reach 10 years. No skipping. Rollback only from a snapshot taken on the older version | P0-3, C-W4-009, -010, -012, -014 | This is the draft's own "main long-term cost". Compose has no equivalent (§6). |
| A/B OS rollback across a k3s minor boots an older k3s against a newer datastore, which k3s refuses. The draft needs a special snapshot-restore hook or a separate update layer | §3.3 (input to DC-12) | k3s **breaks the clean A/B story** that W3 is built on. Docker volumes and Compose files have no schema version tied to the engine. |
| SUSE's k3s/RKE2 support matrix **does not list Debian** | P0-4, C-W4-013 | The chosen base OS has no commercial support for k3s from the k3s vendor. |
| NVIDIA's validated Kubernetes stack (GPU Operator, AICR, AI conformance) **does not cover Debian or k3s**. GPU Operator does not support Jetson | P0-5, P0-7, C-W4-021…-029 | On OneMind's actual tiers, k3s gets **none** of NVIDIA's Kubernetes value. GPU access comes down to driver + Container Toolkit + device plugin, and Docker uses the same toolkit (§7). |
| Devices under 4 GB "join as NATS leaf nodes", not Kubernetes nodes. "Below that line, the 'one OS' promise is kept by the bus, not by Kubernetes" | P0-1, §1.4 | The draft **already accepts** that one OS does not need one orchestrator (§3). |
| Multi-site: "**never stretch one cluster across sites.** Each site is its own cluster … sites connect through NATS leaf links" | §3.1 | At fleet scale the draft's topology is **many independent units joined by NATS**. A Compose unit fits that topology just as well. |
| k3s minimum is 2 GB for a server; Olares, the only k3s competitor, requires **8 GB** | C-W4-001, -042 | — |

## 3. G5 is mis-specified, and the draft already admits it

- **N-9 is an open question, not a requirement for Kubernetes.** The text reads: "Decide whether to stay with native Kubernetes (k8s/k3s) over Docker-only … To be decided from research" (`docs/REQUIREMENTS.md` N-9). The research is free to choose Compose.
- **F-14 is a user-experience promise:** "the user never switches products" and "the experience stays simple while capability scales". It does not say "the same orchestrator binary on every device". The draft reads it the same way when convenient. Sensors, drones and Pi Zero-class devices are kept inside "one OS" through NATS + an MCP/MHS adapter + systemd, with no Kubernetes (§1.4). If F-14 survives a Kubernetes-free tier there, it survives a Kubernetes-free tier on a 4 GB Pi too.
- **The real contract across tiers in the draft is already three things:** the `onemind.app.yaml` app format (D-003), the NATS subject grammar and bus, and the dashboard. None of them is Kubernetes. The steelman's design (§9) keeps all three identical on every tier. Only the runtime under the app format changes, and on every box OneMind sells there is just one runtime: Compose.
- **Two management planes is a false choice.** The draft's G5 fail for "tiered mix" counts a k3s plane plus a Compose plane. The pure runner-up has **one** plane on every box (Compose, driven by the OneMind controller). Kubernetes appears only when a customer already owns a cluster, and then it is *their* plane: OneMind emits manifests into it (Compose Bridge "converts your Docker Compose configuration into platform-specific deployment formats … by default … Kubernetes manifests and a Kustomize overlay", docs.docker.com/compose/bridge/, opened 2026-11-10; Kompose is listed as a Compose Spec implementation, github.com/compose-spec/compose-spec README).

## 4. F-11 IoT and IIoT: where Compose wins most clearly

### 4.1 The biggest device-integration fleet in the comparison set runs on Docker

`https://analytics.home-assistant.io/data.json`, fetched 2026-11-10 (`current.last_updated` 1794315298662 = 2026-11-10 12:54 UTC; opt-in, so these are lower bounds):

| Metric | Value |
|---|---|
| Active installations | **727,232** |
| `installation_types.os` (HAOS: Docker under the Supervisor) | **577,938** |
| `installation_types.container` (plain Docker) | 129,629 |
| Integration `mqtt` | **278,341** |
| Integration `bluetooth` | 280,504 |
| Integration `matter` / `thread` | 240,380 / 218,830 |
| Integration `esphome` | 157,919 |
| Integration `zha` (Zigbee) | 145,954 |
| Integration `zwave_js` | 46,776 |
| Integration `modbus` (industrial fieldbus) | **19,216** |
| Integration `knx` (building automation) | 9,141 |

**Reading it:** about **97% of opted-in Home Assistant installs** (HAOS + Container, 707,567 of 727,232) talk to Zigbee, Z-Wave, Bluetooth, Thread, Modbus and KNX hardware **from Docker containers**. No product in the W4 comparison has done consumer-plus-light-industrial device integration at this scale on Kubernetes. That includes the founder's DOKS cluster and Olares.

### 4.2 Host devices: a Compose field compared with a Kubernetes plugin you must ship

- **Docker / Compose:** `devices:` and device cgroup rules are first-class. The Home Assistant Supervisor grants hot-plug access by **device-cgroup rule per class**: serial `ttyAMA/ttySAC` (major 204), `ttyUSB` (188), `ttyACM` (166), `/dev/bus/usb` (189), plus GPIO and Bluetooth, with dynamic majors from udev (`home-assistant/supervisor@040f14cd8aa2902401d30aaeb0cb71215854c78c:supervisor/hardware/policy.py` L15–L106). That lets a user **plug in a Zigbee or Modbus-RTU dongle after the app started** and the app sees it. That is what F-11's greenhouse and farm users will do.
- **Kubernetes:** the Pod API has no `--device` equivalent. The 2015 issue "add support for host devices" (`kubernetes/kubernetes#5607`, opened 2015-03-18, closed 2018-03-03, 90 comments) ended with the **device-plugin API** as the answer. As late as 2021 the thread notes mounting `/dev/fuse` "without `privileged:true`" was not possible except through a device manager. On k3s OneMind would have to ship and maintain a third-party plugin (`squat/generic-device-plugin`, 416 stars, last push 2026-11-09) or **Akri** (`project-akri/akri`, still pre-1.0: v0.14.0, 2026-09-01). The other choice is running IoT apps `privileged`, which defeats U-4.
- **Plain reading:** for the F-11 device classes (serial, USB, GPIO, CAN, Bluetooth), Compose needs **zero extra components**. k3s needs **one more pre-1.0 or single-maintainer component on the critical path**, or privileged pods.

### 4.3 Industrial edge platforms ship apps as Compose files and manage fleets from outside the device

| Platform | App unit on the device | Evidence |
|---|---|---|
| **Siemens Industrial Edge** | A Docker Compose app imported into the Industrial Edge App Publisher and deployed by Industrial Edge Management | `github.com/industrial-edge/hello-world` (org linked to new.siemens.com, Siemens CLA): ships `docker-compose.yml` and `docker-compose-arm64.yml`, needs "Docker Compose V2.4", "Docker Engine 27.0", "Industrial Edge App Publisher (IEAP) V1.27.9". **SECONDARY for the general rule:** the official IEAP operation manual was not opened, so "all IE apps are Compose" is UNVERIFIED beyond these Siemens-org repos. |
| **AWS IoT Greengrass v2** | A component whose run step is `docker-compose … up`; Docker Engine "up to and including 29.6.0" supported | `docs.aws.amazon.com/greengrass/v2/developerguide/run-docker-container.html` (opened 2026-11-10) |
| **balena** | "The multicontainer functionality provided by balena is built around the Docker Compose file format"; the device supervisor "implements a subset of the Compose v2.1 feature set" | `docs.balena.io/learn/develop/multicontainer/` (opened 2026-11-10) |

**Why this matters for F-11 ("fleets of thousands"):** none of these industrial fleets runs a control plane *on the device*. They run a container engine on the device, plus a fleet manager (IEM, Greengrass, balenaCloud) that pushes desired state. The pattern is "single-node runtime + external fleet manager", and OneMind already has the transport for it: NATS leaf links that dial out, with store-and-forward proven in lab W8-1 (C-W4-054, -055). Kubernetes adds nothing to a 1-node fleet member except its own upkeep.

### 4.4 IEC 62443 and real time

- The draft concedes that hard real time sits **off Kubernetes** (§1.6 robotics row; W7). The same isolated-cores/PREEMPT_RT setup works the same way under Docker (`cpuset`, `--cpu-rt-runtime`, `--ulimit rtprio`), and balena's documented Compose subset includes `ulimits` and `cap_add` (balena page above).
- IEC 62443-4-2 component requirements reward a **minimal, enumerable** attack surface (see §8). A box with no API server, datastore or kubelet has fewer components to document. UNVERIFIED: no 62443 certificate for either runtime was found in this pass.

## 5. F-14: the Pi end of "one OS" is real only with Compose

| Device | Docker/Compose evidence | k3s evidence |
|---|---|---|
| Raspberry Pi 3 (1 GB) | HAOS `rpi3-64` board: **10,136** opted-in installs (analytics `operating_system.boards`, per W3 steelman §2.1, same data.json) | Below the 2 GB server minimum (C-W4-001) |
| Pi 4 / Pi 5 on SD card | HAOS `rpi4-64` 78,086 · `rpi5-64` 47,615 (same source) | "SD cards and eMMC cannot handle the IO load" (C-W4-002) |
| HA Green (RK3566, eMMC) | **78,470** installs, Home Assistant's own hardware | eMMC called out as unsuitable (C-W4-002) |
| 4 GB Pi 5 | Lab: container engine + app leaves 3,513 MiB of 3,923 | Lab: k3s + app leaves 2,557 MiB (C-W4-078); marketed by the draft only as a "TAK node / greenhouse profile" |
| 8 GB+ box | Same runtime | Olares' floor (C-W4-042) |

So the draft's own "one OS" already **starts at 4 GB on NVMe**. Everything below that becomes a "leaf device", not a OneMind box. With Compose, the **same OneMind OS, Market and dashboard** run from a 1 GB Pi 3 upward, as HAOS shows on 10k+ such boards. That is a stronger reading of "as simple as setting up a Raspberry Pi" (F-14) than the ADR's.

**Scaling up without a product switch:**
1. **One box:** Compose.
2. **Several boxes in a household (UX-6):** each box runs its own Compose apps; the OneMind controller places apps by NodeCapabilities (D-002) and moves them by stop → sync volume → start, over NATS. This is the same model as Siemens IEM, Greengrass and balena (§4.3). **Optional:** Docker Swarm mode is built into Moby (`moby/swarmkit` not archived, last push 2026-11-03), and Mirantis says "Swarm will be fully supported through at least 2030 as part of Mirantis Kubernetes Engine 3" (mirantis.com blog, 2025-07-01).
3. **Many sites:** the draft's topology unchanged: each site a unit, NATS leaf links between them (§3.1).
4. **Customer GPU clusters (Omni/Cluster):** OneMind is an app source for the customer's own Kubernetes or Slurm. The same `onemind.app.yaml` is compiled to Compose for boxes, or to Kubernetes manifests through Compose Bridge/Kompose. The user keeps one Market and one dashboard.

## 6. Longevity to 2036

| Axis | Docker + Compose | k3s |
|---|---|---|
| Format stability | Compose v2-syntax files still run today. ROS 2's own docs (`ros2/ros2_documentation@8eceaa71ddb010b61b48f56639f74eaf37e06d55:source/Developer-Tools/Build/Run-2-nodes-in-single-or-separate-docker-containers.rst` L93–L109) ship a `version: '2'` file run with `docker compose up` | API removals with the deprecation policy; 3 minors per year, about 1 year of patches each (C-W4-014) |
| Format governance | Compose Specification: **Apache-2.0**, with Docker Compose as reference implementation. Also implemented by Kompose, nerdctl, Podman Compose, Okteto, Google Cloud Run Compose and Compose Bridge (`github.com/compose-spec/compose-spec` README). **No single vendor can strand it.** | Kubernetes API: CNCF. The *distribution* is single-vendor (SUSE) |
| Engine license | Moby **Apache-2.0** (`gh api repos/moby/moby/license`); Docker Compose Apache-2.0; Engine is "Apache License, Version 2.0" (docs.docker.com/engine/install/) | Apache-2.0 (C-W4-075) |
| Engine age and activity | Docker Engine since 2013; current `docker-v29.9.3` (2026-11-03); Compose `v5.7.0` (2026-11-02) | k3s since 2019; v1.37.2+k3s1 (C-W4-011) |
| Forced upgrades for an offline box | None structural. A container engine has no persisted cluster schema; the box keeps running old Compose files after any number of skipped releases | Must step every minor in order; downgrade refused; rollback needs a pre-upgrade snapshot (C-W4-009, -010) |
| Upgrade inside A/B | The engine is just a file in the image; an OS rollback rolls the engine back too, and volumes and Compose files are unaffected | Needs a special hook so a rollback across a minor doesn't strand the datastore (draft §3.3) |
| Time bombs on a box that runs for years | None found | k3s "client and server certificates are valid for 365 days" and renew "every time K3s starts" if they are within 120 days of expiry. The self-signed CA certs "are valid for 10 years … and are not automatically renewed" (`k3s-io/docs@8958508:docs/cli/certificate.md` L9–L10, L73). A box first booted in 2026 meets CA expiry in **2036**, and a box that is never restarted for a year has expired leaf certs. Both can be handled, but only Kubernetes needs handling for them. |
| Commercial support for the base | The Compose path has no vendor matrix to fall out of | SUSE matrix excludes Debian (C-W4-013) |

## 7. Robotics, drones and physical AI (M-7, N-7, N-8, F-2)

- **NVIDIA's robotics stack is documented on Docker.** Isaac ROS getting-started (nvidia-isaac-ros.github.io/getting_started/, opened 2026-11-10): "Docker is the recommended option for most users. It provides the highest level of isolation from your host system." On DGX Spark, "Docker and NVIDIA Container Toolkit are already configured". The page does not mention Kubernetes. Supported: Jetson Thor/Orin on JetPack 7.2, x86 on Ubuntu 24.04.
- **The Jetson container ecosystem is Docker.** `dusty-nv/jetson-containers` runs `docker run --runtime nvidia … --network=host` and `jetson-containers run` "launches docker run with some added defaults (like --runtime nvidia …)". It tests JetPack 6.2 and 7. Its README does not mention Kubernetes.
- **GPU in Compose is a documented, stable field:** `deploy.resources.reservations.devices` with `driver: nvidia`, `count` or `device_ids`, `capabilities: [gpu]` (docs.docker.com/compose/how-tos/gpu-support/). The NVIDIA Container Toolkit lists Docker as a supported engine and covers Debian through apt (NVIDIA install guide, opened 2026-11-10). On Jetson, the draft's own path (L4T + toolkit + device plugin, P0-7) is the Docker path plus a Kubernetes plugin on top.
- **ROS 2 / DDS networking is easier without a CNI.** DDS discovers over multicast. eProsima's DDS Router docs choose a Discovery Server in the cloud because of "the difficulty of enabling multicast routing in cloud environments" (eprosima-dds-router.readthedocs.io stable, `use_cases/ros_cloud`). Canonical's ROS 2-on-Kubernetes posts end up at `hostNetwork` (SECONDARY, canonical.com/blog/exploring-ros-2-kubernetes-configurations, found by search, not opened). On a robot every perception container runs host-network anyway, which removes most of what a CNI, Services and ingress would add.
- **Drones and robots are single-machine, power-limited computers.** A control plane that writes about 1.9 GB/day at idle (C-W4-077) and keeps reconciling burns flash and watts for scheduling decisions that never change on a robot with fixed hardware.

## 8. Security

- **Less to attack.** No kube-apiserver, no datastore holding every secret, no kubelet API, no service-account token system, no RBAC to misconfigure. The official Kubernetes CVE feed lists **27 CVEs in 2025–2026** (kubernetes.io/docs/reference/issues-security/official-cve-feed/, opened 2026-11-10). In fairness, **most are ingress-nginx**, which k3s does not ship. The core-cluster ones are still part of what a k3s box carries and a Compose box doesn't: CVE-2025-4563 (nodes bypass DRA authorization), CVE-2025-0426 (kubelet checkpoint DoS), CVE-2025-5187 (nodes delete themselves via OwnerReference), CVE-2026-2270 (StatefulSet/ControllerRevision write → cross-namespace pod creation).
- **Proven isolation model on appliances.** HAOS runs every add-on as a Docker container with per-add-on AppArmor and the device-cgroup policy above (§4.2). That is the same per-app isolation U-4 asks for, already in the field at about 578k boxes.
- **Rootless is available.** In rootless mode "both the daemon and the container are running without root privileges" inside a user namespace (docs.docker.com/engine/security/rootless/). k3s also has a rootless mode, so this is parity, not an advantage. It does remove the "root daemon" objection.
- **CRA (Regulation (EU) 2024/2847):** a smaller runtime means a shorter SBOM and fewer components to track for vulnerability handling from 2027-12-11 (dates per `07-security-compliance.md`).

## 9. Solo-developer operability (M-6) and the concrete runner-up design

**Operability evidence:**
- **Umbrel's App Store is about 398 Compose apps** (top-level app directories in `getumbrel/umbrel-apps@678cb037a0de50b1c9012534ba41b5d372cf9efb`, dot-folders excluded; a few may be non-app folders), run by `umbreld` reading and writing `docker-compose.yml` (C-W4-043). A small company maintains a Market of that size on Compose.
- **Every self-hosted app already ships a Compose file**, so a OneMind Market on Compose can take in the existing ecosystem with almost no translation. On k3s, each app needs a Helm chart or a generated manifest set that OneMind must test.
- **Fewer failure classes to debug alone:** no datastore stalls (C-W4-069), no order-of-operations traps on secrets encryption (C-W4-070), no cgroup-version crash-loops in the control plane (C-W4-071), no cert rotation, no minor-version skew.

**What OneMind would build (keeping ADR D1–D3, D5, D6):**
1. **Image:** unchanged (Debian 13 + A/B per W3). Ship upstream Moby + Compose v2 in the image, pinned and rebuilt with each OS bundle (see §10 item 6 for why not Debian's `docker.io`).
2. **App format:** `onemind.app.yaml` stays the source of truth. Its runtime section is a Compose Spec document, plus OneMind capability declarations (accelerator, devices, NATS subjects).
3. **Controller:** `onemindd` (the HA Supervisor / `umbreld` pattern) installs apps, owns devices and backups, and reports health. Desired state arrives over NATS from the dashboard or from a fleet hub, the same way IEM, Greengrass and balena work.
4. **Multi-box:** placement by NodeCapabilities, with migration done as backup → restore. Swarm is kept as an optional later add-on, not a dependency.
5. **Cluster export:** a `onemind export --k8s` target (Compose Bridge/Kompose-based) for customers with Kubernetes, and for the founder's DOKS hub during migration.
6. **Health gate for A/B (W3):** "good" = Docker up + OneMind core containers healthy. That is simpler than waiting for k3s + core pods.

### 9.1 Re-scoring with G5 read as the user-experience promise (§3)

The draft's S3 cells are unchanged except where this steelman brings new primary evidence:

| Criterion (weight) | Draft Compose | Steelman Compose | Draft k3s | Reason |
|---|---|---|---|---|
| C1 lifecycle (20) | 3 | **4** | 3 | No minor-version treadmill; Apache-2.0 spec with 7+ implementations (§6) |
| C2 hardware (20) | 3 | 3 | 3 | Same NVIDIA toolkit path; Isaac ROS documents Docker (§7). Lacks k8s-native NVIDIA tools (§10) |
| C3 rollback (15) | 1 | **2** | 1 | The engine and its state roll back inside the A/B slot, with no datastore schema to strand (§6) |
| C4 proven (15) | 5 | 5 | 4 | — |
| C5 solo operability (10) | 4 | 4 | 4 | — |
| C6 openness (10) | 4 | 4 | 4 | — |
| C7 ecosystem (10) | 3 | 3 | 4 | — |
| **Total** | 64 | **71** | 63 | Even keeping the draft's scores, Compose leads once G5 is read as in §3 |

The re-score is advocacy. The move from 64 to 71 rests on two judgement calls (C1, C3), each argued with the evidence in §6. The decisive point does not depend on them: **at the draft's own scores, Compose is the top option on every box once G5 is read the way the draft itself reads it for sub-4 GB devices.**

## 10. Genuine weaknesses (stated plainly)

1. **Large GPU clusters and the Omni/Cluster tier are Kubernetes country.** NVIDIA's data-centre stack (GPU Operator, DRA driver, KAI Scheduler, Dynamo, AICR, NIM Operator) is Kubernetes-native (C-W4-021…-038). F-2 says "keep pace with NVIDIA … the Kubernetes GPU stack". The "export to the customer's cluster" answer turns OneMind into a guest on that tier instead of the OS. That weakens F-14 at the top end exactly as the ADR's design weakens it at the bottom.
2. **OneMind would have to build its own multi-machine scheduler.** Placement, failover, rolling updates, health-based restarts across nodes, service discovery and multi-user isolation all come free with Kubernetes and must be written by hand for Compose. For one developer (M-6) this risks **rebuilding a worse Kubernetes over 10 years**. HAOS and Umbrel never solved multi-node at all (draft §1.1). Swarm support is promised only "through at least 2030" and tied to Mirantis' MKE 3 product.
3. **The founder's assets and stated intent are Kubernetes.** The DOKS cluster (P-9) is Helm + Argo CD with about 250 pods. Context/01 records the founder saying "Kubernetes stays the long-term application substrate. Not every sensor must run Kubernetes." Compose means porting those charts *down*, and Compose Bridge goes only Compose → Kubernetes, not the other way. GitOps, declarative reconciliation and Argo patterns have no Compose equivalent that is as mature.
4. **The closest platform competitor chose k3s.** Olares, which is the most similar on multi-user, Market and GPU sharing, runs k3s (C-W4-041). The Compose winners (HAOS, Umbrel) are single-box products. OneMind's M-4/UX-6 scope is Olares-shaped.
5. **Multi-user isolation (U-4, Olares as benchmark)** maps naturally onto Kubernetes namespaces, NetworkPolicy and RBAC. On Compose it falls to OneMind's own controller plus AppArmor/userns.
6. **The Docker Engine has no LTS, and Debian's package lags.** Docker states it "doesn't support Docker Engine directly"; the Moby maintainers and community do, and no support period is published (docs.docker.com/engine/install/). Debian 13 ships `docker.io` 26.1.5 and the security tracker shows several 2024–2026 Moby CVEs as **"vulnerable (no DSA)"** for trixie (security-tracker.debian.org/tracker/source-package/docker.io, opened 2026-11-10). OneMind would have to track upstream Moby itself, which is a treadmill of its own, though one without schema migrations. The Docker daemon's root socket is also a large blast radius unless rootless is used.
7. **Compose isn't free of format churn.** Compose v1 (Python) was replaced by v2 (Go plugin), and implementations support different subsets (balena: "a subset of the Compose v2.1 feature set"). OneMind would have to pin and test its own subset.
8. **Docker Inc. is a commercial company.** Desktop licensing and Hub pull limits show it changes terms. The Moby engine and Compose Spec are Apache-2.0, so this is a fork-ability risk, not a lock-in, but it is real.
9. **Evidence gaps in this steelman:** Siemens IE is evidenced from Siemens-org example repos, not the official manual. ROS docs on docs.ros.org were behind a bot wall (`UNVERIFIED (blocked)`; the GitHub source at a pinned SHA was used instead). The NVIDIA NIM getting-started page returned empty, so no NIM claim is made. No Pi-silicon measurement was taken; the lab is a VM.

## 11. What evidence would flip the decision toward Compose (or confirm k3s)

| If this is found | Then |
|---|---|
| Real Pi 5 4 GB on NVMe: k3s slim + OneMind core + one app leaves < 2 GiB, or writes > 5 GB/day (the draft's own flip rule, §1.5) | Compose on every box OneMind sells; Kubernetes only as an export target |
| A spike shows offline boxes 2+ minors behind can't be brought current safely without manual work | Compose on consumer tiers |
| Market spike: one `onemind.app.yaml` compiles cleanly to both Compose and Kubernetes manifests, and the 20 most-used Market apps pass both | The cost of the Compose path (item 3 above) disappears; Compose is the default |
| The F-11 device spike needs a privileged pod or a pre-1.0 plugin for serial/USB/CAN hot-plug on k3s | F-11 weighs toward Compose |
| Conversely: a OneMind household needs cross-node failover, or the Omni tier needs DRA/KAI on the box itself | k3s is confirmed and this steelman loses |

---

## Sources (all opened 2026-11-10 unless marked)

| Source | Type |
|---|---|
| `research-output/05-kubernetes-cluster-conversion-nvidia.md` §0–§3, §12–§13 and `evidence/claims/W4.csv` (C-W4-001…-081) | Internal (draft under test) |
| https://analytics.home-assistant.io/data.json (`current`, last_updated 1794315298662) | PRIMARY (data) |
| https://github.com/home-assistant/supervisor/blob/040f14cd8aa2902401d30aaeb0cb71215854c78c/supervisor/hardware/policy.py#L15-L106 | PRIMARY (code) |
| https://github.com/kubernetes/kubernetes/issues/5607 | PRIMARY (issue) |
| https://github.com/squat/generic-device-plugin · https://github.com/project-akri/akri/releases/tag/v0.14.0 | PRIMARY-METADATA |
| https://github.com/industrial-edge/hello-world | PRIMARY (Siemens-org example); general rule SECONDARY |
| https://docs.aws.amazon.com/greengrass/v2/developerguide/run-docker-container.html | PRIMARY (docs) |
| https://docs.balena.io/learn/develop/multicontainer/ | PRIMARY (docs) |
| https://docs.docker.com/compose/how-tos/gpu-support/ | PRIMARY (docs) |
| https://docs.docker.com/compose/bridge/ | PRIMARY (docs) |
| https://docs.docker.com/engine/install/ · https://docs.docker.com/engine/security/rootless/ | PRIMARY (docs) |
| https://github.com/compose-spec/compose-spec (README) | PRIMARY |
| `gh api` moby/moby (release docker-v29.9.3, 2026-11-03; Apache-2.0), docker/compose (v5.7.0, 2026-11-02; Apache-2.0), moby/swarmkit (not archived) | PRIMARY-METADATA |
| https://www.mirantis.com/blog/mirantis-guarantees-long-term-support-for-swarm/ (2025-07-01) | PRIMARY (vendor-stated) |
| https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html | PRIMARY (docs) |
| https://nvidia-isaac-ros.github.io/getting_started/index.html | PRIMARY (docs) |
| https://github.com/dusty-nv/jetson-containers (README) | PRIMARY |
| https://github.com/ros2/ros2_documentation/blob/8eceaa71ddb010b61b48f56639f74eaf37e06d55/source/Developer-Tools/Build/Run-2-nodes-in-single-or-separate-docker-containers.rst | PRIMARY (docs source; docs.ros.org UNVERIFIED (blocked)) |
| https://eprosima-dds-router.readthedocs.io/en/stable/rst/use_cases/ros_cloud.html | PRIMARY (docs) |
| https://canonical.com/blog/exploring-ros-2-kubernetes-configurations | SECONDARY (search result, not opened) |
| https://kubernetes.io/docs/reference/issues-security/official-cve-feed/ | PRIMARY (feed) |
| https://github.com/k3s-io/docs/blob/8958508d493c12778517f2a178080f221cbe1081/docs/cli/certificate.md | PRIMARY (docs at SHA) |
| https://packages.debian.org/trixie/docker.io · https://security-tracker.debian.org/tracker/source-package/docker.io | PRIMARY |
| https://github.com/getumbrel/umbrel-apps/tree/678cb037a0de50b1c9012534ba41b5d372cf9efb (directory count) | PRIMARY (code tree) |
| `docs/REQUIREMENTS.md` (N-9, F-11, F-14, M-6, U-4, UX-6, P-9); `context/01` §1 item 1 | Internal |
