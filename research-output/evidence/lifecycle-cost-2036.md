# Lifecycle cost to 2036 per device (DC-03, pass-2 gap #12)

**Date:** 2026-11-11 · **Tag:** COST · **Closes:** critic pass-2 gap #12 (DC-03 "bounded, not quoted"; rebase labour unpriced) as far as public evidence allows · **Bank IDs:** Q1, Q168, Q213 (DC-03), with inputs to Q167 (DC-04) and Q313 (W16)
**Serves requirements:** R-3, H-1, M-6, M-8, F-1, F-11, F-14, R-1, D-001
**Claim IDs** resolve in `evidence/claims/COST.csv` (new, C-COST-001…014) and the existing per-tag ledgers. **Model:** `evidence/sources/COST/cost-model.py` (inputs as code; output in `cost-model-output.txt`; hashes in `SHA256SUMS`). Every number below is reproducible from that script.

> ### Explain it like I'm the founder
> "Debian is free" is true for the licence and false for the work. Over ten years, the real bill for any base OS is mostly **your hours**: moving the image to each new major release, keeping the build green, and doing the security paperwork the EU's Cyber Resilience Act (CRA) now demands. Paid bases swap some of those hours for a fee.
> We priced all four options with one formula and one explicit wage. Here is the result at the middle assumption, per device, for the whole life to 2036. **Debian ≈ $400 at 1,000 boxes and ≈ $40 at 10,000.** **Ubuntu Pro for Devices costs about the same at 1,000 boxes, *if* Canonical's secret price is around $60–70 a box. It costs about three times more at 10,000.** **Red Hat Device Edge is the most expensive, about $1,400–1,750 a box,** because it is paid every year. **Building your own Yocto OS costs about $900 a box at 1,000 and $90 at 10,000,** and needs the most hours.
> The cheapest option changes with fleet size: fixed hours get spread across more boxes, while a per-box fee does not shrink. **Cost alone does not flip the ADR-001 decision.** Debian is never more than 25% above the cheapest alternative. The one exception would be Canonical quoting under about **$18 a box at 1,000 units** (under about **$2 at 10,000**). Each box running a Jetson robot adds roughly $50–400 at the middle assumption. That cost is mostly NVIDIA's branch upgrades, and it is about the same on every base.

---

## 1. The answer

| # | Finding | Evidence |
|---|---|---|
| COST-1 | **Labour, not licences, is the dominant 10-year cost for every base except Red Hat Device Edge (RHDE).** At the middle (base) assumptions, Debian needs about 1,680 base-specific hours plus about 1,480 CRA hours over 2027–2036. That is about $380k at $120 an hour. | §5, model |
| COST-2 | **Per device, base + CRA, 2027–2036 (base scenario): at 1k units** A Debian $403 · D Ubuntu Pro $385 · C RHDE $1,756 · Y Yocto $900. **At 10k units** A $40 · D $120 · C $1,391 · Y $90. Low–high ranges are in §6. | model |
| COST-3 | **The DC-03 flip condition is not met.** Debian's bounded cost exceeds the cheapest alternative's by at most 5% (1k, base: A $403 vs D $385), well below the 25% margin. At 10k Debian is the cheapest. **D flips DC-03 only if Canonical quotes a 10-year Pro for Devices fee ≤ about $18 at 1k units, or ≤ about $2 at 10k (before the Legacy uplift).** That would need to come with written redistribution permission, which is priced separately (G1). | §7; C-COST-002, -003, C-W2-050 |
| COST-4 | **Debian + ELTS is cost-neutral only when the fleet-wide ELTS fee is ≤ about $4,800 a year** (base; $20,400 at high labour rates). ELTS saves one or two rebases. Its contract still forbids sharing packages with third parties, so it is unusable for shipped boxes without a special agreement. | §7.2; C-W2-004, C-COST-006 |
| COST-5 | **RHDE is a per-device annual subscription.** The only public anchor is a reseller listing: $806.55 MSRP for 3 years (about $269 a year, SECONDARY). Even at an assumed 80% OEM discount (about $50 a year), it is the most expensive path at both fleet sizes. The **free RHEL-family path (AlmaLinux 10 bootc)** costs about the same as Debian ($406 at 1k, $41 at 10k), but has no Pi 5 or Jetson path of its own. | C-COST-009, -010; §6.3 |
| COST-6 | **A Yocto own-BSP is cheap in fees and expensive in hours** (about 5,700 base-specific hours, base). It beats Ubuntu Pro at 10k units, never beats Debian, and its high case (11,400 hours) is beyond one developer (M-6). | §6 |
| COST-7 | **Jetson branch upgrades cost about the same on every base**: roughly $48–394 per Jetson device at base assumptions, falling to $5–33 on RHDE. They are driven by NVIDIA's branch cadence (r35 2022 → r36 Dec 2023 → r38 Aug 2025 → r39 Jun 2026) and fixes that ship only at branch head. After Orin modules stop shipping (Jan 2032), a partner maintenance tail is quote-only. | §9; C-W7-006, C-REF-W7-T-004, -005, C-REF-W7L-001, C-W2-030 |
| COST-8 | **The CRA lines are about the same size as the base-specific lines** (about 1,400–1,500 hours, base) and roughly base-neutral. A paid base does not remove the manufacturer's Art. 13/14 duties. Each major rebase adds documentation work, which is the one CRA line that differs by base. | §10; C-W6-002…005 |

