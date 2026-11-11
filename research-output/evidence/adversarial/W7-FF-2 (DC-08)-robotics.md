# W7 refuter: FF-2 (DC-08), robotics-fit lens

- **Claim under test:** Mainline Linux cannot replace NVIDIA's Jetson kernel within the planning window. Mainline v6.18 has Orin (tegra234) and Thor (tegra264) device trees, but NVIDIA still ships out-of-tree modules for drivers that "cannot be upstreamed or that have not yet been upstreamed", and calls its kernel "the most complete and best tested".
- **Refuter lens:** robotics fit (cameras, GPU/CUDA, video, real-time, long-lived fielded robots)
- **Date:** 2026-11-10. Protocol: RESEARCH-MISSION.md §2 rule 7.
- **Verdict:** **WEAKENED.** The literal near-term statement holds, but the decision it implies ("so OneMind ships NVIDIA's kernel on Jetson") does not follow.

## 1. Re-check of the cited sources (opened 2026-11-10)

| Source | What it actually says | Status |
|---|---|---|
| torvalds/linux v6.18 `arch/arm64/boot/dts/nvidia` | It has 13 tegra234 files (p3701/p3737 AGX Orin, p3767/p3768 Orin NX/Nano, p3740) and 7 tegra264 files (p3834/p3971, Thor). | PRIMARY, confirmed |
| NVIDIA r39.2.1 "Bring Your Own Kernel" | It says the NVIDIA kernel source "is considered to be the most complete and best tested source code for Tegra devices". It mentions "a set of out-of-tree modules for drivers that cannot be upstreamed". Its upstream patch list starts at v5.15, with patches tagged up to v6.7. It does **not** list the features that an upstream kernel loses. | PRIMARY, confirmed. The claim quotes "or that have not yet been upstreamed", but the opened page text did not show that wording, so treat it as UNVERIFIED wording. |

Note: the BYOK page exists to let users **bring their own kernel**. NVIDIA supports a non-NVIDIA kernel combined with its out-of-tree (OOT) modules. That cuts against the claim's framing.

## 2. Strongest counter-argument

**The claim sets up a false choice: "mainline alone" versus "NVIDIA's kernel". The real third option is a OneMind-owned LTS kernel plus NVIDIA's OOT modules, and the evidence says it works today.**

1. **A mainline LTS kernel with OOT modules already runs CUDA on Orin.** In siderolabs/pkgs PR #1518 (open, approved by a maintainer on 2026-11-02), Talos Linux builds NVIDIA's OE4T OOT stack against the Talos kernel, which is built from mainline. That stack is host1x, nvmap, tegra-drm, nvgpu and others. The author verified CUDA on Orin NX 16GB on 6.18 and 7.3, and a second user verified it on AGX Orin 64GB. A strict, immutable, Kubernetes-only OS (the closest analogue to OneMind's k3s design) therefore gets GPU compute on Jetson with no L4T kernel. This is what F-7 ("own the kernel") and the one-pipeline-many-profiles rule in DECISIONS.md need.
2. **NVIDIA's kernel is the weaker base for a 10-year robot.** Per NVIDIA's own docs and a secondary BSP summary, Jetson Linux r39.x (JetPack 7) tracks **Linux 6.8**. kernel.org lists 6.8 nowhere among its longterm kernels: today those are 6.18 and 6.12 to Dec 2028, 6.6 and 6.1 to Dec 2027, and 5.15 and 5.10 to Dec 2026. So the vendor kernel gets no upstream stable fixes, and every CVE fix depends on NVIDIA backporting it. Mainline 6.18 is an LTS kernel.
3. **NVIDIA cuts its kernels off on a schedule shorter than a robot's service life.** NVIDIA announced on 2026-10-30 that JetPack 5.1.8 (kernel 5.10) is the final JetPack 5 release. Users "will no longer receive any critical updates", and NVIDIA points them to a paid partner (RidgeRun). JetPack 4 went the same way earlier. Orin modules are sold until 2032-01 (SECONDARY), so a fielded Orin robot will outlive at least one more vendor kernel line. "Best tested" therefore expires.
4. **The mainline gap is closing, partly through NVIDIA's own engineers.** On the linux-tegra list (thread from Jul 2025 to Oct 2026), the NVDEC and T234 VIC drivers had been upstream for about 3 years without firmware. On 2026-10-13 an NVIDIA engineer reported that firmware for VIC, NVDEC, NVENC, NVJPG, OFA and XUSB is now in linux-firmware, and said he is looking at GA10B (the Orin GPU) support. NVJPG and Tegra264 VIC drivers were merged or reached -next in 2026. Over a 10-year horizon, "cannot replace within the planning window" is a forecast, not a fact.

## 3. Where the counter-argument fails (why this is not a refutation)

The robotics blocks that matter are still vendor-only, and the counter-evidence itself shows how fragile they are.

