# Sources: QBANK (question-bank compiler)

**Date:** 2026-11-11 · **Used in:** [`../../24-QUESTION-BANK-ANSWERS.md`](../../24-QUESTION-BANK-ANSWERS.md) · **Claims:** [`../claims/QBANK.csv`](../claims/QBANK.csv)

Saved texts are in `QBANK/`, converted from HTML or PDF to plain text, with e-mail addresses and anything resembling a credential or private IP masked before hashing. Hashes are listed in `QBANK/SHA256SUMS`. Wayback save requests are not available in this environment (ARCHIVE-GAP for every row); the saved text and its sha256 are the archive.

| # | Source | URL | Type | Accessed | Pin / version | Saved copy (sha256 prefix) | Claims |
|---|---|---|---|---|---|---|---|
| 1 | FAR 52.204-25, Prohibition on contracting for certain telecommunications and video surveillance services or equipment (Nov 2021) | https://www.acquisition.gov/far/52.204-25 | PRIMARY (regulation) | 2026-11-11 | clause dated Nov 2021 | `far-52-204-25.txt` (45b42216) | C-QBANK-001 |
| 2 | FAR 25.003, Definitions (designated country, WTO GPA, FTA countries) | https://www.acquisition.gov/far/25.003 | PRIMARY (regulation) | 2026-11-11 | FAC 2026-01, effective 2026-03-13 | `far-25-003.txt` (a69517d1) | C-QBANK-002 |
| 3 | 14 CFR Part 89, Remote identification of unmanned aircraft (eCFR versioner API) | https://www.ecfr.gov/api/versioner/v1/full/2026-11-09/title-14.xml?part=89 | PRIMARY (regulation) | 2026-11-11 | eCFR point in time 2026-11-09 | `ecfr-14-89.txt` (20bb81d8) | C-QBANK-003 |
| 4 | 47 CFR 15.212, Modular transmitters (eCFR versioner API) | https://www.ecfr.gov/api/versioner/v1/full/2026-11-09/title-47.xml?section=15.212 | PRIMARY (regulation) | 2026-11-11 | eCFR point in time 2026-11-09 | `ecfr-47-15-212.txt` (ca8432ae) | C-QBANK-004 |
| 5 | EDPB Guidelines 3/2019 on processing of personal data through video devices, version 2.0 (PDF) | https://www.edpb.europa.eu/system/files/documents/files/file1/edpb_guidelines_201903_video_devices_en_0.pdf | PRIMARY (EU regulator guidance) | 2026-11-11 | v2.0, adopted 2020-01-29 | `edpb-3-2019.txt` (cbff90e2) | C-QBANK-005, C-QBANK-006 |
| 6 | labgrid documentation, Overview | https://labgrid.readthedocs.io/en/latest/overview.html | PRIMARY (project docs) | 2026-11-11 | repo HEAD b1b5b8e2335b4362f59cdd95f939bf95824979f1 | `labgrid.txt` (165a58e3) | C-QBANK-007 |
| 7 | METR, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity" (blog) | https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ | PRIMARY (study authors) | 2026-11-11 | published 2025-07-10 | `metr-2025.txt` (3a010720) | C-QBANK-008 |
| 8 | Chaos Mesh docs, Simulate Pod faults | https://chaos-mesh.org/docs/simulate-pod-chaos-on-kubernetes/ | PRIMARY (project docs) | 2026-11-11 | repo HEAD 8e5a702ee41f538109183b01b1b6b65f73772d11 | `chaos-mesh.txt` (6bb73326) | C-QBANK-009 |
| 9 | DigitalOcean docs, Custom Images Limits | https://docs.digitalocean.com/products/custom-images/details/limits/ | PRIMARY (vendor docs) | 2026-11-11 | page "last verified 13 Jul 2026" | `do-custom-images.txt` (0f5bd8b8) | C-QBANK-010 |
| 10 | Spamhaus, Policy Blocklist (PBL) | https://www.spamhaus.org/blocklists/policy-blocklist/ | PRIMARY (list operator) | 2026-11-11 | web page | `spamhaus-pbl.txt` (657c7047) | C-QBANK-011 |
| 11 | system76/firmware-open (README and submodule pins) | https://github.com/system76/firmware-open | PRIMARY (code) | 2026-11-11 | 0cf80d89edecd6cdeeddc408a84740b5ce60740c | `system76-firmware-open.txt` (621c5704) | C-QBANK-012 |
| 12 | Open Invention Network, "Joining OIN" and "Linux System" pages | https://openinventionnetwork.com/joining-oin/ | UNVERIFIED (blocked) | 2026-11-11 | not opened: bot wall to curl, HTTP 403 to the fetch tool; not circumvented | none | C-QBANK-013 |

## Sources tried and not readable (not cited as fact)

| Source | Result | Effect |
|---|---|---|
| https://www.fcc.gov/supplychain/coveredlist | "Access Denied" to automated fetch | The Covered List drone entry rests on the existing SECONDARY claim C-W15-019 |
| https://www.diu.mil/blue-uas | Page renders only with JavaScript; no list content in the HTML | Blue UAS status is UNVERIFIED in Q27 and Q182 |
| EUR-Lex (Product Liability Directive 2024/2853) | Not retried: EUR-Lex returned empty pages to automated fetches earlier in this run [C-STEEL-cra-nb-018] | Q194 marks the PLD and AI Act text as not opened |

## Re-used claims (opened by other agents, cited in 24-…)

The compiled answers cite 650+ existing claim IDs from `evidence/claims/*.csv`. A compile-time script resolved every cited ID (including `…` ranges) against those ledgers: 0 unresolved.
