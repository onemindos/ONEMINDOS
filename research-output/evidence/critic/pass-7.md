# Completeness critic, pass 7

**Date:** 2026-11-11 · **Scope:** RESEARCH-MISSION.md §4, §6, §7 and §9, checked against everything in `research-output/`. Inputs: `evidence/critic/pass-3.md` … `pass-6.md`.

**What changed since pass 6:** nothing. No file under `research-output/` other than `critic/pass-6.md` itself was written after pass 6 (11:05:53 local). This pass re-ran the mandated checks independently on the same tree, then looked for gaps that passes 1–6 did not raise.

**Not counted as gaps** (the orchestrator handles these at commit time): uncommitted files; the master `evidence/claims.csv` re-merge (2,704 rows against 2,894 in the 107 per-tag ledgers); the gitleaks run at commit; PR #1 still being a draft.

**Method:** scripted checks plus targeted reading.
- **Claim IDs.** Resolved against the per-tag ledgers in 00, 01, 03–07, 20–30, `decision-critical.md`, `scorecard-weights.md` and `report/chapters/*.md`. New in this pass: 02-competitors, 08–17, every lab README, every adversarial file, `README.md`, `REVIEW-CHECKLIST.md`, `license-matrix.md`, `lifecycle-cost-2036.md`, `scorecard-rev3.md` and `qbank/*.md`.
- **Ledger fields.** Header identity, empty `source_url` and `accessed_date`, overdue `recheck_by` dates, and status values. Every `superseded` row was traced to where it is cited (new in this pass).
- **S1 verdict.** Recomputed from the 01 rev-4 card under the frozen §6 rescaling and the top-two tie-break.
- **Refuters.** Counted per DC from `adversarial/` and from 01 §5.9.2.
- **Requirements and bank.** The 97 table IDs in `docs/REQUIREMENTS.md` checked against 25. The 335 bank IDs in `context/05-research-questions.md` checked against 24. `blocked: founder-decision` IDs checked against 26.
- **Licence matrix.** Coverage of 01 §1 and LICENSE permalink pinning.
- **PDF.** `pdfinfo` and `pdftotext`, then the rev-4 figures and stale-stack wording.
- **Hygiene.** Account name, host folder layout, `/Users/`, tailnet names, RFC1918/CGNAT, e-mail and credential patterns. `gitleaks dir .` from the repo root, and `gitleaks git` on `origin/main..HEAD` (8.30.1).
- **Header sync.** Each workstream file's declared 01 revision (new in this pass).
- **DNS probe.** One read-only lookup of the Ubuntu archive names, for P6-3.

**The critic fixed nothing.**

**Severity:** **S1** blocks §9 or breaks a hard rule · **S2** weakens a P0 conclusion or a decision-critical answer · **S3** a protocol or ledger defect · **S4** hygiene or polish.

**Bottom line.**
- Every pass-6 finding reproduces exactly; nothing was fixed between the passes.
- **Four new gaps, none S1.** The most important is **P7-2**: the must-pass IIoT gate G4 for the decision of record (Ubuntu 26.04, D) is cited to a ROS 2 platform-tier claim. That claim covers none of G4's five sub-checks. DC-02, the decision-critical question that owns G4, was never re-run for Ubuntu.
- **P7-3:** the Tier A files 07 and 09 still describe the foundation as "Debian 13 + Rugix" and are still "draft for refuters".
- **P7-1:** three citations rest on ledger rows CIT4 marked `superseded`.
- **P7-4:** two stale self-notes in 00.

The run is **not dry**.

---

## Part 1. §9 Definition of done

