# S1 protocol ruling (rev. 4): what the frozen scorecard rules actually produce

**Date:** 2026-11-11 · **Agent:** PROTO4 (S1 protocol adjudicator) · **Closes:** critic pass-3 gap **P3-1** (and supplies the protocol facts for Q-P3-1)
**Scope:** this file rules **only on the protocol**: what the rules frozen in `evidence/scorecard-weights.md` produce when applied mechanically to the rev-3 S1 card. It takes **no side** on which base OS is better, and it changes no score, gate or weight.
**Inputs read:** `scorecard-weights.md` at three commits (git history below), `scorecard-rev3.md` §3, `01-FOUNDATION-DECISION.md` §2 and §3.1, `23-RISK-REGISTER.md` RR-09, `evidence/critic/pass-3.md` P3-1/P3-3/Q-P3-1, RESEARCH-MISSION.md §6.
**Ledger:** `claims/PROTO4.csv` (C-PROTO4-001…018). Every source is a file in `<repo>` pinned to a commit SHA; the sha256 values below let anyone check the text has not moved.
**Serves requirements:** RS-1, RS-4, F-12 (the scorecard protocol and its fairness to the runner-ups)

> ### Explain it like I'm the founder
> Before anyone scored a single OS, we wrote down the rules of the contest and locked them. One of those rules says: **if the top two are less than 3 points apart, call it a tie and settle it with the decision-critical evidence.** Only the top **two**.
>
> In revision 3 the scores came out **bootc 64, Ubuntu 62, Debian 60**. The top two are bootc and Ubuntu (2 points apart, a tie). Debian is third, 4 points behind the leader. Applying the locked rule, the tie-break is bootc vs Ubuntu, and the existing tie-break table gives that pair to **Ubuntu, 6 rows to 4**.
>
> Revision 3 instead brought Debian back in as a third finalist and compared all three in pairs ("head-to-head"), which Debian won. That pairs rule was **written after the scores were known** and **was not logged** in the change log, which only allows rule changes for a factual error in an anchor or a new founder decision. So it is a **rule change**, not the locked rule's result. It can still be adopted, but only as **your decision**, written down openly, not as "what the scorecard says".
>
> None of this says Ubuntu is the better base. It says what the locked rules produce. The rules are fragile here: a few small, plausible changes give bootc or Debian instead (§7).

---

## 1. Ruling in four lines

1. **Frozen protocol result on the rev-3 card:** finalists **C (RHEL-family bootc, 64.0) and D (Ubuntu 26.04, 62.0)**; tie-break winner **D, 6–4** on the decision-critical rows already in 01 §3.1.5 [C-PROTO4-009, C-PROTO4-011]. A (Debian 13, 60.0) is ranked third and is **not a finalist** [C-PROTO4-001, C-PROTO4-008].
2. **The rev-3 three-way pairwise tie-break is a protocol change under §8.** It changes who may win, it was introduced in commit `7836316` after the rev-3 scores were known, it is not logged in §8, and neither allowed reason (a factual anchor error or a new founder decision) applies [C-PROTO4-003, C-PROTO4-004, C-PROTO4-007].
3. **Ranking:** old (frozen) rules **D > C > A**; new (rev-3) rule **A > D > C** (§5).
4. **Outcome-changing variants exist and are close:** the protocol winner is D in 11 of the 14 sensitivity runs and C in 3; one cell variant (D·C1 = 2) makes C win outright in all 14; one (C·C2 = 2) leaves a shared second place the frozen text gives no method for (§6, §7).

---

## 2. What the frozen rules said before any score was known

### 2.1 Git evidence

`scorecard-weights.md` has been committed three times. The body of the file (lines 1–195: gates, weights, tie rule, anchors, evidence rules, sensitivity, score-sheet format and the §8 preamble) is **byte-identical in all three**: sha256 of lines 1–195 = `7d82ef25311c2778796bc026e51978cf58003d8591a3fb59af888d1ede34990d` at each commit [C-PROTO4-001]. `git log -p` shows the only later changes are three rows appended to the §8 table [C-PROTO4-004].

