# Review checklist for Zeus

**Owner:** FINAL · **Date:** 2026-11-11 · **Matches:** `01-FOUNDATION-DECISION.md` revision 4.1 (no score change from rev. 4) and `26-OPEN-QUESTIONS-FOR-ZEUS.md` Z-01…Z-41
**Serves requirements:** RS-1, RS-6, RS-7, F-10, D-001
**How to use it:** read in the order of §1, then tick one box per line in §2 and §3. A ticked **Approve** means "build on this". **Change** means "write your choice next to it"; the plan in `20-…` names the week each decision is needed. Nothing here is legal advice; items marked (legal) need counsel.

> ### Explain it like I'm the founder
> You don't need to read 30 files. Read the five in bold in §1. That takes about three hours, and the PDF alone is the one-sitting version. Then work down the boxes. The decisions in §2 are the research's recommendations: approving them tells the build session (`30-…`) to go ahead. The ones in §3 are yours alone. Each has a recommendation you can accept, but nobody can make it for you. The first block in §3 is due **this week**.
>
> **What changed in revision 4.** Before scoring, the research locked its contest rules. Revision 3 broke one of them to keep Debian, so revision 4 applies the rules as locked. The base OS of record is now **Ubuntu 26.04 LTS + RAUC**. It wins narrowly (11 of 14 sensitivity runs) and only if Canonical allows a modified Ubuntu, or OneMind strips the brand and rebuilds. Debian 13 is still built alongside it, and it becomes the base automatically if bootc's Pi 5 test fails. You can still choose Debian yourself, but then it is your logged decision (Z-38), not the scorecard's result. **Revision 4.1** changed no score: three critics who saw only the decision all said "weakened", none "wrong". The test most likely to move the base without hardware, the Ubuntu Secure Boot VM test (U-SB, LT-VM-20), could not run here; if it fails, bootc becomes the base. Running it is Z-41.

---

## 1. Reading order