| §9 item | Verdict | Evidence |
|---|---|---|
| Tier A to the teardown minimum, scorecard protocol, adversarial protocol, VM lab | **Not met** (narrowly) | The four Tier A teardowns (HAOS, umbrelOS, Olares, VillageOS) each have all seven minimum sections and three Mermaid diagrams. There are 19 spikes, 18 executed; U-SB is BLOCKED and turned into founder test LT-VM-20. The §7 item-5 restore (SQLite **and** etcd, fresh VM) ran in `k3s-footprint-restore`. **Scorecard protocol: met** (Part 3.1). **Adversarial protocol:** ≥ 3 lenses per DC, but the rev-4 S1 refuters are not blind (P5-2). The new P7-2 means the G4 gate cell for the decision of record has no G4 evidence. Loop-until-dry is not reached |
| Every workstream W1–W17 has its file at its tier's depth | **Met for depth; sync defect** | All files exist. 07, 08 and 09 are still "draft for refuters", and 16 and 27 declare revision 2 (**P7-3**) |
| Every bank question has a status; DCs fully evidenced | **Status met; DCs not fully evidenced** | 335/335 bank IDs present, one status each. P4-3 (colliding REF4 IDs) is still open, and DC-02 does not cover the decision of record (**P7-2**) |
| All 97 requirement IDs traced | **Met** | 97/97 in 25; none missing, none extra. F-10's row is stale (P4-5) |
| ADR-001 explicitly confirmed / changed / overturned | **Met** | 01 §7: D2 changed (rev. 4, conditional) to Ubuntu 26.04. DC-04's answer still says "D2 confirmed" (P7-2) |
| 20 (gates) and 21 (exit criteria) complete | **Met, with a gate defect** | 20 has A01–A24 (all 24 linked), 45 h/week, the cut list and day-level weeks 1–2. 21 has, for every era, exit criteria, leading indicators and scenario triggers. The G1 and G6 rows have no U-SB branch (P6-1, open) |
| Every claim used in 01 resolves to a primary-source row | **Not met** (master merge excluded) | 804 distinct IDs, **0 unresolved**. 107 are not PRIMARY and 30 are not `verified`. 52 of the 127 exception IDs are still not in `cit4-mapping.md` (P4-4) |
| `license-matrix.csv` covers every recommended component | **Met** | 282 rows; none lacks a SPDX entry or permalink. Every 01 §1 component has a row. The 19 rows without a pinned LICENSE file are policy or EULA pages, or are labelled UNVERIFIED (blocked) |
| 28, 29, 30 complete | **Met** | 30 l. 597 is still stale (P5-4) |
| PDF built, standalone, visual, covers every topic | **Met for coverage; stale** | 108 pages, built 10:41:55. The S1 figures match 01 rev. 4 (Ubuntu 65 · bootc 64 · Debian 63; 6–4; 11 of 14). 0 U-SB / BLOCKED mentions (P6-5); P4-5 and P5-6 are open |
| PR marked ready for review | Not met; **not counted** | Draft; blocked on Z-28 |

## Part 2. §6 deliverables

All §6 files exist; none changed since pass 6. Pass 6 Part 2 stands. This pass adds the following:

| Deliverable | Note |
|---|---|
| 00 | l. 87: "`24`'s S1 item should become `blocked: founder-decision`". 24 l. 94 already has that status. l. 99: "07–09, 28 and 29 headers say 'draft'". 28 declares rev. 4 and 29 says "draft complete", so the line is partly wrong, and no critic has tracked the real residue (**P7-3**, **P7-4**) |
| 07, 08, 09 | Header "Status: draft for refuters", dated 2026-11-10. 07 and 09's founder boxes frame the stack as Debian 13 + Rugix (P7-3) |
| 16, 27 | l. 6: "Consistent with `01` revision 2". 27 adds "(Debian 13 core, …)" (P7-3) |
| 26 | Has REQUIREMENTS open questions 2–5, the four recurring Blueprint questions and an RS-6 section (§D). Q288 is missing (P4-6) and there is no U-SB RS-6 row (P6-2) |
| `outreach-drafts.md` | O-1 (Canonical) asks the Z-01 redistribution question that G1 depends on. No gap |
| 22 | LT-VM-16 (LAB-W8-4) now runs "on the core legs **and** EL10 bootc", so the FDO founder test does cover the Ubuntu leg. The desk analysis behind G4 does not (P7-2) |

## Part 3. Mandated checks in detail

