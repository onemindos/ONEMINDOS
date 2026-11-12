# Refuter report: W2 P0-1, robotics and IIoT fit lens

- **Refuter lens:** robotics and IIoT fit (ROS 2 robots on Pi 5 / x86 / Jetson; unattended industrial boxes)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10
- **Verdict:** **weakened** (the ranking may survive; the robotics reason given for it is weaker than stated, and 26.04 carries a new class of unattended-update risk)
- **New ledger rows:** C-REF-W2-robotics-001 … 005 in [`../claims/REF-W2-robotics.csv`](../claims/REF-W2-robotics.csv)

## Claim under test

> On the frozen scorecard, Ubuntu 26.04 LTS (+Ubuntu Pro) as the base of OneMind's own A/B image, with JetPack (Ubuntu) on Jetson ranks first (62.0) … The winner is robust: it is the same in all 14 ±5 weight runs, and its smallest margin is 3.9. (C-W2-005, 026, 028, 009)

## What the cited sources confirm (re-opened 2026-11-10)

| Claim | Status |
|---|---|
| C-W2-028 ROS 2 Lyrical: Ubuntu 26.04 Tier 1 amd64+arm64; RHEL 10 Tier 2 amd64 only; Debian Trixie Tier 3; Fedora absent | Confirmed. Also on the same page: **Ubuntu Noble (24.04) is Tier 3 for Lyrical**, and Tier 3 means "you must build ROS Lyrical from source". Jetson and Raspberry Pi are not mentioned. |
| C-W2-005 26.04 Pro to May 2036 | Not re-disputed under this lens. |
| C-W2-026 GPU Operator K3s column Ubuntu only | Not re-opened; this is an x86/dGPU fact. Jetson iGPU does not use the GPU Operator. |
| C-W2-009 Ubuntu Core 24 adds Pi 5 | Confirmed by ledger; it supports Ubuntu Core, not the classic-Ubuntu A/B image that won. |

## Strongest counter-argument

1. **The robotics advantage is real on x86/Pi but not on the platform robots actually use for AI.** NVIDIA's own ROS stack, Isaac ROS, now targets ROS 2 **Lyrical** but on **Ubuntu 24.04**: x86 needs "Ubuntu 24.04, CUDA 13.2+", Jetson needs JetPack 7.2, DGX Spark needs DGX OS 7.2.3; Ubuntu 26.04 is not mentioned [C-REF-W2-robotics-001]. JetPack 7.2.1 (Jetson Linux 39.2.1, 2026-08-11) is still "L4T Ubuntu 24.04", kernel 6.8, and lists Isaac ROS as "Coming soon" [C-REF-W2-robotics-002]. So on Jetson, OneMind runs Lyrical from **NVIDIA's buildfarm on a Tier 3 host**, i.e. exactly the position Debian is penalised for. And an x86 GPU robot that wants Isaac ROS is pushed to 24.04, not 26.04. The "same userland Pi → Jetson → DGX" story is two Ubuntu releases and two ROS build sources.

2. **ROS host tier is a weak discriminator because the robotics stack is containerised.** Isaac ROS says Docker is the recommended mode, "the highest isolation from the host" [C-REF-W2-robotics-001]. If ROS ships as a container (as OneMind's Market would ship it anyway), the host's ROS tier mostly stops mattering; what matters is the container runtime and the GPU/CDI path, which on Jetson is JetPack whatever the "base" is. Scoring Ubuntu 26.04 up and Debian down on ROS tier double-counts a benefit OneMind's own architecture discards.

3. **Mixed ROS releases across a fleet are a real wire risk, so "one family" does not buy ROS interoperability.** rmw_zenoh (Tier 1 middleware in C-W2-028) shipped a backported wire break in Jazzy: 0.2.5 cannot talk to 0.2.3 and mismatches "will crash the process"; users were told to update every instance including cached Docker images [C-REF-W2-robotics-003]. Maintainers commit to wire compatibility from Kilted on, but cross-distro compatibility is not guaranteed. A fleet must pin ROS per site regardless of the host OS; the host choice does not solve it.

4. **IIoT: 26.04 swapped core userland in the release cycle that produced an update-killing bug.** In 25.10 (the 26.04 run-up) the Rust `date -r` bug made `apt.systemd.daily` think no time had passed, so **unattended upgrades silently never ran**; recovery needed a manual `apt update` (Launchpad #2129660, dup of #2127970, reported 2025-10-23) [C-REF-W2-robotics-004]. 26.04 ships rust-coreutils 0.8.0; Canonical kept `cp`, `mv`, `rm` on GNU because eight TOCTOU issues from a Zellic audit (113 issues over two rounds) were still open on 2026-04-22, and thread replies report `install` breaking symlinks and an unverified file-corruption bug [C-REF-W2-robotics-005]. For a box nobody logs into, a silent "updates stopped" failure is the worst kind. The scorecard (as summarised) has no row for userland churn inside the LTS.

**Mitigation that limits the damage:** OneMind's image is A/B and updated by image, not by `unattended-upgrades`, and the image build can pin GNU coreutils and classic sudo (Canonical documents both remain installable). So point 4 is a build-config cost and a test item, not a disqualifier.

## Verdict: weakened

Nothing here proves Ubuntu 26.04 should lose. But two of the four supports (ROS Tier 1, Jetson continuity) are weaker for robots than stated: Jetson and Isaac ROS sit on 24.04 with Lyrical from NVIDIA's own buildfarm, and containerised ROS reduces the host-tier gap with Debian. If the ROS/robotics row is re-scored on "ROS as a container on this host" Debian and Ubuntu move closer, and the 3.9 margin should be re-checked.

## What would flip the decision

- **To upheld:** NVIDIA publishes a JetPack (or Isaac ROS release) on Ubuntu 26.04 with a date; or Isaac ROS lists Ubuntu 26.04 x86 as tested.
- **To refuted:** a scorecard re-run with the ROS row scored by container hosting (Debian/bootc not penalised for Tier 3) drops Ubuntu's margin to ≤ 0 in any of the 14 runs; or a confirmed 26.04 LTS regression in rust-coreutils/sudo-rs that breaks boot, update or file integrity on a fielded LTS install (e.g. Launchpad 2158615 confirmed and not fixed in an SRU).
