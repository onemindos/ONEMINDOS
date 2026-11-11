# Scorecard weights and anchors (FROZEN)

**Status:** FROZEN v1.0 · **Frozen on:** 2026-11-10 · **Frozen before:** any candidate was scored
**Applies to:** every P0 foundation decision scored in `01-FOUNDATION-DECISION.md` and in `03`–`07`, `28`
**Protocol source:** RESEARCH-MISSION.md §6, "Scorecard protocol"
**Serves requirements:** RS-1, RS-4, M-6, M-7, R-1, R-3, H-1, N-2, F-1, F-2, F-11, F-12, F-14

> ### Explain it like I'm the founder
> Before we compare Debian, Fedora IoT, Ubuntu, Yocto and the rest, we write down the rules of the contest and lock them. That stops anyone, including us, from quietly changing the rules after seeing which option is ahead.
> 1. **Gates come first.** A candidate that fails a gate is out, however good it looks elsewhere. Example: if an option can't legally ship inside an Apache-2.0 open-core product, the rest doesn't matter.
> 2. **The survivors get 0–5 points on seven criteria.** Each criterion has a weight (how much it matters), and each score has a written meaning, so a "4" means the same thing to every agent.
> 3. **Every score needs a source.** No source, no points: an unproven cell gets 0.
> 4. **Then we shake the weights** (each one ±5) to check that the winner doesn't depend on one judgement call.

---

## 1. What gets scored

The scorecard is used for these P0 decisions. Each candidate is a **complete stack** for that decision, not a single product. For example, "Debian 13 + Rugix A/B", not just "Debian".

| Decision | ADR-001 section | Candidates that must be scored (others may be added and logged in §8) |
|---|---|---|
| **S1. Base OS and image family** | D1, D2 | Debian 13 + Rugix (ADR-001 proposal) · Fedora IoT / Fedora bootc (F-12) · CentOS Stream 10 → RHEL 10 image mode (bootc) · Ubuntu 24.04/26.04 LTS (+ Ubuntu Pro) · Ubuntu Core 24/26 · Buildroot + RAUC (the HAOS pattern) · Yocto/OE + RAUC or Mender · CIP Core / Debian via Isar · Talos Linux · Kairos · SUSE SL Micro · balenaOS |
| **S2. Image build, A/B update and rollback framework** | D3 | Rugix · RAUC · Mender (OSS) · SWUpdate · OSTree/rpm-ostree + greenboot · bootc · Kairos agent · NVIDIA L4T A/B (Jetson only) |
| **S3. App runtime and Kubernetes** | D4 | k3s · RKE2 · k0s · MicroK8s · Talos-native Kubernetes · MicroShift · Docker/Compose · Podman + Quadlet · tiered mix (k3s on some tiers, Compose/Quadlet on others) |
| **S4. Backup and restore** | D5 | restic · Kopia · borg · Velero (+ Kopia uploader) · Longhorn backup · ZFS send/recv · k3s datastore snapshots (SQLite and etcd) |
| **S5. Kernel route** (W18) | D2, D6 | (a) stock distro kernel · (b) upstream LTS with a OneMind config · (c) vendor BSP kernels · (d) patched OneMind kernel (PREEMPT_RT, security) · CIP SLTS kernel |

A Jetson-only or Pi-only flavor is scored as part of the stack that carries it. Example: "Debian 13 core + NVIDIA L4T Ubuntu flavor" is one S1 candidate, and the cost of running two flavors counts against it under C5.

---

## 2. Must-pass gates

Each candidate gets one result per gate.

- **PASS:** the gate is met, with a cited claim ID.
- **CONDITIONAL:** met only with a named mitigation that has a stated cost and owner. Example: "Pi 5 needs Raspberry Pi's kernel repo, which Umbrel already does". A CONDITIONAL result carries its mitigation into the plan (`20-PLAN-180-DAYS.md`) and the risk register (`23-RISK-REGISTER.md`).
- **FAIL:** not met, or not shown to be met. **An unproven gate counts as FAIL** for ranking purposes, and the gap is listed in `24-QUESTION-BANK-ANSWERS.md`.

A candidate with any FAIL is **not ranked**. It still gets a row in the scorecard, showing which gate it failed and why, so the founder can see it was evaluated fairly. Fedora IoT/bootc must be taken through every gate with evidence, never dismissed in one line (F-12).

