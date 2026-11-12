# Refuter (technical): W19 DC-16 CONSTRAINT, kernel drivers [C-W19-048]

**Refuter:** independent, technical lens. **Date:** 2026-11-11. Read: the conclusion, claim rows C-W19-005, C-W19-008 and C-STEEL-KRU-013, and the lab log L47-L49 and L66.

## Target
Third parties cannot install kernel drivers at runtime. Driver plugins are therefore per-kernel, OneMind-signed packs from the OneMind pipeline, with one sysext owning the module indexes per kernel (an inference, test T-W19-02).

## Strongest counter-argument
1. **"Cannot" is a policy, not a technical limit.** The cited Debian SecureBoot source (C-STEEL-KRU-013) describes the standard escape hatch: DKMS modules signed with a Machine Owner Key that the owner enrolls at the console. So a third party *can* install a driver at runtime if the owner enrolls a key. The honest claim is "OneMind chooses not to allow this, because MOK enrollment needs console presence and widens the trust root". That is a defensible choice, but it is a choice.
2. **"One combined pack per kernel" is not the only fix for index masking.** A Flatcar maintainer, writing about module sysexts, warned that each sysext "still overrides the modules.dep so having multiple sysexts like this won't play well", and suggested **a modprobe hook, as the official sysexts do** (flatcar/Flatcar#1448). That is an alternative to one combined pack, and it keeps vendor packs separately updatable.

## NEW sources (failure-seeking)
- **flatcar/Flatcar#1576** (opened 2024-11-01, **still open**, kernel 6.6.54-flatcar): "The `nvidia-driver` extension hides the `zfs` modules in `/usr/lib/modules/*/modules.dep`"; `flatcar-zfs` then works only with manual `insmod`. https://github.com/flatcar/Flatcar/issues/1576 → **field confirmation of the untested masking inference**. This supports the constraint, and shows that even the reference sysext distribution has not fixed it after a year.
- **flatcar/Flatcar#1448** (opened 2024-05-17, open): module overlays fail on the symlinked `/usr/lib64/modules` ("Mount path ... is not canonical"); the maintainer's modules.dep warning and modprobe-hook advice (2025-06-06). https://github.com/flatcar/Flatcar/issues/1448
- NVIDIA forum threads (supporting sources, read only as search summaries): no official procedure for signing out-of-tree modules on JetPack. This means "built per OneMind kernel" depends on OneMind controlling the kernel. That holds for Debian, not for Jetson L4T.

## Verdict: **UPHELD (core); remedy WEAKENED**
Per-kernel, pipeline-signed driver packs are the right model, and Flatcar #1576 turns the masking inference into observed behaviour. Two amendments: say "will not" rather than "cannot", naming MOK as the rejected path; and keep T-W19-02 open to compare "one combined pack" against "per-vendor packs plus a modprobe hook or merged index". The combined-pack approach ties every vendor's driver release to every other vendor's.

## What would flip it
- **To REFUTED:** a test where two module sysexts with separate `modules.dep` both load via modprobe under systemd 257 (for example through a depmod-at-merge hook writing to `/run`), making third-party per-vendor packs safe. Or a decision to support owner-enrolled MOK keys for driver plugins.
- **Stronger UPHELD:** T-W19-02 reproduces Flatcar #1576 on Debian 13.