**Bottom line for ADR-001:** DC-03 moves from "no ranking" to **"A ≈ D at 1k units, A < Y < D ≪ C at 10k units; flip condition not met."** That ranking is **conditional** on (i) the rebase-hours assumption (T-W3-04 must measure it) and (ii) the Pro for Devices quote. Both are named in §12 with their thresholds.

---

## 2. Glossary

| Term | Meaning here |
|---|---|
| **Lifecycle cost** | Everything OneMind pays to keep a box's OS secure and supported from first sale (late 2027) to 2036-12-31: fees and labour. Hardware, app development and cloud services are excluded. |
| **Major / rebase** | Moving a fielded box to the next major OS release (Debian 13 → 15, RHEL 9 → 10, Yocto LTS → next LTS) through the A/B update system, without a reflash. |
| **Per device** | Total cost to 2036 ÷ units. Fixed costs (hours) shrink with more units; per-box fees do not. |
| **Base-specific vs common** | Base-specific lines differ between the four options and decide DC-03. Common lines (CRA, Jetson) are reported separately so they don't hide the comparison. |
| **ESM / Pro for Devices** | Canonical's paid security maintenance. For devices it is a one-time or annual fee for up to 10 years, and years 11–15 need the Legacy add-on [C-COST-002]. |
| **ELTS** | Freexian's paid Debian Extended LTS. For Debian 13 it runs to 2035-06-30 and covers only packages customers use [C-COST-006]. |
| **RHDE** | Red Hat Device Edge: RHEL binaries with edge pricing and MicroShift support [C-COST-009]. |
| **Own-BSP (Yocto)** | OneMind builds the whole OS from source with Yocto layers (meta-tegra, meta-raspberrypi) and owns every package's security fixes. |
| **L / B / H** | Low, base and high scenario. Each runs all of its own assumptions together. |
| **Loaded hourly rate** | Wage plus overhead (taxes, tools, benefits). It is what an hour of engineering really costs the company. |

---

## 3. Scope and method

