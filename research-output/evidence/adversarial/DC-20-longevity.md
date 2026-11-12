# DC-20 · A distro base vs a build-from-source appliance — longevity refuter

**Refuter:** REF4, lens **longevity and vendor risk** (RESEARCH-MISSION.md §2 rule 7) · **Date:** 2026-11-11 · **Verdict: weakened**

## Conclusion under test

`evidence/decision-critical.md` DC-20: the same minimal x86 core built with mkosi (Debian 13.7) and Buildroot 2025.02.19 LTS; Buildroot is 4–6x smaller with a complete SBOM, but only 7–18% fewer CVE IDs because the kernel is 73–80% of IDs either way; "Debian has triaged all 161 userspace IDs while 32–53 of Buildroot's have unapplied upstream fixes" [C-LAB-minimal-image-dc20-011…013, -021]. **Flip not met; D1 stands, now because of the userspace patch backlog.**

## Strongest counter-argument

The deciding argument is now Debian's security team. That is a snapshot from Debian 13's **full-support** phase (to 2028-08-09). Over a 10-year box life the advantage decays in three steps, and the lab measured none of them:

1. **"Triaged" is not "will be fixed".** The lab counts 74 not-fixed and 87 wont-fix as triaged. Debian's tracker defines `<ignored>` as "no updates will be provided for it", `<no-dsa>` as not warranting an advisory, and `unimportant` as also covering "issues in packages without security support" [C-REF4-DC-longevity-006]. For a CRA "no known exploitable vulnerability" claim, OneMind must still assess every ignored and no-dsa ID that ships in its image, which is the same work as Buildroot's backlog, only with someone else's triage label as the starting point.
2. **LTS phase (2028–2030): fewer packages, fewer architectures, sponsor-funded.** Bookworm's LTS handover says "a few packages are not covered" and lists amd64, i386, arm64, armhf and ppc64el [C-REF4-DC-longevity-005]; the trixie release page says "the set of supported architectures is reduced during the LTS term", and the LTS wiki lists trixie's LTS architectures as "to be determined" and ties package coverage to funding [C-REF4-DC-longevity-007]. arm64 has been an LTS architecture, so this is a risk, not a loss.
3. **ELTS phase (2030–2035): one commercial vendor, amd64 only confirmed.** Freexian's trixie ELTS page confirms only amd64 for the whole period; other architectures depend on customer requests; package coverage is "as long as we have customers paying"; the kernel is a backport from newer releases [C-REF4-DC-longevity-008]. For the Pi 5 and other arm64 boxes, years 5–10 of "Debian patches it" become "OneMind pays a single vendor, if it agrees to cover arm64, or patches itself", which is the Buildroot position, plus a base still pinned to 2025-era userspace.

Buildroot has its own longevity cost (LTS series EOL March 2028 [C-LAB-minimal-image-dc20-001], so a rebase every LTS), and the kernel dominates CVEs in both legs, so the counter-argument does not make Buildroot the winner. It shows the stated reason for D1 ("Debian has the patch backlog handled") holds for roughly the first 3–5 years on arm64, not for the declared support period, and that the decision needs a per-architecture plan for 2030–2035 (ELTS quote for arm64, or a rebase onto Debian 14/15 inside the box's life).

## Verdict: weakened

The measured 2026 result stands and D1 is not overturned. The rationale is time-limited and architecture-dependent: the advantage it rests on is reduced in LTS and, for arm64, not confirmed at all in ELTS, and "triaged" includes IDs Debian will never fix.

**Proposed changes (for the owner, not applied):** re-state DC-20's answer as "D1 stands for the full-support and LTS phases; ELTS-phase coverage on arm64 unconfirmed"; add to the lab a split of Debian's 161 IDs by tracker state (`ignored` / `no-dsa` / `postponed` / unfixed) and a re-run of the scan against a Debian 13 LTS-phase package set; add a Freexian arm64 ELTS quote (or a planned in-life rebase to Debian 14) to `evidence/lifecycle-cost-2036.md`.

## What would flip it

- **To upheld:** the Debian LTS team announces arm64 (and armhf if needed) for trixie LTS, and Freexian quotes arm64 ELTS for trixie at a cost inside the C5 anchors, or the support plan commits to an in-life base rebase before 2030.
- **To refuted:** the per-state split shows most of Debian's 161 IDs are `ignored`/end-of-life (no fix ever), making Debian's real backlog comparable to Buildroot's, and no arm64 ELTS is available.

## Sources (new in this refuter)

- Debian news, "Security support for Bookworm handed over to the LTS team" (2026-07-12): <https://www.debian.org/News/2026/20260712>
- Debian security tracker documentation (tag definitions): <https://security-team.debian.org/security_tracker.html>
- Re-cited (already in other ledgers): Debian LTS wiki <https://wiki.debian.org/LTS>; Freexian "About Debian 13 Trixie" <https://www.freexian.com/lts/extended/docs/debian-13-support/>; trixie release information <https://www.debian.org/releases/trixie/>
