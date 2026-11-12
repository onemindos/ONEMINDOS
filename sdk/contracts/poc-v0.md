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
