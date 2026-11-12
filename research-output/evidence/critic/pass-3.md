# Completeness critic, pass 3

**Date:** 2026-11-11 · **Scope:** RESEARCH-MISSION.md §4, §6, §7 and §9, checked against everything in `research-output/` (working tree of `research/ultracode-foundation` on top of `ee98bc7`, which is pushed: **52 modified and 190 untracked paths are not committed**). Inputs: `evidence/critic/tier-a-pass-1.md`, `evidence/critic/pass-2.md` and `evidence/critic/ledger-audit.md`. **Method:** scripted checks plus targeted reading. The checks covered claim-ID resolution of 00, 01, 03–07, 20, 21, 24 and 30 against the per-tag ledgers (`evidence/claims/*.csv`, 2,704 rows) and the master `evidence/claims.csv` (2,039 rows), using a regex with a look-behind so `REC-…` labels are not counted; `source_type` and `status` of every ID cited in 01; refuter files grouped by conclusion; the 97 IDs of `docs/REQUIREMENTS.md` against `25-…`; the 335 questions of `context/05` against `24-…` (status, duplicates, conflicts); `blocked: founder-decision` items against `26-…`; the components that 01, 13 and 30 recommend against `license-matrix.csv`; `pdfinfo`/`pdftotext` of the PDF against `context/00` and `report/checklist.tsv`; `gitleaks dir` and `gitleaks git` (origin/main..HEAD); the RFC1918/CGNAT, `.ts.net`, e-mail, username and home-path greps over the working tree; the same greps over commits `414d60a` and `ee98bc7`; and `gh pr view 1` (read-only). **The critic fixed nothing.**

**Severity:** **S1** blocks §9 or breaks a hard rule · **S2** weakens a P0 conclusion or a decision-critical answer · **S3** a protocol or ledger defect · **S4** hygiene or polish.

**Bottom line.** Revision 3 closed most of pass 2: 22, 24, 25, 26, SOURCES.md and the PDF exist and are substantive, the Ubuntu and Mender legs and RAUC 1.15.2 ran, DC-20 was measured, every DC has a Result block, the licence matrix covers the Market seed apps, and the working tree is clean of personal data. **The run is still not dry.** The most serious new finding is that **the S1 base-OS verdict (Debian) is not the outcome of the frozen scorecard protocol as written**: the rev-3 tie-break rule was introduced after scoring, is not logged in `scorecard-weights.md`, and was never put to a refuter (P3-1, P3-2). The PDF also tells the founder that all three bases are "inside the tie band" when the frozen rule puts Debian outside it (P3-3). Rev. 3 is not committed, so the public draft PR still shows rev. 2 (P3-5).

---

## Part 1. §9 Definition of done

