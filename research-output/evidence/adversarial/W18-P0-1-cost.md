# W18 P0-1 refuter: cost and solo-developer operability

| Field | Value |
|---|---|
| Claim | P0-1: Linux is the only kernel family that passes OneMind's gates. |
| Lens | Cost and solo-developer operability |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter saw only the claim and its sources. |
| Date | 2026-11-10 (re-check by 2027-05-10: kernel, BSP and Kubernetes facts) |
| Verdict | **weakened**. The conclusion stands, but one premise is false and one is worded in a way that misleads. A written response is required. |

## 1. Re-checking the cited sources

| Sub-claim | What the source says (opened 2026-11-10) | Holds? |
|---|---|---|
| The Kubernetes control plane runs only on Linux. Workers can be Linux or Windows. | "While you can only run the control plane on Linux, you can deploy worker nodes running either Windows or Linux." Windows workers must run Windows Server 2022 or 2025. (kubernetes.io/docs/concepts/windows/intro/) | Yes |
| "CUDA 13.5 covers only Linux distributions" | The cited page is the **Linux** install guide, so it cannot show that CUDA is Linux-only. NVIDIA's **Windows** guide for CUDA 13.5 lists Windows 10 22H2, Windows 11 22H2 to 25H2, and Windows Server 2022/2025 (docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/). | **No, as worded** |
| CUDA 13.5 includes Debian 13 and Jetson | Debian 12 and 13 are listed for x86_64 and arm64-SBSA. Debian 12 is deprecated in 13.5. The **only** Jetson entry is Ubuntu 24.04, "Rel39 (JP7.2)". Cross-development for Jetson is supported only on Ubuntu 24.04. Orin and Thor use separate APT repos (`jetson-nvgpu` and `jetson-openrm`) and need extra `cuda-compat` packages. | Partly. "incl. Debian 13 and Jetson" suggests Debian 13 runs on Jetson. It does not. |
| NVIDIA's FreeBSD driver is x64-only | The driver archive lists FreeBSD x64 and FreeBSD x86 (legacy). There is no FreeBSD aarch64 build. Linux aarch64 exists. (nvidia.com/en-us/drivers/unix/) | Yes |
| REP 2000 Kilted: Tier 1 Ubuntu and Windows, macOS Tier 3 amd64 only, no BSD | Tier 1: Ubuntu 24.04 (amd64, arm64) and Windows 10 (amd64). Tier 2: RHEL 9. Tier 3: macOS amd64, **Debian 12**, Yocto, and Ubuntu arm32. No BSD. | Yes. The claim leaves out that Debian is Tier 3 only. |
| TrueNAS CORE 13.3 plans | iXsystems, 2024-03-20: CORE "is now entering a sustaining engineering phase". New features go to the Linux-based SCALE because open-source software is "built for Linux first". | Supports the claim that BSD carries cost |

## 2. Strongest counter-argument (cost and solo-operability lens)

**A. One premise is false: Windows passes the CUDA gate and the ROS 2 Tier 1 gate.** Windows is not ruled out by CUDA or ROS 2. CUDA 13.5 supports Windows, and REP 2000 lists Windows 10 as Tier 1. Windows is ruled out because:

- the Kubernetes control plane runs only on Linux;
- Windows Kubernetes workers must be Windows Server, which costs a licence per box;
- Windows is not offered on Pi 5 or Jetson.

The claim cites none of these reasons for Windows. Its conclusion is right, but the evidence chain is wrong. If the final report says "CUDA is Linux-only", any reader can disprove that with NVIDIA's own Windows guide.

**B. "Linux passes" is not the same as "one Linux". The claim hides the real cost.** The gates are passed by three different Linux stacks, each with its own vendor:

1. Mainline or distro kernel on x86. Debian 13 works here.
2. The Raspberry Pi kernel on Pi 5.
3. Jetson Linux r39 / JetPack 7.2. CUDA on Jetson is supported on **Ubuntu 24.04 only**, using NVIDIA's 6.8-based kernel.

The Jetson stack has already split in two:

- Orin uses `nvgpu` with `cuda-compat-orin`.
- Thor uses OpenRM / SBSA.

NVIDIA staff on the developer forum (2026-03-09 to 2026-04-07) said "There will be two separable drivers in JetPack 7.2". They also warned that newer CUDA on Orin may need newer drivers "or not behavior as expected". A secondary write-up quotes NVIDIA: "The only exception is Orin (sm_87), which will continue on its current path for now."

For a solo founder, this means at least two base distros (Debian and Ubuntu 24.04 for Jetson) and three kernel lines, all under one product. Choosing the kernel family is cheap. Keeping these BSP lines patched is where the cost is.

**C. Linux has a large, ongoing security-maintenance cost.** The Linux kernel became its own CVE Numbering Authority (CNA) in February 2024. Since then it issues a CVE for nearly every stable fix:

- 3,529 kernel CVEs in 2024, against 290 in 2023 (TuxCare, 2025-01-28).
- About 5,600 in 2025, roughly 8 to 9 a day (several trackers; the counts differ by method).

