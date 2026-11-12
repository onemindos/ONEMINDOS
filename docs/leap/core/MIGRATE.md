<!-- SPDX-License-Identifier: Apache-2.0 -->
# Migration kit: moving off your current cluster (CORE-DEPLOY-6)

**Date:** 2026-11-12 · Part of [the leap](../README.md) · **Branch:** `feat/migrate-kit` · **Serves:** BACKLOG S3 CORE-DEPLOY-6 and CORE-DOGFOOD-2; [DEPLOYMENTS.md](DEPLOYMENTS.md) §3.6; [DOGFOOD.md](DOGFOOD.md) §3–§4.1; `docs/architecture/DEPLOYMENTS.md` §9 (DEP-B2, test DT-11).

> **Explain it like I am the founder**
> You already run apps on a Kubernetes cluster. This kit moves one namespace at a time onto the OneMind box.
> 1. **Plan.** You give the box a key to the old cluster that can only *look* at one namespace. The box reads it and tells you, line by line, what moves as it is, what it changed (for example: the exact image version is locked), what you must re-enter (passwords are never copied), and what blocks the move. Nothing changes anywhere.
> 2. **Import.** After you approve, the box creates the app with its storage, but starts nothing.
> 3. **Copy.** After you approve, a small helper runs next to your old app, reads its data without changing it, and sends it to the box. The box checks every single file against a fingerprint (sha256). Then the new app starts. Old and new now run **side by side**, so you can try the new one.
> 4. **Switch over.** After you approve, the old app is stopped, the last changes are copied and checked again, and the new app takes over. If anything does not match, both go back to running side by side. The old app is left in place (stopped) so you can **revert** in one step. Anything written to the new app after the switch-over is not in the old app; it stays on the box until the next copy replaces it.
>
> Every step after the plan waits for your approval. An AI agent can read plans but cannot start a step.

## 1. The flow

```console
$ onemind migrate role --namespace notes --copy --cutover | kubectl apply -f -     # on the OLD cluster
$ # make migrate.kubeconfig with the recipe printed at the top of that output (token, 8 hours)
$ onemind migrate plan --hub http://box.local:8080 --kubeconfig migrate.kubeconfig --namespace notes
Plan    mig_01JD…  namespace notes → private app notes ("notes")
MOVE    Secret/notes-env               values are never imported (API_KEY)
          ↳ set them on the box: onemind secret set notes <KEY> (CORE-DEPLOY-4)
FIXED   Image/busybox:1.37.0           pinned to the digest the old cluster runs (sha256:a7dbc319…)
FIXED   PersistentVolumeClaim/notes-data  storage class local-path → onemind-local (kept when the app is removed)
DROP    Ingress/notes                  → served by OneMind at https://notes.onemind.local
SKIP    CronJob/nightly                not imported yet  ↳ re-create it as a OneMind automation
Data    2 volume(s) to copy            notes-data (1Gi), data-db-0 (1Gi)
Result  0 blocking                     3 fixed · 1 to re-enter · 2 dropped · 1 skipped · 0 notes
Next    onemind migrate import mig_01JD…
$ onemind migrate import  mig_01JD…                                      --wait   # approve on the phone
$ onemind migrate copy    mig_01JD… --kubeconfig migrate.kubeconfig      --wait
$ onemind migrate cutover mig_01JD… --kubeconfig migrate.kubeconfig --stop-old --wait
$ onemind migrate revert  mig_01JD… --kubeconfig migrate.kubeconfig               # if needed
```

| Step | API | Action type | Risk (§12.3) | Changes on the old cluster | Changes on the box |
|---|---|---|---|---|---|
| plan | `POST /v1/migrate/plans` (owner, direct) | – | – | nothing (GET only) | bundle files under `ONEMIND_MIGRATE_DATA_DIR` |
| import | `POST /v1/migrate/plans/{id}/import` → 202 | `migrate.import` | sensitive | nothing | namespace `app-<id>`, config, volumes; every workload at 0 replicas |
| copy | `…/copy` with the kubeconfig → 202 | `migrate.copy` | destructive | one helper pod per volume, deleted after | volumes restored and checked; app started |
| cutover | `…/cutover` (`stop_old`) → 202 | `migrate.cutover` | destructive | workloads scaled to 0 (only with `stop_old`) | final copy, check, start |
| revert | `…/revert` → 202 | `migrate.revert` | destructive | workloads scaled back | app stopped |

Read (owner, adult, agent; guests get 403) with `GET /v1/migrate/plans`, `GET /v1/migrate/plans/{id}` (report, copies, state, `next`) and `GET /v1/migrate/plans/{id}/helper?pvc=` (the exact helper pod, credentials shown as placeholders). Plan states: `planned → staged → running → switched` (revert goes back to `staged`, from `switched` or from a `running` plan whose switch-over left the old app stopped; a newer plan for the same app supersedes an older un-imported one).

## 2. What maps and what does not