| §9 item | Verdict | Evidence |
|---|---|---|
| Tier A complete to the teardown minimum, scorecard protocol, adversarial protocol and VM lab | **Not met** | Teardown minimum met for HAOS, umbrelOS, Olares and VillageOS: sequence diagram, claims-vs-code table and pinned code in each; VillageOS is docs-only by necessity; Olares now has the "same at 1.12.7?" table (§3.5a). The VM lab meets §7 items 1–5: Rugix x86_64 and aarch64; RAUC x86_64 (1.13 and 1.15.2); forced bad update with a real k3s gate; power cut; footprint; SQLite and etcd restore. **Fails on protocol:** S1 rev-3 verdict (P3-1, P3-2); DC-12 and DC-20 have no dedicated refuter and E10 has two (P3-9); loop-until-dry not reached |
| Every workstream W1–W17 has its file at its tier's depth | **Met** | 02-competitors (31 files incl. MATRIX and flagged-repos), 03–17, 27; Tier C teardowns all present |
| Every bank question has a status; DCs fully evidenced | **Status met; DCs not fully evidenced** | 335/335 have exactly one allowed status (76 answered · 236 partial · 14 founder-hardware · 6 founder-decision · 2 live-cluster · 1 paywalled). 30 IDs appear twice (§4 and §5), with **no conflicting status**. DCs: 6 answered, 12 partial, 5 blocked, 1 blocked: founder-decision; the partials rest on founder tests, now all present in 22 |
| All 97 requirement IDs traced | **Met** (with stale rows) | 97/97 in 25 (205 table rows, no unknown IDs, no empty cells). Named homes all hold their IDs. **F-9 and F-10 rows are stale** (P3-8) |
| ADR-001 explicitly confirmed/changed/overturned | **Met** | 01 §7; but the S1 basis is contested (P3-1) |
| 20 (with gates) and 21 (with exit criteria) complete | **Met** | 20: six phases, eight gates G1–G8, every lab test scheduled, A01–A24, hours/week and cut list, weeks 1–2 by day. 21: four horizons, 12 exit-criteria mentions, 16 scenario triggers, stop/pivot rules |
| Every claim in 01 resolves to a PRIMARY row in `evidence/claims.csv` | **Not met** | 551 distinct IDs in 01. **All resolve in the per-tag ledgers; 129 are missing from the master file.** Of the 551, **64 are not PRIMARY** (≈52 SECONDARY, 12 PRIMARY-METADATA, 2 UNVERIFIED) and **15 are not `verified`** (P3-4) |
| `license-matrix.csv` covers every recommended component | **Not met** | 231 rows, all with a source. The pass-2 N5 items are now present (seed apps, model weights, Kyverno, Falco, Trivy, go-tuf, GFD, SWUpdate, U-Boot). **Missing: PostgreSQL (BD-04 core datastore), syft, grype, sbsigntools, efitools, tpm2-tools, erofs-utils and UnifiedPush** (P3-6) |
| 28, 29 and 30 complete | **Met** | 30 has layout, pipeline, kernel contract, update/signing chain, milestones, DoD and founder-decision defaults; 29's header predates 01 rev. 2–3 (disclosed in 00) |
| PDF built, standalone, visual, covers every topic in context/00 | **Met, with one misstatement** | 101 A4 pages (Typst 0.15.1), 38 embedded images, 932 claim-ID mentions; checklist rows for every §1–§14 topic plus wellness, finance, OSINT, competitors and flagged repos; F-14 walkthrough at §1.3; Darwin/XNU/BSD, HarmonyOS, Omarchy, GrapheneOS/ATAK, VillageOS, D-001…D-006 all present; no host path, tailnet name or e-mail in the text. **Misstatement on p. 6** (P3-3) |
| PR marked ready for review | **Not met** | PR #1 is still a draft, last updated 2026-11-11T07:08Z with 2 commits; rev. 3 is uncommitted (P3-5) |

## Part 2. §6 deliverables: existence and depth

| Deliverable | Exists | Depth / note |
|---|---|---|
| 00 | Yes (3,903 words) | All required sections, including the per-workstream status table and an honest §7. Longer than "2–3 pages" (P3-11) |
| 01 | Yes (254 KB) | Scorecards, adversarial tables, steelmen, ADR-001 verdict, founder explanation. S1 protocol issue (P3-1) |
| 02-competitors + MATRIX + flagged-repos | Yes | Tier A/B/C depth met |
| 03–17 | Yes | All present; 03–09 and 28–29 headers still say "draft" (disclosed in 00) |
| 20, 21, 23 | Yes | 23 has L, I, score, mitigation, owner, trigger, links and requirement columns (62 risks) |
| 22 | Yes | 16 critical-path tests, exact commands, pass/fail; every founder test the DCs name is present (W2-HW-3, T-W3-04, T-W3-06, LAB-W7-1/2/3/6, T-W5-01/03, F1/F2, F-SB-1, SB-5b, F-PI5, T-W19-01…03, DC20-R6), plus GrapheneOS/ATAK and read-only cluster checks |
| 24, 25, 26 | Yes | See Part 3 |
| 27, 28, 29, 30 | Yes | Met |
| PDF + `report/` | Yes | Source, diagrams, charts, generators and `verify_pdf.py` committed in the tree (not yet in git) |
| SOURCES.md | Yes (252 KB) | Says 2,690 claim rows; the ledgers now hold 2,704 (P3-13) |
| REVIEW-CHECKLIST.md | Yes | 96 approval checkboxes |
| `evidence/claims.csv` | Yes, **stale** | 2,039 of 2,704 rows |
| license-matrix.csv, scorecard-weights.md, decision-critical.md, lab/, outreach-drafts.md | Yes | Gaps P3-1, P3-6, P3-8 |

