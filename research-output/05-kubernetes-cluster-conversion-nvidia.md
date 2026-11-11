# 05 · Kubernetes, cluster conversion and NVIDIA (W4)

**Workstream:** W4 (Tier A) · **Date:** 2026-11-10 · **Status:** draft for refutation · **Claims:** `evidence/claims/W4.csv` (C-W4-001 … C-W4-081) · **Sources:** `evidence/sources/W4.md` · **Question statuses:** `evidence/qbank/W4.md`
**Decision-critical questions owned:** DC-10 (k3s on every tier?) and DC-13 (NVIDIA drivers on Debian). **Inputs given to:** DC-12 (A/B ↔ k3s), DC-17 (one OS Pi → GPU cluster), DC-22 (platform first or image first), DC-23 (Talos/Kairos).
**Serves requirements:** N-9, N-8, N-2, N-3, N-5, N-6, F-2, F-6, F-14, P-9, P-2, P-5, M-4, M-6, M-7, AI-8, AI-9, R-1, R-3, U-5, UX-4, UX-6, A-1, A-5.
**Lab spike:** W4-1 "k3s vs Podman footprint on a 4 GiB arm64 node" (raw files in the W4 lab folder listed in `evidence/sources/W4.md`; criteria written before running).

> ### Explain it like I'm the founder
> Your DigitalOcean cluster already proves the *software* works: NATS, Argo CD, Authentik, TAK, Hermes. What it can't do is live in a box on a shelf. This file answers five questions:
> 1. **Should the box run Kubernetes at all,** when Umbrel and Home Assistant run plain Docker? Yes, but only the small, self-contained kind (k3s), on boxes with **4 GB or more**, and with a measured budget. On anything smaller (a sensor, a drone, a Pi Zero), the device is a **NATS leaf node**, not a Kubernetes node. Below that line, the "one OS" promise is kept by the bus, not by Kubernetes.
> 2. **Which Kubernetes?** k3s by default, its bigger sibling RKE2 for GPU servers and regulated customers. They are the same family from the same vendor, with the same upgrade and snapshot tools, so moving between them is not a product switch.
> 3. **How do NVIDIA GPUs work on it?** On Jetson: NVIDIA's own Linux plus the NVIDIA device plugin (NVIDIA's GPU Operator does not support Jetson). On x86 RTX boxes: install the driver in the image, then the device plugin. NVIDIA's newest Kubernetes tools (the DRA driver, KAI Scheduler, AICR, the KubeCon NA 2026 "NVKE") are aimed at data centres and validate Ubuntu/RHEL/SLES/Talos and RKE2, not Debian or k3s. That is a real gap, and it decides which OS the GPU tier runs.
> 4. **How do we move the cloud cluster?** Not all at once. It is not "three changes" as the ADR said; your own lock-in inventory lists 13 items, four of them real work (storage, the control plane, load balancers and snapshots). The plan: keep DigitalOcean as the hub while a home box takes over, app by app, with NATS flipping last.
> 5. **What happens to Backstage and Hermes?** Backstage stays as the developer/enterprise portal in the cloud tier (it needs about 6 GB of RAM just to run, so it can't live on a home box). The OneMind dashboard becomes the front door. Hermes moves as-is, because its container already builds for arm64, and its NATS contracts become the OS's internal API.

---

## 0. The answer in ten lines (P0 conclusions)

| # | Conclusion | Confidence | Claims |
|---|---|---|---|
| P0-1 | **Keep Kubernetes (k3s) as the app platform on every OneMind node with ≥ 4 GB RAM; do not require it below that.** Devices under 4 GB (sensors, drones, MCU-class robots, Pi Zero) join as NATS leaf nodes with an MCP/MHS adapter. This keeps F-14 ("one OS") true at the platform level, while the smallest devices stay light. | Medium-high (lab on VM, not Pi silicon) | C-W4-001, -003, -004, -042, -043, -044, lab C-W4-076…-081 |
| P0-2 | **k3s is the default distribution; RKE2 is the GPU/AI-conformant and regulated tier.** On the frozen weighted scorecard, k3s (63), RKE2 (62) and Talos-native Kubernetes (61) are a **statistical tie** (under 3 points). The tie is settled by the gates: RKE2 needs 4 GB min / 8 GB recommended, Talos has no merged Jetson Orin support, k3s passes every gate. | Medium (fragile under weights) | C-W4-012, -038, -064, -072, -073 |
| P0-3 | **The k3s version treadmill is the main long-term cost:** SUSE supports each k3s/RKE2 minor for about 13–18 months, upstream skew rules forbid skipping minors, and rollback needs a snapshot from the older version. A 10-year box needs about 8–10 Kubernetes minor upgrades, all automated and snapshot-gated. | High | C-W4-009, -010, -012, -014 |
| P0-4 | **SUSE's k3s and RKE2 support matrices do not list Debian.** OneMind's Debian base is supportable by OneMind itself, not by SUSE commercial support. | High | C-W4-013, -072 |
| P0-5 | **NVIDIA's validated Kubernetes stack does not cover Debian or k3s.** GPU Operator lists no Debian; AICR lists neither Debian nor k3s; the Kubernetes AI Conformance list has RKE2, Talos and k0s but not k3s. On Debian the supported path is: NVIDIA driver (DKMS/open modules) + Container Toolkit (apt, "Ubuntu, Debian") + device plugin. | High | C-W4-021, -022, -026, -027, -028, -029, -037, -038 |
| P0-6 | **DC-13 verdict: weakened, not flipped.** The Debian path works for device-plugin GPU access and time-slicing, but loses the GPU Operator's validated lifecycle, signed precompiled drivers and AI conformance. The GPU server tier (Omni/Cluster) should therefore be allowed to run the **NVIDIA-validated base (Ubuntu 24.04/26.04 or the L4T Ubuntu flavour) with RKE2**, within the same app platform. | Medium | C-W4-021, -025, -028, -037, -038 |
| P0-7 | **Jetson: GPU Operator is unsupported; use L4T + container toolkit (≥ 1.11) + NVIDIA device plugin on k3s.** | High | C-W4-023, -029, -020 |
| P0-8 | **Lock-in guard:** Market apps must request accelerators through a OneMind capability (mapped to Kubernetes DRA DeviceClasses or extended resources), never through vendor names directly. NVIDIA, AMD and Intel ship Kubernetes plugins and DRA drivers; Hailo and RK3588 NPUs have no vendor plugin, so OneMind must ship a generic CDI/device-plugin adapter for them. | Medium-high | C-W4-030, -031, -036, -065, -066, -067, -068 |
| P0-9 | **ingress-nginx is retired (March 2026, no security fixes).** OneMind standardises on Gateway API with Traefik (bundled in k3s and default in RKE2). The founder's cloud cluster still runs ingress-nginx publicly and must migrate first. | High | C-W4-015, -016, -017, -018, -063 |
| P0-10 | **The DOKS conversion is 13 dependencies, not "three changes".** Four need real work: storage (95 PVs, about 1.2 TiB, effort L), the control plane (M), load balancers (M) and CSI snapshots (M). ADR-001 D4 should be corrected. | High (founder's own inventory) | C-W4-063 |

---

## 1. Why Kubernetes at all? (DC-10, Q125, Q19, Q44, N-9)

### 1.1 What the proven competitors actually run

| Product | App runtime (from code) | Smallest supported box | Kubernetes? | Robotics / multi-node? | Constraint fit with OneMind |
|---|---|---|---|---|---|
| Home Assistant OS | Docker, driven by the Supervisor (`supervisor/docker/`) [C-W4-044] | Pi-class (HA Green) | No | No / no | **Partial.** Appliance UX and Pi target match; no multi-node, no GPU scheduling, no robotics. |
| umbrelOS 2.x | Docker Compose: each app is a `docker-compose.yml` that `umbreld` reads and writes [C-W4-043] | Pi 5 class | No | No / no | **Partial.** Debian appliance on Pi 5 matches; single box only. |
| Olares | **k3s**, with its own external etcd, Calico, and every k3s add-on disabled [C-W4-041] | 4 cores, 8 GB RAM, 150 GB SSD; Pi 4B/5 **8 GB** only [C-W4-042] | Yes | No / yes (multi-node) | **Closest on platform** (k3s, Market, GPU sharing), but it needs 8 GB and has no A/B image. |
| Founder's cluster | Managed Kubernetes (DOKS) + Argo CD, about 250 pods [context/01 §2] | Cloud nodes, 16 GB+ | Yes | No / yes | **Exact on software** (NATS, Argo, TAK, Hermes); wrong on hardware and hosting. |

**What this teaches:** the two most successful consumer appliances (HAOS, Umbrel) chose Docker because they never needed more than one machine. The only competitor that chose Kubernetes (Olares) did it for multi-node, GPU sharing and per-user isolation, and paid for it with an **8 GB floor**. OneMind's requirements (M-4 scale to enterprise, N-7 robotics and simulation, P-9 the founder's cluster as reference, UX-6 many machines in one view, F-14 one OS) are Olares-shaped, not Umbrel-shaped. So Kubernetes stays, but the 8 GB floor is the risk to beat.

### 1.2 The evidence on cost

- **Documented minimums:** k3s server 2 cores / 2 GB, agent 1 core / 512 MB, on x86_64, armhf and arm64 [C-W4-001]. RKE2: 4 GB minimum, 8 GB recommended [C-W4-072]. k0s: 1 GB controller, 0.5 GB worker [C-W4-045].
- **Measured by the k3s project (old version):** a k3s server with a workload uses about 1.6 GB on both x86 and a Pi 4B; an agent uses about 270 MB [C-W4-003]. The datastore alone generates about 10 IOPS / 500 KiB/s with SQLite [C-W4-004].
- **Flash wear:** k3s's own docs say SD cards and eMMC "cannot handle the IO load" of etcd and recommend an external SSD on Pi/ARM [C-W4-002]. A real failure report shows what slow disks do: a 30-second SQLite checkpoint stall on a 2 vCPU / 4 GB node caused API-server timeouts; the maintainer blamed the disk [C-W4-069].
- **Our measurement (W4-1 lab, Debian 13 arm64 VM, 4 vCPU / 4 GiB, k3s v1.37.2+k3s1):** see §1.3.

### 1.3 Lab W4-1 result

Setup: disposable Lima VM, Debian 13 arm64, 4 vCPU, 3,923 MiB RAM, no host mounts; k3s v1.37.2+k3s1 binary checked against the release SHA-256; Podman 5.4.2 from Debian; reference app = nginx 1.29-alpine + redis 8-alpine. Criteria were written before running: **PASS if state D leaves ≥ 2.0 GiB available and writes ≤ 5 GB/day.**

| State | RAM available (MiB) | Disk writes (extrapolated) | CPU (4 cores) | Claim |
|---|---|---|---|---|
| A. Bare Debian 13 | 3,545 | 0.07 GB/day | 0.1% | C-W4-076 |
| B. Podman + reference app | 3,513 | 0.07 GB/day | 0.1% | C-W4-076 |
| C. k3s default, idle | 2,615 | 1.89 GB/day | 2.0% | C-W4-077 |
| **D. k3s default + reference app** | **2,557 (2.50 GiB)** | **2.75 GB/day** | 2.3% | C-W4-078 |
| E. k3s slim + app (just after restart) | 2,702 | 6.06 GB/day (transient: uninstall job still running) | 1.8% | C-W4-080 |

k3s reached node Ready in 5 s and all system pods in 22 s [C-W4-079]; its SQLite datastore was 30 MB after about 40 minutes [C-W4-081].

**Verdict: PASS (DC-10 flip condition not met on the VM).** The cost of Kubernetes is real but bounded: **about 0.95 GiB of RAM and about 2.7 GB/day of writes more than Podman** for the same two apps [C-W4-076, C-W4-078]. On a 4 GB box that leaves about 2.5 GiB for the OneMind core and apps; on an 8 GB box it is noise.

**Reading the numbers:**
- 2.7 GB/day is about 5 TB over five years. That is fine for any NVMe SSD and for a good industrial eMMC, and it is why k3s's own docs push Pi users to SSDs [C-W4-002]. A plain consumer SD card is the wrong medium for a platform node.
- The "slim" profile saved about 145 MiB of RAM. Its write figure was taken while k3s was still uninstalling Traefik, so it is not a steady-state number; re-run before quoting slim as a write saving.
- The VM is not a Pi 5: RAM numbers carry over roughly (same arm64 binaries); CPU, timing and flash behaviour don't. The real Pi 5 4 GB / 8 GB test on NVMe and SD is in `22-HARDWARE-LAB-TEST-PLAN.md` (status **blocked: founder-hardware**).
- Raw files: README with pre-registered criteria, `run.sh`, `run-1.log` (SHA-256 c019bc07…c5c7), `RESULT.md`; see `evidence/sources/W4.md`.

### 1.4 Decision: a tiered *node* model, one *app* platform

| Node class | Example hardware | Runs | Why |
|---|---|---|---|
| **Platform node** (k3s server) | Pi 5 / CM5 8 GB on NVMe, x86 mini PC, Jetson Orin NX/AGX, RTX box | k3s single server (SQLite), OneMind core, Market apps | The Lite, Pro, Robotics and Omni boxes. |
| **Platform node, minimum** | Pi 5 **4 GB** on NVMe/SSD | k3s "slim" (Traefik, ServiceLB, metrics-server off) and a capped app budget | Allowed, but marketed as "TAK node / greenhouse profile" (P-8), not "run anything". |
| **Worker** (k3s agent) | Extra Pi/Jetson/mini PC in a household | k3s agent only (about 270 MB [C-W4-003]) | Adds capacity to a household cluster. |
| **Leaf device** (no Kubernetes) | Pi Zero 2 W, ESP32 gateways, drones, MCU robots, battery field kits | NATS leaf (or MQTT → NATS bridge) + an MCP/MHS device adapter, supervised by systemd; optional Podman Quadlet for one or two containers [C-W4-051] | The bus is the "one OS" contract here. A leaf stores and forwards during outages [C-W4-055]. |

This answers N-9 ("stay with Kubernetes over Docker-only"): **yes for every box OneMind sells or installs; no for every device OneMind merely connects.** It also matches the founder's own durable requirement in context/01 §1: "Kubernetes stays the long-term application substrate. Not every sensor must run Kubernetes."

### 1.5 Steelman for the runner-up: "Compose on small boxes, k3s on big ones"

*Written arguing **for** the alternative, as the protocol requires.*

The two most-used consumer appliances in the world of self-hosting run Docker, not Kubernetes [C-W4-043, C-W4-044]. On the generic scorecard (§2.4, gate G5 relaxed) Docker/Compose scores **64**, level with k3s's 63, because it is the most proven appliance runtime. Compose is easy to read, everyone already knows it, every self-hosted app ships a compose file, and it costs almost nothing in RAM and flash. Podman Quadlet even accepts Kubernetes YAML through `podman kube play` [C-W4-051], so a OneMind Lite box could run the same Deployments without an API server. A solo founder should not carry a control plane, an etcd/SQLite datastore and a minor-version treadmill [C-W4-012] on a $80 greenhouse box. Ship Compose/Quadlet on Lite, k3s on Pro and above, and let the Market compile one `onemind.app.yaml` into both.

**Why it still loses (for now):**
1. **G5 fails:** two runtimes means two management planes and two app formats (Helm charts don't run under `podman kube play`, which takes plain YAML). That breaks F-14's "no product switch" and doubles the Market test matrix for a solo developer (M-6).
2. **The founder's existing assets are Helm/Argo/Kubernetes-native** (P-9, context/01 §14.3); a Compose tier means porting them twice.
3. **Upgrade from Lite to a household cluster** (UX-6) is trivial with k3s (an agent joins; SQLite converts to etcd in place [C-W4-006]) and a migration with Compose.

**What would flip it:** if the W4-1 measurement on a **real Pi 5 4 GB** (test in `22-…`) leaves under 2 GiB for apps with k3s slim, or flash writes exceed about 5 GB/day on the default storage, then the Lite tier should switch to Podman Quadlet with a OneMind-rendered subset of the app format, and F-14 is kept by the Market compiler instead of the runtime.

### 1.6 Pre-refutation and verdict table for DC-10

*Author's own adversarial pass. It does not replace the independent refuters required by brief §2.7; those see only the P0 claims returned with this file.*

| Lens | Strongest counter-argument | Evidence | Verdict | What would flip it |
|---|---|---|---|---|
| Technical | k3s's datastore and control plane are too heavy for SD/eMMC Pis. | C-W4-002, C-W4-004, C-W4-069 | **Weakened** → mitigated by requiring NVMe/SSD for platform nodes and keeping SD-only devices as leaves | Real Pi 5 NVMe test shows > 5 GB/day writes at idle |
| Longevity / vendor | k3s depends on SUSE; minors live ~13–18 months; Debian isn't in SUSE's matrix. | C-W4-012, C-W4-013 | **Upheld with risk** → k3s is Apache-2.0, CNCF, kine/containerd are upstream; worst case is forking upgrade tooling | SUSE stops k3s releases, or relicenses |
| Cost / business | Olares needs 8 GB; customers want $80 boxes. | C-W4-042 | **Weakened** → Olares runs a much larger stack (KubeSphere, Calico, external etcd) [C-W4-041]; our slim profile is smaller (lab) | A 4 GB Pi 5 can't hold k3s + core + one app |
| Robotics fit | Robots need real time and a light supervisor, not kubelet. | context/01 §1 req. 10 | **Upheld for control loops** → hard real time is off-Kubernetes (W7); k3s supervises perception/AI containers only | W7 shows ROS 2 containers on k3s lose DDS/SHM or RT behaviour |

---

## 2. Which distribution? Scorecard S3 (frozen weights)

### 2.1 Gates (parts S3 controls)

| Candidate | G1 License | G2 x86 + Pi 5 + Jetson | G3 Path to 2036 | G4 IoT/IIoT | G5 Pi → GPU cluster |
|---|---|---|---|---|---|
| **k3s** | PASS: Apache-2.0 [C-W4-075] | PASS: x86_64/arm64 [C-W4-001]; Jetson via nvidia runtime + device plugin [C-W4-020, -029] | CONDITIONAL: continuous minor upgrades, ~13–18 months each [C-W4-012]; paid SUSE support doesn't cover Debian [C-W4-013] | CONDITIONAL: protocols run as apps; RT only off-node or isolated cores (W7) | PASS: 2 GB documented [C-W4-001], measured slim profile (§1.3); scales to 3-server etcd HA [C-W4-006] |
| **RKE2** | PASS: Apache-2.0 | CONDITIONAL: x86_64/arm64 [C-W4-072]; no documented Jetson recipe found | CONDITIONAL: same SUSE cadence [C-W4-012] | CONDITIONAL: as k3s | CONDITIONAL: 4 GB min / 8 GB rec [C-W4-072] rules out the 4 GB Pi |
| **Talos-native** | PASS: MPL-2.0 (Omni BSL, optional) | CONDITIONAL: Pi 5 overlay yes; Orin only in an open PR [C-W4-064] → Jetson needs a separate flavour | CONDITIONAL: published enterprise price per node (W2) | CONDITIONAL: no shell; host services only as extensions (W2) | CONDITIONAL: replaces the base OS (decision S1, DC-23) |
| **k0s** | PASS: Apache-2.0 code, CC-BY-SA docs | CONDITIONAL: arm64/armv7 [C-W4-045]; no Jetson recipe found | CONDITIONAL: Mirantis policy not opened | CONDITIONAL | PASS: 1 GB controller [C-W4-045] |
| **MicroK8s** | PASS: Apache-2.0 | CONDITIONAL: snap-based; not in v1.37 conformance [C-W4-073] | CONDITIONAL | CONDITIONAL | PASS |
| **MicroShift** | PASS (upstream); RHEL subscription for support | **FAIL**: no Pi 5 path found; Jetson only as Red Hat Device Edge (prior W2 research, not re-opened by W4) | CONDITIONAL | CONDITIONAL | FAIL (unproven) |
| **Docker / Compose** | PASS | PASS (Umbrel/HAOS on Pi [C-W4-043, -044]) | PASS | CONDITIONAL: no fleet orchestration | **FAIL**: no multi-node GPU cluster without a different product |
| **Podman + Quadlet** | PASS | PASS | PASS | CONDITIONAL | **FAIL**: single host only [C-W4-051] |
| **Tiered mix** (Quadlet on Lite, k3s above) | PASS | PASS | CONDITIONAL | CONDITIONAL | **FAIL**: two management planes and app formats |

### 2.2 Scores (0–5 anchors; one claim per cell)

| Candidate | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | Total | Rank |
|---|---|---|---|---|---|---|---|---|---|
| **k3s** | 3 — documented in-place minor upgrades, support dated to 2028 per minor chain [C-W4-012, -010] | 3 — x86/Pi/Jetson paths, GPU Operator lists K3s [C-W4-022, -020] | 1 — no atomic k8s-layer rollback; snapshot restore only [C-W4-009] | 4 — Olares (appliance, code), SUSE Edge, Kairos; 3 failure reports read [C-W4-041, -069, -070, -071] | 4 — single binary, add-ons disable-able, measured slim profile (lab) | 4 — Apache-2.0, no blobs [C-W4-075] | 4 — Helm/CNCF ecosystem; NVIDIA lists K3s [C-W4-022] | **63.0** | 1 (tie) |
| **RKE2** | 3 [C-W4-012] | 4 — AI-conformant v1.34–1.37, AICR-listed, GPU Operator partner-validated [C-W4-038, -037, -022] | 1 [C-W4-009 applies to the same tooling] | 3 — SUSE Edge, Rancher Government; no appliance competitor [C-W4-072] | 3 — 4 GB floor, heavier [C-W4-072] | 4 | 4 [C-W4-038] | **62.0** | 2 (tie) |
| **Talos-native** | 3 (W2 price, rebase by API) | 3 — AICR/AI-conformant, but no Orin [C-W4-037, -038, -064] | 2 — A/B with boot-failure rollback (W2), doc-only | 3 (W2) | 3 — API-only model to learn | 4 | 4 [C-W4-037] | **61.0** | 3 (tie) |
| **k0s** | 2 — release cadence only; own policy not opened | 3 — GPU Operator partner-validated; AI-conformant v1.35–1.36 [C-W4-022, -038] | 1 | 2 | 4 [C-W4-045] | 4 | 3 | **51.0** | 4 |
| **MicroK8s** | 2 | 2 — snap; dropped from v1.37 conformance [C-W4-073] | 1 | 2 | 3 | 4 | 3 | **45.0** | 5 |
| *Docker/Compose (gate G5 relaxed)* | 3 | 3 | 1 | 5 — HAOS and umbrelOS, constraint-matched, 2+ years, code [C-W4-043, -044] | 4 | 4 | 3 | *64.0* | not ranked (G5) |
| *Tiered mix (G5 relaxed)* | 3 | 3 | 1 | 3 | 2 — two runtimes | 4 | 4 | *56.0* | not ranked (G5) |
| *Podman + Quadlet (G5 relaxed)* | 3 | 3 | 1 | 2 | 4 | 4 | 2 | *53.0* | not ranked (G5) |

Notes: C3 here judges the Kubernetes layer only. Atomic OS rollback is S2's job (Rugix/RAUC, `04-…`); the Kubernetes layer's safety comes from the snapshot-before-upgrade rule (§3.3). `pending-lab` cells: k3s C5 (Pi silicon), all C3 (no k8s-layer lab yet).

### 2.3 Sensitivity analysis (±5 per weight, 14 runs)

| Perturbation | Winner | Runner-up | Margin |
|---|---|---|---|
| C1 +5 / −5 | k3s / k3s | RKE2 / RKE2 | 0.9 / 1.1 |
| C2 +5 / −5 | **RKE2** / k3s | k3s / Talos | 0.3 / 2.1 |
| C3 +5 / −5 | k3s / k3s | Talos / RKE2 | 0.7 / 1.1 |
| C4 +5 / −5 | k3s / **RKE2** | RKE2 / k3s | 2.1 / 0.1 |
| C5 +5 / −5 | k3s / **RKE2 (tie 62.1)** | RKE2 / k3s | 2.1 / 0.0 |
| C6 +5 / −5 | k3s / k3s | RKE2 / RKE2 | 0.9 / 1.1 |
| C7 +5 / −5 | k3s / k3s | RKE2 / RKE2 | 0.9 / 1.1 |

**Result: fragile.** The winner changes in 3 of 14 runs, always to RKE2, when hardware fit (C2) weighs more, or proven-in-production (C4) or solo operability (C5) weigh less. That is defensible: k3s and RKE2 are one family (same vendor, upgrade controller, snapshot CLI and Helm controller [C-W4-010, C-W4-012]), so the "flip" is really "use the bigger sibling on GPU servers", which is the recommendation anyway.

**Gates relaxed:** with G5 relaxed, Docker/Compose (64) would tie k3s. **G5 (F-14) is the single gate that keeps Compose out.** If the founder ever drops "one OS from Pi to GPU cluster", Compose on Lite becomes the default (see §1.5).

### 2.4 Recommendation (D4, refined)

- **k3s on every platform node** (single server + SQLite on one box; `--cluster-init` etcd when a second server joins [C-W4-006]).
- **RKE2 on the Omni/Cluster GPU tier and the hardened public-safety tier**, because it is the member of the family that NVIDIA's AI tooling and the CNCF AI-conformance program actually cover [C-W4-037, C-W4-038].
- **Charts must not depend on k3s-only features** (`HelmChart` CRD, `/manifests` auto-deploy, ServiceLB, kine). This is already the founder's rule ("avoid k3s-only features in Git", context/01 §11).
- **Don't use NATS as the Kubernetes datastore**, even though kine supports it [C-W4-053]: the founder's rule "the thing that fixes problems must not depend on the thing it is fixing" (context/01 §4.2) applies; a NATS outage would then take down both the bus and the control plane.

---

## 3. Topology: one box → household cluster → many sites (Q130, Q131, Q132, Q145, Q157, Q163)

### 3.1 Growth path without kubeconfig

1. **One box:** k3s single server, SQLite, local-path storage. Backup = copy of `server/db` + token [C-W4-007], plus app volumes (W5).
2. **Second and third box:** the OneMind app shows "Add a node" → QR (N-4) → the new node joins as an **agent** (about 270 MB [C-W4-003]). No HA yet, by design: two-server etcd has no fault tolerance.
3. **HA at three servers:** restart the first server with `--cluster-init` (SQLite → embedded etcd in place [C-W4-006]); promote two agents to servers. Requires SSD/NVMe on all three [C-W4-002]. Snapshots then run twice a day, keep 5, optional S3 [C-W4-008].
4. **More sites:** **never stretch one cluster across sites.** Each site is its own cluster and its own NATS JetStream domain; sites connect through NATS leaf links that dial out to a hub [C-W4-054] and keep working when cut off (store-and-forward proven in the W8 lab [C-W4-055]). Desired state flows by GitOps per cluster.

### 3.2 Multi-site and edge frameworks

| Option | What it is | Status (2026-11-10) | Fit for OneMind | Constraint fit |
|---|---|---|---|---|
| **NATS leaf + JetStream domains** | Data/command plane across sites | Proven in founder cluster and W8 lab [C-W4-054, -055] | **Primary inter-site fabric** | Exact (founder's doctrine) |
| **Argo CD ApplicationSets / Fleet / Flux per cluster** | Desired-state fan-out | Argo CD v3.6.1, Fleet v0.16.3, Flux v2.10.0 [C-W4-048, -049] | Hub-and-spoke from the cloud/HQ for enterprise; each box also reconciles locally | Good |
| **Open Cluster Management** | Hub/spoke multi-cluster API | v1.4.0 [C-W4-048] | Candidate for enterprise fleets (year 2–3) | Medium |
| **Karmada** | Federated scheduling across clusters | v1.19.1 [C-W4-048] | Not needed until multi-cluster scheduling is | Low for homes |
| **Liqo** | Peering clusters, virtual nodes | v1.3.0 [C-W4-048] | Interesting for "burst to my friend's GPU" (F-6), later | Low now |
| **KubeEdge** | Cloud core + edge nodes, device twins | v1.23.1, CNCF Graduated [C-W4-048] | Not adopted: it needs a cloud control plane, which contradicts "home is the authority"; NATS + MHS adapters cover device twins | Low |
| **OpenYurt** | Edge autonomy for nodes of a central cluster | v1.7.0 [C-W4-048] | Not adopted, same reason | Low |

### 3.3 Upgrades across thousands of boxes (Q145)

- **Cadence is forced:** upstream supports three minors, about one year each [C-W4-014]; SUSE supports each k3s minor for about 13–18 months [C-W4-012]. A box left offline for two years will be two or three minors behind and **must step through each one** [C-W4-010].
- **Rollback is snapshot-based:** to go back a minor you need a datastore snapshot taken on the older version [C-W4-009]. Rule for OneMind: **every k3s minor upgrade is preceded by an automatic datastore snapshot**, and the update UI says "rolling back will lose changes made after <time>".
- **Input to DC-12 (W3):** if k3s lives inside the A/B OS image, an OS rollback across a k3s minor boots an *older* k3s against a *newer* datastore, which k3s refuses [C-W4-010]. Safe design: the update bundle that changes the k3s minor takes the pre-update snapshot; the rollback path restores it before starting k3s on the old slot. Without this hook, keep k3s minors out of OS updates (ship them as a separate layer via system-upgrade-controller).

---

## 4. GitOps and the Market controller (Q133, Q149, Q293)

- **One owner per resource** (the founder's ADR 0002 rule, context/01 §4.3). The Market writes a `OneMindApp` object; *one* reconciler turns it into a Helm release. The user never edits Git on a home box.
- **On boxes:** Argo CD **Core** (controller + Redis + CRDs, no API server, no UI, no OIDC [C-W4-050]) is the lightest way to keep the founder's Argo patterns; Flux is the alternative. The decision between them is a lab item (RAM on Pi 5) in `22-…`.
- **In the cloud/enterprise tier:** full Argo CD (as today) with ApplicationSets fanning out to sites.
- **KubeVela and Crossplane (ADR 0002):** not on appliances. They solve app-infrastructure provisioning in clouds; on a box they add controllers and RAM for no user benefit. Keep them as optional enterprise-tier modules.

---

## 5. Storage per tier (Q135)

| Tier | Storage | Why | Claims |
|---|---|---|---|
| 1 box (Lite/Pro/Robotics) | `local-path` on NVMe/SSD; optional host ZFS mirror (W5) | Zero overhead; data protection comes from backups, not replication | C-W4-002 |
| 3+ boxes | Longhorn V1 | Simplest replicated option; but needs 3 nodes × 4 vCPU / 4 GiB [C-W4-046] | C-W4-046 |
| Enterprise / large sites | Rook-Ceph on dedicated disks | Only with ops staff | VK8S §10 (prior) |
| Never on Pi | Longhorn V2 / OpenEBS Mayastor | Hugepages + dedicated cores [C-W4-046] | C-W4-046 |

**Charts take `storageClassName` as a value.** For the cloud migration, the founder's own inventory recommends creating StorageClasses *named* like the DigitalOcean ones on the new cluster so no manifest changes are needed for the first rebuild [C-W4-063].

---

## 6. Ingress, networking and remote access (Q137, Q138, Q153)

- **Ingress:** ingress-nginx is retired with no security fixes after March 2026 [C-W4-016]. RKE2 removed it for new clusters in v1.37 [C-W4-017]. **OneMind uses Gateway API** through **Traefik**, which ships in k3s with optional Gateway API support [C-W4-015] and is RKE2's default [C-W4-017]. Six implementations pass Gateway API v1.6 conformance, so apps aren't tied to Traefik [C-W4-018].
- **CNI:** Flannel (k3s default) on boxes; Cilium on GPU/enterprise clusters for parity with the founder's cloud (kernel 5.10+, arm64 supported [C-W4-047]). The lab measures Flannel only.
- **LAN load balancers:** ServiceLB (hostPort per Service) on one box; MetalLB on multi-box (requires disabling ServiceLB [C-W4-019]).
- **Remote access:** Tailscale operator in the cloud tier (ingress, egress, API-server proxy, subnet routers [C-W4-062]). For sovereignty, a self-hosted control server: **Headscale** covers a single tailnet (one household or small org) [C-W4-060]; **NetBird** is fully self-hostable but its management/signal/relay servers are AGPL-3.0 [C-W4-061] (fine to *run* unmodified; never copy its code into the Apache core, D-001).
- **Offline images:** k3s's embedded Spegel P2P mirror shares images between nodes, but assumes all nodes are equally trusted [C-W4-052]: enable it inside a household cluster only.

---

## 7. NVIDIA on k3s (N-8, F-2, AI-8, DC-13, Q16, Q143, Q144)

### 7.1 The NVIDIA Kubernetes toolbox, checked on 2026-11-10

| Component | What it does | Version | Supports Jetson? | Supports Debian? | Supports k3s? | Claims |
|---|---|---|---|---|---|---|
| **Driver + Container Toolkit** | Kernel driver and the runtime hook that gives containers the GPU | Toolkit 1.20.1; CUDA 13.5 | Jetson: in JetPack | **Yes** (apt "Ubuntu, Debian"; CUDA lists Debian 13) | n/a | C-W4-026, -027, -028 |
| **k8s-device-plugin** | Advertises `nvidia.com/gpu`, time-slicing | v0.20.1 | **Yes** (toolkit ≥ 1.11 on Tegra) | Not OS-specific | Yes, with `runtimeClassName: nvidia` | C-W4-029, -020 |
| **GPU Operator** | Installs and upgrades driver, toolkit, plugin, DCGM, MIG manager | v26.7.2 | **No** (discrete GPUs only) | **Not listed** | **Listed** (K3s 1.33–1.37) | C-W4-021, -022, -023 |
| **DRA driver for GPUs** | Next-generation allocation (DRA); ComputeDomains for multi-node NVLink | v0.5.1; now under kubernetes-sigs | Not mentioned | n/a | Needs DRA (stable in recent Kubernetes) | C-W4-030, -031, -033 |
| **KAI Scheduler** | GPU-aware queues, fair share, GPU sharing | v0.18.7, CNCF Sandbox | Not stated | n/a | Not stated | C-W4-034 |
| **Dynamo** | Distributed LLM inference serving | v1.6.2, Apache-2.0 | n/a | n/a | n/a | C-W4-035 |
| **AICR** (AI Cluster Runtime) | NVIDIA-signed, validated "recipes" for GPU clusters | v1.2.0, Apache-2.0 | No | **No** | **No** (RKE2, k0s, Talos and clouds yes) | C-W4-037 |
| **HAMi** (CNCF, not NVIDIA) | GPU memory/compute slicing for many vendors (Olares uses a fork) | v2.11.0 | **No** | n/a | Yes (generic) | C-W4-036 |
| **NVKE / NVKR** (KubeCon NA 2026) | Open-source managed-Kubernetes building blocks for GPU data centres | Public preview | No | n/a | No (kubeadm + Cluster API) | C-W4-039 |
| **Agent Substrate** (KubeCon NA 2026) | Sandboxed agent sessions with GPU suspend/resume on DRA | CNCF Sandbox | n/a | n/a | Generic Kubernetes | C-W4-040 |

> **KubeCon NA 2026 box (Salt Lake City, 9–12 Nov) — re-check by 2026-12-10.** On day 2 NVIDIA released NVKE and NVKR (Apache-2.0, public preview, "not yet recommended for production", data-centre bare metal) [C-W4-039] and moved Agent Substrate into the CNCF Sandbox, building GPU suspend/resume on DRA [C-W4-040]. The bigger moves of 2026 came at KubeCon Europe: the DRA driver was donated to the Kubernetes project and KAI Scheduler entered the CNCF Sandbox [C-W4-032]. **None of the NA 2026 items mention edge, Jetson or k3s.** Lesson for OneMind: NVIDIA's Kubernetes roadmap is converging on **DRA + AI conformance + validated recipes**, and the validated set is RKE2/Talos/k0s/clouds on Ubuntu/RHEL/SLES. A OneMind GPU tier that wants "day-one NVIDIA" (F-2) should sit inside that set.

### 7.2 DC-13 answered: NVIDIA drivers on Debian

| Need | Debian 13 + driver + toolkit + device plugin | Validated base (Ubuntu + GPU Operator, or RKE2 + AICR recipe) |
|---|---|---|
| CUDA containers on an RTX/RTX PRO GPU | **Works**: driver and toolkit document Debian [C-W4-026, -027, -028]; k3s detects the runtime [C-W4-020] | Works |
| Time-slicing | Works (device plugin feature) [C-W4-029] | Works |
| MIG | Only on data-centre GPUs; needs MIG manager (Operator) or manual config | Works (Operator) |
| Driver lifecycle (upgrade without rebuild) | **OneMind's job**: DKMS-built modules [C-W4-028] must be built into the image at build time on a read-only root | Operator-managed; signed precompiled driver containers for Ubuntu kernels [C-W4-025] |
| Secure Boot | **OneMind's job**: sign the modules with OneMind's key at image build (NVIDIA's Debian page gives no procedure [C-W4-028]) | Precompiled signed modules on Ubuntu [C-W4-025] |
| DRA / AI conformance / AICR recipes | **Not covered** (Debian and k3s absent [C-W4-037, -038]) | Covered (RKE2, Talos, k0s; Ubuntu/RHEL/SLES) |
| Consumer GeForce RTX | Works for CUDA; not in GPU Operator lists on any OS [C-W4-024] | Same gap |

**Verdict: weakened, not flipped.** DC-13's flip condition was "a needed feature fails on Debian 13 but works on a validated base". For the Pro box (one consumer/pro RTX, time-sliced Ollama/ComfyUI), nothing needed fails; the cost is that OneMind builds and signs its own driver modules into each image. For the **Omni/Cluster tier** (MIG, DRA, multi-GPU, Dynamo, "keep pace with NVIDIA"), the validated base wins. **Recommendation to W2/01:** allow the GPU-server flavour to use Ubuntu LTS + RKE2 (the same flavour family as the Jetson L4T/Ubuntu flavour), with the same OneMind app platform, Market and update UX. This costs a second x86 flavour; the alternative is fighting NVIDIA on every release.

### 7.3 Jetson on k3s (Q144)

- GPU Operator: **not supported** on Jetson [C-W4-023]. Use JetPack's driver and container toolkit (≥ 1.11 for Tegra) + the NVIDIA device plugin [C-W4-029] + k3s's `nvidia` RuntimeClass [C-W4-020].
- HAMi does not list Jetson [C-W4-036]; GPU sharing on Jetson is time-slicing only.
- Keep the Jetson an ordinary k3s node (server on a standalone robot, agent in a household cluster). Control loops stay outside Kubernetes (W7).

---

## 8. Lock-in guard: same manifests on NVIDIA, AMD, Intel, Hailo, RK3588 (F-2, F-6)

**Rule:** a Market app never asks for `nvidia.com/gpu` directly. It declares a **capability** in `onemind.app.yaml` (e.g. `accelerator: {class: gpu.cuda | gpu.rocm | gpu.any | npu.inference, memory: 8Gi}`). The OneMind controller maps it to whatever the node offers: a DRA DeviceClass where a DRA driver exists, or an extended resource from a device plugin otherwise. Node Feature Discovery labels the node [C-W4-068].

| Vendor | Kubernetes path today | Gap OneMind fills | Claims |
|---|---|---|---|
| NVIDIA dGPU | Device plugin, GPU Operator, DRA driver | Capability mapping | C-W4-022, -029, -030 |
| NVIDIA Jetson | Device plugin + JetPack | Capability mapping | C-W4-023, -029 |
| AMD GPU | ROCm GPU Operator, device plugin, DRA driver; HAMi slicing | Capability mapping | C-W4-066, -036 |
| Intel GPU / NPU | Intel device plugins operator (GPU, NPU, QAT…) | Capability mapping | C-W4-065 |
| **Hailo** | **No vendor plugin** (only tiny community repos) | Ship a OneMind CDI spec + generic device plugin | C-W4-067, -068 |
| **Rockchip RK3588 NPU** | **No vendor plugin** | Same | C-W4-067, -068 |

Test of the guard (in `22-…`): the same `onemind.app.yaml` for an inference app installs on an RTX box, a Jetson and an RK3588/Hailo box, each landing on the right runtime image.

---

## 9. Converting the founder's DOKS cluster (Q140, Q155, Q33, P-9)

### 9.1 Correction to ADR-001 D4

ADR-001 says DOKS apps "convert with three changes" (LB annotations, storage class, ingress-nginx → Traefik). The founder's own read-only inventory (2026-10-10) lists **13 dependencies** [C-W4-063]:

| # | Dependency | Effort (founder's estimate) | OneMind replacement |
|---|---|---|---|
| 1 | Managed control plane | M | k3s / RKE2 (and etcd backups become ours) |
| 2 | Block-storage classes (95 PVs, ~1.2 TiB) | **L** | local-path (1 box) / Longhorn (3 boxes); data moves by backup-restore |
| 3 | DO load balancers + annotations | M | Tailscale (admin, TAK), Cloudflare Tunnel (web), ServiceLB/MetalLB |
| 4 | Object storage for all backups | S–M | Any S3 (Garage/MinIO at home + an off-site provider); archives are client-side encrypted |
| 5 | CSI snapshot classes (46 VolSync sources) | M | Longhorn snapshot class or VolSync copy methods that need no CSI snapshots |
| 6–13 | Firewalls, node label, annotations, doctl, Terraform, DO system images, (no registry), (no managed DB) | S or none | Router firewall + Tailscale ACLs; label the home node the same |

Plus one item the inventory predates: the public **ingress-nginx** is now unmaintained [C-W4-016] and is a security debt today, independent of any move.

### 9.2 The conversion plan

*Principles: never move the authority twice; one app at a time; backups are the moving van; WAN-off test before cut-over (the founder's REBUILD-FROM-ZERO pattern, context/01 §10).*

| Phase | When (see `20-…`) | Do | Exit test |
|---|---|---|---|
| **0. Fix in place** | Weeks 1–4 | Replace ingress-nginx with Gateway API (Traefik or the Cilium Gateway classes already present, context/01 §2); finish Helm → Argo adoption of NATS, TAK core, Argo CD; enable the off-site backup copy; add `storageClassName` values to every chart. | No Helm-CLI releases left; public ingress on a maintained controller |
| **1. Home box as a spoke** | Weeks 5–10 | First OneMind box (Pro tier, k3s) joins the tailnet; its NATS runs as a **leaf in its own JetStream domain** dialling the cloud hub [C-W4-054]; Argo CD on the box reconciles a `home` overlay (storage classes named like DO's [C-W4-063], no LB annotations, node label set). | Leaf buffers through a WAN cut (W8 lab pattern [C-W4-055]) |
| **2. Move stateless and local-first apps** | Weeks 8–16 | Vaultwarden, Karakeep, Nextcloud, n8n, Home Assistant bridges move by restore-into-new-PVC; cloud copies scaled to zero but kept. | Each app passes its restore drill on the box with WAN off |
| **3. Identity and agents** | Months 4–6 | Authentik (or the OS identity, `10-…`) primary at home, cloud as replica/relay; Hermes gets a body on the box (§11). | Login and agent prompts work with WAN off |
| **4. Flip the bus authority** | Month 6+ | Home NATS becomes the hub; the cloud cluster becomes a leaf (mirrors for DR); TAK Server moves home or stays as cloud relay (decision for Zeus). | 7-day soak; cloud outage drill |
| **5. Cloud = OneMind Cloud/Omni tier** | Year 1 | The DOKS cluster keeps public apps, relay, off-site backups, image build/signing CI, the update server and Backstage. Optionally rebuilt on RKE2 to match the enterprise tier. | Cost and latency within budget (Q155, `22-…` read-only checks) |

**Read-only commands for Zeus** (go to `22-HARDWARE-LAB-TEST-PLAN.md`): `kubectl get sc`, PV totals by class, `kubectl get svc -A | grep LoadBalancer`, `kubectl get ingress -A`, Helm releases still CLI-owned (`helm list -A` vs Argo Applications), and a grep for `do-` annotations and storage class names in the repo.

---

## 10. Backstage's future (Q141, Q255, P-2)

| Option | Cost | Fit |
|---|---|---|
| Backstage on every box | Needs at least 6 GB RAM and 20 GB disk just for the standalone app [C-W4-059] | **No**: more than a Lite box has |
| Replace Backstage everywhere | Lose 27 custom plugins and the catalog work (context/01 §4.4) | Wasteful |
| **Keep Backstage as the developer/enterprise portal in the cloud and Cluster tiers; the OneMind dashboard is the front door** | Already running; MCP actions exist | **Recommended**, matching the repo's own 2026-10-08 recommendation (context/01 §4.5) |

What moves into the OS: the **catalog model** (systems, components, owners) becomes the source for the dashboard's "Apps" and "Infrastructure map" (UX-7), read through the Backstage MCP endpoint where Backstage exists, and from `OneMindApp` objects where it doesn't. Backstage stays the place where developers build plugins for OneMind (A-5, F-5).

---

## 11. AI-9: moving Hermes and the NATS contracts

- **Hermes runs anywhere:** the upstream hermes-agent image is built on `debian:trixie` for amd64 **and arm64** (MIT) [C-W4-058], so a Pi 5 or Jetson body is a build, not a port. The founder's custom images are often amd64-only (context/01 §11): add arm64 builds to CI before the first ARM box.
- **NATS is OneMind's, not Hermes's:** hermes-agent has no NATS integration in its repo [C-W4-058]; the NATS leaf sidecar and Agent Protocol subjects are OneMind code. Keep that design: it is what lets "one identity, several bodies" work through queue groups (context/01 §6).
- **Migration steps:** (1) publish the subject grammar, envelope schemas and Stream/KV CRs as the OS's **bus contract** (versioned, Apache-2.0); (2) run NACK on every platform node so streams are declared as CRs, not created by hand [C-W4-057]; (3) give each box its own JetStream domain and leaf link [C-W4-054]; (4) start a Hermes body on the box with read-only permissions (layer 1 trust model, context/01 §4.2); (5) only after the bus authority flips (phase 4 above) does the home body become primary.
- **Licence risk is closed:** CNCF keeps NATS under Apache-2.0 after the 2025 Synadia dispute [C-W4-056].

---

## 12. Why an OS now, instead of "cluster + portal"?

The cluster proved the software. It cannot provide what only the machine owner can: atomic OS updates with rollback, hardware detection, first-boot onboarding, local-first operation through WAN loss, physical device access, and per-device keys (context/01 §4.5 item 7, §14.2). Competitor evidence agrees: HAOS and umbrelOS, the two products that won households, ship their **own image** and keep the app runtime simple [C-W4-043, -044]; Olares, which ships only an installer on a stock distro, needs 8 GB and has no OS rollback [C-W4-042]. And the founder's cloud stack depends on retired or provider-bound parts (ingress-nginx [C-W4-016], DO storage and snapshots [C-W4-063]). Owning the image (W3/W18) plus a portable k3s platform (this file) is what turns the proven software into a product. **Input to DC-22 (W18):** build the platform layer (k3s profile, Market controller, NATS contracts) *first, on the existing cluster and a VM*, because it is portable across DOKS, a VM and the image; then wrap it in the image. The two are not either/or.

---

## 13. Risks (for `23-RISK-REGISTER.md`)

| Risk | Likelihood | Impact | Mitigation | Trigger |
|---|---|---|---|---|
| k3s minor treadmill on offline boxes | High | High | Snapshot-gated, stepwise upgrades; support window in CRA declaration | Box > 2 minors behind |
| NVIDIA validates only Ubuntu/RHEL/SLES + RKE2/Talos | High | Medium | GPU-server flavour on Ubuntu + RKE2 | New NVIDIA feature unusable on Debian |
| SD/eMMC wear from datastore | Medium | High | NVMe/SSD required for platform nodes | Field failures; lab writes > 5 GB/day |
| SUSE changes k3s licensing/stewardship | Low | High | Apache-2.0 fork-ability; k0s as fallback | Relicensing notice |
| Public ingress-nginx in the cloud | High | High | Phase 0 migration | Any new ingress-nginx CVE |
| Hailo/RK3588 without vendor plugins | High | Low | OneMind generic CDI adapter | — |

## 14. Open items (UNVERIFIED or blocked)

1. Real Pi 5 (4 GB and 8 GB, NVMe and SD) footprint and write volume: **blocked: founder-hardware** → `22-…`.
2. Argo CD Core vs Flux RAM on a Pi 5: lab in `22-…`.
3. Mirantis k0s formal support lifecycle: not opened.
4. RKE2 on Jetson: no documented recipe found.
5. Consumer RTX time-slicing + driver upgrade on Debian 13 with a signed module on Secure Boot: needs a GPU (cloud or founder box).
6. DOKS current state (whether ingress-nginx is still public): **live-cluster** → read-only commands in §9.2.

## 15. Requirement traceability

| Requirement | Where answered |
|---|---|
| N-9 | §1, §2 |
| N-8, F-2, AI-8 | §7 |
| N-2, F-14, M-4, P-5 | §1.4, §2, §3 |
| N-3 | §8 (NFD capability detection) |
| N-5, F-6 | §3, §9 |
| N-6, U-5 | §6 |
| P-9 | §9 |
| P-2 | §10, §12 |
| M-6 | §1.5, §2, §4 |
| M-7, N-7 | §1.4, §7.3 |
| AI-9 | §11 |
| R-1, R-3 | §3.3 |
| UX-6 | §3.1 |
| A-1, A-5 | §4, §8, §10 |

## Glossary

- **Kubernetes (k8s):** software that runs containers across one or many machines, restarts them, and gives them network and storage. **k3s** is a small, single-binary Kubernetes; **RKE2** is its hardened, heavier sibling from the same vendor (SUSE).
- **Control plane / datastore:** the "brain" of Kubernetes and where it stores its state. On one box k3s uses **SQLite** (a file); with three boxes it uses **etcd** (a replicated database).
- **Minor version / skew:** Kubernetes 1.36 → 1.37 is a minor upgrade. You can't skip one, and you can't go back without a snapshot.
- **Leaf node (NATS):** a small NATS server on a device that dials out to a bigger one and stores messages locally while the link is down.
- **JetStream domain:** a name that keeps one site's stored streams separate from another's.
- **GitOps:** the desired state lives in Git (or in a OneMind object) and a controller makes the cluster match it. **Argo CD** and **Flux** are such controllers.
- **Gateway API:** the modern Kubernetes standard for routing web traffic into a cluster, replacing "Ingress".
- **Device plugin / DRA:** two Kubernetes mechanisms that let a pod ask for a GPU or NPU. **DRA (Dynamic Resource Allocation)** is the newer, richer one.
- **GPU Operator:** NVIDIA's installer that manages drivers and GPU plugins on Kubernetes nodes.
- **CDI (Container Device Interface):** a vendor-neutral file format describing how to give a container a device.
- **Time-slicing / MIG:** two ways to share one GPU between apps (taking turns, or hardware partitions).
- **Constraint fit:** whether a competitor's situation (hardware, team, Kubernetes or not) matches OneMind's closely enough to copy its choice.

## Sources

All sources, access dates and archive links are in `evidence/sources/W4.md`; every claim ID resolves in `evidence/claims/W4.csv`.
