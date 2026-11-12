# Completeness critic, pass 4

**Date:** 2026-11-11 · **Scope:** RESEARCH-MISSION.md §4, §6, §7 and §9, checked against everything in `research-output/` (working tree of `research/ultracode-foundation`: rev. 3 is committed and pushed as `7836316`; the wave-4 / rev-4 changes are uncommitted, which is expected). Input: `evidence/critic/pass-3.md`. **Not counted as gaps (orchestrator's job at commit time):** uncommitted files, the master `evidence/claims.csv` re-merge, the gitleaks run at commit, and PR #1 still being a draft.

**Method:** scripted checks plus targeted reading. Claim-ID resolution of 00, 01, 03–07, 20, 21, 24, 26, 30, `decision-critical.md`, the S1 protocol ruling and the PDF source (`report/chapters/*.md`, `main.typ`) against the 105 per-tag ledgers (2,875 rows, no duplicate IDs). The regex uses a look-behind and expands `…` ranges. I also checked the `source_type` and `status` of every ID cited in 01 and compared the result with `critic/cit4-mapping.md`. Other checks:
- the S1 rev-4 verdict re-read against `scorecard-weights.md` (frozen §2, §3 line 67, §5 rule 6, §6, §8) and `adversarial/S1-protocol-ruling-rev4.md`;
- refuter files grouped by conclusion;
- the 97 IDs of `docs/REQUIREMENTS.md` against 25;
- the 335 bank IDs against 24 (one allowed status each, no conflicts);
- every `blocked: founder-decision` ID in 24 against 26;
- licence-matrix coverage of the rev-4 decision of record;
- `pdfinfo`/`pdftotext` and `report/verify_pdf.py` on the PDF;
- the hygiene greps (username, `/Users/`, `/home/`, host folder layout, `.ts.net`, RFC1918 and CGNAT, e-mail, credential patterns) over the working tree and over commits `414d60a`, `ee98bc7` and `7836316`;
- `gitleaks dir research-output` and `gitleaks git` on `origin/main..HEAD` (8.30.1).

**The critic fixed nothing.**

**Severity:** **S1** blocks §9 or breaks a hard rule · **S2** weakens a P0 conclusion or a decision-critical answer · **S3** a protocol or ledger defect · **S4** hygiene or polish.

**Bottom line.** Rev. 4 closes the protocol finding that drove pass 3:
- **01's S1 verdict now follows the frozen protocol.** The rev-3 pairwise rule is withdrawn and logged in `scorecard-weights.md` §8. The top-two tie (D 65 · C 64, margin 1.0 < 3.0) is broken 6–4 for D on decision-critical rows. The fragility (D 11/14) is labelled under §6.3, and every outcome-changing variant is shown.
- The PDF has been rebuilt from rev. 4 (108 pages, 75/75 topics, every source claim ID resolves).
- Licence gaps P3-6 and gitleaks hits P3-7 are closed.

**The run is still not dry.**
- The **new decision of record (Ubuntu 26.04) has no refuter of its own**. Its rev-4 re-scores, recount, new tie-break row and decision map were never attacked; 00 §6 admits this (P4-1).
- **The licence matrix has no row for the base it now recommends** (P4-2).
- **The round-4 refuter files reuse claim IDs for different facts**, so several rev-4 answer changes rest on unledgered sources (P4-3).

---

## Part 1. §9 Definition of done

| §9 item | Verdict | Evidence |
|---|---|---|
| Tier A to the teardown minimum, scorecard protocol, adversarial protocol, VM lab | **Not met** (narrowly) | Teardowns and VM lab as in pass 3, plus `lab/aarch64-gate` (RAUC 1.15.2 + real k3s gate on arm64, PASS) and `lab/secureboot-1152` (PASS), both pre-registered with hashes in `PREREGISTRATION.md`. **Scorecard protocol: now met** (Part 3.1). **Adversarial protocol: fails for the rev-4 S1 conclusion**: 0 refuters (P4-1). Loop-until-dry not reached |
| Every workstream W1–W17 has its file at its tier's depth | **Met** | Unchanged from pass 3 |
| Every bank question has a status; DCs fully evidenced | **Status met; DCs not fully evidenced** | 335/335 have exactly one allowed status, no conflicts (74 answered · 237 partial · 14 founder-hardware · 7 founder-decision · 2 live-cluster · 1 paywalled). Every DC has ≥3 refuters counting borrowed ones. DC-12, DC-20 and E10 have dedicated sets. But DC-11, DC-12, DC-21/R4-10 and E10 answer changes rest on round-4 sources that are "not ledgered" or sit under colliding IDs (P4-3) |
| All 97 requirement IDs traced | **Met** (one stale row) | 97/97 in 25. F-10's row is stale (P4-5) |
| ADR-001 explicitly confirmed / changed / overturned | **Met** | 01 §7: D2 **changed (rev. 4, conditional)** to Ubuntu 26.04, with the pre-registered map. 00 states the same |
| 20 (gates) and 21 (exit criteria) complete | **Met** | Both synced to 01 rev. 4. 20 puts W2-HW-3 before G1 and adds a base-lock gate |
| Every claim in 01 resolves to a primary-source row | **Not met** (excluding the master-file merge, as instructed) | 786 distinct IDs in 01. **All resolve in the per-tag ledgers.** 103 are not PRIMARY (71 SECONDARY, 26 PRIMARY-METADATA, 2 COMMUNITY, 2 UNVERIFIED, 1 VENDOR-FORUM, 1 INFERRED) and 28 are not `verified` (21 partial, 4 unverified, 3 superseded). 01 now states "met with listed exceptions" and labels rows inline. **But 48 of the 123 exception IDs are not in the list it points to** (P4-4), C-W19-047…049 are still typed PRIMARY (P3-4 residual), and 14 places in 01 rely on refuter sources marked "not ledgered" (P4-3) |
| `license-matrix.csv` covers every recommended component | **Not met** | 277 rows; all eight P3-6 items are present. **Missing:** the Ubuntu 26.04 **core** image (x86_64, arm64, Pi 5 certified image, `linux-raspi`), which is now the decision of record (P4-2) |
| 28, 29, 30 complete | **Met** | 30 builds both base legs (`debian.args` / `ubuntu.args`); its default base waits on Z-38 |
| PDF built, standalone, visual, covers every topic | **Met** | 108 pages, built 2026-11-11 10:14. `verify_pdf.py`: 75 topics, 0 missing, 36 images embedded. All 462 claim IDs in `report/` resolve. Consistent with 01 rev. 4: 65/64/63, top-two tie, 6–4, fragile 11/14, decision map, D2 changed. The p. 6 "all inside the tie band" sentence is gone (P3-3 closed). No host path, tailnet name or e-mail in the text |
| PR marked ready for review | Not met; **not counted** | PR #1 is a draft; per 26 it is blocked on Z-28 (founder) |

## Part 2. §6 deliverables

All §6 files exist (00–17, 20–30, `02-competitors/` with MATRIX and flagged-repos, PDF + `report/`, SOURCES.md, REVIEW-CHECKLIST.md, `evidence/` files and labs). Changes since pass 3:

| Deliverable | Note |
|---|---|
| 00 | 1,609 words, so P3-11 is closed. Has stale PDF and 24-status lines (P4-5) |
| 01 | Rev. 4: §3.1.6 protocol re-derivation, §5.1.1 and §5.9.2 new refuters, §6.14 bootc steelman, §7.3. Some §1/§7 lines are Debian-specific without a rev-4 qualifier (P4-7) |
| 03, 04, 05, 06, 22, 23, 24, 25, 26, 28 | Headers say synced to 01 rev. 4 |
| SOURCES.md | Compiled from 2,875 rows, equal to the ledgers, so P3-13 is closed |
| `scorecard-weights.md` | §8 rev-4 row logs the withdrawal, the S1-12 re-score, the ranking under both rules, and the pre-registered decision map |
| `license-matrix.csv` / `.md` | P3-6 closed; P4-2 open |
| Lab | 18 spikes. `secureboot-1152`, `rauc`, `secureboot-rauc` and `w19-sysext` have no versions file (N11 residual) |

## Part 3. Mandated checks in detail

**3.1 S1 verdict against the frozen protocol (`scorecard-weights.md`).** Checked step by step:

1. **Gates:** A, C and D have no FAIL. COND results are ranked, per §2 lines 35–41.
2. **Re-scores (§5 rule 6):** S1-12 sets C3 = 4 for **every** RAUC stack (A, D, G and F), with D, G and F marked `doc-only`. The steelman independently keeps C·C3 = 3 (W6: sealed images and boot counting live in different backends). S1-13 and S1-14 were rejected because they were one-sided; the symmetric versions are shown as variants V4 and V6.
3. **Totals** (my recomputation): D 65.0 · C 64.0 · A 63.0 · G 54 · B 52 · E 52 · F 49.
4. **Tie test** (line 67, "the top two"): D–C, margin 1.0, so it is a tie.
5. **Tie-break** on decision-critical rows: D 6–4. The rev-4 row changes (DC-05 A–D → ≈; the new "signed GPU modules" row) leave the D–C count unchanged.
6. **Sensitivity (§6):** D 11, A 2, C 1, so **fragile**, with the flipping weights named.
7. **Change log (§8):** the rev-3 rule is withdrawn; rankings under both rules are recorded for the rev-3 and rev-4 cards; no weight or anchor changed.

**Verdict: the S1 result in 01 rev. 4 follows the frozen protocol.** Two caveats are disclosed and routed to the founder:
- **(a)** the row-count tie-break method is used but not written into the frozen file (Z-40);
- **(b)** COND needs "a stated cost and owner", but D's G1 has no cost (P4-8; Z-39 / V9).

**3.2 Claim IDs.** 0 unresolved IDs in every file checked. Counts are in the Part 1 table. Per file, non-PRIMARY / non-verified: 00 2/1 · 03 2/1 · 04 5/3 · 05 7/0 · 06 7/0 · 07 0/0 · 20 7/2 · 21 5/4 · 24 64/35 · 26 17/7 · 30 14/6.

**3.3 Refuters.** 152 files in `adversarial/`.
- **Two round-4 dedicated lenses** (technical, longevity) plus the earlier borrowed P0 lenses: DC-01, 02, 05, 06, 08, 10, 11 and 21. That is ≥3 per DC overall, and closes P3-9's "one-line re-check" request.
- **Three dedicated lenses:** DC-12, DC-20 and DC-E10, so E10 now has 5.
- **Rev-3 S1 verdict:** the S1R4 technical, longevity and security refuters, plus the STEEL4 bootc steelman.
- **Rev-4 S1 verdict (Ubuntu as decision of record): none** (P4-1).

**3.4 Requirements.** 97/97 in 25 (no unknown IDs).

**3.5 Question bank.** 335/335. Of the 21 `blocked: founder-decision` IDs in 24 (bank plus added), **20 are named in 26 and Q288 is not** (P4-6).

**3.6 Licence matrix.** 277 rows, every row with a source. The P3-6 components (PostgreSQL, syft, grype, sbsigntools, efitools, tpm2-tools, erofs-utils, UnifiedPush) are present. The single Ubuntu row covers only "Ubuntu 24.04 rootfs under L4T (Jetson flavor) and Ubuntu 26.04 LTS (GPU-server flavor option)". "Debian 13 'trixie' base (core image, D2)" still holds the core label (P4-2). Twenty-odd rows give a branch (`main`/`master`) as the version. Most have SHA-pinned licence permalinks, so they pass the "pinned LICENSE file" rule, but the version column is unpinned (S4, same class as pass-3 §3.5).

**3.7 PDF.** See Part 1. `00`, `README.md`, `REVIEW-CHECKLIST.md` and `25` still describe it as the 101-page rev-3 build (P4-5).

**3.8 Public-repo hygiene.**

*Working tree (`research-output/`):*
- No account name, no `/Users/` path, no RFC1918 or CGNAT address, no `.ts.net` name.
- The `/home/…` hits are upstream documentation (`/home/username/`, `/home/user/`, `/home/robot/`).
- E-mail-shaped strings are public project addresses (`security@pengutronix.de`, `aur-general@lists.archlinux.org`, `git@github.com`) and systemd unit names.
- **gitleaks dir: 0 leaks. gitleaks git (origin/main..HEAD): 0 leaks.**
- The host folder layout survives only as quotations inside `critic/pass-2.md` (l. 48) and `critic/pass-3.md` (l. 61, 114) (P4-11). Relative `work/.lab` mentions in old refuter files are disclosed in `hygiene-log.md` §3.

*Outside `research-output/`:*
- `research/platform/iiot-landscape-and-requirements.md:441` contains a `/Users/<founder alias>/…` path (commit `6790db5`, on `main`) (P4-10).
- `context/00-CONVERSATION-RECORD.md:111` names the collaborator's GitHub handle. That file is founder-authored context and was committed before the run; it is out of scope for edits.

*History:*
- `414d60a`: 17 files hold the account name and home path (Z-28).
- `ee98bc7` and `7836316` (both pushed): 11 and 13 files hold the host folder layout (no account name). Z-28 names only `414d60a` (P4-9).

---

## Part 4. Pass-3 gaps (and the earlier ones pass 3 carried): closed or open

| Gap | Status | Evidence |
|---|---|---|
| **P3-1** S1 verdict not the frozen protocol's outcome | **Closed** | 01 §3.1.6; `scorecard-weights.md` §8 rev-4 row; `S1-protocol-ruling-rev4.md`; Part 3.1. Founder residue Z-38/Z-39/Z-40 is correctly routed |
| **P3-2** rev-3 S1 verdict has no refuter | **Closed** | S1R4 technical, longevity and security refuters, plus STEEL4. The **rev-4** verdict has none: new gap P4-1 |
| **P3-3** PDF "all inside the tie band" | **Closed** | `report/chapters/01-executive-answer.md:26` and PDF p. 6 now read "within 2 points … the locked rules pick Ubuntu" |
| **P3-4** non-PRIMARY / non-verified rows in 01; conclusions ledgered as PRIMARY | **Partly closed** | CIT4 (17 new primary rows, 3 supersessions, inline labels) and 01's "met with listed exceptions" statement. **Open:** C-W19-047…049 are still `PRIMARY` in `claims/W19.csv`, though CIT4 §5 says to re-type them (01 labels them "derived" inline only); the exception list is incomplete for rev. 4 (P4-4) |
| **P3-5** rev. 3 not in git | **Closed** | `7836316` is on `origin/research/ultracode-foundation`. Rev. 4 being uncommitted is not counted |
| **P3-6** licence matrix missing build-brief components | **Closed** | All eight present (`license-matrix.md` l. 114–117). See P4-2 for the new base |
| **P3-7** gitleaks 2 hits | **Closed** | 0 hits; FP-6 and FP-6b are in `.gitleaksignore` and `hygiene-log.md` |
| **P3-8** stale statements | **(a) closed** (no "not yet written" in decision-critical) · **(b) partly**: F-9 fixed, F-10 stale again after the rebuild (P4-5) · **(c) closed** · **(d) closed** (00 no longer cites C-W7-005) · **(e)** README is stale on the PDF (P4-5) |
| **P3-9** DC refuter coverage | **Closed** | Part 3.3 |
| **P3-10** host-layout residue in labs | **Closed in the tree** | `lab.sh` and `secureboot-rauc/README.md` are clean. Critic-file quotations: P4-11. History: P4-9 |
| **P3-11** 00 length | **Closed** | 1,609 words |
| **P3-12** BSP/kernel re-check windows | **Closed for the named rows** | C-W7-040/041 and C-TD-talos-009/038 now re-check at 6 months |
| **P3-13** SOURCES.md row count | **Closed** | 2,875 = ledgers |
| P1 #3 master `claims.csv` | **Not counted** (merged at commit time) | README discloses 171 rev-4 rows are pending |
| N1/N2 history | **Open (founder, history rewrite)** | Z-28; scope gap P4-9 |
| N6 RAUC 1.15.2 Secure Boot re-run | **Closed** | `lab/secureboot-1152` PASS [C-LAB-secureboot-1152-005] |
| N8 Pi 5 / aarch64 RAUC path | **Closed for emulation** | `lab/aarch64-gate` PASS; a real Pi 5 stays a founder test (F-PI5) |
| N11 lab versions files | **Open (S4)** | `rauc/`, `secureboot-rauc/`, `w19-sysext/` and now `secureboot-1152/` have no versions file |
| N12 KubeCon NA 2026 days 3–4 | **Open (date)** | C-W4-039/040 `recheck_by` 2026-12-10; cannot close before 2026-11-12 |

**Tally:** of pass-3's 13 gaps, **11 are closed** (P3-1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13) and **2 are partly closed** (P3-4, P3-8). Of the earlier carried items, N6 and N8 are closed; N1/N2, N11 and N12 stay open.

---

## Part 5. New gaps not raised by passes 1–3

| # | Sev | Gap | File(s) | What would close it | Agent can fix? |
|---|---|---|---|---|---|
| **P4-1** | **S2** | **The rev-4 decision of record has no refuter.** "Ubuntu 26.04 + RAUC wins S1 under the frozen protocol" is now the P0 conclusion. It rests on four things decided in rev. 4: the S1-12 re-score that gives D·C3 = 4 `doc-only` without an Ubuntu Secure Boot leg (variant V3, D·C3 = 3, makes **C** win); the S1-13/S1-14 rulings; the new tie-break row and the DC-05 row change; and the decision map. The S1R4 refuters attacked only the rev-3 Debian verdict. §2 rule 7 needs ≥3 refuters per P0 conclusion. 00 §6 admits "the rev-4 re-scores, recount and decision map have no refuter yet". | `01` §3.1.6; `evidence/adversarial/` | Three independent refuters (technical, longevity, cost or security) given only §3.1.6 (c)–(h) and their cited rows. At minimum, one must test whether D·C3 = 4 is legitimate before an Ubuntu Secure Boot leg runs | Yes |
| **P4-2** | **S2** | **The licence matrix does not cover the recommended base.** It has no row for the Ubuntu 26.04 **core** image on x86_64, arm64 and the Pi 5 (Canonical's certified Pi 5 image and `linux-raspi`, which 01 §4.1 names for the D leg), and no Ubuntu Pro for Devices terms row. The only Ubuntu row is scoped to the Jetson flavor and the GPU-server option. "Debian 13 'trixie' base (core image, D2)" still holds the core label. §9 requires every recommended component. | `evidence/license-matrix.csv`, `.md` | Add pinned rows for the Ubuntu 26.04 core image, `linux-raspi` and the Pi 5 firmware/boot path on Ubuntu, with the Canonical IP-policy obligations (C-LIC-011). Relabel the Debian row as "A leg" | Yes (rows); Canonical's answer is Z-01 |
| **P4-3** | S3 | **Round-4 refuter files reuse claim IDs for different facts.** Each refuter numbered from 001 or 006 within a shared tag. Examples: `C-REF4-DC-technical-001` is cited in DC-01, DC-08 and DC-12 technical; `C-REF4-DC-technical-006` is an Umbrel OTA report in the ledger and in DC-05, but a kine compaction bug in DC-11-technical and an EEPROM CI point in DC-E10-technical; `C-REF4-DC-longevity-001` is cited in DC-01 and DC-12. The ledgers kept one file's row per ID. So a reader who resolves an ID from DC-11, DC-12, DC-21 or E10 gets the wrong fact. 01 marks 14 places "not ledgered". Load-bearing for: the narrowed DC-12 answer, R4-10 (K2-hybrid → shim route), DC-11 and E10. The DC-24 refuter has the same problem under REF3. | `evidence/adversarial/DC-*.md`; `claims/REF4-DC-*.csv`; `01` §5.9.2, R4-10 | Re-ledger each file's sources under unique IDs (e.g. `C-REF4-DC12-technical-001`), rewrite the citations in the refuter files, and replace "not ledgered" in 01 with IDs | Yes |
| **P4-4** | S3 | **01's "met with listed exceptions" list is incomplete.** 01 says the non-PRIMARY or non-verified rows "are listed in `critic/cit4-mapping.md`". That file covers rev. 3 (558 IDs, 74 rows). In rev. 4, 123 cited IDs are exceptions, and **48 are not in the mapping**. They are mostly new tags: REF4-DC 12, REF3-DC 8, STEEL4 4, LAB-minimal-image-dc20 4, LAB-aarch64-gate 3, REF3-W19 3, LAB-secureboot-1152 2, REF4-S1R4 3, and others. Examples: C-REF4-S1R4-security-007 (INFERRED/unverified, in the new tie-break row) and C-STEEL4-bootc-013 (partial). | `01` §12; `critic/cit4-mapping.md` | Extend the mapping (or add a rev-4 appendix) for all 123, with role and "does a cell or row change without it" | Yes |
| **P4-5** | S3 | **Stale PDF status after the rebuild.** The PDF is now 108 pages and built from rev. 4, but: `00` l. 4 says "The PDF still shows rev. 3"; `00` §5 row "Built (101 pages) from rev. 3 · Needs rebuild"; `00` §6 says "rebuild from rev. 4; it still misstates the tie (P3-3)"; `README.md` l. 42 says "101 pages. Built from rev. 3 … (Debian 13)"; `REVIEW-CHECKLIST.md` l. 18 says 101 pages / built from rev. 3, and l. 191 has an open "PDF rebuilt" box; `25` F-10 is **Partial** ("101 pages", built from rev. 3), which makes 25's counts (90 / 4 / 3) wrong. Also, `00` §5 says "24's S1 item should become `blocked: founder-decision`", which 24 already did (Q288). | `00`, `README.md`, `REVIEW-CHECKLIST.md`, `25` | One sync pass after the final build; re-count 25 | Yes |
| **P4-6** | S3 | **Q288 is not mapped in 26.** Rev. 4 moved Q288 (DC-01) from partial to `blocked: founder-decision` (24 l. 463, 669, 674). §6 requires every such item in 26, and 26 §G claims to map every one, but Q288 appears nowhere in 26 (Z-38 covers it in substance). | `26` §G | Add Q288 → Z-38 (and DC-01) to §G | Yes |
| **P4-7** | S4 | **Debian-specific lines in 01 without a rev-4 qualifier:** the §1 table "Image build (D1)" row ("snapshot-pinned Debian"), the §1 "Kernel" row ("Debian stock"), and §7's "Net" and "Final net (revision 3)" paragraphs ("confirmed — D2 (Debian core)") directly under a §7 heading titled "revision 4". §4.1 handles this correctly with an explicit A-leg note. "Explain it" items 10–13 ("Debian still wins the base") are labelled rev. 3 but read as current. | `01` §1, §7, founder box | Add the same "describes the A leg / superseded by §7.3" qualifier | Yes |
| **P4-8** | S2 | **The decision of record's G1 COND has no stated cost.** Frozen §2 defines CONDITIONAL as "a named mitigation that has a stated cost and owner", and "an unproven gate counts as FAIL". RR-09 and C-DEC4-010 say the cost is **unbounded**. 01 itself uses Ubuntu Pro's published per-machine price [C-W2-007] to bound D·C1, so the run has a figure it could use to bound G1 and does not. The rev-4 card stands only because the same gap is applied to every candidate (V9), which Z-39 puts to the founder. | `01` §3.1.6 (i); `23` RR-09; `lifecycle-cost-2036.md` | State a bounded estimate for the Canonical agreement or the debrand-and-recompile route, with its assumptions. Otherwise the S1 result is formally `blocked: founder-decision` until Z-01 or Z-39 is answered | No: the decisive figure needs Canonical or counsel (Z-01) and the founder's ruling on Z-39; an agent can add only a provisional bound |
| **P4-9** | S4 | **Z-28 is scoped too narrowly.** It names only `414d60a`. Pushed commits `ee98bc7` (11 files) and `7836316` (13 files) also carry the lab host's folder layout (no account name). A rewrite "from masked commits" must cover them. | `26` Z-28; branch history | Widen Z-28's text to every pushed commit, then let the founder decide | No (history rewrite and founder decision) |
| **P4-10** | S4 | **A home path with the founder's account alias is on `main`**, outside `research-output/`: `research/platform/iiot-landscape-and-requirements.md` l. 441 (`/Users/<alias>/…`), from commit `6790db5`, which predates the run. The repo is public. | `research/platform/…` | Founder: mask it in a `fix(docs):`-style commit and decide whether history matters (Z-28) | No (founder-authored file on `main`; history) |
| **P4-11** | S4 | **The critic files themselves quote the host folder layout** (`critic/pass-2.md` l. 48, `critic/pass-3.md` l. 61 and 114) in the working tree. | `evidence/critic/` | Replace it with `<host folder layout>` | Yes |

## Part 6. Founder-only and date-bound items (for the orchestrator's final list)

- **Z-38, Z-39, Z-40** (base-OS decision, COND-as-FAIL reading, the four written scoring rules) and **Z-01** (Canonical/counsel). Each can change S1 by the pre-registered map.
- **Z-28** (history rewrite), widened per P4-9; P4-10.
- **Hardware:** W2-HW-3 (Pi 5 bootc) before G1; F-PI5; Jetson, RT latency and real power-cut tests in 22.
- **N12:** the KubeCon NA 2026 days 3–4 re-check cannot run before 2026-11-12 (C-W4-039/040 due 2026-12-10).

---

**Loop-until-dry status:** pass 1 added 24 gaps, pass 2 added 15 and pass 3 added 13. Pass 4 closes 11 of pass 3's 13 outright, plus N6 and N8, and adds **11 new gaps**: 0 S1, 3 S2 (P4-1, P4-2, P4-8), 4 S3 (P4-3…P4-6) and 4 S4 (P4-7, P4-9…P4-11). Eight new gaps can be fixed by an agent. P4-8, P4-9 and P4-10 need the founder, history or Canonical. The run is **not dry**, but no S1 gap remains. The main remaining risk is P4-1: S1 is again fragile and depends on judgement, and its new winner has not been attacked.
