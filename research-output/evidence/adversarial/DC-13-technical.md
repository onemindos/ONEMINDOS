# DC-13 — Refuter report: NVIDIA GPU drivers on Debian, technical lens

- **Conclusion under test (qbank W4 Q16, 05 §7, W9 Q92):** Debian works for the driver, the Container Toolkit and the device plugin (time-slicing). It loses the GPU Operator lifecycle, signed precompiled drivers, and AICR / CNCF AI conformance. The GPU Operator is not a blocker for the Pro box. Verdict: weakened, not flipped. Allow Ubuntu + RKE2 for the GPU-server tier. A GPU lab is pending.
- **Flip condition (decision-critical.md):** a needed feature (time-slicing, MIG, CDI, DRA, Secure Boot-signed modules) fails on Debian 13 but works on a validated base.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W4-020 to 029, 037, 038). I did not read the author's reasoning or other refuter files first.
- **Date:** 2026-11-11

## Verdict: **weakened** (further than the author's own "weakened", but not flipped)

The flip condition is about features. The evidence I found is about **lifecycle and supply**, which the condition does not test but which N-8/F-2 care about:

1. NVIDIA has now **explicitly declined** Debian for the GPU Operator. Its feature request was closed "not planned" on 2026-09-11, because Debian "is not currently on our priority roadmap" (C-REF3-DC-technical-018). "Not listed" (C-W4-021) became "refused", so waiting for support is not a plan.
2. NVIDIA's own **debian13 repo lacks the 580 production branch** and offers only the 590/595 branches (C-REF3-DC-technical-020). A Debian 13 GPU box therefore rides newer feature branches or borrows the debian12 repo. Either way, it cannot sit on the branch NVIDIA steers fleets towards. (I did not open NVIDIA's branch-lifecycle page, so the length of the 580 support window is unverified here.)
3. **DKMS builds break on routine Debian point kernels.** nvidia-open 595.71.05 failed on 6.12.94 → 6.12.96+deb13 because of a packaging permission bug. The issue is still open, with no NVIDIA reply (C-REF3-DC-technical-019).

"Debian works" is true on the day of install. Whether it **keeps** working across a five-year fleet is unproven, and the vendor has said it won't help.

## Checks of the cited sources

| Sub-claim | Claim | Result |
|---|---|---|
| GPU Operator OS list has no Debian | C-W4-021 | Holds, and is now stronger: support was refused in #2225. |
| Container Toolkit apt "Ubuntu, Debian" | C-W4-026 | Holds. The toolkit is distro-light, so it is not the weak point. |
| CUDA 13.5 supports Debian 12/13 | C-W4-027 | Holds for CUDA userspace. But the driver branch choice on debian13 is narrower (N2). |
| Debian driver guide uses DKMS, no Secure Boot procedure | C-W4-028 | Holds, and it matters: on Debian, signed modules mean building and signing them yourself at image-build time. |
| k3s nvidia RuntimeClass; device plugin | C-W4-020, 029 | Holds. These are distro-neutral. |
| AICR / AI conformance exclude k3s and Debian | C-W4-037, 038 | Holds. |

## Strongest counter-argument

For an image-based OS, the DKMS argument is partly defused: the module is built in CI, not on the device. That moves the failure from the field to the release pipeline. But the release pipeline is **one developer**, and each Debian kernel point release (several per year, often security-driven) now needs a working NVIDIA module build before the security fix can ship. Upstream showed in July 2026 that this can break with no vendor response (N3). On Ubuntu, NVIDIA and Canonical ship **prebuilt, signed** `linux-modules-nvidia-*` packages and precompiled driver containers (C-W4-025), so the kernel security fix and the GPU module arrive together, already signed. On Debian, OneMind owns that join permanently, plus MOK/Secure Boot signing, with no vendor path and with NVIDIA on record refusing Debian (N1). That cost falls on the **Pro box** too, not only on the GPU-server tier. So the "allow Ubuntu for GPU servers" split should be tested for the Pro tier as well: any box whose value depends on the GPU arguably belongs on the validated base.

## New sources (searched for failures, abandonment and regressions)

- **N1. NVIDIA/gpu-operator #2225 "Support for Debian 13 (Trixie)"** — https://github.com/NVIDIA/gpu-operator/issues/2225 (opened). The driver image `580.105.08-debian13` does not exist, which causes ImagePullBackOff. NVIDIA: "We fully support Ubuntu 22.04 and 24.04". The issue was closed "not planned" on 2026-09-11. [C-REF3-DC-technical-018]
- **N2. NVIDIA forum, "Nvidia production driver not found on debian13 repo"** — https://forums.developer.nvidia.com/t/nvidia-production-driver-not-found-on-debian13-repo/363462 (opened). The debian13 repo has only the 590/595 branches, without 580 or 570. The workaround is the debian12 repo. There is no NVIDIA reply. [C-REF3-DC-technical-020]
- **N3. NVIDIA/open-gpu-kernel-modules #1258** — https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1258 (opened). The DKMS build of 595.71.05 fails on the Debian 13 kernel update 6.12.94 → 6.12.96 and leaves packages unconfigured. A second user reproduced it on 6.12.101. The issue is open with no maintainer reply. [C-REF3-DC-technical-019]
- Context only (search results, not opened): a community gist reports the same `pahole.sh` failure with the trixie-backports 7.0.7 kernel. NVIDIA forum threads report Hash Sum mismatches on the debian13 CUDA repo.

## What would flip the decision

- **Towards Ubuntu (or RHEL-family) for every GPU tier, including Pro:** the pending GPU lab shows that a Debian 13 point-kernel update plus the NVIDIA repo driver fails to build or to sign in CI more than once in a 6-month window, or Secure Boot-signed nvidia-open on Debian needs a self-managed MOK that the D6 secure-boot design can't accommodate. Separately, if the GPU Operator's driver-lifecycle features (driver upgrade controller, precompiled signed drivers) turn out to be needed for the Pro box, Debian is out, given N1.
- **Back towards the conclusion:** the lab runs Debian 13 + the debian13 repo driver + toolkit + device plugin on k3s through three consecutive Debian point kernels, with modules built and signed in CI, time-slicing and CDI working, and no manual fixes. NVIDIA adding a 580-class (long-lived) branch to the debian13 repo would also help.
