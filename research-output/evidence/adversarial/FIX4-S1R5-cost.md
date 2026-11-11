# S1R5 · Rev-4 S1 decision of record (Ubuntu 26.04 + RAUC) · cost / business refuter

**Lens:** cost and business · **Date:** 2026-11-11 · **Refuter round:** 5 (critic pass-4 gap P4-1; touches P4-8)
**Target:** `01-FOUNDATION-DECISION.md` §3.1.6 (c)–(i): the Ubuntu win is CONDITIONAL on G1 (Z-01: Canonical's permission, or a debrand-and-recompile), whose cost §3.1.6 (i) calls "unbounded".
**Read:** §3.1.6 (c)–(i), frozen `scorecard-weights.md` §2 (COND needs "a stated cost and owner") and §4 (C6 anchors), and the cited rows C-W2-006/007/050, C-LIC-011, C-DEC4-010, C-COST-002, C-STEEL-ubu-002.
**Independence limit:** written sequentially by the same agent as the other two S1R5 files (see the [technical file](FIX4-S1R5-technical.md) header).
**New sources:** C-FIX4-001…004, 013 (`sources/FIX4.md`).

> **Explain it like I'm the founder.** Ubuntu's win needs Canonical's permission to ship a changed Ubuntu. We called that cost "unknown". Canonical's own pricing page tells us what the permission most likely is: **"Trademark use" is one of the things listed inside Ubuntu Pro for Devices**, a subscription paid per device. So the probable price of choosing Ubuntu is a per-box fee on every box, including the cheapest Pi, for the life of the box. Debian and AlmaLinux charge nothing for this. The "strip the logos and recompile everything" escape route exists, but history suggests even big projects end up signing a licence instead. Canonical publishes no device price, so we can only bracket it. That bracket should be written down rather than left as "unbounded".

---

## 1. Verdict: **weakened**

The ranking survives: C6 already scores D at 2 for this exact reason, and the G1 row already counts for C in the tie-break. What is weak is the **cost honesty of the COND**. The frozen §2 says a CONDITIONAL gate needs "a named mitigation that has a stated cost and owner". Canonical's own pages now let the run state a provisional cost, and §3.1.6 (i) does not.

## 2. Strongest counter-argument

**2.1 The G1 mitigation is most likely a per-device subscription.** Canonical's device pricing page lists what "Ubuntu Pro for devices" includes: security maintenance, Landscape, Livepatch, certification, support, and **"Trademark use"** [C-FIX4-001]. It can be paid "annually or as a one-time fee for up to 10 years", with a Legacy add-on for years 11–15 [C-FIX4-001, C-FIX4-003]. No per-device price is published [C-FIX4-001, C-W2-006]. The policy says a modified image needs Canonical's approval under a licence "for which you may be required to pay" [C-LIC-011]. The page that sells the device product names trademark use as part of it. The straightforward reading: OneMind's G1 condition would be met by buying Pro for Devices **for every box** that carries the Ubuntu marks.

**2.2 The debrand-and-recompile escape is costly, and the precedent did not take it.** Canonical has required "binary redistributors (such as Linux Mint)" to obtain a licence [C-FIX4-013, SECONDARY]. SFC said permission to redistribute Ubuntu as a whole "remains in question" for non-copyleft packages [C-STEEL-ubu-002, SECONDARY]. A debranded rebuild means rebuilding the archive OneMind ships from source and maintaining that rebuild for ten years. That is a second distribution to run, the kind of work 01 rejected for Buildroot on maintainability grounds (DC-20).

**2.3 The cost lands hardest on the tier F-14 cares about most.** A per-device fee is the same on a Pi 5 greenhouse node as on a GPU server. Debian (A) and AlmaLinux bootc (C) have no per-device licence cost for the core [C-W2-001, C-STEEL4-bootc-014]. On the Lite tier, D's base cost is therefore the only non-zero one among the three finalists.

**2.4 A provisional bound is possible, and should be stated.** Canonical publishes Ubuntu Pro list prices of **$25 per workstation per year** and **$500 per server per year**, without support [C-FIX4-004]. These are not Pro for Devices prices. Two assumptions give a provisional bracket per box over a 10-year life:
- **Low: $0.** Canonical waives the fee, or trademark use is granted without Pro.
- **High: $250.** The device price is at or below the workstation list price, $25 × 10 years.

DC-03's working assumption of about $60 per box [C-COST-002] sits inside that bracket. **This is an assumption from adjacent list prices, not a quote.** A server-class price ($500 per year) on GPU boxes would sit above the bracket and is plausible for the GPU-server flavor. Canonical's paid device services start at $3,000 (Snap store) and $25,000 (SmartStart) [C-FIX4-002], but they are not needed for trademark use.

## 3. Where the counter-argument is weaker (fair limits)
- Pro for Devices also buys things OneMind would otherwise have to provide itself: ten years of ESM over Universe as well as Main, Livepatch, and FIPS and CIS tooling [C-FIX4-003]. Part of the fee is value received, not pure licence cost. Debian's equivalent after year 5 rests on Freexian ELTS, which is quote-only and amd64-only [C-W2-004].
- The page does not say trademark use is available **only** through Pro for Devices. A separate, cheaper trademark agreement may exist.
- C6 = 2 already prices in "a legal process beyond standard copyleft". The ranking does not double-count it.

## 4. What would flip it
- **To refuted:** Canonical quotes a per-device price above about $25 per box per year (above the bracket) for every box carrying the marks, **or** requires Pro for Devices on the whole fleet as the condition for trademark use. D's Lite tier then fails F-14's "simple on a Pi" economics, and the founder should treat G1 as FAIL (map row "Canonical refuses" → **bootc**).
- **To upheld:** Canonical grants trademark use for OneMind-modified images at no charge, or within a Pro for Devices price at or below the DC-03 assumption. The map row "Z-01 granted with a priced Pro for Devices" (D·C6 → 3, D outright) then applies.
- **Required now:** replace "unbounded" in §3.1.6 (i) with the provisional bracket and its assumptions. Ask Canonical in O-1 whether trademark use is sold only inside Pro for Devices. Critic P4-8 stays a founder and Canonical item (Z-01, Z-39); this only bounds it.

## 5. New sources (opened 2026-11-11)
- ubuntu.com source @ `ec15716`: device pricing (Pro for devices incl. "Trademark use"; services price list; certification terms), Pro for Devices page, Ubuntu Pro list prices. [C-FIX4-001…004]
- LWN 586446 (2014-02-14), Canonical's licence requirement for binary redistributors such as Linux Mint (SECONDARY). [C-FIX4-013]
