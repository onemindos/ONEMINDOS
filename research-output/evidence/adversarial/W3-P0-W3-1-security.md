# Adversarial review: P0-W3-1 (security lens)

- **Claim under test:** Rugix (rugix/rugix) has an effective bus factor of one: between 2025-11-10 and 2026-11-10, 303 of its 304 default-branch commits were by a single author and only 2 distinct human authors committed; all-time the second contributor has 4 contributions. It reached v1.0.0 only on 2026-02-25 (v1.4.0 on 2026-11-02), and its SECURITY.md gives security fixes to the latest minor version only.
- **Refuter lens:** security (vulnerability response, review discipline, patch-support window, supply chain)
- **Date:** 2026-11-10. Re-check by: 2027-05-10 (6 months; project activity and support facts move fast).
- **Verdict: `upheld`.** Every number reproduces. The strongest counter-arguments lower how much damage the bus factor could do, but they do not change the fact. Seen through security, the evidence makes the risk worse, not better.

## 1. Re-verification of the claim (cited sources, re-run 2026-11-10)

| Sub-claim | Re-run result | Status |
|---|---|---|
| 304 default-branch commits since 2025-11-10, 303 by one author | `gh api --paginate repos/rugix/rugix/commits?since=2025-11-10T00:00:00Z&until=2026-11-10T23:59:59Z` returns 304 rows: 303 `koehlma` (Maximilian Köhl), 1 `maco2035`. The saved TSV has sha256 `fce7137e3d275947c0c3e02256ad74dfa6d5ad14ddf69ae59fc2847fe67ba8ed` (scratch copy, not committed) | **Confirmed** |
| The second contributor has 4 contributions all-time | `/contributors?anon=1` gives koehlma 1161, reubenmiller 4, tboehler1 2, and four others with 1 each | **Confirmed** |
| v1.0.0 on 2026-02-25, v1.4.0 on 2026-11-02 | Releases API: v1.0.0 `2026-02-25T06:07:29Z`; v1.4.0 `2026-11-02T16:35:41Z` | **Confirmed** |
| SECURITY.md: latest minor only | `rugix/rugix@6d7fc277919b0048893c80d7e1e6e488ddc7b27b:SECURITY.md#L14-L15`: "Only the latest minor version branch receives security updates." | **Confirmed, with a caveat:** the table at L17-L22 of the same file still marks `1.0.0` as the only supported row, although 1.4 is the latest minor. The policy text and the table contradict each other (see §3.4). |

Other facts I checked: the repository is Apache-2.0, with a LICENSE-MIT file also present. The owner is the `rugix` GitHub organisation (171 stars, 23 forks, last pushed 2026-11-10). From 2025-11-10 to 2026-11-10 there were 47 PRs: 43 by koehlma and 1 each by four other people. 20 issues came from about 15 distinct reporters. The REST API returns no branch protection on `main`, and the HTTP 404 does not tell me whether that is because protection is absent or because I lack permission to see it. There is no CODEOWNERS file (`.github/` holds only `workflows`). The OpenSSF Scorecard API has no data for the repository.

## 2. Strongest counter-argument (steelman against the claim's implication)

"Commit count is the wrong measure of security bus factor. What matters is (a) whether vulnerabilities get fixed fast, (b) whether someone could take over, and (c) whether serious users are invested."

