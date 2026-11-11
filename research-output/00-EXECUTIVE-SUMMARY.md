# 00 · Executive summary (Tier A decided, Tier B drafted)

**Date:** 2026-11-11 (revision 2, after the wave-2 adversarial pass) · **Status:** Tier A decision revised; Tier B drafted for W1 (8 teardowns + matrix), W9, W10, W11, W12, W16 and W19; Tier C not started; plan, roadmap, build brief and PDF not started · **Read next:** [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) (§7.1 lists what changed), then [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)
**Claim IDs** below resolve in `evidence/claims/*.csv`. This page summarises; the evidence and reasoning are in `01-…` and the workstream files.
**Serves requirements:** RS-1, RS-4, RS-6, R-1, R-3, M-6, M-7, N-9, F-11, F-12, F-14, A-5, A-6, D-001

> ### Explain it like I'm the founder
> We tested ADR-001 the hard way, twice. In the second round, every main conclusion went to **at least three** independent "refuters" told to break it (91 adversarial reports in all), seven agents argued as hard as they could *for* the runner-up in each decision, and two more lab experiments ran: the update system with real Kubernetes, and the update system with Secure Boot switched on.
> **The plan still survives,** and its core is unchanged: your own read-only image, Debian 13, two OS copies with automatic rollback, k3s, restic backups. But two wins got thinner. **Ubuntu vs Debian** and **RAUC vs Mender** are now near-ties that Debian and RAUC win on the deciding evidence, not on the score. Each has a written, testable path back to the runner-up, and we keep that path cheap (an Ubuntu build runs in CI from day one; the disk layout works with any engine).
> Three things are new for you. **Your Jetson robots run a modified Ubuntu too,** so the "may we ship Ubuntu?" question for Canonical now covers them; we also test a Jetson image that does not need Ubuntu. **Secure Boot works with our layout** in the lab, but we found it will happily boot an *old* signed kernel, so we add an anti-downgrade rule. **Plugins** get ten built-in sockets, and the refuters showed the standard Linux feature behind them accepts unsigned add-ons unless we switch that off.

---

## 1. The answer

