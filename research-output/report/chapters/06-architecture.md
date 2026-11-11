# How everything connects {#sec-architecture}

> **Explain it like I'm the founder.** Read the picture from the bottom. A **device** (a sensor, a robot, a drone) joins a **node** (a box running the OneMind image). The image boots **k3s**, which runs the apps and the **NATS bus**. Every app declares what it can do, and the **capability gateway** turns that into tools that people and **AI agents** can use, only through the gateway, with approvals for anything risky. People reach it through the **dashboard and clients**; the **cloud** is optional and self-hostable. The **Marketplace** feeds signed apps and plugins in from the side.

![The OneMind layer cake (repeated from Chapter 1 for reference).](img/architecture.png){width=96%}

## The layers, mapped onto Olares's model (P-3) {#sec-layers}

Olares organises itself in five layers (infrastructure, platform, framework, built-in apps, community apps). OneMind keeps that shape and adds two layers Olares lacks: an owned OS underneath and a device-and-robot layer beside the platform (`01` §8).

| OneMind layer | What it is | Different from Olares because |
|---|---|---|
| **L0 · OS image** | Read-only A/B (RAUC) core image on Ubuntu 26.04 (decision of record, conditional on Z-01), with a Debian 13 leg until the base lock; signed releases, health gate, LUKS2 data; Jetson flavor on L4T | Olares has no OS rollback and only same-origin checksums [C-TD-olares-003, C-TD-olares-004] |
| **L1 · Cluster** | k3s (SQLite on one box, etcd at three servers), Flannel (Cilium on GPU/enterprise), Retain storage, Longhorn on 3+ nodes | Olares ships a Kubernetes minor past its end of life [C-TD-olares-022] |
| **L2 · Platform services** | NATS JetStream as the authority bus, object storage, restic backup agent, identity store | Each box has its own JetStream domain and leaf links [C-W4-054] |
| **L2b · Devices and robots** | MCP/MHS device adapters, ROS 2 bridge, MAVLink, MQTT 5 site bus bridged to NATS, TAK | Olares has none |
| **L3 · Framework** | `onemindd` update agent, Market controller, capability gateway, offline identity, Headscale/Tailscale | Default-deny egress (Olares has ingress-only policies [C-TD-olares-034]) |
| **L4 · App shell + modules** | Dashboard, files, alerts, settings, map, family, finance, wellness, robotics, mesh/IoT, OSINT, education | Each module is also a Market app (D-003) |
| **L5 · Market** | Helm + `onemind.app.yaml`, public linter, signed publishers, Compose importer | Trust by signature, never by image name: Olares's linter exempts any image path containing "beclab/" [C-TD-olares-030] |

## Why Kubernetes at all, and where it stops {#sec-why-k8s}

The two most-used self-hosting appliances run Docker, not Kubernetes [C-W4-043, C-W4-044], and on a relaxed scorecard Compose ties k3s (`05` §1). Kubernetes still wins for OneMind because the same app contract must run from a Pi to a GPU cluster with GitOps, multi-node placement and GPU scheduling, which is your existing cluster's whole stack. **The cost is measured:**

![k3s on a 4 GiB arm64 box: about 0.9 GiB idle, 1.5 GiB under load, 2.5 GiB left for apps.](img/chart-k3s-footprint.png){width=78%}

k3s added 936 MiB at idle and 1,529 MiB under load on a 4 GiB arm64 VM [C-LAB-k3s-footprint-restore-007, C-LAB-k3s-footprint-restore-008]; with an app running, 2.50 GiB stayed free and writes were about 2.75 GB/day [C-W4-078]. So:

| Node class | Rule | Why |
|---|---|---|
| **Platform node** (≥ 4 GB RAM **and** SSD/NVMe; 8 GB recommended) | Runs k3s; 4 GB boxes run a slim profile sold as a profile (TAK node, greenhouse) | Measured footprint above |
| **Capturable field node** (robots, field kits) | **k3s agent only**: no API server, no datastore, no admin credentials on disk | A k3s server holds every Secret; Kubernetes assumes physically secure nodes [C-REF-W4-security-008] |
| **Pi as a cluster server** | Never the server of a cluster that holds GPU-tier or fleet secrets | A Pi has no TPM, and k3s keeps its encryption key in a plain file [C-REF3-DC-security-008] |
| **Below 4 GB or SD-only** | **NATS leaf** with store-and-forward, plus an MCP/MHS adapter | 600/600 messages survived an outage [C-W8-050] |
| **Regulated / AI-conformant GPU cluster** | RKE2, only when a buyer needs it | RKE2 is on the AI-conformance list; k3s is not [C-W4-038] |

**What competitors run (constraint fit):**

