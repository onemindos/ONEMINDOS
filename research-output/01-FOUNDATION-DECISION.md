# 01 · Foundation decision: what OneMind OS is built on

**Owner:** DEC (synthesis of W2–W8, W18, the Tier A teardowns, the four VM lab spikes and 31 refuter/steelman reports) · **Date:** 2026-11-10 · **Status:** Tier A decision draft, ready for the founder's review
**Decides:** ADR-001 D1–D6 · decisions S1–S5 of the frozen scorecard ([`evidence/scorecard-weights.md`](evidence/scorecard-weights.md) v1.0, unchanged) · the 24 decision-critical questions ([`evidence/decision-critical.md`](evidence/decision-critical.md))
**Inputs:** [`03`](03-base-os.md) · [`04`](04-image-install-updates-rollback.md) · [`05`](05-kubernetes-cluster-conversion-nvidia.md) · [`06`](06-backups-recovery.md) · [`07`](07-security-compliance.md) · [`08`](08-robotics-drones-physical-ai.md) · [`09`](09-iot-mesh-offgrid-tak.md) · [`28`](28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md) · [`02-competitors/`](02-competitors/) · [`evidence/adversarial/`](evidence/adversarial/) · [`evidence/lab/`](evidence/lab/)
**Claims:** every load-bearing sentence cites a claim ID that exists in `evidence/claims/*.csv`. New facts verified by this agent are `C-DEC-001…007` ([`evidence/claims/DEC.csv`](evidence/claims/DEC.csv), sources in [`evidence/sources/DEC.md`](evidence/sources/DEC.md)). Counter-arguments in §5 are summaries of the refuter files, which carry their own sources.
**Serves requirements:** RS-1, RS-2, RS-4, R-1, R-2, R-3, M-2, M-4, M-6, M-7, M-8, N-1, N-2, N-4, N-6, N-7, N-8, N-9, H-1, H-3, P-3, P-5, P-7, P-8, P-9, U-4, AI-4, AI-5, AI-7, AI-9, UX-6, A-1, A-5, F-1, F-2, F-7, F-8, F-11, F-12, F-14, F-15, D-001, D-002

> ### Explain it like I'm the founder
> You asked one question: **what should OneMind OS stand on for the next 10 years?** Here is the answer, layer by layer, in plain words.
>
> 1. **Base OS: Debian 13, as ADR-001 proposed, kept.** Ubuntu 26.04 came first on the raw scorecard (62 vs 56). But the refuters showed its lead rests on things that don't reach the Jetson robots (they run NVIDIA's Ubuntu 24.04, not 26.04), and that Canonical's trademark policy needs its approval before we redistribute a modified Ubuntu image [C-W2-050]. Once one score is corrected with evidence (Umbrel already moved its fielded boxes from Debian 12 to 13 over the air [C-W3-039]), the two are a **tie (62 vs 60)**, and the protocol says ties go to the decision-critical evidence. That evidence favours Debian: it is the base of the closest proven competitor (umbrelOS), it is what every one of our lab spikes actually ran on, and it carries no vendor legal condition. **Ubuntu still wins where NVIDIA rules:** Jetson robots stay on NVIDIA's Ubuntu, and the big GPU-server tier may use Ubuntu + RKE2 once the Canonical question is answered.
> 2. **Fedora IoT (your question): a profile, not the base.** Its bootc lineage did exactly what we want in our lab (it refused a broken update and rolled back by itself [C-W2-054]), and Red Hat has the industrial certificates [C-W2-042]. But on the Pi 5 it is still experimental [C-W2-018] and each Fedora release lives about 13 months [C-W2-015]. So it becomes the **Industrial/Enterprise profile** later, with Fedora IoT as our early-warning "canary".
> 3. **Updates: two copies of the OS (A/B), engine changed from Rugix to RAUC.** Rugix is excellent but is written by essentially one person (303 of 304 commits in a year [C-W3-001]); RAUC runs Home Assistant OS. Both passed our lab tests: bad updates rolled back by themselves and pulling the power mid-update never bricked the machine [C-LAB-rauc-015, C-LAB-rauc-017, C-LAB-debian-rugix-022]. The disk layout stays compatible with both, so we can switch engines later with an update, not a reflash.
> 4. **"Healthy" must mean healthy *now*.** Our lab found a trap nobody documents: after an update, Kubernetes shows the *previous* boot's "all good" status. A naive check committed an update whose Kubernetes never started [C-LAB-debian-rugix-023]. Our gate checks fresh signals only.
> 5. **Kubernetes: k3s on every box with at least 4 GB of RAM and an SSD; smaller gadgets join over NATS.** k3s costs about 1 GB of RAM in our lab [C-LAB-k3s-footprint-restore-007]. RKE2 is kept for the day a regulated or big-GPU customer needs it.
> 6. **Backups: restic, plus a correct way to back up k3s's database on a single box.** ADR-001's "k3s etcd-snapshot" simply fails on a single box [C-W5-001]; the right method restored a whole box onto a fresh machine in our lab [C-LAB-k3s-footprint-restore-011].
> 7. **Security and the law:** decide the disk layout *now* so Secure Boot and disk encryption can be switched on later without wiping boxes, and be ready for the EU Cyber Resilience Act, which expects security updates to install automatically by default [C-W6-008]. That last point collides with "never auto-install" and is your call.
>
> **What you must decide** (details in [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)): ask counsel and Canonical about Ubuntu redistribution; accept or reject automatic security updates by default; RAUC vs Rugix if you value Rugix's convenience more; who holds the signing keys.

---

## Contents

1. The answer per tier (one table)
2. Glossary
3. Scorecards: S1 base OS, S2 updates, S3 Kubernetes, S4 backups, S5 kernel (gates, weighted cells, corrections log, sensitivity, tie-breaks)
4. The recommendation per tier, in detail
5. Adversarial tables per decision, with a written response to every weakened or refuted verdict
6. The runner-up steelmen, summarised fairly
7. ADR-001: confirmed / changed / overturned, element by element
8. P-3: OneMind mapped onto Olares's layers
9. What competitors do (constraint fit)
10. What the VM lab proved, and what it didn't
11. Recommendations → requirement IDs
12. Conditions, open items and limits of this decision

---

## 1. The answer per tier

| Tier of the stack | Decision | vs ADR-001 | Confidence | Key evidence |
|---|---|---|---|---|
| **Base OS (D2, S1)** | **Debian 13 "trixie" core image** (x86_64, generic arm64, Pi 5 with Raspberry Pi's kernel) · **Jetson flavor on NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+)** · **GPU-server flavor (Omni/Cluster) may run Ubuntu LTS + RKE2**, gated on the Canonical redistribution answer · **bootc (CentOS Stream 10 / AlmaLinux 10 / RHEL image mode) Industrial profile** as a year-2 track, Fedora IoT bootc as CI canary | **Confirmed, with changes** (two flavors named, bootc profile added) | Medium: S1 is a tie after refuter correction; settled by tie-break (§3.1.5) | C-W2-001, C-W2-043, C-W2-044, C-W3-039, C-W2-026, C-W2-050, C-W7-007, C-W2-041, C-W2-042, C-W2-054 |
| **Image build (D1)** | OneMind owns the image: rootfs defined as a container build on a snapshot-pinned Debian (umbrelOS pattern), turned into A/B disk images; NVIDIA flash tools for Jetson | **Confirmed** | High | C-W2-043, C-W18-012, C-W18-015, C-W3-049 |
| **Updates and rollback (D3, S2)** | **RAUC** for x86 and Pi 5 (verity bundles only, ≥ 1.15.2), **NVIDIA rootfs A/B + image-based OTA** on Jetson, under **one OneMind release contract** (manifest, signing, health gate, UI). Rugix is the documented alternative; the layout stays engine-neutral | **Changed** (lead engine; Jetson method decided; update-default is a founder decision) | Medium: S2 is a RAUC/Mender tie after correction; settled by tie-break (§3.2) | C-W3-001, C-W3-013, C-W3-021, C-W3-049, C-W3-050, C-DEC-004, C-LAB-rauc-013…018 |
| **Health gate (D3)** | Commit only after **fresh** signals pass: local kubelet answers, node heartbeat newer than this boot, core pods Ready since this boot, data partition read-write, local OneMind API answers; apps excluded; watchdog; 2–3 boot tries; never auto-retry a failed release | **Confirmed and made concrete** | High (lab) | C-LAB-debian-rugix-023, C-LAB-debian-rugix-024, C-W5-010, C-LAB-rauc-010, C-LAB-rauc-018 |
| **Install paths (D1, P-7)** | Flash image (Pi), USB installer ISO (x86, doubles as rescue disk), VM images, preinstalled boxes, NVIDIA flash (Jetson); script-on-distro = developer preview only; fleet/PXE year 2 | **Confirmed** | High | C-W3-028, C-TD-olares-042, C-W3-059 |
| **Kubernetes (D4, S3)** | **k3s** on every *platform node* (≥ 4 GB RAM **and** SSD/NVMe; 8 GB recommended for a server); devices below that are **NATS leaf nodes**; **RKE2** reserved for the regulated tier and an AI-conformant GPU cluster, adopted only when a buyer needs it; Gateway API + Traefik | **Changed** (storage gate, leaf tier, RKE2 deferred, FIPS text) | Medium (S3 fragile; Pi silicon untested) | C-W4-002, C-W4-078, C-LAB-k3s-footprint-restore-007, C-W4-038, C-W4-016 |
| **Storage (D5)** | local-path with a OneMind **Retain** storage class on one box; Longhorn (LUKS volumes) on 3+ nodes; optional ZFS mirror on Pro ("not a backup") | **Confirmed with a change** (Retain class) | High | C-W5-019, C-W4-002 |
| **Backups (D5, S4)** | **restic** (three-key repository); single-box k3s datastore = online SQLite `.backup` + token, inside restic; `etcd-snapshot` only on etcd clusters, restic-wrapped; automatic verified restores | **Changed** (datastore method) | High (lab, robust scorecard) | C-W5-001, C-W5-009, C-W5-013, C-W5-023, C-LAB-k3s-footprint-restore-011, C-LAB-k3s-footprint-restore-015 |
| **Kernel (D2/D6, S5)** | The board maintainer's kernel (Debian stock, Raspberry Pi's, NVIDIA L4T) plus a CI-checked **kernel contract**; PREEMPT_RT as an image profile | **Confirmed** | Medium-high | C-W18-012, C-W18-005, C-W18-019 |
| **Security (D6)** | Day-1 layout prerequisites (1 GiB ESP, verity headroom, **LUKS2 data from first boot**); signed releases from release 1; gateway-enforced human approval for actuation, OS updates, installs, exports; robot-runtime exception profile; CRA programme; FIPS 140-3 (not 140-2) for the public-safety tier | **Changed** (layout moves to day 1; FIPS text; AI approvals) | Medium | C-W6-008, C-W6-019, C-W6-047, C-W6-052, C-W6-026, C-W6-028, C-W7-033 |

