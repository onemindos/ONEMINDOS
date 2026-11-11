# Refuter report: W2 P0-2, robotics and IIoT fit lens

- **Refuter lens:** robotics and IIoT fit
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10
- **Verdict:** **upheld** (new sources make the case stronger, not weaker; the steelman for Fedora under this lens is real but does not reach "single base")
- **New ledger rows:** C-REF-W2-robotics-006 … 008 in [`../claims/REF-W2-robotics.csv`](../claims/REF-W2-robotics.csv)

## Claim under test

> Fedora IoT should not be OneMind's single base today. Its releases live about 13 months (F45 EOL 2027-12-08), it has no hold-back tree ("We don't have the resources for that"), its bootc images don't boot on Raspberry Pi (issue #82 open, fix PR open), Raspberry Pi 5 is not in its reference platforms, and no shipping product on it was found. (C-W2-015, 016, 018, 019)

## What the cited sources confirm

Ledger rows checked: C-W2-015 (F45 EOL 2027-12-08), C-W2-016 (reference platforms: Pi 4 and **Jetson Orin** listed, Pi 5 not), C-W2-018 (#82 and bootupd PR #935 open), C-W2-019 ("We don't have the resources for that"). "No shipping product found" is a negative-search claim I did not re-test.

## Strongest counter-argument (steelman for Fedora IoT under this lens)

- Fedora IoT lists **Jetson Orin** as a reference platform (C-W2-016), which Debian does not; a robotics vendor could read that as a better Jetson story.
- Robots run ROS in containers (Isaac ROS recommends Docker, see C-REF-W2-robotics-001), so Fedora's absence from the ROS 2 tier table (C-W2-028) matters less than it looks.
- The 13-month release life matters less for an image fleet that rebases automatically every release, and greenboot gives the health-gated rollback ADR-001 wants.

## Why it fails for robots and IIoT (new sources)

1. **Maintainer depth, the precondition for the 13-month treadmill, is thin and was formally questioned.** In July 2025 Fedora Quality proposed reconsidering IoT's Edition status, stating "we believe just two maintainers" and countme at "just under 4k" weekly check-ins; a QA lead noted the loss of the dedicated IoT QA person ("Geoff is not the only one who decided to leave"). The proposal was withdrawn on 2025-09-08 only because "the Fedora IoT team decided to take over most of the Quality tasks" [C-REF-W2-robotics-006, 007]. A ~2-person team now also carrying its own QA is the same resource limit as C-W2-019, from a second, independent source. An auto-rebasing fleet is only as safe as the release testing behind each rebase.
2. **"Jetson Orin reference platform" does not mean a robot's GPU works.** The only public Fedora-on-Orin install report found boots Fedora 38 Silverblue but with no Ethernet driver, software rendering on nouveau, the NVIDIA CUDA driver package preventing boot, and CUDA as "TODO … porting the Jetson CUDA .deb package to RPM"; the author notes "This is not supported by NVIDIA" [C-REF-W2-robotics-008]. This is 2023 and low-weight, but I found nothing newer showing CUDA/TensorRT on Fedora IoT on Orin. Containerised ROS does not help: the container still needs the host's L4T GPU stack (nvgpu, CDI), which ships only for Ubuntu-based JetPack (C-REF-W2-robotics-002) and downstream RHEL Device Edge, not Fedora.
3. So under this lens Fedora IoT is the weakest family for a robot's AI compute node, on top of the Pi bootc gap in the claim.

## Verdict: upheld

The conclusion is narrowly worded ("single base", "today") and every robotics/IIoT fact found points the same way. It does not argue against Fedora IoT as an upstream canary or bootc as an industrial profile (P0-3, not tested here).

## What would flip the decision

- Fedora IoT gains a supported longer-life or hold-back stream, **and** its team grows beyond ~2 maintainers (e.g. named additional maintainers in the iot-distro repo or a Council-funded initiative).
- A documented, NVIDIA- or Red Hat-supported path to CUDA on **Fedora** IoT on Jetson Orin/Thor (not only RHEL Device Edge).
- bootupd PR #935 merged and a Fedora IoT bootc image booting on Raspberry Pi 5 from first flash, with Pi 5 added to the reference platforms.
