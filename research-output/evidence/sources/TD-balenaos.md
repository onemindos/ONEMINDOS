# Sources: TD-balenaos (balenaOS Tier B teardown)

**Accessed:** 2026-11-11 unless noted · **Claims:** `evidence/claims/TD-balenaos.csv` (C-TD-balenaos-001…060) · **Saved copies:** `evidence/sources/TD-balenaos/` with `SHA256SUMS`. Wayback save requests are denied in this environment; the docs are pinned to a git commit instead, which is a stronger archive than a page snapshot.

## Code (shallow clones in `<lab-dir>/src/`, pinned)

| Repo | Commit | Tag / date | Type | Used for |
|---|---|---|---|---|
| github.com/balena-os/meta-balena | `48184b689a43b762c5eea6efbc16b018eed70839` | v9.0.6 · 2026-11-09 | PRIMARY (code, Apache-2.0) | image build, partitions, update client, hooks, rollback, signing |
| github.com/balena-os/balena-supervisor | `321c7d3718ba6c79504e8d027f23779feac22a76` | v20.0.7 · 2026-11-09 | PRIMARY (code, Apache-2.0) | app format, update strategies, feature labels, contracts, provisioning, update locks |
| github.com/balena-os/balena-jetson-orin | `862a3522f4292c6bf8a00432b5087038fae00083` | v9.0.5+rev1 · 2026-11-08 | PRIMARY (code) | Jetson BSP base, UEFI patch, capsule, board health check |
| github.com/balena-os/balena-raspberrypi | `64e81417cba33495afe68e923638ef9e0812e741` | v9.0.3+rev2 · 2026-11-10 | PRIMARY (code) | Pi 5 bootloader and image sizing |
| github.com/balena-os/balena-engine | `68537442895ea82de68f6f7a49ce8cd2458430cc` | 2026-10-01 | PRIMARY (licence) | licence |
| github.com/balena-io/open-balena | `7b2247d5ddb5965e1e91cc5538124c94ad13592a` | v4.1.996 · 2026-11-05 | PRIMARY (licence, README) | self-hosted server licence and limits |
| github.com/balena-io/docs | `6b962939c0d6cca9ee3c6cf2fb398cc9a320ae0b` | 2026-11-11 | PRIMARY (official docs source) | ESR, update process, Secure Boot/FDE, app format, offline/delta updates |
| github.com/balena-io-experimental/balenamcp | `e3cce179c5031f003240a83779319bf3a32f5696` | archived | PRIMARY-METADATA (GitHub API) | AI/MCP status |
| github.com/balena-os/balena-yocto-scripts | `436cae1eb39b15b2c74bac1450162eba0855eb0d` | v1.42.17 | PRIMARY (code, read only) | build entry points (`barys`, `balena-build.sh`) |

## Issue trackers (failure reports)

| URL | Opened | Claim |
|---|---|---|
| https://github.com/balena-os/balena-jetson-orin/issues/636 | 2026 | C-TD-balenaos-046 |
| https://github.com/balena-os/meta-balena/issues/2301 | 2021-08-26 | C-TD-balenaos-047 |
| https://github.com/balena-os/meta-balena/issues/2833 | 2022-10-27 | C-TD-balenaos-048 |
| https://github.com/balena-os/balena-raspberrypi/issues/1146 | 2024-07-02 | C-TD-balenaos-049 |

## Web pages (saved text + sha256 in `TD-balenaos/`)

| URL | Saved as | Type | Claims |
|---|---|---|---|
| https://www.balena.io/pricing (accessed 2026-11-10) | `W16/balena-pricing.txt` (saved by W16; sha256 `635f3390…b674`) | PRIMARY | 052 |
| https://www.prnewswire.com/news-releases/balena-raises-14-4m-to-expand-team-and-bring-edge-computing-to-every-developer-300890087.html | `prnewswire-2019-series-b.txt` | PRIMARY (company press release) | 054 |
| https://blog.balena.io/balena-docs-platform-migration-to-gitbook/ | `blog-gitbook-mcp.txt` | PRIMARY | 056 |
| Ten docs pages from `balena-io/docs@6b96293` | `docs-*.md` (each starts with its pinned URL) | PRIMARY | 015, 021, 022, 027–030, 036–040, 053, 058–060 |

Emails in saved pages are masked as `<email-masked>`; one example command value in `docs-learn_deploy_offline-updates.md` line 79 is masked as `<masked>` (gitleaks false positive).

## Opened but not cited

- Third-party aggregators (Dealroom, CB Insights, Crunchbase) on headcount and total funding: not opened as primary; a search-result title on one of them contained an instruction aimed at language models, which was ignored. Headcount after 2019 is therefore **UNVERIFIED** and not used.
- Community MCP servers `kieksme/mcp-balena` (GPL-3.0, `b171b8c`) and `schubydoo/balenamcp` (MIT, `4cd698f`): repo metadata only, used only to say "community servers exist".
