# Completeness critic, pass 6

**Date:** 2026-11-11 · **Scope:** RESEARCH-MISSION.md §4, §6, §7 and §9, checked against everything in `research-output/`. The working tree is `7836316` (rev. 3, pushed) plus the uncommitted wave-4 changes (rev. 4, FIX4 and FIX5). Inputs: `evidence/critic/pass-3.md`, `pass-4.md` and `pass-5.md`.

**What changed since pass 5:** FIX5 only.
- **Files changed after pass 5 (10:48 local):** `00`, `01`, `20`, `22`, `evidence/scorecard-weights.md` (new §8 row, l. 206) and `evidence/lab/PREREGISTRATION.md`.
- **New files:** `evidence/claims/FIX5.csv` (C-FIX5-001…004), `evidence/sources/FIX5.md` and the spike `evidence/lab/ubuntu-secureboot/`.
- **Unchanged:** no other deliverable, ledger, refuter file, `SOURCES.md` or the PDF.

**Not counted as gaps (the orchestrator handles these at commit time):**
- uncommitted files;
- the master `evidence/claims.csv` re-merge (2,704 rows against 2,894 in the per-tag ledgers);
- the gitleaks run at commit;
- PR #1 still being a draft.

**Method:** scripted checks plus targeted reading.
- **Claim IDs.** Every claim ID in 00, 01, 03–07, 20–30, `decision-critical.md`, `scorecard-weights.md`, the U-SB README, `report/chapters/*.md` and `main.typ` was resolved against the 107 per-tag ledgers. Those hold 2,894 rows with 0 duplicate IDs. The regex uses a look-behind and expands `…` ranges.
- **Exceptions.** 01's non-PRIMARY or non-`verified` IDs were diffed against `critic/cit4-mapping.md`.
- **S1 verdict.** Re-read against `scorecard-weights.md` rules 2 and 5, and the §8 rows on l. 204–206, and against 01 S1-12, §3.1.6 (h) and R4-16.
- **Refuters.** Lenses were grouped per DC from `adversarial/` (155 files).
- **Requirements and bank.** The 97 table IDs in `docs/REQUIREMENTS.md` were checked against 25's rows. 24's status column was parsed, and every `blocked: founder-decision` ID was checked against 26.
- **Licence matrix.** Row count, the source column, and coverage of the decision of record.
- **PDF.** `pdfinfo` and `pdftotext`, then a comparison of `report/chapters/04`, `11` and `15` with 01 rev. 4, FIX4 and FIX5.
- **Hygiene.** Greps over the working tree and the PDF text: account name, `/Users/`, host folder layout, tailnet names, RFC1918/CGNAT, e-mail and credential patterns. `gitleaks dir` was run from the repo root with `.gitleaksignore`, and `gitleaks git` on `origin/main..HEAD` (8.30.1). The account name and host layout were also grepped in commits `414d60a`, `ee98bc7`, `7836316` and `origin/main`.
- **FIX5 provenance.** The U-SB README, `env-probe.log` and C-FIX5-001…004 were compared with `lab/ubuntu-2604-leg/` (versions file and build logs) and with the host lab workspace, read-only.

**The critic fixed nothing.**

**Severity:** **S1** blocks §9 or breaks a hard rule · **S2** weakens a P0 conclusion or a decision-critical answer · **S3** a protocol or ledger defect · **S4** hygiene or polish.

