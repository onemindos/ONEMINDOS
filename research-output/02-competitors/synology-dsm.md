# Synology DSM: Tier C teardown

**Workstream:** W1 (Tier C) · **Tag:** TD-tier-c-nas · **Date:** 2026-11-11
**Claims:** `evidence/claims/TD-tier-c-nas.csv` (Synology rows C-TD-tier-c-nas-031 … 042), plus reused C-W11-057 and C-W18-001 · **Sources:** `evidence/sources/TD-tier-c-nas.md`
**Release analysed:** **DSM 7.4.1-90080 Update 1** (2026-10-12), using the DS925+ release-note feed [C-TD-tier-c-nas-031]. Closed source, so there are no code pins. The GPL kernel sources for DSM 7.4-90080 were inspected as an index [C-TD-tier-c-nas-035].
**Requirements served:** R-1, R-3, A-1, A-5, A-6, AI-1, AI-3, AI-4, AI-5, M-2, M-8, H-1, H-2, UX-6, F-14

> ### Explain it like I'm the founder
> Synology is the big, polished NAS brand. It sells boxes, and DSM (DiskStation Manager) is the OS that comes on them. It is the "Apple" model: **hardware and software from one vendor**, a desktop-like web UI, and dozens of first-party apps.
>
> **The lessons for OneMind are mostly warnings.**
> 1. **Old kernels for a long time.** DSM 7.4 still ships Linux **3.10, 4.4 and 5.10** kernels across 28 chip platforms. Only 5.10 is still a kernel.org longterm kernel, and that ends in Dec 2026 [C-TD-tier-c-nas-035, C-W18-001]. Every box gets the kernel it shipped with.
> 2. **No way back.** Every DSM update says you can never downgrade [C-TD-tier-c-nas-032].
> 3. **App signing was removed.** DSM 7 removed package signing [C-TD-tier-c-nas-036].
> 4. **Lock-in backfired.** Restricting third-party drives caused a backlash, and Synology relaxed it in DSM 7.3 [C-TD-tier-c-nas-038].
>
> **But its AI design is worth copying.** "AI Console" lets an admin turn AI on per app and per user. It masks personal data before it leaves the box and logs every AI request [C-TD-tier-c-nas-037]. That maps directly onto OneMind's "may this data go to AI" flag.

## 1. W1 fields

| Field | Synology DSM (evidence) |
|---|---|
| **Architecture** | A vendor appliance OS. Web desktop plus Package Center for first-party and third-party `.spk` packages. Container Manager (Docker) for containers [C-TD-tier-c-nas-036, C-TD-tier-c-nas-040]. Two-box High Availability on identical units [C-W11-057]. |
| **Base OS / kernel** | Closed Linux distribution. Per-platform kernels: **3.10.x** (8 platforms), **4.4.x** (13) and **5.10.x** (7), spanning Intel, AMD EPYC/Ryzen and ARM (Annapurna Alpine, Marvell Armada, Realtek RTD1296/1619B) [C-TD-tier-c-nas-035]. |
| **Update / rollback** | Signed-in update channel with region-staged rollout and auto-update. "Important" updates can be postponed for up to 28 days [C-TD-tier-c-nas-034]. **No downgrade after any 7.x update** [C-TD-tier-c-nas-032]. The update file format and signing are not public (UNVERIFIED). |
| **Lifecycle** | Status labels: Full → Limited (security only) → EOL [C-TD-tier-c-nas-041]. DSM 6.2 (2018) got updates until 2024-10-01 [C-TD-tier-c-nas-041]. DSM 7.4 is the **last** version for many 2016–2019 models, and some of them are held back even from 7.4 [C-TD-tier-c-nas-033]. 7.2.2 and 7.3.2 still get security updates in Oct 2026 [C-TD-tier-c-nas-031]. |
| **App format** | `.spk` packages. Since DSM 7.0, **no code signing and no user keyring**. Third-party packages only trigger a warning. Packages must run as their own **non-root user**, and privileged actions go through "resource workers" [C-TD-tier-c-nas-036]. Container Manager runs Docker Compose "Projects". Its package still tracks Docker **24.0.2**, and it gained NVIDIA GPU access in 2026 [C-TD-tier-c-nas-040]. |
| **Identity** | Local users and groups, AD/LDAP, SSO server/client (SAML, CAS), 2FA with recovery codes [C-TD-tier-c-nas-031, C-TD-tier-c-nas-034]. |
| **AI features** | **AI Console** (DSM 7.2+): per-package and per-user/group enablement, cloud providers or any OpenAI-compatible endpoint, local LLMs from 1.2.0, de-identification (regex + local NER models, with no guarantee of full masking), and full request logs with token counts [C-TD-tier-c-nas-037, C-TD-tier-c-nas-039]. GPU-only search models (embedding, OCR, speech-to-text, captioning) need a GPU-equipped Synology [C-TD-tier-c-nas-037]. **DSM Agent** (7.4) is a natural-language admin assistant [C-TD-tier-c-nas-039]. Vendor claims 430,000+ AI Console deployments [C-TD-tier-c-nas-038]. No MCP server was found on the pages read. |
| **Backups** | Strong first-party suite (Hyper Backup, Snapshot Replication, Active Backup; named in the 7.3/7.4 notes) [C-TD-tier-c-nas-031]. |
| **Security** | Non-root packages [C-TD-tier-c-nas-036]. KEV/EPSS/LEV risk indicators; "50+ proactive security updates" in 12 months (vendor claim) [C-TD-tier-c-nas-038]. Weak points: end-of-life kernels [C-TD-tier-c-nas-035] and unsigned third-party packages [C-TD-tier-c-nas-036]. |
| **Hardware** | Synology's own boxes only (the GPL index lists 28 platforms) [C-TD-tier-c-nas-035]. 2025 models accept third-party HDDs/SATA SSDs. M.2 pools still need listed drives [C-TD-tier-c-nas-038]. |
| **License** | Proprietary, with a GPL source offer published per DSM version [C-TD-tier-c-nas-035]. |
| **Business model** | Hardware margin plus paid first-party apps, licences and drives (the drive programme in [C-TD-tier-c-nas-038]). Company revenue and headcount: UNVERIFIED. |

