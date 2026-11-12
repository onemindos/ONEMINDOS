# Proof-of-concept v0 contract (node agent ↔ gateway ↔ dashboard ↔ apps)

**Status:** binding for the wave-1 feature PRs (2026-11-11). Every stream builds against this file. A change to it is a separate PR that all streams adopt.
**Serves:** brief 30 B9 (D-B9.5, D-B9.8 subset), B10 (seed apps), B11 (Home, Nodes, Market, Approvals), D-B2.4 (developer install P6), D-007.
**Rule kept:** AI never actuates without human approval. Every state-changing request is an *action* that an owner must approve. An agent principal can request an action but can never approve one.

**Deliberate v0 shortcuts:** these are flagged and must be listed in each PR.
- Auth is static bearer tokens from config. Kanidm (BD-03) comes later.
- The ledger runs on SQLite in dev and tests through a repository interface, with PostgreSQL (BD-04) as the target. A PostgreSQL URL must work too.
- Nodes publish straight to the hub's NATS. NATS leaf nodes come later.

## 1. Ports and names
| Thing | Value |
|---|---|
| Hub gateway (REST + dashboard static) | `:8080` |
| Node agent `onemindd` local API | `:7480` |
| NATS (hub) | `:4222` |
| Heartbeat subject | `onemind.node.<node_id>.status`, every 10 s |
| Env vars | `ONEMIND_NATS_URL`, `ONEMIND_NODE_ROLE` (`hub` / `node`), `ONEMIND_NODE_ID` (default: a stable id derived from `/etc/machine-id` as sha256, first 12 hex characters; never the raw machine-id), `ONEMIND_TOKENS_FILE`, `ONEMIND_DB_URL`, `ONEMIND_APPS_DIR`, `ONEMIND_DASHBOARD_DIST`, `ONEMIND_EXECUTOR` (`kubernetes` / `noop`) |

## 2. Node heartbeat (JSON, published by `onemindd`, and served at `GET :7480/api/v1/node`)
```json
{
  "schema": "onemind.node.status/v1",
  "node_id": "3f9c2a1b7d4e",
  "hostname": "beelink",
  "role": "hub",
  "board": "x86_64-efi",
  "arch": "amd64",
  "os": {"id": "debian", "version_id": "13", "pretty": "Debian GNU/Linux 13 (trixie)"},
  "kernel": "6.12.0-amd64",
  "cpu_model": "…", "cpus": 4,
  "mem_total_mb": 7800, "mem_available_mb": 5100,
  "disk_total_gb": 238.0, "disk_free_gb": 190.2,
  "tpm2": false,
  "secure_boot": "disabled",
  "k3s": {"present": true, "role": "server", "ready": true},
  "rauc": {"present": false, "booted_slot": null, "slots": []},
  "gpu": {"nvidia": false, "model": null},
  "uptime_s": 1234,
  "agent_version": "0.1.0",
  "observed_at": "2026-11-11T22:00:00Z"
}
```
- `board` is one of `x86_64-efi`, `arm64-efi`, `rpi5`, `jetson-orin`, `vm`, `vm-do`, `unknown`.
  - Detect `rpi5` from `/proc/device-tree/model`, `jetson-orin` from `/etc/nv_tegra_release`, and `vm` from DMI/systemd-detect-virt.
  - Detect `vm-do` from the DMI vendor "DigitalOcean".
- `secure_boot` is `enabled`, `disabled`, `unsupported` or `unknown`.
- Never include serial numbers, MAC addresses, IP addresses or user names.

## 3. Gateway REST (`core/`, FastAPI, OpenAPI published at `/openapi.json`)
Auth: `Authorization: Bearer <token>`. `ONEMIND_TOKENS_FILE` (YAML) maps each token to a principal: `{id, kind: person|agent, role: owner|adult|guest|agent}`. Missing or unknown token → 401. `GET /healthz` is open.

