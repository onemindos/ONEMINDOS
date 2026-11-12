# Refuter report: P0-1 (DC-04), security lens

- **Claim under test:** the EU CRA does not force a different base OS. A OneMind box sold from December 2027 can meet the five-year support period by rebasing in place to later Debian releases under Art. 13(10). The binding limits are the in-place rebase path and per-board vendor kernel support.
- **Refuter lens:** security (vulnerability handling, patch coverage, update-path integrity)
- **Date:** 2026-11-10 · **Re-check by:** 2027-05-10 (CRA guidance and harmonised standards are still moving)
- **Verdict: WEAKENED.** The conclusion survives: the CRA alone does not force a different base. The legal mechanism the claim relies on is wrong for a hardware box, and the claim understates how much security coverage Debian's lifecycle really provides on the arm64 boards.

## 1. Strongest counter-argument

### 1.1 Art. 13(10) is the wrong hook for a hardware product
Art. 13(10) applies to "subsequent substantially modified versions of a **software product**". A OneMind box is a hardware product with digital elements. Recital 40 handles the hardware case separately and more strictly:

> "where a hardware product, such as a smartphone, is not compatible with the latest version of the operating system it was originally delivered with, the manufacturer should continue to provide security updates at least for the latest compatible version of the operating system for the support period."

As a result, rebasing in place is allowed only while every board can run the next Debian release. When a board stops being able to (a vendor kernel or BSP pinned to an old release, Jetson L4T, or a board dropped from Debian), the manufacturer must keep **patching the old release itself** until the support period ends. For Debian that means Freexian ELTS, which guarantees only amd64. arm64 and armhf are "on request", the price is by quote, and support is promised "as long as we have customers paying". The two boards most exposed to this, Pi 5 and Jetson, are both arm64. The claim names "per-board vendor kernel support" as a limit but does not say what follows legally: the fallback is mandatory and possibly unbuyable, not optional.

### 1.2 Even where 13(10) applies, it relieves only one requirement
Art. 13(10) relieves only Annex I Part II point (2), "address and remediate vulnerabilities without delay". Recital 40 says the manufacturer "should continue to comply, for the support period, with other vulnerability-handling requirements" (the CVD policy, information sharing and so on) "for all subsequent substantially modified versions". Art. 13(9) also requires every security update issued to stay available for **at least 10 years** or for the rest of the support period, whichever is longer. That is an artifact-hosting and signing-key obligation that outlasts any single Debian release. A free rebase does not remove these obligations.

### 1.3 Debian's lifecycle covers less than the date suggests
- **Packages:** Debian 12 LTS: "A few packages are not covered by the Bookworm LTS support". ELTS for Debian 13 likewise says "Not all packages can be supported". The CRA's vulnerability-handling duty covers the product "including its components" (Art. 13(8); Recital 34), so every uncovered package OneMind ships becomes OneMind's own patching work.
- **Architectures:** each move into LTS has dropped architectures. Debian 12 LTS kept only amd64, i386, arm64, armhf and ppc64el; armel, MIPS and s390x were dropped. arm64 is safe in free LTS today. In ELTS it is not guaranteed for Debian 12 or 13.
- **Kernels:** on Pi 5 the kernel is Raspberry Pi's tree, and on Jetson it is NVIDIA's L4T. Debian LTS and ELTS do not patch either. On 2 of the 3 target platforms, the Debian dates cover userland only. Kernel CVE handling depends on the vendor and has no end date anyone has published.
- **Beyond Debian:** k3s, containerd, the Market apps and the firmware have their own lifecycles, mostly about 12 months per k3s minor release. These, not Debian, set how often OneMind has to ship CRA updates. This supports "the CRA does not force a different base", but it also means "Debian lasts to 2030/2035" is not the figure that matters for compliance.

### 1.4 An in-place rebase is a security risk unless it is an atomic image swap
A failed major upgrade leaves a fielded box unpatched or bricked, and both outcomes break the CRA duty to deliver security updates. Raspberry Pi's own engineers advise against upgrading Bookworm to Trixie in place. Simon Long (Raspberry Pi OS) is quoted saying it "is not a good idea… there are many underlying bugs in the background", and field reports describe in-place upgrades that hung or failed. "Rebase in place" therefore has to mean a full signed A/B image swap with a health-gated commit and rollback (W3). An `apt full-upgrade` across major releases is not acceptable. Each rebase also needs its own risk check: under Art. 3(30) and the Commission guidance (C(2026) 5252, 27 July 2026), a change that affects Annex I Part I compliance is a substantial modification. The guidance says this triggers a reassessment of the support period, and that the period is not automatically reset. A major OS rebase plausibly counts, which would mean a fresh conformity check for each rebase. For a solo founder, that is real recurring work.

