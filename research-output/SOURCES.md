# SOURCES · Bibliography of the OneMind OS research run

**Compiled:** 2026-11-11 · **Owner:** TRACE · **Compiled from:** every `evidence/sources/*.md` list (70 files), joined with the per-tag claim ledgers in `evidence/claims/*.csv` (2986 claim rows) · **Companion:** [`25-TRACEABILITY.md`](25-TRACEABILITY.md)

> ### Explain it like I'm the founder
> Every fact in this research points to a **claim ID** (like `C-W3-017`), and every claim points to a **source** that someone actually opened. This file is the phone book of those sources: where each one lives, when it was read, what kind of source it is, and how we kept a copy so the fact can be checked later even if the web page changes.
>
> Web pages change and disappear. The brief says a page that a decision rests on (a *load-bearing* source) must be preserved in one of two ways: a snapshot in the Internet Archive's **Wayback Machine**, or a **saved text copy plus its fingerprint (sha256 hash)** inside this repo. Code is different: a link pinned to a git **commit SHA** can never change, so it is its own archive.
>
> **The short answer:** 1567 source entries are listed. Most are preserved: 749 have a saved copy in the repo, 124 have a Wayback capture, and 415 are code pinned to a commit. The **ARCHIVE-GAP** section at the end lists the **110** web sources that support a verified or partly verified claim but have neither a Wayback capture nor a saved copy. 28 of them back claims used in the decision documents (00, 01, 03–07, 28); those should be re-captured or replaced first. This compilation did not check whether any of them is the *only* support for a decision; that check belongs to the next ledger pass. Saving new Wayback snapshots was refused by this environment's permission policy throughout the run, so the gaps can only be closed by saving text copies or by Zeus requesting captures.

## Glossary

| Term | Meaning |
|---|---|
| **Claim ID** | `C-<TAG>-###`: one row in `evidence/claims/<TAG>.csv` holding one checkable fact, its source, version and re-check date. |
| **TAG** | The workstream or agent that opened the source (W2…W19, TD-* teardowns, LAB-* lab spikes, REF-* refuters, STEEL-* steelmen, DEC, LIC, SCORE, COST and others). |
| **PRIMARY** | Official docs, release notes, standards, legal text, or source code at a pinned commit. |
| **PRIMARY-METADATA** | An official catalogue page, abstract or API record (used for paywalled standards and repository metadata). |
| **SECONDARY** | Press, blogs, law-firm notes, forums. Allowed only where labelled. |
| **UNVERIFIED** | Opened but blocked (bot wall, 403) or not confirmable; never used as sole support for a verified claim. |
| **Wayback capture** | An existing snapshot on web.archive.org. This run could only *look up* existing captures; it could not create new ones. |
| **Saved copy** | The page text saved under `evidence/sources/<TAG>/` (or `<TAG>-archive/`) with its sha256 in a `SHA256SUMS`/`INDEX` file. Emails and token-shaped strings were masked before hashing. |
| **Commit pin** | A code link fixed to a 40-character git SHA. It cannot change, so it needs no other archive. |
| **Load-bearing** | Here: a source that supports at least one claim whose ledger status is `verified` or `partial`. |
| **ARCHIVE-GAP** | A load-bearing web source with neither a Wayback capture nor a saved copy in the repo. |

## How this file was compiled (reproducible)

1. Every table row in `evidence/sources/*.md` was parsed. The source is the row's first URL, or `owner/repo@sha` for code, or the first cell.
2. Claims are the `C-…` IDs in the row plus shorthand in a "Claims"/"Supports" column (for example `001–004, 013` in `W3.md` means `C-W3-001…004, C-W3-013`). Only IDs that exist in a ledger are kept. Where a web row named no claim, claims were matched from the ledger's `source_url`.
3. **Archive class**, in priority order: *Wayback* (a `web.archive.org` link or a capture timestamp in the row) · *saved* (a saved file is named, or the row's hash, full or 16-hex prefix, appears in a `SHA256SUMS`/`INDEX`/`HASHES` file in the repo, or a file named after the page or issue exists in the tag's folder) · *commit pin* · *version-tag URL* · *API response* · *hash only* (a hash is recorded but the copy is not in the repo) · *none*.
4. Rows repeated within one tag file were merged. The same URL opened by two tags appears under both, because each tag's ledger cites it separately.
5. **Limits:** source-list formats differ by agent, so classification is heuristic. Spot checks were done on TD-umbrelos, TD-olares, TD-villageos, TD-tier-c-nas, TD-truenas-scale, TD-balenaos and W2/W4/W6/W7/W8/W11/W17/W18. Claim IDs cited only in a ledger's `source_url` without a row in any `sources/*.md` are **not** listed here (see the last section).

## Totals

| Archive class | Entries |
|---|---|
| saved | 749 |
| wayback | 124 |
| sha-pin | 415 |
| tag-pin | 2 |
| api | 14 |
| hash-only | 19 |
| none | 244 |
| **All** | **1567** |

| Source type (as labelled in the row) | Entries |
|---|---|
| PRIMARY | 1159 |
| not stated in row (see tag file) | 232 |
| PRIMARY-METADATA | 79 |
| SECONDARY | 79 |
| UNVERIFIED | 18 |

Claim IDs reached through these entries: **1596** of 2986 ledger rows.

## Bibliography by tag

Columns: **Source** (URL or `repo@sha`) · **Accessed** · **Type** · **Archive** (Wayback link, saved copy and hash prefix, or commit pin) · **Claims supported**. The full row, with notes, is in the linked tag file.

### ARCH5

Tag file: [`evidence/sources/ARCH5.md`](evidence/sources/ARCH5.md) · 6 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://bugs.launchpad.net/ubuntu/+source/linux-raspi/+bug/2170238 | 2026-10-08 | — | — | C-DEC-006 |
| 2 | https://www.raspberrypi.com/news/price-rises-for-some-16gb-raspberry-pi-products/ | 2026-10-08 | — | saved: `ARCH5/rpi-news-price-rises-16gb.txt` · sha256 `dee070ed23ef6215…` | C-ARCH5-002; C-CIT4-008 |
| 3 | https://bodhi.fedoraproject.org/releases/F45 | 2026-10-08 | — | saved: `ARCH5/bodhi-release-F45.json.txt` · sha256 `f0444844a5083228…` | C-ARCH5-001; C-W2-015 |
| 4 | https://canonical.com/legal/intellectual-property-policy | 2026-10-08 | — | saved: `LIC/05-canonical-iprights-policy.txt` · sha256 `0c9214f3adc1138a…` | C-LIC-011; C-W2-050 |
| 5 | https://github.com/home-assistant/operating-system/pull/4757 | 2026-10-08 | PRIMARY | saved: `ARCH5/haos-operating-system-pr-4757.json.txt` · sha256 `4d82b7c5bb6a9ffc…` | C-ARCH5-004; C-W3-024 |
| 6 | https://genai.owasp.org/llmrisk/llm01-prompt-injection/ | 2026-10-08 | — | saved: `ARCH5/owasp-llm01-2025-prompt-injection.txt` · sha256 `1b45fccdcc78401b…` | C-ARCH5-003; C-W6-068 |

### BRIEF30

Tag file: [`evidence/sources/BRIEF30.md`](evidence/sources/BRIEF30.md) · 3 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | kanidm/kanidm@a52b723ce8efb1f4d0a6bc2a2c36b4071f95317d | 2026-11-11 | PRIMARY | commit pin `a52b723ce8ef` | C-BRIEF30-001 |
| 2 | systemd/systemd@70b5d110be7702afc4dbce012f60d49506d513da | 2026-11-11 | PRIMARY | commit pin `70b5d110be77` | C-BRIEF30-002 |
| 3 | GitHub releases/latest API for cosign, sigstore-go, Lima, Kanidm, gitleaks, RAUC, k3s, nats-server, restic, Helm, Traefik; tag → commit by g | 2026-11-11 | PRIMARY-METADATA | saved: `BRIEF30/github-releases-latest-2026-11-11.txt` | C-BRIEF30-003…007 |

### CIT4

Tag file: [`evidence/sources/CIT4.md`](evidence/sources/CIT4.md) · 23 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | IronFlock/ironflockos@bb33a82dfa959366bb90896fc69b601604131185 | 2026-11-11 | PRIMARY | saved: `CIT4/ironflockos-bb33a82d-README.md.txt` · sha256 `67e7b31855185ede…` | C-CIT4-001, 002 |
| 2 | GitHub API: repos/IronFlock/ironflockos, /releases, /contributors, tag refs | 2026-11-11 | PRIMARY-METADATA | — | C-CIT4-002 |
| 3 | https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html | 2026-11-11 | PRIMARY | saved: `CIT4/nvidia-cuda-13.5-install-guide-linux.txt` · sha256 `35c39830dd3903f3…` | C-CIT4-003 |
| 4 | https://antonio.paolillo.be/publications/workshops/ecrtsOspert2024_dewit_rtlinux_paper.pdf | 2026-11-11 | PRIMARY | saved: `antonio.paolillo.be/publications/workshops/ecrtsOspert2024_dewit_rtlinux_paper.pdf` | C-CIT4-004 |
| 5 | https://www.osadl.org/…qa-profile-r2s7… | 2026-11-11 | PRIMARY | saved: `CIT4/osadl-qafarm-r2s7-pi5-profile.txt` · sha256 `9b554eeb4fffcab6…` | C-CIT4-005 |
| 6 | https://docs.nvidia.com/jetson/archives/r36.4.3/DeveloperGuide/SD/Kernel/KernelCustomization.html | 2026-11-11 | PRIMARY | saved: `CIT4/nvidia-jetson-linux-r36.4.3-kernel-customization.txt` · sha256 `3985b8e32c92030f…` | C-CIT4-006 |
| 7 | https://www.wimcorp.co.kr/tech/en/posts/embedded/preempt-rt-jetson-orin/ | 2026-11-11 | SECONDARY | saved: `CIT4/wimcorp-preempt-rt-jetson-orin.txt` · sha256 `72bc8477aa4acd46…` | C-CIT4-007 |
| 8 | https://www.raspberrypi.com/news/price-rises-for-some-16gb-raspberry-pi-products/ | 2026-11-11 | PRIMARY | saved copy in `sources/CIT4/` | C-ARCH5-002; C-CIT4-008 |
| 9 | https://developer.nvidia.com/embedded/faq | 2026-11-11 | PRIMARY | saved: `CIT4/nvidia-jetson-faq-prices.txt` · sha256 `de6b9636eae765e0…` | C-CIT4-009 |
| 10 | https://digital-strategy.ec.europa.eu/en/policies/cra-conformity-assessment | 2026-11-11 | PRIMARY | saved: `CIT4/ec-digital-strategy-cra-conformity-assessment.txt` · sha256 `a803bd47fbc2d427…` | C-CIT4-010 |
| 11 | https://www.cencenelec.eu/news-events/events/2026/2026-06-18-cra-unlocked-deep-dive-technical-component-requirements-for-acs/ | 2026-11-11 | PRIMARY | saved: `CIT4/cencenelec-2026-06-18-cra-unlocked-62443-4-2-prAA.txt` · sha256 `c1034ff27f282ecc…` | C-CIT4-011 |
| 12 | https://www.boschrexroth.com/en/at/company/press/ctrlx-os-cra-30528.html | 2026-11-11 | PRIMARY | saved: `CIT4/boschrexroth-press-2025-03-18-ctrlx-os-cra.txt` · sha256 `f2fe8db38f7d6cca…` | C-CIT4-012 |
| 13 | GitHub advisories GHSA-vjh7-5r6x-xh6g, GHSA-m5q5-8mfw-p2hr (CasaOS), GHSA-vmg3-7v43-9g23 (NVIDIA Container Toolkit), via gh api /advisories/ | 2026-11-11 | PRIMARY | saved copy in `sources/CIT4/` · sha256 `a5422460343cc283…` | C-CIT4-013, 014 |
| 14 | http://archive.raspberrypi.com/debian/dists/trixie/main/binary-arm64/Packages.gz | 2026-11-11 | PRIMARY-METADATA | saved: `CIT4/rpi-os-trixie-arm64-kernel-metapackages.txt` · sha256 `c71c794444b05c4f…` | C-CIT4-015 |
| 15 | https://developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/Packages.gz | 2026-11-11 | PRIMARY-METADATA | saved: `CIT4/nvidia-cuda-repo-debian13-x86_64-driver-branches.txt` · sha256 `4be06140520acf8a…` | C-CIT4-016 |
| 16 | https://docs.nvidia.com/jetson/archives/r36.4.3/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | 2026-11-11 | PRIMARY | saved: `CIT4/nvidia-jetson-linux-r36.4.3-software-packages-update-mechanism.txt` · sha256 `67453dca894347ff…` | C-CIT4-017 |
| 17 | NANDO (webgate.ec.europa.eu/single-market-compliance-space, notified bodies by legislation) | 2026-11-11 | UNVERIFIED | — | C-STEEL-cra-nb-017 |
| 18 | apps.boschrexroth.com/microsites/ctrlx-automation/en/cra/ (C-STEEL-ubu-011's URL) | 2026-11-11 | — | — | C-STEEL-ubu-011 |
| 19 | nvidia.custhelp.com/app/answers/detail/a_id/5659 (CVE-2025-23266 bulletin) | 2026-11-11 | — | — | — |
| 20 | Raspberry Pi news and product pages by direct download | 2026-11-11 | — | — | — |
| 21 | OSADL QA Farm, Jetson | 2026-11-11 | — | — | — |
| 22 | NVIDIA Jetson Linux docs, latency figures | 2026-11-11 | — | — | — |
| 23 | Extended web search plus GitHub code search for a Debian/Ubuntu + RAUC product (C-DEC-013) | 2026-11-11 | — | — | C-DEC-013 |

### COST

Tag file: [`evidence/sources/COST.md`](evidence/sources/COST.md) · 14 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://ubuntu.com/pricing/pro | 2026-11-11 | PRIMARY | saved: `COST/ubuntu-pricing-pro.txt` | C-COST-001 |
| 2 | https://ubuntu.com/pricing/devices | 2026-11-11 | PRIMARY | saved: `COST/ubuntu-pricing-devices.txt` | C-COST-002 |
| 3 | https://ubuntu.com/pro/devices | 2026-11-11 | PRIMARY | saved: `COST/ubuntu-pro-devices.txt` | C-COST-003 |
| 4 | https://canonical.com/blog/ubuntu-20-04-end-standard-support-for-devices | 2026-11-11 | PRIMARY | saved: `COST/canonical-2004-devices.txt` | C-COST-004 |
| 5 | https://www.freexian.com/lts/debian/ | 2026-11-11 | PRIMARY | saved: `COST/freexian-lts-sponsorship.txt` | C-COST-005 |
| 6 | https://www.freexian.com/lts/extended/ | 2026-11-11 | PRIMARY | saved: `COST/freexian-elts.txt` | C-COST-006 |
| 7 | https://www.debian.org/releases/ | 2026-11-11 | PRIMARY | saved: `COST/debian-releases.txt` | C-COST-007 |
| 8 | https://wiki.yoctoproject.org/wiki/Releases | 2026-11-11 | PRIMARY | saved: `COST/yocto-releases.txt` | C-COST-008 |
| 9 | https://www.redhat.com/en/blog/red-hat-device-edge-decision-framework | 2026-11-11 | PRIMARY | saved: `COST/redhat-rhde-decision-framework.txt` | C-COST-009 |
| 10 | https://global.channelonline.com/arlingtoncp/tech/Products/overview/M024316101 | 2026-11-11 | SECONDARY | saved: `COST/reseller-rhde-3y-premium.txt` | C-COST-010 |
| 11 | https://www.cdw.com/product/red-hat-device-edge-standard-subscription-3-years-1-socket-up-to-32/7504915 | 2026-11-11 | SECONDARY | saved: `COST/reseller-rhde-3y-standard.txt` | C-COST-011 |
| 12 | https://www.bls.gov/ooh/computer-and-information-technology/software-developers.htm | 2026-11-11 | PRIMARY | saved copy in `sources/COST/` | C-COST-012 |
| 13 | https://www.dataguard.com/cyber-resilience-act/certification/ | 2026-11-11 | SECONDARY | — | C-COST-013 |
| 14 | Search-result absence (no Pro for Devices price found) | 2026-11-11 | UNVERIFIED | — | C-COST-014 |

### DEC

Tag file: [`evidence/sources/DEC.md`](evidence/sources/DEC.md) · 12 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | rauc/rauc@4fb7c798d6ae412344fb8f8d310d773046af3441 | 2026-11-10 | PRIMARY | commit pin `4fb7c798d6ae` | C-DEC-001, 003, 005, 011 |
| 2 | rauc/rauc@4fb7c798 | 2026-11-10 | PRIMARY | saved: `docs/integration.rst` · sha256 `4fd15cb14a71212f…` | C-DEC-002 |
| 3 | https://github.com/rauc/rauc/security/advisories/GHSA-6hj7-q844-m2hx | 2026-11-10 | PRIMARY | commit pin `4fb7c798` | C-DEC-004 |
| 4 | https://bugs.launchpad.net/ubuntu/+source/linux-raspi/+bug/2170238 | 2026-11-10 | PRIMARY | saved copy in `sources/DEC/` · sha256 `7b4319ba46df06f3…` | C-DEC-006 |
| 5 | https://www.truenas.com/docs/scale/24.10/gettingstarted/scalereleasenotes/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261015034155/https://www.truenas.com/docs/scale/24.10/gettingstarted/scalereleasenotes/ | C-DEC-007 |
| 6 | torvalds/linux@adc218676eef25575469234709c2d87185ca223a | 2026-11-10 | PRIMARY | saved: `sources/DEC/linux-v6.12-kernel-module-signing.c.txt` · sha256 `b6dac3fb2527b3a2…` | C-DEC-008 |
| 7 | same commit: security/integrity/platform_certs/load_uefi.c (L156–L191) | 2026-11-10 | PRIMARY | saved: `sources/DEC/linux-v6.12-security-integrity-platform_certs-load_uefi.c.txt` · sha256 `a3ceaf8ad33201a5…` | C-DEC-009 |
| 8 | same commit: security/integrity/Kconfig (L55–L75) | 2026-11-10 | PRIMARY | saved: `sources/DEC/linux-v6.12-security-integrity-Kconfig.txt` · sha256 `53c2a292cfdab6e3…` | C-DEC-009, 010 |
| 9 | https://rauc.io/ | 2026-11-10 | PRIMARY | saved: `sources/DEC/rauc-io-home-2026-11-11.txt` · sha256 `21e00910f606f091…` | C-DEC-012 |
| 10 | N9 precedent search, 2026-11-11: three extended web searches ("Debian-based appliance product uses RAUC A/B update production"; RAUC users l | 2026-11-10 | — | — | C-DEC-013 |
| 11 | https://www.sonarsource.com/blog/security-vulnerabilities-in-casaos/ | 2026-11-10 | SECONDARY | saved: `sources/DEC/sonarsource-casaos-cve-2023-37265-2026-11-11.txt` · sha256 `dc02ed815b6672f3…` | C-DEC-014 |
| 12 | https://kubernetes.io/docs/concepts/security/pod-security-standards/ | 2026-11-10 | PRIMARY | saved: `sources/DEC/kubernetes-pod-security-standards-2026-11-11.txt` · sha256 `f152f25273712a2b…` | C-DEC-015 |

### FIX4

Tag file: [`evidence/sources/FIX4.md`](evidence/sources/FIX4.md) · 11 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | canonical/ubuntu.com@ec15716b1c4b95f1860672d4274dda730ee9b4fe | 2026-11-11 | PRIMARY | commit pin `ec15716b1c4b` | C-FIX4-001, 002 |
| 2 | canonical/ubuntu.com@ec15716 | 2026-11-11 | PRIMARY | saved: `01-ubuntu.com-pro-devices.txt` | C-FIX4-003…005 |
| 3 | https://forums.raspberrypi.com/viewtopic.php?t=398535 | 2026-11-11 | SECONDARY | saved: `04-forums-raspberrypi-t398535-extract.txt` | C-FIX4-006 |
| 4 | https://github.com/raspberrypi/rpi-eeprom/issues/776 | 2026-11-11 | PRIMARY | API response (values quoted in the claim) | C-FIX4-007 |
| 5 | https://github.com/uutils/coreutils/issues/15768 | 2026-11-11 | PRIMARY | API response (values quoted in the claim) | C-FIX4-008 |
| 6 | https://github.com/uutils/coreutils/issues/15254 | 2026-11-11 | SECONDARY | API response (values quoted in the claim) | C-FIX4-009 |
| 7 | This repo, evidence/lab/ubuntu-2604-leg/versions.md L20–L23 and ubuntu-observations-u2.txt L17–L23 @ 7836316 | 2026-11-11 | PRIMARY | saved: `ubuntu-observations-u2.txt` | C-FIX4-010, 011 |
| 8 | https://computingforgeeks.com/ubuntu-2604-dracut-guide/ | 2026-11-11 | SECONDARY | saved: `06-computingforgeeks-ubuntu-2604-dracut-extract.txt` | C-FIX4-012 |
| 9 | https://lwn.net/Articles/586446/ | 2026-11-11 | SECONDARY | saved: `05-lwn-586446-extract.txt` | C-FIX4-013 |
| 10 | This repo, evidence/scorecard-weights.md L106 and L159 @ 7836316 | 2026-11-11 | PRIMARY | saved: `evidence/scorecard-weights.md` | C-FIX4-014 |
| 11 | torvalds/linux@028ef9c96e96197026887c0f092424679298aae8 | 2026-11-11 | PRIMARY | commit pin `028ef9c96e96` | C-FIX4-015 |

### FIX5

Tag file: [`evidence/sources/FIX5.md`](evidence/sources/FIX5.md) · 4 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | evidence/lab/ubuntu-secureboot/logs/env-probe.log (DNS probe on the host and in the Debian 13 Lima VM; host paths masked) | 2026-11-11 | PRIMARY | — | C-FIX5-001 |
| 2 | evidence/lab/ubuntu-secureboot/README.md + PREREGISTRATION.sha256 + ../PREREGISTRATION.md row | 2026-11-11 | PRIMARY | saved: `../PREREGISTRATION.md` | C-FIX5-002 |
| 3 | evidence/lab/ubuntu-secureboot/scripts/ compared with evidence/lab/secureboot-1152/scripts/ (cmp, diff) | 2026-11-11 | PRIMARY | — | C-FIX5-003 |
| 4 | evidence/sources/FIX4.md, "Access note" | 2026-11-11 | PRIMARY | saved: `evidence/sources/FIX4.md` | C-FIX5-004 |

### FIX7

Tag file: [`evidence/sources/FIX7.md`](evidence/sources/FIX7.md) · 6 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://isasecure.org/hubfs/EUTC-RCOR4411-CSA-E01.pdf | 2026-11-11 | PRIMARY | saved: `FIX7/isasecure-EUTC-RCOR4411-CSA-E01.txt` | C-FIX7-001 |
| 2 | FIX7/ubuntu.com-real-time-index@ec15716 | 2026-11-11 | PRIMARY | saved: `ec15716.txt` | C-FIX7-002 |
| 3 | https://repology.org/project/linux-raspi-realtime/versions | 2026-11-11 | SECONDARY | saved: `FIX7/repology-linux-raspi-realtime.txt` | C-FIX7-003 |
| 4 | https://repology.org/project/{open62541,mosquitto,libmodbus,can-utils}/versions | 2026-11-11 | SECONDARY | — | C-FIX7-004 |
| 5 | https://repology.org/project/rauc-hawkbit-updater/versions | 2026-11-11 | SECONDARY | saved: `FIX7/repology-rauc-hawkbit-updater.txt` | C-FIX7-005 |
| 6 | FIX7/rauc-hawkbit-updater-README@37b2ef4 | 2026-11-11 | PRIMARY | commit pin `37b2ef4` | C-FIX7-006 |

### FRAME

Tag file: [`evidence/sources/FRAME.md`](evidence/sources/FRAME.md) · 7 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | RESEARCH-MISSION.md (§2, §4, §6) | 2026-11-10 | — | — | — |
| 2 | context/05-research-questions.md (Q1–Q335) | 2026-11-10 | — | saved: `context/05-research-questions.md` | — |
| 3 | context/03-repo-findings-index.md (§1.1, §1.2, §1.4, §1.5, §3.1) | 2026-11-10 | — | saved: `context/03-repo-findings-index.md` | — |
| 4 | docs/ADR-001-foundation.md | 2026-11-10 | — | saved: `docs/ADR-001-foundation.md` | — |
| 5 | docs/REQUIREMENTS.md | 2026-11-10 | — | saved: `docs/REQUIREMENTS.md` | — |
| 6 | research/platform/fedora-iot-and-redhat-edge-deep-dive.md | 2026-11-10 | — | saved: `research/platform/fedora-iot-and-redhat-edge-deep-dive.md` | — |
| 7 | research/platform/iiot-landscape-and-requirements.md | 2026-11-10 | — | saved: `research/platform/iiot-landscape-and-requirements.md` | — |

### LAB-aarch64-gate

Tag file: [`evidence/sources/LAB-aarch64-gate.md`](evidence/sources/LAB-aarch64-gate.md) · 3 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/rauc/rauc | 2026-11-11 | PRIMARY | commit pin `f1ceebd68b4e` | C-LAB-aarch64-gate-001 |
| 2 | https://github.com/k3s-io/k3s/releases/download/v1.37.2%2Bk3s1/sha256sum-arm64.txt | 2026-11-11 | PRIMARY | saved: `k3s1-sha256sum-arm64.txt` | C-LAB-aarch64-gate-002 |
| 3 | raspberrypi/documentation@21d772e7ee022e36a8f43c3ee75e20ca359fb832 | 2026-11-11 | PRIMARY | commit pin `21d772e7ee02` | C-LAB-aarch64-gate-007 |

### LAB-debian-rugix

Tag file: [`evidence/sources/LAB-debian-rugix.md`](evidence/sources/LAB-debian-rugix.md) · 11 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/rugix/rugix | 2026-11-10 | PRIMARY | commit pin `6d7fc277919b` | — |
| 2 | https://github.com/rugix/rugix-bakery | 2026-11-10 | PRIMARY | commit pin `c43fdc11b88e` | — |
| 3 | https://github.com/rugix/rugix-docs | 2026-11-10 | PRIMARY | commit pin `227f902790fe` | — |
| 4 | https://rugix.org/docs/ctrl/updates/system-updates/boot-flows/ | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261111013709/https://rugix.org/docs/ctrl/updates/system-updates/boot-flows/ | — |
| 5 | https://rugix.org/docs/ctrl/updates/system-updates/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260807102425/https://rugix.org/docs/ctrl/updates/system-updates/ | — |
| 6 | https://github.com/rugix/rugix-testkit | 2026-11-10 | PRIMARY | commit pin `f78ae636418d` | — |
| 7 | https://update.k3s.io/v1-release/channels/stable | 2026-11-10 | PRIMARY-METADATA | — | — |
| 8 | https://github.com/k3s-io/k3s/releases/download/v1.37.2%2Bk3s1/ | 2026-11-10 | PRIMARY | saved: `versions.md` | — |
| 9 | https://deb.debian.org/debian/dists/trixie/Release | 2026-11-10 | PRIMARY | — | C-LAB-debian-rugix-015 |
| 10 | https://snapshot.debian.org/archive/debian/20261109T000000Z/ | 2026-11-10 | PRIMARY | — | — |
| 11 | https://cloud.debian.org/images/cloud/trixie/20261103-2651/debian-13-genericcloud-arm64-20261103-2651.qcow2 | 2026-11-10 | PRIMARY | — | — |

### LAB-fedora-bootc

Tag file: [`evidence/sources/LAB-fedora-bootc.md`](evidence/sources/LAB-fedora-bootc.md) · 14 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/fedora-iot/greenboot-rs @ v0.16.4 | 2026-11-10 | PRIMARY | commit pin `438eb9645f08` | C-LAB-fedora-bootc-003…005 |
| 2 | github.com/fedora-iot/greenboot-rs @ v0.16.5 (= main HEAD) | 2026-11-10 | PRIMARY | commit pin `6efc3c109b54` | C-LAB-fedora-bootc-003, 013 |
| 3 | github.com/bootc-dev/bootc tag v1.17.1 (the version in the image) | 2026-11-10 | PRIMARY-METADATA | commit pin `434e0e7e1b26` | C-LAB-fedora-bootc-002, 007 |
| 4 | https://github.com/fedora-iot/greenboot-rs/issues/219 | 2026-11-10 | PRIMARY | saved: `sources/LAB-fedora-bootc/greenboot-rs-issue-219.txt` · sha256 `4708f47aaa08b9d0…` | C-LAB-fedora-bootc-012 |
| 5 | https://github.com/fedora-iot/greenboot-rs/issues/218 | 2026-11-10 | PRIMARY | saved: `sources/LAB-fedora-bootc/greenboot-rs-issue-218.txt` · sha256 `f6b78dab322f760d…` | C-LAB-fedora-bootc-014 |
| 6 | https://github.com/fedora-iot/greenboot-rs/issues/217 | 2026-11-10 | PRIMARY | — | — |
| 7 | https://github.com/fedora-iot/greenboot-rs/releases | 2026-11-10 | PRIMARY-METADATA | Wayback: http://web.archive.org/web/20260601011011/https://github.com/fedora-iot/greenboot-rs | C-LAB-fedora-bootc-003 |
| 8 | https://github.com/bootc-dev/bootc/releases | 2026-11-10 | PRIMARY-METADATA | Wayback: http://web.archive.org/web/20261020214826/https://github.com/bootc-dev/bootc | C-LAB-fedora-bootc-002 |
| 9 | https://quay.io/repository/fedora/fedora-bootc | 2026-11-10 | PRIMARY-METADATA | — | C-LAB-fedora-bootc-001 |
| 10 | https://quay.io/repository/centos-bootc/bootc-image-builder | 2026-11-10 | PRIMARY-METADATA | — | C-LAB-fedora-bootc-016 |
| 11 | docker.io/library/registry:2 (lab registry only) | 2026-11-10 | PRIMARY-METADATA | hash only `a3d8aaa63ed8681a…` (copy not in repo) | — |
| 12 | Lima | 2026-11-10 | — | — | — |
| 13 | QEMU (Homebrew) | 2026-11-10 | — | — | — |
| 14 | Host | 2026-11-10 | — | — | — |

### LAB-k3s-footprint-restore

Tag file: [`evidence/sources/LAB-k3s-footprint-restore.md`](evidence/sources/LAB-k3s-footprint-restore.md) · 10 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://docs.k3s.io/datastore/backup-restore | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261111011629/https://docs.k3s.io/datastore/backup-restore | C-LAB-k3s-footprint-restore-003; C-W17-014; C-W3-064 |
| 2 | https://docs.k3s.io/cli/etcd-snapshot | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261111011648/https://docs.k3s.io/cli/etcd-snapshot | C-LAB-k3s-footprint-restore-004; C-W4-008 |
| 3 | https://docs.k3s.io/reference/resource-profiling | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261111011706/https://docs.k3s.io/reference/resource-profiling | C-LAB-k3s-footprint-restore-006 |
| 4 | https://docs.k3s.io/installation/requirements | 2026-11-10 | PRIMARY | saved: `installation_requirements.html` · sha256 `34a53f14763b3447…` | C-LAB-k3s-footprint-restore-005; C-REF-DC-technical-007; C-W8-049 |
| 5 | https://github.com/k3s-io/k3s/releases/tag/v1.37.2%2Bk3s1 | 2026-11-10 | PRIMARY-METADATA | saved: `k3s1-sha256sum-arm64.txt` · sha256 `b017cfc151c92e30…` | C-LAB-debian-rugix-014; C-LAB-k3s-footprint-restore-001; C-W4-011; C-W5-055 |
| 6 | https://raw.githubusercontent.com/k3s-io/k3s/v1.37.2%2Bk3s1/install.sh | 2026-11-10 | PRIMARY | hash only `ed01f89fd977bf20…` (copy not in repo) | — |
| 7 | https://github.com/restic/restic/releases/tag/v0.19.1 | 2026-11-10 | PRIMARY-METADATA | API response (values quoted in the claim) | C-LAB-k3s-footprint-restore-002; C-W5-025 |
| 8 | k3s-io/k3s@f6973cb850e9b245585363d15bde80904ac862fd | 2026-11-10 | PRIMARY | commit pin `f6973cb850e9` | — |
| 9 | Lab logs evidence/lab/k3s-footprint-restore/logs/ | 2026-11-10 | PRIMARY | — | — |
| 10 | context/03-repo-findings-index.md, research/platform/verify-updates-rollback-backups-security.md §1, §2, §6, §7 | 2026-11-10 | — | saved: `research/platform/verify-updates-rollback-backups-security.md` | — |

### LAB-mender

Tag file: [`evidence/sources/LAB-mender.md`](evidence/sources/LAB-mender.md) · 9 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/mendersoftware/mender/blob/0f4eb08e9d7114e5159de16656962fa2478cb580/support/modules/rootfs-image | 2026-11-11 | PRIMARY | commit pin `0f4eb08e9d71` | C-LAB-mender-001, 002 |
| 2 | https://github.com/mendersoftware/grub-mender-grubenv/blob/d7c3ec217e281727f56c3651799f805637cb2cda/04_mender_setup_env_functions_grub.cfg | 2026-11-11 | PRIMARY | commit pin `d7c3ec217e28` | C-LAB-mender-003, 004 |
| 3 | https://github.com/mendersoftware/mender-convert/blob/85e8c506cd59dc4a8e66ad07fbe28a3c33488c46/configs/mender_grub_config | 2026-11-11 | PRIMARY | commit pin `85e8c506cd59` | C-LAB-mender-005 |
| 4 | https://github.com/mendersoftware/mender/blob/0f4eb08e9d7114e5159de16656962fa2478cb580/src/mender-update/standalone/standalone.cpp#L551-L732 | 2026-11-11 | PRIMARY | commit pin `0f4eb08e9d71` | C-LAB-mender-006 |
| 5 | https://github.com/mendersoftware/mender/blob/0f4eb08e9d7114e5159de16656962fa2478cb580/src/artifact/v3/scripts/executor.cpp#L116-L139 | 2026-11-11 | PRIMARY | commit pin `0f4eb08e9d71` | C-LAB-mender-007 |
| 6 | https://github.com/mendersoftware/mender-docs/blob/960555bf503f97f7cbfbbb23f3deb5297002f8ee/08.Artifact-creation/04.State-scripts/docs.md | 2026-11-11 | PRIMARY | commit pin `960555bf503f` | C-LAB-mender-007 |
| 7 | https://github.com/mendersoftware/mender-docs/blob/960555bf503f97f7cbfbbb23f3deb5297002f8ee/08.Artifact-creation/08.Standalone-deployment/docs.md | 2026-11-11 | PRIMARY | commit pin `960555bf503f` | C-LAB-mender-006 |
| 8 | https://github.com/mendersoftware/mender/blob/0f4eb08e9d7114e5159de16656962fa2478cb580/LICENSE | 2026-11-11 | PRIMARY | commit pin `0f4eb08e9d71` | C-STEEL-updates-mender-001 |
| 9 | https://downloads.mender.io/repos/device-components/dists/debian/trixie/stable/Release | 2026-11-11 | PRIMARY-METADATA | — | C-LAB-mender-005 |

### LAB-minimal-image-dc20

Tag file: [`evidence/sources/LAB-minimal-image-dc20.md`](evidence/sources/LAB-minimal-image-dc20.md) · 6 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://buildroot.org/download.html | 2026-11-11 | PRIMARY | saved: `buildroot-download-page.txt` | C-LAB-minimal-image-dc20-001 |
| 2 | https://gitlab.com/buildroot.org/buildroot | 2026-11-11 | PRIMARY | commit pin `4f924fd52841` | C-LAB-minimal-image-dc20-002, 003 |
| 3 | https://www.kernel.org/releases.json | 2026-11-11 | PRIMARY-METADATA | saved: `kernel-org-releases.json` | C-LAB-minimal-image-dc20-004 |
| 4 | https://sources.debian.org/api/src/mkosi/ | 2026-11-11 | PRIMARY-METADATA | saved: `debian-sources-mkosi.json` | C-LAB-minimal-image-dc20-005 |
| 5 | https://update.k3s.io/v1-release/channels | 2026-11-11 | PRIMARY-METADATA | saved: `k3s-release.json` | C-LAB-minimal-image-dc20-006 |
| 6 | https://github.com/anchore/syft/releases/tag/v1.57.1 | 2026-11-11 | PRIMARY-METADATA | saved: `grype-release.json` | C-LAB-minimal-image-dc20-007 |

### LAB-rauc-1152

Tag file: [`evidence/sources/LAB-rauc-1152.md`](evidence/sources/LAB-rauc-1152.md) · 9 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://security-tracker.debian.org/tracker/CVE-2026-34155 | 2026-11-11 | PRIMARY | saved: `LAB-rauc-1152/debian-sectracker.txt` | C-LAB-rauc-1152-004 |
| 2 | https://security-tracker.debian.org/tracker/source-package/rauc | 2026-11-11 | PRIMARY | saved: `LAB-rauc-1152/debian-srcpkg-sectracker.txt` | — |
| 3 | https://tracker.debian.org/pkg/rauc | 2026-11-11 | PRIMARY | saved: `LAB-rauc-1152/debian-pkgtracker.txt` | C-LAB-rauc-1152-005, 006 |
| 4 | https://github.com/rauc/rauc.git | 2026-11-11 | PRIMARY | — | — |
| 5 | rauc/rauc@4fb7c798d6ae412344fb8f8d310d773046af3441 | 2026-11-11 | PRIMARY | commit pin `4fb7c798d6ae` | — |
| 6 | raspberrypi/documentation@21d772e7ee022e36a8f43c3ee75e20ca359fb832 | 2026-11-11 | PRIMARY | commit pin `21d772e7ee02` | — |
| 7 | home-assistant/operating-system@fc301f556647b53281e853b9ce7f44915b3c7b14 | 2026-11-11 | PRIMARY | commit pin `fc301f556647` | — |
| 8 | https://downloads.raspberrypi.com/os_list_imagingutility_v4.json | 2026-11-11 | PRIMARY-METADATA | saved: `downloads.raspberrypi.com/os_list_imagingutility_v4.json` | C-LAB-rauc-1152-016 |
| 9 | https://github.com/k3s-io/k3s/releases/tag/v1.37.2%2Bk3s1 | 2026-11-11 | PRIMARY | — | C-LAB-debian-rugix-014; C-LAB-k3s-footprint-restore-001; C-W4-011; C-W5-055 |

### LAB-rauc-k3s-gate

Tag file: [`evidence/sources/LAB-rauc-k3s-gate.md`](evidence/sources/LAB-rauc-k3s-gate.md) · 9 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/src/install.c#L1444-L1520 | 2026-11-11 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-k3s-gate-001 |
| 2 | https://github.com/rauc/rauc/blob/1183a396a2e10e92e428c396a510113edcd9037b/src/install.c#L1420-L1490 | 2026-11-11 | PRIMARY | commit pin `1183a396a2e1` | C-LAB-rauc-k3s-gate-001 |
| 3 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/docs/reference.rst#L639-L647 | 2026-11-11 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-k3s-gate-002 |
| 4 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/src/bootloaders/grub.c#L137-L185 | 2026-11-11 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-k3s-gate-003 |
| 5 | https://github.com/home-assistant/operating-system/blob/ab7d0f1a0174760353780a21be2befecbc80a672/buildroot-external/board/pc/grub.cfg#L10-L45 | 2026-11-11 | PRIMARY | commit pin `ab7d0f1a0174` | C-LAB-rauc-010; C-LAB-rauc-k3s-gate-003 |
| 6 | https://github.com/k3s-io/k3s/blob/f6973cb850e9b245585363d15bde80904ac862fd/pkg/datadir/datadir.go#L12-L16 | 2026-11-11 | PRIMARY | commit pin `f6973cb850e9` | C-LAB-rauc-k3s-gate-004 |
| 7 | https://github.com/k3s-io/k3s/blob/f6973cb850e9b245585363d15bde80904ac862fd/pkg/rootless/mounts.go#L34-L40 | 2026-11-11 | PRIMARY | commit pin `f6973cb850e9` | C-LAB-rauc-k3s-gate-004 |
| 8 | https://github.com/k3s-io/k3s/blob/f6973cb850e9b245585363d15bde80904ac862fd/pkg/cli/cmds/server.go#L282-L288 | 2026-11-11 | PRIMARY | commit pin `f6973cb850e9` | C-LAB-rauc-k3s-gate-004 |
| 9 | https://github.com/k3s-io/k3s/releases/tag/v1.37.2%2Bk3s1 | 2026-11-11 | PRIMARY-METADATA | saved: `../lab/rauc-k3s-gate/versions.md` | C-LAB-debian-rugix-014; C-LAB-k3s-footprint-restore-001; C-W4-011; C-W5-055 |

### LAB-rauc

Tag file: [`evidence/sources/LAB-rauc.md`](evidence/sources/LAB-rauc.md) · 9 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/rauc/rauc/releases | 2026-11-10 | PRIMARY-METADATA | API response (values quoted in the claim) | C-LAB-rauc-001 |
| 2 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/src/install.c#L1466 | 2026-11-10 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-003 |
| 3 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/src/bootloaders/grub.c#L190-L213 | 2026-11-10 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-004, 005 |
| 4 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/contrib/grub.conf#L11-L41 | 2026-11-10 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-006 |
| 5 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/docs/integration.rst#L1207-L1226 | 2026-11-10 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-007, 008 |
| 6 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/docs/reference.rst#L359-L373 | 2026-11-10 | PRIMARY | commit pin `2d17b27041db` | C-LAB-rauc-009 |
| 7 | https://github.com/home-assistant/operating-system/blob/ab7d0f1a0174760353780a21be2befecbc80a672/buildroot-external/board/pc/grub.cfg#L10-L61 | 2026-11-10 | PRIMARY | commit pin `ab7d0f1a0174` | C-LAB-rauc-010 |
| 8 | https://github.com/home-assistant/supervisor/blob/040f14cd8aa2902401d30aaeb0cb71215854c78c/supervisor/os/manager.py#L467-L478 | 2026-11-10 | PRIMARY | commit pin `040f14cd8aa2` | C-LAB-rauc-011 |
| 9 | http://deb.debian.org/debian | 2026-11-10 | PRIMARY-METADATA | saved: `../lab/rauc/image-packages.txt` | C-LAB-rauc-002, 012 |

### LAB-secureboot-1152

Tag file: [`evidence/sources/LAB-secureboot-1152.md`](evidence/sources/LAB-secureboot-1152.md) · 1 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/CHANGES | 2026-11-11 | PRIMARY | commit pin `4fb7c798d6ae` | — |

### LAB-secureboot-rauc

Tag file: [`evidence/sources/LAB-secureboot-rauc.md`](evidence/sources/LAB-secureboot-rauc.md) · 11 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/src/bootloaders/efi.c#L378-L498 | 2026-11-11 | PRIMARY | commit pin `4fb7c798d6ae` | C-LAB-secureboot-rauc-001 |
| 2 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/reference.rst#L155-L161 | 2026-11-11 | PRIMARY | saved: `rauc.readthedocs.io/en/v1.15.2/reference.html` | C-LAB-secureboot-rauc-001 |
| 3 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/docs/integration.rst#L1226-L1300 | 2026-11-11 | PRIMARY | commit pin `4fb7c798d6ae` | C-LAB-secureboot-rauc-001 |
| 4 | https://github.com/rauc/rauc/blob/4fb7c798d6ae412344fb8f8d310d773046af3441/src/context.c#L69-L91 | 2026-11-11 | PRIMARY | commit pin `4fb7c798d6ae` | C-LAB-secureboot-rauc-002 |
| 5 | https://github.com/tianocore/edk2/blob/fbe0805b2091393406952e84724188f8c1941837/MdeModulePkg/Universal/BdsDxe/BdsEntry.c#L1052-L1093 | 2026-11-11 | PRIMARY | commit pin `fbe0805b2091` | C-LAB-secureboot-rauc-003 |
| 6 | https://www.freedesktop.org/software/systemd/man/257/systemd-stub.html | 2026-11-11 | PRIMARY | saved: `systemd-stub.txt` | C-LAB-secureboot-rauc-004, 005 |
| 7 | https://www.freedesktop.org/software/systemd/man/257/systemd-cryptenroll.html | 2026-11-11 | PRIMARY | saved: `systemd-cryptenroll.txt` | C-LAB-secureboot-rauc-006, 007 |
| 8 | https://www.freedesktop.org/software/systemd/man/257/systemd-pcrphase.service.html | 2026-11-11 | PRIMARY | saved: `systemd-pcrphase.txt` | C-LAB-secureboot-rauc-008 |
| 9 | https://www.freedesktop.org/software/systemd/man/257/ukify.html | 2026-11-11 | PRIMARY | saved: `systemd-measure.txt` | C-LAB-secureboot-rauc-009 |
| 10 | http://deb.debian.org/debian | 2026-11-11 | PRIMARY-METADATA | saved: `../lab/secureboot-rauc/image-packages.txt` | C-LAB-secureboot-rauc-010 |
| 11 | https://uefi.org/specs/UEFI/2.10/03_Boot_Manager.html | 2026-11-11 | UNVERIFIED | saved: `uefi.org/specs/UEFI/2.10/03_Boot_Manager.html` | — |

### LAB-ubuntu-2604-leg

Tag file: [`evidence/sources/LAB-ubuntu-2604-leg.md`](evidence/sources/LAB-ubuntu-2604-leg.md) · 6 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://documentation.ubuntu.com/release-notes/26.04/summary-for-lts-users/ | 2026-11-11 | PRIMARY | saved: `LAB-ubuntu-2604-leg/ubuntu-2604-relnotes-summary-full.txt` | — |
| 2 | https://github.com/rauc/rauc/blob/1183a396a2e10e92e428c396a510113edcd9037b/src/dm.c#L229-L244 | 2026-11-11 | PRIMARY | commit pin `1183a396a2e1` | — |
| 3 | https://github.com/rauc/rauc/blob/2d17b27041db7fa8b13a61c5e168f49310a06566/src/dm.c#L71-L100 | 2026-11-11 | PRIMARY | commit pin `abeccdc5406e` | — |
| 4 | https://github.com/rauc/rauc/issues/1842 | 2026-11-11 | PRIMARY | saved: `LAB-ubuntu-2604-leg/rauc-issue-1842.txt` | — |
| 5 | https://github.com/torvalds/linux/commit/ae97648e14f7907f4b0e0b295eb2fdcf43806f9d | 2026-11-11 | PRIMARY | commit pin `ae97648e14f7` | — |
| 6 | https://github.com/home-assistant/operating-system/blob/ab7d0f1a0174760353780a21be2befecbc80a672/buildroot-external/configs/generic_x86_64_defconfi… | 2026-11-11 | PRIMARY | commit pin `ab7d0f1a0174` | — |

### LABPLAN

Tag file: [`evidence/sources/LABPLAN.md`](evidence/sources/LABPLAN.md) · 9 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://docs.digitalocean.com/reference/doctl/reference/kubernetes/cluster/get/ | 2026-11-11 | PRIMARY | saved: `LABPLAN/doctl-kubernetes-cluster-get.txt` | C-LABPLAN-006 |
| 2 | https://docs.digitalocean.com/reference/doctl/reference/kubernetes/cluster/list/ | 2026-11-11 | PRIMARY | saved: `LABPLAN/doctl-kubernetes-cluster-list.txt` | C-LABPLAN-007 |
| 3 | https://argo-cd.readthedocs.io/en/stable/user-guide/commands/argocd_app_list/ | 2026-11-11 | PRIMARY | saved: `LABPLAN/argocd-app-list.txt` | C-LABPLAN-008 |
| 4 | https://kubernetes.io/docs/reference/kubectl/generated/kubectl_get/ | 2026-11-11 | PRIMARY | saved: `LABPLAN/kubectl-get.txt` | C-LABPLAN-009 |
| 5 | https://kubernetes.io/docs/concepts/security/pod-security-admission/ | 2026-11-11 | PRIMARY | saved: `LABPLAN/k8s-pod-security-admission.txt` | C-LABPLAN-010 |
| 6 | home-assistant/operating-system@ab7d0f1a0174760353780a21be2befecbc80a672 | 2026-11-11 | PRIMARY | commit pin `ab7d0f1a0174` | C-LABPLAN-001 |
| 7 | getumbrel/umbrel@c43beed964074d08865d648ca9ac3359826a14ff | 2026-11-11 | PRIMARY | commit pin `c43beed96407` | C-LABPLAN-003 |
| 8 | balena-os/meta-balena@48184b689a43b762c5eea6efbc16b018eed70839 | 2026-11-11 | PRIMARY | commit pin `48184b689a43` | C-LABPLAN-004 |
| 9 | beclab/Olares@e7fe1c9634f26530386c2033a33be7a9495704f3 | 2026-11-11 | PRIMARY | commit pin `e7fe1c9634f2` | C-LABPLAN-011 |

### LEDGER

Tag file: [`evidence/sources/LEDGER.md`](evidence/sources/LEDGER.md) · 10 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://umbrel.com/downloads | 2026-11-11 | PRIMARY | saved: `W3/umbrel-com-downloads.txt` · sha256 `8b620e02296e2250…` | C-W3-042 |
| 2 | https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/RootFileSystem.html | 2026-11-11 | PRIMARY | saved: `W3/nvidia-jetson-r39.2-RootFileSystem.txt` · sha256 `15c229de73f2ba77…` | C-W3-049 |
| 3 | https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | 2026-11-11 | PRIMARY | saved: `W3/nvidia-jetson-r39.2-SoftwarePackagesAndTheUpdateMechanism.txt` · sha256 `78e39c105276e296…` | C-W3-050 |
| 4 | https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | 2026-11-11 | PRIMARY | saved: `W3/nvidia-jetson-r36.4-SoftwarePackagesAndTheUpdateMechanism.txt` · sha256 `0c3534ca37b25242…` | C-W3-051 |
| 5 | cip-core/isar-cip-core@e957cf930cef8c7cf8a55817f624bcf10bd81789 | 2026-11-11 | PRIMARY | commit pin `e957cf930cef` | C-W3-057 |
| 6 | raspberrypi/documentation@21d772e7ee022e36a8f43c3ee75e20ca359fb832 | 2026-11-11 | PRIMARY | commit pin `21d772e7ee02` | C-W3-066 |
| 7 | https://www.home-assistant.io/installation/generic-x86-64 | 2026-11-11 | PRIMARY | saved: `W3/home-assistant-io-installation-generic-x86-64.txt` · sha256 `f6018cb6622c4c95…` | C-W3-027 |
| 8 | W18/ | 2026-11-11 | — | saved copy in `sources/LEDGER/` | — |
| 9 | TD-villageos/ | 2026-11-11 | — | — | — |
| 10 | TD-truenas-scale/from-lab/ | 2026-11-11 | — | — | — |

### LIC

Tag file: [`evidence/sources/LIC.md`](evidence/sources/LIC.md) · 39 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | nvidia-l4t-core_39.2.1-20260806224157_arm64.deb from NVIDIA's public Jetson apt feed (repo.download.nvidia.com/jetson/som/pool/main/n/nvidia | 2026-11-11 | — | hash only `277a6fb25f2c06cc…` (copy not in repo) | C-LIC-001, 006, 048 |
| 2 | Tegra_Software_License_Agreement-Tegra-Linux.txt inside (1) ("NVIDIA Driver License Agreement", v. 2025-02-25). md5 376d20bd5275442226fcdf54 | 2026-11-11 | — | saved: `LIC/01-nvidia-tegra-sla-r39.2.1.txt` · sha256 `828f46b4982622a4…` | C-LIC-001…005, 048 |
| 3 | /usr/share/doc/nvidia-l4t-core/copyright inside (1) | 2026-11-11 | — | saved: `LIC/02-nvidia-l4t-core-39.2.1-copyright.txt` · sha256 `1b648a06caf4c771…` | C-LIC-006 |
| 4 | cuda-cudart-13-2_13.2.86-1_arm64.deb, /usr/share/doc/cuda-cudart-13-2/copyright (CUDA EULA, last updated 2026-01-26) | 2026-11-11 | — | saved: `LIC/03-cuda-cudart-13.2.86-copyright-eula.txt` · sha256 `550a1c3c915637b5…` | C-LIC-007…010 |
| 5 | https://docs.nvidia.com/cuda/eula/index.html | 2026-11-11 | — | saved: `LIC/04-docs-nvidia-cuda-eula.txt` | C-LIC-007…010 |
| 6 | NVIDIA-ISAAC-ROS/isaac_ros_common@7bec6ae5db | 2026-11-11 | — | saved: `LIC/12-isaac-ros-software-license.txt` | C-LIC-021 |
| 7 | canonical/linux-noble@78272943bba3 | 2026-11-11 | — | saved: `LIC/20-l4t-kernel-linux-noble-COPYING.txt` | C-LIC-017 |
| 8 | https://developer.nvidia.com/embedded/jetson-linux-r3921 | 2026-11-11 | — | — | — |
| 9 | https://canonical.com/legal/intellectual-property-policy | 2026-11-11 | — | saved: `LIC/05-canonical-iprights-policy.txt` | C-LIC-011 |
| 10 | https://www.debian.org/trademark | 2026-11-11 | — | saved: `LIC/06-debian-trademark-policy.txt` | C-LIC-012 |
| 11 | https://www.debian.org/social_contract | 2026-11-11 | — | saved: `LIC/07-debian-social-contract.txt` | — |
| 12 | https://www.redhat.com/en/about/trademark-guidelines-and-policies | 2026-11-11 | — | saved: `LIC/08-redhat-trademark-guidelines.txt` | C-LIC-013 |
| 13 | https://www.centos.org/legal/trademarks/ | 2026-11-11 | — | saved: `LIC/09-centos-trademark-guidelines.txt` | C-LIC-014 |
| 14 | https://docs.fedoraproject.org/en-US/legal/trademark-guidelines/ | 2026-11-11 | UNVERIFIED | saved: `LIC/21-fedora-trademark-BLOCKED-anubis.txt` | C-LIC-049 |
| 15 | https://almalinux.org/legal/ | 2026-11-11 | UNVERIFIED | — | — |
| 16 | raspberrypi/firmware@016253866bbd6c77fcb2a744a97d81e79ad4884f | 2026-11-11 | PRIMARY | commit pin `016253866bbd` | C-LIC-015 |
| 17 | raspberrypi/rpi-eeprom (tag v2026.10.30-2712) LICENSE | 2026-11-11 | — | saved: `LIC/11-rpi-eeprom-LICENSE.txt` | C-LIC-016 |
| 18 | kernel-firmware/linux-firmware@69e51bb26f3fa3e118dd770f1962a93bed690dc1 | 2026-11-11 | PRIMARY | commit pin `69e51bb26f3f` | C-LIC-020, 055 |
| 19 | open-webui/open-webui (v0.13.3) LICENSE | 2026-11-11 | — | saved: `LIC/13-open-webui-license.txt` | C-LIC-022 |
| 20 | hailo-ai/hailort@e7727f7482477e448f4c93b33dc62f9e5a30c3e7 | 2026-11-11 | PRIMARY | commit pin `e7727f748247` | C-LIC-025 |
| 21 | airockchip/rknn-toolkit2 (master) LICENSE | 2026-11-11 | — | saved: `LIC/15-rknn-sdk-license.txt` | C-LIC-024 |
| 22 | emqx/emqx (6.3.2) LICENSE (BSL 1.1) | 2026-11-11 | — | saved: `LIC/16-emqx-bsl-1.1.txt` | C-W8-013 |
| 23 | markqvist/Reticulum (1.6.0) LICENSE | 2026-11-11 | — | saved: `LIC/17-reticulum-license.txt` | C-W8-014 |
| 24 | nvidia-driver-libs_620.70.06-1_amd64.deb from NVIDIA's CUDA apt repo (developer.download.nvidia.com/compute/cuda/repos/debian13/x86_64/), de | 2026-11-11 | — | saved: `LIC/22-nvidia-driver-libs-620.70.06-copyright.txt` · sha256 `847a3a5d20174de4…` | C-LIC-077 |
| 25 | https://docs.nvidia.com/jetson/jetpack/eula/index.html | 2026-11-11 | — | saved: `LIC/23-jetpack-eula-web.txt` | C-LIC-078 |
| 26 | api.ngc.nvidia.com/v2/repos/nvidia/l4t-base, …/nvidia/l4t-jetpack, …/nvidia/isaac/ros (licence sections of the catalogue descriptions) | 2026-11-11 | — | saved: `LIC/24-ngc-container-license-excerpts.txt` | C-LIC-078 |
| 27 | https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/ | 2026-11-11 | — | saved: `LIC/25-nvidia-open-model-license.txt` | C-LIC-076 |
| 28 | https://ai.google.dev/gemma/terms | 2026-11-11 | — | saved: `LIC/26-gemma-terms-of-use.txt` | C-LIC-073, 074 |
| 29 | https://ai.google.dev/gemma/prohibited_use_policy | 2026-11-11 | — | saved: `LIC/27-gemma-prohibited-use-policy.txt` | C-LIC-075 |
| 30 | https://ai.google.dev/gemma/apache_2 | 2026-11-11 | — | saved: `LIC/28-gemma4-apache-page-head.txt` | C-LIC-074 |
| 31 | meta-llama/llama-models@0e0b8c519242d5833d8c11bffc1232b77ad7f301 | 2026-11-11 | PRIMARY | commit pin `0e0b8c519242` | C-LIC-070, 071 |
| 32 | same commit, models/llama4/{LICENSE,USE_POLICY.md} | 2026-11-11 | — | saved: `LIC/31-llama-4-community-license.txt` | C-LIC-071, 072 |
| 33 | n8n-io/n8n@cc8686c5f01069714f69056112aec28f789f79e6 | 2026-11-11 | PRIMARY | commit pin `cc8686c5f010` | C-LIC-064 |
| 34 | outline/outline@09f11188b87b0220fa318dfa6fdd0fa9772195dd | 2026-11-11 | PRIMARY | commit pin `09f11188b87b` | C-LIC-065 |
| 35 | TandoorRecipes/recipes@d0a587832523a3e561932ce649c018b535fd43b5 | 2026-11-11 | PRIMARY | commit pin `d0a587832523` | C-LIC-066 |
| 36 | invoiceninja/invoiceninja@2e52eca85aa5 | 2026-11-11 | — | saved: `LIC/37-invoiceninja-elastic-2.0.txt` | C-LIC-067 |
| 37 | HabitRPG/habitica@12091ca02990 | 2026-11-11 | — | saved: `LIC/39-habitica-license.txt` | C-LIC-061 |
| 38 | activepieces/activepieces@dec8e16d4e02 | 2026-11-11 | — | saved: `LIC/40-activepieces-license.txt` | C-LIC-068 |
| 39 | u-boot/u-boot@5508406582f6f7120dce0c4b3059819a41788db2 | 2026-11-11 | PRIMARY | commit pin `5508406582f6` | C-LIC-059 |

### LIC4

Tag file: [`evidence/sources/LIC4.md`](evidence/sources/LIC4.md) · 22 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.postgresql.org/about/licence/ | 2026-11-11 | — | saved: `LIC4/01-postgresql-licence-page.txt` | C-LIC4-001 |
| 2 | https://www.postgresql.org/support/versioning/ | 2026-11-11 | — | saved: `LIC4/02-postgresql-versioning-page.txt` | C-LIC4-002 |
| 3 | postgres/postgres@724edf9bde9d | 2026-11-11 | — | saved: `LIC4/03-postgresql-COPYRIGHT-REL_18_6.txt` | C-LIC4-001 |
| 4 | jejb/sbsigntools@9cfca9fe7aa7 | 2026-11-11 | — | saved: `LIC4/04-sbsigntools-COPYING-head.txt` | C-LIC4-004 |
| 5 | jejb/efitools@392836a46ce3 | 2026-11-11 | — | saved: `LIC4/05-efitools-COPYING-head.txt` | C-LIC4-005 |
| 6 | xiang/erofs-utils@f36cadb5c563 | 2026-11-11 | — | saved: `LIC4/06-erofs-utils-COPYING.txt` | C-LIC4-007 |
| 7 | tytso/e2fsprogs@7ee1d505ef3b | 2026-11-11 | — | saved: `LIC4/07-e2fsprogs-NOTICE-head.txt` | C-LIC4-013 |
| 8 | stefanberger/libtpms@03ff2481e133 | 2026-11-11 | — | saved: `LIC4/08-libtpms-LICENSE.txt` | C-LIC4-016 |
| 9 | tpm2-software/tpm2-tools@bc25f7149372 | 2026-11-11 | — | saved: `LIC4/09-tpm2-tools-docs-LICENSE.txt` | C-LIC4-006 |
| 10 | UnifiedPush/android-connector@04820c8cfe11 | 2026-11-11 | — | saved: `LIC4/10-unifiedpush-connector-and-spec.txt` | C-LIC4-008 |
| 11 | josch/mmdebstrap@a6fcdbc4dde9 | 2026-11-11 | — | saved: `LIC4/11-mmdebstrap-script-header.txt` | C-LIC4-013 |
| 12 | nodejs/node@18b32a3b1552 | 2026-11-11 | — | saved: `LIC4/12-nodejs-LICENSE-index.txt` | C-LIC4-012 |
| 13 | SBOM/CVE | 2026-11-11 | — | — | C-LIC4-003 |
| 14 | UnifiedPush | 2026-11-11 | — | — | C-LIC4-008 |
| 15 | Sandboxes | 2026-11-11 | — | — | C-LIC4-009 |
| 16 | Core and dashboard | 2026-11-11 | — | — | C-LIC4-010…012 |
| 17 | Image build | 2026-11-11 | — | — | C-LIC4-013 |
| 18 | Boot runtime | 2026-11-11 | — | — | C-LIC4-014 |
| 19 | Time | 2026-11-11 | — | — | C-LIC4-015 |
| 20 | CI firmware and rigs | 2026-11-11 | — | — | C-LIC4-016 |
| 21 | Lab tools | 2026-11-11 | — | — | C-LIC4-017 |
| 22 | CI scanners and linters | 2026-11-11 | — | — | C-LIC4-018 |

### MATRIX

Tag file: [`evidence/sources/MATRIX.md`](evidence/sources/MATRIX.md) · 1 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | kairos-io/kairos-docs@b1bf8bed | 2026-11-11 | PRIMARY | saved: `MATRIX/casaos-kairos-checks-2026-11-11.txt` | C-MATRIX-014, 015 |

### PLAN180

Tag file: [`evidence/sources/PLAN180.md`](evidence/sources/PLAN180.md) · 5 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/rauc/rauc | 2026-11-11 | PRIMARY | saved: `PLAN180/rauc-tags.txt` | C-PLAN180-001 |
| 2 | https://github.com/fedora-iot/greenboot-rs/issues/219 | 2026-11-11 | PRIMARY | saved: `PLAN180/greenboot-rs-219.txt` | C-PLAN180-002 |
| 3 | https://github.com/coreos/bootupd/pull/935 | 2026-11-11 | PRIMARY | saved: `PLAN180/bootupd-pr-935.txt` | C-PLAN180-003 |
| 4 | https://api.launchpad.net/1.0/bugs/2170238/bug_tasks | 2026-11-11 | PRIMARY | saved: `PLAN180/launchpad-2170238.txt` | C-PLAN180-004 |
| 5 | https://github.com/k3s-io/k3s/releases | 2026-11-11 | PRIMARY | saved: `PLAN180/k3s-releases.txt` | C-PLAN180-005 |

### QBANK

Tag file: [`evidence/sources/QBANK.md`](evidence/sources/QBANK.md) · 15 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.acquisition.gov/far/52.204-25 | 2026-11-11 | PRIMARY | saved: `far-52-204-25.txt` | C-QBANK-001 |
| 2 | https://www.acquisition.gov/far/25.003 | 2026-11-11 | PRIMARY | saved: `far-25-003.txt` | C-QBANK-002 |
| 3 | https://www.ecfr.gov/api/versioner/v1/full/2026-11-09/title-14.xml?part=89 | 2026-11-11 | PRIMARY | saved: `ecfr-14-89.txt` | C-QBANK-003 |
| 4 | https://www.ecfr.gov/api/versioner/v1/full/2026-11-09/title-47.xml?section=15.212 | 2026-11-11 | PRIMARY | saved: `ecfr-47-15-212.txt` | C-QBANK-004 |
| 5 | https://www.edpb.europa.eu/system/files/documents/files/file1/edpb_guidelines_201903_video_devices_en_0.pdf | 2026-11-11 | PRIMARY | saved: `edpb-3-2019.txt` | C-QBANK-005, 006 |
| 6 | https://labgrid.readthedocs.io/en/latest/overview.html | 2026-11-11 | PRIMARY | commit pin `b1b5b8e2335b` | C-QBANK-007 |
| 7 | https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ | 2026-11-11 | PRIMARY | saved: `metr-2025.txt` | C-QBANK-008 |
| 8 | https://chaos-mesh.org/docs/simulate-pod-chaos-on-kubernetes/ | 2026-11-11 | PRIMARY | commit pin `8e5a702ee41f` | C-QBANK-009 |
| 9 | https://docs.digitalocean.com/products/custom-images/details/limits/ | 2026-11-11 | PRIMARY | saved: `do-custom-images.txt` | C-QBANK-010 |
| 10 | https://www.spamhaus.org/blocklists/policy-blocklist/ | 2026-11-11 | PRIMARY | saved: `spamhaus-pbl.txt` | C-QBANK-011 |
| 11 | https://github.com/system76/firmware-open | 2026-11-11 | PRIMARY | commit pin `0cf80d89edec` | C-QBANK-012 |
| 12 | https://openinventionnetwork.com/joining-oin/ | 2026-11-11 | UNVERIFIED | — | C-QBANK-013 |
| 13 | https://www.fcc.gov/supplychain/coveredlist | 2026-11-11 | SECONDARY | — | C-W15-019 |
| 14 | https://www.diu.mil/blue-uas | 2026-11-11 | UNVERIFIED | — | — |
| 15 | EUR-Lex (Product Liability Directive 2024/2853) | 2026-11-11 | — | — | C-STEEL-cra-nb-018 |

### ROADMAP

Tag file: [`evidence/sources/ROADMAP.md`](evidence/sources/ROADMAP.md) · 2 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | ros-infrastructure/rep@11ca24a41f31480dfb9562ba99f2a5b93d3ebda5 | 2026-11-11 | PRIMARY | commit pin `11ca24a41f31` | C-ROADMAP-001 |
| 2 | https://ubuntu.com/about/release-cycle | 2026-11-11 | PRIMARY | saved: `ROADMAP/ubuntu-release-cycle.txt` | C-ROADMAP-002 |

### SCORE

Tag file: [`evidence/sources/SCORE.md`](evidence/sources/SCORE.md) · 25 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | k0sproject/k0s@d65558bb77e540ba723067243235b0d0a396b187 | 2026-11-11 | PRIMARY | saved: `docs/autopilot.md` | C-SCORE-001…005 |
| 2 | canonical/microk8s@e254fda97340b3d307a993eac6baafda3fa409ff | 2026-11-11 | PRIMARY | commit pin `e254fda97340` | C-SCORE-006 |
| 3 | https://canonical.com/microk8s/docs/upgrading | 2026-11-11 | PRIMARY | saved: `microk8s-docs-upgrading.txt` · sha256 `eb2d14948baeefe1…` | C-SCORE-007 |
| 4 | https://canonical.com/microk8s/docs/high-availability | 2026-11-11 | PRIMARY | saved copy in `sources/SCORE/` · sha256 `0456afbb0892253d…` | C-SCORE-008 |
| 5 | moby/moby@70efc0e31da3a115fc87574d1b786fa2b867c346 | 2026-11-11 | PRIMARY | saved: `moby-70efc0e3-project-BRANCHES-AND-TAGS.md.txt` | C-SCORE-009, 010 |
| 6 | https://docs.docker.com/engine/install/debian/ | 2026-11-11 | PRIMARY | saved copy in `sources/SCORE/` · sha256 `7017ab50b44ff95c…` | C-SCORE-011 |
| 7 | containers/podman@055de046937d29450f310fce0fe3071485d8bed9 | 2026-11-11 | PRIMARY | saved: `docs/source/markdown/podman-auto-update.1.md` | C-SCORE-012, 013 |
| 8 | flightctl/flightctl@f99870eafa95003d1511577efc1c6e8c4ce7d5d1 | 2026-11-11 | PRIMARY | saved: `flightctl-f99870ea-README.md.txt` | C-SCORE-014 |
| 9 | vmware-tanzu/velero@4ee1e79a7aed367fd9b767b8219ec65bd0c96892 | 2026-11-11 | PRIMARY | saved: `velero-4ee1e79a-support-process.md.txt` | C-SCORE-015, 016 |
| 10 | longhorn/longhorn.wiki@2aea6d68f663ededc0b04b7d0a9d5b5fdf701197 | 2026-11-11 | PRIMARY | saved: `-Support.md` | C-SCORE-017 |
| 11 | openzfs/zfs@71a9f9578616a90c3c14bb59629fb4d31bfd68d1 | 2026-11-11 | PRIMARY | saved: `openzfs-71a9f957-RELEASES.md.txt` | C-SCORE-018 |
| 12 | borgmatic-collective/borgmatic@2499e0d75c41ad15b0bfee8e73338922ad56b822 | 2026-11-11 | PRIMARY-METADATA | commit pin `2499e0d75c41` | C-SCORE-019 |
| 13 | sbabic/swupdate@9000ecb52677da7d9676a61b729bab57dba99674 | 2026-11-11 | PRIMARY | saved: `doc/source/signed_images.rst` | C-SCORE-020 |
| 14 | https://docs.mender.io/artifact-creation/standalone-deployment | 2026-11-11 | PRIMARY | saved copy in `sources/SCORE/` · sha256 `b4a54f19c3187688…` | C-SCORE-021 |
| 15 | agherzan/meta-raspberrypi@72f7dfc6a6fea2490ad28ae9c660fb5728f87c40 | 2026-11-11 | PRIMARY | commit pin `72f7dfc6a6fe` | C-SCORE-022 |
| 16 | https://canonical.com/blog/bosch-rexroth-adopts-ubuntu-core-and-snaps-for-app-based-ctrlx-automation-platform | 2026-11-11 | PRIMARY | saved copy in `sources/SCORE/` · sha256 `7cfcbeca8cda0521…` | C-SCORE-023 |
| 17 | https://apps.boschrexroth.com/microsites/ctrlx-automation/en/portfolio/ctrlx-os/ | 2026-11-11 | PRIMARY | saved copy in `sources/SCORE/` · sha256 `dba761133e1164f9…` | C-SCORE-024 |
| 18 | AlmaLinux/bootc-images-rpi@bb8e83e6b898db63ca2b53a69343f067dfa4f28a | 2026-11-11 | PRIMARY | saved: `almalinux-bootc-images-rpi-bb8e83e6-README.md.txt` | C-SCORE-025 |
| 19 | kfox1111/rpi-bootc-bootloader@82739f4c9ae6de9ce071014bff9dee16842fb978 | 2026-11-11 | PRIMARY | saved: `rpi-bootc-bootloader-82739f4c-README.md.txt` | C-SCORE-026 |
| 20 | https://nullr0ute.com/2026/10/raspberry-pi-5-on-fedora/ | 2026-11-11 | SECONDARY | saved copy in `sources/SCORE/` · sha256 `de22d08d8c5137e5…` | C-SCORE-027 |
| 21 | https://fedora.yaasharc.me/posts/bootc/fedora-bootc-rpi5-report/ | 2026-11-11 | UNVERIFIED | — | C-SCORE-028 |
| 22 | https://repo.almalinux.org/almalinux/10/RT/x86_64/os/Packages/ | 2026-11-11 | PRIMARY | saved copy in `sources/SCORE/` · sha256 `92688eb23570db3f…` | C-SCORE-029 |
| 23 | https://developer.download.nvidia.com/compute/cuda/repos/ | 2026-11-11 | PRIMARY | saved copy in `sources/SCORE/` · sha256 `e065d0f19ec12628…` | C-SCORE-030 |
| 24 | https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html | 2026-11-11 | PRIMARY | saved: `docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html` · sha256 `3d75171d2b3ad62b…` | C-SCORE-031 |
| 25 | kopia/kopia@72ec08fd8edb86c67ed27099bf1b955e1f308ffa | 2026-11-11 | PRIMARY | commit pin `72ec08fd8edb` | C-SCORE-032 |

### STEEL4-bootc

Tag file: [`evidence/sources/STEEL4-bootc.md`](evidence/sources/STEEL4-bootc.md) · 15 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | AlmaLinux/bootc-images-rpi@bb8e83e6b898db63ca2b53a69343f067dfa4f28a | 2026-11-11 | PRIMARY | saved: `-issue22.json` | C-STEEL4-bootc-001…003 |
| 2 | https://repo.almalinux.org/almalinux/10/raspberrypi/aarch64/os/Packages/ | 2026-11-11 | PRIMARY | saved: `alma10-raspberrypi-aarch64-Packages.txt` | C-STEEL4-bootc-004, 005 |
| 3 | kfox1111/rpi-bootc-bootloader@82739f4c9ae6de9ce071014bff9dee16842fb978 | 2026-11-11 | PRIMARY | saved: `rpi-bootc-bootloader-82739f4c-LICENSE.txt` | C-STEEL4-bootc-006 |
| 4 | https://repo.almalinux.org/almalinux/10/RT/ | 2026-11-11 | PRIMARY | saved: `alma10-rt-index.txt` | C-STEEL4-bootc-007 |
| 5 | https://mirror.stream.centos.org/10-stream/RT/ | 2026-11-11 | PRIMARY | saved: `cs10-RT-x86_64-Packages.txt` | C-STEEL4-bootc-008 |
| 6 | https://www.centos.org/download/ | 2026-11-11 | PRIMARY | saved: `centos-download.txt` | C-STEEL4-bootc-009 |
| 7 | https://access.redhat.com/support/policy/updates/errata | 2026-11-11 | PRIMARY | saved: `rhel-lifecycle.txt` | C-STEEL4-bootc-010 |
| 8 | https://www.redhat.com/en/about/press-releases/red-hat-nvidia-pair-enterprise-open-source-rack-scale-ai-faster-production-ready-innovation | 2026-11-11 | PRIMARY | saved: `rh-press-rhel-for-nvidia.txt` | C-STEEL4-bootc-011 |
| 9 | https://www.redhat.com/en/blog/red-hat-device-edge-now-available-run-nvidia-jetson-orin | 2026-11-11 | PRIMARY | saved: `rh-blog-rhde-orin-ga.txt` | C-STEEL4-bootc-012 |
| 10 | https://repo.download.nvidia.com/jetson/rhel-9.4/r36.3.1/ | 2026-11-11 | PRIMARY | saved: `nvidia-jetson-rhel-9.4-r36.3.1-primary.xml.txt` | C-STEEL4-bootc-013 |
| 11 | https://almalinux.org/p/the-almalinux-os-trademark-usage-policy/ | 2026-11-11 | PRIMARY | saved copy in `sources/STEEL4-bootc/` | C-STEEL4-bootc-014 |
| 12 | https://almalinux.org/blog/future-of-almalinux/ | 2026-11-11 | PRIMARY | saved: `alma-blog-future-2023.txt` | C-STEEL4-bootc-015 |
| 13 | https://wiki.almalinux.org/release-notes/ | 2026-11-11 | PRIMARY | saved: `alma-release-notes.txt` | C-STEEL4-bootc-016 |
| 14 | bootc-dev/bootc@27f1e64ea93639929ed0088cdc230c220dac0fe6 | 2026-11-11 | PRIMARY | saved: `bootc-installation.7.md` | C-STEEL4-bootc-017…023, 025 |
| 15 | GitHub API: fedora-iot/greenboot-rs issue #219 and PR #223 (and the 15 newest PRs), fedora-iot/iot-distro issue #82, coreos/bootupd PR #935 | 2026-11-11 | PRIMARY-METADATA | saved copy in `sources/STEEL4-bootc/` | C-STEEL4-bootc-024 |

### TD-balenaos

Tag file: [`evidence/sources/TD-balenaos.md`](evidence/sources/TD-balenaos.md) · 17 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/balena-os/meta-balena | 2026-11-11 | PRIMARY | commit pin `48184b689a43` | — |
| 2 | github.com/balena-os/balena-supervisor | 2026-11-11 | PRIMARY | commit pin `321c7d3718ba` | — |
| 3 | github.com/balena-os/balena-jetson-orin | 2026-11-11 | PRIMARY | commit pin `862a3522f429` | — |
| 4 | github.com/balena-os/balena-raspberrypi | 2026-11-11 | PRIMARY | commit pin `64e81417cba3` | — |
| 5 | github.com/balena-os/balena-engine | 2026-11-11 | PRIMARY | commit pin `68537442895e` | — |
| 6 | github.com/balena-io/open-balena | 2026-11-11 | PRIMARY | commit pin `7b2247d5ddb5` | — |
| 7 | github.com/balena-io/docs | 2026-11-11 | PRIMARY | commit pin `6b962939c0d6` | — |
| 8 | github.com/balena-io-experimental/balenamcp | 2026-11-11 | PRIMARY-METADATA | commit pin `e3cce179c503` | — |
| 9 | github.com/balena-os/balena-yocto-scripts | 2026-11-11 | PRIMARY | commit pin `436cae1eb39b` | — |
| 10 | https://github.com/balena-os/balena-jetson-orin/issues/636 | 2026-11-11 | — | — | C-TD-balenaos-046 |
| 11 | https://github.com/balena-os/meta-balena/issues/2301 | 2021-08-26 | — | — | C-TD-balenaos-047 |
| 12 | https://github.com/balena-os/meta-balena/issues/2833 | 2022-10-27 | — | — | C-TD-balenaos-048 |
| 13 | https://github.com/balena-os/balena-raspberrypi/issues/1146 | 2024-07-02 | — | — | C-TD-balenaos-049 |
| 14 | https://www.balena.io/pricing | 2026-11-11 | PRIMARY | saved: `W16/balena-pricing.txt` | C-TD-balenaos-052 |
| 15 | https://www.prnewswire.com/news-releases/balena-raises-14-4m-to-expand-team-and-bring-edge-computing-to-every-developer-300890087.html | 2026-11-11 | PRIMARY | saved: `prnewswire-2019-series-b.txt` | C-TD-balenaos-054 |
| 16 | https://blog.balena.io/balena-docs-platform-migration-to-gitbook/ | 2026-11-11 | PRIMARY | saved: `blog-gitbook-mcp.txt` | C-TD-balenaos-056 |
| 17 | balena-io/docs@6b96293 | 2026-11-11 | PRIMARY | commit pin `6b96293` | C-TD-balenaos-015, 021, 022, 027…030, 036…040, 053, 058…060 |

### TD-casaos-zimaos

Tag file: [`evidence/sources/TD-casaos-zimaos.md`](evidence/sources/TD-casaos-zimaos.md) · 4 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://get.casaos.io | 2026-11-11 | — | hash only `4a9e7c4ba4159aa7…` (copy not in repo) | C-TD-casaos-zimaos-022 |
| 2 | https://www.zimaspace.com/zimaos | 2026-11-11 | — | saved: `TD-casaos-zimaos/zimaos.txt` | C-TD-casaos-zimaos-035 |
| 3 | https://www.zimaspace.com/zimaos/pricing | 2026-11-11 | — | saved: `TD-casaos-zimaos/zimaos-pricing.txt` | C-TD-casaos-zimaos-032, 033 |
| 4 | https://shop.zimaspace.com/products.json?limit=250 | 2026-11-11 | — | saved: `TD-casaos-zimaos/shop-products-extract.txt` | — |

### TD-flagged

Tag file: [`evidence/sources/TD-flagged.md`](evidence/sources/TD-flagged.md) · 23 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/morluto/rea | 2026-11-10 | PRIMARY | commit pin `e2585aa7ce31` | — |
| 2 | github.com/storytold/craft-anything | 2026-11-10 | PRIMARY | commit pin `4f61975f25d9` | — |
| 3 | github.com/qybaihe/bla | 2026-11-10 | PRIMARY | commit pin `3e53a1e5b63f` | — |
| 4 | github.com/getumbrel/umbrel LICENSE.md | 2026-11-10 | PRIMARY | commit pin `c43beed96407` | — |
| 5 | github.com/gitleaks/gitleaks config/gitleaks.toml | 2026-11-10 | PRIMARY | commit pin `5f6ec56cfa6f` | — |
| 6 | GitHub REST /repos/{morluto/rea, storytold/craft-anything, qybaihe/bla} | 2026-11-10 | PRIMARY-METADATA | saved: `TD-flagged/github-repo-metadata.json` | — |
| 7 | GitHub REST /repos/{r}/commits?since=2026-10-11 (paginated) | 2026-11-10 | PRIMARY-METADATA | saved: `TD-flagged/activity-2026-10-11_to_2026-11-10.txt` | — |
| 8 | GitHub REST /repos/{r}/stargazers and GraphQL stargazers | 2026-11-10 | UNVERIFIED | — | — |
| 9 | GitHub REST /repos/{home-assistant/operating-system, beclab/Olares} (licence field) | 2026-11-10 | PRIMARY-METADATA | — | — |
| 10 | https://api.npmjs.org/downloads/point/{last-week,last-month}/{rea-agents,bla-agents} | 2026-11-10 | PRIMARY-METADATA | — | — |
| 11 | https://registry.npmjs.org/{rea-agents,bla-agents} | 2026-11-10 | PRIMARY-METADATA | — | — |
| 12 | https://github.com/morluto/rea/issues/9317 | 2026-11-10 | PRIMARY | saved: `TD-flagged/rea-issue-9317.txt` | C-TD-flagged-015 |
| 13 | https://www.law.cornell.edu/uscode/text/17/1201 | 2026-11-10 | PRIMARY | — | C-TD-flagged-030 |
| 14 | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024 | 2026-11-10 | PRIMARY | — | C-TD-flagged-031 |
| 15 | https://polyformproject.org/licenses/noncommercial/1.0.0/ | 2026-11-10 | — | saved: `LICENSE.md` | — |
| 16 | HAOS signs RAUC bundles and cosign-signs release checksums | 2026-11-10 | — | — | C-TD-home-assistant-os-012 |
| 17 | umbrelOS 2.1 signed-release trust chain; 2.0.1 runs an unsigned update script | 2026-11-10 | — | — | C-TD-umbrelos-010 |
| 18 | umbrelOS licence FAQ bars commercial forks | 2026-11-10 | — | — | C-TD-umbrelos-045 |
| 19 | Olares release integrity is an MD5 sum, no signature | 2026-11-10 | — | — | C-TD-olares-004 |
| 20 | research/competitors/flagged-repos.md (phase-1 review) | 2026-11-10 | — | saved: `research/competitors/flagged-repos.md` | — |
| 21 | context/03-repo-findings-index.md (REPOS rows, C-38, open items) | 2026-11-10 | — | saved: `context/03-repo-findings-index.md` | — |
| 22 | context/05-research-questions.md (Q297) | 2026-11-10 | — | saved: `context/05-research-questions.md` | — |
| 23 | docs/DECISIONS.md (D-001), docs/ADR-001-foundation.md (D3, security) | 2026-11-10 | — | saved: `docs/ADR-001-foundation.md` | — |

### TD-home-assistant-os

Tag file: [`evidence/sources/TD-home-assistant-os.md`](evidence/sources/TD-home-assistant-os.md) · 22 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/home-assistant/operating-system | 2026-11-10 | PRIMARY | commit pin `fc301f556647` | — |
| 2 | github.com/home-assistant/buildroot (submodule of the above) | 2026-11-10 | PRIMARY | commit pin `5c344b3789e3` | — |
| 3 | github.com/home-assistant/supervisor | 2026-11-10 | PRIMARY | commit pin `c1c6f0a754c0` | — |
| 4 | github.com/home-assistant-libs/securetar (formerly pvizeli/securetar) | 2026-11-10 | PRIMARY | commit pin `224df990ebea` | — |
| 5 | github.com/home-assistant/core (sparse: auth/, components/mcp_server, components/backup) | 2026-11-10 | PRIMARY | commit pin `d8a0dc698c89` | — |
| 6 | github.com/home-assistant/contributors.home-assistant.io (sparse: docs/apps, docs/os) | 2026-11-10 | PRIMARY | commit pin `1fb728335467` | — |
| 7 | TD-home-assistant-os/ha-blog-securetar-v3@6f38b5b4 | 2026-11-10 | PRIMARY | saved: `6f38b5b4.md` | — |
| 8 | https://github.com/home-assistant/operating-system/issues/4632 | 2026-11-10 | PRIMARY | saved: `haos-issue-4632.txt` · sha256 `173dc043df548dbb…` | C-TD-home-assistant-os-042 |
| 9 | https://github.com/home-assistant/operating-system/issues/4845 | 2026-11-10 | PRIMARY | saved: `haos-issue-4845.txt` · sha256 `d3d869fd335c2ced…` | C-TD-home-assistant-os-043 |
| 10 | https://github.com/home-assistant/operating-system/issues/5031 | 2026-11-10 | PRIMARY | saved: `haos-issue-5031.txt` · sha256 `3a49fec79c42d683…` | C-TD-home-assistant-os-044 |
| 11 | https://github.com/home-assistant/operating-system/issues/4785 | 2026-11-10 | PRIMARY | saved: `haos-issue-4785.txt` · sha256 `81ca7a3e2222be80…` | C-TD-home-assistant-os-045 |
| 12 | https://github.com/home-assistant/supervisor/issues/7034 | 2026-11-10 | PRIMARY | saved: `supervisor-issue-7034.txt` · sha256 `481626c67b112bc9…` | C-TD-home-assistant-os-046 |
| 13 | https://github.com/home-assistant/operating-system/pull/4757 | 2026-11-10 | PRIMARY | saved: `haos-pr-4757.txt` · sha256 `23b1c11a3ee8d490…` | C-ARCH5-004; C-TD-home-assistant-os-014; C-W3-024 |
| 14 | https://github.com/home-assistant/operating-system/pull/5053 | 2026-11-10 | PRIMARY | saved: `haos-pr-5053.txt` · sha256 `744ab7b9b4f5b61a…` | C-TD-home-assistant-os-015 |
| 15 | https://github.com/home-assistant/operating-system/releases/tag/18.5 | 2026-11-10 | PRIMARY-METADATA | API response (values quoted in the claim) | C-TD-home-assistant-os-001 |
| 16 | https://github.com/home-assistant/supervisor/releases/tag/2026.11.0 | 2026-11-10 | PRIMARY-METADATA | — | C-TD-home-assistant-os-002 |
| 17 | https://www.openhomefoundation.org/structure/ | 2026-11-10 | PRIMARY | — | C-TD-home-assistant-os-047; C-W16-012 |
| 18 | https://www.home-assistant.io/installation/ | 2026-11-10 | PRIMARY | commit pin `6f38b5b4` | C-REF3-DC-technical-006; C-TD-home-assistant-os-048; C-W8-024 |
| 19 | https://github.com/trailofbits/publications/blob/master/reviews/2026-03-open-home-foundation-securetar-v3-securityreview.pdf | 2026-11-06 | — | saved: `github.com/trailofbits/publications/blob/master/reviews/2026-03-open-home-foundation-securetar-v3-securityreview.pdf` | — |
| 20 | research/platform/verify-updates-rollback-backups-security.md §1–§2 | 2026-11-06 | — | saved: `research/platform/verify-updates-rollback-backups-security.md` | — |
| 21 | context/03-repo-findings-index.md §1 (HAOS rows 105–114) | 2026-11-06 | — | saved: `context/03-repo-findings-index.md` | — |
| 22 | research/competitors/landscape.md §1.4 | 2026-11-06 | — | saved: `research/competitors/landscape.md` | — |

### TD-kairos

Tag file: [`evidence/sources/TD-kairos.md`](evidence/sources/TD-kairos.md) · 43 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | kairos-io/kairos | 2026-11-11 | PRIMARY | commit pin `6f33334a6a6c` | — |
| 2 | kairos-io/kairos-docs | 2026-11-11 | PRIMARY | commit pin `b1bf8bedc436` | — |
| 3 | kairos-io/kairos-operator | 2026-11-11 | PRIMARY | commit pin `7317f4c1ae6e` | — |
| 4 | kairos-io/community | 2026-11-11 | PRIMARY | commit pin `66ce4dd173f7` | — |
| 5 | kairos-io/AuroraBoot | 2026-11-11 | PRIMARY | commit pin `c99b1ac6aefa` | — |
| 6 | images/Dockerfile#L1-L37 | 2026-11-11 | — | — | C-TD-kairos-007 |
| 7 | kairos-init/pkg/values/values.go#L30-L46, #L68-L78 | 2026-11-11 | — | — | C-TD-kairos-008, 009 |
| 8 | kairos-init/pkg/values/packagemaps.go#L957-L976 | 2026-11-11 | — | — | C-TD-kairos-010 |
| 9 | kairos-init/pkg/bundled/jetson_qspi.go#L3-L18 | 2026-11-11 | — | — | C-TD-kairos-017 |
| 10 | kairos-init/pkg/bundled/cloudconfigs/13_nvidia_qspi.yaml#L1-L37 | 2026-11-11 | — | — | C-TD-kairos-018 |
| 11 | agent/pkg/action/upgrade.go#L80-L97, #L186-L240 | 2026-11-11 | — | — | C-TD-kairos-020 |
| 12 | kairos-init/pkg/bundled/cloudconfigs/08_grub.yaml#L5-L44, #L79-L131 | 2026-11-11 | — | — | C-TD-kairos-021 |
| 13 | agent/pkg/utils/common.go#L648-L673, kairos-init/.../08_efi_assessment.yaml#L1-L35 | 2026-11-11 | — | — | C-TD-kairos-023 |
| 14 | agent/pkg/elemental/elemental.go#L451-L462, sdk/types/config/config.go#L48-L50 | 2026-11-11 | — | — | C-TD-kairos-026 |
| 15 | agent/pkg/uki/upgrade.go#L220-L256 | 2026-11-11 | — | — | C-TD-kairos-027 |
| 16 | sdk/bundles/bundles.go#L25, #L182-L282 | 2026-11-11 | — | — | C-TD-kairos-037 |
| 17 | agent/pkg/action/sysext.go#L17-L50 | 2026-11-11 | — | — | C-TD-kairos-038 |
| 18 | kairos-init/pkg/bundled/cloudconfigs/99_sysext.yaml#L47-L110 | 2026-11-11 | — | — | C-TD-kairos-039 |
| 19 | sdk/extensions/catalog.go#L14-L92 | 2026-11-11 | — | — | C-TD-kairos-040 |
| 20 | provider/README.md#L7-L27 | 2026-11-11 | — | saved: `provider/README.md` | C-TD-kairos-042 |
| 21 | immucore/README.md#L253-L275 | 2026-11-11 | — | saved: `immucore/README.md` | C-TD-kairos-044 |
| 22 | kairos-operator@7317f4c1 api/v1alpha1/nodeopupgrade_types.go#L9-L120 | 2026-11-11 | — | commit pin `7317f4c1` | C-TD-kairos-029 |
| 23 | https://api.github.com/repos/kairos-io/kairos/releases | 2026-11-11 | PRIMARY-METADATA | API response (values quoted in the claim) | C-TD-kairos-001 |
| 24 | https://github.com/kairos-io/kairos/releases/tag/v4.4.0 | 2026-11-11 | PRIMARY | saved: `kairos-v4.4.0-release-notes.md` | C-TD-kairos-034 |
| 25 | https://www.cncf.io/projects/kairos/ | 2026-11-11 | PRIMARY | saved: `cncf-projects-kairos-2026-11-11.txt` | C-TD-kairos-004 |
| 26 | https://www.spectrocloud.com/solutions/kairos-support | 2026-11-11 | PRIMARY | saved: `spectrocloud-kairos-support-2026-11-11.txt` | C-TD-kairos-049 |
| 27 | kairos-docs docs/upgrade/boot_assessment.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__docs_upgrade_boot_assessment.md` | C-TD-kairos-022, 024 |
| 28 | kairos-docs docs/examples/boot_assessment_trusted_boot.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__docs_examples_boot_assessment_trusted_boot.md` | C-TD-kairos-025 |
| 29 | kairos-docs docs/installation/edge-devices/raspberry.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__docs_installation_edge-devices_raspberry.md` | C-TD-kairos-011 |
| 30 | kairos-docs docs/installation/edge-devices/nvidia-jetson-images.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__docs_installation_edge-devices_nvidia-jetson-images.md` | C-TD-kairos-015 |
| 31 | kairos-docs docs/installation/edge-devices/nvidia_orin_nx.md | 2026-11-11 | PRIMARY | saved: `docs/installation/edge-devices/nvidia_orin_nx.md` | C-TD-kairos-016 |
| 32 | kairos-docs docs/reference/featuresets.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__docs_reference_featuresets.md` | C-TD-kairos-013, 014 |
| 33 | kairos-docs docs/architecture/immutable.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__docs_architecture_immutable.md` | C-TD-kairos-019, 051 |
| 34 | kairos-docs docs/installation/check-the-signatures.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__docs_installation_check-the-signatures.md` | C-TD-kairos-028 |
| 35 | kairos-docs operator-docs/nodeop-upgrade.md | 2026-11-11 | PRIMARY | saved: `b1bf8bed__operator-docs_nodeop-upgrade.md` | C-TD-kairos-029 |
| 36 | kairos-docs docs/examples/kubeadm-provider.md | 2026-11-11 | PRIMARY | saved: `docs/examples/kubeadm-provider.md` | C-TD-kairos-043 |
| 37 | kairos-docs docs/installation/ (index of install pages) | 2026-11-11 | PRIMARY | — | C-TD-kairos-045 |
| 38 | kairos-docs quickstart/index.md#L77-L83 | 2026-11-11 | PRIMARY | saved: `quickstart/index.md` | C-TD-kairos-046 |
| 39 | kairos-docs docs/integrations/localai.md | 2026-11-11 | PRIMARY | saved: `docs/integrations/localai.md` | C-TD-kairos-050 |
| 40 | kairos-docs blog 2025-08-08 commercial support | 2026-11-11 | PRIMARY | commit pin `b1bf8bed` | C-TD-kairos-048 |
| 41 | kairos-docs blog 2025-12-17 Hadron | 2026-11-11 | PRIMARY | commit pin `b1bf8bed` | C-TD-kairos-047 |
| 42 | community MAINTAINERS.md, ADOPTERS.md | 2026-11-11 | PRIMARY | commit pin `66ce4dd1` | C-TD-kairos-005, 006 |
| 43 | GitHub issues #2010, #2864, #4345, #4969, #5032, #5923, #5965, #6018, #6027 | 2026-11-11 | PRIMARY | saved copy in `sources/TD-kairos/` | C-TD-kairos-012, 024, 030…033, 035, 041 |

### TD-olares

Tag file: [`evidence/sources/TD-olares.md`](evidence/sources/TD-olares.md) · 23 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/beclab/Olares | 2026-11-10 | PRIMARY | commit pin `e7fe1c9634f2` | C-TD-olares-054; C-W18-064 |
| 2 | Olares release 1.12.7 | 2026-11-10 | PRIMARY-METADATA | commit pin `e4a353dfe737` | — |
| 3 | https://github.com/beclab/Olares/releases | 2026-11-10 | PRIMARY-METADATA | API response (values quoted in the claim) | C-TD-olares-002, 057 |
| 4 | https://github.com/beclab/apps | 2026-11-10 | PRIMARY | commit pin `37a1fb4f44b2` | — |
| 5 | https://github.com/beclab/lares | 2026-11-10 | PRIMARY-METADATA | API response (values quoted in the claim) | — |
| 6 | https://github.com/kubernetes/website/blob/4c77b36edb121506e7eb2983777e7c4b49f98ab1/data/releases/eol.yaml | 2026-11-10 | PRIMARY | commit pin `4c77b36edb12` | — |
| 7 | docs/developer/install/versioning.md | 2026-11-10 | PRIMARY | saved: `TD-olares/docs_developer_install_versioning.md` | — |
| 8 | docs/manual/olares/settings/update.md | 2026-11-10 | PRIMARY | saved: `TD-olares/docs_manual_olares_settings_update.md` | — |
| 9 | docs/manual/get-started/install-linux-iso.md | 2026-11-10 | PRIMARY | saved: `TD-olares/docs_manual_get-started_install-linux-iso.md` | — |
| 10 | docs/one/connect-two-olares-one.md | 2026-11-10 | PRIMARY | saved: `TD-olares/docs_one_connect-two-olares-one.md` | — |
| 11 | docs/one/upgrade-multi-node-cluster.md | 2026-11-10 | PRIMARY | saved: `TD-olares/docs_one_upgrade-multi-node-cluster.md` | — |
| 12 | docs/one/spec.md | 2026-11-10 | PRIMARY | saved: `TD-olares/docs_one_spec.md` | — |
| 13 | docs/developer/concepts/network.md | 2026-11-10 | PRIMARY | saved: `TD-olares/docs_developer_concepts_network.md` | — |
| 14 | LICENSE.md (legacy "Olares License") | 2026-11-10 | PRIMARY | saved: `TD-olares/LICENSE.md` | — |
| 15 | docs/developer/concepts/system-architecture.md, docs/manual/get-started/install-olares.md, install-raspberry-pi.md, docs/manual/olares/setti | 2026-11-10 | PRIMARY | saved: `docs/one/update-firmware.md` | — |
| 16 | https://shop.olares.com/products/olares-one | 2026-11-10 | PRIMARY | saved: `TD-olares/shop-olares-one.json` | C-TD-olares-046 |
| 17 | https://github.com/beclab/Olares/issues/4268 | 2026-11-10 | PRIMARY | saved: `TD-olares/issue-4268.json` | C-TD-olares-049 |
| 18 | https://github.com/beclab/Olares/issues/4171 | 2026-11-10 | PRIMARY | saved: `TD-olares/issue-4171.json` | C-TD-olares-050 |
| 19 | https://github.com/beclab/Olares/issues/1716 | 2026-11-10 | PRIMARY | saved: `TD-olares/issue-1716.json` | C-STEEL-etcd-every-box-018; C-TD-olares-051 |
| 20 | https://github.com/beclab/Olares/issues/4185 | 2026-11-10 | PRIMARY | saved: `TD-olares/issue-4185.json` | C-TD-olares-052 |
| 21 | https://github.com/beclab/Olares/issues/2350 | 2026-11-10 | PRIMARY | saved: `TD-olares/issue-2350.json` | C-TD-olares-053 |
| 22 | research/competitors/olares.md (OLA) | 2026-11-10 | — | saved: `research/competitors/olares.md` | — |
| 23 | context/03-repo-findings-index.md | 2026-11-10 | — | saved: `context/03-repo-findings-index.md` | — |

### TD-project-nomad

Tag file: [`evidence/sources/TD-project-nomad.md`](evidence/sources/TD-project-nomad.md) · 18 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/Crosstalk-Solutions/project-nomad | 2026-11-11 | PRIMARY | commit pin `0dbbd21c2f47` | — |
| 2 | same repo, main | 2026-11-11 | PRIMARY | commit pin `c903da48c97b` | — |
| 3 | repos/Crosstalk-Solutions/project-nomad | 2026-11-11 | — | — | C-TD-project-nomad-003 |
| 4 | repos/.../releases and git/refs/tags/v1.35.1 | 2026-11-11 | — | — | C-TD-project-nomad-001 |
| 5 | repos/.../contributors, search/commits (12 months) | 2026-11-11 | — | — | C-TD-project-nomad-004 |
| 6 | #949 app update leaves service down | 2026-11-11 | — | — | C-TD-project-nomad-020 |
| 7 | #858 unchecked containerd growth | 2026-11-11 | — | — | C-TD-project-nomad-037 |
| 8 | #1468 sidecar image not rebuilt | 2026-11-11 | — | — | C-TD-project-nomad-038 |
| 9 | #661 mysql:8.0 needs x86-64-v2 | 2026-11-11 | — | — | C-TD-project-nomad-039 |
| 10 | #400, #1007 UI system update fails | 2026-11-11 | — | — | C-TD-project-nomad-040 |
| 11 | PR #419 ARM64 images; #816 Pi support | 2026-11-11 | — | — | C-TD-project-nomad-041 |
| 12 | #1238 admin-only access | 2026-11-11 | — | — | C-TD-project-nomad-042 |
| 13 | #278 Dozzle shell on unauthenticated port | 2026-11-11 | — | — | C-TD-project-nomad-043 |
| 14 | #715 scheduled backups | 2026-11-11 | — | — | C-TD-project-nomad-035 |
| 15 | https://www.projectnomad.us/ | 2026-11-11 | PRIMARY | Wayback: http://web.archive.org/web/20261105010723/https://www.projectnomad.us/ | C-TD-project-nomad-046 |
| 16 | https://www.projectnomad.us/hardware | 2026-11-11 | PRIMARY | Wayback: http://web.archive.org/web/20261104052914/https://www.projectnomad.us/hardware | C-TD-project-nomad-013 |
| 17 | https://www.projectnomad.us/install | 2026-11-11 | PRIMARY | Wayback: http://web.archive.org/web/20261103051833/https://www.projectnomad.us/install | C-TD-project-nomad-012, 042 |
| 18 | https://www.projectnomad.us/support | 2026-11-11 | PRIMARY | Wayback: http://web.archive.org/web/20261013224855/https://www.projectnomad.us/support | C-TD-project-nomad-031 |

### TD-proxmox-ve

Tag file: [`evidence/sources/TD-proxmox-ve.md`](evidence/sources/TD-proxmox-ve.md) · 23 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/proxmox/pve-installer | 2026-11-11 | PRIMARY | commit pin `ce4ea55a471f` | — |
| 2 | github.com/proxmox/pve-manager | 2026-11-11 | PRIMARY | commit pin `e1e1c4afbe2d` | — |
| 3 | github.com/proxmox/pve-container | 2026-11-11 | PRIMARY | commit pin `15eb5c70bb55` | — |
| 4 | github.com/proxmox/pve-access-control | 2026-11-11 | PRIMARY | commit pin `bbc4ed634272` | — |
| 5 | github.com/proxmox/pve-docs | 2026-11-11 | PRIMARY | commit pin `7742f85bfb53` | — |
| 6 | git.proxmox.com/proxmox-kernel-helper | 2026-11-11 | PRIMARY | commit pin `3b801dcd7bcc` | — |
| 7 | github.com/community-scripts/ProxmoxVE | 2026-11-11 | PRIMARY-METADATA | commit pin `c1e45c1c5192` | — |
| 8 | https://pve.proxmox.com/wiki/Roadmap | 2026-11-11 | PRIMARY | saved: `roadmap.txt` | C-TD-proxmox-ve-001, 025, 026, 035 |
| 9 | https://pve.proxmox.com/wiki/FAQ | 2026-11-11 | PRIMARY | saved: `faq.txt` | C-TD-proxmox-ve-003, 014 |
| 10 | https://pve.proxmox.com/wiki/Upgrade_from_8_to_9 | 2026-11-11 | PRIMARY | saved: `upgrade-8-to-9.txt` | C-TD-proxmox-ve-018 |
| 11 | https://pve.proxmox.com/wiki/Package_Repositories | 2026-11-11 | PRIMARY | saved: `package-repos.txt` | C-TD-proxmox-ve-037 |
| 12 | https://pve.proxmox.com/wiki/Secure_Boot_Setup | 2026-11-11 | PRIMARY | saved: `secure-boot.txt` | — |
| 13 | https://www.proxmox.com/en/products/proxmox-virtual-environment/pricing | 2026-11-11 | PRIMARY | saved: `pricing.txt` | C-TD-proxmox-ve-036; C-W16-028 |
| 14 | https://pdm.proxmox.com/docs/roadmap.html | 2026-11-11 | PRIMARY | saved: `pdm.proxmox.com/docs/roadmap.html` | C-TD-proxmox-ve-040 |
| 15 | https://pbs.proxmox.com/wiki/Roadmap | 2026-11-11 | PRIMARY | saved: `pbs-roadmap.txt` | — |
| 16 | https://git.proxmox.com/?a=project_index | 2026-11-11 | PRIMARY | saved: `git-index.txt` | C-TD-proxmox-ve-008 |
| 17 | https://www.proxmox.com/en/about/company-details/press-releases | 2026-11-11 | SECONDARY | saved: `press.txt` | — |
| 18 | pr-arm64.txt | 2026-11-11 | SECONDARY | saved: `pr-arm64.txt` | — |
| 19 | pr-nvidia-mission-control.txt | 2026-11-11 | SECONDARY | saved: `pr-nvidia-mission-control.txt` | — |
| 20 | pr-20-years.txt | 2026-11-11 | SECONDARY | saved: `pr-20-years.txt` | — |
| 21 | https://forum.proxmox.com/threads/issue-booting-into-grub-after-upgrade-from-proxmox-8-to-9.178482/ | 2026-11-11 | SECONDARY | saved: `forum-grub-8to9.txt` | C-TD-proxmox-ve-019 |
| 22 | https://forum.proxmox.com/threads/broken-boot-after-upgrade-from-8-9.176455/ | 2026-11-11 | SECONDARY | saved: `forum-broken-boot.txt` | C-TD-proxmox-ve-020 |
| 23 | https://forum.proxmox.com/threads/pve-9-beta-pve-nested-upgrade-from-8-to-9-breaks-boot.168662/ | 2026-11-11 | SECONDARY | saved: `forum-nested-beta.txt` | C-TD-proxmox-ve-021 |

### TD-startos

Tag file: [`evidence/sources/TD-startos.md`](evidence/sources/TD-startos.md) · 17 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/Start9Labs/start-technologies | 2026-11-11 | PRIMARY | commit pin `175ce3beb370` | — |
| 2 | Earlier clone at <lab-dir>/src/start-os/ | 2026-11-11 | — | — | C-TD-startos-011; C-W3-048 |
| 3 | https://github.com/Start9Labs/start-technologies/releases/tag/start-os/v0.4.2 | 2026-11-11 | PRIMARY | API response (values quoted in the claim) | C-TD-startos-001, 006, 049, 050 |
| 4 | https://start9.com/server-one | 2026-11-11 | PRIMARY | saved: `start9-server-one.txt` | C-TD-startos-039, 040 |
| 5 | https://start9.com/premium-support | 2026-11-11 | PRIMARY | saved: `start9-premium-support.txt` | C-TD-startos-040 |
| 6 | https://backports.debian.org/ | 2026-11-11 | PRIMARY | saved: `debian-backports.txt` | C-TD-startos-009 |
| 7 | https://github.com/Start9Labs/start-technologies/issues/735 | 2026-11-11 | PRIMARY | saved: `issue-735.txt` | C-TD-startos-033 |
| 8 | https://github.com/Start9Labs/start-technologies/issues/3465 | 2026-11-11 | PRIMARY | saved: `issue-3465.txt` | C-TD-startos-008, 010 |
| 9 | https://github.com/Start9Labs/start-technologies/issues/3923 | 2026-11-11 | PRIMARY | saved: `issue-3923.txt` | C-TD-startos-044 |
| 10 | https://github.com/Start9Labs/start-technologies/issues/4009 | 2026-11-11 | PRIMARY | saved: `issue-4009.txt` | C-TD-startos-046 |
| 11 | https://github.com/Start9Labs/start-technologies/issues/4435 | 2026-11-11 | PRIMARY | saved: `issue-4435.txt` | C-TD-startos-045 |
| 12 | https://github.com/Start9Labs/start-technologies/issues/4454 | 2026-11-11 | PRIMARY | saved: `issue-4454.txt` | C-TD-startos-023 |
| 13 | https://github.com/Start9Labs/start-technologies/issues/4647 | 2026-11-11 | PRIMARY | saved: `issue-4647.txt` | C-TD-startos-008, 043 |
| 14 | https://github.com/Start9Labs/start-technologies/issues/3881 | 2026-11-11 | PRIMARY | — | C-TD-startos-032, 036 |
| 15 | https://api.github.com/repos/Start9Labs/start-technologies/contributors | 2026-11-11 | PRIMARY-METADATA | API response (values quoted in the claim) | C-TD-startos-042 |
| 16 | https://api.github.com/repos/Start9Labs/start-technologies | 2026-11-11 | PRIMARY-METADATA | API response (values quoted in the claim) | C-TD-startos-002 |
| 17 | evidence/sources/W16/start9-coincarp.txt (CoinCarp seed-round page, saved by W16) | 2026-11-11 | SECONDARY | saved: `evidence/sources/W16/start9-coincarp.txt` | C-TD-startos-041 |

### TD-talos

Tag file: [`evidence/sources/TD-talos.md`](evidence/sources/TD-talos.md) · 15 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/siderolabs/talos | 2026-11-11 | PRIMARY | commit pin `dad8d3edfe7c` | — |
| 2 | github.com/siderolabs/extensions | 2026-11-11 | PRIMARY | commit pin `8db133ae509f` | — |
| 3 | github.com/siderolabs/image-factory | 2026-11-11 | PRIMARY | commit pin `c9c1f3946ddb` | — |
| 4 | github.com/siderolabs/omni | 2026-11-11 | PRIMARY | commit pin `bcbb0eff06a6` | — |
| 5 | github.com/siderolabs/docs (source of docs.siderolabs.com) | 2026-11-11 | PRIMARY | commit pin `9cddec20fd08` | — |
| 6 | github.com/siderolabs/sbc-raspberrypi | 2026-11-11 | PRIMARY | commit pin `9fa9252cca1a` | — |
| 7 | github.com/siderolabs/sbc-jetson | 2026-10-26 | PRIMARY | commit pin `6468a58b8d11` | C-W2-038 |
| 8 | github.com/siderolabs/talos/releases/tag/v1.14.5 | 2026-11-11 | PRIMARY | — | — |
| 9 | GitHub API: repos/siderolabs/talos/commits?since=2025-11-11, /contributors | 2026-11-11 | PRIMARY-METADATA | — | — |
| 10 | https://www.siderolabs.com/pricing/ | 2026-11-11 | PRIMARY | saved: `siderolabs-pricing-2026-11-11.txt` · sha256 `987eb9d9faa7162d…` | C-REF3-DC-cost-004; C-TD-talos-037 |
| 11 | https://www.siderolabs.com/platform/talos-os-for-kubernetes/ | 2026-11-11 | PRIMARY | saved: `siderolabs-talos-platform-2026-11-11.txt` · sha256 `78c9351b41af48b5…` | C-TD-talos-038 |
| 12 | https://github.com/siderolabs/talos/issues/14260 | 2026-11-11 | PRIMARY | saved: `talos-issue-14260.txt` · sha256 `5c22237b0a1fe440…` | C-TD-talos-020 |
| 13 | https://github.com/siderolabs/talos/issues/14000 | 2026-11-11 | PRIMARY | saved: `talos-issue-14000.txt` · sha256 `b58b04c89678a010…` | C-TD-talos-021 |
| 14 | https://github.com/siderolabs/talos/issues/14061 | 2026-11-11 | PRIMARY | saved: `talos-issue-14061.txt` · sha256 `6c3b9b10279be178…` | C-TD-talos-022 |
| 15 | https://github.com/siderolabs/talos/issues/14002 | 2026-11-11 | PRIMARY | saved: `talos-issue-14002.txt` · sha256 `628b2e12a50cc1eb…` | C-TD-talos-023 |

### TD-tier-c-alt

Tag file: [`evidence/sources/TD-tier-c-alt.md`](evidence/sources/TD-tier-c-alt.md) · 28 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/HeyPuter/puter | 2026-11-11 | PRIMARY | commit pin `44bf99f80840` | — |
| 2 | github.com/sandstorm-io/sandstorm | 2026-11-11 | PRIMARY | commit pin `5c7c29c16f45` | — |
| 3 | github.com/sandstorm-io/sandstorm (master) | 2026-11-11 | PRIMARY | commit pin `a97cf3ee19d3` | — |
| 4 | salsa.debian.org/freedombox-team/freedombox | 2026-11-11 | PRIMARY | commit pin `fadba12ed288` | — |
| 5 | github.com/openclaw/openclaw (LICENSE only) | 2026-11-11 | PRIMARY | commit pin `926ce0a6f6f5` | — |
| 6 | github.com/NousResearch/hermes-agent (LICENSE only) | 2026-11-11 | PRIMARY | commit pin `9373dc1e315a` | — |
| 7 | repos/HeyPuter/puter, /releases, /contributors | 2026-11-11 | — | — | C-TD-tier-c-alt-012 |
| 8 | repos/sandstorm-io/sandstorm, /tags | 2026-11-11 | — | — | C-TD-tier-c-alt-027 |
| 9 | repos/openclaw/openclaw, repos/NousResearch/hermes-agent | 2026-11-11 | — | — | C-TD-tier-c-alt-049, 050 |
| 10 | https://puter.com/ | 2026-11-11 | PRIMARY | saved: `puter-root.txt` | C-TD-tier-c-alt-011 |
| 11 | https://sandstorm.org/ | 2026-11-11 | PRIMARY | saved: `sandstorm-org.txt` | C-TD-tier-c-alt-023, 026 |
| 12 | https://sandstorm.io/ | 2026-11-11 | PRIMARY | saved: `sandstorm-io.txt` | C-TD-tier-c-alt-026 |
| 13 | https://sandstorm.io/news/2019-09-15-shutting-down-oasis | 2026-11-11 | PRIMARY | saved: `sandstorm-oasis.txt` | C-TD-tier-c-alt-025 |
| 14 | https://freedombox.org/ | 2026-11-11 | PRIMARY | saved: `fbx-root.txt` | C-TD-tier-c-alt-030 |
| 15 | https://freedombox.org/download/ | 2026-11-11 | PRIMARY | saved: `fbx-download.txt` | C-TD-tier-c-alt-038 |
| 16 | https://freedombox.org/download/pioneer/ | 2026-11-11 | PRIMARY | saved: `fbx-pioneer.txt` | C-TD-tier-c-alt-039 |
| 17 | https://freedombox.org/buy/ | 2026-11-11 | PRIMARY | saved: `fbx-buy.txt` | C-TD-tier-c-alt-040 |
| 18 | https://clawbox.com/home-ai-server | 2026-11-11 | PRIMARY | saved: `clawbox-home.txt` | C-TD-tier-c-alt-045, 048 |
| 19 | https://clawbox.com/hermes | 2026-11-11 | PRIMARY | saved: `cb-hermes.txt` | C-TD-tier-c-alt-042, 045 |
| 20 | https://clawbox.com/blog/2026-05-28-openclaw-hardware-requirements-2026-the-complete-guide | 2026-11-11 | PRIMARY | saved: `clawbox-hwreq.txt` | C-TD-tier-c-alt-042 |
| 21 | https://clawbox.com/faq | 2026-11-11 | PRIMARY | saved: `cb-faq.txt` | C-TD-tier-c-alt-044, 046 |
| 22 | https://clawbox.com/clawbox-price | 2026-11-11 | PRIMARY | saved: `cb-clawbox-price.txt` | C-TD-tier-c-alt-044 |
| 23 | https://clawbox.com/clawbox-workstation | 2026-11-11 | PRIMARY | saved: `cb-clawbox-workstation.txt` | C-TD-tier-c-alt-047 |
| 24 | https://clawbox.com/terms | 2026-11-11 | PRIMARY | saved: `cb-terms.txt` | C-TD-tier-c-alt-046 |
| 25 | https://ubuntu.com/about/release-cycle | 2026-11-11 | PRIMARY | saved: `ubuntu-release-cycle.txt` | C-TD-tier-c-alt-043 |
| 26 | https://www.tomshardware.com/tech-industry/artificial-intelligence/setting-up-openclaw-isnt-as-straightforward-as-the-internet-wants-you-to-think-r… | 2026-11-11 | SECONDARY | saved: `toms-openclaw.txt` | C-TD-tier-c-alt-051 |
| 27 | https://acemagic.com/blogs/about-ace-mini-pc/best-mini-pc-for-openclaw | 2026-11-11 | PRIMARY | saved: `acemagic-openclaw.txt` | C-TD-tier-c-alt-052 |
| 28 | https://snyk.io/articles/clawdhub-malicious-campaign-ai-agent-skills/ | 2026-11-11 | SECONDARY | saved: `snyk-clawdhub.txt` | C-TD-tier-c-alt-053 |

### TD-tier-c-nas

Tag file: [`evidence/sources/TD-tier-c-nas.md`](evidence/sources/TD-tier-c-nas.md) · 22 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://hexos.com/ | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `d70cce8f541a9667…` | C-TD-tier-c-nas-029 |
| 2 | https://hexos.com/faq | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `bf406d6b071e95a4…` | C-TD-tier-c-nas-020, 024 |
| 3 | https://hexos.com/hardware | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `f0db6094b244ad01…` | C-TD-tier-c-nas-024 |
| 4 | https://docs.hexos.com/getting-started/installation/InstallGuide | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `b013cd930b29af85…` | C-TD-tier-c-nas-018, 019 |
| 5 | https://docs.hexos.com/release-notes/command-deck | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `1af5eb49685f9d83…` | C-TD-tier-c-nas-022 |
| 6 | https://docs.hexos.com/release-notes/command-deck/2026-04-21 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `db6c308e0312f590…` | C-TD-tier-c-nas-020 |
| 7 | https://docs.hexos.com/release-notes/command-deck/2026-11-06 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `2dacb89a8f635af9…` | C-TD-tier-c-nas-027, 028 |
| 8 | https://docs.hexos.com/release-notes/command-deck/2026-11-10 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `8e2eddc082332515…` | C-TD-tier-c-nas-026 |
| 9 | https://www.synology.com/en-global/releaseNote/DSM | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `4449b1edb81ded25…` | C-TD-tier-c-nas-031…034, 042 |
| 10 | https://archive.synology.com/download/ToolChain/Synology%20NAS%20GPL%20Source/7.4-90080 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `a46f61c79080875c…` | C-TD-tier-c-nas-035 |
| 11 | https://help.synology.com/developer-guide/breaking_changes.html | 2026-11-11 | — | saved: `help.synology.com/developer-guide/breaking_changes.html` · sha256 `8cb9a461130737a4…` | C-TD-tier-c-nas-036 |
| 12 | https://help.synology.com/developer-guide/toolkit/sign_package.html | 2026-11-11 | — | saved: `help.synology.com/developer-guide/toolkit/sign_package.html` · sha256 `4a1b264469b0b631…` | C-TD-tier-c-nas-036 |
| 13 | https://help.synology.com/developer-guide/privilege/preface.html | 2026-11-11 | — | saved: `help.synology.com/developer-guide/privilege/preface.html` · sha256 `5c9d8e1800f71e1a…` | C-TD-tier-c-nas-036 |
| 14 | https://www.synology.com/en-global/dsm/7.4/software_spec/ai_console | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `5dd3db1674143eca…` | C-TD-tier-c-nas-037 |
| 15 | https://www.synology.com/en-global/company/news/article/dsm73 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `2671017ec0ac70cf…` | C-TD-tier-c-nas-038 |
| 16 | https://www.synology.com/en-us/DSM74 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `6d52f18c27bc2d4f…` | C-TD-tier-c-nas-039 |
| 17 | https://www.synology.com/en-us/DSM73 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `9aeb2d7cb728bbf4…` | C-TD-tier-c-nas-039 |
| 18 | https://www.synology.com/releaseNote/ContainerManager | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `4e55a6ae2d99b9c7…` | C-TD-tier-c-nas-040 |
| 19 | https://www.synology.com/en-global/products/status/eol-dsm62 | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `5730f54c63533001…` | C-TD-tier-c-nas-041 |
| 20 | https://www.synology.com/en-global/products/status | 2026-11-11 | — | saved copy in `sources/TD-tier-c-nas/` · sha256 `1ce94237c839ba63…` | C-TD-tier-c-nas-041 |
| 21 | https://unraid.net/pricing | 2026-11-11 | — | saved: `W16/unraid-pricing.txt` · sha256 `a3f2bcd990ee0d3b…` | C-W16-029 |
| 22 | https://www.xda-developers.com/hexos-finally-manage-nas-locally-instead-cloud-fixes-flaw/ | 2026-11-11 | SECONDARY | — | C-TD-tier-c-nas-023 |

### TD-tier-c-robotics

Tag file: [`evidence/sources/TD-tier-c-robotics.md`](evidence/sources/TD-tier-c-robotics.md) · 42 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/viamrobotics/agent | 2026-11-11 | PRIMARY | commit pin `6d641fa60f76` | — |
| 2 | github.com/viamrobotics/rdk | 2026-11-11 | PRIMARY | commit pin `046082ec9d51` | — |
| 3 | github.com/viamrobotics/micro-rdk | 2026-11-11 | PRIMARY-METADATA | commit pin `b03697b75c7d` | — |
| 4 | github.com/foxglove/foxglove-sdk | 2026-11-11 | PRIMARY | commit pin `8dc7525eda8c` | — |
| 5 | github.com/FormantIO/formant | 2026-11-11 | PRIMARY | commit pin `64bcdb0dbafe` | — |
| 6 | github.com/ros2/ros2_documentation | 2026-11-11 | PRIMARY | commit pin `1c5c20cb9f14` | — |
| 7 | https://docs.formant.io/docs/the-formant-agent.md | 2026-11-11 | PRIMARY | saved: `docs.formant.io/docs/the-formant-agent.md` | C-TD-tier-c-robotics-001, 002, 007 |
| 8 | https://docs.formant.io/docs/system-requirements.md | 2026-11-11 | PRIMARY | saved: `docs.formant.io/docs/system-requirements.md` | C-TD-tier-c-robotics-003, 006, 014 |
| 9 | https://docs.formant.io/docs/getting-started-install-the-formant-agent.md | 2026-11-11 | PRIMARY | saved: `docs.formant.io/docs/getting-started-install-the-formant-agent.md` | C-TD-tier-c-robotics-004 |
| 10 | https://docs.formant.io/docs/install-formant-agent-apt.md | 2026-11-11 | PRIMARY | saved: `docs.formant.io/docs/install-formant-agent-apt.md` | C-TD-tier-c-robotics-005 |
| 11 | https://docs.formant.io/docs/agent-faq.md | 2026-11-11 | PRIMARY | saved: `docs.formant.io/docs/agent-faq.md` | C-TD-tier-c-robotics-005 |
| 12 | https://docs.formant.io/docs/getting-started-install-agent-docker-ros-2.md | 2026-11-11 | PRIMARY | saved: `docs.formant.io/docs/getting-started-install-agent-docker-ros-2.md` | — |
| 13 | https://docs.formant.io/docs/terminal-and-port-forwarding-security.md | 2026-11-11 | PRIMARY | saved: `docs.formant.io/docs/terminal-and-port-forwarding-security.md` | C-TD-tier-c-robotics-008 |
| 14 | https://docs.formant.io/llms.txt | 2026-11-11 | PRIMARY | saved: `docs.formant.io/llms.txt` | C-TD-tier-c-robotics-015 |
| 15 | formant-channel.txt, formant-fleetmgmt.txt, formant-adapters-faq.txt | 2026-11-11 | PRIMARY | saved: `formant-adapters-faq.txt` | — |
| 16 | https://formant.io/terms-of-service | 2026-11-11 | PRIMARY | saved: `formant-tos.txt` | C-TD-tier-c-robotics-009 |
| 17 | https://formant.io/ | 2026-11-11 | PRIMARY | saved: `formant-home.txt` | C-TD-tier-c-robotics-013 |
| 18 | https://www.silicon.co.uk/press-release/formant-f3-brings-generative-ai-and-agentic-reasoning-to-robot-ops | 2026-11-11 | SECONDARY | saved: `formant-f3-SECONDARY.txt` | C-TD-tier-c-robotics-011 |
| 19 | https://www.therobotreport.com/formant-brings-in-21m-to-expand-enterprise-focus/ | 2026-11-11 | SECONDARY | saved: `formant-21m-SECONDARY.txt` | C-TD-tier-c-robotics-012 |
| 20 | https://docs.foxglove.dev/docs/fleet | 2026-11-11 | PRIMARY | saved: `foxglove-foxlet-faq.txt` | C-TD-tier-c-robotics-020 |
| 21 | https://docs.foxglove.dev/docs/fleet/foxlet/installation | 2026-11-11 | PRIMARY | saved: `foxglove-foxlet-install.txt` | C-TD-tier-c-robotics-021 |
| 22 | https://docs.foxglove.dev/docs/fleet/bridge | 2026-11-11 | PRIMARY | saved: `foxglove-bridge.txt` | — |
| 23 | https://docs.foxglove.dev/docs/fleet/remote-access | 2026-11-11 | PRIMARY | saved: `foxglove-remote-access.txt` | C-TD-tier-c-robotics-022 |
| 24 | https://docs.foxglove.dev/docs/data/edge-sites | 2026-11-11 | PRIMARY | saved: `foxglove-edge-sites.txt` | C-TD-tier-c-robotics-023 |
| 25 | https://docs.foxglove.dev/docs/data/primary-sites/installation | 2026-11-11 | PRIMARY | saved: `foxglove-primary-onprem.txt` | C-TD-tier-c-robotics-024 |
| 26 | https://foxglove.dev/pricing | 2026-11-11 | PRIMARY | saved: `foxglove-reduced-pricing.txt` | C-TD-tier-c-robotics-025 |
| 27 | https://foxglove.dev/blog/foxglove-vs-foxglove-studio-two-years-on | 2026-11-11 | PRIMARY | saved: `foxglove-twoyears.txt` | C-TD-tier-c-robotics-026 |
| 28 | https://docs.foxglove.dev/docs/agents | 2026-11-11 | PRIMARY | saved: `foxglove-mcp-server.txt` | C-TD-tier-c-robotics-028, 029 |
| 29 | https://docs.foxglove.dev/docs/standalone-license | 2026-11-11 | PRIMARY | saved: `foxglove-standalone.txt` | C-TD-tier-c-robotics-030 |
| 30 | https://docs.foxglove.dev/llms.txt | 2026-11-11 | PRIMARY | saved: `docs.foxglove.dev/llms.txt` | — |
| 31 | https://docs.viam.com/reference/viam-agent/ | 2026-11-11 | PRIMARY | saved: `viam-agent.txt` | C-TD-tier-c-robotics-043, 044, 046, 050, 057 |
| 32 | https://docs.viam.com/fleet/manage-versions/ | 2026-11-11 | PRIMARY | saved: `viam-manage-versions.txt` | C-TD-tier-c-robotics-044, 049 |
| 33 | https://docs.viam.com/reference/viam-server/ | 2026-11-11 | PRIMARY | saved: `viam-server-ref.txt` | C-TD-tier-c-robotics-048 |
| 34 | https://docs.viam.com/reference/mcp/ | 2026-11-11 | PRIMARY | saved: `viam-mcp.txt` | C-TD-tier-c-robotics-051, 056 |
| 35 | https://docs.viam.com/build-apps/use-viam-from-an-agent/ | 2026-11-11 | PRIMARY | saved: `viam-agent-guide.txt` | C-TD-tier-c-robotics-052, 055 |
| 36 | https://docs.viam.com/hardware/ai-assistant/ | 2026-11-11 | PRIMARY | saved: `viam-ai-assistant.txt` | C-TD-tier-c-robotics-053 |
| 37 | https://docs.viam.com/set-up-a-machine/first-machine/ | 2026-11-11 | PRIMARY | saved: `viam-first-machine.txt` | C-TD-tier-c-robotics-056 |
| 38 | https://www.viam.com/pricing | 2026-11-11 | PRIMARY | saved: `viam-pricing.txt` | C-TD-tier-c-robotics-054 |
| 39 | https://docs.viam.com/llms.txt | 2026-11-11 | PRIMARY | saved: `docs.viam.com/llms.txt` | — |
| 40 | https://balena.io/industries/robotics | 2026-11-11 | PRIMARY | saved: `balena-industries-robotics.txt` | C-TD-tier-c-robotics-070 |
| 41 | https://forums.balena.io/t/anyone-here-using-balenaos-for-robotics/36362 | 2026-11-11 | SECONDARY | saved: `balena-forum-robotics.txt` | C-TD-tier-c-robotics-072 |
| 42 | https://discourse.openrobotics.org/t/automatic-deployment-of-ros2-based-system-to-remote-devices-dual-copy-or-containers/33884 | 2026-11-11 | SECONDARY | saved: `ros-discourse-dualcopy.txt` | C-TD-tier-c-robotics-073 |

### TD-tier-c-selfhost

Tag file: [`evidence/sources/TD-tier-c-selfhost.md`](evidence/sources/TD-tier-c-selfhost.md) · 16 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://cosmos-cloud.io/pricing | 2026-11-11 | — | saved: `cosmos-pricing.txt` · sha256 `9a487061bd8f22d5…` | C-TD-tier-c-selfhost-009 |
| 2 | https://cosmos-cloud.io/ | 2026-11-11 | — | saved: `cosmos-home.txt` · sha256 `fd8ebbfa1eb8331c…` | C-TD-tier-c-selfhost-013 |
| 3 | https://yunohost.org/roadmap.en.html | 2026-11-11 | — | saved: `ynh-roadmap.txt` · sha256 `c8979305ead2a38d…` | C-TD-tier-c-selfhost-022 |
| 4 | https://doc.yunohost.org/en/admin/get_started/install_on/raspberry_pi/ | 2026-11-11 | — | saved: `ynh-pi.txt` · sha256 `08e4038bc43f5902…` | C-TD-tier-c-selfhost-028 |
| 5 | https://forum.yunohost.org/t/yunohost-13-0-trixie-spooky-beta/40656 | 2026-11-11 | — | hash only `51bc4e9333a7b7c4…` (copy not in repo) | C-TD-tier-c-selfhost-029 |
| 6 | https://donate.yunohost.org/ | 2026-11-11 | — | — | C-TD-tier-c-selfhost-030 |
| 7 | https://runtipi.io/docs/quick-start | 2026-11-11 | — | saved: `runtipi-qs.txt` · sha256 `d668dc317951a837…` | C-TD-tier-c-selfhost-047 |
| 8 | https://www.cloudron.io/pricing.html | 2026-11-11 | — | saved: `cloudron-pricing.txt` · sha256 `46d3741fb1eb58c3…` | C-TD-tier-c-selfhost-067, 068 |
| 9 | https://docs.cloudron.io/installation/ | 2026-11-11 | — | saved: `cloudron-req.txt` · sha256 `0a495d1baf909e20…` | C-TD-tier-c-selfhost-061 |
| 10 | https://docs.cloudron.io/updates/ | 2026-11-11 | — | saved: `cloudron-updates.txt` · sha256 `505cd990fbe1302e…` | C-TD-tier-c-selfhost-063, 068 |
| 11 | https://docs.cloudron.io/packaging/manifest/ | 2026-11-11 | — | saved: `cloudron-packaging.txt` · sha256 `6b934498ba7a1b21…` | C-TD-tier-c-selfhost-066 |
| 12 | https://coolify.io/pricing/ | 2026-11-11 | — | saved: `coolify-pricing.txt` · sha256 `abd8186938196884…` | C-TD-tier-c-selfhost-087 |
| 13 | https://coolify.io/docs/get-started/installation | 2026-11-11 | — | saved: `coolify-req.txt` · sha256 `950420ac6a68cb5a…` | C-TD-tier-c-selfhost-086 |
| 14 | https://dokploy.com/pricing | 2026-11-11 | — | saved: `dokploy-pricing.txt` · sha256 `8a75e5d89e91fa42…` | C-TD-tier-c-selfhost-108 |
| 15 | https://docs.dokploy.com/docs/core/installation | 2026-11-11 | — | saved: `dokploy-req.txt` · sha256 `7206afcdab294f30…` | C-TD-tier-c-selfhost-103 |
| 16 | https://docs.dokploy.com/docs/core/ai | 2026-11-11 | — | saved: `dokploy-ai.txt` · sha256 `98a552182fe6c211…` | C-TD-tier-c-selfhost-106 |

### TD-truenas-scale

Tag file: [`evidence/sources/TD-truenas-scale.md`](evidence/sources/TD-truenas-scale.md) · 20 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.truenas.com/software-status/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `e73565277b11924d…` | C-TD-truenas-scale-001, 040 |
| 2 | https://www.truenas.com/docs/scale/27/gettingstarted/versionnotes/ | 2026-11-11 | — | Wayback: http://web.archive.org/web/20261029160152/https://www.truenas.com/docs/scale/27/gettingstarted/versionnotes/ | C-TD-truenas-scale-002, 006, 016, 039 |
| 3 | https://www.truenas.com/docs/scale/26/gettingstarted/versionnotes/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `740763e54cda0119…` | C-TD-truenas-scale-030, 031 |
| 4 | https://www.truenas.com/docs/scale/25.10/gettingstarted/versionnotes/ | 2026-11-11 | — | Wayback: http://web.archive.org/web/20261101222433/https://www.truenas.com/docs/scale/25.10/gettingstarted/versionnotes/ | C-TD-truenas-scale-006, 014, 033, 038 |
| 5 | https://www.truenas.com/blog/smarter-and-streamlined-updates-with-truenas-25-10 | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `3b7341a236a11057…` | C-TD-truenas-scale-011, 038 |
| 6 | https://www.truenas.com/docs/scale/25.10/gettingstarted/scalehardwareguide/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `6eb7e3b3719c0cd9…` | C-TD-truenas-scale-015 |
| 7 | https://www.truenas.com/docs/scale/25.10/scaletutorials/systemsettings/updatescale/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `3e952706c0a71e98…` | C-TD-truenas-scale-029 |
| 8 | https://www.truenas.com/docs/scale/25.10/scaletutorials/dataprotection/truecloudtasks/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `d9f65ed702693e07…` | C-TD-truenas-scale-028 |
| 9 | https://www.truenas.com/docs/scale/27/systemsettings/advanced/advancedsettings/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `09f81d90090caaea…` | C-TD-truenas-scale-032 |
| 10 | https://www.truenas.com/docs/solutions/optimizations/stigcompliance/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `35024a063c2bc310…` | C-TD-truenas-scale-032 |
| 11 | https://www.truenas.com/blog/building-a-bridge-between-community-enterprise | 2026-11-11 | — | Wayback: http://web.archive.org/web/20260918184834/https://www.truenas.com/blog/building-a-bridge-between-community-enterprise/ | C-TD-truenas-scale-036 |
| 12 | https://connect.truenas.com/pricing/ | 2026-11-11 | — | Wayback: http://web.archive.org/web/20261108191831/https://connect.truenas.com/pricing/ | C-TD-truenas-scale-037 |
| 13 | https://www.truenas.com/blog/truenas-plans-for-2026 | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `74b5e42acb13a654…` | — |
| 14 | https://www.truenas.com/blog/blog-truenas-26-beta1-release/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `d24105b575ac2fa5…` | — |
| 15 | https://www.truenas.com/docs/scale/25.10/scaleuireference/apps/ | 2026-11-11 | — | saved copy in `sources/TD-truenas-scale/` · sha256 `3442d4e5ce314cd2…` | — |
| 16 | https://forums.truenas.com/t/the-future-of-electric-eel-and-apps/5409 | 2026-11-11 | PRIMARY | saved copy in `sources/TD-truenas-scale/` · sha256 `c904e5467fa86260…` | C-TD-truenas-scale-017 |
| 17 | https://forums.truenas.com/t/k3s-server-uses-10-cpu-for-no-reason/6034 | 2026-11-11 | SECONDARY | saved copy in `sources/TD-truenas-scale/` · sha256 `d21291a2d2737935…` | C-TD-truenas-scale-019 |
| 18 | https://forums.truenas.com/t/potential-k3s-database-corruption-issue-need-assistance/9038 | 2026-11-11 | SECONDARY | saved copy in `sources/TD-truenas-scale/` · sha256 `66f647af90e36aea…` | C-W5-052 |
| 19 | https://forums.truenas.com/t/truenas-labs-mcp-server/63816 | 2026-11-11 | PRIMARY | saved copy in `sources/TD-truenas-scale/` · sha256 `e4d92bdfbd245eb5…` | C-TD-truenas-scale-034 |
| 20 | https://forums.truenas.com/t/secureboot-is-necessary-for-truenas-attention-all-users/13691 | 2026-11-11 | SECONDARY | saved copy in `sources/TD-truenas-scale/` · sha256 `8e4ab9152ee8b322…` | C-TD-truenas-scale-033 |

### TD-umbrelos

Tag file: [`evidence/sources/TD-umbrelos.md`](evidence/sources/TD-umbrelos.md) · 22 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/getumbrel/umbrel | 2026-11-10 | PRIMARY | commit pin `a72dac249974` | — |
| 2 | github.com/getumbrel/umbrel-apps | 2026-11-10 | PRIMARY | commit pin `51aac978c67c` | — |
| 3 | github.com/silitics/rugix | 2026-11-10 | PRIMARY-METADATA | commit pin `a455ea393326` | — |
| 4 | https://github.com/getumbrel/umbrel/releases | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261009194712/https://github.com/getumbrel/umbrel/releases/tag/2.0.0 | C-TD-umbrelos-001 |
| 5 | https://umbrel.com/support/basics/updating-umbrelos | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261015040551/https://umbrel.com/support/basics/updating-umbrelos | C-TD-umbrelos-024 |
| 6 | https://umbrel.com/support/backups-and-recovery/backing-up-your-data | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261102030304/https://umbrel.com/support/backups-and-recovery/backing-up-your-data | C-TD-umbrelos-032; C-W5-048 |
| 7 | https://umbrel.com/support/storage/managing-your-storage | 2026-11-10 | PRIMARY | saved: `TD-umbrelos/umbrel-support-storage_managing-your-storage.txt` | C-TD-umbrelos-043 |
| 8 | https://umbrel.com/support/advanced/connecting-ai-agents | 2026-11-10 | PRIMARY | saved: `TD-umbrelos/umbrel-support-advanced_connecting-ai-agents.txt` | C-TD-umbrelos-039 |
| 9 | https://umbrel.com/support/basics/sharing-your-umbrel-with-other-users | 2026-11-10 | PRIMARY | saved: `TD-umbrelos/umbrel-support-basics_sharing-your-umbrel-with-other-users.txt` | C-TD-umbrelos-033 |
| 10 | https://umbrel.com/support/apps/running-custom-docker-containers | 2026-11-10 | PRIMARY | saved: `TD-umbrelos/umbrel-support-apps_running-custom-docker-containers.txt` | C-TD-umbrelos-057 |
| 11 | https://store.umbrel.com/products.json | 2026-11-10 | PRIMARY | saved: `TD-umbrelos/umbrel-store-products.json` | C-TD-umbrelos-047; C-W10-018, 050 |
| 12 | https://umbrel.com/umbrel-home | 2026-11-10 | PRIMARY | — | — |
| 13 | https://umbrel.com/umbrel-pro | 2026-11-10 | PRIMARY | — | C-TD-umbrelos-046 |
| 14 | https://github.com/getumbrel/umbrel/wiki/License-FAQ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260309061923/https://github.com/getumbrel/umbrel/wiki/License-FAQ | C-TD-umbrelos-045 |
| 15 | https://rugix.org/docs/ctrl/over-the-air-updates | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260608053547/https://rugix.org/docs/ctrl/over-the-air-updates/ | C-TD-umbrelos-021 |
| 16 | https://github.com/getumbrel/umbrel/issues/2072 | 2026-11-10 | PRIMARY | — | C-TD-umbrelos-050 |
| 17 | https://github.com/getumbrel/umbrel/issues/2190 | 2026-11-10 | PRIMARY | — | C-TD-umbrelos-051 |
| 18 | https://github.com/getumbrel/umbrel/issues/2245 | 2026-11-10 | PRIMARY | — | C-TD-umbrelos-052 |
| 19 | https://github.com/getumbrel/umbrel/issues/2124 | 2026-11-10 | PRIMARY | — | C-TD-umbrelos-053 |
| 20 | https://github.com/getumbrel/umbrel/issues/2298 | 2026-11-10 | PRIMARY | — | C-TD-umbrelos-054 |
| 21 | https://github.com/getumbrel/umbrel/issues/1955 | 2026-11-10 | PRIMARY | — | C-TD-umbrelos-055 |
| 22 | https://github.com/getumbrel/umbrel/issues/2001 | 2026-11-10 | PRIMARY | — | — |

### TD-villageos

Tag file: [`evidence/sources/TD-villageos.md`](evidence/sources/TD-villageos.md) · 13 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.villageos.ai/ | 2026-11-10 | PRIMARY | saved copy in `sources/TD-villageos/` · sha256 `15fd034d0f1f756c…` | C-TD-villageos-001…003 |
| 2 | https://github.com/ReGen-Villages/VillageOS-API | 2026-11-10 | PRIMARY | commit pin `0082f5bb6763` | C-TD-villageos-006…025, 033…036 |
| 3 | https://github.com/ReGen-Villages/VillageOS-API/pull/12 | 2026-11-10 | PRIMARY | — | C-TD-villageos-027 |
| 4 | https://github.com/ReGen-Villages/VillageOS-API/pull/121 | 2026-11-10 | PRIMARY | — | C-TD-villageos-028 |
| 5 | https://github.com/ReGen-Villages/VillageOS-API/pull/111 | 2026-11-10 | PRIMARY | — | C-TD-villageos-029 |
| 6 | https://github.com/ReGen-Villages/VillageOS-API/pull/140 | 2026-11-10 | PRIMARY | — | C-TD-villageos-030 |
| 7 | https://github.com/ReGen-Villages/VillageOS-API/pull/28 | 2026-11-10 | PRIMARY | — | C-TD-villageos-031 |
| 8 | https://edgeaipod.buzzsprout.com/2363070/episodes/18240345-village-os-ai-for-sustainable-living | 2026-11-10 | SECONDARY | saved copy in `sources/TD-villageos/` · sha256 `df4bc18726f77ee7…` | C-TD-villageos-026 |
| 9 | http://web.archive.org/web/20260413083803/https://singularityhub.com/2024/12/29/inside-villageos-a-simcity-like-tool-for-regenerative-living-spaces/ | 2026-11-11 | SECONDARY | Wayback: http://web.archive.org/web/20260413083803/https://singularityhub.com/2024/12/29/inside-villageos-a-simcity-like-tool-for-regenerative-living-spaces/ | — |
| 10 | https://github.com/farmOS/farmOS | 2026-11-10 | PRIMARY-METADATA | — | C-TD-villageos-037 |
| 11 | https://github.com/OpenEMS/openems | 2026-11-10 | PRIMARY | — | C-TD-villageos-038 |
| 12 | https://github.com/Crosstalk-Solutions/project-nomad | 2026-11-10 | PRIMARY-METADATA | — | C-TD-villageos-039 |
| 13 | https://www.home-assistant.io/docs/energy/ | 2026-11-10 | PRIMARY | — | C-TD-villageos-040 |

### W10

Tag file: [`evidence/sources/W10.md`](evidence/sources/W10.md) · 37 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | getumbrel/umbrel packages/umbreld/source/modules/hardware/gpu.ts, apps/app.ts, apps/schema.ts, system/system.ts | 2026-11-11 | PRIMARY | commit pin `c43beed96407` | C-W10-001…005 |
| 2 | beclab/Olares framework/app-service/pkg/apiserver/compute_preflight_types.go, pkg/compute/preflight_types.go, pkg/utils/gpu_types.go, infras | 2026-11-11 | PRIMARY | commit pin `e7fe1c9634f2` | C-W10-006…009 |
| 3 | kubernetes-sigs/node-feature-discovery docs/usage/customization-guide.md, docs/usage/image-compatibility.md, source/ | 2026-11-11 | PRIMARY | commit pin `459284529bea` | C-W10-010…013 |
| 4 | NVIDIA/k8s-device-plugin cmd/gpu-feature-discovery/main.go, internal/lm/resource.go | 2026-11-11 | PRIMARY | commit pin `de8841190ea6` | C-W10-014, 015 |
| 5 | ollama/ollama docs/gpu.mdx | 2026-11-11 | PRIMARY | commit pin `8a89b76cc735` | C-W10-017 |
| 6 | https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html | 2026-11-11 | PRIMARY | Wayback capture 20260927005047 | C-W10-016 |
| 7 | https://store.umbrel.com/products.json | 2026-11-11 | PRIMARY | saved: `umbrel-store-feed.txt` | C-W10-018, 050 |
| 8 | https://one.olares.com/products.json | 2026-11-11 | PRIMARY | saved: `olares-store-feed.txt` | C-W10-019, 050 |
| 9 | https://shop.zimaspace.com/products.json?limit=250 | 2026-11-11 | PRIMARY | saved: `zima-store-feed.txt` | C-W10-020, 050 |
| 10 | https://www.home-assistant.io/green/ | 2026-11-11 | PRIMARY | Wayback capture 20261103013843 | C-W10-021 |
| 11 | https://www.nabucasa.com/hardware/ | 2026-11-11 | PRIMARY | saved: `nabucasa-hw.txt` | C-W10-022 |
| 12 | https://start9.com/server-one | 2026-11-11 | PRIMARY | saved: `start9-serverone.txt` | C-W10-023 |
| 13 | https://clawbox.com/home-ai-server | 2026-11-11 | PRIMARY | Wayback capture 20260906081304 | C-W10-024 |
| 14 | https://developer.nvidia.com/blog/nvidia-jetson-orin-nano-developer-kit-gets-a-super-boost/ | 2026-11-11 | PRIMARY | saved: `nv-superboost.txt` | C-W10-025 |
| 15 | https://developer.nvidia.com/embedded/faq | 2026-11-11 | PRIMARY | Wayback capture 20261031235630 | C-W10-026…028 |
| 16 | https://developer.nvidia.com/embedded/lifecycle | 2026-11-11 | PRIMARY | Wayback capture 20261011013431 | C-W10-029 |
| 17 | https://www.nvidia.com/en-us/autonomous-machines/embedded-systems/jetson-orin/nano-super-developer-kit/ | 2026-11-11 | PRIMARY | saved: `orin-nano-super.txt` | C-W10-030 |
| 18 | https://www.nvidia.com/en-us/products/workstations/dgx-spark/ | 2026-11-11 | PRIMARY | Wayback capture 20261106082035 | C-W10-031 |
| 19 | https://forums.developer.nvidia.com/t/2-23-2026-price-change-announcement/361713 | 2026-11-11 | PRIMARY | Wayback capture 20260927163228 | C-W10-032 |
| 20 | https://www.heise.de/en/news/Nvidia-s-DGX-Spark-becomes-more-expensive-despite-halved-RAM-11475128.html | 2026-11-11 | UNVERIFIED | saved copy in `sources/W10/` | C-W10-033 |
| 21 | https://www.raspberrypi.com/news/price-rises-for-some-16gb-raspberry-pi-products/ | 2026-11-11 | PRIMARY | Wayback capture 20261110012223 | C-W10-034 |
| 22 | https://www.raspberrypi.com/products/raspberry-pi-5/ | 2026-11-11 | PRIMARY | — | C-W10-034; C-W2-029 |
| 23 | https://www.raspberrypi.com/products/compute-module-5/ | 2026-11-11 | PRIMARY | — | C-W10-035 |
| 24 | https://www.raspberrypi.com/products/ai-hat-plus-2/ | 2026-11-11 | PRIMARY | — | C-W10-036 |
| 25 | https://www.trendforce.com/presscenter/news/20260202-12911.html | 2026-11-11 | SECONDARY | saved: `trendforce-0202.txt` | C-W10-037 |
| 26 | https://www.trendforce.com/presscenter/news/20260930-13258.html | 2026-11-11 | SECONDARY | Wayback capture 20261102172417 | C-W10-038 |
| 27 | https://www.intel.com/content/www/us/en/products/sku/241636/intel-processor-n150-6m-cache-up-to-3-60-ghz/specifications.html | 2026-11-11 | PRIMARY | Wayback capture 20261002225320 | C-W10-039 |
| 28 | https://www.intel.com/content/www/us/en/products/sku/231806/intel-core-i3n300-processor-6m-cache-up-to-3-80-ghz/specifications.html | 2026-11-11 | PRIMARY | saved copy in `sources/W10/` | C-W10-040 |
| 29 | https://www.intel.com/content/www/us/en/products/sku/84695/intel-core-i35005u-processor-3m-cache-2-00-ghz/specifications.html | 2026-11-11 | PRIMARY | saved copy in `sources/W10/` | C-W10-041 |
| 30 | https://www.intel.com/content/www/us/en/products/sku/232127/intel-core-i51345u-processor-12m-cache-up-to-4-70-ghz/specifications.html | 2026-11-11 | PRIMARY | saved copy in `sources/W10/` | C-W10-042 |
| 31 | https://www.dell.com/support/manuals/en-us/latitude-15-5540-laptop/latitude-5540-owners-manual/system-setup-options?guid=guid-3b0ef8b1-6a72-41b4-90… | 2026-11-11 | PRIMARY | — | C-W10-043 |
| 32 | https://bbs.bee-link.com/d/11740-request-for-auto-power-on-bios-for-beelink-u55-sn-5005uqig90163 | 2026-11-11 | UNVERIFIED | — | C-W10-044 |
| 33 | https://www.nvidia.com/en-us/startups/ | 2026-11-11 | PRIMARY | Wayback capture 20261024090411 | C-W10-045 |
| 34 | https://www.bis.gov/learn-support/encryption-controls/mass-market | 2026-11-11 | PRIMARY | Wayback capture 20260507024706 | C-W10-046 |
| 35 | https://www.federalregister.gov/documents/2026/01/20/2026-01052/… | 2026-11-11 | PRIMARY | saved: `fr-2026-01052.txt` | C-W10-047 |
| 36 | https://eur-lex.europa.eu/eli/dir/2019/771/oj/eng | 2026-11-11 | PRIMARY | saved: `eurlex-2019-771.txt` | C-W10-048 |
| 37 | https://www.raspberrypi.com/for-industry/integrator-programme/ | 2026-11-11 | PRIMARY | — | C-W10-049 |

### W11

Tag file: [`evidence/sources/W11.md`](evidence/sources/W11.md) · 63 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/ui/package.json#L66-L161 | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W11-001 |
| 2 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/ui/src/trpc/trpc.ts#L97-L122 | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W11-002 |
| 3 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/ui/src/utils/misc.ts#L42-L44 | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W11-003 |
| 4 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/umbreld/source/modules/notifications/notifications.ts#L1… | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W11-004 |
| 5 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/umbreld/source/modules/widgets/routes.ts#L11-L43 | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W11-005 |
| 6 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/os/overlay/etc/systemd/system/umbrel.service#L1-L19 | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W11-006 |
| 7 | https://github.com/getumbrel/umbrel/tree/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/ui/src/routes/onboarding | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W11-007 |
| 8 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/ui/src/features/photos/components/sources/add-source-dia… | 2026-11-11 | PRIMARY | saved copy in `sources/W11/` | C-W11-008 |
| 9 | https://github.com/beclab/Olares/blob/e7fe1c9634f26530386c2033a33be7a9495704f3/docs/developer/develop/package/manifest.md#L363-L372 | 2026-11-11 | PRIMARY | commit pin `e7fe1c9634f2` | C-W11-009 |
| 10 | https://github.com/beclab/Olares/blob/e7fe1c9634f26530386c2033a33be7a9495704f3/docs/developer/concepts/network.md#L15-L89 | 2026-11-11 | PRIMARY | commit pin `e7fe1c9634f2` | C-W11-010 |
| 11 | https://github.com/beclab/Olares/blob/e7fe1c9634f26530386c2033a33be7a9495704f3/apps/packages/app/package.json#L1-L255 | 2026-11-11 | PRIMARY | commit pin `e7fe1c9634f2` | C-W11-011 |
| 12 | https://github.com/beclab/Olares/blob/e7fe1c9634f26530386c2033a33be7a9495704f3/docs/manual/olares-vs-nas.md#L84 | 2026-11-11 | PRIMARY | commit pin `e7fe1c9634f2` | C-W11-012 |
| 13 | https://github.com/home-assistant/frontend/blob/5b1ecdb0b0718a37ba09d872924259cda14b7344/package.json#L103-L133 | 2026-11-11 | PRIMARY | commit pin `5b1ecdb0b071` | C-W11-013 |
| 14 | https://github.com/home-assistant/frontend/tree/5b1ecdb0b0718a37ba09d872924259cda14b7344/src/onboarding | 2026-11-11 | PRIMARY | commit pin `5b1ecdb0b071` | C-W11-014 |
| 15 | https://github.com/home-assistant/android | 2026-11-11 | PRIMARY | commit pin `f160c758` | C-W11-015 |
| 16 | https://companion.home-assistant.io/docs/notifications/notification-details/ | 2026-11-11 | PRIMARY | saved: `sources/W11/ha-notification-details.txt` · sha256 `8604f0df3d8d98e5…` | C-W11-016 |
| 17 | https://companion.home-assistant.io/docs/notifications/notification-local/ | 2026-11-11 | PRIMARY | saved: `sources/W11/ha-notification-local.txt` · sha256 `85e833003f4bb680…` | C-W11-017 |
| 18 | https://github.com/home-assistant/core/blob/d8a0dc698c8946b44e455d904000db563cfbf1ba/homeassistant/helpers/issue_registry.py#L50-L99 | 2026-11-11 | PRIMARY | commit pin `d8a0dc698c89` | C-W11-018 |
| 19 | https://contributors.home-assistant.io/blog/2026/05/26/advanced-mode-config-flow-deprecation | 2026-11-11 | PRIMARY | saved: `sources/W11/ha-advanced-mode-deprecation.txt` · sha256 `56bbdcaf82b32dec…` | C-W11-019 |
| 20 | https://github.com/IceWhaleTech/CasaOS-UI/blob/400a22c120e9f14b6e5c2276f9b79253acf95f35/package.json#L35-L81 | 2026-11-11 | PRIMARY | commit pin `400a22c120e9` | C-W11-020 |
| 21 | https://github.com/homarr-labs/homarr/tree/dfcaa9b0f83c3e658c451ae437021ee3b5e05ffa/packages/integrations/src | 2026-11-11 | PRIMARY | commit pin `dfcaa9b0f83c` | C-W11-021 |
| 22 | https://github.com/gethomepage/homepage | 2026-11-11 | PRIMARY-METADATA | commit pin `91b28e8a` | C-W11-022 |
| 23 | https://github.com/binwiederhier/ntfy/blob/a331a5c8db86d8e0fa743de5af98be586afe3b0a/README.md | 2026-11-11 | PRIMARY | commit pin `a331a5c8db86` | C-W11-023 |
| 24 | https://docs.ntfy.sh/config/ | 2026-11-11 | PRIMARY | saved: `sources/W11/ntfy-config.txt` · sha256 `bb86cbfec5a92800…` | C-W11-024 |
| 25 | https://developer.apple.com/documentation/usernotifications/modifying-content-in-newly-delivered-notifications | 2026-11-11 | PRIMARY | saved: `sources/W11/apple-modifying-content-in-newly-delivered-notifications.txt` · sha256 `5363d64f551e391d…` | C-W11-025 |
| 26 | https://developer.apple.com/documentation/usernotifications/generating-a-remote-notification | 2026-11-11 | PRIMARY | saved: `sources/W11/apple-generating-a-remote-notification.txt` · sha256 `836ee94320195d0a…` | C-W11-026 |
| 27 | https://developer.apple.com/documentation/usernotifications/establishing-a-token-based-connection-to-apns | 2026-11-11 | PRIMARY | saved: `sources/W11/apple-establishing-a-token-based-connection-to-apns.txt` · sha256 `f39d9509b19897da…` | C-W11-027 |
| 28 | https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/ | 2026-11-11 | PRIMARY | saved: `sources/W11/webkit-web-push-ios164.txt` · sha256 `cf5dcb9791190b54…` | C-W11-028 |
| 29 | https://www.rfc-editor.org/rfc/rfc8030 | 2026-11-11 | PRIMARY | saved: `sources/W11/rfc8030.txt` · sha256 `3987f49d2b8d8d2b…` | C-W11-029 |
| 30 | https://unifiedpush.org/ | 2026-11-11 | PRIMARY | saved: `sources/W11/unifiedpush-home.txt` · sha256 `04d5eae843b2af77…` | C-W11-030 |
| 31 | https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts/features_restricted_to_secure_contexts | 2026-11-11 | PRIMARY | saved: `sources/W11/mdn-secure-context-features.txt` · sha256 `ff54374630048c42…` | C-W11-031 |
| 32 | https://tailscale.com/kb/1153/enabling-https | 2026-11-11 | PRIMARY | saved: `sources/W11/tailscale-https.txt` · sha256 `a0abdf9685b01c35…` | C-W11-032 |
| 33 | https://github.com/Start9Labs/start-os/blob/246876d319a1b9fd0222701f028316c04b61014c/projects/start-cli/man/start-cli-net-ssl.1#L5-L17 | 2026-11-11 | PRIMARY | commit pin `246876d319a1` | C-W11-033 |
| 34 | https://github.com/NabuCasa/snitun/blob/1f540e40951b9fcfb89d8237ade2413e36f494a0/README.md | 2026-11-11 | PRIMARY | commit pin `1f540e40951b` | C-W11-034 |
| 35 | https://v2.tauri.app/blog/tauri-20/ | 2026-11-11 | PRIMARY | saved: `sources/W11/tauri-20-blog.txt` · sha256 `e28477660c30e664…` | C-W11-035 |
| 36 | https://v2.tauri.app/plugin/notification/ | 2026-11-11 | PRIMARY | commit pin `66b29d1b` | C-W11-036 |
| 37 | https://capacitorjs.com/docs/apis/push-notifications | 2026-11-11 | PRIMARY | saved: `sources/W11/capacitor-push.txt` · sha256 `45ba3ee9d7d8c3b5…` | C-W11-037 |
| 38 | https://developer.apple.com/app-store/review/guidelines/ | 2026-11-11 | PRIMARY | saved: `sources/W11/apple-app-review-guidelines.txt` · sha256 `dcc7b181a8f9b937…` | C-W11-038, 039 |
| 39 | https://support.google.com/googleplay/android-developer/answer/12564964 | 2026-11-11 | PRIMARY | saved: `sources/W11/gplay-vpnservice.txt` · sha256 `c153ba11c4071603…` | C-W11-040 |
| 40 | https://www.samba.org/samba/docs/current/man-html/vfs_fruit.8.html | 2026-11-11 | PRIMARY | saved: `sources/W11/samba-vfs-fruit.txt` · sha256 `d0b4ae43c83f5549…` | C-W11-041 |
| 41 | https://support.apple.com/en-us/102423 | 2026-11-11 | PRIMARY | saved: `sources/W11/apple-time-machine-nas.txt` · sha256 `39584648cc55ac0b…` | C-W11-042 |
| 42 | https://www.w3.org/TR/webxr/ | 2026-11-11 | PRIMARY | saved: `sources/W11/w3c-webxr.txt` · sha256 `61a5354a039e1f68…` | C-W11-043 |
| 43 | https://developer.android.com/develop/xr/web | 2026-11-11 | PRIMARY | saved: `sources/W11/android-xr-web.txt` · sha256 `12162daf14785c27…` | C-W11-044 |
| 44 | https://developer.apple.com/videos/play/wwdc2024/10066/ | 2026-11-11 | PRIMARY | saved: `sources/W11/wwdc24-10066.txt` · sha256 `f1986033a98d0c02…` | C-W11-045 |
| 45 | https://www.macrumors.com/2025/10/21/samsung-galaxy-xr-headset/ | 2026-11-11 | SECONDARY | — | C-W11-046 |
| 46 | https://github.com/basecamp/omarchy/blob/ceb30ed19ab1926713a7832dd4de5868c90d7b94/manual/17-ai.md#L57 | 2026-11-11 | PRIMARY | commit pin `ceb30ed19ab1` | C-W11-047 |
| 47 | https://github.com/basecamp/omarchy/releases | 2026-11-11 | PRIMARY-METADATA | — | C-W11-048 |
| 48 | https://github.com/basecamp/omarchy/blob/ceb30ed19ab1926713a7832dd4de5868c90d7b94/manual/30-updates.md#L11-L21 | 2026-11-11 | PRIMARY | commit pin `ceb30ed19ab1` | C-W11-049 |
| 49 | https://github.com/basecamp/omarchy/blob/ceb30ed19ab1926713a7832dd4de5868c90d7b94/manual/32-shell-plugins.md#L7-L96 | 2026-11-11 | PRIMARY | commit pin `ceb30ed19ab1` | C-W11-050 |
| 50 | https://github.com/ublue-os/bazzite/blob/b8881a9db67c6a6c341413a4c770db2814a34329/Containerfile#L35-L102 | 2026-11-11 | PRIMARY | commit pin `b8881a9db67c` | C-W11-051 |
| 51 | https://github.com/project-chip/connectedhomeip/blob/24d27615fd0c326edcedf3f64e3c9b704ff3f055/src/setup_payload/SetupPayload.h#L95-L134 | 2026-11-11 | PRIMARY | commit pin `24d27615fd0c` | C-W11-052 |
| 52 | https://github.com/k3s-io/docs/blob/8958508d493c12778517f2a178080f221cbe1081/docs/cli/token.md#L73-L111 | 2026-11-11 | PRIMARY | commit pin `8958508d493c` | C-W11-053 |
| 53 | https://docs.nats.io/running-a-nats-service/configuration/leafnodes | 2026-11-11 | PRIMARY | saved: `sources/W11/nats-leafnodes.txt` · sha256 `843f3a197b6fde0e…` | C-W11-054 |
| 54 | https://docs.nats.io/running-a-nats-service/configuration/gateways | 2026-11-11 | PRIMARY | saved: `sources/W11/nats-gateways.txt` · sha256 `ac98d27f778d9e12…` | C-W11-055 |
| 55 | https://pve.proxmox.com/wiki/Cluster_Manager | 2026-11-11 | PRIMARY | saved: `sources/W11/proxmox-cluster-manager.txt` · sha256 `4b63fe9801dd80aa…` | C-W11-056 |
| 56 | https://www.synology.com/en-global/dsm/7.4/software_spec/SHA | 2026-11-11 | PRIMARY | saved: `sources/W11/synology-sha-74.txt` · sha256 `12228439e9c84a23…` | C-W11-057 |
| 57 | https://github.com/netbox-community/netbox | 2026-11-11 | PRIMARY-METADATA | commit pin `28755a9d` | C-W11-058 |
| 58 | https://github.com/lichtblick-suite/lichtblick/blob/9589f381a420f2ab278b981cbfc4450816dc96fb/LICENSE | 2026-11-11 | PRIMARY | commit pin `9589f381a420` | C-W11-059 |
| 59 | https://www.w3.org/TR/WCAG22/ | 2026-11-11 | PRIMARY | saved: `sources/W11/w3c-wcag22.txt` · sha256 `43c5f540d7edf1d1…` | C-W11-060 |
| 60 | https://www.access-board.gov/ict/ | 2026-11-11 | PRIMARY | saved: `sources/W11/access-board-ict.txt` · sha256 `627d7c2228d4e24a…` | C-W11-061 |
| 61 | https://www.etsi.org/deliver/etsi_en/301500_301599/301549/03.02.01_60/ | 2026-11-11 | PRIMARY-METADATA | — | C-W11-062 |
| 62 | https://github.com/tailscale/tailscale | 2026-11-11 | PRIMARY-METADATA | commit pin `c31b4c13` | C-W11-063 |
| 63 | https://v2.vuejs.org/eol/ | 2026-11-11 | PRIMARY | — | C-W11-064 |

### W12

Tag file: [`evidence/sources/W12.md`](evidence/sources/W12.md) · 120 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://github.com/getumbrel/umbrel-apps/tree/3a087384be96ea6890a7428f62e28a2203c1ea6e | 2026-11-11 | PRIMARY | commit pin `3a087384be96` | C-W12-001, 008 |
| 2 | https://api.github.com/repos/getumbrel/umbrel-apps/license | 2026-11-11 | PRIMARY-METADATA | commit pin `3a087384be96` | C-W12-002 |
| 3 | https://github.com/beclab/apps/tree/37a1fb4f44b2428feb7978b25fdc798d6d6310ed | 2026-11-11 | PRIMARY | commit pin `37a1fb4f44b2` | C-W12-003 |
| 4 | https://github.com/beclab/apps/blob/37a1fb4f44b2428feb7978b25fdc798d6d6310ed/LICENSE | 2026-11-11 | PRIMARY | commit pin `37a1fb4f44b2` | C-W12-004 |
| 5 | https://github.com/beclab/apps/blob/37a1fb4f44b2428feb7978b25fdc798d6d6310ed/affine/OlaresManifest.yaml#L70-L80 | 2026-11-11 | PRIMARY | commit pin `37a1fb4f44b2` | C-W12-005 |
| 6 | https://github.com/beclab/apps/blob/37a1fb4f44b2428feb7978b25fdc798d6d6310ed/ollamagemma412budq8kxlv2/OlaresManifest.yaml | 2026-11-11 | PRIMARY | commit pin `37a1fb4f44b2` | C-W12-006 |
| 7 | https://github.com/toeverything/AFFiNE/blob/e2767cb27186a344c5d14f1d1643caf50f638988/packages/backend/server/LICENSE#L1-L8 | 2026-11-11 | PRIMARY | commit pin `e2767cb27186` | C-W12-007 |
| 8 | https://github.com/IceWhaleTech/CasaOS-AppStore/blob/820f99007fd521d0b534d94366371debea2ed438/Apps/Jellyfin/docker-compose.yml#L98-L105 | 2026-11-11 | PRIMARY | commit pin `820f99007fd5` | C-W12-009 |
| 9 | https://github.com/runtipi/runtipi-appstore/blob/1de3985bd40ecfcb6ec5204d5672b073e3a164dd/LICENSE | 2026-11-11 | PRIMARY | commit pin `1de3985bd40e` | C-W12-010 |
| 10 | https://github.com/compose-spec/compose-spec/blob/3a4a6995e4a971f6173dff9130cb3e38e6738651/spec.md#L3325-L3330 | 2026-11-11 | PRIMARY | commit pin `3a4a6995e4a9` | C-W12-011 |
| 11 | https://github.com/kubernetes/kompose/tree/59af0f0e641e3a4e4b4c7696dc65acf5c8c8df77 | 2026-11-11 | PRIMARY-METADATA | commit pin `59af0f0e641e` | C-W12-012 |
| 12 | https://github.com/getumbrel/umbrel/blob/6f357e18d0a4faccb69d9fa59e3eae9cc3380538/packages/umbreld/source/modules/apps/schema.ts#L96-L127 | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | C-W12-013 |
| 13 | https://github.com/home-assistant/core/blob/89f10085bdd61987547bbb41ca566ef1bce642f8/script/hassfest/quality_scale.py#L37-L95 | 2026-11-11 | PRIMARY | commit pin `89f10085bdd6` | C-W12-014 |
| 14 | https://github.com/open-webui/open-webui/blob/b0e6098e940942281d9c83f3529ea117287a3a22/LICENSE#L20-L36 | 2026-11-11 | PRIMARY | commit pin `b0e6098e9409` | C-W12-015 |
| 15 | https://github.com/n8n-io/n8n/blob/d48891758396576dc1d835d48a7f7e4be15f2684/LICENSE.md#L1-L34 | 2026-11-11 | PRIMARY | commit pin `d48891758396` | C-W12-016 |
| 16 | https://github.com/TandoorRecipes/recipes/blob/cbb96e151fe0c57c16a4456fe1bd04230b1c1e5c/LICENSE.md#L1-L9 | 2026-11-11 | PRIMARY | commit pin `cbb96e151fe0` | C-W12-017 |
| 17 | https://github.com/outline/outline/blob/309dd022f6ff5c67ce5d264e081fd6c559243163/LICENSE#L1-L20 | 2026-11-11 | PRIMARY | commit pin `309dd022f6ff` | C-W12-018 |
| 18 | https://github.com/akaunting/akaunting/blob/fe073235cdf762ef52b3264b790601ad40d32ff0/LICENSE.txt#L1-L30 | 2026-11-11 | PRIMARY | commit pin `fe073235cdf7` | C-W12-019 |
| 19 | https://github.com/invoiceninja/invoiceninja/blob/15ea35ea63f367eba33c04b7acd9ab1227853537/LICENSE | 2026-11-11 | PRIMARY | commit pin `15ea35ea63f3` | C-W12-020, 153 |
| 20 | https://github.com/monetr/monetr/blob/d901e042bfb9a790bfee9f0c54d02d0578e11ad4/LICENSE.md | 2026-11-11 | PRIMARY | commit pin `d901e042bfb9` | C-W12-021, 155 |
| 21 | https://github.com/we-promise/sure/blob/264bbf7cb71da65448ab74e4a650a1540dd0d3c4/LICENSE | 2026-11-11 | PRIMARY-METADATA | commit pin `264bbf7cb71d` | C-W12-022, 150 |
| 22 | https://github.com/OpenCTI-Platform/opencti/blob/f5ba2a776c39594184509f3e439f8b24c4ad8ce5/LICENSE | 2026-11-11 | PRIMARY | commit pin `f5ba2a776c39` | C-W12-023, 158 |
| 23 | https://github.com/esphome/esphome/blob/29875a9e03051dab71fdf326681fa8656e410781/LICENSE#L1-L7 | 2026-11-11 | PRIMARY | commit pin `29875a9e0305` | C-W12-024 |
| 24 | https://github.com/pi-hole/pi-hole/blob/259d8f9ee12fb91461ebfc670ec74032ea360a36/LICENSE#L1-L12 | 2026-11-11 | PRIMARY | commit pin `259d8f9ee12f` | C-W12-025 |
| 25 | https://github.com/HabitRPG/habitica/blob/a888dcbebbc392655a5388f82cd4a33f8343ed0c/LICENSE#L1-L7 | 2026-11-11 | PRIMARY | commit pin `a888dcbebbc3` | C-W12-026 |
| 26 | https://github.com/activepieces/activepieces/blob/e2cbf1665273627edbf5e2f23f99efc2edf2e7f6/LICENSE#L1-L5 | 2026-11-11 | PRIMARY | commit pin `e2cbf1665273` | C-W12-027 |
| 27 | https://github.com/fastenhealth/fasten-onprem/blob/36d92446884e9e20eda8d2b2a0a1115c9c57f7ef/LICENSE.md | 2026-11-11 | PRIMARY-METADATA | commit pin `36d92446884e` | C-W12-028, 146 |
| 28 | https://github.com/filebrowser/filebrowser/tree/833d908884d5c801f30f5c098d7977177eb3a36b | 2026-11-11 | PRIMARY-METADATA | commit pin `833d908884d5` | C-W12-029 |
| 29 | https://www.gnu.org/licenses/gpl-3.0.txt#L230-L243 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/gpl-3.0-s5-aggregate-excerpt.txt` | C-W12-030 |
| 30 | https://www.gnu.org/licenses/agpl-3.0.txt#L540-L560 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/agpl-3.0-s13-excerpt.txt` | C-W12-031 |
| 31 | https://developer.apple.com/app-store/review/guidelines/ | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/apple-app-review-guidelines-excerpt.txt` | C-W12-040, 041 |
| 32 | https://support.google.com/googleplay/android-developer/answer/12991134 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/google-play-health-permissions-excerpt.txt` | C-W12-042 |
| 33 | https://cloud.ouraring.com/legal/api-agreement | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/oura-api-agreement-excerpt.txt` | C-W12-043 |
| 34 | https://www.strava.com/legal/api | 2026-11-11 | PRIMARY | saved: `evidence/sources/W9/strava-api-policy.txt` | C-W12-044 |
| 35 | https://developer.garmin.com/gc-developer-program/overview/ | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/garmin-connect-developer-program.txt` | C-W12-045 |
| 36 | https://www.dcrainmaker.com/2026/10/garmin-connect-api-revamps-connect-developer.html | 2026-11-11 | SECONDARY | saved copy in `sources/W12/` | C-W12-046 |
| 37 | https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-160/subpart-A/section-160.103 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/ecfr-45cfr160.103-excerpt.txt` | C-W12-047 |
| 38 | https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-318 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/ecfr-16cfr318-hbnr-excerpt.txt` | C-W12-048 |
| 39 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/eu-gdpr-excerpt.txt` | C-W12-049, 073 |
| 40 | https://app.leg.wa.gov/RCW/default.aspx?cite=19.373&full=true | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/wa-rcw-19-373-excerpt.txt` | C-W12-050 |
| 41 | https://beta-bridge.simplefin.org/ | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/simplefin-bridge.txt` | C-W12-060 |
| 42 | https://www.simplefin.org/protocol.html | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/simplefin-protocol-excerpt.txt` | C-W12-061 |
| 43 | https://actualbudget.org/docs/advanced/bank-sync/ | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/actual-bank-sync.txt` | C-W12-062 |
| 44 | https://actualbudget.org/docs/advanced/bank-sync/gocardless/ | 2026-11-11 | SECONDARY | saved: `evidence/sources/W12/actual-gocardless-excerpt.txt` | C-W12-063 |
| 45 | https://plaid.com/legal/#developer-policy | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/plaid-legal-excerpt.txt` | C-W12-064 |
| 46 | https://plaid.com/legal/#end-user-privacy-policy | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/plaid-legal-excerpt.txt` | C-W12-065 |
| 47 | https://www.ecfr.gov/current/title-12/chapter-X/part-1033/subpart-A/section-1033.121 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/ecfr-12cfr1033.121.txt` | C-W12-066 |
| 48 | https://www.federalregister.gov/documents/2025/08/22/2025-16139/personal-financial-data-rights-reconsideration | 2026-11-11 | PRIMARY-METADATA | — | C-W12-067 |
| 49 | https://www.cozen.com/news-resources/publications/2026/section-1033-compliance-date-open-banking-rule-enjoined-and-under-reconsideration | 2026-11-11 | SECONDARY | saved copy in `sources/W12/` | C-W12-068 |
| 50 | https://www.law.cornell.edu/uscode/text/18/1030 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/us-18usc1030-excerpt.txt` | C-W12-070 |
| 51 | https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/van-buren-2021-excerpt.txt` | C-W12-071 |
| 52 | https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/hiq-v-linkedin-2022-excerpt.txt` | C-W12-072 |
| 53 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2065 | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/eu-dsa-excerpt.txt` | C-W12-074 |
| 54 | https://opensky-network.org/about/terms-of-use | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/opensky-terms-excerpt.txt` | C-W12-075 |
| 55 | https://www.maltego.com/license-agreement/ | 2026-11-11 | PRIMARY | saved: `evidence/sources/W12/maltego-license-excerpt.txt` | C-W12-076 |
| 56 | https://github.com/smicallef/spiderfoot/blob/0f815a203afebf05c98b605dba5cf0475a0ee5fd/LICENSE | 2026-11-11 | PRIMARY | commit pin `0f815a203afe` | C-W12-077, 157 |
| 57 | https://github.com/home-assistant/core/blob/89f10085bdd61987547bbb41ca566ef1bce642f8/LICENSE.md | 2026-11-11 | PRIMARY | commit pin `89f10085bdd6` | C-W12-101 |
| 58 | https://github.com/esphome/esphome/blob/29875a9e03051dab71fdf326681fa8656e410781/LICENSE | 2026-11-11 | PRIMARY | commit pin `29875a9e0305` | C-W12-102 |
| 59 | https://github.com/Koenkk/zigbee2mqtt/blob/3c841fdfd66c92239921ef84fde8f039c64e1662/LICENSE | 2026-11-11 | PRIMARY | commit pin `3c841fdfd66c` | C-W12-103 |
| 60 | https://github.com/eclipse-mosquitto/mosquitto/blob/fda14f2c196d9d2fcdd07d6c5d31a673524f7368/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `fda14f2c196d` | C-W12-104 |
| 61 | https://github.com/node-red/node-red/blob/25a016177d2eedfb641e7b9aa1d203ff60c5abee/LICENSE | 2026-11-11 | PRIMARY | commit pin `25a016177d2e` | C-W12-105 |
| 62 | https://github.com/blakeblackshear/frigate/blob/fba967c74be0b6aa5bc630ae2c3eb7d070ab8761/LICENSE | 2026-11-11 | PRIMARY | commit pin `fba967c74be0` | C-W12-106 |
| 63 | https://github.com/binwiederhier/ntfy/blob/a331a5c8db86d8e0fa743de5af98be586afe3b0a/LICENSE | 2026-11-11 | PRIMARY | commit pin `a331a5c8db86` | C-W12-107 |
| 64 | https://github.com/immich-app/immich/blob/3b2f4642882189260d11fb529bbf8b9021a075ff/LICENSE | 2026-11-11 | PRIMARY | commit pin `3b2f46428821` | C-W12-108 |
| 65 | https://github.com/syncthing/syncthing/blob/ed2e0fd441cf4ed797f6dee6e3db4d1a6ddb82f5/LICENSE | 2026-11-11 | PRIMARY | commit pin `ed2e0fd441cf` | C-W12-109 |
| 66 | https://github.com/nextcloud/server/blob/9fd1e5f00e4ae51ef22e4a5f228c1ac01cfc0ae9/COPYING | 2026-11-11 | PRIMARY | commit pin `9fd1e5f00e4a` | C-W12-110 |
| 67 | https://github.com/paperless-ngx/paperless-ngx/blob/d05e96cda26449cf46c6fcaaf5d1f8941dc7276f/LICENSE | 2026-11-11 | PRIMARY | commit pin `d05e96cda264` | C-W12-111 |
| 68 | https://github.com/filebrowser/filebrowser/blob/833d908884d5c801f30f5c098d7977177eb3a36b/LICENSE | 2026-11-11 | PRIMARY | commit pin `833d908884d5` | C-W12-112 |
| 69 | https://github.com/makeplane/plane/blob/618d0eb74658329a6f6e92434ac54231422c5b96/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `618d0eb74658` | C-W12-113 |
| 70 | https://github.com/go-vikunja/vikunja/blob/0f586d2fc193d7a95efaa1a38d0cfae54cc7a5c3/LICENSE | 2026-11-11 | PRIMARY | commit pin `0f586d2fc193` | C-W12-114 |
| 71 | https://github.com/toeverything/AFFiNE/blob/e2767cb27186a344c5d14f1d1643caf50f638988/LICENSE | 2026-11-11 | PRIMARY | commit pin `e2767cb27186` | C-W12-115 |
| 72 | https://github.com/TriliumNext/Trilium/blob/b8ae1382455bf907379a97f149357d584f6a44ba/LICENSE | 2026-11-11 | PRIMARY | commit pin `b8ae1382455b` | C-W12-116 |
| 73 | https://github.com/outline/outline/blob/309dd022f6ff5c67ce5d264e081fd6c559243163/LICENSE | 2026-11-11 | PRIMARY | commit pin `309dd022f6ff` | C-W12-117 |
| 74 | https://github.com/BookStackApp/BookStack/blob/0b6b667e0d84ebb3406de6de9fadbf4230c29c0b/LICENSE | 2026-11-11 | PRIMARY | commit pin `0b6b667e0d84` | C-W12-118 |
| 75 | https://github.com/usememos/memos/blob/9ee06fdc4722b45cc7efe1311767407fc86fec66/LICENSE | 2026-11-11 | PRIMARY | commit pin `9ee06fdc4722` | C-W12-119 |
| 76 | https://github.com/dani-garcia/vaultwarden/blob/17b159beff4b892f07f61f38ce2fe452e55251c1/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `17b159beff4b` | C-W12-120 |
| 77 | https://github.com/AdguardTeam/AdGuardHome/blob/3cac53a48e9fd573c09e3088207c192e8f75b5cf/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `3cac53a48e9f` | C-W12-121 |
| 78 | https://github.com/pi-hole/pi-hole/blob/259d8f9ee12fb91461ebfc670ec74032ea360a36/LICENSE | 2026-11-11 | PRIMARY | commit pin `259d8f9ee12f` | C-W12-122 |
| 79 | https://github.com/tailscale/tailscale/blob/c31b4c133d277c45c7fa6a4b18d5e122437d26e5/LICENSE | 2026-11-11 | PRIMARY | commit pin `c31b4c133d27` | C-W12-123 |
| 80 | https://github.com/juanfont/headscale/blob/7989fed78e8ac3c3ea4f12d8a2a423335a2f450f/LICENSE | 2026-11-11 | PRIMARY | commit pin `7989fed78e8a` | C-W12-124 |
| 81 | https://github.com/louislam/uptime-kuma/blob/fb8ef0fa8200bb989f3a115dda3b0e09a3c31167/LICENSE | 2026-11-11 | PRIMARY | commit pin `fb8ef0fa8200` | C-W12-125 |
| 82 | https://github.com/ollama/ollama/blob/8a89b76cc7359805e48357ba7e5b99e845a4c211/LICENSE | 2026-11-11 | PRIMARY | commit pin `8a89b76cc735` | C-W12-126 |
| 83 | https://github.com/open-webui/open-webui/blob/b0e6098e940942281d9c83f3529ea117287a3a22/LICENSE | 2026-11-11 | PRIMARY | commit pin `b0e6098e9409` | C-W12-127 |
| 84 | https://github.com/mudler/LocalAI/blob/d3c1eaee92ae16f53e4f3e9724ebef34692eba07/LICENSE | 2026-11-11 | PRIMARY | commit pin `d3c1eaee92ae` | C-W12-128 |
| 85 | https://github.com/Mintplex-Labs/anything-llm/blob/728586d76c843ed25cb7a27c7403f4b79bd960c8/LICENSE | 2026-11-11 | PRIMARY | commit pin `728586d76c84` | C-W12-129 |
| 86 | https://github.com/searxng/searxng/blob/57ff753ad416b7bf27e59d72ae8c7cac93b56be4/LICENSE | 2026-11-11 | PRIMARY | commit pin `57ff753ad416` | C-W12-130 |
| 87 | https://github.com/n8n-io/n8n/blob/d48891758396576dc1d835d48a7f7e4be15f2684/LICENSE.md | 2026-11-11 | PRIMARY | commit pin `d48891758396` | C-W12-131 |
| 88 | https://github.com/LibreChat-AI/LibreChat/blob/e6567c7a681ce67869dce31486a21d3a25d6931b/LICENSE | 2026-11-11 | PRIMARY | commit pin `e6567c7a681c` | C-W12-132 |
| 89 | https://github.com/jellyfin/jellyfin/blob/8466670e95b5f4f0b55d6353cf9fb3d6123217e3/LICENSE | 2026-11-11 | PRIMARY | commit pin `8466670e95b5` | C-W12-133 |
| 90 | https://github.com/navidrome/navidrome/blob/514207faf1e51543a0b026e0bf658cf160a5675a/LICENSE | 2026-11-11 | PRIMARY | commit pin `514207faf1e5` | C-W12-134 |
| 91 | https://github.com/advplyr/audiobookshelf/blob/2dde0bf1c7b294a84fd8147706ca64e006ae5d8a/LICENSE | 2026-11-11 | PRIMARY | commit pin `2dde0bf1c7b2` | C-W12-135 |
| 92 | https://github.com/kiwix/kiwix-tools/blob/00a9200cea6e870ef32441b5166112428a4654f9/COPYING | 2026-11-11 | PRIMARY | commit pin `00a9200cea6e` | C-W12-136 |
| 93 | https://github.com/learningequality/kolibri/blob/2d29598fc66f8f97527d224e965a3f2de080bb07/LICENSE | 2026-11-11 | PRIMARY | commit pin `2d29598fc66f` | C-W12-137 |
| 94 | https://github.com/mealie-recipes/mealie/blob/95c462d61b14481b9a939ff87d91a093e6b9582b/LICENSE | 2026-11-11 | PRIMARY | commit pin `95c462d61b14` | C-W12-138 |
| 95 | https://github.com/grocy/grocy/blob/41206cb90154e0d17d3e108cc1f182b94fdb465d/LICENSE.md | 2026-11-11 | PRIMARY | commit pin `41206cb90154` | C-W12-139 |
| 96 | https://github.com/TandoorRecipes/recipes/blob/cbb96e151fe0c57c16a4456fe1bd04230b1c1e5c/LICENSE.md | 2026-11-11 | PRIMARY | commit pin `cbb96e151fe0` | C-W12-140 |
| 97 | https://github.com/sysadminsmedia/homebox/blob/ea0461ec98060e6c6d21bc5f48953cdc75208617/LICENSE | 2026-11-11 | PRIMARY | commit pin `ea0461ec9806` | C-W12-141 |
| 98 | https://github.com/wger-project/wger/blob/c6ee8a740137c498ee7221e6cd3d8ad84b4a9304/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `c6ee8a740137` | C-W12-142 |
| 99 | https://github.com/endurain-project/endurain/blob/e4871d6ec6381e8c1bcf5a7cfac73bc633357a88/LICENSE | 2026-11-11 | PRIMARY | commit pin `e4871d6ec638` | C-W12-143 |
| 100 | https://github.com/HabitRPG/habitica/blob/a888dcbebbc392655a5388f82cd4a33f8343ed0c/LICENSE | 2026-11-11 | PRIMARY | commit pin `a888dcbebbc3` | C-W12-144 |
| 101 | https://github.com/SamR1/FitTrackee/blob/2129e443363a231c936fc339a44cd533acc7e4cb/LICENSE | 2026-11-11 | PRIMARY | commit pin `2129e443363a` | C-W12-145 |
| 102 | https://github.com/actualbudget/actual/blob/2ee836c222104854e0dedb904f940f4a4aca4a22/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `2ee836c22210` | C-W12-147 |
| 103 | https://github.com/firefly-iii/firefly-iii/blob/d65e916130c91d8f13ca808ca088d225ddd9a939/LICENSE | 2026-11-11 | PRIMARY | commit pin `d65e916130c9` | C-W12-148 |
| 104 | https://github.com/maybe-finance/maybe/blob/77b5469832758d1cbee1a940f3012a1ae1c74cd3/LICENSE | 2026-11-11 | PRIMARY | commit pin `77b546983275` | C-W12-149 |
| 105 | https://github.com/ghostfolio/ghostfolio/blob/aea75a89a3ea840d1c32ec11ad3595bcca99c93e/LICENSE | 2026-11-11 | PRIMARY | commit pin `aea75a89a3ea` | C-W12-151 |
| 106 | https://github.com/wealthfolio/wealthfolio/blob/71b218ab7fa836b8e778f08fa1ef14fea140f530/LICENSE | 2026-11-11 | PRIMARY | commit pin `71b218ab7fa8` | C-W12-152 |
| 107 | https://github.com/akaunting/akaunting/blob/fe073235cdf762ef52b3264b790601ad40d32ff0/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `fe073235cdf7` | C-W12-154 |
| 108 | https://github.com/rotki/rotki/blob/24804f9eb5a755d08c109f170c7915d5cfd4053c/LICENSE.md | 2026-11-11 | PRIMARY | commit pin `24804f9eb5a7` | C-W12-156 |
| 109 | https://github.com/intelowlproject/IntelOwl/blob/bf75e8b2f465f27c590cd0d7fea61d65fb6aab56/LICENSE | 2026-11-11 | PRIMARY | commit pin `bf75e8b2f465` | C-W12-159 |
| 110 | https://github.com/MISP/MISP/blob/04fc5f8b7ccb52bb6614ca3e9ccdbfdf6585d985/LICENSE | 2026-11-11 | PRIMARY | commit pin `04fc5f8b7ccb` | C-W12-160 |
| 111 | https://github.com/dgtlmoon/changedetection.io/blob/1882705fd7f34aa74b9ee8512b242f7d402821e5/LICENSE | 2026-11-11 | PRIMARY | commit pin `1882705fd7f3` | C-W12-161 |
| 112 | https://github.com/ArchiveBox/ArchiveBox/blob/ddcc6e8a8e84507b5caf5b6850f003ab67ae89a6/LICENSE | 2026-11-11 | PRIMARY | commit pin `ddcc6e8a8e84` | C-W12-162 |
| 113 | https://github.com/FreshRSS/FreshRSS/blob/6af8ebcbff9f10ec8fc7573879aa6151bc68ac56/LICENSE.txt | 2026-11-11 | PRIMARY | commit pin `6af8ebcbff9f` | C-W12-163 |
| 114 | https://github.com/lissy93/web-check/blob/fd08be81f700254214ef49d093e71a991567841f/LICENSE | 2026-11-11 | PRIMARY | commit pin `fd08be81f700` | C-W12-164 |
| 115 | https://github.com/brian7704/OpenTAKServer/blob/052a3d4a9f9d1ddefdee3ce303daffb4480f3d5d/LICENSE | 2026-11-11 | PRIMARY | commit pin `052a3d4a9f9d` | C-W12-165 |
| 116 | https://github.com/go-gitea/gitea/blob/c62bcf19f632919b70a947942b708565cef2e483/LICENSE | 2026-11-11 | PRIMARY | commit pin `c62bcf19f632` | C-W12-166 |
| 117 | https://github.com/coder/code-server/blob/05286010ae04f951d4702b49a50c2647a3d817d5/LICENSE | 2026-11-11 | PRIMARY | commit pin `05286010ae04` | C-W12-167 |
| 118 | https://github.com/grafana/grafana/blob/4f2bebd4a0f2d36b2559330878b9b48f3a79e9b6/LICENSE | 2026-11-11 | PRIMARY | commit pin `4f2bebd4a0f2` | C-W12-168 |
| 119 | https://github.com/activepieces/activepieces/blob/e2cbf1665273627edbf5e2f23f99efc2edf2e7f6/LICENSE | 2026-11-11 | PRIMARY | commit pin `e2cbf1665273` | C-W12-169 |
| 120 | https://github.com/homarr-labs/homarr/blob/dfcaa9b0f83c3e658c451ae437021ee3b5e05ffa/LICENSE | 2026-11-11 | PRIMARY | commit pin `dfcaa9b0f83c` | C-W12-170 |

### W13

Tag file: [`evidence/sources/W13.md`](evidence/sources/W13.md) · 27 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | Jellyfin UserPolicy.cs, AccessSchedule.cs @ 8466670e | 2026-11-11 | PRIMARY | — | C-W13-001, 002 |
| 2 | AdGuard Home openapi/openapi.yaml#L2523-L2560 @ 3cac53a4 | 2026-11-11 | PRIMARY | — | C-W13-003 |
| 3 | Apple docs: FamilyControls, family-controls entitlement, ManagedSettings, DeclaredAgeRange (documentation JSON) | 2026-11-11 | PRIMARY | — | C-W13-004…006 |
| 4 | developer.android.com/work/dpc/build-dpc | 2026-11-11 | PRIMARY | — | C-W13-007 |
| 5 | developers.google.com/android/work/play/emm-api/prov-devices | 2026-11-11 | PRIMARY | — | C-W13-008 |
| 6 | developer.android.com/google/play/age-signals/overview | 2026-11-11 | PRIMARY | — | C-W13-009 |
| 7 | Repo licence files at pinned SHAs (Headwind MDM, NanoMDM, Kolibri, kiwix-tools, IIAB, Moodle, Frappe LMS, Discourse, Zammad, FreeScout, Chat | 2026-11-11 | PRIMARY | saved: `W13/repo-licences-pinned-2026-11-11.txt` | C-W13-010, 011, 019, 021, 023, 024, 027, 039…042 |
| 8 | California AB 1043 bill text via calmatters.digitaldemocracy.org (leginfo.legislature.ca.gov returned 403/bot wall: UNVERIFIED (blocked) for | 2026-11-11 | UNVERIFIED | — | C-W13-012 |
| 9 | gov.ca.gov release 2026-09-10 (bills signed, incl. AB 1856) | 2026-11-11 | PRIMARY | saved: `W13/ca-governor-2026-09-10-signed-bills.txt` | C-W13-013 |
| 10 | anoni.net summary of AB 1856 (cites leginfo, EFF, Debian, Ubuntu, systemd) | 2026-11-11 | SECONDARY | — | C-W13-014 |
| 11 | systemd PR #40954 (GitHub API) | 2026-11-11 | PRIMARY | — | C-W13-015 |
| 12 | Fifth Circuit order No. 25-51073 (2026-06-04) | 2026-11-11 | PRIMARY | saved: `W13/ca5-25-51073-stay-order-2026-06-04.txt` | C-W13-016 |
| 13 | Federal Register 90 FR 16918 (COPPA final rule), API metadata + full text | 2026-11-11 | PRIMARY | saved: `W13/coppa-90FR16918-dates.txt` | C-W13-017, 018 |
| 14 | kolibri.readthedocs.io system requirements | 2026-11-11 | PRIMARY | — | C-W13-020 |
| 15 | download.kiwix.org/zim/ listings | 2026-11-11 | PRIMARY | saved: `W13/kiwix-zim-sizes-2026-11-11.txt` | C-W13-022 |
| 16 | help.circle.so "Export your data" (.md) and /llms.txt | 2026-11-11 | PRIMARY | saved: `W13/circle-export-your-data.md` | C-W13-025, 026 |
| 17 | discourse.org/pricing | 2026-11-11 | PRIMARY | — | C-W13-027 |
| 18 | zoho.com/know-your-datacenter.html | 2026-11-11 | PRIMARY | — | C-W13-028 |
| 19 | shopify.com/pricing | 2026-11-11 | PRIMARY | — | C-W13-029 |
| 20 | eCFR 16 CFR 255.5 (versioner API, 2026-11-01) | 2026-11-11 | PRIMARY | saved: `W13/ecfr-16cfr255.5.txt` | C-W13-030 |
| 21 | Home pages and subdomains of umbrel.com, olares.com, home-assistant.io, nabucasa.com, openhomefoundation store, start9.com, zimaspace.com, f | 2026-11-11 | PRIMARY | saved: `obsidian.md` | C-W13-031…038, 044…046, 051 |
| 22 | my.home-assistant.io source @ 1bb9d44c (README, redirect.json, src/entrypoints/my-redirect.ts, src/data/instance_info.ts) | 2026-11-11 | PRIMARY | — | C-W13-043 |
| 23 | developers.home-assistant.io docs/core/integration/diagnostics.md @ 50b51889 | 2026-11-11 | PRIMARY | saved: `docs/core/integration/diagnostics.md` | C-W13-047 |
| 24 | home-assistant/core components/analytics/{analytics,const}.py @ d9115f3e | 2026-11-11 | PRIMARY | — | C-W13-048 |
| 25 | AnswerDotAI/llms-txt nbs/index.qmd @ 3700a0a6 | 2026-11-11 | PRIMARY | — | C-W13-049 |
| 26 | GitHub REST API repo metadata (stars, created dates) | 2026-11-11 | PRIMARY-METADATA | — | C-W13-050 |
| 27 | Search-result summaries used only to find the above (Texas SB 2420 trackers, AB 1856 press coverage, Circle help search) | 2026-11-11 | — | — | — |

### W14

Tag file: [`evidence/sources/W14.md`](evidence/sources/W14.md) · 30 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://grapheneos.org/faq | 2026-11-11 | PRIMARY | saved: `W14/gos-faq-devices.txt` · sha256 `6c12fa4b3f9e957f…` | C-W14-001…004, 041 |
| 2 | https://grapheneos.org/usage | 2026-11-11 | PRIMARY | saved: `W14/gos-usage-excerpt.txt` · sha256 `f935a7a894da244b…` | C-W14-005…008 |
| 3 | https://grapheneos.org/features | 2026-11-11 | PRIMARY | saved: `W14/gos-features-excerpt.txt` · sha256 `43e1fbdb80cac029…` | C-W14-006…009 |
| 4 | https://grapheneos.org/releases | 2026-11-11 | PRIMARY | saved: `W14/gos-releases-excerpt.txt` · sha256 `e26c269ea7af56bb…` | C-W14-009, 012, 017, 033, 040 |
| 5 | https://github.com/GrapheneOS/os-issue-tracker/issues/8066 | 2026-11-11 | PRIMARY | saved: `W14/gos-issue-8066.txt` · sha256 `db91407c605c3335…` | C-W14-010 |
| 6 | https://github.com/GrapheneOS/os-issue-tracker/issues/6727 | 2026-11-11 | PRIMARY | saved: `W14/gos-issue-6727.txt` · sha256 `e24dce922551c8a1…` | C-W14-013 |
| 7 | https://github.com/GrapheneOS/os-issue-tracker/issues/4306 | 2026-11-11 | PRIMARY | saved: `W14/gos-issue-4306.txt` · sha256 `fad469178c3a4612…` | C-W14-014 |
| 8 | GitHub search API: repo:GrapheneOS/os-issue-tracker ATAK, repo:GrapheneOS/os-issue-tracker "Pixel Tablet" crash, repo:TAK-Product-Center/ata | 2026-11-11 | PRIMARY-METADATA | — | C-W14-018 |
| 9 | https://support.google.com/googlepixeltablet/answer/13555146?hl=en | 2026-11-11 | PRIMARY | saved: `W14/pixel-tablet-specs.txt` · sha256 `d3528960237943ed…` | C-W14-011 |
| 10 | https://github.com/TAK-Product-Center/atak-civ | 2026-11-11 | PRIMARY | commit pin `9f6893dd657f` | C-W14-015, 016 |
| 11 | https://constellationresponse.com/blogs/news/atak-quick-start-guide-pt-4-technical-difficulties | 2026-11-11 | SECONDARY | saved: `W14/constellation-atak-pt4.txt` · sha256 `79c74caa541e62ee…` | C-W14-019 |
| 12 | https://getgotak.com/products/eudv3 | 2026-11-11 | SECONDARY | saved: `W14/gotak-eudv3.txt` · sha256 `3e5f9d876b2677e8…` | C-W14-020 |
| 13 | https://docs.samsungknox.com/admin/fundamentals/whitepaper/samsung-knox-mobile-security/system-security/hw-backed-security/ | 2026-11-11 | PRIMARY | saved: `W14/knox-hw-security.txt` · sha256 `6dfc7f24f7c19622…` | C-W14-021 |
| 14 | https://www.androidauthority.com/samsung-bootloader-unlocking-disabled-one-ui-8-3581366 | 2026-11-11 | SECONDARY | — | C-W14-022 |
| 15 | https://github.com/RikkaApps/Shizuku | 2026-11-11 | PRIMARY-METADATA | commit pin `b844bc491f17` | C-W14-023 |
| 16 | https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation | 2026-11-11 | PRIMARY-METADATA | commit pin `9fcad87bf78c` | C-W14-024 |
| 17 | https://github.com/ImranR98/Obtainium | 2026-11-11 | PRIMARY-METADATA | commit pin `35c3e7fea4f3` | C-W14-025 |
| 18 | https://github.com/PeterCxy/Shelter | 2026-11-11 | PRIMARY-METADATA | commit pin `0afac87b2dc3` | C-W14-026 |
| 19 | https://calyxos.org/install/ | 2026-11-11 | PRIMARY | saved: `W14/calyxos-devices.txt` · sha256 `f60fba3d22478082…` | C-W14-027 |
| 20 | https://doc.e.foundation/devices/FP6 | 2026-11-11 | PRIMARY | saved: `W14/eos-fp6.txt` · sha256 `bed99b251f6f2a92…` | C-W14-028 |
| 21 | https://nura.eco/ | 2026-11-11 | UNVERIFIED | saved: `W14/nura-home.txt` · sha256 `ef19139bcead1216…` | C-W14-029 |
| 22 | https://furilabs.com/shop/flx1s/ | 2026-11-11 | PRIMARY | saved: `W14/furilabs.txt` · sha256 `a8c520c21164876f…` | C-W14-030 |
| 23 | https://github.com/waydroid/waydroid/issues/226 | 2026-11-11 | PRIMARY | commit pin `db7294c4c2bd` | C-W14-031 |
| 24 | https://devices.ubuntu-touch.io/ | 2026-11-11 | PRIMARY | saved: `W14/ubports-devices.txt` · sha256 `ff51c33dc8dd65c7…` | C-W14-032 |
| 25 | https://developer.android.com/work/dpc/dedicated-devices/lock-task-mode | 2026-11-11 | PRIMARY | saved: `W14/android-lock-task.txt` · sha256 `be919e113248cdad…` | C-W14-034 |
| 26 | https://github.com/h-mdm/hmdm-server | 2026-11-11 | PRIMARY-METADATA | commit pin `dfe9fdb5d7ef` | C-W14-035 |
| 27 | https://github.com/openharmony/communication_dsoftbus | 2026-11-11 | PRIMARY | commit pin `0e0c18c4a10b` | C-W14-036 |
| 28 | https://tech-ish.com/2026/08/30/harmonyos-worlds-third-largest-mobile-os/ | 2026-11-11 | SECONDARY | — | C-W14-037 |
| 29 | https://apps.apple.com/us/app/itak/id1561656396 | 2026-11-11 | PRIMARY | saved: `W14/itak-appstore.txt` · sha256 `f30a4ccc5c343bb8…` | C-W14-038 |
| 30 | https://volla.online/en/ | 2026-11-11 | PRIMARY | saved: `W14/volla.txt` · sha256 `7df48056ee103368…` | C-W14-039 |

### W15

Tag file: [`evidence/sources/W15.md`](evidence/sources/W15.md) · 22 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.accessnow.org/press-release/rising-and-resisting-in-the-darkness-internet-shutdowns-in-2025/ | 2026-11-11 | PRIMARY | saved: `accessnow-keepiton-2025.txt` | C-W15-001, 002 |
| 2 | https://www.entsoe.eu/news/2026/03/20/entso-e-publishes-expert-panel-final-report-on-28-april-2025-blackout-in-spain-and-portugal/ | 2026-11-11 | PRIMARY | saved: `entsoe-iberian-blackout-final-report.txt` | C-W15-003 |
| 3 | https://www.globaltimes.cn/page/202511/1347625.shtml | 2026-11-11 | SECONDARY | saved: `globaltimes-mofcom-suspension-2025-11-07.txt` | C-W15-004 |
| 4 | https://www.bis.gov/press-release/department-commerce-announces-rescission-biden-era-artificial-intelligence-diffusion-rule-strengthens | 2026-11-11 | PRIMARY | saved: `bis-ai-diffusion-rescission-2025-05-13.txt` | C-W15-005 |
| 5 | https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-742/section-742.15 | 2026-11-11 | PRIMARY | saved: `ecfr-15cfr734.3.txt` | C-W15-006 |
| 6 | https://docs.github.com/en/site-policy/other-site-policies/github-and-trade-controls | 2026-11-11 | PRIMARY | saved: `github-trade-controls.txt` | C-W15-007 |
| 7 | https://docs.docker.com/docker-hub/usage/ | 2026-11-11 | PRIMARY | saved: `docker-hub-usage-limits.txt` | C-W15-008 |
| 8 | https://github.com/bitnami/containers/issues/83267 | 2026-11-11 | PRIMARY | saved: `bitnami-catalog-changes-83267.txt` | C-W15-009 |
| 9 | https://developer.android.com/developer-verification | 2026-11-11 | PRIMARY | saved: `android-developer-verification.txt` | C-W15-010 |
| 10 | https://ec.europa.eu/commission/presscorner/detail/en/ip_25_1085 | 2026-11-11 | PRIMARY | saved: `ec-dma-apple-meta-decision-ip-25-1085.txt` | C-W15-011 |
| 11 | https://digital-strategy.ec.europa.eu/en/factpages/data-act-explained | 2026-11-11 | PRIMARY | saved: `ec-data-act-explained.txt` | C-W15-012 |
| 12 | https://streamlex.eu/articles/da-en-art-50/ | 2026-11-11 | SECONDARY | saved: `data-act-art50-streamlex.txt` | C-W15-013 |
| 13 | https://commission.europa.eu/law/law-topic/consumer-protection-law/directive-repair-goods_en | 2026-11-11 | PRIMARY | saved: `ec-right-to-repair-directive.txt` | C-W15-014 |
| 14 | https://commission.europa.eu/news-and-media/news/commission-advances-cloud-sovereignty-through-strategic-procurement-2026-04-17_en | 2026-11-11 | PRIMARY | saved: `ec-sovereign-cloud-tender-2026-04.txt` | C-W15-015, 016 |
| 15 | https://www.sovereign.tech/programs/fund | 2026-11-11 | PRIMARY | saved: `sovereign-tech-fund.txt` | C-W15-017 |
| 16 | https://www.opendesk.eu/en | 2026-11-11 | PRIMARY | saved: `opendesk-zendis.txt` | C-W15-018 |
| 17 | https://www.hklaw.com/en/insights/publications/2025/12/fcc-adds-all-foreign-made-drones | 2026-11-11 | SECONDARY | saved: `hklaw-fcc-covered-list-drones.txt` | C-W15-019 |
| 18 | https://www.whitehouse.gov/presidential-actions/2025/12/eliminating-state-law-obstruction-of-national-artificial-intelligence-policy/ | 2026-11-11 | PRIMARY | saved: `whitehouse-eo-ai-national-framework-2025-12-11.txt` | C-W15-020 |
| 19 | https://www.debian.org/releases/trixie/ | 2026-11-11 | PRIMARY | saved: `debian-trixie-release-info.txt` | C-W15-021 |
| 20 | https://ubuntu.com/blog/risc-v-profiles-why-is-rva23-significant | 2026-11-11 | PRIMARY | saved: `canonical-rva23.txt` | C-W15-022 |
| 21 | https://www.tomshardware.com/tech-industry/taiwanese-research-firm-says-tsmc-will-maintain-foundry-lead-until-at-least-2032 | 2026-11-11 | SECONDARY | saved: `tomshardware-sia-sub10nm.txt` | C-W15-023 |
| 22 | https://iconnect007.com/article/138941/…/138938/ein | 2026-11-11 | SECONDARY | saved: `trendforce-iconnect-foundry-share.txt` | C-W15-024 |

### W16

Tag file: [`evidence/sources/W16.md`](evidence/sources/W16.md) · 54 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.apache.org/licenses/LICENSE-2.0.txt | 2026-11-10 | PRIMARY | saved: `W16/apache-license-2.0.txt` | C-W16-001 |
| 2 | https://developercertificate.org/ | 2026-11-10 | PRIMARY | saved: `W16/dco.txt` | C-W16-002 |
| 3 | https://www.home-assistant.io/developers/cla/ | 2026-11-10 | PRIMARY | saved: `W16/ha-cla-page.txt` | C-W16-003 |
| 4 | https://about.gitlab.com/blog/gitlab-switches-to-dco-license/ | 2026-11-10 | PRIMARY | saved: `W16/gitlab-dco.txt` | C-W16-004 |
| 5 | https://github.com/home-assistant/core/blob/89f10085bdd61987547bbb41ca566ef1bce642f8/LICENSE.md | 2026-11-10 | PRIMARY-METADATA | commit pin `89f10085bdd6` | C-W16-005 |
| 6 | https://github.com/beclab/Olares/commit/534a73122710057ea2c26763028a65117918dc90 | 2026-11-10 | PRIMARY | commit pin `534a73122710` | C-W16-006 |
| 7 | https://www.hashicorp.com/en/blog/hashicorp-adopts-business-source-license | 2026-11-10 | PRIMARY | — | C-W16-007 |
| 8 | https://www.elastic.co/blog/elasticsearch-is-open-source-again | 2026-11-10 | PRIMARY | saved: `W16/elastic-agpl.txt` | C-W16-008 |
| 9 | https://redis.io/blog/agplv3/ | 2026-11-10 | PRIMARY | saved: `W16/redis-agpl.txt` | C-W16-009 |
| 10 | https://fsl.software/ | 2026-11-10 | PRIMARY | saved: `W16/fsl.txt` | C-W16-010 |
| 11 | https://www.debian.org/trademark | 2026-11-10 | PRIMARY | saved: `W16/debian-trademark.txt` | C-W16-011 |
| 12 | https://www.openhomefoundation.org/structure/ | 2026-11-10 | PRIMARY | saved: `W16/ohf-structure.txt` | C-W16-012 |
| 13 | https://www.openhomefoundation.org/media-room/annual-report-factsheet/ | 2026-11-10 | PRIMARY | saved: `W16/ohf-factsheet.txt` | C-W16-013 |
| 14 | https://www.nabucasa.com/pricing/ | 2026-11-10 | PRIMARY | saved: `W16/nabucasa-pricing.txt` | C-W16-014 |
| 15 | https://partner.home-assistant.io/ | 2026-11-10 | PRIMARY | saved: `W16/wwha-program.txt` | C-W16-015 |
| 16 | https://www.home-assistant.io/green/ | 2026-11-10 | PRIMARY | saved: `W16/ha-green.txt` | C-W16-016 |
| 17 | https://community.umbrel.com/t/we-ve-raised-a-3m-seed-round-and-are-now-hiring/4365 | 2026-11-10 | PRIMARY | saved: `W16/umbrel-seed-forum.txt` | C-W16-017 |
| 18 | https://www.prnewswire.com/news-releases/olares-showcases-private-ai-at-intels-ai-nas--thunderbolt-technology-forum-in-japan-302909516.html | 2026-11-10 | PRIMARY | saved: `W16/olares-pr-2026-10.txt` | C-W16-018 |
| 19 | https://www.wtrf.com/business/press-releases/cision/20251110CN02968/backed-by-45m-in-funding-olares-to-launch-a-personal-ai-device-bringing-cloud-l… | 2026-11-10 | UNVERIFIED | — | C-W16-019 |
| 20 | https://www.olares.com/docs/manual/help/olares | 2026-11-10 | PRIMARY | saved: `W16/olares-faq.txt` | C-W16-020 |
| 21 | https://start9.com/ | 2026-11-10 | PRIMARY | saved: `W16/start9-support.txt` | C-W16-021 |
| 22 | https://www.coincarp.com/fundraising/start9-labs-seed/ | 2026-11-10 | SECONDARY | saved: `W16/start9-coincarp.txt` | C-W16-022 |
| 23 | https://frame.work/blog/frameworks-series-a-1-and-community-participation | 2026-11-10 | PRIMARY | saved: `W16/framework-a1.txt` | C-W16-023 |
| 24 | https://foxglove.dev/blog/foxglove-series-b | 2026-11-10 | PRIMARY | saved: `W16/foxglove-seriesb.txt` | C-W16-024 |
| 25 | https://www.therobotreport.com/viam-brings-in-45m-to-accelerate-enterprise-partnerships/ | 2026-11-10 | SECONDARY | saved: `W16/viam-seriesb.txt` | C-W16-025 |
| 26 | https://shop.zimaspace.com/products.json | 2026-11-10 | PRIMARY | saved: `W16/zima-store-feed.txt` | C-W16-026 |
| 27 | https://www.kickstarter.com/projects/icewhaletech/zimacube-personal-cloud-re-invented | 2026-11-10 | UNVERIFIED | — | C-W16-027 |
| 28 | https://www.proxmox.com/en/products/proxmox-virtual-environment/pricing | 2026-11-10 | PRIMARY | saved: `W16/proxmox-pricing.txt` | C-W16-028 |
| 29 | https://unraid.net/pricing | 2026-11-10 | PRIMARY | saved: `W16/unraid-pricing.txt` | C-W16-029 |
| 30 | https://www.balena.io/pricing | 2026-11-10 | PRIMARY | saved: `W16/balena-pricing.txt` | C-W16-030 |
| 31 | https://www.nvidia.com/en-us/startups/ | 2026-11-10 | PRIMARY | saved: `W16/nvidia-inception-faq.txt` | C-W16-031, 032 |
| 32 | https://www.nvidia.com/en-us/about-nvidia/partners/become-a-partner/ | 2026-11-10 | PRIMARY | saved: `W16/nvidia-npn.txt` | C-W16-033 |
| 33 | https://www.raspberrypi.com/products/raspberry-pi-5/ | 2026-11-10 | PRIMARY | — | C-W16-034 |
| 34 | https://www.raspberrypi.com/products/compute-module-5/ | 2026-11-10 | PRIMARY | — | C-W16-035 |
| 35 | https://www.raspberrypi.com/for-industry/powered-by/ | 2026-11-10 | PRIMARY | — | C-W16-036 |
| 36 | https://www.anthropic.com/news/model-hardware-standard-research-preview | 2026-11-10 | PRIMARY | saved: `W16/anthropic-mhs-news.txt` | C-W16-037 |
| 37 | https://www.grandviewresearch.com/industry-analysis/consumer-network-attached-storage-nas-market | 2026-11-10 | SECONDARY | saved: `W16/mkt-nas-gvr.txt` | C-W16-038 |
| 38 | https://www.polarismarketresearch.com/industry-analysis/consumer-network-attached-storage-nas-market | 2026-11-10 | SECONDARY | saved: `W16/mkt-nas-polaris.txt` | C-W16-039 |
| 39 | https://www.mordorintelligence.com/industry-reports/robot-operating-system-market | 2026-11-10 | SECONDARY | saved: `W16/mkt-ros-mordor.txt` | C-W16-040 |
| 40 | https://www.precedenceresearch.com/robot-operating-system-market | 2026-11-10 | SECONDARY | saved: `W16/mkt-ros-precedence.txt` | C-W16-041 |
| 41 | https://www.prnewswire.com/news-releases/edge-ai-hardware-market-worth-58-90-billion-by-2030---exclusive-report-by-marketsandmarkets-302498128.html | 2026-11-10 | SECONDARY | saved: `W16/mkt-edgeai-mnm.txt` | C-W16-042 |
| 42 | https://www.thebusinessresearchcompany.com/report/edge-ai-hardware-global-market-report | 2026-11-10 | SECONDARY | saved: `W16/mkt-edgeai-tbrc.txt` | C-W16-043 |
| 43 | https://www.takalliance.org/ | 2026-11-10 | SECONDARY | saved: `W16/tak-alliance.txt` | C-W16-044 |
| 44 | https://breakingdefense.com/2025/11/evolution-and-future-of-the-tactical-assault-kit-for-soldiers-and-special-operators/ | 2026-11-10 | SECONDARY | saved: `W16/tak-breakingdefense.txt` | C-W16-045 |
| 45 | https://circle.so/pricing | 2026-11-10 | PRIMARY | saved: `W16/circle-pricing.txt` | C-W16-046 |
| 46 | https://nlnet.nl/propose/ | 2026-11-10 | PRIMARY | saved: `W16/nlnet-ngi0.txt` | C-W16-047 |
| 47 | https://www.sovereign.tech/programs/fund | 2026-11-10 | PRIMARY | saved: `W16/sta-fund.txt` | C-W16-048 |
| 48 | https://www.digitalocean.com/hatch | 2026-11-10 | PRIMARY | saved: `W16/do-hatch.txt` | C-W16-049 |
| 49 | https://sandstorm.io/news/2017-02-06-sandstorm-returning-to-community-roots | 2026-11-10 | PRIMARY | saved: `W16/sandstorm-postmortem.txt` | C-W16-050 |
| 50 | https://www.westerndigital.com/support/product-security/wdc-21008-recommended-security-measures-wd-mybooklive-wd-mybookliveduo | 2026-11-10 | PRIMARY | — | C-W16-051 |
| 51 | https://developers.cloudflare.com/r2/pricing/ | 2026-11-10 | PRIMARY | saved: `W16/r2-pricing.txt` | C-W16-052 |
| 52 | https://www.yubico.com/product/yubihsm-2-series/ | 2026-11-10 | PRIMARY | saved: `W16/yubihsm.txt` | C-W16-053 |
| 53 | https://tmsearch.uspto.gov/ | 2026-11-10 | UNVERIFIED | — | C-W16-054 |
| 54 | https://mender.io/pricing/plans | 2026-11-10 | PRIMARY | saved: `W16/mender-pricing.txt` | C-W16-055 |

### W17

Tag file: [`evidence/sources/W17.md`](evidence/sources/W17.md) · 36 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | ros2/ros2_documentation@0d1704f95ff68dfece22817a13dbe14bc50d8060 | 2026-11-11 | PRIMARY | commit pin `0d1704f95ff6` | C-W7-027, 029 |
| 2 | raspberrypi/documentation@21d772e7ee022e36a8f43c3ee75e20ca359fb832 | 2026-11-11 | PRIMARY | commit pin `21d772e7ee02` | C-W17-011 |
| 3 | kelseyhightower/kubernetes-the-hard-way@52eb26dad1a3e9e8083a899bc854421eb4842a73 | 2026-11-11 | PRIMARY | commit pin `52eb26dad1a3` | C-W17-016 |
| 4 | rauc/rauc@2d17b27041db7fa8b13a61c5e168f49310a06566 | 2026-11-11 | PRIMARY | commit pin `2d17b27041db` | C-W17-009, 010 |
| 5 | https://bootlin.com/docs/ | 2026-11-11 | PRIMARY | saved: `bootlin-docs.txt` · sha256 `65995ee745f0c83b…` | C-W17-001 |
| 6 | https://bootlin.com/training/embedded-linux/ | 2026-11-11 | PRIMARY | saved: `bootlin-emb.txt` · sha256 `2a4a10755e8c83da…` | C-W17-002 |
| 7 | https://training.linuxfoundation.org/training/introduction-to-linux/ | 2026-11-11 | PRIMARY | saved: `lf101.txt` · sha256 `a507e88c9596ca54…` | C-W17-003 |
| 8 | https://debian-handbook.info/browse/stable/ | 2026-11-11 | PRIMARY | saved: `debhandbook-stable.txt` · sha256 `3993c917ef8adaba…` | C-W17-004 |
| 9 | https://www.linuxfromscratch.org/lfs/read.html | 2026-11-11 | PRIMARY | — | C-W17-005 |
| 10 | https://docs.kernel.org/core-api/real-time/index.html | 2026-11-11 | PRIMARY | saved: `kernel-rt.txt` · sha256 `1be55b87b046c7c6…` | C-W17-006 |
| 11 | https://www.freedesktop.org/software/systemd/man/latest/systemd-cryptenroll.html | 2026-11-11 | PRIMARY | saved: `cryptenroll.txt` · sha256 `2dbd326b00933bf4…` | C-W17-007 |
| 12 | https://uapi-group.org/specifications/specs/unified_kernel_image/ | 2026-11-11 | PRIMARY | saved: `uapi-uki.txt` · sha256 `18085d5a4d7c3e09…` | C-W17-008 |
| 13 | https://rauc.readthedocs.io/en/latest/integration.html | 2026-11-11 | PRIMARY | saved: `rauc-integ.txt` · sha256 `9970d4984dd2f10a…` | C-W17-009, 010 |
| 14 | https://rauc.readthedocs.io/en/latest/basic.html | 2026-11-11 | PRIMARY | saved: `rauc-basic.txt` · sha256 `a624f9937e9d9504…` | — |
| 15 | https://docs.docker.com/build/building/multi-platform/ | 2026-11-11 | PRIMARY | — | C-W17-012 |
| 16 | https://docs.k3s.io/architecture | 2026-11-11 | PRIMARY | saved: `k3s-arch.txt` · sha256 `87a4bea178b90bfd…` | C-W17-013 |
| 17 | https://docs.k3s.io/datastore/backup-restore | 2026-11-11 | PRIMARY | saved: `k3s-backup.txt` · sha256 `103c4b01aa5b0840…` | C-W17-014 |
| 18 | https://docs.k3s.io/security/hardening-guide | 2026-11-11 | PRIMARY | — | C-W17-015 |
| 19 | https://github.com/kelseyhightower/kubernetes-the-hard-way | 2026-11-11 | PRIMARY | saved: `kthw.txt` · sha256 `ed1da4d5c86e0e9a…` | C-W17-016 |
| 20 | https://docs.nats.io/running-a-nats-service/configuration/leafnodes | 2026-11-11 | PRIMARY | saved: `nats-leaf.txt` · sha256 `067a4e3f51e02714…` | C-W17-017 |
| 21 | https://docs.nats.io/running-a-nats-service/configuration/securing_nats/auth_intro/jwt | 2026-11-11 | PRIMARY | — | C-W17-018 |
| 22 | https://natsbyexample.com/ | 2026-11-11 | SECONDARY | saved: `natsbyexample.txt` · sha256 `013b8e0f36ecd715…` | C-W17-019 |
| 23 | https://slsa.dev/spec/v1.1/ | 2026-11-11 | PRIMARY | — | C-W17-020 |
| 24 | https://docs.sigstore.dev/ | 2026-11-11 | PRIMARY | — | C-W17-021 |
| 25 | https://link.springer.com/book/10.1007/978-1-4302-6584-9 | 2026-11-11 | SECONDARY | — | C-W17-022 |
| 26 | https://nvidia-isaac-ros.github.io/getting_started/index.html | 2026-11-11 | PRIMARY | saved: `isaac-ros.txt` · sha256 `c3f230ebd2f898c1…` | C-W17-023 |
| 27 | https://docs.nvidia.com/jetson/archives/index.html | 2026-11-11 | PRIMARY | saved: `jetson-archives.txt` · sha256 `13c8f4d515e583d0…` | C-W17-024 |
| 28 | https://www.jetson-ai-lab.com/tutorials/ | 2026-11-11 | PRIMARY | saved: `jal-tutorials.txt` · sha256 `b353398e1521f294…` | C-W17-025 |
| 29 | https://www.nvidia.com/en-us/training/self-paced-courses/ | 2026-11-11 | PRIMARY | — | C-W17-026 |
| 30 | https://docs.kernel.org/kbuild/index.html | 2026-11-11 | PRIMARY | — | C-W17-027 |
| 31 | https://www.freedesktop.org/software/systemd/man/latest/bootup.html | 2026-11-11 | PRIMARY | — | C-W17-028 |
| 32 | https://snapshot.debian.org/ | 2026-11-11 | PRIMARY | — | C-W17-029 |
| 33 | https://lima-vm.io/docs/config/vmtype/vz/ | 2026-11-11 | PRIMARY | saved: `lima-vz.txt` · sha256 `0becb7e780d7ebf9…` | C-W18-053, 054 |
| 34 | https://www.raspberrypi.com/documentation/computers/raspberry-pi.html | 2026-11-11 | PRIMARY | saved copy in `sources/W17/` | C-W17-011 |
| 35 | https://reproducible-builds.org/docs/ | 2026-11-11 | PRIMARY | — | — |
| 36 | https://github.com/systemd/mkosi | 2026-11-11 | PRIMARY | — | C-W18-049 |

### W18

Tag file: [`evidence/sources/W18.md`](evidence/sources/W18.md) · 69 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | home-assistant/operating-system@fc301f556647b53281e853b9ce7f44915b3c7b14 | 2026-11-10 | PRIMARY | commit pin `fc301f556647` | C-W18-008, 009, 011 |
| 2 | getumbrel/umbrel@a72dac249974d1603be9423d3cf6ac1a2d8f65f9 | 2026-11-10 | PRIMARY | commit pin `a72dac249974` | C-W18-012…015 |
| 3 | raspberrypi/linux@e045ff670093cf3d515d121ab2678ce295f61f43 | 2026-11-10 | PRIMARY | commit pin `e045ff670093` | C-W18-009, 016 |
| 4 | torvalds/linux@adc218676eef25575469234709c2d87185ca223a | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `f14fbe202a14454e…` | C-W18-005, 018 |
| 5 | torvalds/linux@7d0a66e4bb9081d75c82ec4957c50034cb0ea449 | 2026-11-10 | PRIMARY | commit pin `7d0a66e4bb90` | C-W18-018, 061, 069 |
| 6 | OE4T/meta-tegra@80f9e27f649901c31e5ab0de627855374402169a | 2026-11-10 | PRIMARY | commit pin `80f9e27f6499` | C-W18-025 |
| 7 | NVIDIA/open-gpu-kernel-modules@e6a2e01579fbbd1ca2ed43fef2ee2589e9bd8bd9 | 2026-11-10 | PRIMARY | commit pin `e6a2e01579fb` | C-W18-026 |
| 8 | apple-oss-distributions/xnu@f6217f891ac0bb64f3d375211650a4c1ff8ca1ea | 2026-11-10 | PRIMARY | commit pin `f6217f891ac0` | C-W18-030 |
| 9 | apple/container@d5416e63231783c9699d31f35381caac941d3cde | 2026-11-10 | PRIMARY | commit pin `d5416e632317` | C-W18-031 |
| 10 | ros-infrastructure/rep@11ca24a41f31480dfb9562ba99f2a5b93d3ebda5 | 2026-11-10 | PRIMARY | saved: `rep-2000.rst` · sha256 `e84c7100a020ed1b…` | C-W18-034 |
| 11 | seL4/seL4@c98d70adf15e8be7d3b99085c28d057069ba7155 | 2026-11-10 | PRIMARY | commit pin `c98d70adf15e` | C-W18-035 |
| 12 | redox-os/redox@674d255f5fa189275e85968c52d55e6711092891 | 2026-11-10 | PRIMARY | commit pin `674d255f5fa1` | C-W18-040 |
| 13 | siderolabs/pkgs@17fdd3333e028525c10cbd90197c4958c03936da | 2026-11-10 | PRIMARY | commit pin `17fdd3333e02` | C-W18-045 |
| 14 | rugix/rugix@6d7fc277919b0048893c80d7e1e6e488ddc7b27b | 2026-11-10 | PRIMARY | commit pin `6d7fc277919b` | — |
| 15 | rugix/rugix-bakery@c43fdc11b88ee3ae8807f6b62802c85213c57be0 | 2026-11-10 | PRIMARY | commit pin `c43fdc11b88e` | — |
| 16 | go-debos/debos@0ad29e736f4760fc7f179d5cd30a8eba31108e0b | 2026-11-10 | PRIMARY | commit pin `0ad29e736f47` | C-W18-048 |
| 17 | systemd/mkosi@904357aa12013e3adbb4857cc4bf8840c6c83682 | 2026-11-10 | PRIMARY | saved: `mkosi/resources/man/mkosi.1.md` · sha256 `51b4df977609ac4b…` | C-W18-049 |
| 18 | osbuild/bootc-image-builder@6b82cb7abfcf59f9ce766318f53b59b1e4bbad20 | 2026-11-10 | PRIMARY | commit pin `6b82cb7abfcf` | C-W18-052 |
| 19 | lima-vm/lima@13424c4af7393a19cb6cad1ba96e87d100d57857 | 2026-11-10 | PRIMARY | commit pin `13424c4af739` | C-W18-054 |
| 20 | https://www.kernel.org/category/releases.html | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261101110002/https://www.kernel.org/category/releases.html | C-W18-001, 002 |
| 21 | https://cip-project.org/blog/2025/05/26/cip-is-now-supporting-five-slts-kernels | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20260501043214/https://cip-project.org/blog/2025/05/26/cip-is-now-supporting-five-slts-kernels | C-W18-003 |
| 22 | https://wiki.linuxfoundation.org/civilinfrastructureplatform/start | 2026-11-10 | SECONDARY | saved copy in `sources/W18/` | C-W18-004 |
| 23 | https://static.sched.com/hosted_files/osseu2025/6f/Civil%20Infrastructure%20Platform-State%20of%20Industrial%20Grade%20Linux-final.pdf | 2026-11-10 | PRIMARY-METADATA | — | — |
| 24 | https://packages.debian.org/trixie/linux-image-rt-arm64 | 2026-11-10 | PRIMARY | — | C-W18-006 |
| 25 | https://lists.debian.org/debian-lts-announce/2026/01/msg00007.html | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20260803214753/https://lists.debian.org/debian-lts-announce/2026/01/msg00007.html | C-W18-007 |
| 26 | https://www.raspberrypi.com/products/raspberry-pi-5/ | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261028093850/https://www.raspberrypi.com/products/raspberry-pi-5/ | C-W18-017 |
| 27 | https://developer.nvidia.com/embedded/jetpack | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261020130915/https://developer.nvidia.com/embedded/jetpack | C-W18-019 |
| 28 | https://docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/SD/Kernel/KernelCustomization.html | 2026-11-10 | PRIMARY | saved: `docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/SD/Kernel/KernelCustomization.html` · sha256 `cb14f27e0bfc0f29…` | C-W18-020 |
| 29 | https://docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/IN/QuickStart.html | 2026-11-10 | PRIMARY | saved: `docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/IN/QuickStart.html` | C-W18-021 |
| 30 | https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/IN/QuickStart.html | 2026-11-10 | PRIMARY | saved: `docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/IN/QuickStart.html` · sha256 `bcee3d35dac6059c…` | C-W18-021 |
| 31 | https://developer.nvidia.com/sdk-manager | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20260703221231/https://developer.nvidia.com/sdk-manager | C-W18-022 |
| 32 | https://docs.nvidia.com/sdk-manager/system-requirements/index.html | 2026-11-10 | PRIMARY | saved: `docs.nvidia.com/sdk-manager/system-requirements/index.html` | C-W18-022 |
| 33 | https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261018024028/https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html | C-W18-023 |
| 34 | https://developer.nvidia.com/embedded/lifecycle | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261011013431/https://developer.nvidia.com/embedded/lifecycle | C-W18-024 |
| 35 | https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261108215719/https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html | C-W18-027 |
| 36 | https://www.nvidia.com/en-us/drivers/unix/ | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `1ef4c56dc56c6b3f…` | C-W18-028 |
| 37 | https://kubernetes.io/docs/concepts/windows/intro/ | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261031040718/https://kubernetes.io/docs/concepts/windows/intro/ | C-W18-029 |
| 38 | https://docs.freebsd.org/en/books/handbook/jails/ | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `7322d40cee77468a…` | C-W18-032 |
| 39 | https://www.truenas.com/blog/truenas-core-13-3-plans/ | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20260714114843/https://www.truenas.com/blog/truenas-core-13-3-plans/ | C-W18-033 |
| 40 | https://docs.sel4.systems/projects/sel4/verified-configurations.html | 2026-11-10 | PRIMARY | saved: `docs.sel4.systems/projects/sel4/verified-configurations.html` · sha256 `b4124905c75b97a3…` | C-W18-035 |
| 41 | https://www.usenix.org/conference/osdi24/presentation/chen-haibo | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `c79dcf6098f298b8…` | C-W18-036 |
| 42 | https://en.wikipedia.org/wiki/HarmonyOS_5 | 2026-11-10 | SECONDARY | — | C-W18-037 |
| 43 | https://gitcode.com/openharmony/docs/blob/master/en/device-dev/kernel/kernel-overview.md | 2026-11-10 | SECONDARY | saved: `gitcode.com/openharmony/docs/blob/master/en/device-dev/kernel/kernel-overview.md` | C-W18-038 |
| 44 | https://www.techspot.com/news/89814-google-fuchsia-os-now-available-update-first-gen.html | 2026-11-10 | SECONDARY | saved copy in `sources/W18/` | C-W18-039 |
| 45 | https://source.android.com/docs/core/architecture/kernel/generic-kernel-image | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `48569e4396391f90…` | C-W18-041 |
| 46 | https://source.android.com/docs/core/architecture/kernel/android-common | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261019235903/https://source.android.com/docs/core/architecture/kernel/android-common | C-W18-042 |
| 47 | https://www.chromium.org/chromium-os/chromiumos-design-docs/chromium-os-kernel/ | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `e2d5a9aab39957e2…` | C-W18-043 |
| 48 | https://www.collabora.com/news-and-blog/news-and-events/steamos-3-6-how-the-steam-deck-atomic-updates-are-improving.html | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `5452984fbb55364c…` | C-W18-044 |
| 49 | https://rugix.org/docs/getting-started | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20260419042319/https://rugix.org/docs/getting-started/ | C-W18-046 |
| 50 | https://docs.yoctoproject.org/ref-manual/system-requirements.html | 2026-11-10 | PRIMARY | saved: `docs.yoctoproject.org/ref-manual/system-requirements.html` · sha256 `5481a241f9f51bd7…` | C-W18-050 |
| 51 | https://buildroot.org/downloads/manual/manual.html | 2026-11-10 | PRIMARY | saved: `buildroot.org/downloads/manual/manual.html` | C-W18-051 |
| 52 | https://osbuild.org/docs/bootc/ | 2026-11-10 | PRIMARY | — | C-W18-052 |
| 53 | https://lima-vm.io/docs/config/vmtype/vz/ | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261007084905/https://lima-vm.io/docs/config/vmtype/vz/ | C-W18-053 |
| 54 | https://www.cncf.io/projects/lima/ | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `a9bde7a47b561d77…` | C-W18-053 |
| 55 | https://orbstack.dev/pricing | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261028203713/https://orbstack.dev/pricing | C-W18-055 |
| 56 | https://docs.docker.com/subscription/desktop-license/ | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` · sha256 `40f22a00964566b9…` | C-W18-056 |
| 57 | https://docs.github.com/en/actions/reference/runners/github-hosted-runners | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261104013643/https://docs.github.com/en/actions/reference/runners/github-hosted-runners | C-W18-057 |
| 58 | https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20260927005047/https://docs.isaacsim.omniverse.nvidia.com/latest/installation/requirements.html | C-W18-058 |
| 59 | https://www.raspberrypi.com/software/ | 2026-11-10 | PRIMARY | saved copy in `sources/W18/` | C-W18-059 |
| 60 | https://ubuntu.com/real-time | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261101110028/https://ubuntu.com/real-time | C-W18-060 |
| 61 | https://lists.infradead.org/pipermail/linux-arm-kernel/2024-September/959465.html | 2026-11-10 | PRIMARY | saved: `lists.infradead.org/pipermail/linux-arm-kernel/2024-September/959465.html` | C-W18-061 |
| 62 | https://developer.apple.com/documentation/virtualization/vzgenericplatformconfiguration/isnestedvirtualizationsupported | 2026-11-10 | PRIMARY | — | C-W18-054 |
| 63 | https://www.jetson-ai-lab.com/tutorials/getting-started-with-jetson/ | 2026-11-10 | PRIMARY | — | — |
| 64 | Spike README (criteria written before the run, results appended after) | 2026-11-10 | — | saved: `<lab-dir>/w18-mac-toolchain/README.md` · sha256 `b3a07a02adcb77a4…` | — |
| 65 | Spike script (runs inside the VM) | 2026-11-10 | — | saved copy in `sources/W18/` · sha256 `208350239210ce75…` | — |
| 66 | Raw log | 2026-11-10 | — | hash only `c2a6f0602f7b4742…` (copy not in repo) | — |
| 67 | VM start log | 2026-11-10 | — | hash only `a1186358193cbd08…` (copy not in repo) | — |
| 68 | Build artefact sizes | 2026-11-10 | — | saved: `<lab-dir>/w18-mac-toolchain/artifacts.txt` · sha256 `90c0217a3b27d8df…` | — |
| 69 | https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.18.62.tar.xz | 2026-11-10 | — | hash only `490a7aedf1b355c5…` (copy not in repo) | — |

### W19

Tag file: [`evidence/sources/W19.md`](evidence/sources/W19.md) · 41 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | omacom/omarchy | 2026-11-11 | PRIMARY | commit pin `ceb30ed19ab1` | — |
| 2 | omacom/omarchy-plugin-marketplace | 2026-11-11 | PRIMARY | commit pin `f01e1860d89b` | — |
| 3 | hacs/integration | 2026-11-11 | PRIMARY | commit pin `8a543828351b` | — |
| 4 | hacs/default | 2026-11-11 | PRIMARY | commit pin `d1bec9610a34` | — |
| 5 | home-assistant/core | 2026-11-11 | PRIMARY | commit pin `d8a0dc698c89` | — |
| 6 | obsidianmd/obsidian-releases | 2026-11-11 | PRIMARY | commit pin `39ae8b23b4bf` | — |
| 7 | grafana/plugin-validator | 2026-11-11 | PRIMARY | commit pin `3ca7bc994716` | — |
| 8 | ros/rosdistro | 2026-11-11 | PRIMARY | commit pin `06990791cebf` | — |
| 9 | getumbrel/umbrel-community-app-store | 2026-11-11 | PRIMARY | commit pin `1b147ae7209f` | — |
| 10 | getumbrel/umbrel | 2026-11-11 | PRIMARY | commit pin `6f357e18d0a4` | — |
| 11 | beclab/Olares | 2026-11-11 | PRIMARY | commit pin `e7fe1c9634f2` | — |
| 12 | modelcontextprotocol/ext-apps | 2026-11-11 | PRIMARY | commit pin `ea3e9d0e624a` | — |
| 13 | viamrobotics/rdk | 2026-11-11 | PRIMARY | commit pin `046082ec9d51` | — |
| 14 | https://www.freedesktop.org/software/systemd/man/latest/systemd-sysext.html | 2026-11-11 | PRIMARY | saved: `systemd-sysext.txt` | C-W19-001…003 |
| 15 | https://sources.debian.org/api/src/systemd/ | 2026-11-11 | PRIMARY-METADATA | saved: `debian-sources-systemd-api.json` | C-W19-004 |
| 16 | https://www.flatcar.org/docs/latest/sys-ext/ | 2026-11-11 | PRIMARY | saved: `flatcar-sysext.txt` | C-W19-005 |
| 17 | https://www.hacs.xyz/docs/publish/include/ | 2026-11-11 | PRIMARY | saved: `hacs-publish.txt` | C-W19-016 |
| 18 | https://developers.home-assistant.io/docs/core/integration-quality-scale/ | 2026-11-11 | PRIMARY | saved: `ha-quality-scale.txt` | C-W19-046 |
| 19 | https://partner.home-assistant.io/ | 2026-11-11 | PRIMARY | saved: `works-with-ha.txt` | C-W19-020 |
| 20 | https://code.visualstudio.com/docs/configure/extensions/extension-runtime-security | 2026-11-11 | PRIMARY | saved: `vscode-ext-runtime-security.txt` | C-W19-023 |
| 21 | https://code.visualstudio.com/api/references/extension-manifest | 2026-11-11 | PRIMARY | saved: `vscode-manifest.txt` | C-W19-024 |
| 22 | https://blogs.eclipse.org/post/mikaël-barbero/open-vsx-security-update-october-2025 | 2026-11-11 | PRIMARY | saved: `eclipse-openvsx-oct2025.txt` | C-W19-025 |
| 23 | https://github.blog/security/supply-chain-security/our-plan-for-a-more-secure-npm-supply-chain/ | 2026-11-11 | PRIMARY | saved: `github-npm-plan.txt` | C-W19-026 |
| 24 | https://itsfoss.com/news/arch-linux-chaos-rat/ | 2026-11-11 | SECONDARY | saved: `itsfoss-aur-chaos-SECONDARY.txt` | C-W19-027 |
| 25 | https://wordpress.org/news/2024/10/secure-custom-fields/ | 2026-11-11 | PRIMARY | saved: `wp-scf.txt` | C-W19-028 |
| 26 | https://developer.wordpress.org/plugins/wordpress-org/detailed-plugin-guidelines/ | 2026-11-11 | PRIMARY | saved: `wp-guidelines.txt` | C-W19-029 |
| 27 | https://grafana.com/legal/plugins/ | 2026-11-11 | PRIMARY | saved: `grafana-sig-levels.txt` | C-W19-030 |
| 28 | https://grafana.com/developers/plugin-tools/publish-a-plugin/sign-a-plugin | 2026-11-11 | PRIMARY | saved: `grafana-sign.txt` | C-W19-030 |
| 29 | https://backstage.io/docs/plugins/ | 2026-11-11 | PRIMARY | saved: `backstage-plugins.txt` | — |
| 30 | https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions | 2026-11-11 | PRIMARY | saved: `chrome-permissions.txt` | C-W19-045 |
| 31 | https://source.android.com/docs/compatibility/cdd | 2026-11-11 | PRIMARY | saved: `android-cdd.txt` | C-W19-039 |
| 32 | https://developer.apple.com/app-store/small-business-program/ | 2026-11-11 | PRIMARY | saved: `apple-small-business.txt` | C-W19-040 |
| 33 | https://support.google.com/googleplay/android-developer/answer/112622 | 2026-11-11 | PRIMARY | saved: `google-play-fees.txt` | C-W19-041 |
| 34 | https://shopify.dev/docs/apps/launch/distribution/revenue-share | 2026-11-11 | PRIMARY | saved: `shopify-revshare.txt` | C-W19-042 |
| 35 | https://www.nabucasa.com/pricing/ | 2026-11-11 | PRIMARY | saved: `nabucasa-pricing.txt` | C-W19-043 |
| 36 | https://www.balena.io/pricing | 2026-11-11 | PRIMARY | saved: `balena-pricing.txt` | C-W19-044 |
| 37 | https://docs.foxglove.dev/docs/visualization/extensions/introduction | 2026-11-11 | PRIMARY | saved: `foxglove-extensions.txt` | C-W19-037 |
| 38 | https://obsidian.md/help/plugin-security | 2026-11-11 | — | — | C-W19-022 |
| 39 | https://lists.archlinux.org/archives/list/<email-masked>/thread/7EZTJXLIAQLARQNTMEW2HBWZYE626IFJ/ | 2026-11-11 | UNVERIFIED | — | C-W19-027 |
| 40 | https://packages.debian.org/trixie/systemd | 2026-11-11 | — | saved copy in `sources/W19/` | — |
| 41 | VS Code 2025 Marketplace security blog, Cyberhaven Chrome incident write-up | 2026-11-11 | — | — | — |

### W2

Tag file: [`evidence/sources/W2.md`](evidence/sources/W2.md) · 48 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.debian.org/releases/ | 2026-11-10 | PRIMARY | saved: `SHA256SUMS.txt` · sha256 `42f7f9a391820f9e…` | C-W2-001 |
| 2 | https://www.debian.org/releases/trixie/ | 2026-11-10 | PRIMARY | saved: `debian-trixie.txt` | C-W2-001 |
| 3 | https://www.freexian.com/lts/extended/ | 2026-11-10 | PRIMARY | saved: `freexian-elts.txt` | C-W2-002 |
| 4 | https://www.freexian.com/lts/extended/debian-elts-subscription-form.pdf | 2026-11-10 | PRIMARY | saved: `freexian-elts-contract.txt` · sha256 `24697cbad7831549…` | C-W2-003, 004 |
| 5 | https://ubuntu.com/about/release-cycle | 2026-11-10 | PRIMARY | saved: `ubuntu-release-cycle.txt` | C-W2-005 |
| 6 | https://ubuntu.com/pricing/devices | 2026-11-10 | PRIMARY | saved: `ubuntu-pro-devices.txt` | C-W2-006 |
| 7 | https://ubuntu.com/pricing/pro | 2026-11-10 | PRIMARY | saved: `ubuntu-pro-pricing.txt` | C-W2-007 |
| 8 | https://documentation.ubuntu.com/core/reference/support-duration/ | 2026-11-10 | PRIMARY | saved: `ubuntu-core-support-duration.txt` | C-W2-008 |
| 9 | https://documentation.ubuntu.com/core/reference/release-notes/ | 2026-11-10 | PRIMARY | — | C-W2-009 |
| 10 | https://access.redhat.com/support/policy/updates/errata | 2026-11-10 | PRIMARY | saved: `rhel-lifecycle.txt` | C-W2-010 |
| 11 | https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/considerations_in_adopting_rhel_10/architectures | 2026-11-10 | PRIMARY | saved: `rhel10-architectures.txt` | C-W2-011 |
| 12 | https://www.redhat.com/en/blog/image-mode-for-red-hat-enterprise-linux-generally-available | 2026-11-10 | PRIMARY | — | C-W2-012 |
| 13 | https://wiki.almalinux.org/release-notes/ | 2026-11-10 | PRIMARY | saved: `almalinux-releases.txt` | C-W2-013 |
| 14 | https://www.centos.org/download/ | 2026-11-10 | PRIMARY | saved: `centos-download.txt` | C-W2-014 |
| 15 | https://bodhi.fedoraproject.org/releases/F45 | 2026-11-10 | PRIMARY | saved: `F44.json.txt` | C-ARCH5-001; C-W2-015 |
| 16 | https://www.redhat.com/en/blog/red-hat-device-edge-now-available-run-nvidia-jetson-orin | 2026-11-10 | PRIMARY | saved: `rh-device-edge-jetson-ga.txt` | C-W2-041 |
| 17 | https://access.redhat.com/compliance/iec-62443-4-2 | 2026-11-10 | PRIMARY | saved: `rh-62443.txt` | C-W2-042 |
| 18 | https://www.raspberrypi.com/products/raspberry-pi-5/ | 2026-11-10 | PRIMARY | — | C-W2-029 |
| 19 | https://developer.nvidia.com/embedded/lifecycle | 2026-11-10 | PRIMARY | saved copy in `sources/W2/` | C-W2-030 |
| 20 | https://www.kernel.org/category/releases.html | 2026-11-10 | PRIMARY | saved: `kernel-org-releases.txt` | C-W2-031 |
| 21 | https://cip-project.org/blog/2025/05/26/cip-is-now-supporting-five-slts-kernels | 2026-11-10 | PRIMARY | — | C-W2-032 |
| 22 | https://packages.debian.org/trixie/linux-image-rt-arm64 | 2026-11-10 | PRIMARY | saved copy in `sources/W2/` | C-W2-033 |
| 23 | https://wiki.yoctoproject.org/wiki/Releases | 2026-11-10 | PRIMARY | saved: `yocto-releases.txt` | C-W2-034 |
| 24 | https://buildroot.org/lts.html | 2026-11-10 | PRIMARY | saved: `buildroot.txt` | C-W2-035 |
| 25 | https://alpinelinux.org/releases/ | 2026-11-10 | PRIMARY | saved: `alpine-releases.txt` | C-W2-036 |
| 26 | https://www.suse.com/lifecycle/ | 2026-11-10 | PRIMARY | saved: `suse-lifecycle-slmicro.txt` | C-W2-037 |
| 27 | https://api.balena-cloud.com/v7/device_type | 2026-11-10 | PRIMARY | — | C-W2-040 |
| 28 | https://canonical.com/legal/intellectual-property-policy | 2026-11-10 | PRIMARY | saved: `LIC/05-canonical-iprights-policy.txt` | C-W2-050 |
| 29 | https://github.com/NixOS/nixpkgs/…/rl-2605.section.md | 2026-11-10 | PRIMARY | saved: `endoflife.date/api/nixos.json` | C-W2-051 |
| 30 | fedora-iot/greenboot-rs @ 6efc3c109b54fec5e8a0ab575721258d28a85d9d (2026-11-02) | 2026-11-10 | PRIMARY | commit pin `6efc3c109b54` | C-W2-022, 023 |
| 31 | bootc-dev/bootc @ 27f1e64ea93639929ed0088cdc230c220dac0fe6 (2026-11-10) | 2026-11-10 | PRIMARY | commit pin `27f1e64ea936` | C-W2-024, 025 |
| 32 | fedora-iot/fedora-iot-bootc @ b68cc3e259d6983de13e3277ecf7ed9ca11d6c80 (2026-11-06) | 2026-11-10 | PRIMARY | commit pin `b68cc3e259d6` | C-W2-021 |
| 33 | fedora-iot/iot-docs @ 3cfcfe788629bde64e5b189a479aee0800fb3698 (2026-09-30) | 2026-11-10 | PRIMARY | commit pin `3cfcfe788629` | C-W2-016, 017 |
| 34 | fedora-iot/iot-distro issues #82, #118, #123, #141 (via gh) | 2026-11-10 | — | — | C-W2-018…020 |
| 35 | coreos/bootupd PR #935 (via gh) | 2026-11-10 | — | — | C-W2-018 |
| 36 | NVIDIA/cloud-native-docs @ d856ea69d8d9138ac171f24e1f9d08df53448591 (2026-11-09) | 2026-11-10 | PRIMARY | commit pin `d856ea69d8d9` | C-W2-026, 027 |
| 37 | ros2/ros2_documentation @ 1c5c20cb9f14cbfec658690c44b70ca3d3ec81e7 (2026-11-11 UTC) | 2026-11-10 | PRIMARY | commit pin `1c5c20cb9f14` | C-W2-028 |
| 38 | siderolabs/sbc-raspberrypi @ 9fa9252cca1a832a6154e3f431927302bb09d9bb; siderolabs/sbc-jetson @ 6468a58b8d1191869ec92dad7d31821c1c2a9de6; PR  | 2026-11-10 | PRIMARY | commit pin `9fa9252cca1a` | C-W2-038 |
| 39 | kairos-io/kairos-init @ ccd9c8929745047e2786763f10a1a12fd198ec1f (2026-08-19) | 2026-11-10 | PRIMARY | commit pin `ccd9c8929745` | C-W2-039 |
| 40 | getumbrel/umbrel @ a72dac249974d1603be9423d3cf6ac1a2d8f65f9 (umbrelOS 2.0.1, 2026-11-01) | 2026-11-10 | PRIMARY | commit pin `a72dac249974` | C-W2-043…046 |
| 41 | home-assistant/operating-system @ fc301f556647b53281e853b9ce7f44915b3c7b14 (2026-11-06) | 2026-11-10 | PRIMARY | commit pin `fc301f556647` | C-W2-047 |
| 42 | rugix/rugix @ c2f5f4f3db45890fe542dbc9608be969a3432cc1 (2026-11-10) | 2026-11-10 | PRIMARY | commit pin `c2f5f4f3db45` | C-W2-048 |
| 43 | GitHub API license fields: rauc/rauc, siderolabs/talos, kairos-io/kairos, sbabic/swupdate, canonical/snapd, home-assistant/operating-system, | 2026-11-10 | PRIMARY-METADATA | — | C-W2-049 |
| 44 | k3s-io/k3s v1.37.2+k3s1 (sha256sum-arm64.txt); k3s-io/k3s-selinux v1.6.latest.1 | 2026-11-10 | — | — | — |
| 45 | quay.io/fedora/fedora-iot:45 (45.20261110.0) | 2026-11-10 | — | hash only `0e4bb1bc0eb6a49d…` (copy not in repo) | — |
| 46 | quay.io/fedora/fedora-bootc:45 (45.20261110.0) | 2026-11-10 | — | hash only `32efabff97ea5062…` (copy not in repo) | — |
| 47 | quay.io/centos-bootc/bootc-image-builder:latest | 2026-11-10 | — | hash only `c8e130ebf2556f67…` (copy not in repo) | — |
| 48 | Fedora-Cloud-Base-Generic-45-1.4.aarch64.qcow2 (lab host) | 2026-11-10 | — | — | — |

### W3

Tag file: [`evidence/sources/W3.md`](evidence/sources/W3.md) · 53 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | github.com/rugix/rugix | 2026-11-10 | PRIMARY | commit pin `6d7fc277919b` | C-W3-001…004, 013 |
| 2 | github.com/rugix/rugix-docs | 2026-11-10 | PRIMARY | commit pin `227f902790fe` | C-W3-005…012, 014, 071 |
| 3 | github.com/rugix/rugix-bsps | 2026-11-10 | PRIMARY | commit pin `37c62d8b9137` | C-W3-013 |
| 4 | github.com/rugix/meta-rugix | 2026-11-10 | PRIMARY | commit pin `2e501d9354c3` | C-W3-013, 070 |
| 5 | github.com/getumbrel/umbrel | 2026-11-10 | PRIMARY | commit pin `a72dac249974` | C-W3-034…041, 043, 071 |
| 6 | github.com/home-assistant/operating-system | 2026-11-10 | PRIMARY | commit pin `fc301f556647` | C-W3-022…024, 026, 029 |
| 7 | github.com/home-assistant/supervisor | 2026-11-10 | PRIMARY | commit pin `c1c6f0a754c0` | C-W3-025, 072 |
| 8 | github.com/rauc/rauc | 2026-11-10 | PRIMARY | commit pin `4fb7c798d6ae` | C-W3-017…020 |
| 9 | github.com/rauc/meta-rauc-community | 2026-11-10 | PRIMARY | commit pin `b89bdf3469c5` | C-W3-021 |
| 10 | github.com/OE4T/tegra-demo-distro | 2026-11-10 | PRIMARY | commit pin `e151343f1dd3` | C-W3-052 |
| 11 | github.com/mendersoftware/meta-mender-community | 2026-11-10 | PRIMARY | commit pin `ebad311b35c4` | C-W3-053 |
| 12 | github.com/mendersoftware/mender-convert | 2026-11-10 | PRIMARY | commit pin `7aee704d808d` | C-W3-054 |
| 13 | github.com/mendersoftware/mender | 2026-11-10 | PRIMARY | commit pin `03297ca3dc6b` | C-W3-055 |
| 14 | github.com/sbabic/swupdate | 2026-11-10 | PRIMARY | commit pin `9ca7bc40ea33` | C-W3-056 |
| 15 | github.com/bootc-dev/bootc | 2026-11-10 | PRIMARY | commit pin `27f1e64ea936` | C-W3-058…060 |
| 16 | github.com/fedora-iot/greenboot-rs | 2026-11-10 | PRIMARY | commit pin `6efc3c109b54` | C-W3-061 |
| 17 | github.com/beclab/Olares | 2026-11-10 | PRIMARY | commit pin `e7fe1c9634f2` | C-W3-045 |
| 18 | github.com/IceWhaleTech/CasaOS | 2026-11-10 | PRIMARY | commit pin `e099dd6b4982` | C-W3-046 |
| 19 | github.com/IceWhaleTech/ZimaOS | 2026-11-10 | PRIMARY | commit pin `8bc15999eb23` | C-W3-047 |
| 20 | github.com/Start9Labs/start-os | 2026-11-10 | PRIMARY | commit pin `246876d319a1` | C-W3-048 |
| 21 | github.com/kairos-io/kairos-agent | 2026-11-10 | PRIMARY | — | C-W3-062 |
| 22 | GET /repos/{rugix/rugix, rauc/rauc, mendersoftware/mender, sbabic/swupdate, ostreedev/ostree, bootc-dev/bootc, fedora-iot/greenboot, kairos- | 2026-11-10 | PRIMARY | — | C-W3-001, 017, 056, 068, 069, 073 |
| 23 | GET /repos/rugix/rugix/contributors, /releases, /issues?state=all | 2026-11-10 | PRIMARY | — | C-W3-002, 003 |
| 24 | GET /repos/{…} (license, archived flag, pushed_at) and /releases/latest for the same set plus greenboot-rs, kairos-agent | 2026-11-10 | PRIMARY | — | C-W3-017, 055…058, 061, 062 |
| 25 | GET /repos/rauc/meta-rauc-community/commits?path=meta-rauc-tegra | 2026-11-10 | PRIMARY | — | C-W3-021 |
| 26 | GET /search/issues on home-assistant/operating-system and getumbrel/umbrel (update failures) | 2026-11-10 | PRIMARY | — | C-W3-030…033, 044 |
| 27 | https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/RootFileSystem.html | 2026-11-10 | PRIMARY | saved: `docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/RootFileSystem.html` · sha256 `15c229de73f2ba77…` | C-W3-049 |
| 28 | https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260823114925/https://docs.nvidia.com/jetson/archives/r39.2/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | C-W3-050 |
| 29 | https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260415154236/https://docs.nvidia.com/jetson/archives/r36.4/DeveloperGuide/SD/SoftwarePackagesAndTheUpdateMechanism.html | C-W3-051 |
| 30 | https://docs.k3s.io/upgrades/roll-back | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260826184914/https://docs.k3s.io/upgrades/roll-back | C-W3-063 |
| 31 | https://docs.k3s.io/datastore/backup-restore | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261111011629/https://docs.k3s.io/datastore/backup-restore | C-W3-064 |
| 32 | https://docs.k3s.io/upgrades/automated | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260911033514/https://docs.k3s.io/upgrades/automated | C-W3-065 |
| 33 | https://docs.k3s.io/upgrades/manual | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260826184914/https://docs.k3s.io/upgrades/manual | C-W3-065 |
| 34 | https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260923030458/https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/ | C-W3-028 |
| 35 | https://www.home-assistant.io/installation/generic-x86-64 | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261030064704/https://www.home-assistant.io/installation/generic-x86-64 | C-W3-027 |
| 36 | https://umbrel.com/downloads | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261108120226/https://umbrel.com/downloads | C-W3-042 |
| 37 | https://umbrel.com/umbrelos | 2026-11-10 | PRIMARY | — | — |
| 38 | https://silitics.com/ | 2026-11-10 | SECONDARY | Wayback: http://web.archive.org/web/20260716200505/https://silitics.com/ | C-W3-015 |
| 39 | https://rugix.org/blog/2026-02-28-ota-update-engines-compared/ | 2026-11-10 | SECONDARY | Wayback: http://web.archive.org/web/20260419042321/https://rugix.org/blog/2026-02-28-ota-update-engines-compared/ | C-W3-016 |
| 40 | https://www.raspberrypi.com/documentation/computers/config_txt.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261102185519/https://www.raspberrypi.com/documentation/computers/config_txt.html | C-W3-066 |
| 41 | https://github.com/home-assistant/operating-system/pull/4757 | 2026-11-10 | PRIMARY | saved: `ARCH5/haos-operating-system-pr-4757.json.txt` · sha256 `c5ded8ef1eca2707…` | C-ARCH5-004; C-W3-024 |
| 42 | https://theupdateframework.github.io/specification/latest/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261027112523/https://theupdateframework.github.io/specification/latest/ | C-W3-067 |
| 43 | https://gitlab.com/cip-project/cip-core/isar-cip-core/-/raw/master/doc/README.swupdate.md | 2026-11-10 | PRIMARY | saved: `gitlab.com/cip-project/cip-core/isar-cip-core/-/raw/master/doc/README.swupdate.md` · sha256 `ff73751b0f43fa5f…` | C-W3-057 |
| 44 | https://docs.mender.io/artifact-creation/create-a-delta-update-artifact | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260709020529/https://docs.mender.io/artifact-creation/create-a-delta-update-artifact | C-W3-055 |
| 45 | https://github.com/home-assistant/operating-system/issues/{4995,5036,3995,5098} | 2026-11-10 | PRIMARY | — | C-W3-030…033 |
| 46 | https://github.com/getumbrel/umbrel/issues/2297 | 2026-11-10 | PRIMARY | — | C-W3-044 |
| 47 | RESEARCH-MISSION.md §2, §4, §5 (W3), §6, §7 | 2026-11-10 | — | — | — |
| 48 | context/03-repo-findings-index.md §1.1, §3, §5 | 2026-11-10 | — | saved: `context/03-repo-findings-index.md` | — |
| 49 | research/platform/verify-updates-rollback-backups-security.md (VUPD) | 2026-11-10 | — | saved: `research/platform/verify-updates-rollback-backups-security.md` | — |
| 50 | docs/ADR-001-foundation.md, docs/REQUIREMENTS.md, docs/DECISIONS.md | 2026-11-10 | — | saved: `docs/DECISIONS.md` | — |
| 51 | research-output/evidence/decision-critical.md, scorecard-weights.md (frozen v1.0) | 2026-11-10 | — | saved: `scorecard-weights.md` | — |
| 52 | research-output/02-competitors/umbrelos.md, home-assistant-os.md (parallel teardowns; cross-checked, consistent) | 2026-11-10 | — | saved: `home-assistant-os.md` | — |
| 53 | research-output/evidence/lab/{debian-rugix,rauc,k3s-footprint-restore}/README.md (pre-registered spikes; results pending at time of writing) | 2026-11-10 | — | saved: `README.md` | — |

### W4

Tag file: [`evidence/sources/W4.md`](evidence/sources/W4.md) · 56 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://www.suse.com/lifecycle/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261101110334/https://www.suse.com/lifecycle/ | C-W4-012 |
| 2 | https://www.suse.com/suse-k3s/support-matrix/all-supported-versions/ | 2026-11-10 | PRIMARY | saved copy in `sources/W4/` · sha256 `caf0eb13148768c5…` | C-W4-013 |
| 3 | https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261026003322/https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/platform-support.html | C-W4-021…025 |
| 4 | https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261013001714/https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/ | C-W4-016 |
| 5 | https://docs.rke2.io/install/requirements | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260902094721/https://docs.rke2.io/install/requirements | C-W4-072 |
| 6 | https://docs.rke2.io/networking/networking_services | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260718000007/https://docs.rke2.io/networking/networking_services | C-W4-017 |
| 7 | https://developer.nvidia.com/blog/manage-kubernetes-clusters-for-gpu-infrastructure-with-nvidia-kubernetes-engine/ | 2026-11-10 | PRIMARY | saved copy in `sources/W4/` · sha256 `1c44562d2e02377e…` | C-W4-039 |
| 8 | https://developer.nvidia.com/blog/agent-substrate-advancing-kubernetes-for-agents-at-scale/ | 2026-11-10 | PRIMARY | saved copy in `sources/W4/` · sha256 `d571e1f3c159cc60…` | C-W4-040 |
| 9 | https://blogs.nvidia.com/blog/nvidia-at-kubecon-2026/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260825203055/https://blogs.nvidia.com/blog/nvidia-at-kubecon-2026/ | C-W4-032 |
| 10 | https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261102095816/https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html | C-W4-026 |
| 11 | https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261108215719/https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html | C-W4-027 |
| 12 | https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/debian.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261020014906/https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/debian.html | C-W4-028 |
| 13 | https://backstage.io/docs/getting-started/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261001043349/https://backstage.io/docs/getting-started/ | C-W4-059 |
| 14 | https://gateway-api.sigs.k8s.io/implementations/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260512134015/https://gateway-api.sigs.k8s.io/implementations/ | C-W4-018 |
| 15 | https://project-hami.io/docs/next/userguide/device-supported | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260710164852/https://project-hami.io/docs/next/userguide/device-supported | C-W4-036 |
| 16 | https://docs.k3s.io/cli/etcd-snapshot | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261111011648/https://docs.k3s.io/cli/etcd-snapshot | C-W4-008 |
| 17 | https://docs.k3s.io/networking/networking-services | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260616225903/https://docs.k3s.io/networking/networking-services | C-W4-015, 019 |
| 18 | https://longhorn.io/docs/latest/best-practices/ | 2026-11-10 | PRIMARY | saved copy in `sources/W4/` · sha256 `f6df774da302228c…` | C-W4-046 |
| 19 | https://docs.k0sproject.io/stable/system-requirements/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260808182824/https://docs.k0sproject.io/stable/system-requirements/ | C-W4-045 |
| 20 | https://argo-cd.readthedocs.io/en/stable/operator-manual/core/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260425195721/https://argo-cd.readthedocs.io/en/stable/operator-manual/core/ | C-W4-050 |
| 21 | https://docs.nats.io/running-a-nats-service/configuration/leafnodes/jetstream_leafnodes | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260608120030/https://docs.nats.io/running-a-nats-service/configuration/leafnodes/jetstream_leafnodes | C-W4-054 |
| 22 | https://kubernetes.io/releases/version-skew-policy/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261011093605/https://kubernetes.io/releases/version-skew-policy/ | C-W4-014 |
| 23 | https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260821054952/https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/ | C-W4-031 |
| 24 | https://docs.cilium.io/en/stable/operations/system_requirements/ | 2026-11-10 | PRIMARY | — | C-W4-047 |
| 25 | https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html | 2026-11-10 | PRIMARY | saved: `docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html` | C-W4-051 |
| 26 | https://tailscale.com/kb/1236/kubernetes-operator | 2026-11-10 | PRIMARY | — | C-W4-062 |
| 27 | https://www.cncf.io/blog/2025/05/01/protecting-nats-and-the-integrity-of-open-source-cncfs-commitment-to-the-community/ | 2026-11-10 | PRIMARY | — | C-W4-056 |
| 28 | https://docs.nats.io/running-a-nats-service/configuration/leafnodes | 2026-11-10 | PRIMARY | saved copy in `sources/W4/` | C-W4-054 |
| 29 | https://docs.nats.io/nats-concepts/jetstream/source_and_mirror | 2026-11-10 | PRIMARY | — | — |
| 30 | https://kubeedge.io/docs/ | 2026-11-10 | PRIMARY | — | — |
| 31 | https://fluxcd.io/flux/installation/ | 2026-11-10 | PRIMARY | saved copy in `sources/W4/` | — |
| 32 | https://canonical.com/blog/canonical-nvidia-kubecon-2026 | 2026-11-10 | PRIMARY | — | — |
| 33 | https://cloudnativenow.com/kubecon-cloudnativecon-north-america-2026/nvidia-adds-kubernetes-engine-recipes-and-snapshot-to-dsx-ai-factory-platform/ | 2026-11-10 | SECONDARY | — | C-W4-039 |
| 34 | https://www.cncf.io/blog/2026/10/07/kubernetes-on-edge-day-returns-to-kubecon-cloudnativecon-north-america-2026/ | 2026-11-10 | PRIMARY | — | C-W4-074 |
| 35 | https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/index.html | 2026-11-10 | PRIMARY | saved: `kernel-modules.html` | C-W4-028 |
| 36 | k3s-io/docs @ 8958508d493c12778517f2a178080f221cbe1081 | 2026-11-10 | PRIMARY | commit pin `8958508d493c` | C-W4-001…010, 020, 052, 053 |
| 37 | k3s-io/kine @ f82bd25164a393b333815f41746ef89de0d5ae20 | 2026-11-10 | PRIMARY | commit pin `f82bd25164a3` | C-W4-053 |
| 38 | beclab/Olares @ e7fe1c9634f26530386c2033a33be7a9495704f3 | 2026-11-10 | PRIMARY | commit pin `e7fe1c9634f2` | C-W4-041, 042 |
| 39 | getumbrel/umbrel @ a72dac249974d1603be9423d3cf6ac1a2d8f65f9 | 2026-11-10 | PRIMARY | commit pin `a72dac249974` | C-W4-043 |
| 40 | home-assistant/supervisor @ c1c6f0a754c0656eb1af189f11009f1cfc4b3e28 | 2026-11-10 | PRIMARY | commit pin `c1c6f0a754c0` | C-W4-044 |
| 41 | NVIDIA/aicr @ c760855ed7307f40731a11f9a1b7898b76167209 | 2026-11-10 | PRIMARY | commit pin `c760855ed730` | C-W4-037 |
| 42 | NVIDIA/k8s-dra-driver-gpu @ e775fdb63e593a121b40fc1cc4c9a9c89955e635 | 2026-11-10 | PRIMARY | commit pin `e775fdb63e59` | C-W4-030 |
| 43 | NVIDIA/k8s-device-plugin @ de8841190ea6bbaceab572f5cb5847da54dff448 | 2026-11-10 | PRIMARY | commit pin `de8841190ea6` | C-W4-029 |
| 44 | NVIDIA/KAI-Scheduler @ 2e3015e96fbae1680125a5802d0596a1183321ef | 2026-11-10 | PRIMARY | commit pin `2e3015e96fba` | C-W4-034 |
| 45 | ai-dynamo/dynamo @ 0f6b82b732183d2a012fe9b8fc75a87951ff223c | 2026-11-10 | PRIMARY | commit pin `0f6b82b73218` | C-W4-035 |
| 46 | Project-HAMi/HAMi @ 2c76cd56b02dcbbb9c0fefbe201809ce6ad757ef | 2026-11-10 | PRIMARY | commit pin `2c76cd56b02d` | C-W4-036 |
| 47 | intel/intel-device-plugins-for-kubernetes @ 657f72da9fab2fad3ab164df7895bcbda0a0d349 | 2026-11-10 | PRIMARY | commit pin `657f72da9fab` | C-W4-065 |
| 48 | NousResearch/hermes-agent @ a55a299b6520dd30bab2871bb58dffbae2f8a915 | 2026-11-10 | PRIMARY | commit pin `a55a299b6520` | C-W4-058 |
| 49 | siderolabs/sbc-raspberrypi @ 9fa9252cca1a832a6154e3f431927302bb09d9bb; siderolabs/sbc-jetson @ 6468a58b8d1191869ec92dad7d31821c1c2a9de6 | 2026-11-10 | PRIMARY | commit pin `9fa9252cca1a` | C-W4-064 |
| 50 | cncf/k8s-ai-conformance @ c64e5bc8085da207715df96e458f2c6585c9f53e | 2026-11-10 | PRIMARY | commit pin `c64e5bc8085d` | C-W4-038 |
| 51 | cncf/k8s-conformance @ 4772d34f020b9408bfa9957b9c244dcb0e8d5d24 | 2026-11-10 | PRIMARY | commit pin `4772d34f020b` | C-W4-073 |
| 52 | context/01-proven-infrastructure-cluster.md | 2026-11-10 | — | saved: `context/01-proven-infrastructure-cluster.md` | — |
| 53 | Founder infrastructure repo, docs/portability/DO-LOCK-IN.md (commit 5ca0ca62, 2026-10-23), read-only on 2026-11-10 as context/01 §14.3 instr | 2026-11-10 | — | saved: `docs/portability/DO-LOCK-IN.md` | C-W4-063 |
| 54 | research/platform/verify-kubernetes-distro.md (VK8S) | 2026-11-10 | — | saved: `research/platform/verify-kubernetes-distro.md` | — |
| 55 | research/platform/fedora-iot-and-redhat-edge-deep-dive.md | 2026-11-10 | — | saved: `research/platform/fedora-iot-and-redhat-edge-deep-dive.md` | — |
| 56 | research-output/evidence/lab/w8-nats-leaf-buffer/ (README, run-1.log) | 2026-11-10 | — | — | C-W4-055 |

### W5

Tag file: [`evidence/sources/W5.md`](evidence/sources/W5.md) · 19 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://docs.k3s.io/datastore/backup-restore | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261111011629/https://docs.k3s.io/datastore/backup-restore | C-W5-003, 004 |
| 2 | https://docs.k3s.io/cli/etcd-snapshot | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261111011648/https://docs.k3s.io/cli/etcd-snapshot | C-W5-011…016 |
| 3 | https://velero.io/docs/v1.18/file-system-backup/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260603220310/https://velero.io/docs/v1.18/file-system-backup/ | C-W5-020…022 |
| 4 | https://umbrel.com/support/backups-and-recovery/backing-up-your-data | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261102030304/https://umbrel.com/support/backups-and-recovery/backing-up-your-data | C-W5-048 |
| 5 | https://community.umbrel.com/t/backups-die-silently-when-kopias-cache-exhausts-sd-card-inodes-umbrelos-1-7-4/25377 | 2026-11-10 | SECONDARY | saved copy in `sources/W5/` · sha256 `8331cd76915f9b38…` | C-W5-047 |
| 6 | https://community.umbrel.com/t/smb-network-backup-restore-fails-infinite-loading-in-onboarding/25506 | 2026-11-10 | SECONDARY | saved copy in `sources/W5/` · sha256 `822bf7e59d9e0051…` | C-W5-049 |
| 7 | https://community.home-assistant.io/t/lost-encryption-key/913110 | 2026-11-10 | SECONDARY | saved copy in `sources/W5/` · sha256 `3cb5d9524a30293e…` | C-W5-051 |
| 8 | https://forums.truenas.com/t/potential-k3s-database-corruption-issue-need-assistance/9038 | 2026-11-10 | SECONDARY | saved copy in `sources/W5/` · sha256 `c1f3ac4a347a02d5…` | C-W5-052 |
| 9 | README.md | 2026-11-10 | — | saved: `README.md` · sha256 `b9f663fd8a842ca6…` | — |
| 10 | scripts/drill.sh | 2026-11-10 | — | hash only `c52abf876b0b1a2d…` (copy not in repo) | — |
| 11 | shared/reverify.sh | 2026-11-10 | — | hash only `2710f7667c5352e5…` (copy not in repo) | — |
| 12 | logs/a1.log (SQLite box, H1, backup) | 2026-11-10 | — | hash only `6dbc95cbc331304d…` (copy not in repo) | — |
| 13 | logs/a1-attempt1-race.log (first run aborted: ServiceAccount race in the script) | 2026-11-10 | — | hash only `65cf8568fbeb1a66…` (copy not in repo) | — |
| 14 | logs/b1.log (SQLite restore on fresh VM) | 2026-11-10 | — | hash only `b9fec5d951e0911f…` (copy not in repo) | — |
| 15 | logs/b2.log (convert to etcd, snapshot) | 2026-11-10 | — | hash only `8b4b77b1a570152b…` (copy not in repo) | — |
| 16 | logs/a2.log (wipe + etcd restore) | 2026-11-10 | — | hash only `6ce66faccab16e0f…` (copy not in repo) | — |
| 17 | logs/a2-reverify.log / b2-reverify.log | 2026-11-10 | — | hash only `fe345ad70f18d033…` (copy not in repo) | — |
| 18 | logs/plaintext-check.log | 2026-11-10 | — | saved copy in `sources/W5/` · sha256 `edc23cb533e03330…` | — |
| 19 | logs/pv-type.log | 2026-11-10 | — | saved copy in `sources/W5/` · sha256 `b7a2c0c03dc7db76…` | — |

### W6

Tag file: [`evidence/sources/W6.md`](evidence/sources/W6.md) · 46 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R2847 | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261101140653/https://eur-lex.europa.eu/eli/reg/2024/2847/oj | C-W6-001…016, 075, 076 |
| 2 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32025R2392 | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261020080018/https://eur-lex.europa.eu/eli/reg_impl/2025/2392/oj | C-W6-017 |
| 3 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R0030 | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260920225034/https://eur-lex.europa.eu/eli/reg_del/2022/30/oj | C-W6-020 |
| 4 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32025D0138 | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260708091327/https://eur-lex.europa.eu/eli/dec_impl/2025/138/oj | C-W6-021 |
| 5 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679 | 2026-11-10 | PRIMARY | saved: `W6-archive/HASHES.txt` | C-W6-037 |
| 6 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32026R1744 | 2026-11-10 | PRIMARY | saved: `W6-archive/HASHES.txt` | C-W6-042 |
| 7 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32023R1230 | 2026-11-10 | PRIMARY | saved: `W6-archive/HASHES.txt` | C-W6-043 |
| 8 | eCFR 16 CFR Part 312 (COPPA Rule), API api/versioner/v1/full/2026-11-01/title-16.xml?part=312 | 2026-11-10 | PRIMARY | saved: `W6-archive/HASHES.txt` | C-W6-035, 036 |
| 9 | eCFR 47 CFR 15.101 and Part 8 (FCC IoT Label) | 2026-11-10 | PRIMARY | — | C-W6-039, 040 |
| 10 | https://www.legislation.gov.uk/uksi/2023/1007/made | 2026-11-10 | PRIMARY | saved: `W6-archive/HASHES.txt` | C-W6-041 |
| 11 | https://cppa.ca.gov/regulations/ccpa_updates.html | 2026-11-10 | PRIMARY | saved: `cppa.ca.gov/regulations/ccpa_updates.html` | C-W6-038 |
| 12 | https://web.archive.org/web/20261101003415/https://le.fbi.gov/file-repository/cjis_security_policy_v6-1_20260625-1.pdf | 2026-11-10 | PRIMARY | Wayback: https://web.archive.org/web/20261101003415/https://le.fbi.gov/file-repository/cjis_security_policy_v6-1_20260625-1.pdf | C-W6-033, 077 |
| 13 | https://www.etsi.org/newsroom/press-releases/etsi-launches-approval-process-for-17-european-standards-supporting-the-cyber-resilience-act/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261102180324/https://www.etsi.org/newsroom/press-releases/etsi-launches-approval-process-for-17-european-standards-supporting-the-cyber-resilience-act/ | C-W6-018 |
| 14 | https://docbox.etsi.org/cyber/CYBER/Open/EN_304-626_V1.0.1_2026-08-12_Operating-Systems_Enquiry-draft.pdf | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260902222720/https://docbox.etsi.org/CYBER/CYBER/Open/EN_304-626_V1.0.1_2026-08-12_Operating-Systems_Enquiry-draft.pdf | C-W6-019 |
| 15 | https://csrc.nist.gov/projects/fips-140-3-transition-effort | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261101002734/https://csrc.nist.gov/projects/fips-140-3-transition-effort | C-W6-024 |
| 16 | CMVP certificates #4407, #4735, #4985, #5247 (csrc.nist.gov/projects/cryptographic-module-validation-program/certificate/<n>) and security p | 2026-11-10 | PRIMARY | saved: `W6-archive/cmvp-sp-4985-5247-excerpt.txt` | C-W6-026, 028…030, 032 |
| 17 | https://go.dev/doc/security/fips140 | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261101110200/https://go.dev/doc/security/fips140 | C-W6-028 |
| 18 | https://openssl-library.org/source/ | 2026-11-10 | PRIMARY | — | C-W6-031 |
| 19 | https://ubuntu.com/security/fips | 2026-11-10 | PRIMARY | — | C-W6-034 |
| 20 | https://slsa.dev/spec/v1.2/ | 2026-11-10 | PRIMARY | — | C-W6-065 |
| 21 | https://genai.owasp.org/llmrisk/llm01-prompt-injection/ | 2026-11-10 | PRIMARY | saved: `ARCH5/owasp-llm01-2025-prompt-injection.txt` | C-ARCH5-003; C-W6-068 |
| 22 | https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices | 2026-11-10 | PRIMARY | — | C-W6-069 |
| 23 | Debenedetti et al., CaMeL, arXiv:2503.18813v2 | 2026-11-10 | PRIMARY | — | C-W6-070 |
| 24 | https://mavlink.io/en/guide/message_signing.html | 2026-11-10 | PRIMARY | saved: `mavlink.io/en/guide/message_signing.html` | C-W6-071 |
| 25 | https://wiki.debian.org/LTS | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261101234839/https://wiki.debian.org/LTS | C-W6-022 |
| 26 | https://www.freexian.com/lts/extended/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261021170327/https://www.freexian.com/lts/extended/ | C-W6-023 |
| 27 | https://docs.rke2.io/security/fips_support | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260914013434/https://docs.rke2.io/security/fips_support | C-W6-025 |
| 28 | https://support.microsoft.com/en-us/servicing/os/secure-boot/2025/06/windows-secure-boot-certificate-expiration-and-ca-updates | 2026-11-10 | PRIMARY | — | C-W6-044 |
| 29 | https://techcommunity.microsoft.com/blog/linuxandopensourceblog/what-it-teams-need-to-know-about-linux-secure-boot-certificates-expiring-in-2026/45… | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260712120516/… | C-W6-045 |
| 30 | https://wiki.debian.org/SecureBoot | 2026-11-10 | PRIMARY | — | C-W6-046 |
| 31 | https://www.freedesktop.org/software/systemd/man/latest/systemd-cryptenroll.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261030231727/… | C-W6-047 |
| 32 | http://web.archive.org/web/20260910232054/https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/SD/Security/SecureBoot.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260910232054/https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/SD/Security/SecureBoot.html | C-W6-059…061 |
| 33 | https://docs.k3s.io/security/hardening-guide | 2026-11-10 | PRIMARY | — | C-W6-062, 063 |
| 34 | Kubernetes AppArmor tutorial and Pod Security Standards (kubernetes.io) | 2026-11-10 | PRIMARY | — | C-W6-064 |
| 35 | https://docs.github.com/en/actions/concepts/security/artifact-attestations | 2026-11-10 | PRIMARY | — | C-W6-066 |
| 36 | https://docs.sigstore.dev/cosign/verifying/verify/ | 2026-11-10 | PRIMARY | — | C-W6-067 |
| 37 | rugix/rugix @ c2f5f4f3db45890fe542dbc9608be969a3432cc1 (2026-11-10; releases v1.4.0 2026-11-02) | 2026-11-10 | PRIMARY | commit pin `c2f5f4f3db45` | C-W6-048…050 |
| 38 | getumbrel/umbrel @ c43beed964074d08865d648ca9ac3359826a14ff (2026-11-04) | 2026-11-10 | PRIMARY | commit pin `c43beed96407` | C-W6-051, 052 |
| 39 | home-assistant/operating-system @ ab7d0f1a0174760353780a21be2befecbc80a672 | 2026-11-10 | PRIMARY | commit pin `ab7d0f1a0174` | C-W6-053 |
| 40 | home-assistant/supervisor @ 040f14cd8aa2902401d30aaeb0cb71215854c78c | 2026-11-10 | PRIMARY | commit pin `040f14cd8aa2` | C-W6-054 |
| 41 | beclab/Olares @ e7fe1c9634f26530386c2033a33be7a9495704f3 | 2026-11-10 | PRIMARY | commit pin `e7fe1c9634f2` | C-W6-055 |
| 42 | raspberrypi/documentation @ 21d772e7ee022e36a8f43c3ee75e20ca359fb832 | 2026-11-10 | PRIMARY | commit pin `21d772e7ee02` | C-W6-056…058 |
| 43 | raspberrypi/rpi-sb-provisioner @ 8c59729412817413cb89c20fb9c82594ad30c53d | 2026-11-10 | PRIMARY | commit pin `8c5972941281` | C-W6-058 |
| 44 | rancher/rke2 @ 15142fcaf53a6a25610ef7e5c9bcceeee75bc00b | 2026-11-10 | PRIMARY | commit pin `15142fcaf53a` | C-W6-027 |
| 45 | openbao/openbao @ 0d706a0c474ebf26265d0d1e4d9060320cd8ae13; Infisical/infisical @ 41f8c8bbb76ae91774ae1fd8350b4743e8cc6237 | 2026-11-10 | PRIMARY | commit pin `0d706a0c474e` | C-W6-072, 073 |
| 46 | GitHub REST API metadata for k3s-io/k3s, rancher/rke2, kyverno/kyverno, sigstore/cosign, theupdateframework/go-tuf, falcosecurity/falco, aqu | 2026-11-10 | — | — | C-W6-074 |

### W7

Tag file: [`evidence/sources/W7.md`](evidence/sources/W7.md) · 42 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://developer.nvidia.com/embedded/lifecycle | 2026-11-10 | PRIMARY | saved: `W7-archive/jetson-lifecycle.txt` | C-W7-001…003 |
| 2 | https://developer.nvidia.com/embedded/jetson-linux-archive | 2026-11-10 | PRIMARY | saved: `W7-archive/jetson-linux-archive.txt` | C-W7-004…006 |
| 3 | https://developer.nvidia.com/embedded/jetpack | 2026-11-10 | PRIMARY | saved: `W7-archive/jetpack.txt` | C-W7-007 |
| 4 | https://developer.nvidia.com/embedded/jetpack/downloads/archive-7.2 | 2026-11-10 | PRIMARY | saved: `W7-archive/jetpack-archive-7.2.txt` | C-W7-008 |
| 5 | https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SD/Kernel/RealTimeKernel.html | 2026-11-10 | PRIMARY | saved: `W7-archive/r39.2.1-rt-kernel.txt` | C-W7-009 |
| 6 | https://nvidia-isaac-ros.github.io/getting_started/compute/preempt_setup.html | 2026-11-10 | PRIMARY | saved: `W7-archive/isaac-ros-preempt.txt` | C-W7-010 |
| 7 | https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SD/Kernel/BringYourOwnKernel.html | 2026-11-10 | PRIMARY | saved: `W7-archive/r39.2.1-byok.txt` | C-W7-011 |
| 8 | https://github.com/torvalds/linux/tree/v6.18/arch/arm64/boot/dts/nvidia | 2026-11-10 | PRIMARY | saved copy in `sources/W7/` | C-W7-012, 049 |
| 9 | https://docs.nvidia.com/jetson/archives/r39.2.1/DeveloperGuide/SD/Bootloader/UpdateAndRedundancy.html | 2026-11-10 | PRIMARY | saved: `W7-archive/r39.2.1-update-redundancy.txt` | C-W7-013 |
| 10 | https://github.com/OE4T/meta-tegra | 2026-11-10 | PRIMARY | commit pin `80f9e27f6499` | C-W7-014, 015, 056, 057 |
| 11 | https://api.github.com/repos/OE4T/meta-tegra/stats/contributors | 2026-11-10 | PRIMARY-METADATA | API response (values quoted in the claim) | C-W7-016 |
| 12 | https://github.com/OE4T/tegra-demo-distro | 2026-11-10 | PRIMARY | commit pin `e151343f1dd3` | C-W7-017 |
| 13 | https://github.com/mendersoftware/meta-mender-community | 2026-11-10 | PRIMARY-METADATA | API response (values quoted in the claim) | C-W7-018 |
| 14 | https://github.com/rugix/rugix | 2026-11-10 | PRIMARY | commit pin `6d7fc277919b` | C-W7-019, 058 |
| 15 | https://github.com/torvalds/linux | 2026-11-10 | PRIMARY | saved: `Documentation/admin-guide/cgroup-v2.rst` | C-W7-020, 023 |
| 16 | https://packages.debian.org/search?keywords=linux-image-rt&suite=trixie | 2026-11-10 | PRIMARY | saved: `W7-archive/debian-trixie-linux-image-rt.txt` | C-W7-021 |
| 17 | https://salsa.debian.org/kernel-team/linux/-/raw/debian/6.12.116-1/debian/config/config | 2026-11-10 | PRIMARY | version-tag URL (not a SHA) | C-W7-022 |
| 18 | http://archive.raspberrypi.com/debian/dists/trixie/main/binary-arm64/Packages.gz | 2026-11-10 | PRIMARY | saved: `W7-archive/rpi-trixie-linux-image-packages.txt` | C-W7-024 |
| 19 | https://www.raspberrypi.com/documentation/computers/linux_kernel.html | 2026-11-10 | PRIMARY | — | C-W7-025 |
| 20 | https://github.com/ros-infrastructure/rep | 2026-11-10 | PRIMARY | commit pin `11ca24a41f31` | C-W7-026 |
| 21 | https://github.com/ros2/ros2_documentation | 2026-11-10 | PRIMARY | commit pin `1c5c20cb9f14` | C-W7-027…029 |
| 22 | https://packages.debian.org/search?keywords=rclcpp&suite=trixie | 2026-11-10 | PRIMARY | saved copy in `sources/W7/` | C-W7-030 |
| 23 | https://nvidia-isaac-ros.github.io/getting_started/index.html | 2026-11-10 | PRIMARY | saved: `W7-archive/isaac-ros-getting-started.txt` | C-W7-031 |
| 24 | https://github.com/ros2/rmw_zenoh | 2026-11-10 | PRIMARY | commit pin `4ce65216eed3` | C-W7-032 |
| 25 | https://fast-dds.docs.eprosima.com/en/latest/docker/shm_docker.html | 2026-11-10 | PRIMARY | saved: `W7-archive/fastdds-shm-docker.txt` | C-W7-033 |
| 26 | https://kubernetes.io/docs/concepts/security/pod-security-standards/ | 2026-11-10 | PRIMARY | saved: `W7-archive/k8s-pss.txt` | C-W7-034 |
| 27 | https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/ | 2026-11-10 | PRIMARY | — | C-W7-035 |
| 28 | https://control.ros.org/jazzy/doc/ros2_control/controller_manager/doc/userdoc.html | 2026-11-10 | PRIMARY | — | C-W7-036 |
| 29 | https://github.com/NVIDIA/cloud-native-docs | 2026-11-10 | PRIMARY | commit pin `d856ea69d8d9` | C-W7-037 |
| 30 | https://github.com/NVIDIA/k8s-device-plugin | 2026-11-10 | PRIMARY | commit pin `de8841190ea6` | C-W7-038 |
| 31 | https://docs.clearpathrobotics.com/docs/ros/installation/robot | 2026-11-10 | PRIMARY | saved: `W7-archive/clearpath-robot-install.txt` | C-W7-039 |
| 32 | https://dev.bostondynamics.com/docs/payload/docker_containers | 2026-11-10 | PRIMARY | saved: `W7-archive/bd-coreio-docker.txt` | C-W7-040 |
| 33 | https://docs.px4.io/main/en/flight_controller/modalai_voxl_2 | 2026-11-10 | PRIMARY | — | C-W7-041 |
| 34 | https://docs.auterion.com/vehicle-operation/settings-and-maintenance/skynode-software-update | 2026-11-10 | PRIMARY | — | C-W7-042 |
| 35 | https://docs.viam.com/reference/viam-agent/ | 2026-11-10 | PRIMARY | — | C-W7-043 |
| 36 | https://docs.px4.io/main/en/middleware/uxrce_dds.html | 2026-11-10 | PRIMARY | — | C-W7-044 |
| 37 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32023R1230 | 2026-11-10 | PRIMARY | saved: `W7-archive/eu-machinery-reg-2023-1230-excerpts.txt` | C-W7-045, 046 |
| 38 | https://www.anthropic.com/news/model-hardware-standard-research-preview | 2026-11-10 | PRIMARY | saved: `W7-archive/anthropic-mhs.txt` | C-W7-047 |
| 39 | https://blogs.nvidia.com/blog/jetson-thor-robotics-edge-ai-agent/ | 2026-11-10 | PRIMARY | saved: `W7-archive/nvidia-t3000-blog.txt` | C-W7-048 |
| 40 | GitHub repository metadata via gh api (Isaac-GR00T, Cosmos, lerobot, newton, IsaacLab, PX4, ArduPilot, micro_ros_setup, open-rmf/rmf, dora,  | 2026-11-10 | PRIMARY-METADATA | — | C-W7-050…053, 059 |
| 41 | https://avweb.com/aviation-news/aviation-law/faa-reopens-part-108-bvlos-comment-period/ | 2026-11-10 | SECONDARY | — | C-W7-054 |
| 42 | https://www.iso.org/standard/73933.html | 2026-11-10 | SECONDARY | saved copy in `sources/W7/` | C-W7-055 |

### W8

Tag file: [`evidence/sources/W8.md`](evidence/sources/W8.md) · 70 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | https://packages.debian.org/trixie/linux-image-rt-arm64 | 2026-11-10 | PRIMARY | saved copy in `sources/W8/` · sha256 `d19b9ef1e716a61d…` | C-W8-001 |
| 2 | https://sources.debian.org/data/main/l/linux/6.12.107-1/debian/config/config | 2026-11-10 | PRIMARY | version-tag URL (not a SHA) | C-W8-002, 003 |
| 3 | https://packages.debian.org/trixie/libopen62541-1.4 | 2026-11-10 | PRIMARY | — | C-W8-004 |
| 4 | https://sources.debian.org/api/src/mosquitto/ | 2026-11-10 | PRIMARY | — | C-W8-005 |
| 5 | https://sources.debian.org/data/main/w/wpa/2:2.10-24/debian/config/wpasupplicant/linux | 2026-11-10 | PRIMARY | saved copy in `sources/W8/` | C-W8-006 |
| 6 | https://github.com/nats-io/nats-server/blob/0e5b4f72ac27f7fbb3bb0fe85fd964f5d4c6b664/server/mqtt.go#L3896-L3901 | 2026-11-10 | PRIMARY | commit pin `0e5b4f72ac27` | C-W8-007 |
| 7 | https://github.com/nats-io/nats-server/blob/0e5b4f72ac27f7fbb3bb0fe85fd964f5d4c6b664/server/mqtt.go#L5288-L5300 | 2026-11-10 | PRIMARY | commit pin `0e5b4f72ac27` | C-W8-008 |
| 8 | https://github.com/nats-io/nats-server/blob/0e5b4f72ac27f7fbb3bb0fe85fd964f5d4c6b664/server/mqtt.go#L6580-L6594 | 2026-11-10 | PRIMARY | commit pin `0e5b4f72ac27` | C-W8-009 |
| 9 | https://github.com/eclipse-sparkplug/sparkplug/blob/e45b61002a2a0cacb4f11fa4be88670435ccfcb0/specification/src/main/asciidoc/chapters/Sparkplug_10_… | 2026-11-10 | PRIMARY | commit pin `e45b61002a2a` | C-W8-010 |
| 10 | https://github.com/eclipse-mosquitto/mosquitto/blob/fda14f2c196d9d2fcdd07d6c5d31a673524f7368/LICENSE.txt | 2026-11-10 | PRIMARY | commit pin `fda14f2c196d` | C-W8-011 |
| 11 | https://github.com/nanomq/nanomq/blob/9c9a313b4038640824365f5be68fbfa9a0310889/README.md | 2026-11-10 | PRIMARY | commit pin `9c9a313b4038` | C-W8-012 |
| 12 | https://github.com/emqx/emqx/blob/ef2beebdc29f89540827d7663c2f9a0e63130c7b/LICENSE | 2026-11-10 | PRIMARY | commit pin `ef2beebdc29f` | C-W8-013 |
| 13 | https://github.com/markqvist/Reticulum/blob/16621a78e35e2ba5156c72af7fe492458ba092d5/LICENSE | 2026-11-10 | PRIMARY | commit pin `16621a78e35e` | C-W8-014 |
| 14 | https://github.com/meshtastic/ATAK-Plugin/blob/784530f8bc9271d59d33caf8afb40f464cab032f/README.md | 2026-11-10 | PRIMARY | commit pin `784530f8bc92` | C-W8-015 |
| 15 | https://meshtastic.org/docs/software/integrations/mqtt/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261011193834/https://meshtastic.org/docs/software/integrations/mqtt/ | C-W8-016 |
| 16 | https://github.com/TAK-Product-Center/Server/blob/5187abd46d827d37cfc5708805eced197a837e49/LICENSE.md | 2026-11-10 | PRIMARY | commit pin `5187abd46d82` | C-W8-017 |
| 17 | https://raw.githubusercontent.com/TAK-Product-Center/Server/5187abd46d827d37cfc5708805eced197a837e49/src/docs/TAK_Server_Configuration_Guide.pdf | 2026-11-10 | PRIMARY | commit pin `5187abd46d82` | C-W8-018 |
| 18 | https://sources.debian.org/api/src/openjdk-17/ | 2026-11-10 | PRIMARY | — | C-W8-019 |
| 19 | https://github.com/TAK-Product-Center/atak-civ/blob/9f6893dd657feacc35ec5de03dad721c2e44170e/LICENSE.md | 2026-11-10 | PRIMARY | commit pin `9f6893dd657f` | C-W8-020 |
| 20 | https://docs.opentakserver.io/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260528125651/https://docs.opentakserver.io/ | C-W8-021 |
| 21 | https://github.com/FreeTAKTeam/FreeTakServer | 2026-11-10 | PRIMARY-METADATA | commit pin `19fcc61` | C-W8-022 |
| 22 | https://github.com/dfpc-coe/CloudTAK/blob/6f77c538e6a7f46f4083d6b2004562b012ac5d62/README.md | 2026-11-10 | PRIMARY | commit pin `6f77c538e6a7` | C-W8-023 |
| 23 | https://www.home-assistant.io/installation/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261103013015/https://www.home-assistant.io/installation/ | C-W8-024, 030 |
| 24 | https://www.home-assistant.io/integrations/matter/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261030115120/https://www.home-assistant.io/integrations/matter/ | C-W8-025 |
| 25 | https://github.com/getumbrel/umbrel-apps/blob/51aac978c67c7c9bbe7e0b42f64ff5f3139c8763/home-assistant/docker-compose.yml#L4-L13 | 2026-11-10 | PRIMARY | commit pin `51aac978c67c` | C-W8-026 |
| 26 | https://github.com/beclab/apps/blob/37a1fb4f44b2428feb7978b25fdc798d6d6310ed/homeassistant/templates/deployment.yaml#L84-L97 | 2026-11-10 | PRIMARY | commit pin `37a1fb4f44b2` | C-W8-027 |
| 27 | https://github.com/getumbrel/umbrel-apps/tree/51aac978c67c7c9bbe7e0b42f64ff5f3139c8763 | 2026-11-10 | PRIMARY | commit pin `51aac978c67c` | C-W8-028 |
| 28 | https://esphome.io/components/api/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261005152832/https://esphome.io/components/api/ | C-W8-029, 051 |
| 29 | https://esphome.io/components/switch/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261021130229/https://esphome.io/components/switch/ | C-W8-030 |
| 30 | https://github.com/esphome/esphome/blob/b03e03e4654660d2693122216c3c0153e9708d21/LICENSE | 2026-11-10 | PRIMARY | commit pin `b03e03e46546` | C-W8-031 |
| 31 | https://www.chirpstack.io/docs/chirpstack/integrations/mqtt.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261014021058/https://www.chirpstack.io/docs/chirpstack/integrations/mqtt.html | C-W8-032 |
| 32 | https://www.moxa.com/en/products/industrial-computing/system-software/moxa-industrial-linux | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261021171537/https://www.moxa.com/en/products/industrial-computing/system-software/moxa-industrial-linux | C-W8-033 |
| 33 | https://www.linuxfoundation.org/press/civil-infrastructure-platform-achieves-significant-cybersecurity-milestone-with-iec-62443-compliance | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261012195104/https://www.linuxfoundation.org/ | C-W8-034 |
| 34 | https://webstore.iec.ch/en/publication/34421 | 2026-11-10 | PRIMARY-METADATA | Wayback: http://web.archive.org/web/20261031085608/https://webstore.iec.ch/en/publication/34421 | C-W8-035 |
| 35 | https://csrc.nist.gov/pubs/sp/800/82/r3/final | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261102111322/https://csrc.nist.gov/pubs/sp/800/82/r3/final | C-W8-021, 036 |
| 36 | https://cache.industry.siemens.com/dl/files/702/109990702/att_1333795/v1/Industrial_Edge_Own_Device_en-US.pdf | 2026-11-10 | PRIMARY | saved: `cache.industry.siemens.com/dl/files/702/109990702/att_1333795/v1/Industrial_Edge_Own_Device_en-US.pdf` · sha256 `7f454777df4e7f01…` | C-W8-037 |
| 37 | https://github.com/siemens/meta-iot2050/blob/5be02695dcd46e0a041fb0e2fe6e3e8530e5b203/kas/iot2050.yml#L17-L40 | 2026-11-10 | PRIMARY | commit pin `5be02695dcd4` | C-W8-038 |
| 38 | https://revolutionpi.com/en/tutorials/images | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20241012011741/https://revolutionpi.com/en/tutorials/images | C-W8-039 |
| 39 | https://github.com/raspberrypi/linux/tree/e045ff670093cf3d515d121ab2678ce295f61f43/arch/arm64/configs | 2026-11-10 | PRIMARY | commit pin `e045ff670093` | C-W8-040 |
| 40 | https://www.raspberrypi.com/documentation/security/security-architecture.html | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260814154455/https://www.raspberrypi.com/documentation/security/security-architecture.html | C-W8-041 |
| 41 | https://fidoalliance.org/specifications/download-iot-specifications/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260721161703/https://fidoalliance.org/specifications/download-iot-specifications/ | C-W8-042 |
| 42 | https://github.com/fdo-rs/fido-device-onboard-rs/blob/99e4b691a4f9ebeb53a049c817ce4e6d9e73b46a/README.md | 2026-11-10 | PRIMARY | commit pin `99e4b691a4f9` | C-W8-043 |
| 43 | https://github.com/fido-device-onboard/go-fdo/blob/65061850e1c91a2cfe83c2dea748989a7e70c110/README.md | 2026-11-10 | PRIMARY | commit pin `65061850e1c9` | C-W8-044 |
| 44 | https://standards.ieee.org/ieee/802.1AR/6995/ | 2026-11-10 | PRIMARY-METADATA | Wayback: http://web.archive.org/web/20260804011956/https://standards.ieee.org/ieee/802.1AR/6995/ | C-W8-040, 045 |
| 45 | https://github.com/rugix/rugix-docs/blob/227f902790fe876b5a0d0df02e9c56e7cf1f6459/src/content/docs-ctrl/1.4/integration/fleet-management/index.md#L15 | 2026-11-10 | PRIMARY | commit pin `227f902790fe` | C-W8-046 |
| 46 | https://github.com/thin-edge/thin-edge.io | 2026-11-10 | PRIMARY | commit pin `5d3ac4a` | C-W8-047 |
| 47 | https://github.com/flightctl/flightctl/blob/f99870eafa95003d1511577efc1c6e8c4ce7d5d1/README.md#L29-L58 | 2026-11-10 | PRIMARY | commit pin `f99870eafa95` | C-W8-048 |
| 48 | https://docs.k3s.io/installation/requirements | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261111011811/https://docs.k3s.io/installation/requirements | C-W8-049 |
| 49 | research-output/evidence/lab/w8-nats-leaf-buffer/results.md | 2026-11-10 | PRIMARY | saved: `research-output/evidence/lab/w8-nats-leaf-buffer/results.md` | C-W8-050 |
| 50 | https://developer.android.com/develop/connectivity/satellite/constrained-networks | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20260920135001/https://developer.android.com/develop/connectivity/satellite/constrained-networks | C-W8-051 |
| 51 | https://www.droid-life.com/2025/10/01/t-mobile-lists-satellite-ready-apps-for-data-connectivity/ | 2026-11-10 | SECONDARY | — | C-W8-052 |
| 52 | https://margo.org/ | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261015055335/https://margo.org/ | C-W8-053 |
| 53 | https://github.com/margo/specification/blob/2eca50a38a9265942b9f8d8ee3138a17fe0ebce3/LICENSE | 2026-11-10 | PRIMARY | commit pin `2eca50a38a92` | C-W8-054 |
| 54 | https://github.com/open62541/open62541/releases | 2026-11-10 | PRIMARY-METADATA | commit pin `667acbc` | C-W8-055 |
| 55 | https://github.com/apache/plc4x/releases | 2026-11-10 | PRIMARY-METADATA | — | C-W8-056 |
| 56 | https://github.com/autonomy-logic/openplc-runtime/releases | 2026-11-10 | PRIMARY-METADATA | — | C-W8-057 |
| 57 | https://github.com/project-akri/akri/releases | 2026-11-10 | PRIMARY-METADATA | — | C-W8-058 |
| 58 | https://github.com/bacnet-stack/bacnet-stack/blob/077729bb3864537afac51b62394b48c03c0856b3/README.md | 2026-11-10 | PRIMARY | commit pin `077729bb3864` | C-W8-059 |
| 59 | https://github.com/getumbrel/umbrel-apps/blob/51aac978c67c7c9bbe7e0b42f64ff5f3139c8763/zigbee2mqtt/docker-compose.yml#L9-L14 | 2026-11-10 | PRIMARY | commit pin `51aac978c67c` | C-W8-060 |
| 60 | https://github.com/home-assistant/core/releases | 2026-11-10 | PRIMARY-METADATA | — | C-W8-061 |
| 61 | https://github.com/TAK-Product-Center/Server/tags | 2026-11-10 | PRIMARY-METADATA | — | C-W8-062 |
| 62 | research/platform/fedora-iot-and-redhat-edge-deep-dive.md | 2026-11-10 | SECONDARY | saved: `research/platform/fedora-iot-and-redhat-edge-deep-dive.md` | C-W8-063 |
| 63 | research/platform/iiot-landscape-and-requirements.md | 2026-11-10 | — | saved: `research/platform/iiot-landscape-and-requirements.md` | — |
| 64 | research/platform/robotics-iot-xr-nvidia.md §3–§7 | 2026-11-10 | — | saved: `research/platform/robotics-iot-xr-nvidia.md` | — |
| 65 | research/platform/fedora-iot-and-redhat-edge-deep-dive.md §7, §9 | 2026-11-10 | SECONDARY | saved: `research/platform/fedora-iot-and-redhat-edge-deep-dive.md` | C-W8-063 |
| 66 | context/01-proven-infrastructure-cluster.md §5, §7 | 2026-11-10 | — | saved: `context/01-proven-infrastructure-cluster.md` | — |
| 67 | 02-competitors/villageos.md, home-assistant-os.md (parallel W1 teardowns) | 2026-11-10 | — | saved: `home-assistant-os.md` | — |
| 68 | evidence/claims/W7.csv C-W7-024 | 2026-11-10 | — | saved: `evidence/claims/W7.csv` | C-W7-024 |
| 69 | https://github.com/nats-io/nats-server/releases/tag/v2.15.2 | 2026-11-10 | PRIMARY | — | C-W4-057 |
| 70 | Search only, not cited as fact: TCG 'TPM 2.0 Keys for Device Identity and Attestation' version (results conflict v1.1 / v1.10) | 2026-11-10 | UNVERIFIED | — | — |

### W9

Tag file: [`evidence/sources/W9.md`](evidence/sources/W9.md) · 39 entries

| # | Source | Accessed | Type | Archive | Claims supported |
|---|---|---|---|---|---|
| 1 | modelcontextprotocol/python-sdk | 2026-11-10 | PRIMARY | commit pin `77001c96f950` | — |
| 2 | modelcontextprotocol/typescript-sdk | 2026-11-10 | PRIMARY | commit pin `919bb8ea88b6` | — |
| 3 | modelcontextprotocol/go-sdk | 2026-11-10 | PRIMARY | commit pin `328036ea2090` | — |
| 4 | goauthentik/authentik | 2026-11-10 | PRIMARY | commit pin `630a866d4341` | — |
| 5 | getumbrel/umbrel | 2026-11-10 | PRIMARY | commit pin `6f357e18d0a4` | — |
| 6 | beclab/Olares | 2026-11-10 | PRIMARY | commit pin `e7fe1c9634f2` | — |
| 7 | kubernetes-sigs/agent-sandbox | 2026-11-10 | PRIMARY | saved: `W9/agent-sandbox-README_dced311e.md` | — |
| 8 | containers/kubernetes-mcp-server | 2026-11-10 | PRIMARY | saved: `W9/kubernetes-mcp-server-README_13bfb96f.md` | — |
| 9 | BerriAI/litellm | 2026-11-10 | PRIMARY | commit pin `63d39b41fd4c` | — |
| 10 | https://modelcontextprotocol.io/specification/versioning.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-versioning.txt` | C-W9-001 |
| 11 | https://modelcontextprotocol.io/specification/2026-07-28/changelog.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-changelog-2026-07-28.txt` | C-W9-002, 003 |
| 12 | https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-authorization-2026-07-28.txt` | C-W9-004 |
| 13 | https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-elicitation.txt` | C-W9-005 |
| 14 | https://modelcontextprotocol.io/registry/about.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-registry-about.txt` | C-W9-006 |
| 15 | https://modelcontextprotocol.io/extensions/overview.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-extensions-overview.txt` | C-W9-007 |
| 16 | https://modelcontextprotocol.io/extensions/tasks/overview.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-tasks.txt` | C-W9-045 |
| 17 | https://modelcontextprotocol.io/community/governance.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-governance.txt` | C-W9-008 |
| 18 | https://modelcontextprotocol.io/docs/sdk.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-sdks.txt` | C-W9-010 |
| 19 | https://modelcontextprotocol.io/development/roadmap.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-roadmap.txt` | C-W9-046 |
| 20 | https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices.md | 2026-11-10 | PRIMARY | saved: `W9/mcp-security-bp.txt` | — |
| 21 | https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation | 2026-11-10 | PRIMARY | saved: `W9/lf-aaif.txt` | C-W9-009 |
| 22 | https://a2a-protocol.org/latest/ | 2026-11-10 | PRIMARY | saved: `W9/a2a-home.txt` | C-W9-024 |
| 23 | https://agentskills.io/specification | 2026-11-10 | PRIMARY | saved: `W9/agentskills-spec.txt` | C-W9-023 |
| 24 | https://www.anthropic.com/news/model-hardware-standard-research-preview | 2026-11-10 | PRIMARY | saved: `W9/anthropic-mhs.txt` | C-W16-037; C-W7-047 |
| 25 | https://www.home-assistant.io/integrations/mcp_server/ | 2026-11-10 | PRIMARY | saved: `W9/ha-mcp-server.txt` | C-W9-016 |
| 26 | https://backstage.io/docs/ai/mcp-actions | 2026-11-10 | PRIMARY | saved: `W9/backstage-mcp-actions.txt` | C-W9-017 |
| 27 | https://www.olares.com/docs/developer/cli-agent-skills | 2026-11-10 | PRIMARY | saved: `W9/olares-cli-skills.txt` | — |
| 28 | https://gvisor.dev/docs/user_guide/install/ | 2026-11-10 | PRIMARY | saved: `W9/gvisor-install.txt` | C-W9-026 |
| 29 | https://gvisor.dev/docs/architecture_guide/platforms/ | 2026-11-10 | PRIMARY | saved: `W9/gvisor-platforms.txt` | — |
| 30 | https://www.strava.com/legal/api** | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261107060610/https://www.strava.com/legal/api | — |
| 31 | https://www.strava.com/legal/api_policy** | 2026-11-10 | PRIMARY | Wayback: http://web.archive.org/web/20261107060547/https://www.strava.com/legal/api_policy | — |
| 32 | https://www.ilga.gov/Legislation/ILCS/Articles?ActID=3004&ChapterID=57 | 2026-11-10 | PRIMARY | saved: `W9/il-bipa-740ilcs14.txt` | C-W9-034, 035 |
| 33 | https://ilga.gov/ftp/Public%20Acts/103/103-0769.htm | 2026-11-10 | PRIMARY | — | — |
| 34 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679 | 2026-11-10 | PRIMARY | saved: `W9/eu-gdpr-excerpt.txt` | C-W12-049, 073; C-W6-037; C-W9-036, 037 |
| 35 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689 | 2026-11-10 | PRIMARY | saved: `W9/eu-ai-act-excerpt.txt` | C-W9-040, 041 |
| 36 | https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202601744 | 2026-11-10 | PRIMARY | saved: `W9/eu-2026-1744-omnibus-excerpt.txt` | C-W9-042 |
| 37 | https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-16?part=312 | 2026-11-10 | PRIMARY | saved: `W9/ecfr-16cfr312-coppa.txt` | C-W9-038 |
| 38 | https://app.leg.wa.gov/RCW/default.aspx?cite=19.375&full=true | 2026-11-10 | PRIMARY | saved: `W9/wa-rcw-19-375.txt` | C-W9-039 |
| 39 | https://www.w3.org/TR/webauthn-3/ | 2026-11-10 | PRIMARY | saved: `W9/w3c-webauthn-3-excerpt.txt` | C-W9-043 |

## ARCHIVE-GAP

Load-bearing web sources (supporting at least one `verified` or `partial` claim) that have **neither a Wayback capture nor a saved copy in the repo**. "Decision-grade" means at least one supported claim is used in 00, 01, 03–07 or 28. "Pinned by other means" means the fact is still checkable without the page (a merge-commit SHA, an image digest, a signed APT Release file, or API values quoted verbatim in the claim); those are lower risk but still count as gaps under the brief's rule.

**How to close each gap:** save the page text and its sha256 into `evidence/sources/<TAG>/` (masking emails and token-shaped strings first), or ask Zeus to request a Wayback capture (this environment refuses Wayback save requests), or replace the source with a SHA-pinned equivalent (for GitHub issues, `gh api` JSON saved as a file, as TD-olares did).

| # | Source | Tag | Claims | Decision-grade | Why no archive (from the tag file) |
|---|---|---|---|---|---|
| 1 | https://bugs.launchpad.net/ubuntu/+source/linux-raspi/+bug/2170238 | ARCH5 | C-DEC-006 | **yes** | API response; values quoted in the claim |
| 2 | https://github.com/k3s-io/k3s/releases/tag/v1.37.2%2Bk3s1 | LAB-rauc-1152 | C-LAB-debian-rugix-014; C-LAB-k3s-footprint-restore-001; C-W4-011; C-W5-055 | **yes** | GitHub page, not SHA-pinned |
| 3 | https://www.raspberrypi.com/products/raspberry-pi-5/ | W10 | C-W10-034; C-W2-029 | **yes** | bot wall / challenge |
| 4 | https://github.com/systemd/mkosi | W17 | C-W18-049 | **yes** | not saved |
| 5 | https://developer.apple.com/documentation/virtualization/vzgenericplatformconfiguration/isnestedvirtualizationsupported | W18 | C-W18-054 | **yes** | no archive recorded in the tag file |
| 6 | https://en.wikipedia.org/wiki/HarmonyOS_5 | W18 | C-W18-037 | **yes** | no archive recorded in the tag file |
| 7 | https://osbuild.org/docs/bootc/ | W18 | C-W18-052 | **yes** | no archive recorded in the tag file |
| 8 | https://packages.debian.org/trixie/linux-image-rt-arm64 | W18 | C-W18-006 | **yes** | bot wall / challenge |
| 9 | https://api.balena-cloud.com/v7/device_type | W2 | C-W2-040 | **yes** | API response; values quoted in the claim |
| 10 | https://cip-project.org/blog/2025/05/26/cip-is-now-supporting-five-slts-kernels | W2 | C-W2-032 | **yes** | read through the fetch tool only |
| 11 | https://documentation.ubuntu.com/core/reference/release-notes/ | W2 | C-W2-009 | **yes** | read through the fetch tool only |
| 12 | https://www.raspberrypi.com/products/raspberry-pi-5/ | W2 | C-W2-029 | **yes** | bot wall / challenge |
| 13 | https://www.redhat.com/en/blog/image-mode-for-red-hat-enterprise-linux-generally-available | W2 | C-W2-012 | **yes** | read through the fetch tool only |
| 14 | https://cloudnativenow.com/kubecon-cloudnativecon-north-america-2026/nvidia-adds-kubernetes-engine-recipes-and-snapshot-… | W4 | C-W4-039 | **yes** | no archive recorded in the tag file |
| 15 | https://docs.cilium.io/en/stable/operations/system_requirements/ | W4 | C-W4-047 | **yes** | no archive recorded in the tag file |
| 16 | https://tailscale.com/kb/1236/kubernetes-operator | W4 | C-W4-062 | **yes** | no archive recorded in the tag file |
| 17 | https://www.cncf.io/blog/2025/05/01/protecting-nats-and-the-integrity-of-open-source-cncfs-commitment-to-the-community/ | W4 | C-W4-056 | **yes** | no archive recorded in the tag file |
| 18 | https://www.cncf.io/blog/2026/10/07/kubernetes-on-edge-day-returns-to-kubecon-cloudnativecon-north-america-2026/ | W4 | C-W4-074 | **yes** | no archive recorded in the tag file |
| 19 | https://docs.github.com/en/actions/concepts/security/artifact-attestations | W6 | C-W6-066 | **yes** | GitHub page, not SHA-pinned |
| 20 | https://docs.k3s.io/security/hardening-guide | W6 | C-W6-062, 063 | **yes** | no archive recorded in the tag file |
| 21 | https://docs.sigstore.dev/cosign/verifying/verify/ | W6 | C-W6-067 | **yes** | no archive recorded in the tag file |
| 22 | https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices | W6 | C-W6-069 | **yes** | no archive recorded in the tag file |
| 23 | https://openssl-library.org/source/ | W6 | C-W6-031 | **yes** | no archive recorded in the tag file |
| 24 | https://slsa.dev/spec/v1.2/ | W6 | C-W6-065 | **yes** | no archive recorded in the tag file |
| 25 | https://support.microsoft.com/en-us/servicing/os/secure-boot/2025/06/windows-secure-boot-certificate-expiration-and-ca-u… | W6 | C-W6-044 | **yes** | no archive recorded in the tag file |
| 26 | https://ubuntu.com/security/fips | W6 | C-W6-034 | **yes** | no archive recorded in the tag file |
| 27 | https://wiki.debian.org/SecureBoot | W6 | C-W6-046 | **yes** | no archive recorded in the tag file |
| 28 | https://github.com/nats-io/nats-server/releases/tag/v2.15.2 | W8 | C-W4-057 | **yes** | GitHub page, not SHA-pinned |
| 29 | https://www.dataguard.com/cyber-resilience-act/certification/ | COST | C-COST-013 | no | read through the fetch tool only |
| 30 | https://repology.org/project/{open62541,mosquitto,libmodbus,can-utils}/versions | FIX7 | C-FIX7-004 | no | no archive recorded in the tag file |
| 31 | https://deb.debian.org/debian/dists/trixie/Release | LAB-debian-rugix | C-LAB-debian-rugix-015 | no | no archive recorded in the tag file |
| 32 | https://quay.io/repository/centos-bootc/bootc-image-builder | LAB-fedora-bootc | C-LAB-fedora-bootc-016 | no | content-addressed image digest recorded |
| 33 | https://quay.io/repository/fedora/fedora-bootc | LAB-fedora-bootc | C-LAB-fedora-bootc-001 | no | content-addressed image digest recorded |
| 34 | https://downloads.mender.io/repos/device-components/dists/debian/trixie/stable/Release | LAB-mender | C-LAB-mender-005 | no | APT-signed Release file |
| 35 | https://www.fcc.gov/supplychain/coveredlist | QBANK | C-W15-019 | no | no archive recorded in the tag file |
| 36 | https://github.com/balena-os/balena-jetson-orin/issues/636 | TD-balenaos | C-TD-balenaos-046 | no | GitHub page, not SHA-pinned |
| 37 | https://github.com/balena-os/balena-raspberrypi/issues/1146 | TD-balenaos | C-TD-balenaos-049 | no | GitHub page, not SHA-pinned |
| 38 | https://github.com/balena-os/meta-balena/issues/2301 | TD-balenaos | C-TD-balenaos-047 | no | GitHub page, not SHA-pinned |
| 39 | https://github.com/balena-os/meta-balena/issues/2833 | TD-balenaos | C-TD-balenaos-048 | no | GitHub page, not SHA-pinned |
| 40 | https://get.casaos.io | TD-casaos-zimaos | C-TD-casaos-zimaos-022 | no | no archive recorded in the tag file |
| 41 | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024 | TD-flagged | C-TD-flagged-031 | no | owner judged official legal text stable |
| 42 | https://www.law.cornell.edu/uscode/text/17/1201 | TD-flagged | C-TD-flagged-030 | no | owner judged official legal text stable |
| 43 | https://github.com/home-assistant/supervisor/releases/tag/2026.11.0 | TD-home-assistant-os | C-TD-home-assistant-os-002 | no | not archived |
| 44 | https://www.openhomefoundation.org/structure/ | TD-home-assistant-os | C-TD-home-assistant-os-047; C-W16-012 | no | not archived |
| 45 | https://github.com/Start9Labs/start-technologies/issues/3881 | TD-startos | C-TD-startos-032, 036 | no | GitHub page, not SHA-pinned |
| 46 | https://www.xda-developers.com/hexos-finally-manage-nas-locally-instead-cloud-fixes-flaw/ | TD-tier-c-nas | C-TD-tier-c-nas-023 | no | no archive recorded in the tag file |
| 47 | https://donate.yunohost.org/ | TD-tier-c-selfhost | C-TD-tier-c-selfhost-030 | no | owner marked it "not load-bearing" |
| 48 | https://forum.yunohost.org/t/yunohost-13-0-trixie-spooky-beta/40656 | TD-tier-c-selfhost | C-TD-tier-c-selfhost-029 | no | hash recorded; copy kept outside the repo |
| 49 | https://github.com/getumbrel/umbrel/issues/1955 | TD-umbrelos | C-TD-umbrelos-055 | no | GitHub page, not SHA-pinned |
| 50 | https://github.com/getumbrel/umbrel/issues/2072 | TD-umbrelos | C-TD-umbrelos-050 | no | GitHub page, not SHA-pinned |
| 51 | https://github.com/getumbrel/umbrel/issues/2124 | TD-umbrelos | C-TD-umbrelos-053 | no | GitHub page, not SHA-pinned |
| 52 | https://github.com/getumbrel/umbrel/issues/2190 | TD-umbrelos | C-TD-umbrelos-051 | no | GitHub page, not SHA-pinned |
| 53 | https://github.com/getumbrel/umbrel/issues/2245 | TD-umbrelos | C-TD-umbrelos-052 | no | GitHub page, not SHA-pinned |
| 54 | https://github.com/getumbrel/umbrel/issues/2298 | TD-umbrelos | C-TD-umbrelos-054 | no | GitHub page, not SHA-pinned |
| 55 | https://umbrel.com/umbrel-pro | TD-umbrelos | C-TD-umbrelos-046 | no | not archived |
| 56 | https://github.com/Crosstalk-Solutions/project-nomad | TD-villageos | C-TD-villageos-039 | no | release tag recorded |
| 57 | https://github.com/OpenEMS/openems | TD-villageos | C-TD-villageos-038 | no | release tag recorded |
| 58 | https://github.com/ReGen-Villages/VillageOS-API/pull/111 | TD-villageos | C-TD-villageos-029 | no | PR: merge commit SHA recorded |
| 59 | https://github.com/ReGen-Villages/VillageOS-API/pull/12 | TD-villageos | C-TD-villageos-027 | no | PR: merge commit SHA recorded |
| 60 | https://github.com/ReGen-Villages/VillageOS-API/pull/121 | TD-villageos | C-TD-villageos-028 | no | PR: merge commit SHA recorded |
| 61 | https://github.com/ReGen-Villages/VillageOS-API/pull/140 | TD-villageos | C-TD-villageos-030 | no | PR: merge commit SHA recorded |
| 62 | https://github.com/ReGen-Villages/VillageOS-API/pull/28 | TD-villageos | C-TD-villageos-031 | no | PR: merge commit SHA recorded |
| 63 | https://github.com/farmOS/farmOS | TD-villageos | C-TD-villageos-037 | no | release tag recorded |
| 64 | https://www.home-assistant.io/docs/energy/ | TD-villageos | C-TD-villageos-040 | no | owner marked it "not load-bearing" |
| 65 | https://www.dell.com/support/manuals/en-us/latitude-15-5540-laptop/latitude-5540-owners-manual/system-setup-options?guid… | W10 | C-W10-043 | no | marked ARCHIVE-GAP by the source owner |
| 66 | https://www.raspberrypi.com/for-industry/integrator-programme/ | W10 | C-W10-049 | no | marked ARCHIVE-GAP by the source owner |
| 67 | https://www.raspberrypi.com/products/ai-hat-plus-2/ | W10 | C-W10-036 | no | marked ARCHIVE-GAP by the source owner |
| 68 | https://www.raspberrypi.com/products/compute-module-5/ | W10 | C-W10-035 | no | marked ARCHIVE-GAP by the source owner |
| 69 | https://github.com/basecamp/omarchy/releases | W11 | C-W11-048 | no | API response; values quoted in the claim |
| 70 | https://v2.vuejs.org/eol/ | W11 | C-W11-064 | no | no archive recorded in the tag file |
| 71 | https://www.etsi.org/deliver/etsi_en/301500_301599/301549/03.02.01_60/ | W11 | C-W11-062 | no | no archive recorded in the tag file |
| 72 | https://www.macrumors.com/2025/10/21/samsung-galaxy-xr-headset/ | W11 | C-W11-046 | no | no archive recorded in the tag file |
| 73 | https://www.federalregister.gov/documents/2025/08/22/2025-16139/personal-financial-data-rights-reconsideration | W12 | C-W12-067 | no | API response; values quoted in the claim |
| 74 | https://www.hashicorp.com/en/blog/hashicorp-adopts-business-source-license | W16 | C-W16-007 | no | HTTP 429 |
| 75 | https://www.raspberrypi.com/for-industry/powered-by/ | W16 | C-W16-036 | no | HTTP 403 |
| 76 | https://www.raspberrypi.com/products/compute-module-5/ | W16 | C-W16-035 | no | HTTP 403 |
| 77 | https://www.raspberrypi.com/products/raspberry-pi-5/ | W16 | C-W16-034 | no | HTTP 403 |
| 78 | https://www.westerndigital.com/support/product-security/wdc-21008-recommended-security-measures-wd-mybooklive-wd-mybookl… | W16 | C-W16-051 | no | script-rendered page |
| 79 | https://docs.docker.com/build/building/multi-platform/ | W17 | C-W17-012 | no | not saved (large page) |
| 80 | https://docs.k3s.io/security/hardening-guide | W17 | C-W17-015 | no | not saved (large page) |
| 81 | https://docs.kernel.org/kbuild/index.html | W17 | C-W17-027 | no | not saved |
| 82 | https://docs.nats.io/running-a-nats-service/configuration/securing_nats/auth_intro/jwt | W17 | C-W17-018 | no | not saved |
| 83 | https://docs.sigstore.dev/ | W17 | C-W17-021 | no | not saved |
| 84 | https://link.springer.com/book/10.1007/978-1-4302-6584-9 | W17 | C-W17-022 | no | bot wall / challenge |
| 85 | https://slsa.dev/spec/v1.1/ | W17 | C-W17-020 | no | not saved |
| 86 | https://snapshot.debian.org/ | W17 | C-W17-029 | no | not saved |
| 87 | https://www.freedesktop.org/software/systemd/man/latest/bootup.html | W17 | C-W17-028 | no | not saved |
| 88 | https://www.linuxfromscratch.org/lfs/read.html | W17 | C-W17-005 | no | read through the fetch tool only |
| 89 | https://www.nvidia.com/en-us/training/self-paced-courses/ | W17 | C-W17-026 | no | not saved |
| 90 | https://lists.archlinux.org/archives/list/<email-masked>/thread/7EZTJXLIAQLARQNTMEW2HBWZYE626IFJ/ | W19 | C-W19-027 | no | bot wall (Anubis), not bypassed |
| 91 | https://obsidian.md/help/plugin-security | W19 | C-W19-022 | no | script-rendered page |
| 92 | https://github.com/getumbrel/umbrel/issues/2297 | W3 | C-W3-044 | no | Wayback not looked up |
| 93 | https://github.com/home-assistant/operating-system/issues/{4995,5036,3995,5098} | W3 | C-W3-030…033 | no | Wayback not looked up |
| 94 | https://avweb.com/aviation-news/aviation-law/faa-reopens-part-108-bvlos-comment-period/ | W7 | C-W7-054 | no | read through the fetch tool only |
| 95 | https://control.ros.org/jazzy/doc/ros2_control/controller_manager/doc/userdoc.html | W7 | C-W7-036 | no | not saved |
| 96 | https://docs.auterion.com/vehicle-operation/settings-and-maintenance/skynode-software-update | W7 | C-W7-042 | no | not saved |
| 97 | https://docs.px4.io/main/en/flight_controller/modalai_voxl_2 | W7 | C-W7-041 | no | not saved |
| 98 | https://docs.px4.io/main/en/middleware/uxrce_dds.html | W7 | C-W7-044 | no | not saved |
| 99 | https://docs.viam.com/reference/viam-agent/ | W7 | C-W7-043 | no | not saved |
| 100 | https://kubernetes.io/docs/tasks/administer-cluster/cpu-management-policies/ | W7 | C-W7-035 | no | not saved |
| 101 | https://www.raspberrypi.com/documentation/computers/linux_kernel.html | W7 | C-W7-025 | no | read through the fetch tool only |
| 102 | https://github.com/TAK-Product-Center/Server/tags | W8 | C-W8-062 | no | GitHub page, not SHA-pinned |
| 103 | https://github.com/apache/plc4x/releases | W8 | C-W8-056 | no | GitHub page, not SHA-pinned |
| 104 | https://github.com/autonomy-logic/openplc-runtime/releases | W8 | C-W8-057 | no | GitHub page, not SHA-pinned |
| 105 | https://github.com/home-assistant/core/releases | W8 | C-W8-061 | no | API response; values quoted in the claim |
| 106 | https://github.com/project-akri/akri/releases | W8 | C-W8-058 | no | API response; values quoted in the claim |
| 107 | https://packages.debian.org/trixie/libopen62541-1.4 | W8 | C-W8-004 | no | no archive recorded in the tag file |
| 108 | https://sources.debian.org/api/src/mosquitto/ | W8 | C-W8-005 | no | API response; values quoted in the claim |
| 109 | https://sources.debian.org/api/src/openjdk-17/ | W8 | C-W8-019 | no | API response; values quoted in the claim |
| 110 | https://www.droid-life.com/2025/10/01/t-mobile-lists-satellite-ready-apps-for-data-connectivity/ | W8 | C-W8-052 | no | no archive recorded in the tag file |

**Gap counts by tag:** W17 12, W8 10, W6 9, TD-villageos 9, W7 8, TD-umbrelos 7, W10 5, W2 5, W4 5, W16 5, W18 4, TD-balenaos 4, W11 4, LAB-fedora-bootc 2, TD-flagged 2, TD-home-assistant-os 2, TD-tier-c-selfhost 2, W19 2, W3 2, ARCH5 1, LAB-rauc-1152 1, COST 1, FIX7 1, LAB-debian-rugix 1, LAB-mender 1, QBANK 1, TD-casaos-zimaos 1, TD-startos 1, TD-tier-c-nas 1, W12 1.

## Ledger sources not listed in any tag file

1685 verified or partial claim rows carry a `source_url` that is not an exact URL in any `evidence/sources/*.md` row. Measured breakdown: **994** are a deep link into a repository that is listed (usually at the same pinned commit); **560** are another page on a site that is listed; **118** are a site that no tag file lists; **13** are an anchor variant of a listed page. They are not itemised here because this file is compiled from the tag files, but every one of them is still a row in its claim ledger with its own `source_url`, `commit_or_tag` and `accessed_date`. The **118** on unlisted sites are the ones a ledger pass should list in their tag files first (by tag: W13 17, TD-tier-c-selfhost 8, DEC5 6, LIC4 5, REF-W19-security 5, REF3-DC-security 5, REF4-DC-longevity 5, REF-W19-longevity 5, STEEL-cra-nb 5, REF-W18-robotics 4, REF3-W19-technical 4, REF-W2-robotics 3, REF-W6-technical 3, REF-W8-security 3, STEEL-ubu 3, REF3-DC-longevity 3, STEEL-IIOT 3, STEEL-updates-mender 3, REF-W4-security 2, REF3-DC-cost 2, REF-W19-cost 2, REF4-DC-security 2, REF-W3-longevity 2, REF-W7-T 2, REF-W19-technical 2, STEEL-backup-kopia 1, W6 1, REF-DC-cost 1, REF-W8-longevity 1, STEEL-jb 1, STEEL-updates-rugix 1, REF-W5-longevity 1, REF4-DC-technical 1, STEEL-etcd-every-box 1, REF-W7L 1, REF-DC-robotics 1, REF3-DC-technical 1, REF5-S1-technical 1, REF-DC-longevity 1).

**Ledgers with no tag file.** 593 claim rows sit in 47 ledgers that have no `evidence/sources/<TAG>.md` list, so none of their sources is itemised above; each row still carries its own `source_url`. Most are refuter and steelman ledgers: DEC4 10, DEC5 28, G4U 12, PROTO4 18, REF-DC-cost 10, REF-DC-longevity 13, REF-DC-robotics 13, REF-DC-technical 10, REF-W18-robotics 6, REF-W19-cost 10, REF-W19-security 11, REF-W19-technical 9, REF-W2-robotics 8, REF-W3-longevity 10, REF-W4-security 8, REF-W5-longevity 9, REF-W6-technical 8, REF-W7-longevity 10, REF-W7-technical 9, REF-W8-longevity 9, REF-W8-security 9, REF3-DC-cost 8, REF3-DC-longevity 11, REF3-DC-security 10, REF3-DC-technical 24, REF3-W19-longevity 12, REF3-W19-technical 17, REF4-DC-longevity 22, REF4-DC-security 8, REF4-DC-technical 13, REF4-S1R4-longevity 4, REF4-S1R4-security 8, REF4-S1R4-technical 6, REF5-S1-longevity 14, REF5-S1-security 12, REF5-S1-technical 12, STEEL-backup-kopia 21, STEEL-base-ubuntu 16, STEEL-cra-notified-body 20, STEEL-etcd-every-box 25, STEEL-iiot-runner-up 12, STEEL-jetson-base 22, STEEL-kernel-runner-up 13, STEEL-updates-mender 25, STEEL-updates-rugix 24, SYNC5-a 2, SYNC5-b 2.

## Change log

| Date | Change |
|---|---|
| 2026-11-11 | First compilation (TRACE), closing critic pass-2 gap N15 for `SOURCES.md`. |
| 2026-11-11 | Regenerated (PDF4) after the rev-4 ledger writes (PROTO4, DEC4, CIT4, STEEL4, REF4, LIC4, new LAB tags), closing critic pass-3 gap P3-13. |
| 2026-11-11 | Regenerated (PDF5) from all 116 ledger fragments (2986 rows) after the FIX4, FIX5, FIX7, ARCH5, G4U, DEC5, REF5 and SYNC5 writes, closing critic pass-5 gap P5-5. The ARCH5 saved copies are now picked up by the compiler, so the hand-written ARCH5 note is no longer needed. Added the list of ledgers with no tag file. |
