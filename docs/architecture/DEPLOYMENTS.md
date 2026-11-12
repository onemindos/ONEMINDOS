<!-- SPDX-License-Identifier: Apache-2.0 -->
# Deployments: core services, apps and your own services

**Status:** design for build agents (2026-11-12). API in [CONTRACT-12-DRAFT.md](CONTRACT-12-DRAFT.md) §12.6.
**Backlog:** core-alignment items 11 (APP-P1, APP-P2, APP-P3), 12 (APP-B1), 13 (DEP-P1, DEP-P2, APP-P4), 14 (DEP-B2); also 10 (OSU-P1, UX-P5) for the OS side.
**Builds on:** contract §3 (actions, kustomize executor), §9–§11 (catalog, scan gate, agent principals); brief 30 B4 (OS updates), E1 (market controller), B6 (hardening); `core/onemind_core/executors.py`; hardening backlog H-02 (manifest allowlist), H-03 (gateway RBAC), H-04 (default-deny network), H-08 (scan bound to digest), H-13 (plan card).

> **In plain words.** There are two kinds of software on a OneMind box. The **core** (gateway, message bus, node agent, Kubernetes itself) is part of the operating system image: it is updated only as a whole new OS version, which rolls back by itself if the box is not healthy afterwards. **Apps** (from the Market or your own) run inside Kubernetes. Every app install, update, setting change or rollback creates a numbered **revision**: an exact, stored copy of what was applied. Updating an app snapshots its data first, checks it is healthy afterwards, and puts the old version back by itself if not. Nothing is applied without an approval you can see.

## 1. Requirements

| ID | Requirement | Source |
|---|---|---|
| D-R1 | Core services are updated atomically with the OS and covered by the health gate | B4, B5 |
| D-R2 | Every app change produces an immutable revision with the exact rendered objects and image digests | DEP-P2, H-13 |
| D-R3 | App lifecycle: install, update, configure, restart, logs, rollback, remove (keeps data), delete data | APP-P1…P3 |
| D-R4 | App updates are health-gated with a pre-update snapshot and automatic revert | APP-B1 |
| D-R5 | Drift between the revision and the cluster is detected and shown; correction is an action | gap list "desired state with drift detection" |
| D-R6 | Your own services deploy from a kustomization, Helm chart or Compose file through the same path (`onemind deploy`) | DEP-P1, APP-P4 |
| D-R7 | Owner-entered secrets are collected by the dashboard at install and stored encrypted, never printed as a shell command | gap list "secrets management" |
| D-R8 | A migration kit imports existing Kubernetes manifests, checks them, runs side by side and switches over | DEP-B2 |
| D-R9 | Nothing reaches the cluster without passing the policy checks (allowlist, pinning, limits, PSA) | H-01, H-02, §10.3 |

## 2. Core services vs apps

### 2.1 Core services (systemd, in the image)

| Service | Where | Why not in k3s |
|---|---|---|
| `onemind-gateway` (FastAPI; serves the dashboard build) | hub | It repairs, restores and updates k3s, so it must run when k3s does not |
| `onemind-nats` | hub (+ leaf on every node) | The bus carries heartbeats and jobs that diagnose a broken k3s |
| `onemindd` (node agent, updater, backup agent, custodian on the hub) | every node | Host-level work: files, restic, RAUC, keys |
| `k3s` (server / agent) | hub / workers | It *is* the runtime |
| identity provider (SEC-P1; BD-03 names Kanidm) | hub | Login must work when k3s is down; placement is decided in the identity design |

**How they update:**
- **Image installs (P1–P3):** only through a signed RAUC bundle from the TUF channel (`internal/update`, `os/update/CHANNEL.md`). Gateway, dashboard and `onemindd` versions equal the OS version. The health gate (`os/gate/onemind-health-gate`) checks fresh signals and rolls back the whole slot. So a broken gateway release cannot strand the box: the previous slot boots with the previous gateway.
- **Developer installs (P6):** `deploy/install.sh` re-run on a newer checkout; pinned versions in `deploy/pins.env`; labelled "no OS rollback" (REC-DEC-30). `onemind self-check` (later) compares the running versions with the pins.
- **Schema migrations** of the gateway database run at gateway start, forward only, and a migration that cannot be undone sets a **data-migration hold**: the updater will not commit a slot until the gateway reports the migration finished (brief 30 B4.2 "data-migration hold", listed open in `internal/update/README.md`).