- **Horizon.** Labour from 2027 to 2036 (10 years). Per-device subscriptions from 2028 to 2036 (9 years). Every unit is assumed to need support to 2036-12-31. This is conservative: units sold later need support for fewer years under the horizon, but their CRA periods run past it (§10).
- **Formula.** Per device = (base-specific hours × rate + fixed $/yr × 10) ÷ units + per-device fees. CRA and Jetson are added the same way, and reported separately.
- **Scenarios.** L, B and H move every assumption together. §8 adds a one-variable sensitivity on the hourly rate.
- **What is not in the number.** (a) Canonical's redistribution or trademark agreement (G1, C-W2-050). (b) A Freexian ELTS fee (it appears as a break-even instead). (c) Red Hat OEM or embedded terms. (d) Notified-body fees (CRA scenario only). (e) A Jetson partner tail after 2032. (f) k3s and application maintenance, which are the same on every base (the Kubernetes treadmill is W4's, C-W4-012). Items (a)–(e) are marked **quote needed**.

---

## 4. Assumptions (all explicit; change them in `cost-model.py`)

| ID | Assumption | L | B | H | Basis |
|---|---|---|---|---|---|
| A-01 | Loaded hourly rate (USD) | 65 | 120 | 300 | L = BLS median for software developers, QA analysts and testers, $64.44 an hour, with no overhead [C-COST-012]. B = BLS developer median $135,980 a year ÷ 2,080 h ≈ $65 × about 1.8 overhead (**assumption**). H = Canonical's published consulting rate, $2,400 a day ÷ 8 [C-COST-002] |
| A-02 | Debian majors to 2036 | 2 | 3 | 4 | Observed cadence about 2 years (11: 2021-08, 12: 2023-06, 13: 2025-08), with about 5 years of free support each [C-COST-007]. Projected (inference): 15 (~2029, to ~2034) and 17 (~2033, to ~2038). An A/B image can skip a release (it is rebuilt fresh, not upgraded with apt in place), so L = 13→15→17. B adds one more step for slot/boot-partition growth or Pi timing [C-REF3-DC-longevity-001, C-REF-DC-robotics-009]. H = every release |
| A-03 | Hours per Debian major (image, Pi kernel, NVIDIA DKMS, RAUC slots, k3s gate, tests) | 80 | 160 | 240 | The DC-03 cost refuter's bounds: "≤ 2 founder-weeks" settles A, and "4–6 founder-weeks" is its working assumption (`adversarial/DC-03-cost.md` §4). **Unmeasured: T-W3-04 must record it** |
| A-04 | Debian base-specific hours a year (snapshot rebuilds, LTS coverage check per release, Pi archive pin, kernel line) | 60 | 120 | 200 | 28-… §4.2 estimate of 25–100 h a year per kernel line [C-W18-010 basis], plus the coverage check named by the refuter [C-REF-DC-cost-002] |
| A-05 | Debian fixed $ a year: optional Freexian LTS sponsorship | 0 | 1,200 | 4,800 | Published yearly levels run from €255/$300 to €24,480/$28,800 [C-COST-005]. Sponsoring protects the 2028–2030 LTS years that OneMind relies on [C-REF3-DC-longevity-003] |
| A-06 | Ubuntu Pro for Devices 10-year one-time fee per device (before Legacy) | $10 | $60 | $250 | **No price is published** [C-COST-002, -003, -014]. The model is volume- and compute-module-based [C-COST-004]. H = the Workstation list price, $25 a year × 10 [C-COST-001], as a ceiling for a discount-model product. B and L are **assumptions**. **Quote needed (O-1)** |
| A-07 | Legacy uplift (needed to reach 2036-12 on 26.04; Pro ends May 2036 [C-W2-005]) | ×1.5 | ×1.5 | ×1.5 | "Legacy price is 50% more" [C-COST-001]. The alternative, one rebase to 28.04, is the H case's extra major |
| A-08 | Ubuntu majors / hours per major / base-specific hours a year | 0 / 80 / 50 | 0 / 160 / 100 | 1 / 240 / 180 | 26.04 + Pro + Legacy needs no rebase. ESM also covers Universe [C-COST-001], so slightly fewer hours than Debian (**assumption**) |
| A-09 | RHDE per-device subscription per year | $50 | $150 | $269 | H = reseller MSRP $806.55 ÷ 3 years, Premium tier [C-COST-010, SECONDARY]. A Standard tier exists, price not seen [C-COST-011]. B and L assume Standard and OEM discounts. **Quote needed (O-3)** |
| A-10 | RHEL bootc majors / hours per major | 1 / 40 | 1 / 80 | 2 / 160 | RHDE on Jetson is aligned with RHEL 9.8 [C-W2-041]. RHEL 10's ten years end about 2035 [C-W2-010]. `bootc switch` measured in the lab [C-LAB-fedora-bootc-015] |
| A-11 | RHEL-family base-specific hours a year (includes the Fedora Pi 5 flavor, rebased every 6–12 months, because RHEL has no Pi 5 path) | 80 | 180 | 350 | 03 §3 gate C·G2 [C-W2-015] |
| A-12 | Yocto LTS migrations / hours per migration | 2 / 120 | 3 / 240 | 5 / 480 | LTS every 2 years, 4-year support (Kirkstone 2022, Scarthgap 2024, Wrynose 2026 to Apr 2030) [C-COST-008, C-W2-034]. L skips every other LTS |
| A-13 | Yocto base-specific hours a year (own CVE triage and patching for every recipe, kernel, BSP layers) | 250 | 500 | 900 | **Assumption.** HAOS needs a funded team for the same pattern (03 §12, C-W2-047). Commercial CVE tooling is quote-only (not priced) |
| A-14 | Yocto fixed $ a year (build servers / CI) | 600 | 2,400 | 6,000 | **Assumption** (from-source builds; DC-20 lab not run) |
| A-15 | CRA hours a year (vulnerability handling, Art. 14 reporting, SBOM/advisories, support-period notices) | 60 | 120 | 250 | **Assumption.** Duties from C-W6-001…005 |
| A-16 | CRA one-time technical documentation (module A) / extra per major rebase | 80 / 20 | 160 / 40 | 300 / 80 | **Assumption.** A major rebase may count as a "substantial modification" (C-REF-W6-technical-001 context) |
| A-17 | CRA hosting of every update for ≥ 10 years (Art. 13(9)), $ a year | 300 | 1,200 | 3,000 | **Assumption** [C-W6-003] |
| A-18 | Jetson share of fleet; NVIDIA branch upgrades to 2036; hours per branch | 20%; 3; 80 | 20%; 4; 160 | 20%; 5; 320 | Orin went r35 (2022) → r36 (Dec 2023) → r39 (Jun 2026) [C-W7-006, C-REF-W7-T-004]; fixes ship only at branch head [C-REF-W7-T-005]. Share is an **assumption** |
| A-19 | Jetson field reflash: fraction of Jetson units × cost per reflash | 0 × $40 | 10% × $100 | 100% × $250 | Rootfs A/B can't be enabled over the air [C-REF-DC-cost-005]; a failed cross-branch OTA needed a USB reflash [C-REF-DC-cost-004]. **Assumption** |
| A-20 | Jetson labour multiplier per base | A, D 1.0 | C 0.6 | Y 0.8 | RHDE ships a pre-built Jetson image [C-W2-041]; meta-tegra tracks branches [C-STEEL-jb-009]. **Assumption** |

