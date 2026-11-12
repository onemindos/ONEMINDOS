<!-- SPDX-License-Identifier: Apache-2.0 -->
# 09 · Updates across classes (FB-8): one release contract, five update engines, rings across thousands of nodes

**Date:** 2026-11-12 · **Workstream:** FB-8 (Tier A) · **Lab:** fb4-fleet-rings (rings, halt, rollback, partition) in `05-…`; engines themselves were tested in mission 01.
**Serves requirements:** R-1, R-2, R-3, F-9, F-11, M-6, N-2 · CRA obligations (C-W6-001, C-W6-002) · not legal advice

> **Explain it like I'm the founder.** Different machines update in different ways, and OneMind should not pretend otherwise. Your OneMind boxes swap to a new copy of the whole system and switch back by themselves if it is unhealthy. A Jetson uses NVIDIA's own two-copy updater. A cloud or company server running OneMind "on top" gets new OneMind packages but keeps its own operating system. A small chip (ESP32) gets new firmware through its bootloader, which tries the new version once and reverts unless it confirms itself. A factory controller (PLC) is **never** updated automatically; OneMind only tells you a newer version exists. What *is* the same everywhere is the release contract: every release is signed, described, goes to one test machine first, then to the next ring only if the previous ring is healthy, and can be stopped with one tap.

## 1. One release contract

Every update, whatever its engine, is a **release** with: a signed manifest (TUF-style metadata, mission 01 / contract §12.13), the target class and engine, a version and a *security version* (for anti-rollback), the health check that decides success, and the rollback path (or the honest "no rollback" label). The gateway applies releases as **jobs** (signed, expiring; FABRIC §5.4) and records each step in the audit.

## 2. Per class

| Class | Engine | Rollback | Who triggers | Notes / evidence |
|---|---|---|---|---|
| Image node | RAUC A/B bundle, fresh-signal health gate (mission 01, OneMind-built RAUC 1.15.2) | automatic (3 trial boots) | owner policy / window (R-1) | not reopened; cluster rollback across a k3s minor needs the pre-update snapshot (`05-…` §3.3) |
| Jetson (L4T) | NVIDIA image-based A/B OTA (mission 01) + OneMind packages | NVIDIA A/B; OneMind packages by version pin | owner | per-module support periods (RR-01); hardware sold to 2032 [C-FB1-001] |
| Installer mode (stock Ubuntu/Debian, company servers) | signed apt packages for `onemindd`, NATS, k3s (pinned) | **package downgrade only; no OS rollback** (labelled) | owner; the OS stays with its admin | Flight Control has the same split ("package mode" vs image mode) and warns that mixing them stalls OS rollouts [C-FB11-005] |
| Managed-K8s site | OneMind workloads by revision; the provider upgrades Kubernetes | revision rollback | owner | no host updates |
| MCU behind an adapter | MCUboot or ESP-IDF OTA, **signed**, test boot then confirm | MCUboot "revert" swap if not confirmed; ESP-IDF pending-verify → rollback on reset [C-FB8-001, C-FB8-002] | owner, per device class; never automatic for devices that actuate | **ESP-IDF anti-rollback burns an eFuse: irreversible**; OneMind must never raise the security version without an explicit owner action |
| PLC / safety controller / flight controller | **none from OneMind** | — | the vendor's tool, by a qualified person | OT practice puts "performance, reliability, and safety requirements" first [C-FB8-003]; OneMind reads the firmware version and raises an advisory |

## 3. Rings across thousands of nodes

