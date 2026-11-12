# Refuter report: P0-2 (kernel family), technical lens

- **Refuter lens:** technical (drivers, NVIDIA/Jetson, containers/k3s, robotics, IoT; requirements F-7, F-15, F-1, F-2, F-11, N-8, D-002)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (kernel facts: 6 months)
- **Verdict:** **weakened.** The decision holds: Linux is the host kernel for every OneMind node class that runs the OS and k3s. But the claim as worded ("no non-Linux kernel is viable") is too broad. Two of its four reasons don't support the conclusion, and one fact is slightly off.

## Claim under test

> No non-Linux kernel (seL4, Zircon/Fuchsia, HongMeng, Redox) is viable for OneMind in 5-10 years: Huawei's production HongMeng microkernel was designed to be Linux API/ABI compatible to reuse Linux apps and drivers; seL4's verification excludes IOMMU/SMMU and boot and covers specific configurations; Redox's latest release is 0.9.0; Fuchsia shipped commercially only on Nest Hub (secondary).

## What the cited sources confirm (re-opened 2026-11-10)

| Item | Source | Status |
|---|---|---|
| HongMeng is designed "to be compatible with the Linux API and ABI to reuse its rich applications and driver ecosystems" and is "deployed in production on tens of millions of devices" | USENIX OSDI '24 abstract (Chen et al.) | Confirmed. The abstract is silent on licensing; it calls HM "a commercialized general-purpose microkernel". |
| seL4 verification excludes "address translation for devices (System MMU or IOMMU)" and "the kernel startup at boot"; proofs cover specific configurations; X64 has C-level functional correctness only ("no VT-x mode"); MCS proofs are still in progress | seL4 verified-configurations page | Confirmed. The list includes Raspberry Pi 5B for AARCH64 (functional correctness, integrity, confidentiality). |
| seL4 kernel code is GPLv2 with a syscall note; user-level code is BSD-2 | `seL4/seL4@c98d70ad:LICENSE.md` | Confirmed (compatible with an Apache-2.0 userspace) |
| Redox latest release is 0.9.0 | `redox-os/redox@674d255f:README.md`; `gh api repos/redox-os/redox/releases` and tags | Confirmed: no tag after 0.9.0. The README pin doesn't state a version at L15. The release was announced 9 Sep 2024 (redox-os.org/news), but the GitHub release object is dated 2025-09-22. Cite the news post for the date. |
| Fuchsia shipped commercially only on Nest Hub | TechSpot 89814 | **UNVERIFIED (blocked):** HTTP 403 when fetched. Wikipedia (SECONDARY) says the Nest Hub (1st gen) rollout ran May to Aug 2021, and the **Nest Hub (2nd gen)** got a Fuchsia update in May 2023. Correct the wording to "the Nest Hub smart-display family". |

## Strongest counter-argument

1. **The claim is over-scoped. Non-Linux kernels are already viable, and needed, inside OneMind's own scope.** F-15 frames this as the host kernel family, but the claim is written as "no non-Linux kernel is viable for OneMind". That is false for three node classes OneMind commits to (F-1, F-11, D-002 robotics and drones):
   - **Drones:** PX4 docs say "NuttX is the primary RTOS for running PX4 on a flight-control board." Every PX4 drone OneMind supports runs a non-Linux kernel on the flight controller.
   - **IIoT/IoT microcontrollers:** F-11 itself names the "control (PLC/RTOS/Zephyr) vs supervision (Linux) split". Zephyr, FreeRTOS and ESP-IDF nodes are non-Linux kernels that OneMind must onboard, update and expose to AI.
   - **Safety robotics on NVIDIA:** QNX (a commercial microkernel) has an NVIDIA-partnered path. QNX OS for Safety 8.0 is integrated with **NVIDIA IGX Thor** and the Halos safety stack, and it targets "autonomous mobile robots (AMRs) and humanoids". Early access is gated. So "only Linux runs on NVIDIA robot silicon" is not quite true for the safety partition, although on **Jetson** L4T Linux is still the only NVIDIA-supported OS (SECONDARY forum evidence).

   The accurate decision is: **Linux is the only viable *host/supervisor* kernel. OneMind must still treat RTOS and microkernel *peer* nodes (NuttX, Zephyr, QNX safety partitions) as first-class managed devices.** Without that sentence, the decision can be misread as "OneMind ignores non-Linux nodes", which would break F-11 and drone support.

2. **The HongMeng reason argues against the conclusion, not for it.** The OSDI paper is evidence that a microkernel *can* reach Linux API/ABI and driver compatibility at production scale (tens of millions of devices). Technically, that shows viability. The real blockers aren't technical. HM is proprietary and Huawei-internal: the abstract states no license, and Promon's HarmonyOS NEXT analysis (SECONDARY) says the kernel binary isn't even accessible. OneMind cannot obtain, license, ship or audit it under an Apache-2.0 open core (D-001), and export-control and vendor-risk issues apply. The reason should read "not available or licensable to OneMind", not "Linux compatibility proves Linux wins". From the technical lens, HongMeng shows that a Linux-ABI microkernel is a credible *10-year* trend. That is a re-check item, not a closed door.

3. **The seL4 reason is the wrong test.** "Verification excludes IOMMU/SMMU and boot" is not a viability argument: Linux has no formal verification at all, and unverified seL4 configurations still run. The real technical blockers for seL4 as OneMind's host are:
   - **No driver ecosystem:** there is no NVIDIA GPU, CUDA, Jetson camera, Wi-Fi or NVMe stack at Linux parity. Trustworthy Systems lists "driver VMs" (running Linux drivers inside a Linux VM on seL4) as **current work**, not a finished feature (virtualisation project page).
   - **No container runtime or k3s:** OneMind's app platform (P-9, k3s) needs Linux namespaces and cgroups.

   seL4 does have a credible *hybrid* role: as a separation kernel under Linux guests (libvmm 0.1.0 Mar 2025, 0.2.0 Aug 2026, AArch64 and x86-64), and the verified list now includes **Raspberry Pi 5B**. "Not viable" is too strong for a future high-assurance Robotics or public-safety edition (Linux VM on seL4). "Not viable as the base in 5-10 years for a solo founder" is defensible.