**Bottom line.**
- **FIX5 handled P5-1 honestly.** U-SB was pre-registered, its criteria hashed and frozen, and the run attempted. It was recorded **BLOCKED (environment)**, with no cell or map change. The frozen protocol still gives **D**, resting on D·C3 = 4 (`doc-only`).
- **The P5-1 residue now needs someone outside this environment.** The Ubuntu archive does not resolve here, and the run must not bypass that. One caveat follows (P6-3).
- **P5-3 is partly closed:** the spike README and `PREREGISTRATION.md` carry the map wording. P5-2 and P5-4…P5-7 are untouched, and every open pass-4 gap is still open.
- **Five new gaps, none S1:**
  - **P6-1:** the 180-day gate rows never act on a U-SB failure.
  - **P6-2:** 26 has no RS-6 entry for the blocked Ubuntu archive.
  - **P6-3:** FIX5's "unreachable" contradicts a same-day Ubuntu build in this environment.
  - **P6-4:** the disclosed read past the DNS block is logged only in a lab README.
  - **P6-5:** the PDF predates FIX5.

**The run is not dry.** No S1 gap remains.

---

## Part 1. §9 Definition of done

| §9 item | Verdict | Evidence |
|---|---|---|
| Tier A to the teardown minimum, scorecard protocol, adversarial protocol, VM lab | **Not met** (narrowly) | Teardowns and 18 executed lab spikes as in pass 4. U-SB is the 19th spike: pre-registered, BLOCKED, and turned into a founder-runnable test (22 LT-VM-20, 20 D1), which §7 allows. **Scorecard protocol: met** (Part 3.1). **Adversarial protocol:** every DC has ≥ 3 lenses (Part 3.3). The rev-4 S1 result's three FIX4 refuters are still not blind (P5-2, open). Loop-until-dry is not reached |
| Every workstream W1–W17 has its file at its tier's depth | **Met** | Unchanged |
| Every bank question has a status; DCs fully evidenced | **Status met; DCs not fully evidenced** | 335/335, one status each: 74 answered · 237 partial · 14 founder-hardware · 7 founder-decision · 2 live-cluster · 1 paywalled. P4-3 colliding IDs are still under DC-11, DC-E10 and R4-10 |
| All 97 requirement IDs traced | **Met** (stale row) | 97/97 rows in 25; none missing, none unknown. F-10 still says 101 pages / rev. 3 (P4-5) |
| ADR-001 explicitly confirmed / changed / overturned | **Met** | 01 §7, §7.3, R4-15 and R4-16: D2 changed (rev. 4, conditional) to Ubuntu 26.04 |
| 20 (gates) and 21 (exit criteria) complete | **Met, with a gate defect** | 20 has G0–G7 and 21 has exit criteria. The G1 and G6 rows have no branch for U-SB, the one VM-only event in the pre-registered map (**P6-1**) |
| Every claim used in 01 resolves to a primary-source row | **Not met** (master merge excluded) | 804 distinct IDs in 01 (800 + 4 FIX5), **0 unresolved**. 107 are not PRIMARY (75 SECONDARY, 26 PRIMARY-METADATA, 2 UNVERIFIED, 2 COMMUNITY, 1 VENDOR-FORUM, 1 INFERRED). 30 are not `verified`. **52 of 127 exception IDs are still not in `cit4-mapping.md`** (P4-4). All four C-FIX5 rows are PRIMARY / verified |
| `license-matrix.csv` covers every recommended component | **Met** | 282 rows, 0 without a source. FIX5 added no component |
| 28, 29, 30 complete | **Met** | 30 l. 597 still says the rev-4 map "has not yet been put to a refuter" (P5-4) |
| PDF built, standalone, visual, covers every topic | **Met for coverage; stale** | 108 pages, Typst 0.15.1, built 10:41:55. 01 last written 10:58 (FIX5). No claim ID in `report/` is unresolved. Stale against FIX5 (**P6-5**); P4-5 and P5-6 are still open |
| PR marked ready for review | Not met; **not counted** | Draft; blocked on Z-28 |

## Part 2. §6 deliverables

All §6 files exist. Changes since pass 5:

| Deliverable | Note |
|---|---|
| 00 | l. 20 and l. 94 record FIX5 (BLOCKED; ready to run on day 1). l. 4 and l. 88 still say the PDF is rev. 3, 101 pages (P4-5) |
| 01 | R4-16; S1-12 FIX5 note; §3.1.6 (h) "U-SB status" paragraph (l. 385); §5.1.2 net line (l. 690). The card, cells and map rows are unchanged. The Debian lines in §1 and §7 are still unqualified (P4-7) |
| 20 | l. 323 (S1 map): FIX5 moves LT-VM-20 to **D1** (2026-11-16); l. 413 and l. 512 match. The G1 and G6 rows are not updated (P6-1). l. 413's outcome is still "rule-6 re-score request" (P5-3 residue) |
| 22 | l. 70 and LT-VM-20 (l. 509) are now week 1 and point to the frozen kit. The pass/fail column still differs from the map (P5-3 residue) |
| `scorecard-weights.md` | §8 row l. 206 (FIX5): "No weight, anchor, cell, row-count or map change"; BLOCKED is not a map event. It meets the §8 logging rule |
| `lab/PREREGISTRATION.md` | New row: ubuntu-secureboot, 2026-11-11T15:51:12Z, sha256 `c98a09d1…f8db` |
| `lab/ubuntu-secureboot/` | README (frozen §1–6, results, §R.2 deviations), `PREREGISTRATION.sha256`, `SHA256SUMS`, five scripts, `logs/env-probe.log`. There is no versions file; the tool versions are inside `env-probe.log` (see N11) |
| 23, 24, 26, 30, README, REVIEW-CHECKLIST, SOURCES.md, PDF | Not touched by FIX5. None of them mentions FIX5. 26, 24, 30, 21, README and REVIEW-CHECKLIST do not mention U-SB / LT-VM-20 at all (P5-4, P6-2, P6-5) |

## Part 3. Mandated checks in detail

**3.1 S1 verdict against the frozen protocol (`evidence/scorecard-weights.md`).**
1. **Gates.** A, C and D have no FAIL. COND results are ranked (§2).
2. **Rule-6 re-scores.** S1-12 is unchanged in value: C3 = 4 for A, D, G and F, and D, G and F are `doc-only`. FIX5's note says the cell stays 4 "on the documentation reading". It also says the reason D's leg is untested is now "an environment limit, not a choice".
3. **Rule 5 against the FIX4 concession.** Rule 5 covers only "hardware not on hand". FIX4 conceded that D's `doc-only` mark is not a hardware case. FIX5 does not invoke rule 5 again. It keeps the cell under the documentation reading of anchor 4, the same basis FIX4 used, and rule 2 does not apply because the cell's support is not UNVERIFIED. The protocol does not cover "a VM test is blocked by the environment". The FIX5 §8 row records the situation without inventing a rule. **Procedurally clean.**
4. **Card.** D 65 · C 64 · A 63 (unchanged).
5. **Tie test.** D–C, 1.0 < 3.0. Tie-break: D 6–4. Sensitivity: D 11/14, fragile.
6. **§8 log.** Rows l. 205 (FIX4) and l. 206 (FIX5) are logged, and both state no change.
7. **Decision map.** 01 l. 375–378 is unchanged and recomputes as before.

**Verdict: 01's S1 result still follows the frozen protocol as written.** The evidential weakness from pass 5 (P5-1) stands: D's lead is a cell with no Ubuntu evidence. It is now *disclosed and unavoidable here*, not a choice. Whether it is truly unavoidable is P6-3.

**3.2 Claim IDs.** 0 unresolved IDs in every file checked, the four C-FIX5 rows included. The non-PRIMARY / non-verified counts per file are the same as pass 5's table (01: 107 / 30; 23: 43 / 13; 24: 64 / 35; 30: 14 / 6). 01 has 127 exception IDs and 52 are still missing from `cit4-mapping.md`: the same list as in pass 5.