### 2.2 The platform layer (k3s objects owned by the OS)

Shipped in the image under `/usr/share/onemind/platform/` (one kustomization), versioned with the OS, and **reconciled by the gateway** at start and every 10 minutes with server-side apply (field manager `onemind-platform`):
- StorageClasses `onemind-local` (default, Retain) and `onemind-scratch` (BACKUPS.md §2.1);
- PriorityClasses `onemind-system`, `onemind-app`;
- the Ingress or Gateway API routes for the gateway and for each app's subdomain (SEC-P2, UX-P2);
- namespace template labels (PSA `restricted` for `app-*`, H-01).

These are not actions: they were approved when the OS update was. A difference found by the reconciler is fixed **and** raised as a repair alert ("platform object changed outside OneMind"), because someone changed it by hand.

### 2.3 Apps (k3s, namespace `app-<id>`)

Market apps (contract §4, §9) and private apps (§6) use one path: **render → check → plan → approve → apply → verify → record**.

## 3. The render pipeline (gateway)

```
onemind.app.yaml + manifests/ (or a private bundle)
  │ kustomize build (pinned kustomize in the image)
  ▼
policy checks (H-02 allowlist; one rule file shared with sdk/tools/app-gate)
  - kinds allowed: Deployment, StatefulSet, Service, ConfigMap, PersistentVolumeClaim, Job, CronJob, ServiceAccount, Role/RoleBinding (namespaced), NetworkPolicy (adds only)
  - no hostPath, hostNetwork, privileged, hostPID/IPC (brief 30 E2 grants come later)
  - every image pinned by digest; digest matches scan.json (H-08)
  - requests and limits on every container
  │
  ▼
OneMind overlay (added by the gateway, never by the app)
  - namespace app-<id>; labels app.kubernetes.io/managed-by=onemind, onemind.io/app=<id>, onemind.io/revision=<n>
  - default-deny NetworkPolicy + egress the manifest declares (H-04)
  - storageClassName onemind-local where unset; nodeAffinity from placement (FABRIC.md §7)
  - automountServiceAccountToken: false unless the manifest asks; securityContext defaults for restricted PSA
  - Secrets from the secret store (§7) and, for agent apps, the §11.2 Secret
  │
  ▼
plan (H-13): objects by kind, images + digests, ports, volumes + sizes, egress, node, diff vs current revision
plan_sha256 = sha256(canonical rendered objects)
```

The plan is stored with the action. **Approval binds to `plan_sha256`.** If anything changes between request and approval (manifest, catalog, placement), a fresh render gives another hash and approval returns `409 stale_precondition` (reason `plan_changed`). The card then shows the new plan.

## 4. Revisions, apply, drift and rollback (GitOps-lite)

**Why "GitOps-lite":** GitOps tools (Argo CD, Flux) keep a cluster equal to a Git repository and correct drift automatically. On a home box, automatic correction means a change nobody approved. OneMind keeps the good part, a declared, versioned desired state, and makes every change and every correction an action.

**Revision** = `{app_id, n, source (catalog version | bundle sha256), manifest digest, rendered objects (stored as one YAML file by sha256 under /data/onemind/deploy/revisions/), images with digests, config values hash, placement, plan_sha256, created_by_action}`. Revisions are immutable and kept (last 20 per app, plus any referenced by a snapshot).

**Apply:** `kubectl apply --server-side --field-manager=onemind` of the rendered objects. Then **explicit deletion**: objects that were in the previous revision and are not in the new one are deleted by name. kubectl's `--prune` with ApplySets is still alpha (`KUBECTL_APPLYSET=true`); computing the deletion set from two stored revisions is deterministic and shows up in the plan.

**Drift:** every 10 minutes, the gateway compares live objects with the current revision (server-side dry-run diff, fields owned by `onemind`). The app's state becomes `drifted` with the differing fields, and an alert is raised. Correction is `app.reconcile` (re-apply the current revision). Per app, the owner can set a policy that auto-approves `app.reconcile` (AUTOMATION.md).