## 2. Failure signals

| Signal | Lesson for OneMind |
|---|---|
| Third-party drive restriction reversed in DSM 7.3 after backlash [C-TD-tier-c-nas-038] | Don't lock components to sell your own. "Works with OneMind" should be a recommendation, never a block (H-2). |
| Server-side HEVC/AVC transcoding removed, and mail and PHP packages dropped in point releases [C-TD-tier-c-nas-042] | Removing a feature breaks trust. OneMind publishes a deprecation window and a migration for every removal. |
| Old models frozen on DSM 7.4 or earlier [C-TD-tier-c-nas-033] | Publish the support end date per SKU at sale (01, REC-DEC-12 caps it by the board's kernel window). |
| Kernels 3.10 and 4.4 still shipping [C-TD-tier-c-nas-035] | Track upstream LTS. Never freeze a board on its launch kernel (REC-DEC-12). |

## 3. What competitors do (constraint-fit)

| Product | Kernel policy | Downgrade | App signing | AI governance | Constraints | Constraint fit with OneMind |
|---|---|---|---|---|---|---|
| **Synology DSM 7.4** | Launch kernel kept per platform (3.10/4.4/5.10) [C-TD-tier-c-nas-035] | Never [C-TD-tier-c-nas-032] | Removed in DSM 7 [C-TD-tier-c-nas-036] | Per-app/user enablement, masking, audit log [C-TD-tier-c-nas-037] | Large vendor; own hardware; closed; no robotics | **Low** for OS/updates; **Default** for AI governance UX |
| TrueNAS CE | Own LTS fork (6.12 → 6.18) | Boot environments | Checksums only | Separate MCP preview | Funded; x86 | Candidate (storage) |
| umbrelOS | Debian backports | A/B (Rugix) | Beta signing chain | MCP server | Small team; x86 + Pi | High (home tier) |
| **OneMind (01)** | Board maintainer's LTS kernel, CI contract | A/B + health gate | Signed bundles and apps | Gateway approvals + AI-data flags | Solo; Pi → GPU; robotics | — |

## 4. What OneMind copies and what it does better

| # | Pattern | Copy or improve | Requirement IDs |
|---|---|---|---|
| REQ-SY-1 | **AI Console:** enable AI per app and per user/group; bring-your-own provider; de-identify before sending; log every request with tokens [C-TD-tier-c-nas-037] | Copy as the OneMind AI gateway policy. It implements the per-integration "may this data go to AI" flag (W9) | AI-1, AI-3, AI-4, AI-5 |
| REQ-SY-2 | **Non-root packages with brokered privileges** [C-TD-tier-c-nas-036] | Copy (Kubernetes Pod Security plus declared capabilities in `onemind.app.yaml`) | A-5, M-2 |
| REQ-SY-3 | **Postpone "important" updates up to N days** [C-TD-tier-c-nas-034] | Copy, with the CRA default for security updates decided by the founder (REC-DEC-14) | R-1, M-8 |
| REQ-SY-4 | **Status labels Full / Limited / EOL** per product [C-TD-tier-c-nas-041] | Copy as a public per-SKU support page with dates | M-8, H-1 |
| REQ-SY-5 | **Two-box HA pair** [C-W11-057] | Candidate for the Pro/Cluster tier (12, mirroring) | UX-6, F-14 |
| REQ-SY-6 | **Package signing** | **Do better:** keep signing mandatory for apps and extensions, where Synology removed it [C-TD-tier-c-nas-036] | A-6, R-3, M-2 |
| REQ-SY-7 | **Rollback** | **Do better:** A/B rollback for every update, not "can't downgrade" [C-TD-tier-c-nas-032] | R-1, P-7 |
| REQ-SY-8 | **Current kernels** | **Do better:** a supported LTS kernel per board, refreshed by rebase (REC-DEC-16) [C-TD-tier-c-nas-035] | F-7, R-3, M-8 |
| REQ-SY-9 | **Open hardware policy** | **Do better:** no drive or part lock-in [C-TD-tier-c-nas-038] | H-2, D-001 |

**Effect on Tier A decisions:** none flip. DSM shows the cost of freezing kernels and dropping signing. That backs REC-DEC-12 and the signed-everything policy. Its AI Console is the most mature AI-governance UX among the NAS vendors reviewed.

## Glossary

| Term | Meaning |
|---|---|
| **DSM** | DiskStation Manager, Synology's operating system. |
| **`.spk`** | Synology's package file format for apps. |
| **Package Center** | DSM's app store. |
| **De-identification** | Removing or masking personal data (names, card numbers) before text goes to an AI service. |
| **NER** | Named-entity recognition: a model that spots names, places and similar data in text. |
| **GPL source offer** | The legal duty to publish the source of GPL code (like the Linux kernel) that a product ships. |
| **LTS kernel** | A Linux kernel version that kernel.org patches for several years. |
