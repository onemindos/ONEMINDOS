# research-output/

**Everything the research run produced is here.** Zeus reviews it through the pull request. Brief: [../RESEARCH-MISSION.md](../RESEARCH-MISSION.md) (§6 lists the expected files). **Index updated:** 2026-11-11 (final for this run).

**Start here:** the PR → [`REVIEW-CHECKLIST.md`](REVIEW-CHECKLIST.md) → [`ONEMIND-OS-FOUNDATION-REPORT.pdf`](ONEMIND-OS-FOUNDATION-REPORT.pdf) → [`00`](00-EXECUTIVE-SUMMARY.md) → [`01`](01-FOUNDATION-DECISION.md) → [`26`](26-OPEN-QUESTIONS-FOR-ZEUS.md) → [`20`](20-PLAN-180-DAYS.md) → [`21`](21-ROADMAP-5-10-YEARS.md) → [`30`](30-NEXT-ULTRACODE-BUILD-BRIEF.md)

Rules: cite primary sources, label UNVERIFIED, no secrets or personal data (public repo), and map everything to the requirement IDs in `docs/REQUIREMENTS.md`.

## Top-level deliverables

| File | What it is | Workstream |
|---|---|---|
| [`00-EXECUTIVE-SUMMARY.md`](00-EXECUTIVE-SUMMARY.md) | The answer, top 10 findings and risks, decisions, status per workstream, VM lab, and what remains | all |
| [`01-FOUNDATION-DECISION.md`](01-FOUNDATION-DECISION.md) | The final foundation decision (rev. 3): scorecards, adversarial tables, steelmen, ADR-001 verdict | DEC |
| [`02-competitors/`](02-competitors/) | 29 teardowns + `MATRIX.md` (below) | W1 |
| [`03-base-os.md`](03-base-os.md) | Base OS comparison, including Fedora IoT/bootc | W2 |
| [`04-image-install-updates-rollback.md`](04-image-install-updates-rollback.md) | Image build, install paths, A/B updates, rollback | W3 |
| [`05-kubernetes-cluster-conversion-nvidia.md`](05-kubernetes-cluster-conversion-nvidia.md) | k3s vs alternatives, DOKS conversion, NVIDIA | W4 |
| [`06-backups-recovery.md`](06-backups-recovery.md) | Backups, restore, k3s datastore | W5 |
| [`07-security-compliance.md`](07-security-compliance.md) | Threat model, Secure Boot/TPM, CRA and other law | W6 |
| [`08-robotics-drones-physical-ai.md`](08-robotics-drones-physical-ai.md) | Robotics, drones, physical AI, Jetson lifecycle | W7 |
| [`09-iot-mesh-offgrid-tak.md`](09-iot-mesh-offgrid-tak.md) | IoT/IIoT, mesh, off-grid, TAK, VillageOS fit | W8 |
| [`10-ai-capability-layer.md`](10-ai-capability-layer.md) | MCP, approvals, local inference, biometrics | W9 |
| [`11-hardware-line.md`](11-hardware-line.md) | Boxes, BOMs, capability detection, founder hardware | W10 |
| [`12-dashboard-clients-xr.md`](12-dashboard-clients-xr.md) | Dashboard, clients, alerts, XR | W11 |
| [`13-apps-market-plugins.md`](13-apps-market-plugins.md) | Market, seed apps, internal apps | W12 |
| [`14-family-education-community-website.md`](14-family-education-community-website.md) | Family, children's devices, education, website | W13 |
| [`15-phones-field-devices.md`](15-phones-field-devices.md) | GrapheneOS/ATAK, phones, field devices | W14 |
| [`16-world-context-scenarios.md`](16-world-context-scenarios.md) | 2030–2036 scenarios and triggers | W15 |
| [`17-business-licensing-gtm.md`](17-business-licensing-gtm.md) | Open core, pricing, segments, partners | W16 |
| [`20-PLAN-180-DAYS.md`](20-PLAN-180-DAYS.md) | 26-week plan, gates G1–G7, test schedule, days 1–10 | PLAN180 |
| [`21-ROADMAP-5-10-YEARS.md`](21-ROADMAP-5-10-YEARS.md) | Year 1 to years 5–10, exit criteria | ROADMAP |
| [`22-HARDWARE-LAB-TEST-PLAN.md`](22-HARDWARE-LAB-TEST-PLAN.md) | Founder-runnable hardware and live-cluster tests | LABPLAN |
| [`23-RISK-REGISTER.md`](23-RISK-REGISTER.md) | 62 risks with owners and triggers | RISK |
| [`24-QUESTION-BANK-ANSWERS.md`](24-QUESTION-BANK-ANSWERS.md) | Status and answer for all 335 questions, plus 34 added | QBANK |
| [`25-TRACEABILITY.md`](25-TRACEABILITY.md) | All 97 requirement IDs → recommendation → file | TRACE |
| [`26-OPEN-QUESTIONS-FOR-ZEUS.md`](26-OPEN-QUESTIONS-FOR-ZEUS.md) | Founder decisions Z-01…Z-37, requirements and Blueprint questions, access needs | DEC, FINAL |
| [`27-LEARNING-PATH.md`](27-LEARNING-PATH.md) | Curriculum for Zeus | W17 |
| [`28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md`](28-KERNEL-IMAGE-OWNERSHIP-AND-DEV-TOOLCHAIN.md) | Kernel families, kernel/image ownership, Mac toolchain, CI/CD | W18 |
| [`29-PLATFORM-ECOSYSTEM-MARKETPLACE.md`](29-PLATFORM-ECOSYSTEM-MARKETPLACE.md) | Plugin types, extension points, SDK, Marketplace | W19 |
| [`30-NEXT-ULTRACODE-BUILD-BRIEF.md`](30-NEXT-ULTRACODE-BUILD-BRIEF.md) | One-shot brief for the build session (F-9) | BRIEF30 |
| [`ONEMIND-OS-FOUNDATION-REPORT.pdf`](ONEMIND-OS-FOUNDATION-REPORT.pdf) | The standalone founder report (F-10), 101 pages | REPORT |
| [`report/`](report/) | PDF source: `chapters/` (15 chapters + 2 generated appendices), `diagrams/`, `charts/`, `img/`, `main.typ`, `build.sh`, `verify_pdf.py`, `checklist.tsv`, `README.md` | REPORT |
| [`REVIEW-CHECKLIST.md`](REVIEW-CHECKLIST.md) | Reading order and approval boxes | FINAL |
| [`SOURCES.md`](SOURCES.md) | Bibliography compiled from every `evidence/sources/*.md` | TRACE |
| `README.md` | This index | FINAL |

