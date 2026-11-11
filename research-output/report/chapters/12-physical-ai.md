# Physical AI, NVIDIA and the next ten years {#sec-physical-ai}

> **Explain it like I'm the founder.** You want to keep pace with NVIDIA and become the OS that robotics companies build on. Two truths sit side by side. **NVIDIA moves fast and ships its robot software as containers and open repos**, so OneMind can list new models and tools the day they ship, if its Jetson image tracks NVIDIA's current software line. But **NVIDIA's Jetson software has ended before its hardware every time so far**, and NVIDIA lock-in is the opposite of sovereignty. So OneMind keeps pace by design and keeps an exit by design: the same app manifest must run on non-NVIDIA chips, and a Jetson image that does not depend on Ubuntu is tested in the first 180 days. Around all this, the world itself is moving (chip blocs, sovereignty rules, shutdowns, walled AI gardens), and the foundation holds in all four futures we wrote.

## Does the base OS hold for robots for ten years? {#sec-robots-10y}

**Yes, with three conditions** (`08-robotics-drones-physical-ai.md`):

1. **Real time** is part of normal Linux since kernel 6.12 [C-W18-005]; Debian, Raspberry Pi and NVIDIA all ship real-time kernels, NVIDIA's still as a preview. On the Pi 5, memory-bus contention gave spikes over 1 ms under stress [C-REF-DC-technical-001], and two identical Orin modules differed by about 10 µs versus 90+ µs [C-REF-DC-technical-002], so each unit is acceptance-tested and loops tighter than about 1 ms go to a microcontroller.
2. **ROS 2 runs in containers on every flavor**, because ROS 2 does not officially support Debian, and its newest release does not support Jetson's Ubuntu 24.04 [C-W7-026, C-W7-027].
3. **On a Jetson, NVIDIA owns the kernel.** Orin modules are sold until January 2032 and Thor until 2035–2036 [C-W7-001, C-W7-002], but NVIDIA publishes no software support period. Branch lives have ranged from about a month to 5.7 years, and security fixes land only at the head of a branch [C-REF-W7-T-004, C-REF-W7-T-005]. So every Jetson is flashed with A/B slots at the factory and must be able to move to a new NVIDIA software line in the field.

## What NVIDIA has shipped (dated, primary) {#sec-nvidia-shipped}

| Date | Release | Why it matters |
|---|---|---|
| 2025-08 | Jetson Linux 38.2 (JetPack 7.0), Thor only [C-W7-006] | New silicon gets the new stack first |
| 2026-04 | GR00T N1.7, code Apache-2.0 [C-W7-051] | An open robot foundation model that runs on Jetson |
| 2026-06 | Cosmos 3 world models; check each model's licence [C-W7-051] | World models reach the edge |
| 2026-06 | JetPack 7.2: Orin joins JetPack 7; official Yocto via OE4T; RT kernel [C-W7-007, C-W7-008] | One stack across Orin and Thor |
| 2026-07 | Jetson T3000/T2000 announced, shipping Q1 2027; IGX T3000 with functional safety [C-W7-048] | Mainstream Thor price points |
| 2026-10 | Isaac Lab 3.0; Newton physics 1.7 (Apache-2.0) [C-W7-051] | The simulation stack moves fast |
| 2026-11 | KubeCon NA: NVKE/NVKR preview [C-W4-039]; Agent Substrate to CNCF Sandbox [C-W4-040] | Data-centre tools, not edge tools (re-check by 2026-12-10) |

**"Keep pace on day one" (F-2), realistically:** list NVIDIA's apps (Isaac ROS, GR00T, Cosmos) in the Market the day they ship, as long as the Jetson flavor already runs the JetPack major they target; keep the Jetson flavor on the **current JetPack major within 60 days** of release (30 is the stretch goal); boot new modules such as T3000/T2000 on the same r39 line with a device-tree addition, not a new flavor, and test this when the dev kits ship.

## Physical AI 2026–2036: what to watch {#sec-pai-trends}

These are **proposals**: scenario reasoning on the evidence above, not sourced forecasts (`08` §12.3).

| Horizon | Expected shift | Signal | What OneMind does |
|---|---|---|---|
| 2027–2028 | Vision-language-action models run on robots with Thor-class modules | GR00T and Cosmos list T2000/T3000 as targets | Robot flavor on r39+; per-device model engines |
| 2027–2029 | ROS 2 Lyrical becomes the default; Jazzy ends May 2029 [C-W7-029] | Isaac ROS and Open-RMF support Lyrical | Ship Lyrical containers |
| 2028–2031 | Rust robot runtimes (dora-rs, copper-rs) gain share [C-W7-053] | Vendors ship their nodes | They are just new Market apps |
| 2028–2032 | EU certification of AI-driven machines becomes normal | Harmonised standards under the Machinery Regulation | Decision log and MCU safety split already in place [C-W7-046] |
| 2030–2036 | Orin end of supply (2032); a Jetson successor | NVIDIA's lifecycle page; a new L4T major | One planned in-field branch upgrade per robot lifetime |
| Any time | NVIDIA changes Jetson's base OS | Release notes | meta-tegra keeps OneMind independent of the root filesystem [C-STEEL-jb-002] |

