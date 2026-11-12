# DC-15 · ROS 2 tier support on the host OS: longevity and vendor-risk refuter

**Refuter:** REF3, lens longevity and vendor risk · **Date:** 2026-11-11 · **Verdict: WEAKENED**
**Read before forming this view:** DC-15 in `decision-critical.md`, `08-robotics-drones-physical-ai.md` FF-6/FF-7 and §6, the DC-15 row in `01-FOUNDATION-DECISION.md` §3, `qbank/W7.md` (DC-15, Q42, Q43, Q56), and the claims they cite (C-W7-026…034, C-REF-W2-robotics-001). No other adversarial file was read first.

## The conclusion under test

The conclusion is "D (small)": ROS 2 runs in containers on every flavor, so Debian's Tier 3 status is not a Debian-specific penalty. **D2 holds with one CONDITIONAL**, which is Isaac ROS on an x86 Debian host (LAB-W7-3). Vendor sensor SDKs (Q56) are "partial". They run in Ubuntu containers, and the residual risk is host kernel modules, tested with one USB depth camera.

## Strongest counter-argument

The CONDITIONAL is drawn too narrowly. The host coupling that DC-15 asks about ("proprietary SDKs (ZED, RealSense) need an Ubuntu host") is real for both leading depth-camera vendors. Containers do not remove it, and the vendor side of it has become less stable.

1. **RealSense's kernel support is Ubuntu-only, by kernel version.** The current `librealsense` Linux distribution guide offers packages "for Ubuntu 20/22/24/26 LTS". It says the `librealsense2-dkms` kernel package "supports Ubuntu LTS HWE kernels 5.15, 5.19 and 6.5". It "strongly recommend[s]" DKMS, and it names manual kernel patching as the route for "non-LTS Ubuntu kernel versions" or other distributions. Debian is not named [C-REF3-DC-longevity-005]. Debian 13 runs kernel 6.12, which is not on that list. A container gets the userland, but the UVC metadata and kernel patches live in the **host** kernel. So on a Debian host OneMind either (a) carries its own port of the RealSense kernel patches against every Debian point kernel until 2036, or (b) uses the user-space backend and accepts whatever it gives up. That is the same failure mode that already hit NVIDIA's DKMS on Debian point kernels (C-REF-DC-cost-009, cited in 01).
2. **The RealSense vendor changed owners twice in 14 months.** Intel spun RealSense out as RealSense, Inc. on 2025-07-11. Cognex then acquired it on 2026-09-22 for about $500 million, with the facial-authentication division excluded [C-REF3-DC-longevity-006, SECONDARY]. The SDK repository has already moved from the IntelRealSense GitHub organisation to `realsenseai`. A buyer focused on industrial machine vision may narrow the open SDK's platform matrix. Nothing in its history suggests it would widen to Debian. For a robot SKU sold in 2027 with support to 2035 or later, the camera SDK's lifecycle is a vendor risk the Debian host cannot absorb.
3. **ZED lists no Debian host.** Stereolabs' specifications page lists the operating system as "Windows, Ubuntu | Windows, Ubuntu | Jetson Linux (L4T)" [C-REF3-DC-longevity-007]. Its ZED X / ZED Link GMSL drivers are built per L4T release, and some L4T point releases are explicitly unsupported (driver page, read via search results only, not ledgered). On Jetson that is the NVIDIA flavor's problem, which A shares with D. On an x86 Debian robot or GPU box, it is an unsupported host.
4. **Tier 3 Debian has an early end date.** Lyrical's Tier 3 trixie entry ends on 2028-08-09 (C-W7-027). After that, even community "functional" status lapses. A Debian host then has no ROS 2 claim at all, and everything depends on the containers' Ubuntu userland plus host kernel compatibility. Points 1 to 3 show that compatibility is not guaranteed.

Combined: the "one host coupling found is Isaac ROS on x86" is not correct. There are at least two more on x86 (RealSense DKMS and the ZED host OS list). Each one has a vendor whose support horizon OneMind does not control.

## What does not break

- On **Jetson** (the robotics flavor), all three vendors target L4T/JetPack, which is Ubuntu-based anyway. So D2's Jetson flavor is unaffected, and stack D gains nothing there.
- RealSense has a user-space (libuvc/RSUSB) backend that needs no kernel patches. Its feature and performance costs were **not verified** here. If LAB-W7-2 shows it is good enough, point 1 shrinks to a support-statement issue.
- Ubuntu 26.04 is not on RealSense's DKMS kernel list either (5.15/5.19/6.5 only). The kernel coupling hurts any host that runs a current kernel, Ubuntu included. That keeps the Debian penalty "small", but it does not remove it: Ubuntu is at least a named, supported OS.

## Verdict: WEAKENED

The rating "D (small)" stands. The CONDITIONAL should cover more: **"Isaac ROS, RealSense kernel support and the ZED SDK on x86 Debian hosts are unvalidated; LAB-W7-2 must use a RealSense camera through the kernel (UVC) backend on Debian 13's 6.12 kernel, not just 'one USB depth camera'."** The vendor-risk note (RealSense ownership changes) belongs in the robotics hardware BOM risk register.

## What would flip it

- **To REFUTED (the robot tier moves to Ubuntu):** LAB-W7-2 shows RealSense or ZED loses a needed capability (frame metadata, sync, multi-camera, IMU) on a Debian 6.12 host and keeps it on an Ubuntu host, **or** Cognex or RealSense announces SDK support limited to named Ubuntu releases.
- **Back to UPHELD:** the user-space backend gives full capability on Debian in LAB-W7-2, **or** OneMind's robot SKUs standardise on Jetson only (where L4T is the host anyway).

## New sources (opened 2026-11-11)

| Claim | Source | Type |
|---|---|---|
| C-REF3-DC-longevity-005 | https://github.com/realsenseai/librealsense/blob/master/doc/distribution_linux.md | PRIMARY (branch head, not pinned) |
| C-REF3-DC-longevity-006 | https://en.wikipedia.org/wiki/RealSense (cites Reuters 2025-07-11 and Cognex press release 2026-09-22) | SECONDARY |
| C-REF3-DC-longevity-007 | https://docs.stereolabs.com/docs/installation/specifications | PRIMARY |
