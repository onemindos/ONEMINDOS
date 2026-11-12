<!-- SPDX-License-Identifier: Apache-2.0 -->
# App deployment: umbrelOS 2.1 study and the OneMind design

**Date:** 2026-11-12 · **Status:** study + proposal · **Area:** install, dependencies, permissions, ports, data, updates, uninstall, exposure (proxy, `.local`, local HTTPS), sandboxing, community stores, app page metadata, manifest format.
**Reference read:** umbrelOS `2.1.0-beta.1`, commit `6f357e18d0a4` (paths below are relative to that tree; `D:` = `packages/umbreld/source/modules/`, `U:` = `packages/ui/src/`). Public pages read on 2026-11-12: `apps.umbrel.com` app pages.
**Related OneMind docs:** contract [`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §3, §4, §9–§11; [`docs/leap/core/SANDBOX.md`](../leap/core/SANDBOX.md), [`DEPLOYMENTS.md`](../leap/core/DEPLOYMENTS.md), [`UPDATES.md`](../leap/core/UPDATES.md); [`docs/architecture/CONTRACT-12-DRAFT.md`](../architecture/CONTRACT-12-DRAFT.md); in-flight: `feat/app-pipeline` (gate, scaffold, schema), `feat/gateway-agent-mcp` (scan catalog, MCP, app page), `feat/deploy-v0`, the networking design `docs/architecture/NETWORKING.md` (mesh, `onemind-edge`, box CA) and `docs/strategy/umbrel-parity.md` (gap ids `PD-xx`).

> **Licence rule for this page.** umbrelOS is PolyForm Noncommercial 1.0.0 (checked at the tag above). OneMind is sold commercially. This page **describes** umbrelOS behaviour and cites file paths; it copies no code, strings, assets or UI text, and every OneMind part named in §4 is our own code on permissively licensed or separately shipped components, each listed with its licence and pinned version.

> **Explain it like I am the founder**
> umbrelOS installs an app by copying a folder from a Git repository (a manifest plus a Docker Compose file plus optional shell scripts) onto the box and running it with Docker. Every app gets one fixed port; umbrelOS sits in front of that port, checks you are signed in, and adds HTTPS with its own home certificate. It is fast and polished, but anything in that folder runs with full control of the box, updates have no undo, and uninstall deletes your data.
> OneMind keeps the polish and closes those holes: apps run in a fenced Kubernetes namespace, nothing unscanned installs, agents can only ask, updates take a snapshot and roll back by themselves, and removing an app keeps its data unless you separately say "delete".

---

## 1. How umbrelOS does it

### 1.1 Architecture in one picture

```
 apps.umbrel.com (editorial feed, release history; optional)        GitHub: official + community app repos
          │  HTTPS JSON (UI fetches directly)                              │ isomorphic-git shallow clone, every 5 min
          ▼                                                                ▼
 ┌────────────── UI (React) ──────────────┐        ┌──────────────── umbreld (Node, runs as root) ─────────────────┐
 │ Discover / Category / App page         │ tRPC   │ AppStore → AppRepository (clone, registry)                    │
 │ Install review → install / update      │──────► │ Apps (install, deps, uninstall) → App (state machine)         │
 │ App settings (env, storage, auth)      │        │   └ legacy-compat/app-script (bash): hooks, exports, compose  │
 └────────────────────────────────────────┘        │ LanIngress: nftables redirect → mux → AppGateway (auth proxy) │
                                                   │   local CA + 30-day server cert, optional native-TLS passthru │
                                                   │ MCP: app tools (install/uninstall directly when granted)      │
                                                   └──────────────────────────┬────────────────────────────────────┘
                                                                              ▼
                                                          Docker Engine, one bridge network umbrel_main_network
```

### 1.2 The manifest (`umbrel-app.yml`) and the app folder

- **Schema:** `D:apps/schema.ts` (`AppManifestSchema`, zod). Fields fall into five groups:
  - *Store metadata:* `id`, `name`, `tagline`, `icon`, `category`, `version`, `description`, `website`, `developer`, `submitter`, `submission` (the PR URL), `repo`, `support`, `gallery` (screenshot file names), `releaseNotes`, `installSize` (bytes).
  - *Runtime:* `port` (the one public port), `path` (path to open), `dependencies` (app ids), `implements` (ids this app can stand in for), `permissions` (today only `GPU` is acted on, `D:apps/app.ts` `patchComposeFile`), `torOnly`, `requiresHttps`, `nativeTlsHostnameSuffixes`, `defaultShell`, `widgets`.
  - *Credentials:* `defaultUsername`, `defaultPassword`, `deterministicPassword` (password derived from the box seed per app, `D:apps/app.ts` `deriveDeterministicPassword`, and `derive_entropy` in the app script).
  - *Data:* `backupIgnore` globs, `storage.dataRoot` (lets the data folder move to another disk), `folderAccess` slots (named host folders an app may mount, with read-only flags and a note).
  - *Settings:* `environment` (variables the user may override, with defaults and option lists).
  - *Compatibility:* `manifestVersion`, checked against the OS release by `D:apps/manifest-compatibility.ts` (a prerelease counts as its final release).
- **Validation is mostly off:** `validateManifest()` in `schema.ts` normalises `manifestVersion` and checks `storage`, then returns the parsed YAML unvalidated (full schema parsing is a TODO in the source). `version` is free text, not semver.
- **The folder** (in the store repository, one directory per app id): `umbrel-app.yml`, `docker-compose.yml`, optional `exports.sh` (shell, sourced on the host to export variables to dependants), `hooks/` (executables: `pre-install`, `post-install`, `pre-start`, `post-start`, `pre-stop`, `post-stop`, `pre-update`, `post-update`, `pre-uninstall`, `post-uninstall`), `*.template` files rendered with `envsubst`, optional `torrc`. See `D:apps/legacy-compat/app-script` (`execute_hook`, `template_app`, `copy_app_files`).
- **Compose conventions:** a service named `app_proxy` is not a container any more; its environment (`APP_HOST`, `APP_PORT`, `PROXY_AUTH_ADD`, whitelist/blacklist paths, `PROXY_TRUST_UPSTREAM`, `PROXY_TIMEOUT`) is rendered with `docker compose config` into `app-gateway.json` and read by umbreld's in-process gateway; the service is stripped from the runtime file (`app-script` `compose()`, `D:app-gateway/app-gateway.ts` `readAppGatewayConfig`). Variables such as `APP_DATA_DIR`, `APP_SEED`, `APP_PASSWORD`, `APP_DOMAIN`, `DEVICE_DOMAIN_NAME` are exported by `source_app`.

### 1.3 Stores: official and community

- **Official store** is a public Git repository (`D:../constants.ts` `UMBREL_APP_STORE_REPO`). Screenshots and icons come from a separate GitHub Pages gallery (`D:apps/app-repository.ts` `readRegistry`).
- **Clone and refresh:** `AppRepository.atomicClone()` does a depth-1, single-branch clone into a temp dir, `chown`s it, deletes `.gitkeep`, then moves it into place. `AppStore.start()` checks every **5 minutes** (`updateInterval`) whether the remote head moved (`checkLatestCommit` via `listServerRefs`) and re-clones. **No signature or commit pinning:** the box follows the branch head of every repository.
- **Community stores:** `addRepository(url)` in `D:apps/app-store.ts` accepts any URL, clones it immediately and saves it (tRPC `apps.addRepository`, owner session). A community repo has an `umbrel-app-store.yml` with an `id` and `name`; its app ids must start with that id (`readRegistry` filter). Duplicate ids resolve by repository order (`resolvedApps`). The UI badges community apps (`U:modules/community-app-store/community-badge.tsx`) and has an add/remove dialog (`U:modules/app-store/community-app-store-dialog.tsx`).

### 1.4 Install flow (data flow)

1. **Review** (`apps.installReview` → `Apps.getInstallReview`): returns required folder-access slots and whether the app asks for GPU. The UI shows required apps, then folders, then GPU (`U:modules/app-store/install-review-dialog.tsx`); dependency alternatives are chosen in `U:modules/app-store/select-dependencies-dialog.tsx` using `implements` (`dependency-alternatives.ts`).
2. **Pre-checks** (`D:apps/apps.ts` `#install`): not already installed; manifest version compatible; the manifest `port` does not collide with a VM port forward (`machines.assertAppPortAvailable`); selected dependency providers validated (`resolveSelectedDependencies`). There is **no** check of the Compose file itself.
3. **Copy:** `rsync` the template folder into `app-data/<id>/`; state `installing`, progress 1.
4. **App.install** (`D:apps/app.ts` `#install`): save dependency and folder choices; `patchComposeFile()` (force legacy container names, migrate old storage paths, redirect the data root, add GPU device mappings when `permissions` has `GPU`); write a user-settings overlay compose; `pull()` all images with progress 1–99 %; refresh LAN ingress; run `app-script install` (hooks, templates, `compose up`) with **2 retries**.
5. **Failure:** the instance is dropped and the UI told `not-installed`; the copied `app-data/<id>` folder and pulled images are left for the image-cleanup sweep (`D:apps/image-cleanup.ts`).
6. **Record:** append the id to `apps` in the store.

**Trust boundary:** hooks and `exports.sh` from the repository run **on the host as umbreld's user (root)**, with non-zero exits swallowed (`execute_hook` ends in `|| true`). A community store therefore has root on the box by design.

### 1.5 Ports, networking and sandboxing

- **One port per app**, chosen by the app author in the manifest; uniqueness is a store-review convention, not enforced on the box beyond the VM check. Apps may also publish further host ports or use `network_mode: host`; LAN ingress reserves those it can see (`D:lan-ingress/lan-ingress.ts` `getAppIngressCandidates`).
- **Network:** every app joins one shared Docker bridge, `umbrel_main_network`, a /16 (`legacy-compat/docker-compose.yml`, `docker-compose.common.yml`). Apps can reach each other and the host. There is no per-app network policy.
- **Sandboxing:** none beyond Docker defaults. The Compose file is not checked for `privileged`, `cap_add`, host paths, host network or devices (no such checks exist in `D:apps/` or `D:lan-ingress/`). Images are pinned by digest by store convention only.
- **Folder access** is the one user-facing permission: named slots mapped to host folders, resolved by the backend (`#resolveFolderAccess`) and written into the overlay compose.

### 1.6 Exposure: app gateway and LAN ingress

- **nftables redirect** (`D:lan-ingress/lan-ingress.ts` `buildNftRuleset`): own table; inbound LAN traffic to an app's public port is redirected to a hidden local port (23000+); direct access to the hidden port is dropped. Apps keep "owning" their port, umbreld sits in front.
- **Mux per app:** each hidden port runs a small TCP mux that sniffs the first bytes: plain HTTP goes to the gateway, TLS is terminated with umbrelOS's certificate and then proxied (`createMuxServer`, `createHttpsProxyServer`). A loopback listener on the public port serves host forwarders such as Tailscale Serve (`ensureAppLoopbackServer`).
- **App gateway** (`D:app-gateway/app-gateway.ts`, express + http-proxy-middleware): checks the umbrelOS session cookie unless the app opts out (`PROXY_AUTH_ADD=false`) or the path is whitelisted; authorises per app (`auth.authorizeApp`, member shares); handles WebSocket upgrades with per-app socket revocation; one-time handoff from the dashboard (`/umbrel_/api/v1/auth/handoff`); a friendly error page while the app starts (`error-page.ts`). The owner can override gateway auth per app (`appProxyAuthEnabled`).
- **Local HTTPS:** a box CA (RSA 4096, 10 years, path length 0) and a **30-day** server certificate whose SANs cover `umbrel.local`, the hostname, the avahi-published name and every IPv4 address including VPN addresses (`getServerSans`, `ensureCa`, `ensureServerCertificate`). The CA can be downloaded and reset (`getCaCertificate`, `resetCa`). **No X.509 name constraints**, so a leaked CA key could sign any site for devices that trust it.
- **Native TLS passthrough** (`D:lan-ingress/native-tls.md`, `tls-client-hello.ts`): apps without `app_proxy` that serve their own TLS may list DNS suffixes; matching SNI (or absent SNI) is passed through unopened. Bounded ClientHello parsing (5 s, 64 KiB, 128 slots).
- **Remote:** Tor hidden service per app (`docker-compose.tor.yml`), or Tailscale (system module).

### 1.7 Updates

- **Detection:** the UI compares the installed `version` string with the registry's (`U:modules/app-store/update-availability.ts`: any difference is "update"). The store repo moves every 5 minutes, so an update appears whenever the upstream branch moves.
- **Apply** (`D:apps/app.ts` `#update`): `pre-patch-update` copies compose, templates, `exports.sh`, `torrc` and `hooks` from the repo; patch compose; pull; start (2 retries); copy the new manifest; `post-patch-update`. **No snapshot, no health check, no rollback.** On error the state becomes `unknown` and the user must retry. Unused images are swept afterwards.
- **Release history** comes from `apps.umbrel.com` (`U:features/app-store/data/releases.ts`, at most 5 releases, accepted only when its current version equals the local registry's; the local registry stays authoritative).

### 1.8 Uninstall

`D:apps/apps.ts` `#uninstall` refuses while another app depends on it; revokes member shares and MCP grants; then `App.#uninstall` runs stop hooks (falling back to a forced container teardown), removes file references, **deletes the app's data root and `app-data/<id>`**, clears notifications, drops it from the app list, recent apps and widgets. Data that sits on unreachable external storage is left behind rather than deleted blind. There is no "keep data" option.

### 1.9 Agents (MCP)

`D:mcp/tools/apps.ts`: with the App Store grant, an MCP client can `install_app` and `uninstall_app` **directly** (no human approval), after reading `get_app_store_details`. Uninstall through MCP permanently deletes app data. Grants are per app or "all" (`D:mcp/mcp.ts`).

### 1.10 The store UI and `apps.umbrel.com`

- **On the box:** Discover, categories rail, search, virtual grid, an updates shelf and dialog, and an app page with hero, gallery (PhotoSwipe), an info band (version, compatibility, developer, source), description and a release timeline (`U:features/app-store/components/**`). Editorial content (banners, sections, artwork) is fetched from `apps.umbrel.com/api/v3/...` and may only decorate apps that exist locally; artwork must come from the same origin (`data/storefront.ts`, `data/catalog.ts`). Offline or blocked feed falls back to the local registry.
- **Public page** (e.g. an `apps.umbrel.com/app/<id>` page): name, tagline, icon, screenshots, version, category, source link, developer (with count of their apps), submitter (with link to the submission PR), compatibility (minimum OS), description, features list, "what's new" (last five releases with dates and links), related apps. It shows **no** install size, hardware needs, licence, security scan or permissions.

### 1.11 What umbrelOS does well (worth matching)

Instant feel (progress from image pull, state pushed over events); install review that asks only what matters; dependency alternatives via `implements`; per-app gateway sign-in with WebSocket revocation; friendly "starting" page; a local CA with automatic short-lived server certs; data root that can move to another disk; folder-access slots; per-app credentials shown before first open; image cleanup; editorial store that degrades gracefully offline; a clear public app page per app.

### 1.12 Where umbrelOS is weak (where OneMind wins)

| # | Weakness | Evidence |
|---|---|---|
| W1 | Store content (hooks, `exports.sh`) runs as root on the host; any community store URL gets root | `app-script` `execute_hook`, `source_app`; `app-store.ts` `addRepository` |
| W2 | No Compose policy: privileged, host network, host paths and devices all allowed | no checks in `D:apps/`, `D:lan-ingress/` |
| W3 | One flat network for all apps | `umbrel_main_network` |
| W4 | Stores follow a mutable branch head; no signature, no pinning, no review on the box | `app-repository.ts` `update`, `atomicClone` |
| W5 | No scan, no licence, no permissions summary on the store or public page | `schema.ts`, public app page |
| W6 | Manifest validation disabled; `version` free text | `schema.ts` `validateManifest` |
| W7 | Updates have no snapshot, health gate or rollback | `app.ts` `#update` |
| W8 | Uninstall deletes data with no keep option | `app.ts` `#uninstall` |
| W9 | Agents install and uninstall without a human | `mcp/tools/apps.ts` |
| W10 | Local CA has no name constraints; 10-year RSA root | `lan-ingress.ts` `ensureCa` |
| W11 | Port is author-chosen and global; conflicts found late | `apps.ts` `#install` (VM check only) |

---

## 2. What OneMind has today

| Area | Today (path) | State |
|---|---|---|
| Manifest | `apps/<id>/onemind.app.yaml`, schema `sdk/schema/onemind.app.schema.json` (contract §4) | `main`: id, name, version, description, category (free text), icon, licence, source, archs, requires, web port, manifests |
| Manifest additions | `links`, `upstream`, `tier`, `spec.updates`, `spec.agent` (contract §9.3, §11.2) | `feat/app-pipeline` schema |
| Packaging | Kustomize per app under `apps/<id>/manifests/`, images pinned by tag + digest | `main` (3 seed apps) + 6 more on `feat/app-pipeline` |
| Scaffold and gate | `sdk/tools/app-scaffold`, `app-gate` (schema, licence class, pinning, Trivy 0.76.2, ClamAV, secrets, cosign, upstream health, non-root, k3d smoke), `app-readme`, `scan.json` | `feat/app-pipeline` |
| Intake and taxonomy | `apps/_intake/queue.yaml`; ranked candidates `apps/_intake/CANDIDATES.md`, `candidates.csv` | `main` / `feat/app-taxonomy` |
| Catalog API | `GET /v1/apps` (`core/onemind_core/catalog.py`); scan, links, tier (§11.4, `core/onemind_core/scan.py`) | `main` / `feat/gateway-agent-mcp` |
| Install / remove | `app.install`, `app.remove` actions, owner approval, idempotent, expiring, audited (`core/onemind_core/actions.py`, `audit.py`) | `main` |
| Executor | `kubectl apply -k` into `app-<id>`; remove deletes the namespace **and its data** (`core/onemind_core/executors.py`) | `main` |
| Scan gate | approve refuses missing/failing/stale scan (§10.3, §11.1) | `feat/gateway-agent-mcp` |
| Agents | agent principals per app, MCP `list_nodes`, `list_apps`, `request_action` (no approve) (§11.2, §11.3) | `feat/gateway-agent-mcp` |
| Dashboard | Market, Approvals, `AppDetail.tsx` with `AppTrust.tsx` (links, licence, tier, last scan) | `main` / `feat/gateway-agent-mcp` |
| Install sandbox | rule file, PSA restricted, gateway RBAC, default-deny NetworkPolicy, `plan_sha256` | spec only (`docs/leap/core/SANDBOX.md`) |
| Private deploys | `onemind deploy`, on-box scan, revisions, rollback, secrets, Git watch, migration kit | spec only (`docs/leap/core/DEPLOYMENTS.md`) |
| App updates | Renovate bumps + gate; `app.update` with health gate and revert | `renovate.json` on `feat/app-pipeline`; on-box part spec only (`UPDATES.md` §3.4) |
| Exposure | `onemind-edge` (Go), forward-auth, `<app>.onemind.local`, name-constrained box CA, mesh names | design only (`docs/architecture/NETWORKING.md`, branch `feat/net`) |
| Developer install | `deploy/install.sh`, compose hub, `verify.sh` | `feat/deploy-v0` |
| Home UI | design system `ui/**`; Home, dock, widgets, store, settings | `main` / `uileap` |

---

## 3. Match and beat

| Topic | umbrelOS | OneMind will match | OneMind will beat |
|---|---|---|---|
| Install review | folders, GPU, deps | Plan card: deps, volumes, GPU, folders, node fit | Plan is **bound by hash** to what is applied (`plan_sha256`); shows images, licence, scan, egress, agent scopes |
| Who can install | owner, or any MCP client with a grant | Owner one-tap | **Agents only request**; owner approves on phone with passkey |
| Store trust | branch head, no signature | Official + community sources | Sources **pinned to a commit**, moved only by approval; on-box scan for community apps; CI gate + daily rescan for the official catalog |
| Sandbox | Docker defaults, shared network, root hooks | Same app variety | Kind allowlist, PSA `restricted`, own namespace, default-deny NetworkPolicy, no host hooks at all (hooks are argv in a container, §12.13) |
| Ports | author-chosen global port | Stable per-app URL | No host ports by default; every app at `https://<app>.onemind.local` behind forward-auth; host ports only declared and conflict-checked in the plan |
| Local HTTPS | 10-year RSA CA, 30-day certs, no name constraints | Automatic per-box CA and renewal | ECDSA P-256 CA with **name constraints**; same certificate over LAN and mesh |
| Updates | copy + pull + start, no undo | Update available badge, release notes | Snapshot → apply → health probe → keep or **auto-revert**; an update that widens permissions needs a fresh approval |
| Uninstall | deletes data | One-tap remove | Remove **keeps data**; `app.delete_data` is separate with typed confirmation and a final snapshot |
| Data location | movable data root | Choose disk per app | Data on Retain storage class with backups on by default (BACKUPS) |
| App page | version, compat, developer, releases, screenshots, related | All of these | Plus licence, tier, last scan date and result, permissions, resources, archs, upstream health, verified restore |
| Manifest | permissive YAML, validation off | Simple author format | One validator shared by CI and box; semver version; `x-` extensions only via schema |
| Dependencies | `dependencies` + `implements` alternatives | Same model | Alternatives resolved into the signed plan; dependants shown before remove |
| Credentials | default or derived password shown | Same convenience | Generated secrets write-only, shown to owner on demand, never to agents or logs |
| Offline store | falls back to local registry | Same | Catalog is signed and cached; installs work from cache with a fresh scan record |

---

## 4. OneMind design for app deployment

### 4.1 Components and licences

All are our own code or separately shipped components; versions are those pinned in `os/versions.lock.yaml` (on `feat/app-pipeline`) or in the cited design, re-read at adoption.

| Component | Role | Licence | Pinned version |
|---|---|---|---|
| Gateway (`core/onemind_core`, Python/FastAPI) | catalog, plan, actions, approvals, audit, forward-auth | OneMind (Apache-2.0 headers) | repo |
| `onemind-edge` (Go) | TLS + routing for `onemind.local` names, forward-auth calls | OneMind | repo (NETWORKING §9.2) |
| `golang.org/x/crypto` (autocert, x509 helpers) | edge certificates | BSD-3-Clause | v0.58.0 (`go.sum`) |
| k3s | runtime for apps | Apache-2.0 | v1.37.2+k3s1 |
| kubectl, kustomize | render and apply checked bytes | Apache-2.0 | v1.37.2, v5.8.3 |
| kubeconform | manifest validation in gate and box | Apache-2.0 | v0.8.0 |
| Trivy | CVE + secret scan, SBOM input | Apache-2.0 | 0.76.2 |
| ClamAV | malware scan; separate process in its own image | GPL-2.0 (separately shipped, never linked) | image pinned by digest at adoption |
| cosign | upstream signature check; catalog signing | Apache-2.0 | v3.1.4 |
| crane (go-containerregistry) | digests, arch lists | Apache-2.0 | v0.22.1 |
| k3d | CI smoke cluster | MIT | v5.9.0 |
| avahi | mDNS `<app>.onemind.local` | LGPL-2.1 (Debian package, unmodified) | Debian snapshot `20261111T000000Z` |
| restic | pre-update app snapshot (BACKUPS) | BSD-2-Clause | pinned by the backups stream |
| Renovate | digest-bump PRs in CI only, not shipped | AGPL-3.0 (service use only) | `renovate.json` |
| NATS server | events `onemind.event.v1` for app state | Apache-2.0 | v2.15.3 (`go.mod`) |

### 4.2 Manifest (author format) — additions to `onemind.app.yaml`

Builds on contract §4, §9.3, §11.2 and draft §12.13; schema changes ship only with the matching contract PR (hotspot rule).

```yaml
apiVersion: onemind.app/v1alpha1
kind: App
metadata:
  id: immich-like                  # ≤ 59 chars
  version: "3.4.1"                 # semver (gate normalises, refuses non-semver)
  tagline: Photo and video backup   # ≤ 60 chars, our own words
  category: photos                  # enum (taxonomy stream)
  tags: [media]                     # ≤ 2
  developer: {name: Example Org, url: https://example.org}
  gallery: [shots/1.webp, shots/2.webp]      # files in apps/<id>/, never hot-linked
  releases_url: https://github.com/owner/repo/releases   # notes pulled by app-scaffold into release_notes
  related: [another-app]            # optional; catalog also derives by category/tag
spec:
  os: {min: "0.3.0"}                # OneMind release needed (compat gate)
  web: {port: 2283, path: /, websocket: true, auth: gateway}   # auth: gateway | app (app does its own login)
  dependencies:
    - {id: postgres, alternatives: [postgres, cnpg-postgres]}
  provides: [photos-library]        # what it can stand in for (umbrel "implements")
  permissions:                      # what the plan card shows; each is checked by the rule file
    gpu: optional                   # none | optional | required
    folders: [{id: library, name: Photo library, mode: ro|rw, default: /data/home/Photos}]
    host_ports: []                  # declared only when unavoidable (e.g. 53/udp), conflict-checked
    egress: internet                # internet | none | ["<cidr>"]  (SANDBOX spec.network.egress)
  credentials: {username: admin, password: generated, show_before_open: true}
  health: {http: {port: 2283, path: /api/server/ping, expect: 200}, deadline_s: 600}
  backup: {mode: hot, exclude: [cache/**]}
  updates: {channel: stable, automerge: patch}
```

Rules: no shell hooks on the host, ever; lifecycle steps are `exec` argv in a named container (draft §12.13). `metadata.tier`, `scan`, `install_size_bytes` and `archs` are computed by `app-gate`, never hand-set.

### 4.3 Data model (gateway database)

| Record | Key fields |
|---|---|
| `catalog_source` | `id`, `url`, `pinned_commit`, `signing_key` (cosign public key or `none`), `kind: official|community`, `added_by`, `added_at` |
| `catalog_app` | `source_id`, `app_id`, `version`, `manifest_sha256`, `rendered_sha256`, `tier`, `scan` (§11.1), `release_notes[≤5]`, `install_size_bytes`, `os_min`, `related[]` |
| `installed_app` | `app_id`, `source_id`, `version`, `plan_sha256`, `digests[]`, `state` (parity vocabulary: `installing`, `running`, `stopped`, `updating`, `reverting`, `failed`, `degraded`, `stale`, `unknown`, `removing`, `removed_data_kept`), `progress {step, pct}`, `settings{}`, `dependency_choice{}`, `folder_grants[]`, `exposure: private|remote|public`, `installed_by`, `approved_by` |
| `app_revision` | `app_id`, `rev`, `version`, `plan_sha256`, `digests[]`, `snapshot_id`, `outcome`, `created_at` (for revert and history) |
| `route` | `app_id`, `hostnames[]`, `upstream: Service/port`, `auth: gateway|app`, `websocket`, written to `/run/onemind/edge/routes.json` |

### 4.4 API, CLI and MCP surface (contract style)

All writes are actions (contract §3, draft §12.2); reads are plain GETs. New action types and routes enter through contract PRs only.

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/apps?source=&category=&q=` | any principal | catalog entries (existing) plus `tagline`, `developer`, `os_min`, `compatible`, `install_size_bytes`, `permissions` summary |
| `GET /v1/apps/{id}` | any principal | full page: description, gallery URLs (served by the gateway), `release_notes`, `related`, `scan`, `licence`, `links`, `installed` block |
| `GET /v1/apps/{id}/plan?node_id=` | owner, adult, agent | plan: objects by kind, images + digests, PVCs, folders, GPU, host ports, egress, deps resolved, node fit and why-not, `plan_sha256` (SANDBOX-2) |
| `GET /v1/apps/{id}/revisions` | owner, adult | `app_revision` list |
| `GET /v1/apps/{id}/logs?tail=&follow=` | owner, adult | redacted container logs |
| `GET /v1/sources` | any principal | catalog sources with pinned commit |
| `POST /v1/actions` types | owner request or agent request; owner approves | `app.install`, `app.remove` (keeps data), `app.start`, `app.stop`, `app.restart`, `app.update`, `app.revert {to_rev}`, `app.configure {diff}`, `app.delete_data` (owner only, typed confirm, never agent-requestable), `app.expose {level}` (critical, owner only), `source.add`, `source.move {to_commit}`, `source.remove` (owner only) |

CLI (`cmd/onemind/cli/app.go`, `source.go`): `onemind app ls|info|plan|install|update|revert|start|stop|logs|remove [--delete-data]`, `onemind source ls|add|move|rm`. Each write prints the action id and `awaiting_approval`, as in DEPLOYMENTS §3.1.

MCP (extends §11.3, DEV-MCP-3): read tools `list_apps`, `get_app`, `preview_action` (returns the plan); write tool `request_action` for `app.install|update|start|stop|restart|remove`. **Never requestable by agents:** `app.delete_data`, `app.expose`, `source.*`. No approve tool exists.

### 4.5 Flows

**Install:** request (owner tap or agent) → gateway resolves deps → renders kustomize → rule check → plan + `plan_sha256` → approval card → approve re-renders and compares hash → scan freshness check → create namespace with PSA label, NetworkPolicy, Secrets (generated credentials, agent token) → `kubectl apply -f -` checked bytes → wait for `spec.health` with progress events on NATS → write route → avahi name → `running`.

**Update:** catalog moves (signed) → `update available` with release notes → request `app.update` → new plan diffed against the current revision (widened permissions flagged) → approve → restic snapshot of the app's PVCs → apply → health probe within `deadline_s` → keep, or re-apply previous revision and restore the snapshot (`reverting` → `running` at old version, alert names the failing probe). Patch updates of verified apps may run under a standing approval (founder decision F-6).

**Remove:** stop workloads and delete non-data objects; PVCs (Retain class) and Secrets kept; state `removed_data_kept`; reinstall re-attaches. `app.delete_data` takes a final snapshot then deletes, owner only.

**Community source:** owner adds URL + commit (+ optional cosign key) → action `source.add` → box clones that commit read-only, validates every manifest with the shared validator, runs the on-box scan Job (DEPLOYMENTS §3.2) for apps on first install → apps appear with "From <source>" badge, tier at most `community`. Moving to a new commit is `source.move` with a diff of changed apps.

### 4.6 UI screens (in `ui/` design system, dashboard pages per WORKSTREAMS §3)

1. **Market** (Discover, categories, search, updates shelf) — every card shows tier and scan freshness.
2. **App page** — hero (icon, name, tagline, developer, Install/Open), gallery, facts band (version, OS compatibility, licence, size, archs, last scan), permissions block (folders, GPU, network, host ports, agent scopes), description, release notes (≤5), related apps, links (docs, source, support).
3. **Plan / approval card** — the exact plan with hash, requester label (person or agent), passkey approve.
4. **Installed app sheet** — state pill (honest vocabulary), progress steps, Open, logs, settings form (from `spec.settings`), credentials (owner reveal), revisions with revert, remove (keeps data) and a separate destructive delete.
5. **Sources** (Settings) — official + community sources with pinned commits and move/remove.
6. **App unavailable page** served by the edge — our own copy and artwork, true state from the gateway.

The public website (`site/**`) renders the same app page from the signed catalog, adding licence, scan and permissions (§3) that the public umbrelOS page lacks.

### 4.7 Security

- No store content executes on the host (fixes W1); lifecycle `exec` runs in the app's own container through the Kubernetes API.
- Rule file + PSA `restricted` + per-app RBAC + default-deny network (SANDBOX; fixes W2, W3).
- Catalog signed in CI (cosign) and verified on the box; community sources pinned and moved by approval (fixes W4).
- Nothing unscanned installs (§10.3); daily rescan blocks and alerts (fixes W5).
- One validator for CI and box; schema validation is mandatory (fixes W6).
- Approvals bound to `plan_sha256` and digests; widened permissions on update need re-approval.
- Agents request only; destructive and exposure actions are not agent-requestable (fixes W9).
- Name-constrained ECDSA box CA; edge never holds the CA key (fixes W10).
- Generated credentials are write-only Secrets, redacted from logs and never returned to agents.
- Every decision audited with requester and approver principal ids.

---

## 5. Deployment gaps and epics

Gaps cross-reference `PD-xx` in `docs/strategy/umbrel-parity.md` (uileap) and existing backlog epics; new epics use the `APPDEP-` prefix and stay inside owned paths from [WORKSTREAMS.md](../leap/WORKSTREAMS.md). Hotspot edits (contract, schema, `App.tsx`, `root.go`, `ledger.py`) go in their own small PRs.

| ID | Title | Size | Owner paths (stream) | Acceptance | Depends on |
|---|---|---|---|---|---|
| APPDEP-C1 | Contract PR: app lifecycle action types, `/v1/apps/{id}` detail, `/plan`, `/revisions`, `/logs`, `/v1/sources`, `source.*` types, never-requestable list | S | `sdk/contracts/poc-v0.md` (contract owner) | Merged before any APPDEP feature PR; every new route and type has an error table | C12-A |
| APPDEP-C2 | Schema PR: `tagline`, `category` enum, `tags`, `developer`, `gallery`, `related`, `spec.os.min`, `spec.dependencies[].alternatives`, `provides`, `permissions`, `credentials`, `web.auth`, `web.websocket` | S | `sdk/schema/onemind.app.schema.json` (hotspot, with APPDEP-C1) | All existing apps validate; a manifest with a non-semver version or unknown permission fails | W2-PIPE, PLAN-E6 |
| APPDEP-1 | Gate computes `install_size_bytes`, `archs`, release notes (≤5, from upstream releases), gallery checks (local files, size limits); `app-readme` renders them | M | `sdk/tools/{app-gate,app-scaffold,app-readme}` (W2-PIPE) | Gate on fixtures writes size, archs and notes into `scan.json`/catalog; hot-linked gallery URL rejected | APPDEP-C2 |
| APPDEP-2 | Signed catalog: CI builds `catalog.json` + cosign signature; gateway verifies before use and serves cached copy offline | M | `.github/workflows/ci-apps.yml` (W2-PIPE), `core/onemind_core/catalog.py` (gateway core) | Tampered catalog refused with audit `catalog.signature_invalid`; unplugged network still lists apps | W2-PIPE |
| APPDEP-3 | Plan endpoint + dependency resolution with alternatives and dependants check | M | `core/onemind_core/policy.py`, `executors.py` (install sandbox) | Plan lists deps, folders, GPU, host ports, egress; remove of a dependency → 409 naming dependants; plan hash changes when any input changes | CORE-SANDBOX-2, APPDEP-C1 |
| APPDEP-4 | Lifecycle actions start/stop/restart/configure with progress events (`{step, pct}`) on NATS `onemind.event.v1` | M | `core/onemind_core/{executors,events}.py` (install sandbox + gateway core) | Install shows ≥4 steps with monotonic pct; stop/start round trip on k3d; agent request appears as `awaiting_approval` | APPDEP-C1, CORE-SANDBOX-2 |
| APPDEP-5 | Remove keeps data; `app.delete_data` owner-only with typed confirm and final snapshot | S | `core/onemind_core/executors.py` (install sandbox) | After `app.remove`, PVC still Bound; reinstall reattaches data; agent `request_action app.delete_data` → 403 | APPDEP-C1, CORE-BACKUP-1 |
| APPDEP-6 | Health-gated update with snapshot and auto-revert; permission-widening re-approval | M | `core/onemind_core/app_updates.py` (updates) | Fixture with failing probe reverts to previous digests and restores data; alert names probe; widened egress → new approval | CORE-UPDATE-5, CORE-UPDATE-6, BACKUP-2 |
| APPDEP-7 | Edge routes per app with forward-auth, WebSocket, per-app auth mode, unavailable page | M | `internal/edge/**` (networking stream), `core/onemind_core/exposure.py` (dogfood) | `https://<app>.onemind.local` 302 to login when signed out, 200 when allowed, 403 for a guest without share; WS survives; page shows true state | NETWORKING Part 1 |
| APPDEP-8 | Name-constrained box CA and cert renewal; `onemind tls trust` | S | `internal/edge/**`, `cmd/onemind/cli/tls.go` (core branch) | Leaf for `example.com` signed by box CA rejected by Go verifier; renewal before 14 days | NETWORKING §9.4 |
| APPDEP-9 | Host ports and conflict check in plan; avahi names per app | S | `core/onemind_core/policy.py` (install sandbox), `internal/edge/**` | Two apps declaring 53/udp: second plan shows conflict and approve → 409; name published and removed with app | APPDEP-3 |
| APPDEP-10 | Community sources pinned to commit, `source.*` actions, on-box scan for first install | M | `core/onemind_core/{catalog,scanjob}.py` (deployments) | Adding a source needs approval; branch push upstream changes nothing on the box; app from source with failing scan cannot be approved | APPDEP-2, CORE-DEPLOY-2 |
| APPDEP-11 | Generated credentials (write-only Secret, owner reveal, redacted logs) | S | `core/onemind_core/deploys.py` secrets part (deployments) | `GET` never returns value except owner reveal route with passkey; agent 403; log scan finds no secret | CORE-DEPLOY-4, CORE-SEC-2 |
| APPDEP-12 | Logs endpoint, redacted | S | `core/onemind_core/routes.py` one line + `logs.py` (gateway core) | Owner/adult 200 with tail; guest/agent 403; known token patterns masked | APPDEP-C1 |
| APPDEP-13 | App page and Market polish: facts band, permissions, release notes, related apps, revisions, Sources settings | M | `dashboard/src/pages/{Market,AppDetail}.tsx`, `dashboard/src/components/**` (dashboard); visual parts from `ui/**` (design system) | Page shows licence, tier, scan date, size, archs, permissions, notes, related; Install disabled with reason when incompatible or scan stale | APPDEP-1, APPDEP-3 |
| APPDEP-14 | CLI `onemind app` and `onemind source` groups | M | `cmd/onemind/cli/{app,source}.go` (CLI) | Each write prints action id; `onemind app plan` matches REST plan hash | APPDEP-C1, DEV-CLI-1 |
| APPDEP-15 | MCP: `get_app`, `preview_action`, never-requestable list enforced | S | `core/onemind_core/mcp/**` (MCP) | No MCP path to approve, delete data, expose or change sources; plan in `request_action` result | DEV-MCP-3, APPDEP-C1 |
| APPDEP-16 | Public app pages on the website from the signed catalog | S | `site/**` (website) | Each catalog app has a page with version, compatibility, developer, licence, scan, permissions, notes, related | APPDEP-2 |
| APPDEP-17 | Image cleanup on nodes after update/remove (k3s image GC thresholds + explicit prune of old digests) | S | `internal/agent/**` (fabric/onemindd owner) | After update, old digest absent within one cycle; running digests never removed | APPDEP-6 |

**Gaps intentionally not taken:** VMs ("Machines"), Tor exposure, native TLS passthrough (P2, revisit when an app needs it), movable data root per app (handled by storage classes and the storage stream).

### Acceptance for the area (end to end)

On a fresh k3d box: an agent requests a verified app; the plan card shows deps, folders, egress and scan; the owner approves by passkey; the app opens at `https://<app>.onemind.local` behind sign-in with progress shown throughout; a patch update with a broken probe reverts by itself and the data is intact; remove keeps the PVC; a community source added at a pinned commit installs only after an on-box scan; at no point does any store content run on the host.