| Gate | Test | How it is checked | Requirement IDs |
|---|---|---|---|
| **G1. License** | Compatible with Apache-2.0 open core (D-001), including transitive parts: firmware blobs, the NVIDIA Jetson Linux/JetPack EULA, CUDA redistributables, Raspberry Pi firmware, GPL source-offer duties and GPLv3 "Installation Information". | Rows in `evidence/license-matrix.csv` with SPDX IDs taken from a pinned LICENSE file. **FAIL** if a required part can't legally be redistributed on sold hardware or forces the OneMind core off Apache-2.0. **CONDITIONAL** if redistribution needs a separate EULA acceptance or download step. | D-001, R-3, H-1 |
| **G2. Hardware coverage** | Runs on x86_64 UEFI **and** Raspberry Pi 5/CM5 **and** Jetson Orin, either in one image family or through an **explicit flavor split** that is named and costed. | Vendor support matrices, plus a lab or founder-hardware result. **FAIL** if any of the three has no workable path. **CONDITIONAL** if a path exists only through a community port or a separate flavor. | N-1, N-2, H-3, M-7, F-2 |
| **G3. Support to 2036** | A credible security-update path to **2036-12-31** for the base (free or paid), at a **stated cost per device** for 1k and 10k units, covering the support period OneMind must declare under the EU CRA. | Lifecycle pages and pricing (claims ledger, 12-month re-check), plus the planned rebase path (for example Debian 13 → 14 → 15). **FAIL** if no path is documented or the cost is unknown and can't be bounded. **CONDITIONAL** if it depends on unpublished pricing (for example Ubuntu Pro for Devices) with a bounded estimate. | R-3, H-1, M-8, F-1 |
| **G4. IoT/IIoT, no blocking limitation** | Nothing in the stack blocks the F-11 sub-checks: (a) industrial protocols (OPC UA, MQTT 5 + Sparkplug B, Modbus, BACnet, CAN) can run as apps; (b) real time: PREEMPT_RT or an isolated-core path for soft real time, with hard real time delegated to a PLC, RTOS or MCU; (c) a path to IEC 62443-4-1/4-2; (d) zero-touch onboarding (FDO, IDevID or an equivalent); (e) fleet scale to about 10k devices. | `09-iot-mesh-offgrid-tak.md`, W8 claims. Each sub-check is PASS, CONDITIONAL or FAIL; **the gate fails if any sub-check fails.** | F-11, AI-7, N-4, N-6, F-13 |
| **G5. One OS from Pi to enterprise** | The same image family and the same app platform run a 4–8 GB Pi 5 greenhouse node **and** a multi-node GPU cluster running Isaac Sim, with no product switch and a simple UX at both ends. | Measured footprint on the smallest node (`evidence/lab/`), plus a documented scale-out path. **FAIL** if the small or the large end needs a different product, app format or management plane. **CONDITIONAL** if the large end needs only an additional flavor of the same family. | F-14, M-4, N-2, P-5, H-3 |

**Gate for S3, S4 and S5 only:** for decisions that don't choose a whole base, check G2–G5 against the parts that decision controls. For example, a backup tool must run on arm64 and x86_64 for G2, and its license must pass G1.

---

## 3. Weighted criteria (total 100)

| ID | Criterion | Weight | Requirement IDs |
|---|---|---|---|
| **C1** | Longevity and support | **20** | R-3, H-1, M-8, F-1 |
| **C2** | Hardware and robotics fit | **20** | M-7, N-2, N-7, N-8, F-2, F-3, F-11 |
| **C3** | Security and update safety | **15** | R-1, M-2, U-4, AI-4 |
| **C4** | Proven in production | **15** | RS-2, RS-1 (founder rule: "use the proven competitors") |
| **C5** | Solo-developer operability | **10** | M-6, F-8, F-9 |
| **C6** | Cost and licensing | **10** | D-001, H-1, H-4 |
| **C7** | Ecosystem | **10** | A-1, A-5, A-6, F-4, F-5 |

