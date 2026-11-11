# W6 · P0-2 · Refuter (cost and business lens)

**Claim under test (P0-2):** OneMind OS is an Annex III Class I "operating system" under the CRA. Integrating a container runtime does not by itself move it to Class II. Without fully applied harmonised standards, Class I needs a notified body (B+C or H) under Art. 32(2). EN 304 626 (operating systems) is only an enquiry draft (V1.0.1, Aug 2026) with no citation date. Art. 32(5) lets FOSS products self-assess (module A) if their technical documentation is public. **Therefore keeping the EU-sold base image fully FOSS is the only route to self-assessment without a cited standard.**

**Refuter:** independent; given only the claim and its sources. Date: 2026-11-10. Lens: cost and business.

**Verdict: WEAKENED.** The legal mechanics are right; I checked them word for word. The conclusion ("the only route", "EU-sold base image fully FOSS") goes too far in three ways. Two of them change what the business should actually do.

---

## 1. What survives (checked against the primary text)

| Element | Check | Result |
|---|---|---|
| Operating systems is Annex III Class I item 11 | CRA Annex III (EUR-Lex 32024R2847) | Holds |
| Art. 32(2): Class I without fully applied hEN, common spec or EUCC "substantial" goes to module B+C or H | Verbatim Art. 32(2) | Holds |
| Art. 32(5): products "qualifying as free and open-source software" in Annex III may use any Art. 32(1) procedure (incl. module A) if their technical documentation is public | Verbatim Art. 32(5). Note it covers **all of Annex III, Class II included** | Holds, and is wider than the claim says |
| FOSS definition, Art. 3(48): source openly shared, under a licence granting rights to access, use, modify and redistribute | Verbatim | Holds |
| Classification follows core functionality; integrated components do not change the class by themselves | Implementing Reg. (EU) 2025/2392, recitals 3–5 | Holds |
| EN 304 626 is a draft with no OJ citation | ETSI docbox V1.0.1 (2026-08-12); ETSI press release 13 Aug 2026 (enquiry and vote to "mid-September to mid-November 2026"); securehabits.nl tracker (16 Oct 2026: "prEN vote") | Holds |
| Notified-body route is costly and scarce | cybercertlabs (late June 2026: "zero notified bodies have been designated for the CRA" in NANDO); Art. 35(2) target of 11 Dec 2026 is best-effort only | Holds and **strengthens** the claim's cost premise |

## 2. Strongest counter-argument

### 2a. "Only route" ignores the actual deadline. The standard will probably arrive before it bites.
The essential requirements and conformity assessment apply from **11 December 2027** (Art. 71(2), verbatim). For self-assessment, what matters is whether EN 304 626 is cited in the OJ before OneMind's first EU placement after that date, not whether it is cited today. In November 2026 ETSI is at the combined enquiry and vote stage, with seven of 17 votes closing by mid-November 2026. Normal steps follow: ratification, a HAS consultant assessment, then citation. That leaves about 12 months of slack. Art. 32(1)(d) and Art. 27 add two more routes: EUCC at "substantial", and Commission **common specifications** (Art. 27(2)–(5)) if standards slip. "Only route" holds for **today**, not for the date that matters. Locking the product to a full-FOSS image now, a ten-year architectural constraint, buys protection against a gap that may close by itself in 2027.

**Business cost of getting this wrong:** the FOSS base-image rule means no closed-source value in the base image (for example a proprietary fleet agent, NVIDIA-optimised userspace or licensed codecs). In an Apache-2.0 open-core model that pushes all monetisation into add-ons, services and hardware margin, possibly for a requirement that disappears before it applies.

### 2b. The FOSS route cannot be met on two of the three target platforms, so "keep the image fully FOSS" is not achievable as stated.
- **Raspberry Pi 5:** the bootloader EEPROM firmware (`firmware-2712/*`) is released under a **"License: custom"** non-free licence, per the `raspberrypi/rpi-eeprom` LICENSE file (repo active, pushed 2026-11-10). The rest of the repo is BSD-3. The Pi 5 cannot boot without that blob. Any Pi 5 image carries it, or relies on it already being in the board's EEPROM.
- **Jetson:** the L4T/Jetson Linux BSP components fall under NVIDIA's Tegra Software License Agreement. Only the kernel and patches are GPLv2. In NVIDIA's own forum thread, a 2017 promise to allow redistribution was never shown to be honoured in the licence text. In 2019 NVIDIA staff told a commercial seller to "consult with a lawyer". CUDA userspace is proprietary on every NVIDIA target.

If "qualifying as FOSS" is judged on the **whole product** (2025/2392 recital 3: assess "the product as a whole"), a Pi 5 or Jetson image is not FOSS. The x86 edition without NVIDIA might be. The decision should split by edition, not apply one blanket rule.

