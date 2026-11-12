# Sources: TD-tier-c-nas (Tier C teardowns of Unraid, HexOS and Synology DSM)

All sources were opened on 2026-11-11. Claim IDs are in `../claims/TD-tier-c-nas.csv` (C-TD-tier-c-nas-001 … 042). Reused claims: C-W16-029 (Unraid pricing), C-W11-057 (Synology High Availability), C-W18-001 (kernel.org longterm list), and C-TD-truenas-scale-* (the TrueNAS base that HexOS runs on).

## Archiving note

The run cannot submit Wayback save requests. Vendor pages are stored as **extracted text plus sha256** in [`TD-tier-c-nas/`](TD-tier-c-nas/) (see `SHA256SUMS`). Before hashing, email-shaped strings, private IP addresses and token-shaped strings were masked, so each hash covers the masked text. The full 381 KB Synology GPL index is kept in the run's lab folder (`<lab-dir>/tier-c-nas/raw/syn-gpl74.txt`, sha256 `2129c1ebc1aa0e7e412389bc362ad97f3732a2dab1ec3ed77c3477167896420f`). Only a derived kernel table is stored in the repo. Code and docs in Git need no archive, because every citation is pinned to a commit SHA.

## Code and docs (pinned)

| # | Repository and pin | What was read | Claims |
|---|---|---|---|
| K1 | `unraid/docs` @ `297a271f7eb4db65b1b619f12d5f0f4d19195f85` (2026-11-10) | `docs/unraid-os/release-notes/7.2.0.md`, `7.2.5.md`, `7.3.0.md`, `7.3.5.md`, `7.4.0.md`; `getting-started/what-is-unraid.mdx`; `getting-started/set-up-unraid/create-your-bootable-media.mdx`; `updating-unraid/index.mdx` + partials; `troubleshooting/licensing-faq.mdx`; `using-unraid-to/customize-your-experience/plugins.mdx`; `community-applications.mdx`; `API/index.mdx` | 001–003, 007, 009–011, 013, 015–017 |
| K2 | `unraid/webgui` @ `b135287c706a30da44f71cc7820615209e83e9a0` (2026-11-04) | `emhttp/plugins/unRAIDServer/unRAIDServer.plg` (OS updater), `etc/rc.d/rc.libvirt`, `ungrub/mkbootable`, `emhttp/plugins/dynamix/LICENSE` | 004–008, 012, 017 |
| K3 | `unraid/api` @ `8e587fe2f8ee6f1c2886401c4b7ae64544819753` (2026-11-04) | `LICENSE.txt`; a grep for MCP found no MCP code | 011, 014 |
| K4 | GitHub search API, `repo:unraid/api MCP` (issues #2024, #2065) | PRIMARY-METADATA, point in time | 014 |
| K5 | `eshtek/hexos-docs` @ `af3e217c9677444128914d933bc9c56967a37d7a` (2026-11-10) | `getting-started/installation/InstallGuide.md`, `troubleshooting/local-access.md`, `release-notes/command-deck.md` and `command-deck/2026-11-06.md`, `2026-11-10.md`, `features/apps/install-scripts.md`, `…/reference/schema.md`, `…/reference/hooks.md`, `about-hexos.md` | 018, 019, 021, 022, 025–028 |
| K6 | `eshtek/hexos-app-catalog` @ `fb2daaa668a158dedda92eee51e64a2d1cb16ba4` (2026-11-08); GitHub REST API `orgs/eshtek/repos` | README, licence field (none) | 025, 030 |

## Web (vendor, PRIMARY)

| # | Source | Saved text (masked) sha256 | Claims |
|---|---|---|---|
| W1 | https://hexos.com/ | `d70cce8f541a9667aa55ace96e0ccd08391e4b5a9cfe3e00d772e548d5e74575` | 029 |
| W2 | https://hexos.com/faq | `bf406d6b071e95a461abf04476e7d5ca25e6ecfd9b6041d57ccc3be0b67b7ca6` | 020, 024 |
| W3 | https://hexos.com/hardware | `f0db6094b244ad01df9442748f787924c708cdd3c29a9a28d72c0a0b94b34cae` | 024 |
| W4 | https://docs.hexos.com/getting-started/installation/InstallGuide | `b013cd930b29af852c016f977614488e8969aec28d3b392da5c41db1f96f497f` | 018, 019 |
| W5 | https://docs.hexos.com/release-notes/command-deck (index) | `1af5eb49685f9d83cf3ff96672b1f3abb0a4aff64c5275095b7ca86bd5f9b43d` | 022 |
| W6 | https://docs.hexos.com/release-notes/command-deck/2026-04-21 | `db6c308e0312f5903890f653b3e21b15ddcbb977a490cf91f477c9de80b1143e` | 020 |
| W7 | https://docs.hexos.com/release-notes/command-deck/2026-11-06 | `2dacb89a8f635af90111480cbaafa45ca7f64e2e1f1f8f9d9af1c61fee8a83ff` | 027, 028 |
| W8 | https://docs.hexos.com/release-notes/command-deck/2026-11-10 | `8e2eddc0823325155b196256b9ff2a8f27b16725ba13dc15ad1fa1fa8debb5fb` | 026 |
| W9 | https://www.synology.com/en-global/releaseNote/DSM (JSON behind it, model DS925+, all versions) | `4449b1edb81ded25b26b0660c5d2c56f843730db3a6e54a91f23b33059d85b4b` | 031–034, 042 |
| W10 | https://archive.synology.com/download/ToolChain/Synology%20NAS%20GPL%20Source/7.4-90080 (derived kernel table) | `a46f61c79080875c4188a34207ad78251e9ba2fe4dcab0d620e85a2b0984387f` | 035 |
| W11 | https://help.synology.com/developer-guide/breaking_changes.html | `8cb9a461130737a4ad97643336e3b88b0c01fd111820c7ce20b527080155ee3b` | 036 |
| W12 | https://help.synology.com/developer-guide/toolkit/sign_package.html | `4a1b264469b0b631ddb9814521f4600e3f97dca7b1fbf10535c1767034e1d809` | 036 |
| W13 | https://help.synology.com/developer-guide/privilege/preface.html | `5c9d8e1800f71e1ae02ff9cf0341ac188cbe63aced7f73ad669af8d446f1f6ec` | 036 |
| W14 | https://www.synology.com/en-global/dsm/7.4/software_spec/ai_console | `5dd3db1674143eca2d80942ac250e7ea9d39a2c3f99869f4b03759a78924a69e` | 037 |
| W15 | https://www.synology.com/en-global/company/news/article/dsm73 (press release, 2025-10-08) | `2671017ec0ac70cf2dacad9b0678c67fd257748d697ba62b07b4e0ac9137d43c` | 038 |
| W16 | https://www.synology.com/en-us/DSM74 | `6d52f18c27bc2d4fd04419db2db8e81a8d9f3858f76e7161a0909e5ad92e4f7a` | 039 |
| W17 | https://www.synology.com/en-us/DSM73 | `9aeb2d7cb728bbf4c431644803415fd8cdaf18275c68211c2c526fbecfc6be34` | 039 |
| W18 | https://www.synology.com/releaseNote/ContainerManager (JSON behind it) | `4e55a6ae2d99b9c7537027cbfb6c3b04aed01e91fff5d6babf5498ab4d9b4a46` | 040 |
| W19 | https://www.synology.com/en-global/products/status/eol-dsm62 | `5730f54c63533001b794aedfc7285f92e2fcc616b343af0f2ab2d1344d2e71ed` | 041 |
| W20 | https://www.synology.com/en-global/products/status | `1ce94237c839ba639e4d7c163836498520e5f35209f6ca6aaa4058288e8a81a0` | 041 |
| W21 | https://unraid.net/pricing (re-saved; the same page as W16/unraid-pricing.txt) | `a3f2bcd990ee0d3bc59f3483de500f921bbc8e878bdb53d745eb55f4aa1934c1` | reuses C-W16-029 |

## Secondary

| # | Source | Type | Claims |
|---|---|---|---|
| S1 | https://www.xda-developers.com/hexos-finally-manage-nas-locally-instead-cloud-fixes-flaw/ (2026-06-10) | SECONDARY (trade press) | 023 |

## Opened but not used, or blocked

- https://hexos.com/pricing: rendered by JavaScript; no price text could be read, so the price stays SECONDARY (C-TD-tier-c-nas-023).
- https://nascompares.com/news/is-hexos-in-trouble-mid-2026-update/: HTTP 403 (not bypassed). Its "25,000 licences" figure appears only in a search snippet, so it is **not used**.
- Synology Knowledge Center pages (Container Manager help, system partition, downgrade, CPU list): rendered by JavaScript and returned empty. The DSM system-partition layout is therefore **not claimed**.
- https://www.synology.com/en-global/dsm/feature/dsm_agent redirected to the home page. DSM Agent is cited from the DSM 7.4 page instead.
- Synology's software life-cycle policy page: 404. Phase lengths are not claimed. Only the DSM 6.2 notice and the status definitions are used.
- Community Unraid MCP servers (glama.ai, PyPI listings): seen in search results only and not opened, so they are not cited beyond the general statement in C-TD-tier-c-nas-014.
