# Scorecard revision 3: every cell cited, totals and sensitivity recomputed

**Date:** 2026-11-11 · **Agent:** SCORE · **Closes:** critic pass-2 gap #9 (uncited and SECONDARY-only scorecard cells) and gap #11b (Fedora 45 Pi 5 and bootc-on-Pi 5 sources)
**Rules applied:** `scorecard-weights.md` v1.0, frozen. **No weight or anchor changed.** Cell changes are logged in that file's §8 as "cells rev-3".
**New evidence:** 32 claims in `claims/SCORE.csv` (C-SCORE-001…032), sources in `sources/SCORE.md`, saved copies and hashes in `sources/SCORE/`.
**Covers:** `01` §3 (read-only here; the decision agent updates it from this file), `03` §4–§5, `04` §6, `05` §2.1–§2.3, `06` §4 and `28` §5 (the S5 scorecard lives in §5, not §11 as the task note said; §11 holds only verification text).
**Serves requirements:** RS-1, RS-4, M-6, M-7, R-1, R-3, N-2, F-1, F-2, F-11, F-12, F-14

> ### Explain it like I'm the founder
> A scorecard is only as honest as its weakest cell. The critic found many cells with a number but no source behind it. The frozen rules say such a cell gets the **lowest** score, so we went back and either **found the source** (32 new ones, most from code at a pinned commit) or **dropped the number to the floor**.
>
> Three results matter:
> 1. **The base-OS race (S1) changed shape.** AlmaLinux publishes bootc images for the Raspberry Pi that it has tested on the Pi 5. They are labelled *experimental*, but they are real and documented. That fills the "no Pi 5" hole the RHEL-family bootc stack (candidate C) was marked down for. On raw score **C now leads with 64.0, ahead of Ubuntu (D) at 62.0 and Debian (A) at 60.0.** C and D are within 3 points, which the rules call a **tie**, so the tie-break in `01` §3.1.5 must be re-run between C and D. A raw-score lead is not a decision. If you discount the experimental Pi 5 path, the old order returns.
> 2. **Every other decision holds.** Updates (S2): Mender vs RAUC is still a tie that the tie-break gives to RAUC. Kubernetes (S3): k3s. Backups (S4): restic. Kernel (S5): K1. The "Docker/Compose would tie k3s if we dropped the one-OS rule" result (64.0) survives full citation.
> 3. **A few candidates dropped out of the ranking** because a gate they "passed" had no source: MicroK8s (small-node footprint) and borg (no cluster operator). Unproven gates count as FAIL.

---

## 1. What changed, per decision

| Decision | Before (01 rev. 2) | After (rev. 3) | Winner changed? | Sensitivity (rev. 3) |
|---|---|---|---|---|
| **S1 Base OS** | D 62.0 · A 60.0 · C 56.0 (tie D/A → tie-break A) | **C 64.0 · D 62.0 · A 60.0** · B 52.0 · E 52.0 · G 51.0 · F 46.0 | **Raw leader changes (D → C); still a tie (C/D)** | C wins 14/14 runs; C–D inside the tie band in 11/14; A is never second |
| S2 Updates | Mender 62.0 · RAUC 61.0 · Rugix 52.0 | Mender 62.0 · RAUC 61.0 · **bootc 58.0 (newly ranked)** · Rugix 52.0 | No | Mender 12, RAUC 2; tie in 14/14 (unchanged) |
| S3 Kubernetes | k3s 63 · RKE2 62 · Talos 61 · k0s 51 · MicroK8s 45 | k3s 63.0 · RKE2 62.0 · Talos 61.0 · **k0s 60.0**; MicroK8s unranked (G5) | No | k3s 11, RKE2 3 (unchanged; fragile) |
| S3, G5 relaxed | Compose 64.0 | **Compose 64.0 survives** | n/a | Compose 12, RKE2 1, k3s 1 |
| S4 Backups | restic 75 · Kopia 66 · borg 49 = Velero 49 | restic 75 · Kopia 66 · Velero 49; **borg unranked (G5)** | No | restic 14/14, margin 8.3–9.7 |
| S5 Kernel | K1 71 · K2 66 · K3 64 · K4 46 | K1 71.0 · K2 66.0 · **K3 61.0** · K4 46.0 | No | K1 14/14, margin ≥ 3.5 |

---

## 2. Method