## `02-competitors/` (W1)

| Tier | Files |
|---|---|
| Summary | [`MATRIX.md`](02-competitors/MATRIX.md) |
| A | [`home-assistant-os.md`](02-competitors/home-assistant-os.md), [`umbrelos.md`](02-competitors/umbrelos.md), [`olares.md`](02-competitors/olares.md), [`villageos.md`](02-competitors/villageos.md), [`flagged-repos.md`](02-competitors/flagged-repos.md) (RS-5) |
| B | [`balenaos.md`](02-competitors/balenaos.md), [`startos.md`](02-competitors/startos.md), [`kairos.md`](02-competitors/kairos.md), [`talos.md`](02-competitors/talos.md), [`truenas-scale.md`](02-competitors/truenas-scale.md), [`casaos-zimaos.md`](02-competitors/casaos-zimaos.md), [`proxmox-ve.md`](02-competitors/proxmox-ve.md), [`project-nomad.md`](02-competitors/project-nomad.md) |
| C | [`unraid.md`](02-competitors/unraid.md), [`hexos.md`](02-competitors/hexos.md), [`synology-dsm.md`](02-competitors/synology-dsm.md), [`cosmos.md`](02-competitors/cosmos.md), [`yunohost.md`](02-competitors/yunohost.md), [`runtipi.md`](02-competitors/runtipi.md), [`cloudron.md`](02-competitors/cloudron.md), [`puter.md`](02-competitors/puter.md), [`sandstorm.md`](02-competitors/sandstorm.md), [`freedombox.md`](02-competitors/freedombox.md), [`coolify-dokploy.md`](02-competitors/coolify-dokploy.md), [`ai-boxes-clawbox.md`](02-competitors/ai-boxes-clawbox.md), [`robotics-formant.md`](02-competitors/robotics-formant.md), [`robotics-foxglove.md`](02-competitors/robotics-foxglove.md), [`robotics-viam.md`](02-competitors/robotics-viam.md), [`robotics-balena.md`](02-competitors/robotics-balena.md) |

## `evidence/`

| Path | What it is |
|---|---|
| [`evidence/claims/`](evidence/claims/) | **Per-tag claim ledgers** (92 CSV files, 2,704 rows); the IDs cited everywhere resolve here |
| [`evidence/claims.csv`](evidence/claims.csv) | The brief's master ledger; **not yet re-merged** (2,039 of 2,704 rows; see `00` §7) |
| [`evidence/license-matrix.csv`](evidence/license-matrix.csv), [`license-matrix.md`](evidence/license-matrix.md) | Licence matrix (231 rows) and its reading |
| [`evidence/scorecard-weights.md`](evidence/scorecard-weights.md) | Frozen scorecard weights and change log |
| [`evidence/scorecard-rev3.md`](evidence/scorecard-rev3.md) | The fully cited scorecard (rev. 3) |
| [`evidence/decision-critical.md`](evidence/decision-critical.md) | The 24 decision-critical questions, with Result blocks |
| [`evidence/lifecycle-cost-2036.md`](evidence/lifecycle-cost-2036.md) | Cost to 2036 per base (DC-03) |
| [`evidence/outreach-drafts.md`](evidence/outreach-drafts.md), [`outreach-drafts-W16.md`](evidence/outreach-drafts-W16.md) | Vendor outreach drafts (not sent) |
| [`evidence/hygiene-log.md`](evidence/hygiene-log.md) | Secret, IP and personal-data scans; reviewed false positives; the history leak (Z-28) |
| [`evidence/adversarial/`](evidence/adversarial/) | 122 refuter and steelman reports |
| [`evidence/qbank/`](evidence/qbank/) | Per-workstream question statuses (19 files) |
| [`evidence/critic/`](evidence/critic/) | Completeness critics: `tier-a-pass-1.md`, `pass-2.md`, `ledger-audit.md` |
| [`evidence/sources/`](evidence/sources/) | Per-tag source lists (61 `.md` files) and saved page text with sha256 (55 folders) |
| [`evidence/lab/`](evidence/lab/) | VM lab spikes, each with README, criteria, scripts and logs: `debian-rugix`, `rauc`, `rauc-k3s-gate`, `secureboot-rauc`, `rauc-1152`, `ubuntu-2604-leg`, `mender`, `minimal-image-dc20`, `fedora-bootc`, `w2-fedora-bootc-greenboot`, `k3s-footprint-restore`, `w4-k3s-footprint`, `w5-restore`, `w8-nats-leaf-buffer`, `w18-mac-toolchain`, `w19-sysext`; index in [`PREREGISTRATION.md`](evidence/lab/PREREGISTRATION.md) |
