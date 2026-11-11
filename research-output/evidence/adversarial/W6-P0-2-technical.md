# W6 — Refuter report: P0-2 (CRA Class I "operating system" and the FOSS self-assessment route), technical lens

- **Claim under test (P0-2, 07-security-compliance.md):** OneMind OS is an "operating system", an Annex III Class I important product [C-W6-011, C-W6-017]. If no harmonised standard is applied, Class I needs a notified body (module B+C or H) [C-W6-012]. The OS standard EN 304 626 is still an enquiry draft (Aug 2026) [C-W6-018, C-W6-019]. A product that qualifies as FOSS may self-assess (module A) if its technical documentation is public [C-W6-013]. Decision: **new constraint on D-001 / D1:** keep the EU-sold base image fully FOSS with public technical documentation, and ship "pro" closed features as separate products.
- **Refuter lens:** technical. I read only the conclusion row and its cited sources (RESEARCH-MISSION.md §2 rule 7). I did not read the author's reasoning sections or the other W6 adversarial files before forming this view.
- **Date:** 2026-11-10
- **Sources cited by the claim:** C-W6-011, 012, 013, 017, 018, 019.

## Verdict: **weakened**

Each legal premise is accurate, and the "separate products" tactic is directly supported by the Commission's guidance. The classification premise, however, is stated without saying **what is sold**, and that choice decides the outcome:

- **The downloadable OS image:** it is an OS, Class I. The FOSS route (Art. 32(5)) applies as claimed.
- **A OneMind box (hardware with the OS preinstalled):** under the Commission's whole-product rule, the box is very likely **not** classified as an "operating system". It is also very likely unable to "qualify as FOSS", because it is a hardware product sold for a price. The FOSS route is irrelevant for the box, and so is the notified-body requirement, **unless** the box's core function falls in another Annex III category.

The "fully FOSS" constraint is therefore narrower than stated. It binds the standalone image, not the box. It also stops binding at all once EN 304 626 is cited in the OJ, because full application of a cited harmonised standard opens module A to a closed image too.

## Checks of the cited sources

- **C-W6-011 / 017 (Annex III item I-11; Implementing Reg. 2025/2392):** accurate. 2025/2392 also says integrating a component does not by itself change the class, which is the hook for the counter-argument below.
- **C-W6-012 / 013 (Art. 32(2), 32(5)):** accurate.
- **C-W6-018 / 019 (ETSI enquiry; EN 304 626 V1.0.1 draft):** accurate as of August 2026. The status has moved on since (see N3).

## New sources (opened 2026-11-10; found by searching for standards delays, scope failures and monetisation edge cases)

- **N1. European Commission, CRA application guidance, Annex to C(2026) 5252 (27 July 2026), PRIMARY.** https://ec.europa.eu/newsroom/dae/redirection/document/131456 (PDF text extracted).
  - Example 58 (p. 49): "The mere integration of an operating system does not mean that the smartphone has the core functionality of an operating system."
  - Para. 144: a product "may not have more than one core functionality". Para. 143: manufacturers may not misrepresent core functionality, judged against promotional material, instructions and technical documentation.
  - Para. 145 / Example 61: modules "offered for separate purchase, licensing or subscription" are "standalone products" classified on their own core functionality. Modules supplied **only** as part of an integrated product take the integrated product's class.
  - Para. 18 / Example 9: software that is needed to operate hardware, from the same manufacturer, forms a **single product** with that hardware, even when it is downloaded separately from an app store.
  - Para. 57 / Example 17: a paid version of a FOSS operating system is placed on the market in the course of commercial activity, "irrespective of whether functionally equivalent software is also available free of charge".
  - Para. 149: module A for Class I via standards needs **all** applicable requirements of a harmonised standard applied, **and** the standard's scope must cover all risks of the core functionality.
  - Para. 148: Class I needs a third party only where cited harmonised standards, common specifications or EUCC "substantial" were not (fully) applied, with the Art. 32(5) FOSS exception.