**3.1 S1 verdict against the frozen protocol (`evidence/scorecard-weights.md`).**
- **Card.** Recomputed from 01 §3.1.6 (d): D 65.0 · C 64.0 · A 63.0.
- **Sensitivity.** 14 runs under the frozen §6 rescaling. Raw winners: D 10, C 3, A 1. With the top-two rule and the logged pairs ({D,C} → D, {A,D} → A, {A,C} → C) applied inside the 3.0 band: **D 11, A 2, C 1**. This matches 01 and the §8 rev-4 row.
- **U-SB failure.** Recomputed: C 64 · A 63 · D 62 → C. This matches the FIX4 row.
- **Change log.** Rows l. 204–206 record every rev-4, FIX4 and FIX5 change before use, with "no weight or anchor change".
- **Gates.** A, C and D have no FAIL, and COND results are ranked. But D·G4 = COND rests on C-W2-028 alone, a ROS 2 platform-tier row (P7-2). "One citation per cell" is met in form, not in substance.

**Verdict: the S1 result follows the frozen protocol as written.** The weaknesses are evidential: D·C3 is `doc-only` (P5-1 residue) and D·G4 is uncited for G4's content (P7-2).

**3.2 Claim IDs.**
- **Unresolved IDs.** 0 in every file pass 6 checked (counts identical to pass 6). The wider scan found 19 apparent misses:
  - 18 come from range shorthand in 13 (`C-W12-001…077`, `C-W12-101…170`) spanning numbers W12 never issued (032–039, 051–059, 069, 078–100);
  - 1 is the spike-name tag `[C-LAB-rauc-1152]` in `lab/aarch64-gate/README.md` l. 54.

  Neither is a real unresolved claim.
- **Ledger fields.** 2,894 rows, 0 duplicates, identical headers. 0 rows lack `source_url` or `accessed_date`. 0 `recheck_by` dates are past.
- **Superseded rows.** Five rows are marked `superseded`; two are still cited as live support (**P7-1**).

**3.3 Refuters.**
- **Dedicated lenses.** DC-03, 04, 07, 08, 09, 12–15, 17–20 and 22–24 have three dedicated files each (DC-08 has six), as does E10.
- **Borrowed lenses.** DC-01, 02, 05, 06, 10, 11 and 21 have two dedicated round-4 files plus their earlier W-series P0 refuters (01 §5.9.2). DC-16 uses the W19 set (25 refuters).
- **S1.** S1R4 ×3, STEEL4 and FIX4 S1R5 ×3.

**≥ 3 per decision-critical question: met.** No new adversarial file since pass 6 (155 files).

**3.4 Requirements.** 97/97 rows in 25.

**3.5 Question bank.**
- **Coverage.** 335 IDs in `context/05`, all present in 24, each with one status.
- **Founder-decision IDs.** Seven carry `blocked: founder-decision` as their status, and Q300 has it in its "Remaining" column. **Q288 is still absent from 26** (P4-6).

**3.6 Licence matrix.**
- **Size.** 282 rows; every row has a SPDX entry and a permalink.
- **Coverage.** Components spot-checked against 01 §1 and §4: Ubuntu 26.04 core, Ubuntu Pro, RAUC, k3s, kine, etcd, SQLite, restic, Kopia, local-path, Longhorn, Traefik, shim, sbsigntools, systemd, cryptsetup, tpm2, cosign, OpenBao, go-fdo, Mosquitto, NATS, the L4T BSP, CUDA, mmdebstrap and containerd/runc. All are present.
- **Not separate rows.** dracut and ukify sit under the Ubuntu and systemd rows, as pass 5 judged. rustic, the CI read-test option, is not recommended over Kopia, which has a row.

No new gap.

**3.7 PDF.** 108 pages, built 10:41:55.
- **Consistent with 01 rev. 4:** the S1 figures, the 6–4 tie-break, 11 of 14 runs, the U-SB-fails row (bootc 64 · Debian 63 · Ubuntu 62 → bootc), and the RAUC 5–3 recount.
- **No stale stack:** no "Debian 13 core" wording and no Rugix-as-engine wording. Rugix appears only as history, a lab, or the alternative.
- **Stale:** the FIX5 status (P6-5). P4-5 and P5-6 are open.