**Score formula:** `total = Σ (weight × score) / 5`, which gives 0–100. A difference of **under 3.0 points** between the top two is a **tie**. A tie is settled by the decision-critical evidence (`evidence/decision-critical.md`) and the refuter tables, never by adjusting scores.

---

## 4. Anchors (0–5) per criterion

Use the anchor whose whole description is met. If a candidate sits between two anchors, give it the **lower** one. Half points are not allowed.

### C1 · Longevity and support (20)
*Interpretation for S2–S5: the project's own release and support policy, its maintainer base and its funding.*

| Score | Anchor |
|---|---|
| 0 | No published lifecycle, or the project is archived, abandoned or unverified. |
| 1 | Free support ends before 2029 and there is no paid extension, or the support model is undocumented. |
| 2 | Free support reaches 2029–2030. A paid or volunteer extension exists but needs a rebase without a documented path, or its cost is unbounded. |
| 3 | Support to 2032+ through a documented free and/or paid path at a bounded cost, **or** a documented in-place rebase path that keeps the device current (one or more rebases expected by 2036). |
| 4 | Support to 2035+ with a published price, **and** a documented in-place major-version rebase without reflashing; at least 2 independent organizations maintain it. |
| 5 | Everything in 4, plus a 10-year-plus formal commitment (for example CIP SLTS, an RHEL-style policy or Ubuntu Core) **that covers OneMind's target boards**, a rebase demonstrated in our lab or by a cited production adopter, and a multi-vendor or foundation governance model. |

### C2 · Hardware and robotics fit (20)
*Covers x86, Pi 5/CM5, Jetson Orin/Thor, RK3588, NVIDIA x86 GPUs, ROS 2 tier status and real time.*

| Score | Anchor |
|---|---|
| 0 | Fails or can't show support for at least two of x86, Pi 5 and Jetson. |
| 1 | One target board family only, or Jetson only through unsupported hacks. |
| 2 | x86 and Pi 5 supported. Jetson and NVIDIA GPUs only through community work. ROS 2 at Tier 3 or unsupported. No RT kernel package. |
| 3 | x86, Pi 5 and Jetson all have a documented path (a flavor split is allowed). NVIDIA x86 driver and container toolkit available from NVIDIA for this base. ROS 2 runs in containers. PREEMPT_RT available. |
| 4 | Everything in 3, plus vendor-validated NVIDIA support (GPU Operator or an equivalent listed in the official matrix) or official Jetson support; ROS 2 Tier 1 or 2 for the host, or a demonstrated containerized ROS 2 stack with no gaps for DDS/Zenoh, devices and real time; one update framework across all three board families. |
| 5 | Everything in 4, plus RK3588 or another non-NVIDIA accelerator path, measured soft-real-time latency on at least 2 boards, and same-day support for new NVIDIA releases shown by history (for example JetPack and CUDA releases picked up within 30 days). |

### C3 · Security and update safety (15)
| Score | Anchor |
|---|---|
| 0 | In-place package updates with no rollback, or unsigned updates. |
| 1 | Signed packages but no atomic update. Rollback is manual. |
| 2 | Atomic A/B or image updates with signatures, but no automatic rollback, or rollback only on boot failure. |
| 3 | Atomic signed updates with automatic rollback, a health-check hook that can gate on application-level checks (k3s and core pods), power-loss safety shown in documentation, and a read-only or verified root. |
| 4 | Everything in 3, plus a documented Secure Boot / measured boot / TPM path that does **not** need a partition or bootloader change later, key rotation and revocation, and offline signed update bundles. |
| 5 | Everything in 4, plus a power-cut and forced-rollback result in **our** lab (`evidence/lab/`), a dm-verity or fs-verity root, and an SBOM plus signing chain that meets SLSA level 2 or higher. **Documentation alone caps this criterion at 4.** |

### C4 · Proven in production (15)
*Uses W1 teardown evidence: code citations, not marketing.*

| Score | Anchor |
|---|---|
| 0 | No production users found. |
| 1 | Hobby or lab use only, or one small adopter. |
| 2 | One shipping product, confirmed from its code or its documentation. |
| 3 | Two or more shipping products, confirmed from code, **or** one product whose constraints match OneMind's (an appliance, a solo or small team, consumer hardware). |
| 4 | Three or more shipping products, including at least one appliance and one robotics or industrial product, with failure reports reviewed (≥3 issues read). |
| 5 | Everything in 4, plus a constraint-matched competitor (HAOS, umbrelOS, Olares, or a robotics fleet vendor) running it at scale for 2+ years, confirmed by code at a pinned SHA. |

