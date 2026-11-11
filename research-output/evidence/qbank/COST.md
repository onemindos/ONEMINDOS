# Question bank: COST (DC-03 update, 2026-11-11)

This file updates the DC-03 entry. The W2 owner rows (`qbank/W2.md` Q1, Q168, Q213) are not edited here; this file supersedes their status for DC-03 until they are synced. Full model: `evidence/lifecycle-cost-2036.md`.

| Bank ID | DC | Status | Answer (short) | Claims |
|---|---|---|---|---|
| **Q1** | DC-03 | **partial** (was: partial, blocked: paywalled). A modelled cost per device now exists. Two inputs still await a quote or a lab: the Ubuntu Pro for Devices fee and the hours per rebase (T-W3-04) | Per device to 2036, base + CRA, base scenario: **1k units:** Debian $403, Ubuntu Pro $385 (fee assumed), RHDE $1,756, Yocto $900. **10k units:** $40, $120, $1,391, $90. Low–high ranges: 1k Debian $99–1,902; 10k Debian $10–190. **Flip condition (Debian > 1.25 × cheapest): not met** in any scenario (max 1.05 at 1k). Debian is cheapest at 10k | C-COST-001…014; C-W2-001, 005, 010, 013, 029, 030; C-W6-001…005 |
| **Q168** | DC-03 | **blocked: vendor quote** (thresholds set) | No public Pro for Devices price exists [C-COST-002, -003, -014]. D equals A at ≤ $72 (1k) / ≤ $7 (10k) per device for 10 years, before Legacy's ×1.5. It flips DC-03 only at ≤ $18 / ≤ $2. ELTS is cost-neutral up to about $4,800 a year fleet-wide, and needs redistribution rights [C-W2-004]. RHDE: reseller anchor about $269 per device-year (SECONDARY) [C-COST-010] | C-COST-002…006, 010, 011, 014 |
| **Q213** | DC-03 / DC-04 | **partial** | Majors to 2036: Debian 2–4, Ubuntu 26.04 + Legacy 0 (1 without Legacy), RHEL bootc 1–2, Yocto LTS 2–5. Jetson needs 3–5 NVIDIA branch upgrades whatever the base (about $50–400 per Jetson device, base). CRA adds about 1,400 hours over the life on every base | C-COST-007, -008; C-W7-006; C-REF-W7-T-005; C-W6-002…005 |

**DC-03 result (for `decision-critical.md`):** ranking **A ≈ D (1k), A < Y < D ≪ C (10k)**; flip condition **not met**. Conditional on T-W3-04 measuring ≤ 240 h per rebase and Canonical quoting above $18 per device (1k). **Re-check by:** 2027-05-11, or when any quote arrives.

**New questions:**
- Q-COST-1: Does a major Debian rebase count as a CRA "substantial modification" that requires new conformity documentation? (W6, counsel)
- Q-COST-2: What does a partner (RidgeRun, TimeSys or Codethink) charge to maintain Orin after NVIDIA ends its last JetPack branch for Orin? (W7, outreach)
