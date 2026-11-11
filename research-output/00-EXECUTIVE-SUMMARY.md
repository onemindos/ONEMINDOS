# 00 · Executive summary (Tier A draft)

**Date:** 2026-11-10 · **Status:** Tier A complete in draft; Tier B and C not started · **Read next:** [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md), then [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)
**Claim IDs** below resolve in `evidence/claims/*.csv`. This page summarises; the evidence and reasoning are in `01-…` and the workstream files.

> ### Explain it like I'm the founder
> We tested ADR-001 the hard way: 14 base-OS stacks, 8 update engines, 9 ways to run apps and 6 backup tools went through a scorecard frozen before scoring. Every main conclusion went to at least two independent "refuters" told to break it, and we ran seven lab experiments in throwaway virtual machines.
> **The plan survives.** Its core stands: your own read-only image, Debian 13, two OS copies with automatic rollback, k3s, restic backups. **Six details change.** The update engine moves from Rugix to RAUC. "Healthy" gets a stricter, lab-proven definition. k3s needs an SSD and at least 4 GB. The k3s database backup method changes. The disk layout is fixed now so security can be switched on later. The EU's new law pushes security updates toward "on by default".
> Fedora IoT is not the base, but its Red Hat lineage becomes the Industrial profile. Ubuntu came first on the raw scorecard, then tied after the refuters' corrections. It stays in for NVIDIA hardware, and it can become the base if Canonical says yes on terms you accept.

---

## 1. The answer

