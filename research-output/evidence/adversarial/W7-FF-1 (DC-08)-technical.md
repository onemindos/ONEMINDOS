# W7 — Refuter report: FF-1 (DC-08), technical lens

- **Claim under test (FF-1):** NVIDIA commits Jetson **hardware** availability (Orin to Jan 2032, AGX Orin Industrial to Jul 2033, T5000 to Aug 2035, T4000 to Jan 2036) but publishes **no software-support period** per Jetson Linux release. Observed branch lifetimes are about 5.7 years (r32) and 4.5+ years and counting (r35). Implication: plan the CRA support period on observed history plus at least one in-field branch upgrade, not on a vendor promise.
- **Cited claims:** C-W7-001 … C-W7-005.
- **Refuter lens:** technical. Read only the conclusion and its sources (RESEARCH-MISSION.md §2 rule 7).
- **Date:** 2026-11-10

## Verdict: **weakened**

The facts hold: the hardware dates and the absence of a software-support statement are confirmed. **The planning heuristic built on them is too optimistic.** "Observed branch lifetime" is the wrong unit, for three reasons:

1. Software support on a branch ended **years before** the hardware it supports stopped shipping.
2. NVIDIA has also shipped short-lived branches.
3. Within a live branch, fixes land only in the newest point release, and at least one fix was incomplete.

"One in-field branch upgrade" understates the work. The real bridge is "track every JetPack major release and the latest point release of it".

## Checks of the cited sources (opened 2026-11-10)

| Sub-claim | Source | Result |
|---|---|---|
| Orin Jan 2032, AGX Orin Industrial Jul 2033, T5000 Aug 2035, T4000 Jan 2036 (C-W7-001/002) | developer.nvidia.com/embedded/lifecycle | **Confirmed.** The same page also lists Jetson Nano "available through" **Jan 2027**, and Xavier NX/AGX Xavier/TX2 NX through **Jul 2027**. |
| No software-support duration; EOL notice at least 8 months before last shipment (C-W7-003) | same | **Confirmed.** The quote is "Official End of Life notice will be sent a minimum of 8 months prior to the last shipment". That notice covers hardware only. |
| r32: 32.1 (Mar 2019) to 32.7.6 (Nov 2024) (C-W7-004) | developer.nvidia.com/embedded/jetson-linux-archive | **Confirmed.** |
| r34/r35: 34.1 (Apr 2022) to 35.7.0 (Oct 2026) (C-W7-005) | same | **Confirmed**, but r34 itself lasted only Apr–May 2022 (34.1, 34.1.1). The archive also shows **r38 at Aug 2025 → Jan 2026 (38.2, 38.2.1, 38.4)**, superseded by r39 (Jun 2026). |

## New sources (found by searching for EOL, CVEs and lifecycle cuts; all opened)

