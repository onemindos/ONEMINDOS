# Completeness critic, pass 8 (final)

**Date:** 2026-11-11 · **Scope:** RESEARCH-MISSION.md §4, §6, §7 and §9, checked against everything in `research-output/`. Inputs: `evidence/critic/pass-3.md` … `pass-7.md`.

**What changed since pass 7** (pass 7 was written at 11:14 local): the FIX7, DEC5 (`01` rev. 4.1), G4U, ARCH5 and SYNC5-a/b/c passes. They touched 00, 01, 07–09, 16, 20–28, 30, `decision-critical.md`, `scorecard-rev3.md`, `scorecard-weights.md`, `cit4-mapping.md`, `hygiene-log.md`, `PREREGISTRATION.md`, five lab `versions.md` files, SOURCES.md, README, REVIEW-CHECKLIST and the report sources. The PDF was rebuilt at 11:57 (111 pages). New files:
- adversarial: `G4-ubuntu-rev5.md` and `S1R5-blind-{technical,security,longevity}.md`;
- ledgers: `ARCH5`, `DEC5`, `FIX7`, `G4U`, `REF5-S1-*` and `SYNC5-a/b`.

**Not counted** (the orchestrator handles these): uncommitted files, the master `evidence/claims.csv` re-merge, the gitleaks run at commit, and PR #1's draft state.

**Method:** the same scripted checks as pass 7.
- **Claim IDs.** Resolved against all 2,986 per-tag ledger rows.
- **Exception list.** 01's non-PRIMARY or non-verified IDs checked against `cit4-mapping.md`.
- **Coverage.** The 97 requirement IDs against 25, the 335 bank IDs against 24, and the founder-decision IDs against 26.
- **PDF.** `pdftotext`, then the U-SB, G4 and stale-stack wording; and the PDF's mtime against its sources.
- **Hygiene.** RFC1918/CGNAT, `.ts.net`, host folder layout and home paths; `gitleaks dir research-output` (no leaks, 28.2 MB).
- **Gaps.** Each pass 3–7 gap re-read at its cited line.

**The critic fixed nothing.**

**Bottom line.**
- **22 of the 29 items** still open after pass 7 are now **closed**. **7 stay open.** None is S1, and only one is S2: P4-8, whose residue needs Z-01, so the founder holds it.
- **New S1/S2 gaps: none.** By the S1/S2 standard the loop is **dry**. Every remaining item needs the founder, a date, a network or hardware the lab lacks, or is a deferred S3/S4 sync. The authoritative list is [`REMAINING-WORK.md`](REMAINING-WORK.md).

---

## Part 1. Earlier gaps: closed or open