### 2c. The revenue product, the box, probably is not an "operating system", and a box is not "software" anyway.
OneMind sells **Edge / Lite / Pro / Robotics / Omni / Cluster editions and boxes**. Two points follow:
1. Art. 32(5) applies to products "qualifying as free and open-source software". A hardware appliance with closed firmware is not software and cannot qualify. **The FOSS route never helps the boxes.**
2. 2025/2392 recital 5 says that a product able to perform a category's functions is not covered if its core functionality differs. A home server or robotics appliance is arguably not an "operating system" (abstract hardware interface) any more than a laptop is. The box may fall in the **default category, module A, with no notified body**, whether or not the image is FOSS. The box could instead fall under a different Annex III item. Candidates are Class I item 16, "smart home general purpose virtual assistants" (OneMind's AI controlling home devices), and item 12, routers (mesh and off-grid networking). The claim does not look at either. Item 16 would need its own vertical standard, so EN 304 626 would not help.

So the FOSS rule applies to only one channel: the **downloadable software image** sold or distributed in the EU. Applied there, the cost-benefit is narrower than the claim implies.

### 2d. Class II risk cuts the other way, and the claim underplays it.
If an authority reads OneMind's core function as "run and manage containerised apps on k3s" (Class II item 1, "container runtime systems that support virtualised execution of operating systems and similar environments"), then a cited OS standard **never** gives self-assessment, because Art. 32(3) has no hEN escape. In that case Art. 32(5) FOSS would be the **only** non-notified-body route. This **supports** keeping the software image FOSS, but for a different reason than the claim gives. The Class I/II boundary is the bigger cost risk and should be stated as such.

## 3. New sources (found by looking for failure, delay and lock-in evidence; all opened)
1. CyberCert Labs, "CRA Notified Bodies 2026": zero CRA notified bodies in NANDO as of late June 2026; capacity target is best-effort. https://www.cybercertlabs.com/case-studies/insights-cra-notified-bodies-2026/
2. SecureHabits, "CRA harmonised standards: development status (October 2026)": EN 304 626 at prEN vote; no citation date; "CRA notified bodies are still getting up to speed". https://www.securehabits.nl/knowledge/cra-harmonised-standards-overview/
3. Raspberry Pi `rpi-eeprom` LICENSE: `firmware-2712/*` (Pi 5) under a custom non-free licence. https://github.com/raspberrypi/rpi-eeprom/blob/master/LICENSE
4. NVIDIA Developer Forums, L4T commercial redistribution thread (2017–2019): the promised licence change was not shown in the text; staff advise consulting a lawyer. https://forums.developer.nvidia.com/t/licensing-issue-selling-product-including-jetson-tx2-bundled-with-l4t-and-self-developed-software/51156
5. Primary text re-read verbatim: CRA Art. 3(48), 27, 32(1)–(5), 71(2), Annex III (EUR-Lex 32024R2847); Reg. (EU) 2025/2392 recitals 3–5 and Annex items 8, 11, 12, 16, 17 and Class II item 1.

## 4. What would flip the decision
- **Towards REFUTED** (drop the FOSS-image constraint): EN 304 626 published as an EN and **cited in the OJ before about Q3 2027**, or Commission common specifications for OS adopted. Then Class I module A is open through standards and the FOSS rule has no compliance value. Also refuted if Commission CRA guidance or FAQ says a hardware appliance with an integrated OS is classified by the appliance's function, not as an "operating system", **and** OneMind sells mainly boxes.
- **Towards UPHELD** (keep it, even stricter): the EN 304 626 vote fails or citation slips past 11 Dec 2027; or guidance puts k3s-based app platforms in **Class II item 1** (then FOSS is the only non-NB route); or notified bodies stay at about zero in NANDO into 2027, or quote high prices for B+C.
- **Needed either way:** a legal opinion on whether non-free firmware blobs (Pi 5 EEPROM, Jetson L4T, NVIDIA userspace) in or under an image stop it "qualifying as FOSS" under Art. 3(48) and 32(5). If they do, the FOSS route is closed for the Pi and Jetson editions whatever OneMind decides.

## 5. Recommended rewording (for the author's response)
> Keep the **downloadable x86/generic software image** fully FOSS, with public technical documentation, as a hedge for **Class II** classification and for EN 304 626 slipping past 11 Dec 2027. Treat **boxes** and the **Pi 5 / Jetson editions** separately: their firmware is non-free, so they need either a cited standard (Class I module A), a default-category classification, or budget for a notified body. Re-check the EN 304 626 OJ status and NANDO by **2027-05-10**.
