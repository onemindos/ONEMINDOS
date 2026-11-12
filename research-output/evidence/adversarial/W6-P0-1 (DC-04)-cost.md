# W6 adversarial refutation: P0-1 (DC-04), cost and business lens

- **Claim:** The CRA requires a support period of at least five years, with the end month and year shown at purchase, but not one base-OS release lasting that long. Art. 13(10) lets OneMind support only the latest version. Debian 13 LTS runs to 2030-06-30 and Freexian ELTS to 2035-06-30 (amd64 guaranteed). So a box sold from December 2027 can comply by rebasing in place to later Debian releases. The binding limits are the in-place rebase path and per-board vendor kernel support.
- **Refuter lens:** cost and business. **Date:** 2026-11-10. **Verdict:** **weakened**.

## 1. What holds up (checked against the primary text)

I downloaded the full regulation from EUR-Lex and extracted the articles.

- Art. 13(8): "the support period shall be at least five years", or the expected use time if that is shorter. It must reflect "reasonable user expectations, the nature of the product". The manufacturer may take into account "the support periods of integrated components that provide core functions and are sourced from third parties".
- Art. 13(19): the end date, "including at least the month and the year", must be given at the time of purchase.
- Art. 71: the regulation applies from 11 Dec 2027. Art. 14 (reporting) applies from 11 Sep 2026.
- Nothing in the CRA ties compliance to one upstream release. The claim's core legal reading is correct.

## 2. The strongest counter-argument

**Art. 13(10) is narrower than the claim assumes, and its own condition is the one OneMind's hardware is most likely to break.**

The verbatim text: "Where a manufacturer has placed subsequent substantially modified versions of a **software product** on the market, that manufacturer may ensure compliance with the essential cybersecurity requirement set out in **Part II, point (2)**, of Annex I only for the version that it has last placed on the market, provided that the users ... have access to the version last placed on the market **free of charge** and **do not incur additional costs to adjust the hardware and software environment**."

Five problems follow from that wording.

