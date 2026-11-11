# W18 adversarial check: P0-2 (non-Linux kernels), cost and solo-developer lens

- **Claim under test:** P0-2. No non-Linux kernel (seL4, Zircon/Fuchsia, HongMeng, Redox) is viable for OneMind in 5-10 years.
- **Refuter lens:** cost and how much one founder can run alone.
- **Date:** 2026-11-10.
- **Protocol:** RESEARCH-MISSION.md §2 rule 7. The refuter saw only the claim and its sources.
- **Verdict:** **weakened.** The decision to use Linux as the host kernel holds. The claim as written is too broad, and two of its four pieces of evidence point the wrong way or are out of date. Under rule 7, the author must respond in writing.

## 1. Strongest counter-argument

### A. The claim is too broad, and OneMind's drone plans already contradict it

"No non-Linux kernel is viable for OneMind" is false as written. Robotics and drones are the stated moat, and PX4 flight controllers run **Apache NuttX**, a non-Linux real-time OS (RTOS). Apache NuttX's own page says: "Every drone built using PX4 Autopilot runs Apache NuttX." [N1] That is a vendor claim with no audit behind it. PX4's README backs the general point: PX4 runs on NuttX, Linux and macOS.

NuttX is Apache-2.0, the same licence as OneMind, so a solo founder can afford it. It is free and upstream-maintained, and OneMind only needs to talk to it over MAVLink, not own it.

So every OneMind drone SKU will ship at least one non-Linux kernel. The correct claim is narrower: **Linux for the host/application kernel (k3s, containers, GPU, ROS 2). Microcontroller (MCU) and flight-controller real-time OSes (NuttX, Zephyr) are supported at the boundary, not owned.**

The claim also leaves out kernels that F-15 (REQUIREMENTS.md) explicitly asks about: Darwin/XNU and the BSDs. A reader cannot tell whether they were rejected or forgotten.

### B. The seL4 evidence is about verification scope, not cost, and partly cuts the other way

The cited verified-configurations page [S2] does say that "none of our verified configurations take into account address translation for devices (System MMU or IOMMU)". It also excludes "the kernel startup at boot".

But the same page lists **AARCH64 Raspberry Pi 4B and 5B** and x86-64 PC99 as verified configurations (re-read 2026-11-10). Pi 5 is OneMind's entry board. So "seL4 can't run on our hardware" is not the obstacle.

Gaps in formal verification do not make a kernel unusable. Linux has no verification at all, so this argument proves nothing *against* seL4 relative to Linux.

The real obstacle is cost, and the claim never states it. Running seL4 means:
- running Linux as a guest under an seL4 virtual machine monitor (VMM) for k3s, CUDA and ROS 2
- so maintaining two kernels, a VMM and a device pass-through story, and on Jetson there is no NVIDIA support path

A narrow use still survives: an **optional seL4 partition** for a safety or command-authority island on Robotics/Omni boxes, built by a funded partner (for example a seL4 Foundation endorsed service provider). This counts as "viable in 5-10 years" for a sub-component, not for the OS.

### C. The HongMeng evidence proves a microkernel *can* succeed commercially

The OSDI '24 abstract [S1] says HongMeng "has been deployed in production on tens of millions of devices" (routers, vehicles, smartphones), with "improved performance and security over their Linux counterparts". So the source shows a microkernel succeeding commercially.

What stops OneMind is cost, not the technology:
- HongMeng needed Linux API/ABI compatibility to reuse apps and drivers. That is a large engineering investment by Huawei.
- It is not available to OneMind as open source on Pi 5 or Jetson.

The claim's wording ("designed to be Linux compatible") implies weakness. The honest reading is: "a microkernel succeeded only by re-implementing the Linux ABI at Huawei scale. A solo founder cannot fund that."

### D. The Fuchsia source is from 2021 and the wording is shaky

The claim cites a 2021 TechSpot article about the first-gen Nest Hub. "Shipped commercially only on Nest Hub (secondary)" needs a current source. The better evidence is how Fuchsia's scope has shrunk:
- In January 2023, Google's layoffs cut at least 16% of the roughly 400-person Fuchsia team, later reported as more than 20% [N2].
- In July 2023, Fuchsia marked all speaker hardware "unsupported" and removed the code: Nest Mini, Nest Audio, Nest Wifi Point and a planned speaker [N3].

### E. The Redox evidence holds up and is stronger than the claim says

0.9.0 (2024-09-09) is still the latest release on the news page 26 months later [N4]. The May 2026 monthly report also says: "Our current spending is exceeding our monthly donations by quite a bit". The project is using donations from earlier years to pay for Summer of Code [N5].