---

## 5. Why the major-release counts differ (the lifecycle facts)

| Base | Support ends (primary) | To cover 2036-12-31 | Majors (L/B/H) |
|---|---|---|---|
| **A. Debian 13** | Security 2028-08-09, LTS 2030-06-30, ELTS 2035-06-30 [C-COST-007] | Free path: rebase to 15 and 17 (projected), or 14 → 15 → 16 → 17 | 2 / 3 / 4 |
| **A2. Debian 13 + ELTS** | ELTS 2035-06-30, Debian 13 on amd64 guaranteed, others on request [C-COST-006] | ELTS to mid-2035, then one rebase | 1 / 1 / 2 |
| **D. Ubuntu 26.04 + Pro** | Pro to May 2036, Legacy to May 2041 [C-W2-005] | Pro + Legacy: none. Without Legacy: one rebase | 0 / 0 / 1 |
| **C. RHDE / RHEL bootc** | RHEL 10 ten years (~2035) + ELCP [C-W2-010]; AlmaLinux 10 to 2035-05-31 [C-W2-013] | 9.8 → 10 (→ 11 or ELCP) | 1 / 1 / 2 |
| **Y. Yocto own-BSP** | Wrynose LTS to 2030-04; LTS every 2 years, 4 years each [C-COST-008] | Three or more LTS hops | 2 / 3 / 5 |
| **All (hardware)** | Pi 5 made to at least Jan 2036; Orin modules to Jan 2032; T5000 to Aug 2035 [C-W2-029, C-W2-030] | Orin boxes face a hardware and software end before 2036 (§9) | — |

