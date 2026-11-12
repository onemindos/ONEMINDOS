# W2 P0-1 refuter: longevity and vendor risk

| Field | Value |
|---|---|
| Claim | P0-1: on the frozen scorecard, "Ubuntu 26.04 LTS + OneMind's own A/B image + JetPack (Ubuntu) on Jetson" wins S1 with 62.0. bootc (RHEL family) and Debian 13 + Rugix tie second at 56.0. The winner is the same in all 14 ±5 weight runs, with a minimum margin of 3.9. |
| Lens | Longevity and vendor risk (C1, G3, plus what the C2 evidence means over the 10-year horizon) |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter saw only the claim and its five cited sources, not the author's scoring sheet or reasoning. |
| Date | 2026-11-10. Re-check BSP and Kubernetes facts by 2027-05-10, and lifecycle and pricing facts by 2027-11-10. |
| Verdict | **weakened**. A written response is required (rule 7). |
| Archiving | Not archived by this refuter, because the refuter may write only this file. The author must archive the load-bearing URLs in §5 under rule 1. |

## 1. Re-checking the cited sources

| Sub-claim | What the source says (opened 2026-11-10) | Holds? |
|---|---|---|
| The GPU Operator's K3s column lists only Ubuntu | The source is NVIDIA cloud-native-docs at `d856ea69:gpu-operator/platform-support.rst`. Ubuntu 26.04, 24.04 and 22.04 list K3s 1.33–1.37. RHEL 8/9/10 and Rocky have blank K3s cells; they are listed for upstream Kubernetes and RKE2. Debian does not appear. The same file also says: "The GPU Operator only supports platforms using discrete GPUs. **NVIDIA Jetson, or other embedded products with integrated GPUs, are not supported.**" | **Partly.** True for x86 or SBSA with a discrete GPU. **It does not apply to the Jetson tier at all.** |
| ROS 2 Lyrical is Tier 1 only on Ubuntu 26.04 (amd64 and arm64) | The source is `ros2_documentation@1c5c20cb:source/Releases/lyrical/supported-platforms.rst`. Tier 1: Ubuntu 26.04 (amd64, arm64) and Windows 11. Tier 2: RHEL 10. Tier 3: **Ubuntu 24.04 (amd64, arm64, arm32)**, Debian 13 and Yocto, all "build from source". "Ubuntu Noble is supported until 2029-06-01." | Yes as written. **But JetPack's Ubuntu is 24.04, so on Jetson, Lyrical is Tier 3** (see §2 A). |
| Ubuntu release cycle | 26.04 LTS: standard security maintenance ends May 2031, ESM ends May 2036, and the Legacy add-on runs to May 2041. 24.04 LTS: standard support ends May 2029, ESM ends May 2034, and Legacy runs to May 2039. | Yes, for Canonical's archive. |
| Ubuntu on Raspberry Pi | Ubuntu 26.04.1 LTS Desktop and Server are offered. The Pi 5 is "Yes, certified" under 26.04 LTS. | Yes |
| The stack is "Ubuntu 26.04 LTS … + JetPack (Ubuntu)" | Not covered by the cited sources. See §2 A: no Jetson module has a 26.04 image from NVIDIA or Canonical. | **The label is misleading** |

## 2. Strongest counter-argument (longevity and vendor-risk lens)

### A. The winning stack is two Ubuntu LTS releases from two vendors, and the Jetson half is the weaker one

- NVIDIA's Jetson FAQ says: "JetPack 7 supports Jetson Thor with Linux 24.04 LTS, Kernel 6.8". It also says "JetPack 6 is in sustaining mode". JetPack 6 is the Ubuntu 22.04 line that Orin used until 7.2.
- JetPack 7.2 reported in June 2026 that it extends Ubuntu 24.04 and kernel 6.8 to Orin (LinuxGizmos, 2026-06-19; SECONDARY).
- Canonical's own Jetson page offers **22.04** (Server and Core 22) for AGX Orin, Orin NX and Orin Nano, and **24.04** for AGX Thor. **No Jetson module has a 26.04 image.**

So the "Robotics" tier (D-002) runs Ubuntu **24.04**, not 26.04. This matters for longevity in three ways:

