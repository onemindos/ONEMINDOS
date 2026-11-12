# Sources: TD-umbrelos (umbrelOS / Umbrel 2.0 Tier A teardown)

Used in `research-output/02-competitors/umbrelos.md`. Claim rows are in `evidence/claims/TD-umbrelos.csv`.

**Code was read from shallow clones** (`--depth 1 --filter=blob:none`) in `.lab/src/umbrel` (tag 2.0.1) and `.lab/src/umbrel-21b1` (tag 2.1.0-beta.1), outside the repo. Nothing was built or run. Code citations are GitHub permalinks pinned to commit SHAs, which serve as their own archive.

**Saved copies** of load-bearing web pages are in `evidence/sources/TD-umbrelos/`, with hashes in `TD-umbrelos/SHA256SUMS`. They were fetched with curl on 2026-11-10, then stripped to plain text with emails redacted (the hashes cover these text files). The store feed is reduced to titles, dates and prices.

## Pinned code

| Source | Commit / tag | Date | Type | Archive |
|---|---|---|---|---|
| github.com/getumbrel/umbrel | `a72dac249974d1603be9423d3cf6ac1a2d8f65f9` = tag 2.0.1 (stable, "Latest") | 2026-11-01 | PRIMARY (code) | SHA permalink |
| github.com/getumbrel/umbrel | `6f357e18d0a4faccb69d9fa59e3eae9cc3380538` = tag 2.1.0-beta.1 | 2026-11-03 | PRIMARY (code) | SHA permalink |
| github.com/getumbrel/umbrel | `9298257b0e904ca8d8270b1702672666343f0b86` = tag 2.0.0 (checked only for MCP permission shape) | 2026-09-22 | PRIMARY (code) | SHA permalink |
| github.com/getumbrel/umbrel | `c43beed964074d08865d648ca9ac3359826a14ff` = master HEAD ("Archive umbrelOS 2.1 Beta 1") | 2026-11-04 | PRIMARY-METADATA | SHA permalink |
| github.com/getumbrel/umbrel-apps | `51aac978c67c7c9bbe7e0b42f64ff5f3139c8763` (master) | 2026-11-11T00:56Z | PRIMARY (CI workflow) | SHA permalink |
| github.com/silitics/rugix | tag v1.3.2 = `a455ea393326e2231b00a0168f922edd0fc84a9b`; repo metadata (license, releases, contributors) via `gh api` | 2026-10-29 | PRIMARY-METADATA | SHA permalink |

### Files read at 2.1.0-beta.1 (`6f357e18`)
`packages/os/umbrelos.Dockerfile`, `packages/os/README.md`, `packages/os/rugix/rugix-bakery.toml`, `packages/os/rugix/layers/umbrelos-amd64.toml`, `packages/os/rugix/recipes/setup-rugix/files/{bootstrapping.toml,bootstrapping-pi.toml,system.toml,state-data.toml}`, `packages/os/rugix/recipes/umbrelos-boot/files/grub.cfg`, `packages/umbreld/source/index.ts`, `packages/umbreld/source/modules/update/{update.ts,rugix.ts,release-signing.ts,signing-keys.ts,install-release.ts}`, `releases/README.md`, `packages/umbreld/source/modules/apps/{schema.ts,app.ts,apps.ts}`, `packages/umbreld/source/modules/backups/backups.ts`, `packages/umbreld/source/modules/user/user.ts`, `packages/umbreld/source/modules/auth/auth.ts`, `packages/umbreld/source/modules/server/trpc/is-authenticated.ts`, `packages/umbreld/source/modules/mcp/{mcp.ts,server.ts}`, `packages/umbreld/source/modules/lan-ingress/lan-ingress.ts`, `packages/umbreld/source/modules/hardware/raid.ts`, `packages/umbreld/source/modules/machines/libvirt.ts`, `scripts/install`.

### Files read at 2.0.1 (`a72dac24`)
`packages/umbreld/source/modules/system/update.ts`, `packages/umbreld/source/modules/system/system.ts`, `packages/umbreld/source/index.ts`, `scripts/update-script`, `packages/umbreld/source/modules/mcp/mcp.ts`, and the tree listing (`git ls-tree`), which shows that `modules/update/` and `releases/` are absent.

## Web and issue sources