---

## 6. Results: cost per device to 2036

### 6.1 Base-specific + CRA, per device, whole life (USD)

| Base | 1k L | **1k B** | 1k H | 10k L | **10k B** | 10k H |
|---|---|---|---|---|---|---|
| **A. Debian 13 (LTS, rebases, no ELTS)** | 99 | **403** | 1,902 | 10 | **40** | 190 |
| **D. Ubuntu 26.04 + Pro for Devices + Legacy** (fee assumed, §4 A-06; G1 agreement **not included**) | 95 | **385** | 1,881 | 23 | **120** | 526 |
| **C. Red Hat Device Edge** | 553 | **1,756** | 4,485 | 460 | **1,391** | 2,627 |
| **Y. Yocto own-BSP + RAUC** | 234 | **900** | 4,470 | 23 | **90** | 447 |
| *C-free. AlmaLinux 10 bootc (same labour as C, no fee; no Pi or Jetson path of its own)* | *103* | *406* | *2,064* | *10* | *41* | *206* |

### 6.2 Per device per year (base scenario ÷ 9 years)

| Base | 1k units | 10k units | What is in the fee part |
|---|---|---|---|
| A. Debian | $45 | $4.5 | $0 per device |
| D. Ubuntu Pro | $43 | $13 | $90 per device one-time (assumed $60 × 1.5) |
| C. RHDE | $195 | $155 | $150 per device per year (assumed) |
| Y. Yocto | $100 | $10 | $0 per device |

### 6.3 How the parts break down (base scenario)

| Base | Base-specific hours | CRA hours | Fees per device (whole life) | Share of the 1k cost that is labour |
|---|---|---|---|---|
| A | 1,680 | 1,480 | $0 | ~97% (the rest is sponsorship and hosting) |
| D | 1,000 | 1,360 | $90 | ~74% |
| C | 1,880 | 1,400 | $1,350 | ~22% |
| Y | 5,720 | 1,480 | $0 | ~96% |

**Reading it.** At 1k units, one hour of rebase work costs every box 12 cents ($120 ÷ 1,000), so fixed labour dominates. At 10k it costs 1.2 cents, so per-box fees dominate. That is why D goes from tied with A to three times A, and why Yocto overtakes Ubuntu.

---

## 7. The DC-03 flip test and the break-evens

### 7.1 DC-03: "Debian's bounded cost exceeds the cheapest gate-passing alternative by more than 25%"

| Fleet | Scenario | A | Cheapest alternative | A ÷ alternative | Flip? |
|---|---|---|---|---|---|
| 1k | L | 99 | D 95 | 1.04 | No |
| 1k | **B** | **403** | **D 385** | **1.05** | **No** |
| 1k | H | 1,902 | D 1,881 | 1.01 | No |
| 10k | L / B / H | 10 / 40 / 190 | Y or D 23 / Y 90 / Y 447 | 0.43 / 0.45 / 0.43 | No (A cheapest) |

