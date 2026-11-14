<!-- SPDX-License-Identifier: Apache-2.0 -->
# Blocked Market apps: why, and what could fix them

Wave G #7 (Market unblock, part 1), checked 2026-11-12. Part of [the Market intake](CANDIDATES.md).

> **Explain it like I am the founder**
> The CI app gate (`sdk/tools/app-gate`) refuses to let an app be installed (tier `blocked`) when its image has a CRITICAL vulnerability that already has a fix, a secret-looking string, a failed smoke test or a licence it cannot confirm. We never weaken the gate. The only honest ways out are: upstream ships a fixed image, we pin that image, and the gate passes on its own.
> This file lists, per blocked app, what blocks it and whether a fixed image really exists. "Verified" means the tag and its digest were read from the registry's HTTPS API on 2026-11-12 (the `crane` tool is not installed on the worker). It does **not** mean the fix works: only a fresh gate run says that, and the gate, not a person, sets the tier.

## How it was checked

For every image of every blocked app, the worker asked the registry (Docker Hub, GHCR) for the current digest of the pinned tag and for newer tags of the same shape. "Same digest" means upstream has not rebuilt the tag since we pinned it, so the finding is still there. Scanning (Trivy) is not available on the worker, so no fix claim here is a scan result.

Not reachable: `registry.librechat.ai` (the proxy refuses it, 403) and the GitHub API (not enabled for this session), so LibreChat's registry and every upstream release date could not be read.

## Apps on `main`

| App | Blocker | Candidate fix | Status |
|---|---|---|---|
| `uptime-kuma` | 13 CRITICAL (4 with a fix) in `2.5.10-rootless`, scan 2026-11-12 | `2.5.11-rootless` @ `sha256:d213a1d2…ffa13dac` (amd64, arm64, arm/v7), built 2026-11-12 09:15 UTC, after 2.5.10 | Verified to exist; pinned in this PR; waits for the PR's CI gate |
| `paperless-ngx` | Only the bundled `postgres:18.6-trixie`: Go `stdlib` CVE-2025-68121 (in `gosu`) and the Debian snakeoil private key. The paperless 3.4.2 image itself is clean of fixable CRITICALs | `postgres:18.6-alpine` @ `sha256:9ba53c7d…193085b` (no `gosu`, no `ssl-cert`); runs as UID 70 | Verified to exist; pinned in this PR (not yet scanned); waits for the PR's CI gate |
| `syncthing` | CRITICAL CVE-2026-111497, `brotli-libs` 1.2.0-r1 (fixed 1.2.1-r0), Alpine base | None: `2.1.7` is the newest tag and `latest`, `2`, `2.1` all point to the same digest | No fix published. Stays blocked until upstream rebuilds on a newer Alpine |
| `gitea` | CRITICAL CVE-2026-123158, `openssh-keygen` 10.3_p1-r1 (fixed r2) | None: `28.3.0-rootless` is the newest tag, digest unchanged | No fix published. Stays blocked |
| `nextcloud` | `libopenexr` CVE-2026-42216/42217; postgres Go `stdlib`; secret findings (Azure key string in a vendored PHP library, postgres snakeoil key) | No newer `33.x` tag (33.0.10 is the last). Majors `34.0.5` and `35.0.2` exist in the registry. Postgres alpine as for paperless-ngx | Not bumped: a major upgrade moves off the pinned stable33 line (a founder call), and the Azure-string finding is in upstream's PHP code either way |
| `librechat` | 5 npm CVEs in the app image; Go and Debian CVEs in ferretdb and `postgres-documentdb`; a test-fixture JWT; no licence-matrix row | ferretdb `2.7.0` and `postgres-documentdb:17-0.107.0-ferretdb-2.7.0` are the newest tags, digests unchanged. LibreChat: registry unreachable; `ghcr.io/danny-avila/librechat` only lists up to `v0.8.8-rc4` | No fix verifiable. Stays blocked. The licence-matrix row is outside `apps/` |
| `hermes-agent` | 3 CRITICAL (1 with a fix), 291 HIGH | None: `v0.23.0` (built 2026-11-05) is newer than the `v2026.9.x` tags | No fix published |
| `home-assistant` | 5 CRITICAL (4 with a fix) | None: `2026.11.1` is the newest, digest unchanged | No fix published |
| `node-red` | `openssh-client` 10.3_p1-r1, CVE-2026-123158 (fixed r2) | None: `5.0.9` is the newest; the `-minimal` variant has the same package and `-debian` has its own CRITICAL | No fix published |
| `immich` | Debian CVEs and Go `stdlib` 1.18.2 in `postgres:14-vectorchord0.4.3-pgvectors0.2.0`; `libopenexr` in the server image | None for the server (`v3.4.1` is the newest). Postgres tags `17-…` and `18-vectorchord1.1.1…` exist, but changing the major version needs a data migration and Immich's supported pairing; not an in-place pin bump | Not bumped. Needs a decision |
| `mosquitto` | Not a vulnerability: the licence matrix row says `EDL-1.0`, which is not an SPDX id, so the licence gate cannot confirm it | Fix is a one-line row in `research-output/evidence/license-matrix.csv` (outside `apps/`), not an image | Out of scope for this PR |