| Gap | Sev | Status | Evidence (one line) |
|---|---|---|---|
| P3-4 residue: C-W19-047…049 typed PRIMARY | S3 | **Closed** | `claims/W19.csv`: all three are now `DERIVED`, medium, partial |
| P4-3 REF4 IDs reused | S3 | **Closed** | 01 l. 5: re-ledgered as C-DEC5-001…028. The "colliding REF4" text now appears only in that changelog sentence |
| P4-4 exception list incomplete | S3 | **Open (1-ID residue)** | `cit4-mapping.md` §8 added. Of 01's 105 exception IDs, 104 are mapped. **C-LAB-secureboot-1152-010** (cited at 01 l. 881) is missing |
| P4-5 stale PDF status | S3 | **Closed** | 00 l. 4 and §6: "111 pages, rev. 4.1 build". 25 rev. 3: F-10 → Covered. No "101 pages" or "built from rev. 3" left in 00, README, REVIEW-CHECKLIST or 25 |
| P4-6 Q288 not in 26 | S4 | **Closed** | 26 l. 287 maps Q288 to Z-38, Z-10, Z-40 and Z-41 |
| P4-7 unqualified Debian lines in 01 | S4 | **Closed** | 01 l. 100 (image build) and l. 107 (kernel) name both legs. l. 1056 and 1058 are labelled "kept for the record / historical"; l. 1064 is "Final net (revision 4)" |
| P4-8 G1 COND has no stated cost | S2 | **Open (founder)** | 01 l. 418 gives the only bounded figure (≈ $60 per box Pro for Devices [C-COST-002]). The decisive cost needs Canonical's or counsel's answer (Z-01) |
| P4-9 Z-28 scoped to `414d60a` only | S4 | **Closed** (text) | 26 l. 211–214 name all four pushed commits. The rewrite itself is founder item N1/N2 |
| P4-10 home path with account alias on `main` | S4 | **Open (founder)** | `research/platform/iiot-landscape-and-requirements.md` l. 441 is unchanged; it is a founder-authored file on `main` |
| P4-11 critic files quote the host layout | S4 | **Closed** | 0 hits for the host layout in `evidence/critic/` or anywhere in `research-output/` |
| P5-1 residue: U-SB / LT-VM-20 not run | S2 (residue) | **Open (network)** | The Ubuntu archive is still unresolvable (`ubuntu-secureboot/README.md` R.5: 16:43Z re-probe). The kit is frozen (sha256 `c98a09d1…`). Founder step Z-41 / LT-ACC-01 |
| P5-2 FIX4 refuters not blind | S3 | **Closed** | `S1R5-blind-{technical,security,longevity}.md` each state they did not open 01, the DC file, the scorecards or the critic folders. All three: weakened (01 §5.1.3) |
| P5-3 LT-VM-20 criteria vs map | S3 | **Closed** | `PREREGISTRATION.md` l. 13, 15 and 45: U-SB entry, hashed, with the (h) rows quoted word for word. 22 LT-VM-20 (l. 509) and 20 l. 413 carry the (h) wording |
| P5-4 FIX4/FIX5 not synced to 24, 30, 26 §H, 23 | S4 | **Closed** | "not yet been put to a refuter": 0 hits in 24 and 30. 26 l. 318: Z-38 (a) names U-SB. 23 rev. 2.1: RR-33 names U-SB |
| P5-5 SOURCES.md behind the ledgers | S4 | **Closed** | SOURCES.md l. 3 says "2986 claim rows", which equals the per-tag ledger count. The FIX7, G4U, ARCH5 and DEC5 tags are present (25 hits) |
| P5-6 PDF §4.4 decision table | S4 | **Closed** | `report/chapters/04` l. 78–96: the three pending events are named, the U-SB pass, fail and combined rows are added, and the text says "at least seven other readings (V1–V6, V8)" |
| P5-7 six decision-grade ARCHIVE-GAP sources | S4 | **Open (network residue)** | `sources/ARCH5.md`: 5 of 6 closed with saved text and sha256. **C-DEC-006** (Launchpad) is unreachable here; founder step F-1 |
| P6-1 gates never act on U-SB | S3 | **Closed** | 20 G1 l. 309: "BLOCKED or not run at G1 → no map event". G6 l. 314 has every U-SB branch. 21 l. 62 and EX-Y1-10 name U-SB |
| P6-2 no RS-6 row for the Ubuntu archive block | S4 | **Closed** | 26 l. 378 (§D RS-6 row) and §I Z-41; 22 LT-ACC-01 |
| P6-3 "unreachable" vs same-day build | S3 | **Closed** | `ubuntu-secureboot/README.md` §R.5 gives the timeline: last archive use at 07:59Z, block before 15:56Z [C-SYNC5-b-002] |
| P6-4 IP read disclosed only in the lab README | S3 | **Closed** (logging) | `hygiene-log.md` §7 D-1, 00 §6 l. 95, 26 Z-41 l. 371. Whether the read was acceptable is founder item Z-41 |
| P6-5 PDF and reading aids predate FIX5 | S4 | **Closed** | PDF 11:57, 111 pages: U-SB 16×, BLOCKED 1×, the G4-for-Ubuntu paragraph present, 0 "Debian 13 core". README and REVIEW-CHECKLIST mention U-SB |
| N1/N2 personal data in pushed history | S1 (hard rule; founder) | **Open (founder)** | Needs a history rewrite and a force-push (Z-28). The brief forbids force-pushing without the founder |
| N11 lab versions files | S4 | **Closed** | `versions.md` now exists in `rauc/`, `secureboot-rauc/`, `secureboot-1152/`, `w19-sysext/` and `ubuntu-secureboot/` |
| N12 KubeCon NA 2026 days 3–4 | S4 | **Open (date)** | Cannot be re-checked before 2026-11-12 |
| P7-1 superseded rows cited as live support | S3 | **Closed** | 28 l. 12 cites C-CIT4-003 ("not on Jetson"). `scorecard-rev3.md` l. 3 records the swap. 23 RR-17 cites C-CIT4-016. In 01, the two superseded IDs (C-W18-027, C-W7-005) appear only in l. 1244's "superseded by" note |
| P7-2 G4 not assessed for the decision of record | S2 | **Closed** | 09 l. 44–63: Ubuntu 26.04 + RAUC column with a source per sub-check [C-FIX7-001…006]. `G4-ubuntu-rev5.md` verifies it (COND, no FAIL) [C-G4U-001…012]. 01 l. 12 re-cites D·G4. DC-02 flip condition restated (l. 71). DC-04 has a rev-4 sync for Pro to May 2036 |
| P7-3 07/08/09/16/27 not synced | S3 | **Closed** | 07, 08 and 09 headers: "final for this run; refuters have run", with a rev-4.1 sync note. 09 l. 225 and 238: "base per `01` §1". 16 and 27 declare rev. 4.1 and name the move |
| P7-4 stale self-notes in 00 | S4 | **Closed** | Neither the l. 87 clause nor the l. 99 "28 and 29 headers say draft" text is still in 00 |

