# Refuter: W7 FF-2 (DC-08), longevity and vendor-risk lens

**Target:** FF-2 in `08-robotics-drones-physical-ai.md`, which says mainline Linux can't replace NVIDIA's Jetson kernel within the planning window. Orin and Thor device trees are upstream, but NVIDIA ships out-of-tree modules and calls its own kernel "the most complete and best tested." Consequence: the Jetson flavor stays on NVIDIA's BSP kernel (kernel route (c) in W18).
**Cited claims read:** C-W7-011 and C-W7-012.
**Refuter:** REF-W7-longevity · 2026-11-10 · I read only the conclusion and its sources.

## Verdict: UPHELD, with a longevity caveat on the chosen route

New evidence supports the claim that mainline cannot replace the BSP:

- **No upstream GPU support for Orin.** The Siderolabs Talos effort to run Orin on a mainline kernel (`siderolabs/pkgs` PR #1518, opened Apr 2026, still open on 4 Nov 2026) relies on NVIDIA's out-of-tree nvgpu module. That module "provides GPU compute on mainline kernels but does not include the nvhost control interface." The PR also uses unreleased OE4T sources: "None have release tags — that is the current state of OE4T for GA10B on kernel 6.x." The GA10B firmware is absent from linux-firmware because "NVIDIA has never submitted the Orin GPU firmware there" [C-REF-W7L-008].
- **Kernel upgrades cause regressions.** On kernel 7.3, the same stack needed patches, and GPU token throughput fell about 7x compared with 6.18 (about 10 versus 70–78 tok/s). The suspected cause is an upstream `soc/tegra` change [C-REF-W7L-008]. A mainline route means OneMind absorbs breakage on every kernel bump.
- The BYOK page lists no tested upstream versions and no list of missing features. It offers out-of-tree modules plus a patch list that "may need prerequisite patches" [C-REF-W7L-009]. That is guidance, not a supported configuration.

## Strongest counter-argument (longevity)

FF-2 is correct that mainline cannot replace the BSP. But "stay on the BSP" is not stable over a long life either:
1. The BSP kernel is tied to NVIDIA's branch schedule, and each branch dies before its hardware stops shipping. JetPack 4 ended Nov 2024 and JetPack 5 ended Oct 2026 (see W7-FF-1-longevity).
2. JetPack 7's kernel base is 6.8 according to the DC-08 prior-verified facts. 6.8 is not a kernel.org longterm release [C-REF-W7L-010], so no upstream stable fixes come for it. Every backport depends on NVIDIA, or on Canonical's support for its own kernel.
3. Late in Orin's 2032 life, the realistic options are a frozen, EOL BSP kernel or exactly the mainline-plus-OOT route FF-2 rejects (Talos/OE4T). So FF-2 holds for the planning window **up to the EOL of Orin's last branch**, not to 2036.

This does not overturn FF-2's decision for the current period. It does mean W18 route (c) needs a named fallback for the end of life. Track the Talos/OE4T mainline-plus-OOT route (meta-tegra) as the exit, not just as the runner-up.

## What would flip this

- **Toward weakened or refuted (mainline becomes viable):** GA10B firmware merged into linux-firmware; nouveau/NVK or an upstream driver supporting the Orin iGPU; NVIDIA publishing BYOK as supported on a named longterm kernel (6.12 or 6.18) with CUDA/TensorRT validated; or Talos shipping Orin GPU support with release-tagged OE4T modules and no regression across two kernel bumps.
- **Toward a stronger uphold:** OE4T losing maintainers or not porting the r36/r38 out-of-tree modules to new kernels; the Talos PR being closed unmerged.

## Sources opened
- https://github.com/siderolabs/pkgs/pull/1518
- https://www.kernel.org/category/releases.html
- https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SD/Kernel/BringYourOwnKernel.html (cited source, re-read)