## Part 3. Mandated checks in detail

**3.1 Claim IDs.** Missing from the master file: 01 129 · 00 10 · 03 8 · 04 4 · 05 15 · 06 6 · 07 0 · 20 12 · 21 9 · 24 88 · 30 31. Missing from the per-tag ledgers: **0 in every file**. The master and per-tag files agree on status and source type for every shared row. 01's non-PRIMARY and non-verified rows are listed in P3-4.

**3.2 Refuters.** 122 files in `evidence/adversarial/`. Three lenses each: W2-P0-1/2, W3-P0-W3-1/2, W4-P0-1/2, W5-P0-1/2, W6-P0-1 (DC-04)/2, W7-FF-1/2, W8-P0-1/2, W18-P0-1/2, and DC-03, 07, 09, 13, 14, 15, 17, 18, 19, 22, 23, 24. DC-16: C-W19-001 and each C-W19-011…028 sub-group 3, C-W19-047/048/049 3 each, E9 4, **E10 2**. **No dedicated refuter:** DC-12 and DC-20 (disclosed). **Borrowed from P0 refuters:** DC-01, 02, 05 (one lens each from three different conclusions), 06, 08, 10, 11, 21. **No refuter at all:** the rev-3 S1 verdict (P3-2).

**3.3 Requirements.** 97/97 in 25. Easily-missed IDs: P-3 in 01; P-4 in 12 (05 answers it but never writes the ID, as 25 F-T2 notes); P-6, A-7, A-8 and H-1 in 11 and 17; UX-8 in 12 §7.2; U-3, W-8 and W-9 in 14; AI-9 in 05 §11 and 10 (REC-W9-12).

**3.4 Question bank.** 335/335 in 24 with an allowed status; 17 `blocked: founder-decision` IDs (bank plus added), **all 17 mapped in 26 §G**. 26 also holds REQUIREMENTS open questions 2–5 (§B), the Blueprint questions (§C: Pixel, Dell 5540, first slice, task system) and RS-6 (§D, plus two later RS-6 lists).

**3.5 Licence matrix.** See P3-6. The Raspberry Pi boot-firmware row gives version `master`, though its licence-file permalink is SHA-pinned.

**3.6 Hygiene.**
- **Working tree:** no username, `/Users/` path, RFC1918, CGNAT or tailnet hostname. The `/home/…` hits are upstream documentation text. E-mail-shaped strings are the five reviewed false positives (FP-1…FP-5).
- **gitleaks:** `gitleaks dir research-output` reports **2 hits** (P3-7). `gitleaks git` on origin/main..HEAD is clean, because the 8 pass-2 hits are in `.gitleaksignore`.
- **History:** commit `414d60a` (pushed) still holds the account name in w4/w18 lab logs and private addresses. `ee98bc7` is clean. This is Z-28, a founder decision.
- **Residual lab-host paths** (`$HOME/<lab-dir>`, `~/<lab-dir>`) in `lab/fedora-bootc/scripts/lab.sh:3` and `lab/secureboot-rauc/README.md:173` (P3-10).

---

## Part 4. Pass-1 and pass-2 gaps: closed or open