**Tally:** 29 items were open after pass 7. **22 are closed**: P3-4, P4-3, P4-5, P4-6, P4-7, P4-9, P4-11, P5-2, P5-3, P5-4, P5-5, P5-6, P6-1, P6-2, P6-3, P6-4, P6-5, N11, P7-1, P7-2, P7-3 and P7-4. **7 are open**:
- **Founder:** P4-8, P4-10, N1/N2.
- **Network:** the P5-1 residue and the P5-7 residue.
- **Date:** N12.
- **Agent, 1 ID:** the P4-4 residue.

Nothing regressed.

## Part 2. §9 Definition of done

| §9 item | Verdict | Evidence |
|---|---|---|
| Tier A to the teardown minimum, scorecard protocol, adversarial protocol, VM lab | **Met, with founder-runnable equivalents** | The four Tier A teardowns are unchanged since pass 7 (all seven minimum sections). 19 spikes: 18 executed, and U-SB is BLOCKED with founder test LT-VM-20 (§7 allows "founder-runnable equivalents"). The scorecard protocol is met (pass 7 §3.1; rev. 4.1 moves no score). Adversarial: ≥ 3 refuters per DC, and the S1 result now has three blind refuters (P5-2 closed). G4 has evidence for D (P7-2 closed) |
| Every workstream W1–W17 has its file, at its tier's depth | **Met** | All files exist. 07, 08 and 09 are final and synced; 16 and 27 declare rev. 4.1 |
| Every bank question has a status; DCs fully evidenced | **Met, with founder/network residue** | 335/335 bank IDs in 24. All 9 `blocked: founder-decision` IDs appear in 26. DC-02 and DC-04 now cover the decision of record. What remains is the evidence only the founder or a network can supply (U-SB, Z-01) |
| All 97 requirement IDs traced | **Met** | 97/97 in 25, 0 missing. F-10 is Covered |
| ADR-001 confirmed / changed / overturned | **Met** | 01 §7 "Final net (revision 4)": D2 changed (conditional) to Ubuntu 26.04; D1, D3, D4 and D5 confirmed |
| 20 (gates) and 21 (exit criteria) complete | **Met** | 20 G1 and G6 now act on U-SB, including its BLOCKED state. 21 has EX-Y1-10 |
| Every claim used in 01 resolves to a primary-source row | **Met with listed exceptions** (master merge excluded) | 704 distinct IDs, 0 unresolved, 0 overdue `recheck_by`. 105 exception IDs, 104 listed in `cit4-mapping.md` (P4-4 residue: 1) |
| `license-matrix.csv` covers every recommended component | **Met** | Unchanged since pass 7 (282 rows; every 01 §1 component present) |
| 28, 29, 30 complete | **Met** | 30's stale line is gone (P5-4 closed). 28 cites C-CIT4-003 |
| PDF built, standalone, visual, covers every topic | **Met** | 111 pages, rev. 4.1 build, 11:57. No report chapter or 01 edit is newer than the PDF. Only reading aids are newer (00, 25, README, REVIEW-CHECKLIST, SOURCES, `report/README.md`), and they do not feed the PDF text |
| PR marked ready for review | Not met; **not counted** | Draft. It is blocked on Z-28 (N1/N2), which only the founder can clear |

