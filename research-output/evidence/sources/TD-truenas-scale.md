# Sources: TD-truenas-scale (Tier B condensed teardown of TrueNAS SCALE / Community Edition)

All sources opened on 2026-11-11. Claim IDs are in `../claims/TD-truenas-scale.csv` (C-TD-truenas-scale-001 … 040).

## Archiving note

The run cannot submit Wayback save requests, so load-bearing vendor pages use the fallback: **extracted text plus sha256** in [`TD-truenas-scale/`](TD-truenas-scale/) (`SHA256SUMS` there). Before hashing, email-shaped strings in the page footers were replaced with `<email-masked>`, so each hash is of the masked text. **Forum pages are not stored in the repo** because they carry user handles and, in one case, a user's private IP and hostname. Their texts sit in the run's lab folder (`.lab/truenas-web/`), and only their hashes are recorded here. Existing Wayback captures are listed where the availability API returned one. Code needs no archive: every code citation is a permalink pinned to a commit SHA.

## Code (pinned)

| # | Repository and pin | What was read | Claims |
|---|---|---|---|
| K1 | `truenas/scale-build` @ `453acc8fddacf20c82a509a0177730e9479d49af` (tag `TS-25.10.8`, commit 2026-10-23) | `conf/build.manifest`, `scale_build/image/update.py`, `scale_build/image/iso.py`, `scale_build/extensions.py`, `truenas_install/__main__.py`, `truenas_install/fhs.py`, `LICENSE` | 003, 005, 007, 009, 010, 012, 013, 025, 028, 033, 039 |
| K2 | `truenas/scale-build` @ `2b2b629f7726daeb2dc5b618ecdd8e1014723a45` (master, 2026-03-10) | `README.md` deprecation notice | 026 |
| K3 | `truenas/scale-build` @ `cf7ca229b2f00b85b421af98c9ec6f05f56e1209` (branch `26.0.0`, 2026-02-23) | `conf/build.manifest` lines 1–3 | 004 |
| K4 | `truenas/middleware` @ `29ed02b8082f38494b0d2896bada8151f0d59716` (tag `TS-25.10.8`, 2026-10-26) | `plugins/update_/*`, `plugins/boot_/environments.py`, `plugins/apps/*`, `plugins/cloud_backup/sync.py`, `plugins/config.py`, `role.py`, `src/freenas/etc/grub.d/10_truenas_linux`, `src/freenas/usr/local/bin/pkg_mgmt_disabled`, `LICENSE` | 008, 011, 012, 021–023, 025, 028–030 |
| K5 | `truenas/middleware` @ `46406b62c28ceab2536dfa0659efeeb350d12b0a` (tag `TS-24.10.0`, 2024-10-25) | `plugins/kubernetes_to_docker/list_utils.py`, `migrate.py` | 018 |
| K6 | `truenas/apps` @ `c85431d5f6ad13eb234bb67a1fc5dc908e05d112` (master, 2026-11-10) | `catalog.json`, `ix-dev/community/actual-budget/*`, `ix-dev/community/ollama/*`, `trains/`, `LICENSE` | 020, 024, 025, 035 |
| K7 | `truenas/truenas-mcp` @ `f0a7a64701fe78e46e938dce90d0337ff857990b` (main) | `README.md` | 034 |
| K8 | GitHub REST API: tags and branches of `truenas/middleware` and `truenas/scale-build`; commit authors of `truenas/middleware` since 2025-11-10; `repos/truenas/truenas-mcp`; code search `MANIFEST.sig org:truenas` | PRIMARY-METADATA, point in time | 008, 025–027, 034 |

## Web (vendor, PRIMARY)

