# W3 P0-W3-1 refuter: longevity and vendor risk

| Field | Value |
|---|---|
| Claim | P0-W3-1 (`04` §14.2 P0-1, DC-06): "Rugix has a bus factor of 1." Rugix had 304 commits on its default branch in the 12 months to 2026-11-10, and one author wrote 303 [C-W3-001]. Only the latest minor version gets security updates [C-W3-004]. Second adopters exist only as a vendor claim [C-W3-015]. |
| Lens | Longevity and vendor risk |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter read only the conclusion text (`04` §1 V1, §5.2 verdict line, §14.2 row) and the cited sources. It did not read the author's reasoning or the other refuter files. |
| Date | 2026-11-11. Re-check repo statistics by 2027-05-11. |
| Verdict | **upheld** |

## 1. Re-checking the cited sources

| Claim | What I found (2026-11-11) | Holds? |
|---|---|---|
| C-W3-001: 303 of 304 commits by one author | Reproduced. `rugix/rugix@c2f5f4f3` has 304 commits since 2025-11-10. Maximilian Köhl wrote 303 of them, under two emails (249 from silitics.com, 54 from koehlma.de). One outside author wrote 1 [C-REF-W3-longevity-002]. | Yes |
| C-W3-004: only the latest minor version gets security fixes | Confirmed by practice. Both October 2026 advisories were fixed only in the 1.3.x line. The 0.8.x users received mitigations, not a fixed release [C-REF-W3-longevity-003, -004]. | Yes |
| C-W3-015: adopters are a vendor claim | Partly confirmed. The reporter of GHSA-f8wx is `lukechilds`, which shows that someone at Umbrel is engaged. It does not show a second maintainer. | Yes |

## 2. Strongest counter-argument

"Bus factor of 1" overstates the practical risk, for four reasons.

1. **A company stands behind the project.** Silitics GmbH has revenue from consulting and from Nexigon. It has published commitments: the licences stay MIT and Apache-2.0, features will not be degraded, and nothing will be gated behind a subscription [C-REF-W3-longevity-005].
2. **The code is permissively licensed Rust with a small surface, so it can be forked.** Umbrel ships it in umbrelOS and is already finding and reporting its security bugs. That makes Umbrel a plausible successor maintainer.
3. **Advisories are handled quickly.** Both 2026 advisories shipped with a fixed release on the day they were published [C-REF-W3-longevity-003, -004].
4. **RAUC's concentration is closer than "16 authors" implies.** In the same window, two Pengutronix engineers wrote 86% of RAUC's commits [C-REF-W3-longevity-001]. Measured strictly as "people whose loss stalls the project", the bus factor is 1 for Rugix and 2 for RAUC.

## 3. New failure, abandonment and CVE evidence (opened by this refuter)

| Source | What it shows | Effect on the claim |
|---|---|---|
| [GHSA-f8wx-p63f-pp8h](https://github.com/rugix/rugix/security/advisories/GHSA-f8wx-p63f-pp8h) (2026-10-29) [C-REF-W3-longevity-003] | High severity, CVSS 8.1. An authentic signed bundle with substituted bytes could run code as root. The flaw spanned 0.8.0 through 1.3.1, roughly two years of releases. An outside party found it with AI assistance, and only 1.3.2 was patched. | **Supports the claim.** A design-level bypass in the signing path survived about two years with no second reviewer. The fix was not backported. |
| [GHSA-637r-qx4c-jm45](https://github.com/rugix/rugix/security/advisories/GHSA-637r-qx4c-jm45) (2026-10-21) [C-REF-W3-longevity-004] | High severity. Rugix's HTTPS downloads trusted compromised eMudhra CA keys. 0.8.x received mitigations only. | **Supports the claim.** Fixing old branches depends on one person's time. |
| [Rugix open-source commitment](https://rugix.org/open-source-commitment) [C-REF-W3-longevity-005] | Promises cover licensing and feature gating. **Nothing covers succession, escrow, governance or the company ceasing.** The Rugix name is a Silitics trademark. | **Supports the claim.** No continuity mechanism exists beyond forking, and a fork could not use the name. |
| Web search for Silitics or Rugix abandonment, acquisition or funding trouble (2026-11-11) | Found nothing. | Neutral. The project is active. The risk is concentration, not decline. |

## 4. Verdict: upheld

The fact is reproduced on primary data, and the claim stands. The counter-arguments lower the *severity* of the risk without changing the *fact*. A forkable project with fast fixes is still a project that one person reviews, and the GHSA-f8wx history shows what that means in practice: a signing-path flaw lasted about two years. Section 2 point 4 is the most useful correction, and it belongs to P0-W3-2 rather than here. RAUC's advantage is "two people at a ten-year-old company with large adopters", not a broad community.

## 5. Evidence that would flip this

- **Commits:** over a rolling 12 months, a second person who is not employed by Silitics authors at least 10% of commits *and* merges other people's PRs.
- **Continuity:** a published succession, escrow or foundation-transfer statement from Silitics, or a written commitment from Umbrel to co-maintain.
- **Support policy:** a supported-versions policy that backports security fixes to the previous minor version for at least 12 months.