| URL | Accessed | Type | Archive |
|---|---|---|---|
| https://github.com/getumbrel/umbrel/releases (2.0.0, 2.0.1, 2.1.0-beta.1) | 2026-11-10 | PRIMARY | Wayback for 2.0.0: http://web.archive.org/web/20261009194712/https://github.com/getumbrel/umbrel/releases/tag/2.0.0 ; saved `TD-umbrelos/umbrel-2.0.0-release-notes.txt`, `umbrel-2.1.0-beta.1-release-notes.txt` (sha256 in SHA256SUMS) |
| https://umbrel.com/support/basics/updating-umbrelos (updated 2026-10-02) | 2026-11-10 | PRIMARY | http://web.archive.org/web/20261015040551/https://umbrel.com/support/basics/updating-umbrelos ; saved `TD-umbrelos/umbrel-support-basics_updating-umbrelos.txt` |
| https://umbrel.com/support/backups-and-recovery/backing-up-your-data (updated 2026-10-02) | 2026-11-10 | PRIMARY | http://web.archive.org/web/20261102030304/https://umbrel.com/support/backups-and-recovery/backing-up-your-data ; saved copy |
| https://umbrel.com/support/storage/managing-your-storage (updated 2026-11-10) | 2026-11-10 | PRIMARY | saved `TD-umbrelos/umbrel-support-storage_managing-your-storage.txt` |
| https://umbrel.com/support/advanced/connecting-ai-agents (updated 2026-09-27) | 2026-11-10 | PRIMARY | saved `TD-umbrelos/umbrel-support-advanced_connecting-ai-agents.txt` |
| https://umbrel.com/support/basics/sharing-your-umbrel-with-other-users (updated 2026-09-27) | 2026-11-10 | PRIMARY | saved `TD-umbrelos/umbrel-support-basics_sharing-your-umbrel-with-other-users.txt` |
| https://umbrel.com/support/apps/running-custom-docker-containers (updated 2026-10-02) | 2026-11-10 | PRIMARY | saved `TD-umbrelos/umbrel-support-apps_running-custom-docker-containers.txt` |
| https://store.umbrel.com/products.json | 2026-11-10 | PRIMARY (store feed) | saved `TD-umbrelos/umbrel-store-products.json` |
| https://umbrel.com/umbrel-home | 2026-11-10 | PRIMARY | not archived (spec summary only; also in phase-1 UMB report) |
| https://umbrel.com/umbrel-pro | 2026-11-10 | PRIMARY | not archived (spec summary only) |
| https://github.com/getumbrel/umbrel/wiki/License-FAQ (read via raw wiki) | 2026-11-10 | PRIMARY | http://web.archive.org/web/20260309061923/https://github.com/getumbrel/umbrel/wiki/License-FAQ |
| https://rugix.org/docs/ctrl/over-the-air-updates | 2026-11-10 | PRIMARY (vendor docs) | http://web.archive.org/web/20260608053547/https://rugix.org/docs/ctrl/over-the-air-updates/ (an older snapshot; the text was read live) |
| https://github.com/getumbrel/umbrel/issues/2072 | 2026-11-10 | PRIMARY (issue tracker) | GitHub (permanent issue URL) |
| https://github.com/getumbrel/umbrel/issues/2190 | 2026-11-10 | PRIMARY (issue tracker) | GitHub |
| https://github.com/getumbrel/umbrel/issues/2245 | 2026-11-10 | PRIMARY (issue tracker) | GitHub |
| https://github.com/getumbrel/umbrel/issues/2124 | 2026-11-10 | PRIMARY (issue tracker) | GitHub |
| https://github.com/getumbrel/umbrel/issues/2298 | 2026-11-10 | PRIMARY (issue tracker, single report) | GitHub |
| https://github.com/getumbrel/umbrel/issues/1955 | 2026-11-10 | PRIMARY (issue tracker) | GitHub |
| https://github.com/getumbrel/umbrel/issues/2001 (LUKS feature request) | 2026-11-10 | PRIMARY (issue tracker) | GitHub |

## Internal sources built on (not re-verified unless a claim row says so)

- `research/competitors/umbrel.md` (UMB): phase-1 teardown; features, app format and website.
- `research/platform/verify-updates-rollback-backups-security.md` §2 (VUPD): signing chain read from `master`. **Correction made here:** that code is in 2.1.0-beta.1 only, not in stable 2.0.x (C-TD-umbrelos-010..012).
- `context/03-repo-findings-index.md` rows for Umbrel, and contradictions C-7, C-8, C-16..C-19, C-40.
- `research-output/evidence/decision-critical.md` (DC-06, DC-11, DC-12, DC-18, DC-19).

## Searches run with no primary result

- WebSearch "umbrel.com support MCP AI agents token permissions": found only a secondary news piece (reclaimthenet.org). It was not used; the support page above was opened directly.
- WebSearch "umbrel.com support multiple users accounts members owner": community threads only. The support page above was used instead.