| Layer | Decision (revision 2) | vs ADR-001 | Confidence |
|---|---|---|---|
| Base OS | **Debian 13** core (x86, arm64, Pi 5 via Raspberry Pi's kernel) with an **Ubuntu 26.04 CI leg** as a hedge. **Jetson on NVIDIA L4T Ubuntu 24.04** for the launch beta, gated on Canonical's answer; **Yocto meta-tegra + 6.18 LTS kernel** tested as the Jetson target within 180 days. **Ubuntu LTS + RKE2** for GPU servers and robotics-simulation boxes once Canonical answers. **bootc Industrial profile** in year 2 | Confirmed, with changes | **Low-medium** (tie settled by tie-break) |
| Image + updates | Own read-only image; **RAUC** A/B (verity bundles, ≥ 1.15.2) on x86/Pi 5; NVIDIA A/B + OTA on Jetson (A/B from the factory); one release contract; **Mender is the named runner-up** | Changed (engine) | **Medium-low** (Mender 62 vs RAUC 61 raw; RAUC wins the tie-break) |
| Health gate | Commit only on fresh post-boot signals; apps excluded; 3 tries; watchdog; trial marker in pre-install; kernel/root version match | Confirmed, made concrete | **High** (two engines, two labs) |
| Boot and Secure Boot (x86) | RAUC `efi` backend + one signed UKI per slot; data key on PCR 7 + signed PCR 11; anti-downgrade; factory key enrolment. The release that enforces Secure Boot with out-of-tree drivers uses a OneMind-built LTS kernel | Changed | Medium (emulation only) |
| Install paths | Flash image, USB installer/rescue ISO, VM images, preinstalled, NVIDIA flash; script install is a developer loop, unsupported after image GA | Confirmed | High |
| Kubernetes | **k3s** on platform nodes (≥ 4 GB + SSD; 8 GB recommended), hardened config; **agent-only on robots and field kits**; **NATS leaf** below; RKE2 only when a buyer needs FIPS/STIG | Changed | Medium |
| Storage + backups | local-path **Retain** class; **restic**, three keys; online SQLite backup bound to the k3s version; restore drill per k3s release | Changed (method) | High |
| Plugins (DC-16) | Ten extension points E1–E10; signed-only system extensions; per-vendor driver packs; expiring revocation list | New | Medium |
| Security + CRA | Day-1 layout; gateway-enforced approvals for AI actions; D2 confirmed for amd64, per board elsewhere; image vs box CRA classes; FIPS 140-3 (k3s FIPS mode blocked upstream) | Changed | Medium |

## 2. Top 10 findings

1. **Debian beats Ubuntu only on the tie-break, and Canonical's answer could flip it.** Corrected scores are Ubuntu 62 vs Debian 60, a tie. Debian wins on what is hard to undo: no permission needed for the core image, four lab spikes, the umbrelOS precedent, community governance. If Canonical grants redistribution, Ubuntu's licensing cell rises and it would lead 67 vs 63 [C-LIC-011, C-STEEL-ubu-002].
2. **The Jetson flavor is a modified Ubuntu, so it needs Canonical's permission too.** NVIDIA's forum defers its Ubuntu rootfs to Canonical's terms [C-REF-DC-cost-007]. NVIDIA's own BSP licence does allow shipping the unmodified BSP on NVIDIA hardware [C-LIC-001…003]. meta-tegra already packages a 6.18 LTS kernel for Orin and Thor [C-STEEL-jb-002].
3. **Mender now edges RAUC on raw score (62 vs 61).** One standard applied to both: Mender is free for all units under Apache-2.0, and Umbrel shipped it [C-STEEL-updates-mender-001, C-W3-040]. RAUC wins the tie-break: it has Secure Boot proven on our layout, revocation, free deltas, Pi 5 tryboot, and three lab passes. Mender's deltas and phased rollouts are paid [C-STEEL-updates-mender-015].
4. **The fresh-signal health gate held with real Kubernetes.** On RAUC with k3s, a naive gate committed a broken kubelet in about a minute, twice; the fresh gate rejected it and rolled back [C-LAB-rauc-k3s-gate-007, C-LAB-rauc-k3s-gate-008]. k3s also needs bind-mounts to run on a read-only root [C-LAB-rauc-k3s-gate-004].
5. **Secure Boot works with the chosen layout, but it is not anti-downgrade.** RAUC's `efi` backend booted signed per-slot kernels with our own keys; the data disk unlocked by TPM across updates and rollbacks [C-LAB-secureboot-rauc-012…016]. An old signed kernel booted against a newer root and was committed [C-LAB-secureboot-rauc-018].
6. **A key in UEFI db cannot sign kernel modules for a stock kernel.** The kernel trusts only built-in and MOK keys for modules [C-DEC-008…010]. So driver plugins under Secure Boot need a OneMind-built kernel or a console step per box.
7. **systemd extensions accept unsigned add-ons by default.** Their default policy admits unsigned images and plain directories [C-REF-W19-security-004]; one bad image blocks all merges [C-REF-W19-cost-005]. DC-16 is only safe with OneMind's own enforcement.
8. **NVIDIA's Jetson software ends before its hardware does.** JetPack 4 ended 26–32 months before Nano/TX2 NX stopped shipping, with no notice [C-REF-W7-T-001, C-REF-W7-T-002]; JetPack 5 ended on 2026-10-30 [C-REF-W7L-001]. Support periods are planned per module.
9. **Robotics simulation is Ubuntu-only at NVIDIA.** Isaac Sim lists Ubuntu and Windows hosts [C-REF-DC-robotics-013], and NVIDIA's DKMS driver broke on routine Debian kernels [C-REF-DC-cost-009].
10. **The CRA treats the image and the box differently.** A downloadable OS image is Class I; a box is probably classified by its own core function [C-REF-W6-technical-008]. Art. 13(10) lets OneMind patch only the latest version, but only where the customer can actually upgrade [C-REF-W6-technical-001].

## 3. Top 10 risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| 1 | Canonical refuses or overprices redistribution, which now blocks the Jetson flavor as well as GPU servers [C-LIC-011, C-REF-DC-cost-007] | medium / high | Ask now (Z-01); meta-tegra Jetson lab within 180 days; Debian core needs no permission |
| 2 | Jetson software ends before the robot does; NVIDIA's 6.8 kernel is not LTS; fixes only at branch head [C-REF-W7-T-004, C-REF-W7-T-007] | high / high | Per-module support periods; track every JetPack major and point release; meta-tegra LTS route as the exit |
| 3 | A third-party plugin persists across slot switches through an unsigned extension [C-REF-W19-security-004] | medium / high | Signed-only policy, no directories, T-W19-01 security variant as the ADR condition |
| 4 | Secure Boot downgrade: old signed kernels boot on new roots [C-LAB-secureboot-rauc-018] | medium / high | Recovery UKI at the fallback path, version-match gate rule, SBAT/key rotation |
| 5 | The Secure Boot release forces a OneMind-built kernel (K2) on a solo founder [C-DEC-008…010] | high / medium | Plan it; measure T-W18-4 (< 1 h per weekly bump); look for a console-free route (T-W19-03) |
| 6 | An in-place Debian 13 → 14 rebase costs more founder time than budgeted, and the Pi is paced by Raspberry Pi's window [C-REF-DC-robotics-009] | medium / high | T-W3-04 with founder-hours recorded; pinned Pi archive and EEPROM |
| 7 | k3s on capturable devices exposes every Secret; hardened k3s may not fit 4 GB [C-REF-W4-security-004, C-REF-W4-security-008] | medium / high | Agent-only field nodes; hardened re-measure; 8 GB floor if it fails |
| 8 | CRA route and classification wrong for the image or the box [C-REF-W6-technical-008] | medium / high | Counsel opinion (Z-05); decide by 2027-Q2 |
| 9 | Prompt injection drives a physical action [C-W6-068] | medium / severe | Gateway-enforced human approval; capability tokens |
| 10 | Solo-founder load: two userlands, three kernel lines, driver packs, two update backends, a plugin review queue [C-REF-W19-cost-004] | high / medium | One image pipeline; v1-beta for three plugin contracts; costed review plan before the Community tier |

Also tracked: the Kubernetes upgrade treadmill (about 8–10 minors to 2036) [C-W4-012], Pi 5 real time unreliable under load [C-REF-DC-technical-001], and k3s crashing in Go's FIPS-only mode [C-REF-DC-longevity-010].

## 4. Decisions Zeus must make (details and recommendations in `26-…`)

1. **Z-01** Ask counsel and Canonical about modified Ubuntu, **now covering Jetson**. *Recommended: yes, now.*
2. **Z-02** Security updates automatic by default (CRA) vs "never auto-install". *Recommended: auto for security, with opt-out, postpone and a window.*
3. **Z-03** Update engine: RAUC (recommended), Mender (runner-up) or Rugix.
4. **Z-04** Signing-key custody, now including the module and extension keys.
5. **Z-16** Jetson: L4T for the beta and a meta-tegra lab within 180 days. *Recommended: yes.*
6. **Z-18/Z-19** x86 boot route and the Secure Boot key model (factory db key, OneMind-built kernel for the enforcing release).
7. **Z-22** Whether third parties may ship host-level plugins in release 1.
8. **Z-25** Whether FIPS/STIG compliance is a P0 product property (it would make RKE2 the default on 8 GB+ nodes).
9. Plus Z-05…Z-15, Z-17, Z-20, Z-21, Z-23, Z-24, Z-26, Z-27, the REQUIREMENTS open questions 2–5 and the recurring Blueprint questions.

## 5. Status and confidence per workstream

| WS | Topic | Tier | Status (2026-11-11) | Confidence | File |
|---|---|---|---|---|---|
| W1 | Competitor teardowns | A / B / C | **Tier A done** (HAOS, umbrelOS, Olares, VillageOS, flagged repos). **Tier B drafted** (balenaOS, StartOS, Kairos, Talos, TrueNAS SCALE, CasaOS/ZimaOS, Proxmox VE, Project N.O.M.A.D.) and `MATRIX.md` written. Tier C not started | High (A); medium (B) | `02-competitors/` |
| W2 | Base OS | A | Complete; **3 refuters per P0** (P0-1: 3 weakened; P0-2: 2 upheld, 1 weakened) + 2 independent steelmen (bootc, Ubuntu) | Low-medium | `03-base-os.md` |
| W3 | Image, install, updates | A | Complete; **3 refuters per P0** (P0-W3-1: 3 upheld; P0-W3-2: 3 weakened) plus one on 01's RAUC decision (upheld); steelmen for Buildroot, Mender, Rugix; **two new labs** | Medium | `04-…` |
| W4 | Kubernetes, DOKS, NVIDIA | A | Complete; **3 refuters per P0** (all 6 weakened) + Compose steelman | Medium | `05-…` |
| W5 | Backups and recovery | A | Complete; **3 refuters per P0** (P0-1 3 upheld; P0-2 3 weakened) + Kopia steelman | High | `06-…` |
| W6 | Security and compliance | A | Complete; **3 refuters per P0** (all 6 weakened); Secure Boot route lab-passed in emulation; **no independent steelman for the notified-body route** | Medium | `07-…` |
| W7 | Robotics foundation fit | A (plan P1) | Complete; **3 refuters per P0** (FF-1 3 weakened; FF-2 2 upheld, 1 weakened) + Jetson-base steelman | Medium | `08-…` |
| W8 | IoT/IIoT foundation fit, TAK, mesh | A (rest B) | Complete; **3 refuters per P0** (P0-1: 3 weakened; P0-2: 2 upheld, 1 weakened) + EL10 bootc steelman | Medium | `09-…` |
| W9 | AI capability layer | B | **Drafted** (12 recommendations; no refuters, not required at Tier B) | Medium | `10-ai-capability-layer.md` |
| W10 | Hardware line, capability detection | B | **Drafted** (five boxes + leaf class; NFD + GFD + OneMind probe) | Medium | `11-hardware-line.md` |
| W11 | Dashboard, clients, XR | B | **Drafted** (20 recommendations, 8 founder tests; no hardware or UI tests run) | Medium | `12-dashboard-clients-xr.md` |
| W12 | Apps, Market, plugins | B | **Drafted** (129 claims incl. one pinned licence row per seed app) | Medium | `13-apps-market-plugins.md` |
| W13 | Family, education, website | C | Not started | — | — |
| W14 | Phones and field devices | C | Not started | — | — |
| W15 | World context, scenarios | C | Not started | — | — |
| W16 | Business, licensing, GTM | B | **Drafted** (55 claims; market sizes as SECONDARY ranges) | Medium | `17-business-licensing-gtm.md` |
| W17 | Founder learning path | C | Not started | — | — |
| W18 | Kernel, image ownership, Mac toolchain | A | Complete; **3 refuters per P0** (all 6 weakened) + K2 steelman; Mac lab done | Medium-high | `28-…` |
| W19 | Platform and plugin ecosystem (DC-16 P0) | B (DC-16 A) | **Drafted**; DC-16 decided in 01 §4.8 after **15 refuters** (9 weakened); sysext VM lab done | Medium | `29-…` |
| LIC | Licence matrix | — | **Done** (153 components; Jetson BSP licence verified) | High (not legal advice) | `evidence/license-matrix.md` |
| DEC | Foundation decision | A | **Revision 2 done** | Low-medium (base, engine) to high (gate, backups) | `01-…` |

## 6. The VM lab (all disposable Lima/QEMU VMs; pass/fail criteria written before each run, self-attested)

| Spike | Result |
|---|---|
| Debian 13 + Rugix, x86_64 and aarch64 | **PASS** (run 4); found the stale-status trap [C-LAB-debian-rugix-022, C-LAB-debian-rugix-023] |
| Debian 13 + RAUC, stand-in gate | **PASS** twice [C-LAB-rauc-014…018] |
| **Debian 13 + RAUC + real k3s gate** (new) | **PASS** twice; naive gate committed a broken kubelet both times [C-LAB-rauc-k3s-gate-006…010] |
| **RAUC under enforced Secure Boot, X-2R** (new) | **PASS** twice; downgrade gap found in an exploratory test [C-LAB-secureboot-rauc-012…018] |
| Fedora bootc + greenboot | **Mostly PASS**; power cut in finalize silently downgraded a healthy box [C-LAB-fedora-bootc-011] |
| Fedora IoT bootc + k3s gate | **PASS** on automation; **FAIL** on the 15-minute rollback target (32 min) [C-W2-054] |
| k3s footprint + restore | **PASS**: +936 MiB idle on Debian 13 arm64; SQLite and etcd restores [C-LAB-k3s-footprint-restore-007, C-LAB-k3s-footprint-restore-011] |
| k3s vs Podman footprint | **PASS**: 2.50 GiB free of 4 GiB (default, unhardened k3s) [C-W4-078] |
| NATS leaf buffering | **PASS**: 600/600 delivered [C-W8-050] |
| Mac kernel build (W18) | **PASS**: arm64 kernel in 333 s [C-W18-066] |
| systemd sysext/confext (W19) | **PASS** functionally; signing and slot switches not tested [C-W19-006…009] |

**What the lab can't show:** real power loss, real PC firmware, Pi 5, Jetson, GPU drivers, or RAUC ≥ 1.15.2 (every RAUC lab used Debian's 1.13). Those need Zeus's hardware or a rebuilt package and are written as founder tests.

