# DC-01 · Fedora IoT / bootc vs Debian 13 + Rugix — longevity refuter (round 4)

> **Refuter round 4 · lens: longevity and vendor risk · 2026-11-11.** Independent refuter (RESEARCH-MISSION.md §2 rule 7). Formed from the DC-01 Result in `decision-critical.md`, `01-FOUNDATION-DECISION.md`, the owning workstream file and the cited claim rows only; no earlier adversarial file was read first. New claims are in `evidence/claims/REF4-DC-longevity.csv`.

## Conclusion under test (rev. 3)
bootc is **not the base**; Debian 13 stays the base on a three-way tie-break (bootc 64 · Ubuntu 62 · Debian 60 on paper), and a **bootc Industrial profile** (CentOS Stream 10 / AlmaLinux 10 / RHEL image mode) is a year-2 track with Fedora IoT bootc as a CI canary [C-SCORE-025, C-LAB-fedora-bootc-011, C-LAB-fedora-bootc-015].

## Strongest counter-argument
Both halves of the answer lean on a 2036 story that the lifecycle sources do not fully support.

1. **The Industrial profile names a distribution that dies in 2030.** CentOS Stream 10 ends **2030-05-31** [C-REF4-DC-longevity-001], earlier than Debian 13's own LTS (2030-06-30) and six years short of 2036. Since June 2023 Stream is the *only* public RHEL source [C-REF4-DC-longevity-002]; AlmaLinux now rebuilds from Stream plus its own work, so "AlmaLinux 10 to 2035" depends on a downstream that Red Hat has already squeezed once. The only Red Hat-family route with a vendor-backed 10-year window is a paid RHEL subscription, which is a per-device cost the profile text does not price. Listing "CentOS Stream 10" as a profile base for industrial buyers who expect a decade is a longevity error, not a wording nit.
2. **Debian's tie-break edge on longevity is thinner on arm64 than the scorecard assumes.** The 2035 tail for Debian 13 is Freexian ELTS, and Freexian confirms **only amd64** for the whole ELTS period; arm64 is "on request" from paying customers, and unsupported packages are excluded [C-REF4-DC-longevity-003]. The Pi 5 tier — the tier where the tie-break was decided — therefore has no published support after 2030 at any price. That narrows, not reverses, the gap: bootc's Pi 5 path is itself only "experimental" AlmaLinux images [C-SCORE-025].

## Why it does not flip
The flip condition is "bootc passes G2 and G3 and outscores Debian by ≥ 3 robustly". Nothing here raises bootc's score: its Pi 5 path is experimental, our lab found a greenboot silent downgrade [C-LAB-fedora-bootc-011], and its 2030 Stream cliff is worse than Debian's. The counter weakens **the profile's framing and the longevity premise of the tie-break**, not the "not the base" answer.

## Verdict: **weakened**
- Required change: name the Industrial profile as **AlmaLinux 10 or RHEL 10 image mode** (support to 2035 / RHEL's published dates), with CentOS Stream 10 only as a CI canary like Fedora; price a RHEL subscription per unit in `lifecycle-cost-2036.md`.
- Required change: state that Debian's post-2030 arm64 coverage is unpublished (Freexian amd64-only by default), so the Pi 5 tier plans a Debian 14 rebase by 2030 (DC-05), not ELTS.

## What would flip this verdict
- **To upheld:** a written Freexian quote covering arm64 for Debian 13 ELTS at a known price, *and* the profile text corrected to AlmaLinux/RHEL.
- **To refuted (bootc as base):** AlmaLinux promoting its Pi 5 bootc images from experimental to supported with a published lifecycle, plus W2-HW-3 passing with no console.

## Sources opened (new)
- https://www.centos.org/download/ [C-REF4-DC-longevity-001]
- https://www.redhat.com/en/blog/furthering-evolution-centos-stream [C-REF4-DC-longevity-002]
- https://www.freexian.com/lts/extended/docs/debian-13-support/ [C-REF4-DC-longevity-003]
