# The hardware line and box designs {#sec-hardware}

> **Explain it like I'm the founder.** The foundation already decides most of the hardware: a box that runs k3s needs at least 4 GB of RAM and an SSD, smaller gadgets join over NATS, Jetsons run NVIDIA's Ubuntu, and everything else runs the same core image (Ubuntu 26.04 under the current decision, or Debian 13 if the decision map picks it; see Chapter 4). So the boxes are not six products; they are **six sizes of one OS**. Each machine gets a "superpower" label automatically from what is inside it. And the money advice is blunt: **don't sell your own boxes in year 1.** Memory and Jetson prices jumped in 2026, so publish a certified hardware list and flashable images first, and have a factory partner build your boxes in year 2.

## Six sizes of one OS {#sec-sizes}

![The line, from a sensor leaf to a simulation workstation.](img/hardware-line.png){width=100%}

| Size | Superpower | Reference spec | Image · k3s role | Sourced price anchor |
|---|---|---|---|---|
| **Node** (leaf) | Sensor gateway | ESP32, Pi Zero class, ≤ 4 GB or no SSD | Vendor firmware or Debian minimal · NATS leaf only | HA Green $199 [C-W10-021] |
| **Edge** | Hub / greenhouse / TAK node | Pi 5 **8 GB** or CM5 + **NVMe**; Zigbee/Thread + LoRa; optional Hailo-10H HAT (40 TOPS, $200 [C-W10-036]) | Core image (Pi 5 kernel) · k3s server | Pi 5 16 GB $385 [C-W10-034]; CM5 from $67.50 [C-W10-035] |
| **Lite** | Home cloud / vault | Intel **N150**, **16 GB** (the chip's maximum), 2+ NVMe, 2.5 GbE, TPM 2.0, custom Secure Boot keys | Core image · k3s server | Umbrel Home $499 / Pro $699 [C-W10-018] |
| **Pro** | Private AI | x86 + NVIDIA RTX ≥ 16 GB VRAM, 64 GB+ RAM; or a GB10 system | Core image + device plugin, or GPU flavor · k3s server | DGX Spark $4,699 [C-W10-032]; Olares One $4,999 [C-W10-019] |
| **Robotics** | Robot brain | **Production** Jetson Orin NX 16 GB / AGX Orin / T4000 on a partner carrier with CAN, GMSL/CSI, PoE | L4T Ubuntu 24.04 · k3s agent (or server) | Orin NX 16 GB $999, T4000 $2,999 (1k units) [C-W10-026] |
| **Omni** | Simulator | RTX PRO 6000 Blackwell workstation, 64 GB+ RAM, 16+ cores (Isaac Sim "ideal" [C-W10-016]), or a DGX Spark pair | GPU-server Ubuntu · k3s/RKE2 | Not priced (no consumer competitor) |

The rest of each bill of materials (enclosure, power supply, NVMe, carrier, radios, certification, freight, duty, warranty reserve) is **not priced**, because no primary or quoted source exists yet (`11-…` §7.3). **Why N150, not N300, for Lite:** both cap at 16 GB, but only the N150 has embedded long-availability options [C-W10-039, C-W10-040]; the 16–32 GB "Lite" in `docs/HARDWARE.md` is impossible on these chips. **Why a production Jetson module:** NVIDIA says its developer kits "are not intended for production use" [C-W10-027].

## Machine superpowers and "can my box run this?" (P-6, A-8, N-3) {#sec-superpowers}

The OS reads what is inside each box (GPU, radios, disks, TPM, CAN bus) using Kubernetes **Node Feature Discovery** and NVIDIA's **GPU Feature Discovery**, the same parts Olares uses [C-W10-009]; NVIDIA's version understands Jetson [C-W10-014]. Rules over those labels give each machine a superpower: *Sensor gateway* (a radio dongle by USB ID), *Always-on hub* (low power, NVMe), *Vault* (two or more disks), *Private AI* (≥ 16 GB VRAM or ≥ 32 GB unified memory), *Robot brain*, *Simulator*.

Each app declares what it needs, and the dashboard answers **runs / runs with caveats / runs on another of your machines / needs new hardware**, for example: "Ollama will run on *garage-pro* (RTX, 24 GB); *greenhouse-pi* can't run it." Olares checks resources before every install [C-W10-006, C-W10-007]; Umbrel's app manifest has no hardware field at all [C-W10-004].

## Bundles and the distributor model (A-7, H-1) {#sec-bundles}

Bundles are data: a hardware rule, a profile and pinned apps. The same **Greenhouse** bundle can be applied to bring-your-own hardware that passes the rule, so a self-builder gets it without buying a box (P-7). **Distribution in phases:** year 1, a "Works with OneMind" certified list and flashable images, selling other makers' hardware through their normal channels; year 2, own Lite and Edge boxes from an ODM, sold direct; years 3–5, partners and distributors (`11-…` §7, `17-…`).

## 2026 prices: why no own boxes in year 1 {#sec-prices}

- DRAM contract prices were forecast to rise 90–95% in a single quarter, 1Q26 (SECONDARY) [C-W10-037].
- NVIDIA's Jetson Orin Nano Super kit launched at $249 [C-W10-025] and lists at $399 today [C-W10-026].
- Raspberry Pi raised the 16 GB Pi 5 by $80 to $385 on 2026-11-02, citing scarce DRAM [C-W10-034].
- Export controls, tariffs and a possible Taiwan disruption could cut SKUs (Chapter 12). Mitigations: memory-indexed pricing, second-source SKUs (RK3588-class), and riscv64 in CI.

## What competitors ship (constraint fit) {#sec-hw-competitors}

| Box | Price | Constraint fit | Lesson |
|---|---|---|---|
| Home Assistant Green | $199 [C-W10-021] | High | A cheap, fixed, low-support entry box sells |
| Umbrel Home / Pro | $499 / $699 [C-W10-018] | High | Consumer x86 boxes at the Lite price point |
| ZimaCube 2 Creator | $2,499 [C-W10-020] | Medium | NAS + apps hybrid |
| Olares One | $4,999 [C-W10-019] | High for Pro | A GPU "private AI" box is a real category |
| NVIDIA DGX Spark | $4,699 [C-W10-032] | Medium | Omni-class compute in a small box |
| ClawBox | €749 [C-W10-024] | Low | Built on a dev kit, which NVIDIA says is not for production |

## Your hardware: what each machine can and cannot prove {#sec-founder-hw}

| Machine | Can validate | Cannot validate |
|---|---|---|
| **Mac** (Apple silicon) | All VM labs, kernel and image builds in Lima [C-W18-066] | Real firmware, power loss, GPUs |
| **Dell Latitude 5540** | Secure Boot with your own keys: its BIOS allows custom PK/KEK/db [C-W10-043]; real power pulls; x86 install | Pi, Jetson, GPU |
| **Beelink U55** | A "worst-case old box": i3-5005U, 16 GB max, no TPM firmware listed [C-W10-041]; power pulls | Secure Boot assurance; new CPU features |
| **Android phone** | OneMind client, ATAK | — |
| **DigitalOcean cluster** | Read-only conversion checks (`22-…`) | Anything physical |

**Buy this week (by 2026-11-16):** a **Pi 5 8 GB** with an M.2 NVMe HAT and SSD, and a **Jetson Orin Nano Super** kit, so ARM and Jetson are on your desk for the week-4 to week-8 bake-off. Then a Zigbee/Thread dongle and two LoRa/Meshtastic radios by week 3 (`11-…` §10.1).

**Requirements served:** H-1, H-2, H-3, H-4, P-5, P-6, A-7, A-8, N-3, D-004.
