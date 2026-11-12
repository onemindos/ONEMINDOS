# DC-06 · Rugix's bus factor and maturity — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-06 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
Rugix's bus factor is about one (303 of 304 commits in a year) [C-W3-001]; **the flip to RAUC is taken**; Mender is the lab-passed runner-up; Rugix stays the documented alternative.

## Strongest counter-argument
Applied evenly, the same test that removed Rugix also flags RAUC and Mender — the flip trades a one-person risk for a one-company risk without saying so.

1. **RAUC is two engineers at one firm.** In the same 12-month window, 441 of 511 RAUC commits (about 91% of non-bot commits) came from two maintainers who both list Pengutronix as their employer [C-REF4-DC-longevity-008]. If Pengutronix re-prioritises, RAUC's maintenance concentration is comparable to Rugix's in practice.
2. **The runner-up has a short, moving support window and packaging accidents.** Mender Client 5.0 (2025-01) was EOL by 2026-09, Client 6.0 is supported only until 2027-04, and the policy guarantees just "at least 6 months" after a new LTS [C-REF4-DC-longevity-009]. Client 4.0.0 was pulled for a Debian packaging fault, and the old APT repository was removed, breaking fielded installs with 403s [C-REF4-DC-longevity-010]. A 10-year fleet on Mender faces roughly yearly forced client migrations.

## Why it is still upheld
The flip rule was "single-maintainer bus factor **with no second adopter**, while RAUC is comparable on features". RAUC differs from Rugix on exactly the missing term: it has long-running independent adopters (HAOS and others, already cited in W3), a company whose business is embedded Linux services, an on-disk bundle format and C code that other teams can maintain, and rev. 3 already pins OneMind's own build from an upstream tag. Two maintainers at a stable consultancy is a real but lower risk than one maintainer at a startup. The direction of the flip is right.

## Verdict: **upheld** (with a disclosure fix)
- Required change: record RAUC's concentration (two Pengutronix maintainers, ~91%) in the risk register beside Rugix's, with the exit already designed (engine-neutral layout; Mender lab-passed).
- Required change: if Mender stays runner-up, budget a client upgrade at least yearly (support windows of 12–16 months).

## What would flip this verdict
- **To weakened:** Pengutronix reducing RAUC maintenance (maintainer departures, no release for 12 months), or evidence that HAOS plans to leave RAUC.
- **To refuted:** Rugix gaining a second active maintainer from another organisation plus a named second adopter with public code, while RAUC loses one of its two maintainers.

## Sources opened (new)
- GitHub API, rauc/rauc commits since 2025-11-11 at 2d17b270 [C-REF4-DC-longevity-008]
- https://docs.mender.io/release-information/supported-releases [C-REF4-DC-longevity-009]
- https://docs.mender.io/troubleshoot/mender-client [C-REF4-DC-longevity-010]