| Commit (date, UTC−5) | What it contains | Tie rule (line 67) | 01's S1 tie-break |
|---|---|---|---|
| `414d60a2…` (2026-11-10 23:13) | Freeze v1.0; first scorecards (rev. 0/1) | "A difference of **under 3.0 points** between **the top two** is a **tie**. A tie is settled by the decision-critical evidence (`evidence/decision-critical.md`) and the refuter tables, never by adjusting scores." | "D vs A; C shown for completeness" (two finalists) [C-PROTO4-005] |
| `ee98bc77…` (2026-11-11 02:08) | §8 rows "cells rev-1" and "cells rev-2" | identical | "D vs A; C shown for completeness"; the word "head-to-head" appears **0** times [C-PROTO4-006] |
| `7836316f…` (2026-11-11 07:08; = HEAD) | §8 row "cells rev-3": "**No weight or anchor change.**" | identical | "A, C and D all finalists, compared head-to-head"; glossary entry "Head-to-head (pairwise) tie-break *(rev. 3)*" [C-PROTO4-007] |

**Limit of the git evidence.** The freeze and the first scores arrived in the **same** commit (`414d60a`), so git cannot prove which was written first inside that commit. What it does prove: (a) the file states "Frozen before: any candidate was scored" and its §8 v1.0 row says "n/a (nothing scored yet)"; (b) the tie rule has **never changed** since its first commit; (c) the pairwise rule **did not exist** in any commit before `7836316`, the commit that also carries the rev-3 scores. So the tie rule is the pre-scoring rule in every sense git can check, and the pairwise rule is post-scoring.

### 2.2 The frozen rules that decide this case

| Rule | Frozen text (`scorecard-weights.md` @ every commit) | Claim |
|---|---|---|
| Who is ranked | "A candidate with any FAIL is **not ranked**." CONDITIONAL is "met only with a named mitigation that has a stated cost and owner" and "carries its mitigation into the plan (20) and the risk register (23)". Only FAIL removes a candidate. (lines 35–41) | C-PROTO4-002 |
| Score | `total = Σ(weight × score)/5`; weights 20/20/15/15/10/10/10 (§3) | C-PROTO4-001 |
| Tie | "under 3.0 points between **the top two**" (line 67) | C-PROTO4-001 |
| Tie-break | "settled by the decision-critical evidence … and the refuter tables, never by adjusting scores" (line 67). **No counting method is written.** Since rev. 1 the run has counted decision-critical rows between the two finalists (S1 rev. 1/2, S2 rev. 1–3); this ruling treats that two-candidate count as the established way of applying line 67. | C-PROTO4-001, C-PROTO4-005 |
| Sensitivity | 14 runs; robust / fragile (1–3 runs change) / unstable (4+, goes to 26) (§6) | C-PROTO4-001 |
| Changes | "Any change after this freeze needs a row here **before** the new weights are used … the ranking under **both** the old and the new weights. Changes are allowed only for a factual error in an anchor or a new founder decision. 'The proposal looks worse' is never a reason." (line 196) | C-PROTO4-003 |
| Brief | "**Freeze the weights** … before scoring, and **log any change**." (RESEARCH-MISSION.md §6) | C-PROTO4-015 |

---

## 3. Mechanical application to the rev-3 S1 card

**Step 1, gates.** On the rev-3 gate table, A, C and D have **no FAIL** (every gate PASS or COND) [C-PROTO4-008]. D's G1 is COND (Canonical permission or debrand-and-recompile) and D's G5 is COND (S1-6). Under the frozen §2, COND candidates **are ranked**; their mitigation goes to 20 and 23, where it is: RR-09 names the mitigation (ask Z-01; Debian core needs no permission; meta-tegra lab) and the owner ("Zeus + counsel") [C-PROTO4-013]. The frozen rules contain **no** clause that turns an unmet or third-party-dependent COND into a FAIL. So all three are ranked.

**Step 2, totals.** Recomputed independently from the cited cells (exact fractions): **C 64.0 · D 62.0 · A 60.0** · B 52.0 · E 52.0 · G 51.0 · F 46.0 [C-PROTO4-009]. This matches `scorecard-rev3.md` §3.2 and 01 §3.1.3.