**Rollback:** `app.rollback {to_revision}` re-applies a stored revision, so images come back by digest. Data is not touched. If the newer version migrated the data, the plan warns, and offers `backup.restore` of the matching pre-update snapshot as the second step.

## 5. App updates, health-gated (APP-P1, APP-B1)

**Finding updates:** the catalog sync (contract §10.2) brings a new version. The app row gets `update_available: {version, channel, released_at, notes_url, scan}`. Policy per app (`spec.updates` in the manifest is the publisher's default; the owner overrides): `off`, `security` (auto-approve security-channel patches in the window), `all`.

**`app.update {app_id, to_version}` steps:**
1. Preflight: scan fresh and bound to the new digests (§10.3, H-08); placement still fits; enough disk for the snapshot.
2. Pre-update snapshot of the app's volumes (`backup.run` unit `app:<id>`, reason `pre-update`). If backups are not set up: the plan says "no snapshot: automatic data revert impossible" and the approval must acknowledge it. Policies never auto-approve that case.
3. Apply the new revision.
4. **Health gate** (the OS gate's rule brought to apps): wait for rollout of every Deployment and StatefulSet; then the app's checks with fresh signals only. That means pods whose `creationTimestamp` is after step 3, readiness as observed now, and the manifest's `health:` checks (default: HTTP 200 on `web.port`). They must pass 3 times in a row over 60 s, within a deadline (default 10 min, manifest may raise it to 30).
5. Pass → revision committed, action `succeeded`.
6. Fail → **automatic revert:** re-apply the previous revision. If the manifest declares `migrations: irreversible`, or the old version then fails its own health gate, restore the pre-update snapshot (owner policy `revert_data: auto` (default) or `ask`). Result `failed` with `reverted: code|code+data`, and an alert naming the failed check.
7. Revert itself fails → `outcome_unknown`, app state `unknown`, critical repair alert. No further automatic attempts.

StartOS restores data when an app update fails ([C-TD-startos-022]); Cloudron, YunoHost and Runtipi back up before updates (core-alignment §4.3). Gating on fresh health after the update and reverting by itself is the part none of them does.

## 6. Your own services (`onemind deploy`, DEP-P1, APP-P4)

```
onemind deploy ./myservice            # kustomization.yaml, Chart.yaml or compose.yaml in the folder
onemind deploy ./myservice --dry-run  # render + checks + plan only
onemind deploy history myservice
onemind deploy rollback myservice --to 3
```

1. **On the developer's machine (CLI):**
   - Detect the input. A Helm chart is rendered with a pinned `helm template` (values file allowed). Compose is converted to Kubernetes objects by `onemind app import` (one Deployment + Service per service, PVCs for named volumes, Secrets declared from `env_file`). That is a OneMind converter: kompose's approach, our code (brief 30 E1).
   - Generate or update `onemind.app.yaml` with `metadata.origin: private`.
   - **Resolve every image tag to a digest** from the registry and write `images.lock`.
   - Pack the folder as a tar with a sha256.
2. `POST /v1/deploy/bundles` uploads the tar (owner session or a deploy token with `deploy:write`).
3. The CLI creates `app.install` or `app.update` with `{app_id, bundle_sha256}`. The gateway runs the same pipeline (§3). **Scanning:** Market apps carry `scan.json` from CI. Private bundles have none. In v0 the approval must acknowledge "not scanned" (`acknowledge_unscanned: true`, bound into the plan). Phase D6 adds an on-box scan with the pinned Trivy run as a Job. **FOUNDER CALL:** whether v0 may run unscanned private images at all. The recommendation is yes for owner-deployed bundles only, never for agent-requested ones.
4. Approve (dashboard, phone, or `onemind actions approve`). The output streams rollout progress.

**Multi-component services:** one bundle may hold several workloads. The manifest's optional `spec.components: [{name, workload, health}]` gives per-component health and logs.

**Watched Git source (DEP-B1, later):** a registered repository and branch. A new commit becomes a pending `app.update` with the diff, digests and scan, ready to approve from the phone. Never an automatic deploy.

## 7. Secrets and settings

- **Manifest declares, owner supplies:** `spec.secrets: [{name, keys: [{key, description, required, generate?}]}]`. At install the dashboard shows a form; values go in the action's **sealed input**: encrypted to the gateway's secret-store key in the browser, never in the plan, the audit log or the action JSON (only `sha256` of each value, so a change shows in the plan). `generate: true` creates a random value on the box. This replaces the printed `kubectl create secret` for Hermes (contract §7).
- **Store:** `secrets(app_id, name, key, ciphertext, nonce, version, updated_at)`. AES-256-GCM, with a key derived from the device key (BACKUPS.md §6.4). They are written into the namespace as Kubernetes Secrets at apply time; k3s secrets encryption at rest is on (H-12).
- **Settings:** `spec.settings` is a typed list (`string|int|bool|enum`, default, description, `env` name). `app.configure {app_id, values}` makes a new revision; the plan shows the changed settings. Secret values are changed with `app.configure` too, through sealed input.
- **Never shown back:** the API returns secret names and `set: true|false`, never values (Coolify redacts secrets in its MCP tools too; core-alignment §4.8).

## 8. Restart and logs (APP-P3)

- `app.restart {app_id, component?}`: rollout restart. Low risk, policy-eligible.
- `GET /v1/apps/{id}/logs?component=&since=&tail=` returns lines through the Kubernetes API. It needs `get pods/log` in that namespace through the gateway's per-app RoleBinding (H-03). `?follow=1` streams as server-sent events (SSE). Capped at 2000 lines per request and 15 minutes per stream.
- Who: owner and adult. Agents only with the grant `logs:read` for that app (H-22), because logs can contain secrets.

## 9. Migration kit (DEP-B2)

For moving services from an existing Kubernetes cluster without guessing.

| Command | Does |
|---|---|
| `onemind migrate check <dir>` | Static report on exported manifests or a Helm values folder: unsupported kinds (CRDs, cluster roles, DaemonSets, host mounts), missing limits, unpinned images, PVCs and their sizes, Ingress hosts, Secret references. Every finding has severity and a fix hint. Runs offline on the developer's machine |
| `onemind migrate import <dir> --group-by namespace` | Writes one `onemind.app.yaml` folder per group: PVCs → `onemind-local`; Ingress → `spec.web` + exposure request; Secrets → `spec.secrets` declarations **without values** (the owner re-enters them; sealed or plain values from the old cluster are never imported) |
| `onemind deploy <folder>` | Installs on the box **side by side** with the old cluster |
| `onemind migrate copy-data --pvc <ns>/<name> --to <app>/<pvc>` | Copies data through the backup system. The box issues a time-limited, append-only rest-server user for a `migration` repository. The CLI runs a one-off restic Job in the **old** cluster (with the user's own kubeconfig) that backs up the PVC to the box. The box then restores it as a normal approved `backup.restore`, and can run a **verified restore** before switch-over |
| `onemind migrate cutover <app>` | Plan: stop the old writer (instructions or a scale command for the user to run), final delta `copy-data`, restore, health gate, then "switch DNS / ingress now" with the exact record to change. Old resources are left untouched for the owner to remove |

Why copy through restic: it reuses the tested restore and verification path, it is resumable, and the box never needs credentials for the old cluster. The old cluster's credentials stay on the developer's machine.

## 10. OS updates in the UI (OSU-P1, UX-P5)

The updater already exists on the box (`internal/update`). This design adds the gateway side that its README lists as open ("Gateway approval … the `/v1/os/*` gateway API … come later"):
- `GET /v1/os/updates`: per node, from the heartbeat `update` object: booted slot, version, channel, policy, window, postpone-until, available release with notes URL and security flag, state, last result, history.
- Actions `os.update.apply {node_id, version}` and `os.update.postpone {node_id, until}`, plus `os.update.policy {node_id, channel, policy, window}`, carried to the node as jobs. The updater's own auto-install for the security channel stays (BD-09). It is shown as "installed automatically by your policy" in the activity feed, with the policy named.
- After a committed update, the dashboard shows "What's new" from the release notes once per user (UX-P5).
- Multi-node rollout: FABRIC.md F6.

## 11. Data model (gateway database)

```
app_installs(app_id PK, origin[market|private], current_revision, status, placement_node,
             update_policy[off|security|all], revert_data[auto|ask], drift_state, drift_json, updated_at)
app_revisions(app_id, n, source_json, objects_sha256, objects_path, images_json, settings_hash,
              secrets_hashes_json, placement, plan_sha256, action_id, created_at, committed bool)
deploy_bundles(sha256 PK, app_id, uploaded_by, size, path, created_at)
secrets(app_id, name, key, ciphertext, nonce, version, updated_at)
```

`app_state` in `ledger.py` stays the status source. `app_installs.status` gains `updating`, `reverting`, `drifted`, `stopped`.

## 12. Security

- One rule file for what an app may contain, enforced in CI (`app-gate`) and again on the box (H-02). The box never trusts that CI ran.
- Approval binds to the exact rendered plan (`plan_sha256`). Agents can request but never approve, and policies never cover `app.install` of unscanned bundles, `app.data.delete` or exposure changes.
- The gateway's Kubernetes rights are per-app RoleBindings plus namespace create and delete (H-03), not cluster-wide `admin`.
- Secrets are sealed from the browser to the store and never returned.
- Private bundles are owner-uploaded and digest-pinned. Unscanned ones are labelled everywhere they appear.

## 13. Test plan and acceptance criteria

| # | Test | Pass when |
|---|---|---|
| DT-1 | Install a seed app (k3d in CI, as §9.4 smoke) | Revision 1 stored; objects carry the overlay labels, default-deny policy and affinity; `plan_sha256` in the audit line |
| DT-2 | Manifest edited between request and approval | Approve → `409 stale_precondition` (`plan_changed`); the new plan has a new hash |
| DT-3 | Update with a broken new version (a fixture image that fails readiness) | Revision 2 applied, health gate fails, revision 1 re-applied, app healthy, action `failed` with `reverted: code`, alert raised |
| DT-4 | Update with `migrations: irreversible` that fails | Data restored from the pre-update snapshot; files match the snapshot |
| DT-5 | Drift | `kubectl scale` by hand → `drifted` within 10 min with the field named; `app.reconcile` restores it |
| DT-6 | Rollback | `app.rollback --to 1` restores revision 1's images by digest |
| DT-7 | Policy checks | A bundle with `hostPath`, an unpinned image, or no limits is refused at render with a named rule |
| DT-8 | `onemind deploy` with compose | A two-service compose file becomes one app with two components, digests in `images.lock`, installs after approval, `history` shows it |
| DT-9 | Secrets | The value entered in the form appears in the pod's env; it does not appear in the action JSON, audit log, plan or any API response; changing it creates a new revision |
| DT-10 | Remove keeps data | `app.remove` then `app.install` of the same app finds the old data; `app.data.delete` removes it after a final snapshot |
| DT-11 | Migration kit (k3d "old cluster" with a PVC app) | `check` reports the findings; `import` + `deploy` run side by side; `copy-data` + restore gives identical files; cutover plan names the DNS change |
| DT-12 | Platform drift | Deleting the `onemind-local` StorageClass by hand → restored within 10 min plus a repair alert |
| DT-13 | Core update rollback (QEMU battery) | A bundle with a gateway that fails to start → gate rolls back; the previous gateway serves `/healthz` |

## 14. Build steps

| Step | What | Size | Depends on |
|---|---|---|---|
| D1 | Platform layer reconciler (§2.2) + render pipeline with H-02 checks, overlay, plan and `plan_sha256` on approval | M | gwmcp merged, H-02 rule file |
| D2 | Revisions store, server-side apply + explicit deletion, `app.rollback`, `app.restart`, logs API, remove keeps data, `app.data.delete` | M | D1 |
| D3 | Settings and sealed secrets (`spec.settings`, `spec.secrets`, `app.configure`); Hermes credentials through the form | M | D2, SEC-P1 |
| D4 | Health-gated `app.update` with pre-update snapshot and revert; update policies per app; app page "update available" | M | D2, BACKUPS K3 |
| D5 | `onemind deploy` (kustomize, Helm, compose import), bundles, history; drift detection + `app.reconcile` | M | D2 |
| D6 | On-box scan of private bundles (Trivy Job, pinned) | S | D5 |
| D7 | Migration kit (`check`, `import`, `copy-data`, `cutover`) | M | D5, BACKUPS K5/K6 |
| D8 | OS updates screen + `os.update.*` actions over jobs; "What's new" | S | updater merged, FABRIC F4 |
