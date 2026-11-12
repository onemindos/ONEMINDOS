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
| Hub gateway (REST + dashboard static) | `:8080` (HTTPS `:8443` and loopback-only `:8080`: §12.7) |
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
- Optional `update`, `mesh`, `backup`, `storage` and `fabric` objects: §12.10.

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
**Errors:** `{"error": "permission_denied"|"stale_precondition"|"expired"|"conflict"|"outcome_unknown"|"not_found"|"unauthenticated", "message": "…"}`. New codes, `reason` and other optional fields: §12.2.
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

## 11. Wave-2 interfaces (amendment 2026-11-12; binding for the wave-2 streams)
These fill in what §7, §9 and §10 leave open, so that the pipeline, gateway, dashboard and app streams build against one definition.

**11.1 Scan record.** The §9.4 gate and the §10.2 daily rescan write `apps/<id>/scan.json` (generated, never edited by hand):
```json
{"scanned_at": "RFC3339", "result": "pass|fail",
 "images": [{"ref": "repo:tag@sha256:…", "archs": ["amd64", "arm64"],
             "trivy": {"version": "0.76.2", "critical_fixable": 0, "critical": 0, "high": 0},
             "clamav": {"signatures": "daily-NNNNN", "infected": 0},
             "secrets": 0, "cosign": "verified|unsigned|failed"}],
 "licence": {"spdx": "MIT", "class": "L1|L2|blocked"},
 "smoke": "pass|fail|skipped"}
```
`result` is `pass` only if every §9.4 check passed. **§10.3:** `POST /v1/actions/{id}/approve` for `app.install` returns 409 `stale_precondition` when `scan.json` is missing, `result` is not `pass`, or `scanned_at` is more than 7 days old. **Dev only:** when the executor is `noop`, `ONEMIND_ALLOW_UNSCANNED=1` disables this check and the gateway logs a warning at startup. It is refused with the `kubernetes` executor.

**11.2 Agent principals for apps.** A manifest may declare `spec.agent: {principal: true, secret: <name>}`. When the gateway installs such an app (kubernetes executor), it:
1. creates the principal `{id: "agent:<app-id>", kind: agent, role: agent}` with a fresh random token, stored hashed in the gateway's database next to the static tokens file (both are honoured);
2. creates the Secret `<name>` in `app-<id>` with `ONEMIND_GATEWAY_URL` and `ONEMIND_AGENT_TOKEN`, before applying the manifests;
3. revokes the principal and deletes the Secret on `app.remove`.

The audit log records the requester of an action as the principal id (e.g. `agent:hermes-agent`) and the approver as the owner's id.

**11.3 MCP endpoint (§7).** `POST /mcp`, Streamable HTTP (MCP 2025-06-18), bearer token, `kind: agent` principals only (anything else → 403 `permission_denied`). Tools: `list_nodes` (= `GET /v1/nodes`), `list_apps` (= `GET /v1/apps`), `request_action` (`{type, app_id, reason?}` → creates an action exactly like `POST /v1/actions` with a generated idempotency key and a 24 h expiry; it returns the action id and state). There is no approve or deny tool.

**11.4 Catalog fields.** `GET /v1/apps` adds to each entry `links` (§9.3), `tier`, and `scan: {scanned_at, result} | null`. The dashboard's Market card and app page show the docs, GitHub, website and support links, the licence, the tier and the last scan date next to Install, and disable Install with the reason when the scan is missing, failing or stale.

**11.5 Namespaces.** App `<id>` installs into namespace `app-<id>`; ids are at most 59 characters (§4 schema).

## 12. Phase-B interfaces (amendment 2026-11-12; binding)
This section makes [`docs/architecture/CONTRACT-12-DRAFT.md`](../../docs/architecture/CONTRACT-12-DRAFT.md) binding. Where that draft and the leap specs used different names ([`docs/leap/DECISIONS-NEEDED.md`](../../docs/leap/DECISIONS-NEEDED.md) §2), the [`docs/leap/dev/API.md`](../../docs/leap/dev/API.md) name is used unless the architecture docs gave a reason; §12.21 records each choice. Feature specs own behaviour; this section owns names, paths, bodies, errors, subjects and risk classes.

**Compatibility.** Everything here is additive. No §1–§11 path, field, state or error changes meaning, and a client written for §3 and §11 keeps working. A route in this section exists only once its module ships; until then it is absent from `/openapi.json` and answers 404.
**v0 shortcuts retired by this section** (each when its module ships): static tokens only (§12.6), no HTTPS (§12.7), unauthenticated NATS with nodes publishing straight to the hub (§12.9, §12.11).
**Founder defaults applied** (recorded in DECISIONS-NEEDED §1; a different founder answer is a follow-up contract PR): F-1 HTTPS, F-2 passkey on every owner approval, F-6 standing approvals for app patch updates, F-7 no unscanned installs in v0, F-8 cobra, F-9 no rescue-mode approvals, F-11 risk policy, F-12 token approvals before passkeys, F-14 role scopes on upgrade, F-15 personal agent tokens, F-16 agents may withdraw, F-19 no `:all` reads for plugin agents, F-24 plugin event relay.

### 12.1 Conventions
**Principal kinds.** §3's `{id, kind, role}` gains three kinds. `person` and `agent` keep their §3 meaning.

| Kind | Id | May request | May approve |
|---|---|---|---|
| `person` | `person:<id>` | by role and scopes (§12.6) | role `owner` only |
| `agent` | `agent:<id>` | by grant (§12.6) | never |
| `plugin` | `plugin:<app-id>` | the scopes the owner approved at install | never |
| `automation` | `automation:<rule-id>` | the rule's action types, never `destructive` (F-11) | never |
| `node` | `node:<node_id>` | `node.join` only, and only with a join code (§12.11) | never |

**Approver.** `approved_by` is a person with role `owner`, or `policy:<policy-id>@<revision>` (§12.17). `approved_via` is `dashboard`, `phone`, `cli`, `policy` or `console`.

**Two kinds of write** (API.md §2.1). A **request** creates an action in `awaiting_approval` and returns `202` with the action and `Location: /v1/actions/{id}` (`POST /v1/actions` keeps its §3 `201`/`200`). A **direct owner write** applies at once and is audited; it is used only for a person's own settings and for removing power (revoke, suspend, disable). Adding power is always a request.
Every request endpoint accepts `{"reason"?: ≤ 500 chars, "expires_at"?: default now + 24 h, at most now + 7 d, "approve"?: bool}` and the `Idempotency-Key` header. `"approve": true` is the **owner shortcut**: owner only, creates and approves in one transaction, audits both steps with `owner_initiated: true`, and still needs the step-up the risk class requires (§12.3). From any other principal it returns `403 permission_denied`, files nothing, and audits `authz.denied`.

**Idempotency.** `POST /v1/actions` keeps its body `idempotency_key` (§3). Every other creating `POST` takes an optional `Idempotency-Key` header (≤ 200 chars, kept 24 h per principal). Same key and body → the first response is replayed with `OneMind-Idempotent-Replay: true`; same key, different body → `409 conflict`.

**Lists.** List endpoints return a JSON **array**, as §3 does. Pagination is `?limit=` (default 100, max 500) and `?cursor=`, with an RFC 8288 `Link: <…>; rel="next"` header that is absent on the last page. Cursors are opaque and valid 24 h. A §3 list called without `limit` returns up to 1,000 items, as today. Filters are query parameters named after fields; a comma means OR, different fields AND, `.*` is a glob (`type=backup.*`), and time windows use `since`/`until`.