**Step 3, tie test.** Top two = C and D. Margin 2.0 < 3.0 → **tie**. A is not one of the top two; it is 4.0 behind C. `scorecard-rev3.md` §3.4 states the same: "the finalists are **C and D**. A sits 4.0 points behind C, outside the band" [C-PROTO4-008].

**Step 4, tie-break.** 01 §3.1.5 already counts the C–D pair on its decision-critical table: **D 6** (DC-07, DC-19, DC-13, DC-15, NVIDIA trajectory, lab) **– C 4** (G1 via Alma, DC-03 at 10k, DC-05, DC-04); DC-17, IIoT, governance and proven-competitor equal [C-PROTO4-011]. I re-derived each row's "Favours" cell for the pair and got the same 6–4. (Whether each row is *right* is not this file's question; P3-2 asks for a refuter of the rule and the rows.)

**Result:** **D (Ubuntu 26.04 + A/B, + JetPack flavor) wins S1 under the frozen protocol, with conditions G1 (Z-01) and G5 carried into 20 and 23.** 01 §3.1.5 itself concedes this ("The strict two-finalist reading … picks **D**") [C-PROTO4-007].

**01's reason for setting D aside** ("D's G1 condition … is unmet and outside OneMind's control, so D cannot ship today") is a feasibility judgement, not a step of the frozen protocol. Inside the protocol it could act only as a **cell re-score** of D·G1 from COND to FAIL, which §5 rule 6 requires to be applied with the same standard to every candidate (see §7, V5).

---

## 4. Is the rev-3 three-way pairwise tie-break a protocol change under §8?

**Ruling: yes.**

1. **It changes the finalist set, which the frozen text defines.** Line 67 names "the top two". Rev. 3 adds a third candidate that is 4.0 behind the leader. Changing who may win changes the outcome exactly as a weight change would: here it turns D into A.
2. **It was made after the scores were known.** It first appears in `7836316`, the commit that carries the rev-3 card; `scorecard-rev3.md` in the same commit had already named the finalists as C and D [C-PROTO4-007, C-PROTO4-008]. The frozen file's own purpose statement is to stop "quietly changing the rules after seeing which option is ahead".
3. **It is not logged.** The §8 rev-3 row says "No weight or anchor change" and records no finalist or tie-break rule [C-PROTO4-004]. 01 §3 says "No weight or anchor was changed, so `scorecard-weights.md` §8 needs no entry" [C-PROTO4-016]. §8 requires a row for "any change after this freeze", with the ranking under both rules, and the brief says "log any change" [C-PROTO4-003, C-PROTO4-015].
4. **Neither allowed reason applies.** No anchor was shown to be factually wrong. No founder decision exists (the founder cannot be asked in this run; mission §2 rule 8). The stated reason, that A's exclusion "depends on one `doc-only` cell", is a sensitivity concern, which the frozen §6 already handles (fragile/unstable labels and 26-OPEN-QUESTIONS), and the swing cell is already shown as a variant.

**Counter-arguments considered**

| Argument (01 rev. 3) | Ruling |
|---|---|
| "This is an interpretation of the frozen protocol (which names only 'the top two'), stated openly, not a change of weights or anchors" (01 §3.1.5, §11) | Stating it openly is good practice, but an interpretation that *contradicts* the plain text ("the top two") and changes the winner is a change. Openness does not substitute for a §8 row and an allowed reason. |
| "§8 is about weights and anchors only" | §8's first sentence covers "any change after this freeze"; the frozen file is frozen as a whole (header "FROZEN v1.0"); the brief says "log any change". Even on the narrowest reading, the §8 duty to show the ranking under both rules was not met. |
| "A is inside **D's** band (2.0)" | The frozen band is measured between the top two, not chained from the runner-up. A chained band ("within 3 of any finalist") is a different rule; it is not in the text. |
| "Both readings lead to the same action until Z-01 or W2-HW-3 changes an input" | Not on the protocol: the strict reading's winner is D with a COND mitigation; the frozen §2 expects COND winners to proceed with their mitigation in 20/23. Choosing to build on A while Z-01 is open is a **decision**, not a protocol output. |
| The pairwise rule "cannot be gamed by adding a third option" (01 glossary) | Pairwise methods resist some manipulation, but **admitting** the third option is itself the choice that decides this case. And see §8: the rule as defined yields no winner here. |