---

## 2. Glossary

| Term | Meaning |
|---|---|
| **A/B update** | Two copies (slots) of the OS. Updates are written into the copy that isn't running; if the new copy fails, the box boots the old one. |
| **Health-gated commit** | The new slot becomes the default only after checks pass. Until then, any reboot returns to the old slot. |
| **Fresh signal** | Evidence produced *after this boot* (a new heartbeat, a local probe), as opposed to status saved in the database from an earlier boot. |
| **Rebase** | Moving a fielded box to a new major OS release (Debian 13 → 14) in place, without wiping it. |
| **Flavor** | A variant image for one hardware family (for example the Jetson flavor on NVIDIA's Ubuntu). |
| **Profile** | A configuration of the same image family for a use (greenhouse, TAK node, Industrial). |
| **bootc / image mode** | Shipping the whole OS as a container image; Red Hat's long-life lineage uses it. |
| **greenboot** | Fedora/RHEL health checks that trigger an automatic rollback. |
| **RAUC / Rugix / Mender** | Open-source A/B update engines (HAOS uses RAUC; umbrelOS uses Rugix). |
| **Verity bundle** | A RAUC update format whose every block is hash-checked, unlike the older "plain" format. |
| **k3s / RKE2 / k0s** | Small Kubernetes distributions. k3s and RKE2 come from SUSE; k0s from Mirantis. |
| **NATS leaf node** | A small NATS server on a device that forwards to the main bus and stores messages while the link is down. |
| **SQLite / etcd** | The two k3s databases: SQLite for one server, etcd for several. |
| **restic** | An encrypting, de-duplicating backup program that allows several keys per repository. |
| **CRA** | EU Cyber Resilience Act (Regulation (EU) 2024/2847); main obligations from 2027-12-11. |
| **Gate / anchor / tie** | Scorecard terms: a gate is pass/fail; an anchor is the written meaning of a 0–5 score; a gap under 3.0 points between the top two is a tie, settled by decision-critical evidence, never by changing scores. |
| **Refuter / steelman** | An independent agent told to disprove a conclusion / an agent told to argue for the runner-up. |
| **Weakened** | A refuter verdict meaning "the conclusion may stand but its evidence or scope must change". Every weakened verdict gets a written response in §5. |

---

## 3. Scorecards

Formula: `total = Σ(weight × score)/5`, weights C1 20 · C2 20 · C3 15 · C4 15 · C5 10 · C6 10 · C7 10 (frozen v1.0, not changed by this file). Each scorecard below shows (1) gates, (2) the workstream's frozen scores with one claim per cell, (3) **the corrections this file makes, each forced by a refuter or by evidence that arrived after the workstream scored**, (4) sensitivity, (5) the tie-break where the top two are within 3 points. No weight or anchor was changed, so `scorecard-weights.md` §8 needs no entry; cell corrections are logged here per §5 rule 6 of that file.

### 3.1 S1 · Base OS and image family (ADR-001 D2)

#### 3.1.1 Gates

| Candidate | G1 Licence | G2 x86 + Pi 5 + Jetson | G3 Support to 2036 | G4 IoT/IIoT | G5 One OS Pi → cluster | Ranked |
|---|---|---|---|---|---|---|
| **A. Debian 13 + A/B (+ L4T Ubuntu Jetson flavor)** | COND: Rugix/RAUC licences fine [C-W2-048]; the Jetson flavor needs the NVIDIA EULA step and is itself modified Ubuntu [C-W2-050] (§4.1) | COND: Pi 5 via Raspberry Pi's kernel repo, as umbrelOS ships [C-W2-044] | COND: LTS to 2030-06-30, ELTS to 2035 quote-only and not shareable with customers [C-W2-001, C-W2-004] | COND: four mitigations, no failure [C-W8-001, C-W8-033] | COND: Jetson is a second family [C-W7-007] | yes |
| **D. Ubuntu 26.04 + A/B (+ JetPack Ubuntu 24.04)** | COND: modified-Ubuntu redistribution needs Canonical approval or trademark removal and recompiled binaries [C-W2-050] | PASS: Pi 5 certified [C-W2-057] | COND: Pro to May 2036 (before 2036-12-31), Pro for Devices unpriced [C-W2-005, C-W2-006] | COND [C-W2-028] | PASS: one family [C-W2-026] | yes |
| **C. RHEL-family bootc (+ RHDE on Orin)** | COND: RHEL/RHDE redistribution needs a Red Hat agreement [C-W2-041] | COND: no Pi 5 path on RHEL [C-W2-018] | COND: AlmaLinux 10 to 2035-05-31 [C-W2-013] | PASS: IEC 62443-4-2 SL-C 2 on RHEL 9.6 [C-W2-042] | COND | yes |
| G. Yocto + RAUC · B. Fedora IoT · F. Buildroot + RAUC · E. Ubuntu Core | PASS/COND per 03 §3 | COND | COND [C-W2-015] | COND | COND | yes |
| H. CIP Core · I. Talos · J. Kairos · K. SL Micro · L. balenaOS · NixOS · Alpine | — | **FAIL** (unproven Pi 5/Jetson, or no Orin) [C-W4-064] | **FAIL** for K, L, NixOS, Alpine [C-W2-015] | — | **FAIL** for balena (no k3s) | no |

#### 3.1.2 Frozen scores (W2, unchanged), one claim per cell

| Candidate | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | Total |
|---|---|---|---|---|---|---|---|---|
| D. Ubuntu 26.04 | 3 [C-W2-005] | 3 [C-W2-026] | 3 pending-lab [C-W2-058] | 3 [C-W7-039] | 3 [C-W2-043] | 2 [C-W2-006] | 5 [C-W2-028] | **62.0** |
| C. RHEL bootc | 3 [C-W2-013] | 1 [C-W2-018] | 3 lab [C-W2-054] | 3 [C-W2-041] | 4 [C-W2-056] | 3 [C-W2-013] | 4 [C-W2-026] | 56.0 |
| A. Debian 13 + Rugix (ADR-001) | 2 [C-W2-001] | 3 [C-W2-044] | 3 pending-lab at scoring, since lab-run [C-LAB-debian-rugix-022] | 3 [C-W2-043] | 3 [C-W2-045] | 3 [C-W2-001] | 3 [C-W2-026] | 56.0 |
| G. Yocto + RAUC | 2 | 3 | 3 | 2 | 2 | 4 | 2 | 51.0 |
| B. Fedora IoT | 3 [C-W2-015] | 1 [C-W2-018] | 3 [C-W2-054] | 1 | 4 | 4 | 2 | 48.0 |
| F. Buildroot + RAUC | 1 | 2 | 3 | 3 | 2 | 4 | 2 | 46.0 |
| E. Ubuntu Core | 3 | 2 | 4 | 0 | 2 | 2 | 3 | 46.0 |

(Full per-cell citations for G, B, F, E are in `03-base-os.md` §4. W2's own sensitivity run: D wins 14/14, minimum margin 3.9.)

#### 3.1.3 Corrections log (this file)

| # | Cell | Change | Reason (evidence) | Effect |
|---|---|---|---|---|
| S1-1 | A · C1 | 2 → **3** | Anchor 3 is met by "a documented in-place rebase path that keeps the device current". W2 held it at 2 only because "rebase path undocumented (DC-05)". W3 then found a production adopter doing exactly that: umbrelOS moved fielded boxes from Debian 12 to 13 by OTA bundle, no reflash [C-W3-039], and DC-05's flip condition is not met [04 §5.1]. | A = **60.0** |
| S1-2 | A · stack | Update engine Rugix → RAUC (S2 result) | Base-OS cells C1, C2, C4–C7 do not depend on the engine. C3 stays 3: both engines passed forced-rollback and power-cut tests on Debian 13 in our lab [C-LAB-debian-rugix-022, C-LAB-rauc-015, C-LAB-rauc-017], but anchor 4 also needs a *documented* Secure Boot path with no later layout change, which for RAUC is a design inference until spike X-2R runs (§4.3). | none |
| S1-3 | D · C2, C7 | **Kept**, evidence restated | Refuters showed both "main supports" (GPU Operator K3s column, ROS 2 Lyrical Tier 1) cover x86 and Pi 5 only: the GPU Operator does not support Jetson [C-W4-023], and Lyrical rates Ubuntu 24.04 (the JetPack 7 base) Tier 3 [C-W7-027]. W2 had already scored C2 = 3, not 4, so no number moves. | none |
| S1-4 | D · C1 | **Kept at 3**, flagged | The longevity refuter argues for 2 (Pro for Devices unpriced; Ubuntu Pro coverage of the NVIDIA L4T kernel undocumented; 26.04 ESM ends May 2036). W2 bounded the cost with Ubuntu Pro's published per-machine list price [C-W2-007], which is a defensible anchor-3 reading. Shown as a variant below. | variant D = 58.0 |
| S1-5 | C · C2 | **Kept at 1** | The W2 steelman argues 2–3 (AlmaLinux bootc images tested on Pi 5; RHDE GA on Orin). The Pi 5 sources it cites are not in the claims ledger and its own §8 calls the route experimental; rule "lower anchor when in doubt" and "unledgered = not scored". Re-score when a ledgered Pi 5 bootc result exists (founder test W2-HW-3). | C stays 56.0 (steelman estimate 60–64) |

**Corrected totals:** D 62.0 · **A 60.0** · C 56.0 · G 51.0 · B 48.0 · F 46.0 · E 46.0. With the S1-4 variant: **A 60.0 · D 58.0** · C 56.0.

#### 3.1.4 Sensitivity of the corrected S1 (14 runs, each weight ±5, others rescaled)

| Perturbation | Winner | Runner-up | Margin | | Variant (D-C1 = 2): winner | Margin |
|---|---|---|---|---|---|---|
| C1 ±5 | D / D | A | 1.9 / 2.1 | | A / A | 3.1 / 0.9 |
| C2 ±5 | D / D | A | 1.9 / 2.1 | | A / A | 1.9 / 1.8 (over C) |
| C3 ±5 | D / D | A | 1.9 / 2.1 | | A / A | 1.9 / 2.1 |
| C4 ±5 | D / D | A | 1.9 / 2.1 | | A / A | 1.9 / 2.1 |
| C5 ±5 | D / D | A | 1.9 / 2.1 | | A / A | 1.9 / 2.1 |
| C6 +5 / −5 | D / D | A | 0.8 / 3.2 | | A / A | 3.0 / 1.0 |
| C7 +5 / −5 | D / **A** | A / D | 4.1 / 0.1 | | **D** / A | 0.3 / 4.3 |

**Reading:** after correction, the top two are **inside the 3-point tie band in 12 of 14 runs**, and the winner flips in one run (C7 −5). Under the frozen protocol this is a **tie**, so the tie-break below decides, not the raw order. The script is in §3.6.

#### 3.1.5 Tie-break by decision-critical evidence (D vs A; C shown for completeness)

| DC | What it asks | D · Ubuntu 26.04 | A · Debian 13 | C · RHEL bootc | Favours |
|---|---|---|---|---|---|
| **G1 / Q-W2-1** | Can OneMind legally ship the image? | Modified Ubuntu needs Canonical approval, or trademark removal **and recompiled binaries** [C-W2-050]: unresolved, needs counsel | A sold appliance already redistributes a modified Debian image [C-W2-043]; Debian has no trademark-approval condition like Canonical's (W2 §7) | Alma free; RHEL needs agreement [C-W2-041] | **A** |
| DC-03 | Bounded cost to 2036 | $0 to 2031, then Pro for Devices (unpublished) [C-W2-006] | $0 if rebased to 14/15; ELTS not usable for a fleet as-is [C-W2-004] | $0 to 2035 on Alma [C-W2-013] | A ≈ C > D |
| DC-05 | Rebase without reflash | No production precedent found for an Ubuntu A/B appliance | umbrelOS did Debian 12 → 13 OTA [C-W3-039] | By design, lab-shown `bootc switch` [C-LAB-fedora-bootc-015] | C > A > D |
| DC-07 | One update framework | RAUC on x86/Pi + NVIDIA on Jetson (same as A) | Same [C-W3-049] | greenboot is GRUB-only; Pi experimental [C-W3-058] | A = D > C |
| DC-19 | Pi 5 pipeline | Certified [C-W2-057], but an open linux-raspi boot regression on older Pi 5 EEPROMs [C-DEC-006] | Shipped in production by umbrelOS with Raspberry Pi's kernel [C-W2-044] | Experimental [C-W2-018] | **A** |
| DC-13 | NVIDIA GPU on the base | Validated with K3s [C-W2-026] | Works via driver + toolkit + device plugin; no Operator lifecycle [C-W4-022, 05 §7.2] | Validated for RKE2/K8s [C-W2-026] | **D** (Omni/Cluster only) |
| DC-15 | ROS 2 tier | Tier 1 on x86/Pi, Tier 3 on Jetson's 24.04 [C-W7-027] | Tier 3; containers everywhere anyway [C-W7-026] | Tier 2 amd64 | D (small: ROS runs in containers on every flavor, 08 FF-6) |
| DC-04 | CRA, FOSS self-assessment route | Modified-Ubuntu terms add a vendor dependency to the route | Cleanest FOSS story (firmware caveats apply to all) [C-W6-013] | Alma clean, RHEL not | A |
| Lab | What actually ran in our lab | Nothing | Rugix A/B, RAUC A/B, k3s footprint and restore, all on Debian 13 [C-LAB-debian-rugix-020, C-LAB-rauc-012, C-LAB-k3s-footprint-restore-007] | bootc + greenboot [C-LAB-fedora-bootc-008] | **A** |
| Proven competitor | Constraint-matched appliance on the stack | none found shipping an Ubuntu A/B appliance | umbrelOS 2.0 (Pi 5 + x86, small team) [C-W2-043] | RHDE (vendor, no Pi) [C-W2-041] | **A** |

**Tie-break verdict: A (Debian 13).** Ubuntu's real advantages (DC-13, DC-15) are concentrated on NVIDIA hardware, and they are captured by the flavors OneMind runs there anyway (L4T Ubuntu on Jetson; Ubuntu LTS + RKE2 permitted for the GPU-server tier). Debian wins the questions that are hard to undo: legal redistribution, the Pi 5 pipeline, and lab-proven integration.

**What re-opens S1 (switch the core to Ubuntu 26.04):** all three of (1) Canonical grants written redistribution permission on acceptable terms (Q-W2-1), (2) Pro for Devices is priced within H-1 margins (Q168), (3) NVIDIA ships a JetPack on 26.04, which turns D into one release family. The switch is cheap if done early, because both are apt-based and the image is defined in a Dockerfile-style build [C-W2-043]. **What re-opens it toward bootc:** a ledgered Pi 5 bootc result passing W2-HW-3 plus a fixed greenboot #219 downgrade bug [C-LAB-fedora-bootc-013].

### 3.2 S2 · Image, A/B update and rollback framework (ADR-001 D3)

**Gates (W3):** RAUC G1 PASS (LGPL-2.1) [C-W3-017 in 04] · G2 COND (x86, Pi 5; Jetson via NVIDIA backend) [C-W3-049]. Mender OSS G2 COND (Jetson only via Yocto) [C-W3-053]. Rugix G2 COND (no Jetson) [C-W3-013], G3 COND (single maintainer, latest-minor-only security support) [C-W3-001, C-W3-004]. SWUpdate, OSTree/bootc, Kairos agent **FAIL G2** (Pi 5 unproven / GRUB-only / Pi 5 unsupported) [C-W3-058]. NVIDIA L4T A/B is a Jetson backend, not a standalone candidate.

| Candidate | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | Frozen total | Corrected |
|---|---|---|---|---|---|---|---|---|---|
| **RAUC** | 3 [C-W3-017] | 2 [C-W3-021] | 4 → **3** [C-W3-018, C-TD-home-assistant-os-014] | 3 [C-W3-029] | 3 [C-W3-020] | 4 [C-W3-017] | 3 [C-W3-019] | 61.0 | **58.0** |
| Mender OSS | 3 [C-W3-069] | 3 [C-W3-053] | 3 [C-W3-055] | 2 [C-W3-040] | 3 [C-W3-053] | 3 [C-W3-055] | 3 [C-W3-053] | 57.0 | 57.0 |
| Rugix | 2 [C-W3-001] | 2 [C-W3-013] | 3 [C-W3-008] | 3 [C-W3-036] | 3 [C-LAB-debian-rugix-020] | 4 [C-W2-048] | 2 [C-W3-016] | 52.0 | 52.0 |

**Correction S2-1 (RAUC C3 4 → 3):** both refuters on P0-W3-2 showed the anchor-4 items are weaker than scored. RAUC's CRL support is not used by its reference adopter: HAOS's 2026 PKI rotation dropped CRLs from its keyrings [C-TD-home-assistant-os-014]; RAUC had a 2026 signature-coverage CVE for large "plain" bundles [C-DEC-004]; and RAUC has no native systemd-boot backend [C-DEC-001], so the "Secure Boot without a later layout change" item is a design inference until spike X-2R. Anchor 5 is not reachable either way (no dm-verity root yet). Lab results lift nothing above 3 on their own, but they do confirm anchor 3 *in our lab* [C-LAB-rauc-015…018].

**Sensitivity (corrected):** RAUC 58.0 vs Mender 57.0 is a **tie**; the winner flips to Mender in 3 of 14 runs (C2 +5, C4 −5, C6 −5). **Fragile.**

**Tie-break (decision-critical evidence):**
- **DC-09 (Jetson base):** W7 keeps stock L4T Ubuntu [C-W7-007]. Mender's Jetson advantage exists only in a Yocto/meta-tegra rebuild [C-W3-053], so it does not apply to the chosen Jetson flavor. → RAUC.
- **DC-06 (maintainers):** Rugix's bus factor was **upheld** by both refuters [C-W3-001]; RAUC and Mender both have multi-author bases. → RAUC or Mender.
- **Cost (C6):** Mender's delta updates are commercial; RAUC's adaptive updates are open source [C-W3-055]. → RAUC.
- **Proof:** RAUC runs HAOS (constraint-matched appliance, Pi 5 tryboot) and passed every pre-registered test in our lab on Debian 13 x86 [C-LAB-rauc-013…018]; Mender has no current constraint-matched appliance (Umbrel left it) [C-W3-040]. → RAUC.

**Verdict: RAUC leads, with conditions** (verity bundles only, version ≥ 1.15.2, 3 boot tries, engine-neutral layout; §4.2). **Rugix remains a legitimate founder choice** (it also passed our lab on both architectures with a real k3s gate [C-LAB-debian-rugix-022]); see §6.

### 3.3 S3 · App runtime and Kubernetes (ADR-001 D4)

**Gates (W4, parts S3 controls):** k3s passes all with G3/G4 CONDITIONAL [C-W4-001 in 05, C-W4-012]. RKE2 G5 CONDITIONAL (4 GB minimum, 8 GB recommended) [C-W4-072 in 05]. MicroShift FAIL G2. **Docker/Compose, Podman+Quadlet and the tiered mix FAIL G5** (no single app platform from Pi to a multi-node GPU cluster) [C-W4-043, C-W4-044].

| Candidate | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|
| **k3s** | 3 [C-W4-012] | 3 [C-W4-022] | 1 [C-W3-063] | 4 [C-TD-olares-021] | 4 [C-W4-078] | 4 [C-W4-075] | 4 [C-W4-022] | **63.0** |
| RKE2 | 3 [C-W4-012] | 4 [C-W4-038] | 1 [C-W3-063] | 3 [C-W4-012] | 3 [C-W4-072] | 4 | 4 [C-W4-038] | 62.0 |
| Talos-native | 3 | 3 [C-W4-064] | 2 | 3 | 3 | 4 | 4 [C-W4-037] | 61.0 |
| k0s | 2 | 3 [C-W4-038] | 1 | 2 | 4 [C-W4-045] | 4 | 3 | 51.0 |
| *Docker/Compose (G5 relaxed)* | 3 | 3 | 1 | 5 [C-W4-043, C-W4-044] | 4 | 4 | 3 | *64.0* |

(Full cells in `05-…` §2.2.)

**Corrections:** none to the numbers. The refuters forced two changes to the **decision text**, not the scores: (1) the platform-node gate must include **storage**, not only RAM: k3s's own docs say SD cards and eMMC "cannot handle the IO load" [C-W4-002]; (2) the competitor framing must include TrueNAS SCALE, a single-box appliance that ran its app catalog on Kubernetes and then moved it to Docker in 24.10 [C-DEC-007], for app-portability and user-complexity reasons (refuter W4-P0-1-technical).

**Sensitivity (W4):** **fragile**: the winner changes to RKE2 in 3 of 14 runs [05 §2.3]. **Tie-break:** k3s and RKE2 are one family (same vendor, snapshot CLI, upgrade controller) [C-W4-012], so the flip means "use the bigger sibling on GPU servers", which is the recommendation. Talos is excluded by G2 (no merged Orin support) [C-W4-064]. **Gates relaxed:** with G5 relaxed, Compose (64) ties k3s, so **G5 (F-14) is the only gate keeping Compose out**; §6 summarises its steelman.

### 3.4 S4 · Backup and restore (ADR-001 D5)

| Candidate | G1–G5 | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|---|
| **restic** | PASS (BSD-2) [C-W5-023] | 3 [C-W5-023] | 4 lab [C-W5-009] | 4 [C-W5-023] | 3 [C-W5-050] | 4 [C-LAB-k3s-footprint-restore-015] | 5 [C-W5-058] | 4 [C-W5-024] | **75** |
| Kopia | PASS | 3 | 3 | 3 [C-W5-028] | 3 [C-W5-041] | 4 | 5 | 3 | 66 |
| borg / Velero | COND | 2 / 3 | 3 / 2 | 3 / 1 [C-W5-021] | 0 / 2 | 3 / 2 | 5 / 5 | 2 / 3 | 49 / 49 |
| ZFS send · Longhorn backup | G1 COND (CDDL) · G5 FAIL | | | | | | | | not ranked |

**Sensitivity:** restic scores ≥ Kopia on every criterion, so it wins all 14 runs; margin 9.0. **Robust.** No correction needed: both refuters **upheld** W5-P0-1, and the two weakened verdicts on W5-P0-2 concern procedure conditions (§5.4), not the engine choice.

### 3.5 S5 · Kernel route (ADR-001 D2/D6)

| Route | Gates | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|---|
| **K1 board maintainer's kernel** (Debian / Raspberry Pi / NVIDIA L4T) | PASS/COND [C-W18-029] | 3 [C-W18-001] | 4 [C-W18-019] | 3 [C-W18-012] | 4 [C-W18-012] | 4 [C-W18-015] | 3 [C-W18-069] | 4 [C-W18-027] | **71.0** |
| K2 OneMind-configured LTS (HAOS way) | COND | 3 | 3 [C-W18-020] | 3 | 5 [C-W18-062] | 3 [C-W18-066] | 3 | 3 | 66.0 |
| K3 CIP SLTS | COND | 4 | 3 | 3 | 3 | 3 | 3 | 3 | 64.0 |
| K4 patched kernel | COND | 2 | 3 | 2 | 2 | 2 | 3 | 2 | 46.0 |
| K5 microkernel / new kernel | **FAIL** G2–G5 [C-W18-027, C-W18-029] | | | | | | | | not ranked |

**Sensitivity:** K1 wins 14/14, minimum margin 3.53. **Robust.** No numeric correction. The refuters' changes are to wording and to one missing gate (§5.5).

**Note on the base decision:** K1 was scored with Debian as the x86 kernel. If S1 is ever re-opened toward Ubuntu, K1 becomes "Ubuntu's kernel + Raspberry Pi's + NVIDIA's" with the same structure; the route choice does not change.

### 3.6 Reproducing the corrected numbers

```python
W=[20,20,15,15,10,10,10]
def tot(s,w): return sum(a*b for a,b in zip(s,w))/5
def run(c):
    for i in range(7):
        for d in (5,-5):
            w=[x*(100-(W[i]+d))/(100-W[i]) for x in W]; w[i]=W[i]+d
            r=sorted(((tot(v,w),k) for k,v in c.items()),reverse=True)
            print(f"C{i+1}{d:+d}", r[0][1], round(r[0][0]-r[1][0],1))
run({'D':[3,3,3,3,3,2,5],'A':[3,3,3,3,3,3,3],'C':[3,1,3,3,4,3,4]})   # S1 corrected
run({'RAUC':[3,2,3,3,3,4,3],'Mender':[3,3,3,2,3,3,3],'Rugix':[2,2,3,3,3,4,2]})  # S2 corrected
```

---

## 4. The recommendation per tier, in detail

### 4.1 Base OS (D2)

- **Core image:** Debian 13 from a snapshot-pinned base, defined as a container build (umbrelOS pattern) [C-W2-043]. x86_64 and generic arm64 use Debian's stock kernel [C-W18-012]; Pi 5/CM5 adds Raspberry Pi's apt repo and `linux-image-rpi-2712` [C-W2-044].
- **Jetson flavor:** NVIDIA L4T Ubuntu 24.04 (JetPack 7.2+), which now covers Orin as well as Thor [C-W7-008]. A Debian rootfs on Jetson is not an NVIDIA-supported option; Yocto meta-tegra is the named fallback [C-W7-007].
- **GPU-server flavor (Omni/Cluster):** permitted on Ubuntu LTS + RKE2, because that is the set NVIDIA validates (GPU Operator on Ubuntu; AI conformance on RKE2) [C-W2-026, C-W4-038]. **Gated on Q-W2-1:** Canonical's policy applies to *any* modified Ubuntu image OneMind redistributes, including this flavor and arguably the Jetson flavor [C-W2-050]. Until counsel answers, the Pro box (single RTX) stays on Debian + NVIDIA driver + toolkit + device plugin, which works [05 §7.2].
- **Industrial profile (year 2):** one Containerfile building on CentOS Stream 10 / AlmaLinux 10 (free) and RHEL 10 image mode (paid, IEC 62443 path) with greenboot gating on k3s; Red Hat Device Edge for enterprise Orin buyers [C-W2-041, C-W2-042]. Fedora IoT bootc builds in CI as a canary with no support promise [C-W2-015].
- **Lifecycle plan:** no base reaches 2036-12-31 on one free release [03 P0-6]. Plan **one or two in-place rebases per box lifetime** (Debian 14, then 15) and test the rebase in CI from day one (T-W3-04). Do **not** plan on Freexian ELTS for a fleet unless an agreement permits redistribution to customer devices [C-W2-004]; ELTS guarantees only amd64, with other architectures "on request" [C-W6-023].
- **Rejected as the base:** Talos (no merged Orin support [C-W4-064]), Kairos (no Pi 5), SL Micro (support ends 2029), balenaOS (no k3s), NixOS and Alpine (short lifecycles), CIP Core (Pi 5/Jetson unproven; kept as the industrial kernel option).

### 4.2 Image build, updates and rollback (D1, D3)

1. **Engine:** RAUC on x86 (GRUB backend at launch, lab-proven [C-LAB-rauc-013]) and Pi 5 (custom tryboot backend; HAOS's script is the reference) [C-W3-066]. Jetson: NVIDIA rootfs A/B + image-based OTA with OneMind's gate in NVIDIA's validation hook [C-W3-049, C-W3-050].
2. **Hardening the engine choice (from the refuters):** set `bundle-formats` to verity only [C-DEC-005]; require RAUC ≥ 1.15.2 or a confirmed Debian backport of the CVE-2026-34155 fix, because Debian 13 ships RAUC 1.13 [C-LAB-rauc-002, C-DEC-004]; install `rauc-service` (Debian splits the D-Bus daemon out) [C-LAB-rauc-002]; set `check-purpose=codesign-rauc` if signing certificates carry the codeSigning EKU [C-LAB-rauc-009].
3. **Boot attempts:** RAUC's reference GRUB script gives one try, so a single interrupted first boot abandons a good update [C-LAB-rauc-006, C-LAB-rauc-018]; use **3 tries** as HAOS does [C-LAB-rauc-010], plus a hardware watchdog and `panic=` reboot.
4. **One release contract:** one signed manifest per release listing a bundle per board family; one key hierarchy; one gate; one `onemind update` CLI/API/UI [04 V2].
5. **The gate (fresh signals only):** local kubelet healthz answers (probe the address it actually listens on; it was `[::1]` in our guest [C-LAB-debian-rugix-025]); node heartbeat newer than this boot; core pods Ready since this boot; 3 consecutive passes; data partition read-write; local OneMind API answers. Apps are not in the gate. A gate reading only API status committed a broken update in our lab [C-LAB-debian-rugix-023]; a gate that gave up on the first refused commit reverted a good one [C-LAB-debian-rugix-024].
6. **k3s and rollback:** k3s lives inside the read-only slot; its datastore is on the data partition; each trial boot runs against a copy; a k3s-minor guard refuses to start an older k3s on a newer datastore and offers the snapshot restore [C-W3-063]. The system-upgrade-controller is not used on image nodes because it writes into the host root [C-W3-065].
7. **Signing from release 1:** offline root, 2-of-3 release signers, signed manifest with expiry and offline grace, in-band revocation, CA rotation drill using HAOS's cross-signing method [C-W3-024]. Umbrel's *stable* release is the warning: it runs a server-supplied script [C-W3-034].
8. **No auto-retry:** after a rollback the release is marked bad on that device. (bootc's default timer re-staged a known-bad image in our lab [C-LAB-fedora-bootc-009]; the same mistake is easy to make with any engine.)
9. **Update default:** see §4.7 and `26-…` (CRA vs R-1, founder decision).

### 4.3 Disk layout (decide now; changing it later means a reflash)

This reconciles W3 (RAUC + GRUB, §11 of `04-…`) with W6 (Secure Boot later without repartitioning, SEC-01 in `07-…`, which assumed Rugix's systemd-boot flow [C-W6-049]). RAUC has **no native systemd-boot backend**; it offers an `efi` backend that boots EFI-stub kernels from two redundant EFI partitions [C-DEC-001, C-DEC-002] and a `custom` backend that can drive any bootloader [C-DEC-003]. The layout below keeps all three routes open:

| # | Label | Size | Content |
|---|---|---|---|
| 1 | `onemind-esp` | 1 GiB FAT32 | first-stage GRUB + grubenv (two copies) at launch; room for systemd-boot later |
| 2–3 | `onemind-boot-a/b` | 512 MiB each, **FAT32 with the EFI System Partition type** | kernel + initrd now; signed UKIs later, bootable directly by RAUC's `efi` backend |
| 4–5 | `onemind-system-a/b` | 10 GiB each, ≥ 10% verity headroom | read-only root |
| 6 | `onemind-recovery` | 1 GiB, reserved | empty at launch |
| 7 | `onemind-data` | rest | **LUKS2 from first boot** (recovery key now, TPM slot later) [C-W6-047] |

The FAT32/ESP-type choice for boot-a/b is **this file's design inference** from [C-DEC-002]; spike **X-2R** (W6's X-2 re-run with RAUC: signed UKI per slot, LUKS2 unlock after update and rollback) must confirm it on the Dell 5540 and in QEMU+OVMF+swtpm before the first image ships. Pi 5 and Jetson layouts are as in `04-…` §11; Pi and Jetson fusing stays irreversible and only for OneMind-built hardware (07 SEC-04).

### 4.4 Install paths (P-7)

| Path | Who | OS rollback | At launch |
|---|---|---|---|
| P1 Preinstalled box | buyers | yes | when boxes ship |
| P2 Flash image | Pi 5/CM5 | yes | yes |
| P3 USB installer ISO (also rescue disk) | x86 BYO | yes | yes |
| P4 VM appliance (qcow2/vhdx/vmdk/vdi/ova) | try-before-buy, homelab, Mac dev | yes | yes |
| P5 NVIDIA flash + OneMind layer | Jetson | yes (NVIDIA A/B) | beta after T-W3-06 |
| P6 Platform mode on existing Debian/Ubuntu | developers | **no** | developer preview only |
| P7 Fleet / PXE | 100+ devices | yes | year 2 |

Why P6 stays developer-only: script installs have no OS rollback (Olares labels everything but Linux/Spark "not for production" [C-TD-olares-042]), and Home Assistant deprecated its script install modes in 2025 [C-W3-028]. Build order (W18 P0-8): the platform is developed first as P6 on plain Debian and in a VM, and the image is produced from the same layers from about week 3 [C-W18-062, C-W18-063, C-W18-064].

### 4.5 Kubernetes (D4)

- **Platform node = ≥ 4 GB RAM and SSD/NVMe** (or industrial eMMC with a measured endurance budget). 8 GB is the recommended server size; 4 GB boxes run the slim profile and are sold as profiles (TAK node, greenhouse), not "run anything" [C-W4-002, C-W4-078]. Lab: k3s added +936 MiB at idle and +1,529 MiB under load on a 4 GiB arm64 VM [C-LAB-k3s-footprint-restore-007, C-LAB-k3s-footprint-restore-008].
- **Below that, or SD-only:** NATS leaf with store-and-forward (lab: 600/600 delivered after an outage [C-W8-050]) plus an MCP/MHS adapter; optionally a k3s agent on SSD.
- **RKE2:** only when a buyer needs FIPS/STIG or an AI-conformant GPU cluster (RKE2 is on the AI-conformance list; k3s is not) [C-W4-038]. k0s is the named alternative for that slot and goes into the founder bake-off [C-W4-045].
- **Portability guard (TrueNAS lesson [C-DEC-007]):** apps never depend on k3s-only features; the Market compiles `onemind.app.yaml` to Helm, and imports Compose files, so the app catalog is not hostage to the runtime.
- **Version treadmill:** about 8–10 Kubernetes minor upgrades to 2036, never skipping one, each preceded by a datastore snapshot [C-W4-012, C-W3-063].
- **Ingress:** Gateway API with Traefik; ingress-nginx is unmaintained since March 2026 [C-W4-016].
- **DOKS conversion:** 13 dependencies, four of them real work, not "three changes" [C-W4-063]; plan in `05-…` §9.

### 4.6 Storage and backups (D5)

- **Storage:** OneMind storage class with `Retain`; k3s's default local-path class deletes data with the claim [C-W5-019]. Longhorn only on 3+ nodes with LUKS volumes; ZFS mirror optional on Pro, labelled "not a backup".
- **Single-box datastore:** online `sqlite3 .backup` + integrity check + token + node password + encryption config, all inside the same restic snapshot as the volumes [C-W5-009]. Lab: a full restore onto a fresh VM brought back all 32 pods with identical data [C-LAB-k3s-footprint-restore-011]. **Conditions the refuters added:** same k3s version, **same node name** (local volumes are pinned to it [C-W5-019]), app-consistent dumps for databases, and never a raw copy outside restic (state.db + token decrypts everything [refuter W5-P0-2-security]).
- **Clusters:** `k3s etcd-snapshot`, restic-wrapped, because snapshots are not encrypted [C-W5-013]. On restore to a new host, pass the original token explicitly; restoring only the token file failed in our lab [C-LAB-k3s-footprint-restore-012, C-LAB-k3s-footprint-restore-013].
- **Growth:** SQLite → etcd in place with `--cluster-init` when a third server joins [C-W5-005].
- **Keys:** restic three-key repository (device, owner recovery, optional escrow) [C-W5-023]; emergency kit required to finish setup.
- **Verified restores:** daily `restic check --read-data-subset`, weekly scratch restore with app probes, "last verified restore" in the dashboard (W5-R7). Restore health checks use fresh signals, not restored status [C-W5-010].
- **Velero:** optional Cluster-tier app only, with a pre-created repository Secret (default static password otherwise) [C-W5-021].

### 4.7 Security and compliance (D6)

- **Day 1:** the §4.3 layout; signed releases; read-only root; k3s secrets encryption, audit, Pod Security Restricted for Market namespaces, default-deny network policy; mandatory owner credential at first boot.
- **Capability gateway:** human approval enforced *in the OS gateway* for physical actuation, OS updates, app installs and data export, because prompt injection has no reliable prevention [C-W6-068] and umbrelOS lets an MCP agent install an OS update and reboot [C-W6-052].
- **Robot runtime exception:** a signed, allowlisted profile granting host network, host IPC and `SYS_NICE` only to robot apps, because Fast DDS shared memory needs them [C-W7-033].
- **CRA:** treat the OS as Class I [C-W6-011]; security updates installed automatically by default with opt-out, postpone and a window [C-W6-008, C-W6-019] (**founder decision**); declare support periods per SKU, capped by each board's kernel window; CVD policy and ENISA reporting runbook; route to self-assessment chosen by 2027-Q2 (§5.6).
- **Public safety:** FIPS 140-3 modules (Go #5247, OpenSSL 3.1.2 provider), not RKE2's historical 140-2 certificate [C-W6-026, C-W6-028]; CJIS also accepts AES-256 under FIPS 197 [C-W6-033].

---

## 5. Adversarial tables, with written responses

Every P0 conclusion in W2–W8 and W18 was sent to at least two independent refuters with different lenses; each refuter saw only the claim and its sources. Files: [`evidence/adversarial/`](evidence/adversarial/). "Response" is required for every weakened or refuted verdict (brief §2 rule 7). **No conclusion was refuted.**

### 5.1 Base OS (S1, W2)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| P0-1 Ubuntu 26.04 ranks first, robust | technical | **weakened** | Both main supports (GPU Operator K3s column, ROS 2 Tier 1) describe x86/Pi 5 only; Jetson ships Ubuntu 24.04 (Tier 3, GPU Operator unsupported); the A/B layer is unbuilt; the ±5 weight sweep doesn't test ±1-anchor errors; 26.04 ESM ends May 2036; Pi 5 boot regression open ([file](evidence/adversarial/W2-P0-1-technical.md)) | NVIDIA ships JetPack on 26.04; OneMind A/B on 26.04 lab-proven on three boards; the linux-raspi bug fixed | **Accepted.** §3.1.3 restates the supports (S1-3), adds a cell correction (S1-1) and shows the ±1-anchor variant (S1-4). The result is a tie, decided for Debian by §3.1.5. The Pi 5 regression is ledgered [C-DEC-006]. |
| P0-1 | longevity / vendor | **weakened** | The winner is two Ubuntu releases from two vendors; Canonical's ESM doesn't cover the NVIDIA kernel; NVIDIA's Ubuntu cadence lags about two years; Canonical's own Pi A/B covers only the boot partition ([file](evidence/adversarial/W2-P0-1-longevity.md)) | A dated JetPack-on-26.04 roadmap; Canonical documenting Pro coverage of the Jetson kernel to 2034+ | **Accepted.** These are why D-C1 is shown at 2 in the variant and why the Ubuntu win does not survive the tie-break. The Jetson lifecycle risk applies to every candidate and is handled in §5.7. |
| P0-2 Fedora IoT not the single base | technical | **weakened** | Release EOL isn't stream EOL for an image fleet; Fedora 45 runs on Pi 5 (Oct 2026 posts); bootc on Pi 5 is reported in a bootc issue; "single base" is a straw man for F-12 ([file](evidence/adversarial/W2-P0-2-technical.md)) | bootupd ESP-root firmware support merged; a bootc Pi disk image that boots without a prior Fedora IoT install; Pi 5 in reference platforms; ≥3 human committers | **Accepted in part.** The claim is restated: "not the single base *today*; a supported Industrial profile and a CI canary". The Pi 5 evidence is newer than W2's and is not yet ledgered, so it cannot raise a score; founder test W2-HW-3 is the path. Our own lab adds a reason for caution: greenboot can silently downgrade a healthy box after a power cut during finalize [C-LAB-fedora-bootc-011, C-LAB-fedora-bootc-013]. |
| P0-2 | longevity / vendor | **upheld** | (counter-case listed in file) ([file](evidence/adversarial/W2-P0-2-longevity.md)) | A long-life tier on Pi (Fedora IoT LTS or RHEL/Alma on Pi 5) **and** upstream Pi bootc first-class | No response required. |
| Steelman: RHEL bootc as the base | — | steelman | See §6.1 ([file](evidence/adversarial/W2-steelman.md)) | Pi 5 hardware test passes; Ubuntu drops out; Rugix rebase spike fails | Answered in §6.1. |

### 5.2 Updates (S2, W3)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| P0-W3-1 Rugix bus factor ≈ 1 | technical | **upheld** | Company-backed (Silitics), mature since 2023, fast advisories, forkable ([file](evidence/adversarial/W3-P0-W3-1-technical.md)) | A second merger with ≥10% of commits; governance or escrow statement | No response required. The counter-points are why Rugix stays the documented alternative. |
| P0-W3-1 | security | **upheld** | Two High advisories handled in hours ([file](evidence/adversarial/W3-P0-W3-1-security.md)) | ≥25% of PRs reviewed by someone else; an LTS line | No response required; the refuter's own finding that security fixes are self-merged without review strengthens the claim. |
| P0-W3-2 RAUC leads S2 | technical | **weakened** | Anti-downgrade is a tie; CRLs unused by HAOS; Rugix 1.4 made delta default; Mender is ahead on Jetson; the 4-point lead is 1–2 anchor steps ([file](evidence/adversarial/W3-P0-W3-2-technical.md)) | DC-09 picks a Yocto Jetson flavor (→ Mender); RAUC fails the lab; Rugix gains a second maintainer | **Accepted.** RAUC C3 corrected to 3 (S2-1); the corrected result is a tie, resolved by DC-09 (stock L4T) and cost (Mender delta is paid) in §3.2. RAUC passed every lab test [C-LAB-rauc-013…018]. |
| P0-W3-2 | security | **weakened** | CVE-2026-34155 in RAUC's default "plain" format; signing-time validation weakens revocation; anti-downgrade is a static floor ([file](evidence/adversarial/W3-P0-W3-2-security.md)) | A verity-format integrity advisory; Pengutronix reducing maintenance | **Accepted.** §4.2 item 2 makes verity-only bundles and RAUC ≥ 1.15.2 mandatory [C-DEC-004, C-DEC-005]. `use-bundle-signing-time` stays only for offline boxes with dead clocks, paired with manifest expiry and in-band revocation (04 §8). Anti-downgrade becomes a OneMind monotonic counter in the manifest, as the draft OS standard asks [C-W6-019]. |
| Steelman: Buildroot + RAUC (HAOS way) | — | steelman | See §6.2 ([file](evidence/adversarial/W3-steelman.md)) | DC-20 lab shows far fewer CVEs; a Debian 14 image won't fit the slot | Answered in §6.2. |

### 5.3 Kubernetes (S3, W4)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| P0-1 k3s on every node ≥ 4 GB | technical | **weakened** | The failure mode is storage, not RAM; TrueNAS SCALE ran apps on k3s and left; single-node SQLite fleets bloat over weeks; one thin VM run ([file](evidence/adversarial/W4-P0-1-technical.md)) | A real Pi 5 4 GB on NVMe leaves < 2 GiB or writes > 5 GB/day; a 30-day soak shows state.db bloat; the Market can't compile one manifest to both runtimes | **Accepted.** The gate becomes "≥ 4 GB **and** SSD/NVMe" (§4.5); TrueNAS is ledgered [C-DEC-007]; a 30-day soak (T-W4 soak) and the Market portability rule are added. |
| P0-1 | cost / solo ops | **weakened** | k3s takes ~24% of a 4 GB board before OneMind runs; HARDWARE.md plans 8–16 GB anyway; every box becomes its own cluster to operate ([file](evidence/adversarial/W4-P0-1-cost.md)) | Real Pi 5 4 GB soak < 1.5 GiB free or OOM; offline catch-up across 2 minors fails | **Accepted.** 8 GB is the recommended server size; 4 GB is a limited profile; the fleet cost is real and is why upgrade automation and stepwise catch-up are in the 180-day plan. |
| P0-2 k3s default, RKE2 for GPU/regulated | technical | **weakened** | k0s fits the Pi tier (1 GB) **and** is AI-conformant; Talos now has a Pi 5 overlay ([file](evidence/adversarial/W4-P0-2-technical.md)) | Founder bake-off shows k0s ≤ k3s memory with working Jetson CDI; Talos Orin merged | **Accepted in part.** k0s is added to the Pi 5/Jetson bake-off. k3s stays default because of proven appliance use (Olares) and the founder's existing practice; Talos stays out until Orin merges [C-W4-064]. |
| P0-2 | cost / solo ops | **weakened** | Two distributions cost twice; the regulated tier is a sales tier, not day one ([file](evidence/adversarial/W4-P0-2-cost.md)) | IREN/Mirantis deprioritise k0s; k3s joins AI conformance | **Accepted.** RKE2 is deferred until a buyer requires it (§4.5); until then, one distribution. |
| Steelman: Compose on every box | — | steelman | See §6.3 ([file](evidence/adversarial/W4-steelman.md)) | Pi 5 4 GB fails the budget; device hot-plug needs privileged pods | Answered in §6.3. |

### 5.4 Backups (S4, W5)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| W5-P0-1 `etcd-snapshot` fails on SQLite | technical | **upheld** | Only the subcommand fails; SQLite has a file-copy path ([file](evidence/adversarial/W5-W5-P0-1-technical.md)) | `etcd-snapshot save` succeeds on SQLite | No response required. The decision text says "`etcd-snapshot` is unavailable", never "SQLite can't be backed up". |
| W5-P0-1 | security | **upheld** | The file-copy fallback leaks secrets if left outside restic ([file](evidence/adversarial/W5-W5-P0-1-security.md)) | A kine snapshot driver ships | No response required; the condition is in §4.6. |
| W5-P0-2 SQLite `.backup` + token restores a box | technical | **weakened** | The cited SQLite-only restore failed its marker check until etcd conversion; node name is a hidden condition; "supported" overstates the vendor ([file](evidence/adversarial/W5-W5-P0-2-technical.md)) | Re-run SQLite-only restore; restore under a different hostname | **Accepted, and largely answered by the second lab.** The separate k3s-footprint-restore spike restored SQLite-only onto a fresh VM and verified PostgreSQL data, a ConfigMap, a Secret and an 8 MiB file [C-LAB-k3s-footprint-restore-011]. The node-name and same-version conditions are now explicit (§4.6); restore under a new hostname is founder test T6 in that spike's README. |
| W5-P0-2 | security | **weakened** | state.db + token decrypts everything; the first lab staged them unencrypted and world-readable ([file](evidence/adversarial/W5-W5-P0-2-security.md)) | A k3s change that stops storing the encryption key in bootstrap data | **Accepted.** Rule: datastore copy and token never exist outside the restic repository; the token is also held out of band in the recovery kit; the second lab found no Secret plaintext in the repository [C-LAB-k3s-footprint-restore-015]. |

### 5.5 Kernel (S5, W18)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| P0-1 Linux is the only family that passes | technical | **weakened** | "CUDA is Linux-only" is false (Windows); ROS citation expiring; a kernel-maintenance gate that Linux only partly passes on Jetson ([file](evidence/adversarial/W18-P0-1-technical.md)) | NVIDIA ships a non-Linux Jetson BSP with CUDA; a conformant non-Linux control plane | **Accepted.** Restated: Linux is the only family that passes because Kubernetes' control plane runs only on Linux [C-W18-029], Windows needs Server licences and has no Pi 5/Jetson image, and no non-Linux kernel has a Jetson CUDA path [C-W18-027]. A "maintained kernel on every tier" requirement is added to the kernel contract (§5.7). |
| P0-1 | cost / solo ops | **weakened** | "Linux" is really three vendor kernel lines plus thousands of kernel CVEs a year ([file](evidence/adversarial/W18-P0-1-cost.md)) | One maintainer provably can't run Debian + Jetson Ubuntu on one update framework | **Accepted.** The cost is why kernel updates ride the image pipeline automatically and why the per-board support period is capped by the vendor kernel window (§4.7). |
| P0-2 no non-Linux kernel viable | technical | **weakened** | Over-scoped: PX4 drones run NuttX, IIoT nodes run Zephyr, QNX has an NVIDIA safety path ([file](evidence/adversarial/W18-P0-2-technical.md)) | A licensable non-Linux BSP with CUDA on Jetson | **Accepted.** Restated: "Linux is the only viable **host** kernel; RTOS and microkernel peer nodes (NuttX, Zephyr, QNX partitions) are first-class managed devices at the boundary." |
| P0-2 | cost / solo ops | **weakened** | Same scope point; seL4 is a possible funded safety-partition add-on ([file](evidence/adversarial/W18-P0-2-cost.md)) | A funded partner offering a maintained seL4 partition | **Accepted** as above; seL4 is a watch item for Robotics/Omni, not a plan item. |

### 5.6 Security and the CRA (W6)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| P0-1 (DC-04) rebase in place meets the CRA support period | security | **weakened** | Art. 13(10) covers *software products*; for hardware, Recital 40 says keep patching the latest compatible OS for boards that can't move; ELTS arm64 is "on request" ([file](evidence/adversarial/W6-P0-1%20(DC-04)-security.md)) | Commission guidance applying 13(10) to OS images on hardware; a lab A/B rebase 13 → 14 on Pi 5 and x86 | **Accepted.** The plan no longer relies on 13(10). Per SKU, the declared support period is capped by the board's kernel window, and a board that can't move to the next Debian is either patched by OneMind on the old release or covered by a quoted ELTS arm64 agreement (outreach draft needed). The rebase spike T-W3-04 becomes a gate. |
| P0-1 (DC-04) | cost / business | **weakened** | The "no additional hardware cost" condition fails when a vendor drops a board (JetPack 4 users were told to buy Orin) ([file](evidence/adversarial/W6-P0-1%20(DC-04)-cost.md)) | Adopted guidance that a base-OS major update is a substantial modification | **Accepted.** Same response; Jetson SKUs get the shortest declared period (§5.7). |
| P0-2 FOSS image is the self-assessment route | security | **weakened** | The boxes may not be "operating systems" at all; "fully FOSS" is impossible on Pi 5 (non-free EEPROM firmware) and Jetson (NVIDIA BSP licence) ([file](evidence/adversarial/W6-P0-2-security.md)) | Guidance on whether firmware blobs disqualify Art. 32(5) | **Accepted.** "Keep the EU image fully FOSS" is withdrawn as a hard rule. Replacement: keep all OneMind-authored code in the base image Apache-2.0 and keep closed features out of it (consistent with D-001 [C-W6-013]); get a counsel opinion on classification and on firmware blobs; choose the route by 2027-Q2. |
| P0-2 | cost / business | **weakened** | EN 304 626 will probably be cited before it bites; the FOSS rule may cost revenue for nothing ([file](evidence/adversarial/W6-P0-2-cost.md)) | EN 304 626 cited before ~2027-Q3 | **Accepted** as above; track EN 304 626 [C-W6-019] and budget a notified body as the fallback. |

### 5.7 Robotics (W7)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| FF-1 (DC-08) NVIDIA gives no software support period | robotics | **weakened** | r35 actually ended Oct 2026 (so branch lives are 5.7 and 4.5 years, shrinking); NVIDIA does publish a general policy (~2 years active, then sustaining); Jetson Nano was sold after its software ended ([file](evidence/adversarial/W7-FF-1%20(DC-08)-robotics.md)) | NVIDIA publishes per-branch end dates reaching module availability | **Accepted.** C-W7-005's "still active" wording is superseded by the refuter's finding (to be re-ledgered by W7). Rule: each Jetson SKU's declared support period = remaining life of its L4T branch at ship date + one planned in-field branch upgrade via NVIDIA image-based OTA [C-W3-050]; every Jetson flashed A/B from day one. |
| FF-2 (DC-08) mainline can't replace NVIDIA's kernel | robotics | **weakened** | Talos builds NVIDIA's out-of-tree modules against a mainline LTS and runs CUDA on Orin (open PR); NVIDIA's 6.8 is not an LTS kernel [C-W18-001] | That PR merged and stable across two kernel updates | **Accepted.** Launch stays on NVIDIA's kernel (K1). A "bring your own LTS kernel" Jetson track is a watch item with that PR as its trigger. |

### 5.8 IoT / IIoT (W8)

| Claim | Lens | Verdict | Strongest counter-argument | Flip evidence (short) | Written response |
|---|---|---|---|---|---|
| P0-1 G4 not failed (CONDITIONAL) | IIoT | **weakened** | Debian's RT kernel can't drive a Pi 5 (RP1 mainline only from 6.17); Pi RT kernel is "experimental"; open62541 has 23 open CVEs marked no-DSA in trixie ([file](evidence/adversarial/W8-P0-1-IIoT.md)) | Fedora/CIP ship supported Pi 5 RT while Raspberry Pi's stays experimental; go-fdo archived | **Accepted.** G4 stays CONDITIONAL with sharper mitigations: Pi 5 soft real time is OneMind-owned work (G4-M1) and an RT IIoT SKU defaults to x86 with Debian's `linux-image-rt` [C-W8-001]; open62541 ships as a pinned upstream container app, not the Debian package. |
| P0-2 62443-4-2 without Red Hat | IIoT | **upheld** | The examples are vendor derivatives (Moxa, CIP), not stock Debian ([file](evidence/adversarial/W8-P0-2-IIoT.md)) | A buyer requiring an OS-level component certificate that only RHEL/MicroShift has | No response required; the industrial route (own 62443-4-1 process vs certified partner) is a founder decision in `26-…`. |

---

## 6. Runner-up steelmen, summarised fairly

### 6.1 RHEL-family bootc as the base ([W2-steelman](evidence/adversarial/W2-steelman.md))
**Its case:** one Containerfile builds the OS as an OCI image; greenboot already implements "commit only when healthy" and did so in our lab [C-W2-052, C-W2-054]; `bootc switch` rebases without reflashing by design [C-LAB-fedora-bootc-015]; three suppliers on one format (Alma free, CentOS, RHEL paid and IEC 62443-certified [C-W2-042]); NVIDIA and Red Hat ship Jetson as a bootc image (RHDE [C-W2-041]). It re-scores bootc at 60–64.
**Where it is right:** on update mechanics and the industrial story, it is the strongest lineage; that is why it becomes the Industrial profile.
**Why it is not the base now:** the Pi 5 route is experimental and community-run by its own admission; the Jetson route needs a paid Red Hat subscription; NVIDIA's GPU Operator doesn't list RHEL with k3s [C-W2-026]; and our lab found greenboot rolling a healthy box back after a power cut in finalize, an open upstream bug [C-LAB-fedora-bootc-011, C-LAB-fedora-bootc-012]. **What would make it the base:** §3.1.5's re-open conditions.

### 6.2 Buildroot + RAUC, the HAOS way ([W3-steelman](evidence/adversarial/W3-steelman.md))
**Its case:** the most proven appliance stack (HAOS), tiny verity-checked images, chained 3-year LTS lines with no distro rebases, a fully enumerated SBOM for the CRA. Its own re-score puts it at 57 vs 59 for Debian + RAUC, a tie.
**Where it is right:** for an appliance with no NVIDIA userland, it is excellent, and it is the source of our engine, our signing pattern and our failure lessons [C-W3-024, C-W3-025].
**Why it loses:** no packaged NVIDIA container toolkit, per-board CI of 75–160 minutes, and nothing in the robotics/AI ecosystem targets it; those are exactly C2, C5 and C7 for a solo founder (M-6, M-7). **What would flip it:** a DC-20 lab showing materially fewer CVEs with < 1 h incremental builds, plus a working CUDA path on a Buildroot host.

### 6.3 Docker + Compose on every box ([W4-steelman](evidence/adversarial/W4-steelman.md))
**Its case:** HAOS and Umbrel run Compose/Docker [C-W4-043, C-W4-044]; k3s costs about 1 GB of RAM and many times the writes of a plain engine [C-W4-078]; 8–10 forced Kubernetes upgrades to 2036 [C-W4-012]; NVIDIA's robotics tools and industrial edge platforms ship Compose; TrueNAS went back to Docker [C-DEC-007]. With G5 relaxed it scores 64.
**Where it is right:** on the smallest boxes and for device access. That is why the platform-node gate now includes storage, why 4 GB is a limited profile, why leaves exist, and why the Market must import Compose.
**Why it loses:** G5 (F-14): two runtimes mean two management planes and two app formats; the founder's working assets are Helm/Argo-native; growing one box into a household cluster is a join with k3s [C-W4-006] and a migration with Compose. **What would flip it:** a real Pi 5 4 GB on NVMe failing the budget, or the founder relaxing F-14.

### 6.4 Steelmen written inside the workstream files (not independent)
Kopia over restic (W5 §4.1: Umbrel's choice, Apache-2.0, error correction; loses on multi-key and append-only) · embedded etcd on every box (W5 §2.4; loses on flash wear [C-W5-018 in 06]) · K2 own kernel config (W18 §11.2; loses only on C1/C5) · keep Rugix (W3 §14.1; see §3.2).

---

## 7. ADR-001: confirmed / changed / overturned

| ADR-001 element | Verdict | What changes | Evidence |
|---|---|---|---|
| **D1** Ship our own image, incl. BYO hardware; script = developer mode | **Confirmed** | Build order: platform developed first in P6/VM, image from the same layers from ~week 3; install matrix P1–P7 | C-W3-028, C-W18-062, C-W18-063 |
| **D2** Debian 13 core | **Confirmed after tie-break** | Ubuntu 26.04 led the raw scorecard; tie after correction; re-open conditions recorded (§3.1.5) | §3.1, C-W3-039, C-W2-050 |
| **D2** L4T Ubuntu 24.04 flavor for Jetson | **Confirmed** | JetPack 7.2+ (Orin and Thor); every Jetson flashed A/B; Yocto meta-tegra fallback | C-W7-007, C-W7-008 |
| **D2** "…/DGX only" (Ubuntu only for NVIDIA boxes) | **Changed** | GPU-server flavor on Ubuntu LTS + RKE2 permitted (gated on Q-W2-1) | C-W2-026, C-W4-038 |
| **D2** (implicit) no Fedora/RHEL role | **Overturned** | bootc Industrial profile (year 2) + Fedora IoT canary | C-W2-041, C-W2-042, C-W2-054 |
| **D2** "GPU risk: driver + toolkit + device plugin" | **Confirmed** for Pro; weakened for Omni (no Operator lifecycle, no AI conformance) | C-W4-022, C-W4-023 |
| **D3** A/B, signed, user-controlled | **Confirmed** (A/B, signed) · **changed** (update default is a CRA founder decision) | C-W6-008, C-W6-019 |
| **D3** Tool: Rugix (RAUC alternative) | **Changed**: RAUC leads, Rugix alternative, engine-neutral layout | §3.2, C-W3-001 |
| **D3** Kairos as Jetson/DGX candidate | **Overturned**: NVIDIA's native A/B + OTA instead | C-W3-049, C-W3-050 |
| **D3** Commit only after k3s + core pods healthy | **Confirmed and made concrete** (fresh signals, tries, watchdog, no auto-retry) | C-LAB-debian-rugix-023, C-LAB-rauc-018 |
| **D3** Signing: offline root, revocation, refuse older | **Confirmed and tightened** (manifest expiry with offline grace, 2-of-3 signers, rotation drill, verity-only) | C-W3-024, C-DEC-004 |
| **D3** "k3s updates separately via system-upgrade-controller" | **Overturned** on image nodes (k3s inside the slot, datastore copy, minor guard) | C-W3-063, C-W3-065 |
| **D4** k3s on every tier | **Changed**: every *platform node* (≥ 4 GB + SSD); leaves below; 8 GB recommended | C-W4-002, C-LAB-k3s-footprint-restore-007 |
| **D4** RKE2 for hardened tier, "FIPS 140-2 builds" | **Changed**: RKE2 deferred to a buyer need; FIPS 140-3 modules | C-W6-026, C-W6-028, C-W4-038 |
| **D4** "3 servers support ~1,200 agents" | **Confirmed in substance**; 10k devices = many site clusters + NATS | C-W8-049 |
| **D4** DOKS converts "with three changes" | **Overturned**: 13 dependencies, four real work | C-W4-063 |
| **D4** ingress-nginx → Traefik | **Confirmed**, via Gateway API | C-W4-016 |
| **D5** Disk layout boot · A · B · overlay · data | **Changed**: §4.3 layout (1 GiB ESP, FAT32 boot-a/b, recovery, LUKS2 data) | C-DEC-002, C-W6-047 |
| **D5** local-path; Longhorn 3+ nodes; ZFS "not a backup" | **Confirmed**, plus Retain class and LUKS-only Longhorn | C-W5-019 |
| **D5** k3s datastore via etcd-snapshot | **Changed**: SQLite online backup on one box | C-W5-001, C-LAB-k3s-footprint-restore-011 |
| **D5** restic, not Velero FSB | **Confirmed** (reason corrected: Velero's static default key, beta FSB) | C-W5-021, C-W5-023 |
| **D5** recovery kit, schedule, pre-update snapshot, restore tests | **Confirmed and specified** (three keys, verified restores) | C-W5-023, C-W5-010 |
| **D6** Day-1 baseline | **Confirmed**, plus gateway-enforced approvals and a robot-runtime exception | C-W6-052, C-W6-068, C-W7-033 |
| **D6** Secure Boot/TPM/LUKS "phase 2" | **Changed**: enforcement stays phase 2, **layout prerequisites move to day 1** | C-W6-047, C-DEC-001 |
| **D6** Pi OTP and Jetson fusing only on OneMind hardware | **Confirmed** | 07 SEC-04 |
| **D6** CRA plan | **Changed**: Class I treatment, per-SKU support periods, route decided by 2027-Q2 | C-W6-011, C-W6-012, C-W6-013 |
| ADR §4 spike list | **Partly done in VM** (spikes 2, 3 and parts of 1); hardware spikes 1, 4, 5, 6 remain | §10 |

**Net: ADR-001 is confirmed in architecture and changed in six specifics; no element of its core (own image, Debian core, A/B with health gate, k3s, restic) is overturned.**

---

## 8. P-3 · OneMind mapped onto Olares's layers

Olares organises itself in five layers: Infrastructure → Platform → Framework → Built-in apps → Community apps (`02-competitors/olares.md` §1). OneMind keeps that shape and adds two layers Olares does not have: an **owned OS** underneath, and a **device and robot** layer beside the platform.

| Olares layer (what Olares runs) | OneMind equivalent | What OneMind does differently, and why |
|---|---|---|
| *(none: rides on a host Ubuntu/Debian; the ISO installs Ubuntu)* [C-TD-olares-007] | **L0 · OneMind OS image:** Debian 13 read-only A/B (RAUC), signed releases, health gate, LUKS2 data; Jetson flavor on L4T | Olares has no OS rollback and no release signatures beyond same-origin checksums [C-TD-olares-003, C-TD-olares-020]; owning the image is what makes updates safe (R-1, R-3) |
| **Infrastructure:** k3s v1.33.3 with external etcd, Calico, OpenEBS, HAMi [C-TD-olares-021, C-TD-olares-023] | **L1 · Cluster:** k3s (SQLite on one box, etcd at 3 servers), Flannel (Cilium on GPU/enterprise), local-path Retain / Longhorn, capability mapping to device plugins and DRA, HAMi optional | Olares ships a Kubernetes minor past its end of life [C-TD-olares-022]; OneMind tracks supported minors and snapshots before each upgrade (N-9, R-3) |
| **Platform:** Postgres/Citus, KVRocks, NATS, JuiceFS/MinIO, KubeBlocks | **L2 · Platform services:** NATS JetStream as the authority bus (founder's doctrine), object storage (Garage/MinIO), backup agent (restic), identity store | NATS is the system bus, not just a component; each box has its own JetStream domain and leaf links [C-W4-054] (N-6, AI-9) |
| *(none)* | **L2b · Devices and robots:** MCP/MHS device adapters, ROS 2 bridge, MAVLink, IIoT site bus (MQTT 5 broker bridged to NATS), TAK | Robotics, IoT and TAK are the moat (M-7, F-11, N-7); Olares has none [olares §8] |
| **Framework:** app-service, bfl, system-server, Authelia/LLDAP, backup-server, market, upgrade, headscale | **L3 · OneMind framework:** `onemindd` (update agent), Market controller (`OneMindApp` → Helm), **capability gateway** (MCP/CLI/API/SSH with gateway-enforced approvals), identity (local OIDC, works offline), backup agent, Headscale/Tailscale | Copy: owner-signed dangerous operations, per-app namespaces, linter. Do better: default-deny egress (Olares has ingress-only policies [C-TD-olares-034]), offline identity, verified restores (A-1, U-4, AI-5) |
| **Built-in apps:** Desktop, Files, Vault, Wise, Settings, Control Hub, Studio | **L4 · OneMind app shell + modules** (D-003): dashboard, files, alerts, settings, infrastructure map, family, finance, wellness, robotics, mesh/IoT, OSINT, education | Each module is also a normal Market app with its own `onemind.app.yaml` (D-003) |
| **Community apps:** OAC (Helm + `OlaresManifest.yaml`) checked by a linter [C-TD-olares-028] | **L5 · Market:** Helm + `onemind.app.yaml`, public linter, signed publishers, Compose importer | Trust by signature and provenance, never by image-name substring (the Olares linter exempts any image path containing "beclab/", which lets its own privileged agent pass [C-TD-olares-030]) (A-5, A-6) |
| AI: Router gateway, Lares agent, CLI with Agent Skills | **AI layer** on the capability gateway: local + cloud model routing, Hermes bodies on the box, versioned CLI skills | Copy the Router and CLI-skills patterns (AI-2, AI-4); never a privileged sidecar for the agent |

---

## 9. What competitors do (constraint fit)

| Product | Base / update / runtime (from code) | Constraints | Constraint fit with OneMind | What this decision takes from it |
|---|---|---|---|---|
| umbrelOS 2.0 | Debian trixie in a Dockerfile, Rugix A/B, Pi via Raspberry Pi kernel, Compose apps [C-W2-043, C-W2-044, C-W4-043] | small company, Pi 5 + x86, no k8s, no robotics | **High** for base and Pi pipeline; low for k8s/robotics | Debian core, image-as-container-build, Debian 12 → 13 OTA precedent [C-W3-039]; **not** its commit-at-daemon-start [C-W3-036] or unsigned stable updates [C-W3-034] |
| Home Assistant OS | Buildroot + RAUC, verity bundles, Docker Supervisor [C-W4-044] | funded team, appliance, no k8s | **High** for update engine and signing; medium overall | RAUC, CA rotation by cross-signing [C-W3-024], 3 boot tries [C-LAB-rauc-010]; **not** commit-while-unhealthy [C-W3-025] |
| Olares | host Ubuntu/Debian, k3s, no OS A/B [C-TD-olares-007, C-TD-olares-021] | funded team, x86 + NVIDIA, 8 GB floor [C-W4-042] | **High** for app platform; none for OS safety | Layer model (§8), OAC linter pattern, AI gateway |
| Red Hat Device Edge | RHEL bootc + MicroShift on Orin [C-W2-041] | vendor, no Pi 5 | **High** for Industrial; none for consumer | Industrial profile |
| TrueNAS SCALE | Debian-based appliance; apps moved from Kubernetes to Docker in 24.10 [C-DEC-007] | funded team, single-box NAS | Medium (single-box appliance) | App portability guard; storage gate on k3s nodes |
| NVIDIA JetPack | L4T Ubuntu 24.04, native rootfs A/B + image-based OTA [C-W7-007, C-W3-049] | vendor | **High** for Robotics | Jetson flavor and update backend |

---

## 10. What the VM lab proved, and what it didn't

| Spike | Result | Claims |
|---|---|---|
| Debian 13 + Rugix (x86_64 and aarch64, QEMU) | All pre-declared tests passed in run 4 on both: good update committed after k3s passed fresh checks; bad update rolled back at the 300 s deadline; power cut mid-write survived. Found the **stale-status trap**. | C-LAB-debian-rugix-020…024 |
| Debian 13 + RAUC (x86_64, QEMU) | Passed twice: wrong-key bundle refused; good update committed; unhealthy and unbootable updates rolled back; power cut mid-write and before commit both fell back safely. Gate was a stand-in service, not k3s. | C-LAB-rauc-013…018 |
| Fedora bootc + greenboot (aarch64) | Build, upgrade, automatic rollback, rebase and data survival passed; **power cut during shutdown finalize silently downgraded a healthy box (2/2 runs)**; auto-update timer re-stages a known-bad image | C-LAB-fedora-bootc-008…015 |
| W2 Fedora IoT bootc + k3s gate | Booted green with composefs and SELinux; broken update rolled back with zero manual commands but took 32 min (time target failed) | C-W2-052, C-W2-054 |
| k3s footprint + restore (aarch64) | +936 MiB idle; +1,529 MiB under load with no OOM; SQLite and etcd restores onto fresh VMs succeeded; etcd restore needs the token passed explicitly | C-LAB-k3s-footprint-restore-007…015 |
| W4-1 k3s vs Podman | 2.50 GiB left on 4 GiB; ~2.75 GB/day writes; PASS on pre-registered thresholds | C-W4-078 |
| W8-1 NATS leaf buffering | 600/600 delivered after a hub outage, no gaps or duplicates | C-W8-050 |

**Not proven (founder hardware or later):** real power pulls on the Beelink/Dell (QEMU's kill doesn't drop disk caches); Pi 5 tryboot with RAUC; Jetson NVIDIA A/B with OneMind's gate (T-W3-06); RAUC with a real k3s gate; signed UKIs with RAUC (X-2R); Debian 13 → 14 rebase (T-W3-04); a 30-day k3s soak on Pi 5 NVMe; GPU time-slicing on Debian; cross-k3s-minor rollback (T-W3-03).

---

## 11. Recommendations → requirement IDs

| ID | Recommendation | Requirement IDs |
|---|---|---|
| REC-DEC-01 | Debian 13 core image; Jetson on L4T Ubuntu 24.04; record the Ubuntu 26.04 re-open conditions | R-3, M-6, M-7, N-2, F-14, D-001, RS-4 |
| REC-DEC-02 | Ask counsel and Canonical about modified-Ubuntu redistribution before any Ubuntu-based flavor ships (Q-W2-1) | D-001, H-1, R-3 |
| REC-DEC-03 | GPU-server flavor on Ubuntu LTS + RKE2 permitted after REC-DEC-02; Pro stays Debian | N-8, F-2, AI-8, M-4 |
| REC-DEC-04 | bootc Industrial profile in year 2; Fedora IoT bootc CI canary now | F-11, F-12, P-8 |
| REC-DEC-05 | RAUC engine (verity-only, ≥ 1.15.2, 3 tries, watchdog); Rugix-compatible layout | R-1, R-3, M-6, U-4 |
| REC-DEC-06 | One release contract over per-board backends; NVIDIA A/B on Jetson | M-7, N-2, F-14 |
| REC-DEC-07 | Fresh-signal health gate; apps excluded; no auto-retry | R-1, R-2, AI-4 |
| REC-DEC-08 | §4.3 layout before the first image; spike X-2R decides the Secure Boot bootloader route | R-1, R-3, U-4, M-2 |
| REC-DEC-09 | k3s on platform nodes (≥ 4 GB + SSD), NATS leaf below; RKE2 on demand; k0s in the bake-off | N-9, F-14, M-6, N-6 |
| REC-DEC-10 | Market portability: no k3s-only features; Compose importer | A-1, A-5, F-5, N-9 |
| REC-DEC-11 | Retain storage class; restic three-key backups with SQLite online backup; verified restores | R-2, M-2, UX-6 |
| REC-DEC-12 | Kernel contract in CI; per-SKU support period capped by the board's kernel window | F-7, R-3, M-8 |
| REC-DEC-13 | Gateway-enforced approvals; robot-runtime exception profile | AI-4, AI-5, AI-7, N-7, U-4 |
| REC-DEC-14 | CRA programme: Class I treatment, route decision by 2027-Q2, security-update default decided by the founder | M-8, R-1, R-3, H-1 |
| REC-DEC-15 | Map the product onto the Olares-derived layer model in §8 (L0–L5) | P-3, A-1, AI-2 |
| REC-DEC-16 | Plan one or two in-place Debian rebases per box; T-W3-04 as a gate | R-3, F-1, M-8 |

---

## 12. Conditions, open items and limits of this decision

- **Founder decisions** (in [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)): Canonical/counsel (Q-W2-1); security updates on by default (SEC-05); RAUC vs Rugix; signing-key custody; open-core boundary vs the CRA route; per-SKU support periods; industrial certification route; RKE2/public-safety timing.
- **Ledger follow-ups for other owners:** C-W7-005 ("r35 still active") is contradicted by refuter W7-FF-1, which cites NVIDIA's JetPack 5.1.8 final-release notice; W7 should re-ledger it. The W2 steelman's Pi 5 bootc sources and the W2-P0-2 refuters' Fedora 45 Pi 5 sources are not ledgered; W2 should add them before any re-score.
- **Not covered by Tier A:** W9–W17 and W19 (see `00-EXECUTIVE-SUMMARY.md`), the licence matrix, and DC-16 (day-one plugin extension points), which is W19's. Two inputs to DC-16 already exist: the base must expose a permissioned host-network/device-grant capability (Home Assistant needs it [C-W8-026]) and a robot-runtime exception [C-W7-033].
- **Archiving:** new Wayback captures were blocked by the environment's permission policy throughout this run; load-bearing pages are pinned to commits or saved with sha256 (see each `evidence/sources/*.md`). The Launchpad bug [C-DEC-006] has no snapshot (ARCHIVE-GAP).
- **Not legal advice.** CRA, licensing and trademark readings are interpretations flagged for counsel.