Vendor BSP kernels (Raspberry Pi, L4T) carry out-of-tree patches that the CNA does not track. Once a long-term (LTS) kernel branch reaches end of life, the device maker has to track fixes. Under the EU Cyber Resilience Act (CRA), that device maker is OneMind. A solo founder cannot triage CVEs one by one, so the Linux choice brings a hidden requirement: continuous, automatic, image-based kernel updates on every board line. The claim presents Linux as having passed the gates, but this cost should be written down next to it.

**D. Gate design bias (minor).** Two of the gates (a Kubernetes control plane, and a k3s-based app platform) are OneMind's own architecture choices, not outside requirements. A FreeBSD route with jails and Podman would fail them by construction. That is fair given F-14 and the 10-year ecosystem bet. But the report should say the gate is self-imposed, and note that the BSD container work is real:

- The FreeBSD Foundation reports OCI containers through Podman on 14.3 and 15.0 (2025-10-31).
- That work was led by one volunteer, which is itself a bus-factor warning.

**What this does not overturn:** None of the counter-evidence makes a non-Linux family pass all the gates:

- FreeBSD has no arm64 NVIDIA driver, no CUDA, and no ROS 2 tier. Its main appliance user (TrueNAS) moved new development to Linux.
- macOS is ROS 2 Tier 3 on amd64 only, and is not an edge OS.
- Windows fails the control-plane gate and the edge-hardware gate.

The decision stands. The rationale and the cost accounting need fixing.

## 3. New sources (found by searching for failure, fragmentation and burden; all opened)

1. NVIDIA, *CUDA Installation Guide for Microsoft Windows*, v13.5. https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/index.html. Shows that the premise "CUDA covers only Linux" is false.
2. NVIDIA Developer Forums, "Will Jetson Orin Nano and all Orin devices get CUDA 13 support one day?" (staff posts 2026-03-09 to 2026-04-07). https://forums.developer.nvidia.com/t/will-jetson-orin-nano-and-all-orin-devices-get-cuda-13-support-one-day/362755. Shows the two-driver split in JetPack 7.2 and staff caveats about running CUDA 13 on Orin.
3. SMF Clearinghouse, "JetPack 7 split the Jetson family" (2026-09-14, secondary; it cites NVIDIA blogs). https://www.smfclearinghouse.com/blog/2026-09-14-jetpack-7-split-the-jetson-family/. Covers Orin staying on its own sm_87 path, and Isaac ROS listed as "coming soon" for JetPack 7.2.1.
4. TuxCare, "The Linux Kernel CVE Flood Continues Unabated in 2025" (2025-01-28; vendor source, so the numbers should be cross-checked). https://tuxcare.com/blog/the-linux-kernel-cve-flood-continues-unabated-in-2025/. Gives 3,529 kernel CVEs in 2024 and 8 to 9 a day in early 2025.
5. FreeBSD Foundation, "OCI Containers on FreeBSD" (2025-10-31). https://freebsdfoundation.org/blog/oci-containers-on-freebsd/. Podman runs on 14.3 and 15.0 but needs root, and the post does not mention Kubernetes. The best case for BSD is still missing the gate.

Also searched but not opened (403): linuxcvetracker.com 2025 statistics (5,681 CVEs). Treat that figure as unverified.

## 4. What would flip the decision

These would refute the conclusion, which is "choose a non-Linux kernel family":

- NVIDIA ships a FreeBSD aarch64 driver **and** CUDA for FreeBSD, **and** REP 2000 adds a BSD at Tier 2 or better for the release after Kilted.
- Kubernetes (or k3s) supports a non-Linux control plane: an upstream FreeBSD port of kubelet, kube-proxy and CRI that passes conformance.
- Windows IoT or Windows Server becomes supported on Pi 5 and Jetson, **and** OneMind drops Kubernetes as a gate. This is very unlikely.

These would turn the verdict into **upheld** without changing the decision:

- P0-1 drops "CUDA covers only Linux". It says instead that Windows passes the CUDA and ROS 2 gates and fails on the control plane, Windows Server licensing for workers, and the lack of Pi 5 and Jetson support.
- P0-1 separates "Debian 13 (x86_64 and SBSA)" from "Jetson (Ubuntu 24.04 only, JP7.2)", and notes that ROS 2 Kilted has Debian at Tier 3 only.
- The ADR records the kernel-line count (mainline, Raspberry Pi, L4T Orin, L4T Thor), the CVE and CRA maintenance cost, and the plan for automatic image-based kernel updates on each line.

These would turn the cost counter into a block:

- Evidence that one solo maintainer cannot keep a Debian base and an Ubuntu-based Jetson base on a shared update framework. For example, Rugix or RAUC has no maintained Jetson r39 integration, or NVIDIA ends Orin support before 2030.

## 5. Required response from the author (weakened, so rule 7 applies)

Fix premises A and B in the claims ledger. Then add a line to ADR-001 on the cost of running three or more kernel lines, with the CVE and CRA burden.