**§9 summary:** every countable item is met. Each one that is met "with residue" is held by the founder, by the network, or by a single ID.

## Part 3. New gaps (S1/S2 only)

**None.** Candidates examined and rejected:
- **D·G4's (a) and (e) rest partly on Repology (SECONDARY) for 26.04 package presence** [C-FIX7-004, C-FIX7-005]. This is disclosed (09 l. 63; `G4-ubuntu-rev5.md` §6), has a founder step, and no sub-check would FAIL if the packages were missing, because OneMind can build `.deb`s. It is a known residue, not a new gap; it is listed in REMAINING-WORK (c).
- **The pre-existing follow-ups at 01 l. 1244** that are still open:
  - 07 X-2's literal `--tpm2-pcrs=7` (07 l. 384);
  - 07's EN 304 626 correction [C-STEEL-cra-nb-020], which is not in 07, so 07 l. 401's trigger "drops the auto-update default" overstates the draft;
  - 08 FF-2 does not cite [C-STEEL-jb-002];
  - 05's S1/S3 Talos sentence, which I did not find.

  01 itself already carries the correct text for each (01 §4.3, l. 643, §4.1), so no decision or P0 conclusion moves. These are S3/S4, so they are not new gaps. They are listed in REMAINING-WORK (d) because they are still open.
- **Hygiene.**
  - Clean: `.ts.net` appears only as a bare pattern (15×, no hostname); 0 RFC1918/CGNAT hits outside critic text; 0 host-layout or home-path hits in `research-output/`; gitleaks found no leaks.
  - One stray file: `evidence/sources/ARCH5/rpi-news-price-rises-16gb.txt.tmp`, 299 bytes. It holds only the header, not the comments, it is not in SHA256SUMS, and it is S4. The orchestrator should drop it at commit.

## Part 4. Loop-until-dry status

- **New gaps per pass:** 24 → 15 → 13 → 11 → 7 → 5 → 4 → **0** (pass 8: 0 S1, 0 S2; S3/S4 not raised, by instruction).
- **Dry at the S1/S2 level.**
  - **Agent-fixable items still open:** the P4-4 one-ID residue and the 01 l. 1244 follow-ups, all S3/S4.
  - **Items held outside the agent:** the founder (Z-01, Z-28, Z-38–Z-41, P4-10), a networked machine (U-SB, C-DEC-006, the 26.04 archive re-check), real hardware (22), and one date (N12, after 2026-11-12).
- **One sync the orchestrator should make with this pass:** 00 §6 l. 94 still ends "Critic pass 7 still found four new gaps, so the loop is not dry". After pass 8 it should say the loop is dry at S1/S2, with the remaining work in `evidence/critic/REMAINING-WORK.md`.
