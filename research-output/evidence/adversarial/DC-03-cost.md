# DC-03 refuter: lifecycle cost to 2036 (cost and business lens)

| Field | Value |
|---|---|
| Target | DC-03 (Q1, Q168, Q213). Conclusion in `evidence/qbank/W2.md` (Q1, Q168, Q213) and the DC-03 row of `01-FOUNDATION-DECISION.md` §3.1: "Bounded cost to 2036: Debian **$0 if rebased to 14/15**; ELTS not usable for a fleet as-is [C-W2-004]; Ubuntu $0 to 2031 then Pro for Devices (unpublished) [C-W2-006]; Alma $0 to 2035 [C-W2-013]. Favours **A ≈ C > D**." |
| Lens | Cost and business (sole developer, H-1 margins) |
| Protocol | RESEARCH-MISSION.md §2 rule 7. The refuter read only the conclusion text and its cited claims (C-W2-001, 003, 004, 005, 006, 013, 030, 031, 032); no reasoning sections and no other adversarial files. |
| Date | 2026-11-10 (re-check by 2027-05-10) |
| Verdict | **weakened**. The lifecycle *dates* hold. The *cost ranking* "A ≈ C > D" does not follow from them: it compares licence fees only, and gives the paid alternative's price as unknown, so the DC-03 flip test (Debian > cheapest alternative by 25%) has not been run. |

## 1. Re-checking the cited sources

| Sub-claim | Ledger evidence | Holds? |
|---|---|---|
| Debian 13 LTS to 2030-06-30, ELTS to 2035-06-30 | C-W2-001 | Yes (dates only) |
| ELTS is quote-only, rises each half-year, and packages are for the client's own use | C-W2-003, C-W2-004 | Yes. This rules out ELTS for a redistributing vendor without a special agreement, as the conclusion says. |
| Ubuntu Pro for Devices has no published price | C-W2-006 | Yes. Re-opened today: the product page says "a one-time fee per device", 10 years, 15 with Legacy, and gives no price [C-REF-DC-cost-001]. |
| Alma 10 security support to 2035-05-31 | C-W2-013 | Yes, but that is 2035, not 2036, so C also needs a rebase. The cell says "$0 to 2035" and ranks it equal to A. |
| kernel.org 6.12 EOL Dec 2028; CIP 6.12 to mid-2035 | C-W2-031, C-W2-032 | Yes |

## 2. Strongest counter-argument

**"$0 if rebased" is a licence price, not a lifecycle cost.** For a sole developer the dominant 10-year cost is engineering labour per major rebase, and the conclusion prices it at zero.

- **Count of rebases.** A box sold in late 2027 on Debian 13 needs support to 2036 (DC-04). Debian LTS gives about five years per release (13 to 2030-06-30, C-W2-001; 12 to 2028-06-30, C-REF-DC-cost-002). With Debian's roughly two-year release cadence, covering 2036 for free needs **13 → 14 → 15, and probably → 16** (inference from cadence; Debian 14+ end dates are not yet published). Each step changes the kernel line, so each one re-runs the Pi kernel/firmware pipeline (DC-19), the NVIDIA DKMS build (DC-13, see `DC-13-cost.md`), the A/B framework integration (DC-07/DC-12) and the OTA rebase path (DC-05). Ubuntu 26.04 with Pro reaches May 2036 on **one** release (C-W2-005). A one-time per-device fee [C-REF-DC-cost-001] could therefore be cheaper than two or three rebase projects at 1k units, which is exactly the comparison DC-03 asked for and the conclusion did not make.
- **"Free" Debian LTS is sponsor-funded and partial.** Debian's own LTS announcement says "a few packages are not covered" and LTS is limited to five architectures [C-REF-DC-cost-002]. Freexian's September 2026 report shows LTS is done by 20 paid contributors "funded by Freexian's Debian LTS offering" [C-REF-DC-cost-003]. Coverage of any given package depends on the sponsor pool. The cost model needs a line for checking `debian-security-support` against OneMind's real package list each release, and for sponsoring LTS if a needed package is excluded. This is cheap, but not $0.
- **Ranking against an unknown.** The D cell is "unpublished". You cannot rank A > D on cost when D's price is a blank; the honest result is "A ≈ C; D unpriced". The ranking reads as a cost finding, but it is really the G1 redistribution finding (Canonical IP policy, C-W2-050) carried over into the cost row.
- **C is not equal to A.** Alma ends 2035-05-31 (C-W2-013) and also needs a rebase before 2036; the equal ranking holds only if Alma's rebase (bootc switch, C-LAB-fedora-bootc-015) is assumed as cheap as Debian's two or three apt-based ones. That assumption is untested in both directions.

**Counter to the counter (why this is not refuted):** the redistribution blockers are real. ELTS can't be shared with customers (C-W2-004), and modified Ubuntu needs Canonical's approval (C-W2-050). A paid path that cannot legally ship has infinite cost, so Debian may still win. But that is G1, not DC-03.

## 3. New sources (searched for lifecycle cuts, funding and coverage gaps)

| ID | Source | What it shows |
|---|---|---|
| C-REF-DC-cost-001 | https://ubuntu.com/pro/devices (opened 2026-11-10) | One-time fee per device, 10 years, 15 with Legacy; no price. The comparator is a single bounded payment, so the comparison can be modelled once a quote arrives. |
| C-REF-DC-cost-002 | https://www.debian.org/News/2026/20260712 | Bookworm LTS ends 2028-06-30, five architectures, "a few packages are not covered". |
| C-REF-DC-cost-003 | https://www.freexian.com/blog/debian-lts-report-2026-09/ | LTS is paid, sponsor-funded work (20 contributors); scope follows funding. |

Searched and found nothing: any announced cut of arm64 from Debian LTS; any published Freexian funding shortfall in 2026.

## 4. What would flip the decision

- **Toward D (Ubuntu core):** a written Canonical quote for Pro for Devices of roughly **≤ (2 × rebase-labour cost) ÷ units**. At 1k units and an assumed 4–6 founder-weeks per Debian major rebase, that means a one-time fee in the tens of dollars per device, **plus** written redistribution permission (C-W2-050). Both are needed; the fee alone does not flip it.
- **Toward A, settled:** a timed rebase drill (13 → 14 on the lab image with Rugix/RAUC, Pi kernel and NVIDIA DKMS) showing ≤ 2 founder-weeks per rebase. That makes "$0 + small labour" a defensible bound, and the A ≈ C > D row would then be earned.
- **Against A:** `debian-security-support` flagging a package OneMind ships (for example a browser engine for the kiosk UI, or a container runtime) as unsupported in LTS, with no sponsorable fix.

**Required correction:** relabel the DC-03 row "licence cost" and add a labour line per major rebase, or mark DC-03 as **unpriced, ranked on G1 only**.