**Ids and times.** Ids are opaque strings; clients never parse them. New tables use prefixed ULIDs (`tkt_`, `job_`, `snap_`, `run_`, `dst_`, `rst_`, `alrt_`, `ntf_`, `chn_`, `dev_`, `rule_`, `pol_`, `win_`, `hook_`, `tok_`, `ses_`, `usr_`); action ids stay UUID v4. Times are RFC 3339 UTC.

**Secrets.** Secrets are write-only. They never appear in `params`, plans, events, logs or the audit (which records `"credentials": "provided"` or the value's `sha256`). A response may carry `"one_time": {…}` (token, join code, recovery key, hook secret): shown once, never stored in clear, never returned again. A request may carry `"sealed": {"alg": "X25519-AES256GCM", "epk", "ct"}`, encrypted to `GET /v1/secrets/public-key` (`{alg: "X25519", key, key_id}`); the gateway decrypts it only into its secret store.

**Headers.** Every response carries `OneMind-Request-Id` and `OneMind-API-Version` (semver of the OpenAPI document). Clients send `OneMind-API-Version: 1`. `GET /v1/instance` gains `api: {version, min_client}` and `features: [..]`.

**Limits** (API.md §9; the owner may raise them). Token bucket per principal, per source address for unauthenticated routes: reads 20/s burst 60; requests 2/s burst 10 **and at most 10 actions in `awaiting_approval` per requester** (owners are not capped; the 11th gets `429 rate_limited`, reason `too_many_pending`); `POST /v1/notifications/send` 10/min per sender; wrong tokens, join codes and logins 10/min per source then a 15-minute back-off; 5 open event streams per principal. Bodies ≤ 256 KiB except `POST /v1/deploy/bundles`.

### 12.2 Errors
The §3 envelope gains optional fields; `error` and `message` are always present and clients branch on `error` only:
```json
{"error": "stale_precondition", "message": "the plan changed since the request",
 "reason": "plan_changed", "request_id": "req_01J…", "details": [{"field": "params.app_id", "problem": "scan stale"}],
 "retry_after_s": null}
```
New codes (an unknown code must be handled by its HTTP status class):

| Code | HTTP | When | Why it is a new code |
|---|---|---|---|
| `rate_limited` | 429 | a §12.1 limit, including the pending-action cap; sets `Retry-After` and `retry_after_s` | callers must back off, not resolve a conflict |
| `unavailable` | 503 | a dependency is down: database, NATS for a job, a node that is `offline` (reason `node_offline`), an unreachable backup destination (`target_unreachable`), the gateway starting | retryable; D-B9.8's `offline_not_supported` is this code with reason `node_offline` (§12.21) |
| `payload_too_large` | 413 | body over its limit | |
| `policy_refused` | 409 | the install sandbox's checks refused the rendered plan (CORE-SANDBOX); the action moves to `failed` with the violations in `result` | distinct from `permission_denied`: the caller is allowed, the content is not |
| `invalid_request` | 422 | body or query fails the schema | **opt-in:** sent only to clients that send `OneMind-Errors: 2`. Others keep §3's `conflict` on 422, with `details` |
| `method_not_allowed` | 405 | wrong method on an existing path | **opt-in** as above; others keep `not_found` on 405 |

`unauthenticated` gains reason `step_up_required` (§12.3). **Reasons** are open-ended (new ones need no contract change): `plan_changed`, `plan_unchecked`, `step_up_required`, `assertion_invalid`, `code_used`, `code_unknown`, `duplicate_node_id`, `node_offline`, `target_unreachable`, `too_many_pending`, `scan_stale`, `scan_missing`, `scan_failed`, `last_owner`, `not_drained`, `version_mismatch`, `limit_reached`, `never_by_policy`.

### 12.3 Risk classes and the approval rule (F-11, F-2)
Every action type has a fixed risk class (§12.5). The class decides who may approve and how:

| Risk | Meaning | Approval |
|---|---|---|
| `read` | no lasting change (`os.update.check`, `system.check`) | auto-approved by the built-in policy `policy:read-only@1`, which the owner may turn off |
| `write` | reversible, adds no power (`backup.run`, `node.drain`, `app.restart`) | owner, or an owner-set standing approval (§12.17) |
| `sensitive` | widens what runs or who can reach it, or changes credentials, destinations, grants or update policy (`app.install`, `node.join`) | owner; never a policy |
| `destructive` | data loss or downtime possible (`backup.restore`, `node.remove`, `app.remove` with `delete_data`) | owner with step-up; never a policy; automations may not request it |
| `actuate` | moves or switches a physical device | owner with step-up; never a policy; lab-only until LT-VM-18 passes (reserved, no type in v1) |

**Step-up (F-2).** Once the owner has a passkey (§12.6), **every** owner approval, and every owner shortcut, carries a WebAuthn assertion; `destructive` and `actuate` always need one. The instance setting `require_passkey_approval` is on for new boxes. Without a passkey (v0 boxes, or the setting off) an approval is accepted for `read`, `write` and `sensitive`, audited `approval: token` and shown on the card as "approved without passkey" (F-12). Missing or stale → `401 unauthenticated`, reason `step_up_required`.

### 12.4 Actions: model and endpoints
**Action object additions** (all optional for v0 readers):
```json
{"id": "6f1c9e0a-…", "type": "backup.restore", "params": {"snapshot_id": "snap_01J…", "scope": {"app_id": "vaultwarden"}, "mode": "portable", "target": "in_place"},
 "state": "awaiting_approval", "risk": "destructive", "reason": "data corrupted since 02:00",
 "requested_by": {"id": "agent:hermes-agent", "kind": "agent"},
 "approved_by": null, "approved_via": null, "approval": null,
 "target": {"kind": "app", "id": "vaultwarden", "node_id": "3f9c2a1b7d4e"},
 "plan": {"summary": "…", "objects": [], "images": [], "volumes": [], "nodes": [], "warnings": []},
 "plan_sha256": "sha256:…", "hold": null, "expires_at": "…", "created_at": "…", "updated_at": "…", "result": null}
```
- `plan` is rendered at request time (H-13). `plan_sha256` = sha256 of the canonical JSON of `{type, params, target, plan.objects}`.
- `approval` is `passkey`, `token`, `policy` or `console`.
- `hold: {window_id, until}` marks an accepted action waiting for its maintenance window. It stays in state `accepted` (no new state). On gateway restart, held actions stay `accepted`; the §3 rule (an interrupted dispatch becomes `outcome_unknown`) applies only to actions that were dispatched.
- `requested_by.id` and `approved_by` are what the audit records (§11.2).

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/actions` | `actions:read` | §3 list plus filters `?state&type&requested_by&risk&since&until&limit&cursor` |
| `POST /v1/plans` | `actions:request` | body `{type, params}` → `{plan, plan_sha256, risk, policy_verdict: needs_approval\|auto_approved\|refused}`; no side effects, nothing filed |
| `GET /v1/actions/{id}/preview` | `actions:read` | the action's stored `plan` and `plan_sha256` (what the approval card shows) |
| `POST /v1/actions/{id}/approve-options` | owner | `{challenge, action_sha256, plan_sha256, expires_at}`; the challenge is `sha256(action_id ‖ action_sha256 ‖ plan_sha256 ‖ nonce)`, single use, valid 120 s |
| `POST /v1/actions/{id}/approve` | owner only (§3) | optional body `{plan_sha256, webauthn: {id, clientDataJSON, authenticatorData, signature}}`. A `plan_sha256` that differs from the stored plan, or a fresh render that differs from it → `409 stale_precondition` (`plan_changed`), the action stays `awaiting_approval`. Without `plan_sha256`: accepted for clients that do not send `OneMind-API-Version: 1`, audited `plan_unchecked`; refused (`409`, `plan_unchecked`) for clients that do |
| `POST /v1/actions/{id}/deny` | owner only (§3) | optional body `{reason}`, recorded and shown to the requester |
| `POST /v1/actions/{id}/cancel` | the requester (any kind, F-16) | `awaiting_approval` → `cancelled`; audited; not an approval |
| `GET /v1/action-types` | `actions:read` | `[{type, risk, params_schema, requested_by: [kinds], runs_on, since}]` from §12.5 |

`POST /v1/actions` accepts every type of §12.5 the caller's kind and scopes allow, plus optional `plan_sha256` (refused with `409 plan_changed` if the fresh plan differs) and `approve` (owner shortcut, §12.1). §11.1's scan precondition still applies to `app.install` and now also to `app.update`. `acknowledge_unscanned` is **not** part of v1 (F-7); a private bundle installs only after the on-box scan passes.

### 12.5 Action-type registry
Requested by: O owner, Ad adult (own scope only), A agent (by grant, §12.6), P plugin (by approved scopes), Au automation, N the joining node. Runs on: G gateway (Kubernetes, database), J a signed job to a node (§12.11), G+J both. Policy coverage follows the risk (§12.3).

| Type | Params | Risk | Requested by | Runs on |
|---|---|---|---|---|
| `app.install` | `{app_id, version?, node_id?, bundle_sha256?, settings?, sealed?}` | sensitive | O, A, P, Au | G |
| `app.remove` | `{app_id, delete_data?: false}` | write; destructive with `delete_data` | O, A, Au (not with `delete_data`) | G (+J) |
| `app.update` | `{app_id, to_version?, bundle_sha256?}`; an update that widens grants is `sensitive` | write | O, A, Au | G+J (pre-update snapshot) |
| `app.rollback` | `{app_id, to_revision}` | write | O, A, Au | G |
| `app.restart` | `{app_id, component?}` | write | O, A, Au | G |
| `app.configure` | `{app_id, settings, sealed?}` | write; sensitive with `sealed` | O, A (no `sealed`) | G |
| `app.reconcile` | `{app_id}` | write | O, Au | G |
| `app.move` | `{app_id, to_node_id}` | sensitive | O | G+J |
| `node.join` | `{join_request_id}` (filed by §12.11) | sensitive | N | G |
| `node.drain` / `node.uncordon` | `{node_id}` | write | O, A, Au | G |
| `node.label` | `{node_id, set, unset}` | write | O, A, Au | G |
| `node.set_role` | `{node_id, role: worker\|leaf}` | sensitive | O | G+J |
| `node.renew` | `{node_id}` | write | O, Au | J |
| `node.remove` | `{node_id, wipe: bool}` | destructive | O, A | G+J |
| `backup.run` | `{scope: "box"\|{app_id}, destination_id?}` | write | O, A, Au | G+J |
| `backup.verify` | `{snapshot_id?\|latest: true, mode: check\|scratch_restore}` | write | O, A, Au | G+J |
| `backup.restore` | `{snapshot_id, scope: "box"\|{app_id}\|{app_id, path}, mode: portable\|exact, target: in_place\|new_namespace}` | destructive | O; A only with the explicit grant `actions:request:backup.restore` | G+J |
| `backup.destination.add` / `.remove` | `{kind, label, config, sealed}` / `{destination_id}` | sensitive / destructive | O | G+J |
| `backup.snapshot.delete` | `{snapshot_id}` | destructive | O | J |
| `backup.prune` | `{destination_id}` | destructive | O | J |
| `backup.key.rotate` | `{which: device\|owner\|escrow}` | destructive | O | G+J |
| `backup.kit.issue` | `{}` → `one_time` emergency kit | sensitive | O | G |
| `os.update.check` | `{node_id}\|{all: true}` | read | O, A, Au | J |
| `os.update.apply` | `{node_id, version, reboot: window\|now\|no}` | write; destructive with `reboot: now` | O, A, Au | J |
| `os.update.postpone` | `{node_id, until}` | write | O, A | J |
| `os.update.settings` | `{node_id, channel?, policy?, window?}` (policy keys only, H-26) | sensitive | O | J |
| `os.rollback` | `{node_id}` | destructive | O | J |
| `automation.rule.create` / `.update` / `.enable` | the rule body / `{rule_id, …}` | write | A, P (owners write directly, §12.17) | G |
| `agent.resume` | `{agent_id}` | sensitive | O | G |
| `tls.acme.set` | `{domain, dns_provider, sealed}` or `{off: true}` | sensitive | O | G |
| `system.check` | `{checks?: [..]}` | read | O, A, Au | G+J |
| `system.restart_unit` | `{node_id, unit}`, unit in `onemind-nats`, `onemindd`, `k3s`, `k3s-agent` | write | O, Au | J |
| `catalog.refresh` | `{}` | write | O, Au | G |
| `exposure.*` | reserved (public exposure review) | sensitive | O | G |

Agents never request `node.join`, grant or role changes, token creation, policy changes, kill-switch changes or data export, whatever their grant (`403 permission_denied` before anything is filed). `ActionType` in `core/onemind_core/actions.py` becomes this registry; `APP_CLAIMS` extends to each type that claims an app or node, so two conflicting actions cannot both be accepted.

### 12.6 Identity: people, roles, sessions, passkeys, tokens, sharing
**Roles.** People have role `owner`, `adult`, `guest` or `child` (`child` is new; v1 clients treat unknown roles as the least privileged). `agent` stays the role of agent principals. The last active owner cannot be demoted or disabled (`409 conflict`, `last_owner`).

**Sign-in** (CORE-SEC-2). The owner registers a passkey at first boot or with `onemind init`; the static owner token then becomes a console-only, single-use break-glass credential that is rotated after use.

| Method and path | Who | Returns |
|---|---|---|
| `POST /v1/auth/passkeys/register/options`, `POST /v1/auth/passkeys/register` | a signed-in person, or the setup session on first boot | WebAuthn registration; `{credential_id, label}` |
| `GET /v1/auth/passkeys`, `DELETE /v1/auth/passkeys/{credential_id}` | the person (own) | own passkeys; removing the last passkey of the last owner → `409 last_owner` |
| `POST /v1/auth/login/options`, `POST /v1/auth/login` | anyone; `rate_limited` per source | a session. Browsers: cookie `HttpOnly; Secure; SameSite=Strict` plus a CSRF token that every non-GET sends as `OneMind-CSRF` (H-16). Apps and the CLI: `{access_token, expires_at, refresh_token}` bearer |
| `POST /v1/auth/logout` | the session | `204` |
| `GET /v1/auth/sessions`, `DELETE /v1/auth/sessions/{id}` | the person (own); owner (all) | `[{id, principal_id, client, created_at, last_seen_at, current}]`; revoke is instant |
| `GET /v1/me` | any principal | `{principal: {id, kind, role, display_name?}, token: {id, scopes, expires_at} \| null, session: {id, expires_at} \| null, passkeys: n, capabilities: ["can_approve", …]}` |

**Users** (direct owner writes with step-up, audited):

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/users` | `users:read` (owner) | `[{id, display_name, role, created_at, last_seen_at, disabled}]` |
| `POST /v1/users` | owner | `{display_name, role}` → `201` with `one_time: {enrolment_url}` valid 24 h (the person registers a passkey there) |
| `PATCH /v1/users/{id}` | owner | role or display name |
| `POST /v1/users/{id}/disable` | owner | also revokes the user's sessions and tokens at once |

**Tokens** (H-09; replaces the static file over time, which keeps working and is listed read-only with `source: file`).
- Format `om_<kind>_<random>`: `om_pat_` person, `om_agt_` agent, `om_plg_` plugin, `om_nod_` node, `om_aut_` automation. Only the sha256 is stored.
- `GET /v1/tokens` (owner: all; others: own) → `[{id, prefix, name, principal_id, kind, scopes, created_at, expires_at, last_used_at, source: api|file|app-install}]`, never the secret.
- `POST /v1/tokens` (`tokens:admin` owner, or `tokens:self` for a person's own token) `{name, principal: "self"|{kind: "agent", id}, scopes, expires_in_days}` → `201` with `one_time: {token}`. **Personal agent tokens (F-15):** default grant `reader`, default and maximum expiry 90 days, renewable.
- `POST /v1/tokens/{id}/rotate` (`grace_s` default 0, at most 3600) and `DELETE /v1/tokens/{id}`: direct writes.
- **Kill switch:** `POST /v1/agents/{id}/suspend` (owner, direct) revokes all of that agent's tokens and cancels its pending actions at once; the next call returns 401. Resuming is the `sensitive` action `agent.resume`.

**Scopes** (API.md §8.2). Effective access = (role defaults for a person's session, or the token's scopes) ∩ what the kind allows ∩ resource ownership (own inbox, own tokens, shared apps).

| Scope | Grants | Allowed for kinds |
|---|---|---|
| `instance:read` | `/v1/instance`, `/v1/me` | all |
| `nodes:read`, `apps:read` | nodes, catalog and installed apps | all |
| `nodes:report` | publish its own heartbeat | node |
| `actions:read` | actions, action types, standing approvals | all |
| `actions:request` | `POST /v1/actions`, `POST /v1/plans`, request endpoints | person, agent, plugin, automation |
| `actions:approve` | approve, deny, standing approvals | person `owner` only |
| `fabric:read` / `:request` / `:admin` | §12.11 | read all; request person, agent, automation; admin owner |
| `backups:read` / `:request` / `:admin` | §12.12 | same pattern |
| `updates:read` / `:request` / `:admin` | §12.13 | same pattern |
| `notifications:read` / `:write` | own inbox, channels, preferences, devices | person |
| `notifications:send` | `POST /v1/notifications/send` | plugin, agent, automation |
| `alerts:read` | `/v1/alerts`, filtered by audience | all |
| `monitoring:read` | §12.15 metrics and health | all |
| `logs:read` | §12.15 app logs | person owner/adult; agent and plugin only with the `:<app-id>` suffix |
| `automation:read` / `:request` / `:write` | §12.17 | read all; request agent, plugin; write owner |
| `audit:read` / `:admin` | §12.16 | read owner, adult; admin owner |
| `users:read` / `:admin`, `tokens:self` / `:read` / `:admin` | users, tokens | owner (`tokens:self`, `tokens:read`: any person) |
| `events:read` | `/v1/events`, filtered by the caller's other read scopes | all |

**Narrowing suffixes:** `actions:request:<type>` (H-22), `logs:read:<app-id>`, `actions:read:own|all`, `audit:read:own|all`, `actions:withdraw:own`, `events:read:<type-glob>`. `actions:read:self` is spelled `actions:read:own`; the plugin permission `alerts:raise` is `notifications:send`. **Never minted** for agent, plugin, automation or node: `actions:approve`, any `:admin` scope, `users:*`, `tokens:admin`. The gateway refuses to mint them (`403`) and refuses a manifest that asks for them (`422`). Plugin and personal agents never get `actions:read:all` or `audit:read:all` (F-19 default).
**Agent grant bundles** (MCP.md §4): `reader` = `instance:read nodes:read apps:read actions:read:own audit:read:own updates:read backups:read docs:read`; `requester` = `reader` + `actions:request:app.install actions:request:app.remove actions:withdraw:own`; `v0` = today's behaviour, the default for static-file agents without `scopes`. An agent's effective rights never exceed its owning person's.
**Manifest principals** (schema change follows in `sdk/schema/`): `spec.agent: {principal: true, secret, scopes: [..]}` (extends §11.2) and `spec.plugin: {principal: true, secret}` with `spec.permissions: [..]`. The install card lists the scopes; an update that widens them is `sensitive`; narrowing needs no approval.

**Role defaults** (`api.enforce_role_scopes`: on for new boxes, off for boxes upgraded from v0 until the owner turns it on, F-14):

| Role | Scopes |
|---|---|
| `owner` | all |
| `adult` | every `:read` except `users:read`, plus `logs:read`, `notifications:write`, `tokens:self`, `actions:request` |
| `guest` | `instance:read`, `nodes:read`, `apps:read` (shared apps only), `notifications:read`, `notifications:write`, `alerts:read` (own audience) |
| `child` | `instance:read`, `apps:read` (shared apps only), `notifications:read`, `alerts:read` (own audience) |

**Per-app sharing.** Owners and adults see and open every installed app. Guests and children see and open only apps shared with them.

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/apps/{id}/access` | owner; a person sees only their own entry | `{app_id, roles: ["owner", "adult"], people: [{id, display_name}], auth: "onemind"\|"app"}` |
| `PUT /v1/apps/{id}/access` | owner (direct, audited) | full replace `{roles, people}`; `owner` is always included. Removing access is instant; the app proxy and `GET /v1/apps` honour it on the next request |

The hub edge's forward-auth (networking stream) answers per person and app from this record: signed out → sign-in, allowed → pass, no share → 403.

### 12.7 HTTPS (F-1)
- At first start the gateway creates a **per-box CA** (ECDSA P-256, name-constrained to the box's names) and a server certificate for `<hostname>`, `<hostname>.local`, `onemind.local` and `*.onemind.local`, renewed yearly, keys `0600` under `/data/onemind/tls/`.
- The gateway serves HTTPS on **`:8443`**. `:8080` (§1) binds `127.0.0.1` only, for local tools and the health gate. HTTP is accepted only on loopback (H-05).
- Pairing a phone or desktop: a QR with `{url, ca_sha256}`, **never a token**; the client pins the fingerprint. `GET /v1/tls` (any principal) → `{ca_sha256, names, not_after, acme: {domain, state, not_after} | null}`.
- **Optional Let's Encrypt** when the owner brings a domain: action `tls.acme.set` (`sensitive`) with the DNS provider credentials sealed; DNS-01 only, so nothing listens on the internet. The per-box CA keeps serving `.local` names. A Tailscale certificate may serve the mesh name when remote access is on (networking stream); tailnet names appear in public certificate-transparency logs and the UI says so.

### 12.8 Events stream (SSE)
`GET /v1/events` with `Accept: text/event-stream` (`events:read`). Query `?types=action.*,node.status&since_id=<id>`; without `types`, everything the caller may read.
```text
id: 18342
event: action.state_changed
data: {"schema":"onemind.event/v1","id":"18342","type":"action.state_changed","ts":"2026-11-12T09:01:12Z","subject":{"action_id":"6f1c9e0a-…"},"severity":"info","data":{"from":"awaiting_approval","to":"accepted","by":"person:owner"}}

: keepalive
```
- **Envelope `onemind.event/v1`:** `schema`, `id`, `type`, `ts` (when it happened), `subject` (the ids it concerns: `action_id`, `node_id`, `app_id`, `alert_id`, `rule_id`, `job_id`, as applicable), `data` (small facts and ids only, never secrets or file contents), and optional `severity` (`info|warning|critical`), `source_id`, `actor_id`, `correlation_id`, `causation_id`, `dedupe_key`, `observed_at`. The same envelope is used on NATS (§12.9).
- `id` is monotonic; audit-derived events use the audit `seq`. Resume with `Last-Event-ID` or `since_id`; the gateway replays from a buffer of 24 h or 10,000 events, and beyond it sends `stream.reset` first (the client re-reads state over REST). `: keepalive` every 15 s.
- Events are filtered per principal before sending (a guest never sees `audit.*`; a plugin sees its own app plus `node.status`).
- **v1 types** (additive; clients ignore unknown types): `action.requested`, `action.state_changed`; `node.status` (status changes only), `node.join_requested`, `node.joined`, `node.removed`, `node.degraded`; `app.status`, `app.health`, `app.restarted`; `backup.run.finished`, `backup.verify.finished`, `backup.health`; `restore.state_changed`; `os.update.state`; `storage.state`; `mesh.state`; `alert.opened`, `alert.updated`, `alert.resolved`; `notification.created` (own inbox); `automation.fired`; `audit.appended` (`audit:read` only), `audit.checkpoint`; `stream.reset`.

### 12.9 NATS
The OS owns `onemind.>`. Apps and plugins never publish there (brief 30 E7); app subjects stay in the app grammar (`evt.`, `cmd.`, `tel.`, `svc.` …) and are out of scope here.

| Subject | Publisher | Payload | Stream |
|---|---|---|---|
| `onemind.node.<node_id>.status` | that node | §2 heartbeat with §12.10 objects | none |
| `onemind.node.<node_id>.event.<type>` | that node | event envelope; the gateway validates and re-publishes it as `onemind.event.<type>` | `ONEMIND_NODE_OUTBOX` on the node's leaf, sourced by the hub |
| `onemind.node.<node_id>.job.<kind>` | gateway | §12.11 job | `ONEMIND_JOBS` (work queue; consumer `node-<node_id>`) |
| `onemind.node.<node_id>.jobresult.<job_id>` | that node | `{job_id, state: running\|succeeded\|failed, progress?, summary, reason?, finished_at?}` | `ONEMIND_JOBRESULTS` (file, 30 days) |
| `onemind.audit` | gateway | §3 audit line | `ONEMIND_AUDIT` (file, 1 year or 2 GiB, deny delete and purge) |
| `onemind.event.<type>` (dots of `type` kept, e.g. `onemind.event.node.status`) | gateway | event envelope | `ONEMIND_EVENTS` (file, 7 days or 1 GiB) |
| `onemind.alert.<source>.<kind>` | gateway, nodes (through their outbox) | alert record `onemind.alert/v1` (§12.14) | `ONEMIND_EVENTS` |
| `onemind.plugin.<app-id>.<event>` | gateway only, relaying a plugin's event (F-24) | event envelope | `ONEMIND_EVENTS` |

**Auth (H-06).** NATS requires TLS with the box CA and nkey users: `gateway` (subscribes `onemind.node.*.status`, `onemind.node.*.event.>`, `onemind.node.*.jobresult.>`; publishes `onemind.audit`, `onemind.event.>`, `onemind.alert.>`, `onemind.plugin.>`, `onemind.node.*.job.>`); one user per node, issued at approved join, that may publish only its own `onemind.node.<node_id>.{status,event.>,jobresult.>}` and pull its own `ONEMIND_JOBS` consumer; everything else denied, never `>`. Seeds are files with mode `0600`. Clients (dashboard, phone, SDKs) never connect to NATS; they use `/v1/events`.

### 12.10 Heartbeat optional objects (extends §2)
All optional. **Absent means "this agent does not report it", never "false" or "zero".** None may contain an IP address, MAC address, serial number or user name.
```json
"update":  {"channel": "security", "current_version": "0.1.20261112", "available_version": null,
            "state": "idle", "last_check": "…", "last_result": "…"},
"mesh":    {"state": "up", "path": "direct"},
"backup":  {"running": false, "last_run_at": "…", "last_result": "succeeded"},
"storage": {"state": "protected", "mount": "/data", "used_bytes": 0, "free_bytes": 0,
            "needs_scrub": false, "reasons": []},
"fabric":  {"role": "worker", "leaf_link": "up", "outbox_pending": 0, "cert_expires_at": "…"}
```
- `update` is exactly the struct in `internal/heartbeat` (PR #15): `state` is `idle|downloading|installing|pending_reboot|trial|committed|rolled_back|error`; `available_version` and `last_check` may be null.
- `mesh.state` is `up|down|none`, `mesh.path` is `direct|relayed|none`. Mesh addresses are never in the heartbeat; the gateway reads them from the coordinator.
- `backup.last_result` is `succeeded|failed|partial|none`; `last_run_at` may be null.
- `storage.state` is `protected|unprotected|degraded|unavailable|unsupported` (`internal/storage`); `reasons` are short slugs; disks are reported only through the owner-only storage API, never in the heartbeat.
- `fabric.role` is `hub|worker|leaf` (the top-level §2 `role` stays `hub|node`); `leaf_link` is `up|down|none`.
- The gateway adds `received_at` and `clock_skew_s` when it serves nodes; they are not in the published heartbeat.

### 12.11 Fabric: join ticket → node request → owner approval
| Method and path | Who | Returns |
|---|---|---|
| `POST /v1/fabric/join-tickets` | owner (`fabric:admin`, direct) | `{role: worker\|leaf ("node" = worker), expires_in_s ≤ 3600 (default 900), labels?}` → `201 {ticket_id, role, expires_at, hub_ca_sha256, qr_payload}` + `one_time: {join_code}`. `qr_payload` = `onemind-join:v1?code=<join_code>&ca=<hub_ca_sha256>&role=<role>[&hub=<url>]`; `hub` is omitted when the owner chooses mDNS discovery |
| `GET /v1/fabric/join-tickets` | owner | `[{ticket_id, role, labels, created_by, expires_at, used_by_node_id}]`, never codes |
| `DELETE /v1/fabric/join-tickets/{ticket_id}` | owner | `204`; revokes an unused ticket at once (removes a right to ask, so not an action) |
| `POST /v1/fabric/join-requests` | **no session**: the join code authenticates; `rate_limited` per source | `{join_code, node: {node_id, hostname, board, arch, os}, csr_pem, nats_pubkey}` → `202` with the `node.join` action (`sensitive`) and `poll: "/v1/fabric/join-requests/{id}"`. Errors: `401 unauthenticated` (`code_unknown`, `code_used`), `409 expired`, `409 conflict` (`duplicate_node_id`) |
| `GET /v1/fabric/join-requests/{id}` | the joining node, header `OneMind-Join-Code` | `{state: awaiting_approval\|approved\|denied\|expired\|delivered}`; once, after approval: `credentials: {node_cert, ca_cert, nats: {url, user_pubkey}, job_pubkey, k3s?: {server_url, token (1 h)}, mesh?: {control_url, auth_key}}`; later calls return `delivered` |
| `POST /v1/fabric/nodes/{node_id}/renew` | that node, mutual TLS | `{csr_pem}` → `{node_cert}`; `403` if removed |
| `GET /v1/fabric` | `fabric:read` | `{hub_node_id, counts: {hub, worker, leaf}, nodes: [{node_id, role, state, leaf_link, mesh, outbox_pending, cert_expires_at}]}` |
| `POST /v1/nodes/{node_id}/drain`, `/remove`, `/labels` | `fabric:request` | `202` with `node.drain`, `node.remove`, `node.label` |
| `GET /v1/apps/{id}/placement` | any principal | `[{node_id, verdict: fits\|fits_with_warning\|no, reasons}]` |

- The approval card shows board, arch, OS, hostname and the ticket's labels; never serials, MAC or IP addresses. The node becomes principal `node:<node_id>` with `nodes:report` only after approval. `node.join` succeeds on the first authenticated heartbeat (and, for a worker, k3s `Ready`).
- `GET /v1/nodes` and `/v1/nodes/{id}` gain `role`, `state` (`joining|online|degraded|stale|offline|draining|drained|removed`), `degraded_reasons`, `received_at`, `clock_skew_s`, `apps` and filters `?status&role&limit&cursor`. §3's `status` keeps `online|stale|offline`.
- **Job** (`onemind.job/v1`): `{schema, job_id, action_id, kind, params, params_sha256, issued_at, expires_at, sig}` signed Ed25519 with the gateway's job key. Kinds: `backup.run`, `backup.restore`, `backup.verify`, `backup.prune`, `backup.snapshot.delete`, `update.check`, `update.apply`, `update.postpone`, `update.settings`, `os.rollback`, `node.leave`, `node.renew`, `host.check`, `system.restart_unit`. A node refuses (and reports `failed` with `reason`) a bad signature, an expired job, a `job_id` it has seen, or an unknown kind.

### 12.12 Backups and restores
| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/backups/status` | `backups:read` | `{health: ok\|stale\|failing\|not_configured, last_success_at, last_verified_restore_at, next_run_at, copies, badges: {box, system, apps: {<id>: <badge>}}, destinations: [..]}`; badge = `{state: verified\|unverified\|stale\|failing\|none, verified_at, last_success_at, reason?}` with BACKUPS.md §8's rules (verified = a restore with fresh signals passed ≤ 8 days ago and the last run succeeded ≤ 2 h ago) |
| `GET /v1/backups/destinations` | owner, adult | `[{id, kind: usb\|box\|s3\|rest, label, primary, append_only, state, last_seen_at, free_bytes?}]`, never credentials |
| `POST /v1/backups/destinations`, `DELETE /v1/backups/destinations/{id}` | owner (`backups:admin`) | `202` with `backup.destination.add` / `.remove`; credentials sealed |
| `POST /v1/backups/runs` | `backups:request` | `202` with `backup.run` |
| `GET /v1/backups/runs`, `/runs/{id}` | `backups:read` | `{id, action_id, reason, destination_id, state, started_at, finished_at, bytes_done, bytes_total, units: [{unit, state, snapshot_id?, error?}]}` |
| `GET /v1/backups/snapshots`, `/snapshots/{id}` | `backups:read` | `{id, unit, app_id?, node_id, destination_id, taken_at, size_bytes, reason, tags, verified_at}`; filters `?app_id&destination_id&since` |
| `GET /v1/backups/snapshots/{id}/tree?path=`, `/file?path=` | owner | directory listing `[{name, type: file\|dir, size, mtime}]`, or the file streamed; each read audited |
| `DELETE /v1/backups/snapshots/{id}` | owner | `202` with `backup.snapshot.delete` |
| `POST /v1/backups/verify` | `backups:request` | `202` with `backup.verify` |
| `GET /v1/backups/verifications` | `backups:read` | `[{id, snapshot_id, unit, mode, result: pass\|fail, probes, started_at, finished_at}]` |
| `POST /v1/restores` | `backups:request` (agents only with the explicit grant) | `202` with `backup.restore` (always `destructive`) |
| `GET /v1/restores`, `/restores/{id}` | `backups:read` | `{id, state, action_id, snapshot_id, scope, mode, target, started_at, finished_at, health_gate: {verdict, probes}}`; a restore whose fresh-signal gate fails ends `failed`, never `succeeded` |
| `POST /v1/onboarding/restore/candidates` | **setup mode only** (no owner yet), from the LAN | `{destination: {kind, config, sealed}, sealed_owner_key}` → `[{instance_id, box_name, generation, restore_points: [{run_id, taken_at, units, arch, k3s_version}]}]`; a box restore chosen here is recorded as the first audit entries of the restored box (`owner_initiated: true`, `phase: onboarding`) |

- `onemindd` local API (loopback only, H-24): `POST :7480/api/v1/backup/run {reason, wait}` → `{run_id, state}`, for the updater's pre-update snapshot.
- **restic tags** (normative, so a repository is readable without OneMind): `onemind`, `box=<instance_id>`, `gen=<n>`, `unit=<system|k3s|nats|app|node|fence>`, `node=<id>`, `run=<run_id>`, `reason=<…>`, and when relevant `app=<id>`, `rev=<n>`, `k3s=<version>`, `audit_head=<hash>`.

### 12.13 OS updates
| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/os/status` | `updates:read` | per node (`?node_id`): the heartbeat `update` object plus `{booted: {version, slot}, policy, window, postponed_until, available: {version, security, notes_url} \| null}` |
| `GET /v1/os/history` | `updates:read` | `[{node_id, from_version, to_version, started_at, state, verdict: committed\|image-bad\|environment-bad\|interrupted, snapshot}]` |
| `POST /v1/os/check` | `updates:request` | `202` with `os.update.check` (`read`, auto-approved) |
| `POST /v1/os/apply` | `updates:request` | `{node_id, version, reboot}` → `202` with `os.update.apply`; it runs as a job after approval, inside the window unless `reboot: now` |
| `POST /v1/os/postpone` | `updates:request` | `202` with `os.update.postpone` |
| `PUT /v1/os/settings` | owner (`updates:admin`) | `{node_id, channel?: security\|stable, policy?: auto\|notify\|off, window?: "HH:MM-HH:MM"\|"any"}` → `202` with `os.update.settings` |
| `POST /v1/os/rollback` | owner | `202` with `os.rollback` |

The security channel's on-box auto-install (§10.1, BD-09) stays: it is the owner's standing policy and each install it makes is audited `approved_by: "policy:os-security-auto@<rev>"`. `onemind update apply` at the console is audited as an owner approval with `approved_via: console`. Root at the console never approves gateway actions (F-9).

### 12.14 Notifications and alerts
An **alert** is a system condition with a lifecycle (one per `dedupe_key` while open). A **notification** is one person's inbox item. Channels deliver notifications.

**Alert record** (`onemind.alert/v1`): `{id, type, severity: info|warning|critical, title, body, subject, source_id, state: open|acknowledged|resolved, dedupe_key, opened_at, updated_at, resolved_at, occurrences, flapping, fix: {type, params} | null, learn_more_url}`.

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/alerts?state=open`, `GET /v1/alerts/{id}` | `alerts:read`, filtered by audience (owners: all; adults: apps they use; guests and children: their own apps and sessions) | alert records |
| `POST /v1/alerts/{id}/ack` | owner, adult | the alert; audited, not an action |
| `POST /v1/alerts/{id}/resolve` | owner; only for alerts without an automatic resolve condition | the alert |
| `POST /v1/alerts/{id}/fix` | owner, agent | `202` with the alert's `fix` filed as a normal request (owners may add `approve: true`) |
| `GET /v1/repairs` | owner | open `repair.*` alerts with their check slug and fix |
| `GET /v1/notifications` | the person | own inbox `[{id, severity, topic, title, body, link, source, action_id?, alert_id?, created_at, read_at}]`, filters `?unread&severity&topic&since` |
| `GET /v1/notifications/{id}` | the person | one item (what a push wakes the phone to fetch); `404` for anyone else's |
| `POST /v1/notifications/{id}/read`, `POST /v1/notifications/read-all` | the person | `200` / `{marked: n}` |
| `GET /v1/notifications/channels` | the person (own); owner (all) | `[{id, kind, label, content_level, verified, state, last_error?, owner_person_id}]`, never secrets |
| `POST /v1/notifications/channels`, `PATCH …/{id}`, `DELETE …/{id}` | the channel's person (`notifications:write`, direct, audited) | `{kind, label, config, content_level, secret?\|sealed?}` → `201`; secrets write-only |
| `POST /v1/notifications/channels/{id}/test` | the channel's person | `{delivered, latency_ms}` |
| `GET /v1/notifications/preferences`, `PUT …` | the person (own) | routing table (below); `ETag`/`If-Match` |
| `POST /v1/notifications/send` | `notifications:send` (plugin, agent, automation) | `{severity, topic, title, body, dedupe_key}` → `202`; no approval (changes no state), rate-limited and audited; the sender never picks channels or recipients |
| `POST /v1/push/registrations`, `GET /v1/push/registrations`, `DELETE …/{id}` | the person's device | `{platform: webpush\|unifiedpush\|apns, endpoint\|token, keys?, label}` |
| `GET /v1/push/vapid-public-key` | any principal | `{key}` |

- **Channel kinds:** `inapp` (the `/v1/events` stream), `webpush`, `unifiedpush` (ntfy), `apns` (through the iOS relay), `email`, `webhook`, `telegram`, `matrix`. **Content levels** `opaque` ("OneMind: new alert" only), `title` (title and severity), `full`; enforced in the channel worker. `apns` is always `opaque` (D-005).
- **Topics** form a fixed tree: `approvals`, `backups`, `updates`, `nodes`, `apps`, `storage`, `security`, `automation`, `plugin.<app-id>`. A plugin may send only under `plugin.<its-app-id>`. Bodies are plain text, at most 4 KiB.
- **Preferences:**
```json
{"quiet_hours": {"tz": "Europe/Berlin", "from": "22:30", "to": "07:00",
                 "except_severity": ["critical"], "except_topics": ["approvals"]},
 "routes": [{"match": {"topic": "approvals.*"}, "channels": ["chn_phone"]},
            {"match": {"severity": "critical"}, "channels": ["chn_phone", "chn_email"]}],
 "digest": {"enabled": true, "at": "08:00"}}
```
Notifications held during quiet hours are delivered as one summary when they end; `except_*` go through. An alert re-notifies at most once per 30 minutes per `dedupe_key` and severity; escalation notifies at once.
- **iOS relay** (separate service, own contract): `POST <relay>/v1/ping {device_token, opaque_id}` → `202`, nothing else.

### 12.15 Monitoring: app health, restarts, logs, node metrics
Core monitoring needs no metrics stack: it reads heartbeats, the Kubernetes API and k3s's bundled metrics-server. History beyond 24 h is a Market app (Prometheus-compatible) whose alerts arrive through a webhook into §12.14.

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/apps/{id}` | `apps:read` (shared apps only for guests and children) | the §11.4 catalog entry plus `{installed, status, node_id, current_revision, update_available?, health: {state: healthy\|unhealthy\|starting\|stopped\|unknown, checked_at, reason?}, components: [{name, ready, restarts, last_restart_at?, last_exit_reason?}], backup: <badge>, access: {roles, shared_with_me}}` |
| `GET /v1/apps/{id}/logs?component=&since=&tail=&follow=` | `logs:read` (owner, adult; agents and plugins only with `logs:read:<app-id>`) | `text/plain` lines, or SSE with `follow=1`; at most 2000 lines per request and 15 min per stream; each stream opened is audited |
| `GET /v1/apps/{id}/metrics` | `monitoring:read` | `{app_id, at, components: [{name, cpu_millicores, mem_mb, restarts}]}` (current values; `null` fields when metrics-server is absent) |
| `GET /v1/nodes/{node_id}/metrics?window=` | `monitoring:read` | `{node_id, source: metrics-server\|heartbeat, samples: [{at, cpu_pct, mem_used_mb, mem_total_mb, disk_free_gb, disk_total_gb}]}`; one sample per minute kept in memory, `window` ≤ 24 h (default 1 h); `cpu_pct` is null for leaf nodes without k3s |
| `GET /v1/monitoring/summary` | `monitoring:read` | `{nodes: {online, stale, offline}, apps: {healthy, unhealthy, starting, stopped}, open_alerts: {info, warning, critical}, storage: [{node_id, state}], at}` for the Home screen |

App status values (§3 `status`) gain `updating`, `reverting`, `drifted`, `stopped`. **Monitoring alerts** (opened by the gateway, resolved automatically): `app.unhealthy` (health check failing for 3 min), `app.crashlooping` (≥ 3 restarts in 10 min), `node.offline`, `node.degraded`, `disk.low` (< 10 % free on `/data`), `storage.degraded`, `backup.failing`, `update.rolled_back`. `system.check` runs the repair checks every 15 minutes and opens `repair:<slug>:<context>` alerts.

### 12.16 Audit: read, verify, checkpoint
The log stays hash-chained JSONL (§3); the API is read-only and nothing edits or deletes a record.

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/audit/events` | `audit:read` | `[{seq, ts, event, principal, action_id, data, prev_hash, hash}]` ordered by `seq`; filters `?after_seq&before_seq&event&principal_id&action_id&since&until&limit` |
| `GET /v1/audit/events/{seq}` | `audit:read` | one record |
| `GET /v1/audit/verify` | `audit:read` | `{ok, records, head: {seq, hash}, first_bad_seq, checked_at, last_checkpoint}`; `?from_seq` checks a range; a full check is cached 60 s |
| `GET /v1/audit/checkpoints`, `/checkpoints/{id}/proof` | `audit:read` | `{id, seq, hash, signed_at, key_id, signature, anchors: [{kind, ref, at}]}`; the proof is everything an off-box tool needs (signed statement and public key id) |
| `POST /v1/audit/checkpoints` | owner (`audit:admin`, direct) | `201` with a checkpoint over the current head (automatic ones run hourly and every N lines) |
| `GET /v1/activity` | `audit:read` (`:own` for agents) | read model over the audit: `[{at, kind, summary, action_id?, requester, approved_by?, outcome?, folded_count?}]`, filters `?node_id&app_id&requester_kind&type&cursor`; routine auto-approved runs are folded |

A checkpoint is `{instance_id, seq, hash, signed_at}` signed Ed25519 with a key kept outside the audit directory, published to `ONEMIND_AUDIT` and stored by the phone app, so a rewritten or cut log is caught off the box. Rotation (H-20) seals a segment with a checkpoint first.

### 12.17 Automation and standing approvals
| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/automation/rules`, `/rules/{id}` | `automation:read` | `{id, name, system, revision, enabled, trigger, conditions, actions, options, created_by, approval_policy_id, last_fired_at, breaker: closed\|open}` |
| `POST /v1/automation/rules`, `PATCH …/{id}` | owner direct (created **disabled**); agent or plugin → `202` with `automation.rule.create` / `.update` | |
| `POST …/{id}/enable` | owner (others request `automation.rule.enable`) | |
| `POST …/{id}/disable` | owner, or anyone with `automation:request` (turning a rule off is always safe) | |
| `DELETE …/{id}` | owner | `204` |
| `POST …/{id}/dry-run` | `automation:read` | `{would_request: [<plans>], policy_outcome: needs_approval\|auto_approved}`; no side effects |
| `GET /v1/automation/runs`, `GET /v1/automation/schedules` | `automation:read` | fires `{id, rule_id, fired_at, trigger_event_id, action_ids, outcome}`; next fire times |
| `GET /v1/approval-policies`; `POST`; `DELETE …/{id}` | read `actions:read`; create owner with step-up; delete owner | `{id, revision, allow: {types, requested_by, params?}, limits: {per_day}, window_id?, expires_at}` |
| `GET /v1/windows`; `PUT /v1/windows/{id}` | any; owner | maintenance windows; editing one a policy uses bumps that policy's revision |
| `POST /v1/hooks/{hook_id}` | no session; HMAC `X-OneMind-Timestamp` + `X-OneMind-Signature: sha256=<hex>` | `202 {event_id}`; 401 bad signature, 409 replay, 413 > 64 KiB, 429 > 60/min |

Triggers: exactly one of `{"schedule": {"cron", "tz"}}` (5 fields, at most once a minute), `{"event": {"type", "where", "for_s"}}`, `{"webhook": {}}`, `{"manual": {}}`. A rule only **requests**; a rule that names a `destructive` type is refused with `422` (F-11). A standing approval covers only `read` and `write` types, always expires (at most 90 days), covers an agent only when it names that agent exactly, and is recorded as `approved_by: "policy:<id>@<rev>"` together with the owner who created it. Standing approvals for `app.update` of `verified` apps with a passing scan, inside the window, are allowed (F-6).

### 12.18 Deployments and manifest additions
- `GET /v1/apps/{id}/revisions` (owner, adult, agent) → `[{n, created_at, source, images, plan_sha256, action_id, committed}]`; `GET /v1/apps/{id}/revisions/{n}` (owner) → the rendered objects.
- `POST /v1/deploy/bundles` (owner, or a token with `deploy:write`) takes `application/x-tar` ≤ 64 MiB → `201 {sha256, app_id, manifest, images_lock, findings}`; it refuses unpinned images. Installing a bundle is `app.install` with `bundle_sha256`, never policy-approved, and needs a passing on-box scan (§11.1, F-7).
- **Manifest** (`sdk/schema/onemind.app.schema.json` follows): `spec.health: {http: {port, path, expect}, deadline_s ≤ 1800}`; `spec.migrations: reversible|irreversible`; `spec.backup: {mode: hot|cold, pre, post, sqlite, exclude, restore: {post}, verify: {http}}`; `spec.settings: [{name, type, default, description, env}]`; `spec.secrets: [{name, description?, keys: [{key, kind?: api-key|password|token|url, description, required?, generate?}]}]` (values are never in the manifest; the sealed-input construction and the store are in `docs/leap/core/SECRETS.md`); `spec.components: [{name, workload, health}]`; `spec.agent` and `spec.plugin` (§12.6). `metadata.origin: market|private` is set by the gateway, never by hand. Every `exec.command` is an argv list run in the named container through the Kubernetes API; no host shell is involved.

### 12.19 MCP additions (extends §11.3)
Still `kind: agent` only and still **no approve, deny, policy, grant or token tool**. Tools are generated from operations tagged `x-onemind-mcp`; CI fails if an operation with `actions:approve` or any `:admin` scope is tagged. New tools: `get_action` (`GET /v1/actions/{id}`), `list_alerts` (`GET /v1/alerts?state=open`), `backup_status` (`GET /v1/backups/status`), `app_status` (`GET /v1/apps/{id}` without settings values), `app_logs` (`GET /v1/apps/{id}/logs?tail=200`, only with `logs:read:<app-id>`), `list_automations` (`GET /v1/automation/rules`), `preview_action` (`POST /v1/plans`), `withdraw_action` (`POST /v1/actions/{id}/cancel`, own requests), `propose_automation` (files `automation.rule.create`). `request_action` accepts every type §12.5 lets the agent's grant request, with `params` in place of only `app_id`. `tools/list` shows only the tools the grant allows.

### 12.20 CLI
`docs/leap/dev/CLI.md` §3 is the command tree (`onemind fabric qr|join|leave`, `onemind auto`, `onemind policy`, `onemind backup now`, `onemind restore`, `onemind audit verify`, `onemind tokens`, `onemind tls show|qr` …), built with cobra (F-8). The draft's verbs are aliases: `node join` = `fabric join`, `automations` = `auto`, `backup run` = `backup now`. Every write verb files the same action as the dashboard, and `--json` prints the API response.

### 12.21 Name resolution (DECISIONS-NEEDED §2)
| Topic | Binding name | Why |
|---|---|---|
| Risk classes | `read`, `write`, `sensitive`, `destructive`, `actuate` (§12.3) | API.md; they say what the action does and standing approvals key on them. The draft's scale maps read→low, write→medium, sensitive→high, destructive and actuate→critical |
| Live stream | `GET /v1/events` | API.md; SDKs and CLI use it |
| Approval challenge | `POST /v1/actions/{id}/approve-options`, field `webauthn`, 120 s | API.md and SECURITY.md |
| Plan preview | `POST /v1/plans` before a request; `GET /v1/actions/{id}/preview` for the card | both, as proposed |
| Approval binding | `plan_sha256`: optional for v0 clients (`plan_unchecked` audited), required with `OneMind-API-Version: 1` | as proposed |
| Principal kinds | `plugin`, `automation`, `node` added together | as proposed |
| Error codes | union: `rate_limited`, `unavailable`, `payload_too_large`, `policy_refused`; `invalid_request` and `method_not_allowed` only with `OneMind-Errors: 2`; optional `reason` | as proposed. API.md's `offline_not_supported` (409) is **not** added: the architecture draft folds it into `unavailable` (503, `node_offline`) because an offline node is a retryable dependency failure, not a state conflict |
| List shape | arrays plus `Link` header pagination | API.md; the SDK iterators rely on it |
| Scopes | API.md §8.2 names; `:own`/`:all`, `:<type>`, `:<app-id>` are narrowing suffixes; `actions:read:self` → `actions:read:own`; `alerts:raise` → `notifications:send` | as proposed |
| Manifest principals | `spec.agent.scopes`; `spec.plugin` + `spec.permissions` | as proposed |
| CLI verbs | CLI.md §3 tree; draft verbs are aliases | as proposed |
| Join flow | `/v1/fabric/join-tickets` + `/v1/fabric/join-requests`, `join_code`, `csr_pem`; credential bundle contents from the draft (node cert, NATS, job key, k3s, mesh) | API.md names; the draft's bundle is what the node needs |
| Ticket role | `worker\|leaf` (`node` accepted as `worker`) | the architecture draft: a leaf runs no k3s, so the ticket must say which |
| Alerts vs inbox | `/v1/alerts` for system alerts; `/v1/notifications/*` for inbox, channels and preferences; `/v1/push/*` for devices | DECISIONS-NEEDED §4 proposal; the draft's `/v1/notify/*` and `/v1/me/…` paths are not used |
| Channel changes | direct, audited writes by the channel's person | API.md P3: own settings; the draft's `notify.channel.*` actions are not used |
| Automation | `/v1/automation/rules`, `/v1/approval-policies`, `automation.rule.*` | API.md (settled 2026-11-12, DECISIONS-NEEDED §3) |
| Backups | `destinations` (not `targets`), `/v1/restores`; badges from the draft | API.md names; the badge is the architecture's verify rule |
| Updates | `/v1/os/status\|history\|check\|apply\|postpone\|settings\|rollback`, `os.update.*`, `os.rollback` | API.md |
| Audit | `/v1/audit/events\|verify\|checkpoints`; the draft's `/v1/audit/status` is `GET /v1/audit/verify` | API.md |
| Heartbeat mesh | top-level `mesh: {state, path}` | one object per subsystem, like `update`, `backup`, `storage`; NETWORKING.md's proposed `fabric.mesh` moves here |
| Decider field | `approved_by` | SDK names (DECISIONS-NEEDED §3) |