1. [ ] **The pull request** (draft PR #1, *Research: OneMind OS foundation & 10-year plan*). Its body holds the summary and links. Check the diff list for anything you don't want public.
2. [ ] **This checklist** (you are here).
3. [ ] **[`ONEMIND-OS-FOUNDATION-REPORT.pdf`](ONEMIND-OS-FOUNDATION-REPORT.pdf)**: the standalone, visual report (F-10), 111 pages (rev. 4.1 build), rebuilt from `01` rev. 4.1. The shortest route is the chapters "Executive answer", "Risks" and "Decisions for Zeus".
4. [ ] **[`00-EXECUTIVE-SUMMARY.md`](00-EXECUTIVE-SUMMARY.md)**: the answer, top findings and risks, and status per workstream, plus what remains (§7).
5. [ ] **[`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md)**: the decision with its scorecards, attacks and steelmen. Read "What changed in revision 4" and "What revision 4.1 changed", the founder box, §1, §3.1.6 (the base-OS result and its decision map), §7 and §12; the rest is evidence.
6. [ ] **[`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)**: every decision only you can make, with options and a recommendation.
7. [ ] [`20-PLAN-180-DAYS.md`](20-PLAN-180-DAYS.md): the next 26 weeks, its gates G0–G7, and days 1–10.
8. [ ] [`21-ROADMAP-5-10-YEARS.md`](21-ROADMAP-5-10-YEARS.md): year 1 through years 5–10, with exit criteria.
9. [ ] [`30-NEXT-ULTRACODE-BUILD-BRIEF.md`](30-NEXT-ULTRACODE-BUILD-BRIEF.md): the brief for the build session. Approve it last, after §2 and §3, because it builds on your answers.

Look things up as needed: `22` (tests to run on your hardware), `23` (risks), `24` (all 335 questions), `25` (all 97 requirements), `27` (learning path), [`README.md`](README.md) (every file).

---

## 2. Approve the research decisions (`01`)

### 2.1 The decision per layer (`01` §1)

| Decision | Recommendation (rev. 4) | Approve | Change |
|---|---|---|---|
| Base OS (D2) | **Ubuntu 26.04 LTS core + RAUC** (the frozen protocol's result; fragile, 11 of 14 runs), **conditional** on scorecard gates G1 (Z-01: Canonical's permission or a debranded rebuild) and G5; a Debian 13 CI leg is built from the same definition until the base is locked at a gate before the first box ships; **pre-registered map:** W2-HW-3 fails → Debian 13, Canonical refuses and you reject the debranded rebuild → RHEL-family bootc, both → back to you; Jetson on L4T/JetPack (beta, after Z-01); meta-tegra tested within 180 days; Ubuntu + RKE2 GPU flavor after Z-01; bootc Industrial profile on AlmaLinux 10 / RHEL 10 image mode in year 2 (CentOS Stream and Fedora IoT as CI canaries only). Overriding the base is Z-38 | [ ] | [ ] |
| Image build (D1) | OneMind's own image from a snapshot-pinned distro base (both legs); distro base kept on the NVIDIA/CUDA path and one-person maintainability, not on CVE counts (DC-20) | [ ] | [ ] |
| Updates and rollback (D3) | RAUC built from a pinned upstream tag (v1.15.2); NVIDIA A/B on Jetson; one release contract; Mender runner-up; engine-neutral layout | [ ] | [ ] |
| Health gate (D3) | Fresh post-boot signals only; apps excluded; 3 tries; watchdog; no auto-retry. Proven for a single box on SQLite; a cluster rolls back through an `etcd-snapshot` restore (untested); app migrations held until commit; "image bad" vs "environment bad" verdicts; old slot retired after commit with a version floor (DC-12) | [ ] | [ ] |
| Install paths (D1, P-7) | Flash image, USB installer, VM images, preinstalled, NVIDIA flash; host-modifying scripts unsupported after image GA | [ ] | [ ] |
| Kubernetes (D4) | k3s on platform nodes (≥ 4 GB + SSD), agent-only on capturable nodes, NATS leaf below, RKE2 on demand | [ ] | [ ] |
| Storage (D5) | local-path with a Retain class; Longhorn on 3+ nodes; ZFS mirror optional | [ ] | [ ] |
| Backups (D5) | restic, three keys; SQLite online backup bound to the k3s version; embedded etcd on hub/Pro/Omni if T-W5-03 passes | [ ] | [ ] |
| Kernel (D2/D6) | Board maintainers' kernels at launch; for the release that enforces Secure Boot with out-of-tree modules, first try a OneMind shim with its own `vendor_cert` on the stock kernel (T-W19-03), and use a OneMind-built LTS kernel (K2-hybrid) only if that fails | [ ] | [ ] |
| Security (D6) | Day-1 layout (1 GiB ESP, LUKS2 data); `efi` + signed UKIs; PCR 7 + signed PCR 11 + PCR 15; anti-downgrade; db key on every x86 box; gateway-enforced approvals; CRA programme | [ ] | [ ] |
| Plugin extension points (DC-16) | E1–E10 in release 1 (E5, E6, E8 as v1-beta), signed-only enforcement; E10 also pins, gates and records the Pi EEPROM and Jetson QSPI firmware | [ ] | [ ] |

### 2.2 The ADR-001 verdict (`01` §7)

- [ ] I accept the verdict: **confirmed** (own image, A/B with a health gate, RAUC, k3s, restic), **changed** (**D2 core base: Debian 13 → Ubuntu 26.04 LTS, conditional on Z-01**; engine, datastore method, RKE2/FIPS, CRA and Secure Boot timing), **overturned** (Kairos for Jetson, system-upgrade-controller on image nodes, "DOKS in three changes", "no Fedora/RHEL role").
- [ ] I accept that the base OS is the **frozen protocol's result** (`01` §3.1.6): every sensitivity run is a tie, settled by a tie-break row count (Ubuntu over bootc 6–4), so it is fragile; Debian or bootc can win only through the decision map written in advance or my own logged decision (Z-38). RAUC remains a **tie-break win** over Mender (`01` §3.2). Revision 3's three-way head-to-head rule and its "Debian kept" verdict are withdrawn.
- [ ] Update `docs/ADR-001-foundation.md` from "proposed" to "accepted with the changes in `01` §7" (a separate PR; the research did not edit `docs/`).

### 2.3 The recommendations (`01` §11; requirement IDs there)

- [ ] REC-DEC-01 Debian 13 core; Jetson on L4T; Ubuntu re-open conditions recorded (**superseded by REC-DEC-42 as the decision of record**; now describes the Debian leg)
- [ ] REC-DEC-02 Ask counsel and Canonical before any Ubuntu-based flavor ships
- [ ] REC-DEC-03 GPU-server flavor on Ubuntu LTS + RKE2 after REC-DEC-02
- [ ] REC-DEC-04 bootc Industrial profile in year 2; Fedora IoT CI canary now
- [ ] REC-DEC-05 RAUC, verity-only, ≥ 1.15.2, 3 tries, watchdog
- [ ] REC-DEC-06 One release contract; NVIDIA A/B on Jetson
- [ ] REC-DEC-07 Fresh-signal health gate
- [ ] REC-DEC-08 §4.3 disk layout before the first image
- [ ] REC-DEC-09 k3s on platform nodes; NATS leaf below; RKE2 on demand
- [ ] REC-DEC-10 Market portability; Compose importer
- [ ] REC-DEC-11 Retain class; restic three-key backups; verified restores
- [ ] REC-DEC-12 Kernel contract in CI; per-SKU support period
- [ ] REC-DEC-13 Gateway-enforced approvals; robot-runtime exception
- [ ] REC-DEC-14 CRA programme
- [ ] REC-DEC-15 Olares-derived layer model L0–L5
- [ ] REC-DEC-16 Planned in-place Debian rebases; T-W3-04 gate
- [ ] REC-DEC-17 Two CI legs (Debian, Ubuntu 26.04)
- [ ] REC-DEC-18 Jetson: L4T beta, meta-tegra lab, factory A/B
- [ ] REC-DEC-19 Robotics simulation GPU boxes on the Ubuntu flavor unless Isaac Sim passes on Debian
- [ ] REC-DEC-20 x86 `efi` backend + signed UKIs; GRUB fallback
- [ ] REC-DEC-21 Anti-downgrade; PCR policy; factory key enrolment
- [ ] REC-DEC-22 k3s node roles; hardened config
- [ ] REC-DEC-23 k3s on a read-only root (bind mounts, pre-install marker)
- [ ] REC-DEC-24 DC-16 enforcement package
- [ ] REC-DEC-25 K2-hybrid kernel for the Secure Boot release (rev. 4: only if the shim route in REC-DEC-48 fails)
- [ ] REC-DEC-26 Mender runner-up tests (F3)
- [ ] REC-DEC-27 IIoT: pinned protocol images, go-fdo, LAB-W8-4 on both stacks
- [ ] REC-DEC-28 Version-bound datastore backups; restore drill per k3s version
- [ ] REC-DEC-29 RT profile with a 12 h acceptance test
- [ ] REC-DEC-30 Script install sunset (host-modifying only)
- [ ] REC-DEC-31 OneMind's own RAUC package from a pinned tag
- [ ] REC-DEC-32 One trial boot on Pi 5 and `efi`: bounded automatic re-offer
- [ ] REC-DEC-33 Run W2-HW-3 (bootc on a Pi 5) early (rev. 4: before gate G1, week 4; see REC-DEC-44)
- [ ] REC-DEC-34 Debian + RAUC + k3s treated as unprecedented: hardware release gates
- [ ] REC-DEC-35 Jetson update backend hardening
- [ ] REC-DEC-36 Rev. 3 security hardening (db key on all x86, PCR 15, RT namespace)
- [ ] REC-DEC-37 Kernel fixes never held for an NVIDIA build
- [ ] REC-DEC-38 Embedded etcd on hub/Pro/Omni if T-W5-03 passes
- [ ] REC-DEC-39 CRA notified-body parallel track from 2027-Q1
- [ ] REC-DEC-40 DC-16 v1 freeze contents
- [ ] REC-DEC-41 Image recipe rules (initramfs, apparmor, SBOM + VEX)
- [ ] REC-DEC-42 *(rev. 4)* Base of record = Ubuntu 26.04 LTS + RAUC (frozen-protocol result), conditional on Z-01 and G5; both CI legs until the base-lock gate; the pre-registered map decides
- [ ] REC-DEC-43 *(rev. 4)* Send the Canonical and counsel outreach in week 1; give RR-09 a stated cost bound
- [ ] REC-DEC-44 *(rev. 4)* Run W2-HW-3 before gate G1 (week 4); a Debian/Ubuntu + RAUC box cannot move to bootc without a reflash
- [ ] REC-DEC-45 *(rev. 4)* DC-12 additions: migrations held until commit, cluster rollback via `etcd-snapshot`, two gate verdicts, `prevent-late-fallback` and a version floor, chart API scan, stepping-path retention
- [ ] REC-DEC-46 *(rev. 4)* DC-20: base the image decision on CUDA and maintainability; re-measure CVEs with a compiled-source kernel filter, a second scanner and VEX
- [ ] REC-DEC-47 *(rev. 4)* E10 firmware layer: EEPROM/QSPI pinned, gated and recorded; kernel × firmware CI on real boards
- [ ] REC-DEC-48 *(rev. 4)* T-W19-03's first arm: a OneMind shim with its own `vendor_cert`; K2-hybrid only if it fails
- [ ] REC-DEC-49 *(rev. 4)* Borrowed-DC fixes: Industrial profile on AlmaLinux 10/RHEL 10; FDO experimental with an IDevID fallback; Jetson support periods from the current branch until an r36 → r39 OTA lab passes; kine ≥ v0.13.10; backups verified only with datastore-health checks

---

## 3. Your decisions (`26`)

Tick the recommended option, or write another. "Due" is the week from `20` §2.3.

### 3.1 Due now (week 1)

- [ ] **Z-28** Purge leaked personal data from the branch history (one-time rewrite of all four pushed commits + force-push) **before the PR is marked ready** · rec. (a)
- [ ] **Z-41** Run the Ubuntu Secure Boot VM test U-SB (LT-VM-20) on your Mac on day 1, or approve an Ubuntu mirror for the lab; also judge the two disclosed reads past the Ubuntu block (`evidence/hygiene-log.md` §7) · rec. (a) run it day 1. If it fails, the pre-registered map gives bootc
- [ ] **Z-01** (legal) Ask counsel and Canonical about modified Ubuntu, including Jetson, with a written price · rec. (a) now. **Rev. 4:** this now gates the base of record; meanwhile the default is Ubuntu 26.04 + RAUC, nothing Ubuntu-based ships before an answer, and both CI legs are built
- [ ] **Z-38** Base OS: accept the frozen-protocol result (Ubuntu 26.04 + RAUC, with its conditions and the pre-registered map), or override it as your own logged decision · rec. (a) accept. It blocks the base-lock gate, the default base in `30-…` and the PDF's base-OS chapter
- [ ] **Z-37** Approve sending the vendor outreach drafts (Canonical, Freexian, Red Hat, NVIDIA/Inception) · rec. (a)
- [ ] **Z-30** (legal) Incorporate, so Inception and vendor agreements can proceed · rec. (a)
- [ ] **Z-14** Platform first inside an image-first plan · rec. (a)
- [ ] **Z-24** Script install unsupported after image GA (host-modifying scripts only) · rec. (a)

### 3.2 Weeks 2–8

- [ ] **Z-29** (legal) Trademark clearance for "OneMind" before public beta branding · rec. (a)
- [ ] **Z-03** Update engine: RAUC / Mender / Rugix · rec. RAUC (gate G1, week 4)
- [ ] **Z-22** Third-party host-level plugins in release 1 only if T-W19-01's security variant passes · rec. (a)
- [ ] **Z-18** x86 boot route: `efi` + signed UKIs if the combined spike passes, else GRUB · rec. (a) (G2, week 6)
- [ ] **Z-04** Signing-key custody: offline root in an HSM, 2-of-3 signers, succession plan; decide on owner "sovereign mode" · rec. (a) (G3, week 8)
- [ ] **Z-07** k3s floor: server on ≥ 8 GB, 4 GB + SSD as a limited profile · rec. (a)
- [ ] **Z-10** bootc Industrial profile in year 2 on AlmaLinux 10 / RHEL 10 image mode (CentOS Stream and Fedora IoT as CI canaries); **run W2-HW-3 before gate G1 (week 4)**, because its result now decides between the protocol result and Debian · rec. (a)
- [ ] **Z-40** Write down the four scoring rules (tie-break counting, how "experimental" support scores, base-only vs whole-stack C4, no third finalist) in `scorecard-weights.md` §8 **before W2-HW-3 runs** · rec. (a) before gate G1
- [ ] **Z-23** Agent-only k3s on robots and field kits · rec. (a)

### 3.3 Weeks 9–21

- [ ] **Z-17** Robotics simulation GPU boxes on the Ubuntu flavor unless Isaac Sim passes on Debian · rec. (a) (G4)
- [ ] **Z-19** Secure Boot key model: factory db key + OneMind-built kernel for the enforcing release · rec. (a)
- [ ] **Z-21** Plugin contracts, review staffing, revenue share · rec. (a)
- [ ] **Z-02** Security updates install automatically by default, with opt-out and a window (CRA) · rec. (a) (G5)
- [ ] **Z-27** Pull LAB-W8-4 and a Flight Control simulation into the 180 days · rec. (a)
- [ ] **Z-12** Default TAK server: TAK Server on 8 GB+, OpenTAKServer on 4 GB · rec. as written
- [ ] **Z-20** Fleet server: OneMind release service on NATS; fleet test picks the plane in year 1 · rec. (a)
- [ ] **Z-16** Jetson base: L4T for the beta, meta-tegra lab within 180 days · rec. (a) (G6)
- [ ] **Z-13** "Mirror" means warm standby by default · rec. (b) warm standby as the default meaning (`26` Z-13); W11 and Q300 suggest shipping config clone + replication first in year 1
- [ ] **Z-06** Support period per SKU ≥ 5 years, capped by the board's kernel window · rec. (a)

### 3.4 Week 26 and later, or on a trigger

- [ ] **Z-05** (legal) CRA route: FOSS self-assessment primary, notified-body parallel track from 2027-Q1, counsel by 2027-Q2 · rec. (a)
- [ ] **Z-36** (legal) Add the four extra counsel questions (rebase as substantial modification, Umbrel store converter, 16 CFR 318, CA/TX app-store laws)
- [ ] **Z-09** GPU-server flavor on Ubuntu + RKE2 once Z-01 is answered · rec. (a)
- [ ] **Z-15** Fuse only OneMind-built hardware after a soak; never in the 180 days · rec. (a)
- [ ] **Z-08** RKE2 only when a buyer needs FIPS/STIG · rec. (a)
- [ ] **Z-25** FIPS/STIG not a P0 property before a public-safety buyer exists · rec. (a)
- [ ] **Z-11** Industrial certification through a certified partner first · rec. (a)
- [ ] **Z-26** Desktop plugins: Omarchy's manifest shape, Verified publishers only, off by default · rec. (a)
- [ ] **Z-39** Does an unmet, third-party-dependent condition (such as Canonical's permission) disqualify a candidate? · rec. (a) no, it stays ranked; cost RR-09 when Canonical answers. Any other reading needs a logged rule change, best written before Canonical answers

### 3.5 Product calls

- [ ] **Z-31** First segment: homestead/greenhouse and self-hosting families, then TAK field teams; interviews before a pre-order · rec. (a)
- [ ] **Z-32** Desktop edition: client + plugin pack for stock Omarchy, no OneMind Arch image · rec. (a)
- [ ] **Z-33** Run a content-free, open-source APNs relay · rec. (a)
- [ ] **Z-34** Remote access: the user chooses at setup (Headscale on Pro, Tailscale simplest) · rec. (c)
- [ ] **Z-35** Kids' tablets: bring-your-own in year 1; a managed bundle only after T-W13-2 · rec. (a) then (b)

### 3.6 REQUIREMENTS open questions and Blueprint questions (`26` §B, §C)

- [ ] **OQ-2** Kubernetes on every box sold; NATS leaf on connected devices (= Z-07)
- [ ] **OQ-3** Apache-2.0 open core (D-001); write the pro/open ADR before the first paid feature
- [ ] **OQ-4** First tier and segment: Lite x86 first, Pi 5 Edge profile second; certified hardware list in year 1 (= Z-31)
- [ ] **OQ-5** First internal app = the Blueprint's seven-step vertical slice
- [ ] **Blueprint:** Google/Pixel hardware is acceptable for field EUDs (Pixel 9a/10a + GrapheneOS) after the ATAK test
- [ ] **Blueprint:** run LT-X86-00 on the Dell and record its state
- [ ] **Blueprint:** task system = a thin OneMind Tasks module with Todoist import; Vikunja optional

### 3.7 Access and information only you can give (`26` §D, §F)

- [ ] Order the Pi 5 (4 and 8 GB, NVMe) and the Jetson Orin Nano Super (`20` day 1)
- [ ] Run the read-only live-cluster checks LT-CLU-01…11 and share the outputs
- [ ] Say where you saw the GrapheneOS Pixel Tablet ATAK crash, and list your ATAK loadout
- [ ] Share the Blueprint originals (Nov 3–4) if available
- [ ] Brief counsel with Z-01, Z-05, Z-19, Z-29, Z-30 and Z-36

---

## 4. Before the PR is marked ready

- [ ] Z-28 decided and, if (a), the rewrite done
- [ ] Working tree committed and pushed (rev. 4 is in `b933b86`, pushed; **rev. 4.1 is not committed yet**); `gitleaks` and the hygiene greps clean, or each hit listed in `evidence/hygiene-log.md` (0 gitleaks hits after rev. 4)
- [ ] The PDF, 111 pages (rev. 4.1 build), checked against `01` rev. 4.1 (base-OS chapter, the U-SB status and the G1/G6 rows)
- [ ] Known gaps accepted: the loop is not dry (critic pass 7 found 4 new gaps; rev. 4.1 added three blind S1R5 refuters, all *weakened*, none refuted, `01` §5.1.3; U-SB is BLOCKED until Z-41); the master `evidence/claims.csv` lacks the 171 rev-4 rows and the rev-4.1 rows; every lab in emulation only (`00` §7)

## Glossary

| Term | Meaning |
|---|---|
| **Approve** | The build session may treat the item as decided. |
| **Gate (G0–G7)** | A dated go/no-go point in `20-…` §4. Not the same as the scorecard's must-pass gates G1–G5 in `evidence/scorecard-weights.md` (G1 licence, G5 one OS from Pi to cluster), which `01` also calls G1 and G5. |
| **Z-ID** | A founder decision in `26-…`. |
| **REC-DEC** | A recommendation in `01-…` §11, each traced to requirement IDs. |
| **Tie-break win** | A choice that tied on the scorecard and won on pre-named decision-critical evidence. |
| **Frozen protocol** | The scoring rules and weights locked in `evidence/scorecard-weights.md` before any candidate was scored. Any later change must be logged there with the ranking under both the old and new rule. |
| **Decision of record** | What the build proceeds on until you decide otherwise. For the base OS it is the frozen protocol's result. |
| **Pre-registered decision map** | Outcomes written down before a test or answer arrives (here W2-HW-3 and Z-01), so the result cannot be argued after the fact. |

## What competitors do about review and approval (constraint fit)

| Practice | Who | Constraint fit |
|---|---|---|
| An architecture decision record per foundation choice, marked proposed → accepted | OneMind already does this (`docs/ADR-001-foundation.md`) | **High**: the §2.2 box closes ADR-001 the same way |
| Release signing key kept in CI secrets | Home Assistant OS [C-TD-home-assistant-os-012] | **Low**: Z-04 recommends an offline root instead, because one CI leak would void every box |
| Offline root with M-of-N hardware signers (2.1 beta only) | umbrelOS [C-TD-umbrelos-013] | **High**: the model Z-04 recommends |