**What the rule change would need to be legitimate:** a §8 row (proposed text in §9) recording it as a **founder decision**, with the ranking under both rules, written before it is relied on; until then it is labelled `blocked: founder-decision` (mission §2 rule 8), which Q-P3-1 already proposes.

---

## 5. Ranking under the old and the new rules (rev-3 card)

| Place | Frozen rules v1.0 (top-two tie + DC tie-break) | Rev-3 rule (three finalists, pairwise) |
|---|---|---|
| 1 | **D · Ubuntu 26.04** (tie-break over C, 6–4) | **A · Debian 13** (beats D 7–4; draws C 5–5, taken on a "tier argument") |
| 2 | C · RHEL-family bootc (64.0, raw leader) | D · Ubuntu 26.04 (beats C 6–4, loses to A) |
| 3 | A · Debian 13 (60.0; not a finalist) | C · RHEL-family bootc (loses to D, draws A) |
| 4–5 | B Fedora IoT 52.0 = E Ubuntu Core 52.0 | same |
| 6 | G Yocto + RAUC 51.0 | same |
| 7 | F Buildroot + RAUC 46.0 | same |

Unranked (a gate FAIL): H, I, J, K, L, as in `scorecard-rev3.md` §3.1.

---

## 6. Sensitivity of the protocol outcome (not just the raw leader)

The frozen §6 asks whether "the winner" changes. On the raw score C wins 14/14 (robust). But the protocol winner is decided by the tie test plus the tie-break, so the honest count is per run [C-PROTO4-010]:

| Run | Top two (margin) | Tie? | Frozen-protocol winner |
|---|---|---|---|
| C1 ±5, C2 ±5, C3 ±5, C4 ±5 (8 runs) | C–D (1.87–2.13) | yes | D (tie-break 6–4) |
| C5 −5 · C6 −5 · C7 +5 | C–D (1.00 · 1.00 · 0.78) | yes | D |
| **C5 +5** | C–D (**exactly 3.0**) | **no** ("under 3.0") | **C outright** |
| **C6 +5** | C–D (**exactly 3.0**) | **no** | **C outright** |
| **C7 −5** | C–**A** (3.11 = 28/9) | **no** | **C outright** |

**Protocol winner: D in 11 runs, C in 3.** Under §6.3 that is **fragile** (the winner changes in 1–3 runs), flipped by C5 +5 and C6 +5 (margin lands exactly on the band edge) and by C7 −5. Fragile is presentable with the flipping weights named; it is not "unstable". Note that two of the three flips sit **exactly** on the 3.0 edge, so the band's "under" wording carries real weight.

---

## 7. Variants that change the outcome

Each variant is a single cell or gate reading already named in 01 or the critic. Totals recomputed; tie-break counts are 01 §3.1.5's pair counts.