| Method and path | Who | Returns |
|---|---|---|
| `GET /healthz` | anyone | `{"ok": true}` |
| `GET /v1/instance` | any principal | `{"name", "version", "hub_node_id"}` |
| `GET /v1/nodes` | any principal | list of heartbeat objects, each plus `"status": "online"|"stale"|"offline"` (stale after 30 s, offline after 120 s without a heartbeat) and `"last_seen"` |
| `GET /v1/nodes/{node_id}` | any principal | one node, or 404 |
| `GET /v1/apps` | any principal | catalog: `[{id, name, version, description, category, icon, license, source, archs, requires, web_port, installed, status}]`, built from `ONEMIND_APPS_DIR/*/onemind.app.yaml` |
| `POST /v1/actions` | owner or agent | body `{"type": "app.install"|"app.remove", "params": {"app_id": "…"}, "idempotency_key": "…", "expires_at": "RFC3339"}` → 201 with the action in `awaiting_approval`. The same idempotency key returns the same action (200) |
| `GET /v1/actions`, `GET /v1/actions/{id}` | any principal | action(s) |
| `POST /v1/actions/{id}/approve` | **owner only** (an agent gets 403 `permission_denied`) | action → `accepted` → `dispatched` → `succeeded` / `failed` |
| `POST /v1/actions/{id}/deny` | owner only | action → `cancelled` |

**Action states:** `requested → awaiting_approval → accepted → dispatched → succeeded | failed | outcome_unknown | expired | cancelled`. Approving after `expires_at` returns 409 `expired`.
**Errors:** `{"error": "permission_denied"|"stale_precondition"|"expired"|"conflict"|"outcome_unknown"|"not_found"|"unauthenticated", "message": "…"}`.
**Audit:** every decision is appended to a hash-chained JSONL audit log (`ONEMIND_AUDIT_PATH`) and published to NATS `onemind.audit` when NATS is up.
**Executor:** the `kubernetes` executor runs `kubectl apply -k <apps_dir>/<id>/manifests` into namespace `app-<id>`, and `kubectl delete` for removal. The `noop` executor marks success, for Mac/compose demos and tests.
**Static:** the gateway serves `ONEMIND_DASHBOARD_DIST` at `/`, with SPA fallback.

## 4. App manifest (`apps/<id>/onemind.app.yaml`; schema in `sdk/schema/onemind.app.schema.json`)
```yaml
apiVersion: onemind.app/v1alpha1
kind: App
metadata:
  id: uptime-kuma
  name: Uptime Kuma
  version: "2.0.2"
  description: Self-hosted uptime monitoring
  category: monitoring
  icon: icon.svg
  license: MIT
  source: https://github.com/louislam/uptime-kuma
spec:
  archs: [amd64, arm64]
  requires: {gpu: false, minMemoryMb: 256}
  web: {port: 3001}
  manifests: manifests/   # kustomization.yaml + Deployment/Service, images pinned by digest where possible
```

## 5. Dashboard (`dashboard/`, React + TypeScript + Vite)
- **Screens:** Home (instance, node count by status, installed apps), Nodes (cards per node with board, arch, OS, k3s and slot, status and `last_seen`; values are never shown as live when stale), Market (catalog, install button → creates an action), Approvals (pending actions with exact params and requester kind person/agent; approve/deny for the owner).
- **Data:** it calls only the §3 API with the token from a sign-in field (v0). Mock mode (`VITE_MOCK=1`) uses fixtures that match §2–§4.

## 6. Deploy (`deploy/`)
- `deploy/install.sh --role hub|node --hub <url> --token <join>`: the P6 developer install on stock Debian 13, Raspberry Pi OS trixie, Jetson L4T Ubuntu or a DigitalOcean Debian 13 droplet. It installs:
  - k3s (server on the hub, agent on nodes)
  - NATS on the hub
  - `onemindd` as a systemd service
  - on the hub, the gateway and dashboard
  It is labelled **unsupported developer install, no OS rollback** (REC-DEC-30).
- `deploy/compose/`: the hub on a Mac with Docker (NATS, gateway with the `noop` executor, dashboard, one simulated node).
- `deploy/verify/verify.sh <hub-url>`: a scripted pass/fail check of everything in this contract.