4. **The Redox reason is weak but its direction is correct.** A version number alone says little. The better evidence: no release in about 26 months (0.9.0 on 9 Sep 2024, none newer as of 8 Nov 2026), funding through small grants (NLnet, Radworks) and donations "to support one or more full-time developers", and current work that is still basic (an EEVDF scheduler in RSoC 2026, virtio-fs and Cloud Hypervisor support in Nov 2026). The project is active, not abandoned, but it is far from Jetson or k3s parity.

5. **Fuchsia: the fact is slightly wrong and the trend is worse than stated.** It shipped on more than one Nest Hub (1st gen 2021, 2nd gen 2023). The stronger evidence is abandonment. The January 2023 layoffs cut about 16% (later "upwards of 20%") of the roughly 400-person Fuchsia team. In July 2023 Google "formally marked all of its speaker hardware as 'unsupported' and altogether removed the related code" (9to5Google). A kernel whose only owner withdrew from its own planned device lines is not a 10-year base for anyone else.

## New sources (opened 2026-11-10; found by searching for failure, abandonment and lifecycle cuts)

1. **9to5Google, "Google abandons work to move Assistant smart speakers to Fuchsia"** (K. Bradshaw, 25 Jul 2023): https://9to5google.com/2023/07/25/google-abandons-assistant-speakers-fuchsia/ . Covers the 16-20% team layoffs and the speaker hardware marked unsupported with its code removed. (Abandonment, SECONDARY.)
2. **iTnews, "UNSW gives dumped Data61 seL4 research group funding lifeline"** (31 May 2021): https://www.itnews.com.au/news/unsw-gives-dumped-data61-sel4-research-group-funding-lifeline-565274 . CSIRO will "no longer maintain" the Trustworthy Systems group, a "zero notice" dismantling; "We lost more than half of the team over the last 12 months"; UNSW gave a six-month bridge. (Lifecycle cut and maintainer risk, SECONDARY.)
3. **Redox OS news index** (latest post 8 Nov 2026; no release after 0.9.0, 9 Sep 2024): https://www.redox-os.org/news/ , plus `gh api repos/redox-os/redox/tags` (latest tag `0.9.0`). (Release stall; PRIMARY.)
4. **Trustworthy Systems, seL4 virtualisation project** (libvmm 0.2.0, 19 Aug 2026; driver VMs listed as current work): https://www.trustworthy.systems/projects/virtualisation/ . (Maturity gap; PRIMARY.)
5. **PX4 architecture docs**: https://docs.px4.io/main/en/concept/architecture.html . "NuttX is the primary RTOS for running PX4 on a flight-control board." (Counter-evidence to the claim's scope; PRIMARY.)
6. **QNX, "Powering Safety-Critical Edge AI with QNX and NVIDIA"** (2026, undated page): https://qnx.software/en/blog/2026/the-qnx-and-nvidia-foundation . QNX OS for Safety 8.0 on IGX Thor and DRIVE AGX Thor, for AMRs and humanoids; early access gated. (Counter-evidence on scope; vendor PRIMARY.)
7. Promon, "A first look at app security on HarmonyOS NEXT": https://promon.io/security-news/harmonyos-next . The HongMeng kernel is closed and its binary inaccessible. (SECONDARY, seen in search results and not opened in full; treat as UNVERIFIED.)

## Suggested rewrite of the claim

> Linux is the only viable **host kernel** for OneMind OS nodes (x86, Pi 5, Jetson, GPU) for 5-10 years. Its rivals fail on **drivers** (NVIDIA supports only L4T Linux on Jetson; seL4 driver VMs are still in development), **containers/k3s** (namespaces and cgroups), **availability and licensing** (HongMeng is proprietary to Huawei, even though it proves a Linux-ABI microkernel is technically possible), and **sponsor commitment** (Fuchsia layoffs and dropped devices; Redox has had no release since Sep 2024 and runs on grants). OneMind still manages non-Linux **peer** kernels as first-class devices: NuttX (PX4), Zephyr/FreeRTOS (IIoT/MCU), and QNX safety partitions on NVIDIA IGX/DRIVE Thor. seL4-as-hypervisor stays a watch item for a high-assurance edition.

## What evidence would flip the decision

- **To refuted, for the host kernel:** NVIDIA ships a supported Jetson/IGX BSP with CUDA on a non-Linux kernel *that OneMind can redistribute* (for example QNX on Jetson, with terms compatible with an open-core edition). Or seL4 or another microkernel ships production driver VMs that reuse Linux NVIDIA, NVMe, Wi-Fi and camera drivers on Pi 5 and Jetson, with a k3s-compatible container runtime (for example via a Linux guest), and a named production adopter.
- **To refuted, for HongMeng:** Huawei open-sources the HongMeng kernel under an OSI license, through OpenHarmony or otherwise, with Linux-ABI compatibility and a Pi 5 or x86 port.
- **To upheld without qualification:** the claim is narrowed to the *host* kernel and adds the peer-node carve-out (NuttX, Zephyr, QNX), and the Fuchsia wording is fixed to "Nest Hub family" with a primary source.
- **Re-check triggers (2027-05):** Redox 0.10 or later released, the seL4 driver-VM work released, QNX on Jetson Thor, Fuchsia device additions or removal.