## Apps in the open batch PRs (read-only, not edited here)

Manifests read from `feat/market-batch-2-3` (#49) and `feat/market-batch-4-5` (#62). Candidates are checked the same way. Many rows add "no licence-matrix row": that is a research-file fix, separate from the image.

| App (PR) | Blocker | Candidate fix | Status |
|---|---|---|---|
| `audiobookshelf` (#49) | npm CVEs: `form-data`, `proxy-addr`, `sequelize`, `tar` | None: `2.37.2` newest | No fix published |
| `calibre-web` (#49) | `certifi`, `zip`; 2 test private keys | `0.6.27-ls394` was rebuilt (now `sha256:868b5627…1b77bd8`); newer tags `0.6.27-ls407` to `-ls409` exist | Verified to exist; not scanned. Try in a follow-up on #49 |
| `code-server` (#49) | Go `stdlib` 1.20.7 | None: `4.145.2` newest | No fix published |
| `esphome` (#49) | libbrotli1, perl, linux-libc-dev, pillow, uv | None: `2026.10.2` newest | No fix published |
| `freshrss` (#49) | libbrotli1 CVE-2026-111497 | None: `1.30.4` newest | No fix published |
| `ghost` (#49) | Go `stdlib` in ghost; certifi and Go in `mysql:8.0.46`; 13 secret strings in upstream JS | None: `6.77.0-alpine` newest; mysql 8.0.46 is the newest 8.0 | No fix published |
| `karakeep` (#49) | libbrotli1, dompurify, Go `stdlib`; meilisearch openssl; meilisearch cosign identity | karakeep: none. meilisearch: newer `v1.56.0` to `v1.56.2` exist | Meilisearch bump verified to exist (a 15-minor jump; needs a compatibility read first). karakeep has no fix |
| `openclaw` (#49) | dompurify; a Slack-token-like string in a QA scenario; startup probe never passes | None: `2026.11.3` newest | No fix published; the probe failure needs a cluster log |
| `photoprism` (#49) | `linux-libc-dev`; mariadb Go `stdlib`; crash loop | photoprism: none. mariadb: `13.0.2` exists (major) | Crash loop needs a cluster log |
| `prowlarr`, `radarr`, `lidarr` (#49, #62) | .NET runtime 8.0.27 CVE-2026-70188/88092 | None: pinned `-ls` tags are the newest and digests unchanged | No fix published. prowlarr and radarr also fail the smoke test (LinuxServer init under non-root) |
| `sonarr` (#49) | brotli-libs; smoke test | None: newest | No fix published |
| `anything-llm` (#62) | many CRITICAL (`linux-libc-dev`, npm); `gitlab-pat` string in the JS bundle | None: `1.19.0` newest | No fix published |
| `bazarr` (#62) | `certifi` GHSA-6q48-6c7w-9gw2 | None: pinned `-ls372` newest | No fix published |
| `copyparty` (#62) | brotli-libs | None: `1.20.26` newest | No fix published |
| `excalidraw` (#62) | brotli-libs, openssl in the floating `latest` image | None: `latest` digest unchanged | No fix published |
| `firefly-iii` (#62) | libbrotli1, `linux-libc-dev`; postgres Go `stdlib` and snakeoil key | App: none. Postgres: `18.6-alpine` as for paperless-ngx | Alpine verified to exist; app image still has its own CRITICALs |
| `komga` (#62) | netty, tomcat, spring CVEs | None: `1.30.1` newest | No fix published |
| `librespeed` (#62) | libbrotli1, `linux-libc-dev` | None: `6.3.1` newest | No fix published |
| `linkwarden` (#62) | Go `stdlib` in the app; postgres 16 Go `stdlib` and snakeoil key | App: none. Postgres 16: `16.15-alpine` would need to be looked up; majors `18.x` exist | App has no fix |
| `mealie` (#62) | 45 secret strings in bundled `yt_dlp` plus a CRITICAL | None: `v3.30.0` newest | No fix published |
| `metabase` (#62) | Postgres Go `stdlib` and snakeoil key only; the metabase image passes | Postgres: `18.6-alpine` as for paperless-ngx. Also `v0.65.4` exists | Best next candidate: same fix as paperless-ngx |
| `penpot` (#62) | Postgres 15 Go `stdlib` and snakeoil key only | Postgres: `15.x-alpine` tag not looked up here; majors `18.x` exist | Candidate: an Alpine tag of the same major |
| `qbittorrent` (#62) | brotli-libs; smoke test gets 401 | None: `5.3.0-2` newest | No fix published; the 401 is a smoke-test setting question |
| `umami` (#62) | Postgres 15 Go `stdlib` and snakeoil key only | Same as penpot | Candidate: an Alpine tag of the same major |
| `wordpress` (#62) | mariadb `11.8.9-noble` Go `stdlib` | `mariadb:12.3.3-noble` exists, a different major | No same-major fix |

## What this PR changed

Only `uptime-kuma` and `paperless-ngx`, and neither tier was changed: both stay `blocked` in the manifest until this PR's `ci-apps` gate run says otherwise. If a gate run passes, the follow-up commit sets the tier to the value the gate computed. Nothing was weakened: no scanner rule, allowlist or gate check was touched.

## Next steps (ordered)

1. Read the gate results for the two bumps; set tiers only where the gate passes.
2. If the Alpine postgres passes, repeat it for `metabase`, `firefly-iii`, `nextcloud` (on their branches or after merge); for `penpot`, `umami` and `linkwarden` find the Alpine tag of their own major first.
3. Add the missing licence-matrix rows (`mosquitto` spelling, LibreChat and the many "no row" apps): a research-file change, one commit.
4. Re-run `apps-rescan` weekly: Alpine and Debian rebuilds clear most brotli, openssh and certifi findings without any change from us.

## Part 2 (apps/market-unblock-2, 2026-11-13)

Every blocked image was read from the Docker Hub and GHCR registry APIs again. All pinned digests are unchanged since part 1 except `calibre-web` (the LinuxServer tag `0.6.27-ls394` was re-pointed; our pinned digest is the one of `0.6.27-ls409`, so only the label was corrected).

- **Changed (unscanned, the gate decides):** `metabase`, `penpot` and `umami` blocked only on their bundled `postgres:*-trixie` (Go `stdlib` CVE-2025-68121 in `gosu`, Debian snakeoil key). They now use `postgres:18.6-alpine` (metabase) and `postgres:15.19-alpine` (penpot, umami), same major as before, UID 70, as `paperless-ngx` did in part 1.
- **Held, documented in each README:** every other blocked app (reasons and "what would unblock it" are in the README of the app). `mealie` has a newer tag `v3.31.0` that is not scanned and cannot be claimed as a fix. `firefly-iii`, `linkwarden` and `nextcloud` have Alpine postgres tags but their app images still block. `nextcloud` 34 is not touched (decision D9 pending). `mosquitto` and `librechat` need a licence-matrix row (outside `apps/`).
- Run 43405572161 (the six apps of #102): `radarr`, `prowlarr` (.NET 8.0.27, fixed in 8.0.32), `sonarr`, `qbittorrent` (brotli-libs; qbittorrent also gets 401), `openclaw` (dompurify, 3 CRITICAL without a fix, a Slack-token-shaped QA file); `photoprism` failed to create the cluster on Docker Hub pulls (infrastructure). Their smoke tests pass except qbittorrent. No fixed tags exist, so they stay blocked.