**3.8 Public-repo hygiene.**
- **Account name:** 0 hits in the working tree and PDF text.
- **Host folder layout:** only in `critic/pass-2.md` l. 48 and `critic/pass-3.md` l. 61 and 114 (P4-11). It also appears in `hygiene-log.md` l. 17, as a grep pattern only.
- **`/Users/`:** only the known false positives (FP-11, the Jellyfin `/Users/` code path, two `trim-logs.sh` masks).
- **Tailnet names:** 0 hostnames. **RFC1918/CGNAT:** 0.
- **E-mail-shaped strings:** systemd unit names, `git@github.com`, a public vendor security address and a public mailing list.
- **Credential patterns:** upstream documentation placeholders only:
  - the Olares Authelia default;
  - ntfy and Clearpath sample configs;
  - the SimpleFIN demo token, which decodes to a public demo URL;
  - the Snyk malware-archive password;
  - C-TD-flagged-033.
- **gitleaks:** `gitleaks dir .` from the repo root found no leaks (28.8 MB). `gitleaks git` on `origin/main..HEAD` found no leaks.
- **History:** unchanged since pass 6 (P4-9, N1/N2).

**3.9 DNS re-probe (P6-3).** At 2026-11-11T16:12Z, from the host: `archive.ubuntu.com`, `security.ubuntu.com` and `ubuntu.com` return no answer; `deb.debian.org` resolves. The block persists, so U-SB stays BLOCKED, and nothing was bypassed. The documentation half of P6-3 (recording the same-day 07:15 Ubuntu build) is still open.

---

## Part 4. Earlier gaps: closed or open

| Gap | Status | Evidence |
|---|---|---|
| P3-1, P3-2, P3-3, P3-5, P3-6, P3-7, P3-9, P3-11, P3-12, P3-13 | **Closed** (pass 4), still closed | Re-checks in Part 3 agree |
| P3-8 | Closed except (b), which is folded into P4-5 | — |
| P3-10 | Closed in the tree; residue is P4-11 and P4-9 | — |
| **P3-4** residual: C-W19-047…049 typed PRIMARY | **Open** | `claims/W19.csv` unchanged |
| P4-1, P4-2 | **Closed**, still closed | — |
| **P4-3** REF4 IDs reused | **Open** | 01 §5.9.2 still says "cited there under colliding REF4 IDs; not ledgered" in 9 rows |
| **P4-4** exception list incomplete | **Open** | 52 of 127 |
| **P4-5** stale PDF status | **Open** | 00 l. 4, 88 and 96; README l. 42; REVIEW-CHECKLIST l. 18; 25 l. 262 and 435 |
| **P4-6** Q288 not in 26 | **Open** | 0 occurrences |
| **P4-7** unqualified Debian lines in 01 | **Open** | l. 95, 102 and 1015 |
| **P4-8** G1 COND cost | **Partly closed** | Decisive figure from Z-01 |
| **P4-9** Z-28 scoped to `414d60a` only | **Open** | 26 l. 210 |
| **P4-10** `/Users/<alias>` path on `main` | **Open** (founder-authored file) | — |
| **P4-11** critic files quote the host layout | **Open** | pass-2 l. 48; pass-3 l. 61 and 114 |
| P5-1 | **Closed as far as this environment allows** | Residue LT-VM-20 (20 D1); still blocked at 16:12Z |
| **P5-2** FIX4 refuters not blind | **Open** | — |
| **P5-3** LT-VM-20 criteria vs map | **Partly closed** | 22 l. 509 and 20 l. 413 unchanged |
| **P5-4** FIX4/FIX5 not synced to 24, 30, 26 §H, 23 | **Open** | 30 l. 597 |
| **P5-5** SOURCES.md behind ledgers | **Open** | 2,875 vs 2,894; 0 FIX4/FIX5 entries |
| **P5-6** PDF §4.4 decision table | **Open** | — |
| **P5-7** six decision-grade ARCHIVE-GAP sources | **Open** | — |
| **P6-1** gates never act on U-SB | **Open** | 20 G1 l. 309, G6 l. 314; 21 l. 62 |
| **P6-2** no RS-6 row for the Ubuntu archive block | **Open** | 26 §D |
| **P6-3** "unreachable" vs same-day build | **Partly answered** | Re-probe: still blocked (3.9). The note on C-FIX5-001, the README and R4-16 is still missing |
| **P6-4** IP read past the DNS block disclosed only in the lab README | **Open** | Not in `hygiene-log.md` or 00 §6 |
| **P6-5** PDF and reading aids predate FIX5 | **Open** | 0 U-SB mentions in the PDF, README or REVIEW-CHECKLIST |
| N1/N2 personal data in history | **Open (founder)** | Z-28 |
| N11 lab versions files | **Open (S4)** | `rauc/`, `secureboot-rauc/`, `secureboot-1152/`, `w19-sysext/` and `ubuntu-secureboot/` still have no versions file |
| N12 KubeCon NA 2026 days 3–4 | **Open (date)** | Cannot close before 2026-11-12 |

