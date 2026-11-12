# Remaining work after the research run (authoritative list)

**Date:** 2026-11-11 · **Source:** the final completeness critic, [`pass-8.md`](pass-8.md), which re-checked every open item from passes 3–7 against the tree after `01` rev. 4.1 (DEC5), FIX7, G4U, ARCH5 and SYNC5.

**State:** the loop is **dry at S1/S2**. No new S1 or S2 gap was found, and every §9 item the critic counts is met or met with residue. Everything below is still open. Each item is in exactly one group.

**Not listed here** (the orchestrator handles these at commit time): committing the rev-4.1 working tree; re-merging the master `evidence/claims.csv` from the per-tag ledgers (2,986 rows); the gitleaks run before push; and marking PR #1 ready. PR #1 also waits on Z-28 in group (a).

> **Explain it like I'm the founder.** The research is finished as far as an agent can take it. What is left is mostly yours:
> - **(a)** decisions and approvals;
> - **(b)** one news check that can't happen before tomorrow;
> - **(c)** tests that need real boxes, or a network that can reach Ubuntu's servers;
> - **(d)** a short list of small text fixes an agent can make later. None of them changes a decision.

---

## (a) Needs the founder

| ID | What is needed | Why it matters | Lives in |
|---|---|---|---|
| **Z-28** (critic N1/N2, P4-9) | Decide whether to purge leaked personal data and the host folder layout from the pushed history (`414d60a`, `ee98bc7`, `7836316`, `b933b86`). A purge needs a history rewrite and a force-push | **Urgent.** The repo is public. Blocks marking PR #1 ready (brief §9) | `26` §F Z-28 (l. 210–220); `evidence/hygiene-log.md` §3 |
| **P4-10** | Mask the home path with the account alias in a founder-authored file on `main`; decide under Z-28 whether its history matters | Public repo; the file predates the run | `research/platform/iiot-landscape-and-requirements.md` l. 441 |
| **Z-01** (+ critic P4-8) | Ask Canonical and counsel whether a modified Ubuntu image may be redistributed, and at what price (Pro for Devices). The drafted outreach is O-1 | Gates the decision of record (D·G1 = COND). It is the only way to put a cost on G1. A refusal moves S1 to bootc (V8) | `26` Z-01 (l. 16, 312, 361); `01` §3.1.6 (h), l. 418; `evidence/outreach-drafts.md` O-1 |
| **Z-38** | Accept the frozen-protocol base (Ubuntu 26.04 + RAUC, fragile, 11 of 14 runs), or override it as your own decision | The base-OS decision of record | `26` §H Z-38 (l. 315); `01` §3.1.6 |
| **Z-39** | Rule whether an unmet condition that depends on a third party disqualifies a candidate (COND read as FAIL) | Changes S1 under V8/V9 | `26` §H Z-39 (l. 326) |
| **Z-40** | Write down the four scoring rules before the next tests (tie-break row count and others) | Prevents rules being written after the scores are known | `26` §H Z-40 (l. 332); `evidence/scorecard-weights.md` §8 |
| **Z-41** (critic P5-1, P6-2, P6-4) | Run the Ubuntu Secure Boot test LT-VM-20 yourself, or approve an Ubuntu archive mirror for the lab. Also judge whether the two disclosed reads past the DNS block were acceptable | U-SB is the one map event that needs no hardware or vendor; a fail moves S1 to bootc | `26` §I Z-41 (l. 364–372); `evidence/hygiene-log.md` §7 D-1 |
| **Z-10** | Approve W2-HW-3 (bootc on a real Pi 5) before gate G1 (week 4) | A fail moves S1 to Debian 13 | `26` Z-10 (l. 58, 313); `22` LT-PI5-02 |
| **Z-05, Z-06** (DC-04) | Counsel on the CRA route (image vs box, notified body), and the declared support period per SKU | DC-04 is `blocked: founder-decision` | `26` Z-05 (l. 37), Z-06 (l. 42); `evidence/decision-critical.md` DC-04 |
| **Z-37** | Approve the vendor and expert outreach | Quotes and programmes feed Z-01, cost and hardware | `26` Z-37 (l. 260); `evidence/outreach-drafts.md` |
| **Remaining founder decisions** | Z-02…Z-04, Z-07…Z-09, Z-11…Z-27, Z-29…Z-36, REQUIREMENTS open questions 2–5, and the recurring Blueprint questions (Pixel hardware, Dell 5540 state, first vertical slice, task system) | Each has options and a recommendation; all 9 `blocked: founder-decision` bank IDs map to a Z-ID | `26` §A–§G (§G is the map from `24`) |
| **Hardware order** | Order the lab hardware on day 1 (2026-11-16) | Every group (c) hardware test depends on it | `20` D1 (l. 512); `22` §2.3; `11` §10.1 |

