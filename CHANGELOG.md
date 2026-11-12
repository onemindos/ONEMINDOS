<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

A plain-language record of everything added to this repo, newest first.

**Every merge adds an entry here.** The PR that merges writes its own entry under "Unreleased / in progress"; the person merging moves it under its merge date with the PR number and link. Dates are the UTC merge dates GitHub shows. Live state of planned work is in [`docs/leap/STATUS.md`](docs/leap/STATUS.md).

## Unreleased / in progress

Branches with work that is not on `main` yet (as of 2026-11-12). The five open PRs are stacked: merge #40, #41, #44, #48, then #54.

| Branch | PR | What it adds |
|---|---|---|
| `feat/sec-p0` | [#40](https://github.com/onemindos/ONEMINDOS/pull/40) | Security P0: the install sandbox (one rule file `sdk/policy/app-objects.yaml`; the gateway renders, checks every object and applies exactly what it checked; app namespaces `restricted`; default-deny network per app; 28 malicious fixtures refused), the gateway without cluster-wide Kubernetes rights (admission policy, 24-hour token), k3s Secrets encryption and Pod Security defaults, request limits, the pending-request cap, security headers, and `onemindd` on loopback. Record: [`docs/leap/core/SECURITY.md`](docs/leap/core/SECURITY.md) §7a |
| `feat/identity` | [#41](https://github.com/onemindos/ONEMINDOS/pull/41) | Household identity (contract §12.6): owner, adult, guest and child accounts; first owner from the install token; password + TOTP or passkey sign-in; cookie sessions with CSRF and CLI bearer sessions; passkey step-up on owner approvals; scoped `om_` API tokens with expiry, rotation and revocation; per-app sharing; `GET /v1/me`; every decision audited. Guide: [`docs/leap/core/IDENTITY.md`](docs/leap/core/IDENTITY.md) |
| `feat/notify-monitor` | [#44](https://github.com/onemindos/ONEMINDOS/pull/44) | Notifications and monitoring (contract §12.14, §12.15): an event catalogue fed by events, the action ledger and node outbox events; alerts with dedupe, re-notify, escalation and flap marking; an inbox API; ntfy/UnifiedPush, webhook, e-mail and Web Push (per-box VAPID keys, encrypted, ids only) with per-person routes, quiet hours, digest and rate caps; app health, restarts, crash loops, redacted logs, app and node metrics with threshold alerts; the heartbeat reports CPU, load and temperature |
| `feat/devsurface` | [#48](https://github.com/onemindos/ONEMINDOS/pull/48) | The developer surface: stable operation ids and the committed OpenAPI spec, the audit read API and the live events stream (§12.8, §12.16), the MCP catalogue v1, generated TypeScript, Python and Go SDKs with one conformance suite, and the `onemind` CLI on cobra with an `onemind mcp` stdio bridge |
| `feat/e2e-golden-path` | [#54](https://github.com/onemindos/ONEMINDOS/pull/54) | The golden-path end-to-end suite on a real hub: `install.sh` in a Debian 13 VM (Lima or QEMU), the dashboard and an MCP agent driven by Playwright, the audit chain re-verified, `verify.sh`; on PRs and nightly |

## 2026-11-12

### [#50](https://github.com/onemindos/ONEMINDOS/pull/50) Learning lessons 07–16
- `docs/learning/` gains ten lessons for the founder on what the first build week made and why: the image and A/B updates with the health gate, the security pipeline and TUF, the gateway and MCP, the app pipeline and scan gate, the mesh, backups, identity, notifications, the design system, and the testing strategy. Each has diagrams, links to the code on `main`, try-it steps and self-check questions.
- Work that is only designed, or only in an open PR, is labelled as such.

### [#45](https://github.com/onemindos/ONEMINDOS/pull/45) Next wave plan and merge ownership
- `docs/leap/` names one owner for every unmerged branch and what it waits for, and plans wave G in order: image integration, a full CI run, security re-review, a second slop pass, a parity re-score, clients, the Market, the fabric and alpha readiness.
- Founder blockers listed: F-25, F-27, F-7 and F-5.

### [#39](https://github.com/onemindos/ONEMINDOS/pull/39) Contract §12: the phase-B interfaces become binding
- `sdk/contracts/poc-v0.md` §12 now fixes the names and shapes for conventions and errors, risk classes and approvals, the action-type registry, identity, HTTPS, the events stream, NATS, heartbeat objects, fabric, backups, OS updates, notifications, monitoring, audit, automation, deployments, MCP additions and the CLI.
- Where the draft and the leap specs disagreed, the API.md names win. Docs only.

### [#38](https://github.com/onemindos/ONEMINDOS/pull/38) Core plumbing: one-line feature registration
- The gateway's routes move into `core/onemind_core/routers/` with one `ROUTERS` registry; features get their own tables with numbered upgrade steps, typed settings sections, and `publish_event` (audit log, NATS `onemind.event.<domain>.<name>` and in-process listeners).
- `onemind` commands move to one file per group in `cmd/onemind/cli/`, and `onemindd` gains a registry for optional services so one failing service never stops the heartbeat.
- No behaviour change: `/openapi.json`, the route table and the CLI output are identical. Guide: `docs/leap/core/PLUMBING.md`.

### [#37](https://github.com/onemindos/ONEMINDOS/pull/37) Mesh networking, part 1
- Lab FB-3 passed 6 of 6: two homes behind separate NATs joined with one-time keys and no open ports, fell back to our own relay within 10 s when UDP was blocked, and kept every NATS event in order through a 30-minute hub outage.
- New modules, not wired in yet (that is part 2): `internal/mesh` (Headscale enrolment and state), the NATS leaf over the mesh, a gateway mesh client, the app reverse proxy and the per-box CA. Design: `docs/architecture/NETWORKING.md`.

### [#36](https://github.com/onemindos/ONEMINDOS/pull/36) OneMind logo
- `brand/` holds the founder's logo in four variants (colour, on-dark, white, black) as SVG and PNG at seven sizes, all with transparent backgrounds, and a README on colours, where each variant goes and the trademark note.

### [#34](https://github.com/onemindos/ONEMINDOS/pull/34) Phone photo backup
- `mobile/` backs up photos in the background, resumes instead of restarting, skips duplicates by hash, and can wait for Wi-Fi or charging. A photo counts only after the box confirms its bytes, and the phone frees space only for photos in a verified backup.
- Tested against a mock server (65 tests); the box side of the protocol (`mobile/docs/photos-backup-api.md`) is still to build.

### [#33](https://github.com/onemindos/ONEMINDOS/pull/33) Desktop client for Mac and Windows
- `desktop/` (Tauri 2) is a tray app that finds boxes by mDNS or URL, pairs with a token kept in the OS keychain, shows nodes, approvals, updates and backups, opens the dashboard and raises native approval notifications.
- CI builds it for macOS and Windows.

### [#32](https://github.com/onemindos/ONEMINDOS/pull/32) Backup agent
- `internal/backup` runs restic (checksum verified) hourly into encrypted repositories, keeps 24 hourly, 7 daily, 4 weekly and 12 monthly copies, and writes to USB, another box over the mesh (append-only) or S3.
- Rewind browses and restores single files, and an automatic restore test into a scratch folder sets the "last verified restore" badge. Not wired into `onemindd` yet.

### [#31](https://github.com/onemindos/ONEMINDOS/pull/31) Storage health, first slice
- `internal/storage` and `onemind storage` list the disks and their roles, read SMART health, temperature and wear, show the btrfs mirror state, and print dry-run plans to create, grow, replace or shrink a mirror.
- Nothing that changes a disk runs yet; those become approval-gated actions. A VM lab built a real mirror, pulled a disk and resynced.

### [#30](https://github.com/onemindos/ONEMINDOS/pull/30) umbrelOS 2 study
- `docs/umbrel2/` studies umbrelOS 2 in ten areas (desktop, clients, photos, virtual machines, agents, accounts, storage, files and backups, apps, updates): how it works, what we have, how we beat it, and the epics. We read and described it and copied no code, text or assets (PolyForm Noncommercial).
- Adds the UMB epics to the backlog and status, and new founder questions to DECISIONS-NEEDED.

### [#29](https://github.com/onemindos/ONEMINDOS/pull/29) UI leap
- `ui/` (`@onemind/ui`) gains customization (themes, accents, wallpapers, density, font size), a Home launcher with a widget grid and dock, an App Store and app manager with live install progress, a command palette, a notification centre, a first-run wizard and the Settings screens.
- `docs/strategy/umbrel-parity.md` compares umbrelOS screen by screen (patterns only) and ranks the gaps; a design critique fixed 18 of 26 defects. The live dashboard moves onto it next.

### [#28](https://github.com/onemindos/ONEMINDOS/pull/28) App and deployment taxonomy
- `docs/design/TAXONOMY.md` defines 16 Market categories (mapped from every competitor store), the deployment classes (core, verified, community, list-only, private, plugin) and the placement facets (hub or worker, archs, GPU, radios, storage, exposure, update channel).
- `apps/_intake/candidates.csv` gains those columns, generated by a committed script.

### [#26](https://github.com/onemindos/ONEMINDOS/pull/26) Developer install, compose hub and verify kit
- `deploy/install.sh --role hub|node` puts k3s (pinned), NATS, the gateway, the dashboard and `onemindd` on stock Debian 13, Raspberry Pi OS, Jetson L4T or a droplet; labelled an unsupported developer install with no OS rollback.
- `deploy/compose/` runs a dev hub on a Mac, and `deploy/verify/verify.sh` checks a hub against the contract. Review fixed a verify script that could run code from a malicious hub.

### [#25](https://github.com/onemindos/ONEMINDOS/pull/25) App pipeline and the wave-2 apps
- `sdk/tools/app-scaffold`, `app-gate` (licence, pins, Trivy, ClamAV, secrets, cosign, kubeconform and a k3d smoke test, writing `scan.json`) and `app-readme`; CI gates changed apps, rescans daily and Renovate pins digests.
- Gate results: ntfy, Vaultwarden, Actual Budget and Zigbee2MQTT verified; the Hermes agent, Uptime Kuma, Home Assistant and Node-RED blocked until upstream fixes critical CVEs in their latest images; Mosquitto unblocked after a licence false match.

### [#24](https://github.com/onemindos/ONEMINDOS/pull/24) Gateway wave 2: scan gate, agent principals and MCP
- Approving an install now needs a passing, recent `scan.json`; apps can have their own agent principal (token stored hashed, revoked on remove); `POST /mcp` gives agents `list_nodes`, `list_apps` and `request_action`, and no approve tool.
- The dashboard shows links, licence, tier and last scan, and gains an app page.

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