**Pro for Devices fee needed to flip DC-03 to D** (10-year one-time, before the Legacy ×1.5): **≤ $18 at 1k units** (base), ≤ $10 (high), and none in the low case. **≤ $2 at 10k units** in every case. The **break-even** where D merely equals A is ≤ $72 at 1k (base) and ≤ $7 at 10k [model output]. A quote above the break-even makes D cost more than A.

### 7.2 Debian 13 + ELTS (the "A2" variant)

ELTS replaces one or two rebases. It is cost-neutral when the **fleet-wide** ELTS fee for 2030–2035 is at most about **$0 (L), $4,800 (B) or $20,400 (H) a year**. ELTS is priced from the customer's package list and rises every half-year [C-W2-003], and its own page shows no price [C-COST-006]. **Two blockers come before price:** the contract restricts packages to "the client's own use" and forbids sharing them with third parties [C-W2-004], and only amd64 is guaranteed [C-COST-006]. So A2 is an option only if O-2 (outreach draft) returns both a fleet price under that line and redistribution rights for arm64.

### 7.3 What does not change the ranking

- **RHDE** stays the most expensive even at an assumed $50 a year. C's labour and CRA alone come to about $406 per device at 1k (base), which is already level with A's $403. So any subscription puts C above A, and a fee above about **$11 per device-year** puts it more than 25% above A ((403 × 1.25 − 406) ÷ 9).
- **Yocto** stays above Debian in every scenario, because it owns every package's CVE work (A-13).

---

## 8. Sensitivity to the hourly rate (base inputs, base + CRA, per device)

| Rate | 1k: A / D / C / Y | 10k: A / D / C / Y |
|---|---|---|
| $65 | 229 / 255 / 1,575 / 504 | 23 / 107 / 1,373 / 50 |
| **$120** | **403 / 385 / 1,756 / 900** | **40 / 120 / 1,391 / 90** |
| $200 | 656 / 574 / 2,018 / 1,476 | 66 / 138 / 1,417 / 148 |
| $300 | 972 / 810 / 2,346 / 2,196 | 97 / 162 / 1,450 / 220 |

Above about $120 an hour, D edges A at 1k units, but never by the 25% margin (at $300: 972 ÷ 810 = 1.20). At 10k units A is cheapest at every rate. **The rebase-hours number (A-03) matters as much as the rate.** At 1k units, each extra 80 hours per Debian rebase adds about $29 a box at the base rate (80 h × 3 majors × $120 ÷ 1,000).

---

## 9. Jetson branch upgrades (add-on per Jetson device)

| Base | 1k fleet (200 Jetson): L / B / H | 10k fleet (2,000 Jetson): L / B / H |
|---|---|---|
| A. Debian core + L4T Ubuntu flavor | 78 / **394** / 2,650 | 8 / **48** / 490 |
| D. Ubuntu + L4T Ubuntu | 78 / **394** / 2,650 | 8 / **48** / 490 |
| C. RHDE on Orin | 47 / **240** / 1,690 | 5 / **33** / 394 |
| Y. Yocto meta-tegra | 62 / **317** / 2,170 | 6 / **41** / 442 |

**Why it is about the same on every base.** NVIDIA fixes security bugs only at the head of each branch: 35.6.4, 36.5 and 38.4 for the March 2026 CVEs [C-REF-W7-T-005]. Staff gave a full BSP upgrade as the only documented remedy [C-REF-DC-robotics-002]. JetPack 5 ended on 2026-10-30, with Orin users sent to 7.2.1 [C-REF-W7L-001]. So every base must follow NVIDIA's branches, whatever the userland. **Not priced (quote needed):** (a) the **Orin tail after Jan 2032** [C-W2-030]. NVIDIA referred JetPack 4 and 5 maintenance to partners (TimeSys, Codethink, RidgeRun) [C-REF-W7-T-001, C-REF-W7L-001], and Canonical's ESM for JetPack 4 excluded the kernel [C-REF-W7L-007]. (b) The 2026 Jetson price rises affect the BOM, not this model [C-REF3-DC-cost-002]. **Mitigation in the plan (01):** ship Jetson A/B from the factory and test cross-branch OTA in CI, so that A-19's reflash fraction stays near the low case.