1. **24.04 is the shorter-lived base.** Standard support ends May 2029 and ESM ends May 2034. Reaching G3's 2036-12-31 on Jetson needs a paid Legacy add-on or a rebase to 26.04. NVIDIA has not announced a 26.04 rebase. The FAQ and lifecycle pages state **no software support duration** for any Jetson Linux release. The lifecycle page covers module availability only: Orin to January 2032, AGX Orin Industrial to July 2033, Thor T4000 to January 2036.
2. **Canonical's ESM does not cover the part that fails first.** The kernel, bootloader and firmware on Jetson are NVIDIA's L4T BSP, not the Ubuntu archive kernel. Neither the release-cycle page nor the Ubuntu Pro for Devices page says that Ubuntu Pro covers the NVIDIA BSP kernel on Jetson, or for how long. The Jetson download page says only "Long-term support from Canonical available with Ubuntu Pro" for Certified images. **On the Jetson tier, the C1 and G3 evidence for Ubuntu is Canonical's archive lifecycle, but kernel security there comes from NVIDIA, and NVIDIA publishes no end date.**
3. **NVIDIA's Ubuntu cadence lags Canonical's by about two years and slips.**
   - Ubuntu 24.04 shipped in April 2024. Orin got it only with JetPack 7.2 in mid-2026.
   - In the NVIDIA forum thread "JetPack 7 release date" (July 2025), users note that the roadmap moved Orin's 24.04 support from JetPack 7.0 to 7.2 in "Q1 2026". Later thread titles target Q2 2026.
   - On that history, a 26.04 JetPack for Orin and Thor is plausible around 2028 at the earliest. Until then, the Jetson flavor is a 24.04 island.
   - For ROS 2 Lyrical, that island is **Tier 3, build from source**. This is the **opposite** of the claim's main robotics support, on the one tier where robotics matters most.

**What this means for scoring:** both "main supports" are true for x86 with a discrete GPU and for the Pi 5. **Neither is true for Jetson.**
- The GPU Operator explicitly excludes Jetson.
- On Jetson's 24.04, Lyrical is Tier 3.

If C2 or C1 was scored as if "Ubuntu 26.04" described all three board families, the cell does not match its sources. Scorecard §5.6 then forces a re-score.

### B. "OneMind's own A/B image" is the least durable part of the stack, and the claim leaves it unscored

- The S2 interpretation of C1 is "the project's own release and support policy, its maintainer base and its funding".
- A home-built A/B mechanism maintained by one founder has a maintainer base of one, no external adopters (C4) and no published lifecycle. Under the C1 anchors for S2, that is 0–1.
- The competitors that took this route did not build their own:
  - HAOS uses RAUC.
  - umbrelOS uses Rugix.
  - Red Hat uses bootc and greenboot.
- Every runner-up in the claim (bootc, Debian + Rugix, Yocto + RAUC, Buildroot + RAUC, Fedora IoT) uses an update framework that **other organizations** maintain. The winner alone does not.
- On a 10-year horizon with a solo founder (M-6), the riskiest component for longevity belongs to the candidate ranked first.
- Note: Ubuntu could use RAUC or Rugix instead. If it does, the stack should be scored under that name, not as "own A/B".

### C. Canonical's own base layer has a recent record of regressions that hit update paths

These are the new failure sources:

