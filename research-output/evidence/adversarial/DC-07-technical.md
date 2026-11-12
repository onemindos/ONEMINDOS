# DC-07: refuter report on one update framework across x86, Pi 5 and Jetson (technical lens)

- **Conclusion under test (04 §5.3, qbank W3 Q6/Q47, 01 §4.2):** no open-source engine covers x86, Pi 5 and stock-L4T Jetson. Use **one release contract over per-board backends**: RAUC on x86 and Pi 5, and NVIDIA rootfs A/B plus image-based OTA on Jetson, with OneMind's gate in `l4t-rootfs-validation-config.service`. The flip condition is not met.
- **Flip condition (decision-critical.md):** no candidate can be one framework for all three, and a per-flavor framework costs more than switching the core framework.
- **Lens:** technical. I read only the conclusion and its cited claims (C-W3-013, 021, 049–054; C-W7-013, 014, 017–019). I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened**

The cited facts hold: Rugix has no Tegra path, the RAUC Tegra layer was removed, and Mender and SWUpdate reach Jetson only through Yocto. The weak point is the word **one** in "one health gate". NVIDIA's backend has **different failure semantics** from RAUC's, and those differences matter most on robots:

1. **Failover counts warm reboots only.** NVIDIA staff say that power cycles do not decrement the rootfs retry counter, and that detecting a successful boot after a cold start is "not supported" [C-REF3-DC-technical-001]. A robot whose new slot hangs and is then power-cycled by a person or a brownout never falls back. RAUC-style boot counting, done in the bootloader per attempt, does fall back in that case. So the OneMind gate cannot sit on top of both backends as one abstraction. On Jetson it must turn every gate failure into a warm reset (watchdog or `reboot`) and must never rely on a power cut to advance the counter.
2. **The watchdog can be the single point of failure.** On an Orin Nano, a rootfs mount failure stopped the watchdog, so the board printed "Switching the bootchain" and still booted the bad slot. NVIDIA fixed this only in R35.5.0 and R36.3.0 [C-REF3-DC-technical-002]. Failover correctness depends on the BSP point release, which OneMind does not control. This adds to the branch-head-only fix pattern already on record.
3. **Custom carrier boards behave differently.** An integrator reports four failure modes that devkits do not show: slot switches that do not persist, a rollback counter (R36.4/36.5) that makes an update **report success while staying on old firmware**, slot B never initialised by vendor flash tools, and unexpected slot switches [C-REF3-DC-technical-003]. This is a vendor blog, so the confidence is low. It still matters for the hardware line, because OneMind robots will not be on devkits.

None of this makes a single engine possible. It does mean the per-board design costs more than "a wrapper around NVIDIA's code". It needs a Jetson-specific gate-to-reset path, a per-BSP failover regression test, a post-update version assertion (not trusting the OTA exit status), and a carrier-board qualification step.

## Strongest counter-argument

"One contract, per-board backends" hides two state machines that disagree about what counts as a boot attempt and who advances the counter. On Jetson the claimed "one gate" is really a gate plus NVIDIA's warm-reboot-only counter plus a watchdog whose correctness depends on the BSP release. The founder test T-W3-06 as written (gate failure plus a power cut during OTA) checks OTA resume. It does **not** check the case that bites robots: a committed trial slot that hangs and is then cold-cycled. If that case can't be made safe without Yocto/meta-tegra control of UEFI, the cost comparison in the flip condition tips towards Mender or SWUpdate on meta-tegra for Jetson. That is the route 01 §4.1 already promotes to "evaluated target".

## New sources (searched for failures and regressions)

- **N1.** NVIDIA forum, "A/B Rootfs Redundancy: No fallback to other slot when one gets corrupted" (2025-06, AGX Orin, r35.4.1). Opened. Cold resets don't count, and cold-boot success detection is unsupported. [C-REF3-DC-technical-001]
- **N2.** NVIDIA forum, "ROOTFS_AB will not switch slot after startup failures 3 times" (2024-05, Orin Nano custom carrier). Opened. A mount failure stopped the watchdog, and the fix landed only in R35.5.0/R36.3.0. [C-REF3-DC-technical-002]
- **N3.** ProventusNova, "Jetson A/B OTA updates: what breaks on custom carrier boards" (2026-03-16). Opened. This is a vendor blog, so the confidence is low. [C-REF3-DC-technical-003]

## What would flip it

- **Towards weakened → refuted (Jetson leaves stock L4T for meta-tegra + Mender/SWUpdate):** an Orin Nano test in which a trial slot that passed the bootloader but fails the OneMind gate (or hangs before it) is **power-cycled three times** and does not fall back, and no gate-to-warm-reset design fixes it on the shipping BSP.
- **Towards upheld:** T-W3-06 extended with (a) a cold-cycle-after-hang case, (b) a mount-failure case that checks the watchdog fires, and (c) a version check after OTA. All three pass on the shipping BSP and on the first production carrier board.