1. **Scope.** The clause covers a "software product" and only one requirement, Annex I Part II(2), timely security updates. A OneMind box is a hardware product with digital elements. Whether a base-OS rebase on a sold box counts as "a subsequently placed version of a software product" is an interpretation, not settled law. The Commission guidance (C(2026) 5252, approved 27 Jul 2026, not yet formally adopted, per cyberresilienceact.eu) has no dedicated section on combined hardware and software products. Every other Part II duty, including the SBOM, vulnerability handling and coordinated disclosure, still covers every box in the field until its stated end date.
2. **The "no additional cost to the hardware environment" condition fails for some boards.**
   - NVIDIA ended JetPack 4 (Ubuntu 18.04) in November 2024. Canonical's migration advice for those boards is to move to Orin hardware (ubuntu.com/blog/jetpack-4-eol). If a newer base needs a newer BSP that the shipped module never gets, the user bears a hardware cost, and the 13(10) safe harbour does not apply.
   - Debian removed armel from forky (#1111010). The trixie release page warns that i386 and armel "will be removed in a future release". A board family dropped upstream is the same failure.
   - Jetson does not run on Debian at all; JetPack is Ubuntu 22.04 with a 5.15 kernel. So "rebase to later Debian" does not cover the Robotics edition. Its support end date depends on NVIDIA's L4T lifecycle, which has no public end date for r36.
3. **Rebasing may itself be a substantial modification, and each one costs a conformity assessment.** Recital 39 and the guidance treat a change as substantial when it alters the cybersecurity risk, and they say new features are typically substantial. A Debian major version brings a new kernel, systemd, OpenSSL and toolchain. That is arguably substantial, and a substantially modified product counts as newly placed on the market (Art. 3(30), Arts. 21 and 22). For a solo founder, each rebase then costs new technical documentation and a new conformity assessment per edition, on top of the engineering.
4. **The arithmetic needs two unreleased Debian releases, which makes the dependency open-ended.** A box sold in Dec 2027 needs support to at least Dec 2032. The claim's own premise is a 10-year horizon, and IIoT and robotics buyers' "reasonable user expectations" often exceed five years, so 2037 is more likely. Free Debian 13 LTS ends 2030-06-30. Covering the gap needs:
   - forky (Debian 14, unreleased, "when ready") and probably Debian 15, each validated on x86, Pi 5/CM5 and RK3588 within the support window; or
   - Freexian ELTS. ELTS guarantees only amd64. arm64 depends on "the request of our customers", the price is by quote only, and even base packages are covered only "as long as we have customers paying for Debian 13 support".

   So the stated end date (Art. 13(19)) is a promise backed by an upstream that is not yet released, plus a vendor contract with no published price.
5. **The in-place path is not free in practice.** Raspberry Pi's official docs say: "don't perform an in-place update ... start again by installing a new image", and "we strongly recommend that you use a clean install". Community bookworm-to-trixie guides report orphaned kernels on 32-bit boards. If the user must reflash and restore, the "free of charge, no extra cost" condition depends on OneMind having a proven A/B whole-image rebase with data preserved. That path is still unbuilt and untested across three architectures.

**The business consequence.** "The CRA alone does not force a different base" is true in law but misleading for cost. The CRA turns the base OS's lifecycle into a priced liability:

- a recurring rebase and re-assessment programme every about two years;
- an unquoted ELTS contract for arm64, or no arm64 ELTS at all;
- a support date printed at the point of sale that OneMind cannot fully control.

A base with a contractual 10-year window on all target arches changes this. Ubuntu Pro (12 years, arm64 included, and the base Jetson already uses) or a fully owned Buildroot/Yocto image, where OneMind controls the package set, swap that recurring cost for a known one. The claim does not compare those costs. "Debian alone suffices" is therefore unproven for the Robotics and Pi editions, though roughly right for x86.

## 3. New sources (searched for lifecycle cuts and failures; each opened)

1. Freexian, *About Debian 13 Trixie* (ELTS): https://www.freexian.com/lts/extended/docs/debian-13-support/. Only amd64 is confirmed. Other arches depend on customer requests, coverage is "as long as we have customers paying", and there is no price.
2. Raspberry Pi documentation, *Raspberry Pi OS*: https://www.raspberrypi.com/documentation/computers/os.html. Officially no in-place major upgrade; clean install recommended.
3. Canonical, *JetPack 4 EOL*: https://ubuntu.com/blog/jetpack-4-eol. A vendor BSP lifecycle cut (Nov 2024) with hardware replacement as the migration path.
4. Debian bug #1111010, *phase out armel for forky*: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=1111010. Also the trixie release page, https://www.debian.org/releases/trixie/, which warns that "Both architectures will be removed in a future release." This is an architecture deprecation precedent.
5. cyberresilienceact.eu, *Commission guidance* summary of C(2026) 5252: https://www.cyberresilienceact.eu/commission-guidance.html. The substantial-modification test is risk-based. The support period is reassessed and "does not automatically reset". Secondary source; it is still a draft pending formal adoption.

The claim's own primary source, CRA Art. 13(8), (9), (10), (19) and Art. 71, was re-verified verbatim from the EUR-Lex HTML.

## 4. What would flip the decision

**To upgrade to `upheld`** (any two of these):

- A tested A/B whole-image rebase, trixie to forky, on x86, Pi 5 and one RK3588 board that preserves user data with no reflash. That meets 13(10)'s "no additional cost" condition in fact.
- A written Freexian quote covering arm64 for Debian 13 ELTS, at a price that fits the box margin.
- Commission or ADCO text, or the adopted C(2026) 5252, confirming that 13(10) applies to the OS of a hardware product and that a base-OS major update with no new intended purpose is not a substantial modification.

**To move to `refuted`:**

- Adopted guidance, or a market-surveillance or notified-body position, saying a major base-OS upgrade on a sold device is a substantial modification requiring a new conformity assessment.
- Or a statement that 13(10) does not cover hardware products.
- Or Debian dropping arm64 board support that OneMind ships, or forky slipping past about 2028.
- Or NVIDIA publishing an L4T r36 end date before the printed support end with no BSP path for shipped Orin modules.

## 5. Recommended response by the author (required for `weakened`)

1. Restate the claim per edition: x86 = Debian plus optional ELTS; Pi 5 and RK3588 = Debian, ELTS not guaranteed; Jetson = Ubuntu/L4T-bound, Debian rebase not applicable.
2. Treat the support end date as the minimum of the dates covered by the base OS, the BSP and the vendor contract, per edition.
3. Budget a rebase-plus-reassessment cycle about every two years in the business model.
4. Get a Freexian arm64 quote before committing to a printed end date beyond 2030-06 on ARM boards.
