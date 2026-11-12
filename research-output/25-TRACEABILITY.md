# 25 · Requirement traceability: every requirement ID → recommendation → file

**Owner:** TRACE · **Date:** 2026-11-11 · **Status:** revision 3 (2026-11-11, SYNC5-a): synced to `01` revision 4.1; F-10 now points to the rebuilt PDF (critic P4-5). Revision 2 (PROP4-d): synced to `01` revision 4 and critic pass 3 (P3-8b). Revision 1 was built when 20, 21, 22, 24, 30, `REVIEW-CHECKLIST.md` and the PDF did not exist yet; all of them exist now
**Serves requirements:** RS-1, RS-7, F-9, F-10, M-6 (and indexes all 97)
**Companion:** [`SOURCES.md`](SOURCES.md) (bibliography and ARCHIVE-GAP list)

> ### Explain it like I'm the founder
> On 2026-11-10 you gave the project **97 numbered requirements** (`docs/REQUIREMENTS.md`): M-1 "local-first is the moat", F-14 "one OS from a Pi to a GPU cluster", and so on. The brief says none of them may be dropped silently. This file is the checklist that proves it: for **each** requirement it names the recommendation(s) that answer it and the exact file and section where you can read the answer.
>
> **The short answer:** all 97 are traced. **91 are covered**, 4 are covered but wait on something only you can provide (a founder decision, or read-only access to the live cluster), and 2 are only partly covered. None is pending: the build brief (F-9) and the PDF (F-10) both exist, and the PDF is rebuilt from `01` revision 4.1. The brief's eight "easily-missed" IDs all sit where the brief said they should, with one small labelling gap (P-4 is answered in `05` but `05` never writes the ID down).
>
> Think of it like a building inspection: each requirement is a line on the inspector's sheet, and each line points to the room where the work was done.

---

## Contents