| Product | App runtime | Smallest box | Kubernetes? | Constraint fit with OneMind |
|---|---|---|---|---|
| Home Assistant OS | Docker via the Supervisor [C-W4-044] | Pi-class (HA Green) | No | Partial: appliance UX and Pi target match; no multi-node, GPU scheduling or robots |
| umbrelOS 2.x | Docker Compose read and written by `umbreld` [C-W4-043] | Pi 5 class | No | Partial: single box only |
| Olares | k3s with external etcd and add-ons disabled [C-W4-041] | 8 GB RAM; Pi 4B/5 8 GB only [C-W4-042] | Yes | Closest on platform, but an 8 GB floor and no A/B image |
| Your DOKS cluster | Managed Kubernetes + Argo CD (`context/01`, reported) | Cloud nodes | Yes | Exact on software, wrong on hardware and hosting |

**Other platform choices:** ingress through Gateway API with Traefik (ingress-nginx is unmaintained since March 2026 [C-W4-016]); about 8–10 Kubernetes minor upgrades to 2036, never skipping one, each preceded by a datastore snapshot [C-W4-012]; apps never depend on k3s-only features, because TrueNAS left Kubernetes for Docker in 24.10 [C-DEC-007].

## The NATS bus: one nervous system from sensor to cloud {#sec-nats}

![Every site has its own hub; small devices and robots are leaves; the cloud is a leaf or mirror. The subject grammar is locked.](img/nats-topology.png){width=86%}

NATS JetStream is the authority bus, as on your cluster today. Each box runs its own JetStream domain; devices, robots and the cloud connect as leaf nodes that buffer through outages, but only for subjects captured by a stream on the leaf [C-W8-050]. The CNCF keeps NATS under Apache-2.0 after the 2025 licence dispute [C-W4-056]. The locked subject grammar (`tel.*`, `det.*`, `evt.*`, `cmd.*`, `intel.*`, `ent.*.state`, `svc.*`, `tak.cot.*`) becomes the OS's published **bus contract**, and plugins get NATS permissions only inside it (E7).

## Robots, drones, IoT and TAK on the bus {#sec-devices}

![A real robot has three brains. OneMind owns the thinking brain and hosts the body brain; it never replaces the reflex brain.](img/robot-brains.png){width=90%}

- **Robots:** ROS 2 runs **in containers** on every flavor, because ROS 2 does not officially support Debian and its newest release does not support Jetson's Ubuntu 24.04 [C-W7-026, C-W7-027]; NVIDIA itself recommends containers for Isaac ROS. ROS 2 stays local to each robot; NATS links robots to the box (`08` §11.3). Fast DDS shared memory needs host IPC and network, so signed robot apps get a narrow, allowlisted exception [C-W7-033].
- **Drones:** PX4 (BSD-3) or ArduPilot (GPL-3.0) on the flight controller [C-LIC-047]; the OneMind Jetson or Pi is the companion computer with a MAVLink-to-NATS gateway. PX4's DDS link is unauthenticated, so it never crosses Wi-Fi or a VPN [C-W7-044].
- **IoT and IIoT:** Home Assistant for consumer radios; protocol adapters (OPC UA, Modbus, Sparkplug B) publish into a unified namespace on NATS, with an MQTT 5 broker bridged in (Chapter 3).
- **TAK:** TAK Server runs as an app; CoT flows in and out through `tak.cot.inject` and `tak.cot.>`; field devices reach it over the tailnet.

## The NVIDIA toolbox on k3s, and the lock-in guard {#sec-nvidia-k8s}

| Component | Supports Jetson? | Supports Debian? | Supports k3s? |
|---|---|---|---|
| Driver + Container Toolkit | In JetPack | Yes [C-W4-026] | n/a |
| k8s device plugin | Yes | Not OS-specific | Yes [C-W4-029] |
| GPU Operator | **No** (discrete GPUs) | **Not listed** | Listed [C-W4-022] |
| DRA driver, KAI Scheduler | Not stated | n/a | Needs DRA [C-W4-030, C-W4-034] |
| AI Cluster Runtime (AICR) | No | **No** | **No** (RKE2, k0s, Talos yes) [C-W4-037] |
| HAMi GPU sharing | No | n/a | Yes [C-W4-036] |

**Lock-in guard (F-2, F-6):** apps declare accelerator *capabilities*, not vendor resources; models ship as ONNX plus per-backend engines. The same manifest must run on a Rockchip RK3588 (mainline NPU driver since Linux 6.18 [C-W7-049]), a Pi with Hailo [C-W7-053], or an x86 GPU. Google Coral is avoided for new SKUs: its repository has been archived since 2021 [C-W7-050].

## Converting your DigitalOcean cluster {#sec-doks}

![Six phases. Backups are the moving van; the bus authority flips last.](img/doks.png){width=100%}

Principles: never move the authority twice; one app at a time; test with the internet unplugged before each cut-over. The DOKS cluster ends as the **OneMind Cloud / Omni tier**: relay, off-site backups, image build and signing CI, the update server and Backstage (`05` §9). Hermes gets a body on the box only after the bus flips (AI-9).

**Requirements served:** N-2, N-3, N-5, N-6, N-8, N-9, P-2, P-3, P-9, AI-8, AI-9, M-7, F-2, F-6, F-14.