1. **Company backing, not a hobby.** Silitics GmbH presents itself as "The maker of Rugix and Nexigon". Nexigon is a commercial control plane built on Rugix, and its self-hosted tier includes a Software Escrow Agreement (https://silitics.com/, opened 2026-11-10). Rugix is how the company earns money, so it has a reason to keep maintaining it.
2. **Fast, disciplined handling of vulnerabilities.** Two high-severity advisories in October 2026 were each handled in hours or days, with a fixed release, a GHSA, a blog post and a release branch:
   - GHSA-637r-qx4c-jm45: the eMudhra CA key compromise. Published 2026-10-21T05:52Z together with v1.3.1, the same day as the guidance post at https://rugix.org/blog/emudhra-ca-key-compromise/ (authored by Köhl, dated 2026-10-21).
   - GHSA-f8wx-p63f-pp8h: execute payloads could run without block encoding. Fixed in v1.3.2 on 2026-10-29. The reporter credited is `lukechilds`.
   - The fixes went to the `release/1.3` branch while `main` was preparing 1.4.0-dev. That shows a working release-branch process.
3. **A capable downstream depends on it and keeps up.** umbrelOS builds its OS with Rugix. `getumbrel/umbrel@c43beed964074d08865d648ca9ac3359826a14ff:packages/os/rugix/layers/umbrelos-pi.toml#L16` pins `version = "v1.3.2"`. Umbrel picked up v1.3.1 on 2026-10-22 (commit `57edd7e8`), less than 24 hours after release. It picked up v1.3.2 on 2026-10-29 (commit `6e4099f7`), about 5 hours after release. Umbrel also found and reported the second vulnerability. A funded downstream with this much at stake could fork the project, since it is Apache-2.0/MIT.
4. **Takeover is possible in principle.** The project is small, written in Rust, and permissively licensed, so anyone can fork it. Umbrel, Memfault and Mender have example integrations (the `rugix-example-*` repositories). Thin-edge.io (reubenmiller) has also contributed.

**Why this does not overturn the claim:** points 1 to 4 are about what happens after a failure, or how much it would hurt. None shows a second person who can review, merge, release or handle security reports today. Points 1 and 2 actually show that one person did all of it: Köhl wrote the hotfix, the release, the advisory text and the blog post.

## 3. Security-lens findings that strengthen the claim (new evidence)

### 3.1 Security fixes are self-merged without review
The fix for GHSA-f8wx-p63f-pp8h (PR #155, "Apply block-index policy consistently during installation") was authored by koehlma, merged by koehlma at 2026-10-29T10:38:59Z, and has **zero reviews** (`gh api repos/rugix/rugix/pulls/155/reviews` returns an empty array). PRs #154 and #137, also security- or hardening-related, are the same: self-merged with no reviews. No CODEOWNERS file exists, and no branch protection is visible. **Every security fix is checked by one person only.**

### 3.2 The high-severity bug was a regression that a second reviewer might have caught
The GHSA-f8wx-p63f-pp8h advisory text says: "Version 1.2 introduced mandatory block indices by default, but the execute-payload path omitted the check." It also says the handler was "not terminated on this error". The result was code execution as root, even with a valid bundle signature. The vulnerability was found by an outside downstream party (lukechilds), not by the project's own review. With one maintainer, finding bugs in the update path relies on outside reporters. That path is exactly what an OTA engine for robots and drones has to get right.

### 3.3 The support window forces frequent minor upgrades over a 10-year horizon
Stable minor releases since 1.0 have arrived roughly every 1 to 3 months: 1.0 (2026-02-25), 1.1 (03-23), 1.2 (05-20), 1.3 (08-05), 1.4 (11-02). Under the "latest minor only" policy, **umbrelOS master became unsupported 8 days ago**: it pins v1.3.2, and 1.4.0 shipped 2026-11-02. If OneMind ships fleets that update when users choose (R-1), devices will regularly run unsupported Rugix Ctrl versions. The policy does not promise any long-term-support line.

### 3.4 The security policy contradicts itself
`SECURITY.md#L14-L15` says only the latest minor is supported. The table at L17-L22 says `1.0.0` is supported. Both the pinned SHA and the current `main` have this mismatch. It is a small point, but it means the support promise cannot be read off the document. The upgrade guide (https://rugix.org/docs/upgrading-from-v0.8/, opened 2026-11-10) makes "no statement about how long older versions are supported".

### 3.5 The 0.8.x line got no fix
Both advisories affect versions from 0.8.0 onward. The eMudhra post gives 0.8.x users workarounds only: pass a trusted bundle hash with `--verify-bundle`, then upgrade. It mentions no backport. Rugix Ctrl 0.8.x also embedded its HTTPS trust roots in the binary, so updating the OS CA store did not help. The post says future releases will use the system trust store instead, which is a good design fix, but every device already in the field had to be reflashed with a new Rugix binary.

## 4. New sources (found by searching for failure, vulnerabilities and lifecycle cuts; all opened)

1. **GHSA-f8wx-p63f-pp8h**, "Code Execution Through Execute Payloads Without Block Encoding", high severity, published 2026-10-29. Affects >=0.8.0, <1.3.2 and 1.4.0-dev.1. Retrieved via `gh api repos/rugix/rugix/security-advisories`. https://github.com/rugix/rugix/security/advisories/GHSA-f8wx-p63f-pp8h. PRIMARY.
2. **GHSA-637r-qx4c-jm45**, "Rugix Ctrl HTTPS downloads trust compromised eMudhra CA keys", high severity, published 2026-10-21. Affects >=0.8.0-rc.1, <1.3.1; references RUSTSEC-2026-0381. https://github.com/rugix/rugix/security/advisories/GHSA-637r-qx4c-jm45. PRIMARY.
3. **Rugix blog, "eMudhra CA Key Compromise: Guidance for Embedded Linux Devices"**, 2026-10-21. No 0.8.x backport; trust roots are embedded in the binary. https://rugix.org/blog/emudhra-ca-key-compromise/. PRIMARY (vendor).
4. **PR #155 review record**: self-merged, no reviews. https://github.com/rugix/rugix/pull/155 (via `gh api .../pulls/155/reviews`). PRIMARY.
5. **umbrelOS dependency and lag**: `getumbrel/umbrel@c43beed964074d08865d648ca9ac3359826a14ff:packages/os/rugix/layers/umbrelos-pi.toml#L16` pins v1.3.2. Commits `57edd7e8949556f759a3928a663f648943faac64` and `6e4099f72af55ab235cbeaacd3da038bf73ae629` record the update speed. PRIMARY.
6. **Silitics GmbH homepage**: maker of Rugix and Nexigon; Nexigon's self-hosted tier includes a Software Escrow Agreement; no team size or SLA is published. https://silitics.com/. PRIMARY-METADATA (vendor).
7. **Rugix "Upgrading from v0.8"**: breaking changes (raw image installs removed, mandatory bundle verification); no support-duration statement. https://rugix.org/docs/upgrading-from-v0.8/. PRIMARY.

Archive note: I could write only this file, so the API outputs above were not saved into `evidence/sources/`. The orchestrator should archive sources 1 to 3 and 6 (Wayback or saved text plus hash) if this claim is load-bearing.

## 5. Implications for OneMind (security)

- The claim stands. In a security review, Rugix counts as **single-maintainer and single-reviewer for code that runs as root and checks signatures in the update path**.
- This argues against adopting Rugix *only if* OneMind cannot absorb the risk. Possible mitigations, which the decision author should weigh:
  - Pin Rugix Ctrl by version and digest.
  - Track GHSAs for `rugix/rugix` in CI.
  - Budget for a minor upgrade every quarter.
  - Never use `--insecure-*` flags.
  - Require block encoding on every payload.
  - Keep a ready fork plan (Apache-2.0/MIT allows it).
  - Get a support contract from Silitics, including escrow if available.
- Compare with the runner-up (RAUC): it has several maintainers and is used by HAOS. The steelman refuter should check RAUC's review practice and its advisory history on the same terms.

## 6. What evidence would flip this

**From `upheld` to `weakened`** (the claim stays true but matters less for security). Any one of these would do:
- A second person with merge or release rights on `rugix/rugix` who actually reviews PRs. Evidence would be at least 25% of merged PRs in a 6-month window approved by someone other than the author, plus a CODEOWNERS file or branch protection that requires review.
- A published Silitics commitment of a long-term-support line (e.g. at least 2 years of security fixes for a named minor), or a paid support offering with a stated security SLA. Software escrow that covers Rugix itself, not only Nexigon, would also count.
- Silitics stating a team size of at least 2 engineers paid to work on Rugix.

**From `upheld` to `refuted`.** Any one of these would do:
- The commit or contributor data turns out to be wrong. For example, co-authored or squash-merged work from other people that GitHub attributes to koehlma, enough that 2 or more people each wrote at least 10% of the code changes in the window.
- An organisation such as Umbrel, Memfault or thin-edge.io formally co-maintains Rugix with write access and a public governance document.

**What would make the claim worse:**
- No commits for 90 days or more.
- A security report not acknowledged within the 3 business days SECURITY.md promises.
- Silitics changing hands or narrowing its focus.
- A licence change on future versions.