## 7. First founder app: Hermes agent (wave 2; founder choice, 2026-11-11)
**Why Hermes:** it is the founder's working AI agent. Running it as a OneMind app proves the core rule end to end: an **AI agent requests, a human approves, the OS executes**.
- **App:** `apps/hermes-agent/`, from the public image `nousresearch/hermes-agent:v0.23.0@sha256:adb7890916de63245523492be8f68f9d2095fecbec4e2a6dab7960381f0fc002`. This is the version and digest the founder's cluster runs today (read-only check, 2026-11-11). Verify the upstream licence before packaging.
- **Runtime facts to keep:**
  - args `gateway run`
  - `HERMES_HOME=/opt/data` on a PVC
  - API server on `:8642`, with readiness `GET /health`
  - dashboard on `:9119` (`HERMES_DASHBOARD=true`)
  - `Recreate` strategy
  - `allowPrivilegeEscalation: false`
  - `automountServiceAccountToken: false`
  - limits 2 CPU / 3 GiB, requests 250m / 1.75 GiB, so the app sets `requires.minMemoryMb: 2048` and a Pi 5 needs 8 GB
- **Clean packaging only.** Copy nothing from the founder's private deployment: no Zoho, Whop or Todoist entries, Mac SSH material, tailnet names, OIDC issuer, owner name or Langfuse. Model-provider credentials come from a Kubernetes Secret `hermes-agent-credentials` that the **owner creates at install time** (`deploy/` prints the command), never from the repo.
- **Agent principal:** at install the gateway creates a token with `kind: agent`, `role: agent` for Hermes and stores it in Secret `hermes-agent-onemind` (`ONEMIND_GATEWAY_URL`, `ONEMIND_AGENT_TOKEN`). Hermes can then **request** actions (`POST /v1/actions`) and read nodes and apps. It can never approve (403, contract §3).
- **Agent tools (gateway, wave 2):** a minimal MCP endpoint `POST /mcp` (Streamable HTTP) on the gateway, for agent principals only, with tools `list_nodes`, `list_apps` and `request_action`. It has no approve tool. Hermes's default config points one `mcp_servers.onemind` entry at it. This is the v0 slice of D-B9.2; the authorization-server façade comes later.
- **Demo to prove:** ask Hermes "install ntfy". An action appears in Approvals as requested by an agent. The owner approves, ntfy is installed, and the audit chain records requester `agent:hermes` and approver `person:owner`.

## 8. Seed apps (B10 list; the wave-1 apps PR ships 3, wave 2 adds 5)
- **Wave 1:** uptime-kuma, ntfy, home-assistant.
- **Wave 2:** node-red, mosquitto, vaultwarden, actual-budget, zigbee2mqtt (each with a licence row; arm64 + amd64; images pinned by digest).

## 9. Adding apps at scale (founder requirement 2026-11-11: 100+ apps, added continuously)
**Goal:** adding an app is a **repeatable, checked, mostly automatic** step that any AI or person can do in one PR. It is never hand-crafted. Every app arrives with its docs, its GitHub repo and its security results attached.

**9.1 Intake queue.** The founder's app list lives in `apps/_intake/queue.yaml`. Each entry is one line plus optional hints:
```yaml
- name: Immich
  github: immich-app/immich          # required: owner/repo
  docs: https://immich.app/docs      # optional; the scaffolder finds it if empty
  priority: 1                        # 1 = next batch
  notes: needs GPU optional
```
The queue is the only list. A status field (`queued`, `in-pr`, `verified`, `blocked: <reason>`) is updated by the PR that adds the app.

**9.2 Scaffolder.** `sdk/tools/app-scaffold` (Python, run with `python3 -I`) takes `owner/repo` and writes `apps/<id>/`. It fills the manifest from **primary sources only**:
- the GitHub API: description, homepage, topics, SPDX licence, latest release, archived flag, stars and last commit
- the upstream's own `compose.yaml`, Helm chart or install docs: image, ports and volumes
- the registry: digest and the architectures available (`docker buildx imagetools inspect`)

Anything it cannot verify is written as `UNVERIFIED` and blocks the `verified` tier. It never guesses an image name.

**9.3 Manifest additions** (extends §4; `sdk/schema/onemind.app.schema.json` is updated to match):
```yaml
metadata:
  links:
    docs: https://…            # upstream documentation
    github: https://github.com/owner/repo
    website: https://…
    support: https://…/issues
  upstream: {release: "v1.2.3", released_at: "…", archived: false}
  tier: verified | community | blocked      # set by CI, not by hand
spec:
  updates: {channel: security|stable, automerge: patch|none}
```
`apps/<id>/README.md` is generated: what the app is, its links, its licence, the resources it needs, first-run steps copied from the upstream docs with the source URL, and the latest scan summary. **The dashboard's app page shows docs, GitHub, website, licence, tier and the last scan date** next to Install.