| ID | Variant (source) | Card | Frozen-protocol result | Rev-3 pairwise result | Changes the frozen outcome? |
|---|---|---|---|---|---|
| — | **Rev-3 cited card** | C 64 · D 62 · A 60 | **D** (C–D tie, 6–4); 11/14 D, 3/14 C | A | — |
| V1 | C·C2 = 2, "experimental is not a documented path" (S1-9 variant) | D 62 · C 60 · A 60 | **Undefined.** Second place is shared, so "the top two" is three candidates, and the frozen text gives no three-way method. D-vs-C gives D; D-vs-A gives A. | A | **Yes: no protocol result without a new, logged rule.** This is the one case where a three-way method is genuinely needed, and the only honest way to supply it is a pre-registered §8 row. |
| V2 | D·C1 = 2 (S1-4, longevity refuter) | C 64 · A 60 · D 58 | **C outright** (margin 4.0; 3.11–4.89 in all 14 runs, no tie in any) | C (no tie to break) | **Yes → C** |
| V3 | C4 = 4 for A and D (S1-7) | D 65 · C 64 · A 63 | D (D–C tie, 6–4). Across runs the top pair varies: D–C 11, D–A 2 (→ A, 7–4), A–C 1 (5–5 draw, undefined) | A | No at base; fragile across runs |
| V4 | Ubuntu steelman full re-score (D C4 = 4, C6 = 3; with or without A C4 = 4) | D 67 · C 64 | **D outright** (margin exactly 3.0) | D outright if A C4 = 3; with A C4 = 4 (A 63) still D outright | No (same winner, no tie-break needed) |
| V5a | Unmet third-party COND = FAIL, applied to **D only** (critic P3-1's reading) | C 64 · A 60 | C outright (4.0) | C | Yes → C, **but** it breaks §5 rule 6 (same standard for every candidate) |
| V5b | Same reading applied **to every candidate's G1** | A's G1 waits on the same Canonical answer for its Jetson flavor (RR-09, Z-01 "covers Jetson too"); C's G1 waits on a Red Hat agreement for RHDE on Orin → A, C, D unranked; B 52 · E 52 · G 51 | **B–E tie, never tie-broken anywhere in the run** → no protocol result | n/a | Yes → no result. I did not re-audit B/E/G/F's own COND gates; extended to every gate, the reading likely empties the card. |
| V6 | Tie band measured as "within 3.0 of the leader" (not "top two") | C 64 · D 62 · A 60 | Same finalists C, D → D | — | No |
| V7 | "Chained" band (within 3.0 of any finalist) | adds A via D | Three-way, no frozen method → needs the rev-3 rule | A | Only by adopting a new rule |

**Readings of the gate rule.** The frozen text supports only the literal one: COND = ranked, with mitigation in 20/23 [C-PROTO4-002]; G1's own definition makes "needs a separate EULA acceptance" a COND, which shows the authors expected COND-G1 candidates to be ranked. One evidentiary gap: §2 requires a COND mitigation to have "a stated cost and owner". RR-09 gives an owner and mitigation but **no cost** [C-PROTO4-013], and it is the same risk row for D's core and A's Jetson flavor. If a refuter says that makes the COND unproven (→ FAIL), it must apply to both, which is V5b, not V5a.

---

## 8. Internal-consistency findings on the rev-3 rule (for whoever writes the §8 row)

1. **The rule as defined gives no winner here.** 01's glossary: "A candidate that **beats every other one** head-to-head wins" [C-PROTO4-012]. A beats D but only **draws** C (5–5), so no candidate meets that definition. The verdict instead uses a weaker test, "the only finalist that **no other finalist beats**", plus a "tier argument" to break the A–C draw. That tier argument is a judgement, not a pre-named decision-critical row (critic P3-1 said the same).
2. **Rows were written and counted in the same commit as the rule.** The A–C and D–C counts first appear with the pairwise rule in `7836316`, after the scores. That is fine for evidence, but it means the count itself has not been put to a refuter (P3-2).
3. **"Within reach of a tie"** (the glossary's trigger) has no numeric definition. Any logged version must say exactly when a third candidate enters (for example "shares second place", or "within 3.0 of the leader"); on either of those definitions A does **not** enter on the rev-3 card.

---

## 9. What the run should do with this (recommendations; this file edits nothing else)

| ID | Recommendation | Requirement IDs |
|---|---|---|
| REC-PROTO4-01 | Present S1 to the founder as: "**Frozen protocol: Ubuntu 26.04 (D), fragile (C in 3/14 runs), conditional on Z-01.** The run's recommendation, Debian (A), rests on a post-scoring three-way rule that needs your approval." Keep the OS argument in 01; change only the label of where the verdict comes from. | RS-1, RS-4 |
| REC-PROTO4-02 | Add a §8 row **only if** the founder adopts the rule. Proposed text: `| <date> | 1.1 | Tie-break: when <exact trigger>, all candidates meeting it are finalists and are compared pairwise on the DC rows; a candidate that no other finalist beats wins; a remaining draw is decided by <pre-named rule>. | Founder decision Z-<n> (Q-P3-1); A's exclusion on rev-3 hinges on doc-only cell C·C2. | Founder | S1: D (frozen, 6–4 over C) → A (pairwise). S2–S5 unchanged. |` | RS-4 |
| REC-PROTO4-03 | Until then, mark the S1 verdict `blocked: founder-decision` in 24 and list Q-P3-1 in 26 (mission §2 rule 8), stating the default the run assumes and why. | RS-1 |
| REC-PROTO4-04 | Pre-register the shared-second-place case now (V1), because W2-HW-3 failing produces exactly that card (D 62 · C 60 · A 60). Without a rule written before the test, that outcome will again be decided after the scores are known. | RS-4, F-12 |
| REC-PROTO4-05 | Correct the founder PDF's "all inside the tie band" sentence (P3-3) to: "bootc and Ubuntu are inside the tie band; Debian is 4 points behind and outside it." | RS-1 |
| REC-PROTO4-06 | Write the row-count tie-break method into the next §8 row as well (it has been used since rev. 1 but is not in the frozen text), so both S1 and S2 tie-breaks rest on a written rule. | RS-4 |

---

## 10. Sources (all inside `<repo>`, pinned)

| Source | Pin | sha256 |
|---|---|---|
| `research-output/evidence/scorecard-weights.md`, lines 1–195 | `414d60a2528a2e0172ff35180c78f6801ec4b1af`, `ee98bc778551b430f3b81707731d8e5f7549fb73`, `7836316f8e63128fbd3c9095a74770b33cc63597` | `7d82ef25…e34990d` (identical at all three) |
| `research-output/evidence/scorecard-weights.md`, whole file | `414d60a2…` | `7970b4e5e330dcc3f0a0f911ee5bb0e33198ad82317378b6c766f2c0425773d3` |
| `research-output/evidence/scorecard-weights.md`, whole file | `7836316f…` | `bb272bcbef56847ae5bc2f6cbe7a8627a20ca88b12cec53cd33f14f7db44beab` |
| `research-output/01-FOUNDATION-DECISION.md` | `7836316f…` | `534a6e069ae0d2dd573d2a1b5f1dd7261b1881c13df5e71e784305aa71ec9809` |
| `research-output/01-FOUNDATION-DECISION.md` §3.1.5 (rev. 1 and rev. 2 headings) | `414d60a2…` L139, `ee98bc77…` L157 | — |
| `research-output/evidence/scorecard-rev3.md` §3.1–§3.4 | `7836316f…` | — |
| `research-output/23-RISK-REGISTER.md` RR-09 (L125) | `7836316f…` | — |
| `RESEARCH-MISSION.md` §6 "Scorecard protocol" (L213–218) | working tree at `7836316f…` | — |

No web sources were needed; every fact here is a repository fact checked with `git show` and `git log -p`. Recalculation used exact fractions (Python `fractions`), with the frozen §6 rescaling rule.

---

## Glossary

- **Frozen protocol:** the contest rules in `scorecard-weights.md`, locked before scoring; only changeable through a logged §8 row for an allowed reason.
- **Tie band:** the frozen rule that a gap of under 3.0 points between the top two is a tie.
- **Finalists:** the candidates that enter the tie-break; under the frozen text, the top two.
- **Tie-break:** settling a tie with the decision-critical evidence and refuter tables, never by changing scores.
- **Pairwise (head-to-head) tie-break:** comparing every pair of finalists separately and looking for one that wins every pair. Added in rev. 3, not in the frozen rules.
- **COND (conditional) gate:** a gate met only with a named mitigation (cost and owner); the candidate stays ranked and the mitigation goes into the plan and risk register.
- **Fragile / unstable:** the frozen sensitivity labels: the winner changes in 1–3 (fragile) or 4+ (unstable) of the 14 weight-perturbation runs.
- **Variant:** the same card with one disputed cell or gate read the other way, shown so the founder can see what that single judgement costs.