| Gap | Status now | Evidence |
|---|---|---|
| P1 #2 steelmen (CRA notified body, etcd on every box) | **Closed** | `steelman-cra-notified-body.md`, `steelman-etcd-every-box.md` |
| P1 #3 master `claims.csv` | **Open (S1)** | 2,039 vs 2,704; 129 of 01's IDs missing. README line 62 and 00 §7 disclose it |
| P1 #4 DC-16 | **Mostly closed** | 25 refuters; qbank/W19 no longer says "not yet run". E10 has 2 refuters; T-W19-01's security variant, on which E1–E10 is conditional, has not run (founder test in 22) |
| P1 #5 lab paths | **Mostly closed** | Labs in repo, claim rows fixed. Residuals: P3-10; 06 line 313 still says `w5-restore` lives "outside the repo" (P3-8) |
| P1 #7 DCs fully evidenced | **Partly closed** | Result blocks for all 24; 22 exists with the tests. Open: DC-12/DC-20 refuters, borrowed refuters (P3-9), stale "22 not yet written" in every Result block (P3-8) |
| P1 #9 uncited scorecard cells | **Closed in `scorecard-rev3.md`** | 32 SCORE claims; MicroK8s and borg drop to gate FAIL; Compose 64.0 survives. **Plausible residual:** rev3 §8 says "01 is not edited here", and 01 carries only 15 `C-SCORE` IDs, so 01's own §3.1.2/§3.3–3.5 tables may not all carry the new citations. Verify |
| P1 #11 C-W7-005 / Fedora 45 Pi 5 sources | **Closed** | 08 repointed; scorecard-rev3 §9 ledgers C-SCORE-027. 01 cites C-W7-005 only in supersession notes. 00 §7's W7 bullet is stale (P3-8) |
| P1 #12 DC-03 cost | **Closed** | `lifecycle-cost-2036.md`; 24 DC-03 gives per-device figures at 1k and 10k units |
| P1 #13 C-W18-038 branch-pinned | **Closed** | Now pinned to `655c9b18…`, verified |
| P1 #14 archive / SOURCES.md | **Closed** | SOURCES.md has 8 ARCHIVE-GAP markers; Wayback was blocked, sha256 saves used instead |
| P1 #15 re-check windows | **Closed for the listed rows**; new stragglers in P3-12 | The seven named rows are now at 6 months |
| P1 #17 pre-registration | **Closed with disclosure** | `lab/PREREGISTRATION.md`: rev-3 spikes frozen with hashes; earlier spikes marked "not verifiable" honestly. The rev-3 hashes have no git timestamp until committed (P3-5) |
| P1 #19 Olares at 1.12.7 | **Closed** | `olares.md` §3.5a |
| N1/N2 personal data and private IPs | **Closed in the working tree; open in history** | `414d60a` still holds them; Z-28 (urgent) and Q-P2-5 await the founder |
| N3 gitleaks | **Partly closed** | 8 hits in `.gitleaksignore`; 2 remain (P3-7) |
| N4 C-W7-056 citations | **Closed** | Remaining mentions are supersession notes |
| N5 licence coverage | **Closed for the named items**; new gaps P3-6 | |
| N6 RAUC ≥ 1.15.2 | **Closed** (x86_64) | `lab/rauc-1152` passed; Debian's 1.13 is CVE-patched but broken on kernels ≥ 6.19. Secure Boot spike not re-run on 1.15.2 (disclosed) |
| N7 asymmetric tie-breaks | **Closed for labs**, but see P3-1 | `ubuntu-2604-leg` and `mender` ran the same battery |
| N8 Pi 5 RAUC path | **Partly closed** | Desk preflight on loop device (C-LAB-rauc-1152-017, partial); LT-PI5-01/F-PI5 founder test written. No aarch64 RAUC + k3s gate run in QEMU |
| N9 Debian + RAUC precedent | **Answered: none found** | C-DEC-013 is an UNVERIFIED/partial negative search (P3-4) |
| N10 status drift | **Closed for the named files**; new drift in P3-8 | |
| N11 lab hashes and versions | **Mostly closed** | Every spike has SHA256SUMS; `rauc/`, `secureboot-rauc/` and `w19-sysext/` have no versions file |
| N12 KubeCon NA 2026 day 3–4 | **Open (cannot close before 2026-11-12)** | C-W4-039/040 `recheck_by` 2026-12-10 |
| N13 hygiene record | **Closed** | `evidence/hygiene-log.md` (says 1 gitleaks hit; there are 2) |
| N14 DC-20 lab | **Closed** | `lab/minimal-image-dc20` |
| N15 missing §9 files | **Closed** | 22, 24, 25 and SOURCES.md exist |

**Tally:** of pass-2's 15 gaps, 9 are closed, 5 partly closed or closed with residue, and N12 is open by date. Pass-1 #3 (the master ledger) is still open.

