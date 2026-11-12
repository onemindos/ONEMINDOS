<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

A plain-language record of everything added to this repo, newest first.

**Every merge adds an entry here.** The PR that merges writes its own entry under "Unreleased / in progress"; the person merging moves it under its merge date with the PR number and link. Dates are the UTC merge dates GitHub shows. Live state of planned work is in [`docs/leap/STATUS.md`](docs/leap/STATUS.md).

## Unreleased / in progress

Branches with work that is not on `main` yet (as of 2026-11-12):

| Branch | PR | What it adds |
|---|---|---|
| `feat/os-security-pipeline` | [#14](https://github.com/onemindos/ONEMINDOS/pull/14) (open) | Nightly OS security pipeline: checks Debian's security tracker, rebuilds from a pinned snapshot, scans (SBOM, Trivy with VEX, ClamAV), runs the QEMU battery, signs RAUC bundles and TUF metadata. Publishing stays off until the signing keys and the offline root exist. Also upgrades base-image packages inside the pinned snapshot |
| `docs/leap` | – | The leap: specs for the core OS (sandbox, security, fabric, backups, deployments, automation, notifications, updates, dashboard, mobile, website, dogfood) and the developer surface (API, SDKs, CLI, MCP, plugin SDK), plus workstreams, one ordered backlog, a status tracker, open decisions, and this changelog |
| `feat/gateway-agent-mcp` | – | Gateway wave 2 (contract §11): scan gate, app agent principals, `/mcp` with 3 tools, new catalog fields, and the dashboard app page with links, licence, tier and last scan |
| `feat/app-pipeline` | – | App pipeline: manifest schema fields (§9.3, §11.2), `app-gate` (§9.4 checks, `scan.json`), `app-scaffold` with recorded fixtures, `app-readme`, a full gate with a k3d smoke test in CI, and a daily rescan |
| `feat/deploy-v0` | – | Developer install on Debian (`install.sh --role hub` or `node`), a compose dev hub for a Mac, `verify.sh` contract checks, re-join on hub change, CI, and a README with a test record |
| `docs/core-architecture` | – | Core alignment against the leading self-hosted OSes (`docs/strategy/core-alignment.md`); phase-B architecture docs and a contract §12 draft (not committed yet) |
| `docs/security-threat-model` | – | Threat model and a ranked hardening backlog for the v0 core |
| `feat/website` | – | The OneMind website (Astro + Starlight), competitor web research and a forum plan |
| `feat/design-system` | – | Design system `@onemind/ui` in `ui/` (not committed yet) |
| `feat/mobile-shell` | – | Android and iPhone app shell in `mobile/` (not committed yet) |
| `feat/app-hermes`, `feat/apps-wave2` | – | Reserved for the Hermes app and wave-2 seed apps; no work yet |

## 2026-11-12

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