**9.4 App CI gate** (`.github/workflows/ci-apps.yml`, runs on every PR that touches `apps/`). An app is `verified` only when all checks pass:
1. Schema valid, and the id is unique.
2. **Licence gate:** the SPDX licence is read from GitHub and must be allowed for the Market's L1/L2 classes (brief 30 B10; `research-output/evidence/license-matrix.*`). Unknown or non-commercial licences (e.g. PolyForm-NC) → `blocked`.
3. **Pinning:** every image is pinned by tag **and** digest, and the image supports the archs it declares.
4. **Vulnerabilities:** Trivy (v0.76.2, brief 30 D-B1.5) over each image produces an SBOM (syft) and a CVE report. CRITICAL with a fix available → fail; other findings are recorded.
5. **Malware:** ClamAV (`clamscan -r`) over each image's exported filesystem, with signatures updated in the same job. Any hit → `blocked`, and a human looks.
6. **Secrets:** Trivy's secret scanner over the image, plus gitleaks over the PR.
7. **Supply chain:** cosign verification when the upstream signs its images; the OpenSSF Scorecard score is recorded (informational). An archived upstream or no release in 18 months → `community` at best.
8. **Manifests:** `kustomize build` passes kubeconform, there are resource limits, and non-root is used where the image allows.
9. **Smoke test:** install on a throwaway k3s in CI (k3d), wait for ready, and get HTTP 200 from the web port.

**9.5 Batches.** Apps are added by an AI batch job: 10 queue entries per PR, one agent per app in its own worktree, then one reviewer per batch. The founder reviews PRs, not YAML. The scaffolder plus the CI gate make the 100-app list a queue that drains during development, not a project of its own.

## 10. Automatic updates and malware checks (founder requirement 2026-11-11)
**Principle:** updates are automatic **by a policy the owner set** (BD-09: the security channel auto-installs by default, the feature channel is manual, with opt-out, postpone and a maintenance window). Every update is scanned before it ships, and every OS update can roll back by itself.

**10.1 The OS image (Debian 13).**
- **Why not just `unattended-upgrades` on the box:** the OneMind image's root is **read-only**, so packages are never upgraded in place. Debian's own default policy is that "the default configuration auto-installs security updates, but not new features" (wiki.debian.org/UnattendedUpgrades). OneMind applies the same policy **at build time**, then ships the result as a signed A/B update.
- **Nightly:** CI checks the Debian security tracker data for the packages in the current image (debsecan-style matching against the image's `dpkg -l`). If a fixed security update exists, CI rebuilds from a new `snapshot.debian.org` timestamp that includes `trixie-security`. It then runs the SBOM, the CVE scan (with Debian tracker states as VEX, brief 30 D-B1.5), ClamAV over the rootfs and the QEMU battery T0–T5. Then it signs the RAUC bundle and TUF metadata and publishes to the **security channel**.
- **On the box:** `onemindd` (B4.2) checks the channel, verifies TUF, takes a pre-update restic snapshot, installs in the maintenance window, and reboots. The health gate commits the update or rolls it back automatically. The dashboard's Updates screen shows the history with the booted slot.
- **Developer installs (P6, stock Debian, no A/B):** `deploy/install.sh` enables Debian's `unattended-upgrades` for security origins plus `needrestart`, as Debian documents. This is labelled as the weaker path because there is no rollback.

**10.2 App images.**
- **Renovate** runs on the repo, with digest pinning on and the Kubernetes manager pointed at `apps/*/manifests/*.yaml`. It opens PRs that bump tag + digest. The §9.4 gate re-runs on each one (vulnerability, malware, smoke test).
- Patch or digest bumps of `verified` apps with `automerge: patch` merge automatically when green. Minor and major bumps wait for a human.
- **Daily rescan:** every published app image is rescanned for new CVEs and ClamAV signatures. A new CRITICAL or malware hit marks the app `blocked` in the catalog and raises an alert (ntfy) to owners who have it installed.
- **On the box:** the catalog update arrives through the gateway. Installed apps follow their `spec.updates.channel`. Security-channel app updates install automatically within the owner's policy; everything else is an action awaiting approval (§3).

**10.3 Nothing unscanned runs.** The gateway refuses to install an app whose catalog entry lacks a passing scan newer than 7 days (error `stale_precondition`).