**Default rings (proposal):** ring 0 = one canary per hardware class chosen by the owner (or OneMind's own lab boxes for OneMind releases); ring 1 = about 10 % of sites; ring 2 = the rest. A ring starts only when the previous ring's success ratio meets the threshold (Flight Control's `BatchSequence` rule [C-FB11-005]) **and** no node of the previous ring is unhealthy (Fleet's partition gate [C-FB4-005]). A failure halts the rollout and alerts; the halted release can be rolled back with one action.

**What the lab adds** (`05-…` §3, fb4-fleet-rings): Fleet's partition settings need care. With `maxUnavailable: 0` **and** `maxUnavailablePartitions: 0`, an update never started in 15 minutes (T3); with `maxUnavailable: 1` a bad release was held at ring 0 and rolled back in one step, but an offline ring-1 site held back ring 2 (E6, `05-…` §3). The general lesson for OneMind's own engine: define "ring k may start" from the *previous* ring's measured health, not from a count of currently-unready partitions that includes the update itself.

**Scale engine options** (unchanged from mission 01 W8-R11, refined):

| Scale | Engine for OS releases | Engine for app releases |
|---|---|---|
| 1–10 sites | the site hub's updater (contract §12.13) + the fleet hub sequencing jobs (CORE-UPDATE-9) | gateway revisions, rings sequenced by the fleet hub |
| 10–1,000 sites | same, with region rings | same |
| 1,000+ sites | optional Eclipse hawkBit as the RAUC deployment server (hawkBit 1.2.0, 2026-11-11; its release notes list target group quotas and request throttling, C-G4U-011; RAUC documents deployment servers as separate, C-G4U-010) | Fleet for Kubernetes-heavy enterprise sites (year 2+, `05-…`) |

## 4. CRA obligations per class (identification, not legal advice)

The CRA (Reg. (EU) 2024/2847) applies from 2027-12-11, reporting from 2026-09-11 (C-W6-001); support periods must reflect expected use and be at least five years unless use is shorter (C-W6-002). Mission 01's interpretation, which needs counsel, is that a OneMind box is classified by its core function (C-REF-W6-technical-008).

| Class | OneMind's role (interpretation) | Update obligation that follows |
|---|---|---|
| OneMind image + boxes | manufacturer of the product | security updates for the support period; vulnerability handling and reporting |
| Installer-mode software on someone else's OS | manufacturer of the OneMind software only | updates for OneMind's components; the OS vendor covers the OS |
| Jetson robots built and sold by OneMind | manufacturer of the integrated product (includes NVIDIA's BSP) | must track NVIDIA's support periods (RR-01) |
| Third-party MCUs, PLCs, flight controllers | not OneMind's product | none from OneMind beyond not breaking them; advisories only |
| Market apps | depends on who places them on the market (29-…) | out of scope here |

All of this is `blocked: founder-decision` for counsel (Z-05 in mission 01).

## 5. What competitors do (constraint-matched)

| Product | Staged rollout | Rollback | Constraint fit | Take |
|---|---|---|---|---|
| Flight Control | `BatchSequence` batches with a success threshold; agent stages, then transactional update or rollback (greenboot) [C-FB11-005] | yes (image mode) | High pattern, RHEL OS | Success-threshold gating |
| Rancher Fleet | partitions, `maxUnavailable`, `maxUnavailablePartitions` [C-FB4-005] | re-apply previous bundle (lab) | High for Kubernetes sites | Partition gate, with the lab's caveat |
| balena | queued OS updates since Q3 2026; ESR every quarter, 9 months each (C-TD-balenaos-022, -039) | automatic on failed health | Medium | ESR as a paid stability channel |
| Viam | modules track latest or a pinned tag; **no canary or percentage rollout** (C-TD-tier-c-robotics-049) | none automatic (C-TD-tier-c-robotics-044) | Low | The beat |
| Greengrass | continuous deployments to thing groups [C-FB11-006] | per component | Low (cloud) | — |

## 6. Open items

- **ZF-12** default ring sizes and success threshold (proposal: 1 canary per class / 10 % / rest; 100 % success for ring 0, 95 % after).
- Proposed **F-21**: "every class in the join matrix has a documented update engine and rollback path, or an explicit 'never updated by OneMind' label".

## Glossary

| Term | Meaning |
|---|---|
| Ring | A group that receives a release together; ring 0 first |
| Success threshold | The share of a ring that must update successfully before the next ring starts |
| Anti-rollback | Hardware refuses older firmware; on ESP32 this is a one-way eFuse |
| TUF | The Update Framework: signed metadata that says which releases are valid |