---

## Part 5. New gaps not raised by pass 1 or pass 2

| # | Sev | Gap | File(s) | What would close it |
|---|---|---|---|---|
| **P3-1** | **S1** | **The S1 verdict is not the frozen protocol's outcome.** `scorecard-weights.md` line 67 freezes: "a difference of under 3.0 points between **the top two** is a tie". The rev-3 cited card is **C 64.0 · D 62.0 · A 60.0**, and `scorecard-rev3.md` line 107 says so itself: "the finalists are **C and D**. A sits 4.0 points behind C, outside the band." 01 §3.1.5 instead adds A as a third finalist through a **head-to-head (pairwise) tie-break that 01's glossary marks "(rev. 3)"**. That is a new decision rule written after the scores were known. `scorecard-weights.md` §8's rev-3 row says only "no weight or anchor change" and does not log it, though §8 requires every change to be logged with the ranking under both the old and the new rule. Under the strict rule, 01 concedes D wins. It then sets D aside because its G1 condition (Z-01) is unmet, but D·G1 is scored **COND, not FAIL**, on the card. **If an unmet COND is disqualifying, D leaves the card, the top two become C (64) and A (60), 4.0 apart, and C (RHEL-family bootc) wins outright with no tie-break.** So Debian survives under neither literal reading. The A-vs-C 5–5 draw is then broken by a "tier argument", which is judgment, not a pre-named row. | `01` §3.1.4–3.1.5, line 102 glossary; `evidence/scorecard-weights.md` §5/§8; `evidence/scorecard-rev3.md` §3.4 | Log the tie-break amendment in `scorecard-weights.md` §8 with the ranking under both rules. Decide explicitly, and record, whether a COND gate that depends on a third party disqualifies, and recompute. Present S1 to the founder as a protocol-level choice (new Z item), not as a protocol result |
| **P3-2** | S2 | **The rev-3 S1 verdict has no refuter.** All base-OS refuters (W2-P0-1/2, DC-17, steelmen) predate the C 64.0 card and the pairwise rule; none attacks "Debian wins head-to-head" or the 5–5 tie-broken-by-tier step. §2 rule 7 requires ≥3 refuters per P0 conclusion, and this is the P0 conclusion as it now stands. | `evidence/adversarial/` | Three independent refuters (technical, longevity, cost) on 01 §3.1.5 rev. 3, given only the verdict and its cited rows |
| **P3-3** | S2 | **The founder PDF misstates the tie.** `report/chapters/01-executive-answer.md` line 26 (PDF p. 6, finding 1) says bootc 64, Ubuntu 62 and Debian 60 are "**all inside the tie band**". Under the frozen 3.0-point rule A is 4.0 behind the leader, and `scorecard-rev3.md` says A is "outside the band". The PDF is the one document the founder is meant to read standalone (F-10). | `report/chapters/01-executive-answer.md`; the PDF | Correct the sentence to match the protocol (or the logged amendment from P3-1), then rebuild |
| **P3-4** | S2 | **§9's "primary-source row" fails beyond the stale master file.** Even in the per-tag ledgers, 01 cites **64 non-PRIMARY** rows and **15 non-verified** rows. Load-bearing examples: **C-DEC-013** (UNVERIFIED/partial negative search: "no Debian/Ubuntu + RAUC product", a tie-break row in S1 and S2); **C-W18-027** (partial: CUDA 13.5 on Debian 13, DC-13); **C-REF3-DC-cost-001/002** (SECONDARY press: Pi 5 and Jetson price rises used in DC-03/DC-10); **C-REF-DC-robotics-005/006** and **C-REF-DC-technical-001/002** (forum posts as the only real-time latency evidence, DC-14); **C-STEEL-cra-nb-017** and **C-REF-W8-longevity-009** (unverified). Also, **conclusions are ledgered as PRIMARY claims**: C-W19-047…049 ("DC-16 ANSWER / CONSTRAINT / FLIP CONDITION"). An agent's verdict is not a source. | `01-…`; `evidence/claims/*.csv` | Per row, state the role (fact vs failure report) and whether the cell or row it carries would change without it. Replace load-bearing SECONDARY rows with primary ones where one exists. Re-type conclusion rows as `DERIVED` or move them out of the ledger. Have 01 state §9 as "met with these listed exceptions" |
| **P3-5** | **S1** | **Revision 3 is not in git.** 52 modified and 190 untracked paths: 20–30, the PDF and `report/`, SOURCES.md, REVIEW-CHECKLIST, all rev-3 labs and claim ledgers, `hygiene-log.md`, `.gitleaksignore`. Public draft PR #1 (2 commits, body 4,372 characters) therefore shows rev. 2, and §8 item 4 ("push after every workstream") has been missed for the whole of rev. 3. The rev-3 pre-registration hashes also lack a git timestamp. 00 §7 notes the agent "does not commit", but no file names who commits, or when relative to Z-28. | repo; PR #1 | Founder or orchestrator: commit and push rev. 3 after the hygiene gate (and after the Z-28 decision if history is to be rewritten), then refresh the PR body with the rev-3 executive summary and checklist |
| **P3-6** | S2 | **The licence matrix misses components that the build brief mandates:** **PostgreSQL** (BD-04, the core datastore on every box), **syft and grype** (D-B1.5 SBOM and CVE scan), **sbsigntools, efitools and tpm2-tools** (Secure Boot enrolment and signing in 30, 22 LT-X86-03 and 01 §4.3), **erofs-utils** (BD-06 follow-up), **UnifiedPush** (REC-W11-09 Android push). | `evidence/license-matrix.csv`; `30-…` §4.2, D-B1.5 | Add pinned-LICENSE rows; re-run the coverage check against every BD-xx and REC-xx component |
| **P3-7** | S3 | **`gitleaks dir research-output` still fails (2 hits):** FP-6 (`MENDER_APT_KEY_FP`, documented in hygiene-log but **not in `.gitleaksignore`**) and a new, undocumented hit at **`lab/mender/scripts/build.sh` line 16 (`MKEY_FP=…`)**. `hygiene-log.md` says 1 hit. | `.gitleaksignore`; `evidence/hygiene-log.md` | Review the new hit (it is probably the same public fingerprint), add both fingerprints to `.gitleaksignore`, and update the log |
| **P3-8** | S3 | **Stale statements after rev. 3.** (a) `decision-critical.md`: every Result block says "Founder test (for `22-…`, **not yet written**)", but 22 exists and contains each named test. (b) `25-…`: F-9 is "Partial (`30-…` **not yet written**)" and F-10 "Pending (PDF **not yet written**)"; the summary line 10, the counts on lines 79–81, finding F-T1 and the glossary line 46 ("22 … does not exist yet") are all stale, so 25's coverage counts are wrong. (c) `06-…` line 313 says `w5-restore` lives "outside the repo"; it is in `evidence/lab/w5-restore/`. (d) 00 §7's W7 bullet asks to repoint C-W7-005 in 08, which is done. (e) `README.md` line 62 is correct, but will go stale with the re-merge. | listed files | One sync pass, then re-count 25's statuses |
| **P3-9** | S2 | **DC refuter coverage is uneven against §4 ("≥3 refuters per … decision-critical question").** DC-12 (the health-gated commit, the core of the update design) and DC-20 have **none dedicated**. DC-05's three lenses come from three different conclusions, one each. DC-01, 02, 06, 08, 10, 11 and 21 borrow P0 refuters that tested rev-1/rev-2 wording, not the rev-3 answers now in their Result blocks. DC-16's E10 has 2. | `evidence/decision-critical.md`; `evidence/adversarial/` | Dedicated three-lens refuters for DC-12 and DC-20, plus a third for E10. For borrowed DCs, a one-line check that the refuted claim still equals the rev-3 answer |
| **P3-10** | S4 | **Residual local folder layout** (`$HOME/<lab-dir>`, `~/<lab-dir>`) in `lab/fedora-bootc/scripts/lab.sh:3`, `lab/secureboot-rauc/README.md:173` and two adversarial files. No username, but it is the host layout, and the runnable script points outside the repo. | listed files | Use a repo-relative or `${LAB:?}` default |
| **P3-11** | S4 | **00 is about 3,900 words**, against the brief's "2–3 pages". | `00-…` | Move the competitor table and glossary to an appendix, or accept it and note the overrun |
| **P3-12** | S4 | **BSP/kernel facts still on a 12-month re-check** (rule 10 says 6 months): C-W7-040 (Spot CORE I/O on JetPack 5.1.2 / L4T R35.4.1), C-W7-041 (VOXL 2 kernel 4.19), C-TD-talos-009 (Image Factory schematic) and C-TD-talos-038 (Omni on Talos). Found with a crude keyword filter; there may be a few more. | `claims/W7.csv`, `TD-talos.csv` | Re-run the window check with a component-class column rather than keywords |
| **P3-13** | S4 | **SOURCES.md was compiled from 2,690 claim rows; the ledgers now hold 2,704.** The 14 later rows have no bibliography entry. | `SOURCES.md` | Regenerate after the last ledger write |