1. [Glossary](#1-glossary)
2. [Count check: 97 IDs](#2-count-check-97-ids)
3. [Coverage summary](#3-coverage-summary)
4. [The easily-missed IDs (brief §5), with their named homes verified](#4-the-easily-missed-ids-brief-5-with-their-named-homes-verified)
5. [The trace matrix: all 97 IDs](#5-the-trace-matrix-all-97-ids)
6. [Findings: gaps and defects in the trace](#6-findings-gaps-and-defects-in-the-trace)
7. [What competitors do (keeping requirements tied to checks)](#7-what-competitors-do-keeping-requirements-tied-to-checks)
8. [Recommendations (with requirement IDs)](#8-recommendations-with-requirement-ids)
9. [Method and limits](#9-method-and-limits)
10. [Appendix A: machine index of every recommendation label per ID](#10-appendix-a-machine-index-of-every-recommendation-label-per-id)
11. [Change log](#11-change-log)

---

## 1. Glossary

| Term | Meaning |
|---|---|
| **Requirement ID** | A numbered founder requirement in `docs/REQUIREMENTS.md`, e.g. `M-7`, `UX-8`, `F-14`. Twelve families: M (mission), P (product shape), A (apps), AI, UX, U (users), N (nodes), R (reliability), H (hardware business), W (website), RS (research mandate), F (platform ambition). |
| **Decision ID** | `D-001`…`D-006` in `docs/DECISIONS.md`. Binding founder decisions, **not** requirement IDs, so they are not counted in the 97 even though many files list them under "Serves". |
| **Recommendation label** | The ID a research file gives one recommendation. Each family lives in one file: `REC-DEC-##` → 01 · `W2-R#` → 03 · `W3-REC-##` → 04 · `W5-R#` → 06 · `SEC-##` → 07 · `W7-R#` → 08 · `W8-R#` → 09 · `REC-W9-##` → 10 · `W10-R#` → 11 · `REC-W11-##` → 12 · `W12-R#` → 13 · `REC-W13-##` → 14 · `REC-W14-##` → 15 · `REC-W15-##` → 16 · `REC-W16-##` → 17 · `REC-W17-##` → 27 · `REC-W18-#` → 28 · `REC-W19-##` → 29 · `REC-MATRIX-##` → `02-competitors/MATRIX.md` · `REC-FL-#` → `02-competitors/flagged-repos.md` · `REC-RISK-##` → 23 · `REC-PLAN-##` → 20 · `REC-B30-##` → 30 (the last two added in revision 2, for F-9 only; §9 item 7). (05 has no labels of its own; its §15 table maps IDs to sections.) |
| **Trace** | The chain *requirement → recommendation → file §section*. |
| **Named home** | The file the brief (§5) says must answer an easily-missed ID. |
| **Covered** | At least one recommendation names the ID, and a body section answers it with cited evidence. |
| **Covered · blocked** | Answered as far as the evidence allows; a deciding input is a founder decision (`blocked: founder-decision`) or the live cluster (`blocked: live-cluster`, answered from `context/01` "reported state"). |
| **Partial** | Addressed, but part of the requirement depends on a deliverable that does not exist yet or is out of date against `01`, or on an outside fact that cannot yet be checked. |
| **Pending** | Its deliverable has not been started. |
| **†** | In the matrix: the recommendation serves the ID in substance but does not list it. |
| **Founder test** | A test only Zeus can run on hardware (named `T-…`, `F-…`, `W2-HW-…`). They are collected, with exact commands and pass/fail criteria, in `22-HARDWARE-LAB-TEST-PLAN.md` (as `LT-…` IDs with the old names as aliases) and scheduled against gates in `20-PLAN-180-DAYS.md`. |

---

## 2. Count check: 97 IDs

`docs/REQUIREMENTS.md` was parsed for table rows that start with an ID. Result: **97 distinct IDs, no duplicates**, matching the change log's final total ("Added F-15 … Total IDs: 97").

| Family | Section in REQUIREMENTS | IDs | Count |
|---|---|---|---|
| M | §0 Mission | M-1…M-8 | 8 |
| P | §1 Product shape | P-1…P-9 | 9 |
| A | §2 Apps, store, plugins | A-1…A-8 | 8 |
| AI | §3 AI-native OS | AI-1…AI-9 | 9 |
| UX | §4 Dashboard and UX | UX-1…UX-10 | 10 |
| U | §5 Users, family, security | U-1…U-5 | 5 |
| N | §6 Nodes, hardware, detection | N-1…N-10 | 10 |
| R | §7 Updates, support, reliability | R-1…R-3 | 3 |
| H | §8 Hardware business | H-1…H-4 | 4 |
| W | §10 Website and community | W-1…W-9 | 9 |
| RS | §11 Research mandate | RS-1…RS-7 | 7 |
| F | §13 Platform ambition | F-1…F-15 | 15 |
| | | **Total** | **97** |

§9 (domains) and §12 (existing assets) carry no IDs; their content is covered through M-7, N-6, P-9, AI-9 and A-4. The "Open questions" list in REQUIREMENTS is not numbered as requirements; its items 2–5 are answered in `26-…` §B (item 2 is also decided in 01 by REC-DEC-09).

---

## 3. Coverage summary

| Status | Count | IDs |
|---|---|---|
| **Covered** | **91** | all others (F-10 since revision 3) |
| **Covered · blocked** | 4 | P-9 and AI-9 (`blocked: live-cluster`, answered from reported state) · A-4 (first internal app, `blocked: founder-decision`, 26 §B item 5) · UX-10 (Omarchy edition, `blocked: founder-decision`, Q-W11-2) |
| **Partial** | 2 | RS-1 (110 ARCHIVE-GAP sources in `SOURCES.md`, 28 of them decision-grade, regenerated by PDF5; `01`'s citation item is met only with listed exceptions; the master ledger lacks the rev-4 rows) · N-10 (Anthropic MHS has no public spec yet, so the integration is MHS-*shaped*, not MHS-conformant) |
| **Pending** | 0 | — (revision 1 had F-10 here; F-9 has moved from Partial to Covered) |
| **Total** | **97** | |

Two caveats apply to many "Covered" rows. (1) Their deciding founder tests are collected in `22-…` and scheduled in `20-…`, but none has run on real hardware yet. (2) Several P0 answers carry open items from critic pass 3 and from `01` §12 (for example the Pi 5 RAUC `tryboot` test, and the rev-4 base-OS result, which is fragile and conditional on Z-01). Those caveats are about *how strong* the answer is, not whether the requirement was traced; strength is tracked in `00-…` §5, `01-…` §12 and `23-RISK-REGISTER.md`.

---

## 4. The easily-missed IDs (brief §5), with their named homes verified

Each home was opened and the section read; "verified" means the named file answers the ID in a dedicated section, not just a passing mention.

| ID | Topic | Brief's home | Where it is answered (verified 2026-11-11) | Result |
|---|---|---|---|---|
| **P-3** | Map OneMind onto Olares's layers | 01 | **01 §8** "P-3 · OneMind mapped onto Olares's layers" (L0–L5) and **REC-DEC-15** (01 §11); also `02-competitors/MATRIX.md` §5, `olares.md` §9 | ✅ Verified |
| **P-4** | SDK / Federation | 12, 05 | **12 §11** "P-4 surfaces: SDK and Federation" (§11.1 SDK, §11.2 Federation over NATS leaf nodes and gateways), REC-W11-02, -17, -18. **05 §3.2** "Multi-site and edge frameworks" (Karmada, Liqo, KubeEdge and NATS leaf compared) answers the federation side | ✅ Verified in substance. ⚠️ 05 never writes "P-4", and its §15 trace table omits it (finding F-T2) |
| **P-6** | Machine superpowers | 11 | **11 §4** "Machine superpowers (P-6) and in-platform recommendations (A-8)", §4.1; W10-R4 | ✅ Verified |
| **A-8** | In-platform recommendations | 11 | **11 §4.2** "Recommendations (A-8)" and §5 capability detection; W10-R3, -R5 | ✅ Verified |
| **A-7** | Bundles | 11, 17 | **11 §6** "Bundles (A-7, H-4)", W10-R6; **17 §6** "Editions and pricing (… P-5, A-7)", REC-W16-04, -05, -07 | ✅ Verified |
| **H-1** | Distributor model | 11, 17 | **11 §7** "Distributor model and economics (H-1, shared with 17)"; **17 §1, §6–8** (REC-W16-01, -03, -05, -08) | ✅ Verified |
| **UX-8** | Windows and macOS clients | 12 | **12 §7.2** "Windows and macOS clients (UX-8)", REC-W11-09, -10; also 15 §1 | ✅ Verified |
| **U-3** | A child's device | 14 | **14 §2** "Putting OneMind on a child's device (U-3)" and §1; REC-W13-03…06 | ✅ Verified |
| **AI-9** | Hermes migration | 05, 10 | **05 §11** "AI-9: moving Hermes and the NATS contracts"; **10 §10** (cross-reference), REC-W9-12 | ✅ Verified (from reported state only: `blocked: live-cluster`) |
| **W-8** | Website plugin distribution | 14 | **14 §6** "Plugins and apps on the website (W-8)", REC-W13-10; also 29 REC-W19-12, 13 §7 | ✅ Verified |
| **W-9** | Competitor website stacks | 14 | **14 §5.1** "What competitors' websites run on (fingerprinted 2026-11-11)", REC-W13-09 | ✅ Verified |

---

## 5. The trace matrix: all 97 IDs

"Main recommendations" lists the ones that answer the ID most directly; Appendix A lists **every** label that names it. Where a workstream recommendation conflicts with 01, 01 wins. (Example: revision 3's REC-DEC-01 decided Debian 13 over W2-R1's Ubuntu 26.04 core; in revision 4, REC-DEC-42 makes Ubuntu 26.04 + RAUC the decision of record under the frozen scorecard protocol, conditional on Z-01, so W2-R1 and 01 now agree and REC-DEC-01 describes the Debian leg.) File numbers refer to `research-output/NN-….md`.

### 5.1 Mission (M)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| M-1 | Local-first is the moat; a OneMind cloud comes later | REC-W16-01; REC-W15-01, -05; REC-W9-10; REC-W11-12; W5-R10; REC-W19-11 | 17 §2, §13 · 16 §6 · 10 §8 · 12 §8 · 06 §8 · 29 §12 | Covered |
| M-2 | Privacy by default; users own data, identities, keys | REC-DEC-08, -11, -21; SEC-01…03, -14; W5-R4, -R9; REC-W9-10; W12-R10…R12 | 07 §1–4 · 06 §6 · 10 §5, §8 · 13 §9–11 · 01 §4.6–4.7 | Covered |
| M-3 | Combining many apps into one OS is the core goal | W12-R1; REC-DEC-15†; REC-W11-01† | 13 §3, §5, §8 · 01 §8 (L0–L5 layer model) · 12 §4 | Covered (only W12-R1 names it; F-T3) |
| M-4 | One person → family → enterprise and public safety | REC-DEC-03, -09; W5-R2, -R3, -R11; W8-R4, -R11; REC-W16-06, -08; SEC-13 | 01 §1, §4.5 · 05 §1.4, §3 · 11 §3 · 17 §6 | Covered |
| M-5 | Long-term alternative to Apple and Google | REC-W14-05…07, -10; REC-W15-06, -10 | 15 §2–10 · 16 §2.8, §6 | Covered |
| M-6 | Guard rails for one developer, no cap on the platform | REC-DEC-01, -05, -09, -17, -30, -34, -38; REC-W18-02, -04, -08, -09; W2-R2; REC-W17-01 | 01 §3 (criterion "Solo-developer operability", weight 10, frozen in `evidence/scorecard-weights.md`) · 28 §6, §8–10 · 03 §11 | Covered |
| M-7 | Robotics, drones, physical AI: the moat, from day one | REC-DEC-06, -13, -18, -19, -29, -35; W7-R1…R11; REC-W18-03; REC-W19-03, -08 | 08 (whole file) · 01 §4.1, §4.8 · 29 §11 · 28 §4 | Covered |
| M-8 | A major long-term company product | REC-DEC-12, -14, -16, -39; REC-W16-01, -10; SEC-05, -06, -17; REC-W15-12 | 07 §8 (CRA) · 17 §12–13 · 01 §4.7 · 16 §6 | Covered |

### 5.2 Product shape (P)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| P-1 | Umbrel-like home cloud that just works in a browser | REC-W11-01, -03…05, -11; REC-DEC-32 | 12 §3–5, §8.1 | Covered (T-W11-01/02 pending) |
| P-2 | A real OS front door; Backstage is too shallow | REC-W11-01, -05, -20 | 12 §4–5 · 05 §10 "Backstage's future", §12 | Covered |
| P-3 | Olares topology where optimal | REC-DEC-15; REC-MATRIX-01; W12-R8 | **01 §8** · MATRIX §5 · olares.md §9 | Covered |
| P-4 | Surfaces: Core, Dashboard, Desktop, SDK, Mobile, OS Image, Federation | REC-W11-02, -17, -18; REC-W18-06, -08; REC-W19-04; REC-DEC-41 | **12 §11** (SDK, Federation), §7, §12 · **05 §3.2** · 28 §3, §7–10 · 29 §7 | Covered (05 untagged; F-T2) |
| P-5 | Editions Lite, Pro, Super/Omni | W10-R1; REC-W16-04; W12-R1; SEC-13; REC-DEC-39 | 11 §3 · 17 §6 · 13 §3.4 · 06 §10 | Covered (first tier to ship: 26 §B item 4) |
| P-6 | Every machine has a "superpower" | W10-R4; REC-W16-04 | **11 §4** | Covered |
| P-7 | Bring your own hardware and a turnkey box | REC-DEC-20, -30, -34; W3-REC-12; W10-R6; REC-W16-01; W5-R6 | 01 §4.4 · 04 §12 (§12.2 install-path matrix) · 11 §6 · 28 §8 | Covered (release gates F1/F2, F-PI5 are founder tests) |
| P-8 | Specialised profiles (TAK node, greenhouse) | REC-DEC-04, -24 (E8); W8-R4, -R8, -R9; W7-R5; REC-W19-02; REC-W18-03, -07 | **09 §8** (§8.2 `tak-node`, §8.3 `greenhouse`) · 29 §3 · 01 §4.8 | Covered |
| P-9 | Support the founder's container/cluster structure | W3-REC-12; REC-W18-08; REC-W17-04 | 05 §9 (DOKS conversion plan), §11 · 04 §12.2 | Covered · blocked: live-cluster |

### 5.3 Apps, store and plugins (A)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| A-1 | One-click install from a library of hundreds of apps | REC-DEC-10, -15, -24 (E1); W12-R1, -R2, -R5, -R6; W10-R3; SEC-08, -11 | 13 §3–6 · 29 §6 · 01 §4.8 · 05 §4 | Covered |
| A-2 | Plug-and-play for any app, including OneMind's own | W12-R4; REC-W19-01, -04 | 13 §5 · 29 §6 | Covered |
| A-3 | Learn from and include competitors' catalogs | W12-R1, -R3, -R5; REC-FL-01 | 13 §2–4, §15 · `evidence/license-matrix.csv` | Covered |
| A-4 | Internal OneMind apps; maybe one unified app | W12-R8, -R9 | 13 §8 (scaffold specs, build order), §9–11 deep dives | Covered · blocked: founder-decision |
| A-5 | Internal plugin system, also distributed via the website | REC-DEC-24, -40, -47; REC-W19-01…04, -12; W12-R13; REC-W13-10; REC-W9-02 | 01 §4.8 (DC-16, E1–E10) · 29 §3, §6–10 · 14 §6 | Covered |
| A-6 | Community ecosystem that edits and shares plugins | REC-DEC-47; REC-W19-01, -06, -07, -13; REC-W13-10, -13; REC-MATRIX-04; W12-R6 | 29 §4, §5, §9 · 14 §9 · 13 §6 | Covered |
| A-7 | Bundles of hardware + software | W10-R6; REC-W16-04, -05, -07; REC-W19-09 | **11 §6** · **17 §6** · 29 §13 | Covered |
| A-8 | Hardware/software recommendations in the platform | W10-R3, -R5; REC-W16-05 | **11 §4.2, §5** · 17 §6 | Covered |

### 5.4 AI-native OS (AI)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| AI-1 | Everything on the OS is AI context, with permission | REC-W9-02, -10; W12-R4, -R10…R12; REC-W11-20; REC-W13-12; SEC-14 | 10 §4, §8 · 13 §9–11 · 12 §4.2 · 14 §8 | Covered |
| AI-2 | Native MCP, CLI, API, SSH and future protocols (MHS) | REC-W9-01, -02, -05; REC-DEC-15; REC-W11-02; REC-W16-09; W7-R12 | 10 §2, §4 · 01 §8 · 12 §4.2 · 08 §11.4 | Covered |
| AI-3 | Installing an app registers it for AI access | REC-W9-01, -02; REC-W19-01, -04; REC-DEC-24 (E6); W12-R4; SEC-09, -12 | 10 §4 · 13 §5.1 · 29 §6, §8.3 | Covered |
| AI-4 | An OS-level agent sets up and manages the OS | REC-DEC-07, -13; REC-W9-03, -04, -07, -08; SEC-12; W7-R11 | 10 §5, §11 · 07 §7 · 01 §4.7 | Covered |
| AI-5 | Human-in-the-loop approvals | REC-DEC-13; REC-W9-03, -06, -07; REC-W19-08; SEC-12; W7-R6, -R9, -R11, -R12 | 10 §5.3 · 07 §7 · 08 §11.1 · 29 §8.3 | Covered |
| AI-6 | Biometric structures (later) | REC-W9-11 | 10 §9 · 12 §8.1 (passkeys need HTTPS) | Covered (phased: passkeys now, opt-in face/voice later) |
| AI-7 | Embedded AI and IoT driven by AI | REC-DEC-13; REC-W9-08, -12; REC-W19-03, -05, -08; W8-R1, -R3, -R9; W7-R10 | 09 §2, §8.3 · 08 §6.3, §11.4 · 29 §11 | Covered |
| AI-8 | Local LLMs with automatic GPU detection, plus external models | REC-W9-09; REC-DEC-03, -19, -37; W12-R7; REC-W15-05 | 10 §7 · 05 §7 · 11 §5 · 13 §3.3 | Covered |
| AI-9 | Hermes agents and NATS discovery carry forward | REC-W9-12; REC-W17-04; REC-W11-18; W12-R12; W7-R10 | **05 §11** · **10 §10** | Covered · blocked: live-cluster |

### 5.5 Dashboard and user experience (UX)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| UX-1 | One unified application for everything | REC-W11-01, -03, -05 | 12 §3–5 | Covered |
| UX-2 | Fully customisable dashboard; replaces Homepage/Homarr | REC-W11-06 | 12 §3, §11.1 (widget SDK), §17 | Covered |
| UX-3 | Cloud app integrations (Strava) available to AI | REC-W9-10; REC-W11-06; W12-R10, -R11; SEC-09, -14 | 10 §8 · 13 §9 · 07 §8 | Covered |
| UX-4 | Native alert system with no external services | REC-W11-07, -08; W8-R2, -R10; REC-MATRIX-02 | 12 §6 | Covered (D-005 tension flagged in 12 §2) |
| UX-5 | Run everything from a phone app | REC-W11-09; REC-W14-05; REC-W15-06; W8-R10 | 12 §7 · 15 §1, §5, §7.3 | Covered |
| UX-6 | Many machines in one interface; cluster features; mirroring | REC-DEC-11, -28; REC-W11-15, -18; W5-R3, -R10, -R11; REC-W15-02; W10-R3, -R4 | 06 §8 · 12 §9 · 05 §3.1 | Covered |
| UX-7 | Automatic infrastructure map (later) | REC-W11-15 | 12 §9 · 05 §10 | Covered |
| UX-8 | Access from every platform, including Mac and Windows | REC-W11-01, -09…11; REC-W14-05, -07; REC-W15-06; REC-W18-09 | **12 §7** (§7.2) · 15 §1 | Covered |
| UX-9 | XR access (WebXR, Android XR) | REC-W11-11, -14 | 12 §13, §8.1 | Covered (T-W11-06 pending) |
| UX-10 | Desktop edition option on Omarchy | REC-W11-13; REC-W19-13 | 12 §12 · 29 §15 | Covered · blocked: founder-decision |

### 5.6 Users, family and security (U)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| U-1 | Multi-user; each household member gets their own space | REC-W13-01, -02; REC-W9-04; REC-W11-03; SEC-14 | 14 §1 · 10 §5.1 · 12 §5 | Covered |
| U-2 | Children can use it, including education | REC-W13-07; REC-W11-19; REC-W9-11; SEC-14 | 14 §3 · 07 §8.4 | Covered |
| U-3 | Parental controls, including OneMind on a child's device | REC-W13-01, -03…06; REC-W14-08; REC-W9-04, -06; SEC-14 | **14 §1, §2** · 15 §9.3 · 10 §5.1 | Covered |
| U-4 | Unified accounts, MFA, secrets, app isolation | REC-DEC-05, -08, -13, -20…22, -24; SEC-01, -02, -08, -09, -11; REC-W9-03…05, -08; REC-W13-01 | 07 §3–5 · 10 §5–6 · 14 §1.2 · 01 §4.7 | Covered |
| U-5 | Remote access from anywhere, private by default | REC-W11-11, -12; REC-W13-04; REC-W9-05; W8-R7 | 12 §8 · 05 §6 · 09 §5.2 | Covered |

### 5.7 Nodes, hardware and capability detection (N)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| N-1 | Everything is a node | W10-R1, -R2, -R4; W8-R1, -R3; W7-R7; REC-W14-01, -02 | 08 §5.4 · 11 §3–5 · 09 §2 | Covered |
| N-2 | Runs on Pis, CPU-only PCs, GPU boxes, edge devices, sensors | REC-DEC-42, -01, -06, -18, -33, -44; REC-W18-02; W10-R1; W8-R4 | 01 §1, §4.1 · 03 §10 · 05 §1.4 · 11 §3 | Covered |
| N-3 | Hardware capability auto-detection | W10-R2, -R3; W12-R4; W7-R13; REC-W15-09 | 11 §5 · 05 §8 · 29 §6 | Covered |
| N-4 | QR-code onboarding for robots and IoT | REC-W11-16; W8-R6; REC-W13-04; REC-W14-08 | 12 §10 · 29 §11 · 09 §1 (FDO zero-touch) | Covered (T-W11-08 pending) |
| N-5 | Cloud, local, edge and hybrid modes | REC-W11-18; REC-W19-11† | 05 §3, §9 · 12 §11.2 · 29 §12 | Covered |
| N-6 | Native mesh networking, cloud optional | REC-DEC-09, -27; W8-R2, -R7, -R8, -R10; REC-W15-01, -02; SEC-15 | 09 §5 · 05 §6 · 16 §6 | Covered |
| N-7 | Built for robotics, drones, physical AI and simulation | REC-DEC-13, -19, -29; W7-R8; REC-W18-03, -09, -11; W10-R8 | 08 §5–7, §11–12 · 28 §9 (Isaac Sim on cloud/RTX) | Covered |
| N-8 | NVIDIA as a major partner | REC-DEC-03, -19, -37; W7-R2, -R13; REC-W9-09; REC-W16-09; W10-R8 | 05 §7 · 08 §2–4, §12 · 17 §10 · 11 §8 | Covered |
| N-9 | Native Kubernetes (k3s) or Docker-only? | REC-DEC-09, -10, -22, -23, -28, -38 | **05 §1–2** · 01 §3.3, §4.5 | Covered (REQUIREMENTS open question 2 answered) |
| N-10 | MHS for edge/IoT context and control | W7-R12; REC-W16-09; "MHS-shaped device registry" (10 §16) | 08 §11.4 · 10 §2.2 · 29 §6 (E6 `exposure.mhs`) | **Partial** (no public MHS spec yet) |

### 5.8 Updates, support and reliability (R)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| R-1 | Solid, safe updates, when the user wants | REC-DEC-05, -07, -08, -20, -23, -26, -30…32, -34, -45; W3-REC-01, -04, -05, -07…09; SEC-05 | 01 §3.2, §4.2–4.3 · 04 §7–11 · 07 §6 | Covered (release gates F1/F2, F-PI5, F-SB-1…3 are founder tests) |
| R-2 | A good support system | REC-W13-11, -12; REC-W16-01, -06; REC-W11-04; REC-DEC-07, -11; W5-R1…R9 | 14 §7 · 17 §7 · 06 §9 · 12 §4.1 (rescue console) | Covered |
| R-3 | Long-term maintainability of hardware OneMind sells | REC-DEC-42, -01, -12, -16, -17, -18, -31, -37, -39, -49; REC-W18-02, -04, -05; W7-R1; SEC-04, -06, -07 | 01 §4.1, §4.7 · 03 §6 · 08 §2 · 28 §6 · 07 §8 | Covered |

### 5.9 Hardware business (H)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| H-1 | Sell hardware; become the main distributor of OneMind boxes | REC-W16-01, -03, -05, -08; W10-R7; REC-DEC-02, -14, -39 | **11 §7** · **17 §1, §6–8** · 07 §8 | Covered (first tier and segment: 26 §B item 4) |
| H-2 | Custom-built boxes, documented; what competitors' boxes run | W10-R7 | 11 §2–3 · `02-competitors/` hardware sections | Covered |
| H-3 | Simple to powerful tiers, incl. GPU, robotics, NVIDIA builds | W10-R1; REC-DEC-32, -33; REC-W16-04; REC-W18-02; W8-R5 | 11 §3 · 01 §1 | Covered |
| H-4 | Bundles and an OEM path | REC-W16-03, -07; W10-R6, -R9; SEC-04 | 17 §8 · 11 §6, §8 | Covered |

### 5.10 Website and community (W)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| W-1 | Blog, news, resources, education, partners, community | REC-W13-09; REC-W17-07 | 14 §5 | Covered |
| W-2 | Education via Circle.so | REC-W13-08; REC-W17-07 | 14 §4 · 17 §9 | Covered |
| W-3 | OS download page and documentation | REC-W13-09, -12; REC-W16-03 | 14 §5, §8 | Covered |
| W-4 | Hardware sales/cart and affiliate links | REC-W13-09, -15; REC-W16-03 | 14 §5 | Covered |
| W-5 | Forms via Zoho Forms | REC-W13-11, -14 | 14 §5.2 | Covered |
| W-6 | Support desk | REC-W13-11 | 14 §7 | Covered |
| W-7 | Possibly a headless API/CMS | REC-W13-09 | 14 §5.2 | Covered |
| W-8 | Plugin/app distribution on the website | REC-W13-10; REC-W19-12; W12-R13 | **14 §6** · 29 §15 · 13 §7 | Covered |
| W-9 | What competitors' websites run on | REC-W13-09 | **14 §5.1** | Covered |

### 5.11 Research mandate (RS)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| RS-1 | No guessing: research, cite, find patterns | REC-W17-06; W12-R14; REC-DEC-42 (scorecard protocol applied as frozen); the claims ledger | every file's claim IDs · `evidence/claims/` · [`SOURCES.md`](SOURCES.md) · `evidence/critic/pass-3.md`, `cit4-mapping.md` · 01 §3.1.6 | **Partial** (110 ARCHIVE-GAP sources, per `SOURCES.md` as regenerated by PDF5; 01's §9 citation item met with listed exceptions; master `claims.csv` lacks the 171 rev-4 rows) |
| RS-2 | Reverse-engineer the competitors | REC-FL-01; REC-W17-06; W12-R3 | `02-competitors/` (teardowns + `MATRIX.md`) | Covered |
| RS-3 | Review Olares built-ins (Desktop, Files, Vault, Market, Wise, Settings, Control Hub, Studio) | — (research task, no product recommendation needed) | `02-competitors/olares.md` §3.12 · `research/competitors/olares.md` §2 | Covered |
| RS-4 | Survey all relevant Linux distributions | REC-DEC-42, -01, -17, -46; W2-R1, -R7; REC-MATRIX-08 | 03 §3–5, §9, §12 · 01 §3.1.6 · `MATRIX.md` | Covered |
| RS-5 | Review the founder-flagged repos | REC-FL-01 | `02-competitors/flagged-repos.md` | Covered |
| RS-6 | Ask Zeus for source code if needed | — (rule 8 substitution: listed, not asked) | 26 §D and its revision-2 RS-6 list | Covered |
| RS-7 | Document everything in this repo | REC-W17-01 | the whole `research-output/` tree, including this file | Covered |

### 5.12 Platform ambition (F)

| ID | Requirement (short) | Main recommendations | Where addressed | Status |
|---|---|---|---|---|
| F-1 | Built for the next 5–10 years of physical AI | REC-DEC-16; W2-R4, -R6; REC-W15-03, -12; REC-W17-05 | 08 §1, §12 · 16 §4–7 | Covered |
| F-2 | Keep pace with NVIDIA, stay hardware-agnostic | REC-DEC-03, -18, -19, -37; W7-R1, -R2, -R13; REC-W15-04, -09; REC-W18-01 | 05 §7–8 · 08 §11.5, §12 · 11 §9 | Covered (KubeCon NA 2026 day 3–4 re-check open: critic N12) |
| F-3 | "Connect a robot → use OneMind", plug and play | REC-W19-03, -05, -08; REC-W11-16; REC-DEC-24; W7-R8, -R12; W8-R6 | 29 §11 · 08 §11 · 12 §10 | Covered |
| F-4 | Supersede the other OSes; be the default | REC-W19-07, -09; REC-W16-07; REC-W18-06; REC-W15-10; W7-R8 | 29 §13 · 16 §3 · 17 §8 | Covered |
| F-5 | Third-party ecosystem: SDK, certification, distribution, revenue | REC-DEC-10, -24, -40; REC-W19-01, -07, -09, -10; REC-W16-02, -07; W12-R4, -R6 | 29 §13–14 · 01 §4.8 · 17 §2 | Covered |
| F-6 | Self-hosted mixed with cloud, hybrid by design | REC-W19-11; REC-W9-01; REC-W11-12, -18; REC-W16-01; W7-R10 | 29 §12 · 05 §3.2 · 12 §11.2 | Covered |
| F-7 | Evaluate owning the kernel and/or the image | REC-DEC-12, -25, -46, -48; REC-W18-01…04, -06, -07; W7-R3, -R5; W2-R7 | **28 §3–6** · 01 §3.5 | Covered |
| F-8 | Dev toolchain from the Mac, plus CI | REC-W18-07, -09…11; REC-W17-02; REC-DEC-25 | 28 §9–10 · 27 (module L0) | Covered |
| F-9 | Two-phase execution: this run produces the build brief | REC-B30-01, -15; REC-PLAN-07; REC-W18-08; REC-W17-01, -08 | **`30-NEXT-ULTRACODE-BUILD-BRIEF.md`** (whole file; §14 trace) · 20 §2–4 (gates the build runs against) · 01 (the decided core) | Covered (30 builds both base legs; its default base still reads rev. 3 until its owner applies `01` rev. 4, a follow-up listed in 01 §11) |
| F-10 | Final PDF report for the founder | — (no recommendation label; the deliverable is the answer, F-T1) | **`ONEMIND-OS-FOUNDATION-REPORT.pdf`**, 111 pages (rev. 4.1 build), and its source `report/` (chapters, diagrams, `verify_pdf.py`, `checklist.tsv`) | **Covered** (rebuilt from `01` rev. 4.1 after this sync; revision 2 had it Partial while the PDF still showed rev. 3) |
| F-11 | IoT and IIoT without limitations | REC-DEC-04, -27, -29, -49; W8-R1, -R5, -R6, -R11; REC-W18-03, -05; W3-REC-08, -10, -13 | **09 §1–4** · 01 §6.11 · 03 §9 | Covered |
| F-12 | Full, fair evaluation of Fedora IoT and the Red Hat edge lineage | REC-DEC-04, -27, -33, -42, -44, -49; W2-R3, -R4; W3-REC-13; W8-R5 | **03 §9** (§9.5 steelman) · 01 §3.1.6, §5.1, §6.1, §6.14 (rev-4 bootc steelman) · `evidence/lab/` (Fedora bootc spike) | Covered (bootc is the protocol's runner-up, 64 vs 65. Founder test W2-HW-3, now before gate G1, feeds the pre-registered map: if it fails the base goes to Debian; if Canonical refuses and the debranded rebuild is rejected, to bootc. Industrial profile on AlmaLinux 10 / RHEL 10 image mode: REC-DEC-44, -49) |
| F-13 | Community-scale resilience; study VillageOS | W8-R2, -R7, -R9, -R12; REC-W15-01, -02; REC-W16-08; REC-W13-07 | 09 §5, §9 · `02-competitors/villageos.md` · 16 §3 | Covered |
| F-14 | One OS, simple at every scale, Pi to enterprise | REC-DEC-42, -01, -06, -09, -17, -22, -33, -38, -44; W10-R1, -R2; REC-W11-01, -05, -13; W5-R1…R3 | 01 §1, §3 · 05 §1.4 · 03 §10 · 09 §8.1 | Covered |
| F-15 | Compare kernel families before committing to Linux | REC-W18-01; REC-W14-10 | **28 §2** · 15 §10 (HarmonyOS) | Covered |

---

## 6. Findings: gaps and defects in the trace

| # | Finding | Evidence | Who should act |
|---|---|---|---|
| **F-T1** | **Three IDs have no recommendation label at all:** RS-3, RS-6 and F-10. RS-3 and RS-6 are research-process requirements met by documents (olares.md §3.12; 26 §D), so no product recommendation is needed. F-10 is met by a document too: the PDF, 111 pages (rev. 4.1 build), rebuilt from `01` rev. 4.1, but no recommendation names F-10. | Appendix A rows for RS-3, RS-6, F-10 | PDF owner (F-10): none open (rebuilt from rev. 4.1); a recommendation label is optional |
| **F-T2** | **P-4's second named home (05) answers it without saying so.** 05 §3.2 compares the federation frameworks, but 05 never writes "P-4" and its §15 trace table omits it. | `05-…` §3.2, §15 | W4 owner: add a `P-4 \| §3.2` row to 05 §15 |
| **F-T3** | **M-3, "the core goal", is named by only one recommendation** (W12-R1, a seed-catalogue rec). The layer model (REC-DEC-15) and the unified front door (REC-W11-01) serve it but do not list it. Not a coverage hole, but a reader scanning by ID would underrate it. | Appendix A, M-3 row | 01 and 12 owners: add M-3 to REC-DEC-15 and REC-W11-01 |
| **F-T4** | **Two recommendations carry no requirement ID**, against brief rule 6: **W10-R11** (buy a Pi 5 and a Jetson Orin Nano Super by 2026-11-16; tagged only D-002, D-004, D-006) and **REC-W14-03** (run the GrapheneOS + ATAK test; tagged only Q298). Suggested IDs: W10-R11 → N-2, N-8, H-3; REC-W14-03 → UX-5, M-5. | `11-…` line with W10-R11; `15-…` §1 | W10 and W14 owners |
| **F-T5** | **Workstream recommendations that 01 overrides are still worded as live.** Revision 1's clearest case has reversed: 03 W2-R1 put the core on Ubuntu 26.04 while REC-DEC-01 decided Debian 13; under `01` rev. 4, REC-DEC-42 makes Ubuntu 26.04 + RAUC the decision of record, 03 already says so (W2-R2 now points to the pre-registered map), and REC-DEC-01 is marked superseded. The remaining overrides are in files whose owners `01` §11 lists as follow-ups (00, 20, 22, 30, the PDF). This matrix follows 01. | 03 §13; 01 §11 | Owners named in 01 §11 |
| **F-T6** | **Closed (revision 2).** Revision 1 found that tests and plans were routed to `20-…`, `21-…`, `22-…`, `24-…` and `30-…`, which did not exist. All five exist now: 22 holds every founder test the DCs name, and 20 schedules them against gates G0–G7. The "Covered" status for R-1, P-1, P-7, N-4, UX-9 and F-12 still depends on tests that have not run on hardware. | 20, 22; critic pass 3 Part 2 | none |
| **F-T7** | **Decision IDs are mixed into "Serves" lists.** D-001…D-006 appear beside requirement IDs in most file headers. That is fine as long as readers know they are not part of the 97; this file does not count them. | Headers of 03–17, 26–29 | none (documented here) |
| **F-T8** | **Narrow requirements have few labels, by design.** IDs named by only one or two labels: M-3, P-6, A-2, A-4, AI-6, UX-2, UX-7, UX-9, UX-10, N-5, N-10, H-2, W-1, W-2, W-5, W-6, W-7, W-9, RS-5, RS-7, F-15. Each has a dedicated section, so this is not a gap; it marks where a single file is the only home. | Appendix A, "#" column | none |

---

## 7. What competitors do (keeping requirements tied to checks)

A trace table is only as good as the discipline that keeps it current. The proven ecosystems OneMind studies do not keep requirements in prose; they turn them into **rules a tool enforces**, so a missing item fails a check instead of being forgotten.

| Project | How a written requirement becomes an enforced check | Evidence | Their constraints | Constraint fit for OneMind's trace |
|---|---|---|---|---|
| **Home Assistant** | The integration quality scale is a rule list enforced by the `hassfest` tool in CI: 54 rules in four tiers (Bronze 20, Silver 10, Gold 21, Platinum 3) | [C-W12-014] | Large community, Python integrations, many maintainers | **High** for the pattern "requirements as a machine-checked list"; OneMind copies the idea, not the code |
| **Olares** | The OAC linter checks every Market app before listing: folder layout, manifest validation, Helm dry-run, no host networking, namespace and limits checks, RBAC inspection | [C-TD-olares-028] | k3s + Helm app format, funded company team | **High**: same k3s/Helm world; the same "lint before publish" gate fits a trace check in OneMind's CI |
| **Omarchy** | `omarchy plugin validate` runs the same checks the shell runs at load time, against a manifest with `schemaVersion`, `id`, `kinds` and `entryPoints` | [C-W11-050] | Single-user desktop, unsandboxed plugins, one lead maintainer | **Medium**: the "one validator everywhere" idea fits a solo developer; the trust model does not |
| **umbrelOS** | The app manifest has a typed schema (`umbrel-app.yml`: permissions, widgets, implements, backupIgnore) checked by umbreld | [C-W12-013] | Docker, PolyForm-Noncommercial licence (study only), small team | **Medium**: schema-first manifests, pattern only |

**Lesson for OneMind:** keep `docs/REQUIREMENTS.md` IDs machine-readable and fail CI when an ID has no recommendation or a recommendation has no ID (REC-TRACE-01). This file was produced that way (§9); the next step is to make it a gate, so the build session (F-9) cannot drop a requirement silently.

---

## 8. Recommendations (with requirement IDs)

| ID | Recommendation | Requirement IDs |
|---|---|---|
| **REC-TRACE-01** | Add a traceability check to the repo's CI in the build session: parse `docs/REQUIREMENTS.md` for IDs, parse every recommendation table for ID columns (with range expansion such as `F-3…F-6`), and fail when an ID has zero recommendations or a recommendation has zero IDs. Today's run would still fail on F-10 (no label) and on W10-R11 and REC-W14-03 (F-T1, F-T4). | RS-1, RS-7, M-6, F-9 |
| **REC-TRACE-02** | Ask the owners of 05, 01, 12, 11, 15 and 03 to fix the labelling defects F-T2 to F-T5 in their own files (P-4 row in 05 §15; M-3 on REC-DEC-15 and REC-W11-01; IDs on W10-R11 and REC-W14-03; mark W2-R1 superseded). This file does not edit them. | P-4, M-3, RS-1 |
| **REC-TRACE-03** | When `20-…`, `22-…`, `24-…` and `30-…` land, re-run this trace and move each founder test from "named in a workstream file" to "scheduled in 20/22", and F-9 from Partial to Covered once 30 exists. *(Revision 2: done for F-9, F-10 and F-T6. Still open: a full re-scan of Appendix A so it indexes the labels of 20–24 and 30, see §9.)* | F-9, R-1, P-7, RS-7 |
| **REC-TRACE-04** | Make the PDF's section 13 (glossary and sources) cite this matrix and `SOURCES.md`, so the founder's report carries the same requirement-to-answer map. | F-10, RS-1 |

---

## 9. Method and limits

1. **IDs:** extracted from `docs/REQUIREMENTS.md` table rows (pattern: family prefix, hyphen, number, at the start of a table row). 97 found; none duplicated.
2. **Mentions:** every `.md` file at the top of `research-output/` and in `02-competitors/` was scanned line by line. An ID matches only when it is not part of a longer token (so `P-3` inside `Q-P2-3` or `UX-1` inside `UX-10` does not count). Ranges written as `F-3…F-6`, `F-1..F-14`, `UX-1–10` or `REC-W11-01…05` were expanded.
3. **Recommendations:** a line counts as a recommendation for an ID when it is a table row whose first cell is a recommendation label (or a bold `**W7-R2:**`-style bullet) and the line contains the ID. Labels that are not recommendations were excluded: P0 conclusions (`P0-#`), extension points (`E#`), tests (`T-…`), failure reports (`F#`), risks (`RR-#`), questions, claim IDs and decisions. Requirement-keyed trace tables (05 §15, 12 §20, 14 §12, 15 §14, 29 §19) were read by hand and merged into §5.
4. **Sections:** every anchor in §4 and §5 was checked against the file's heading list on 2026-11-11.
5. **Statuses** were assigned by reading the answering sections and the file's own open-items section, not by counting labels.
6. **Limits:** the matrix is a snapshot. Other agents were writing deliverables while it was built (`23-RISK-REGISTER.md` appeared mid-run). Section numbers can shift when files are revised; the IDs and labels are the stable keys. A label match shows that a recommendation *names* an ID; whether the recommendation is *right* is the job of the refuters and critics, not of this file.
7. **Revision 2 (2026-11-11, after `01` rev. 4) was a targeted sync, not a full re-scan.** By hand: the F-9 and F-10 rows (both tables), the coverage counts, REC-DEC-42…49 added to every ID they name (Appendix A counts and the "01" file column updated by script; main-matrix cells only where the rec answers the ID most directly), and findings F-T1, F-T5 and F-T6. **Not re-scanned:** the labels of `20-…` (REC-PLAN), `21-…`, `22-…`, `24-…` and `30-…` (REC-B30) are indexed in Appendix A only for F-9; the "Top-level files" column is unchanged except for F-9, F-10 and the rows that gained a REC-DEC label. A full re-scan would raise label counts but cannot lower coverage, so no status depends on it.

---

## 10. Appendix A: machine index of every recommendation label per ID

Generated from the scan in §9 on 2026-11-11. "#" is the number of distinct labels; "Top-level files" are the `NN-` prefixes of files that mention the ID anywhere; "Teardowns" counts `02-competitors/*.md` files that mention it (their own `REC-TD-*`, `REC-TDC-*`, `REQ-*` labels are teardown lessons and are not listed here). Labels are grouped by family: `REC-DEC-08, 11` means REC-DEC-08 and REC-DEC-11.

| ID | Recommendation labels that name this ID | # | Top-level files that mention it | Teardowns |
|---|---|---|---|---|
| M-1 | REC-W11-08, 12; REC-W13-07, 08; REC-W15-01, 05; REC-W16-01, 10; REC-W19-11; REC-W9-10; SEC-14; W5-R10 | 12 | 06, 07, 10, 12, 14, 16, 17, 29 | 5 |
| M-2 | REC-DEC-08, 11, 20, 21, 22, 25, 28, 36, 47, 48; REC-FL-02, 03, 04; REC-W11-08, 11; REC-W13-03, 06, 10, 13, 14; REC-W14-01; REC-W15-05, 07, 08, 10; REC-W16-10; REC-W9-10; SEC-1, 2, 3, 14, 17; W10-R5; W12-R10, 11, 12; W3-REC-7, 9, 11; W5-R4, 9, 10, 14; W7-R9 | 44 | 01, 04, 06, 07, 08, 10, 11, 12, 13, 14, 15, 16, 17, 23 | 13 |
| M-3 | W12-R1 | 1 | 13 | 1 |
| M-4 | REC-DEC-03; REC-W11-19; REC-W14-01, 08; REC-W16-06, 08; SEC-13; W2-R3; W5-R2, 3, 11; W8-R4, 11 | 13 | 01, 03, 05, 06, 07, 09, 11, 12, 14, 15, 16, 17, 23 | 2 |
| M-5 | REC-W14-05, 06, 07, 10; REC-W15-06, 10; W5-R14 | 7 | 06, 10, 15, 16 | 0 |
| M-6 | REC-DEC-01, 05, 09, 17, 30, 31, 34, 38, 41, 42, 49; REC-RISK-01, 05; REC-W15-11; REC-W16-08; REC-W17-01; REC-W18-02, 04, 08, 09; REC-W9-07; SEC-10; W10-R7; W12-R5, 9; W2-R2; W3-REC-1, 2; W5-R1 | 29 | 00, 01, 03, 04, 05, 06, 07, 10, 11, 13, 16, 17, 23, 27, 28, 29 | 12 |
| M-7 | REC-DEC-01, 06, 18, 19, 26, 29, 35, 36, 49; REC-MATRIX-07; REC-W11-14; REC-W15-04; REC-W16-07; REC-W17-05; REC-W18-01, 03, 11; SEC-16; W10-R8; W12-R9; W2-R1; W3-REC-3; W7-R1, 2, 4, 5, 6, 8, 9, 11 | 30 | 00, 01, 03, 04, 05, 07, 08, 09, 11, 12, 13, 16, 17, 23, 27, 28, 29 | 12 |
| M-8 | REC-DEC-12, 14, 16, 39; REC-MATRIX-06; REC-RISK-01, 04; REC-W15-07, 08, 12; REC-W16-01, 10; REC-W17-01; REC-W18-06; SEC-5, 6, 17; W2-R6; W3-REC-1 | 19 | 01, 03, 04, 07, 16, 17, 23, 26, 27, 28 | 15 |
| P-1 | REC-DEC-32; REC-W11-01, 03, 04, 05, 11 | 6 | 01, 07, 12 | 7 |
| P-2 | REC-W11-01, 05, 20 | 3 | 05, 12, 13 | 2 |
| P-3 | REC-DEC-15; REC-MATRIX-01; W12-R8 | 3 | 01, 13 | 2 |
| P-4 | REC-DEC-31, 41; REC-W11-02, 17, 18; REC-W18-06, 08; REC-W19-04 | 8 | 01, 12, 28, 29 | 0 |
| P-5 | REC-DEC-39; REC-FL-04; REC-W16-04; SEC-13; W10-R1; W12-R1; W2-R1 | 7 | 01, 03, 05, 06, 07, 11, 13, 17 | 1 |
| P-6 | REC-W16-04; W10-R4 | 2 | 11, 17 | 2 |
| P-7 | REC-DEC-20, 30, 34; REC-W16-01; REC-W18-08; SEC-1, 3; W10-R6; W3-REC-12; W5-R6 | 10 | 01, 03, 04, 06, 07, 11, 16, 17, 23, 28 | 14 |
| P-8 | REC-DEC-04, 24, 47; REC-W14-02, 04; REC-W18-03, 07; REC-W19-02; W10-R6; W12-R1; W2-R3; W3-REC-12; W7-R5; W8-R4, 8, 9 | 16 | 01, 03, 04, 05, 06, 08, 09, 11, 12, 13, 15, 28, 29 | 5 |
| P-9 | REC-RISK-03; REC-W17-04; REC-W18-08; W3-REC-12 | 4 | 01, 04, 05, 23, 27, 28 | 1 |
| A-1 | REC-DEC-10, 15; REC-MATRIX-01; SEC-8, 11; W10-R3; W12-R1, 2, 5, 6; W5-R5 | 11 | 01, 05, 06, 07, 11, 13, 17, 29 | 25 |
| A-2 | W12-R4 | 1 | 13, 29 | 11 |
| A-3 | REC-FL-01; W12-R1, 3, 5 | 4 | 13 | 6 |
| A-4 | W12-R8, 9 | 2 | 13, 23 | 0 |
| A-5 | REC-DEC-10, 24, 40, 47; REC-FL-05, 06; REC-W11-17; REC-W13-10; REC-W15-09; REC-W16-02; REC-W19-01, 02, 04, 12; REC-W9-02; SEC-10, 11; W12-R13; W5-R5; W8-R1, 3 | 21 | 00, 01, 05, 06, 07, 09, 10, 12, 13, 14, 16, 17, 23, 29 | 19 |
| A-6 | REC-DEC-24, 40, 47; REC-FL-05; REC-MATRIX-04; REC-W11-17; REC-W13-10, 13; REC-W16-02; REC-W19-01, 04, 06, 07, 13; REC-W9-02; SEC-10, 11; W12-R6; W8-R3 | 19 | 00, 01, 07, 09, 10, 12, 13, 14, 17, 23, 29 | 17 |
| A-7 | REC-W13-07; REC-W16-04, 05, 07; REC-W19-09; W10-R6; W8-R4 | 7 | 09, 11, 14, 17, 29 | 2 |
| A-8 | REC-W16-05; W10-R3, 5 | 3 | 11, 17 | 5 |
| AI-1 | REC-FL-03; REC-W11-20; REC-W13-12; REC-W9-02, 10; SEC-14; W12-R4, 10, 11, 12 | 10 | 07, 10, 12, 13, 14, 23, 29 | 10 |
| AI-2 | REC-DEC-15; REC-FL-06, 07; REC-MATRIX-05; REC-W11-02; REC-W16-09; REC-W9-01, 02, 05; W7-R12 | 10 | 01, 08, 10, 12, 17, 23 | 15 |
| AI-3 | REC-DEC-24; REC-FL-06; REC-W11-02; REC-W19-01, 04; REC-W9-01, 02; SEC-9, 12; W12-R4 | 10 | 01, 07, 10, 12, 13, 29 | 8 |
| AI-4 | REC-DEC-07, 13, 45; REC-FL-03, 06; REC-MATRIX-05; REC-W11-20; REC-W9-03, 04, 07, 08; SEC-12; W2-R5; W3-REC-4, 5; W5-R7, 8, 13; W7-R11 | 19 | 01, 03, 04, 06, 07, 08, 10, 12, 23 | 19 |
| AI-5 | REC-DEC-13, 24, 40; REC-MATRIX-05; REC-W11-20; REC-W13-03; REC-W19-08; REC-W9-03, 06, 07; SEC-12; W12-R10, 11, 12; W7-R6, 9, 11, 12; W8-R9 | 19 | 01, 07, 08, 09, 10, 12, 13, 14, 23, 29 | 21 |
| AI-6 | REC-W9-11 | 1 | 10, 12, 23 | 0 |
| AI-7 | REC-DEC-13; REC-W19-03, 05, 08; REC-W9-08, 12; SEC-12; W2-R3; W7-R10; W8-R1, 3, 9 | 12 | 01, 03, 07, 08, 09, 10, 29 | 2 |
| AI-8 | REC-DEC-03, 19, 37; REC-W15-05; REC-W9-09; W12-R7 | 6 | 01, 05, 10, 13, 16, 23 | 6 |
| AI-9 | REC-W11-18; REC-W17-04; REC-W9-12; W12-R12; W7-R10 | 5 | 01, 05, 08, 10, 12, 13, 23, 27 | 1 |
| UX-1 | REC-W11-01, 03, 05 | 3 | 12, 13 | 1 |
| UX-2 | REC-W11-06 | 1 | 12 | 1 |
| UX-3 | REC-W11-06; REC-W9-10; SEC-9, 14; W12-R10, 11 | 6 | 07, 10, 12, 13, 23 | 0 |
| UX-4 | REC-MATRIX-02; REC-W11-07, 08; W8-R2, 10 | 5 | 05, 09, 12, 13, 23 | 8 |
| UX-5 | REC-W11-09; REC-W14-05; REC-W15-06; W8-R10 | 4 | 09, 12, 15, 16 | 1 |
| UX-6 | REC-DEC-11, 28; REC-W11-15, 18; REC-W15-02; W10-R3, 4; W5-R3, 10, 11 | 10 | 01, 05, 06, 11, 12, 16, 23 | 19 |
| UX-7 | REC-W11-15 | 1 | 05, 12 | 1 |
| UX-8 | REC-FL-07; REC-W11-01, 09, 10, 11; REC-W14-05, 07; REC-W15-06; REC-W18-09 | 9 | 12, 15, 16, 23, 28 | 1 |
| UX-9 | REC-W11-11, 14 | 2 | 12 | 0 |
| UX-10 | REC-W11-13; REC-W19-13 | 2 | 12, 29 | 0 |
| U-1 | REC-W11-03; REC-W13-01, 02; REC-W9-04; SEC-14; W12-R10 | 6 | 06, 07, 10, 12, 13, 14 | 9 |
| U-2 | REC-W11-19; REC-W13-07; REC-W9-11; SEC-14 | 4 | 07, 10, 12, 14, 23 | 2 |
| U-3 | REC-W13-01, 03, 04, 05, 06; REC-W14-08; REC-W9-04, 06, 11; SEC-14 | 10 | 07, 10, 12, 13, 14, 15, 23 | 5 |
| U-4 | REC-DEC-05, 08, 13, 20, 21, 22, 24, 27, 35, 36, 40, 45, 47; REC-FL-02, 03, 07; REC-MATRIX-04, 05; REC-W13-01; REC-W17-03; REC-W18-10; REC-W19-02, 03, 05, 06; REC-W9-03, 04, 05, 08; SEC-1, 2, 8, 9, 11; W3-REC-6, 7; W5-R4, 12, 13; W8-R3 | 40 | 01, 04, 06, 07, 09, 10, 14, 23, 26, 27, 28, 29 | 24 |
| U-5 | REC-RISK-03; REC-W11-11, 12; REC-W13-04; REC-W9-05; W8-R7 | 6 | 05, 07, 09, 10, 12, 14, 16, 23 | 3 |
| N-1 | REC-W14-01, 02, 09, 10; W10-R1, 2, 4; W7-R7; W8-R1, 3 | 10 | 01, 03, 08, 09, 11, 15, 23 | 6 |
| N-2 | REC-DEC-01, 06, 18, 33, 35, 44; REC-W13-02; REC-W15-03; REC-W18-02, 07; W10-R1; W2-R1; W3-REC-3; W8-R4 | 14 | 01, 03, 04, 05, 08, 09, 11, 14, 16, 23, 28 | 7 |
| N-3 | REC-W15-09; W10-R2, 3; W12-R4; W7-R13 | 5 | 05, 08, 11, 13, 16, 23, 29 | 7 |
| N-4 | REC-W11-16; REC-W13-04; REC-W14-08; W8-R6 | 4 | 01, 04, 05, 07, 08, 09, 12, 14, 15, 23, 29 | 4 |
| N-5 | REC-W11-18 | 1 | 05, 12, 16 | 2 |
| N-6 | REC-DEC-09, 27; REC-W14-04; REC-W15-01, 02; REC-W17-04; REC-W19-11; SEC-15; W3-REC-8, 10; W5-R10; W7-R10; W8-R2, 7, 8, 10 | 16 | 01, 04, 05, 06, 07, 08, 09, 15, 16, 23, 27, 29 | 10 |
| N-7 | REC-DEC-13, 29, 36; REC-MATRIX-07; REC-W11-07; REC-W15-04; REC-W17-05; REC-W18-03, 09, 11; SEC-12, 16; W10-R8; W2-R1; W7-R8 | 15 | 01, 03, 05, 07, 08, 11, 12, 16, 23, 27, 28, 29 | 7 |
| N-8 | REC-DEC-03, 19, 37; REC-W16-09; REC-W17-05; REC-W18-01; REC-W9-09; W10-R8; W2-R1; W3-REC-3; W7-R2, 13 | 12 | 01, 03, 04, 05, 08, 10, 11, 17, 23, 27, 28 | 8 |
| N-9 | REC-DEC-09, 10, 22, 23, 28, 38, 45, 49; REC-W17-04; REC-W18-01; W12-R5; W3-REC-4; W7-R7 | 13 | 00, 01, 04, 05, 08, 13, 23, 26, 27, 28 | 7 |
| N-10 | REC-W16-09; W7-R12 | 2 | 08, 09, 10, 17, 23, 29 | 0 |
| R-1 | REC-DEC-05, 07, 08, 14, 20, 21, 23, 26, 30, 31, 32, 34, 35, 36, 45; REC-FL-03; REC-MATRIX-01, 02, 03, 04; REC-RISK-02; REC-W11-04; REC-W15-01; REC-W16-06; REC-W17-03; REC-W18-04, 07, 10; REC-W19-02, 06; SEC-1, 5; W2-R3, 5; W3-REC-1, 4, 5, 7, 8, 9; W5-R2, 8; W7-R4; W8-R11 | 44 | 00, 01, 03, 04, 05, 06, 07, 08, 09, 10, 12, 16, 17, 23, 26, 27, 28, 29 | 27 |
| R-2 | REC-DEC-07, 11, 23, 28, 32, 38, 45, 49; REC-FL-02; REC-MATRIX-02, 06; REC-RISK-06; REC-W11-04, 07; REC-W13-11, 12, 13; REC-W16-01, 06; REC-W18-10; SEC-5, 6; W10-R7, 10; W12-R6; W3-REC-4, 5, 9, 11; W5-R1, 2, 4, 5, 7, 9; W8-R2 | 36 | 01, 04, 06, 07, 09, 11, 12, 13, 14, 17, 23, 28 | 22 |
| R-3 | REC-DEC-01, 02, 05, 08, 12, 14, 16, 17, 18, 20, 25, 26, 31, 34, 37, 39, 41, 42, 43, 46, 48, 49; REC-FL-02, 03, 05; REC-MATRIX-01, 03, 04, 06; REC-RISK-01; REC-W13-05; REC-W15-01, 03, 07, 11; REC-W16-06, 10; REC-W17-03; REC-W18-02, 04, 05; SEC-1, 4, 6, 7, 17; W10-R8, 9, 10; W12-R2; W2-R1, 2, 6; W3-REC-1, 2, 6; W5-R1, 6; W7-R1, 3, 11; W8-R5, 11 | 63 | 00, 01, 03, 04, 05, 06, 07, 08, 09, 11, 13, 14, 16, 17, 23, 26, 27, 28 | 25 |
| H-1 | REC-DEC-02, 14, 39, 43; REC-FL-02, 04; REC-W15-07, 08; REC-W16-01, 03, 05, 08; REC-W18-05, 10; SEC-3, 4, 6, 7, 15; W10-R7; W12-R2; W2-R2; W3-REC-6, 7, 12; W5-R6; W7-R1, 3; W8-R5 | 29 | 01, 03, 04, 06, 07, 08, 09, 11, 13, 16, 17, 23, 26, 28 | 15 |
| H-2 | W10-R7 | 1 | 11, 23 | 5 |
| H-3 | REC-DEC-32, 33, 44; REC-RISK-04; REC-W15-03, 04; REC-W16-04; REC-W18-02; W10-R1; W2-R1; W3-REC-6; W8-R5 | 12 | 01, 03, 04, 08, 09, 11, 16, 17, 23, 28 | 3 |
| H-4 | REC-W16-03, 07; SEC-4; W10-R6, 9 | 5 | 07, 08, 11, 17 | 4 |
| W-1 | REC-W13-09; REC-W17-07 | 2 | 14, 27 | 0 |
| W-2 | REC-W13-08; REC-W17-07 | 2 | 14, 27 | 0 |
| W-3 | REC-W13-09, 12; REC-W16-03 | 3 | 14, 17 | 4 |
| W-4 | REC-W13-09, 15; REC-W16-03 | 3 | 14, 17 | 0 |
| W-5 | REC-W13-11, 14 | 2 | 14 | 0 |
| W-6 | REC-W13-11 | 1 | 14 | 1 |
| W-7 | REC-W13-09 | 1 | 14 | 0 |
| W-8 | REC-W13-10; REC-W19-12; W12-R13 | 3 | 13, 14, 29 | 1 |
| W-9 | REC-W13-09 | 1 | 14 | 0 |
| RS-1 | REC-DEC-42; REC-FL-01; REC-RISK-02, 06; REC-W17-06; W12-R14 | 6 | 00, 01, 03, 13, 23, 27 | 5 |
| RS-2 | REC-FL-01; REC-W17-06; W12-R3 | 3 | 01, 03, 13, 27 | 9 |
| RS-3 | — | 0 | — | 1 |
| RS-4 | REC-DEC-01, 17, 41, 42, 46; REC-MATRIX-08; W2-R1, 7 | 8 | 00, 01, 03 | 2 |
| RS-5 | REC-FL-01 | 1 | — | 1 |
| RS-6 | — | 0 | 00, 26 | 0 |
| RS-7 | REC-W17-01 | 1 | 23, 27 | 0 |
| F-1 | REC-DEC-16; REC-W15-03, 12; REC-W17-05; W2-R4, 6 | 6 | 01, 03, 08, 11, 12, 16, 23, 27 | 1 |
| F-2 | REC-DEC-03, 18, 19, 37; REC-W15-04, 09; REC-W16-09; REC-W17-05; REC-W18-01; REC-W9-09; W10-R2; W2-R1; W3-REC-3; W7-R1, 2, 13 | 16 | 01, 03, 04, 05, 08, 10, 11, 12, 16, 17, 23, 27, 28 | 3 |
| F-3 | REC-DEC-24, 40; REC-W11-16; REC-W19-03, 05, 08; REC-W9-02; SEC-12; W7-R8, 12; W8-R6 | 11 | 01, 07, 08, 09, 10, 11, 12, 13, 29 | 8 |
| F-4 | REC-DEC-24; REC-W14-08; REC-W15-10; REC-W16-07; REC-W18-06; REC-W19-07, 09; W7-R8 | 8 | 01, 08, 11, 12, 15, 16, 17, 23, 28, 29 | 4 |
| F-5 | REC-DEC-10, 24, 40; REC-FL-05; REC-W15-09; REC-W16-02, 07; REC-W19-01, 07, 09, 10; W12-R4, 6; W7-R9, 12; W8-R12 | 16 | 01, 05, 08, 09, 11, 12, 13, 16, 17, 23, 29 | 8 |
| F-6 | REC-W11-12, 18; REC-W16-01; REC-W19-11; REC-W9-01; W7-R10 | 6 | 01, 05, 07, 08, 10, 11, 12, 16, 17, 29 | 10 |
| F-7 | REC-DEC-12, 25, 46, 48; REC-W17-03, 08; REC-W18-01, 02, 03, 04, 06, 07, 11; W2-R7; W7-R3, 5 | 16 | 01, 03, 08, 11, 15, 23, 27, 28 | 5 |
| F-8 | REC-DEC-25, 48; REC-W14-09; REC-W15-11; REC-W17-02; REC-W18-07, 09, 10, 11; W3-REC-12 | 10 | 01, 04, 15, 16, 23, 27, 28 | 5 |
| F-9 | REC-B30-01, 15; REC-PLAN-07; REC-W17-01, 08; REC-W18-08 | 6 | 00, 20, 24, 27, 28, 30 | 1 |
| F-10 | — | 0 | 00, 24 | 0 |
| F-11 | REC-DEC-04, 26, 27, 29, 49; REC-MATRIX-07; REC-W18-03, 05; W2-R3; W3-REC-8, 10, 13; W7-R5, 6; W8-R1, 5, 6, 11 | 18 | 00, 01, 03, 04, 06, 07, 08, 09, 16, 23, 26, 28 | 4 |
| F-12 | REC-DEC-04, 27, 33, 42, 44, 49; W2-R3, 4; W3-REC-13; W8-R5 | 10 | 00, 01, 03, 04, 09, 23, 26, 27 | 0 |
| F-14 | REC-DEC-01, 06, 09, 17, 22, 33, 38, 42, 44; REC-RISK-02; REC-W11-01, 05, 13; REC-W13-02; REC-W15-02, 03; REC-W16-04; REC-W18-01, 02; REC-W9-09; SEC-1, 8, 13; W10-R1, 2; W2-R1; W3-REC-3; W5-R1, 2, 3, 6, 12; W7-R7; W8-R4 | 34 | 00, 01, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 16, 17, 23, 26, 28, 29 | 15 |
| F-15 | REC-W14-10; REC-W18-01 | 2 | 01, 15, 28 | 0 |
| F-13 | REC-W13-07; REC-W15-01, 02; REC-W16-08; W3-REC-10; W8-R2, 7, 9, 12 | 9 | 04, 09, 14, 16, 17, 23 | 3 |

---

## 11. Change log

| Date | Change |
|---|---|
| 2026-11-11 | Revision 1 (TRACE): all 97 IDs traced; easily-missed homes verified; findings F-T1…F-T8; closes critic pass-2 gap N15 for `25-…`. |
| 2026-11-11 | Revision 2 (PROP4-d): synced to `01` rev. 4 and closes critic pass-3 P3-8(b). F-9 Partial → **Covered** (30 exists; its base default awaits its owner); F-10 Pending → **Partial** (PDF built from rev. 3); counts now 90 · 4 · 3 · 0. REC-DEC-42…49 traced (REC-DEC-42, the base-OS decision of record, supersedes REC-DEC-01). RS-1 and F-12 notes restated for rev. 4. Every "not yet written" / "does not exist yet" statement about 20, 22, 24, 30 and the PDF removed; F-T6 closed; F-T5 restated. Scope limits in §9 item 7. |
| 2026-11-11 | Revision 3 (SYNC5-a): synced to `01` rev. 4.1 (no score or ranking change) and closes critic P4-5 for this file. F-10 Partial → **Covered**: the PDF is rebuilt from rev. 4.1 (111 pages, rev. 4.1 build; the "101 pages / rev. 3" wording is gone). Counts now 91 · 4 · 2 · 0. F-T1 restated. No other row re-scanned. |
| 2026-11-11 | PDF5: RS-1's ARCHIVE-GAP count set to 110 (28 decision-grade) from the regenerated `SOURCES.md` (critic P5-5); F-10 now names the built PDF (111 pages). |
