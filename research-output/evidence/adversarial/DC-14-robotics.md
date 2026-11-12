# DC-14 refuter: real-time kernel needs of robotics (robotics lens)

| Field | Value |
|---|---|
| Target | DC-14. Current answer (08 FF-5): a PREEMPT_RT kernel **exists on every target flavor**: mainline 6.12, Debian `linux-image-rt-*`, the Pi's `-rpi-v8-rt` builds (no Pi 5-optimised build), and the L4T RT kernel (Developer Preview). The flip condition is **not met**. RT is an image profile, not the default, and hard real time and safety go to an MCU. |
| Cited claims | C-W7-020, -021, -024, -009 (and -022, -023 for cgroups) |
| Lens | Robotics fit: control loops sharing a node with k3s |
| Protocol | RESEARCH-MISSION.md §2 rule 7. I read only the conclusion and its cited claims before forming this view. |
| Date | 2026-11-10. Re-check by 2027-05-10. |
| Verdict | **upheld** on the flip condition as written; **weakened** on the implied claim that RT-on-node is usable for soft-RT control on Pi 5 and Jetson |

## 1. Cited sources re-checked

The cited claims establish availability: the 6.12 Kconfig change, the trixie RT packages, the Pi repo holding only `-rpi-v8-rt` builds, and NVIDIA's "Developer-Preview quality" RT kernel. I don't dispute these. On availability alone the flip condition is not met, and no alternative base improves Jetson, since every base uses NVIDIA's kernel.

## 2. Strongest counter-argument

The flip condition tests only whether an RT kernel **exists**. DC-14's real question is whether control loops can share a node with k3s. On the two robot boards the evidence says "only with measured, per-unit qualification":

1. **Pi 5:** under memory stress, PREEMPT_RT on Pi 5 showed cyclictest maxima of 196–458 µs per thread, and **above 1000 µs overnight**. The linux-rt-users discussion attributed this to a contended Pi 5 memory bus [C-REF-DC-robotics-006]. A Raspberry Pi engineer's only advice was to use the 4k-page `v8` kernel, the same non-2712 build that C-W7-024 found to be the only packaged RT option. A k3s node is a memory-heavy co-tenant, so a 1 kHz ros2_control loop on Pi 5 is not dependable without measurement.
2. **Jetson AGX Orin:** on JetPack 6.2 with cores 8–11 isolated (`isolcpus`, `nohz_full`, `rcu_nocbs`), one module held about 10 µs maximum latency while a second identical module exceeded 50 µs and reached 90 µs or more. NVIDIA staff replied "This not not expected" (sic), and the thread is unresolved [C-REF-DC-robotics-005]. Latency then varies **per unit**, so a profile qualified on one dev kit does not carry to the fleet.

**Effect:** "RT becomes an image profile" is right, but the profile cannot be just a kernel package. It needs a per-unit acceptance test (cyclictest under k3s plus a GPU or memory stressor) and a stated latency budget. The robotics default should be **MCU for any loop tighter than about 1 ms on Pi 5**, not only for "hard real time and safety". This narrows G4 sub-check (b) without changing D2.

## 3. New sources (searched for regressions and failures)

- NVIDIA forum, "[JetPack 6.2][AGX Orin 64GB][PREEMPT_RT] Large cyclictest latency variation between different modules", 2026-08-26: https://forums.developer.nvidia.com/t/jetpack-6-2-agx-orin-64gb-preempt-rt-large-cyclictest-latency-variation-between-different-modules-up-to-90-us-even-with-cpu-isolation/381288 [C-REF-DC-robotics-005]
- Raspberry Pi Forums, "PREEMPT_RT performance on Raspberry Pi 5", January 2025: https://forums.raspberrypi.com/viewtopic.php?t=382231 [C-REF-DC-robotics-006]

Both are SECONDARY (user reports with vendor-engineer replies). The founder-hardware cyclictest from DC-14's evidence list is what turns them into a decision input.

## 4. What would flip the decision

- **Flip (node architecture changes):** the founder cyclictest on Pi 5 with the trixie `-rpi-v8-rt` kernel, k3s running and a memory stressor, gives a worst case above the target loop period over 24 h, **and** an alternative base offers a Pi 5 RT kernel that does not. That second part is unlikely, because every base uses Raspberry Pi's kernel.
- **Re-open the Jetson RT profile:** NVIDIA keeps the L4T RT kernel at Developer Preview through JetPack 7.x, or explains the unit-to-unit variance as silicon-dependent.
- **Upholds it fully:** a 24 h cyclictest under k3s and stress stays below 100 µs on Pi 5 and below 50 µs on two different Orin modules.