---

## Part 6. New sources to open (not listed by pass 1 or 2)

1. **`AlmaLinux/bootc-images-rpi`**: commit history, contributor count, open issues and release cadence. C·C2 = 3 rests on this one "experimental" repo, and C·C2 alone decides whether bootc leads S1 (P3-1). Apply the same bus-factor test that removed Rugix.
2. **greenboot issue #219** (silent downgrade after a power cut during finalize): current upstream status. It is a named S1 flip condition.
3. **Upstream RAUC fix for the dm-verity status field on kernels ≥ 6.19**: the release that carries it, and any Debian BTS bug or `trixie-proposed-updates` upload. This decides whether "OneMind builds its own RAUC" is permanent or a stop-gap (RR-16).
4. **OSADL QA Farm latency data** (or another primary measured source) for Pi 5 and Jetson Orin under PREEMPT_RT, to replace forum-sourced rows C-REF-DC-robotics-005/006 and C-REF-DC-technical-001/002 for DC-14.
5. **The EU NANDO database** (CRA notified bodies, Regulation 2024/2847), through another access path such as the database's export or the Commission's single-market pages. C-STEEL-cra-nb-017 is unverified, and the CRA steelman leans on it.
6. **Pinned LICENSE files** for PostgreSQL, syft, grype, sbsigntools, efitools, tpm2-tools, erofs-utils and UnifiedPush (P3-6).

