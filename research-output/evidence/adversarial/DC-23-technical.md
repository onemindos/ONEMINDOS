# DC-23: refuter report on a Kubernetes-native immutable OS (Talos, Kairos) instead of Debian + A/B + k3s (technical lens)

- **Conclusion under test (03 P0-7 and W2-R7, qbank W2 Q13/Q127, W4 Q127, 01 §4.1):** reject Talos and Kairos as the base. Talos fails G2 because Jetson support is Nano only and Orin is unmerged PR #23. Kairos fails G2 because it has no Pi 5 model. Talos's API-only model fights host-level needs (BLE, LoRa, CAN), and its "one signed artifact" idea is matched by bootc plus greenboot.
- **Flip condition:** one of them passes G2 (Pi 5 and Jetson Orin) and G5, and outscores the proposal.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W2-038, 039, 052; C-W4-064, 037, 038). I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **upheld**, but the Talos gap is closing faster than "fails G2" implies

As of 2026-11-11 neither OS passes G2 with official support, so the rejection stands. Two corrections sharpen it:

1. **The Talos Pi 5 "PASS" is softer than recorded.** An `rpi_5` installer does exist. But Sidero's own Pi 5 discussion closed with "Nothing out of the box yet" (2026-07-19), and a maintainer said Pi 5 is "not fully supported until the upstream kernel and uboot add support" [C-REF3-DC-technical-008]. The overlay's v0.3.0 (2026-11-02) moved Pi 5/CM5 to the upstream RP1 device tree on Linux 7.3. It marks the separate `rpi_5` installer for removal (#93), and **Pi 5 support in the generic U-Boot build, including NVMe, is still an open PR (#88)** [C-REF3-DC-technical-009]. "Pi 5 overlay yes" should read "Pi 5 boots; NVMe boot and the long-term installer path are unmerged".
2. **The Talos Orin gap is now the GPU, not the boot.** Talos has booted on Orin over UEFI since 2024. Through 2025 the blocker was "you cannot use the gpu". In April 2026 a community user ran CUDA in pods on Orin NX on Talos 1.12.6, and a Sidero maintainer said CDI and the device plugin "should already work starting with Talos 1.13" [C-REF3-DC-technical-007]. Official support is still absent, and it depends on unreleased OE4T sources (already on record in the ledger).
3. **Kairos on Jetson is less proven than "supports Orin" suggests.** A public report of an Orin NX flashed with Kairos that "is not bootable", with no Kairos response [C-REF3-DC-technical-010], is a single 2024 data point (low confidence). It is still the only field report I found, and it argues against treating Kairos's Jetson models as a ready base.

## Strongest counter-argument

The rejection compares a **finished** Talos against an **unbuilt** OneMind stack. The proposal itself still lacks a lab-proven Jetson A/B path (DC-07, T-W3-06 blocked) and a proven Pi 5 A/B on NVMe. Talos already gives atomic A/B, an API-managed node and Kubernetes upgrades that roll back with the OS. That removes DC-12's k3s-minor-versus-datastore problem by design. On Pi 5 it is one U-Boot PR away from NVMe boot, and on Orin it is one approved-but-unmerged pkgs PR away from GPU. Judged on "who reaches G2 first", it is not obvious OneMind's own stack wins. The rejection still stands on two things this lens cannot dismiss. First, Talos has no shell and no host package manager, so host radios and CAN would have to be extensions. Second, Talos's Orin path would rest on the same untagged OE4T sources that OneMind would otherwise control directly.

## New sources (searched for failure, abandonment and regressions)

- **N1.** siderolabs/talos discussion #8316, "Support for Nvidia Jetson Orin Family?". Opened. [C-REF3-DC-technical-007]
- **N2.** siderolabs/talos discussion #7821, "Raspberry PI 5 support". Opened. [C-REF3-DC-technical-008]
- **N3.** siderolabs/sbc-raspberrypi v0.3.0 release notes and PR #88. Opened, and the status was queried via the GitHub API on 2026-11-11. [C-REF3-DC-technical-009]
- **N4.** NVIDIA forum, "Orin NX flashed using Kairos" (2024-10-08). Opened. Low confidence. [C-REF3-DC-technical-010]

## What would flip it

- **Towards weakened/refuted:** sbc-raspberrypi #88 merged with Pi 5 NVMe boot, **and** an official Talos release with Orin GPU support (the pkgs nvgpu package merged and an `sbc-jetson` Orin installer), **and** a lab showing the NATS leaf, Tailscale and one USB or CAN radio running as Talos system extensions. Talos would then pass G2 and must be scored on S1, not just gated out.
- **Stays upheld if:** by the 2027-Q2 review, Talos Pi 5 still needs a third-party overlay for NVMe, or Orin GPU on Talos still depends on untagged OE4T snapshots.
