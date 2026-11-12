# DC-03 · Lifecycle cost to 2036: longevity and vendor-risk refuter

**Refuter:** REF3, lens longevity and vendor risk · **Date:** 2026-11-11 · **Verdict: WEAKENED**
**Read before forming this view:** DC-03 in `decision-critical.md`, `03-base-os.md` §6, the DC-03 row of `01-FOUNDATION-DECISION.md` §3 (tie-break table), `qbank/W2.md` Q1/Q168/Q213, and the claims they cite (C-W2-001…006, 013, 030–032, C-REF-DC-cost-001…003, C-REF-DC-robotics-009/010). No other adversarial file was read first.

## The conclusion under test

DC-03 is "partial; blocked: paywalled" and unranked in revision 2. The load-bearing statement that survives is: **the free path to 2036 for stack A is "$0 in licences if rebased to Debian 14/15"**, so Debian's cost problem reduces to unpriced rebase labour plus an unusable ELTS contract. The flip condition is a bounded cost more than 25% above the cheapest gate-passing alternative, or a G3 FAIL.

## Strongest counter-argument

"$0 if rebased" treats Debian's free security support as covering the stack OneMind ships. Debian's own release notes say it does not, and they say the rebase cannot be compressed.

1. **Debian gives the platform's core components only "limited security support".** The trixie release notes (§5.2.3.2) and the draft forky notes (§5.2.1.2) both say Go- and Rust-based packages "will be covered by limited security support", with library fixes generally arriving only in point releases [C-REF3-DC-longevity-001, -002]. k3s, containerd and the Kubernetes tooling are Go, and Rugix is Rust. So for the parts of the image an attacker would target first, the "free" Debian security track is weaker than the S1 row implies. OneMind will have to rebuild those components itself, or take them from upstream, on its own schedule, for every year to 2036 and on every base release. That is recurring labour on all bases, but Debian states it outright for both trixie and forky.
2. **A fielded box cannot skip a release.** Trixie's release notes say "Skip-upgrades are not supported" (§5.1.25). A box that misses forky must still go 13 → 14 → 15 in order. They also list manual steps that an image-based rebase must absorb. For example, §5.1.5 says to make `/boot` at least 768 MB with about 300 MB free, §5.1.10 says encrypted filesystems need the `systemd-cryptsetup` package before rebooting, §5.1.17 warns that network interface names may change, and §5.1.11 says plain dm-crypt defaults have changed [C-REF3-DC-longevity-001]. Each of these touches A/B slot sizing, the LUKS data partition or networking on a headless box. An A/B image update avoids running `apt` in place, but the slot and boot-partition sizes still have to fit both generations. The 768 MB `/boot` rule shows partition needs grow between releases. So "2–3 rebases" are not optional events that can be priced away. Each is a sequential, mandatory engineering cycle.
3. **The free LTS years (2028–2030) run through one commercial intermediary.** Debian's wiki says the paid LTS effort is coordinated by Freexian, "just an intermediary company", which collects sponsor money and pays contributors [C-REF3-DC-longevity-003]. The years after the security team (2028-08-09 to 2030-06-30) and the whole ELTS tail therefore depend on one SARL and its sponsors' renewals. The trixie LTS architecture list is still "to be determined" [C-REF-DC-robotics-010]. "Community-governed, no single vendor" (the Governance row in 01) is true for Debian stable. For the years that decide DC-03, it is less true.
4. **The "free" alternative (Alma, path C) has its own upstream-supply risk.** After Red Hat restricted RHEL sources in 2023, AlmaLinux moved from 1:1 to ABI compatibility. The article says that "AlmaLinux can no longer pull these updates from Red Hat without violating licensing agreements" [C-REF3-DC-longevity-004, SECONDARY, Linux Magazine issue 278/2024]. This does not help Debian. It means the "$0 to 2035" cell for C also carries vendor risk that the table doesn't price.

## What does not break

- The forky draft currently lists no special pre-reboot actions (§5.1.3) [C-REF3-DC-longevity-002]. The next rebase may be lighter than trixie's, but the draft is incomplete.
- Revision 2 already leaves DC-03 unranked and names rebase labour as unpriced. This refuter sharpens that point. It does not reverse it.
- The limitation on Go and Rust is a Debian packaging policy. Ubuntu and Alma ship the same upstream projects, and OneMind will likely ship k3s from upstream on any base. The extra labour is therefore roughly base-neutral, but it means the "$0" cell is not $0 of work on any base.

## Verdict: WEAKENED

The "no ranking" outcome stands. The row's wording does not: "**$0 in licences if rebased to 14/15**" should read "$0 in licences. Plus 2–3 mandatory sequential rebases (no skip-upgrades). Plus self-maintained security for the Go/Rust components that Debian covers only partly. Plus dependence on Freexian for 2028–2035." No new evidence moves the cost above the 25% flip margin, because the alternatives' quotes are still unknown.

## What would flip it

- **To REFUTED (Debian clearly worse):** a Canonical Pro for Devices quote per device that is lower than the measured per-release rebase labour from the timed T-W3-04 drill, spread over the fleet at 1k and 10k units, **or** a Freexian answer that trixie LTS will not cover arm64.
- **Back to UPHELD:** the T-W3-04 drill shows a 13 → 14 image rebase is less than a few engineer-weeks, with no repartitioning. In addition, OneMind's Go/Rust components already come from upstream with their own update cadence, which makes the Debian limitation irrelevant to the image.

## New sources (opened 2026-11-11)

| Claim | Source | Type |
|---|---|---|
| C-REF3-DC-longevity-001 | https://www.debian.org/releases/trixie/release-notes/issues.en.html | PRIMARY |
| C-REF3-DC-longevity-002 | https://www.debian.org/releases/forky/release-notes/issues.en.html | PRIMARY (draft) |
| C-REF3-DC-longevity-003 | https://wiki.debian.org/LTS/Funding | PRIMARY |
| C-REF3-DC-longevity-004 | https://www.linux-magazine.com/Online/Features/AlmaLinux | SECONDARY (trade press, opened) |