### C5 · Solo-developer operability (10)
| Score | Anchor |
|---|---|
| 0 | Needs a dedicated team (for example BSP maintenance per board, or a custom distro). |
| 1 | Long build times (over 4 h per board), heavy custom layers, no Mac/CI path. |
| 2 | Workable, but needs specialist knowledge (for example Yocto layers, a custom bootloader) and monthly manual security rebuilds. |
| 3 | Builds in CI from a Mac via a Linux VM or remote runners in under 1 h per image; security updates come from the upstream distro; manageable documentation. |
| 4 | Everything in 3, plus declarative, container-like image definitions (for example a Containerfile, a Bakery recipe or an mkosi config), one toolchain for all flavors, and good upstream docs and community answers. |
| 5 | Everything in 4, plus measured in our lab: image rebuild under 30 minutes, under 2 h per month of maintenance in a dry run, and AI agents can drive the whole pipeline from the CLI. |

### C6 · Cost and licensing (10)
| Score | Anchor |
|---|---|
| 0 | Fails G1, or the per-device cost is unknown and unbounded. |
| 1 | Over $50 per device per year at 1k units, or a restrictive license term (for example noncommercial or source-available for a core part). |
| 2 | $10–50 per device per year, or a copyleft obligation that needs legal process (GPLv3 Installation Information on locked boxes). |
| 3 | Under $10 per device per year, or free with paid support optional; standard copyleft duties only (GPLv2 source offer). |
| 4 | Free for all units, permissive or weak-copyleft licenses, and clear redistribution rights for firmware. |
| 5 | Everything in 4, plus no proprietary blob that needs a EULA step on OneMind's default boards, and all licenses Apache-2.0-compatible with SPDX IDs verified from pinned files. |

### C7 · Ecosystem (10)
| Score | Anchor |
|---|---|
| 0 | No community, no third-party packages. |
| 1 | A small community with few packages or integrations. |
| 2 | An active community, but few robotics, IoT or AI packages target it. |
| 3 | A large community, and the major robotics, IoT and AI vendors publish packages or containers that run on it. |
| 4 | Everything in 3, plus vendors certify against it (NVIDIA, ROS, Canonical/Red Hat partner programs, industrial vendors) and there is a plugin or extension model OneMind can build on. |
| 5 | Everything in 4, plus it's the default target for physical-AI vendors (NVIDIA, ROS 2 Tier 1, OEMs) **and** it's open to OneMind's Marketplace without a gatekeeper. |

---

## 5. Evidence rules for every cell

1. **One claim ID per cell, at least.** Each gate result and each score cites a claim ID (`[C-<TAG>-###]`) from `evidence/claims.csv`, or a lab result in `evidence/lab/<spike>/`.
2. **Unverified scores 0.** A cell whose only support is UNVERIFIED gets the lowest anchor (0). For a gate, it counts as FAIL.
3. **SECONDARY caps at 3.** A cell supported only by SECONDARY sources can't score above 3.
4. **Lab-only anchors.** Anchors that say "in our lab" can be met only with an `evidence/lab/` result. A founder-hardware test that hasn't run yet leaves the cell at the highest anchor met **without** it, marked `pending-lab` in the cell.
5. **Hardware not on hand.** Where hardware is unavailable (`blocked: founder-hardware`), score on documentation evidence and mark the cell `doc-only`.
6. **Same evidence for every candidate.** The proposal (Debian 13 + Rugix) and the runner-up don't get different evidence standards. A refuter that finds a cell inconsistent with its sources forces a re-score, logged in §8.

## 6. Sensitivity analysis (mandatory)

For each decision S1–S5:

1. Recompute the ranking 14 times: each of the 7 weights at **+5** and at **−5**. The other weights are scaled in proportion so the total stays 100.
2. Report a table: perturbation → winner → margin over the runner-up.
3. **Robust:** the winner is the same in all 14 runs. **Fragile:** the winner changes in 1–3 runs; name the weight(s) that flip it and why that judgement is defensible. **Unstable:** the winner changes in 4 or more runs; the decision may not be presented as settled, and it goes to `26-OPEN-QUESTIONS-FOR-ZEUS.md`.
4. Also report the ranking with **gates relaxed one at a time** for any candidate that failed exactly one gate as CONDITIONAL-able, so the founder sees what each gate costs.

