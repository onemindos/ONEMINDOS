# 11 · Hardware line, machine superpowers and capability detection

**Workstream:** W10 (Tier B: at least one primary source per claim) · **Date:** 2026-11-11 · **Status:** draft
**Owns:** P-6 and A-8 (machine superpowers and in-platform recommendations), A-7 and H-1 (bundles and the distributor model, shared with `17-…`), N-3 (capability detection), H-2, H-3, H-4, the founder-hardware questions (Q290) and the bake-off purchase dates. Bank questions are listed in `evidence/qbank/W10.md`.
**Builds on:** `01-FOUNDATION-DECISION.md` (Tier A, binding here), `05-…` §8 (lock-in guard), `08-…` (Jetson flavor, robot runtime), `09-…` (profiles, NATS leaf), `28-…` (Mac toolchain), `02-competitors/` (umbrelOS and Olares teardowns), `docs/HARDWARE.md`, `research/competitors/landscape.md` and `research/platform/robotics-iot-xr-nvidia.md` §5. Verified Tier A work is reused by claim ID, not redone.
**Evidence:** claims `evidence/claims/W10.csv` (C-W10-001…050) · sources `evidence/sources/W10.md` · saved pages `evidence/sources/W10/` (with `SHA256SUMS`)
**Serves requirements:** P-5, P-6, P-7, P-8, A-7, A-8, H-1, H-2, H-3, H-4, N-1, N-2, N-3, N-8, F-2, F-14, M-4, M-6, M-7, R-2, R-3, D-002, D-004, D-006

> ### Explain it like I'm the founder
> **Your hardware line is mostly decided by the Tier A foundation already.** A box that runs k3s needs at least 4 GB of RAM and an SSD. Smaller gadgets join over NATS instead. Jetsons run NVIDIA's Ubuntu. Everything else runs the same Debian image. So the boxes are not five different products. They are **five sizes of one OS**.
>
> **What this file adds:**
> 1. **Every machine gets a "superpower" automatically.** The OS reads what is inside the box (GPU, radios, disks, TPM, CAN bus), then labels it: "Robot brain", "Private AI", "Simulator", "Sensor gateway" and so on. Kubernetes already has the parts for this: Node Feature Discovery and NVIDIA's GPU Feature Discovery. Olares uses the same parts [C-W10-009], and NVIDIA's version even understands Jetson [C-W10-014].
> 2. **"Can my box run this?" gets a real answer.** Each app declares what it needs, and the dashboard answers *runs / runs with caveats / runs on another of your machines / needs new hardware*. Olares already does a version of this before every install [C-W10-006, C-W10-007]. Umbrel does not: its app manifest has no hardware-requirement field at all [C-W10-004].
> 3. **Don't sell boxes in year 1.** Memory contract prices were forecast to nearly double in a single quarter (1Q26) [C-W10-037]. NVIDIA raised the $249 Jetson kit to $399 [C-W10-025, C-W10-026]. The 16 GB Pi 5 went to $385 nine days ago [C-W10-034]. In year 1, publish a **certified hardware list** and **flashable images**, and sell bundles of other people's hardware through their normal channels. Your own boxes come in year 2, from an ODM.
> 4. **Your test hardware:** the **Dell 5540** is the best security test bed you have, because you can load your own Secure Boot keys [C-W10-043]. The **Beelink U55** is a "worst-case old box": its CPU stopped getting Intel security updates in 2021 [C-W10-041]. **Buy a Pi 5 (8 GB) and a Jetson Orin Nano Super this week** (by 2026-11-16), so ARM and Jetson are both on your desk for the week-4 bake-off.
>
> **Things that contradict earlier docs (flagged, not silently fixed):** the "Lite: Intel N150/N300 with 16–32 GB" spec in HARDWARE.md is impossible, because Intel caps both chips at 16 GB [C-W10-039, C-W10-040]. The HARDWARE.md Pi and DGX Spark prices are out of date. NVIDIA says Jetson dev kits "are not intended for production use" [C-W10-027], so a Robotics box must use a production module on a partner carrier board, unlike ClawBox's design [C-W10-024].

---

## 0. The answer (W10 conclusions)

| # | Conclusion | Confidence | Key claims |
|---|---|---|---|
| W10-C1 | The line is **five platform-node sizes plus one leaf-node class**, all on the Tier A image families. Edge (Pi 5/CM5) and Lite (x86 N-series) run the Debian core image. Pro (x86 + discrete GPU) runs the Debian core or the Ubuntu GPU-server flavor. Robotics runs L4T Ubuntu on Jetson. Omni runs the GPU-server flavor. Anything under 4 GB or without an SSD is a **NATS leaf node** (01 §1). | High (follows from Tier A) | C-W4-002, C-LAB-k3s-footprint-restore-007, C-W10-021 |
| W10-C2 | **Capability detection = NFD + GFD + a OneMind probe**, published as node labels and as a `NodeCapabilities` document, then matched against the `requires`/`recommends` block in `onemind.app.yaml`. NFD alone is not enough: it reports no total RAM and no TPM or Secure Boot state [C-W10-011]. | High | C-W10-010…015, C-W10-006…009 |
| W10-C3 | **The same probe must also run on leaf nodes without Kubernetes**, publishing over NATS. Otherwise F-14 breaks at the small end, and the "can I run this?" answer would exist only on k3s nodes. | Medium (design) | C-W10-012 |
| W10-C4 | **Superpowers (P-6) are derived, not marketed.** A superpower is the top-ranked capability profile a node matches. The same rules drive placement and recommendations (A-8). | Medium (design; no competitor does exactly this) | C-W10-005, C-W10-008 |
| W10-C5 | **Year 1: no own-brand hardware.** Ship a "Works with OneMind" list, flashable images and bundles built from third-party hardware. Own boxes come in year 2 from an ODM, on CPUs that Intel lists with embedded (long-life) options. | Medium | C-W10-037, C-W10-026, C-W10-034, C-W10-039, C-W10-040 |
| W10-C6 | **Robotics SKUs use production Jetson modules on partner carrier boards, never dev kits.** Dev kits are dev-only, with a 1-year dev-use warranty; modules carry 3 years and are available to January 2032 (Orin) and up to January 2036 (Thor-class T4000) [C-W10-027, C-W10-029]. | High | C-W10-027…029 |
| W10-C7 | **Bake-off purchases this week:** a Pi 5 8 GB + NVMe and a Jetson Orin Nano Super Developer Kit, both ordered by **2026-11-16**. Apply to NVIDIA Inception the same day, but don't wait for it: it publishes no discount amounts [C-W10-045]. | High | C-W10-026, C-W10-034, C-W10-045 |