---

## 10. CRA support-period obligations (common lines)

| Obligation | Text (claim) | Cost line in the model | Differs by base? |
|---|---|---|---|
| Support period ≥ 5 years, reflecting expected use and the support periods of integrated components | Art. 13(8) [C-W6-002] | Drives the horizon. A box sold in Dec 2027 with a declared 2036 end must be supported by **some** base to 2036 | Yes: this is why every base needs majors or a paid tail (§5) |
| Each security update available for ≥ 10 years or the rest of the support period | Art. 13(9) [C-W6-003] | A-17 hosting | No |
| Patch only the latest version, if users get it free and without new hardware | Art. 13(10) [C-W6-004]; guidance on "additional costs" [C-REF-W6-technical-001] | Lets OneMind support only the newest major, **if** rebases work without a reflash (DC-05). A Jetson reflash that needs a host PC may count as an "additional cost" (A-19 risk) | Yes, via rebase feasibility |
| End date stated at purchase | Art. 13(19) [C-W6-005] | Inside A-15 | No |
| Vulnerability reporting from 2026-09-11; main duties from 2027-12-11 | Art. 14, Art. 71 [C-W6-001] | A-15 | No. A paid base supplies fixes, but the reporting duty stays with OneMind |
| Conformity assessment | Module A for a default-category box; the image may be Class I (W6) | A-16. **Notified body not in the base case.** No public price exists: a consultancy says "no official per-company figure is published" [C-COST-013]. The €20–60k (module B) / €80–150k (module H) figures in `adversarial/W6-P0-2-security.md` are unopened consultancy estimates (UNVERIFIED) | Partly. Each major rebase adds re-documentation (A-16) |

**UK PSTI** also requires a published support period [C-W6-041]. It is covered by the same A-15 line.

---

## 11. What competitors do (constraint-fit column)

| Product | Base and who pays for the long tail | Published price signal | Constraints | Constraint-fit for OneMind |
|---|---|---|---|---|
| **umbrelOS** | Debian, rebuilt as an image; the company carries the labour [C-W2-043] | none | Small company; Docker, not k3s; no robotics | **High** for the "free base + own labour" pattern (A) |
| **Home Assistant OS** | Buildroot from source; a funded team carries it, financed by about CHF 8.84M of revenue [C-W16-013, C-W2-047] | HA Green $199 box [C-W16-016] | Funded team; no k3s; no Jetson | **Low** for a solo founder: shows what a from-source OS (Y) needs |
| **Talos / Omni** | Own OS; vendor sells support | Talos Enterprise $1,000 per node per year, 10-node minimum; Omni Edge quote-only [C-REF3-DC-cost-004] | Kubernetes-only; no Pi 5/Jetson GA (03 §3) | **Medium** as a price anchor: a vendor-supported edge OS costs far more per node than C's assumed $150 |
| **Mender** | Update tool, any base | Open source free; hosted tiers $34–$291 a month; Enterprise quote [C-STEEL-updates-mender-015] | Update layer only | **Medium**: hosted fleet tooling is cheap next to OS labour |
| **Proxmox VE** | Debian; per-socket subscription funds the vendor | €120–€1,100 per socket per year [C-W16-028] | Servers, not devices | **Low** (not device-priced), but shows a Debian-based vendor charging per unit |
| **NVIDIA Jetson vendors** | L4T Ubuntu; NVIDIA ends branches and refers the tail to partners [C-REF-W7L-001] | partner support quote-only | Hardware-tied | **High**: OneMind's Robotics tier inherits exactly this |

---

## 12. Recommendations (requirement IDs)