- **N1. NVIDIA forum, "Announcing End of Life for NVIDIA JetPack 4 with the release of JetPack 4.6.6"** (https://forums.developer.nvidia.com/t/announcing-end-of-life-for-nvidia-jetpack-4-with-the-release-of-jetpack-4-6-6/314300, 2024-11-22). JetPack 4.6.6 "was released today" and "marks the final release for JetPack 4 series". After EOL, users "will no longer receive any critical updates". It covers Jetson Nano, TX2 and TX1. For maintenance beyond 4.6.6 it points to the paid partners TimeSys and Codethink. **The software EOL was announced the same day as the last release, with no advance notice.**
- **N2. Canonical, "JetPack 4 EOL"** (https://ubuntu.com/blog/jetpack-4-eol, 2025-07-03). Ubuntu Pro ESM covers the 18.04 userspace until 2028, but "The JetPack 4 kernel (based on the Linux kernel 4.9) remains outside of the scope of the service." Third-party help does not cover the BSP kernel.
- **N3. NVIDIA Security Bulletin, Jetson and IGX, March 2026** (https://nvidia.custhelp.com/app/answers/detail/a_id/5797/, rev 1.0, 2026-03-31). It covers CVE-2026-24148 (8.3), CVE-2026-24154 (7.6) and CVE-2026-24153 (5.2), with fixes only at the head of each branch: 35.x "prior to 35.6.4", 36.x "prior to 36.5", and 38.x fixed in 38.4. r32 is absent, which is consistent with N1.
- **N4. ONEKEY advisory, secure-boot bypass on Jetson for Linux** (https://www.onekey.com/resource/security-advisory-secure-boot-bypass-on-nvidia-jetson-for-linux, 2026-09-03). This is a bypass of the CVE-2026-24153 fix, so the earlier fix was incomplete. Affected: 39.2.0, 38.4.0, 38.2.x, 36.5.0 and 35.6.4. Fixed: 39.2.1, 36.5.2 and 35.6.5. **38.x had no confirmed fix at publication.** NVIDIA declined to share its private advisory. The timeline from report to patch was about 3.5 months (May 20 to Aug/Sep). This is a vendor research blog (SECONDARY to NVIDIA). No CVE ID had been assigned at publication.

## Strongest counter-argument

**Hardware availability is not a floor for software support, and branch lifetime is not a floor for any given SKU.** Across the cited pages and N1:

- **Jetson Nano** can be bought until **Jan 2027**, and **TX2 NX** (r32 only) until **Jul 2027**. Yet r32 got its final release in **Nov 2024**, and NVIDIA said there would be no further critical updates (N1). Hardware a customer can still buy new has gone **26–32 months without vendor software support**, and the BSP kernel (4.9) is outside even Canonical's ESM (N2). A CRA support period anchored to "availability through" dates would already be in breach for these SKUs.
- **The software EOL came with zero notice** (N1: the final release and the EOL notice came on the same day). The 8-month notice in C-W7-003 applies only to hardware.
- **Not every branch lasts 4.5+ years.** r34 lasted about 1 month. r38, the first Thor branch, lasted about 5 months before r39, and it had no fix for N4 when that issue was disclosed. A Thor product that shipped on r38 had to make a branch change within a year to stay patched. The 5.7-year and 4.5-year figures are survivorship: they are the two long LTS-style branches, not the distribution of branch lifetimes.
- **Patch only at branch head, and fixes can be incomplete** (N3, N4). Staying "on a branch" is not enough. Every security fix means moving to the newest point release (35.6.4 → 35.6.5, 36.5.0 → 36.5.2). Each one requires a full image rebuild and test, at a cadence NVIDIA sets.

What survives: the bridge exists. r39 (JetPack 7.2) supports Orin as well as Thor, so an Orin fleet has a branch to upgrade to. The core of FF-1 ("no vendor promise; plan your own bridge") is correct.

## Required corrections to the conclusion text

- Replace "observed branch lifetimes are about 5.7 years (r32) and 4.5+ years" with the full record: "r32 about 5.7 years and r35 4.5+ years, but r34 about 1 month and r38 about 5 months. r32 ended about 2–2.7 years before the hardware it supported stopped shipping, with no advance software-EOL notice."
- Replace "at least one in-field branch upgrade" with "an in-field upgrade to each new JetPack major release, plus rollout of every security point release at branch head. Budget for both for the whole support period."
- Add: "Hardware 'available through' dates must not be used as, or assumed to bound, the software-support end."

## What evidence would flip the decision

- **Toward upheld as written:** NVIDIA publishing a per-branch software/security support period (for example "each JetPack major release receives security updates for N years"), or a written answer through Inception (open question 4) that covers the SKU's full availability window.
- **Toward refuted, so that DC-08's flip condition triggers:** NVIDIA ending r36/r39 support for Orin while Orin modules are still sold (before Jan 2032) with no successor branch that supports Orin. Or, a second instance of a security fix not shipped to a branch that still has hardware on sale (the N4 38.x gap would count if r38 never gets a fix). Either would mean the "affordable bridge" does not exist for that SKU.
