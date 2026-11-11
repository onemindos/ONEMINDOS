# Refuter S1R4 · S1 base-OS verdict (rev. 3) · lens: longevity and vendor risk

**Target:** `01-FOUNDATION-DECISION.md` §3.1 (rev. 3): Debian 13 (A, 60.0) kept over RHEL-family bootc (C, 64.0) and Ubuntu 26.04 (D, 62.0) through a three-way head-to-head tie-break (§3.1.5).
**Protocol checked against:** `evidence/scorecard-weights.md` v1.0 (frozen), §3 tie rule, §5 evidence rules, §8 change log.
**Read for this refutation:** the S1 section and glossary of `01-…`, DC-05 in `decision-critical.md`, the frozen scorecard, and the cited claims (C-W2-001/004/005/006/007/013/041/043/044, C-W3-039, C-REF-DC-cost-002/003, C-REF-DC-robotics-009/010, C-STEEL-KRU-009, C-SCORE-025, C-COST-002/009, C-REF3-DC-longevity-001). Existing adversarial files were not read first.
**New ledger rows:** `claims/REF4-S1R4-longevity.csv` (C-REF4-S1R4-longevity-001 to 004).
**Verdict: WEAKENED.** It is close to refuted on protocol grounds. On the merits, Debian is not clearly wrong, but its longevity case is thinner than the card shows.

---

## 1. Strongest counter-argument

### 1a. Protocol: the verdict needs D to be in the race and out of it at the same time

The frozen rule (§3) is: "A difference of under 3.0 points between **the top two** is a tie… settled by the decision-critical evidence." On the rev. 3 card the top two are **C 64.0 and D 62.0**. A (60.0) is 4.0 behind the leader, which is outside the band. The tie-break between the frozen top two picks **D** 6–4, as `01-…` itself reports.

To keep A, the verdict uses two arguments that cannot both hold:

1. **A becomes a finalist only because it is within 3.0 of D**, the runner-up. The frozen protocol has no "within the band of the runner-up" rule.
2. **D is then set aside because its G1 condition (Canonical permission, Z-01) is unmet and "cannot ship today".** But D's G1 is CONDITIONAL, not FAIL. Under §2, a CONDITIONAL candidate is ranked and its mitigation goes into the plan. Using G1 to rule D out also counts it twice, because G1 is already one of the rows A wins against D in the head-to-head count.

If argument 2 is right and D cannot be a finalist, the frozen protocol compares **C 64.0 vs A 60.0**. That is a 4.0 margin, outside the tie band, so **C wins outright** and no tie-break is run. A wins only under the rev. 3 variant C·C2 = 2, which the file itself calls the stricter reading, not the scored one. If argument 2 is wrong, D stays in and the strict reading picks D. **Neither consistent reading of the frozen protocol gives A.**

The "head-to-head (pairwise) tie-break" is new in rev. 3 (glossary marked *(rev. 3)*). It was adopted **after** the cited card showed C leading. `scorecard-weights.md` §8 says a change needs a row "before the new weights are used" and that "the proposal looks worse is never a reason". The rev. 3 §8 row logs cell moves only, not a new tie-break mechanism. `01-…` calls this "an interpretation… stated openly". Being open about it does not make it compliant. This is the kind of post-scoring rule change the freeze exists to prevent.

The A vs C pair then ties 5–5. That tie is broken by a qualitative "which tier each row is about" argument that no frozen rule provides. As a result, the choice of A rests on three judgment layers, none of which were frozen in advance: the finalist rule, the pairwise rule and the tier rule.

### 1b. Merits: A's C1 = 3 rests on one precedent whose post-rebase update path has long-lived stranding defects

A·C1 was raised from 2 to 3 (S1-1) only through anchor 3's second clause, "a documented in-place rebase path that keeps the device current". The sole evidence is umbrelOS's Debian 12 → 13 OTA move [C-W3-039]. The free first-party path does not reach 2032: LTS ends 2030-06-30, and ELTS cannot be passed to customers [C-W2-001, C-W2-004].

New evidence shows the precedent's fleet did **not** reliably stay current after the rebase:

- **Rugix path, Debian 13 base:** updates hang at 93% and never switch slots, because the update subprocess cannot find `sfdisk` (PATH lacks `/usr/sbin`). The issue was opened 2026-05-24 and is still unfixed in 2.0.1 (2026-11-03). It has no maintainer response, and the fix PR is still open [C-REF4-S1R4-longevity-001]. The device reports nothing; the update just stays "running".
- **Mender path, Debian 13 base:** a box on 1.5.0 was offered no further updates. A manual install failed because Debian's packaged Mender 3.4.0 rejects the artifact format, and the newer client could not be installed. No staff reply is shown [C-REF4-S1R4-longevity-002]. This is a single user report and weak on its own. It is still consistent with a known risk: a distribution-packaged update client lags the vendor's artifact format, which is the same failure `01-…` §4.2 found for Debian's RAUC 1.13 on kernels ≥ 6.19.

So "keeps the device current" is shown in the precedent's own field only with open, unanswered failures. The precedent also ran on Rugix and Mender, **not RAUC**, the engine A now ships. The "proven competitor" row that A wins against both rivals carries the same weakness.

### 1c. Merits: the C1 anchor treats three sequential rebases the same as one or none