## 7. Honest disclosure: what is still short of the brief

- **Adversarial protocol:** every P0 now has ≥ 3 refuters. But seven decision-critical questions have only one or two dedicated refuters (01 §5.9), two DC-16 conclusions have fewer than three (01 §5.10), and two runner-ups (embedded etcd on every box; the CRA notified-body route) still lack an independent steelman. A second completeness-critic pass has **not** run, so "loop until dry" is not met.
- **Deliverables not started:** `20-PLAN-180-DAYS`, `21-ROADMAP`, `22-HARDWARE-LAB-TEST-PLAN` (tests exist inside each workstream file), `23-RISK-REGISTER`, `24-QUESTION-BANK-ANSWERS` (per-workstream statuses in `evidence/qbank/`), `25-TRACEABILITY`, `27-LEARNING-PATH`, `30-NEXT-ULTRACODE-BUILD-BRIEF`, the PDF, `SOURCES.md`, `REVIEW-CHECKLIST.md`; Tier C workstreams W13, W14, W15, W17.
- **Ledger:** `evidence/claims.csv` (the brief's master ledger) still holds the 861 Tier A rows; the per-tag ledgers now hold about 2,030. It must be re-merged and re-checked. Some critic items from pass 1 remain (SHA-pinning of older code claims, 6-month re-check dates, non-standard status values, unledgered Pi 5 bootc sources).
- **Pricing:** Ubuntu Pro for Devices, Freexian ELTS for arm64 and Red Hat RHDE are unpriced; outreach is drafted in `evidence/outreach-drafts.md` but not sent (the brief forbids contacting vendors).
- **Labs:** all emulation; nothing has run on Pi 5, Jetson, a real PC's firmware or a real power cord.
- **Archiving:** Wayback save requests are blocked here; load-bearing pages are pinned to commits or saved with sha256, with ARCHIVE-GAPs listed per `evidence/sources/*.md`.
- **Not legal advice:** CRA, licence and trademark readings are flagged for counsel.