## (b) Needs a date

| ID | What | Earliest | Lives in |
|---|---|---|---|
| **N12** | Re-check the KubeCon NA 2026 days 3–4 NVIDIA and CNCF announcements (NVKE/NVKR, Agent Substrate, GPU Operator / DRA / KAI / Dynamo on k3s). Update C-W4-039 and C-W4-040, then re-read the NVIDIA-on-k3s items for years 2–3 | **After 2026-11-12**; ledger `recheck_by` 2026-12-10 | `05` l. 250–251; `21` l. 503; `evidence/claims/W4.csv` |

## (c) Needs physical hardware, or a network the lab doesn't have

**Network.** The research environment cannot resolve Ubuntu, Canonical or Launchpad names; the run did not bypass that.

| ID | What | Decision consequence | Lives in |
|---|---|---|---|
| **LT-VM-20 / U-SB** (critic P5-1 residue) | Run the frozen kit (sha256 `c98a09d1…f8db`) on a machine that reaches `archive.ubuntu.com`: about 1.5–2 h, no hardware. Pass = two unchanged runs | Fail, or pass only after a layout change → S1 = bootc. Pass → D's `doc-only` mark on C3 is dropped | `22` LT-VM-20 (l. 509), LT-ACC-01 (l. 695); `evidence/lab/ubuntu-secureboot/` README §R.3, §R.5; `evidence/lab/PREREGISTRATION.md` |
| **C-DEC-006** (critic P5-7 residue) | Save the Launchpad `linux-raspi` bug 2170238 as text with its sha256 (founder step F-1) | Archive integrity for a row DC-19's tie-break uses | `evidence/sources/ARCH5.md` F-1; `SOURCES.md` §ARCHIVE-GAP |
| **26.04 package facts** | Confirm against the 26.04 archive what Repology (SECONDARY) shows: open62541, mosquitto, libmodbus, can-utils in universe; `linux-raspi-realtime`; the hawkBit updater not in 26.04 | Supports D·G4 (a), (b) and (e); a missing package does not FAIL G4, because OneMind can build the `.deb` | `09` l. 63; `evidence/adversarial/G4-ubuntu-rev5.md` §6; `evidence/claims/FIX7.csv` (C-FIX7-003…005) |
| **LT-VM-16 on the Ubuntu leg** | Run the FDO onboarding test on the Ubuntu leg. It needs the archive for the Ubuntu image | D·G4 (d) | `22` LT-VM-16 |
| ARCH5 F-2, F-3 (optional) | Take a fresh copy of Canonical's IP policy; re-check the Pi 5 16 GB price page | Archive freshness only | `evidence/sources/ARCH5.md` |

**Hardware.** No test in `22` has run on real hardware yet.