- **Ubuntu 25.10:** the Rust coreutils `date -r` bug (Launchpad #2127970, duplicate #2129660, confirmed 2025-10-24) meant "unattended upgrades never run". Devices silently stopped taking security updates until someone ran `apt` by hand. For an unattended appliance fleet, that is exactly the failure mode that matters.
- **26.04 LTS** is the first LTS that ships rust-coreutils 0.8.0 and sudo-rs by default.
  - Canonical's own status post ("An update on rust-coreutils", 2026-04-22) says a Zellic audit found 113 issues and lists CVE-2026-35338 to CVE-2026-35381.
  - The same post says `cp`, `mv` and `rm` stay on GNU because of 8 open TOCTOU issues. Fully Rust coreutils is targeted for 26.10.
  - In the same thread, users report file-corruption and symlink issues in 0.8.0. These are community reports and are UNVERIFIED by Canonical.
- **Launchpad #2150073** (May 2026): sudo-rs on a 26.04 pre-release suspends `apt-get upgrade -y` in non-interactive SSH sessions. It "does not reproduce" with classic sudo. That is again an unattended-update path.

These are not reasons to rule Ubuntu out. Fallbacks exist, and OneMind's A/B image would not rely on `unattended-upgrades`. They do show three things:

- Canonical changes core userland mid-lifecycle, between LTS releases.
- The 26.04 LTS base is the least mature LTS for a decade in its core utilities.
- "Canonical is a big vendor" is not the same as "low update-path risk". In C3 and C1 terms, Ubuntu should not get credit simply for being Canonical.

### D. The Jetson advantage is eroding toward a runner-up

- From JetPack 7.2, NVIDIA's own Jetson Linux r39.2.1 developer guide says: "Beginning with JetPack 7.2, NVIDIA supports Yocto on Jetson platforms". It calls this "moving from a community-only model to an officially supported NVIDIA path" through OE4T.
- So "JetPack is Ubuntu" is no longer NVIDIA's only supported Jetson OS path. Yocto + RAUC (51.0) now has vendor-supported Jetson images, which may raise its C2 and C7 scores.
- The page states no support duration for the Yocto path either. Neither path has a published Jetson software lifecycle, so "only Ubuntu has a durable Jetson path" cannot be scored as an advantage.

### E. The margin is about one and a half anchor steps on one criterion

- With `total = Σ w·s / 5`, one anchor step is worth 4.0 points on C1 or C2, 3.0 on C3 or C4, and 2.0 on C5, C6 or C7.
- The lead over the joint runners-up is **6.0**.
- **If Ubuntu drops 1 step on C1** (for example, it cannot meet the C1-5 rule "covers OneMind's target boards" on Jetson, or the C1-4 rule "published price" for the device route, where Ubuntu Pro for Devices is "a one-time fee per device" with no amount published): 62 → 58. The gap is then **2.0, which is a tie** under the scorecard's under-3.0 rule. The decision moves to the decision-critical evidence.
- **If it also drops 1 step on C2** (the two main supports do not hold on Jetson) or on C4: 62 → 54 or 55. **bootc and Debian + Rugix (56) then win.**
- The 14-run weight-sensitivity test cannot detect this, because it varies weights, not cell scores. "Robust" here means robust to weights. It does not mean robust to the scoring of Ubuntu's Jetson cells.

## 3. Where the claim survives

- On x86 with discrete NVIDIA GPUs plus k3s, Ubuntu really is the only base the GPU Operator lists for K3s.
- Ubuntu 26.04 is ROS 2 Lyrical Tier 1 on amd64 and arm64.
- The Pi 5 is certified on 26.04.
- Canonical's archive lifecycle (ESM to 2036, Legacy to 2041) is the strongest published one in the candidate set.
- No runner-up has an equivalent of the x86 GPU Operator listing for K3s: RHEL is listed for Kubernetes and RKE2, and Debian is absent.

Ubuntu is therefore a defensible winner **for the x86 and Pi tiers**. What the evidence does not support is the claim's single label "Ubuntu 26.04 LTS" for all three tiers, and the 6-point margin built on it.

## 4. What would flip the decision

**Towards refuted:** any one of these, applied as a §5.6 re-score.

1. Ubuntu's C1 cell is shown to rest on Ubuntu Pro for Devices, which has no published price, or on 26.04 coverage that does not reach Jetson. **And** one more cell drops a step: C2 for Jetson (GPU Operator excludes Jetson, and Lyrical is Tier 3 on 24.04), or C4 or C3 for the home-built A/B. Ubuntu then falls to 54–55 and loses to bootc or Debian + Rugix at 56.
2. NVIDIA states that Jetson Linux r39 (Ubuntu 24.04) on Orin is supported only until a date before 2031, with no 26.04 JetPack on its public roadmap.
3. A Canonical statement that Ubuntu Pro does **not** cover the NVIDIA L4T kernel or BSP on Jetson.

**Towards upheld:** all of these.

1. A dated NVIDIA roadmap or release notes showing a JetPack on Ubuntu 26.04 for Orin and Thor, or a published Jetson Linux software support period to 2032 or later.
2. Canonical documentation, or a published price, showing that Ubuntu Pro (for Devices) covers the Jetson BSP kernel to 2034 or later.
3. The stack is re-specified as "Ubuntu + RAUC" or "Ubuntu + Rugix" rather than "OneMind's own A/B", so that the update framework has an external maintainer base.
4. The Jetson tier is scored as Ubuntu 24.04 + JetPack, with its own C1 and C2 cells, and Ubuntu still leads by 3.0 or more.

## 5. Sources

**Cited by the claim (re-opened):**
- NVIDIA cloud-native-docs@d856ea69d8d9138ac171f24e1f9d08df53448591:gpu-operator/platform-support.rst. Includes the line "NVIDIA Jetson … not supported".
- ros2/ros2_documentation@1c5c20cb9f14cbfec658690c44b70ca3d3ec81e7:source/Releases/lyrical/supported-platforms.rst. Noble is Tier 3, until 2029-06-01.
- https://ubuntu.com/about/release-cycle
- https://ubuntu.com/download/raspberry-pi

**New sources (failure, lag, lifecycle and regression evidence), all opened 2026-11-10:**

| # | Source | Type | What it shows |
|---|---|---|---|
| N1 | https://developer.nvidia.com/embedded/faq | PRIMARY | JetPack 7 = Ubuntu 24.04 with kernel 6.8. JetPack 6 is "sustaining". No software support duration is given. |
| N2 | https://developer.nvidia.com/embedded/lifecycle | PRIMARY | Hardware availability only: Orin to Jan 2032, AGX Orin Industrial to Jul 2033, Thor T4000 to Jan 2036. No software support period. |
| N3 | https://ubuntu.com/download/nvidia-jetson | PRIMARY | Canonical's Jetson images are 22.04 for Orin and 24.04 for Thor. **No 26.04.** |
| N4 | https://forums.developer.nvidia.com/t/jetpack-7-release-date/339956 | SECONDARY (user forum; staff status unconfirmed) | The roadmap moved Orin's Ubuntu 24.04 support to JetPack 7.2, and the target date slipped from Q1 to Q2 2026. |
| N5 | https://linuxgizmos.com/nvidia-jetpack-7-2-expands-support-for-nemoclaw-yocto-project-and-agx-orin-32gb-super-mode/ (2026-06-19) | SECONDARY | JetPack 7.2 brings Ubuntu 24.04 and kernel 6.8 to Orin, about 2 years after Ubuntu 24.04 shipped. |
| N6 | https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/AR/YoctoOnJetson.html | PRIMARY | "Beginning with JetPack 7.2, NVIDIA supports Yocto on Jetson platforms". No support duration is stated. |
| N7 | https://bugs.launchpad.net/ubuntu/+source/unattended-upgrades/+bug/2129660 | PRIMARY | Ubuntu 25.10: a Rust coreutils bug meant "unattended upgrades never run". Confirmed 2025-10-24. |
| N8 | https://discourse.ubuntu.com/t/an-update-on-rust-coreutils/80773 (2026-04-22) | PRIMARY (Canonical post) | 26.04 ships rust-coreutils 0.8.0. The Zellic audit found 113 issues (CVE-2026-35338 to 35381). `cp`, `mv` and `rm` stay GNU because of 8 open TOCTOU issues. |
| N9 | https://lists.snapcraft.io/archives/foundations-bugs/2026-May/548514.html (LP #2150073) | PRIMARY (bug report) | sudo-rs on a 26.04 pre-release hangs non-interactive `apt-get upgrade`. Classic sudo does not. |
| N10 | https://ubuntu.com/pro/devices | PRIMARY | Ubuntu Pro for Devices is "a one-time fee per device", with no amount published. No statement on Jetson or Pi coverage. |

**Marked UNVERIFIED (not used for scoring):**
- That a JetPack 6 → 7 move on Orin needs a reflash rather than an in-place rebase. If true, it weakens C1 anchor 4 ("in-place major-version rebase without reflashing") for the Jetson tier. The only source found was secondary.