**Tally:** none of pass 6's five gaps is closed (P6-3's probe is answered, but its note is not written). Every gap pass 6 listed as open is still open. Nothing regressed.

---

## Part 5. New gaps not raised by passes 1–6

| # | Sev | Gap | File(s) | What would close it | Agent can fix? |
|---|---|---|---|---|---|
| **P7-1** | S3 | **Superseded ledger rows are still cited as live support outside 01.** CIT4 marked C-W18-027 `superseded` by C-CIT4-003, which narrows CUDA-on-Debian-13 to exclude Jetson. It also marked C-REF3-DC-technical-020 `superseded` by C-CIT4-016, which reports branches 590–620 and still no 580 or 570. `cit4-mapping.md` §2.2 and l. 85 say where to swap the IDs. 01 was fixed, but: (a) 28 l. 171, S5 card K1·C7 "NVIDIA lists Debian 13 [C-W18-027]"; (b) `scorecard-rev3.md` l. 169 and 173, the S5 cells and the K5 gate that 01 §3.5 adopts "unchanged" by reference; (c) 23 RR-17 (l. 135) still cites C-REF3-DC-technical-020. No score moves (cit4-mapping: "Cell change: none"), but a reader following the card to its source lands on a row marked superseded. No earlier pass traced `superseded` rows. | `28` l. 171; `evidence/scorecard-rev3.md` l. 169, 173; `23` l. 135 | Swap C-W18-027 → C-CIT4-003 (adding "not on Jetson" to the 28 cell text) and C-REF3-DC-technical-020 → C-CIT4-016 | **Yes** |
| **P7-2** | **S2** | **The must-pass IIoT gate G4 (F-11) was never assessed for the decision of record.** (a) 01 §3.1.1 l. 161 scores D·G4 = COND on **[C-W2-028] alone**. That row says Ubuntu 26.04 is ROS 2 Lyrical Tier 1. It says nothing about G4's five sub-checks: industrial protocols, real time, the IEC 62443 path, zero-touch onboarding and fleet scale. A·G4 and C·G4 cite W8 and 62443 evidence. (b) DC-02, the DC that owns G4, still states its flip condition as "any G4 sub-check FAILs for **Debian + Rugix**" (`decision-critical.md` l. 71). Its rev-4 result has 0 Ubuntu mentions. (c) 09's G4 sub-check table (l. 43) has columns for Debian 13 + Rugix, Fedora, CentOS/RHEL, CIP Core and **Ubuntu Core**, but none for Ubuntu 26.04 classic + RAUC. (d) DC-04's answer (`decision-critical.md` l. 98) still says "**D2 confirmed** for amd64", although 01 §7 says D2 changed in rev. 4; its support-period reasoning is not restated for Ubuntu Pro to May 2036. The founder FDO test LT-VM-16 does cover "the core legs", so this is a desk-evidence gap, not a test gap. G4 for D is probably COND, since most sub-checks are base-agnostic app images, but it is unevidenced on the shipping base. | `01` §3.1.1 l. 161; `evidence/decision-critical.md` DC-02 (l. 66–80), DC-04 (l. 98); `09` §G4 table l. 43 | Add an Ubuntu 26.04 + RAUC column to 09's G4 table, with one primary source per sub-check (for example the real-time kernel under Pro, any IEC 62443 statement from Canonical, FDO on Ubuntu). Re-cite D·G4 to it. Restate DC-02's flip condition for the decision of record and DC-04's answer for D2 rev. 4. If any sub-check FAILs for D, the map in 01 §3.1.6 (h) applies | **Yes** (desk research) |
| **P7-3** | S3 | **The Tier A W6 and W8 files, and two Tier B/C files, were never synced past rev. 1–2.** 07 (owner of DC-04, DC-18, DC-24), 08 (DC-08, 09, 14, 15) and 09 (DC-02, gate G4) still read "**Status: draft for refuters**", dated 2026-11-10, although their refuters have run. 07's bottom line (l. 15) says "none of this overturns **Debian 13 + Rugix + k3s**". 09's founder box (l. 10), P0-1 (l. 25), profile definition (l. 214, "the same signed OneMind image (Debian 13 + Rugix A/B + k3s + NATS)") and base row (l. 227) do the same. Rugix stopped being the engine in rev. 1, and the base changed in rev. 4. 16 l. 6 and 27 l. 6 declare "Consistent with `01` revision 2", and 27 spells it out as "(Debian 13 core, …)", so the learning path teaches a Debian-host setup without saying the decision moved. Pass 4 l. 56 listed the rev-4-synced files and omitted these without raising a gap. 00 l. 99 self-reports a garbled version of it (P7-4). | `07` l. 3, 15; `08` l. 3; `09` l. 3, 10, 25, 214, 227; `16` l. 6; `27` l. 6 | Add a rev-4 header note to each ("Status: final; base per 01 rev. 4 = Ubuntu 26.04 + RAUC, Debian 13 leg kept; Rugix = alternative"). Correct the founder boxes and the 09 profile/base rows to "the OneMind image (base per 01 §1)". Leave the historical analysis intact | **Yes** |
| **P7-4** | S4 | **Two stale self-notes in 00's status table.** l. 87 asks for "`24`'s S1 item" to become `blocked: founder-decision`, which 24 l. 94 (DC-01 / Q288) already shows. l. 99 says "28 and 29 headers say 'draft'", but 28 declares rev. 4 and 29 "draft complete"; it omits that 07–09's founder text names the old stack. Distinct from P4-5 (the PDF row, l. 88 and 96). | `00` l. 87, 99 | Drop the l. 87 clause; reword l. 99 to the P7-3 list | **Yes** |

