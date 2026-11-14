<!-- SPDX-License-Identifier: Apache-2.0 -->
# Market candidates from competitor app stores

This is the ranked list of upstream projects that OneMind could package for the Market. It was built on 2026-11-12 from seven competitor app stores. The full list is in [`candidates.csv`](candidates.csv): 1199 upstream projects, one row each. It proposes candidates only. An app joins the queue when a PR adds it to [`queue.yaml`](queue.yaml), and the scaffolder and gate then check it (`sdk/contracts/poc-v0.md` §9).

## Legal rule

From each competitor store we took **facts only**: the app name, its upstream source repository URL, its category, its declared CPU architectures and which stores list it. We copied no manifests, compose files, descriptions, screenshots or icons. The repo keeps no file from any store. Descriptions were read only to help assign a category and are not stored. The scaffolder builds every OneMind manifest from the upstream project itself.

## Sources (pinned)

| Letter | Store | Repository @ commit | Store licence | Entries read |
|---|---|---|---|---|
| `u` | umbrel | `getumbrel/umbrel-apps@3a087384be96` | none (no licence file; L4 study only) | 399 |
| `o` | olares | `beclab/apps@37a1fb4f44b2` | Apache-2.0 | 396 |
| `c` | casaos | `IceWhaleTech/CasaOS-AppStore@07178f6d2c27` | Apache-2.0 | 183 |
| `r` | runtipi | `runtipi/runtipi-appstore@2d6b144a1cf6` | GPL-3.0 | 267 |
| `y` | yunohost | `YunoHost/apps@224637ea0f17` | GPL-3.0 | 703 |
| `x` | cosmos | `azukaar/cosmos-servapps-official@26c6e1c3aa05` | AGPL-3.0 | 151 |
| `k` | coolify | `coollabsio/coolify@37aaf6074c30` | Apache-2.0 | 384 |

Notes on the sources:

- Umbrel and Olares were read from the existing W12 facts extract `research-output/evidence/sources/W12/catalog-umbrel-3a087384-olares-37a1fb4f.csv`. The umbrel-apps repo has no licence (L4, study only).
- YunoHost: `apps.toml` at the pinned commit lists each package repo (`*_ynh`), not the upstream code repo. The upstream `code` URL and the architectures were read from the catalog that YunoHost builds from that file (`https://app.yunohost.org/default/v3/apps.json`, fetched 2026-11-12).
- Cosmos: the official servapps market (`azukaar/cosmos-servapps-official`); the `repository` field of each `description.json`.
- Coolify: the service templates in `coollabsio/coolify` (`templates/compose/`). Only the header `documentation` URL, the category and `ghcr.io` image paths were read. Coolify has no repo field, so most of its entries were matched by name to an upstream found in another store.
- Upstream facts (SPDX licence, stars, archived flag, last push, latest release/tag) come from the authenticated GitHub GraphQL API on 2026-11-12. The responses are cached outside the repo.

## Method

1. **Normalise.** Each store entry was resolved to a GitHub `owner/repo` in four passes:
   1. the store's own repo or source field;
   2. otherwise, a unique app-name match to an upstream another store resolved;
   3. otherwise, a secondary URL in the store data (a `ghcr.io/owner/repo` image, or a website or support link on GitHub).
   4. Repos that only package an app (`linuxserver/docker-*`, `YunoHost-Apps/*_ynh`, `bitnami/containers`) do not count as upstreams. GitHub redirects for renamed repos were followed, and duplicates were merged on the canonical `owner/repo`.
2. **Facts.** GitHub returns the SPDX licence, stars, archived flag, push date and latest release. When GitHub reported `NOASSERTION` or no licence, the licence file was fetched and matched against known licence texts; those rows are labelled "(licence-file text match)". Where `research-output/evidence/license-matrix.csv` has a hand-read licence for a repo, it wins.
3. **Licence class.**
   - **L1 permissive**: MIT, Apache, BSD, ISC, Unlicense, Zlib, PostgreSQL and similar. Open-core repos whose core is MIT or Apache (Activepieces, authentik, LiteLLM, OpenCTI) are L1 with the EE directories excluded, as in 13 §3.3.
   - **L2 copyleft**: AGPL, GPL, LGPL, MPL, EUPL, EPL. This follows the task brief, which puts MPL under L2; 13 §4 puts MPL under L1. Both classes can be queued, so the difference does not change any tier.
   - **L3 source-available**: BUSL, SSPL, Elastic, FSL, Sustainable Use, Commons Clause, PolyForm, non-commercial terms (including CC-BY-NC assets), Open WebUI branding, AFFiNE backend.
   - **L4**: no licence, archived, or no release in 18 months. Repos that never publish releases or tags are dated by their last push and flagged.
   - **`L?`**: GitHub could not identify the licence, or the file adds terms (branding, an `ee/` directory, enterprise terms). These need a human read and are list-only until then.
