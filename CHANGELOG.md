<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

A plain-language record of everything added to this repo, newest first.

**Every merge adds an entry here.** The PR that merges writes its own entry under "Unreleased / in progress"; the person merging moves it under its merge date with the PR number and link. Dates are the UTC merge dates GitHub shows. Live state of planned work is in [`docs/leap/STATUS.md`](docs/leap/STATUS.md).

## Unreleased / in progress

Branches with work that is not on `main` yet (as of 2026-11-12):

| Branch | PR | What it adds |
|---|---|---|
| `feat/desktop-v1` | [#51](https://github.com/onemindos/ONEMINDOS/pull/51) | Desktop app v1 (Tauri, `desktop/`, on top of #33): an approval card with risk, reason and plan, approved only with the plan hash it showed; passkey approvals (destructive, or an owner with a passkey) finish in the browser on the box's page; native banners and a Notifications view from the inbox (§12.14); live updates from `/v1/events` (§12.8); fixes to #33 (the contract's `/v1/os/status` route, server-side pending filter, HTTPS :8443 discovery, token copy checked against `ui/`); name, logo, icons and accent from `brand/brand.json` (#52) through `scripts/brand-sync.py`. Designs, not built: WebDAV mount (`desktop/docs/FILES.md`, waits on UMB-FILES-5) and update channels with our signing (`desktop/docs/UPDATER.md`, updater off until F-59 and the new F-61) |
| `docs/learning-what-we-built` | – | Learning lessons 07–16 for the founder: what was built this week and why (image and A/B updates with the health gate, security pipeline and TUF, gateway approvals, agents and MCP, app pipeline and scan gate, mesh and the FB-3 lab, backups, identity and passkeys, notifications, design system and dashboard, testing), each with diagrams, links to the code and "try it" steps checked against `main`, plus an index at `docs/learning/README.md` |
| `feat/core-plumbing` | – | Core plumbing so streams add features without editing the same lines (no behaviour change; OpenAPI and CLI output identical): gateway routes split into `core/onemind_core/routers/` with one registry in `app.py`; per-feature tables and versioned upgrade steps (`store.py`); per-feature `ONEMIND_<FEATURE>_*` settings sections; `publish_event` (audit log + NATS `onemind.event.<type>` + in-process subscribers); `onemind` commands in `cmd/onemind/cli/<group>.go`; `onemindd` subcommand and optional-service registry (`internal/service`). Guide: [`docs/leap/core/PLUMBING.md`](docs/leap/core/PLUMBING.md) |
| `feat/sec-p0` | – | Security P0: the install sandbox (one rule file `sdk/policy/app-objects.yaml`; the gateway renders, checks every object and applies exactly what it checked; app namespaces `restricted`; default-deny network per app; 28 malicious fixtures refused), the gateway without cluster-wide Kubernetes rights (admission policy, 24-hour token), k3s Secrets encryption and Pod Security defaults, request limits, the pending-request cap, security headers, and `onemindd` on loopback. Record: [`docs/leap/core/SECURITY.md`](docs/leap/core/SECURITY.md) §7a |
| `feat/identity` | – | Household identity (contract §12.6): owner, adult, guest and child accounts; first owner from the install token; password + TOTP or passkey sign-in; cookie sessions with CSRF and CLI bearer sessions; passkey step-up on owner approvals; scoped `om_` API tokens with expiry, rotation and revocation; per-app sharing; `GET /v1/me`; every decision audited. Guide: [`docs/leap/core/IDENTITY.md`](docs/leap/core/IDENTITY.md) |
| `feat/gateway-agent-mcp` | – | Gateway wave 2 (contract §11): scan gate, app agent principals, `/mcp` with 3 tools, new catalog fields, and the dashboard app page with links, licence, tier and last scan |
| `feat/app-pipeline` | – | App pipeline: manifest fields (§9.3, §11.2), `app-gate` (§9.4 checks, `scan.json`), `app-scaffold`, a full gate with a k3d smoke test in CI, Renovate, a daily rescan, and the wave-2 apps (Hermes, Node-RED, Mosquitto, Vaultwarden, Actual Budget, Zigbee2MQTT) |
| `feat/deploy-v0` | – | Developer install on Debian (`install.sh --role hub` or `node`), a compose dev hub for a Mac and `verify.sh` contract checks |
| `feat/core-net` | – | Internal networking and mesh: a WireGuard mesh with a self-hosted Headscale coordinator and relay, NATS leaf links with TLS and per-node credentials, the app reverse proxy with login, a per-box CA, and the NAT lab test |
| `feat/ui-leap` | – | UI leap: umbrelOS parity audit, customization (themes, accents, wallpapers, density), Home with widgets and dock, App Store with install progress and app management, command palette, notifications, onboarding, and Settings |
| `feat/notify-monitor` | – | Notifications and monitoring (contract §12.14, §12.15): an event catalogue fed by events, the action ledger and node outbox events; alerts with dedupe, re-notify, escalation and flap marking; an inbox API; ntfy/UnifiedPush, webhook, e-mail and Web Push (per-box VAPID keys, encrypted, ids only) with per-person routes, quiet hours, digest and rate caps; app health, restarts, crash loops, redacted logs, app and node metrics with threshold alerts; the heartbeat reports CPU, load and temperature |
| `feat/app-taxonomy` | – | App and deployment categories (`docs/design/TAXONOMY.md`), applied to the candidate list |
| `feat/market-batch-2-3` | [#49](https://github.com/onemindos/ONEMINDOS/pull/49) | Market batches 2 and 3: 17 apps (Memos, Jellyfin, FreshRSS, Audiobookshelf, Calibre-Web, Ghost with MySQL, PhotoPrism with MariaDB, OpenClaw, Trilium, Karakeep with Meilisearch, Navidrome, Sonarr, Radarr, ESPHome, code-server, HomeBox, Prowlarr), all non-root with probes, limits and volumes, tier `community` until CI scans them. Stirling-PDF, Docmost and Duplicati are queued as licence-blocked: their images ship code under licences that forbid redistribution |

## 2026-11-12

### [#22](https://github.com/onemindos/ONEMINDOS/pull/22) Market candidate list from competitor stores
- `apps/_intake/candidates.csv` and `CANDIDATES.md`: 1,199 unique upstream apps drawn from 7 competitor stores (umbrel, Olares, CasaOS, Runtipi, YunoHost, Cosmos, Coolify), facts only. Each app's licence, stars, archived flag and latest release were checked on GitHub.
- Tiers: 849 ready to queue, 59 list-only, 73 parked (crypto), 218 excluded. It also proposes the first 5 batches of 10, starting with daily essentials: Nextcloud, Immich, Syncthing, Paperless-ngx, Gitea, Grafana, Ollama, LibreChat, SearXNG and AdGuard Home.

### [#21](https://github.com/onemindos/ONEMINDOS/pull/21) Android and iPhone app shells
- `mobile/` (Expo, React Native) adds these screens: Connect (token in the Keychain or Keystore), Home, Nodes, Apps, Approvals (approve or deny) and Activity, plus local notifications and a mock mode. 37 tests pass. It builds and runs on the iOS simulator, and builds an Android debug APK.
- Also allow-lists the npm author address that appears in lock files (hygiene B-FP-5).

### [#20](https://github.com/onemindos/ONEMINDOS/pull/20) Design system `@onemind/ui`
- `docs/design/` adds principles, information architecture, tokens, components and the plugin UI extension points.
- `ui/` adds the React component library (tokens, light and dark themes, accessible components), a dashboard shell and demo screens. 73 tests pass, including WCAG AA contrast checks.

### [#19](https://github.com/onemindos/ONEMINDOS/pull/19) Website
- `site/` (Astro and Starlight) adds an install-first landing page, docs, a blog, an apps catalog with trust cards built from `apps/`, and a community page.
- Also adds research on competitor websites and a forum plan (GitHub Discussions now, Discourse later). There is no deploy step yet, because hosting is a founder decision.

### [#18](https://github.com/onemindos/ONEMINDOS/pull/18) Security threat model
- `docs/security/` adds a STRIDE threat model for every core component with file:line evidence, and a ranked hardening backlog (H-01 to H-30).

### [#17](https://github.com/onemindos/ONEMINDOS/pull/17) Core competitor alignment and architecture
- `docs/strategy/core-alignment.md` compares OneMind with 11 competitors across 14 core areas: what we must match, where we can beat them, and a ranked backlog.
- `docs/architecture/` adds the fabric, backups, deployments, automation and notifications designs, plus a draft of contract §12.

### [#16](https://github.com/onemindos/ONEMINDOS/pull/16) The leap plan and this changelog
- `docs/leap/` adds the API, SDK, CLI, MCP and plugin SDK specs, the core epic specs, workstreams, a 182-epic backlog, a status tracker and the decisions still needed.
- Also adds this `CHANGELOG.md`.

### [#14](https://github.com/onemindos/ONEMINDOS/pull/14) OS security pipeline (contract §10.1, CI side)
- A nightly job checks the image's packages against Debian's security tracker and, when fixes exist, rebuilds every board from a newer pinned Debian snapshot.
- Each build is scanned (SBOM with syft, Trivy with a VEX file from the Debian tracker, ClamAV) and must pass the QEMU boot battery; any failure blocks publishing.
- Bundles are signed with RAUC and listed in a TUF channel that a TUF client verifies before anything leaves the job. Publishing stays off until the real signing keys and the offline TUF root exist; until then it runs with throwaway keys and keeps artifacts only. Interface: `os/update/CHANNEL.md`.
- Fix: the image build now runs `apt-get upgrade` inside the pinned snapshot, so packages from the Debian base image get their security fixes (zlib had 3 open CVEs).

### [#15](https://github.com/onemindos/ONEMINDOS/pull/15) onemindd OS updater (contract §10.1, box side)
- `onemindd` can now update the OS by itself. It reads `/etc/onemind/update.conf` (channel, URL, maintenance window, policy) and checks the update channel with TUF, always trusting only the root shipped in the image.
- It picks only newer versions that match the board; downgrades are refused. Security updates install automatically inside the window; stable updates only notify.
- Before installing it takes a restic snapshot of `/data`, then runs `rauc install` and reboots; the health gate keeps or rolls back the update.
- Adds an optional `update` object to the heartbeat, the `onemind update status|check|apply` commands and a systemd unit.

### [#12](https://github.com/onemindos/ONEMINDOS/pull/12) Contract §11: wave-2 interfaces
- Defines the `apps/<id>/scan.json` scan record and the rule "nothing unscanned installs".
- Adds `spec.agent` so an app can be an agent principal (it can request, never approve), the `/mcp` tools, new `/v1/apps` fields, and the `app-<id>` namespace rule. Docs only.

### [#13](https://github.com/onemindos/ONEMINDOS/pull/13) CI back to green
- Every GitHub Action is pinned to the commit recorded in `os/versions.lock.yaml` (five were missing), and the wave-1 workflows gained SPDX licence headers.

### [#11](https://github.com/onemindos/ONEMINDOS/pull/11) App manifest schema, validator and the first three apps
- `sdk/schema/onemind.app.schema.json`: the JSON Schema for `onemind.app.yaml`.
- `sdk/tools/validate-apps`: checks the schema, ids, icons, a `kustomize build` passed to `kubeconform`, digest-pinned images, resource requests and limits, and that each web Service points at its pod.
- CI for apps with gitleaks, and the first seed apps: Uptime Kuma, ntfy and Home Assistant, each pinned by digest with a README citing upstream docs. Smoke-tested on k3s.

### [#10](https://github.com/onemindos/ONEMINDOS/pull/10) OneMind OS image build, first milestones (BM0/BM1)
- The repo skeleton for the OS (`os/`, `test/`, `lab-kits/`, Makefile) and an image built on Debian 13 from a pinned snapshot.
- RAUC A/B updates built from a pinned commit, the health gate with version matching and clear verdicts, and an assembler for x86_64 EFI, arm64 EFI, a VM and a DigitalOcean-compatible VM (BIOS boot).
- The QEMU test battery with criteria written before the runs, a hygiene gate, CI workflows, and lab kits for x86, Pi 5, Jetson and DigitalOcean. Battery passed on x86_64 EFI and the DigitalOcean VM; first tests passed on arm64.

### [#8](https://github.com/onemindos/ONEMINDOS/pull/8) Dashboard MVP
- A React and TypeScript dashboard with token sign-in and four screens: Home (instance, machine counts, installed apps), Nodes (one card per machine, honest stale and offline labels), Market (install and remove create actions) and Approvals.

### [#7](https://github.com/onemindos/ONEMINDOS/pull/7) onemindd node agent and the `onemind` CLI
- `onemindd` detects the board, OS, CPU, memory, disk, TPM, Secure Boot, k3s, RAUC and NVIDIA GPU, and publishes a heartbeat to NATS every 10 seconds. The node id is a hash, with no serials, MACs or IPs.
- A local API on the node, the `onemind node info` and `onemind nodes` commands, static builds for amd64 and arm64, and a locked-down systemd unit.

### [#9](https://github.com/onemindos/ONEMINDOS/pull/9) Gateway v0 (contract §3)
- The OneMind Core gateway in Python and FastAPI. Owners and agents can request actions; **only a person with the owner role can approve or deny**, and an agent's attempt gets 403 and is recorded.
- An action ledger with idempotency and expiry, a node registry fed by NATS heartbeats, the app catalog, `noop` and Kubernetes executors that run only after approval, and a hash-chained audit log with a verify tool.
- Serves the dashboard and `/openapi.json`; a multi-arch container image; tests on SQLite and on PostgreSQL with NATS.

### [#6](https://github.com/onemindos/ONEMINDOS/pull/6) Contract §9–§10: adding apps at scale and automatic updates
- An app intake queue, a scaffolder that builds apps from upstream sources, manifest links, and a CI gate with licence, digest, CVE, malware (ClamAV), secrets, signature and smoke checks.
- The update policy: nightly OS security rebuilds that are scanned, tested and signed before boxes install them with health-gated rollback; app updates by Renovate with re-scans.

### [#5](https://github.com/onemindos/ONEMINDOS/pull/5) Contract §7–§8: Hermes as the first app, and wave-2 seed apps
- Hermes packaged as `apps/hermes-agent`: an agent principal that can request actions but never approve them, reaching the gateway through a minimal MCP endpoint. Five more seed apps planned for wave 2.

### [#4](https://github.com/onemindos/ONEMINDOS/pull/4) Hardware bring-up plan
- Lesson 06 maps the founder's hardware (an x86 mini PC, DigitalOcean, Pi 5, Jetson) to the build boards and lab kits, in order.
- Build-brief item BD-DO-1: a BIOS-booting `vm-do` image so OneMind can run as a DigitalOcean droplet.

### [#1](https://github.com/onemindos/ONEMINDOS/pull/1) Research: OneMind OS foundation and 10-year plan
- The full research output in `research-output/`: the foundation decision, workstream reports, the 180-day plan, the 5–10-year roadmap, the hardware lab plan, risk register, traceability, founder questions, the next build brief, about 2,986 sourced claims and a 111-page founder report.

## 2026-11-11

### [#3](https://github.com/onemindos/ONEMINDOS/pull/3) Research mission 02: the One Mind fabric
- The brief for the next research run: how every kind of machine joins one OneMind, with phones as clients. Also removed a local folder path from a research note.

### [#2](https://github.com/onemindos/ONEMINDOS/pull/2) Learning lessons 03–05
- Plain-language notes on Debian vs Ubuntu as the base, install modes and running OneMind in the cloud, and the official route.

## 2026-11-10 (before pull requests)

Direct commits that started the repo:
- The research repo itself: requirements, the decision log, ADR-001, the context pack and research mission 01.
- A second brief (kernel and image ownership, the Mac development path, the ecosystem, physical AI, the build brief) and its kickoff prompt.
- The move to the `onemindos` GitHub organisation.
- Research priorities for IoT and IIoT, Fedora IoT and the Red Hat edge lineage, VillageOS, one OS from Pi to enterprise, and kernel families.
- The plugin ecosystem made a founder priority: plugin types, extension points and a study of proven ecosystems.