**3.3 Refuters.** No new adversarial file since pass 5 (155 files). Dedicated lenses per DC:
- **Three dedicated lenses:** DC-03, 04, 07, 08, 09, 12, 13, 14, 15, 17, 18, 19, 20, 22, 23, 24 and E10.
- **Two dedicated lenses plus borrowed W-series P0 lenses:** DC-01, 02, 05, 06, 10, 11 and 21.
- **DC-16:** the W19 set.
- **S1:** S1R4 ×3, STEEL4, and FIX4 S1R5 ×3 (not blind; P5-2).

**≥ 3 per decision-critical question: met** (unchanged reading). FIX5 is a lab attempt, not a conclusion, so it needs no refuter.

**3.4 Requirements.** 97/97 in 25. Every easily-missed ID is in its named home.

**3.5 Question bank.** 335/335, one status each in the status column. Ten rows mention a second status word only in the "Remaining" column, for example Q300 "partial | founder-decision". That is allowed. Seven `blocked: founder-decision` IDs; **Q288 is still not in 26** (P4-6).

**3.6 Licence matrix.** 282 rows, all sourced. It covers the rev-4 decision of record and the Secure Boot chain (pass 5, 3.6). The U-SB kit adds dracut on Ubuntu, which pass 5 judged to be inside the Ubuntu 26.04 aggregate row. No new gap.

**3.7 PDF.** 108 pages, built 10:41:55, 17 minutes before FIX5's last write to 01. Chapter 04 §"What changes the result" says Ubuntu "gets its own Secure Boot test in a virtual machine before week 4". It does not say that the test was attempted and BLOCKED, or that it moved to D1. The P5-6 defects are all still there: "Both of the above", "before either is known", "Three single judgements", and the missing "U-SB passes" and U-SB + W2-HW-3 rows. Chapter 15's "Decision map" entry still says "two pending answers". Chapter 11's G6 row lists only Canonical and W2-HW-3. See P6-5.

**3.8 Public-repo hygiene.**

*Working tree (`research-output/`, PDF text included):*
- **Account name:** 0 hits.
- **`/Users/`:** only false positives: the Jellyfin `/Users/{id}` path, the masked `/Users/<…>` rule in 30, and the sed mask in two `trim-logs.sh` files, one of them the new U-SB copy.
- **`.ts.net` / tailnet names:** 0. **RFC1918/CGNAT:** 0.
- **E-mail-shaped strings:** unchanged public or project addresses and systemd unit names.
- **Credential patterns:**
  - Olares's upstream Authelia default (`adminpassword`, quoted as a finding) and two upstream doc placeholders.
  - The public password of a malware sample archive, in a Snyk report.
  - C-TD-flagged-033.
  - None of them is a OneMind secret.
- **`env-probe.log`:** no host paths, addresses or names.
- **gitleaks:** `gitleaks dir` from the repo root: no leaks. Run from inside `research-output/` it reports 10 hits, all on the allowlisted FP-6/6b (public Mender key fingerprint) and on `systemd-measure`/`ukify` man-page key filenames. The allowlist uses repo-root paths, so the scan must be run from the root (hygiene-log l. 72 says so implicitly). `gitleaks git` on `origin/main..HEAD`: no leaks.
- **Relative `work/.lab/…` lab paths:** in W4/W5 refuter files, `k3s-footprint-restore/README.md` and `sources/W18.md`. They hold no username or home path and are not raised.
- **Host folder layout:** still in `critic/pass-2.md` l. 48 and `critic/pass-3.md` l. 61 and 114 (P4-11).

*History and `main`:*
- `414d60a`: account name in 17 files, host layout in 16.
- `ee98bc7` and `7836316`: host layout in 11 and 13 files.
- Z-28 (26 l. 209–212) still names only `414d60a` (P4-9).
- `origin/main:research/platform/iiot-landscape-and-requirements.md` l. 441 still holds `/Users/<founder alias>/…` paths (P4-10).

---

## Part 4. Earlier gaps: closed or open