4. **Category.** Each project gets one OneMind category (13 §3.1, plus `Social & Communication`, `Games`, `Desktop & VMs`, `Other` and `Bitcoin & Crypto`). The category comes from a vote of the stores' categories, then from keywords in the name, topics and description. The seed list in 13 §3.3 overrides it.
5. **Score** = number of stores listing the app (0 to 7) + log10(stars + 1) + recency + category weight − licence penalty.
   - Recency of the latest release, tag or push: 1.0 within 90 days, 0.75 within 180, 0.5 within 365, 0.25 within 548.
   - Category weight: +2 for the founder's core self-hosting areas (files and photos, passwords and network, notes and docs, home and IoT, monitoring, AI, developer, media, family, finance, automation). +1 for health, education, social, field and mesh, and media download automation (torrent, usenet and `*arr` tools; ranked lower because they carry review risk on a sold box). 0 for everything else.
   - Licence penalty: L1 and L2 0, `L?` 1, L3 2, L4 3.
6. **Tier.**
   - `excluded`: L4.
   - `parked`: Bitcoin, crypto and node apps, a separate category per 13 §3.1.
   - `list-only`: L3, `L?`, and apps that run a proprietary OS image.
   - `queue`: everything else.
7. **arm64** (`arm64_store`): `yes` when any store declares arm64, `no` when stores declare architectures without arm64, `unknown` otherwise. This is unverified until the gate checks the image manifest in the registry.

Weak signals, stated plainly: stars and store counts measure popularity, not quality or install base. The categoriser is keyword based, so some categories will be wrong; a wrong category moves a score by at most 2. Licence-file text matches are a first pass, not a legal reading.

## Counts per stage

| Store | Entries | Store repo field | Name match | Secondary URL | Non-GitHub upstream | Packaging repo only | Unresolved |
|---|---|---|---|---|---|---|---|
| umbrel | 399 | 378 | 1 | 0 | 9 | 3 | 8 |
| olares | 396 | 287 | 16 | 0 | 4 | 0 | 89 |
| casaos | 183 | 168 | 5 | 1 | 1 | 5 | 3 |
| runtipi | 267 | 250 | 6 | 0 | 5 | 3 | 3 |
| yunohost | 703 | 568 | 5 | 0 | 89 | 5 | 36 |
| cosmos | 151 | 130 | 13 | 0 | 1 | 5 | 2 |
| coolify | 384 | 75 | 134 | 29 | 9 | 2 | 135 |
| **total** | 2483 | 1856 | 180 | 30 | 118 | 23 | 276 |

- Store entries resolved to a GitHub URL: 2066, which give **1244 distinct GitHub URLs**.
- 22 of those URLs could not be fetched: GitHub returned "not found" (deleted repos, or `ghcr.io` image paths that are not repos). The rest merge, through redirects, into **1199 canonical upstream projects**, the rows of the CSV.
- 101 distinct upstreams are hosted outside GitHub (Codeberg, GitLab and others). They are not scored, because their facts cannot be fetched with `gh`. Notable ones: Forgejo (`codeberg.org/forgejo/forgejo`), Readeck and GitLab. Score them by hand if they are wanted.
- Unresolved entries are mostly Olares model packages (Ollama, vLLM or llama.cpp wrappers around one model) and Coolify templates whose documentation URL is not on GitHub.

| Tier | Upstreams |
|---|---|
| `queue` | 849 |
| `list-only` | 59 |
| `parked` | 73 |
| `excluded` | 218 |

| Class | Upstreams |
|---|---|
| L1 | 487 |
| L2 | 431 |
| L? | 27 |
| L3 | 36 |
| L4 | 218 |

Categories: Productivity & Knowledge 239, AI & Models 115, Files & Photos 113, Bitcoin & Crypto 105, Developer 100, Social & Communication 100, Monitoring & Intel 88, Security & Network 78, Media 74, Media: download automation 41, Home & IoT 34, Other 28, Games 20, Finance 16, Automation 14, Family & Home Life 13, Health & Fitness 10, Education & Offline 7, Desktop & VMs 3, Field, Mesh & TAK 1.

<!-- taxonomy:begin (generated by scripts/app-taxonomy.py; do not edit) -->
## Market categories and deployment classes

Each row is normalised to the Market taxonomy in [`docs/design/TAXONOMY.md`](../../docs/design/TAXONOMY.md) by [`scripts/app-taxonomy.py`](../../scripts/app-taxonomy.py): `category` (one of 16), `subtags`, `deploy_class` and `placement`. The research-run category is kept as `category_v0`. The batches and the Top 100 table below show the Market category. `deploy_class` here is a target: CI sets the real tier when an app is added (contract §9.4).

| Category | Slug | All rows | `queue` rows |
|---|---|---|---|
| Home & IoT | `home` | 38 | 31 |
| Files & Photos | `files` | 108 | 88 |
| Media | `media` | 123 | 98 |
| Notes & Knowledge | `notes` | 74 | 58 |
| Productivity | `productivity` | 138 | 102 |
| Chat & Social | `communication` | 116 | 86 |
| AI & Agents | `ai` | 134 | 98 |
| Automation | `automation` | 18 | 15 |
| Network & Security | `network` | 83 | 68 |
| Monitoring | `monitoring` | 45 | 38 |
| News & Intel | `news` | 21 | 14 |
| Developer | `developer` | 97 | 73 |
| Family & Health | `family` | 36 | 30 |
| Finance | `finance` | 126 | 20 |
| Learning & Games | `learning` | 33 | 23 |
| Field & Robotics | `field` | 9 | 7 |

| Deploy class | Rows |
|---|---|
| `core` | 1 |
| `plugin` | 2 |
| `market-verified` | 268 |
| `market-community` | 578 |
| `list-only` | 59 |
| `none` | 291 |