## 7. Score-sheet format

Every scorecard in the output files uses this layout:

| Candidate | G1 | G2 | G3 | G4 | G5 | C1 (20) | C2 (20) | C3 (15) | C4 (15) | C5 (10) | C6 (10) | C7 (10) | Total | Rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| *example* | PASS [C-…] | CONDITIONAL [C-…] | … | … | … | 3 [C-…] | … | … | … | … | … | … | 0–100 | |

Under the table, list each CONDITIONAL mitigation and each `pending-lab` cell.

### What competitors chose (the same scorecard, applied to the reference products)

This table frames how the gates read against proven products. It is filled in by W1 and W2 with claim IDs; it isn't a score of OneMind's options.

| Product | Base / update stack | Team-size constraint | Kubernetes? | Robotics? | Constraint fit with OneMind |
|---|---|---|---|---|---|
| Home Assistant OS | Buildroot + RAUC | Funded team (Nabu Casa) | No (Docker) | No | Partial: appliance and consumer UX match; no k8s, no robotics |
| umbrelOS 2.0 | Debian 13 + Rugix | Small company | No (Compose) | No | Partial: Debian appliance and Pi 5 match; no k8s, no IIoT |
| Olares | Installs on Ubuntu/Debian; no OS A/B | Funded team | Yes (k3s) | No | Partial: k3s match; lacks an image or rollback |
| balenaOS / Talos / Ubuntu Core / Red Hat Device Edge | Yocto A/B / API-driven immutable / snaps / bootc + greenboot | Vendor teams | Varies | Some | To be scored by W2 |

---

## 8. Change log

Any change after this freeze needs a row here **before** the new weights are used: date, version, the change, the reason, the evidence, who proposed it, and the ranking under **both** the old and the new weights. Changes are allowed only for a factual error in an anchor or a new founder decision. "The proposal looks worse" is never a reason.

