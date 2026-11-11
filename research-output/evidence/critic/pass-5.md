# Completeness critic, pass 5

**Date:** 2026-11-11 · **Scope:** RESEARCH-MISSION.md §4, §6, §7 and §9, checked against everything in `research-output/`. The working tree of `research/ultracode-foundation` is `7836316` (rev. 3, pushed) plus the uncommitted wave-4 changes (rev. 4 and FIX4). Inputs: `evidence/critic/pass-3.md` and `pass-4.md`.

**Not counted as gaps (the orchestrator handles these at commit time):**
- uncommitted files;
- the master `evidence/claims.csv` re-merge (2,704 rows against 2,890 in the per-tag ledgers);
- the gitleaks run at commit;
- PR #1 still being a draft.

**Method:** scripted checks plus targeted reading.
- **Claim IDs.** Every claim ID in 00, 01, 03–07, 20–30, `decision-critical.md`, `scorecard-weights.md`, the three FIX4 refuter files and the PDF source (`report/chapters/*.md`, `main.typ`) was resolved against the 106 per-tag ledgers (2,890 rows, 0 duplicate IDs). The regex uses a look-behind and expands `…` ranges. I recorded `source_type` and `status` for every ID cited in 01.
- **Exceptions list.** 01's exception rows were diffed against `critic/cit4-mapping.md`.
- **S1 verdict.** Re-read against `scorecard-weights.md` (§2, line 67, §5 rules 2/5/6, §6, §8, including the new FIX4 row on line 205) and against 01 §3.1.6 and §5.1.2.
- **Refuters.** Files in `adversarial/` were grouped by DC.
- **Requirements and bank.** The 97 IDs of `docs/REQUIREMENTS.md` were checked against 25. Each of the 335 bank IDs in 24 was checked for exactly one status per table row. Every `blocked: founder-decision` ID was checked against 26.
- **Licence matrix.** Coverage of the rev-4 decision of record, including the Secure Boot chain.
- **PDF.** `pdfinfo`, `pdftotext` and `report/verify_pdf.py` were run on the PDF, and its text was compared with 01 rev. 4 and FIX4.
- **U-SB.** Traced through 20, 22, 23, 24, 26, 30 and `PREREGISTRATION.md`.
- **Hygiene.** Greps for the account name, `/Users/`, the host folder layout, `.ts.net`, RFC1918/CGNAT, e-mail and credential patterns over the working tree. The same greps over commits `414d60a`, `ee98bc7`, `7836316` and `origin/main`. `gitleaks dir research-output` and `gitleaks git` on `origin/main..HEAD` (8.30.1).

**The critic fixed nothing.**

**Severity:** **S1** blocks §9 or breaks a hard rule · **S2** weakens a P0 conclusion or a decision-critical answer · **S3** a protocol or ledger defect · **S4** hygiene or polish.

**Bottom line.**
- **FIX4 closes P4-1 and P4-2.** The rev-4 decision of record has three refuters (all *weakened*). The Ubuntu Secure Boot leg (U-SB) is pre-registered in 01 §3.1.6 (h) and logged in `scorecard-weights.md` §8 before it runs. The licence matrix now has the Ubuntu 26.04 core image, both Ubuntu kernels, the Pi 5 boot path and Ubuntu Pro for Devices.
- **P4-8 is partly closed.** G1 has a provisional $0–$250-per-box bracket.
- **Eight pass-4 gaps are untouched:** P4-3, P4-4, P4-5, P4-6, P4-7, P4-9, P4-10 and P4-11.
- **The main new finding (P5-1):** the decision of record now rests openly on one cell, D·C3 = 4. That cell cites no Ubuntu-specific evidence. 01 concedes that the `doc-only` mark does not apply to it. The test that settles it (U-SB / LT-VM-20) needs only a VM and the existing `secureboot-1152` kit, which this environment has already run. It is scheduled as a founder task for weeks 2–3 instead of being run now.

**The run is not dry.** No S1 gap remains.

---

## Part 1. §9 Definition of done

