# W3 Tier A decision refuter: "RAUC replaces Rugix as lead engine" (longevity and vendor risk)

| Field | Value |
|---|---|
| Claim | `01-FOUNDATION-DECISION.md`, executive point 3 and the D3 row. The update engine changes from Rugix to RAUC because "Rugix is excellent but is written by essentially one person (303 of 304 commits in a year [C-W3-001]); RAUC runs Home Assistant OS". Both engines passed the lab's rollback and power-cut tests [C-LAB-rauc-015, C-LAB-rauc-017, C-LAB-debian-rugix-022]. The layout stays engine-neutral. RAUC must be ≥ 1.15.2 and use verity bundles only [C-DEC-004]. "RAUC and Mender both have multi-author bases." |
| Lens | Longevity and vendor risk to the 2036 horizon |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter saw only the conclusion text and the cited sources. |
| Date | 2026-11-11 |
| Verdict | **upheld**, with two wording corrections |

## 1. Re-checking the cited sources

- **C-W3-001:** reproduced [C-REF-W3-longevity-002].
- **C-DEC-004:** the CHANGES file and the advisory agree. CVE-2026-34155 affects only plain bundles below 1.15.2, and verity bundles are unaffected [C-REF-W3-longevity-008]. The "≥ 1.15.2, verity only" condition is the right mitigation.
- **The lab claims** are outside this lens and were not re-run.
- **"Multi-author base":** not supported for RAUC as worded. 89% of its commits come from one company and 86% from two people [C-REF-W3-longevity-001].

## 2. Strongest counter-argument

The switch trades a one-person vendor for a two-person vendor, and it pays a real convenience cost: Rugix's image builder and state management. Rugix is permissively licensed and forkable, and Umbrel is engaged with it. The founder could keep Rugix and take on the bus-factor risk as a fork contingency. On top of that, neither engine publishes support beyond its latest release [C-REF-W3-longevity-004, -008], and both had a high-severity signing-path bug in 2026 [C-REF-W3-longevity-003, C-DEC-004].

## 3. Why the decision still holds on this lens

- **Track record and adopters.** RAUC has 10 years of releases. Its adopters include HAOS (verifiable in code) and, per Pengutronix, Valve's Steam Deck, IKEA Dirigera and German rail [C-REF-W3-longevity-007]. If Pengutronix faltered, those are well-funded parties that would keep RAUC alive. Rugix's equivalent is Umbrel, a much smaller company.
- **Who finds the bugs.** RAUC's 2026 CVE was found by Sony [C-REF-W3-longevity-008]. Rugix's 2026 advisories show that a design flaw in the signing path survived about two years in a codebase with one reviewer [C-REF-W3-longevity-003].
- **No paid-tier lock-in.** Pengutronix publicly rules out an enterprise edition and relicensing [C-REF-W3-longevity-006]. Silitics' promises cover licensing but not succession, and the Rugix name is a Silitics trademark [C-REF-W3-longevity-005].
- **The exit stays cheap.** The engine-neutral layout keeps the decision reversible by an update. That is the strongest longevity mitigation available, and it applies in both directions.

## 4. Corrections the author should make (wording, not the decision)

1. **Replace "RAUC and Mender both have multi-author bases"** with "RAUC is maintained by Pengutronix, mainly by two engineers, with a 10-year record and large adopters".
2. **State that neither engine publishes support beyond its latest release.** Keep the "≥ 1.15.2" floor, and add a rule to track RAUC's latest release within N days.
3. **Cite stronger adopters.** "RAUC runs Home Assistant OS" is true but understates the case. The Steam Deck and IKEA adopters belong in the text, labelled as vendor-stated.

## 5. New sources opened for this target

[Pengutronix sponsorship post](https://pengutronix.de/en/blog/2025-11-21-labgrid-rauc-sponsoring.html) · [RAUC 10-year retrospective](https://pengutronix.de/en/blog/2025-04-22-10-years-of-rauc.html) · [Rugix GHSA-f8wx](https://github.com/rugix/rugix/security/advisories/GHSA-f8wx-p63f-pp8h) · [Rugix open-source commitment](https://rugix.org/open-source-commitment) · [RAUC SECURITY.md](https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/SECURITY.md)

## 6. Evidence that would flip the decision

- **RAUC loses its maintainers:** Pengutronix announces reduced maintenance, or either of its two key maintainers leaves and no RAUC release ships for more than 12 months.
- **Rugix gains durable maintenance:** it acquires an independent co-maintainer with at least 10% of commits, plus a published succession or foundation arrangement.
- **Rugix grows a major adopter:** a large adopter (not Umbrel) publicly ships Rugix *and* contributes maintainers.
- **RAUC falls behind on fixes:** a RAUC CVE goes unfixed for more than 90 days.