---

## Part 6. Founder-only and date-bound items (for the orchestrator's final list)

| Item | Why the agent cannot close it | `fixable_by_agent` |
|---|---|---|
| **LT-VM-20 / U-SB run** (P5-1 residue) | The Ubuntu archive is still unresolvable here at 16:12Z and must not be bypassed. It needs a networked machine (20 D1, 2026-11-16) | false |
| **Z-38, Z-39, Z-40, Z-01** | Base-OS acceptance, COND-as-FAIL reading, the written tie-break row count, Canonical/counsel. The P4-8 figure depends on Z-01 | false |
| **Z-28 / N1 / N2 / P4-9** | Removing content from `414d60a`, `ee98bc7` and `7836316` needs a history rewrite and a force-push | false |
| **P4-10** | Founder-authored file on `main` | false |
| **P6-4 acceptability** | Whether the disclosed IP read is acceptable is Zeus's call; logging it is agent work | false |
| **Hardware** | W2-HW-3 (Pi 5, before G1), F-PI5, Jetson, RT latency, real power-cut and firmware tests in 22 | false |
| **N12** | KubeCon NA 2026 days 3–4 re-check cannot run before 2026-11-12 | false (date) |
| **P5-2 blind refuters** | Needs separate blind sub-agents; possible in principle | true |

---

**Loop-until-dry status.**
- **New gaps per pass:** 24 → 15 → 13 → 11 → 7 → 5 → **4** (pass 7: 0 S1, 1 S2, 2 S3, 1 S4).
- **The run is not dry.** No fix landed between passes 6 and 7, so every agent-fixable gap is still open.
- **The cheapest path to a dry pass** is one sync-and-evidence pass:
  1. Close P7-2 first: it is the only S2, and it touches a must-pass gate of the decision of record.
  2. Then the edits to existing files: P6-1, P6-2, P7-1, P7-3, P7-4, the P5-3 residue, P5-4, P4-5, P4-6 and P4-7.
  3. Then the P6-3 and P6-4 notes.
  4. Then the PDF rebuild (P6-5, P5-6).