- **Cameras and the GPU are the robotics-critical gap.** Per a SECONDARY BSP guide, CUDA/cuDNN/TensorRT, the DLA, the ISP/VI cameras (libargus, nvarguscamerasrc) and the NVDEC/NVENC user API exist only on L4T. The linux-tegra thread confirms there is no GA10B GPU driver upstream. nouveau has no GA10B support, and nova is judged a poor fit. A Jetson robot with CSI cameras and CUDA perception cannot run on mainline alone.
- **OOT on mainline is fragile.** In the same Talos PR, LLM token generation fell from about 70 to about 10 tok/s when moving from kernel 6.18 to 7.3. The suspected cause is an SMCCC change in 7.2 that makes nvgpu treat the Orin as a simulator and skip clock setup; this is unconfirmed. The PR also needed patches and a Clang conftest fix, the OE4T maintainers made no upstream commitment, and the GA10B firmware is under the NVIDIA Driver License and not in linux-firmware. A solo founder would carry this breakage on every kernel bump.
- **Firmware in linux-firmware is not a working stack.** The media firmware landed only in Oct 2026, and the GPU still has no driver.

## 4. New sources (found by looking for failures, cutoffs and regressions)

| # | Source | Kind | What it shows |
|---|---|---|---|
| N1 | https://forums.developer.nvidia.com/t/announcing-end-of-life-for-nvidia-jetpack-5-with-the-release-of-jetpack-5-1-8/387446 | PRIMARY (NVIDIA announcement) | Lifecycle cut: the JetPack 5 kernel line is EOL, with no further critical updates and paid partner support only. |
| N2 | https://www.kernel.org/category/releases.html | PRIMARY | 6.8 (the r39 vendor base) is not LTS. 6.18 is LTS to Dec 2028. |
| N3 | https://github.com/siderolabs/pkgs/pull/1518 | PRIMARY (source/PR) | Mainline LTS plus OE4T OOT runs CUDA on Orin. It also shows a 7x performance regression on 7.3 and the firmware licensing gap. |
| N4 | https://ratatoskr.run/linux-tegra/2025/07/14555496/t | PRIMARY (mailing-list archive mirror) | Upstream drivers sat for about 3 years without firmware ("taking a really long time"). Firmware landed in Oct 2026, and GA10B is unsupported upstream. |
| N5 | https://www.techveda.live/jetson-orin/ | SECONDARY | Lists which blocks are vendor-only (GPU, DLA, VI/Argus, NVDEC user API). Gives 6.8 as non-LTS and module availability to 2032-01. |
| N6 | https://nullr0ute.com/2023/12/any-linux-distro-on-nvidia-jetson-orin-with-jetpack-6/ | SECONDARY (Fedora/Red Hat engineer blog) | Since JetPack 6, UEFI firmware lets generic distro kernels (Fedora, RHEL) boot Orin. |

Archive N1, N3 and N4 under `research-output/evidence/sources/` before relying on them (rule 1). This refuter did not archive them.

## 5. Verdict and required written response

**WEAKENED.**
- **Upheld:** stock mainline cannot replace L4T for a camera- and CUDA-using Jetson robot in 2026–2028.
- **Weakened:** the claim implies that OneMind should therefore ship NVIDIA's kernel. N2, N3 and N1 show a credible alternative: own an LTS kernel (6.18 to Dec 2028) and build NVIDIA's OOT modules against it, as NVIDIA's own BYOK path allows and Talos does. That option needs to be evaluated. N1 and N2 also show that the vendor kernel carries its own lifecycle risk. The claim does not mention that risk.

**The author must:**
- restate DC-08 as a three-way choice: L4T vendor kernel, OneMind LTS kernel plus NVIDIA OOT modules (BYOK), or mainline only;
- give the OOT maintenance cost per kernel bump;
- say which Jetson features (Argus cameras, DLA, PREEMPT_RT) are lost on BYOK.

PREEMPT_RT on Jetson was not checked here. It is UNVERIFIED.

## 6. What evidence would flip the decision

- **Toward "OneMind LTS kernel plus OOT (BYOK)" as the Jetson default:**
  - NVIDIA documents BYOK support for a named LTS (6.12 or 6.18) with the full OOT set, including camera/VI/Argus, nvgpu and DLA.
  - The Talos #1518 approach merges and holds across two kernel bumps with no performance regression.
  - The GA10B firmware is relicensed into linux-firmware.
- **Toward "mainline only" (claim refuted):**
  - An upstream GA10B GPU driver (nouveau or another) plus upstream VI/CSI camera capture for tegra234 or tegra264 that runs a ROS 2 perception pipeline.
  - Or NVIDIA shipping a JetPack release whose kernel is an unmodified LTS.
- **Toward the claim fully upheld (stay on L4T):**
  - The OOT stack breaks on mainline LTS updates repeatedly. The Talos 7.3 regression stays unfixed, or OE4T/NVIDIA refuse non-L4T kernels.
  - Or NVIDIA commits to multi-year security support for each JetPack kernel line that covers Orin to 2032.
