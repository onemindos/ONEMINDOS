# 08 · Robotics, drones and physical AI

**Workstream:** W7 · **Depth:** Tier A for foundation fit (DC-08, DC-09, DC-14, DC-15, plus Jetson input to DC-07); P1 for the plan and the physical-AI outlook · **Date:** 2026-11-10 (synced to `01` rev. 4.1 on 2026-11-11, SYNC5-c) · **Status:** final for this run; refuters have run (W7 P0 refuters and the dedicated DC-08, DC-09, DC-14 and DC-15 refuters, `01` §5.7 and §5.9)
**Sync note (rev. 4.1):** the core base is now the one in `01` §1: **Ubuntu 26.04 LTS + RAUC A/B** is the decision of record, with a **Debian 13 leg** built from the same definition until the base is locked. The update engine is **RAUC** on x86 and Pi 5 and **NVIDIA's rootfs A/B + image-based OTA on Jetson**, under one OneMind release contract, so "Rugix everywhere" below is history (Rugix is the documented alternative). The Jetson flavor is unchanged: **NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+)** on every core base. Two points from the blind S1 refuters (`01` §5.1.3) bear on this file. First, "one OS" is one runtime contract over a 26.04 core and a 24.04 Jetson flavor: JetPack 7.2 is still Ubuntu 24.04 on kernel 6.8, with no 26.04 base stated [C-REF5-S1-technical-003, C-REF5-S1-technical-004, C-REF5-S1L-009], and 24.04's standard support ends 2029-05-31, two years before 26.04's 2031-05-29 [C-REF5-S1-technical-001]. Second, NVIDIA's first official Yocto release for JetPack 7.2 (via OE4T meta-tegra, no formal LTS commitment stated) is new evidence for the Jetson-flavor question DC-09 (§3 row (c), `01` §6.9), not for the core base [C-REF5-S1L-010].
**Claims:** `evidence/claims/W7.csv` (C-W7-001 to C-W7-059) · **Sources:** `evidence/sources/W7.md` · **Question statuses:** `evidence/qbank/W7.md`
**Serves requirements:** M-7, N-1, N-2, N-3, N-4, N-7, N-8, N-10, F-1, F-2, F-3, F-4, F-7, F-11, F-14, R-1, R-3, H-1, H-3, AI-2, AI-4, AI-5, AI-7, P-8, D-001, D-002

> ### Explain it like I'm the founder
> A robot is not one computer. A real robot has **three brains**, and each one has a different job.
> 1. **The reflex brain:** a small microcontroller (MCU) that runs the emergency stop and the motor safety limits. It must never crash, so it runs tiny certified firmware. Linux and AI never run here.
> 2. **The body brain:** Linux on the robot (a Jetson, a Pi or a mini PC). It runs the motor control loops, the sensors and ROS 2, the robot software framework. This Linux needs **real-time** behavior: the control loop must run every millisecond, on time, every time.
> 3. **The thinking brain:** the AI models and the OneMind box or cluster. They plan, see and talk, and they can be a little slow without anyone getting hurt.
>
> "Does our base OS hold for robots for 10 years?" really asks whether **the body brain** can run on OneMind's image for that long. This report's answer is **yes, with three conditions**.
> - **Real time** is now part of normal Linux (since kernel 6.12). Debian ships a ready-made real-time kernel, and so do Raspberry Pi and NVIDIA. NVIDIA's version is still labelled "preview".
> - **ROS 2 doesn't officially support Debian.** It doesn't support the Ubuntu that NVIDIA's Jetson uses (24.04) for its newest release either. So ROS 2 runs in containers on every OneMind box, whatever the base. That is the industry pattern already: NVIDIA itself recommends Docker for Isaac ROS.
> - **On a Jetson, NVIDIA owns the kernel.** NVIDIA promises the Orin chips stay on sale until January 2032 and the Thor chips until 2035–2036. But it publishes **no promise** about how long it ships software updates. Its history is about 5 years per software branch. So every Jetson robot must be built to move to a new NVIDIA software branch **in the field, without being reflashed**. That only works if the robot was flashed with a two-slot (A/B) disk layout on day one.
>
> **What changes in ADR-001:** nothing in the core decision (D2) on robotics grounds. (When this was written D2 was Debian 13; `01` rev. 4 moved the decision of record to Ubuntu 26.04 for scorecard reasons, not robotics ones, and the Jetson flavor is the same on both.) The Jetson flavor stays on NVIDIA's Ubuntu-based software, as proposed. But D3's "Rugix everywhere" **can't cover Jetson today**: Rugix has no Jetson support. The robot tier will therefore have a second updater unless W3 picks a framework that also covers Jetson. D6's default security policy also needs a named exception for robot apps, because ROS 2's fast shared-memory transport needs permissions that the default policy blocks.

---

## 0. The answer (P0 conclusions, each stated so it can be refuted alone)

| ID | Conclusion | Evidence | Effect on ADR-001 |
|---|---|---|---|
| **FF-1** (DC-08) | NVIDIA commits Jetson **hardware** availability (Orin to Jan 2032, AGX Orin Industrial to Jul 2033, T5000 to Aug 2035, T4000 to Jan 2036), but publishes **no software-support period** per Jetson Linux release. Its observed branch lifetimes are about 5.7 years (r32) and about 4.5 years (r35, ended 2026-10-30 with JetPack 5.1.8, the final JetPack 5 release). | [C-W7-001] [C-W7-002] [C-W7-003] [C-W7-004] [C-REF-W7L-001] [C-STEEL-jb-012] | D2 holds. The CRA support period for any Jetson SKU must be planned on observed history plus at least one in-field branch upgrade, not on a vendor promise. |
| **FF-2** (DC-08) | Mainline Linux can't replace NVIDIA's Jetson kernel within the planning window. Orin and Thor device trees are upstream, but NVIDIA still ships out-of-tree modules and calls its own kernel "the most complete and best tested". | [C-W7-011] [C-W7-012] | The Jetson flavor stays on NVIDIA's BSP kernel (kernel route (c) in W18). |
| **FF-3** (DC-09) | The Jetson flavor should stay on **NVIDIA's L4T Ubuntu 24.04 (JetPack 7.2+)**, as ADR-001 proposes. A **Debian rootfs on Jetson is not a supported option**: NVIDIA lists only L4T Ubuntu, Canonical Ubuntu for Jetson and Yocto (OE4T). **Yocto meta-tegra is now NVIDIA-official** and has LTS branches, which makes it the credible runner-up for a product-grade robot image. | [C-W7-007] [C-W7-008] [C-W7-015] | D2 confirmed for Jetson. Add meta-tegra as the named fallback. |
| **FF-4** (DC-07 input) | **Rugix has no Jetson boot flow**, and RAUC's community layers have no Tegra layer. Mender (JetPack 5/6 layers) and SWUpdate (OE4T's own A/B demo) are the open frameworks with maintained Jetson integrations. NVIDIA's own image-based A/B also exists. Both stock JetPack and OE4T flash a **non-redundant** layout by default. | [C-W7-017] [C-W7-018] [C-W7-019] [C-W7-014] [C-W7-013] | D3 "one updater" fails for Rugix and RAUC on Jetson. W3 must weigh a second updater against Mender or SWUpdate everywhere. Every Jetson must be flashed A/B from day one. |
| **FF-5** (DC-14) | A PREEMPT_RT kernel exists on **every** target flavor: mainline since v6.12, Debian trixie `linux-image-rt-{amd64,arm64}`, Raspberry Pi `-rpi-v8-rt` builds (no Pi 5-optimised build), and NVIDIA's L4T RT kernel (**Developer-Preview quality**). No alternative base gives Jetson a better RT kernel, because they all use NVIDIA's kernel. | [C-W7-020] [C-W7-021] [C-W7-024] [C-W7-009] | DC-14's flip condition is **not met**. Real time becomes an image profile, not the default. Hard real time and safety go to an MCU. |
| **FF-6** (DC-15) | ROS 2 treats **Debian as Tier 3** (Jazzy: Bookworm only; Lyrical: trixie, with early EOL 2028-08-09), and Debian packages no ROS 2. For the current LTS (Lyrical), **Ubuntu 24.04, the JetPack 7 base, is also Tier 3**. So ROS 2 must run in containers on every OneMind flavor; Debian isn't singled out. The one Ubuntu-only coupling found is **Isaac ROS on x86**, which officially lists only Ubuntu 24.04 hosts. | [C-W7-026] [C-W7-027] [C-W7-030] [C-W7-031] | D2 holds with one CONDITIONAL: Isaac ROS on a Debian x86 host is unvalidated (lab LAB-W7-3). |
| **FF-7** (DC-15) | Containerized ROS 2 works, but its fast paths need host privileges: Fast DDS shared memory needs host network **and** host IPC; real-time threads need `SYS_NICE`. Kubernetes' Baseline Pod Security forbids all three. Debian's kernel leaves `RT_GROUP_SCHED` off, so cgroup v2 doesn't block real-time threads inside containers. | [C-W7-033] [C-W7-034] [C-W7-022] [C-W7-023] | D6 needs a **scoped "robot runtime" exception** (a signed-app allowlist), not a blanket relaxation. |
| **FF-8** (Q44) | No robot vendor checked runs Kubernetes on board. Spot CORE I/O uses Docker Extensions on JetPack 5.1.2. Clearpath installs plain Ubuntu 24.04 from an ISO. AuterionOS ships OS plus flight firmware as one signed file. Viam's agent installs on an existing OS. | [C-W7-040] [C-W7-039] [C-W7-042] [C-W7-043] | Input to D4 (W4): the robot should be a **k3s agent or a lighter node agent**, never a k3s server, and control loops stay outside Kubernetes scheduling. |