### 1.5 Timeline check
A box sold in December 2027 needs support until at least December 2032. Free Debian 13 LTS ends 2030-06-30, so at least one rebase (to Debian 14, expected around 2027 but **unconfirmed**) is needed. A box sold in 2030 needs Debian 15 or later, whose release dates are unknown. The plan depends on Debian keeping its usual cadence and on the boards keeping up with it.

## 2. What still holds
- Nothing in the CRA ties the support period to a single base-OS release. Art. 13(8) sets a duration ("at least five years", reflecting expected use), and Art. 13(19) requires the end month and year to be shown at purchase. Recital 40 explicitly expects the OS to move to newer compatible versions. The core claim, that the CRA alone does not force a different base, is **upheld**.
- Any alternative base (Ubuntu Core, Fedora/bootc, Yocto) runs into the same Recital 40 and vendor-kernel problems on Jetson and Pi. Switching base does not remove them.
- Freexian ELTS backports newer kernels on amd64. On x86 the rebase-or-ELTS fallback is credible.

## 3. Requested rewrite of the claim
Replace "Art. 13(10) lets a manufacturer support only the latest version…" with this: *"For hardware, Recital 40 lets the manufacturer move users to the latest **compatible** OS version. Where a board cannot move, the manufacturer must keep patching that board's last compatible release for the whole support period, which for Debian means ELTS (arm64 not guaranteed). Art. 13(10), for software products, relieves only Annex I Part II(2). The other vulnerability-handling duties and the 10-year availability of updates under Art. 13(9) remain."* Also add that the Debian dates cover userland only on Pi 5 and Jetson, and that a rebase must be an atomic A/B image swap, not `apt` dist-upgrade.

## 4. Evidence that would flip the decision
**Toward REFUTED (the CRA effectively forces a different base or a different design):**
- Commission guidance, an implementing act or a harmonised standard (the prEN 40000 vulnerability-handling series) stating that a major OS rebase on hardware is a substantial modification needing a new conformity assessment **and** a new support-period declaration. The cost of each rebase would then favour a base with one release lasting ten years or more.
- Freexian declining arm64 ELTS for Debian 13, or quoting it at a price a solo vendor cannot pay, while Pi 5 or Jetson cannot move to Debian 14 or 15, leaving no lawful patch source for the support period.

**Toward UPHELD as written:**
- Commission FAQ or guidance explicitly applying the 13(10) latest-version logic to OS images on hardware.
- A VM or Pi 5 lab spike (W3) showing a signed Rugix/RAUC A/B rebase from Debian 13 to 14 with health-gated rollback and power-cut survival.
- Raspberry Pi and NVIDIA public commitments of kernel/BSP support for Pi 5 and the Jetson Orin/Thor boards to at least 2032.

## 5. Sources (opened 2026-11-10)
Cited by the claim and re-checked:
- Regulation (EU) 2024/2847: Art. 3(30), Art. 13(5), (8), (9), (10), (19), Recitals 34 and 40. https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R2847
- Freexian ELTS for Debian 13 (amd64 guaranteed, other architectures "on request", not all packages, support "as long as we have customers paying", end 2035-06-30). https://www.freexian.com/lts/extended/docs/debian-13-support/

New sources, found by searching for lifecycle cuts and failures:
1. Debian news, 2026-07-12: Bookworm security support handed to LTS. Architectures cut to amd64/i386/arm64/armhf/ppc64el, and "a few packages are not covered". https://www.debian.org/News/2026/20260712
2. Debian bookworm release page: "All other architectures are no longer supported in bookworm." https://www.debian.org/releases/bookworm/
3. Raspberry Pi engineers advising against an in-place Bookworm-to-Trixie upgrade (secondary reporting quoting Simon Long; I did not open the primary Raspberry Pi post): https://raspberrytips.com/upgrade-raspberry-pi-os-major-release/ and https://www.notebookcheck.net/Raspberry-Pi-releases-free-major-Trixie-OS-update-for-Raspberry-Pi-single-board-computers.1130182.0.html
4. Field report of an in-place upgrade that hung on a Pi 4: https://discussions.flightaware.com/t/inplace-upgrade-to-raspberry-pi-os-trixie/100456
5. Commission CRA guidance C(2026) 5252 (27 July 2026), via secondary summaries: substantial modification means reassessing the support period, with no automatic reset. https://www.orrick.com/en/Insights/2026/09/EU-Cyber-Resilience-Act-New-Guidance-Clarifies-Scope-Reporting and https://www.cyberresilienceact.eu/commission-guidance.html

Reliability note: the cyberresilienceact.eu summary says "Five years is the default, not a floor". This contradicts Art. 13(8) ("the support period shall be at least five years"). Do not cite that sentence. Sources 3 and 4 are secondary or anecdotal, and I did not open the primary C(2026) 5252 PDF.
