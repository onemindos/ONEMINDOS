# Sources: TD-tier-c-selfhost (Tier C teardowns: Cosmos, YunoHost, Runtipi, Cloudron, Coolify and Dokploy)

All sources were opened on 2026-11-11. Claim IDs are in `../claims/TD-tier-c-selfhost.csv` (C-TD-tier-c-selfhost-001 … 110; the numbering has gaps by product block).

## Archiving note

The run cannot submit Wayback save requests. Load-bearing vendor pages therefore use the fallback: **extracted text plus sha256**, stored in [`TD-tier-c-selfhost/`](TD-tier-c-selfhost/) (list in `SHA256SUMS`). Before hashing, the text was masked: email-shaped strings, private IP addresses and prefixes, and anything shaped like a credential (including the public demo login on the Cloudron pricing page) were replaced with `<…-masked>`. Each hash is of the masked text. The secret scan (`gitleaks dir`) found no leaks in that folder.

**Forum pages are not stored in the repo** because they carry user handles. The YunoHost 13.0 beta thread is kept in the run's lab folder (`<lab-dir>/tierc-web/`), and only its hash is recorded below. Code needs no archive: every code citation is a permalink pinned to a commit SHA.

## Code (pinned shallow clones in `<lab-dir>/src/`)

| # | Repository and pin | What was read | Claims |
|---|---|---|---|
| K1 | `azukaar/Cosmos-Server` @ `69c53038287c6a15c53ddcab74ea20ef8b79ad90` (master, 2026-08-30; = v0.23.4) | `LICENCE`, `dockerfile`, `readme.md`, `changelog.md`, `src/update.go`, `src/launcher/launcher.go`, `src/market/init.go`, `src/pro/index.go`, `src/backups/restic.go`, `src/constellation/` (file list), AI/MCP code search | 001, 003–008, 010, 011 |
| K2 | `YunoHost/yunohost` @ `2734f2337921717a138953640522646094103d5a` (dev, 2026-10-30; changelog 12.1.41.2 stable) and tag `debian/13.0.9` @ `5b4d51cb8f986f41636f53a0879c336924d2099b` | `LICENSE`, `debian/changelog`, `src/app.py`, `src/tools.py`, `src/app_catalog.py`, `src/utils/resources.py`, `src/migrations/` (list), AI/MCP code search | 020, 021, 023, 024, 026, 027, 032 |
| K3 | `YunoHost-Apps/nextcloud_ynh` @ `ae8b20a7027c8178c5dde7f58f5b6e912a885cc2` (2026-10-15) | `manifest.toml` | 025 |
| K4 | `runtipi/runtipi` @ `a8f22ed8bae48af0bce99a218c902261ea472d45` (2026-11-03) | `LICENSE`, `README.md`, `.gitmodules`, `scripts/install.sh`, `docker-compose.prod.yml`, `packages/backend/src/modules/app-lifecycle/commands/update-app-command.ts`, `…/apps/app-files-manager.ts`, AI/MCP code search | 040, 042–046, 049 |
| K5 | `runtipi/runtipi-appstore` @ `1de3985bd40ecfcb6ec5204d5672b073e3a164dd` (already cited as C-W12-010) | `apps/nextcloud/config.json` | 046 |
| K6 | `platform/box` on git.cloudron.io @ `3a75b3638940559e8c803cdc46cacf38b016a6d4` (master, 2026-11-10) | `LICENSE`, `CHANGES`, `scripts/cloudron-setup`, `scripts/installer.sh`, `src/updater.js`, `src/apptask.js`, `src/docker.js`, `src/apphealthmonitor.js`, AI/MCP code search | 060–066, 069, 070 |
| K7 | `coollabsio/coolify` @ `37aaf6074c309492a42cf7e8ccba23fbc8cc3c58` (2026-11-10; release.json stable 4.7.5) | `LICENSE`, `release.json`, `routes/ai.php`, `routes/api.php`, `app/Mcp/Servers/CoolifyServer.php`, `app/Mcp/Tools/` (count), `scripts/upgrade.sh`, `scripts/install.sh`, `templates/compose/` (count), `composer.json`, `bootstrap/helpers/remoteProcess.php`, `app/Enums/ProxyTypes.php` | 080–086, 089 |
| K8 | `Dokploy/dokploy` @ `1048bcb113cee9f40ef82ffd6216e19c6faad94d` (2026-11-09; v0.31.0) | `LICENSE.MD`, `LICENSE_PROPRIETARY.md`, `README.md`, `proprietary/` directories, `packages/server/src/setup/server-setup.ts`, `…/services/settings.ts`, `…/services/rollbacks.ts`, `…/utils/ai/select-ai-provider.ts`, `apps/dokploy/package.json`, `…/setup/traefik-setup.ts` | 100, 101, 103–106, 110 |
| K9 | `Dokploy/mcp` @ `26799a777e444a7cad6bb7ecf0d5969fb859fa58` (2026-09-23; package 0.30.7) | `LICENSE`, `README.md`, `src/types.ts`, `src/generated/tools.ts` (annotation counts) | 107 |
| K10 | GitHub REST API (PRIMARY-METADATA, point in time): releases of Cosmos, Runtipi, Coolify and Dokploy; repo metadata and contributor lists of all five GitHub repos; tags of `YunoHost/yunohost` | | 002, 012, 021, 031, 041, 048, 081, 088, 102, 109 |