| Placement | Rows |
|---|---|
| `hub` | 11 |
| `worker` | 65 |
| `leaf` | 0 |
| `any` | 1123 |
<!-- taxonomy:end -->

## Proposed queue batches

These batches are ordered by priority, ten apps each. They skip apps already in `apps/` (Home Assistant, ntfy, Uptime Kuma) and apps already in `queue.yaml` (Hermes Agent, Node-RED, Mosquitto, Vaultwarden, Actual Budget, Zigbee2MQTT).

Batch 1 holds the daily essentials for replacing a home cluster, as the founder asked. The data supports this set: all ten are L1 or L2, are listed in at least four of the seven stores, and had a release (SearXNG: a push) within the last 30 days. Seven of them are in the top 30 by score. Gitea is chosen over Forgejo because Forgejo is hosted on Codeberg and could not be scored here; Forgejo is the copyleft fork, if that is preferred. The LibreChat repo has moved to `LibreChat-AI/LibreChat`.

Batches 2 to 5 follow the score, with no hand reordering.

**Batch 1.** Nextcloud (`nextcloud/server`, Files & Photos, L2, arm64 yes), Immich (`immich-app/immich`, Files & Photos, L2, arm64 yes), Syncthing (`syncthing/syncthing`, Files & Photos, L2, arm64 yes), Paperless-ngx (`paperless-ngx/paperless-ngx`, Files & Photos, L2, arm64 yes), Gitea (`go-gitea/gitea`, Developer, L1, arm64 yes), Grafana (`grafana/grafana`, Monitoring, L2, arm64 yes), Ollama (`ollama/ollama`, AI & Agents, L1, arm64 yes), LibreChat (`LibreChat-AI/LibreChat`, AI & Agents, L1, arm64 yes), SearXNG (`searxng/searxng`, AI & Agents, L2, arm64 yes), AdGuard Home (`AdguardTeam/AdGuardHome`, Network & Security, L2, arm64 yes).

**Batch 2.** Memos (`usememos/memos`, Notes & Knowledge, L1, arm64 yes), Jellyfin (`jellyfin/jellyfin`, Media, L2, arm64 yes), FreshRSS (`FreshRSS/FreshRSS`, News & Intel, L2, arm64 yes), Audiobookshelf (`advplyr/audiobookshelf`, Media, L2, arm64 yes), Calibre-web (`janeczku/calibre-web`, Media, L2, arm64 yes), Stirling-PDF (`Stirling-Tools/Stirling-PDF`, Productivity, L1, arm64 yes), Ghost (`TryGhost/Ghost`, Productivity, L1, arm64 yes), PhotoPrism (`photoprism/photoprism`, Files & Photos, L2, arm64 yes), OpenClaw (`openclaw/openclaw`, AI & Agents, L1, arm64 yes), Trilium Notes (`TriliumNext/Trilium`, Notes & Knowledge, L2, arm64 yes).

**Batch 3.** Karakeep (`karakeep-app/karakeep`, Notes & Knowledge, L2, arm64 yes), Navidrome (`navidrome/navidrome`, Media, L2, arm64 yes), Docmost (`docmost/docmost`, Notes & Knowledge, L2, arm64 yes), Sonarr (`Sonarr/Sonarr`, Media, L2, arm64 yes), Duplicati (`duplicati/duplicati`, Files & Photos, L1, arm64 yes), Radarr (`Radarr/Radarr`, Media, L2, arm64 yes), ESPHome (`esphome/esphome`, Home & IoT, L2, arm64 yes), code-server (`coder/code-server`, Developer, L1, arm64 yes), HomeBox (`sysadminsmedia/homebox`, Family & Health, L2, arm64 yes), Prowlarr (`Prowlarr/Prowlarr`, Media, L2, arm64 yes).

**Batch 4.** Penpot (`penpot/penpot`, Developer, L2, arm64 yes), qBittorrent (`qbittorrent/qBittorrent`, Media, L2, arm64 yes), changedetection (`dgtlmoon/changedetection.io`, News & Intel, L1, arm64 yes), Firefly III (`firefly-iii/firefly-iii`, Finance, L2, arm64 yes), WordPress (`WordPress/WordPress`, Productivity, L2, arm64 yes), Linkwarden (`linkwarden/linkwarden`, Notes & Knowledge, L2, arm64 yes), LibreSpeed (`librespeed/speedtest`, Network & Security, L2, arm64 yes), Mealie (`mealie-recipes/mealie`, Family & Health, L2, arm64 yes), Grocy (`grocy/grocy`, Family & Health, L1, arm64 yes), Lobe Hub (`lobehub/lobehub`, AI & Agents, L1, arm64 yes).

**Batch 5.** Netdata (`netdata/netdata`, Monitoring, L2, arm64 yes), AnythingLLM (`Mintplex-Labs/anything-llm`, AI & Agents, L1, arm64 yes), Komga (`gotson/komga`, Media, L1, arm64 yes), Tautulli (`Tautulli/Tautulli`, Media, L2, arm64 yes), Lidarr (`Lidarr/Lidarr`, Media, L2, arm64 yes), Metabase (`metabase/metabase`, Monitoring, L2, arm64 yes), copyparty (`9001/copyparty`, Files & Photos, L1, arm64 yes), Bazarr (`morpheus65535/bazarr`, Media, L2, arm64 yes), Excalidraw (`excalidraw/excalidraw`, Notes & Knowledge, L1, arm64 yes), Umami (`umami-software/umami`, Monitoring, L1, arm64 yes).