| Layer | Decision | ADR-001 |
|---|---|---|
| Base OS | **Debian 13** core image (x86, arm64, Pi 5 via Raspberry Pi's kernel). **Jetson on NVIDIA L4T Ubuntu 24.04.** GPU-server tier may use **Ubuntu LTS + RKE2** once Canonical's redistribution terms are clear. **bootc (CentOS/Alma/RHEL) Industrial profile** in year 2. | Confirmed, with changes |
| Image + updates | Own read-only image; **RAUC** A/B (verity bundles, ≥ 1.15.2) on x86/Pi 5; **NVIDIA A/B + OTA** on Jetson; one OneMind release contract; signed from release 1 | Changed (engine) |
| Health gate | Commit only on fresh post-boot signals (kubelet, heartbeat, core pods, data RW, local API); apps excluded; 3 tries; watchdog | Confirmed, made concrete |
| Install paths | Flash image, USB installer/rescue ISO, VM images, preinstalled, NVIDIA flash; script install = developer preview | Confirmed |
| Kubernetes | **k3s** on platform nodes (≥ 4 GB + SSD/NVMe; 8 GB recommended); **NATS leaf** below; RKE2 only when a buyer needs it | Changed |
| Storage | local-path with a **Retain** class; Longhorn (LUKS) on 3+ nodes | Confirmed + change |
| Backups | **restic**, three keys; single-box k3s via online SQLite backup + token, inside restic; verified restores | Changed (method) |
| Security | Day-1 layout prerequisites (1 GiB ESP, verity headroom, LUKS2 data); gateway-enforced approvals for AI actions; CRA programme; FIPS 140-3 | Changed |

**Confidence: medium.** The architecture is well supported. The base-OS and update-engine rankings are **ties settled by decision-critical evidence**, and real-hardware tests are still pending. See §4.

## 2. Top 10 findings

1. **The raw scorecard put Ubuntu 26.04 first (62 vs 56), but the lead does not survive scrutiny.** Its two main supports, NVIDIA's K3s validation and ROS 2 Tier 1, do not reach Jetson, which ships Ubuntu 24.04 [C-W4-023, C-W7-027]. Canonical requires approval before anyone redistributes a modified Ubuntu [C-W2-050]. After one evidence-based correction it is a tie, and Debian wins the tie-break [C-W3-039].
2. **Fedora IoT can't be the base today, but its lineage is strong.** It has no supported Pi 5 bootc path [C-W2-018] and ~13-month releases [C-W2-015]. Even so, bootc + greenboot rolled back a broken k3s update with zero manual commands in our lab [C-W2-054], and Red Hat holds IEC 62443-4-2 [C-W2-042]. It becomes the Industrial profile.
3. **Rugix is essentially one developer,** with 303 of 304 commits in a year [C-W3-001]. Both refuters upheld this. RAUC (Home Assistant OS) leads instead, after a tie-break against Mender.
4. **Both proven competitors commit updates too early.** umbrelOS commits at daemon start [C-W3-036]. HAOS commits even when unhealthy [C-W3-025]. OneMind's gate is a real improvement.
5. **There is a stale-status trap.** After a slot switch, Kubernetes reports the previous boot's "Ready". A naive gate committed a broken update in our lab [C-LAB-debian-rugix-023].
6. **ADR-001's backup command doesn't work on a single box.** `k3s etcd-snapshot` fails on SQLite [C-W5-001]. Online SQLite backup + token + restic restored a full box onto a fresh VM [C-LAB-k3s-footprint-restore-011].
7. **umbrelOS stable releases are not signed.** 2.0.1 runs a server-supplied script [C-W3-034]. The signed design exists only in its 2.1 beta.
8. **The CRA expects automatic security updates by default** [C-W6-008]. The draft OS standard makes this testable [C-W6-019]. It collides with ADR-001's "never auto-install".
9. **NVIDIA's validated Kubernetes stack skips Debian and k3s.** AI conformance lists RKE2, Talos and k0s, not k3s [C-W4-038]. The GPU Operator doesn't support Jetson at all [C-W4-023].
10. **Converting the DOKS cluster is not "three changes".** It involves 13 dependencies, four of them real work [C-W4-063], and ingress-nginx has been unmaintained since March 2026 [C-W4-016].

## 3. Top 10 risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| 1 | Jetson software ends before the robot does: NVIDIA publishes no per-release support period, branch lives are about 5.7 and 4.5 years, and the JetPack 7 kernel 6.8 is not an LTS kernel [C-W7-004, C-W18-001] | high / high | Flash every Jetson A/B; plan one in-field branch upgrade; per-SKU support periods |
| 2 | Canonical refuses or overprices redistribution of modified Ubuntu, which also affects the Jetson and GPU flavors [C-W2-050, C-W2-006] | medium / high | Counsel + Canonical before any Ubuntu flavor ships; Debian core is already the default |
| 3 | An in-place Debian 13 → 14 rebase doesn't fit the slots or needs a bootloader change | medium / high | Layout fixed now; rebase spike T-W3-04 as a gate |
| 4 | k3s on 4 GB Pi boxes runs short of RAM or wears out flash; SQLite bloat across a fleet | medium / medium | SSD gate, 8 GB recommended, 30-day soak, leaf tier |
| 5 | The Secure Boot path with RAUC is unproven (no native systemd-boot backend [C-DEC-001]) | medium / high | Engine-neutral layout; spike X-2R before first image |
| 6 | CRA classification and route: a notified body needed, or no FOSS route on Pi 5/Jetson firmware [C-W6-012, C-W6-013] | medium / high | Counsel opinion; track EN 304 626; decide by 2027-Q2 |
| 7 | Prompt injection drives a physical action [C-W6-068] | medium / severe | Gateway-enforced human approval; capability tokens |
| 8 | Kubernetes upgrade treadmill: about 8–10 minors to 2036, no skipping, on offline boxes [C-W4-012] | high / medium | Automated, snapshot-gated, stepwise upgrades |
| 9 | Pi 5 real time is OneMind-owned work; Raspberry Pi has no Pi 5 RT build [C-W7-024] | high / medium | RT IIoT SKUs on x86 first; Pi RT build later |
| 10 | Solo-founder load: two userlands, three kernel lines, many CVEs | high / medium | Everything through one image pipeline; no hand patching |

## 4. Decisions Zeus must make (details and recommendations in `26-…`)

1. Ask counsel and Canonical about redistributing modified Ubuntu (Q-W2-1). *Recommended: yes, now.*
2. Security updates install automatically by default (CRA) vs "never auto-install" (R-1). *Recommended: auto for the security channel, with opt-out, postpone and a window.*
3. RAUC (recommended) or Rugix (more convenient, single maintainer).
4. Signing-key custody and ceremony.
5. Open-core boundary vs the CRA self-assessment route.
6. Support period per SKU, and the first SKU and segment.
7. Industrial route: own IEC 62443-4-1 process or certified partner.
8. Plus the REQUIREMENTS open questions 2–5 and the recurring Blueprint questions.

## 5. Status and confidence per workstream

| WS | Topic | Tier | Status | Confidence | File |
|---|---|---|---|---|---|
| W1 | Competitor teardowns | A / B / C | **Tier A done:** HAOS, umbrelOS, Olares, VillageOS, flagged repos. Tier B/C teardowns and `MATRIX.md` **not started** | High (code at pinned SHAs) | `02-competitors/` |
| W2 | Base OS | A | Draft complete; refuters ran (2 weakened, 1 upheld + steelman) | Medium | `03-base-os.md` |
| W3 | Image, install, updates | A | Draft complete; refuters ran (2 upheld, 2 weakened + steelman); labs done | Medium-high | `04-…` |
| W4 | Kubernetes, DOKS, NVIDIA | A | Draft complete; refuters ran (4 weakened + steelman) | Medium | `05-…` |
| W5 | Backups and recovery | A | Draft complete; refuters ran (2 upheld, 2 weakened) | High | `06-…` |
| W6 | Security and compliance | A | Draft complete; refuters ran (4 weakened) | Medium | `07-…` |
| W7 | Robotics foundation fit | A (plan P1) | Foundation fit complete; refuters ran (2 weakened) | Medium | `08-…` |
| W8 | IoT/IIoT foundation fit, TAK, mesh | A (rest B) | Foundation fit complete; refuters ran (1 weakened, 1 upheld); lab W8-1 passed | Medium-high | `09-…` |
| W9 | AI capability layer | B | Not started | — | — |
| W10 | Hardware line | B | Not started | — | — |
| W11 | Dashboard, clients, XR | B | Not started | — | — |
| W12 | Apps, Market, plugins | B | Not started | — | — |
| W13 | Family, education, website | C | Not started | — | — |
| W14 | Phones and field devices | C | Not started | — | — |
| W15 | World context, scenarios | C | Not started | — | — |
| W16 | Business, licensing, GTM | B | Not started | — | — |
| W17 | Founder learning path | C | Not started | — | — |
| W18 | Kernel, image ownership, Mac toolchain | A | Draft complete; refuters ran (4 weakened); Mac lab done | Medium-high | `28-…` |
| W19 | Platform and plugin ecosystem (DC-16 is P0) | B | Not started; **DC-16 open** | — | — |
| DEC | Foundation decision | A | Draft complete | Medium | `01-…` |

**Also not started:** `20-PLAN-180-DAYS`, `21-ROADMAP`, `22-HARDWARE-LAB-TEST-PLAN` (tests exist inside each workstream file), `23-RISK-REGISTER`, `24-QUESTION-BANK-ANSWERS` (per-workstream statuses are in `evidence/qbank/`), `25-TRACEABILITY`, `27-LEARNING-PATH`, `29-…`, `30-NEXT-ULTRACODE-BUILD-BRIEF`, the PDF, `SOURCES.md`, `REVIEW-CHECKLIST.md`, `evidence/license-matrix.csv` and the consolidated `evidence/claims.csv` (the per-tag ledgers in `evidence/claims/` hold the 861 claim rows).

## 6. Did the VM lab run? Yes.

All in disposable Lima/QEMU VMs on the research Mac, with no host mounts or credentials. Pass/fail criteria were written before each run.

| Spike | Result |
|---|---|
| Debian 13 + Rugix, x86_64 and aarch64 | **PASS** (run 4): health-gated commit, automatic rollback, power cut survived; found the stale-status trap [C-LAB-debian-rugix-022, C-LAB-debian-rugix-023] |
| Debian 13 + RAUC, x86_64 | **PASS** twice: bad-key refusal, rollback from unhealthy and unbootable updates, two power-cut cases [C-LAB-rauc-014…018] |
| Fedora bootc + greenboot | **Mostly PASS**; power cut during finalize silently downgraded a healthy box (upstream bug) [C-LAB-fedora-bootc-011] |
| Fedora IoT bootc + k3s gate | **PASS** on automation; **FAIL** on the 15-minute rollback-time target (32 min) [C-W2-054] |
| k3s footprint + restore | **PASS**: +936 MiB idle; SQLite and etcd restores onto fresh VMs [C-LAB-k3s-footprint-restore-007, C-LAB-k3s-footprint-restore-011] |
| k3s vs Podman footprint | **PASS** on thresholds: 2.50 GiB free of 4 GiB [C-W4-078] |
| NATS leaf buffering | **PASS**: 600/600 delivered after an outage [C-W8-050] |
| Mac kernel build path (W18) | **PASS**: nested KVM; arm64 kernel in 333 s [C-W18-066] |

**What the lab can't show** is real power loss, Pi 5 or Jetson behaviour, or GPU drivers. Those tests need Zeus's hardware and are written as founder-runnable tests in each workstream file.