| Source | Becomes | Level |
|---|---|---|
| Deployment, StatefulSet | the same, minus node placement, service account, `imagePullSecrets` and projected service account tokens; `automountServiceAccountToken: false`; limits added where missing; StatefulSet volume retention set to `Retain` | ok / fixed |
| Image by tag | pinned to the digest the running pod reports (`imageID`); no registry access needed | fixed; **fail** if no pod runs and the tag is unpinned |
| PersistentVolumeClaim (mounted by an imported workload) | same name and size on `onemind-local`, `ReadWriteOnce`; StatefulSet claims are written out explicitly so the data lands in them | fixed |
| Service | ClusterIP (NodePort and LoadBalancer dropped); ExternalName or selector-less → not imported | fixed / skip |
| ConfigMap | the same | ok |
| Secret referenced by a workload | declared in `spec.secrets` without values | move |
| Ingress | dropped; hosts kept for the switch-over hint; the first backend port becomes `spec.web.port` | drop |
| DaemonSet, CronJob, Job, bare Pod, unused PVC | not imported | skip |
| hostPath, hostNetwork/PID/IPC, privileged, privilege escalation, and the rest of PSA baseline (capabilities beyond its list, seccomp or AppArmor `Unconfined` by field or annotation, custom SELinux type/user/role, `procMount` other than `Default`, sysctls outside its safe set, `hostProcess`), raw block volumes, other volume types | blocks the import | fail |

The bundle is `onemind.app.yaml` (`metadata.origin: private`, contract §12.18; `generatedBy: onemind-migrate/<version>`) plus `manifests/` (kustomization with the `onemind.io/app` label) and `staging/` (the same objects at 0 replicas). Its sha256 binds the import approval: a bundle edited after the request is refused (409 `stale_precondition`).

## 3. How data moves

```
old cluster, namespace N                         OneMind box
┌──────────────────────────────┐                 ┌───────────────────────────────────────────┐
│ helper pod (restic image)    │  restic REST    │ gateway /v1/migrate/repo/<plan>/           │
│  PVC mounted read-only       │ ───────────────▶│  append-only, per-action user, sha256 of   │
│  sha256 manifest of files    │  (upload user)  │  every object checked, restic local layout │
│  restic backup /src + manifest                 │                    │ (read-only user)       │
└──────────────────────────────┘                 │ restore Job in app-<id>:                   │
                                                 │  restic restore --delete into the new PVC  │
                                                 │  sha256sum -c against the old manifest     │
                                                 └───────────────────────────────────────────┘
```

- **Why restic:** it is the stack's backup engine (pinned 0.19.1, BSD-2-Clause), resumable and incremental (the final copy only sends what changed), and it encrypts the data with a per-plan password kept in a 0600 file on the box. The repository is readable without OneMind (`restic -r <data_dir>/repos/<plan>`).
- **Why the gateway serves the repository:** the old cluster then only needs to reach the box's existing listener; each user belongs to one action and is revoked when it ends.
- **Check:** a copy is `verified` when the restored files match the manifest taken on the old side, file by file. A warm copy taken while the old app writes may show `mismatch` (expected, reported, not a failure); the switch-over copy runs with the old writers stopped and must verify, or both apps are put back side by side and the action fails.
- **Ownership and modes** are kept (the restore Job runs as root with CHOWN, DAC_OVERRIDE, FOWNER, FSETID only).

## 4. Security model

- **Old-cluster credential:** a kubeconfig the owner provides, refused if it uses `exec` or `auth-provider` plugins, files, basic auth, impersonation, `insecure-skip-tls-verify`, `proxy-url` or plain http. It is used for the request it came with and, for copy/cutover/revert, held **in memory only** until that action ends or expires; a restart drops it and the approval then answers 409 asking for a new request. The audit log records `"credentials": "provided"` and a sha256 fingerprint, never the token.
- **Where the gateway connects:** to the API server the kubeconfig names, over https with that kubeconfig's CA. Only an owner can hand it one, so this is not an open proxy, but an owner could point it at any address the box can reach.
- **Verb fence** (`migrate/kube.py`, unit-tested): plan = GET on a fixed list of namespaced paths, **never Secrets**; copy adds create/delete of pods named `onemind-migrate-*` with the helper label, and their logs; switch-over and revert add the `scale` subresource only. Anything else is refused before it is sent. `onemind migrate role` prints Roles with the same verbs, but Kubernetes RBAC cannot limit pod creation by name or content: while the copy Role is bound, its token can create any pod in that namespace. The token lives only in the box's memory and expires after 8 hours; delete the copy Role after the switch-over (`kubectl -n <ns> delete role,rolebinding onemind-migrate-copy`).
- **Helper pod:** no API token, read-only volume, read-only root filesystem, all capabilities dropped but `DAC_READ_SEARCH`, `seccomp: RuntimeDefault`, a deadline, pinned image by digest. Its upload user can add files but never overwrite or delete them (only lock files), expires, and is revoked when the action ends. It is visible in the pod spec to anyone who can read pods in that namespace; they can already read the data.
- **Box side:** the restore Job's read-only user and the repository password are in a Secret deleted with the Job, never in argv, steps, the ledger or the audit.
- **Approval:** only a person with role owner requests and approves; agents get 403 (contract §12.1). Plans name the old cluster's API host, secret names and hostnames, so guests cannot read them (§12.6 role defaults). A denied or expired step drops its kubeconfig at once. Import keeps the scan gate (F-7): nothing unscanned runs, private apps included.