**Overall verdict on the foundation question (does the base hold for robots for 10 years?):** **Upheld, CONDITIONAL.** ADR-001's base design (D2) survives every W7 flip condition. The conditions it carries into the plan are: (1) A/B redundant flashing of every Jetson from day one, plus at least one planned in-field NVIDIA branch upgrade per robot lifetime; (2) an updater decision for Jetson (FF-4, owned by W3); (3) a robot-runtime security profile (FF-7, owned by W6); (4) the founder-hardware lab tests in §10. **Refuters:** this file states each conclusion so it can be tested alone. The 3-refuter tables are produced by the orchestrator and recorded in `01-FOUNDATION-DECISION.md`. §8 lists the strongest counter-evidence W7 found against itself.

---

## 1. Does the base OS hold for robots over 10 years? The timeline

Every line below comes from a primary source. "Free" means community or vendor support at no per-device cost.

```
                    2026   2027   2028   2029   2030   2031   2032   2033   2034   2035   2036
Debian 13 (trixie)  ████████████████ LTS to 2030-06-30 (W2 claims) ····· ELTS paid → 2035 ·····
ROS 2 Jazzy LTS     ██████████████████ May 2029                          [C-W7-029]
ROS 2 Lyrical LTS   ███████████████████████████████ May 2031             [C-W7-029]
 ↳ Lyrical on trixie (Tier 3)  ████ early EOL 2028-08-09                 [C-W7-027]
 ↳ Lyrical on Ubuntu 24.04 (Tier 3) ███████ early EOL 2029-06-01         [C-W7-027]
Jetson Orin modules ████████████████████████████████████ Jan 2032        [C-W7-001]
AGX Orin Industrial ██████████████████████████████████████████ Jul 2033  [C-W7-001]
Jetson T5000 / T4000 ████████████████████████████████████████████████████ Aug 2035 / Jan 2036 [C-W7-002]
L4T branch history  r32: 2019-03 → 2024-11 (≈5.7 y) · r35: 2022-04 → EOL 2026-10-30 (≈4.5 y) [C-W7-004][C-REF-W7L-001]
EU Machinery Reg.   applies from 2027-01-14 ─────────────────────────────────────────────────▶ [C-W7-045]
```

**How to read it:** the hardware outlives every software line under it. A robot sold in 2027 on an Orin module can still be built in 2032. It will outlive Lyrical (2031), Debian 13's free LTS (2030), and probably the JetPack 7 branch. So the 10-year question isn't "which distro lasts 10 years". **Nothing in robotics lasts 10 years on one release.** The real question is **"can a robot in the field move to the next release safely?"**. That is a property of the update system (A/B slots, signed bundles, health-gated commit), not of the distro. ADR-001 already makes that the core of D3, which is the right instinct.

---

## 2. DC-08: the Jetson BSP and module lifecycle

### 2.1 What NVIDIA promises (and doesn't)

| Item | Fact | Claim |
|---|---|---|
| Orin hardware | AGX Orin 64/32 GB, Orin NX 16/8 GB, Orin Nano 8/4 GB: available through **January 2032** | [C-W7-001] |
| Industrial | AGX Orin Industrial: **July 2033** | [C-W7-001] |
| Thor hardware | T5000: **August 2035**; T4000: **January 2036** | [C-W7-002] |
| New Thor modules | T3000 (865 FP4 TFLOPS, 32 GB) and T2000 (400 FP4 TFLOPS, 16 GB) announced 2026-07-15, **available Q1 2027**; IGX T3000 adds integrated functional safety | [C-W7-048] |
| Software support period | **Not stated.** The lifecycle page covers hardware only. It promises an EOL notice at least 8 months before last shipment. | [C-W7-003] |

### 2.2 What NVIDIA actually did (branch history)

| Branch | JetPack | Base | First listed | Latest listed | Lifetime so far | Claim |
|---|---|---|---|---|---|---|
| r32 | 4.x | Ubuntu 18.04 (UNVERIFIED by W7) | 32.1, Mar 2019 | 32.7.6, Nov 2024 | ≈ 5 y 8 m | [C-W7-004] |
| r34/r35 | 5.x | Ubuntu 20.04 (UNVERIFIED by W7) | 34.1, Apr 2022 | **35.7.0, Oct 2026 (final; JetPack 5 EOL 2026-10-30)** | ≈ 4 y 6 m, ended | [C-REF-W7L-001] [C-STEEL-jb-012] |
| r36 | 6.x | Ubuntu 22.04, kernel 5.15 (SECONDARY: JetPack 7.2 migration tables) | 36.2, Dec 2023 | 36.5.2, Aug 2026 | ≥ 2 y 8 m, still active | [C-W7-006] |
| r38 | 7.0/7.1 | Ubuntu 24.04, kernel 6.8 | 38.2, Aug 2025 | 38.4, Jan 2026 | **Thor only**, superseded by r39 | [C-W7-006] [C-W7-015] |
| r39 | 7.2/7.2.1 | Ubuntu 24.04, kernel 6.8 | 39.2, Jun 2026 | 39.2.1, Aug 2026 | brings **Orin into JetPack 7** | [C-W7-007] [C-W7-008] |

**Two lessons.**
1. NVIDIA keeps old branches alive for years in practice: r35 still got a release in October 2026. But this is behaviour, not a contract. A refuter can rightly point out that a future branch could be cut shorter.
2. **Orin waited about 10 months for JetPack 7** (r38 shipped Thor-only in August 2025, and r39 brought Orin in June 2026). New NVIDIA software lands on the newest silicon first. This resolves contradiction C-6 in `context/03`: r38.x was Thor-only, r39.x covers both.

**Real-world proof that robot vendors sit on old branches:** Boston Dynamics' Spot CORE I/O 4.x still runs **JetPack 5.1.2 (L4T R35.4.1)** [C-W7-040]. ModalAI's VOXL 2 (a Qualcomm drone computer) is documented as **Ubuntu 18.04 with kernel 4.19** [C-W7-041]. Both show the real risk: **vendor-BSP robots get stuck.** OneMind's differentiation can be that its robots **don't**.

### 2.3 How far is Jetson from mainline Linux?