| ID | Recommendation | Serves |
|---|---|---|
| **REC-COST-01** | Record DC-03 as **"A ≈ D at 1k, A cheapest at 10k; flip condition not met (max 1.05×)"**, conditional on REC-COST-02 and -03. Replace 03 §6.2's "bounded, not quoted" with §6.1 of this file. | R-3, M-8, H-1 |
| **REC-COST-02** | Make **T-W3-04 a timed drill**: founder-hours for a Debian 13 → 14 (testing) image rebase, including the Pi kernel, NVIDIA DKMS, RAUC slot sizing and the k3s gate. **Thresholds:** ≤ 160 h keeps the base case; > 240 h moves A to the H column. Re-run the model. | R-3, R-1, M-6 |
| **REC-COST-03** | Send O-1 (Canonical) with the explicit thresholds: a fee ≤ **$72** (1k) or ≤ **$7** (10k) per device for 10 years makes D cheaper than A, and ≤ **$18 / $2** flips DC-03. Price the redistribution agreement (G1) in the same quote. | H-1, F-14, D-001 |
| **REC-COST-04** | Send O-2 (Freexian) asking for a **fleet-wide** ELTS price for arm64 + amd64 with redistribution. Below about **$4,800 a year**, ELTS replaces one Debian rebase at no extra cost. Above it, rebase. | R-3, M-8 |
| **REC-COST-05** | Budget a **Freexian LTS sponsorship** (B: $1,200 a year, from the published table) from the first sale. It protects the 2028–2030 LTS years OneMind relies on. | R-3, M-8 |
| **REC-COST-06** | Do not adopt RHDE as the device base on cost grounds. Keep the **free RHEL-family path (AlmaLinux bootc)** as the cost-equal IIoT profile (03 W2-R3/R4). Ask Red Hat (O-3) only if an IIoT buyer requires RHEL certification (C-W2-042). | F-11, F-12, H-1 |
| **REC-COST-07** | Price the Robotics tier with a **Jetson add-on** (base: about $50–400 per Jetson device, depending on fleet size) and an Orin end-of-sale plan for 2032: a partner quote, or migrating to the meta-tegra/6.18 route (01). | H-1, F-1, R-3 |
| **REC-COST-08** | Put the **CRA lines** (about 120 h a year + about 160 h one-time, base) into the 180-day plan and the W16 company model (Q313) as a fixed cost, separate from base choice. | M-8, H-1 |
| **REC-COST-09** | Re-run `cost-model.py` whenever a quote arrives or T-W3-04 reports, and record the result in `qbank/COST.md`. | M-6 |

---

## 13. Honest limits (what would change the answer)

- **Three inputs are assumptions, not evidence:** the Pro for Devices fee (A-06), the rebase hours (A-03) and the Yocto CVE hours (A-13). Each is bracketed, and each has a named test or quote that replaces it.
- **No vendor price was obtained.** The brief forbids contacting vendors. Drafts O-1…O-3 are in `evidence/outreach-drafts.md`. The RHDE anchor is a single reseller listing (SECONDARY). The Ubuntu Pro for Devices price was searched for and not found [C-COST-014].
- **The model treats all units as sold at once** and needing support to 2036. A real sales ramp lowers per-device fixed cost for later units, but lengthens their CRA period past 2036.
- **The hourly rate is US-based** [C-COST-012]. A founder's own hours carry an opportunity cost that may be higher than the rate.
- **Debian 14–17 dates are projections** from the observed two-year cadence [C-COST-007], not published dates.
- **Not legal or financial advice.** Counsel should read the CRA lines (Z-05).

**Follow-ups for other owners (not edited here, per house rules):** 03 §6.2 and the 01 DC-03 tie-break row should point to this file. `26-…` line 107 still says the outreach drafts are "to be written", but they exist (critic N10). `qbank/W2.md` Q1/Q168/Q213 should reference `qbank/COST.md`. W16 Q313 can take §6 as its OS-support line.
