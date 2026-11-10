# OneMind OS: Hardware

Sources for competitor specs and prices: `research/competitors/landscape.md`, `umbrel.md`, `olares.md`, and `research/platform/robotics-iot-xr-nvidia.md` (prices as of Nov 2026; items marked *secondary* came from press, not the vendor store). Verify prices again at purchase time.

---

## 1. What Zeus has now (D-004)

| Device | Specs | Role in the bake-off |
|---|---|---|
| **Dell Latitude 5540** | Intel i5-1345U (13th gen), 16 GB RAM, Intel UHD *(user-reported)* | **Main x86 test box** for the Lite tier: image install, k3s, dashboard, A/B rollback |
| **Beelink U55** | Most sources: Intel Core i3-5005U (2-core Broadwell, 2015), 8 GB DDR3L, 128–256 GB M.2 SSD ([droix](https://droix.net/product/beelink-u55/), [androidpctv](https://androidpctv.com/beelink-u55-a-mini-pc-with-intel-core-i3-5005u-processor/)). *One source claims an N100. Run `lscpu` on it to confirm.* | **Minimum-spec / old hardware test** and a second node for multi-node join tests. Below the Olares minimum (4 cores / 8 GB), so it shows what a low-end BYO user gets |
| **Mac** | (Apple silicon assumed; confirm model) | Dev machine, VM host for quick image tests, desktop client |
| **Android phone** | (model?) | PWA/mobile client, push alerts, QR-scan join flow |
| **Cloud (DigitalOcean)** | Existing cluster | Cluster/enterprise tier test, Market/registry hosting, CI image builds. GPU droplets can stand in for the Pro tier before buying an RTX box |

## 2. Buy list, phased (when needed)

| Phase | Item | Why | Price (sourced) |
|---|---|---|---|
| **Now (bake-off)** | **Raspberry Pi 5, 16 GB** + NVMe HAT + official 27 W PSU + case | Edge tier. Pi 5 support is the weakest point in the research, so it must be tested early | $305 board ([Pi](https://www.raspberrypi.com/products/raspberry-pi-5/)); accessories not priced |
| **Now (bake-off)** | **NVIDIA Jetson Orin Nano Super Dev Kit** (8 GB, 67 TOPS) | Robotics/edge-AI tier, Jetson image path, device plugin + CDI | **$399** (after the July 2026 increase from $249; *secondary*, [Hardware Busters](https://hwbusters.com/news/nvidia-jetson-prices-jump-up-to-101-the-249-orin-nano-super-is-now-399/)) |
| **Soon** | **Intel N150 or i3-N300 mini PC, 16 GB, 2+ NVMe slots, 2.5 GbE** | The *reference Lite box*: the same chip class as Umbrel Home (N150) and Umbrel Pro (i3-N300) | Model and price to pick at purchase |
| **Soon** | **Zigbee/Thread dongle** (e.g. Home Assistant Connect ZBT-2) + **2× Meshtastic/LoRa radios** | IoT and mesh tests (greenhouse, off-grid) | Not priced in research |
| **Later (Pro)** | **RTX GPU box, 16–24 GB VRAM** (an RTX 4080 16 GB is the Isaac Sim *minimum*) | Pro tier: local LLMs, GPU sharing (HAMi), GPU Operator on consumer RTX (unverified, must test), robot simulation | Not priced |
| **Later (Pro alt)** | **NVIDIA DGX Spark** (GB10, 128 GB unified, Arm) | The only Arm host for Isaac Sim, plus GR00T; good with Inception discounts | $4,699 Founders Edition (*secondary*, Tom's Hardware) |
| **Later (Robotics)** | **Jetson AGX Orin 64 GB** or **AGX Thor** dev kit | On-robot brain: VLA policies, Isaac ROS, GR00T (~28 Hz on Thor) | $3,499 / $5,499 (*secondary*, post-hike) |
| **Much later (Omni)** | RTX PRO 6000 workstation or DGX Station | Simulation, training, multi-user AI | Not listed / unverified |

**Tip:** apply to NVIDIA Inception (D-006) **before** buying Jetson or DGX hardware, in case discounts apply.

## 3. What competitors ship

| Product | CPU | RAM | Storage | Network / other | Price (store feed, Nov 2026) |
|---|---|---|---|---|---|
| **Umbrel Home** | Intel N150, 4-core, 6 W TDP | 16 GB DDR5 | 1/2/4 TB NVMe | GbE, 3× USB 3.0 | $499 (512 GB) – $949 (4 TB) |
| **Umbrel Pro** | Intel i3-N300, 8-core | 16 GB LPDDR5 | 4× M.2 NVMe (up to 32 TB) + 64 GB OS | 2.5 GbE, Wi-Fi 6, BT 5.2, 2× USB-C, HDMI 2.1; aluminum + walnut | $699 (no SSD) – $1,899 (8 TB) |
| **Olares One** | Intel Core Ultra 9 275HX, 24-core | 96 GB DDR5-5600 | 2 TB PCIe 4.0 | RTX 5090 Mobile 24 GB, TB5, 2.5 GbE, Wi-Fi 7, 330 W, 3.5 L | $4,999 feed (Kickstarter $2,999; prices conflict) |
| **ZimaBoard 2** | Intel (832/1664 models) | 8 / 16 GB | 32 / 64 GB eMMC | SBC, PCIe | $339 / $399 board |
| **ZimaCube 2** | i3-1215U / i5-1235U | 8 / 16 / 64 GB | multi-bay NAS | top SKU includes RTX Pro 2000; OCuLink GPU dock $179.90 | $799 / $1,299 / $2,499 |
| **Home Assistant Green** | Rockchip RK3566, 4× A55 | 4 GB LPDDR4X | 32 GB eMMC | GbE (Yellow/Blue discontinued) | $199 |
| **Start9 Server One** | AMD Ryzen 5 6600H, 6c/12t | 16 / 32 GB LPDDR5 | 2 / 4 TB NVMe | GbE, 2× HDMI; $200/yr support | Configurator (not listed) |
| **ClawBox** | Jetson Orin Nano Super | 8 GB | 512 GB NVMe | 20–25 W, Ubuntu + local models | €749 |

**Patterns:**
1. Low-power Intel N-series dominates the entry tier (Umbrel, ZimaCube).
2. Storage bays and NVMe count sell the mid tier.
3. Only Olares sells a serious GPU box, and it's expensive.
4. **Nobody sells a robotics- or mesh-ready box.** That's an opening for OneMind.

## 4. Proposed OneMind box family (reference designs, draft)

| Box | Superpower | Reference spec | Positioned against |
|---|---|---|---|
| **OneMind Edge** | Greenhouse, sensors, mesh gateway, TAK node | Pi 5 / CM5, 8–16 GB, NVMe; LoRa/Meshtastic + Zigbee/Thread radios **built in** | HA Green ($199) |
| **OneMind Lite** | Home cloud for a family | Intel N150/N300, 16–32 GB, 2–4 NVMe, 2.5 GbE, Wi-Fi 6 | Umbrel Home/Pro ($499–1,899) |
| **OneMind Pro** | Private AI and agents | Core Ultra / Ryzen + RTX 16–24 GB VRAM, 64–96 GB RAM, 2+ NVMe | Olares One ($4,999) |
| **OneMind Robotics** | On-robot / field AI brain | Jetson Orin NX/AGX/Thor carrier, rugged, CAN/serial/GPIO, PoE | ClawBox (€749, consumer only) |
| **OneMind Omni** | Simulation, training, multi-site | RTX PRO workstation or DGX-class | No consumer competitor |

Every box runs the same OneMind OS image family (D-002), and boxes form one mesh and cluster. Before any hardware sale: certification tests, warranty/support terms, and the OEM partner model (copy Olares's "Manufacture with" approach).
