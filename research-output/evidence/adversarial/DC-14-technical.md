# DC-14 — Refuter report: real-time kernel needs of robotics, technical lens

- **Conclusion under test (08 FF-5, qbank W7 DC-14):** A PREEMPT_RT kernel exists on every target flavor: mainline since v6.12, Debian trixie `linux-image-rt-{amd64,arm64}`, Raspberry Pi `-rpi-v8-rt` builds (no Pi 5-optimised build), and NVIDIA's L4T RT kernel (Developer-Preview quality). No other base gives Jetson a better RT kernel. The flip condition is **not met**. Real time becomes an image profile, not the default. Hard real time and safety go to an MCU.
- **Flip condition (decision-critical.md):** an RT kernel isn't available on a target flavor, and the alternative base provides one.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W7-009, 010, 020–025, 035, 036). I did not read the author's reasoning or other refuter files first.
- **Date:** 2026-11-10

## Verdict: **weakened** (the literal flip condition is not met, but it tests the wrong thing)

The availability facts check out. The problem is that the flip condition asks only whether a kernel *exists*. The ADR question in "Why it can flip" asks something else: **can control loops share a node with k3s?** Field reports show that worst-case latency on the two cheapest robot boards is decided by the hardware and the board, not by which distro supplied the RT kernel. The conclusion survives because no alternative base fixes this either. But "RT as an image profile on a k3s node" is not demonstrated on Pi 5 or Orin, and it should not be planned as anything stronger than **soft** real time until LAB-W7-1 measures it.

## Checks of the cited sources

| Sub-claim | Claim | Result |
|---|---|---|
| Mainline PREEMPT_RT since 6.12 | C-W7-020 | Holds (Kconfig `select ARCH_SUPPORTS_RT` in v6.12 for x86 and arm64). |
| Debian ships RT images | C-W7-021, C-W7-022 | Holds for amd64/arm64. But Debian's generic arm64 kernel is **not** the Pi 5 kernel. The Pi 5 flavor runs Raspberry Pi's kernel (03/umbrelOS pattern), so the Debian RT package does not count for Pi 5. |
| Pi RT build exists | C-W7-024, C-W7-025 | Only `-rpi-v8-rt` (generic 4K-page arm64), no `2712` RT build, and Raspberry Pi states no support for a prebuilt RT kernel. On Pi 5 the RT kernel is **community-grade and unsupported**, which is weaker than "exists". |
| L4T RT kernel | C-W7-009, C-W7-010 | Developer Preview, and Isaac ROS recommends it "only for use with robot manipulators". Holds. |
| Static CPU manager / ros2_control | C-W7-035, C-W7-036 | Holds. These are mechanisms, not latency evidence. |

## Strongest counter-argument

An RT kernel is necessary but not sufficient. On Pi 5, memory-bus contention gives spikes of hundreds of µs to over 1 ms under memory stress, even on PREEMPT_RT. A k3s node (containerd, kubelet, image pulls, log shipping) is a memory-stress workload. On Orin, two modules on the same JetPack with full CPU isolation differ by an order of magnitude (about 10 µs vs 90+ µs), and NVIDIA has given no root cause. So "control loop + k3s on the same SoC" is unproven on both boards, and the variation between boards means one dev kit passing LAB-W7-1 says little about a production fleet. That points the node architecture towards the MCU/RTOS split (or a partitioning hypervisor) **for any loop under about 1 ms**, as the default rather than as an exception. That is part of what DC-14 says could flip.

## New sources (searched for failures and regressions)

- **N1. Raspberry Pi Forums, "PREEMPT_RT performance on Raspberry Pi 5"** — https://forums.raspberrypi.com/viewtopic.php?t=382231 (opened). The thread started 2025-01-09 and is locked. It tested 6.13.0-rc3/rc6 RT (both 16k and 4k-page builds) with `cyclictest -m -p 90/95` under `stress -m 4 --vm-bytes 512000000 -c 4`. Per-thread maxima were 196–458 µs, with spikes up to 800 µs, and an **overnight run exceeded 1 ms**. The linux-rt-users discussion suggested Pi 5 memory-bus contention. No Raspberry Pi staff fix appears in the thread. [C-REF-DC-technical-001]
- **N2. NVIDIA Developer Forums, "[JetPack 6.2][AGX Orin 64GB][PREEMPT_RT] Large cyclictest latency variation between different modules"** — https://forums.developer.nvidia.com/t/jetpack-6-2-agx-orin-64gb-preempt-rt-large-cyclictest-latency-variation-between-different-modules-up-to-90-us-even-with-cpu-isolation/381288 (opened). Posted 2026-08-26 on L4T 36.4.3 with isolcpus/nohz_full/rcu_nocbs on cores 8–11. Board A ran at about 10 µs, board B at 50–90+ µs. NVIDIA replied: "The deviation between the two modules are huge. This not not expected." No fix is posted. [C-REF-DC-technical-002]
- Context only (search result, not opened in full): other Orin NX threads report maxima up to 2.2 ms on the RT kernel, and an Orin Nano NVMe initrd bug "not fixed in 36.3". These suggest the Developer-Preview label is earned.

## What would flip the decision

- **Towards a base change (the formal flip):** an alternative base (Ubuntu's `linux-raspi-realtime`, or a vendor BSP) shipping a **supported** Pi 5 (`2712`) RT kernel with measured worst case under 100 µs under memory stress, while Raspberry Pi's `-v8-rt` on Debian stays above 500 µs on the same board. Canonical's real-time Pi kernel is the candidate to test, because ros2_control itself lists `linux-raspi-realtime` (C-W7-036).
- **Towards a node-architecture change (the likelier flip):** LAB-W7-1 on a real Pi 5 and at least **two** Orin modules, running cyclictest for at least 12 h with k3s plus a representative pod load. If the worst case is above about 250 µs on Pi 5, or varies more than 3x between Orin modules, then control loops under 1 ms go to an MCU by default and the "RT image profile" is limited to soft real time (perception, planning).
- **Upheld cleanly if:** the same 12 h run under k3s load stays under about 100 µs on Pi 5 with `-v8-rt` and under 50 µs on two or more Orin modules.