- Mainline v6.18 has device trees for Orin (tegra234: P3701 AGX, P3767 Orin NX/Nano and their carriers) and Thor (tegra264: P3834, P3971) [C-W7-012].
- NVIDIA's "Bring Your Own Kernel" page lists Tegra patches accepted upstream from v5.15 to v6.7. It ships **out-of-tree modules** for drivers that "cannot be upstreamed or that have not yet been upstreamed", and says its own kernel is "the most complete and best tested" [C-W7-011]. The RT kernel packages are split the same way: Orin needs `nvidia-l4t-rt-kernel-nvgpu`, and Thor needs `-openrm` [C-W7-009].
- **Conclusion:** a mainline kernel boots Jetson, but the GPU, camera and display paths a robot needs still come from NVIDIA's out-of-tree code. Within the 5-year horizon, the Jetson flavor uses **NVIDIA's kernel**. That means W18's kernel route (c), a vendor BSP kernel, for this flavor only.

### 2.4 Verdict, flip condition and what would change it

- **DC-08 flip condition:** "the security-update window per L4T release is shorter than the support period OneMind must declare, with no affordable bridge." **Status: not triggered, but unbounded.** With no published window, OneMind can't *prove* the bridge. The affordable bridge is the in-field branch upgrade (§4). Its cost is real but bounded: a Jetson image rebuild and a test cycle per JetPack major release, about every 2–3 years based on r32 → r35 → r36 → r39.
- **What would flip it:** (a) NVIDIA ending r36/r39 security releases less than 3 years after first release; or (b) an in-field JetPack 6 → 7 upgrade failing on the A/B layout in LAB-W7-4. In either case the Jetson SKUs would need a paid support route (an NVIDIA or partner agreement), or a CRA support period declared short.
- **Recommendation W7-R1:** for any Jetson SKU, declare a CRA support period that **ends no later than** the earlier of (module "available through" date + 2 years) and (the last observed branch lifetime + one planned in-field upgrade). Re-check NVIDIA's archive every 6 months (claims re-check dates). *Serves R-3, H-1, M-7, F-2.* Draft outreach to NVIDIA asking for a written software-support statement goes in `evidence/outreach-drafts.md` if W16/W6 request it.

---

## 3. DC-09: which base for the Jetson flavor?

### 3.1 The options, against primary sources

| Option | Who supports it | JetPack stack (CUDA, TensorRT, Isaac ROS) | A/B and updates | Evidence | Fit for OneMind |
|---|---|---|---|---|---|
| **(a) NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+)**, made image-based by OneMind | NVIDIA (reference) | Full; Isaac ROS lists JetPack 7.2 | NVIDIA bootloader A/B is on by default; rootfs A/B is a flash-time option; capsule updates for firmware | [C-W7-007] [C-W7-013] [C-W7-031] | **Recommended now.** It is the path NVIDIA and Isaac ROS test. ADR-001's proposal. |
| (b) Canonical Ubuntu 24.04 for Jetson | NVIDIA lists it as a supported distro | Same as (a), per NVIDIA's listing (component parity not verified by W7) | Ubuntu tooling | [C-W7-008] | Possible; adds Canonical terms (W2/W16 price Ubuntu Pro). No advantage over (a) for OneMind found. |
| **(c) Yocto meta-tegra (OE4T)** | **NVIDIA-official recipes since JetPack 7.2**; community maintainers | JetPack 7.2.1 on `wrynose` (LTS); JetPack 6.2.3 on `scarthgap` (LTS); container runtime docs exist | Redundant layouts, capsule build, SWUpdate demo, Mender layers (JP5/6) | [C-W7-008] [C-W7-015] [C-W7-017] [C-W7-018] | **Runner-up**, and the right choice if OneMind sells its own Jetson robot with a minimal, SBOM-clean image. Bus-factor risk: one maintainer has 2,373 commits against 189 for the next [C-W7-016]. |
| (d) Debian 13 rootfs on NVIDIA's BSP | **Not in NVIDIA's supported-distro list** | Unvalidated | You build it all | [C-W7-008] (absence) | **Rejected.** It would make OneMind the only tester of NVIDIA's userspace on Debian. |
| (e) Kairos Jetson / balenaOS Jetson | Vendors (prior-verified in `context/03`, not re-opened by W7) | Per vendor | Kairos A/B; balena Yocto A/B | `context/03` §1.2 | Reference designs only. Kairos lacks Pi 5, and balena is a fleet platform with its own plane. |

### 3.2 Recommendation

- **W7-R2:** keep the Jetson flavor on **NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+)** and make it image-based: a read-only root, A/B slots, and OneMind's agent, k3s agent and NVIDIA container toolkit in the image. Everything else ships as containers. *Serves M-7, N-8, F-2, D-002.*
- **W7-R3:** build a **meta-tegra `wrynose` spike** in year 1 (LAB-W7-6). Switch to it only if OneMind ships its own Jetson robot hardware and the CRA SBOM work on (a) proves too heavy. *Serves R-3, F-7, H-1.*
- **Ruled out for now:** Debian on Jetson. Re-open it only if NVIDIA adds Debian to its supported-distro list.
- **G1 (license) is CONDITIONAL for every Jetson option.** The BSP binaries are covered by NVIDIA's `Tegra_Software_License_Agreement-Tegra-Linux.txt`, whichever rootfs is used [C-LIC-001]. The agreement text has since been opened (license matrix §6): the BSP may be redistributed **unmodified**, on NVIDIA hardware only, with the agreement attached; it is revocable and not certified for "Critical Applications" [C-LIC-002] [C-LIC-003] [C-LIC-004] [C-LIC-005]. So the BSP part of G1 passes with conditions [C-LIC-048]; the Jetson flavor stays G1-conditional because of the Ubuntu rootfs [C-LIC-011]. NVIDIA partner terms (Q59) are still worth confirming before any Jetson SKU is sold.

### 3.3 What competitors chose for NVIDIA robot computers (constraint fit)

| Product | Jetson/robot OS and updates | Constraints | Constraint fit with OneMind |
|---|---|---|---|
| Boston Dynamics Spot CORE I/O | JetPack 5.1.2 (L4T R35.4.1); apps as Docker "Extensions" | One robot SKU; large company; payload computer, not the safety system | **High for app delivery** (containers on a vendor BSP). **Low for longevity**: it is two JetPack majors behind. [C-W7-040] |
| Clearpath (ROS 2 Jazzy) | Lightly customized Ubuntu 24.04 ISO plus a setup script; amd64 only | Research robots; customers own the OS | **Low**: no image updates or rollback; a reinstall wipes the drive. [C-W7-039] |
| Auterion (Skynode) | AuterionOS plus flight firmware in **one signed .auterionos file**; remote, app or USB updates | Drone OEM; defense customers | **High for the update model**: one artifact for OS + firmware, verified before install. [C-W7-042] |
| ModalAI VOXL 2 | Ubuntu 18.04, kernel 4.19, on Qualcomm QRB5165 | Small drone-compute vendor on a Qualcomm BSP | **Cautionary**: shows how vendor-BSP stagnation looks. [C-W7-041] |
| Home Assistant OS / umbrelOS / Olares | No robotics support or Jetson image found (ADR-001 §1; W1 teardowns) | Appliances; Olares runs k3s | **None for robotics.** OneMind can't copy a robot pattern from them. This is why W7 uses robot vendors as the proof. |

---

## 4. Jetson updates (W7 input to DC-07, owned by W3)

**What the code and docs show:**

| Framework | x86 | Pi 5 | Jetson | Evidence |
|---|---|---|---|---|
| Rugix v1.4.0 (2026-11-02) | GRUB / systemd-boot | tryboot | **None** (no Tegra, Jetson, L4T or nvbootctrl code) | [C-W7-019] [C-W7-058] |
| RAUC (meta-rauc-community) | genericx86-64 | raspberrypi | **No Tegra layer** | [C-W7-018] |
| Mender (meta-mender-community) | yes (W3 to confirm) | meta-mender-raspberrypi | **meta-mender-tegra-jetpack5 / -jetpack6** (scarthgap) | [C-W7-018] |
| SWUpdate | yes (W3) | UNVERIFIED by W7 | **OE4T's own A/B demo image** | [C-W7-017] |
| NVIDIA native | n/a | n/a | Bootloader A/B on by default, capsule firmware updates, rootfs A/B as a flash option | [C-W7-013] |

