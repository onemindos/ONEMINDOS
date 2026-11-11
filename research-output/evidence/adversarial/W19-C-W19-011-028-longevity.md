# W19 · C-W19-011…028 (ecosystem comparators): refuter, longevity and vendor-risk lens

**Target conclusions** (`29-PLATFORM-ECOSYSTEM-MARKETPLACE.md` §0 lesson 2, §4 comparator table rows 127–137, §5 incident table rows 153–157, §8.4, §9; DC-16 in `evidence/decision-critical.md`): OneMind should copy proven ecosystem controls: the HACS "critical" list as the kill-switch pattern ("High for the kill-switch pattern") [C-W19-015], Home Assistant's Bronze–Platinum quality scale [C-W19-018], Works with Home Assistant as the certification template [C-W19-020], VS Code Marketplace's supply-chain controls ("copy all of it") [C-W19-023], CI-only OIDC trusted publishing as the npm lesson [C-W19-026], and Omarchy's manifest shape for desktop plugins [C-W19-010…013]. Incidents [C-W19-025…028] are the failure cases.

**Verdict: WEAKENED (group).** Every cited fact checks out where I could re-open it. Three of the *inferences* drawn from them do not survive a look at how those mechanisms behaved over time.

## Strongest counter-argument
The comparator table judges each ecosystem by what its controls look like today. It does not ask whether those controls were used, kept, or survived their owner's incentives. Three things the table rates "high" fail that test:
1. **The HACS kill switch has never been used for real.** The `critical` file in `hacs/default` holds one entry, `test/test`. It was created and last changed on 2019-11-01 [C-REF-W19-longevity-001]. That is still true at the commit W19 pinned. HACS handled 551 removals [C-W19-014] by delisting, not by force-uninstalling. The code path exists. The operational practice behind a "pattern" does not. A kill switch nobody has used in seven years has unknown false-positive, appeal and recovery behaviour. OneMind would be designing those from nothing, not copying them.
2. **The HA quality scale was reset once already.** In November 2024 Home Assistant replaced its 2020 scale because it "was never updated." It **dropped the existing ratings of every integration**, which had to file a PR to regain a tier [C-REF-W19-longevity-002]. The 20/10/21/3 rule counts [C-W19-018] are a snapshot of a scale under active revision. A Bronze–Platinum ladder that boxes, store listings and "Works with OneMind" contracts depend on will need a versioning and migration policy. The ladder copied from HA does not provide one.
3. **Trusted publishing became the attack path.** 29 §5 turns Shai-Hulud [C-W19-026] into "publish only from CI with OIDC trusted publishing." In the May 2026 TanStack wave, attackers poisoned a GitHub Actions cache, took the OIDC token from runner memory, and shipped packages with valid SLSA L3 provenance. A June 2026 wave abused the OIDC publish endpoint directly [C-REF-W19-longevity-006]. Each npm control was answered within months. A control list frozen at schemaVersion 1 ages the same way.

Two vendor-risk points the table also misses:
- **A central marketplace is a vendor lever.** VS Code's terms had limited Marketplace use to Microsoft products since 2020. They were enforced in April 2025, when C/C++ extension v1.24.5 began refusing to run in forks such as Cursor and VSCodium [C-REF-W19-longevity-003]. "Copy all of it" [C-W19-023] includes the power to lock out downstreams. That matters for a sovereignty-first OS whose users may fork it (MISSION). The ACF→SCF case [C-W19-028] is the same lesson. OneMind's countersignature (E9) gives OneMind that lever too.
- **The registry operator's commitment is the weakest link.** Open VSX, the open registry this table offers as the alternative, is "free to use, but not free to operate." Costs "scale directly with usage," and it had to bring in tiered rate limits in 2026 [C-REF-W19-longevity-004]. Automattic cut its sponsored WordPress contributions to about 45 h/week in January 2025, citing lawsuits [C-REF-W19-longevity-005]. A store's review, scanning and kill-list duties last only as long as someone pays for them. 29 does not cost or escrow them.

## Per-claim check
| Claim | Verdict | Note |
|---|---|---|
| C-W19-011, 012, 013 (Omarchy) | upheld | Longevity risk is *lower* than "Young" suggests: 500+ plugins by 2026-08-19, and a funded Omacom Foundation [C-REF-W19-longevity-007] (the funding headline and slug disagree: 23.7M vs 8M). The manifest is cited from the `quattro` branch, so schemaVersion 1 should be rechecked against a tagged release before OneMind adopts the shape. |
| C-W19-014 | upheld | Counts are correct as a snapshot. |
| C-W19-015 | **weakened** as a template | Code fact is true. The list has never held a real entry [C-REF-W19-longevity-001]. HACS's codeowner is one person (`@ludeeus` in the manifest), so its continuity is not a model either. |
| C-W19-016, 017, 019 | upheld | |
| C-W19-018 | **weakened** as a frozen ladder | Scale reset and ratings dropped in 2024 [C-REF-W19-longevity-002]. The docs domain has since moved to `contributors.home-assistant.io` (301) [C-REF-W19-longevity-012], so the citations need rechecking. |
| C-W19-020 | upheld | No contrary evidence found. Fee and terms are annual and should be rechecked. |
| C-W19-021, 022 | upheld | 022 stays `partial` (ARCHIVE-GAP). |
| C-W19-023, 024 | **weakened** as "copy all of it" | Marketplace lock-out of forks [C-REF-W19-longevity-003]. |
| C-W19-025 | upheld, omission | Add the registry-cost lesson [C-REF-W19-longevity-004]. |
| C-W19-026 | **weakened** as mitigation | Trusted publishing was itself the vector in 2026 [C-REF-W19-longevity-006]. |
| C-W19-027 | upheld | Still SECONDARY. |
| C-W19-028 | upheld, strengthened | Governance risk includes the operator withdrawing [C-REF-W19-longevity-005]. |

## New sources (searched for abandonment, lifecycle cuts, regressions)
See `evidence/claims/REF3-W19-longevity.csv`, C-REF-W19-longevity-001…007, 012. All were opened. 006 is a security-vendor blog (SECONDARY).

## What would flip it
- **To upheld:** evidence that HACS (or HA core's `BLOCKED_CUSTOM_INTEGRATIONS`) has force-removed real installs at scale without harm, and a written OneMind ladder-versioning policy (how a tier survives a rule change).
- **To refuted:** a costed plan showing OneMind can't staff review, scanning and kill-list operation at all. Every copied control would then be decorative.
- **Further weakening:** another trusted-publishing or provenance bypass that defeats the 29 §5 control list as written.

**Recommendation to the author (not applied):** relabel HACS's row as "kill-switch *code path*; never exercised." Add "ladder version + migration rule" to the quality-tier design. Add "OIDC publish + CI hardening (no `pull_request_target`, cache isolation), plus delay-before-promote" to 29 §5. Add an escrow or continuity line for store operations.