| §9 item | Verdict | Evidence |
|---|---|---|
| Tier A to the teardown minimum, scorecard protocol, adversarial protocol, VM lab | **Not met** (narrowly) | Teardowns and 18 lab spikes as in pass 4. **Scorecard protocol: met** (Part 3.1), but the deciding cell's support is thin (P5-1). **Adversarial protocol:** the rev-4 S1 result has 3 refuters (technical/security, longevity, cost), each with ≥ 2 new sources [C-FIX4-001…013], a verdict, flip evidence and a written response. Rule 7's "gets *only* the claim and its cited sources" is not met: one agent wrote all three after reading 01 (disclosed in 01 §5.1.2; P5-2). Loop-until-dry is not reached |
| Every workstream W1–W17 has its file at its tier's depth | **Met** | Unchanged |
| Every bank question has a status; DCs fully evidenced | **Status met; DCs not fully evidenced** | 335/335 IDs, one allowed status each, 0 conflicts (74 answered · 237 partial · 14 founder-hardware · 7 founder-decision · 2 live-cluster · 1 paywalled). Every DC has ≥ 3 refuter lenses (Part 3.3). DC-11, DC-21/R4-10 and E10 still rest on round-4 sources cited under colliding IDs (P4-3 open) |
| All 97 requirement IDs traced | **Met** (stale row) | 97/97 in 25, no unknown IDs. F-10 is still "Partial … 101 pages, built from rev. 3" (P4-5) |
| ADR-001 explicitly confirmed / changed / overturned | **Met** | 01 §7 and §7.3: D2 changed (rev. 4, conditional) to Ubuntu 26.04; R4-15 records that FIX4 left it unchanged |
| 20 (gates) and 21 (exit criteria) complete | **Met** | 20 schedules LT-VM-20 (U-SB) at G1 (l. 309, 413) and the base lock at G6 |
| Every claim used in 01 resolves to a primary-source row | **Not met** (excluding the master merge) | 800 distinct IDs in 01, **0 unresolved**. 107 are not PRIMARY (75 SECONDARY, 26 PRIMARY-METADATA, 2 UNVERIFIED, 2 COMMUNITY, 1 VENDOR-FORUM, 1 INFERRED). 30 are not `verified`. 01 claims "met with listed exceptions", but **52 of the 127 exception IDs are not in `cit4-mapping.md`** (P4-4, up from 48). C-W19-047…049 are still typed `PRIMARY` (P3-4 residual) |
| `license-matrix.csv` covers every recommended component | **Met** | 282 rows, each with a source. New rows: Ubuntu 26.04 core image (x86_64, arm64, Pi 5), Ubuntu generic kernel 7.0, `linux-raspi`, Pi 5 boot path on Ubuntu, Ubuntu Pro for Devices. The Debian row is relabelled "A leg". P4-2 is closed. The S4 residue from pass 4 (about 20 rows with a branch name as the version) remains |
| 28, 29, 30 complete | **Met** | Unchanged. 30 l. 597 is stale after FIX4 (P5-4) |
| PDF built, standalone, visual, covers every topic | **Met** | 108 pages, built 10:41 (after 01's last write at 10:40). `verify_pdf.py`: 75 topics, 0 missing, 36 images embedded, 477 claim IDs in the text. All IDs in `report/` resolve. Consistent with 01 rev. 4 + FIX4: 65/64/63, 6–4, 11/14, U-SB row, $0–$250 bracket, Z-38/39/40. The "tie band" misstatement is gone. Wording defects in §4.4: P5-6 |
| PR marked ready for review | Not met; **not counted** | Draft; blocked on Z-28 |

## Part 2. §6 deliverables

All §6 files exist. Changes since pass 4:

| Deliverable | Note |
|---|---|
| 00 | §6 records FIX4 and says P4-2 is closed. **The same section still says** "PDF: rebuild from rev. 4; it still misstates the tie (P3-3)". l. 4 says "The PDF still shows rev. 3", and §5 says "Built (101 pages) from rev. 3 · Needs rebuild" (P4-5) |
| 01 | R4-15, S1-12 FIX4 note, §3.1.6 (h) U-SB rows, (i) G1 bracket, §5.1.2 table, §12 adversarial bullet. §1 and §7 Debian lines are unqualified (P4-7) |
| 20, 22 | LT-VM-20 added and scheduled at G1. Its criteria differ from the pre-registered map (P5-3) |
| 23, 26 | RR-09 and Z-01 carry the FIX4 cost and kernel-tie questions. Z-38, Z-10 and RR-33 do not name U-SB as a deciding event (P5-4) |
| `scorecard-weights.md` | §8 has a FIX4 row (l. 205): decision-map addendum, "no weight, anchor, cell or tie-break-row change", outcome under each event. It meets the §8 logging rule |
| `license-matrix.*` | P4-2 closed |
| SOURCES.md | Compiled from 2,875 rows; the ledgers now hold 2,890 (P5-5) |
| Lab | Still no versions file in `rauc/`, `secureboot-rauc/`, `secureboot-1152/`, `w19-sysext/` (N11) |

## Part 3. Mandated checks in detail

**3.1 S1 verdict against the frozen protocol (`evidence/scorecard-weights.md`).** I re-checked each step after FIX4:

1. **Gates.** A, C and D have no FAIL. COND results are ranked (§2).
2. **Rule-6 re-scores.** S1-12 is unchanged: C3 = 4 for A, D, G and F; D, G and F are marked `doc-only`. FIX4 adds a note that `doc-only` under rule 5 covers missing hardware only. It keeps D·C3 = 4 "on the documentation reading of anchor 4", because lowering D alone would break rule 6.
3. **Card.** D 65 · C 64 · A 63 (unchanged).
4. **Tie test.** D–C, 1.0 < 3.0. Tie-break: D 6–4. Sensitivity: D 11/14, fragile.
5. **§8 log.** The FIX4 row adds U-SB to the map, logged before the run, with the card under each outcome. Recomputed totals match 01 (h) and the PDF.

**Verdict: 01's S1 result still follows the frozen protocol as written.** The pass-4 caveats remain: Z-40 (the counting method) and Z-39 (uncosted COND); P4-8 is now partly bounded. The new weakness is evidential, not procedural (P5-1). D's one-point lead is the C3 cell. Its two citations are C-LAB-ubuntu-2604-leg-011, a Ubuntu lab with **no** Secure Boot and the GRUB path [C-FIX4-010], and C-LAB-secureboot-1152-005, a **Debian** guest. Neither establishes anchor 4 for Ubuntu. "One citation per cell" is met in form but not in substance.

**3.2 Claim IDs.** 0 unresolved IDs in every file checked, including the FIX4 files (13/15/28 IDs) and every PDF chapter. Non-PRIMARY / non-verified IDs per file:

| File | Non-PRIMARY | Non-verified |
|---|---|---|
| 00 | 2 | 1 |
| 03 | 2 | 1 |
| 04 | 5 | 3 |
| 05 | 10 | 0 |
| 06 | 7 | 0 |
| 07 | 0 | 0 |
| 20 | 7 | 2 |
| 21 | 5 | 4 |
| 22 | 8 | 7 |
| 23 | 43 | 13 |
| 24 | 64 | 35 |
| 26 | 17 | 7 |
| 30 | 14 | 6 |

The 52 exception IDs missing from `cit4-mapping.md` include:
- C-FIX4-006, -009, -012 and -013 (the new SECONDARY rows);
- C-REF4-S1R4-security-007 (INFERRED, in the tie-break row);
- C-STEEL4-bootc-013, -024 and -025;
- C-REF4-DC-technical-006 and -007, which are also colliding IDs;
- the LAB-aarch64-gate, LAB-secureboot-1152 and LAB-minimal-image-dc20 rows.

**3.3 Refuters.** 155 files in `adversarial/`.
- **Three or more dedicated lenses:** DC-03, 07, 09, 12, 13, 14, 15, 17, 18, 19, 20, 22, 23, 24 and E10. DC-04 has three lenses in the `W6-P0-1 (DC-04)` files.
- **Two dedicated round-4 lenses plus borrowed P0 lenses:** DC-01, 02, 05, 06, 08, 10, 11 and 21.
- **DC-16:** 25+.
- **Rev-3 S1 verdict:** S1R4 ×3 plus STEEL4.
- **Rev-4 S1 result:** FIX4 S1R5 ×3, not blind (P5-2).

**≥ 3 per decision-critical question: met.**

**3.4 Requirements.** 97/97 in 25. Every easily-missed ID is in its named home.

**3.5 Question bank.** 335/335, 0 conflicts. Seven `blocked: founder-decision` IDs; **Q288 is still not named in 26** (P4-6).

**3.6 Licence matrix.** Covers the rev-4 decision of record (P4-2 closed). The Secure Boot chain is covered: shim, systemd (systemd-boot, UKI, cryptenroll), tpm2-tss/tools, cryptsetup, sbsigntools, efitools and efibootmgr. No separate row exists for an initramfs generator (dracut on Ubuntu 26.04, initramfs-tools on Debian). It is arguably inside each distro's aggregate row, so it is not raised as a gap.

**3.7 PDF.** See Part 1 and P5-6.

**3.8 Public-repo hygiene.**

*Working tree (`research-output/`):*
- No account name. No RFC1918 or CGNAT address. No tailnet hostname: only the bare string `.ts.net` appears, in rule text.
- The `/Users/` hits are false positives: a sed mask pattern in `lab/secureboot-1152/scripts/trim-logs.sh`, the Jellyfin API path `/Users/{id}` in a claim row, `hygiene-log.md` FP-11, and grep descriptions in the critic files.
- The e-mail-shaped strings are public project addresses (`security@pengutronix.de`, `aur-general@lists.archlinux.org`, `git@github.com`), systemd unit names and one archive filename.
- The credential-pattern grep hit only C-TD-flagged-033, which describes a gitleaks rule.
- **`gitleaks dir research-output`: no leaks. `gitleaks git` on `origin/main..HEAD`: no leaks (3 commits).**
- The host folder layout is still quoted in `critic/pass-2.md` l. 48 and `critic/pass-3.md` l. 61 and 114 (P4-11, open).

*History and `main`:*
- `414d60a` still has the account name in 17 files.
- `ee98bc7` and `7836316` still carry the host folder layout.
- Z-28 still names only `414d60a` (P4-9, open).
- `origin/main:research/platform/iiot-landscape-and-requirements.md` l. 441 still holds a `/Users/<founder alias>/…` path (P4-10, open).

---

## Part 4. Pass-3 and pass-4 gaps: closed or open

| Gap | Status | Evidence |
|---|---|---|
| **P4-1** rev-4 decision of record has no refuter | **Closed, with residue** | `FIX4-S1R5-{technical,longevity,cost}.md`; 01 §5.1.2; R4-15. Residue: not blind (P5-2) |
| **P4-2** licence matrix misses the recommended base | **Closed** | 282 rows; Ubuntu 26.04 core, generic 7.0 kernel, `linux-raspi`, Pi 5 boot path on Ubuntu, Pro for Devices; Debian row relabelled "A leg" |
| **P4-3** REF4 claim IDs reused for different facts | **Open** | `DC-11-technical.md` and `DC-E10-technical.md` still cite `C-REF4-DC-technical-006/007`, whose ledger rows are the Umbrel OTA facts. 01 still says "not ledgered" in 14 places, including the new S1 tie-break row "signed GPU/driver modules" (l. 339) and R4-10 |
| **P4-4** exception list incomplete | **Open (worse)** | 127 exception IDs in 01; 52 not in `cit4-mapping.md` (pass 4: 48 of 123) |
| **P4-5** stale PDF status | **Open** | `00` l. 4, l. 88 and l. 96; `README.md` l. 42; `REVIEW-CHECKLIST.md` l. 18; `25` F-10 (l. 262) and changelog l. 435 still say 101 pages / rev. 3. 25's counts (90 · 4 · 3) are therefore wrong. 00 §5 still says "24's S1 item should become blocked", which is already done |
| **P4-6** Q288 not mapped in 26 | **Open** | Q288 does not occur in 26 |
| **P4-7** unqualified Debian lines in 01 | **Open** | §1 "Image build (D1)" ("snapshot-pinned Debian") and "Kernel" ("Debian stock"); §7 "Net" and "Final net (revision 3): confirmed — D2 (Debian core)" under the rev-4 heading |
| **P4-8** G1 COND has no stated cost | **Partly closed** | 01 §3.1.6 (i): provisional $0–$250 per box over 10 years [C-FIX4-001, C-FIX4-004], labelled an assumption; RR-09 and PDF carry it. The decisive figure still needs Canonical (Z-01) and the Z-39 ruling |
| **P4-9** Z-28 scoped to `414d60a` only | **Open** | 26 l. 210 is unchanged |
| **P4-10** `/Users/<alias>` path on `main` | **Open** | Unchanged |
| **P4-11** critic files quote the host layout | **Open** | pass-2 l. 48; pass-3 l. 61 and 114 |
| P3-4 residual: C-W19-047…049 typed PRIMARY | **Open** | `claims/W19.csv`: PRIMARY / partial |
| P3-8 (b)/(e) residual | Folded into P4-5 | — |
| N1/N2 personal data in history | **Open (founder)** | Z-28 |
| N11 lab versions files | **Open (S4)** | 4 spikes |
| N12 KubeCon NA 2026 days 3–4 | **Open (date)** | Today is 2026-11-11; cannot close before 2026-11-12. C-W4-039/040 `recheck_by` 2026-12-10 |
| P1 #3 master `claims.csv` | Not counted | 2,704 vs 2,890 |

**Tally:**
- **Pass 4's 11 gaps:** 2 closed (P4-1, P4-2), 1 partly closed (P4-8), 8 open (P4-3…P4-7, P4-9…P4-11).
- **Carried items still open:** P3-4 residual, N1/N2, N11 and N12.

---

## Part 5. New gaps not raised by passes 1–4

| # | Sev | Gap | File(s) | What would close it | Agent can fix? |
|---|---|---|---|---|---|
| **P5-1** | **S2** | **The decision of record rests on a cell that cites no Ubuntu evidence, and the test that settles it is runnable now.** The D–C margin is 1.0, and D·C3 = 4 alone carries it (V3, D·C3 = 3, gives **C**). The cell cites C-LAB-ubuntu-2604-leg-011, a Ubuntu leg with no Secure Boot that booted through GRUB [C-FIX4-010], and C-LAB-secureboot-1152-005, a Debian guest. 01's own S1-12 FIX4 note concedes that `doc-only` (rule 5) covers missing hardware only, and that here "the Ubuntu leg can run in the same VM and simply has not". **U-SB / LT-VM-20** needs only QEMU + OVMF + swtpm and the existing `secureboot-1152` kit, which this environment has already run twice. Yet 20 schedules it for the founder in weeks 2–3, and 01 calls it "VM-only, so it runs before G1". Today the S1 answer reads "D, contingent on a cell the run could have tested". | `01` §3.1.6 (c), (d), (h); `22` LT-VM-20; `20` l. 413 | Pre-register a `lab/ubuntu-secureboot` spike (README with the pass/fail of (h): same verdicts as the Debian run, two complete runs, no partition or bootloader change), run it, ledger the result, and apply the pre-registered map row (D stays, or C) | **Yes** (VM only) |
| **P5-2** | S3 | **The FIX4 refuters are not independent** (rule 7: "each refuter gets *only the claim and its cited sources*, not the author's reasoning"). One agent wrote all three in sequence after reading 01 (disclosed in 01 §5.1.2 and REVIEW-CHECKLIST l. 192). They are the only refuters of the P0 conclusion as it now stands. | `adversarial/FIX4-S1R5-*.md`; `01` §5.1.2 | Re-run the three lenses as separate blind sub-agents. Give each only §3.1.6 (c)–(h), the frozen file and the cited rows. Compare their verdicts with FIX4's | Yes (orchestrator can start sub-agents) |
| **P5-3** | S3 | **LT-VM-20's criteria differ from the pre-registered map.** 01 (h) and `scorecard-weights.md` l. 205 say: fail, or pass only after a partition or bootloader change → D·C3 = 3 → **C** automatically; the pass needs **two unchanged runs**. 22 LT-VM-20 says instead: "any difference → a rule-6 re-score **request** … goes to the DEC owner". It does not require two runs and does not name the layout-change condition. `PREREGISTRATION.md` has no U-SB entry. A test whose result changes the base OS should not have two readings. | `22` LT-VM-20; `20` l. 413; `lab/PREREGISTRATION.md` | Copy the (h) wording into 22 and 20 verbatim, and add a frozen, hashed U-SB entry to `PREREGISTRATION.md` | Yes |
| **P5-4** | S4 | **FIX4 has not reached every file that describes the S1 result.** `24` l. 682 and `30` l. 597 still say the rev-4 re-scores, recount and decision map "have not yet been put to a refuter". 26 Z-38 option (a) ("the pre-registered map decides on W2-HW-3 and Z-01"), Z-10 and 23 RR-33 do not name U-SB as a deciding event. The founder could then approve a map that is missing its likeliest flip. | `24`, `30`, `26` §H, `23` RR-33 | One sync pass naming U-SB / LT-VM-20 and the three FIX4 refuters | Yes |
| **P5-5** | S4 | **SOURCES.md is behind the ledgers again** (P3-13 regression). It was compiled from 2,875 rows; there are now 2,890, and the 15 `C-FIX4-*` rows (4 cited in the PDF) have no bibliography entry. 25 l. 80 says "112 ARCHIVE-GAP sources", but SOURCES.md says 114. | `SOURCES.md`; `25` | Regenerate after the last ledger write; take 25's count from SOURCES.md | Yes |
| **P5-6** | S4 | **The PDF's §4.4 decision table (p. 26) was abridged ambiguously when U-SB was added.** The row "Both of the above" now sits under three events (U-SB, W2-HW-3, Canonical) but means only W2-HW-3 + Canonical. The U-SB-plus-W2-HW-3 combination (→ Debian, 14/14) and the "U-SB passes" row are omitted. The intro says "before **either** is known" after naming three tests. "Three single judgements change the winner" omits V2, V3 and V8, which 01 (g) also lists. | `report/chapters/` (§4.4); PDF | Name the events in the combined rows, add the two U-SB rows, fix "either", and say "at least three" or list V1–V8 | Yes |
| **P5-7** | S4 | **Six ARCHIVE-GAP sources marked "decision-grade" are cited in 01:** C-DEC-006 (the open Launchpad `linux-raspi` bug, used in DC-19's tie-break row and in 22's EEPROM note), C-CIT4-008, C-W2-015 (Fedora's 13-month life, used in the founder box), C-W2-050, C-W3-024 and C-W6-068. Rule 1 requires load-bearing web sources to be archived. Saved text with a sha256 is the stated method when Wayback is blocked. These six have neither. | `SOURCES.md` §ARCHIVE-GAP; `evidence/sources/` | Save text + sha256 for the six (or SHA-pin the GitHub ones); then do the remaining decision-grade rows | Yes (page fetches; one bot-walled page may stay UNVERIFIED) |

## Part 6. Founder-only and date-bound items (for the orchestrator's final list)

- **Z-38, Z-39, Z-40 and Z-01** (base-OS decision, COND-as-FAIL reading, written scoring rules, Canonical/counsel). P4-8's decisive figure comes from Z-01.
- **Z-28** (history rewrite), widened per P4-9; **P4-10** (path on `main`, founder-authored file).
- **Hardware:** W2-HW-3 (Pi 5 bootc) before G1; F-PI5; Jetson; RT latency; real power-cut and firmware tests in 22. U-SB is **not** on this list: it is VM-only (P5-1).
- **N12:** the KubeCon NA 2026 days 3–4 re-check cannot run before 2026-11-12.

---

**Loop-until-dry status:**
- **New gaps per pass:** pass 1 added 24, pass 2 added 15, pass 3 added 13, pass 4 added 11.
- **Pass 5 closes** P4-1 and P4-2, partly closes P4-8, and leaves 8 pass-4 gaps open.
- **Pass 5 adds 7 new gaps:** 0 S1, 1 S2 (P5-1), 2 S3 (P5-2, P5-3) and 4 S4 (P5-4…P5-7). All seven can be fixed by an agent.

The run is **not dry**. The cheapest, highest-value next step is P5-1: one VM spike decides between Ubuntu and bootc without waiting for the founder.