Hardware support is also thin. The same report lists new compatibility results as "Broken" or "Booting", ARM64 boot fixes and Intel display mode-setting only. It mentions no Raspberry Pi or NVIDIA support.

## 2. What the cost and solo-founder lens adds (the argument the claim should have made)

| Kernel | Licence cost | Engineering cost to reach k3s + CUDA + ROS 2 | Who carries it | Solo-viable? |
|---|---|---|---|---|
| Linux | GPL-2.0, free | ~0 (upstream + vendor BSPs) | Upstream, NVIDIA, RPi | Yes |
| seL4 (+ Linux guest VMM) | GPL-2.0 kernel [S3], free | High: VMM, pass-through, two kernels, no Jetson path | OneMind or a paid integrator | No as the OS; maybe as a partner-built safety island |
| Zircon/Fuchsia | Open source, but Google-driven | Very high: no k3s, no CUDA, scope shrinking [N2][N3] | Nobody outside Google | No |
| HongMeng | Not available | n/a (closed) | Huawei | No |
| Redox | MIT, free | Very high: pre-1.0, underfunded [N4][N5] | Volunteers | No |
| NuttX (flight controller) | Apache-2.0, free | Low: use PX4 upstream, talk over MAVLink | PX4/Apache | **Yes, at the boundary** |

## 3. New sources (opened 2026-11-10, searched for failure and abandonment)

- [N1] Apache NuttX, "Market Share & Ecosystem": https://nuttx.apache.org/market-share (vendor-side claims, no citations)
- [N2] 9to5Google, Fuchsia / Area 120 layoffs (2023-01-21): https://9to5google.com/2023/01/21/fuchsia-area-120-google-layoffs/ (figures cross-checked in search summaries and OSNews, https://www.osnews.com/story/135778/googles-fuchsia-and-area-120-see-significant-cuts-in-layoffs/)
- [N3] 9to5Google, "Google abandons Assistant speakers on Fuchsia" (2023-07-25): https://9to5google.com/2023/07/25/google-abandons-assistant-speakers-fuchsia/
- [N4] Redox OS news index (latest release 0.9.0, 2024-09-09; posts up to 2026-11-08): https://www.redox-os.org/news/
- [N5] This Month in Redox, May 2026 (spending exceeds donations): https://www.redox-os.org/news/this-month-260531/

The claim's own sources were re-checked: [S1] the USENIX OSDI '24 HongMeng abstract and [S2] the seL4 verified configurations. [S3] (the seL4 LICENSE) and the TechSpot article were not re-opened.

I searched for a seL4 maintainer-funding shortfall and found none. The Foundation says membership fees fund maintenance, and DARPA's PROVERS programme still targets seL4 (sel4.systems/news). No abandonment evidence turned up for seL4, so the claim's seL4 argument rests only on technical scope.

## 4. What evidence would flip the decision

The Linux host-kernel decision would flip only if one non-Linux kernel showed **all** of the following, publicly, at zero licence cost:

1. **NVIDIA GPU/CUDA on Jetson Orin/Thor and discrete GPUs:** a vendor-supported driver on that kernel, not a VM pass-through hack.
2. **containerd + k3s (or a Kubernetes-conformant runtime)** running unmodified OCI images through a maintained Linux-ABI layer, as HongMeng does internally, but open and with Pi 5 + x86 + Jetson drivers. Example: OpenHarmony shipping the HongMeng ABI layer with those drivers.
3. **ROS 2 Tier 1 or Tier 2 support** on that kernel.
4. **A sustainable maintainer base** for the 10-year horizon. Examples: Redox 1.0 with income that covers its spending, or a seL4 vendor selling a maintained Linux-guest VMM product for Pi 5/Jetson with IOMMU covered.

Narrower changes that would amend the claim without flipping it:
- A funded partner offering a maintained seL4 safety partition for ARM64 boards. That would make an optional "seL4 command-authority island" a viable Robotics/Omni add-on.
- PX4 officially supporting Zephyr. That would add a second boundary RTOS and doesn't touch the host decision.

## 5. Required response from the author (weakened verdict)

1. Narrow the claim to the **host/application kernel**. Name NuttX/Zephyr as supported boundary RTOSes for flight controllers and MCUs.
2. Address Darwin/XNU and the BSDs (F-15) explicitly, or point to where they are decided.
3. Replace "seL4 verification excludes IOMMU/boot" as the reason for rejecting seL4 with the cost argument (two kernels, VMM, no Jetson path). Note that Pi 5 and x86-64 are verified configurations.
4. Reword HongMeng as "succeeded only by re-implementing the Linux ABI at vendor scale; closed; not available".
5. Replace the 2021 TechSpot Fuchsia source with [N2]/[N3], and add a 6-month re-check-by date (rule 10).
