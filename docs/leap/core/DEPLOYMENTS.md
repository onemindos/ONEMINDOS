<!-- SPDX-License-Identifier: Apache-2.0 -->
# Deployments: running your own services (CORE-DEPLOY)

**Date:** 2026-11-12 · **Status:** proposal · **Plan epic:** none yet (added by the founder focus of 2026-11-12) · **Deeper docs:** `docs/architecture/DEPLOYMENTS.md` (architecture stream, branch `docs/core-architecture`, in progress); core-alignment §4.4 (DEP-P1…P3, DEP-B1, DEP-B2) · **Serves:** brief 30 E1 (Compose importer `onemind app import`); contract §3, §9.4, §11.1.

> **Explain it like I am the founder**
> Market apps are other people's software. Deployments are **yours**: a folder with Kubernetes files, a Helm chart or a Compose file, turned into a private OneMind app.
> It goes through the same fence and scan as a Market app, waits for your approval, and every version is kept so you can roll back in one step.
> Secrets you give it are stored on the box and never shown back, not even to you.

## 1. Goals and non-goals

| Goals | Non-goals (now) |
|---|---|
| `onemind deploy <dir \| git-url>` from kustomize, Helm or Compose → private app | Building images from source on the box (use your own CI; push to a registry) |
| Same sandbox (SANDBOX) and scan rule as Market apps; scan runs on the box | A hosted CI service |
| Deploy history per service; one-step rollback to the previous digests | Blue/green or canary per service (later) |
| Secrets sealed on the box, write-only | A general secrets vault UI (Vault module, APPS.md) |
| Watched Git source: a new commit becomes a pending action with a diff | Auto-deploy without approval (only via standing approval, AUTOMATION) |
| Migration kit: import existing manifests, check, run side by side, switch | Importing cluster-scoped resources |

## 2. What exists today

| Piece | Where | State |
|---|---|---|
| Executor applies a kustomization into `app-<id>` | `core/onemind_core/executors.py` | `main` |
| Manifest schema, validator | `sdk/schema/onemind.app.schema.json`, `sdk/tools/validate-apps` | `main` |
| `app-gate` (licence, pinning, Trivy, ClamAV, secrets, manifests, smoke) and `scan.json` | `sdk/tools/app-gate` | `feat/app-pipeline` |
| Scan gate at approve | `core/onemind_core/scan.py` | `feat/gateway-agent-mcp` |
| No Git source, history, rollback or secret handling | – | not built |

## 3. Design

### 3.1 A private app
`onemind deploy` writes a normal manifest with `metadata.tier: private` and stores the rendered bundle on the box under `/data/onemind/deploys/<id>/<revision>/`. Private apps never appear in the public catalog.

```console
$ onemind deploy ./notes-service --name notes
Detected     kustomize (3 objects: Deployment, Service, PersistentVolumeClaim)
Images       registry.example.org/me/notes:1.4.0 → pinned @sha256:7d0e…
Rules        ok (rules v1)
Scan         queued on the box (job scan-notes-r3)…  trivy 0 critical · clamav clean · secrets 0
Action       a_77  deploy.apply  notes r3  awaiting_approval → approve on your phone
```

```console
$ onemind deploy ./compose.yaml --name paperwork     # Compose → generated kustomization (kompose-style, E1)
Generated    apps-private/paperwork/manifests/ (review with --dry-run)
Warnings     ports: 8000 → served at https://paperwork.onemind.local (no host port)
             volume ./data → PVC paperwork-data 10Gi on onemind-local
```

### 3.2 On-box scan (CORE-DEPLOY-2)
The gateway runs a Job in namespace `onemind-scan` with the pinned Trivy and ClamAV images from `os/versions.lock.yaml`, writes `scan.json` bound to the rendered hash and image digests (H-08), and only then lets the action be approved. "Nothing unscanned installs" (contract §10.3) holds for private apps too. Offline boxes need a current signature database; if it is older than 7 days the scan is `fail` with the reason.

### 3.3 History and rollback (CORE-DEPLOY-3)
| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/deploys` | any principal | private apps with current revision |
| `GET /v1/deploys/{id}/revisions` | owner, adult | `[{rev, created_at, digests, rendered_sha256, scan, approved_by}]` |
| `POST /v1/actions {"type": "deploy.apply", "params": {"deploy_id", "rev"}}` | owner or agent request | owner approval |
| `POST /v1/actions {"type": "deploy.rollback", "params": {"deploy_id", "to_rev"}}` | owner or agent request | owner approval; re-applies the stored, already-scanned bundle |

```console
$ onemind deploy history notes
REV  WHEN              IMAGES              SCAN  APPROVED BY
r3   2026-11-20 10:02  notes@sha256:7d0e…  pass  person:owner
r2   2026-11-18 21:40  notes@sha256:19bb…  pass  person:owner
$ onemind deploy rollback notes --to r2
action a_78  deploy.rollback  awaiting_approval
```

```python
client.actions.request("deploy.rollback", deploy_id="notes", to_rev="r2")          # Python
```
```ts
const revs = await om.deploys.revisions("notes");                                 // TypeScript
```
```go
_, err := om.Actions.Request(ctx, onemind.Action{Type: "deploy.apply",
          Params: map[string]any{"deploy_id": "notes", "rev": "r3"}})            // Go
