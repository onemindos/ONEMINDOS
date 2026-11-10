# OneMind OS: Robotics, IoT, XR and NVIDIA Edge Stack Research

Date: 2026-11-10. Method: every factual claim below was read from a page, repo README, or GitHub API response opened during this session; URLs are inline. Items I could not confirm are marked **UNVERIFIED**. Statements labelled **PROPOSAL** are my design suggestions, not sourced facts. Prices are volatile (see section 1.5): re-check before purchasing.

---

## 1. NVIDIA edge and robotics stack

### 1.1 Jetson lineup (module level)

From the [NVIDIA Jetson modules page](https://developer.nvidia.com/embedded/jetson-modules):

| Module | AI perf (as listed) | Memory | Power |
|---|---|---|---|
| Jetson AGX Thor (T5000, T4000) | up to 2070 FP4 TFLOPS | 128 GB (T5000) | 40 W to 130 W |
| Jetson AGX Orin (64GB/32GB/Industrial) | up to 275 TOPS | 64 / 32 GB | not listed |
| Jetson Orin NX (16GB/8GB) | up to 157 TOPS | 16 / 8 GB | not listed |
| Jetson Orin Nano (8GB/4GB) | up to 67 TOPS | 8 / 4 GB | 7 W to 25 W |

- The [Jetson Linux 38.4 developer guide](https://docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/index.html) lists T5000 128GB (developer kit only) and T4000 64GB (commercial module), and states 38.4 does not support the Orin family.
- Dev kits ([developer kits page](https://developer.nvidia.com/embedded/jetson-developer-kits)): AGX Thor Dev Kit (Blackwell GPU, 128 GB, 130 W envelope, "7.5x the AI compute" of AGX Orin per NVIDIA), Orin Nano Super Dev Kit, AGX Orin Dev Kit 64GB (275 TOPS; one SoC architecture so it can emulate any Orin module).
- GPU/CPU core counts were not on these pages: UNVERIFIED here.

### 1.2 DGX Spark and DGX Station

[DGX Spark](https://www.nvidia.com/en-us/products/workstations/dgx-spark/): GB10 Grace Blackwell (20-core Arm: 10 Cortex-X925 + 10 Cortex-A725), up to 1 PFLOP FP4 (with sparsity), 128 GB coherent LPDDR5X (273 GB/s), up to 4 TB NVMe, ConnectX-7 200 Gbps (2 QSFP) + 10 GbE + Wi-Fi 7 + BT 5.4, 240 W PSU, 150 x 150 x 50.5 mm, 1.2 kg, NVIDIA DGX OS (Ubuntu-based). 2-3 units cluster by direct cable; 4 need a 200 GbE switch. Also sold via OEMs (Dell, HP, Lenovo, ASUS) and a 64 GB OEM variant.

[DGX Station](https://www.nvidia.com/en-us/products/workstations/dgx-station/): GB300 Grace Blackwell Ultra (1 Blackwell Ultra GPU + 72-core Grace), 252 GB HBM3e + 496 GB LPDDR5X (748 GB coherent), ConnectX-8 up to 800 Gb/s, 1,600 W (20 A circuit). Price and release date not on the page. OEMs listed: ASUS, Dell, Exxact, Gigabyte, HP, MSI, Supermicro.

### 1.3 JetPack, L4T base OS, containers, Kubernetes

- [JetPack page](https://developer.nvidia.com/embedded/jetpack): JetPack 7 (7.2 highlighted, adding NemoClaw and Yocto support) supports Jetson Orin and Jetson Thor; **Ubuntu 24.04 LTS on Linux kernel 6.8**; CUDA 13.0 on Thor with a unified Arm install; NGC containers (PyTorch, vLLM, SGLang tagged 26.04-py3, Triton); "cloud-native development with containers and Kubernetes" supported. The linked guides are r39.2 (Jetson Linux version inferred, not stated).
- Older [JetPack 6.2.1 install doc](https://docs.nvidia.com/jetson/jetpack/install-setup/index.html): SDK Manager needs an x64 Ubuntu host; `nvidia-jetpack` apt metapackages; `nvidia-container-toolkit` is in the package list. Orin Nano kits with old firmware must update firmware before JetPack 6.x.
- Kubernetes on Jetson: the [NVIDIA k8s-device-plugin README](https://github.com/NVIDIA/k8s-device-plugin) requires nvidia-container-toolkit 1.11.0+ "to use integrated GPUs on Tegra-based systems". GPU Operator Jetson support: UNVERIFIED (its docs URL 404'd for me).
- Community container build system: [dusty-nv/jetson-containers](https://github.com/dusty-nv/jetson-containers) (last push 2026-11-02) packages PyTorch, vLLM, ROS, Isaac Sim, Cosmos, DeepStream, Holoscan, Home Assistant and Wyoming voice pieces for Jetson.

### 1.4 Isaac, GR00T, Cosmos, Holoscan, Metropolis, NIM, Omniverse

- **Isaac Sim requirements** ([docs](https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html)): x86 Ubuntu 22.04/24.04 (22.04 deprecated) or Windows 11. Minimum: RTX 4080 16 GB VRAM, 32 GB RAM, 4 cores, 50 GB SSD. Good: RTX 5080, 64 GB RAM, 8 cores. Ideal: RTX PRO 6000 Blackwell 48 GB, 64 GB, 16 cores. **GPUs without RT cores (A100, H100) are not supported.** aarch64: **DGX Spark only** (DGX OS 7; cuRobo/cuMotion not supported there in Isaac Sim 6.0). Jetson is not listed as an Isaac Sim host. (Note: jetson-containers lists an isaac-sim package; I did not verify it.)
- **Isaac Lab** ([README via GitHub](https://github.com/isaac-sim/IsaacLab)): v3.0.0 released 2026-10-20, main branch targets Isaac Sim 6.2; supports multiple backends and "does not require Isaac Sim for every workflow". Its own VRAM/RAM table: UNVERIFIED (use the Isaac Sim table; the GR00T README says training needs more).
- **Isaac ROS** ([getting started](https://nvidia-isaac-ros.github.io/getting_started/index.html)): supported = Jetson AGX Thor (T5000/T4000) and Orin on JetPack 7.2 with 128+ GB NVMe; x86 with Ampere+ GPU, 8 GB+ RAM, Ubuntu 24.04, CUDA 13.2+, driver 595+; DGX Spark on DGX OS 7.2.3. ROS 2 **Lyrical**. Docker is the recommended mode (`isaac-ros init docker`, needs NVIDIA Container Toolkit).
- **GR00T** ([repo](https://github.com/NVIDIA/Isaac-GR00T)): N1.7 GA (release tag 2026-04-18), open VLA model, code Apache-2.0, weights NVIDIA Open Model License, commercially usable. Inference: 1 GPU with 16 GB+ VRAM (RTX 4090, L40, H100, Jetson AGX Thor/Orin, DGX Spark); ~28 Hz on Thor with TensorRT, ~40 Hz on RTX PRO 6000 Blackwell. Fine-tune: 40 GB+ VRAM recommended.
- **Cosmos** ([repo](https://github.com/NVIDIA/Cosmos)): Cosmos 3 (May 2026) family: Super 64B (H200/B200/GB200), Nano 16B (RTX Pro 6000/H100/B200), **Edge 4B (Jetson AGX Orin / Thor / RTX Pro 6000)** released Jul 2026. Reasoner + Generator towers; OpenAI-compatible serving via vLLM, vLLM-Omni or NIM. License shown by GitHub API: NOASSERTION (read the license before commercial use).
- **Holoscan**: [SDK v5.0.0](https://github.com/nvidia-holoscan/holoscan-sdk) (2026-10-21, Apache-2.0), an AI sensor-processing platform. Detail on Jetson/IGX support: UNVERIFIED.
- **Metropolis / DeepStream**: [developer.nvidia.com/deepstream-sdk](https://developer.nvidia.com/deepstream-sdk) redirects to [github.com/NVIDIA/DeepStream](https://github.com/NVIDIA/DeepStream); I did not open it, so version, platforms and licence are UNVERIFIED.
- **NIM**: [NIM docs](https://docs.nvidia.com/nim/index.html) describe microservices for foundation-model deployment, part of NVIDIA AI Enterprise, with a NIM Operator. Jetson support and free-dev-use terms: UNVERIFIED.
- **Omniverse**: not researched beyond Isaac Sim (which is built on it). UNVERIFIED.

### 1.5 Prices (volatile)

- Jetson price hike reported July 2026 ([Hardware Busters](https://hwbusters.com/news/nvidia-jetson-prices-jump-up-to-101-the-249-orin-nano-super-is-now-399/), citing a US table; the same piece says NVIDIA gave no reason and the kits were out of stock on the NVIDIA US Marketplace): AGX Thor Dev Kit $3,499 to **$5,499**; AGX Orin Dev Kit $1,999 to **$3,499**; Orin Nano Super Dev Kit $249 to **$399**; AGX Orin 32GB module $899 to $1,799. I did not confirm on NVIDIA's own store (CNX Software's article returned 403).
- DGX Spark Founders Edition: $3,999 to **$4,699** in Feb 2026 per [Tom's Hardware](https://www.tomshardware.com/desktops/mini-pcs/nvidia-dgx-spark-gets-18-percent-price-increase-as-memory-shortages-bite-founders-edition-now-usd4-699-up-from-usd3-999) (NVIDIA forum thread: [price change announcement](https://forums.developer.nvidia.com/t/2-23-2026-price-change-announcement/361713), title only seen in search).
- Raspberry Pi 5 16GB: $305 ([product page](https://www.raspberrypi.com/products/raspberry-pi-5/); other RAM sizes' prices not shown).
- Takeaway: memory-driven price instability. Do not hard-code hardware prices in product marketing.

### 1.6 Startup / partner programs

- [NVIDIA Inception](https://www.nvidia.com/en-us/startups/): free; incorporated, under 10 years old, working website, founder-operated; no revenue required. Benefits: training, SDK access, cloud credits (amounts unspecified), VC introductions, "preferred pricing on a subset of enterprise-grade GPUs and select hardware" as a rebate through the supplier (NVIDIA does not sell directly to members). No Jetson-specific discount listed. Excludes resellers/distributors, consulting firms, CSPs.
- [NVIDIA-Certified Systems](https://www.nvidia.com/en-us/data-center/products/certified-systems/): certification for data-center servers, workstations (RTX PRO), and edge systems (enterprise and industrial). Vendors pass functional, security and performance tests plus thermal/mechanical/power qualification. The page does not mention Jetson; whether a Jetson-based OEM system can be "certified" is UNVERIFIED. OEM program terms for module resale (Jetson partner/"Jetson ecosystem"): UNVERIFIED, not researched.

---

## 2. Robotics software on clusters

### 2.1 ROS 2 distro status

- **Lyrical Luth**, released 2026-05-22 ([release page source](https://github.com/ros2/ros2_documentation), `Release-Lyrical-Luth.rst`, and [Discourse announcement](https://discourse.openrobotics.org/t/ros-2-lyrical-luth-released/55021)): twelfth ROS 2 release, **LTS supported until May 2031**. Platform table (`lyrical/supported-platforms.rst`): **Tier 1 = Ubuntu 26.04 (Resolute) amd64/arm64 and Windows 11 amd64; Ubuntu 24.04 (Noble) is Tier 3 (source build) and early-EOL 2029-06-01**.
- **Jazzy Jalisco**: LTS, May 2024 to May 2029, Tier 1 Ubuntu 24.04 amd64/arm64 ([REP-2000](https://github.com/ros-infrastructure/rep/blob/master/rep-2000.rst)). **Humble**: LTS to May 2027 (Ubuntu 22.04). **Kilted**: non-LTS, EOL Nov 2026 (this month).
- **Critical tension for OneMind**: JetPack 7.2 is Ubuntu 24.04, and Isaac ROS targets Lyrical there through its own buildfarm (Isaac ROS page), while upstream Tier 1 for Lyrical is Ubuntu 26.04. Containers resolve this: run the ROS distro of your choice in a container (Ubuntu userland inside) on whatever host OS.
- Default RMW is still Fast DDS ([Discourse post title, not opened](https://discourse.openrobotics.org/t/ros-2-lyrical-luth-and-11-years-of-fast-dds-as-ros-2-default-middleware/55062)). rmw_zenoh tier status in Lyrical: UNVERIFIED (docs.ros.org returned Anubis access-denied).

### 2.2 DDS vs Zenoh

[rmw_zenoh README](https://github.com/ros2/rmw_zenoh): binary packages `ros-<distro>-rmw-zenoh-cpp` for supported distros on Tier 1 platforms; multicast discovery **off by default**, so a **Zenoh router** (`rmw_zenohd`) is needed; cross-host via router-to-router links or client mode; shared memory optional; **Humble cannot talk to newer distros**; does **not interoperate** with `zenoh-plugin-ros2dds` / `zenoh-bridge-ros2dds`; known issues with IPv4-only hosts (default listens on IPv6) and SHM under load. Repo is active (push 2026-11-07, Apache-2.0). The Lyrical notes say `rmw_fastrtps_cpp` and `rmw_zenoh_cpp` can use the new `rosidl::Buffer` feature for `uint8[]` (hardware-accelerator buffer backends).

Zenoh ecosystem ([eclipse-zenoh/zenoh](https://github.com/eclipse-zenoh/zenoh) 1.10.2; [zenoh-plugin-mqtt](https://github.com/eclipse-zenoh/zenoh-plugin-mqtt); [zenoh-plugin-ros2dds](https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds)): pub/sub + storage + query, with an MQTT bridge and a ROS 2-over-DDS bridge (for DDS-RMW fleets). Zenoh and PX4 uXRCE-DDS interplay: UNVERIFIED.

### 2.3 ROS 2 on Kubernetes / fleets

- I found no authoritative "ROS 2 on Kubernetes" reference (a GitHub repo search returned nothing relevant). Patterns below are **PROPOSAL**: (a) one robot = one k3s/KubeEdge edge node; (b) ROS graph stays local on the robot (`ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` or a per-robot Zenoh router); (c) cross-robot/cloud traffic goes through a bridge (Zenoh router link, or ROS-to-NATS gateway), never raw DDS multicast over a VPN.
- [KubeEdge](https://github.com/kubeedge/kubeedge) (v1.23.1, 2026-07-15, Apache-2.0): Kubernetes extension for edge with cloud/edge parts, metadata sync and MQTT device access. [k3s](https://github.com/k3s-io/k3s) v1.37.2+k3s1 (2026-11-03). Offline autonomy details for KubeEdge: UNVERIFIED (docs 404'd).
- **Open-RMF** ([rmf](https://github.com/open-rmf/rmf), [rmf_ros2](https://github.com/open-rmf/rmf_ros2)): multi-fleet manager; fleet adapters for commercial robots via `fleet_adapter_template`, `free_fleet` for robots with native ROS navigation; supports Humble, Jazzy, Kilted, Rolling, amd64 and aarch64. Lyrical support: UNVERIFIED (not in the list I read). Other fleet managers: not researched.
- NVIDIA scheduling: [KAI Scheduler](https://github.com/kai-scheduler/KAI-Scheduler) (Apache-2.0, v0.18.7, 2026-11-02) exists for GPU workloads; description not read, so use is UNVERIFIED.

### 2.4 Drone stacks

- [PX4](https://github.com/PX4/PX4-Autopilot) v1.17.0 (2026-05-13, BSD-3). [ArduPilot](https://github.com/ArduPilot/ardupilot) Plane-4.7.2 (2026-10-14, GPL-3.0). [MAVSDK](https://github.com/mavlink/MAVSDK) v4.1.0 (2026-10-27, BSD-3).
- [MAVLink](https://mavlink.io/en/): pub/sub streams + point-to-point with retransmit (missions, params); MAVLink 2 (12 bytes overhead), authentication/signing, up to 255 systems; XML dialects with generators (C, C++, Python, Rust, Java, C#, JS); message XML and generated C are MIT; under Dronecode (Linux Foundation).
- [PX4 uXRCE-DDS](https://docs.px4.io/main/en/middleware/uxrce_dds.html): PX4 exposes uORB to ROS 2 via a Micro XRCE-DDS client on the flight controller and an Agent on the companion computer (serial or UDP only). **"The DDS transport is unauthenticated and reaches uORB directly, so the DDS network must be kept isolated."** Lyrical/Rolling need Fast DDS 3.6.x and Agent 3.0.2, with `UXRCE_DDS_CLIENT_USE_DDS_V3` set when building PX4 (PX4 v1.18 doc).
- **Implication**: keep MAVLink/DDS on a local link on the vehicle; put a NATS/MQTT gateway (authenticated) on the companion computer. TAK/ATAK path for vehicles: UNVERIFIED (not researched).

### 2.5 Bridges to NATS/MQTT

- I found no maintained generic ROS 2-to-NATS bridge (GitHub search returned empty). **PROPOSAL**: write a thin "robot gateway" service (rclcpp/rclpy or Zenoh) that maps selected ROS topics to NATS subjects with JetStream for reliable telemetry and request/reply for commands.
- MQTT: Zenoh MQTT plugin (above); KubeEdge MQTT device path; Meshtastic MQTT (below). NATS server v2.15.2 (2026-10-26) supports leaf nodes (section 7). NATS MQTT bridge-in-server: UNVERIFIED (not opened).

---

## 3. IoT, home and agriculture automation

- **Home Assistant** ([core](https://github.com/home-assistant/core) 2026.11.1): [Matter integration](https://www.home-assistant.io/integrations/matter/): HA is a Matter **controller** only (not a bridge for its own devices); official Matter Server app on HA OS is the supported setup (standalone Docker unsupported); phone does commissioning over Bluetooth by scanning the QR; Thread needs a Thread border router (e.g., HA OpenThread Border Router app on a ZBT-1/ZBT-2/SkyConnect, or Nest Hub, HomePod mini, Apple TV 4K); Matter depends on IPv6 + mDNS multicast, which VLANs and IGMP snooping can break; OTA updates for Thread devices fail with Apple border routers.
- **Matter** SDK: [connectedhomeip](https://github.com/project-chip/connectedhomeip) v1.6.1.0 (2026-09-25, Apache-2.0). **Thread**: [ot-br-posix](https://github.com/openthread/ot-br-posix) v2026.11.0.
- **Zigbee/Z-Wave**: [Zigbee2MQTT](https://github.com/Koenkk/zigbee2mqtt) 2.14.3 (GPL-3.0, publishes to MQTT); [Z-Wave JS UI](https://github.com/zwave-js/zwave-js-ui) v11.26.2 (MIT). HA's built-in Zigbee (ZHA) and Z-Wave integrations: UNVERIFIED (not opened).
- **ESPHome** ([guide](https://esphome.io/guides/getting_started_hassio.html), [repo](https://github.com/esphome/esphome) 2026.10.2): YAML to firmware for ESP32/ESP8266/RP2040/nRF52 (sidebar lists platforms); first flash by USB, later OTA; auto-discovery by mDNS in HA; has Native API, MQTT client, and Improv (BLE/serial) provisioning components (existence confirmed by sidebar only; behavior UNVERIFIED).
- **LoRaWAN**: [ChirpStack](https://www.chirpstack.io/docs/) open-source network server, regions incl. US915/EU868/AU915, classes A/B/C, LoRaWAN 1.0.x/1.1; gRPC API; repo [v4.20.0, MIT](https://github.com/chirpstack/chirpstack). MQTT integration specifics: UNVERIFIED (page did not cover).
- **Meshtastic**: [firmware](https://github.com/meshtastic/firmware) v2.7.26 (GPL-3.0). **MQTT gateway** ([docs](https://meshtastic.org/docs/software/integrations/mqtt/)): any node with internet can uplink/downlink per channel; topics `msh/REGION/2/e/CHANNEL/USERID` (protobuf) and `.../json/...` (JSON, not on nRF52); duplicates from multiple gateways must be de-duplicated by packet ID; public broker is zero-hop; on private brokers avoid the default PSK. **ATAK plugin** ([repo](https://github.com/meshtastic/ATAK-Plugin) 1.1.42, GPL-3.0): requires the Meshtastic Android app + ATAK-CIV; converts CoT (PLI, GeoChat, sensor data, generic CoT with EXI) to Meshtastic protobuf, fountain-codes anything over 231 bytes; file transfer capped at 56 KB and requires Short_Turbo; default hop limit 3 (range 1-7); optional AES-256-GCM extra encryption. It goes via the phone app, so a self-hosted box needs a Meshtastic node on MQTT/serial instead (**PROPOSAL**: an "mesh-gateway" service translating Meshtastic MQTT to NATS and CoT to TAK Server).
- **Reticulum** ([manual](https://reticulum.network/manual/whatis.html), [repo](https://github.com/markqvist/Reticulum) 1.6.0, 2026-11-07): non-IP crypto networking stack in Python; interfaces include LoRa (RNode), packet-radio KISS TNC, serial, TCP/UDP, I2P, Ethernet/Wi-Fi; no central address coordinator; no source addresses in packets; X25519/Ed25519, AES-256-CBC + HMAC-SHA256; works above 5 bit/s with 500-byte MTU. Repo license shows NOASSERTION: read before bundling.
- **Greenhouse/ag controller patterns**: I found no authoritative source in this session; the following is **PROPOSAL**: ESP32/ESPHome nodes (sensors + relays) on a local broker, setpoints and schedules owned by the box, local failsafe rules running on the device (safe state on loss of box), telemetry uplink via NATS. Marked UNVERIFIED as best practice.

---

## 4. Device onboarding by QR code (patterns to copy)

| System | What the QR carries | Source |
|---|---|---|
| **Matter** | String starting `MT:` (base-38). Fields: 3-bit version (000 for Matter 1.0 to 1.6.1), vendor ID and product ID (16-bit each), 12-bit discriminator, 27-bit setup passcode, commissioning flow, discovery capabilities. Passcode seeds PASE (password-authenticated session). Manual pairing code is 11 digits (21 if non-standard flow). Reference tool: [SetupPayload.py](https://github.com/project-chip/connectedhomeip/blob/master/src/setup_payload/python/README.md). | [Silicon Labs Matter commissioning](https://docs.silabs.com/matter/2.7.0/matter-overview-guides/matter-commissioning), search-result summary (spec §5.1 not opened) |
| **Wi-Fi Easy Connect (DPP)** | Product QR or NFC; public-key authentication; supports multiple configurators; devices stay connected across SSID changes. DPP role details not on the page. | [Wi-Fi Alliance](https://www.wi-fi.org/discover-wi-fi/wi-fi-easy-connect) |
| **k3s** | `K10<sha256(CA)>::<credentials>` secure token: joining node downloads the CA, checks the hash, then verifies the server cert; short token skips this (MITM risk). Bootstrap tokens `[a-z0-9]{6}.[a-z0-9]{16}`, default 24 h TTL, 0 = never; agent token does not expire by default; server token = admin. | [k3s token docs](https://docs.k3s.io/cli/token) |
| **KubeEdge** | `keadm gettoken` on cloud, `keadm join --cloudcore-ipport=IP:10000 --token=...` on edge; needs ports 10000/10002; keadm does not install K8s or a runtime; edge and cloud same KubeEdge version. | [keadm install](https://kubeedge.io/docs/setup/install-with-keadm) |
| **balena** | Provisioning-key flow not confirmed. I only confirmed that docs list API keys and fleet management, and a [fleet-management masterclass](https://docs.balena.io/learn/more/masterclasses/fleet-management.md) covers config/variables/tags/release pinning. QR provisioning in balena: UNVERIFIED. | |
| **HA companion app** | Phone scans the device QR and sends Wi-Fi/Thread credentials to the device over Bluetooth. | [HA Matter](https://www.home-assistant.io/integrations/matter/) |

**PROPOSAL: "OneMind Join" QR** (compose, do not invent crypto):
1. Box generates a short-lived, single-use enrollment token (k3s bootstrap-token pattern, minutes not 24 h) bound to a role (robot, sensor, XR).
2. QR payload = URL/scheme containing: box URL, CA fingerprint (k3s `K10` idea: client pins the CA hash before sending secrets), token, and requested role. Keep it small (Matter's payload is a few dozen bytes plus a passcode).
3. Device side: phone or the device itself scans, verifies CA hash, enrolls, receives a per-device identity (NATS creds + Tailscale/Headscale node key). The token is burned on use.
4. For constrained devices that cannot scan (sensors): QR printed on the device carrying a device-unique passcode (Matter model), scanned by the phone, which acts as the commissioner (HA model).
5. For robots with cameras: robot displays a QR or reads the box's QR; either direction is workable.

---

## 5. Hardware capability auto-detection

Sourced building blocks:
- [Node Feature Discovery](https://github.com/kubernetes-sigs/node-feature-discovery) v0.20.1 (Apache-2.0): `nfd-worker` DaemonSet detects hardware/OS features and publishes `NodeFeature` objects; `nfd-master` evaluates rules and labels nodes with `feature.node.kubernetes.io/...` (for example `cpu-cpuid.AESNI`); supports Kubernetes 1.24+. Feature-source list and NodeFeatureRule CRD details: UNVERIFIED (docs 404'd), though the existence of rules is stated.
- **GPU Feature Discovery**: the standalone [NVIDIA/gpu-feature-discovery](https://github.com/NVIDIA/gpu-feature-discovery) repo is **archived** (last release v0.8.2, 2023); GFD is now part of [k8s-device-plugin](https://github.com/NVIDIA/k8s-device-plugin) since v0.15.0, enabled with `gfd.enabled=true`, deployable without the device plugin (`devicePlugin.enabled=false`), and uses NFD. Labels such as `nvidia.com/gpu.product`; with time-slicing, `-SHARED` suffix and `nvidia.com/<resource>.replicas`. The full label list (memory, compute capability) was not in the pages I read: UNVERIFIED.
- **Olares** ([repo README](https://github.com/beclab/Olares)): Kubernetes-based (k3s, KubeSphere), "pool GPUs and other accelerators across nodes, with time-slicing, memory-slicing, and exclusive GPU modes"; Linux script needs 4+ cores and 8 GB RAM, dedicated GPU optional. Detection internals: UNVERIFIED (its GPU concepts doc returned 404).
- **Umbrel** ([umbrelOS](https://umbrel.com/umbrelos)): supports NVIDIA, AMD and Intel graphics; apps like Ollama and Jellyfin use them; "finds your GPU automatically". Mechanism: UNVERIFIED.
- inxi / lshw / hwinfo: not opened. UNVERIFIED (generic Linux tools; do not cite as researched).
- Jetson note: integrated (Tegra) GPU needs toolkit 1.11+ (see 1.3); whether NFD/GFD label Jetson properly is UNVERIFIED, so test on a real Orin before promising it.

**PROPOSAL: capability model.** Each node publishes a `NodeCapabilities` document (also as node labels), computed from NFD + GFD/NVML + custom probes:

```
cpu:        {arch: arm64|amd64, cores, isa_flags[]}
memory:     {total_gb, unified: bool}          # unified on Spark/Thor/Orin, true "VRAM" = shared pool
accel:      [{kind: cuda|rocm|oneapi|npu, product, vram_gb, compute_cap, unified: bool,
              rt_cores: bool, driver, cuda_version, sharing: exclusive|timeslice|mig}]
storage:    {free_gb, nvme: bool}
network:    {gbps, wifi, lora?, thread?, zigbee?, mesh?}
io/sensors: [{bus: usb|csi|gpio|can|serial, kind: camera|lidar|imu|gps|radio, vid_pid}]
os:         {distro, kernel, jetpack?, container_runtime, k8s_role}
power:      {mains|battery, budget_w}
```

App manifests declare `requires` and `recommends` against that model, and the UI says "can / can't / can with caveats":
- Isaac Sim: `accel.rt_cores=true`, `vram_gb>=16`, `memory>=32`, `arch=amd64` or the Spark exception (from section 1.4); A100/H100 fail by rule.
- GR00T inference: `accel.vram_gb>=16` (unified memory counts: Spark/Thor/Orin qualify per README); fine-tune: `vram_gb>=40`.
- Cosmos3-Edge (4B): Jetson AGX Orin/Thor or RTX PRO 6000 per README; Cosmos3-Nano 16B: RTX PRO 6000/H100/B200 class.
- Isaac ROS: Thor/Orin with JetPack 7.2, or Ampere+ x86 8 GB+, or Spark.
- Matter/Thread apps: `io` has a Thread radio or `network.thread`; warn when VLAN/IGMP snooping is detected (HA doc).
Rules should be data (CEL/NodeFeatureRule-style) so third-party apps can ship their own. Important caveat: "VRAM" on unified-memory machines (Spark 128 GB shared) is not comparable to discrete VRAM; encode `unified` explicitly.

---

## 6. XR

- **WebXR** ([W3C spec](https://immersive-web.github.io/webxr/)): Candidate Recommendation Snapshot dated 2022-03-31 (later changes not read). Modes `inline`, `immersive-vr`, `immersive-ar` (AR in separate module). [MDN](https://developer.mozilla.org/en-US/docs/Web/API/WebXR_Device_API): marked not Baseline and experimental; HTTPS-only; depends on Permissions-Policy `xr-spatial-tracking`. Feature-detect with `navigator.xr.isSessionSupported`. Quest: [Meta docs](https://developers.meta.com/horizon/documentation/web/webxr-overview) say do not infer support from the user agent; Immersive Web SDK recommended; mixed reality, hand tracking, layers linked (details not read).
- **Vision Pro / Safari**: WebXR on by default since visionOS 2, **immersive-vr only** as of May 2025, immersive-ar still in development (secondary sources: [Road to VR](https://roadtovr.com/visionos-2-webxr-support-vision-pro/), [UploadVR](https://uploadvr.com/visionos-2-apple-vision-pro-webxr)); current (2026) AR status: UNVERIFIED. A June 2026 article mentions "Web Environments" default in visionOS 27 ([VR.org](https://vr.org/articles/visionos-27-developer-features-safari-requestimmersive-spatial-web)), a separate feature.
- **Android XR** ([developer overview](https://developer.android.com/develop/xr)): headsets, wired XR glasses, audio glasses, display glasses; Jetpack XR SDK (Compose for XR, Compose Glimmer, SceneCore, ARCore for Jetpack XR); Unity, Godot, Unreal; OpenXR and WebXR; Android Studio emulators. Devices: [Samsung Galaxy XR](https://9to5google.com/2025/10/21/samsung-galaxy-xr-launch/) launched 2025-10-21 at $1,799 (Chrome with WebXR per a review summary); [Xreal Aura](https://9to5google.com/guides/xreal-project-aura/) tethered glasses with 70-degree FOV, Snapdragon Reality Elite puck, **price reports conflict** ($1,099, $1,279, "under $1,500"; ship Oct 28 or Nov 2026): treat as unconfirmed.
- **OpenXR** ([Khronos](https://www.khronos.org/openxr/)): royalty-free, v1.1 current; conformant runtimes include Android XR, Meta Quest line, Monado (open-source), Magic Leap 2, HTC, Pico, Varjo, SteamVR. Apple Vision Pro is not in that list.
- **TAK and XR**: I found no "TAK XR" product. [VR-TAK](https://www.ara.com/vr-tak/) (ARA, formerly VTAK) is a VR TAK client for Quest/Quest 2/Quest 3 with 3D terrain annotation and TAK Server connectivity (sources 2020-2021, may be stale); tak.gov lists it in the TAK family. 3D CoT rendering and any AR mode: UNVERIFIED.
- **Self-hosted box serving XR (PROPOSAL)**: the box serves a WebXR/PWA over HTTPS (needed for `navigator.xr`) behind the Tailscale/Headscale or local TLS; digital-twin scene = glTF/USD assets + live state over WebSocket from NATS (JetStream for history); target Quest Browser and Android XR Chrome first (both documented to support WebXR); treat Vision Pro as VR-only until verified; keep native OpenXR/Unity/Jetpack XR as a later layer. Capability model gains `xr_client` entries (headset, passthrough yes/no).

---

## 7. Mesh and off-grid networking for homesteads

- **Meshtastic / Reticulum**: see section 3. Meshtastic suits low-rate text/telemetry/PLI with TAK (via the plugin); Reticulum is a general crypto network stack over very slow links with LoRa, TCP, serial.
- **batman-adv** ([kernel doc](https://www.kernel.org/doc/html/latest/networking/batman-adv.html)): Layer 2 mesh kernel module, emulates a virtual switch across nodes so IPv4/IPv6/DHCP run unchanged; `bat0` interface, `batctl` tooling; works over Wi-Fi, Ethernet, VPNs. BATMAN_V not covered by the page.
- **Tailscale / Headscale**: [Headscale](https://github.com/juanfont/headscale) v0.29.7 (BSD-3, 2026-10-30) is a self-hosted Tailscale control server; it exchanges WireGuard public keys, assigns IPs and advertises routes; **scope is a single tailnet** for personal use or a small organisation. DERP/relay fallback: UNVERIFIED (Tailscale page did not cover).
- **NATS leaf nodes** ([docs](https://docs.nats.io/running-a-nats-service/configuration/leafnodes)): the leaf dials **out** to a hub (hub listens on 7422), so NAT-friendly; multiple hub URLs for failover; creds and account binding isolate subjects; interest propagates both ways, so only subscribed subjects cross the link. **JetStream on a leaf needs its own domain** or it collides with/extends the hub's ([JetStream leaf doc](https://docs.nats.io/running-a-nats-service/configuration/leafnodes/jetstream_leafnodes)); mirrors/sources are the named mechanism for factory-local copies and sourcing up to a hub, but the pages I read did not describe buffering or store-and-forward during outages, so intermittent-link behavior is **UNVERIFIED** and must be tested.
- **Homestead topology (PROPOSAL)**: LAN/Wi-Fi + batman-adv for the farm; Tailscale/Headscale for remote reach; NATS leaf per site/vehicle with its own JetStream domain and stream sources up to the hub; Meshtastic/Reticulum as the fallback control channel when IP is down.

---

## Implications for OneMind OS architecture

What must be native from day one (otherwise robotics/IoT/XR become bolt-ons):

1. **Node identity and enrollment as a first-class primitive.** One token/QR-based join flow (section 4) for boxes, robots, sensors and headsets, producing per-device identity (NATS creds + mesh VPN key + k8s join). Pin the CA hash in the payload; short TTL, single-use tokens.
2. **A hardware capability model** published by every node (section 5) and consumed by the app store/scheduler: unified memory, RT-core presence, driver/JetPack versions, radios and buses. Required because Isaac Sim excludes A100/H100, runs on aarch64 only on DGX Spark, and Jetson hosts are a different OS/CUDA line from x86.
3. **Two-tier compute model: box (k3s server) and edge nodes (k3s agent or KubeEdge) with offline autonomy.** Robots and drones must keep working when the link drops, so every edge node runs a NATS leaf with its own JetStream domain and sources/mirrors to the hub; validate the outage behavior early (docs do not guarantee it).
4. **NATS subject grammar that includes device class and site** (telemetry, command, event, twin state) with per-device accounts/ACLs; MQTT, Meshtastic, Zenoh and ROS 2 are gateways into that grammar. Keep ROS graphs local to each robot; do not expose DDS/uXRCE-DDS across the network (PX4 states it is unauthenticated).
5. **Container-first robotics runtime.** ROS distro decoupled from host OS: JetPack 7.2 is Ubuntu 24.04, Lyrical Tier 1 is Ubuntu 26.04, Jazzy (to 2029) is Tier 1 on 24.04. Ship pinned, multi-arch (amd64/arm64) images; support the NVIDIA Container Toolkit with Tegra mode (1.11+).
6. **Time-series + geo state + digital twin store** that feeds three consumers with one source of truth: TAK Server (CoT), dashboards, and XR clients (WebXR over HTTPS with glTF/USD assets).
7. **Protocol adapters as plug-ins, not core:** Matter (controller via HA or own), Zigbee2MQTT, Z-Wave JS, ESPHome, ChirpStack/LoRaWAN, Meshtastic gateway, MAVLink/PX4 gateway, Open-RMF fleet adapters. Home Assistant is a controller only for Matter, so plan whether OneMind exposes devices as a Matter bridge (UNVERIFIED feasibility).
8. **Mesh-first networking assumptions**: Headscale for overlay (single tailnet scope: plan multi-tenant separation), batman-adv for local mesh, LoRa fallback channels with tiny payload budgets (Meshtastic 231-byte packets / 56 KB file cap).
9. **Safety/failsafe contract** for anything that moves or controls heat/water: device-local safe states, signed commands, command TTLs. (**PROPOSAL**; no source in this research.)
10. **Plan for supply and price volatility:** Jetson and DGX Spark prices rose sharply in 2026. Support heterogeneous hardware and let the capability model, not SKUs, define "supported".

Open verification items before committing: Jetson GPU Operator/NFD behavior on JetPack 7, NATS leaf outage buffering, rmw_zenoh tier in Lyrical, Open-RMF on Lyrical, DeepStream/NIM on Jetson licensing, NVIDIA Jetson OEM/partner terms, visionOS immersive-ar status, Olares and Umbrel detection mechanics.

---

## Hardware tiers (proposal; prices only where sourced)

| Tier | Role | Example real hardware | Sourced price | Notes |
|---|---|---|---|---|
| **Lite** | Home box: apps, MQTT/Matter hub, small LLMs, no GPU | Raspberry Pi 5 16GB (Cortex-A76 quad, [Pi page](https://www.raspberrypi.com/products/raspberry-pi-5/)); Umbrel Home ([umbrelOS](https://umbrel.com/umbrelos)) | Pi 5 16GB $305 (board only); Umbrel Home price not shown | Olares needs 4+ cores / 8 GB; Pi-class suits HA + NATS + k3s, not AI |
| **Pro** | Home/small-office AI box, discrete or big unified GPU | Olares One (RTX 5090 Mobile 24 GB, 96 GB RAM, 2 TB; [olares.com](https://www.olares.com/)); DGX Spark (128 GB unified, GB10) | Olares One: **conflicting** ($2,999 / $3,999 / $4,999 per [search results](https://one.olares.com/products/olares-one)); DGX Spark FE $4,699 | Spark is the only aarch64 host for Isaac Sim and supports GR00T inference; ConnectX-7 for clustering |
| **Omni** | Sim/training/world-model host, multi-user | DGX Station (GB300; 252 GB HBM3e + 496 GB LPDDR5X, 1,600 W); x86 + RTX PRO 6000 Blackwell workstation (Isaac Sim "ideal" tier) | DGX Station: not listed; RTX PRO 6000 box: price UNVERIFIED | Needs 20 A circuit for Station; Isaac Sim ideal: 48 GB VRAM, 64 GB RAM, 16 cores |
| **Edge** | Small autonomy/vision node, greenhouse/camera/sensor gateway | Jetson Orin Nano Super Dev Kit (up to 67 TOPS, 8 GB, 7-25 W); Orin NX modules | Dev kit **$399** (post July 2026 hike; was $249) | Runs JetPack 7.2 containers; Cosmos3-Edge targets AGX Orin/Thor, not Nano |
| **Robotics** | On-robot brain: VLA policy, perception, Isaac ROS | Jetson AGX Thor Dev Kit (128 GB, up to 2070 FP4 TFLOPS, 40-130 W); Jetson AGX Orin Dev Kit 64GB (275 TOPS) | Thor kit **$5,499**; AGX Orin kit **$3,499** (post-hike per Hardware Busters, not confirmed on NVIDIA store) | GR00T N1.7 ~28 Hz on Thor (TensorRT); Isaac ROS officially supports Thor T5000/T4000 and Orin |

XR clients (not a tier, endpoints): Samsung Galaxy XR $1,799 (launch price, 2025); Xreal Aura price unconfirmed (reports $1,099 to $1,279).

---

## Sources (all opened or returned during this session)

NVIDIA: https://developer.nvidia.com/embedded/jetson-modules ; https://developer.nvidia.com/embedded/jetson-developer-kits ; https://developer.nvidia.com/embedded/jetpack ; https://docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/index.html ; https://docs.nvidia.com/jetson/jetpack/install-setup/index.html ; https://www.nvidia.com/en-us/products/workstations/dgx-spark/ ; https://www.nvidia.com/en-us/products/workstations/dgx-station/ ; https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html ; https://nvidia-isaac-ros.github.io/getting_started/index.html ; https://github.com/NVIDIA/Isaac-GR00T ; https://github.com/NVIDIA/Cosmos ; https://github.com/isaac-sim/IsaacLab ; https://github.com/nvidia-holoscan/holoscan-sdk ; https://github.com/NVIDIA/k8s-device-plugin ; https://github.com/NVIDIA/gpu-feature-discovery ; https://github.com/kai-scheduler/KAI-Scheduler ; https://docs.nvidia.com/nim/index.html ; https://www.nvidia.com/en-us/startups/ ; https://www.nvidia.com/en-us/data-center/products/certified-systems/ ; https://github.com/dusty-nv/jetson-containers ; https://hwbusters.com/news/nvidia-jetson-prices-jump-up-to-101-the-249-orin-nano-super-is-now-399/ ; https://www.tomshardware.com/desktops/mini-pcs/nvidia-dgx-spark-gets-18-percent-price-increase-as-memory-shortages-bite-founders-edition-now-usd4-699-up-from-usd3-999 ; https://forums.developer.nvidia.com/t/2-23-2026-price-change-announcement/361713

ROS/robotics: https://github.com/ros2/ros2_documentation (Release-Lyrical-Luth.rst, lyrical/supported-platforms.rst) ; https://discourse.openrobotics.org/t/ros-2-lyrical-luth-released/55021 ; https://github.com/ros-infrastructure/rep/blob/master/rep-2000.rst ; https://github.com/ros2/rmw_zenoh ; https://github.com/eclipse-zenoh/zenoh ; https://github.com/eclipse-zenoh/zenoh-plugin-mqtt ; https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds ; https://github.com/open-rmf/rmf ; https://github.com/open-rmf/rmf_ros2 ; https://docs.px4.io/main/en/middleware/uxrce_dds.html ; https://mavlink.io/en/ ; https://github.com/PX4/PX4-Autopilot ; https://github.com/ArduPilot/ardupilot ; https://github.com/mavlink/MAVSDK ; https://github.com/kubeedge/kubeedge ; https://kubeedge.io/docs/setup/install-with-keadm ; https://github.com/k3s-io/k3s ; https://docs.k3s.io/cli/token

IoT/mesh: https://www.home-assistant.io/integrations/matter/ ; https://github.com/home-assistant/core ; https://github.com/project-chip/connectedhomeip ; https://github.com/project-chip/connectedhomeip/blob/master/src/setup_payload/python/README.md ; https://docs.silabs.com/matter/2.7.0/matter-overview-guides/matter-commissioning ; https://github.com/openthread/ot-br-posix ; https://github.com/Koenkk/zigbee2mqtt ; https://github.com/zwave-js/zwave-js-ui ; https://esphome.io/guides/getting_started_hassio.html ; https://github.com/esphome/esphome ; https://www.chirpstack.io/docs/ ; https://github.com/chirpstack/chirpstack ; https://meshtastic.org/docs/software/integrations/mqtt/ ; https://github.com/meshtastic/ATAK-Plugin ; https://github.com/meshtastic/firmware ; https://reticulum.network/manual/whatis.html ; https://github.com/markqvist/Reticulum ; https://www.wi-fi.org/discover-wi-fi/wi-fi-easy-connect ; https://docs.balena.io/learn/more/masterclasses/fleet-management.md ; https://github.com/balena-os/balena-supervisor ; https://www.kernel.org/doc/html/latest/networking/batman-adv.html ; https://github.com/juanfont/headscale ; https://github.com/nats-io/nats-server ; https://docs.nats.io/running-a-nats-service/configuration/leafnodes ; https://docs.nats.io/running-a-nats-service/configuration/leafnodes/jetstream_leafnodes

Detection/platforms: https://github.com/kubernetes-sigs/node-feature-discovery ; https://github.com/beclab/Olares ; https://www.olares.com/ ; https://one.olares.com/products/olares-one ; https://umbrel.com/umbrelos ; https://www.raspberrypi.com/products/raspberry-pi-5/

XR: https://immersive-web.github.io/webxr/ ; https://developer.mozilla.org/en-US/docs/Web/API/WebXR_Device_API ; https://developers.meta.com/horizon/documentation/web/webxr-overview ; https://developer.android.com/develop/xr ; https://www.khronos.org/openxr/ ; https://roadtovr.com/visionos-2-webxr-support-vision-pro/ ; https://uploadvr.com/visionos-2-apple-vision-pro-webxr ; https://vr.org/articles/visionos-27-developer-features-safari-requestimmersive-spatial-web ; https://9to5google.com/2025/10/21/samsung-galaxy-xr-launch/ ; https://9to5google.com/guides/xreal-project-aura/ ; https://www.ara.com/vr-tak/

Limitations: several docs.ros.org and open-mesh.org pages returned Anubis access-denied; CNX Software returned 403; balena, Olares GPU concepts, NFD feature docs and GPU Operator docs 404'd. Search-result pages (WebSearch summaries) were used for visionOS, Galaxy XR, Xreal, Olares price, Matter payload and VR-TAK; those are secondary and flagged.