## Web (vendor, PRIMARY)

| # | Source | Saved text (masked) sha256 | Claims |
|---|---|---|---|
| W1 | https://cosmos-cloud.io/pricing | `9a487061bd8f22d54dabaf7375b9364c5f52ea663e97999541be5e07ace06399` (`cosmos-pricing.txt`) | 009 |
| W2 | https://cosmos-cloud.io/ | `fd8ebbfa1eb8331c5f7c561a63e90c91e8c7f4bed29604386818cdb8abc0c022` (`cosmos-home.txt`) | 013 |
| W3 | https://yunohost.org/roadmap.en.html | `c8979305ead2a38d164ce56f2a673ca092bcd6db9604edae1cbd5b68fb384e64` (`ynh-roadmap.txt`) | 022 |
| W4 | https://doc.yunohost.org/en/admin/get_started/install_on/raspberry_pi/ (plus the `install_on/` index page, not saved) | `08e4038bc43f59024ff864b44c8f744be0dc513f89a173f84df04eae2567102c` (`ynh-pi.txt`) | 028 |
| W5 | https://forum.yunohost.org/t/yunohost-13-0-trixie-spooky-beta/40656 (not in repo: user handles) | lab text sha256 `51bc4e9333a7b7c49c1c42918dce4fdc8d344e56f3d2af8302d946e1a95d4c54` | 029 |
| W6 | https://donate.yunohost.org/ (not saved; not load-bearing) | — | 030 |
| W7 | https://runtipi.io/docs/quick-start | `d668dc317951a837cbd3f5ed4f08d181c141fc88049356b8320537c95de6a020` (`runtipi-qs.txt`) | 047 |
| W8 | https://www.cloudron.io/pricing.html | `46d3741fb1eb58c39a53de76334de01adb39664c6bbc57b9a037be37bc7a9689` (`cloudron-pricing.txt`) | 067, 068 |
| W9 | https://docs.cloudron.io/installation/ | `0a495d1baf909e20f241cfcf55c94c3c46b16035d0b29b647609b7b2d88559fc` (`cloudron-req.txt`) | 061 |
| W10 | https://docs.cloudron.io/updates/ | `505cd990fbe1302ea85b2423d9f2aa30178e1b2b28ef00ff691c563c1ed18cd6` (`cloudron-updates.txt`) | 063, 068 |
| W11 | https://docs.cloudron.io/packaging/manifest/ | `6b934498ba7a1b217d1fdf28f89f7fef73538b2a610cb24258e76edc7b1a121d` (`cloudron-packaging.txt`) | 066 |
| W12 | https://coolify.io/pricing/ | `abd8186938196884f64417ae38cc45ed26a6b9b3a99a3e067ecf7c35d51c51c6` (`coolify-pricing.txt`) | 087 |
| W13 | https://coolify.io/docs/get-started/installation | `950420ac6a68cb5adc5145abe44d9c2d96848ef82116f7abfdba03147a6fb858` (`coolify-req.txt`) | 086 |
| W14 | https://dokploy.com/pricing | `8a75e5d89e91fa42de6b10e1032eda90327cc68059d387e9db9fd7a4b4fbcad9` (`dokploy-pricing.txt`) | 108 |
| W15 | https://docs.dokploy.com/docs/core/installation | `7206afcdab294f30dbe616e24e2aee85239280d75f139d027cf6c2a78c99f421` (`dokploy-req.txt`) | 103 |
| W16 | https://docs.dokploy.com/docs/core/ai | `98a552182fe6c211812f24c0d599b9a615ca9c73a283a032d87a4af8631b6466` (`dokploy-ai.txt`) | 106 |

## Opened but not used

- `https://coolify.io/docs/knowledge-base/mcp` returned "Page not found". The Coolify MCP facts come from code (K7) instead.
- `https://www.mintlify.com/Dokploy/mcp/introduction` returned "Page gone". The Dokploy MCP facts come from the `Dokploy/mcp` repo (K9) instead.
- `https://doc.yunohost.org/en/admin/install/` returned 404; the `install_on/` pages were used.
- Third-party pricing summaries (Capterra, GetApp, review blogs) surfaced by search were **not cited**. They disagree with each other, and the vendor page (W8) was available.

## Not done (Tier C limits)

- No product was installed in a VM for this pass. Every behaviour comes from reading code at the pins above and from vendor docs.
- No issue-tracker failure reports were collected (Tier C does not require them).
- Team sizes are contributor-list proxies on the default branch (all-time), not headcounts.