1. **Find every cell without a claim.** A script parsed the scorecard tables in 01, 03, 04, 05, 06 and 28. For each gate and criterion cell it listed claim IDs that don't resolve, are missing, or resolve only to SECONDARY or unverified rows. The script is in §10.
2. **Reuse before researching.** Many cells had a verified claim already in the ledger (for example C-TD-talos-*, C-W5-*, C-LIC-033, C-W18-*). Those were cited as they are.
3. **Research the rest at primary sources.** Licences came from the GitHub licence API at the release commit. Lifecycle and adopter facts came from repo files at pinned SHAs (k0s, Moby, Podman, Velero, OpenZFS, Longhorn wiki, Flight Control, AlmaLinux, rpi-bootc-bootloader). Web docs (Docker, MicroK8s, Mender, NVIDIA, Canonical, Bosch) were saved as text with hashes.
4. **Score by the frozen anchors, same standard for everyone (weights §5 rule 6).** Where a source supports a *higher* anchor than the cell had, and that anchor was already granted to a peer on the same evidence, the cell was raised (k0s versus k3s). Where nothing supports the cell, it went to the floor (0 for a criterion, FAIL for a gate).
5. **Gates of candidates already out** (for example H, K, Kairos, SWUpdate's G4) are marked "not assessed (moot)" instead of being given a fabricated PASS.
6. **Recompute** with `total = Σ(weight × score)/5` and the §6 rescaling, for 14 runs per decision.

**Cells deliberately left without a claim** (all at the lowest result the rules allow): MicroK8s C4 = 0, borg C4 = 0, borg G5 FAIL, MicroK8s G5 FAIL, SUSE SL Micro G2 FAIL, K5 G3/G4 FAIL, and the "n/a" and "not assessed" gates.

---

## 3. S1 · Base OS and image family

### 3.1 Gates (from 03 §3–§4, every cell cited)

| Candidate | G1 | G2 | G3 | G4 | G5 | Ranked |
|---|---|---|---|---|---|---|
| C. RHEL-family bootc (+RHDE on Orin) | COND [C-W2-041] | COND: Pi 5 only through AlmaLinux's experimental images [C-SCORE-025, C-W2-041] | COND [C-W2-013] | PASS [C-W2-042] | COND [C-SCORE-025, C-W2-041] | yes |
| D. Ubuntu 26.04 + A/B (+JetPack) | COND [C-W2-050, C-LIC-011] | PASS [C-W2-057] | COND [C-W2-005, C-W2-006] | COND [C-W18-060, C-STEEL-ubu-007] | COND (S1-6) [C-REF-DC-technical-005, C-STEEL-ubu-006] | yes |
| A. Debian 13 + A/B (+L4T) | COND [C-W2-048, C-W2-050] | COND [C-W2-044] | COND [C-W2-001, C-W2-004] | COND [C-W8-001, C-W8-033] | COND [C-W7-007] | yes |
| B. Fedora IoT / fedora-bootc | PASS [C-W2-024] | COND [C-W2-018, C-SCORE-027] | COND [C-W2-015] | COND [C-W2-021] | COND [C-W2-016] | yes |
| E. Ubuntu Core 24/26 | PASS [C-W2-049] | COND [C-W2-009] | COND [C-W2-008] | COND [C-W18-060] | COND [C-W2-006] | yes |
| G. Yocto + RAUC | PASS [C-W2-049] | COND [C-W3-052, C-SCORE-022] | COND [C-W2-034] | COND [C-W18-005] | COND [C-W7-007] | yes |
| F. Buildroot + RAUC | PASS [C-W2-049] | COND [C-W2-047] | COND [C-W2-035] | COND [C-W18-005] | COND [C-W2-047] | yes |
| H. CIP Core / Isar | not assessed (moot) | FAIL [C-W2-032] | COND [C-W2-032] | — | — | no |
| I. Talos | PASS [C-TD-talos-035] | FAIL [C-W2-038] | — | — | — | no |
| J. Kairos | PASS [C-W2-049] | FAIL [C-W2-039] | — | — | — | no |
| K. SUSE SL Micro | not assessed (moot) | FAIL (unproven) | FAIL [C-W2-037] | — | — | no |
| L. balenaOS | PASS [C-TD-balenaos-003] | PASS [C-W2-040] | FAIL (unproven) [C-TD-balenaos-040] | — | FAIL [C-TD-balenaos-031] | no |

### 3.2 Scores (01's corrected card, A·C1 = 3; one or more claims per cell)

| Candidate | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | **Total** |
|---|---|---|---|---|---|---|---|---|
| **C. RHEL bootc** | 3 [C-W2-013] | **3** doc-only [C-W2-041, C-SCORE-025, C-SCORE-030, C-SCORE-031, C-SCORE-029] (was 1) | 3 lab [C-W2-054] | 3 [C-W2-041, C-W2-025] | 4 [C-W2-056] | 3 [C-W2-013] | 4 [C-W2-026] | **64.0** |
| D. Ubuntu 26.04 | 3 [C-W2-005] | 3 [C-W2-026] | 3 pending-lab [C-W2-058] | 3 [C-W7-039] | 3 [C-W2-043] | 2 [C-W2-006] | 5 [C-W2-028] | 62.0 |
| A. Debian 13 + RAUC | 3 [C-W3-039] | 3 [C-W2-044] | 3 lab [C-LAB-debian-rugix-022, C-LAB-rauc-015] | 3 [C-W2-043] | 3 [C-W2-045] | 3 [C-W2-001] | 3 [C-W2-026] | 60.0 |
| B. Fedora IoT | 3 [C-W2-015, C-W2-024] | **2** [C-SCORE-027 SECONDARY, C-W2-016, C-W2-028] (was 1) | 3 [C-W2-052, C-W2-054] | 1 [C-W2-019] | 4 [C-W2-056] | 4 [C-W2-024] | 2 [C-W2-028] | **52.0** |
| E. Ubuntu Core | 3 [C-W2-008] | 2 [C-W2-009] | 4 [C-W2-006] | **2** [C-SCORE-023, C-SCORE-024] (was 0) | 2 [C-W2-006] | 2 [C-W2-006] | 3 [C-SCORE-023] | **52.0** |
| G. Yocto + RAUC | 2 [C-W2-034] | 3 [C-W2-049] | 3 [C-W2-049] | 2 [C-W2-040] | 2 [C-W18-050] | 4 [C-W2-049] | 2 [C-W7-007, C-W3-052] | 51.0 |
| F. Buildroot + RAUC | 1 [C-W2-035] | 2 [C-W2-047] | 3 [C-W2-047] | 3 [C-W2-047] | 2 [C-W2-047] | 4 [C-W2-049] | 2 [C-W4-044, C-W2-047] | 46.0 |

On 03's frozen W2 card (A·C1 = 2), A scores 56.0 and the rest are the same.

**Why C·C2 = 3 and not 2.** Anchor 3 reads: "x86, Pi 5 and Jetson all have a documented path (a flavor split is allowed). NVIDIA x86 driver and container toolkit available from NVIDIA for this base. ROS 2 runs in containers. PREEMPT_RT available." Each clause now has a ledgered source:
- **Pi 5:** AlmaLinux's own GitHub organisation documents the install and says the images were tested on several Pi 5 models [C-SCORE-025].
- **Jetson:** RHDE is GA on Orin [C-W2-041].
- **NVIDIA:** `rhel10` CUDA repository [C-SCORE-030] and a toolkit `dnf` path [C-SCORE-031].
- **ROS 2:** runs in containers on every flavor (08 FF-7); RHEL 10 is Tier 2 on amd64 [C-W2-028].
- **RT:** `kernel-rt` ships in AlmaLinux 10 [C-SCORE-029].

The frozen rules let hardware we don't have be scored on documentation (§5 rule 5, `doc-only`). The "lower anchor" rule applies only when a candidate sits *between* anchors, and C meets anchor 3's whole text. **The counter-reading:** the route is labelled "experimental", firmware updates are manual, and it rests on one community effort [C-SCORE-025, C-SCORE-026]. A refuter who calls that "not a documented path" gets C2 = 2, which gives C = 60.0. 01's rev. 1 note (S1-5) asked for a *hardware* result before re-scoring; the frozen protocol does not require one, so rev. 3 applies the protocol and leaves the stricter reading as the variant.

**Why B·C2 = 2.** The Fedora ARM/IoT lead writes that Fedora 44/45 run on all Pi 5B variants, with no sound, no USB boot and CM5 still a work in progress [C-SCORE-027]. Orin is on Fedora IoT's reference list but untested [C-W2-016], and Fedora has no `kernel-rt`. That meets anchor 2 ("x86 and Pi 5 supported; Jetson only through community work; no RT kernel package"). The source is a personal blog, labelled SECONDARY, and the SECONDARY cap of 3 is respected. The community bootc-on-Pi 5 report stays UNVERIFIED (HTTP 403) [C-SCORE-028] and is not used.

**Why E·C4 = 2.** Canonical announced that Bosch Rexroth selected Ubuntu Core for ctrlX AUTOMATION [C-SCORE-023]. Bosch's page shows ctrlX OS shipping on ctrlX CORE and ctrlX DRIVE, with Canonical providing its security and support [C-SCORE-024, partial: the page does not name Ubuntu Core]. Anchor 2 ("one shipping product, confirmed from its documentation") is met. W2's "0, unverified" is superseded.

### 3.3 Sensitivity (14 runs, each weight ±5, others rescaled)

| Perturbation | 01 corrected card: winner / runner-up / margin | 03 frozen card: winner / runner-up / margin | Variant C·C2 = 2: winner / margin |
|---|---|---|---|
| C1 +5 / −5 | C / D / 1.9 · C / D / 2.1 | C / D / 1.9 · C / D / 2.1 | D 1.9 · D 2.1 |
| C2 +5 / −5 | C / D / 1.9 · C / D / 2.1 | same | D 1.9 · D 0.9 |
| C3 +5 / −5 | C / D / 1.9 · C / D / 2.1 | same | D 1.9 · D 2.1 |
| C4 +5 / −5 | C / D / 1.9 · C / D / 2.1 | same | D 1.9 · D 2.1 |
| C5 +5 / −5 | C / D / 3.0 · C / D / 1.0 | same | D 0.8 · D 2.1 |
| C6 +5 / −5 | C / D / 3.0 · C / D / 1.0 | same | D 0.8 · D 3.2 |
| C7 +5 / −5 | C / D / 0.8 · C / **A** / 3.1 | C / D / 0.8 · C / D / 3.2 | D 3.0 · **A** 0.1 |

**Reading.** On the cited card C wins all 14 runs, but its margin over D is under 3.0 in **11 of 14**, so under the frozen protocol S1 is a **C–D tie** that the decision-critical evidence must settle. A margin of exactly 3.0 (C5 +5, C6 +5) is outside the band, because a tie is "under 3.0". With the S1-4 variant (D·C1 = 2), C leads A by 3.1–4.9 in all 14 runs, which is **not** a tie.

### 3.4 What the decision agent must do with this (not decided here)

- **Re-run 01 §3.1.5 with C as a finalist.** The protocol sends ties between the top two to the tie-break, so on the cited card the finalists are **C and D**. A sits 4.0 points behind C, outside the band, and enters only under the C·C2 = 2 variant (D 62 · C 60 · A 60, all within 2). 01's existing C column already favours C on DC-05 (rebase by design) and on licensing (AlmaLinux is free). It disfavours C on DC-07 (greenboot is GRUB-only; Pi tryboot is a manual-commit community port [C-SCORE-026]), DC-19 (experimental Pi 5), Lab (one bootc spike versus four Debian spikes) and the proven appliance (none for C).
- **Swing cell:** C·C2. Founder test **W2-HW-3** (flash the AlmaLinux bootc RPi image to a Pi 5 and try a k3s-gated `bootc switch` with a forced bad image) converts it from doc-only to measured. If the test fails, C·C2 = 2 and the rev. 2 order returns.
- **Re-open condition already written in 01 §3.1.5** ("a ledgered Pi 5 bootc result passing W2-HW-3 plus a fixed greenboot #219"): the ledgered source now exists, but the hardware pass and the #219 fix do not.

---

## 4. S2 · Image, A/B update and rollback framework

| Candidate | G1 | G2 | G3 | G4 | G5 | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mender OSS | PASS [C-W3-055] | COND [C-W3-053] | PASS [C-W3-069] | PASS [C-SCORE-021] | COND [C-W3-053] | 3 [C-W3-069] | 3 [C-W3-053, C-W3-054] | 3 [C-W3-055] | 3 [C-W3-040] | 3 [C-W3-054] | 4 [C-STEEL-updates-mender-001] | 3 [C-W3-053] | **62.0** |
| **RAUC** | PASS [C-W3-017] | COND [C-W3-029, C-W3-049] | PASS [C-W3-017] | PASS [C-W3-018] | COND [C-W3-049] | 3 [C-W3-017] | 2 [C-W3-021] | 4 [C-LAB-secureboot-rauc-012…015, C-W3-018] | 3 [C-W3-029, C-W3-047] | 3 [C-W3-020] | 4 [C-W3-017] | 3 [C-W3-019] | **61.0** |
| OSTree/bootc + greenboot | PASS [C-W3-061] | **COND** (was FAIL) [C-W3-058, C-SCORE-026, C-W2-041] | PASS [C-W3-068] | PASS [C-W8-048] | — | 4 [C-W3-068, C-W2-024] | 1 [C-W3-058, C-SCORE-026] | 3 lab [C-W2-054, C-LAB-fedora-bootc-011] | 3 [C-W2-025] | 3 [C-W2-056] | 4 [C-W2-024, C-LIC-040] | 3 [C-W8-048, C-W11-051] | **58.0** |
| Rugix | PASS [C-W2-048] | COND [C-W3-071, C-W3-013] | COND [C-W3-001, C-W3-004] | PASS [C-W3-008] | COND [C-W3-013] | 2 [C-W3-001, C-W3-004] | 2 [C-W3-013] | 3 [C-W3-008] | 3 [C-W3-036] | 3 [C-LAB-debian-rugix-020] | 4 [C-W2-048] | 2 [C-W3-016] SECONDARY | 52.0 |
| SWUpdate | PASS [C-W3-056] | **FAIL** [C-W3-056] | PASS [C-W3-056] | not assessed | — | 4 [C-W3-056, C-W3-057] | **1** (was 2) [C-W3-057, C-W7-017] | 3 [C-W3-057, C-SCORE-020] | 3 [C-W3-057] | 2 [C-W3-057] | 3 [C-W3-056] | 3 [C-W3-057, C-STEEL-jb-020] | (54.0, unranked) |
| Kairos agent | PASS [C-W2-049] | **FAIL** [C-W2-039, C-REF3-DC-cost-005] | PASS [C-W3-062] | not assessed | — | — | — | — | — | — | — | — | unranked |
| NVIDIA L4T A/B | COND [C-LIC-001] | Jetson only [C-W3-049] | — | — | — | — | — | — | — | — | — | — | backend |

**Sensitivity:** unchanged from 01 rev. 2. Mender wins 12 runs and RAUC 2 (C2 −5, C3 +5), and all 14 are inside the tie band. **bootc wins none:** its best run is C1 +5, where it scores 59.4 against Mender's 61.9. The verdict still comes from the tie-break (01 §3.2). **bootc's G2 moved to COND** because the gate's own wording ("CONDITIONAL if a path exists only through a community port or a separate flavor") fits the newly ledgered Pi tryboot port and RHDE on Orin. Its C2 stays 1: a 1-star personal repo that needs a manual `sync` to commit is not "Pi 5 supported" in anchor 2's sense, so the cell sits between anchors 1 and 2 and takes the lower one.

---

## 5. S3 · App runtime and Kubernetes

Gate changes (05 §2.1): MicroK8s G5 PASS → **FAIL** (HA needs 3 nodes [C-SCORE-008]; no small-node footprint source). Docker G3, Podman G2/G3 and Tiered G2 PASS → COND (no dated upstream window [C-SCORE-010]; distro-packaged [C-W4-076]). MicroShift's G3–G5 are "not assessed" (G2 FAIL). All other gate cells were cited without a result change.

| Candidate | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|
| **k3s** | 3 [C-W4-012, C-W4-010] | 3 [C-W4-022, C-W4-020] | 1 [C-W4-009] | 4 [C-W4-041, C-W4-069…071] | 4 [C-W4-078] | 4 [C-W4-075, C-LIC-033] | 4 [C-W4-022] | **63.0** |
| RKE2 | 3 [C-W4-012] | 4 [C-W4-038, C-W4-037, C-W4-022] | 1 [C-W4-009] | 3 [C-W4-072] | 3 [C-W4-072] | 4 [C-LIC-033] | 4 [C-W4-038] | 62.0 |
| Talos-native | 3 [C-TD-talos-012, -003, -037] | 3 [C-W4-037, C-W4-038, C-W4-064] | 2 [C-TD-talos-012, -027] | 3 [C-TD-talos-040] | 3 [C-TD-talos-028, -009] | 4 [C-TD-talos-035, -037] | 4 [C-W4-037] | 61.0 |
| k0s | **3** [C-SCORE-002, C-SCORE-005] (was 2) | 3 [C-W4-022, C-W4-038] | 1 [C-SCORE-003] | **3** [C-SCORE-004] (was 2) | 4 [C-W4-045] | 4 [C-SCORE-001] | **4** [C-W4-022, C-W4-037, C-W4-038] (was 3) | **60.0** (was 51.0) |
| *MicroK8s (G5 FAIL)* | **3** [C-SCORE-007] (was 2) | 2 [C-W4-073] | 1 [C-SCORE-007] | **0** floor (was 2) | 3 [C-SCORE-007] | 4 [C-SCORE-006] | 3 [C-W4-022] | *43.0* |
| *Docker/Compose (G5 relaxed)* | 3 [C-SCORE-010, C-SCORE-011] | 3 [C-SCORE-011, C-W4-026, C-W7-040] | 1 [C-SCORE-011, C-TD-project-nomad-016] | 5 [C-W4-043, C-W4-044] | 4 [C-W12-011, C-W4-043] | 4 [C-SCORE-009] | 3 [C-W7-040, C-TD-tier-c-selfhost-085] | *64.0* |
| *Tiered mix (G5 relaxed)* | **2** [C-W4-076, C-W4-012] (was 3) | 3 [C-W4-022, C-W4-026] | 1 [C-W4-009] | 3 [C-TD-olares-021, C-SCORE-014] | 2 [C-W4-051, C-W4-001] | 4 [C-LIC-033, C-SCORE-012] | 4 [C-W4-022] | *52.0* (was 56.0) |
| *Podman + Quadlet (G5 relaxed)* | **2** [C-W4-076, C-SCORE-012] (was 3) | 3 [C-W4-026, C-W4-076] | 1 [C-SCORE-013] | 2 [C-SCORE-014] | 4 [C-W4-051, C-W4-076] | 4 [C-SCORE-012] | 2 [C-W4-026] | *49.0* (was 53.0) |

**Why k0s rose.** Same evidence, same score (weights §5 rule 6). k3s has C1 = 3 for "documented in-place minor upgrades" on a ~14–18-month minor cycle. k0s documents the same ~14-month cycle, in-place Autopilot upgrades and paid patches beyond [C-SCORE-002, C-SCORE-005]. k0s's ADOPTERS file names at least two shipping products [C-SCORE-004], the same kind of evidence that gave Talos C4 = 3 [C-TD-talos-040]. NVIDIA partner-validates k0s, as it does RKE2 [C-W4-022]. k0s still sits at or below k3s on every criterion, so it never wins a run.

**Sensitivity:** identical to 05 §2.3. k3s wins 11 runs and RKE2 3 (C2 +5, C4 −5, C5 −5); all 14 are in the tie band; the result is fragile but defensible, because k3s and RKE2 are one family. **Compose with G5 relaxed:** 64.0 survives, winning 12 of 14 (RKE2 wins C4 −5 and k3s wins C7 +5), all within the tie band. G5 (F-14) is still the only gate keeping Compose out.

---

## 6. S4 · Backup and restore

| Candidate | G1–G5 | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|---|
| **restic** | PASS ×4, G4 n/a [C-W5-023, C-W5-009, C-W5-033] | 3 [C-W5-023, C-W5-025] | 4 lab [C-W5-009] | 4 [C-W5-023, C-W5-024] | 3 [C-W5-050, C-W5-033, C-W5-034] | 4 [C-W5-009] | 5 [C-W5-058, C-LIC-036] | 4 [C-W5-033, C-W5-034, C-W5-024] | **75** |
| Kopia | PASS ×4, G4 n/a [C-W5-027, C-W5-046, C-W5-022] | 3 [C-STEEL-backup-kopia-014, -015] (citation fixed) | 3 doc-only [C-W5-046] | 3 [C-W5-028] | 3 [C-W5-041] | 4 [C-W5-041] | 5 [C-W5-058, C-SCORE-032] | 3 [C-W5-022] | 66 |
| Velero (+Kopia) | PASS [C-SCORE-015, C-SCORE-016]; G5 COND [C-W5-020] | 3 [C-SCORE-016] | 2 [C-W5-020] | 1 [C-W5-021] | 2 [C-W5-056] | 2 [C-W5-020] | 5 [C-W5-058, C-SCORE-015] | 3 [C-W5-057] | 49 |
| *borg* | G5 **FAIL** (unproven; was COND) | 2 [C-W5-030] | 3 [C-W5-030] | 3 [C-W5-030] | 0 floor | 3 [C-W5-030] | 5 [C-W5-030] | 2 [C-SCORE-019] | *49, unranked* |
| *ZFS send/recv* | G1 COND (CDDL) [C-W5-058] | 3 [C-SCORE-018] | 2 [C-TD-umbrelos-004] | 3 [C-W5-032] | 1 [C-TD-umbrelos-042] | 2 [C-TD-umbrelos-058] | 2 [C-W5-058] | 3 [C-TD-truenas-scale-006, C-TD-proxmox-ve-011] | *46, unranked* |
| *Longhorn backup* | G5 FAIL [C-W4-046] | 3 [C-SCORE-017] | 1 [C-W4-046] | 2 [C-W5-031] | 1 [C-TD-talos-021] | 2 [C-W4-046] | 5 [C-LIC-033] | **2** [C-TD-talos-021] (was 3) | *43, unranked* |

C1 for S4 uses 06's pre-declared reading ("release/format stability, maintainers and licence-forkability"). That is why Velero (current + n-1, best effort [C-SCORE-016]) and Longhorn (6 months per minor [C-SCORE-017]) keep 3. **Sensitivity:** restic wins all 14 runs by 8.3–9.7. Robust, unchanged.

---

## 7. S5 · Kernel route

| Route | Gates | C1 | C2 | C3 | C4 | C5 | C6 | C7 | Total |
|---|---|---|---|---|---|---|---|---|---|
| **K1** board maintainer's kernel | PASS/COND [C-W18-069, C-W18-013, C-W18-019, C-W18-006, C-W18-029] | 3 [C-W18-007] | 4 [C-W18-019, C-W18-027, C-W18-006] | 3 [C-W18-012] | 4 [C-W18-012, C-W18-013, C-W18-009] | 4 [C-W18-015, C-W18-046, C-W18-066] | 3 [C-LIC-017, C-W18-069] | 4 [C-W18-027, C-STEEL-jb-015] | **71.0** |
| K2 OneMind-configured LTS | PASS/COND [C-LIC-017, C-W18-009, C-W18-002, C-W18-005, C-W18-029] | 3 [C-W18-001, C-W18-002] | 3 [C-W18-020] | 3 [C-W18-010] | 5 [C-W18-008, C-W18-010] | 3 [C-W18-066] | 3 [C-LIC-017] | 3 [C-W18-008] | 66.0 |
| K3 CIP SLTS | PASS/COND [C-LIC-017, C-W2-032, C-W18-003, C-W18-005, C-W18-029] | 4 [C-W18-003] | 3 [C-W18-009, C-W18-019] | 3 [C-REF-W8-security-004] | **2** [C-W8-038] (was 3) | 3 [C-W18-066] | 3 [C-LIC-017] | 3 [C-W8-038, C-REF-W8-longevity-006] | **61.0** (was 64.0) |
| K4 patched kernel | COND [C-LIC-017, C-W18-009, C-W18-002, C-W18-005, C-W18-029] | 2 [C-W18-002] | 3 [C-W18-020] | 2 [C-W18-011] | 2 [C-W18-011] (re-cited) | 2 [C-W18-010] | 3 [C-LIC-017] | 2 [C-W18-011] | 46.0 |
| K5 microkernel | FAIL [C-W18-027, C-W18-029]; G3/G4 FAIL (unproven) | | | | | | | | not ranked |

**K3·C4 3 → 2:** anchor 3 needs "two or more shipping products confirmed from code" or one constraint-matched product. The ledger confirms one: Siemens IOT2050 on isar-cip-core [C-W8-038], an industrial product that is not an appliance match. **K4·C4 re-cited:** its old citation (C-W18-044, SteamOS) is about RAUC A/B, not kernel patches. HAOS carrying 3 kernel patches [C-W18-011] supports the same score. **Sensitivity:** K1 wins all 14 runs. The narrowest is C4 +5 at 3.5 over K2. In the C4 −5 run the runner-up is now K2 (6.5) instead of K3.

---

## 8. Change list (every score or gate result that moved)

| # | Decision | Cell | Before → after | Reason | Claims |
|---|---|---|---|---|---|
| R3-01 | S1 | C·C2 | 1 → **3** | Pi 5 documented path now ledgered; every clause of anchor 3 cited (doc-only) | C-SCORE-025, -029, -030, -031, C-W2-041 |
| R3-02 | S1 | B·C2 | 1 → 2 | Fedora 45 runs on Pi 5B (SECONDARY; cap respected) | C-SCORE-027 |
| R3-03 | S1 | E·C4 | 0 → 2 | ctrlX OS: one shipping product, from vendor documentation | C-SCORE-023, -024 |
| R3-04 | S1 | C·G2, C·G5 | COND kept, now cited | AlmaLinux Pi 5 path is experimental, so CONDITIONAL, not PASS | C-SCORE-025 |
| R3-05 | S1 | H·G1, K·G1 | PASS → not assessed | No source; moot after another gate's FAIL | — |
| R3-06 | S2 | bootc·G2 | FAIL → **COND** | Community Pi tryboot port plus RHDE on Orin fit the gate's CONDITIONAL wording; bootc is now ranked (58.0) | C-SCORE-026, C-W2-041 |
| R3-07 | S2 | SWUpdate·C2 | 2 → 1 | Anchor 2 requires Pi 5; not shown | C-W3-057, C-W7-017 |
| R3-08 | S2 | SWUpdate·G4, Kairos·G4 | PASS → not assessed | Moot after G2 FAIL | — |
| R3-09 | S3 | k0s·C1 | 2 → 3 | Same lifecycle and in-place upgrade evidence as k3s | C-SCORE-002, -005 |
| R3-10 | S3 | k0s·C4 | 2 → 3 | ADOPTERS names ≥2 shipping products (same evidence class as Talos) | C-SCORE-004 |
| R3-11 | S3 | k0s·C7 | 3 → 4 | NVIDIA partner-validated, AICR- and AI-conformance-listed (as RKE2) | C-W4-022, -037, -038 |
| R3-12 | S3 | MicroK8s·C1 | 2 → 3 | Documented in-place channel refresh (the k3s standard) | C-SCORE-007 |
| R3-13 | S3 | MicroK8s·C4 | 2 → 0 | No shipping product found (floor) | — |
| R3-14 | S3 | MicroK8s·G5 | PASS → **FAIL** | Small-node footprint unproven; HA needs 3 nodes | C-SCORE-008 |
| R3-15 | S3 | Podman·C1, Tiered·C1 | 3 → 2 | No upstream support window; tied to the distro package | C-W4-076, C-SCORE-012 |
| R3-16 | S3 | Docker·G3; Podman·G2, G3; Tiered·G2 | PASS → COND | No dated window [C-SCORE-010]; distro-packaged; no Jetson recipe opened | C-SCORE-010, C-W4-076 |
| R3-17 | S3 | MicroShift·G3–G5 | COND/FAIL → not assessed | Moot after G2 FAIL | — |
| R3-18 | S4 | borg·G5 | COND → **FAIL** | "No operator found" is unproven, and an unproven gate counts as FAIL | — |
| R3-19 | S4 | Longhorn·C7 | 3 → 2 | No vendor-ecosystem claim; community use only | C-TD-talos-021 |
| R3-20 | S4 | Kopia·C1 | citation fixed | C-W5-030 is the borg claim | C-STEEL-backup-kopia-014, -015 |
| R3-21 | S4 | all G4 | PASS → n/a | A backup engine controls no G4 sub-check | — |
| R3-22 | S5 | K3·C4 | 3 → 2 | One industrial product confirmed, not two | C-W8-038 |
| R3-23 | S5 | K4·C4 | citation replaced | C-W18-044 does not support kernel patches | C-W18-011 |

Every other uncited cell in 03, 04, 05, 06 and 28 gained a citation with no change of score. 01 is not edited here; its rows G, B, F, E (§3.1.2), S3 (§3.3), S4 (§3.4) and S5 (§3.5) should take their citations and numbers from §3–§7 above.

---

## 9. Gap #11b: Fedora 45 Pi 5 and bootc-on-Pi 5 sources, ledgered

| Source (from W2-steelman / W2-P0-2-technical) | Claim | Status | Effect |
|---|---|---|---|
| AlmaLinux/bootc-images-rpi README (S-01) | C-SCORE-025 | verified, PRIMARY | **S1 C·C2 1 → 3** |
| kfox1111/rpi-bootc-bootloader README (S-03) | C-SCORE-026 | verified, PRIMARY | **S2 bootc·G2 FAIL → COND** (C2 stays 1) |
| nullr0ute, "Raspberry Pi 5 on Fedora" (2026-10-27) | C-SCORE-027 | verified, SECONDARY | **S1 B·C2 1 → 2** |
| fedora.yaasharc.me bootc RPi5 report | C-SCORE-028 | **UNVERIFIED** (HTTP 403 again) | none |
| NVIDIA CUDA repos (S-05) | C-SCORE-030 | verified, PRIMARY | supports C·C2 |
| AlmaLinux 10 RT repo (lineage RT, cf. S-06) | C-SCORE-029 | verified, PRIMARY | supports C·C2 |

**So the answer to 01 S1-5 is yes: re-score.** The steelman's 60–64 estimate lands at its top end (64.0) on the literal anchor reading and at 60.0 on the strict one.

---

## 10. Reproducing the numbers

```python
W=[20,20,15,15,10,10,10]
def tot(s,w=W): return sum(a*b for a,b in zip(s,w))/5
def run(c):
    for i in range(7):
        for d in (5,-5):
            w=[x*(100-(W[i]+d))/(100-W[i]) for x in W]; w[i]=W[i]+d
            r=sorted(((tot(v,w),k) for k,v in c.items()),reverse=True)
            print(f"C{i+1}{d:+d}", r[0][1], r[1][1], round(r[0][0]-r[1][0],1))
run({'C':[3,3,3,3,4,3,4],'D':[3,3,3,3,3,2,5],'A':[3,3,3,3,3,3,3]})                       # S1, 01 corrected
run({'C':[3,3,3,3,4,3,4],'D':[3,3,3,3,3,2,5],'A':[2,3,3,3,3,3,3]})                       # S1, 03 frozen card
run({'C':[3,2,3,3,4,3,4],'D':[3,3,3,3,3,2,5],'A':[3,3,3,3,3,3,3]})                       # S1 variant C-C2 = 2
run({'Mender':[3,3,3,3,3,4,3],'RAUC':[3,2,4,3,3,4,3],'bootc':[4,1,3,3,3,4,3],'Rugix':[2,2,3,3,3,4,2]})   # S2
run({'k3s':[3,3,1,4,4,4,4],'RKE2':[3,4,1,3,3,4,4],'Talos':[3,3,2,3,3,4,4],'k0s':[3,3,1,3,4,4,4]})       # S3
run({'k3s':[3,3,1,4,4,4,4],'RKE2':[3,4,1,3,3,4,4],'Docker':[3,3,1,5,4,4,3]})                           # S3, G5 relaxed
run({'restic':[3,4,4,3,4,5,4],'Kopia':[3,3,3,3,4,5,3],'Velero':[3,2,1,2,2,5,3]})                       # S4
run({'K1':[3,4,3,4,4,3,4],'K2':[3,3,3,5,3,3,3],'K3':[4,3,3,2,3,3,3],'K4':[2,3,2,2,2,3,2]})             # S5
```

A margin printed as 3.0 is 2.99999… in floating point. It is treated as exactly 3.0, which is outside the tie band ("under 3.0").

The cell checker that found the gaps is a short script that parses each table, expands `[C-…]` groups (including `-002` shorthands and `012…015` ranges), and looks up each ID's `status` and `source_type` across `claims/*.csv`. It flags cells with no ID, unresolved IDs, or only SECONDARY or unverified support.

---

## 11. What competitors do (constraint fit)

| Product | What it chose (scorecard-relevant) | Team | Kubernetes? | Robotics / industrial? | Constraint fit with OneMind | Claims |
|---|---|---|---|---|---|---|
| Home Assistant OS | Buildroot + RAUC, Docker apps, own kernel config | Funded (Nabu Casa) | No | No | Partial: appliance UX matches; no k8s, no Jetson | C-W2-047, C-W4-044, C-W18-008 |
| umbrelOS 2.0 | Debian 13 + Rugix (earlier Mender), Compose, Kopia | Small company | No | No | High for the appliance, Pi 5 and x86 tiers | C-W2-043, C-W4-043, C-W3-040, C-W5-041 |
| Olares | k3s on Ubuntu/Debian, restic | Funded | Yes | No | Partial: k3s matches; no OS A/B | C-TD-olares-021, C-W5-050 |
| Bosch ctrlX OS | Ubuntu Core + snaps, Canonical-serviced | Large industrial | No | Industrial automation | Partial: IIoT match; team size and licensing differ | C-SCORE-023, C-SCORE-024 |
| Red Hat Device Edge + Flight Control | bootc/ostree + greenboot; Podman/Quadlet or MicroShift workloads | Vendor | Optional (MicroShift) | Edge, Orin | Partial: lineage of candidate C; paid; no Pi 5 | C-W2-041, C-SCORE-014, C-W8-048 |
| TrueNAS SCALE | Moved its app catalog from k3s to Docker Compose (24.10) | Funded | Was, now no | No | Cautionary for S3 | C-DEC-007 |
| Talos adopters | Talos Linux, API-only | Vendor | Yes | Two edge-device users | Low: no Pi 5/Orin in the official list | C-TD-talos-040, C-TD-talos-004 |
| k0s adopters | k0s (AudioCodes, Defense Unicorns, exalsius) | Vendor (Mirantis) | Yes | Defense, GPU | Partial: same class as k3s, smaller appliance footprint evidence | C-SCORE-004 |

**Lesson for the scorecard:** the closest appliance matches (umbrelOS, HAOS) still run Debian/Buildroot with Docker. The new S1 leader (C) has a vendor-proven lineage (RHDE, Flight Control) but **no constraint-matched appliance on a Pi 5**. That is exactly the tie-break row 01 calls "Proven competitor".

---

## 12. Recommendations with requirement IDs

| ID | Recommendation | Requirement IDs |
|---|---|---|
| REC-SCORE-01 | The decision agent re-runs the S1 tie-break (01 §3.1.5) with **C and D** as the finalists on the cited card, and shows A's position under the C·C2 = 2 variant. Raw score must not decide. | RS-1, RS-4, F-12, F-14, N-2, M-7 |
| REC-SCORE-02 | Schedule founder test **W2-HW-3** (AlmaLinux bootc RPi image on Pi 5, k3s-gated `bootc switch` to a broken image, automatic return with no console) early in the 180-day plan. It decides C·C2 = 3 or 2, and with it the S1 finalists. | F-12, F-14, N-2, H-3 |
| REC-SCORE-03 | Take 01's S1 G/B/F/E rows and its S3, S4 and S5 cards from this file, so every cell in 01 cites a claim (§9 "every claim used in 01 resolves to a primary-source row"). | RS-1, M-6 |
| REC-SCORE-04 | S2, S3, S4 and S5 verdicts stand (RAUC by tie-break, k3s, restic, K1); MicroK8s and borg leave the ranked sets. | R-1, R-3, F-14, M-4 |
| REC-SCORE-05 | Keep the cell checker (§10) as a pre-merge check on every scorecard edit, so the rev. 3 citations cannot silently drift back. | RS-1, M-6 |

---

## 13. Open items and limits

- **Inconsistency for the decision agent:** 01 §3.3 says Talos is "excluded by G2 (no merged Orin support)", while 05 §2.1 scores its G2 as CONDITIONAL and ranks it 61.0. Rev. 3 kept 05's gate (Pi 5 overlay plus an open Orin PR is a "separate flavor"), but one of the two files must change.
- **04's table still shows the frozen W3 totals.** The current S2 totals (rev. 1–3) are in 01 §3.2 and §4 above; a note under 04's table says so.
- **Not re-opened:** W2 steelman S-02 (AlmaLinux Pi kernel repo), S-04 (Red Hat KB on JetPack for RHEL) and S-06 (CentOS Stream RT compose). C-W2-041 and C-SCORE-029 cover the same points.
- **E·C4 rests on two vendor documents**, one of them `partial` (Bosch's page does not itself say "Ubuntu Core"). The cell is at anchor 2, not higher.
- **Docker C1 = 3** uses the "documented in-place path that keeps the device current" branch of anchor 3, as k3s does. Moby publishes no dated window, and only the latest major is maintained [C-SCORE-010]. A stricter reader gives 2, which makes Compose (G5 relaxed) 60.0 and no longer ahead of k3s.
- No lab ran in this pass. Every rev. 3 change is documentation evidence.

---

## Glossary

- **Anchor:** the written meaning of a score (0–5) for a criterion, frozen before scoring.
- **Floor:** the lowest result the rules allow when a cell has no evidence: 0 for a criterion, FAIL for a gate.
- **doc-only:** scored from documentation because we don't have the hardware (weights §5 rule 5).
- **Tie band:** two totals less than 3.0 apart. The rules then decide by decision-critical evidence, not by the higher number.
- **Gate relaxed:** re-scoring a candidate as if one failed gate had passed, to show what that gate costs.
- **SECONDARY cap:** a cell backed only by SECONDARY sources can't score above 3.
- **Rev. 1 / 2 / 3:** successive scorecard corrections. Rev. 1 and 2 came from refuters and steelmen (logged in 01 §3); rev. 3 is this citation pass.
- **bootc:** a way to ship a whole OS as a container image and update it atomically. **RHDE** is Red Hat Device Edge; **greenboot** is its health-check-and-rollback tool.
- **tryboot:** the Raspberry Pi firmware's "boot this other image once" feature, which A/B update tools use for safe rollback.
