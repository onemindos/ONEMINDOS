# Refutation: P0-W3-1 (Rugix bus factor), technical lens

- Refuter lens: technical
- Date: 2026-11-10
- Verdict: **upheld**. The facts are correct, with one small counting caveat. The counter-evidence lowers how much the risk matters. It does not disprove the claim.

## Claim under test

> Rugix (rugix/rugix) has an effective bus factor of one: between 2025-11-10 and 2026-11-10, 303 of its 304 default-branch commits were by a single author and only 2 distinct human authors committed; all-time the second contributor has 4 contributions. It reached v1.0.0 only on 2026-02-25 (v1.4.0 on 2026-11-02), and its SECURITY.md gives security fixes to the latest minor version only.

## Re-check of the cited sources (authenticated `gh api`, run 2026-11-10)

| Item | Claim | Re-measured | Holds? |
|---|---|---|---|
| Commits since 2025-11-10 on the default branch | 304 | 304 with no upper bound. The count includes `c2f5f4f3`, committed 2026-11-10T21:56Z, which is today. With `until=2026-11-10T00:00Z` there are 303. | Yes. The window is off by one day; the result is the same. |
| Commits by the top author | 303 | 303 by `koehlma` (Maximilian Köhl, Silitics) | Yes |
| Distinct human commit authors | 2 | 2: `koehlma`, plus `maco2035` with one commit (`d98833b0`, 2026-05-18, a bundler `--disable-pinning` fix) | Yes |
| All-time second contributor | 4 | `reubenmiller` 4. Next are `tboehler1` 2, and four others with 1 each. `koehlma` has 1161. | Yes |
| v1.0.0 date | 2026-02-25 | 2026-02-25T06:07Z | Yes |
| v1.4.0 date | 2026-11-02 | 2026-11-02T16:35Z | Yes |
| SECURITY.md support model | Latest minor only | "Only the latest minor version branch receives security updates." | Yes. Note that the table still lists only `1.0.0` as supported, while the latest release is 1.4.0 (see below). |

All maintainer PRs since 2025-11-10 were opened and merged by `koehlma`. One PR, "Address GPT-5.6 review" (merged 2026-07-14), suggests that review is done by AI rather than by a second human.

## Strongest counter-argument

"Bus factor of one" measured by commits overstates the technical risk to OneMind. Five points support this.

1. **It is a company project, not a hobby project.** The repository belongs to the `rugix` organisation, which has 17 repositories. Fifteen of them were pushed within the last day, including `rugix-bakery`, `meta-rugix` (Yocto), `rugix-bsps`, `rugix-admin`, `rugix-testkit` and examples for Mender, Memfault, NixOS and RevPi. The project is backed by Silitics GmbH, which sells custom engineering (embedded Linux and OTA, Rust, CRA compliance) and the Nexigon fleet control plane. Its site names Umbrel, enmo, eChecker and Aqa Technologies as users and claims "tens of thousands of devices". The developer is paid, and his commercial customers have a direct stake in the project's continuity.
2. **Maturity predates v1.0.** The repository was created on 2023-05-18. It shipped as Rugpi and as 0.6 to 0.8.x for about 2.5 years before v1.0.0, including at least 17 releases in the 0.8 line. "Reached v1.0.0 only on 2026-02-25" is about version numbering, not about how long the code has run in the field.
3. **Outside parties are involved even though commits are not.** Eighteen distinct accounts opened issues or PRs since 2025-11-10. An advisory, GHSA-f8wx-p63f-pp8h, credits `lukechilds` (Umbrel) as the reporter. Umbrel, which ships Rugix in umbrelOS 1.7 and 2.0, is in effect an external security reviewer and a large production tester.
4. **The security process works.** Two High advisories were handled in October 2026. Each was fixed and disclosed the same day as its patch release: GHSA-637r-qx4c-jm45 with v1.3.1 on 2026-10-21, and GHSA-f8wx-p63f-pp8h with v1.3.2 on 2026-10-29. SECURITY.md gives a 3-business-day acknowledgement SLA, a PGP key, and CycloneDX SBOMs. A "latest minor only" policy is normal for a rolling tool when minor releases are drop-in.
5. **Forking is realistic.** The code is a dual Apache-2.0/MIT Rust workspace, and the on-disk formats (bundles, slots, boot flows) are documented. If the maintainer left, OneMind or Umbrel could keep a fork going, which is not true of a proprietary OTA vendor.

## New sources found by looking for failure, abandonment and regressions (opened)

1. **GHSA-f8wx-p63f-pp8h, High, 2026-10-29: "Code Execution Through Execute Payloads Without Block Encoding."** https://github.com/rugix/rugix/security/advisories/GHSA-f8wx-p63f-pp8h
   - It affects `>= 0.8.0, < 1.3.2` and `1.4.0-dev.1`.
   - Unverified payload bytes could reach a root execute handler even when a signature or hash was required. This is a verification-bypass class bug in the core trust path.
   - No CVE was assigned.
   - The reporter was Umbrel, not the maintainer.
