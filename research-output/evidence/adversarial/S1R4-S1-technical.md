# S1R4 · S1 base-OS verdict (rev. 3) · technical refuter

**Lens:** technical · **Date:** 2026-11-11 · **Refuter round:** 4 (RESEARCH-MISSION.md §2 rule 7)
**Target:** `01-FOUNDATION-DECISION.md` §3.1.2–§3.1.5 and §1: "Debian 13 (A, 60.0) is kept as the base over RHEL-family bootc (C, 64.0) and Ubuntu 26.04 (D, 62.0) by a three-way pairwise tie-break." Judged on (1) whether the frozen protocol in `evidence/scorecard-weights.md` v1.0 yields this result and (2) the technical merits.
**Read:** `01` §1, §3.1, §4.1; `scorecard-weights.md` §1–§6, §8; `scorecard-rev3.md` §1, §3; `decision-critical.md` DC list; cited claims C-W2-001/004/013/018/043/044/050/057, C-W3-039/049/058, C-DEC-006/013, C-SCORE-025/026/029/030, C-LAB-fedora-bootc-011/013, C-LAB-ubuntu-2604-leg-004, C-REF-DC-cost-003/009, C-REF-DC-robotics-009/010, C-REF-DC-longevity-001, C-REF3-DC-technical-022/024, C-REF3-DC-longevity-001, C-STEEL-jb-015. No earlier adversarial file was read before this view was formed.
**New sources:** `claims/REF4-S1R4-technical.csv` (C-REF4-S1R4-technical-001…006).

> **Explain it like I'm the founder.** The rules we froze say: if the top two are within 3 points, compare those two on the decision-critical evidence. On the final card the top two are bootc (64) and Ubuntu (62). Debian is third (60), and in none of the 14 weight-shake runs is it within 3 points of the winner. To keep Debian, the decision added it as a third finalist, then counted rows. Several of those rows are not decision-critical questions, and one draw was broken by a new "which tier does this row matter for" rule. If you count only the decision-critical questions, the three bases beat each other in a circle: Debian beats Ubuntu, Ubuntu beats bootc, bootc beats Debian. Debian may still be the sensible engineering choice, but the frozen rules did not produce it. The decision says so in one sentence, and the summary should say so too.

---

## 1. Verdict

**WEAKENED.** The protocol-compliance part is **refuted**, and the engineering merits survive.

- **Protocol: refuted.** The frozen protocol (§3: "a difference of under 3.0 points between the **top two** is a tie") does not make A a finalist on the cited card. The extra finalist, the row-count method, the non-DC rows and the tier rule that breaks the 5–5 draw were all added after the ranking was known. That is the move the freeze exists to prevent (`scorecard-weights.md`, founder box: "stops anyone… from quietly changing the rules after seeing which option is ahead"). `01` §3.1.5 admits the strict reading picks **D**. It then sets D aside on G1 COND, which the gate rules do not allow (see §2.3).
- **Merits: hold, narrowly.** bootc's Pi 5 path is experimental, and its commit step is manual through a one-star, unlicensed bootloader [C-SCORE-025, C-SCORE-026]. The greenboot silent-downgrade bug is still open with no fix PR [C-REF4-S1R4-technical-006]. Ubuntu's redistribution permission is unanswered [C-W2-050]. Debian is the lowest-regret *engineering* choice today. But this is a judgement and should be labelled one, not a protocol result.

## 2. Strongest counter-argument

### 2.1 A is never a top-two tie candidate on the cited card

I recomputed the 14 runs from `scorecard-rev3.md` §3.2 cells (C: 3,3,3,3,4,3,4 · D: 3,3,3,3,3,2,5 · A: 3,3,3,3,3,3,3; ±5 per weight, others rescaled). C wins all 14, which is **Robust** under §6.3. A's gap to the winner ranges from 3.1 to 4.9: it is **never under 3.0**. A is second in exactly one run (C7 −5: C 63.11, A 60.00, D 59.89), and even there it is outside the band. (`scorecard-rev3.md` §1 says "A is never second". That is wrong for C7 −5, and `01` §3.1.4 has it right.) A reaches the tie band only through D's band (D 62 → A 60). §3 does not provide for this, because it defines the tie between the leader and the runner-up.

The reading that does make A a finalist is the stricter C·C2 = 2 variant (D 62 · C 60 · A 60). That reading may be the correct one (§2.4). But the decision did not adopt it. It adopted C·C2 = 3 (`01` S1-9) and then argued as if the variant held.

