# 00 · Executive summary

**Date:** 2026-11-11 (revision 4; follows `01` rev. 4) · **Status:** every brief §6 deliverable exists; the base-OS decision is conditional. **Not done:** see §6
**Read next:** [`REVIEW-CHECKLIST.md`](REVIEW-CHECKLIST.md), then [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) and [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md). The PDF still shows rev. 3 (§6).
**Claim IDs** resolve in `evidence/claims/*.csv`; this page adds no facts (`FINAL.csv` is header-only). Lab table, glossary and competitor table: `01` §10, §2, §9.
**Serves requirements:** RS-1, RS-4, RS-6, RS-7, R-1, R-3, M-6, M-7, N-9, F-9, F-10, F-11, F-12, F-14, A-5, A-6, D-001

> ### Explain it like I'm the founder
> **The answer:** OneMind OS is **your own read-only image** with two OS copies, updated by **RAUC**; a new copy is kept only once Kubernetes is healthy *right now*. Boxes with 4 GB+ and an SSD run **k3s**, gadgets join over **NATS**, **restic** backs up. That part of ADR-001 holds.
> **What changed in revision 4: the base.** Under the contest rules we locked before scoring, **Ubuntu 26.04 LTS** wins narrowly (Ubuntu 65, bootc 64, Debian 63). Revision 3 had kept Debian with a tie-break rule written after the scores were known. That rule is withdrawn [C-PROTO4-018]. Ubuntu's win is fragile, and it needs Canonical's permission or a debranded rebuild (Z-01).
> **The next steps are written down in advance.** If bootc fails on a real Pi 5 (W2-HW-3), Debian wins. If Canonical refuses and you reject a debranded rebuild, bootc wins. If both happen, you decide. You may also pick Debian yourself, logged as your decision (Z-38).
> **Only you can:** ask Canonical and counsel (Z-01), rule on Z-38 to Z-40, Z-02, Z-04 and Z-28, and buy a Pi 5 and a Jetson Orin Nano: every test so far ran in emulation.

---

## 1. The answer (`01` rev. 4)

| Layer | Decision | vs ADR-001 | Confidence |
|---|---|---|---|
| Base OS | **Ubuntu 26.04 LTS core + RAUC** (frozen-protocol result); Jetson on L4T Ubuntu 24.04; **CONDITIONAL on G1 (Z-01) and G5**. A Debian 13 leg is built until the base is locked before the first box. Pre-registered: W2-HW-3 fails → Debian 13; Z-01 refused, debrand rejected → bootc; Ubuntu Secure Boot VM leg U-SB fails → bootc (FIX4; FIX5: pre-registered and attempted, BLOCKED because the Ubuntu archive is unreachable from the research environment; ready to run on day 1 [C-FIX5-002]) [C-DEC4-001, C-DEC4-006] | **Changed (conditional)** | **Low**: a tie in all 14 weight runs; Ubuntu wins 11, Debian 2, bootc 1 |
| Industrial profile | AlmaLinux 10 or RHEL 10 image mode (year 2); CentOS Stream, Fedora IoT as CI canaries | New | Medium |
| Image | OneMind owns it; a distro base, for CUDA and one-person upkeep | Confirmed | High |
| Updates | RAUC A/B (OneMind-built v1.15.2) on x86 and Pi 5; NVIDIA A/B on Jetson; one release contract; Mender runner-up | Changed (engine) | Medium-low: Mender 62 vs RAUC 61, a tie; RAUC wins the tie-break 5–3 |
| Health gate | Fresh signals, apps excluded, 3 tries, watchdog; shown safe for **one box on SQLite** only; cluster rollback untested | Confirmed, narrowed | High (single box) |
| Secure Boot (x86) | RAUC `efi` + signed UKI per slot, TPM-bound data key, anti-downgrade; OneMind shim (`vendor_cert`) before any OneMind-built kernel | Changed | Medium (emulation) |
| Kubernetes | k3s on platform nodes (≥ 4 GB + SSD), hardened; agent-only on robots; kine ≥ v0.13.10; RKE2 only for a FIPS or GPU-cluster buyer | Changed | Medium |
| Storage + backups | local-path Retain; restic, three keys; online SQLite backup, verified only with datastore-health checks | Changed (method) | High |
| Plugins (DC-16) | Ten signed-only extension points E1–E10; Pi EEPROM and Jetson QSPI versions pinned and gated | New | Medium |
| CRA | FOSS self-assessment primary; notified-body track from 2027-Q1 | Changed | Medium |