---

## 1. What Tier A already fixed for hardware (binding)

| Tier A decision (01 §1) | Consequence for the hardware line |
|---|---|
| k3s only on platform nodes with **≥ 4 GB RAM and SSD/NVMe**; 8 GB recommended for a server | Every OneMind box ships **NVMe**, never SD or eMMC as the system disk (k3s docs: SD and eMMC cannot handle etcd's IO load [C-W4-002]). An HA Green-class device (4 GB, 32 GB eMMC [C-W10-021]) is a leaf node, not a platform node. |
| NATS leaf below k3s | A sensor/radio class with no Kubernetes. It still needs capability reporting (W10-C3). |
| Debian 13 core; Jetson on L4T Ubuntu 24.04 (JetPack 7.2+) | Two image families. The hardware line maps onto them, not onto a new one. |
| GPU-server flavor may be Ubuntu LTS + RKE2 | Pro/Omni SKUs that advertise **Isaac Sim** depend on that flavor: Isaac Sim lists only Ubuntu 22.04/24.04 and Windows 11 on x86 [C-W10-016], and the GPU Operator does not list Debian [C-W4-021]. **Flag F-3 (below).** |
| LUKS2 data from first boot; Secure Boot and TPM later | Own boxes need firmware that allows **custom Secure Boot keys** and a **TPM 2.0**. ODM selection must check this (§8). |
| RAUC A/B on x86 and Pi 5; NVIDIA A/B on Jetson | No hardware constraint beyond UEFI on x86 and the Pi 5 bootloader; W3 owns the details. |

---

## 2. What competitors ship (with constraint fit)

All prices were read from the vendor's own store or page on 2026-11-11.

| Product | Compute | Memory / storage | Price | OS · k8s? | Channel · warranty | Constraint fit with OneMind |
|---|---|---|---|---|---|---|
| **Umbrel Home** | Intel N150, 4 cores | 16 GB DDR5 · 0.5–4 TB NVMe | $499–$949 [C-W10-018] | umbrelOS (Debian, Docker) · no | Own Shopify store; 1-year warranty [C-TD-umbrelos-046, C-W10-050] | **High** for Lite (same chip class, small team, appliance); low for robotics |
| **Umbrel Pro** | Intel i3-N300, 8 cores | 16 GB LPDDR5 · 4× NVMe + 64 GB OS | $699–$1,899 [C-W10-018] | umbrelOS · no | Own store; "Umbrel Protect" add-on $39–$99 [C-W10-018] | High for Lite/storage. **N300 has no embedded option** [C-W10-040] (longevity risk) |
| **Olares One** | Core Ultra 9 275HX + RTX 5090 Mobile 24 GB | 96 GB · 2 TB | $4,999 [C-W10-019] | Olares (k3s) · **yes** | Own store [C-W10-050] | High for Pro (k3s, GPU, multi-node); no Jetson support in its GPU model [C-W10-008] |
| **ZimaBoard 2 / ZimaCube 2** | Intel N-class / i3-1215U, i5-1235U | 8–64 GB · eMMC / bays | Board $339–$399; kits $379–$999; Cube $799–$2,499 [C-W10-020] | ZimaOS (Buildroot, Docker) · no | Own store; **sells pre-assembled kits** | Medium: kit model worth copying (A-7); Docker-only |
| **Home Assistant Green** | RK3566, 4× A55 | 4 GB · 32 GB eMMC | $199 / €179 MSRP, set by retailers [C-W10-021] | HAOS (Buildroot, RAUC) · no | **Retail partners**; Nabu Casa, no VC [C-W10-022] | High as a **leaf-node** pattern (1.7 W idle); fails the k3s gate (eMMC) |
| **Start9 Server One** | Ryzen 5 6600H, 6c/12t | 16/32 GB · 2/4 TB NVMe | Configurator (not listed) | StartOS (Debian) · no | Own store; 1-year warranty + 1 year Premium Support ($200) [C-W10-023] | Medium: support bundled with hardware (R-2 pattern) |
| **ClawBox** | Jetson Orin Nano Super, 67 TOPS | 8 GB · 512 GB NVMe | €749 [C-W10-024] | Ubuntu + agent · no | Own store | Shows demand for a Jetson "AI box"; built on dev-kit-class hardware that NVIDIA does not intend for production [C-W10-027] |
| **NVIDIA DGX Spark** | GB10, unified memory | 64 or 128 GB | FE $4,699 since Feb 2026 [C-W10-032]; later press reports of $6,000–$6,950 are UNVERIFIED [C-W10-033] | DGX OS (Ubuntu) | NVIDIA + OEM partners; 64 GB only via OEMs; hardware support from seller [C-W10-031] | High for Pro/Omni AI (only Arm host for Isaac Sim [C-W18-058]); price volatile |

**What the proven competitors actually show:**
1. **Low-power Intel N-series is the entry tier** (Umbrel, Zima). Intel caps the N150 and i3-N300 at **16 GB on one channel, no ECC** [C-W10-039, C-W10-040].
2. **Everyone sells direct from their own Shopify store** [C-W10-050]. Only Nabu Casa leans on retailers [C-W10-021], and NVIDIA sells Jetson through authorized distributors [C-W10-028].
3. **Bundles exist as kits and add-ons**, not as software profiles: Zima's NAS, Smart Home and Firewall kits [C-W10-020], Umbrel Protect [C-W10-018], HA Green plus Connect dongles [C-W10-021].
4. **Nobody ships a robotics, mesh or industrial box** (landscape §3, still true in this pass). That remains the opening (M-7).
5. **Only Olares has real capability-aware installs** (§5). Umbrel detects GPUs but has no requirements field [C-W10-001…004].

---

## 3. The OneMind line: reference designs (H-2, H-3, P-5)

"Compute cost" counts only the part with a primary price. **The rest of the BOM** (enclosure, PSU, NVMe, carrier, radios, packaging, certification, freight, duty, warranty reserve) **is not priced here**, because no primary or quoted source exists yet. §7.3 gives the formula and the quotes needed. No made-up totals.

| Size | Superpower (default) | Reference spec | Image family · k3s role | Compute cost (sourced) | Shelf anchor |
|---|---|---|---|---|---|
| **Node** (leaf, not a box) | Sensor gateway | ESP32/Pico, Pi Zero-class, HA Green-class, ≤ 4 GB or no SSD | Vendor firmware or Debian minimal · **NATS leaf only** | n/a | HA Green $199 [C-W10-021] |
| **Edge** | Always-on hub / greenhouse / TAK node | Pi 5 **8 GB** or CM5 on a carrier; **NVMe mandatory**; Zigbee/Thread + LoRa radios; optional Hailo-10H AI HAT+ 2 (40 TOPS, $200 [C-W10-036]) | Debian core (Pi kernel) · k3s server (single box) | Pi 5 16 GB $385 [C-W10-034]; 8 GB price not on a primary page (~$175 per press, SECONDARY); CM5 from $67.50 [C-W10-035] | HA Green $199; Pi production to 2036 [C-W2-029, C-W10-035] |
| **Lite** | Home cloud / vault | Intel **N150** (embedded option: yes [C-W10-039]), **16 GB** (chip maximum), 2+ NVMe, 2.5 GbE, TPM 2.0, firmware with custom Secure Boot keys | Debian core · k3s server | not priced (ODM quote) | Umbrel Home $499 / Pro $699 [C-W10-018] |
| **Pro** | Private AI | x86 (Core Ultra / Ryzen) + discrete NVIDIA RTX **≥ 16 GB VRAM**, 64 GB+ RAM, 2+ NVMe; or a GB10 system | Debian core + device plugin, or Ubuntu GPU-server flavor (Flag F-3) · k3s server | DGX Spark FE $4,699 [C-W10-032] | Olares One $4,999 [C-W10-019]; ZimaCube 2 Creator $2,499 [C-W10-020] |
| **Robotics** | Robot brain | **Production** Jetson Orin NX 16 GB / AGX Orin / T4000 on a partner carrier with CAN, GMSL/CSI, PoE; rugged | L4T Ubuntu 24.04 · k3s agent or server, per `08-…` | Orin NX 16 GB $999, AGX Orin 64 GB $2,999, T4000 $2,999, T5000 $4,999 (1KU+) [C-W10-026] | ClawBox €749 (consumer) [C-W10-024] |
| **Omni** | Simulator | RTX PRO 6000 Blackwell (48 GB) workstation, 64 GB+ RAM, 16+ cores (Isaac Sim "ideal") [C-W10-016]; or a DGX Spark pair | Ubuntu GPU-server flavor · k3s/RKE2 server | not priced | none (no consumer competitor) |

**Why Pi 5 8 GB rather than 16 GB for Edge:** Tier A recommends 8 GB for a server node, and the 16 GB price has risen faster: the extra 8 GB now costs more than a whole 8 GB board (press, SECONDARY), after the $80 rise [C-W10-034].
**Why N150 rather than N300 for Lite:** both are 16 GB parts, but only the N150 has embedded (long-availability) options [C-W10-039, C-W10-040], and R-3 plus the CRA support-period rules [C-W6-002, C-W6-005] reward stable hardware.

---

## 4. Machine superpowers (P-6) and in-platform recommendations (A-8)

### 4.1 Superpowers are rules over detected capabilities

| Superpower | Detection rule (over the §5 capability model) | What the OS does with it |
|---|---|---|
| **Sensor gateway** | Radio dongle by USB VID:PID (Zigbee/Thread/LoRa/Meshtastic), or leaf node with radios | Places IoT apps (HA, ChirpStack) here; shows on the map |
| **Always-on hub** | Low power draw (≤ 15 W class), mains, NVMe | Holds NATS JetStream, backups target, TAK server for small sites |
| **Vault** | ≥ 2 NVMe/disks, data disks non-rotational or mirrored | Places storage apps; backup destination for the cluster |
| **Private AI** | Accelerator with ≥ 16 GB VRAM, or ≥ 32 GB unified memory | Places LLM, vision and agent workloads |
| **Simulator** | RT-core GPU ≥ 16 GB VRAM, ≥ 32 GB RAM, amd64 (or the DGX Spark exception) [C-W10-016] | Offers Isaac Sim and digital-twin apps |
| **Robot brain** | Tegra GPU (GFD `tegra` strategy [C-W10-014]) plus CAN/CSI/GPIO | Robot runtime profile; ROS 2 containers |
| **Field node** | Battery or 12/24 V DC input, rugged chassis tag | Tighter update windows; offline-first defaults |
| **Trust anchor** | TPM 2.0 present and Secure Boot in user/custom mode | Preferred key holder for cluster secrets and backup keys |

A node can match several rules. The dashboard shows the highest-ranked one as its superpower and lists the rest. Ranking: Simulator > Robot brain > Private AI > Vault > Trust anchor > Field node > Always-on hub > Sensor gateway, adjustable by the user.

**Precedent:** umbrelOS already names its own boxes from SMBIOS SKUs and the Pi 5 from `/proc/cpuinfo` [C-W10-005], and its manifest flag `optimizedForUmbrelHome` [C-W10-004] is a crude "this app is best on our box" hint. Olares labels each node with one compute mode, including unified-memory GB10 and Apple M [C-W10-008]. OneMind generalises both into rules anyone can read.

### 4.2 Recommendations (A-8)

| Type | Trigger | Example output | Data |
|---|---|---|---|
| **Placement** | Install, or a node joins | "Ollama will run on *garage-pro* (RTX, 24 GB); *greenhouse-pi* can't run it" | Capability model + app `requires` |
| **Upgrade** | App verdict is "needs hardware" | "Isaac Sim needs an RTX GPU with RT cores and ≥ 16 GB VRAM. None of your nodes has one." [C-W10-016] | Same |
| **Purchase / compare** | User asks, or an upgrade is needed | Certified boxes that pass the rule, OneMind-sold and third-party side by side, with prices and their date | "Works with OneMind" list (§7) |
| **Health** | Probe change | "This box's CPU no longer receives vendor security updates" (Beelink case [C-W10-041]) | Probe + a vendor-lifecycle table |

**Rules for trust:** every recommendation shows its reason (the failed rule). OneMind-sold hardware is labelled as such and is never ranked above an equal third-party option. Prices carry their date, because they moved several times in 2026 (§9). A BYO machine is never blocked when it passes the rule. The "can't" answer is a **warning with an override**, except for safety gates owned by W7.

---

## 5. Capability detection (N-3): "can my box run this?"

### 5.1 What competitors and tools do (constraint fit)

| System | How it detects | What it tells the user | Constraint fit |
|---|---|---|---|
| **umbrelOS** | `lspci` PCI class 03xx, `/dev/dri`, `/dev/kfd`, NVIDIA = Docker runtime + `nvidia-smi`; re-probed on every app start for eGPU hot-plug [C-W10-001, C-W10-002] | Nothing up front. A `GPU` permission adds devices to the app [C-W10-003]. No RAM/CPU requirement field [C-W10-004] | Docker single box; good **probe** pattern, no **verdict** pattern |
| **Olares** | Node labels `gpu.bytetrade.io/<mode>`; HAMi for NVIDIA; NFD rules for Intel [C-W10-008, C-W10-009] | Preflight before install: installable or not, failing demand, reason code (capacity, pressure, quota, unschedulable) [C-W10-006, C-W10-007] | **k3s multi-node, closest match.** Gap: no Jetson mode [C-W10-008] |
| **NFD** (Kubernetes SIGs) | CPU flags, kernel modules/config, PCI, USB (vendor/device/serial), DMI (product, SKU, BIOS), block devices, NIC speed [C-W10-010]; external probes via `local` [C-W10-012] | Node labels; `NodeFeatureRule`; experimental Image Compatibility artifact [C-W10-013] | Vendor-neutral and Apache-2.0 [C-W4-068]. **No RAM size, no TPM/Secure Boot** [C-W10-011] |
| **NVIDIA GFD** | NVML, or `tegra` for Jetson, or `vfio` [C-W10-014] | Product, memory, count, compute capability, family, sharing [C-W10-015] | Covers dGPU and Jetson; NVIDIA only |
| **Isaac Sim Compatibility Checker** | Local app installed with Isaac Sim [C-W10-016] | Whether this machine meets the requirements | Only after installing a large package; one app |
| **Ollama** | Driver and compute capability (NVIDIA CC 5.0+, driver 550+; AMD ROCm v7; Vulkan fallback) [C-W10-017] | Falls back to CPU | Shows why "has a GPU" is not enough: drivers and compute capability decide |

### 5.2 The OneMind model

```
              ┌──────────── per node ─────────────┐
 NFD worker ──┤ cpu, kernel, pci, usb, dmi, disk, nic ├─┐
 GFD (nvml|tegra)─┤ gpu product, vram, cc, family     ├─┤  NodeFeature objects
 onemind-probe ──┤ RAM, unified?, TPM2, SecureBoot mode,├─┤  (via NFD "local" files
 (also on leaf   │ power source, radios, JetPack ver,   │ │   on k3s nodes; via NATS
  nodes, no k8s) │ RT kernel, vendor-lifecycle status   │ │   on leaf nodes)
              └───────────────────────────────────────┘ │
                                                         ▼
        NodeFeatureRule CRs (shipped as data; third parties add their own)
                                                         ▼
        node labels  onemind.io/cap.*   +  NodeCapabilities document (NATS KV)
                                                         ▼
  onemind.app.yaml  requires / recommends  ──►  verdict per node and per cluster
                                                         ▼
  Dashboard: Runs ✓ · Runs with caveats ! · Runs on <other node> → · Needs hardware ✗ · Untested ?
```

**Capability classes** reuse the W4 lock-in guard (`05-…` §8): apps ask for `accelerator.class: gpu.cuda | gpu.rocm | gpu.any | npu.inference` and a memory size, never for `nvidia.com/gpu`. Detection adds the facts the guard needs: `memory.unified` (GB10, Thor, Orin and Apple-M class, which Olares also models separately [C-W10-008]), `accelerator.rt_cores`, `security.tpm2`, `security.secureboot_mode`, `storage.ssd`, `io.can`, `radio.*`, `power.source`.

**Manifest block (proposal, owned with W19):**
```yaml
requires:                       # hard: verdict ✗ if unmet
  arch: [amd64, arm64]
  memory: 4Gi
  storage: {free: 20Gi, ssd: true}
  accelerator: {class: gpu.any, memory: 8Gi}   # unified memory counts, flagged
recommends:                     # soft: verdict ! if unmet
  accelerator: {rt_cores: true, memory: 16Gi}
placement: {multiNode: false}   # Olares has supportMultiNodes/Cards [C-W10-006]
```

**Verdict rules:**
1. All `requires` met on the target node → ✓, or ! if `recommends` are unmet.
2. Unmet here but met on another node in the user's cluster → "→ runs on <node>". This is Olares's multi-node preflight idea [C-W10-006], made visible.
3. Met nowhere → ✗ with the failed rule, plus an A-8 upgrade suggestion.
4. A probe value is unknown (not "false") → **? Untested**, never ✓. This follows the Tier A rule that unverified evidence scores the lowest anchor.
5. Re-evaluate on hot-plug: Umbrel re-probes on every app start for exactly this reason [C-W10-002].

**Why a OneMind probe is needed:** NFD has no total-memory or TPM feature [C-W10-011]. GFD covers NVIDIA only. Hailo and RK3588 have no vendor device plugin [C-W4-067]. The probe is small (sysfs, `/proc/meminfo`, `/sys/class/tpm`, `mokutil`/efivars, USB IDs) and writes NFD feature files [C-W10-012]. On leaf nodes the same binary publishes over NATS (W10-C3).

**Validation:** test plan items W10-T3 and W10-T4 (§11).

---

## 6. Bundles (A-7, H-4)

A **bundle** = hardware (OneMind-sold or certified third-party) + a **profile** (W8's signed image family + pinned apps + config pack, `09-…` §8) + accessories + a support term. One SKU per real-world job:

| Bundle | Hardware | Profile / apps | Accessories | Pattern copied from |
|---|---|---|---|---|
| **Greenhouse** | Edge (Pi 5 8 GB + NVMe) | Greenhouse profile: HA, MQTT, NATS leaf for sensors | Zigbee/Thread dongle, LoRa radio, sensors | Zima Smart Home Kit [C-W10-020]; HA Green + Connect [C-W10-021] |
| **TAK field kit** | Edge or Lite | TAK node profile (`09-…` §8) | 2× Meshtastic radios, UPS/battery | none (gap) |
| **Home cloud** | Lite | Family apps, backups | 2nd NVMe | Umbrel Home [C-W10-018] |
| **Private AI** | Pro | Local LLM, agents | n/a | Olares One [C-W10-019] |
| **Robot starter** | Robotics (production Jetson + carrier) | Robot runtime, ROS 2 containers | Arm kit (W7 picks it) | ClawBox shows demand [C-W10-024] |
| **Protect** (add-on) | any | Extended warranty and support | n/a | Umbrel Protect $39–$99 [C-W10-018]; Start9 Premium Support [C-W10-023] |

Bundles are data (a bundle manifest referencing a hardware rule, a profile and app pins). The same bundle can then be "applied" to BYO hardware that passes the rule. That is how a BYO user gets the Greenhouse bundle without buying a box (P-7).

---

## 7. Distributor model and economics (H-1, shared with `17-…`)

### 7.1 Phases

| Phase | When | What OneMind sells | Channel | Why |
|---|---|---|---|---|
| **0 · Certify** | 180 days → year 1 | Nothing physical. "Works with OneMind" list, flash images, bundle guides | Vendor stores and authorized distributors (NVIDIA [C-W10-028]); Raspberry Pi programmes for design and compliance help [C-W10-049] | Prices are volatile (§9); no RMA load for a solo founder (M-6) |
| **1 · Preinstalled DTC** | Year 2 | Lite and Edge boxes from an ODM, OneMind image preinstalled; small batches | Own store (Shopify-style, like Umbrel/Olares/Zima [C-W10-050]) | Proven pattern, constraint-matched (Umbrel: small team, N-series) |
| **2 · Partners** | Years 2–3 | Pro, Robotics; OEM "Manufacture with OneMind" | Regional resellers, robotics integrators, OEMs | HA Green sells through retailers at a set MSRP [C-W10-021]; Jetson carriers come from partners [C-W10-028] |
| **3 · Distributor** | Years 3–5 | Full line, government and public-safety variants | Distributors and public-sector resellers | Needs certifications and NDAA/TAA work (W6/W16) |

**About "Manufacture with Olares":** no public page for that programme was found in this pass. The Olares OEM model in `docs/REQUIREMENTS.md` H-4 stays UNVERIFIED, and `02-competitors/olares.md` should confirm it.

### 7.2 Warranty and support floor
- **EU:** the seller is liable for defects that appear **within two years of delivery**, and for goods with digital elements must supply updates, including security updates (Directive 2019/771 Art. 10(1), 7(3)) [C-W10-048]. So the market's 1-year warranties (Umbrel, Start9 [C-TD-umbrelos-046, C-W10-023]) are a US floor only.
- **CRA:** the support-period end date must be stated at purchase [C-W6-005], at least 5 years unless use is shorter [C-W6-002]. Every SKU sheet carries a "security updates until" date, bounded by the board's lifecycle: Orin modules to January 2032 [C-W10-029], Pi 5/CM5 production to January 2036 [C-W2-029, C-W10-035].
- **NVIDIA:** modules carry 3 years; dev kits 1 year, dev use only [C-W10-027].

### 7.3 Unit economics (formula; numbers pending quotes)
`landed = compute + memory/storage + enclosure/PSU/radios + factory flashing & provisioning + certification amortised over the batch + freight + duty (§9) + payment fees + warranty reserve (2-year EU basis) + support allowance`
`price = landed ÷ (1 − target gross margin)` (the margin is a **founder decision**, Q181/Q260 in `17-…`).
Missing inputs, which need quotes rather than research: ODM unit price and MOQ, carrier boards, certification lab fees, 3PL and freight, distributor and reseller margins. None has a public primary source. Status: `partial` (§12).

---

## 8. ODM/OEM path, certification and NVIDIA/Pi programmes (H-4, N-8, D-006)

| Topic | Finding | Claims |
|---|---|---|
| ODM firmware needs | The box needs TPM 2.0, a UEFI that allows **custom Secure Boot keys (PK/KEK/db/dbx)**, auto power-on after power loss, and LVFS/fwupd firmware updates. The Dell 5540 shows what "good" looks like [C-W10-043]. Consumer mini-PC vendors must be asked for the same (Q180, quotes needed) | C-W10-043 |
| Long-life silicon | Prefer CPUs with embedded options (N150: yes; i3-N300: no) [C-W10-039, C-W10-040]; Jetson production modules to 2032+; CM5 to 2036 | C-W10-029, C-W10-035 |
| Jetson design-in | Modules ship blank and are flashed with your image on your carrier [C-W10-028]. Super mode can require a carrier and thermal redesign [C-W10-028]. Partner tiers and their entry requirements were **not found** in primary sources | C-W10-028 |
| NVIDIA Inception | Free, no fees, deadlines or cohorts; "preferred pricing on select NVIDIA hardware and software", cloud credits, training [C-W10-045]. No discount figures are published, so **budget at list price** | C-W10-045 |
| Raspberry Pi | Integrator Programme: approved Design Partners plus a compliance and Global Market Access team; "Powered by Raspberry Pi" logo licence; no fees published [C-W10-049] | C-W10-049 |
| Certification | RED cybersecurity (EN 18031) applies to radio boxes [C-W6-020, C-W6-021]. Use pre-certified radio modules and the Pi compliance team where possible. Lab cost and time: **not sourced** (quotes) | C-W6-020/021 |

---

## 9. Supply, prices, tariffs and export controls (2026)

| Signal | Evidence | Consequence |
|---|---|---|
| Memory | TrendForce: 1Q26 conventional DRAM contract +90–95% QoQ, NAND +55–60% [C-W10-037]; 4Q26 still +10–15% DRAM, +15–20% NAND [C-W10-038] (SECONDARY, market research) | Don't commit to a RAM-heavy fixed SKU in year 1; prefer BYO-RAM or fewer configurations |
| Raspberry Pi | 16 GB Pi 5 +$80 to $385 on 2026-11-02 (DRAM supply) [C-W10-034] | Edge on 8 GB; HARDWARE.md's $305 is stale (Flag F-2) |
| Jetson | Orin Nano Super kit $249 at launch (2024-12-17) [C-W10-025] → $399 now [C-W10-026]; AGX Orin kit $3,499, Thor kit $5,499 [C-W10-026] | Budget the bake-off at list; Robotics BOM at 1KU module prices |
| DGX Spark | $3,999 → $4,699 (Feb 2026, all regions) [C-W10-032]; later press reports up to $6,950 UNVERIFIED [C-W10-033]; a 64 GB version via OEMs [C-W10-031] | Omni/Pro planning uses a price **range**, re-checked at purchase |
| US tariffs | Proclamation 11002: 25% from 2026-01-15 on advanced computing chips and derivatives in its Annex [C-W10-047]; whether a mini PC or Jetson box is covered depends on the Annex parameters (not checked) | Counsel or broker check before phase 1 (Q177: partial) |
| US export | Mass-market encryption items can be 5A992.c/5D992.c, self-classified under ENC 740.17(b)(1) with an annual report [C-W10-046] | Plan the self-classification for the image and boxes; advanced-compute ECCNs for Thor/RTX PRO boxes are not checked (Q178: partial) |

---

## 10. Founder hardware: what each machine can and cannot validate

| Machine | Facts | **Can validate** | **Cannot validate** | Claims |
|---|---|---|---|---|
| **Dell Latitude 5540** (i5-1345U, 16 GB user-reported) | 10 cores/12 threads, up to 96 GB per CPU, vPro Enterprise, Boot Guard [C-W10-042]; BIOS: Secure Boot on, **custom PK/KEK/db/dbx mode**, UEFI only, TPM 2.0 on, Wake on AC / Auto On [C-W10-043] | The **x86 Lite path end to end**: USB installer, RAUC A/B, the k3s gate, power-cut tests; **Secure Boot with OneMind's own keys + TPM2-sealed LUKS2** (W6's day-1 layout); Intel iGPU via the Intel device plugin (the non-NVIDIA capability path, C-W4-065); appliance auto power-on; the x86 Ubuntu 24.04 **host for full Jetson flashing and SDK Manager** (booted from USB), which production modules and recovery need [C-W18-021, C-W18-022] | ARM, Jetson, NVIDIA GPU, radios (without dongles), a fanless always-on box. It is also the **Omarchy pilot**, so wiping it conflicts with that use (founder decision: use a second SSD or USB boot) | C-W10-042, C-W10-043 |
| **Beelink U55** (i3-5005U per sources; `lscpu` to confirm) | 2 cores/4 threads, max 16 GB DDR3L, AVX2, VT-x/VT-d; **Intel servicing ended 2021-06-30** (no more microcode security updates) [C-W10-041]. TPM and Secure Boot: **unknown** [C-W10-044] | Minimum and old-BYO behaviour: k3s at 8 GB, the capability verdicts ("Untested"/✗), the lifecycle warning (§4.2), a second node for multi-node join, a NATS leaf, real power-pull tests, installer pre-checks on old firmware | Secure Boot/TPM work (likely absent), anything Olares-class (needs ≥ 4 cores [C-W4-042]), GPU work, performance baselines for a product. **Never a recommended target** | C-W10-041, C-W10-044 |
| **Mac** (the research Mac here is an Apple M5 Max [C-W18-065]; confirm it is the founder's dev Mac) | Lima VMs with nested KVM; arm64 kernel build in 333 s in the lab [C-W18-065, C-W18-066] | From **week 1** (D-002): arm64 image builds and QEMU boots, RAUC/k3s tests on aarch64, capability-probe unit tests, Pi image flashing with Raspberry Pi Imager [C-W18-059], and writing the Orin Nano dev kit's JetPack 7.2.1 USB installer ISO, which installs without an Ubuntu host [C-W18-023] | Pi 5 firmware, EEPROM and tryboot; full Jetson flashing and SDK Manager (Ubuntu host only; macOS unsupported [C-W18-021, C-W18-022]); GPU drivers; real power loss | C-W18-065, C-W18-066 |

### 10.1 Bake-off purchases (dates)

| Item | Order by | In hand (target) | Used for | Price (source) |
|---|---|---|---|---|
| **Pi 5 8 GB** + M.2 NVMe HAT + NVMe SSD + official PSU + case | **2026-11-16** (end of week 1) | Week 2–3 | ARM gate at week 4: RAUC tryboot A/B, k3s on NVMe, capability probe, greenhouse profile | 8 GB board ~$175 (press, SECONDARY); accessories not priced. 16 GB is $385 [C-W10-034] (not recommended) |
| **Jetson Orin Nano Super Developer Kit** | **2026-11-16** | Week 3–4 | Jetson flavor (JetPack 7.2.1 via the USB installer ISO, written from the Mac or the Dell [C-W18-023]; full flash from the Dell's Ubuntu host when needed [C-W18-022]), GFD `tegra` labels (W10-T4), NVIDIA A/B, k3s footprint | $399 MSRP [C-W10-026]; dev use only, 1-year warranty [C-W10-027] |
| NVIDIA Inception application | **2026-11-11/12** (same day as the orders) | n/a | Later Pro/Robotics/DGX purchases | Free, no deadlines [C-W10-045] |
| Zigbee/Thread dongle + 2 LoRa/Meshtastic radios | Week 3 | Week 5 | Sensor-gateway superpower, Greenhouse/TAK bundles | not priced |
| Intel N150 mini PC, 16 GB, 2× NVMe, TPM 2.0 | Week 6–8 (after the week-4 gate) | Week 8–10 | Reference Lite box; ODM firmware checklist (§8) | ODM quote |

**Why not wait for Inception:** no discount amounts are published [C-W10-045]. The kit price already rose 60% once [C-W10-025, C-W10-026], and the ARM and Jetson tests are on the critical path of the week-4 gate (`20-PLAN-180-DAYS.md`).

---

## 11. Founder-runnable tests (copy into `22-HARDWARE-LAB-TEST-PLAN.md`)

| ID | Test | Pass criteria |
|---|---|---|
| **W10-T1** (Q290) | On the U55 and the Dell: `lscpu; sudo dmidecode -t system -t bios; ls /sys/class/tpm; mokutil --sb-state; cat /proc/meminfo | head -1; lsblk -d -o NAME,ROTA,TRAN,SIZE; fwupdmgr get-devices`. On the Mac: `sysctl -n machdep.cpu.brand_string hw.memsize`. Record in `research-output/evidence/lab/founder-hardware/inventory.md` (template: device, CPU, RAM, disk type, TPM yes/no, Secure Boot state, BIOS version, LVFS yes/no) | All fields filled, no "unknown"; U55 CPU confirmed (i3-5005U vs N100) |
| **W10-T2** | Dell: enrol a OneMind test PK/KEK/db in Expert Key Management custom mode, boot a signed UKI, unlock LUKS2 sealed to the TPM, run one RAUC update and one rollback | Boots only with the OneMind-signed image; the TPM unlock survives the A/B switch; rollback works |
| **W10-T3** | Install NFD v0.20.1 + the OneMind probe on the Dell, the U55 and the Pi 5 (k3s), and run the probe alone on a leaf device. Apply three sample manifests (Ollama-like, Isaac-Sim-like, HA-like) | Verdicts match a hand-made expectation table; the leaf node reports over NATS; unknown values give "?" not ✓ |
| **W10-T4** | Jetson Orin Nano Super with k3s: GFD with `device-discovery-strategy=tegra` | `nvidia.com/gpu.product`, `.family` and `.memory` labels appear; the probe sets `memory.unified=true` |
| **W10-T5** (Q304) | Measure idle and load watts with a USB-C/AC meter: Pi 5, Jetson (7/15/25 W modes), U55, Dell (lid closed) | Numbers recorded; Edge idle within 2× of HA Green's ~1.7 W [C-W10-021] (expected to fail: Pi 5 + NVMe is higher; record it) |
| **W10-T6** | Hot-plug a Zigbee dongle and a USB-CAN adapter into the Pi 5 | Superpower changes to "Sensor gateway" within 60 s; the HA app's verdict changes from ! to ✓ |

---

## 12. Recommendations with requirement IDs

| ID | Recommendation | Requirements | Depends on |
|---|---|---|---|
| **W10-R1** | Define the line as Node (leaf) + Edge + Lite + Pro + Robotics + Omni, all on Tier A image families; NVMe on every box | H-3, P-5, F-14, N-1, N-2 | 01 §1 |
| **W10-R2** | Build `onemind-probe` + NFD + GFD capability detection; labels `onemind.io/cap.*`; `NodeCapabilities` in NATS KV; probe also on leaf nodes | N-3, F-14, N-1, F-2 | W4 §8, W19 manifest |
| **W10-R3** | Add `requires`/`recommends`/`placement` to `onemind.app.yaml`; five verdicts including "runs on another node" and "untested" | N-3, A-8, A-1, UX-6 | W19 (DC-16) |
| **W10-R4** | Derive superpowers from rules (§4.1); show them on the dashboard and use them for placement | P-6, N-1, UX-6 | R2 |
| **W10-R5** | Recommendation engine with stated reasons, labelling of OneMind-sold items, dated prices and BYO overrides | A-8, M-2 | R2, R3, R7 |
| **W10-R6** | Bundles = hardware rule + profile + pins + accessories + support; applicable to BYO | A-7, H-4, P-7, P-8 | W8 Q258, W12 |
| **W10-R7** | Year 1: "Works with OneMind" certified list + images; no own hardware. Year 2: ODM DTC Lite/Edge. Partners and distributors later | H-1, H-2, M-6, R-2 | W16 pricing |
| **W10-R8** | Robotics SKUs on production Jetson modules + partner carriers only; dev kits for development | M-7, N-7, N-8, R-3 | W7 |
| **W10-R9** | ODM requirements: TPM 2.0, custom Secure Boot keys, auto power-on, LVFS, BOM lock, embedded-option silicon | R-3, D6 (ADR-001), H-4 | W6 |
| **W10-R10** | Every SKU sheet states a support-end date bounded by the module lifecycle; 2-year EU liability in the reserve | R-2, R-3 | W6 CRA |
| **W10-R11** | Order a Pi 5 8 GB + NVMe and a Jetson Orin Nano Super by 2026-11-16; apply to Inception now; run W10-T1 in week 1 | D-004, D-006, D-002 | 20-PLAN |

---

## 13. Flags: contradictions with Tier A or the docs (not silently resolved)

| # | Flag | Where | Evidence | Suggested resolution (owner) |
|---|---|---|---|---|
| **F-1** | HARDWARE.md "Lite: Intel N150/N300, **16–32 GB**" is impossible: Intel caps both at 16 GB, single channel | `docs/HARDWARE.md` §4 | C-W10-039, C-W10-040 | Lite = 16 GB; a 32 GB box needs a different CPU class (docs owner) |
| **F-2** | HARDWARE.md prices are stale: Pi 5 16 GB $305 → $385; DGX Spark $4,699 may be higher (UNVERIFIED) | `docs/HARDWARE.md` §2 | C-W10-034, C-W10-032, C-W10-033 | Re-price at purchase; buy the 8 GB Pi |
| **F-3** | Pro/Omni "Isaac Sim" promise vs the **Debian core** on x86: Isaac Sim lists only Ubuntu and Windows; GPU Operator lists no Debian | 01 §1 (GPU-server flavor conditional) | C-W10-016, C-W4-021 | Isaac-Sim-capable SKUs ship the Ubuntu GPU-server flavor once Q-W2-1 (Canonical) is answered; until then they are "Untested" on Debian. **Founder decision**, consistent with 01's conditional |
| **F-4** | "Edge" means Pi 5/CM5 in HARDWARE.md, but Jetson Orin Nano in `research/platform/robotics-iot-xr-nvidia.md` | docs vs research | — | This file uses HARDWARE.md's meaning (Edge = Pi); Jetson = Robotics |
| **F-5** | HARDWARE.md's Robotics tier implies dev kits as candidates ("AGX Orin 64 GB or AGX Thor dev kit"); NVIDIA says dev kits are not for production | `docs/HARDWARE.md` §2 | C-W10-027 | Dev kits for the lab; production modules for SKUs (W10-R8) |
| **F-6** | 01 says "k3s on every platform node ≥ 4 GB + SSD"; a Jetson Orin Nano 8 GB qualifies on paper, but its 8 GB is **shared with the GPU** | 01 §1 | C-W10-030, C-LAB-k3s-footprint-restore-007 | Measure in W10-T4; W7 decides agent vs leaf on robots (Q44) |
| **F-7** | "Manufacture with Olares" (H-4's model) was not found on any public page | `docs/REQUIREMENTS.md` H-4 | search only | Treat as UNVERIFIED until the Olares teardown confirms it |

---

## 14. Open items and assumptions

- **Assumptions (rule 8):** the founder accepts a no-own-hardware year 1 (W10-R7); the 8 GB Pi is acceptable for the bake-off; the Dell can be dual-booted or given a second SSD. All three go to `26-…` as `blocked: founder-decision`.
- **Not sourced (need quotes):** ODM prices and MOQs, carrier-board prices, certification lab cost and time, freight, distributor margins, warranty failure rates (Q176, Q180, Q191, Q192). Draft outreach belongs in `evidence/outreach-drafts.md` (owned by the lead, not written here).
- **Not researched in this pass:** RK3588/Qualcomm/NXP vendor longevity (Q24), RISC-V timing (Q203), rugged carrier prices (Q319), LVFS support per vendor (Q36), Jetson partner-tier entry requirements (Q179), Umbrel/Olares ODM identities via FCC IDs (Q171).
- **Volatility:** every price here has a 12-month re-check, but 2026 prices moved within weeks. Re-read before any purchase.

---

## Glossary

| Term | Meaning |
|---|---|
| **BOM** | Bill of materials: every part in a product and its cost. "Landed" cost adds shipping, duty and fees. |
| **ODM / OEM** | Original design manufacturer (designs and builds a box you brand) / original equipment manufacturer (sells a product under its own name, possibly built by an ODM). |
| **MOQ** | Minimum order quantity. |
| **Carrier board** | The board a Jetson or Compute Module plugs into; it provides the connectors (USB, CAN, cameras, power). |
| **Dev kit vs production module** | A dev kit is for building software; NVIDIA warrants it for development use only. A production module goes into the product you sell. |
| **NFD** | Node Feature Discovery: a Kubernetes add-on that inspects each node's hardware and labels it. |
| **GFD** | GPU Feature Discovery: NVIDIA's add-on that labels nodes with GPU model, memory and compute capability, including on Jetson. |
| **Unified memory** | CPU and GPU share one RAM pool (Jetson, DGX Spark, Apple M). "16 GB" there is not the same as 16 GB of graphics memory on a card. |
| **RT cores** | Ray-tracing hardware on RTX GPUs; Isaac Sim needs them. |
| **Superpower (P-6)** | The specialty OneMind assigns to a machine from its detected hardware. |
| **Verdict** | The answer to "can this app run here?": ✓, !, →, ✗ or ?. |
| **Leaf node** | A small device that runs only a NATS leaf (no Kubernetes) and forwards data to the cluster. |
| **Embedded options** | Intel's marker for CPUs offered in long-availability embedded versions. |
| **LVFS / fwupd** | The Linux firmware-update service and tool; vendors publish BIOS updates through it. |
| **ENC / 5A992** | US export-control rules for products containing encryption; mass-market items can self-classify. |
| **MSRP** | Manufacturer's suggested retail price. |

## Sources
See `evidence/sources/W10.md` (37 rows, plus reused claim IDs). Every claim ID above resolves in `evidence/claims/W10.csv` or in the Tier A ledgers listed there.