**Three facts the update design must respect on Jetson:**
1. **A/B must be chosen at first flash.** Stock JetPack and OE4T both default to *non-redundant* layouts, and OE4T notes that picking the redundant one at the start "might give you the option to support updates later without a repartition (or tegraflash)" [C-W7-014]. → **W7-R4:** every OneMind Jetson is flashed with the redundant rootfs layout, even before the update agent exists. *Serves R-1, M-7.*
2. **Firmware and OS slots are paired.** Capsule updates write the non-current bootloader slot, and the redundant rootfs follows the slot [C-W7-013] [C-W7-014]. An updater that only swaps the rootfs (the Rugix model) would leave the Jetson bootloader unmanaged.
3. **Branch jumps have traps.** From L4T R38 on, NVIDIA uses a different capsule GUID per UEFI configuration. A field upgrade to R39 must plan the GUID, or capsules won't apply [C-W7-057]. → the LAB-W7-4 test must include a JetPack 6 → 7 jump.

**W7 position for W3:** the "Rugix everywhere" design (D3) needs either (i) a **second updater on Jetson** (NVIDIA's native A/B, or SWUpdate/Mender via meta-tegra) behind the **same OneMind update API, signing keys and UX**, or (ii) a single framework that covers all three (Mender or SWUpdate are the only candidates with maintained Jetson layers). W7 doesn't decide D3. Option (i) is workable for a solo developer only if the OneMind update agent abstracts the slot tool, as Rugix's own "boot flow" design already does for other bootloaders.

---

## 5. DC-14: real-time needs of robotics

### 5.1 What "real time" means here

A **control loop** reads sensors, computes and writes motor commands, often 1,000 times per second (every 1 ms). If one cycle is late, the arm jerks. **PREEMPT_RT** makes Linux's worst-case delay small and predictable. It doesn't make Linux "safe", and it doesn't make it certifiable.

### 5.2 Availability per flavor (primary sources)

| Flavor | RT kernel available? | Package / source | Quality | Claim |
|---|---|---|---|---|
| Mainline | Yes, **from v6.12** (`ARCH_SUPPORTS_RT` selected on x86, arm64 and riscv in v6.12, none in v6.11) | upstream | Upstream | [C-W7-020] |
| Debian 13 x86 and arm64 | Yes | `linux-image-rt-amd64`, `linux-image-rt-arm64` 6.12.116-1 | Debian-supported | [C-W7-021] [C-W7-022] |
| Raspberry Pi 5 (Raspberry Pi kernel) | Partly | `-rpi-v8-rt` builds 6.12.x and 6.18.x; **no `rpi-2712` RT build**; the docs say you can build one without patches | Packaged but not documented as supported | [C-W7-024] [C-W7-025] |
| Jetson (L4T r39.2.1) | Yes | `nvidia-l4t-rt-kernel*` via apt (OTA) | **"Developer-Preview quality"**; Isaac ROS recommends it "only for use with robot manipulators" | [C-W7-009] [C-W7-010] |
| Kubernetes | Placement only | static CPU manager: exclusive cores for Guaranteed pods with integer CPUs | Stable since v1.26; no API for SCHED_FIFO | [C-W7-035] |
| Containers on cgroup v2 | Works on Debian's kernel | `RT_GROUP_SCHED` is off in Debian, so RT threads can run in non-root cgroups | — | [C-W7-022] [C-W7-023] |
| ros2_control | Expects it | controller_manager tries SCHED_FIFO priority 50; the docs say a normal kernel is "not well suited for hardware control" | — | [C-W7-036] |

### 5.3 Verdict

- **DC-14 flip condition:** "an RT kernel isn't available on a target flavor, and the alternative base provides one." **Not met.** Every flavor has one. On Jetson the RT kernel is NVIDIA's on *every* base (Ubuntu, Yocto, Canonical), so no alternative base improves it.
- **Two real gaps:** (1) the Pi 5 RT build is the generic `v8` kernel, not the Pi 5-optimised `2712` build. OneMind either uses `v8-rt` (to be measured) or builds a `2712` RT variant in CI. (2) Jetson RT is preview-quality, so **OneMind must not market hard real time on Jetson.**
- **Latency numbers:** `blocked: founder-hardware`. QEMU timing is meaningless for this, so the measurement is LAB-W7-1.

### 5.4 The robot node architecture (recommendation)

```
┌───────────── OneMind box / cluster (k3s server, NATS, AI capability gateway, sim) ─────────────┐
│  Plans, perceives, talks. May be slow or offline. Never the safety function.                    │
└───────────────▲──────────────────────── NATS leaf (store-and-forward) ──────────────────────────┘
                │ commands go through the capability gateway: approval, rate limit, geofence, TTL
┌───────────────┴──────────── Robot Linux = OneMind image (Jetson / Pi 5 / x86) ──────────────────┐
│ Non-RT cores: k3s AGENT (not server) · ROS 2 containers (Lyrical) · Zenoh router · robot gateway │
│ RT cores (isolcpus, static CPU manager): ros2_control in a "robot-runtime" pod, SCHED_FIFO      │
│ Kernel: RT image profile (Debian linux-image-rt / rpi-v8-rt / nvidia-l4t-rt-kernel)             │
└───────────────▲──────────────────────────── serial / CAN / dedicated Ethernet ──────────────────┘
┌───────────────┴────────── MCU safety layer (Zephyr / NuttX-PX4 / safety PLC) ───────────────────┐
│ E-stop, safety-rated speed and force limits, watchdog → safe state if Linux stops answering     │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **W7-R5:** ship real time as an **image profile** ("robot-rt"), not the default kernel. Default boxes keep the standard kernel, which gives better throughput for AI. *Serves M-7, F-7, F-11, P-8.*
- **W7-R6:** hard real time and every safety function run on an **MCU or safety controller**, never on Linux or AI. This matches the IIoT report's "supervise, not control" principle (`research/platform/iiot-landscape-and-requirements.md`). The EU Machinery Regulation also adds third-party assessment for machine-learning safety components [C-W7-046]. *Serves M-7, F-11, AI-5.*
- **W7-R7:** the robot runs a **k3s agent** (or a lighter OneMind node agent on very small robots), never the k3s server. The ROS graph stays on the robot. *Serves N-1, N-9 (input to W4), F-14.*

---

## 6. DC-15: ROS 2 tier support and containerized ROS

### 6.1 Tier facts

| ROS 2 distro | EOL | Tier 1 hosts | Ubuntu 24.04 (JetPack 7 base) | Debian | Claim |
|---|---|---|---|---|---|
| Humble | May 2027 | Ubuntu 22.04 | — | — | [C-W7-029] |
| Jazzy (LTS) | **May 2029** | Ubuntu 24.04 amd64/arm64, Windows 10 | **Tier 1** | **Bookworm Tier 3; trixie not listed** | [C-W7-026] |
| Kilted | **December 2026** (the docs table; REP 2000 says November 2026) | — | — | — | [C-W7-029] |
| Lyrical (LTS) | **May 2031** | Ubuntu 26.04 amd64/arm64, Windows 11 | **Tier 3**, early EOL 2029-06-01 | **trixie Tier 3**, early EOL 2028-08-09 | [C-W7-027] |

- Tier 3 means "community reports indicate that the release is functional" and the team runs no tests; you build it from source [C-W7-026] [C-W7-027].
- Debian packages no ROS 2: `rclcpp` returns nothing for trixie [C-W7-030].
- `rmw_zenoh_cpp` is a **Tier 1 middleware** in Lyrical [C-W7-028]. Without a Zenoh router, nodes don't discover each other, because multicast is off by default [C-W7-032].
- **Isaac ROS** targets Lyrical on JetPack 7.2 (Ubuntu 24.04), x86 Ubuntu 24.04 or DGX OS, and recommends Docker [C-W7-031]. So NVIDIA itself runs the current ROS 2 LTS on a host where upstream ROS 2 gives it only Tier 3.

### 6.2 What this means

1. **Containers are mandatory on every flavor, so this is not a Debian penalty.** Even a pure Ubuntu 24.04 OneMind would need Lyrical from containers (or NVIDIA's own build). The one way to get Lyrical Tier 1 on the host is **Ubuntu 26.04**, which no Jetson ships.
2. **OneMind should publish ROS 2 as pinned multi-arch container images**: Jazzy and Lyrical, Ubuntu userland inside, plus NVIDIA's Isaac ROS images for GPU work. → **W7-R8.** *Serves M-7, N-7, F-3, F-4.*
3. **The one host coupling found is Isaac ROS on x86**, where only Ubuntu 24.04 is listed [C-W7-031]. DC-15 is therefore **CONDITIONAL**: the Debian x86 GPU host must pass LAB-W7-3. **If it fails:** the Pro/Omni x86 GPU tier gets an Ubuntu 24.04 flavor (D2 changes for that tier only; W2/W4 decide).
4. Vendor sensor SDKs (ZED, RealSense, Ouster) weren't verified by W7 (Q56, `partial`). They run in Ubuntu containers. The risk is host kernel modules (DKMS), which LAB-W7-2 checks with one USB depth camera.

### 6.3 Containerized ROS 2 on k3s: what it needs from the OS

| Need | Mechanism | Kubernetes field | Allowed by Baseline Pod Security? | Claim |
|---|---|---|---|---|
| Same-host discovery and SHM (Fast DDS) | host network and host IPC | `hostNetwork: true`, `hostIPC: true` | **No** | [C-W7-033] [C-W7-034] |
| Zenoh discovery | a router per robot (a sidecar or DaemonSet) | normal pod networking works | Yes | [C-W7-032] |
| RT scheduling | SCHED_FIFO in the container | `capabilities.add: [SYS_NICE]` | **No** | [C-W7-034] [C-W7-036] |
| Exclusive cores | static CPU manager, Guaranteed QoS, integer CPUs | kubelet config + pod resources | Yes | [C-W7-035] |
| Devices (CAN, serial, cameras, GPU) | device plugin or DRA; the NVIDIA device plugin on Tegra needs container toolkit ≥ 1.11 | `resources.limits` | Yes (via a plugin) | [C-W7-038] |
| GPU Operator on Jetson | **Not supported** by NVIDIA | — | — | [C-W7-037] |

- **W7-R9:** define a **`robot-runtime` namespace class**. Only apps signed by a verified publisher and declaring `capabilities: [realtime, host-ipc]` in `onemind.app.yaml` may get `hostIPC`/`hostNetwork`/`SYS_NICE` there. Everything else stays on Baseline or Restricted. The Market shows a "this app controls hardware in real time" badge, and installing it needs owner approval (AI-5). *Serves M-7, AI-5, F-5; input to W6 (D6) and W19 (plugin types).*
- **W7-R10:** prefer **rmw_zenoh** for robot-to-box traffic, because a router-based design avoids DDS multicast over VPNs. Keep Fast DDS SHM inside the robot for high-bandwidth sensor data. Bridge to NATS through one **robot gateway** service. No maintained ROS 2–NATS bridge was found in phase 1 (ROBO §2.5), so OneMind builds a thin one. *Serves N-6, AI-7, AI-9, F-6.*

---

## 7. How robotics companies ship and update their OS (Q50, Q44)

| Company / product | Base | Build | Updater | Apps | k8s on board? | Claim |
|---|---|---|---|---|---|---|
| Boston Dynamics Spot CORE I/O | L4T R35.4.1 (JetPack 5.1.2) | Vendor | Vendor | Docker Extensions (compose, journald) | No | [C-W7-040] |
| Clearpath | Ubuntu 24.04 ISO | Custom ISO + script | apt | ROS 2 debs | No | [C-W7-039] |
| Auterion Skynode | AuterionOS | Vendor | Single signed `.auterionos` (OS + PX4) | Auterion apps | Not stated | [C-W7-042] |
| ModalAI VOXL 2 | Ubuntu 18.04, kernel 4.19 | Vendor (SDK) | Flash the SDK | VOXL SDK | No | [C-W7-041] |
| Viam | Customer's OS (Debian, Ubuntu, Pi OS, RHEL…) | — | viam-agent manages viam-server and apt updates | Viam modules | No | [C-W7-043] |
| NVIDIA reference (Isaac ROS) | JetPack 7.2 / Ubuntu 24.04 | NVIDIA | NVIDIA OTA, capsule | Docker | Optional | [C-W7-031] [C-W7-013] |

**Pattern:** vendor BSP base, containers for apps, a signed single-artifact update at the high end (Auterion), and **no Kubernetes on the robot**. OneMind's twist, k3s *agent* on the robot with the server on the box, is new. It is defensible because it makes the robot "just another node" (N-1), but nobody has proven it in production. W4 must measure the agent's footprint and flash writes on a Pi 5 and an Orin Nano (DC-10).

---

## 8. Self-check: the strongest evidence against these conclusions

The orchestrator runs the independent refuters. These are the attacks W7 found on its own conclusions, so refuters can go further.

| Conclusion | Strongest counter-argument | Response |
|---|---|---|
| FF-1/FF-3 (stay on NVIDIA L4T) | NVIDIA publishes no software support period. A product promising 10 years on a BSP with no written commitment is a CRA liability. Yocto + CIP-style kernels (meta-tegra) give more control. | Agreed that control is better with meta-tegra, but **the kernel is NVIDIA's either way** [C-W7-011]. meta-tegra changes the userspace, not the BSP dependency. Kept as the runner-up (W7-R3). |
| FF-4 (no Rugix on Jetson) | Rugix is extensible (a "custom boot flow" API exists), so a Jetson boot flow could be written. | True, but nobody has written or tested one. The NVIDIA-paired bootloader and rootfs slots plus capsule GUIDs [C-W7-013] [C-W7-057] make it a non-trivial, safety-critical piece for a solo developer. |
| FF-5 (RT available) | "Available" isn't "good enough". Without measurements on Pi 5 and Orin under k3s load, the claim is about packages, not latency. | Agreed. The flip test is LAB-W7-1, and the status is `blocked: founder-hardware`. |
| FF-6 (containers neutralise the Debian penalty) | Ubuntu 24.04 is Jazzy Tier 1 (to May 2029), so an Ubuntu host *does* get native Jazzy binaries that Debian doesn't. Robot integrators expect `apt install ros-jazzy-*` on the host. | True for Jazzy. But the Jazzy window (to 2029) is shorter than a 2027 robot's life, and Lyrical is Tier 3 on 24.04 too. Containers are the 10-year path either way. Recorded as a C7 (ecosystem) point for Ubuntu in the W2 scorecard. |
| FF-8 (no k3s on robots) | The absence of evidence is not proof. Some fleets may run k3s or KubeEdge on robots without publishing it. | Agreed. Phrased as "none found among those checked". |

**Steelman of the runner-up for the robot tier (Yocto meta-tegra + SWUpdate/Mender):** NVIDIA made OE4T official in JetPack 7.2 [C-W7-008]. meta-tegra keeps an LTS branch per JetPack major (scarthgap = JP6, wrynose = JP7) [C-W7-015]. OE4T already ships an A/B update demo [C-W7-017]. Mender has JetPack layers [C-W7-018]. A Yocto image carries only what OneMind puts in it, which gives a smaller CRA SBOM and less CVE noise, and the same build system covers Pi (meta-raspberrypi) and x86. If W2 picks Yocto for the core too (DC-20), the Jetson flavor stops being a second build system. **Weakness:** solo-developer cost (C5) and one dominant maintainer [C-W7-016].

---

## 9. Scorecard input: C2 (hardware and robotics fit)

Frozen anchors (`evidence/scorecard-weights.md` §4, C2). W7 supplies the C2 cell evidence for the main S1 stacks. W2 owns the final scorecard.

| S1 stack | x86 / Pi 5 / Jetson path | NVIDIA | ROS 2 host tier | RT | One updater across all 3 | Proposed C2 | Why not higher |
|---|---|---|---|---|---|---|---|
| Debian 13 + Rugix + L4T flavor (ADR-001) | yes / RPi kernel / L4T flavor [C-W7-007] | Jetson official; x86 GPU Operator doesn't list Debian (W4) | containers; Debian Tier 3 [C-W7-027] | yes [C-W7-021] | **No** (Rugix lacks Jetson) [C-W7-019] | **3** `pending-lab` | No vendor-validated x86 NVIDIA, no demonstrated container ROS stack, no single updater |
| Ubuntu 24.04 + L4T | yes / certified / native | GPU Operator + Jetson official | Jazzy Tier 1; Lyrical Tier 3 [C-W7-026] [C-W7-027] | yes (Ubuntu RT, W2) | No inherent single A/B updater | **3** (4 if W3 shows one updater) | Needs one updater across all three for 4 |
| Yocto (meta-intel/raspberrypi/tegra) + Mender or SWUpdate | yes / yes / **NVIDIA-official** [C-W7-008] | Jetson official; x86 GPU unvalidated | OpenEmbedded Tier 3 [C-W7-026] | linux-yocto-rt (W2) | **Possible** (Mender/SWUpdate have Tegra layers) [C-W7-017] [C-W7-018] | **3** (4 once the container ROS stack is demonstrated) | ROS 2 container stack not yet demonstrated |
| Fedora IoT / bootc | x86 yes; Pi 5 unproven; Jetson none found (context/03) | No Jetson path | RHEL 10 Tier 2 for Lyrical (for RHEL, not Fedora) [C-W7-027] | Fedora RT (W2) | No Jetson | **2** | No documented Jetson path |

**Finding for the scorecard:** on C2, the leading stacks **tie at 3** until two lab results land: LAB-W7-2 (container ROS on the host) and a W3 decision on one updater. So the robotics criterion **doesn't separate Debian from Ubuntu or Yocto today**. The deciding robotics factor is the updater coverage of Jetson (FF-4), which scores under C3/C5 as well.

---

## 10. Lab tests owned by W7 (for `22-HARDWARE-LAB-TEST-PLAN.md`)

Pass/fail criteria are written before running. Thresholds are W7 assumptions for a 1 kHz control loop and must be stated as such.

| ID | Hardware | Test | Pass | Fail → consequence |
|---|---|---|---|---|
| **LAB-W7-1** | Beelink/Dell (x86), Pi 5, Orin Nano | `cyclictest -m -Sp90 -i200 -h400 -D1h` on the stock and RT kernels, idle and under `stress-ng --cpu N --io 2 --vm 2` with k3s plus 10 pods running; then with `isolcpus`/`nohz_full` on 2 cores and the static CPU manager | RT kernel, isolated cores, under load: **max < 250 µs** (x86 and Pi 5); report Orin's number as-is (preview) | Pi 5 fails → build a `2712` RT kernel in CI or drop Pi 5 from robot-rt. x86 fails → investigate SMIs/firmware before blaming the OS. |
| **LAB-W7-2** | x86 + Pi 5 on Debian 13 + k3s | ROS 2 Lyrical containers: talker/listener over Fast DDS SHM with `hostIPC`; rmw_zenoh with a router pod; ros2_control demo with `SYS_NICE` + SCHED_FIFO; one USB depth camera and one USB-CAN adapter via device plugin | All four work; SHM confirmed (no UDP fallback); camera frames at nominal FPS | Any failure that works on an Ubuntu 24.04 host → DC-15 flips for that tier |
| **LAB-W7-3** | Cloud x86 RTX (Ampere+) on Debian 13 | NVIDIA driver from NVIDIA's `debian13` repo + container toolkit + Isaac ROS dev container; run one Isaac ROS sample | Sample runs with GPU acceleration | Fails on Debian, passes on Ubuntu 24.04 → Pro/Omni GPU tier gets an Ubuntu flavor |
| **LAB-W7-4** | Orin Nano Super | Flash JetPack 6.2.x with the **redundant** layout; OTA to JetPack 7.2.x; corrupt slot B → confirm fallback; cut power during the capsule update | Device boots in all cases; `nvbootctrl dump-slots-info` shows the expected slot | Bricks → Jetson SKUs need the vendor's recovery process, or a CRA period limited to one branch |
| **LAB-W7-5** | Orin Nano Super | Install `nvidia-l4t-rt-kernel*` via OTA packages; repeat LAB-W7-1 | Boots RT; report latency | Fails to boot → Jetson not offered for robot-rt |
| **LAB-W7-6** | Build host (Linux VM or cloud) | meta-tegra `wrynose` `demo-image-base` + nvidia-container runtime + k3s agent for the Orin Nano | Image builds in < 4 h on cache; container with CUDA runs | Too heavy for one developer → keep (a) permanently |

---

## 11. The robotics plan (P1)

### 11.1 Safety and regulation (what the OS must provide)

| Rule | What it says | What the OS must do | Claim |
|---|---|---|---|
| EU Machinery Regulation 2023/1230 | Applies from **14 January 2027** (the bank's "2027-01-20" is wrong). ML-based safety components need third-party conformity. Self-evolving machines must stay within their task and movement space, and must **record safety-related decision data and keep it for one year**. | A tamper-evident, append-only **robot decision log** kept ≥ 1 year; geofence and workspace limits enforced outside the AI; AI never the safety component. | [C-W7-045] [C-W7-046] |
| ISO 10218-1/-2:2025 | Robot safety classes and **cybersecurity requirements** where they affect robot safety (SECONDARY; iso.org blocked) | Signed updates and access control on anything that commands a robot | [C-W7-055] |
| ISO 13482 (service robots) | Second edition at FDIS (SECONDARY) | Same, for home and service robots | [C-W7-055] |
| PX4 uXRCE-DDS | The DDS link is **unauthenticated** and reaches uORB directly; isolate it | Never route flight-controller DDS over Wi-Fi or a VPN; serial or a dedicated cable only | [C-W7-044] |

- **W7-R11:** build the **robot decision log** into the OS audit layer in phase 1, not later. It costs little early and is a legal requirement for EU robots from 2027 [C-W7-046]. *Serves AI-4, AI-5, M-7, R-3.*

### 11.2 Drones

- **Flight firmware:** PX4 is BSD-3-Clause and ArduPilot is GPL-3.0 [C-W7-052]. Selling locked hardware favours **PX4** (no GPLv3 installation-information duty). Support MAVLink for both through MAVSDK/MAVROS adapters.
- **Companion computer:** the OneMind Jetson or Pi flavor runs the companion role (k3s agent, MAVLink gateway to NATS, video). The flight controller keeps NuttX/ChibiOS.
- **Update model to copy:** Auterion's single signed artifact for the companion OS **plus** flight firmware [C-W7-042]. OneMind's update bundle should be able to carry MCU/FC firmware as a payload (ADR-001 D3's "firmware layer").
- **US rules:** FAA Part 108 (BVLOS) was still not final as of the latest sources (SECONDARY) [C-W7-054]. Remote ID (Part 89) and EASA rules weren't opened by W7 (`partial`). Drones are therefore a **year 2+** product line; year 1 supports drones only as integrated third-party devices.

### 11.3 Middleware, fleet and data

- **NATS stays the platform bus.** ROS 2 stays local to each robot (W7-R10). Open-RMF's latest GitHub release tag is `release-jazzy-240617` (2024) [C-W7-052]. OneMind should **integrate it as a Market app**, not build fleet management on it, until its Lyrical support is shown.
- **Robot data:** record in MCAP (MIT-licensed, active in November 2026 [C-W7-059]) and sync selected streams over NATS JetStream through the robot gateway.

### 11.4 AI control of robots: Anthropic MHS

- **Status:** a research preview since **2026-08-27**. MHS has standardized drivers with read/write primitives, a device reference file that includes **"what safety limits will be enforced"**, and access through MCP, a CLI or code. Hugging Face (LeRobot) and Raspberry Pi are early adopters. There is **no public spec**, and open-sourcing has no date [C-W7-047].
- **W7-R12:** design OneMind's **device-adapter plugin type** (W19 type 4) in the same shape: a capability description, read/write primitives, declared safety limits enforced by the adapter (not by the model), and MCP exposure through the capability gateway. When MHS publishes a spec, OneMind adds an MHS driver host instead of rewriting adapters. Don't depend on MHS before the spec exists (matches `context/03` AINP). *Serves AI-2, N-10, AI-5, F-3, F-5.*
- **First demo target (P1):** a LeRobot SO-101-class arm (LeRobot is Apache-2.0, v0.7.0 [C-W7-051]) on a Pi 5 or an Orin Nano, driven through an MHS-shaped adapter, with the safety limits held by the adapter and the arm's MCU.

### 11.5 Non-NVIDIA accelerators (lock-in guard)

| Option | 2026 evidence | 10-year fit |
|---|---|---|
| Rockchip RK3588 NPU | **`drivers/accel/rocket` is in mainline from v6.18** [C-W7-049]; the vendor toolkit rknn-toolkit2 v2.5.0 is active [C-W7-053] | Good, and improving: a mainline driver means no vendor-BSP lock. Watch export rules (Q77). |
| Hailo (Pi AI HAT+ class) | HailoRT v5.5.0, Oct 2026 [C-W7-053] | Good for Pi-tier vision. Out-of-tree driver. |
| Google Coral Edge TPU | **The `edgetpu` repo is archived (last push 2021)** [C-W7-050] | **Avoid** for new SKUs |
| Qualcomm (QRB5165 / QCS6490) | VOXL 2 is still on Ubuntu 18.04 / 4.19 [C-W7-041] | Risky. Support only via vendor containers, not as an OS flavor. |

- **W7-R13:** apps declare accelerator needs through the capability model (`research/platform/robotics-iot-xr-nvidia.md` §5), and models ship as ONNX plus per-backend engines. No app may hard-require CUDA unless it is an NVIDIA-only app marked as such. *Serves N-3, F-2 (hardware-agnostic), N-8.*

---

## 12. Physical AI 2026–2036: the outlook and keeping pace with NVIDIA (P1)

### 12.1 What NVIDIA has actually shipped (dated, primary)

| Date | Release | Why it matters to OneMind | Claim |
|---|---|---|---|
| 2025-08 | Jetson Linux 38.2 (JetPack 7.0), Thor only | New silicon gets the new stack first | [C-W7-006] |
| 2026-04-18 | GR00T N1.7 (code Apache-2.0) | Open VLA model you can run on Jetson AGX Orin/Thor (per ROBO) | [C-W7-051] |
| 2026-06-01 | Cosmos 3 (repo license NOASSERTION, so check the model license) | World models; the Edge variant targets Jetson | [C-W7-051] |
| 2026-06-02 | JetPack 7.2 / r39.2: Orin joins JetPack 7; official Yocto via OE4T; RT kernel | One stack across Orin and Thor | [C-W7-007] [C-W7-008] |
| 2026-07-15 | Jetson T3000/T2000 announced, shipping Q1 2027; IGX T3000 with functional safety | Mainstream Thor price/power points; a safety-certified variant | [C-W7-048] |
| 2026-10 | Isaac Lab 3.0.0; Newton physics 1.7.0 (Apache-2.0) | The sim and training stack moves fast | [C-W7-051] |

### 12.2 "Keep pace on day one" (F-2): what is realistic

- **Day one, apps:** NVIDIA ships Isaac ROS, GR00T and Cosmos as containers and open repos. OneMind can list them in the Market **the day they ship**, if the Jetson flavor already runs the JetPack major they target. → keep the Jetson flavor on the **current JetPack major within 60 days** of NVIDIA's release (the C2 anchor 5 target is 30 days; 60 is the solo-developer realistic target, reviewed yearly).
- **New modules:** T3000/T2000 arrive in Q1 2027 on the same r39 line (T3000 emulation is already in 7.2.1) [C-W7-048]. A OneMind Jetson image built on r39 should boot them with a device-tree and flash-config addition, not a new flavor. **Test this when the dev kits ship.**
- **Lock-in guard:** the same app manifest runs on an RK3588 (mainline NPU), a Pi + Hailo, or an x86 GPU through the capability model (W7-R13).

### 12.3 2026–2036 trends and the trigger signals to watch

These are labelled **PROPOSAL** (scenario reasoning on the evidence above, not sourced forecasts).

| Horizon | Expected shift | Signal that it's happening | What OneMind does |
|---|---|---|---|
| 2027–2028 | VLA models run on-robot on Thor-class modules; T2000/T3000 bring them to mainstream robots | GR00T and Cosmos releases list T2000/T3000 as targets | Robot flavor on r39+; model store with per-device engines |
| 2027–2029 | ROS 2 Lyrical becomes the default; Jazzy ends in 2029 | Isaac ROS and Open-RMF Lyrical support | Ship Lyrical containers; keep Jazzy until May 2029 |
| 2028–2031 | Rust robot runtimes (dora-rs, copper-rs are active in 2026 [C-W7-053]) gain share at the edge | Vendors ship dora/copper nodes; ROS 2 interop bridges mature | Robot apps are containers, so new runtimes are just new Market apps |
| 2028–2032 | EU certification of AI-driven machines becomes normal | Harmonised standards under 2023/1230 published | The decision log (W7-R11) and an MCU safety split (W7-R6) are already in place |
| 2030–2036 | Orin EOL (2032); Thor through 2035–36; a Jetson successor arrives | NVIDIA lifecycle page changes; a new L4T major | One planned in-field branch upgrade per robot lifetime (§2.4) |
| Any time | NVIDIA changes its Jetson base OS (e.g. away from Ubuntu) | A Jetson Linux release notes a new rootfs | meta-tegra fallback (W7-R3) keeps OneMind independent of the rootfs choice |

---

## 13. Robotics track for `20-PLAN-180-DAYS.md` and `21-ROADMAP-5-10-YEARS.md` (P1 input)

| When | Robotics deliverable | Gate | Requirement IDs |
|---|---|---|---|
| Weeks 1–4 | Jetson Orin Nano flashed **A/B redundant**; k3s agent + NVIDIA device plugin; LAB-W7-4 rollback | Rollback works → proceed; bricks → NVIDIA-native-only update path for Jetson | M-7, R-1, D-002 |
| Weeks 5–8 | LAB-W7-1 (RT) on x86/Pi 5/Orin; LAB-W7-2 (container ROS) | Container ROS fails on Debian but works on Ubuntu → DC-15 flips for that tier | M-7, N-7, F-11 |
| Weeks 9–12 | `robot-runtime` namespace policy (W7-R9); robot gateway ROS ↔ NATS; decision log (W7-R11) | Security review by W6 | AI-5, AI-4, M-2 |
| Weeks 13–20 | First "connect a robot" demo: LeRobot SO-101-class arm via an MHS-shaped adapter; QR join (N-4) | A non-developer adds the arm in < 10 min | F-3, N-4, AI-2, N-10 |
| Weeks 21–26 | LAB-W7-3 (Isaac ROS on Debian x86 GPU); LAB-W7-6 (meta-tegra spike) | Decide x86 GPU tier base; decide whether meta-tegra stays the fallback | N-8, F-2, F-7 |
| Year 1 | Robotics edition beta on Orin; Market lists Isaac ROS, Open-RMF, LeRobot, MAVLink gateway | Exit: 3 third-party robots/devices onboarded by QR; 1 in-field JetPack upgrade done on a test fleet | M-7, F-4, F-5 |
| Years 2–3 | Thor T2000/T3000 support; drone companion profile (PX4); EU 2023/1230-ready logging | Exit: one OEM ships a robot "built on OneMind" | H-1, H-4, F-4 |
| Years 3–5 | Optional OneMind robot reference hardware; meta-tegra or core-image decision revisited | Exit: CRA support periods honoured on every shipped SKU | R-3, H-1 |
| Years 5–10 | Orin EOL migration (2032); the Jetson successor | Exit: no shipped robot stranded on an unsupported branch | F-1, R-3 |

**Capacity note:** a solo developer can do the weeks 1–12 items only if Jetson hardware is bought by week 1 (D-004). Without it, every Jetson row is `blocked: founder-hardware`. **Cut list if behind:** LAB-W7-6 and the drone profile move to year 2 first.

---

## 14. Recommendations and requirement trace

| ID | Recommendation | Requirement IDs | Owner workstream |
|---|---|---|---|
| W7-R1 | Bound each Jetson SKU's CRA support period by module availability and observed branch life + one planned in-field upgrade | R-3, H-1, M-7, F-2 | W7 → W6 |
| W7-R2 | Jetson flavor = NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+), image-based, containers on top | M-7, N-8, F-2, D-002 | W7 → W2 |
| W7-R3 | meta-tegra `wrynose` as the named fallback; spike in year 1 | R-3, F-7, H-1 | W7 → W2/W18 |
| W7-R4 | Flash every Jetson with the redundant (A/B) layout from day one | R-1, M-7 | W7 → W3 |
| W7-R5 | Real time is an image profile ("robot-rt"), not the default | M-7, F-7, F-11, P-8 | W7 → W18 |
| W7-R6 | Hard real time and safety on an MCU or safety controller, never Linux or AI | M-7, F-11, AI-5 | W7 |
| W7-R7 | The robot runs a k3s agent or a lighter node agent, never the k3s server | N-1, N-9, F-14 | W7 → W4 |
| W7-R8 | Publish pinned multi-arch ROS 2 (Jazzy, Lyrical) container images; Isaac ROS images for GPU | M-7, N-7, F-3, F-4 | W7 → W12 |
| W7-R9 | `robot-runtime` namespace class: signed apps only get hostIPC/hostNetwork/SYS_NICE | M-7, AI-5, F-5, M-2 | W7 → W6/W19 |
| W7-R10 | rmw_zenoh between robot and box; SHM inside the robot; one ROS ↔ NATS robot gateway | N-6, AI-7, AI-9, F-6 | W7 → W9 |
| W7-R11 | Robot decision log (append-only, ≥ 1 year) in the OS audit layer from phase 1 | AI-4, AI-5, M-7, R-3 | W7 → W6 |
| W7-R12 | MHS-shaped device-adapter plugin type; adopt MHS when its spec ships | AI-2, N-10, AI-5, F-3, F-5 | W7 → W9/W19 |
| W7-R13 | Accelerator needs declared through the capability model; ONNX + per-backend engines; avoid Coral | N-3, F-2, N-8 | W7 → W10 |

---

## 15. Corrections and contradictions found

| Item | Repo file says | Primary source says | Claim |
|---|---|---|---|
| EU Machinery Regulation application date | `context/05` Q63: "applies from 2027-01-20" | **14 January 2027** | [C-W7-045] |
| Kilted EOL | ROBO §2.1 and REP 2000: November 2026 | ROS 2 docs release table: **December 2026** (the two upstream sources disagree) | [C-W7-029] |
| `context/03` C-6 (which L4T line Orin uses under JetPack 7) | Unresolved | r38.x was Thor-only; **r39.2 (JetPack 7.2) adds Orin** | [C-W7-006] [C-W7-008] |
| ADR-001 §5 "Jetson A/B method" | Kairos vs NVIDIA's own vs RAUC | **RAUC and Rugix have no maintained Tegra layer.** SWUpdate (OE4T demo), Mender (JP5/6 layers) and NVIDIA native do. | [C-W7-017] [C-W7-018] [C-W7-019] |

These are recorded for the lead. W7 doesn't edit `docs/` or `context/`.

## 16. Open questions for Zeus (to `26-OPEN-QUESTIONS-FOR-ZEUS.md`)

1. **Will OneMind sell its own Jetson robot hardware in years 1–3, or only run on third-party Jetson devices?** Recommendation: third-party first. If you sell hardware, the meta-tegra fallback (W7-R3) becomes the default. *(blocked: founder-decision)*
2. **Is hard real time (motor control) a OneMind product promise, or only soft real time with an MCU doing safety?** Recommendation: soft real time on Linux, safety on an MCU (W7-R6). *(blocked: founder-decision)*
3. **When will the Orin Nano Super and Pi 5 be bought?** Every Jetson and RT test is `blocked: founder-hardware` until then. *(D-004)*
4. **Should OneMind ask NVIDIA (through Inception) for a written Jetson software-support statement?** It would turn FF-1 from observed history into a commitment. Draft on request in `evidence/outreach-drafts.md`.

---

## Glossary

- **A/B (redundant) layout:** two copies of the OS on disk. Updates go to the copy that isn't running, so a failed update falls back to the old copy. On Jetson, the bootloader also has A and B slots, paired with the OS slots.
- **BSP (board support package):** the vendor's kernel, drivers, firmware and flashing tools for a board. NVIDIA's is called **L4T / Jetson Linux**.
- **Capsule update:** the standard UEFI way to update firmware. On Jetson it writes the bootloader into the spare slot.
- **Companion computer:** the Linux computer on a drone that runs AI and networking, next to the flight controller that keeps the drone in the air.
- **cyclictest:** the standard tool for measuring how late a real-time Linux task wakes up (its latency).
- **DDS / Fast DDS / Cyclone DDS:** the default ROS 2 networking layers. They discover peers by multicast and can use shared memory on one machine.
- **Developer-Preview quality:** NVIDIA's label for features that aren't production-supported.
- **Device tree:** a file that tells the Linux kernel what hardware a board has.
- **JetPack:** NVIDIA's full Jetson software bundle (Jetson Linux + CUDA + TensorRT + more). JetPack 7.2 = Jetson Linux r39.2.
- **k3s agent vs server:** the server runs the Kubernetes brain (API and datastore); an agent only runs workloads it is told to run.
- **MCU (microcontroller):** a small, simple computer for reflexes, safety and motor drivers.
- **meta-tegra / OE4T:** the open-source Yocto layer for building Jetson images, now with NVIDIA-official recipes.
- **MHS (Model Hardware Standard):** Anthropic's research-preview standard for AI agents to operate physical devices with declared safety limits.
- **out-of-tree module:** a kernel driver kept outside the official Linux source, which must be rebuilt for each kernel.
- **Pod Security Standards (Baseline/Restricted):** Kubernetes' built-in rules that stop pods from getting dangerous host access.
- **PREEMPT_RT:** the Linux real-time option, buildable from mainline since 6.12, which bounds worst-case delays.
- **REP 2000 / Tier 1–3:** the ROS document listing supported platforms. Tier 1 is fully tested with binaries; Tier 3 is "reported to work", build it yourself.
- **rmw_zenoh / Zenoh router:** the Zenoh-based ROS 2 middleware. It uses a router for discovery instead of multicast, which suits VPNs and Wi-Fi better.
- **ros2_control:** the ROS 2 framework for real-time motor control loops.
- **SCHED_FIFO / SYS_NICE:** a Linux real-time scheduling policy, and the permission a process needs to use it.
- **Static CPU manager:** a Kubernetes setting that gives a pod whole CPU cores to itself.
- **uXRCE-DDS:** the link between PX4 flight firmware and ROS 2. It is unauthenticated, so it must stay on a private wire.
- **VLA (vision-language-action) model:** an AI model that sees, understands instructions and outputs robot actions (for example NVIDIA GR00T).
