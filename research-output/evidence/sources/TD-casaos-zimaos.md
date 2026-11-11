# Sources · TD-casaos-zimaos (CasaOS / ZimaOS, Tier B teardown)

**Accessed:** 2026-11-11 (UTC) · **Used in:** [`02-competitors/casaos-zimaos.md`](../../02-competitors/casaos-zimaos.md) · **Claims:** [`../claims/TD-casaos-zimaos.csv`](../claims/TD-casaos-zimaos.csv) (C-TD-casaos-zimaos-001 … 051)
**Archive:** Wayback save requests are denied in this environment. Load-bearing web pages and the release-artifact inspection are saved as text in [`TD-casaos-zimaos/`](TD-casaos-zimaos/) with a [`SHA256SUMS`](TD-casaos-zimaos/SHA256SUMS) file. Code is cited at pinned commits (shallow clones in `work/.lab/src/icewhale_*`, outside the repo).

## Code (pinned)

| # | Repository | Commit | Commit date | License (pinned file) | Used for |
|---|---|---|---|---|---|
| K1 | IceWhaleTech/CasaOS | `e099dd6b4982a264663df2536a55bfea2ae5448a` | 2026-11-09 | Apache-2.0 (`LICENSE`) | install/update paths, `UpdateSystemVersion` |
| K2 | IceWhaleTech/get | `15d5563aef5e3628f2b2ac65d619d81228ab2f3e` | 2025-04-16 | Apache-2.0 | installer download and verification behaviour |
| K3 | IceWhaleTech/CasaOS-AppManagement | `debfa317f0f996b91b43210e8d57799461388704` | 2025-04-16 | Apache-2.0 | app format, validator, app update/rollback, catalog refresh |
| K4 | IceWhaleTech/CasaOS-AppStore | `820f99007fd521d0b534d94366371debea2ed438` | 2026-11-04 | Apache-2.0 | `x-casaos` manifests (sparse checkout: Jellyfin, HomeAssistant, Immich, Ollama) |
| K5 | IceWhaleTech/CasaOS-UserService | `800c630c3443364cde142a9aadea0dc3880e6232` | 2025-04-16 | Apache-2.0 | identity (JWT/JWKS, roles) |
| K6 | IceWhaleTech/CasaOS-Common | `bd9a9049507c3bb9fea9f2caf389f738d10e74b3` | 2026-10-29 | Apache-2.0 | ES256 JWT helper |
| K7 | IceWhaleTech/ZimaOS | `8bc15999eb23085dbe5de5310cba4d7489507565` | 2026-10-15 | **none** (no LICENSE file) | README, OTA feed `rauc.txt`, workflow, SECURITY.md |
| K8 | IceWhaleTech/ZimaDocs | `43d34b94077db2f608e6d28970814b027e7b1fb3` | 2026-11-11 | MIT | recovery, offline update, backup, remote access, AI docs, release notes |
| K9 | IceWhaleTech/buildroot (branch `2026.02.x-zima`) | `4d129097f2261310c821e47931114a9712c0372d`; compare against `2026.02.x` via `gh api …/compare` | 2026-11-04 | Buildroot (GPL-2.0, NOASSERTION in API) | image build fork, Docker pin commit `bca5fabb9be2ef0b04d53104db85904b55033df9` |
| K10 | IceWhaleTech/ZimaOS-MCP | `1a153d1ce7138e7c67c0ebf79d14e090100e22b4` | 2025-04-01 | none | external MCP server |
| K11 | IceWhaleTech/ZimaOS-Blue | `60c0872d28aefa880390a937220a0b824729a158` | 2026-10-22 | MIT | agent runtime |

Also cloned but only skimmed: CasaOS-Gateway `606a8452`, CasaOS-UI `400a22c1`, Mod-Store `d012ab43`.

## Release artifacts

| # | Artifact | Hash / identity | How read | Saved |
|---|---|---|---|---|
| R1 | `zimaos-x86_64-1.8.0.raucb` (GitHub release 1.8.0, 2026-10-15) | sha256 `c24bccfd72e5df3e0af31e55160878ea8f20d0fccd531a0437ab370cd6042b45` | host: HTTP range read of the CMS signature and signed manifest; VM: full download, `unsquashfs`, read-only loop mounts of `rootfs.img` and `boot.vfat` in a disposable Lima Debian 13 VM with no host mounts (deleted afterwards). Nothing executed. | [`TD-casaos-zimaos/zimaos-1.8.0-bundle-inspection.txt`](TD-casaos-zimaos/zimaos-1.8.0-bundle-inspection.txt) |
| R2 | `zimaos-x86_64-1.8.0_installer.img` | first 1 MiB only (GPT) | HTTP range read, parsed with a short Python script | same file |
| R3 | `https://get.casaos.io` live installer | sha256 `4a9e7c4ba4159aa7516c7c1acb3f017235868f80a6c2ce2922a9ee00a6837536` (807 lines, "v0.4.16") | downloaded and read, not run; `/update` and `/update.sh` returned HTTP 500 at 2026-11-11 04:27 UTC | hash and observations in the same file |

## Web pages (PRIMARY, vendor)

| # | URL | Saved text | sha256 |
|---|---|---|---|
| W1 | https://www.zimaspace.com/zimaos | [`zimaos.txt`](TD-casaos-zimaos/zimaos.txt) | `6473cc33…f7dd` |
| W2 | https://www.zimaspace.com/zimaos/pricing | [`zimaos-pricing.txt`](TD-casaos-zimaos/zimaos-pricing.txt) | `c2a91006…8f` |
| W3 | https://shop.zimaspace.com/products.json?limit=250 (Shopify feed) | [`shop-products-extract.txt`](TD-casaos-zimaos/shop-products-extract.txt) (Zima products, first 6 variants) | `958ef5e6…51` |

## Issue tracker (PRIMARY)

| # | Item | Read |
|---|---|---|
| I1 | IceWhaleTech/ZimaOS#557 "Update fails silently on Zimacube 1: slot B permanently marked bad…" (2026-07-29, closed) | body and resolution comment |
| I2 | IceWhaleTech/ZimaOS#549 "Docker 28.x mount churn knocks NetworkManager, logind, polkit, PID 1 & rauc off the system bus…" (2026-07-22, open) | body (first part) |
| I3 | IceWhaleTech/ZimaOS#478 "[Beta][Bug] Corrupt Services and boot" (2026-04-19, open) | title and state only |
| I4 | IceWhaleTech/ZimaOS#587 "compose teardown doesn't dispose of containers" (2026-09-08, open) | title only (not cited as a claim) |

## Metadata (gh api, 2026-11-11)

- `orgs/IceWhaleTech/repos`: names, licenses, stars, push dates (60+ repos).
- `repos/IceWhaleTech/ZimaOS/releases`: tags, dates, asset names, sizes, download counts.
- `repos/IceWhaleTech/buildroot/branches` and `compare/2026.02.x...2026.02.x-zima`.

## Reused from earlier passes (not re-derived)

C-W3-046, C-W3-047 (W3 install/update survey), C-REF-DC-longevity-006 (CasaOS release stall), C-W18-064 (script-then-image sequencing). Phase-1 landscape notes on CasaOS/ZimaOS: `research/competitors/landscape.md` §1.3.
