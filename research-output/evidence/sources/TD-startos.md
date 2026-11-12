# Sources: TD-startos (StartOS / Start9, Tier B condensed teardown)

Used in `research-output/02-competitors/startos.md`. Claim rows are in `evidence/claims/TD-startos.csv` (C-TD-startos-001 … 051). Accessed 2026-11-11 unless stated.

## Code (pinned)

| Source | Pin | Notes |
|---|---|---|
| https://github.com/Start9Labs/start-technologies (formerly `Start9Labs/start-os`; the old name redirects) | tag `start-os/v0.4.2` = commit `175ce3beb370443d8db2cea30c3f99ebdcd1a8f5` (2026-11-08) | Shallow, blob-filtered worktree at `<lab-dir>/src/start-os-v0.4.2/` (outside the repo). All `repo@sha:path#Lx-Ly` citations in the teardown use this commit. Files read: `ARCHITECTURE.md`, `LICENSE`, `NOTICE.md`, `projects/start-os/ARCHITECTURE.md`, `projects/start-os/build/image-recipe/{build.sh,Dockerfile,run-local-build.sh,README.md}`, `projects/start-os/build/lib/scripts/{upgrade,prune-images,prune-boot,startos-initramfs-module,sign-unsigned-modules}`, `shared-libs/crates/start-core/src/{update/mod.rs,mcp.rs,disk/main.rs,setup.rs,init.rs,service/mod.rs,version/mod.rs,s9pk/v2/mod.rs,s9pk/v2/manifest.rs}`, `shared-libs/crates/start-core/{s9pk-structure.md,mcp-tools.json}`, `shared-libs/crates/start-core/src/version/update_details/v0_4_0.md`, `projects/start-os/backup-fs/DESIGN.md`, `projects/start-os/docs/src/*.md` (install, update, trusted keys, hardware, backups, health checks, registries, containers, CLI reference, overview), `projects/start-os/release-notes/0.4.1.md`. |
| Earlier clone at `<lab-dir>/src/start-os/` | `master` @ `246876d3` (2026-11-10) | Used by the earlier claim C-W3-048. The tag differs from it in 270 files; the image/rootfs facts in C-W3-048 hold at the tag too (C-TD-startos-011, -012). |

## Saved web pages and API output (`evidence/sources/TD-startos/`, hashes in `SHA256SUMS`)

| File | URL | Type | Claims |
|---|---|---|---|
| `release-v0.4.2.txt` | https://github.com/Start9Labs/start-technologies/releases/tag/start-os/v0.4.2 (via `gh api`) | PRIMARY | 001, 006, 049, 050 |
| `start9-server-one.txt` | https://start9.com/server-one | PRIMARY | 040 |
| `start9-server-one-prices.txt` | https://start9.com/server-one (Shopify variant JSON embedded in the page) | PRIMARY | 039 |
| `start9-premium-support.txt` | https://start9.com/premium-support | PRIMARY | 040 |
| `debian-backports.txt` | https://backports.debian.org/ | PRIMARY | 009 |
| `issue-735.txt` | https://github.com/Start9Labs/start-technologies/issues/735 | PRIMARY | 033 |
| `issue-3465.txt` | https://github.com/Start9Labs/start-technologies/issues/3465 | PRIMARY | 008, 010 |
| `issue-3923.txt` | https://github.com/Start9Labs/start-technologies/issues/3923 | PRIMARY | 044 |
| `issue-4009.txt` | https://github.com/Start9Labs/start-technologies/issues/4009 | PRIMARY | 046 |
| `issue-4435.txt` | https://github.com/Start9Labs/start-technologies/issues/4435 | PRIMARY | 045 |
| `issue-4454.txt` | https://github.com/Start9Labs/start-technologies/issues/4454 | PRIMARY | 023 |
| `issue-4647.txt` | https://github.com/Start9Labs/start-technologies/issues/4647 | PRIMARY | 008, 043 |

## Opened but not saved

| URL | Type | Claims |
|---|---|---|
| https://github.com/Start9Labs/start-technologies/issues/3881, /3702, /4499, /4402, /4453, /4450, /4160, /2837 | PRIMARY (issue tracker) | 032, 036 (titles and states read with `gh`) |
| https://api.github.com/repos/Start9Labs/start-technologies/contributors | PRIMARY-METADATA | 042 |
| https://api.github.com/repos/Start9Labs/start-technologies (full_name, created_at, license) | PRIMARY-METADATA | 002 |

## Reused from other workstreams

| File | Type | Claims |
|---|---|---|
| `evidence/sources/W16/start9-coincarp.txt` (CoinCarp seed-round page, saved by W16) | SECONDARY | 041 |

**Not done:** no Wayback captures were requested (save requests are denied here) and none were looked up. No StartOS image was booted; nothing in this teardown comes from running Start9 code.