**Humanoids and robot hardware.** The research did not find primary sources that would let it forecast humanoid volumes or prices; it treats humanoids as one more robot class on the same three-brain architecture (Chapter 6) and watches NVIDIA's GR00T targets and the EU Machinery Regulation as the signals.

## How robot makers ship and update their computers (constraint fit) {#sec-robot-competitors}

| Product | Robot OS and updates | Constraint fit with OneMind |
|---|---|---|
| Boston Dynamics Spot CORE I/O | JetPack 5.1.2; apps as Docker "Extensions" [C-W7-040] | High for app delivery (containers on a vendor BSP); low for longevity, two JetPack majors behind |
| Clearpath (ROS 2 Jazzy) | Lightly customised Ubuntu 24.04 ISO plus a setup script [C-W7-039] | Low: no image updates or rollback |
| Auterion Skynode | OS plus flight firmware in one signed file; remote, app or USB updates [C-W7-042] | High for the update model |
| ModalAI VOXL 2 | Ubuntu 18.04, kernel 4.19, on a Qualcomm BSP [C-W7-041] | Cautionary: what vendor-BSP stagnation looks like |
| Home Assistant OS, umbrelOS, Olares | No robotics support or Jetson image [C-MATRIX-002] | None for robotics: robot vendors are the proof instead |

## Non-NVIDIA silicon: the lock-in guard {#sec-non-nvidia}

| Option | 2026 evidence | Ten-year fit |
|---|---|---|
| Rockchip RK3588 NPU | Mainline driver `drivers/accel/rocket` since Linux 6.18 [C-W7-049] | Good and improving: no vendor-BSP lock |
| Hailo (Pi AI HAT+ class) | HailoRT 5.5.0, Oct 2026 [C-W7-053]; Hailo-10H HAT, 40 TOPS [C-W10-036] | Good for Pi-tier vision |
| Google Coral | Repository archived since 2021 [C-W7-050] | Avoid for new SKUs |
| Qualcomm robotics boards | VOXL 2 still on Ubuntu 18.04 / kernel 4.19 [C-W7-041] | Risky; vendor containers only |

Apps declare accelerator *capabilities*; models ship as ONNX plus per-backend engines; no app may hard-require CUDA unless marked NVIDIA-only (W7-R13). That is how "the same manifests run on AMD, Intel, Hailo and RK3588" (F-2, F-6).

## Robot safety and drone rules {#sec-robot-safety}

- **EU Machinery Regulation 2023/1230 applies from 14 January 2027**; machines with self-evolving behaviour must stay within their task space and **record safety-related decision data for one year** [C-W7-045, C-W7-046]. OneMind builds that log into the audit layer in phase 1.
- **ISO 10218 (2025)** adds cybersecurity requirements where they affect robot safety (SECONDARY, catalogue only) [C-W7-055].
- **Drones:** PX4 is BSD-3 and ArduPilot GPL-3.0 [C-LIC-047]; selling locked hardware favours PX4. FAA Part 108 (BVLOS) was not final in the latest sources (SECONDARY) [C-W7-054]. Drones are a year-2+ line; in year 1 they are integrated third-party devices. The update model to copy is a single signed artifact carrying the companion OS **and** the flight firmware [C-W7-042].
- **MHS:** design adapters in its shape (capabilities, read/write primitives, declared safety limits enforced by the adapter), but don't depend on it until its spec is public [C-W7-047].

## The world around OneMind, 2030–2036 {#sec-world}

Four scenarios from `16-world-context-scenarios.md`. They are not predictions; real life will be a mix. Each has warning lights (triggers) wired into the roadmap.

| Scenario | Already visible | What OneMind must be able to do |
|---|---|---|
| **A · Fortress blocs** | Taiwan makes about two-thirds of the most advanced chips [C-W15-023]; China paused, not cancelled, rare-earth export controls, and the pause ran out on 2026-11-10 (SECONDARY) [C-W15-004]; a 16 GB Pi 5 costs more than three times its launch price [C-REF3-DC-cost-001] | Run on more than one kind of chip; second-source SKUs |
| **B · Sovereignty mandate** | The EU Commission bought cloud with a sovereignty score as an entry gate [C-W15-015]; CRA, Data Act and right-to-repair in force or coming [C-W6-001] | Sell legally into Europe; publish a sovereignty dossier |
| **C · Grey grid** | 313 government internet shutdowns in 2025, including 14 of satellite internet [C-W15-001, C-W15-002]; all of mainland Spain and Portugal went dark in April 2025 [C-W15-003] | Build and update itself with **no internet**; store-and-forward everywhere |
| **D · Walled AI gardens** | Google will require registered developers for apps installed outside its store, globally from 2027 [C-W15-010] | Keep phones working with boxes: PWA first, an APK channel outside Play |

**The foundation holds in all four**, because Debian, an open image, k3s, NATS and Apache-2.0 belong to no single company or country. The work is at the edges: twelve no-regret moves (`16-…` §6), most of which cost days, not months, if done now.

**Requirements served:** F-1, F-2, F-6, M-7, N-1, N-2, N-7, N-8, N-10, AI-2, AI-5, R-3.