- **N2. Secuvi, "CRA standards are delayed — what manufacturers must do now" (undated, about mid-2026), vendor blog.** https://www1.secuvi.com/blog/compliance/cra-standards-are-delayed-what-manufacturers-must-do-now/. M/606 (C(2025)618): a draft amendment, triggered by the CEN/CENELEC/ETSI report of 2025-12-03, moves the 26 vertical standards from 30.10.2026 to 31.12.2026. The 13 remaining horizontal standards stay at 30.10.2027, about six weeks before CRA full application. The blog says the amendment was "neither adopted nor confirmed".
- **N3. SecureHabits, "CRA harmonised standards: development status" (2026-10-19), secondary tracker.** https://www.securehabits.nl/knowledge/cra-harmonised-standards-overview/. EN 304 626 is at "prEN vote", with votes closing mid-November 2026. Horizontal EN 40000-1-4 (generic security requirements) "remains in drafting". No OJ citation date has been given for any of them. CRA notified bodies are "still getting up to speed".

## Strongest counter-argument

1. **Classification is decided per product sold, and a box is probably not an "operating system".** N1 Example 58 is directly on point: a device that integrates an OS does not take the OS's core functionality. A OneMind box whose intended purpose is "home or field hub that runs apps, NATS and TAK" has one core functionality (para. 144), and it is not "abstracting hardware and controlling execution" as a product. It is likely default category (module A, no notified body, no FOSS condition needed). The risk runs the other way. Depending on how it is marketed, the box could fall into **another** Annex III category: router (I-12), VPN (I-5), smart-home virtual assistant (I-16) or identity management (I-1). Container runtime systems are Class II, and Art. 32(5) does not help a hardware product there. P0-2 never runs this analysis for the box SKU.
2. **For the box, the FOSS route is likely unavailable anyway.** Art. 32(5) speaks of "products ... qualifying as free and open-source software". A priced hardware product is not software under a FOSS licence, and N1 Example 17 places even a paid version of a FOSS OS on the market as commercial (this is an interpretation that needs counsel). The "keep the image fully FOSS" constraint buys nothing for the box SKU.
3. **"Pro as separate Market apps" works only if the apps are optional.** N1 para. 145 supports it: separately sold modules are their own products, each classified on its own function. Para. 18 / Example 9 cuts the other way: if a box's intended function needs a OneMind-supplied app, that app is part of the box product even when it is installed later. The boundary must be "pro = optional extras", not "pro = needed to deliver the advertised use".
4. **The FOSS constraint is a hedge against a standards delay, not a permanent rule.** EN 304 626 is in its formal vote now (N3). If it is cited in the OJ before the first EU sale **and** fully applied, module A is open to an image with closed parts (N1 paras. 148–149). The caveat is para. 149: the vertical standard must cover all the OS's risks. Its generic baseline (EN 40000-1-4) is still in drafting, and the horizontal deadline is October 2027 (N2, N3). The citation date is therefore genuinely uncertain, so the hedge is reasonable. It should be labelled as conditional on the standards timeline.

## Required corrections to the decision text

- Split the conclusion by SKU:
  - **(a) Standalone/downloadable image:** Class I OS. Either the FOSS route (Art. 32(5), public technical documentation) or full application of cited EN 304 626, or a notified body.
  - **(b) Box:** classify by the box's single core functionality (N1 paras. 141–145). This is likely default category; screen it against I-1, I-5, I-12 and I-16 and the Class II container-runtime entry. The FOSS route is likely not applicable.
- Add N1 para. 145 as the evidence for "pro as separate products". Add the para. 18 / Example 9 limit: anything needed for the box's intended function is part of the box.
- Re-label the D-001 constraint as **"until a harmonised OS standard is cited and fully applied"**, not as a permanent product rule.

## What evidence would flip the decision

- **To refuted (no FOSS constraint needed on D-001):** (a) EN 304 626 passes the November 2026 vote and is cited in the OJ before OneMind's first EU sale, with a gap analysis showing OneMind applies it fully (para. 149); or (b) counsel confirms that OneMind will place on the EU market **only** boxes whose core functionality is not an Annex III category, and no standalone image.
- **To upheld (as written):** (a) the EN 304 626 vote fails, or its OJ citation slips past December 2027; (b) counsel or an ADCO/Commission FAQ classifies a general-purpose "app host" box as having the core functionality of an operating system (the reverse of Example 58 for this product type); (c) OneMind decides the standalone image is the primary EU SKU.
- **To a stronger constraint:** counsel reads Art. 32(5) "qualifying as FOSS" as excluding an image that carries non-free firmware blobs (Pi firmware, NVIDIA drivers). The FOSS route would then close even for a pure-OneMind-code image, and a notified body (B+C) would become the base case.

## Ledger rows

C-REF-W6-technical-001, 006, 007 and 008 in `evidence/claims/REF-W6-technical.csv` (TAG REF-W6-technical).