| Date | Version | Change | Reason and evidence | Proposed by | Ranking before → after |
|---|---|---|---|---|---|
| 2026-11-10 | 1.0 | Initial freeze. Weights as suggested in RESEARCH-MISSION.md §6. Added two stricter rules: SECONDARY caps a cell at 3, and documentation alone caps C3 at 4. | Brief §6; stricter evidence rules reduce the risk of scoring marketing claims. | FRAME agent | n/a (nothing scored yet) |
| 2026-11-10 | 1.0 · cells rev-1 | **No weight or anchor change.** Cell re-scores under §5 rule 6 (transcribed here from `01-…` §3, where they were first logged): S1-1 A·C1 2 → 3 (umbrelOS Debian 12 → 13 OTA rebase [C-W3-039]); S1-2 A's engine Rugix → RAUC (no cell moves); S1-3/S1-4/S1-5 kept D·C2, D·C1 and C·C2 with variants; S2-1 RAUC·C3 4 → 3 (HAOS dropped CRLs [C-TD-home-assistant-os-014]; CVE [C-DEC-004]; no systemd-boot backend [C-DEC-001]). | Refuter findings on W2-P0-1/2 and P0-W3-2, and W3's rebase evidence. | DEC agent (rev. 1) | S1: D 62 · A 56 · C 56 → **D 62 · A 60** · C 56 (tie band; tie-break → A). S2: RAUC 61 · Mender 57 → **RAUC 58 · Mender 57** (tie; Mender wins 3/14). |
| 2026-11-11 | 1.0 · cells rev-2 | **No weight or anchor change.** Cell re-scores (from `01-…` §3, rev. 2): S1-6 D·G5 PASS → COND (Jetson is a second release and GPU path [C-REF-DC-technical-005, C-STEEL-ubu-006]); S1-7 and S1-8 kept A/D·C4 = 3 and D·C6 = 2, with variants; S2-2 RAUC·C3 3 → 4 (Secure Boot lab X-2R [C-LAB-secureboot-rauc-012…015]); S2-3 Mender·C6 3 → 4 (Apache-2.0, free at any size [C-STEEL-updates-mender-001]); S2-4 Mender·C4 2 → 3 (umbrelOS shipped on Mender [C-W3-040]); S4 Kopia·C1 citation fixed (C-W5-030 is the borg claim → C-STEEL-backup-kopia-014…016), score unchanged. | Independent steelmen (Ubuntu, Mender, Rugix, Kopia, K2) and the X-2R lab. | DEC agent (rev. 2) | S1: totals unchanged (D 62 · A 60); gates now COND for both on G5. S2: RAUC 58 · Mender 57 → **Mender 62 · RAUC 61** (tie in 14/14; tie-break → RAUC). S3–S5 unchanged. |
| 2026-11-11 | 1.0 · cells rev-3 | **No weight or anchor change.** Citation pass over every scorecard cell (critic pass-2 gap #9) plus the #11b Pi 5 sources: 32 new claims (`claims/SCORE.csv`). Uncited cells were cited, or set to the lowest anchor or a gate FAIL where no primary source exists. **Score moves:** S1 C·C2 1 → 3 (AlmaLinux bootc RPi images tested on Pi 5 [C-SCORE-025]; CUDA `rhel10` [C-SCORE-030]; toolkit `dnf` [C-SCORE-031]; `kernel-rt` [C-SCORE-029]), B·C2 1 → 2 [C-SCORE-027, SECONDARY], E·C4 0 → 2 [C-SCORE-023, C-SCORE-024]. S2 bootc·G2 FAIL → COND [C-SCORE-026, C-W2-041] (now ranked, 58.0); SWUpdate·C2 2 → 1. S3 k0s·C1 2 → 3, C4 2 → 3, C7 3 → 4 (same standard as k3s [C-SCORE-002, C-SCORE-004, C-W4-022]); MicroK8s·C1 2 → 3, C4 2 → 0, G5 PASS → FAIL (unproven); Podman·C1 3 → 2; Tiered·C1 3 → 2; Docker·G3, Podman·G2/G3, Tiered·G2 PASS → COND. S4 borg·G5 COND → FAIL (unproven); Longhorn·C7 3 → 2. S5 K3·C4 3 → 2. Full list: `scorecard-rev3.md` §8. | Critic pass-2 #9 and #11b; weights §5 rules 1, 2, 3, 5 and 6. | SCORE agent | **S1: D 62 · A 60 · C 56 → C 64 · D 62 · A 60** (C wins 14/14 on raw score but is inside the tie band with D in 11/14, so the tie-break must be re-run; variant C·C2 = 2 restores D 62 · C 60 · A 60). S2: Mender 62 · RAUC 61 unchanged (bootc 58 third, wins no run). S3: k3s 63 · RKE2 62 · Talos 61 · k0s 60 (was 51); MicroK8s unranked; Compose's G5-relaxed 64.0 survives. S4: restic 75 · Kopia 66 · Velero 49; borg unranked. S5: K1 71 · K2 66 · K3 61 (was 64) · K4 46. |

---

## Glossary

- **A/B update:** two copies of the OS ("slots"). The update is written to the copy that isn't running, and the device boots into it. If it fails, the device goes back to the old copy.
- **Health-gated commit:** the new slot is marked "good" only after checks pass (for example k3s and the core pods are ready). Until then, a reboot returns to the old slot.
- **Rebase:** moving a device to a new major OS version (for example Debian 13 to 14) in place, without reflashing.
- **Flavor split:** separate image variants for different hardware (for example a Jetson flavor on NVIDIA's Ubuntu-based Linux for Tegra), built and supported in parallel.
- **Gate:** a pass/fail test. Failing one removes a candidate from the ranking.
- **Anchor:** the written meaning of a score, so a "3" means the same thing to everyone.
- **Sensitivity analysis:** re-running the scoring with slightly different weights to check that the winner doesn't depend on one judgement call.
- **CRA:** the EU Cyber Resilience Act (Regulation (EU) 2024/2847), which requires sellers of digital products to declare and honour a security-support period.
- **PREEMPT_RT:** the Linux real-time patch set, now in the mainline kernel, which makes timing more predictable for control loops.
- **SBOM:** software bill of materials, the list of every component inside an image.