```
**MCP:** an agent can request `deploy.apply` or `deploy.rollback` for an existing private app; it cannot create a new private app or set secrets.

### 3.4 Secrets (CORE-DEPLOY-4)
```console
$ onemind secret set notes DATABASE_URL       # reads the value from the terminal, no echo
stored  notes/DATABASE_URL  (write-only; referenced as secretRef notes-env)
$ onemind secret list notes
NAME           SET AT             BY
DATABASE_URL   2026-11-20 09:58   person:owner
```
Values go straight into a k8s Secret in `app-<id>` (encrypted at rest, CORE-SEC-5) and into backups; they are never returned by any API. Setting a secret is an owner-only direct call (it changes data, not power); an agent can never set or read one.

### 3.5 Watched Git source (CORE-DEPLOY-5, DEP-B1)
`onemind deploy watch notes --git https://example.org/me/notes.git --path deploy/ --branch main`: the gateway polls (or receives a signed webhook, AUTOMATION), renders the new commit, scans it, and creates a `deploy.apply` action whose card shows the diff of rendered objects and digests. The box stores the commit SHA, never follows a branch blindly.

### 3.6 Migration kit (CORE-DEPLOY-6, DEP-B2)
`onemind migrate check <dir>` reads existing manifests or Helm values and reports: cluster-scoped objects (refused), unpinned images, missing limits, storage classes (→ `onemind-local`), ingress (→ gateway proxy), secrets (→ `onemind secret set`). `onemind migrate import` produces a private app; the owner runs old and new side by side, then switches DNS. See [DOGFOOD.md](DOGFOOD.md).

## 4. Security model
- Same fence as Market apps (SANDBOX): kind allowlist, PSA restricted, own namespace, default-deny network.
- Approval binds to `rendered_sha256` and digests; rollback re-applies a stored bundle whose scan is re-checked for age (a 7-day-old scan is rescanned first).
- Private registries: pull credentials are a secret of the app, never global.
- Owner override for a failing scan: none in v0 (founder decision F-7).

## 5. Versioning and compatibility
- `metadata.tier: private` added to the schema enum; contract §3 gains `deploy.apply`, `deploy.rollback`; `/v1/deploys` is additive.
- Revisions are kept until the owner prunes them (default: last 10); pruning is a `deploy.prune` action.
- Generated manifests carry `generatedBy: onemind-deploy/<version>` so a later converter can upgrade them.

## 6. Test plan and acceptance

| Test | Pass when |
|---|---|
| Kustomize, Helm and Compose fixtures | Each becomes a private app that passes rules and installs on k3d |
| Forbidden object in a private app | Refused exactly like a Market app |
| Unscanned | Approval of a private app without a passing on-box scan → 409 `stale_precondition` |
| Rollback | r3 → r2 restores the r2 digests; audit shows both actions |
| Secret | `GET` on any route never returns a secret value; agent token gets 403 on `secret set` |
| Git watch | A new commit creates one pending action with a non-empty diff; a force-push to an old commit is shown as a downgrade |

## 7. Build steps

| Epic | Step | Effort | Depends on |
|---|---|---|---|
| CORE-DEPLOY-1 | `onemind deploy` (kustomize, Helm, Compose) → private app | M | SANDBOX-2 |
| CORE-DEPLOY-2 | On-box scan Job + scan bound to digests | M | 1, `feat/app-pipeline` |
| CORE-DEPLOY-3 | Revisions, history, rollback | M | 1 |
| CORE-DEPLOY-4 | Write-only secrets | S | SEC-5 |
| CORE-DEPLOY-5 | Watched Git source with diff card | M | 3, AUTO-2 |
| CORE-DEPLOY-6 | Migration kit (`onemind migrate check\|import`) | M | 1 |

## 8. Who owns which files

| Branch (proposed) | Files |
|---|---|
| `feat/deploy-own` | new `core/onemind_core/deploys.py`, `cmd/onemind/cli/deploy.go`, `cmd/onemind/cli/secret.go`, new `sdk/tools/compose-import/` |
| `feat/onbox-scan` | new `core/onemind_core/scanjob.py`, scanner pins in `os/versions.lock.yaml` |
| `feat/migrate-kit` | `cmd/onemind/cli/migrate.go`, reuse of `sdk/policy/check.py` |
| Hotspots (serialized) | `core/onemind_core/app.py`, contract §3, schema (`tier: private`), `os/versions.lock.yaml` |
