# DC-23 · Talos / Kairos instead of Debian + Rugix + k3s: refuter, longevity and vendor-risk lens

**Target conclusion** (`03-base-os.md` P0-7, W2-R7; `05-…` Talos row): reject Talos and Kairos as the base, because Talos has no Jetson Orin (sbc-jetson only `jetson_nano`, Orin PR #23 unmerged) [C-W2-038, C-W4-064] and Kairos has no Pi 5 model [C-W2-039]. Licences: Talos MPL-2.0, Kairos Apache-2.0 [C-W2-049].

**Verdict: UPHELD.** Rechecked on 2026-11-10 against newer artefacts than the pinned SHAs.

## Strongest counter-argument (steelman for the rejected options)
Hardware gates move, and Debian's own Pi 5 and Jetson paths are vendor side-repos too (see DC-19). Kairos already supports AGX Orin, Orin NX, Thor and DGX Spark [C-W2-039]. That is exactly the Jetson half Debian has to handle with a separate L4T Ubuntu flavour. If Kairos lands Pi 5, it would pass G2 with *one* immutable framework across Pi, Jetson and x86. That is a better DC-07 answer than Rugix plus NVIDIA tools. Kairos also uses Ubuntu or Debian underneath, so the userland bet is not lost. Rejecting it on a gate that might close in 2027 risks locking in a weaker update story.

## New sources (searched for stalls, unmerged support, maintainer statements)
1. **Talos Orin has still not shipped.** `sbc-jetson` v0.2.0 (2026-11-02) still ships only `jetson_nano` (tag = 6468a58, the SHA the author pinned). PR #23 (Orin Nano/AGX) is open, unmerged, and untouched since 2026-04-22 [C-REF-DC-longevity-007]. A release cut nine months after the PR, without it, looks like deprioritisation.
2. **Kairos Pi 5 is blocked upstream and on the roadmap only for Q2 2027.** Issue #2010 has been open since 2023-11-17. Maintainers say U-Boot lacks Pi 5 USB/disk support, and the first milestone is likely SD-card only. It was moved to "Q2 2027" on 2026-11-09 [C-REF-DC-longevity-008].
3. **Talos's Pi 5 support is itself thin.** The Siderolabs maintainer says Pi 5 RP1 support needs RPi patches on Sidero's kernel: "There is no good path forward without it". NVMe boot needed rpi5-uefi or a community U-Boot [C-REF-DC-longevity-009]. So Talos is weak on *both* founder boards, not just Orin.

## What would flip it
- Kairos ships a Pi 5 model that boots from NVMe or USB, not SD only, in a tagged release. It would then pass G2 on Pi 5 + Orin + x86 and must be scored, with weight on DC-07 (one update framework). Check issue #2010 at the Q2 2027 board date.
- `siderolabs/sbc-jetson` PR #23 merges and a release ships Orin installers, **and** Talos's Pi 5 overlay boots NVMe with Sidero's kernel. Talos would then pass G2, but still needs a host-services answer (NATS leaf, radios, CAN) under an API-only OS.
- Vendor-risk tripwire: any licence change on Talos core (today MPL-2.0; Omni is already BSL) would move it from "rejected on hardware" to "rejected on G1".