## Part 7. New questions for the bank (no IDs yet)

- **Q-P3-1:** Under the frozen protocol, does a gate scored COND because it waits on a third party (D·G1, Canonical's permission) disqualify a candidate? If yes, S1 is C vs A at 4.0 and bootc wins outright; if no, the strict top-two tie-break picks D. Which reading does the founder adopt, and is the rev-3 pairwise rule accepted as a logged amendment? (P3-1; founder-decision)
- **Q-P3-2:** Should the C2 anchors say how "experimental" or "preview" vendor support scores, the way the SECONDARY cap does for sources? The S1 order turns on that one cell (C·C2 3 vs 2).
- **Q-P3-3:** Is OneMind's own RAUC build permanent, or does it end once Debian ships a fixed RAUC? Who tracks RAUC CVEs, under what SLA, and how is that recorded as CRA component due diligence?
- **Q-P3-4:** What is the bus factor and release cadence of AlmaLinux's Pi bootc images, by the same test that moved the engine from Rugix to RAUC?
- **Q-P3-5:** Which load-bearing rows in 01 are SECONDARY or forum-only, and does any scorecard cell or tie-break row change if each is set to the lowest anchor? (P3-4)

---

**Loop-until-dry status:** pass 1 added 24 gaps and pass 2 added 15. Pass 3 adds **13 new gaps** (P3-1…P3-13: 2 S1, 5 S2, 2 S3, 4 S4), **6 new sources** and **5 new questions**. The run is **not dry**. A pass 4 should verify P3-1 to P3-9, the master ledger re-merge (pass-1 #3), the commit and push of rev. 3 (P3-5), and the post-2026-11-12 KubeCon re-check (N12).
