<!-- SPDX-License-Identifier: Apache-2.0 -->
# App lifecycle: start, stop, update, configure, remove, delete data

**Date:** 2026-11-12 · **Branch:** `feat/app-lifecycle` · **Serves:** umbrel-parity PD-03..PD-07 ([docs/strategy/umbrel-parity.md](../../strategy/umbrel-parity.md)), STATUS rows UMB-APP-0, -3, -4, -5 · **Contract:** [poc-v0.md §12.40](../../../sdk/contracts/poc-v0.md)

> **Explain it like I am the founder**
> Until now an app could only be installed or removed, and "remove" threw the app's files away. Now an app has a full life: it can be stopped and started, restarted, reconfigured and updated. Every one of those is a *request* that waits for you. Before you approve, the box shows a **plan** (what will happen) with a fingerprint (`plan_sha256`). Your approval is for that fingerprint. If anything changed in between (a new app version landed, the app's files differ), the approval is refused instead of running something you never read. An AI can ask for any of these, but only you can approve, and only you can ask to delete an app's data.

## 1. What each action does

| Action | Starts from | What happens | Data |
|---|---|---|---|
| `app.install` | not installed, failed, removed | as before, plus the app's generated login if it declares one | kept volumes are picked up again |
| `app.stop` | installed | workloads scaled to zero, replica counts remembered | untouched |
| `app.start` | stopped | workloads scaled back to the remembered counts, wait until ready | untouched |
| `app.restart` | installed | workloads rolled one by one, wait until ready | untouched |
| `app.configure` | installed | settings written to ConfigMap `onemind-settings`, workloads rolled | untouched |
| `app.update` | installed | new version checked by the install sandbox and applied; kept only if healthy | untouched |
| `app.remove` | installed, stopped, failed | workloads deleted; the namespace and the data volumes stay | **kept** |
| `app.delete_data` | removed | the namespace is deleted with every volume | **erased, no undo** |

Why remove keeps data: Umbrel erases it, Runtipi and Cosmos keep it. A mistaken tap must not cost a family its photos (PD-06). Erasing is a second, deliberate request: owner only, the app id typed again, risk class `destructive`. An agent cannot even preview it.

## 2. The plan and the fingerprint

`GET /v1/apps/{id}/plan?type=app.update` (or `POST /v1/plans` for actions with parameters) returns the plan and `plan_sha256`, the sha256 of `{type, params, target, objects}`. `objects` includes a fingerprint of the app's manifest folder, so a changed file changes the hash.

1. **Request:** the gateway renders the plan and stores it on the action. A requester that sends the hash it read gets `409 plan_changed` if it is stale.
2. **Approval:** the gateway renders again. Different hash: `409 plan_changed`, the action stays `awaiting_approval`. The owner's client sends the hash it showed on the card; clients that send `OneMind-API-Version: 1` must.
3. **Execution:** one last render right before the executor. Different hash: nothing runs, the action ends `failed` (`plan_changed`), the app goes back to the state it had.

## 3. Health-gated update with revert

Update applies the new bundle, then asks every Deployment and StatefulSet for `kubectl rollout status` within a timeout (default 120 s). If any is not ready, the executor runs `kubectl rollout undo` on each and waits again. The action ends `failed` with `result.reverted: true`, the app stays `installed` at the old version, and `app.update_reverted` is audited. If the revert cannot be confirmed the action is `outcome_unknown` and a person looks (we never claim what we cannot see).

**Known limits (UNVERIFIED on a real cluster; needs the lab kit):** `rollout undo` restores workloads, not ConfigMaps or Services the new version changed. The volume snapshot before an update (PD-05) waits for box backups (`feat/backups-on`); the plan says so.

## 4. Credentials (PD-07)

An app can declare `spec.credentials: {username?, password: generated, showBeforeOpen?}`. At the first install the gateway generates a password, seals it (AES-256-GCM, key file `credentials.key` next to the audit log, mode 0600, the app id bound in) and gives it to the executor for Secret `<id>-credentials`. The owner reads it with `GET /v1/apps/{id}/credentials`: audited, never cached, 403 for everyone else including agents, never in a plan, event, action or log. It survives remove (the data still needs it) and is erased by `delete_data`. **Back up `credentials.key` together with the database**, or sealed logins cannot be opened after a restore.

`sealed` request envelopes (X25519, contract §12.1) for app secrets belong to the secrets store (`feat/app-secrets`); this change only refuses secret-looking names in `settings`.

## 5. Progress

Executors call `report_progress(step, pct)`. The action carries `progress: {step, pct}` and each report is the event `action.progress`, so the dashboard's jobs tray can show it.

## 6. For developers

- Types, states, risk: `core/onemind_core/lifecycle.py` (`TYPES`). The rest of the gateway reads that table.
- Executors that predate this take no `ctx` argument; the service only passes it to executors that accept it.
- Database: core schema v2 adds `plan`, `plan_sha256`, `progress`, `risk` to `actions` (upgrade step in `store.py`), and tables `app_runtime` (version, previous version, applied settings) and `app_credentials`.
- Tests: `core/tests/test_app_lifecycle.py` (SQLite and PostgreSQL).

## 7. Not done here (next)

- An update that widens an app's grants is `sensitive` in the contract; the gateway does not diff grants yet, so every update is `write`.
- Per-app host ports and dependency resolution in the plan (UMB-APP-3 remainder, UMB-APP-9).
- CLI verbs (`onemind app stop|start|update`, UMB-APP-14) and the dashboard pages (B5).