**ADR-001 (`01` §7):** D1, D3, D4 and D5 confirmed. **D2 changed (conditional): Debian 13 → Ubuntu 26.04.** Engine changed from Rugix to RAUC. Overturned: Kairos for Jetson, system-upgrade-controller on image nodes, "DOKS in three changes" and "no Fedora/RHEL role".

## 2. Top 10 findings

1. **The three bases are within 2 points; the locked rules pick Ubuntu**, 6–4 over bootc on the top-two tie-break [C-DEC4-001, C-DEC4-006]. One or two rows decide every pair.
2. **Revision 3 bent the rules; revision 4 follows them.** The three-way tie-break was written after scoring [C-PROTO4-018]. DC-01's own bootc flip margin was met on the rev-3 card and is not met on the rev-4 card [C-DEC4-008].
3. **Stock Mender allows one trial boot; RAUC three** [C-LAB-mender-013].
4. **Distribution RAUC is a trap.** Debian's 1.13 cannot install on kernels 6.19 or newer [C-LAB-ubuntu-2604-leg-010], so OneMind ships its own 1.15.2 [C-LAB-rauc-1152-011].
5. **Nobody ships our exact combination.** We found no field-proven Debian or Ubuntu + RAUC product [C-DEC-013, UNVERIFIED: negative search]; IronFlockOS is pre-1.0 [C-CIT4-001].
6. **"Healthy" must mean healthy now.** A naive gate committed a broken kubelet on every engine, and on arm64 too. The fresh-signal gate caught it every time [C-LAB-rauc-k3s-gate-008, C-LAB-aarch64-gate-004].
7. **Jetson software dies before its hardware.** JetPack 5 ended on 2026-10-30 [C-REF-W7L-001]; support is declared from the current branch until an r36 → r39 lab passes. Canonical's question covers Jetson too [C-REF-DC-cost-007 (SECONDARY), C-LIC-011].
8. **Secure Boot works in emulation on RAUC 1.15.2, but an old signed kernel still boots** [C-LAB-secureboot-1152-005, C-LAB-secureboot-1152-009], so an anti-downgrade rule is required.
9. **Plugin sockets must be locked.** systemd extensions accept unsigned images by default [C-REF-W19-security-004].
10. **Building from source was not decided on CVEs** [C-LAB-minimal-image-dc20-011]; labour dominates the 10-year cost (`evidence/lifecycle-cost-2036.md`).

## 3. Top 10 risks (from `23`; 62 risks, 5 Critical)

| # | Risk | L × I | Mitigation |
|---|---|---|---|
| RR-01 | Jetson software ends before the robot | 16 | Per-module support periods; meta-tegra exit |
| RR-02 | k3s upgrade treadmill on offline boxes | 16 | Snapshot-gated stepwise upgrades |
| RR-03 | Solo-founder load | 16 | One pipeline; extras only for a named buyer |
| RR-04 | Live cloud cluster on retired ingress-nginx | 16 | Phase-0 move to Gateway API + Traefik |
| RR-05 | Wrong CRA route or class | 16 | Counsel by 2027-Q2 (Z-05); notified-body track |
| RR-06 | Prompt injection drives a physical action | 15 | Gateway-enforced human approval |
| RR-07 | Signing-key loss or theft | 10 | Offline root, HSM, 2-of-3 (Z-04) |
| RR-08 | k3s on small, capturable devices | 12 | Agent-only field nodes; 8 GB floor if needed |
| RR-09 | Canonical refuses or overprices (now decides S1) | 12 | Ask in week 1; Debian leg built; no quote yet. Canonical sells "Trademark use" inside Ubuntu Pro for Devices; provisional bracket $0–$250 per box over 10 years (an assumption, not a quote) [C-DEC4-010, C-FIX4-001, C-FIX4-004] |
| RR-10 | Secure Boot downgrade to an old signed kernel | 12 | Version floor, SBAT rotation |

## 4. Decisions Zeus must make (all in `26`, dated in `20` §2.3)