### 2.2 The tie-break used non-DC rows and an extra rule. A DC-only recount gives a cycle

§3 says a tie "is settled by the decision-critical evidence (`evidence/decision-critical.md`) and the refuter tables". Of the 15 rows in §3.1.5, five are not DC questions: governance, NVIDIA trajectory, IIoT vendor process, lab and proven competitor. G1/Q-W2-1 is a gate, not a DC. Several of these rows score the same thing as a weighted cell a second time: governance repeats C1, proven competitor repeats C4 (3 for all three), and lab repeats C3. Here is the recount on DC rows only, using `01`'s own "favours" assignments:

| Pair | DC rows won | Result |
|---|---|---|
| A vs D | A: DC-03 (10k), DC-05, DC-19, DC-04 · D: DC-13, DC-15 | **A 4–2** |
| D vs C | D: DC-07, DC-19, DC-13, DC-15 · C: DC-03 (10k), DC-05, DC-04 | **D 4–3** |
| A vs C | A: DC-07, DC-19 · C: DC-05, DC-13, DC-15 | **C 3–2** |

The result is a **cycle with no undefeated finalist**: A beats D, D beats C, C beats A. With the G1 row added back (A ≈ C > D), D vs C becomes 4–4, and **C is the only finalist no one beats**. On either count, Debian's "beats or draws everyone" (`01` §3.1.5) depends on the five non-DC rows. The A–C draw also needs an extra rule that weights rows by tier ("C's five wins sit on tiers the plan already gives to other flavors"). The frozen file contains no such rule. It also applies only one way: A's Jetson and GPU weaknesses are likewise "given to other flavors", yet A was not credited on that basis against D.

### 2.3 Using G1 COND to set aside the strict-reading winner breaks the gate rule

§2 says CONDITIONAL is *ranked*: the mitigation goes into the plan and the risk register, and the candidate is not excluded. `01` §3.1.5 sets D aside because "D's G1 condition… is unmet… so D cannot ship today". That turns COND into FAIL, after the fact and for one candidate only. **A carries the same condition**: its G1 is COND on the same claim [C-W2-050], because its Jetson flavor is modified L4T Ubuntu [C-REF-DC-cost-007]. G1 has now entered three times (gate, D·C6 = 2, and tie-break row 1). Under the stated rules, the strict reading's answer is **D, carrying a COND mitigation**.

### 2.4 Stack-consistency (rule 6) cuts against A's own cells

§1 says each candidate is "a complete stack… for example 'Debian 13 + Rugix', not just 'Debian'". A is now **Debian 13 + RAUC**. Its two cells that decide the outcome both cite evidence from **Debian + Rugix**:
- A·C4 = 3 cites umbrelOS [C-W2-043], which ships Rugix. The ledger records **no shipped Debian or Ubuntu + RAUC product** [C-DEC-013].
- A·C1 = 3 (S1-1) cites umbrelOS's Debian 12 → 13 OTA rebase [C-W3-039], which was also done through Rugix. A RAUC-driven Debian rebase is unmeasured (T-W3-04 has not run).

S1-2 asserts that the base cells "do not depend on the engine". The protocol's own unit is the stack, and the bootc row is scored as an integrated bootc + greenboot stack. On a stack-consistent reading, A·C4 → 2 gives **A = 57.0**, which is outside every band. The best counter-point for A is C·C3. bootc's power-cut silent downgrade [C-LAB-fedora-bootc-011] is still unfixed and has no linked fix PR [C-REF4-S1R4-technical-006], while anchor 3 requires "power-loss safety". Applied symmetrically, rule 6 gives **C·C3 → 2 (C = 61.0)**. That would leave D 62 · C 61 · A 60 (or 57). The protocol has to apply both corrections or neither, and the decision applied neither.

### 2.5 New technical evidence against A's lifecycle and Pi cells

