# W7 — Refuter report: FF-2 (DC-08), technical lens

- **Claim under test (FF-2):** Mainline Linux cannot replace NVIDIA's Jetson kernel within the planning window. Orin and Thor device trees are upstream, but NVIDIA still ships out-of-tree modules and calls its own kernel "the most complete and best tested". Implication: the Jetson flavor stays on NVIDIA's BSP kernel (kernel route (c) in W18).
- **Cited claims:** C-W7-011, C-W7-012.
- **Refuter lens:** technical. Read only the conclusion and its sources (RESEARCH-MISSION.md §2 rule 7).
- **Date:** 2026-11-10

## Verdict: **upheld** (the core claim), with one gap in the implication

No source shows mainline Linux carrying a supported, CUDA-capable GPU stack for Orin or Thor. The mainline-replacement claim stands. The implication, "stays on NVIDIA's BSP kernel", leaves out two facts that change what "NVIDIA's kernel" costs to keep secure:

1. That kernel is **6.8**, which is not a kernel.org longterm kernel.
2. There is at least one **non-NVIDIA-maintained Jetson kernel** (Canonical's Tegra kernel for Ubuntu 22.04 on Orin), and on Thor the GPU driver is now the out-of-tree OpenRM stack shared with discrete GPUs.

Neither fact makes mainline viable, so the decision holds. Both should be recorded.

## Checks of the cited sources (opened 2026-11-10)

| Sub-claim | Source | Result |
|---|---|---|
| BYOK lists upstreamed Tegra patches v5.15 → v6.7; out-of-tree modules for drivers that "cannot be upstreamed"; NVIDIA source is "the most complete and best tested" (C-W7-011) | docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SD/Kernel/BringYourOwnKernel.html | **Confirmed.** Also: the page names **no tested or supported upstream kernel version**, warns that patches "might not apply cleanly", and says some patches land in NVIDIA's kernel before upstream. This strengthens FF-2: BYOK is a do-it-yourself path with no support commitment. |
| Mainline v6.18 has Orin (tegra234-p3701/p3737/p3767/p3768) and Thor (tegra264-p3834/p3971) device trees (C-W7-012) | github.com/torvalds/linux/tree/v6.18/arch/arm64/boot/dts/nvidia | Not re-opened in this pass. The claim is narrow and plausible. A device tree means the board boots, not that the GPU, codecs or camera work. It does not affect the verdict. |

## New sources (found by searching for lifecycle cuts, missing security maintenance and driver regressions; all opened)

- **N1. kernel.org releases** (https://www.kernel.org/category/releases.html). The longterm kernels are 6.18 and 6.12 (Dec 2028), 6.6 and 6.1 (Dec 2027), and 5.15 and 5.10 (**Dec 2026**). **6.8 is not longterm.** Jetson Linux r38/r39 ship kernel 6.8 (r39.2 release notes / JetPack downloads, per search; the r39.2.1 Thor guide was cited by the W18 refuter). The r36 (JetPack 6) Orin line is on 5.15, which reaches upstream EOL next month (SECONDARY, not opened here). NVIDIA's kernel therefore has **no upstream stable stream behind it**. Every kernel CVE fix depends on NVIDIA backporting it.
- **N2. Canonical, "Canonical brings Ubuntu and ROS to NVIDIA Jetson Orin"** (https://ubuntu.com/blog/ubuntu-and-ros-to-nvidia-jetson-orin, 2023-10-18). It states that under JetPack, kernel security updates were previously unavailable, commits to "regression testing and validating periodic updates to the kernel" including CVE patching, and promises "long-term support (LTS) and security patching on Ubuntu 22.04" for Orin, **without a number of years**. Search results also show the `linux-nvidia-tegra-jetson` kernel flavor (5.15-based, Ubuntu-certified on Orin NX/Nano/AGX). Those were not opened and are SECONDARY.
- **N3. NVIDIA forum, Jetson AGX Thor FAQ** (https://forums.developer.nvidia.com/t/jetson-agx-thor-faq/346561). "The low-level software stack is unified to dGPU driver(openrm)", and the release check reports `KERNEL_VARIANT: oot`. The Thor GPU driver is the out-of-tree OpenRM family, not upstream. This supports FF-2: a mainline kernel still needs NVIDIA's out-of-tree modules.

## Strongest counter-argument

"Mainline can't replace it" is true, but it frames the choice wrongly. The real choice is not "NVIDIA kernel vs mainline". It is **which maintained kernel carries NVIDIA's out-of-tree modules**:

- **(a)** NVIDIA's 6.8 kernel. It is not LTS, has no published security window (see FF-1), and gets fixes only at branch head.
- **(b)** Canonical's Tegra kernel. It is derived from NVIDIA's source, but Canonical has given a security-patching commitment, so a second party patches it (N2).
- **(c)** BYOK on a kernel.org LTS (6.12/6.18) with NVIDIA's out-of-tree modules. NVIDIA does not support this (C-W7-011), but on Thor it is technically more plausible than on Orin, because the GPU is now OpenRM-shaped (N3). OpenRM is the driver family that builds out of tree against many kernel versions on discrete GPUs.

Option (b) is a credible alternative to "NVIDIA's BSP kernel" that FF-2's implication ignores. Its weaknesses: it is tied to the Ubuntu 22.04 + 5.15 era, it has no published year count, it covers Orin only, and it lags NVIDIA's releases. It does not overturn FF-2, but the decision record should say option (b) was considered and why it was rejected. The planning window (to 2035/2036 for Thor) is also long enough that "can't within the planning window" is a forecast, not a finding. It should be stated as "not now, and no announced path".

## Required corrections

- Restate FF-2 as: "No mainline or LTS kernel has NVIDIA-supported GPU/CUDA/multimedia on Orin or Thor today, and NVIDIA has announced no path to one. The Jetson flavor uses NVIDIA's BSP kernel (6.8, not LTS), with Canonical's Tegra kernel as the evaluated alternative."
- Add to the risk register: the BSP kernel is not LTS, so OneMind's CVE exposure on Jetson depends entirely on NVIDIA's backports at branch head (ties to FF-1).

## What evidence would flip the decision

- **Toward refuted (mainline/LTS becomes viable):** NVIDIA's BYOK page naming a **tested and supported** kernel.org LTS version for Orin or Thor, or NVIDIA stating that OpenRM on Thor is supported on upstream LTS kernels. Either one would make route "LTS kernel plus NVIDIA's out-of-tree modules" a supported option and remove the NVIDIA-kernel dependency.
- **Toward a different implication (not mainline, but not NVIDIA's kernel either):** Canonical publishing a numbered security-support window (for example 10 years with Ubuntu Pro) for a Jetson Orin/Thor kernel that tracks current JetPack releases.
- **Strengthening FF-2:** an r39-era NVIDIA statement that out-of-tree modules are built and tested only against the 6.8 Tegra kernel.