| When | Decisions |
|---|---|
| **Week 1** | **Z-28**, **Z-01**, **Z-37**, **Z-30**, **Z-14/Z-24** |
| **Before W2-HW-3 (week 4)** | **Z-40** scoring rules · **Z-38** accept Ubuntu or override · **Z-39** does an unmet outside condition disqualify? |
| Weeks 2–8 | **Z-29** trademark · **Z-03** engine and **Z-22** host plugins (G1) · **Z-18** x86 boot (G2) · **Z-04**, **Z-07**, **Z-23** (G3) |
| Weeks 9–21 | **Z-17**, **Z-19**, **Z-21** (G4) · **Z-02**, **Z-10/Z-27**, **Z-12**, **Z-20** (G5) · **Z-16**, **Z-13**, **Z-06** (G6) |
| Week 26+ | **Z-05** (+ **Z-36**) CRA · **Z-09** · **Z-15** fusing · Z-08, Z-25, Z-11, Z-26 on a buyer trigger |
| Product | Z-31…Z-35 |

Until Zeus rules, the run assumes the protocol result (Ubuntu) with its conditions (`01` §3.1.6 i).

## 5. Status and confidence per workstream

| WS / file | Status (2026-11-11) | Confidence |
|---|---|---|
| W1 teardowns (`02-competitors/`) | Done: Tier A, 8 Tier B, 16 Tier C, `MATRIX.md` | High (A), medium (B), low-medium (C) |
| W2 base OS (`03`, `01` §3.1) | Done; rev-4 protocol ruling, 3 refuters on it, bootc steelman | **Low** (conditional, fragile) |
| W3 updates (`04`) | Done; RAUC 1.15.2 on x86 and arm64, Mender, Secure Boot labs | Medium-low (engine), high (gate) |
| W4 Kubernetes (`05`) | Done; KubeCon NA 2026 days 3–4 not re-checked | Medium |
| W5 backups (`06`) | Done; restore lab | High |
| W6–W8 (`07`–`09`) | Done; no Jetson, RT or real-firmware test | Medium |
| W9–W17 (`10`–`17`, `27`) | Drafted (Tier B/C) | Medium / medium-low |
| W18 kernel, Mac (`28`) | Done; Mac lab | Medium-high |
| W19 ecosystem (`29`, `01` §4.8) | Drafted; DC-16 decided, E10 has 5 refuters | Medium |
| `20`–`26`, `30` | Complete (`22`: none run). `24`'s S1 item should become `blocked: founder-decision` | Medium |
| PDF | Built (101 pages) from **rev. 3** | Needs rebuild |

**VM lab:** eighteen spikes, criteria written before each run (`evidence/lab/PREREGISTRATION.md` says which are hash-verifiable; results in `01` §10). Real power loss, firmware, Pi 5, Jetson, GPUs, RT latency and a major rebase are founder tests in `22`, gated in `20`.

## 6. What remains (brief §9)

- **Loop until dry: not met.** Rev. 4 closes critic pass-3 P3-1, P3-2, P3-8(a) and P3-9, and P3-4 with listed exceptions ([`cit4-mapping.md`](evidence/critic/cit4-mapping.md)). The rev-4 re-scores, recount and decision map now have three refuters (FIX4: technical/security, longevity, cost; all *weakened*, none refuted). They were written sequentially by one agent, so they are not blind (`01` §5.1.2). They added one pre-registered test, the Ubuntu Secure Boot VM leg U-SB, which gives bootc if it fails. FIX5 (critic P5-1) pre-registered it as a lab spike and tried to run it. It is **BLOCKED**: the Ubuntu archive does not resolve from this environment, and the run did not bypass that. So the S1 result is unchanged and still rests on D·C3 = 4 (`doc-only`). The kit is ready for day 1 [C-FIX5-001, C-FIX5-002].
- **Ledgers:** the master `evidence/claims.csv` is stale and needs a re-merge. Ten round-4 refuter files need re-ledgering (`01` §12). Licence matrix: P3-6 and P4-2 closed (282 rows; the Ubuntu 26.04 core image, its two kernels, the Pi 5 boot path on Ubuntu and Ubuntu Pro for Devices now have rows).
- **PDF:** rebuild from rev. 4; it still misstates the tie (P3-3).
- **Git:** rev. 4 is uncommitted; PR #1 is a draft, blocked on Z-28.
- **Hardware:** W2-HW-3 before G1, then the rest of `22`.
- **Sync:** 07–09, 28 and 29 headers say "draft"; 16 and 27 cite rev. 2. None of this is legal advice.
