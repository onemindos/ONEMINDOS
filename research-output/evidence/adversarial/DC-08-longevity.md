# DC-08 · Jetson BSP and module lifecycle — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-08 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
NVIDIA publishes no per-branch security window; per module, support_end = EOL of the last JetPack branch NVIDIA ports it to; JetPack 5 ended 2026-10-30 [C-REF-W7L-001]. **Not flipped**: an affordable bridge exists (in-field branch upgrades, meta-tegra's LTS route).

## Strongest counter-argument
The "bridge" depends on NVIDIA porting each module to the next branch on time, and the record shows the port lags while the old branch is closed.

1. **Orin waited on the new branch.** JetPack 7 shipped for Thor first; Orin's port was on NVIDIA's roadmap for Q1 2026 and arrived as JetPack 7.2 in early June 2026 [C-REF4-DC-longevity-011]. Then JetPack 5 was closed on 2026-10-30, with Xavier left on its final release and ongoing maintenance referred to a paid partner (RidgeRun) [C-REF-W7L-001]. The pattern — new silicon first, older modules ported late, oldest branch cut with a partner referral — means a module's *effective* security window is "until NVIDIA stops porting it", which nobody can put in a CRA declaration today.
2. **The community bridge is now partly NVIDIA's.** From JetPack 7.2 NVIDIA "supports Yocto on Jetson", aligned with OE4T, but states no lifetime and no module list [C-REF4-DC-longevity-012]. That improves today's maintenance, but it also ties meta-tegra's cadence to NVIDIA's branches: when NVIDIA stops a module, the layer's binary blobs (firmware, CUDA, TensorRT) stop too. meta-tegra itself has about three active maintainers [C-REF4-DC-longevity-013], so it is not a 10-year guarantee either.

## Why it does not flip
The flip needs a security window shorter than OneMind's declared period **with no affordable bridge**. In-field branch upgrades are real (Orin did get 7.2 [C-REF4-DC-longevity-011]), NVIDIA's Yocto commitment lowers the cost of the meta-tegra route, and a paid partner exists for the tail. The bridge is affordable but **not schedulable**.

## Verdict: **weakened**
- Required change: the CRA support period for any Jetson SKU must be declared per module as "until the last JetPack branch NVIDIA ports this module to, plus N months", with the RidgeRun-style paid tail priced in `lifecycle-cost-2036.md`.
- Required change: plan for a 6–12-month gap between a new JetPack branch and its arrival on older modules.

## What would flip this verdict
- **To upheld:** NVIDIA publishing a per-module software support end date (e.g. on the Jetson lifecycle page) or a security-support statement for JetPack 7.x.
- **To refuted:** NVIDIA declining to port Orin to the branch after 7.x while JetPack 7 closes, with no partner offering arm64 kernel and CUDA fixes at solo-company cost.

## Sources opened (new)
- https://forums.developer.nvidia.com/t/is-the-q2-2026-release-target-of-jetpack-7-on-orin-still-accurate/369201 [C-REF4-DC-longevity-011]
- https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/AR/YoctoOnJetson.html [C-REF4-DC-longevity-012]
- GitHub API, OE4T/meta-tegra commits since 2025-11-11 at 80f9e27f [C-REF4-DC-longevity-013]
