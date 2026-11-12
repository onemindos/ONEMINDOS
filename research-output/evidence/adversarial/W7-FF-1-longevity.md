# Refuter: W7 FF-1 (DC-08), longevity and vendor-risk lens

**Target:** FF-1 in `08-robotics-drones-physical-ai.md`, which says NVIDIA commits to Jetson hardware availability (Orin to Jan 2032, AGX Orin Industrial to Jul 2033, T5000 to Aug 2035, T4000 to Jan 2036) but publishes no software-support period per Jetson Linux release. It gives observed branch lifetimes of about 5.7 years (r32) and "4.5+ years and counting" (r35). Consequence: D2 holds, and the CRA support period has to be planned on observed history plus at least one in-field branch upgrade.
**Cited claims read:** C-W7-001 to C-W7-005.
**Refuter:** REF-W7-longevity · 2026-11-10 · I read only the conclusion and its sources, not the author's reasoning or the other adversarial files.

## Verdict: WEAKENED

The core finding stands: NVIDIA states no software-support period, and the plan should not depend on a vendor promise. The evidence behind it is out of date, though, and the proposed bridge is incomplete.

1. **"r35 and counting" is no longer true.** NVIDIA declared JetPack 5 end of life on 30 Oct 2026. JetPack 5.1.8 / Jetson Linux R35.7 is the final release, and "you will no longer receive any critical updates" [C-REF-W7L-001]. r34/r35 ran from Apr 2022 to Oct 2026, a closed life of about 4.5 years. That is shorter than r32, so branch life is falling (5.7 → 4.5 years).
2. **Branch length is the wrong number to plan on.** The number that matters is when the last branch a module supports reaches EOL, measured against the date that module stops shipping. In every case so far, NVIDIA's software EOL has come **before** its own hardware availability date:
   - **Nano, TX2 NX, TX2i:** JetPack 4 ended in Nov 2024 with no further critical updates [C-REF-W7L-002]. These modules stay available until Jan 2027 (Nano) and Jul 2027 (TX2 NX/TX2i) [C-REF-W7L-004]. That is about 26 to 32 months on sale with no vendor kernel support.
   - **AGX Xavier, Xavier NX:** EoL on JetPack 5.1.8 as of Oct 2026 [C-REF-W7L-001]. These modules stay available until Jul 2027 by the lifecycle page, or Jan 2028 by the FAQ, which disagrees with the lifecycle page [C-REF-W7L-004][C-REF-W7L-005]. That is about 9 to 15 months.
   If Orin follows the same pattern, its software ends before its Jan 2032 availability date. A unit built in OneMind's last production year could ship with no vendor support left.
3. **The "in-field branch upgrade" only works while NVIDIA ports the module to the next branch.** Nano/TX2 stopped at JetPack 4, and Xavier stopped at JetPack 5 [C-REF-W7L-001][C-REF-W7L-002]. For each module, at most N−1 upgrades exist, and NVIDIA decides N. Today Orin is on r35, r36 and JetPack 7 [C-REF-W7L-001], so the bridge exists for Orin for now, but nothing commits NVIDIA to it.
4. **Security fixes reach only the live branches, and slowly.** The Oct 2025 bulletin (CVE-2025-33182/-33177) lists fixes for 35.6.3, 36.4.7 and 38.2.2 only, and doesn't mention r32 [C-REF-W7L-003]. On the forum, the 36.4.7 fix broke cameras, NVIDIA acknowledged a fix "side effect" in Dec 2025, and users were still asking for archive tarballs in Jan 2026 [C-REF-W7L-006]. When the conclusion says "observed lifetime," it does not mean a usable patch stream for every module.
5. **Bridges after EOL are partial or paid.** Canonical's ESM for JetPack 4 covers only the 18.04 userspace, until 2028. It says the 4.9 Jetson kernel "remains outside of the scope," and that migration is the long-term path [C-REF-W7L-007]. For JetPack 5, NVIDIA refers users to a paid ecosystem partner (RidgeRun) [C-REF-W7L-001]. The cost is unknown.

## Strongest counter-argument

NVIDIA's history is not "observed history plus one upgrade gives a usable support period." It is "software for a module dies 1 to 3 years before NVIDIA stops selling it, and branch lifetimes are getting shorter." A CRA support period anchored to any Jetson module's availability date is, on NVIDIA's record, a period that OneMind alone pays for: maintaining the kernel itself, or buying RidgeRun-style sustaining support. That is a recurring vendor cost, and the D2 scoring should account for it.

## What survives

D2 does not flip. The alternative bases (DC-09) still run NVIDIA's kernel and out-of-tree modules, so changing the base doesn't remove the dependency. Orin is supported on JetPack 7 today, which gives a live upgrade path.

## Required corrections to the conclusion

- Change "r35: 4.5+ years and counting" to "r35: ~4.5 years, EOL 30 Oct 2026 (JetPack 5.1.8 / R35.7)", and update C-W7-005's `support_end`.
- State the support period per module: `support_end = EOL of the last JetPack branch NVIDIA ports this module to`. Plan for that to fall **before** the hardware availability date. Budget either OneMind kernel maintenance or a paid sustaining contract from that date to the CRA end date.
- Make the in-field upgrade conditional: "if NVIDIA ports the module to the next major release, as it has for Orin up to JetPack 7."

## What would flip this

- **Back to upheld:** a written NVIDIA statement (for example through Inception) of a software or security support end date per module or per branch that reaches the hardware availability date. Or Orin JetPack 7.x support continuing until at least Jan 2032.
- **To refuted (D2 at risk):** NVIDIA dropping Orin from the JetPack 7 or next-major line before about 2029, an Orin security bulletin with no fixed version on a supported branch, or a sustaining-contract quote too large for the CRA budget.

## Sources opened
- https://forums.developer.nvidia.com/t/announcing-end-of-life-for-nvidia-jetpack-5-with-the-release-of-jetpack-5-1-8/387449
- https://forums.developer.nvidia.com/t/announcing-end-of-life-for-nvidia-jetpack-4-with-the-release-of-jetpack-4-6-6/314300
- https://nvidia.custhelp.com/app/answers/detail/a_id/5716
- https://forums.developer.nvidia.com/t/jetpack-releases-with-security-fixes-cve-2025-33182-cve-2025-33177/347678
- https://ubuntu.com/blog/jetpack-4-eol
- https://developer.nvidia.com/embedded/lifecycle
- https://developer.nvidia.com/embedded/faq