2. **GHSA-637r-qx4c-jm45, High, 2026-10-21: "Rugix Ctrl HTTPS downloads trust compromised eMudhra CA keys."** https://github.com/rugix/rugix/security/advisories/GHSA-637r-qx4c-jm45
   - It affects `>= 0.8.0-rc.1, < 1.3.1`.
   - It was caused by bundled WebPKI roots.
   - It was fixed by moving to the system trust store (PR "Use the system trust store for HTTPS update downloads").
3. **getumbrel/umbrel #2153: "OS update hangs at 93%: rugix-ctrl can't find sfdisk because /usr/sbin is missing from PATH."** https://github.com/getumbrel/umbrel/issues/2153
   - It was opened 2026-05-24 and is still open.
   - A comment on 2026-11-03 reports that it still reproduces on umbrelOS 2.0.1, through the legacy-to-Rugix migration bundle.
   - The update hangs forever with no timeout and no error.
   - The root cause is shared between Rugix and umbreld: the PATH comes from the caller. Even so, Rugix's update path has no time limit, and the failure surfaces as a silent hang rather than a rollback.
4. **Umbrel community: "Fail to Update umbrelOS 1.5 → 1.7.1".** https://community.umbrel.com/t/fail-to-update-umbrelos1-5-1-7-1/25043
   - Users blame the Rugix migration for apps that would not start after the update.
   - This was found through search. The attribution is the users' own and is not confirmed by a root-cause analysis.
5. **Silitics home page.** https://silitics.com/
   - It shows the company backing and the named customers.
   - It gives no team size and names no second engineer.
6. **Open issues #120, #121 and #122 in rugix/rugix**, all opened 2026-08-22, still open with no maintainer response:
   - encrypted update bundles
   - device-side anti-downgrade protection
   - Buildroot integration

   Anti-downgrade matters for OneMind's signing chain (W3). The backlog shows that one person decides the priorities.

## Why the counter-argument does not refute the claim

- The claim is about **commit concentration**, and every number in it reproduces. Company backing raises the chance that someone keeps paying the one maintainer. It does not add a second person who can review or release. The Silitics site names no other engineer, and every merge in the past year is self-merged.
- The failure evidence makes the single-maintainer risk concrete:
  - In nine days of October 2026, two High-severity flaws in the trust and verification path were fixed by one person.
  - One flaw was found by an outside party (Umbrel).
  - Neither received a CVE ID, so CVE-feed scanners that OneMind might rely on would not flag them. They appear only as GHSAs.
- **SECURITY.md is out of date.** Its table lists `1.0.0` as the only supported version, while 1.4.0 is current and the text says only the latest minor version is supported. This is a small sign of one person with too little time for project upkeep.
- **"Latest minor only" plus frequent breaking changes is costly.** Recent PRs include breaking changes inside 1.x (`feat(apps)!`, `fix(bundle)!`, mainly in the newer Rugix Apps and bundle code). OneMind would have to follow every minor release to stay patched, and there is no LTS branch to hold back on for a 10-year product.

## Implication for OneMind (technical)

- The claim should stand as a **risk** in the claims ledger. It is not by itself a reason to reject Rugix.
- The defensible position is to adopt Rugix only with these mitigations:
  - A documented fork-readiness plan, given the Apache-2.0/MIT code.
  - Watching GHSAs as well as CVEs.
  - OneMind's own power-loss and timeout tests on the update path.
  - A plan for anti-downgrade protection, either upstream or OneMind's own.
  - Keeping RAUC as the fallback. RAUC has multi-maintainer governance and is used by HAOS.
- Re-check by **2027-05-10** (6 months).

## What evidence would flip the verdict

The claim would become **weakened** or **refuted** if any of the following appeared:

- A second human with commit or merge rights who lands at least 10% of default-branch commits, or who reviews and approves the maintainer's PRs, over a 6-month window.
- A published governance or continuity statement from Silitics: named engineering staff on Rugix, an escrow or succession commitment, or an LTS or support-window policy for commercial customers.
- Umbrel or another adopter (enmo, eChecker, Aqa) contributing upstream on a sustained basis, beyond reporting issues.
- Rugix moving to a foundation (for example LF Edge or OpenSSF) or adding a co-maintainer to `CODEOWNERS`.

The claim's **impact** would become more serious (escalate to "avoid"):

- If commit activity stops for 90 days or more.
- If Silitics changes the license or ownership.
- If another verification-bypass advisory is published.
- If #2153-class silent hangs keep happening without a fix on the Rugix side.