To declare CRA support to 2036-12-31 (gate G3), each finalist needs:

- **D:** no rebase. Ubuntu 26.04 Pro runs to May 2036 and Legacy to 2041 [C-W2-005]. The price is unpublished [C-W2-006].
- **C:** one rebase. AlmaLinux 10 runs to 2035-05-31 [C-W2-013].
- **A:** several rebases. Debian 13's LTS ends 2030-06-30 [C-W2-001]. Debian does not support skip-upgrades [C-REF3-DC-longevity-001], so every release must be taken in turn. On Debian's roughly two-year cadence, 2036 means 13 → 14 → 15 → 16. That count is my projection, not a published schedule.

Each rebase re-qualifies Raspberry Pi's kernel, which has no dated support window [C-REF-DC-robotics-009]. It also re-qualifies NVIDIA DKMS and the A/B pipeline. Anchor 3 scores all three finalists the same ("one or more rebases expected"). The DC-03 cost row then counts A's rebase labour as "unmeasured until T-W3-04" and still credits A at 10k units.

The longevity lens says that **A carries the most rebase exposure of the three, and the only measure of it is a drill that has not been run.**

### 1d. Vendor risk: "community-governed" overstates Debian after year 3 of each release

The governance row goes to A as "community-governed". After regular security support ends (2028-08-09), Debian 13 security depends on **one company**: Freexian funds and staffs LTS, with 20 paid contributors and no stated funding level [C-REF-DC-cost-003]. Freexian also sells ELTS, which is not redistributable [C-W2-004]. Free LTS already leaves "a few packages" uncovered [C-REF-DC-cost-002], and trixie LTS architectures are "to be determined" [C-REF-DC-robotics-010].

CIP's 6.12 SLTS kernel to mid-2035 [C-W18-003] is a real mitigation for Debian's kernel line. But CIP covers "a reduced set of kernel subsystems and features", only boards it actively tests, and it names neither Pi nor Jetson [C-REF4-S1R4-longevity-004]. The Pi 5 tier, which is the tier the A-vs-C tie-break gives to A, runs on Raspberry Pi's kernel and gets no benefit.

## 2. What survives (fairness to the verdict)

- **C has its own vendor risk.** The free AlmaLinux path to 2035 [C-W2-013] belongs to a downstream whose upstream source access Red Hat cut in 2023. That forced AlmaLinux to drop 1:1 RHEL compatibility [C-REF4-S1R4-longevity-003]. The governance row against C is therefore defensible.
- **D's single-vendor exposure is real.** Canonical alone controls the archive, the price and the redistribution terms [C-W2-006, C-W2-050].
- No finalist has a published, priced, redistributable path to 2036-12-31 on all three board families. A's weaknesses are a matter of degree, not a disqualification.
- The plan already contains the cheap hedge: two CI legs, `FROM debian:trixie` and `FROM ubuntu:26.04` (REC-DEC-17).

## 3. Verdict

**WEAKENED.**

- **On protocol:** the decision does **not** follow the frozen scorecard. Under either consistent reading, the frozen rule selects C (D excluded) or D (D kept), never A. Debian survives only through a tie-break mechanism added after scoring, which is not logged in §8.
- **On the merits:** Debian is not shown to be the wrong base. Its edge in longevity and governance is smaller than the card implies, and its one rebase precedent has open field failures.

**Required responses:**

1. Log the pairwise tie-break in `scorecard-weights.md` §8, with the ranking before and after, or drop it.
2. Either re-score D·G1 as FAIL with evidence, accepting that C then wins under the frozen rule unless C·C2 = 2 is adopted, or keep D in and accept the strict D result.
3. State the result as "Debian is a **provisional** pick pending T-W3-04 and W2-HW-3", not "kept".

## 4. What would flip this verdict

- **To upheld:**
  - A §8 change row that adopts the pairwise rule with a reason other than the result (for example, the strict rule's sensitivity to adding candidates), plus the C·C2 = 2 reading adopted on evidence, such as W2-HW-3 failing. With C·C2 = 2, A, C and D are all within 2.0 and A is a legitimate finalist.
  - T-W3-04 running a Debian 13 → 14 RAUC rebase on Pi 5 and x86 in under 4–6 founder-weeks.
- **To refuted:**
  - W2-HW-3 passing, so C·C2 = 3 stands as measured, while D·G1 stays unmet. The frozen protocol then picks C by 4.0 with no tie.
  - T-W3-04 showing a Debian major rebase needs a reflash or a layout change.
  - The trixie LTS architecture list excluding arm64 or armhf boards OneMind ships.

## Sources opened for this file

- [getumbrel/umbrel issue #2153](https://github.com/getumbrel/umbrel/issues/2153)
- [Umbrel community thread 24970](https://community.umbrel.com/t/umbreld-crashes-every-36h-with-gpf-in-libc-so-6-node-process-on-amd64-umbrelos-1-5-0-update-system-also-broken/24970)
- [AlmaLinux, "The future of AlmaLinux is bright" (2023-07-13)](https://almalinux.org/blog/future-of-almalinux/)
- [CIP, "Kernel 6.12 will have 10 years support via CIP" (2025-01-13)](https://cip-project.org/blog/2025/01/13/kernel-6-12-will-have-10-years-support-via-cip-are-all-your-maintenance-problems-solved)