| Gap | Status | Evidence |
|---|---|---|
| **P5-1** decision rests on an untested Ubuntu cell; U-SB runnable now | **Closed as far as this environment allows; residue to founder** | `lab/ubuntu-secureboot/` was pre-registered (15:51:12Z, hashed) and attempted, and is BLOCKED because the Ubuntu archive does not resolve [C-FIX5-001…004]. 01 R4-16, S1-12 and (h); `scorecard-weights.md` l. 206; 20 D1; 22 LT-VM-20. **Residue:** run LT-VM-20 on a networked machine (D1, 2026-11-16). See P6-3 for one more attempt worth making here |
| **P5-2** FIX4 refuters not blind | **Open** | No new refuter files |
| **P5-3** LT-VM-20 criteria differ from the map | **Partly closed** | Closed: `PREREGISTRATION.md` row and the spike README §4 (frozen) use the (h) wording. Open: 22 LT-VM-20 (l. 509) and 20 l. 413 still say "any difference → a rule-6 re-score **request** … goes to the DEC owner", without the two-run or layout-change conditions |
| **P5-4** FIX4 not synced to 24, 30, 26 §H, 23 RR-33 | **Open** | 30 l. 597 is unchanged; 24, 26 and 23 have no U-SB, FIX4 or FIX5 sync (26 U-SB hits: 0) |
| **P5-5** SOURCES.md behind the ledgers | **Open (worse)** | SOURCES.md (10:14) was compiled from 2,875 rows; the ledgers now hold 2,894. 0 `C-FIX4-*` / `C-FIX5-*` entries. 25 l. 80 says "112 ARCHIVE-GAP"; SOURCES.md says 114 |
| **P5-6** PDF §4.4 decision table ambiguous | **Open** | `report/chapters/04-linux-distributions.md` l. 64–77 unchanged |
| **P5-7** six decision-grade ARCHIVE-GAP sources cited in 01 | **Open** | All six are still in SOURCES.md §ARCHIVE-GAP (C-DEC-006 is row 1) |
| **P4-3** REF4 claim IDs reused | **Open** | 01 still has 14 "not ledgered" notes; `DC-E10-technical.md` and `DC-11-technical.md` are unchanged |
| **P4-4** exception list incomplete | **Open** | 52 of 127 (same list as pass 5) |
| **P4-5** stale PDF status | **Open** | 00 l. 4 and l. 88; README l. 42; REVIEW-CHECKLIST l. 18; 25 l. 262 and l. 435 (101 pages / rev. 3) |
| **P4-6** Q288 not in 26 | **Open** | 0 occurrences |
| **P4-7** unqualified Debian lines in 01 | **Open** | l. 95 "snapshot-pinned Debian", l. 102 "Debian stock", l. 1015 "Final net (revision 3) … D2 (Debian core)" |
| **P4-8** G1 COND cost | **Partly closed** (unchanged) | Provisional bracket; the decisive figure comes from Z-01 |
| **P4-9** Z-28 scoped to `414d60a` only | **Open** | 26 l. 210 |
| **P4-10** `/Users/<alias>` path on `main` | **Open** (founder-authored file) | Unchanged |
| **P4-11** critic files quote the host layout | **Open** | pass-2 l. 48; pass-3 l. 61 and 114 |
| P3-4 residual: C-W19-047…049 typed PRIMARY | **Open** | `claims/W19.csv`: PRIMARY / partial |
| N1/N2 personal data in history | **Open (founder)** | Z-28 |
| N11 lab versions files | **Open (S4)** | Still none in `rauc/`, `secureboot-rauc/`, `secureboot-1152/` and `w19-sysext/`. The new `ubuntu-secureboot/` also has none; its build-VM tool versions are only in `env-probe.log` |
| N12 KubeCon NA 2026 days 3–4 | **Open (date)** | Cannot close before 2026-11-12; C-W4-039/040 recheck by 2026-12-10 |

