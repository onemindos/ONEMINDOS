# DC-09 refuter: base for the Jetson flavor (robotics lens)

| Field | Value |
|---|---|
| Target | DC-09. Current answer (08 FF-3; 01 §3.2 tie-break): keep **NVIDIA's L4T Ubuntu 24.04 (JetPack 7.2+)**. A Debian rootfs is not supported. Yocto meta-tegra is NVIDIA-official and the **named fallback**. This answer also decides S2 for RAUC over Mender. |
| Cited claims | C-W7-007, C-W7-008, C-W7-015, C-W3-053 |
| Lens | Robotics fit: a product-grade robot image that must be patched in the field for years |
| Protocol | RESEARCH-MISSION.md §2 rule 7. I read only the conclusion and its cited claims before forming this view. |
| Date | 2026-11-10. Re-check by 2027-05-10. |
| Verdict | **weakened** (the Debian-rootfs exclusion is upheld; the ordering "L4T Ubuntu first, meta-tegra fallback" is not firmly supported) |

## 1. Cited sources re-checked

C-W7-007 and -008 support "JetPack 7.2 = Ubuntu 24.04, Orin added, Yocto via OE4T official, Canonical Ubuntu 24.04 for Jetson listed". C-W7-015 supports meta-tegra LTS branches on R39.2.1. The exclusion of a Debian rootfs follows from these and stands.

## 2. Strongest counter-argument

For a robot that ships and is patched for years, the reasons given for L4T Ubuntu over meta-tegra are weaker than they look.

1. **"Stock" does not mean "patchable package by package".** NVIDIA's March 2026 Jetson bulletin fixes its CVEs only as whole Jetson Linux releases (35.6.4, 36.5, 38.2/38.4), and it has **no 39.x (JetPack 7.2, Orin + Thor) row** [C-REF-DC-robotics-001]. When a user asked which package carries the CVE-2026-24148 fix, NVIDIA staff declined to say [C-REF-DC-robotics-002]. On L4T Ubuntu, the security unit is therefore the full BSP, just as on meta-tegra. Staying "stock" gives no finer-grained patching.
2. **The Ubuntu userspace on L4T has no stated owner for 2029 onward.** Canonical's own Jetson images give Orin only **22.04**; 24.04 is offered only for Thor, and the long-term-support period is "available with Ubuntu Pro" with no number of years [C-REF-DC-robotics-003]. NVIDIA's L4T 24.04 rootfs pulls Canonical's archive, so after 24.04 standard support ends (May 2029, C-W2-005) its security depends on a Pro arrangement that nobody has priced for a Jetson rootfs.
3. **meta-tegra is not a thin fallback.** In the last 12 months its commits come from four substantial contributors (madisongh 114, ichergui 97, kekiefer 69, dwalkes 25) [C-REF-DC-robotics-004]. With JetPack 7.2 it is also NVIDIA-official (C-W7-008). It gives OneMind a rootfs it controls, a full SBOM, and maintained A/B integrations: Mender (C-W3-053) and SWUpdate. Robotics firms that ship Jetson products commonly use it for exactly these reasons (DC-20 premise).

**Effect:** the robotics case for meta-tegra as the Jetson product image is as strong as the case for L4T Ubuntu. The L4T advantage is real only for developer convenience and for apt-installed NVIDIA SDKs (Isaac ROS, DeepStream). Because DC-09 is used as the tie-break that gives S2 to RAUC over Mender, this weakens that tie-break too.

## 3. New sources (searched for CVEs, lifecycle gaps and maintainer loss)

- NVIDIA Security Bulletin, Jetson and IGX, March 2026: https://nvidia.custhelp.com/app/answers/detail/a_id/5797 [C-REF-DC-robotics-001]
- NVIDIA forum, CVE-2026-24148 package question: https://forums.developer.nvidia.com/t/cve-2026-24148-which-specific-debian-package-contains-the-fix-and-is-a-partial-update-feasible-on-jetpack-36-4-3/367096 [C-REF-DC-robotics-002]
- Canonical, Ubuntu on NVIDIA Jetson: https://ubuntu.com/download/nvidia-jetson [C-REF-DC-robotics-003]
- GitHub API, OE4T/meta-tegra commits since 2025-11-10 [C-REF-DC-robotics-004]

## 4. What would flip the decision

- **To meta-tegra as primary:** the founder-hardware lab shows Isaac ROS and the needed NVIDIA SDKs (CUDA, TensorRT, VPI) running in containers on a meta-tegra wrynose host with no capability loss, and a Mender or SWUpdate A/B update passes on Orin Nano. Either result also re-opens S2 (Mender).
- **Upholds L4T Ubuntu:** NVIDIA publishes a per-release security-support period for JetPack 7.x that includes package-level updates, or Canonical offers priced Pro coverage for the L4T 24.04 rootfs on Orin through at least 2034.
- **Against meta-tegra:** madisongh's share of commits rises above about 70%, or NVIDIA withdraws the "official Yocto" statement in a later JetPack.
