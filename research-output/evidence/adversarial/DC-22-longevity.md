# DC-22 · Platform first, or own image first? Refuter, longevity and vendor-risk lens

**Target conclusion** (`28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md` §8): D1 ("ship our own image") stands, sequenced in three steps. In weeks 1–4, Core installs by script onto Debian 13. From week 3, the same layers produce the Rugix image. The image ships only after the rollback spike passes, and **the script install stays as the preview channel** and the BYO path (P-7). Cited history: HA platform first [C-W18-062]; Umbrel image first [C-W18-063]; Start9 image first; CasaOS script then ZimaOS image; Olares script only [C-W18-064].

**Verdict: WEAKENED, on the dual-channel part, not on D1.** Repo creation dates show which product came first. They don't show what happened to the non-image path afterwards. In the three cases checked, it was cut or left to stagnate because of support cost.

## Strongest counter-argument
The answer treats "script install + image from one source" as nearly free. The longevity record says otherwise: every constraint-matched competitor that ran both paths later killed or abandoned the non-image one. A solo developer keeping a script channel on BYO Linux takes on the support matrix that HA, a team far larger than OneMind, chose to drop. The script channel should get an explicit sunset rule, or be scoped as developer-only and never offered as a supported BYO path.

## New sources (searched for abandonment and deprecation)
1. **Home Assistant** deprecated the Core and Supervised install methods on 2025-05-22, at 2.5% and 3.3% of installs, and ended support with 2025.12. The stated reason: they "generate more issues that are more difficult to solve" [C-REF-DC-longevity-004]. The "platform first" exemplar ended up image (plus container) only.
2. **Umbrel** dropped install-by-script on Linux at 1.0: "we have decided not to support it in favor of offering increased system reliability and stability" [C-REF-DC-longevity-005]. Linux-script users were never given an upgrade path to 1.0.
3. **CasaOS**, the installer that preceded ZimaOS: last stable release v0.4.15 (2024-12-19), with nothing since an April 2025 alpha. The repo is still pushed, but the company's effort went to the image product [C-REF-DC-longevity-006].

## What would flip it
- **Toward the author's plan:** evidence that a constraint-matched appliance kept a supported script/BYO path alongside its image for more than 3 years at low issue volume. None was found among HA, Umbrel or CasaOS/Zima.
- **Toward dropping the script channel entirely:** issue-tracker data showing installer-path issues outweigh image-path issues, like HA's ratio.
- D1 itself would flip only if the image-first gate (the W3 rollback spike) slips past the 180-day plan while the script preview has real users.

**Recommendation (not applied):** keep the weeks 1–4 script install as a *developer loop* on a VM, and keep its sunset in the plan as written: "preview until image GA, unsupported after". Treat BYO hardware (P-7) as "flash our image on your x86 box", not "run our script on your distro". That was Umbrel's end state.