**Tally:**
- **Pass 5's 7 gaps:** 1 closed as far as the environment allows (P5-1), 1 partly closed (P5-3), 5 open (P5-2, P5-4, P5-5, P5-6, P5-7).
- **Pass 4's gaps:** P4-1 and P4-2 stay closed, P4-8 stays partly closed, 8 stay open.
- **Carried items still open:** P3-4, N1/N2, N11 and N12.

---

## Part 5. New gaps not raised by passes 1–5

| # | Sev | Gap | File(s) | What would close it | Agent can fix? |
|---|---|---|---|---|---|
| **P6-1** | **S3** | **The 180-day gates never act on U-SB.** U-SB is the only event in the pre-registered S1 map that needs no hardware and no vendor, and it is now scheduled for D1. Yet: (a) **G1** (20 l. 309) lists LT-VM-20 as an input, but its pass and fail columns read S1 only from LT-PI5-02 and Z-01. Nothing says "LT-VM-20 fails, or passes only after a layout change → D·C3 = 3 → **C (bootc)**", or that U-SB + W2-HW-3 → **A**. (b) The **G6 base-lock rule** (l. 314) lists Z-01 granted → Ubuntu, W2-HW-3 failed → Debian, and Z-01 refused → bootc, but not U-SB failed → bootc. A founder following the gate table would lock Ubuntu after a failed U-SB. 21 l. 62 and PDF ch. 11 repeat the G6 list without U-SB. This is a different location from P5-4: the gate table, not 23, 24, 26 or 30. | `20` §G1 and §G6 rows; `21` l. 62; `report/chapters/11-plan-roadmap.md` | Add the U-SB rows of 01 (h) l. 375–378 verbatim to G1's outcome columns and to the G6 lock rule | **Yes** |
| **P6-2** | **S3** | **26 has no RS-6 entry for the Ubuntu archive block.** §6 requires 26 to list "code or access you needed but couldn't get (RS-6)". The run needed `archive.ubuntu.com` for the one test that could move the base-OS result, and could not reach it [C-FIX5-001, C-FIX5-004]. §D (l. 101), "added in revision 2" (l. 187) and "added in the final pass" (l. 258) have no entry. No Z-item asks Zeus to run LT-VM-20 on D1 or to say whether the block is deliberate. | `26` §D (RS-6) and §H (Z-38) | Add an RS-6 row: what was blocked, why it matters (D·C3, the S1 map), the one-step action (run LT-VM-20 on a networked machine), and its link to Z-38 | **Yes** |
| **P6-3** | S4 | **FIX5's "unreachable from the research environment" contradicts a same-day Ubuntu build here, and nothing reconciles them.** `lab/ubuntu-2604-leg/versions.md` l. 13 records "build day 2026-11-11, archive.ubuntu.com + security.ubuntu.com". `logs/build-u2.log` shows `mmdebstrap amd64 resolute (RAUC_MODE=archive)` at 07:15. So the archive resolved earlier the same day, and the block started mid-run, before FIX4's access note. C-FIX5-001, the README and 01 R4-16 present the block as a property of the environment. None of them mentions this. The host lab workspace kept no Ubuntu rootfs or image from that build, so the cache cannot help (checked read-only). The block may be transient or newly imposed. | `claims/FIX5.csv` C-FIX5-001; `lab/ubuntu-secureboot/README.md` results; `01` R4-16 | Add the same-day build fact and its time to C-FIX5-001 and the README. Re-run `env-probe` once before the final commit: if the names resolve normally, run U-SB under its frozen rule (this reopens P5-1); if not, keep BLOCKED. Never bypass | **Partly**: the note, yes. Running U-SB depends on whether the environment allows it |
| **P6-4** | S4 | **The read past the DNS block is disclosed only inside a lab README.** U-SB README §R.2 item 1: the agent "asked a public resolver from inside the VM for the archive's address and read the 26.04 `Release` file once by IP" before it recognised a deliberate block. It is honestly disclosed and not cited. But it went around an access control of this environment, in the spirit of rule 5 ("never bypass … mark the source UNVERIFIED (blocked)"). It is not in `hygiene-log.md`, `00` §6 or 26, so a founder reading the summary would not see it. | `evidence/hygiene-log.md`; `00` limitations; `lab/ubuntu-secureboot/README.md` §R.2 | Log it as a hygiene / process deviation in `hygiene-log.md` and one line in 00 §6, with "nothing used as evidence". Whether that is acceptable is for Zeus to judge; logging it is not | **Yes** (the logging) |
| **P6-5** | S4 | **The PDF and the founder's reading aids predate FIX5.** The PDF was built 10:41:55; 01 was last written 10:58. PDF §4.4 says U-SB runs "before week 4". It does not say the test was attempted and BLOCKED, that the kit is frozen and ready, or that it moved to D1. `README.md` and `REVIEW-CHECKLIST.md` do not mention U-SB / LT-VM-20 at all, so the checklist has no approval box for the event most likely to flip the base. This is separate from P4-5 (the "101 pages / rev. 3" labels) and P5-6 (the abridged table). | `report/chapters/04`, `11`, `15`; PDF; `README.md`; `REVIEW-CHECKLIST.md` | After P6-1, P5-4 and P5-6: add one FIX5 sentence to ch. 04 and a U-SB row to ch. 11's G1/G6, rebuild the PDF, and add a U-SB line plus checkbox to REVIEW-CHECKLIST | **Yes** |