Batches after 5 continue in score order through the `queue` rows of the CSV.

**Batch 6.** Wiki.js (`requarks/wiki`, Notes & Knowledge, L2), Jenkins (`jenkinsci/jenkins`, Developer, L1), BentoPDF (`alam00000/bentopdf`, Productivity, L2), MeTube (`alexta69/metube`, Media, L2), Seerr (`seerr-team/seerr`, Media, L1), Prometheus (`prometheus/prometheus`, Monitoring, L1), Vikunja (`go-vikunja/vikunja`, Productivity, L2): the next rows in score order that could be packaged as non-root without privileges. Skipped, with reasons in `queue.yaml`: Portainer, Frigate, Glances (licence gate cannot confirm), ArchiveBox, WireGuard, BookStack, FlareSolverr, Jackett, Kavita, Miniflux, LibreTranslate, PrivateBin (licence gate cannot confirm).

## Top 100

These are the top 100 rows by score, across all tiers. The `stores` column uses the letters u = Umbrel, o = Olares, c = CasaOS, r = Runtipi, y = YunoHost, x = Cosmos, k = Coolify.

| # | App | Upstream | Market category | Stores | Licence | Class | Stars | Last release | arm64 | Score | Tier |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Immich | `immich-app/immich` | Files & Photos | uocryxk | AGPL-3.0 | L2 | 118927 | v3.4.1 2026-11-11 | yes | 15.08 | queue |
| 2 | Home Assistant | `home-assistant/core` | Home & IoT | uocryxk | Apache-2.0 | L1 | 92258 | 2026.11.1 2026-11-09 | yes | 14.97 | queue |
| 3 | Uptime Kuma | `louislam/uptime-kuma` | Monitoring | uocryxk | MIT | L1 | 93538 | 2.5.10 2026-11-12 | yes | 14.97 | queue |
| 4 | Syncthing | `syncthing/syncthing` | Files & Photos | uocryxk | MPL-2.0 | L2 | 90391 | v2.1.7 2026-10-21 | yes | 14.96 | queue |
| 5 | Grafana | `grafana/grafana` | Monitoring | uocryxk | AGPL-3.0 | L2 | 77857 | v13.3.1 2026-11-10 | yes | 14.89 | queue |
| 6 | Vaultwarden | `dani-garcia/vaultwarden` | Network & Security | uocryxk | AGPL-3.0 | L2 | 70615 | 1.37.5 2026-11-01 | yes | 14.85 | queue |
| 7 | Memos | `usememos/memos` | Notes & Knowledge | uocryxk | MIT | L1 | 64413 | 26.11.0 2026-11-01 | yes | 14.81 | queue |
| 8 | Gitea | `go-gitea/gitea` | Developer | uocryxk | MIT | L1 | 59038 | v28.3.0 2026-11-01 | yes | 14.77 | queue |
| 9 | Jellyfin | `jellyfin/jellyfin` | Media | uocryxk | GPL-2.0 | L2 | 59239 | v12.4 2026-10-26 | yes | 14.77 | queue |
| 10 | Nextcloud | `nextcloud/server` | Files & Photos | uocryxk | AGPL-3.0-or-later | L2 | 37486 | v33.0.10 2026-10-15 | yes | 14.57 | queue |
| 11 | FreshRSS | `FreshRSS/FreshRSS` | News & Intel | uocryxk | AGPL-3.0 | L2 | 16563 | 1.30.4 2026-10-21 | yes | 14.22 | queue |
| 12 | Audiobookshelf | `advplyr/audiobookshelf` | Media | uocryxk | GPL-3.0 | L2 | 14981 | v2.37.2 2026-10-23 | yes | 14.18 | queue |
| 13 | Calibre-web | `janeczku/calibre-web` | Media | uocryxk | GPL-3.0 | L2 | 18554 | 0.6.27 2026-08-08 | yes | 14.02 | queue |
| 14 | Stirling-PDF | `Stirling-Tools/Stirling-PDF` | Productivity | uoryxk | MIT (licence-file text match) | L1 | 96355 | v3.3.0 2026-11-05 | yes | 13.98 | queue |
| 15 | Ghost | `TryGhost/Ghost` | Productivity | uoryxk | MIT | L1 | 55786 | v6.77.0 2026-11-11 | yes | 13.75 | queue |
| 16 | PhotoPrism | `photoprism/photoprism` | Files & Photos | uocryx | AGPL-3.0 (licence-file text match) | L2 | 40435 | 261029-963b58c50 2026-10-29 | yes | 13.61 | queue |
| 17 | OpenClaw | `openclaw/openclaw` | AI & Agents | uocrk | MIT | L1 | 394373 | v2026.11.3 2026-11-10 | yes | 13.60 | queue |
| 18 | SearXNG | `searxng/searxng` | AI & Agents | uoryxk | AGPL-3.0 | L2 | 39474 | none (push 2026-11-11) | yes | 13.60 | queue |
| 19 | Trilium Notes | `TriliumNext/Trilium` | Notes & Knowledge | uocryk | AGPL-3.0 | L2 | 38877 | v0.107.0 2026-11-08 | yes | 13.59 | queue |
| 20 | ntfy | `binwiederhier/ntfy` | Automation | uoryxk | Apache-2.0 OR GPL-2.0 | L1 | 35493 | v2.37.2 2026-11-04 | yes | 13.55 | queue |
| 21 | Karakeep | `karakeep-app/karakeep` | Notes & Knowledge | uocryk | AGPL-3.0 | L2 | 30471 | v0.34.1 2026-10-22 | yes | 13.48 | queue |
| 22 | Navidrome | `navidrome/navidrome` | Media | uocryx | GPL-3.0 | L2 | 24663 | v0.64.2 2026-09-24 | yes | 13.39 | queue |
| 23 | Docmost | `docmost/docmost` | Notes & Knowledge | uocryk | AGPL-3.0 | L2 | 22312 | v0.97.0 2026-10-25 | yes | 13.35 | queue |
| 24 | n8n | `n8n-io/n8n` | Automation | uocryxk | LicenseRef-n8n-Sustainable-Use-License AND Licen | L3 | 210244 | n8n@2.47.4 2026-11-11 | yes | 13.32 | list-only |
| 25 | Ollama | `ollama/ollama` | AI & Agents | uocry | MIT | L1 | 186734 | v0.40.16 2026-11-09 | yes | 13.27 | queue |
| 26 | Sonarr | `Sonarr/Sonarr` | Media | uocryxk | GPL-3.0 | L2 | 17660 | v5.0.0.2941 2026-11-03 | yes | 13.25 | queue |
| 27 | Duplicati | `duplicati/duplicati` | Files & Photos | uocrxk | MIT (licence-file text match) | L1 | 15199 | v2.4.1.0_stable_2026-10-29 2026-10-29 | yes | 13.18 | queue |
| 28 | Radarr | `Radarr/Radarr` | Media | uocryxk | GPL-3.0 | L2 | 14753 | v7.0.2.10888 2026-11-08 | yes | 13.17 | queue |
| 29 | ESPHome | `esphome/esphome` | Home & IoT | ucryxk | MIT (Python) AND GPL-3.0 (C/C++ runtime) | L2 | 12093 | 2026.10.2 2026-11-02 | yes | 13.08 | queue |
| 30 | code-server | `coder/code-server` | Developer | uoryx | MIT | L1 | 79838 | v4.145.2 2026-11-07 | yes | 12.90 | queue |
| 31 | HomeBox | `sysadminsmedia/homebox` | Family & Health | uoryxk | AGPL-3.0 | L2 | 7842 | v0.27.1 2026-10-23 | yes | 12.89 | queue |
| 32 | Prowlarr | `Prowlarr/Prowlarr` | Media | uocryxk | GPL-3.0 | L2 | 7547 | v2.7.0.5723 2026-10-27 | yes | 12.88 | queue |
| 33 | Penpot | `penpot/penpot` | Developer | uoryk | MPL-2.0 | L2 | 62286 | 2.19.1 2026-11-11 | yes | 12.79 | queue |
| 34 | Paperless-ngx | `paperless-ngx/paperless-ngx` | Files & Photos | uryxk | GPL-3.0 | L2 | 48040 | v3.4.2 2026-11-03 | yes | 12.68 | queue |
| 35 | qBittorrent | `qbittorrent/qBittorrent` | Media | uocryk | GPL (licence-file text match) | L2 | 41537 | release-5.3.0 2026-10-20 | yes | 12.62 | queue |
| 36 | AdGuard Home | `AdguardTeam/AdGuardHome` | Network & Security | uocry | GPL-3.0 | L2 | 38380 | v0.107.80 2026-11-03 | yes | 12.58 | queue |
| 37 | changedetection | `dgtlmoon/changedetection.io` | News & Intel | uryxk | Apache-2.0 | L1 | 35759 | 0.70.3 2026-11-09 | yes | 12.55 | queue |
| 38 | Actual | `actualbudget/actual` | Finance | ucryk | MIT | L1 | 30187 | v26.11.0 2026-11-02 | yes | 12.48 | queue |
| 39 | Hermes Agent | `NousResearch/hermes-agent` | AI & Agents | uock | MIT | L1 | 262808 | v0.23.1 2026-11-10 | yes | 12.42 | queue |
| 40 | Firefly III | `firefly-iii/firefly-iii` | Finance | uoryx | AGPL-3.0 | L2 | 25223 | develop-20261111.1 2026-11-11 | yes | 12.40 | queue |
| 41 | Node-RED | `node-red/node-red` | Automation | ucryx | Apache-2.0 | L1 | 23837 | 5.0.9 2026-10-21 | yes | 12.38 | queue |
| 42 | WordPress | `WordPress/WordPress` | Productivity | uoryx | LGPL (licence-file text match) | L2 | 21536 | 7.1.4 2026-10-28 | yes | 12.33 | queue |
| 43 | Linkwarden | `linkwarden/linkwarden` | Notes & Knowledge | ucryk | AGPL-3.0 | L2 | 20392 | v2.17.0 2026-11-10 | yes | 12.31 | queue |
| 44 | Transmission | `transmission/transmission` | Media | uocryxk | NOASSERTION | L? | 15407 | 4.1.4 2026-10-24 | yes | 12.19 | list-only |
| 45 | LibreSpeed | `librespeed/speedtest` | Network & Security | uoryk | LGPL-3.0 | L2 | 15294 | v6.3.1 2026-10-21 | yes | 12.18 | queue |
| 46 | Mealie | `mealie-recipes/mealie` | Family & Health | uorxk | AGPL-3.0 | L2 | 13882 | v3.30.0 2026-10-31 | yes | 12.14 | queue |
| 47 | Grocy | `grocy/grocy` | Family & Health | uryxk | MIT | L1 | 9674 | v4.7.1 2026-09-04 | yes | 11.99 | queue |
| 48 | Lobe Hub | `lobehub/lobehub` | AI & Agents | uork | Apache-2.0 (licence-file text match) | L1 | 85101 | v2.3.2 2026-11-06 | yes | 11.93 | queue |
| 49 | Netdata | `netdata/netdata` | Monitoring | ocry | GPL-3.0 | L2 | 81379 | v2.12.3 2026-11-04 | yes | 11.91 | queue |
| 50 | AnythingLLM | `Mintplex-Labs/anything-llm` | AI & Agents | uock | MIT | L1 | 68202 | v1.19.0 2026-10-26 | yes | 11.83 | queue |
| 51 | Komga | `gotson/komga` | Media | uocry | MIT | L1 | 6838 | 1.30.1 2026-11-10 | yes | 11.83 | queue |
| 52 | Tautulli | `Tautulli/Tautulli` | Media | uocrx | GPL-3.0 | L2 | 6639 | v2.19.1 2026-11-10 | yes | 11.82 | queue |
| 53 | Lidarr | `Lidarr/Lidarr` | Media | uocryx | GPL-3.0 | L2 | 5820 | v3.1.6.5079 2026-10-26 | yes | 11.76 | queue |
| 54 | Odoo | `odoo/odoo` | Productivity | oryxk | NOASSERTION | L? | 55734 | none (push 2026-11-12) | yes | 11.75 | list-only |
| 55 | Metabase | `metabase/metabase` | Monitoring | oryk | AGPL-3.0 (licence-file text match) | L2 | 50296 | v0.65.3 2026-11-06 | yes | 11.70 | queue |
| 56 | copyparty | `9001/copyparty` | Files & Photos | ucyx | MIT | L1 | 47334 | v1.20.26 2026-10-14 | yes | 11.68 | queue |
| 57 | LibreChat | `LibreChat-AI/LibreChat` | AI & Agents | uock | MIT | L1 | 47019 | v0.8.9-rc1 2026-10-26 | yes | 11.67 | queue |
| 58 | Bazarr | `morpheus65535/bazarr` | Media | uocryx | GPL-3.0 | L2 | 4417 | v1.6.3-beta.30 2026-11-11 | yes | 11.65 | queue |
| 59 | Excalidraw | `excalidraw/excalidraw` | Notes & Knowledge | ocry | MIT | L1 | 135531 | v0.18.1 2026-04-21 | yes | 11.63 | queue |
| 60 | Umami | `umami-software/umami` | Monitoring | uryk | MIT | L1 | 40080 | v3.5.0 2026-11-12 | yes | 11.60 | queue |
| 61 | Portainer | `portainer/portainer` | Developer | ucrk | Zlib | L1 | 38818 | 2.45.3 2026-10-21 | yes | 11.59 | queue |
| 62 | Frigate | `blakeblackshear/frigate` | Home & IoT | uocx | MIT | L1 | 37418 | v0.18.2 2026-10-15 | yes | 11.57 | queue |
| 63 | Glances | `nicolargo/glances` | Monitoring | cryk | AGPL-3.0 (licence-file text match) | L2 | 33936 | v4.5.9 2026-11-07 | yes | 11.53 | queue |
| 64 | Wiki.js | `requarks/wiki` | Notes & Knowledge | uryk | AGPL-3.0 | L2 | 29261 | 3.3.1 2026-11-11 | yes | 11.47 | queue |
| 65 | ArchiveBox | `ArchiveBox/ArchiveBox` | News & Intel | ucry | MIT | L1 | 29011 | v0.9.77 2026-10-27 | yes | 11.46 | queue |
| 66 | WireGuard | `wg-easy/wg-easy` | Network & Security | ucrk | AGPL-3.0 | L2 | 27476 | v15.5.0 2026-10-24 | yes | 11.44 | queue |
| 67 | Jenkins | `jenkinsci/jenkins` | Developer | cyxk | MIT | L1 | 26765 | jenkins-2.590 2026-11-10 | yes | 11.43 | queue |
| 68 | BookStack | `BookStackApp/BookStack` | Notes & Knowledge | uryk | MIT | L1 | 19141 | v26.09.3 2026-11-11 | yes | 11.28 | queue |
| 69 | BentoPDF | `alam00000/bentopdf` | Productivity | ucyk | AGPL-3.0 | L2 | 16354 | v2.8.11 2026-10-31 | yes | 11.21 | queue |
| 70 | FlareSolverr | `FlareSolverr/FlareSolverr` | Network & Security | uocr | MIT | L1 | 16197 | v3.5.2 2026-09-12 | yes | 11.21 | queue |
| 71 | Jackett | `Jackett/Jackett` | Media | uocry | GPL-2.0 | L2 | 16356 | v0.24.3053 2026-11-12 | yes | 11.21 | queue |
| 72 | Open WebUI | `open-webui/open-webui` | AI & Agents | uocrk | LicenseRef-Open-WebUI-License (BSD-3 + branding  | L3 | 158445 | v0.13.3 2026-11-08 | yes | 11.20 | list-only |
| 73 | Langflow | `langflow-ai/langflow` | AI & Agents | uck | MIT | L1 | 156555 | v1.13.2 2026-11-10 | no | 11.19 | queue |
| 74 | MeTube | `alexta69/metube` | Media | uorxk | AGPL-3.0 | L2 | 15250 | 2026.11.10 2026-11-10 | yes | 11.18 | queue |
| 75 | Seerr | `seerr-team/seerr` | Media | ucryx | MIT | L1 | 13188 | v3.5.1 2026-10-21 | yes | 11.12 | queue |
| 76 | Kavita | `Kareadita/Kavita` | Media | cryx | GPL-3.0 | L2 | 12106 | v0.9.1.4 2026-09-02 | yes | 11.08 | queue |
| 77 | Miniflux | `miniflux/v2` | News & Intel | oyxk | Apache-2.0 | L1 | 9921 | 2.3.5 2026-11-02 | yes | 11.00 | queue |
| 78 | LibreTranslate | `LibreTranslate/LibreTranslate` | AI & Agents | uryk | AGPL-3.0 | L2 | 17495 | v1.9.6 2026-05-26 | yes | 10.99 | queue |
| 79 | PrivateBin | `PrivateBin/PrivateBin` | Files & Photos | uryk | Apache-2.0 (licence-file text match) | L1 | 8741 | 2.1.1 2026-11-04 | yes | 10.94 | queue |
| 80 | Prometheus | `prometheus/prometheus` | Monitoring | oyx | Apache-2.0 | L1 | 67561 | v3.16.0 2026-11-05 | yes | 10.83 | queue |
| 81 | NocoDB | `nocodb/nocodb` | Productivity | uoryk | LicenseRef-Sustainable-Use (licence-file text ma | L3 | 65509 | 2026.10.1 2026-10-29 | yes | 10.82 | list-only |
| 82 | Plane | `makeplane/plane` | Productivity | uok | AGPL-3.0 | L2 | 62338 | v1.4.3 2026-10-28 | no | 10.79 | queue |
| 83 | Pi-hole | `pi-hole/pi-hole` | Network & Security | cry | EUPL-1.2 | L2 | 61844 | v6.6 2026-11-11 | yes | 10.79 | queue |
| 84 | Vikunja | `go-vikunja/vikunja` | Productivity | uryk | AGPL-3.0 | L2 | 6023 | v2.8.0 2026-11-05 | yes | 10.78 | queue |
| 85 | Joplin | `laurent22/joplin` | Notes & Knowledge | ryxk | NOASSERTION | L? | 57147 | v3.7.22 2026-10-28 | yes | 10.76 | list-only |
| 86 | Homarr | `homarr-labs/homarr` | Monitoring | uryk | Apache-2.0 | L1 | 5344 | v2.12.0 2026-11-06 | yes | 10.73 | queue |
| 87 | Rallly | `lukevella/rallly` | Productivity | oryk | AGPL-3.0 | L2 | 5357 | v4.17.0 2026-11-11 | yes | 10.73 | queue |
| 88 | Kimai | `kimai/kimai` | Productivity | uryk | AGPL-3.0 | L2 | 5150 | 2.71.0 2026-10-25 | yes | 10.71 | queue |
| 89 | LocalAI | `mudler/LocalAI` | AI & Agents | uoy | MIT | L1 | 50332 | v4.12.1 2026-10-23 | yes | 10.70 | queue |
| 90 | Mastodon | `mastodon/mastodon` | Chat & Social | oryx | AGPL-3.0 | L2 | 50596 | v4.7.5 2026-11-03 | yes | 10.70 | queue |
| 91 | Dokuwiki | `dokuwiki/dokuwiki` | Notes & Knowledge | ryxk | GPL-2.0 | L2 | 4740 | release-2026-07-14c 2026-09-02 | yes | 10.68 | queue |
| 92 | RSSHub | `DIYgod/RSSHub` | News & Intel | ory | AGPL-3.0 | L2 | 46956 | v2026.11.12-8637.9b47c74 2026-11-12 | yes | 10.67 | queue |
| 93 | SiYuan Note | `siyuan-note/siyuan` | Notes & Knowledge | crk | AGPL-3.0 | L2 | 47195 | v3.8.10 2026-11-10 | yes | 10.67 | queue |
| 94 | Appsmith | `appsmithorg/appsmith` | Developer | uok | Apache-2.0 | L1 | 41235 | v2.6.0 2026-10-28 | yes | 10.62 | queue |
| 95 | Tailscale | `tailscale/tailscale` | Network & Security | ucr | BSD-3-Clause | L1 | 38970 | v1.104.6 2026-11-11 | yes | 10.59 | queue |
| 96 | Glance | `glanceapp/glance` | Monitoring | ryk | AGPL-3.0 | L2 | 38148 | v0.8.8 2026-11-07 | yes | 10.58 | queue |
| 97 | Mosquitto | `eclipse-mosquitto/mosquitto` | Home & IoT | uryx | EPL-2.0 OR EDL-1.0 (BSD-3-Clause) | L2 | 11360 | v2.1.2 2026-02-09 | yes | 10.56 | queue |
| 98 | CyberChef | `gchq/CyberChef` | Developer | ryk | Apache-2.0 | L1 | 36380 | v11.5.0 2026-09-18 | yes | 10.56 | queue |
| 99 | Zipline | `diced/zipline` | Files & Photos | ryxk | MIT | L1 | 3499 | v4.8.3 2026-11-08 | yes | 10.54 | queue |
| 100 | Homepage | `gethomepage/homepage` | Monitoring | rxk | GPL-3.0 | L2 | 33627 | v2.8.0 2026-11-11 | yes | 10.53 | queue |

## Not resolved

- **GitHub "not found"** (22): `getumbrel/umbrel-back-that-mac-up`, `stan-smith/fossflow`, `lightning-network-plus/lnpclient`, `nibdo/bloben-app`, `beclab/flowstudio`, `xxnuo/mtranserve`, `beclab/router`, `veyvey45-eng/wealthpilot`, `xinference/xinference`, `roonlabs/roonserver`, `jedie/django-for-runners`, `jedie/django-fritzconnection`, `jedie/django-example`, `jedie/pyinventory`, `browserless/chromium`, `capsoftware/cap-web`, `bluewave-labs/checkmate-backend-mono-multiarch`, `drizzle-team/gateway`, `ente/server`, `rhyssullivan/executor-selfhost`, `rybbit-io/rybbit-backend`, `getzep/postgres`.
- **Packaging repo only, no upstream match** (16): `bitnami/containers`, `linuxserver/budge`, `linuxserver/docker-chromium`, `linuxserver/docker-duckdns`, `linuxserver/docker-obsidian`, `linuxserver/docker-plex`, `linuxserver/docker-qdirstat`, `linuxserver/docker-resilio-sync`, `linuxserver/docker-unifi-controller`, `linuxserver/docker-unifi-network-application`, `linuxserver/heimdall`, `yunohost-apps/custom_backup_ynh`, `yunohost-apps/mail_relay_ynh`, `yunohost-apps/my_webdav_ynh`, `yunohost-apps/timemachine_ynh`, `yunohost-apps/wasteofspace_ynh`.
- **Licence needs a human read** (`L?`): Transmission, Odoo, Joplin, Dify, Twenty, Formbricks, Planka, ZeroTier, Langfuse, NocoBase, RabbitMQ, TLDraw, Rocket.Chat, Medusa, FastGPT, Firefox, ShowDoc, Prestashop, Scrypted, Jaaz, Upload Assistant, Luanti, PureBlog, Bison Wallet, Nostr Relay, Electrs, WoofBot (without Lightning).
- **No licence detected** by GitHub or in a licence file. These are L4 and excluded, but some are known open source with non-standard licence files (for example Cockpit, Drupal and Stalwart) and deserve a check: Plex (`plexinc/pms-docker`), Stalwart (`stalwartlabs/stalwart`), Claude Code (`anthropics/claude-code`), Cockpit (`cockpit-project/cockpit`), Drupal (`drupal/drupal`), Obsidian (`obsidianmd/obsidian-releases`), Qwen3.6-27B (llama.cpp) (`QwenLM/Qwen3`), Tor Browser (`torproject/tor`), redroid (`remote-android/redroid-doc`), phpIPAM (`phpipam/phpipam`), Mantis (`mantisbt/mantisbt`), Cowyo (`schollz/cowyo`), Firefly (`Safe3/firefly`), Pool CLI (`poolsideai/pool`), OPcache GUI (`amnuts/opcache-gui`), Lazylibrarian (`lazylibrarian/LazyLibrarian`), Leed (`LeedRSS/Leed`), Hello World (`crccheck/docker-hello-world`), myTinyTodo (`maxpozdeev/mytinytodo`), OpenThread Border Router (`ownbee/hass-otbr-docker`), Inspircd (`inspircd/inspircd`), Bonfire (`bonfire-networks/bonfire-app`), GlassHome (`glasshome/homeassistant-addon`), Indexhibit (`Indexhibit/indexhibit`), Excalidraw (`ozencb/excalidraw-persist`), udctl (`oatnil-top/udctl`), Mixpost (`inovector/MixpostApp`), h5ai (`lrsjng/h5ai`), xTeVe (`dnsforge-repo/xteve`), Lidarr on Steroids (`youegraillot/lidarr-on-steroids`), Lionwiki (`farvardin/lionwiki-t2t`), Route96 (`v0l/route96`), SkyBro (`xDeeKay/SkyBro`), Urbit (`mopfel-winrux/urbit-umbrel`), Qwen3.5 35B-A3B Q4_K_M (lcpp) (`aamsellem/orales-market`), VRAMarket (`jeffreyturov-dev/vramarket`), L-Town (`besoeasy/linktown`), Obsidian LiveSync (`vrtmrz/self-hosted-livesync-server`), Armadietto (`remotestorage/armadietto`), Secret Santa (`arcanis/secretsanta`), Sikka (`sikkalabs/sikka`), terraria-server (`hexlo/terraria-server-docker`), Formicaio (`bochaco/formicaio`), Bitcoin Cash Node (`danhaus93-ops/umbrel-bch-apps`), ElectrumX (`getumbrel/umbrel-electrumx`), 20 euros (`jatekos101/20euros`), Kollider (`kolliderhq/kollider-lite-app`), Urbit Bitcoin Connector (`yapishu/urbit-bitcoin-node`).