- **Kernel runway shorter than Debian LTS.** Trixie's 6.12 kernel and Raspberry Pi's 6.18 line both have an upstream LTS EOL of **Dec 2028** [C-REF4-S1R4-technical-001]. Debian LTS runs to 2030-06-30 [C-W2-001]. From 2029 to mid-2030, A's x86 kernel security therefore depends on Debian's own kernel team, or on a CIP 6.12 SLTS branch that Debian does not package (CIP's dates were not verified here; the CIP announcements page shows no text). On the Pi, it depends on Raspberry Pi, which gives no dated window [C-REF-DC-robotics-009]. A·C1 = 3 rests on a rebase that has never been shown on this stack (§2.4). C (AlmaLinux 10, vendor-maintained el10 kernel to 2035 [C-W2-013]) and D (Canonical's kernel to 2036 [C-W2-005]) do not have this gap.
- **The Pi 5 trixie pipeline keeps regressing at the initramfs and bootloader level.** A Raspberry Pi kernel bump from 6.12 to 6.18 on trixie hung boot on Pi 5 NVMe/LVM. Raspberry Pi closed the report as outside its repo, because Debian's `initramfs-tools` `MODULES=dep` drops `dm_mod` [C-REF4-S1R4-technical-004]. That falls on OneMind's own image build, which mixes Debian's initramfs tooling with Raspberry Pi's kernel. Separately, a trixie Pi 5 that boots NVMe on the 2026-02-23 bootloader does not enumerate certain drives. Raspberry Pi declined drive-specific fixes, and a second drive model reported the same failure in October 2026 [C-REF4-S1R4-technical-005]. These add to the DC-19 regressions already ledgered [C-REF3-DC-technical-022, -024]. They weaken "A ≥ D" on DC-19, where D has a single certified vendor kernel [C-W2-057], with its own open boot bug [C-DEC-006].
- **Secure Boot CA expiry (neutral, recorded).** Debian 13.6 warns that future `shim-signed` updates could make systems unbootable under Secure Boot unless the OEM's CA, KEK and DBX updates are applied [C-REF4-S1R4-technical-003]. This affects every shim-based base equally. It matters only for the "BYO hardware, flash our image" path, because factory-enrolled boxes use OneMind's own db key. It does not move the ranking.

## 3. What would flip this verdict

- **To UPHELD:** the protocol owner logs a §8 entry *before* any new data, defining "finalist" as any candidate within 3.0 of **any** finalist, and limiting tie-break rows to DC questions or to rows declared ahead of time. Then either (a) the stricter C·C2 = 2 reading is adopted (D 62 · C 60 · A 60), and a DC-only head-to-head without the tier rule makes A undefeated, or (b) W2-HW-3 fails on a real Pi 5, so C·C2 → 2 is measured rather than chosen.
- **To REFUTED on the merits too:** T-W3-04 measures a Debian major rebase above the lifecycle-cost bound, or Debian publishes no kernel-security path for 6.12 after Dec 2028 that covers arm64; **or** W2-HW-3 passes and greenboot #219 is fixed (C then wins the Pi rows); **or** Canonical grants Q-W2-1 (D then wins the strict reading with no condition to argue over).
- **Housekeeping either way:** correct `scorecard-rev3.md` §1 ("A is never second"), and state in `01` §1 that the S1 result is a **founder judgement outside the frozen tie-break**, since §6.3 sends unsettled decisions to `26-OPEN-QUESTIONS-FOR-ZEUS.md`.

## 4. Sources opened (new)

| ID | Source | What it shows |
|---|---|---|
| C-REF4-S1R4-technical-001 | https://www.kernel.org/category/releases.html | 6.12 and 6.18 longterm, projected EOL Dec 2028 |
| C-REF4-S1R4-technical-002 | https://www.debian.org/releases/trixie/ (via search summary; not used for a score) | LTS to 2030-06-30; architecture set reduced during LTS |
| C-REF4-S1R4-technical-003 | https://www.debian.org/News/2026/20260711 | 13.6: 2013 Secure Boot CA expired; future shim-signed updates may not boot without OEM CA/KEK/DBX updates |
| C-REF4-S1R4-technical-004 | https://github.com/raspberrypi/linux/issues/7367 | 6.18.29 on trixie hangs Pi 5 boot on NVMe LVM; cause: initramfs-tools `MODULES=dep` omits `dm_mod`; closed as outside repo |
| C-REF4-S1R4-technical-005 | https://github.com/raspberrypi/rpi-eeprom/issues/816 | Trixie Pi 5 NVMe not enumerated with bootloader 2026-02-23; drive-specific fix declined; second drive model reported 2026-10-22 |
| C-REF4-S1R4-technical-006 | https://github.com/fedora-iot/greenboot-rs/issues/219 | Silent-rollback bug open, no linked fix PR or branch (checked 2026-11-11) |
