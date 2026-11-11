# DC-08: refuter report on the Jetson BSP and module lifecycle (technical lens, round 4)

- **Conclusion under test (decision-critical DC-08 Result, rev. 3; 01 §4.1 "Jetson support period"):** NVIDIA publishes no per-branch security window. Per module, `support_end` = EOL of the last JetPack branch NVIDIA ports it to; budget every JetPack major and every security point release. Not flipped, because "an affordable bridge exists (in-field branch upgrades, meta-tegra's LTS route)".
- **Flip condition:** the security window per L4T release is shorter than the support period OneMind must declare, **with no affordable bridge**.
- **Lens:** technical. I read only the conclusion, 01 §4.1 and the cited claim C-REF-W7L-001. I formed this view before reading any other refuter file.
- **Date:** 2026-11-11

## Verdict: **weakened** (the support_end rule stands; the "affordable bridge" that keeps DC-08 from flipping is not demonstrated)

The rule "support ends with the last branch the module is ported to" is sound and conservative. The part that holds the flip off is the bridge, and its two legs are both unproven:

1. **In-field branch upgrade.** No NVIDIA source I found documents a supported, console-free JetPack 6 → JetPack 7.2 (r36 → r39) upgrade for production Orin modules that also moves QSPI firmware. NVIDIA's own recommended route to r39.2.1, even on its developer kit, is **Jetson ISO**: it needs r35.5 or later installed, may stop to ask for a "required" QSPI capsule update ("press Y … Do not skip this prompt"), and ends in `oem-config`. It does not say whether data survives [C-REF4-DC-technical-003]. When a 2,000-unit Orin NX fleet that cannot be serviced on site asked exactly this, NVIDIA staff said only that it "should be supported" as JP5 → JP6 was, through image-based OTA. The QSPI question was left unanswered [C-REF4-DC-technical-002]. "Budget an in-field upgrade to each new JetPack major" therefore budgets something NVIDIA has not committed to.
2. **NVIDIA's dates cannot be used even as estimates.** NVIDIA's own roadmap (Dec 2023, reproduced by RidgeRun) put JetPack 5's EOL in Q4 2027 and JetPack 6's in Q3 2028 [C-REF4-DC-technical-001]. JetPack 5 actually ended on 2026-10-30 [C-REF-W7L-001], about a year early. So JetPack 6's "Q3 2028" may also come early. A planner who fills `support_end` from NVIDIA estimates overstates it.

meta-tegra's LTS route, the second leg, is an "evaluated target" gated on LAB-W7-6 (01 §4.1), not a bridge in hand.

## Strongest counter-argument

OneMind cannot declare a CRA support period for a Jetson SKU at ship time. The branch's end date is unpublished and arrives early. The only way past it, a major-branch upgrade, has no documented console-free path that covers QSPI on production modules, and NVIDIA's reference path is an interactive ISO reinstall. Until a lab proves r36 → r39 image-based OTA on an A/B (`ROOTFS_AB=1`) production module with QSPI updated and data kept, the declared period for an Orin SKU has to be "remaining life of the current branch" alone. Under DC-08's own flip condition, that is short enough to flip, unless a paid sustaining contract (RidgeRun-style, C-REF-W7L-001) is priced into DC-03/DC-04.

## New sources (searched for lifecycle cuts and upgrade failures; each opened)

- **N1.** RidgeRun, *JetPack 6 Migration and Developer Guide: Versions and Support* (NVIDIA roadmap figure, estimates of Dec 2023; page edited 2025-06-07). [C-REF4-DC-technical-001]
- **N2.** NVIDIA Developer Forums, "Updating major Jetpack releases OTA" (Dec 2025). [C-REF4-DC-technical-002]
- **N3.** NVIDIA, *Jetson AGX Orin Developer Kit User Guide: Quick Start* (Jetson ISO to r39.2.1). [C-REF4-DC-technical-003]

Not used: an LLM-generated forum reply in N2 claiming image-based OTA handles partition-layout changes (no staff confirmation).

## What would flip this verdict

- **To upheld:** NVIDIA documents a supported r36 → r39 image-based OTA for production Orin modules, including QSPI, and a OneMind lab runs it unattended on an A/B module with data kept. Or NVIDIA publishes per-branch end dates and meets them.
- **To refuted:** the lab upgrade fails or needs USB/console on production modules, **and** no sustaining contract fits the DC-03 budget. Or JetPack 6 is ended before mid-2028 while r39 upgrade remains unproven for Orin NX/Nano.

## Recommended change (for the owner, not applied)

Add a founder test: **r36.5 → r39.2 image-based OTA on a production Orin NX with `ROOTFS_AB=1`**, unattended, with QSPI version checked before and after. Until it passes, declare Jetson support periods from the current branch alone, and record NVIDIA roadmap dates as "estimate, has been missed early".