---

## Part 6. Founder-only and date-bound items (for the orchestrator's final list)

| Item | Why the agent cannot close it | `fixable_by_agent` |
|---|---|---|
| **LT-VM-20 / U-SB run** (residue of P5-1) | Needs a machine that reaches `archive.ubuntu.com`. This environment blocks it and must not be bypassed. VM only, no hardware: about 1.5–2 h, 20 D1 (2026-11-16). Unless P6-3's re-probe finds the archive reachable | false |
| **Z-38, Z-39, Z-40, Z-01** | Base-OS acceptance or override, COND-as-FAIL reading, written scoring rules, Canonical/counsel. P4-8's decisive figure comes from Z-01 | false |
| **Z-28 / N1 / N2 (widened per P4-9)** | Removing `414d60a`, `ee98bc7` and `7836316` content needs a history rewrite and a force-push | false |
| **P4-10** | Founder-authored file on `main` | false (the edit needs Zeus's approval) |
| **P6-4 acceptability** | Whether the disclosed IP read is acceptable | false (logging it is agent-fixable) |
| **P5-2 blind refuters** | Needs separate blind sub-agents | true |
| **Hardware** | W2-HW-3 (Pi 5 bootc, before G1); F-PI5; Jetson; RT latency; real power-cut and firmware tests in 22 | false |
| **N12** | KubeCon NA 2026 days 3–4 re-check cannot run before 2026-11-12 | false (date) |

---

**Loop-until-dry status:**
- **New gaps per pass:** pass 1 added 24, pass 2 added 15, pass 3 added 13, pass 4 added 11, pass 5 added 7.
- **Pass 6** closes P5-1 as far as the environment allows, partly closes P5-3, and leaves P5-2 and P5-4…P5-7 open.
- **Pass 6 adds 5 new gaps:** 0 S1, 0 S2, 2 S3 (P6-1, P6-2) and 3 S4 (P6-3, P6-4, P6-5). All five come from FIX5's own changes, and the trend is falling.

The run is **not dry**: this pass found new gaps, and the rule needs two consecutive passes with none. The cheapest next steps:
1. **One sync pass.** Fixes P6-1, P6-2, P6-5, P5-3 residue, P5-4, P4-5, P4-6, P4-7, then the PDF rebuild. All are edits to existing files.
2. **One `env-probe` re-run** (P6-3).
