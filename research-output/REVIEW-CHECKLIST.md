# Review checklist for Zeus

**Owner:** FINAL · **Date:** 2026-11-11 · **Matches:** `01-FOUNDATION-DECISION.md` revision 3 (final) and `26-OPEN-QUESTIONS-FOR-ZEUS.md` Z-01…Z-37
**Serves requirements:** RS-1, RS-6, RS-7, F-10, D-001
**How to use it:** read in the order of §1, then tick one box per line in §2 and §3. A ticked **Approve** means "build on this". **Change** means "write your choice next to it"; the plan in `20-…` names the week each decision is needed. Nothing here is legal advice; items marked (legal) need counsel.

> ### Explain it like I'm the founder
> You don't need to read 30 files. Read the five in bold in §1. That takes about three hours, and the PDF alone is the one-sitting version. Then work down the boxes. The decisions in §2 are the research's recommendations: approving them tells the build session (`30-…`) to go ahead. The ones in §3 are yours alone. Each has a recommendation you can accept, but nobody can make it for you. The first block in §3 is due **this week**.

---

## 1. Reading order

1. [ ] **The pull request** (draft PR #1, *Research: OneMind OS foundation & 10-year plan*). Its body holds the summary and links. Check the diff list for anything you don't want public.
2. [ ] **This checklist** (you are here).
3. [ ] **[`ONEMIND-OS-FOUNDATION-REPORT.pdf`](ONEMIND-OS-FOUNDATION-REPORT.pdf)**: the standalone, visual report (101 pages, F-10). The shortest route is the chapters "Executive answer", "Risks" and "Decisions for Zeus".
4. [ ] **[`00-EXECUTIVE-SUMMARY.md`](00-EXECUTIVE-SUMMARY.md)**: the answer, top findings and risks, and status per workstream, plus what remains (§7).
5. [ ] **[`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md)**: the decision with its scorecards, attacks and steelmen. Read the founder box, §1, §7 and §12; the rest is evidence.
6. [ ] **[`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md)**: every decision only you can make, with options and a recommendation.
7. [ ] [`20-PLAN-180-DAYS.md`](20-PLAN-180-DAYS.md): the next 26 weeks, its gates G1–G7, and days 1–10.
8. [ ] [`21-ROADMAP-5-10-YEARS.md`](21-ROADMAP-5-10-YEARS.md): year 1 through years 5–10, with exit criteria.
9. [ ] [`30-NEXT-ULTRACODE-BUILD-BRIEF.md`](30-NEXT-ULTRACODE-BUILD-BRIEF.md): the brief for the build session. Approve it last, after §2 and §3, because it builds on your answers.

Look things up as needed: `22` (tests to run on your hardware), `23` (risks), `24` (all 335 questions), `25` (all 97 requirements), `27` (learning path), [`README.md`](README.md) (every file).

---

## 2. Approve the research decisions (`01`)

### 2.1 The decision per layer (`01` §1)

| Decision | Recommendation (rev. 3) | Approve | Change |
|---|---|---|---|
| Base OS (D2) | Debian 13 core; Ubuntu 26.04 CI leg; Jetson on L4T Ubuntu 24.04 (beta, after Z-01); meta-tegra tested within 180 days; Ubuntu + RKE2 GPU flavor after Z-01; bootc Industrial profile in year 2 | [ ] | [ ] |
| Image build (D1) | OneMind's own image from a snapshot-pinned Debian; distro base kept (DC-20) | [ ] | [ ] |
| Updates and rollback (D3) | RAUC built from a pinned upstream tag (v1.15.2); NVIDIA A/B on Jetson; one release contract; Mender runner-up; engine-neutral layout | [ ] | [ ] |
| Health gate (D3) | Fresh post-boot signals only; apps excluded; 3 tries; watchdog; no auto-retry | [ ] | [ ] |
| Install paths (D1, P-7) | Flash image, USB installer, VM images, preinstalled, NVIDIA flash; host-modifying scripts unsupported after image GA | [ ] | [ ] |
| Kubernetes (D4) | k3s on platform nodes (≥ 4 GB + SSD), agent-only on capturable nodes, NATS leaf below, RKE2 on demand | [ ] | [ ] |
| Storage (D5) | local-path with a Retain class; Longhorn on 3+ nodes; ZFS mirror optional | [ ] | [ ] |
| Backups (D5) | restic, three keys; SQLite online backup bound to the k3s version; embedded etcd on hub/Pro/Omni if T-W5-03 passes | [ ] | [ ] |
| Kernel (D2/D6) | Board maintainers' kernels at launch; a OneMind-built LTS kernel (K2-hybrid) for the release that enforces Secure Boot with out-of-tree modules | [ ] | [ ] |
| Security (D6) | Day-1 layout (1 GiB ESP, LUKS2 data); `efi` + signed UKIs; PCR 7 + signed PCR 11 + PCR 15; anti-downgrade; db key on every x86 box; gateway-enforced approvals; CRA programme | [ ] | [ ] |
| Plugin extension points (DC-16) | E1–E10 in release 1 (E5, E6, E8 as v1-beta), signed-only enforcement | [ ] | [ ] |

### 2.2 The ADR-001 verdict (`01` §7)

- [ ] I accept the verdict: **confirmed** (own image, Debian core, A/B with a health gate, k3s, restic), **changed** (engine, datastore method, RKE2/FIPS, CRA and Secure Boot timing), **overturned** (Kairos for Jetson, system-upgrade-controller on image nodes, "DOKS in three changes", "no Fedora/RHEL role").
- [ ] I accept that Debian and RAUC are **tie-break wins** with written re-open triggers (`01` §3.1.5, §3.2; `20` §4.1), not scorecard wins.
- [ ] Update `docs/ADR-001-foundation.md` from "proposed" to "accepted with the changes in `01` §7" (a separate PR; the research did not edit `docs/`).

### 2.3 The recommendations (`01` §11; requirement IDs there)

- [ ] REC-DEC-01 Debian 13 core; Jetson on L4T; Ubuntu re-open conditions recorded
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
- [ ] REC-DEC-25 K2-hybrid kernel for the Secure Boot release
- [ ] REC-DEC-26 Mender runner-up tests (F3)
- [ ] REC-DEC-27 IIoT: pinned protocol images, go-fdo, LAB-W8-4 on both stacks
- [ ] REC-DEC-28 Version-bound datastore backups; restore drill per k3s version
- [ ] REC-DEC-29 RT profile with a 12 h acceptance test
- [ ] REC-DEC-30 Script install sunset (host-modifying only)
- [ ] REC-DEC-31 OneMind's own RAUC package from a pinned tag
- [ ] REC-DEC-32 One trial boot on Pi 5 and `efi`: bounded automatic re-offer
- [ ] REC-DEC-33 Run W2-HW-3 (bootc on a Pi 5) early
- [ ] REC-DEC-34 Debian + RAUC + k3s treated as unprecedented: hardware release gates
- [ ] REC-DEC-35 Jetson update backend hardening
- [ ] REC-DEC-36 Rev. 3 security hardening (db key on all x86, PCR 15, RT namespace)
- [ ] REC-DEC-37 Kernel fixes never held for an NVIDIA build
- [ ] REC-DEC-38 Embedded etcd on hub/Pro/Omni if T-W5-03 passes
- [ ] REC-DEC-39 CRA notified-body parallel track from 2027-Q1
- [ ] REC-DEC-40 DC-16 v1 freeze contents
- [ ] REC-DEC-41 Image recipe rules (initramfs, apparmor, SBOM + VEX)

---

## 3. Your decisions (`26`)

Tick the recommended option, or write another. "Due" is the week from `20` §2.3.

### 3.1 Due now (week 1)

- [ ] **Z-28** Purge leaked personal data from the branch history (one-time rewrite + force-push) **before the PR is marked ready** · rec. (a)
- [ ] **Z-01** (legal) Ask counsel and Canonical about modified Ubuntu, including Jetson · rec. (a) now
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
- [ ] **Z-23** Agent-only k3s on robots and field kits · rec. (a)

### 3.3 Weeks 9–21

- [ ] **Z-17** Robotics simulation GPU boxes on the Ubuntu flavor unless Isaac Sim passes on Debian · rec. (a) (G4)
- [ ] **Z-19** Secure Boot key model: factory db key + OneMind-built kernel for the enforcing release · rec. (a)
- [ ] **Z-21** Plugin contracts, review staffing, revenue share · rec. (a)
- [ ] **Z-02** Security updates install automatically by default, with opt-out and a window (CRA) · rec. (a) (G5)
- [ ] **Z-10** bootc Industrial profile in year 2; run W2-HW-3 early · rec. (a)
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
- [ ] Working tree committed and pushed; `gitleaks` and the hygiene greps clean, or each hit listed in `evidence/hygiene-log.md`
- [ ] Known gaps accepted: no completeness-critic pass 3; the master `evidence/claims.csv` not re-merged; every lab in emulation only (`00` §7)

## Glossary

| Term | Meaning |
|---|---|
| **Approve** | The build session may treat the item as decided. |
| **Gate (G1–G7)** | A dated go/no-go point in `20-…` §4. |
| **Z-ID** | A founder decision in `26-…`. |
| **REC-DEC** | A recommendation in `01-…` §11, each traced to requirement IDs. |
| **Tie-break win** | A choice that tied on the scorecard and won on pre-named decision-critical evidence. |

## What competitors do about review and approval (constraint fit)

| Practice | Who | Constraint fit |
|---|---|---|
| An architecture decision record per foundation choice, marked proposed → accepted | OneMind already does this (`docs/ADR-001-foundation.md`) | **High**: the §2.2 box closes ADR-001 the same way |
| Release signing key kept in CI secrets | Home Assistant OS [C-TD-home-assistant-os-012] | **Low**: Z-04 recommends an offline root instead, because one CI leak would void every box |
| Offline root with M-of-N hardware signers (2.1 beta only) | umbrelOS [C-TD-umbrelos-013] | **High**: the model Z-04 recommends |