| # | Source | Saved text sha256 (masked) | Wayback | Claims |
|---|---|---|---|---|
| W1 | https://www.truenas.com/software-status/ (last modified 2026-04-13; table live on 2026-11-11) | `e73565277b11924d4b10c704481d120fb3b0199b2c2a9c79f269f7acbf32624b` | 20251119171200 (older than the content used) | 001, 040 |
| W2 | https://www.truenas.com/docs/scale/27/gettingstarted/versionnotes/ | `61dc2afcbd24465e12466dedbe17e20f4ccad1b26cdf764e47e262728ce897f6` | http://web.archive.org/web/20261029160152/https://www.truenas.com/docs/scale/27/gettingstarted/versionnotes/ | 002, 006, 016, 039 |
| W3 | https://www.truenas.com/docs/scale/26/gettingstarted/versionnotes/ (last modified 2026-10-06) | `740763e54cda011964864167efa8c5fd802589691cca876f1d53d75d2c3a72fc` | none checked | 030, 031 |
| W4 | https://www.truenas.com/docs/scale/25.10/gettingstarted/versionnotes/ | `1cdfd11c585bb48b21392464ed5560856cba51f3edc0cf7497283a81ae1d7b68` | http://web.archive.org/web/20261101222433/https://www.truenas.com/docs/scale/25.10/gettingstarted/versionnotes/ | 006, 014, 033, 038 |
| W5 | https://www.truenas.com/blog/smarter-and-streamlined-updates-with-truenas-25-10 | `3b7341a236a110574ea200481461102d7a4b5d6edb9c5ce9f36fa8c4437d82cb` | none checked | 011, 038 |
| W6 | https://www.truenas.com/docs/scale/25.10/gettingstarted/scalehardwareguide/ (last modified 2025-08-22) | `6eb7e3b3719c0cd92703ff7f27e978d6508fc063c5e5d1305bcccc2bb27fe384` | none checked | 015 |
| W7 | https://www.truenas.com/docs/scale/25.10/scaletutorials/systemsettings/updatescale/ (last modified 2025-08-29) | `3e952706c0a71e988dd200c30bddeed73f211432cf52ddb77c68bc3f13f6f82f` | none checked | 029 |
| W8 | https://www.truenas.com/docs/scale/25.10/scaletutorials/dataprotection/truecloudtasks/ | `d9f65ed702693e07146a361e7f7075ff69900528f7ab6f02590f5845486a849e` | none checked | 028 |
| W9 | https://www.truenas.com/docs/scale/27/systemsettings/advanced/advancedsettings/ (last modified 2026-10-06) | `09f81d90090caaea6e69c69967289efcc79e90f5a746dca531595af65eee2b90` | none checked | 032 |
| W10 | https://www.truenas.com/docs/solutions/optimizations/stigcompliance/ (last modified 2026-10-06) | `35024a063c2bc310393cb1b6f3c76392c59b4cc2e92b219e6f4c6449ad531d56` | none checked | 032 |
| W11 | https://www.truenas.com/blog/building-a-bridge-between-community-enterprise (2026-03-12) | `7993c9168734e94d66d7f6a04155d931de0e02984cc3ac5db073f54d2d17f7eb` | http://web.archive.org/web/20260918184834/https://www.truenas.com/blog/building-a-bridge-between-community-enterprise/ | 036 |
| W12 | https://connect.truenas.com/pricing/ (last modified 2026-02-17) | `900a597f34d2b41cff1efa595874cbb35e76f16e88b60905b3ac2faad5bf19b6` | http://web.archive.org/web/20261108191831/https://connect.truenas.com/pricing/ | 037 |
| W13 | https://www.truenas.com/blog/truenas-plans-for-2026 (2026-02-04) | `74b5e42acb13a654996d6d0e7e0d855fd655b37eade4bffa9007173f32b48e08` | none checked | background (annual cadence, 6.18 LTS) |
| W14 | https://www.truenas.com/blog/blog-truenas-26-beta1-release/ (2026-04-07) | `d24105b575ac2fa53e7650363b70c5ed810298dce21179a5f5c7e97d9f1ec325` | none checked | background (26 Beta 1 date) |
| W15 | https://www.truenas.com/docs/scale/25.10/scaleuireference/apps/ | `3442d4e5ce314cd23d67eb402f72dd4e2d371aa49fba59c55cdb90640bbb0652` | none checked | background (app trains in UI) |

## Forums (texts kept outside the repo; hashes only)

| # | Source | Type | sha256 of saved text | Claims |
|---|---|---|---|---|
| F1 | https://forums.truenas.com/t/the-future-of-electric-eel-and-apps/5409 (iX announcement, 2024-05-29) | PRIMARY (vendor statement) | `c904e5467fa86260363b5fb895444f2ea90df692bfa2288d63912e35d57fabda` | 017 |
| F2 | https://forums.truenas.com/t/k3s-server-uses-10-cpu-for-no-reason/6034 (2024-06-06 to 07-23) | SECONDARY | `d21291a2d27379354a5452700e801bb755afbc7b6cf1f05cbe1e7b498ec4d18b` | 019 |
| F3 | https://forums.truenas.com/t/potential-k3s-database-corruption-issue-need-assistance/9038 (2024-07) | SECONDARY | `66f647af90e36aeafd9b1dacb47ba0237f76b1b3564ede75013f0117ab277828` | reuses C-W5-052 |
| F4 | https://forums.truenas.com/t/truenas-labs-mcp-server/63816 (2026-02-20) | PRIMARY (vendor statement) | `e4d92bdfbd245eb50c68065befc9d452a2418e7544a31c06a1ab4b9f9d02369e` (a user's private IP and hostname masked) | 034 |
| F5 | https://forums.truenas.com/t/secureboot-is-necessary-for-truenas-attention-all-users/13691 | SECONDARY | `8e4ab9152ee8b322a723eab2969aca48f0bb6b7760f9878cbeaf4031215f66e1` | 033 |

## Claims reused from other workstreams (not re-ledgered)

- **C-DEC-007:** 24.10.0 (2024-10-29) moves the apps backend from Kubernetes to Docker.
- **C-W18-033:** TrueNAS CORE (FreeBSD) in sustaining engineering; new work goes to the Linux edition.
- **C-W5-052:** k3s SQLite "database disk image is malformed" report on SCALE.

## Searches run (2026-11-11)

- "TrueNAS 26 release date version numbering annual release 2026 Halfmoon trixie" (extended)
- "TrueNAS 25.10 Goldeye release notes features TrueNAS Connect NVMe-oF Secure Boot"
- "TrueNAS MCP server AI official iXsystems 2026" (extended)
- "TrueNAS Connect pricing tiers Foundation Plus Business 2026"
- "TrueNAS STIG FIPS mode Secure Boot support docs 25.10"
- "truenas.com blog Electric Eel why move apps from Kubernetes k3s to Docker resource overhead"

Search-result summaries were used only to find pages. Every claim cites a page or code that was opened.