| ID | What | Decision consequence | Lives in |
|---|---|---|---|
| **W2-HW-3 = LT-PI5-02** | bootc on a real Pi 5, before G1 (week 4) | Fail → S1 = Debian 13 (6–5) | `22` l. 44; `20` G1 (l. 309) |
| **G1 x86 battery** | LT-X86-01, LT-X86-02 (LT-X86-08 only if -01 fails) and the rest of LT-X86-00…16: update engine, real power cut, firmware | Gate G1 (the x86 update engine), G6 (LT-X86-14 whole-box restore) | `22`; `20` §5 G1, G6 |
| **Pi 5 series** | LT-PI5-01…14, including the real-time latency run (G4 (b): Canonical documents `raspi` RT for 26.04, but Pi 5 latency is unmeasured [C-G4U-001, C-G4U-002]) and restic vs Kopia (LT-PI5-05) | D·G4 (b); backup engine at G6 | `22`; `09` §1 (b) |
| **Jetson series** | LT-JET-01…08, including meta-tegra (LT-JET-06) | Jetson base, Z-16, G6 | `22`; `08` |
| **Live cluster (read-only)** | LT-CLU-01…12 on the DOKS hub | Cluster-conversion facts in `05` | `22`; `20` weeks 1–2 |
| **Business tests** | LT-BIZ-01…05 (for example NVIDIA Inception, LT-BIZ-03) | Cost and programme inputs | `22`; `20` D1 |
| **Fleet scale ~10k** | Nobody has run 10k devices; Landscape is not an A/B OTA plane, so hawkBit is the update server | D·G4 (e) stays COND until demonstrated | `09` §1 (e); `G4-ubuntu-rev5.md` §1 |

## (d) Agent-fixable but deferred (S3/S4; no decision moves)

| ID | Fix | Lives in |
|---|---|---|
| **P4-4 residue** | Add **C-LAB-secureboot-1152-010** (cited at `01` l. 881) to the exception appendix | `evidence/critic/cit4-mapping.md` §8 |
| **01 follow-up: W6 X-2** | Replace the literal `--tpm2-pcrs=7` with the PCR 7 + signed PCR 11 policy that `01` §4.3 / SB-5 adopts | `07` l. 384 |
| **01 follow-up: EN 304 626** | Apply [C-STEEL-cra-nb-020]: the draft accepts KEVD or KEVA, and auto-update by default comes from CRA Annex I, not the draft. Reword trigger P0-3 accordingly | `07` l. 401 (and §P0-2, l. 25) |
| **01 follow-up: 08 FF-2** | Cite meta-tegra's packaged LTS route [C-STEEL-jb-002] in FF-2 (the text is at l. 112 but uncited) | `08` FF-2 |
| **01 follow-up: 05 Talos** | State the S1/S3 Talos distinction in §3.3, as `01` l. 1244 asks (not found in pass 8) | `05` §3.3 |
| **01 follow-up: W2 Pi 5 bootc sources** | Ledger the W2 steelman's and W2-P0-2 refuters' Pi 5 bootc and Fedora 45 sources "before any re-score", per `01` l. 1244 (not re-verified in pass 8) | `evidence/claims/W2.csv`; `01` l. 1244 |
| **00 loop status** | Change 00 §6's "Critic pass 7 still found four new gaps, so the loop is not dry" to the pass-8 result, and link this file | `00` §6 l. 94 |
| **Stray file** | Delete `rpi-news-price-rises-16gb.txt.tmp` (299 B, header only, not in SHA256SUMS) before commit | `evidence/sources/ARCH5/` |

---

**Counts:** after pass 7, 29 critic items were open. **22 are now closed and 7 are open.**
- **Founder:** P4-8 (via Z-01), P4-10, N1/N2 (via Z-28).
- **Network:** the P5-1 residue (U-SB) and the P5-7 residue (C-DEC-006).
- **Date:** N12.
- **Agent:** the P4-4 one-ID residue.

The other rows above are founder decisions, hardware tests and deferred `01` follow-ups that the critics did not number.

## Closed by the orchestrator at final commit (2026-11-11)

- (d) P4-4 residue: C-LAB-secureboot-1152-010 added to `cit4-mapping.md` §8.
- (d) 00 §6 loop line updated to the pass-8 result.
- (d) Stray `evidence/sources/ARCH5/*.tmp` deleted.

Still open in (d): the 01 l.1244 follow-ups (07 X-2 literal, EN 304 626 correction, 08 FF-2 citation, 05 §3.3 Talos sentence, W2 Pi 5 bootc ledger rows). They are wording and citation fixes that do not change any decision.