## 5. Settings (`ONEMIND_MIGRATE_*`)

| Variable | Default | Meaning |
|---|---|---|
| `DATA_DIR` | `<ONEMIND_DATA_DIR>/migrate` | bundles, repositories, keys |
| `REPO_URL` | `ONEMIND_PUBLIC_URL`, else the listen address | how pods (old cluster and box) reach this gateway; the plan warns when it is plain http |
| `CA_FILE` | none | CA certificate the pods trust for `REPO_URL` (the per-box CA when HTTPS is on) |
| `HELPER_IMAGE` | `docker.io/restic/restic:0.19.1@sha256:1366…d510` | must be pinned by digest |
| `COPY_TIMEOUT_S`, `ROLLOUT_TIMEOUT_S`, `POLL_S`, `KUBE_TIMEOUT_S` | 21600, 600, 3, 30 | |

Events (`publish_event`, audit + NATS): `migrate.plan.created`, `migrate.import.done`, `migrate.copy.verified|mismatch|failed`, `migrate.cutover.done` (with the hosts to repoint), `migrate.reverted`, `migrate.step.failed`. Tables: `migrate_plans`, `migrate_copies`, `migrate_repo_users` (feature schema `migrate`, v1).

## 6. Tests

| Test | Where | Covers |
|---|---|---|
| Units | `core/tests/test_migrate_units.py` | kubeconfig refusals, every fence rule, mapper levels and objects, bundle hash, helper and restore specs, result parsing |
| API flow | `core/tests/test_migrate_flow.py` (fake old cluster, fake box kubectl) | owner-only, scan gate, tampered bundle, kubeconfig dropped on restart, wrong cluster, warm mismatch, cutover undo (also when stopping the old app fails, or scaling it back fails), revert, guests refused, kubeconfig dropped on deny and expiry, secrets never in audit or actions |
| restic REST | `core/tests/test_migrate_repo.py` | append-only rules, hash check, range reads, v1/v2 listing, expired and revoked users |
| Action hook | `core/tests/test_feature_actions.py` | the feature action type hook in `actions.py` |
| CLI | `cmd/onemind/cli/migrate_test.go` | bodies sent, report output, refusals, `--wait`, role YAML |
| Real system | `test/migrate/lima-e2e.sh` | a throwaway Debian 13 VM with pinned k3s: seeds `legacy-demo`, makes the namespaced kubeconfig from `onemind migrate role`, runs plan → import → copy → cutover → revert through the real gateway and real restic, compares file hashes, modes and owners old vs new |

All Python tests run on SQLite and PostgreSQL.

## 7. Not done yet (follow-ups)

- **Scan record for private bundles:** import needs a passing scan like any app (F-7). The on-box scan (CORE-DEPLOY-2) does not exist yet; until it does, a real box cannot import. The e2e writes a stand-in record, labelled as such.
- **Private apps in the catalog:** imported apps are tracked in `app_states` and `/v1/migrate/plans`, but `GET /v1/apps`, the app proxy (`<app>.onemind.local`) and `app.remove` read only the Market catalog. A private-app root in the catalog belongs to CORE-DEPLOY-1/3.
- **Secrets:** `onemind secret set` (CORE-DEPLOY-4) is not built; until then a workload that needs a non-optional secret will not start on the box.
- **PSA:** when app namespaces enforce `restricted` (SANDBOX), the root restore Job must move to a system path (same question as `backup.restore`).
- **Action registry:** the four types use the stopgap hook in `actions.py` (`FeatureActionType`); DEV-API-7's registry replaces it, and contract §12.5 should list the `migrate.*` types.
- **Schema:** `metadata.origin`, `metadata.generatedBy` and `spec.secrets` follow contract §12.18 but are not in `sdk/schema/onemind.app.schema.json` yet.
- **Two clusters:** the e2e uses one k3s for both sides (separate namespaces, separate identities). A two-VM run and a CI job are next.
- **Offline check:** `onemind migrate check <dir>` on exported files (DEPLOYMENTS §3.6) is not built; the plan is the dry-run.
- **Repository limits:** the upload user can add objects up to 512 MiB each with no total quota until it expires (copy timeout + 1 h), and anyone who can read pods in the old namespace can read it from the helper pod; a per-plan quota (sum of the volume sizes plus a margin) is next. The data-plane routes read whole objects into memory and do file I/O on the event loop; streaming reads are next.
- **Plain-http hub:** `onemind migrate` sends the kubeconfig to `--hub` as given; until the box has HTTPS (F-1), an `http://` hub on the network sees the 8-hour token in clear.
- **Cleanup:** the repository and bundle stay until removed by hand; a `migrate.cleanup` action after the 14-day rule (DOGFOOD §3) is next.
