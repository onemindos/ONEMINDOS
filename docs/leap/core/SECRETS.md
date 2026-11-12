<!-- SPDX-License-Identifier: Apache-2.0 -->
# App secrets and the F-7 owner override

**Date:** 2026-11-12 · Part of [the leap](../README.md) · **Branch:** `feat/app-secrets` · **Serves:** CORE-SECRETS-1, APP-OVERRIDE-1; [DEPLOYMENTS.md](../../architecture/DEPLOYMENTS.md) D-R7, §7 and test DT-9 (build step D3, secrets part); contract §12.1 (sealed input) and §12.18 (`spec.secrets`); [BACKUPS.md](../../architecture/BACKUPS.md) §6.4; founder decision F-7 ([DECISIONS-NEEDED](../DECISIONS-NEEDED.md)).

> **Explain it like I am the founder**
> Some apps need a password or an API key that only you have, like Hermes's model-provider key. Until now the install printed a `kubectl` command for you to paste in a terminal. Now the app's manifest lists what it needs, and the approval card shows a form. Your browser locks what you type with your box's key before sending it, so it never travels or rests in plain text. The box keeps it encrypted, writes it into the app's namespace when you approve, and never shows it again: not to you, not to agents, not in any log.
> Separately, an app whose security scan failed cannot be installed. F-7 asked whether you should be able to override that. The answer for v0 is "no", so the override is built but **off**. If you turn it on, you must request the install yourself, type the app's name and give a reason, and a red "owner override" mark goes into the audit log for good.

## 1. What an app declares

```yaml
spec:
  secrets:
    - name: hermes-agent-credentials          # the Kubernetes Secret in app-<id>
      description: Model-provider keys
      keys:
        - {key: OPENROUTER_API_KEY, kind: api-key, description: OpenRouter API key}
        - {key: OPENAI_BASE_URL, kind: url, description: Optional OpenAI-compatible endpoint}
        - {key: SESSION_SECRET, kind: token, generate: true}   # made by the box, rotatable
```

| Field | Meaning |
|---|---|
| `name` | Secret name (DNS-1123), unique in the app, never the `spec.agent` Secret |
| `keys[].kind` | `api-key`, `password` (default), `token` or `url`: how the form shows and checks it |
| `keys[].required` | owner-entered and needed: the install cannot be approved without it |
| `keys[].generate` | the box creates 32 random bytes (base64url) at install; never typed; rotatable. Not with `required`, not for a `url` |

The schema is `sdk/schema/onemind.app.schema.json`; the gateway runs the same rules (`core/onemind_core/appsecrets/spec.py`) and skips an app whose declaration is invalid. `app-gate`'s smoke test fills required and generated keys with placeholders. Hermes now declares `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `OPENAI_BASE_URL` this way, and `deploy/install.sh` no longer prints a `kubectl create secret` command.

## 2. How the owner enters values

Both paths go through an approval, so a value reaches the cluster only when the owner decides.

| When | How | What happens |
|---|---|---|
| Install | The approval carries the form: `POST /v1/actions/{id}/approve` with `{"sealed": …}` | Missing required keys → `409 stale_precondition`, the action stays awaiting. Otherwise the values are committed after acceptance, missing generated keys are created, and the executor applies the Secrets **before** the app's manifests |
| Later (change, rotate, clear) | `POST /v1/apps/{id}/secrets` (owner) with `{sealed?, generate: ["<secret>/<key>"], clear: [...]}` | Files an `app.configure` action (`202`). Its params list each change with a keyed fingerprint, never the value; the values wait encrypted in `secrets_staged`. Approving it applies the Secrets and restarts the app's Deployments and StatefulSets. Deny deletes the staged values at once; after expiry they are deleted at the next change request or gateway start. An empty body re-applies the current values |
| Terminal, until the dashboard pass wires the form | `onemind-secrets approve <action> <secret>/<key>` or `onemind-secrets change <app> --set …` on the hub | Reads each value without echo, seals it exactly as the browser does, and calls the routes above. The owner token comes from `ONEMIND_TOKEN` or `--token-file`, never the command line |

Removing an app keeps its stored values, like its data, so a reinstall finds both (a generated database password must still match the kept volume). Clearing is explicit.

## 3. API

| Method and path | Who | Returns |
|---|---|---|
| `GET /v1/secrets/public-key` | any principal | `{alg: "X25519", key, key_id, sealed_alg: "X25519-AES256GCM"}` |
| `GET /v1/apps/{id}/secrets` | any principal | `{app_id, key_id, secrets: [{name, description, keys: [{key, kind, description, required, source, set, version, updated_at}]}], missing_required}`. Never a value |
| `POST /v1/apps/{id}/secrets` | owner (others `403`, audited) | `202` with the `app.configure` action and `Location`; `Idempotency-Key` header supported |
| `POST /v1/actions/{id}/approve` | owner | optional body `{sealed?, override?, webauthn?}` |
| `GET /v1/apps/{id}/owner-override` | owner | `{enabled, scan_problem, eligible, refusal, confirm, reason_length, step_up}` for the approval card |

`app.configure` is not accepted by `POST /v1/actions` or the MCP `request_action` tool: only an owner files it, through the secrets route. Agents can read which keys are set (as contract §12.18's `GET /v1/apps/{id}` allows) and nothing else.

**Sealed input** (contract §12.1): `shared = X25519(ephemeral, box)`, `k = HKDF-SHA256(shared, salt = epk ‖ box_pub, info = "onemind sealed-input v1")`, `ct = nonce(12) ‖ AES-256-GCM(k, nonce, {"values": {<secret>: {<key>: <value>}}}, aad = "onemind/app-secrets/<app-id>")`; `epk` and `ct` are base64url without padding, `kid` is optional. The AAD binds a sealed form to one app, so it cannot be replayed into another. The browser side is `ui/src/secrets/seal.ts` (WebCrypto); a one-off run on 2026-11-12 sealed with that file under Node and opened with the gateway's Python code.

## 4. Where values live and which key protects them

- **Store key:** 32 random bytes in the box key store: `ONEMIND_SECRETS_KEY_FILE`, else a systemd credential named `onemind-secrets-key` (`$CREDENTIALS_DIRECTORY`), else `$ONEMIND_DATA_DIR/custodian/secrets.key`. Created on first start with mode 0600 in a 0700 directory, never overwritten; a key file readable by group or others stops the gateway.
- **Derived keys** (HKDF-SHA256 with separate labels): AES-256-GCM for stored values (AAD = app, Secret, key, version, so rows cannot be swapped), the X25519 pair for sealed input, and an HMAC key for fingerprints.
- **Tables** (feature `secrets`, PLUMBING §3): `secrets_values(app_id, name, key, ciphertext, nonce, key_id, version, source, fingerprint, action_id, updated_by, updated_at)` and `secrets_staged(action_id, name, key, app_id, op, ciphertext, nonce, key_id, fingerprint, created_by, created_at)`. Tested on SQLite and PostgreSQL.
- **Why this is independent of LUKS:** the database, its dumps, a PostgreSQL server and backups hold only ciphertext. The key is a separate file with its own permissions. LUKS (CORE-SEC-5) and k3s secrets encryption (H-12) add layers; neither is assumed.
- **Backups:** the key travels in the restic `system` unit with the custodian directory (BACKUPS.md §6.4). A database restored **without** its key cannot open the values: the next approval that needs them answers `409` naming the key to enter again, instead of applying garbage.
- **In the cluster:** each declared Secret is applied by server-side apply (field manager `onemind-gateway`), never client-side apply, which would copy the values into the `last-applied-configuration` annotation. A key the manager stops sending (a cleared value) is removed by the API server. Values travel to `kubectl` on stdin only; every value (raw and base64) is scrubbed from recorded kubectl output.

## 5. F-7 owner override

F-7's proposed default is "no in v0", so the override exists but is **off** unless the gateway starts with `ONEMIND_ALLOW_OWNER_OVERRIDE=1` (an unknown value stops the gateway; turning it on logs a warning and writes a `security.owner_override.enabled` event at each start).

When on, an owner adds `"override": {"reason": "...", "confirm": "<app id>"}` to the approval of an `app.install` whose scan failed or is stale. It is accepted only if:

| Rule | Otherwise |
|---|---|
| The approver is an owner | `403` (as every approval) |
| The install was **requested by a person**: an agent cannot ask for a scan-failed app and have it waved through | `409`; the owner can request it themselves |
| A scan record exists and its ClamAV count is known and zero: an override covers vulnerabilities and age, never malware | `409` naming the reason |
| The reason has 10–500 characters and `confirm` is the app id typed exactly | `422` |
| Once the owner has passkeys, the approval carries a passkey assertion | `401` (`step_up_required` in the message) |

A used override writes a **critical** `app.owner_override` event (audit line, NATS `onemind.event.app.owner_override`, in-process subscribers) with `mark: "owner override: <reason>"`, `tone: "red"`, the scan facts, the requester and how presence was proven; `owner_override: true` on `action.approved`; and the mark in the action's `result.owner_override`, so the dashboard shows it wherever the install appears (`OwnerOverrideMark`). With the override off, the attempt is refused with `403` and audited as `authz.denied` (`owner_override_disabled`).

**Passkeys.** `OwnerOverride.step_up` takes any object with `passkeys_active() -> bool`. The identity feature (`feat/identity`) already verifies a `webauthn` assertion in its approval guard before the action service runs; when it merges, its `register` adds one line, `gw.actions.owner_override.step_up = svc`, and the override then refuses any approval without an assertion while an owner passkey exists. Until then no passkeys exist, and the audit records `step_up: "none (no passkeys registered)"`.

## 6. Security model

| Asset | Attacker | Control |
|---|---|---|
| A value in transit | LAN sniffer, proxy log | Sealed in the browser; plaintext is never accepted (`422`) |
| A value at rest | copy of the database or a backup | AES-256-GCM with a key outside the database |
| A value in the cluster | someone reading object annotations | Server-side apply only; namespace isolation; k3s secrets encryption (H-12) |
| A value in logs | anyone reading audit, events, actions, kubectl output | Only names and keyed fingerprints are recorded; kubectl output scrubbed; error messages never quote input |
| Entering or changing values | a prompt-injected agent | Owner-only writes; the change is an action the owner approves |
| The scan gate | an agent, or an owner on autopilot | Override off by default; owner requests only; never malware; typed app id and reason; passkey once available; permanent red mark |

Why fingerprints are keyed: contract §12.1 suggests recording a value's sha256. A plain hash of a short password in an audit log anyone with `audit:read` sees can be guessed offline, so the gateway records `HMAC-SHA256(box key, app | secret | key | value)` truncated to 96 bits instead: a change still shows, a guess cannot be checked.

## 7. Tests

| What | Where | Result (2026-11-12) |
|---|---|---|
| Declarations, store key, sealed input, install and change flows, purge, restart, key loss, executor plans, scrubbing, `onemind-secrets` | `core/tests/test_secrets.py`, `test_secrets_cli.py`, `test_hermes_secrets.py` | pass |
| Override off/on, every refusal, passkey step-up, red mark, env parsing | `core/tests/test_owner_override.py` | pass |
| Whole core suite on SQLite and on PostgreSQL 17 | `make -C core test`; `ONEMIND_TEST_DB_URL=postgresql+psycopg://…` | 403 passed, 2 skipped (NATS) on each |
| Form, dialog, mark (axe), WebCrypto sealing opened with the box's construction | `ui/src/secrets/*.test.ts(x)` | pass |
| `validate-apps hermes-agent`, `app-readme --check`, sdk tool tests | `sdk/tools` | pass |

**On a real cluster** (throwaway Lima VM, k3s v1.37.2, created and deleted 2026-11-12): the executor's own install and configure plans were run with the VM's kubectl. Both Secrets were server-side applied with `onemind-gateway` as the only field manager and no `last-applied-configuration` annotation; the pod read the value through `envFrom`; configure replaced it, removed a cleared key from the Secret and restarted the Deployment, whose new pod had the new value; `rollout restart deployment,statefulset` in a namespace without either kind exited 0 ("No resources found"). The executor also accepts kubectl's older `no objects passed to restart` failure as "nothing to restart" (UNVERIFIED on any current kubectl). Still to do in CI: DT-9 through the full gateway on k3d.

## 8. Follow-ups

- Dashboard wiring of `ui/src/secrets` (install approval card, app page, override dialog) in the dashboard pass; until then `onemind-secrets`.
- Identity merge: the one `step_up` line above.
- Owner reveal of a generated value with passkey (APPDEP-11), for apps whose generated password the owner must type somewhere.
- Rotating the store key itself (re-encrypt every row; `key_id` is stored per row for this).
- Revisions and plans (DEPLOYMENTS D2): record secret fingerprints in the revision and the plan, so approval binds to them.
- A Go `onemind secrets` command group when DEV-CLI lands.
- Image: see [`SECRETS-os.patch.md`](SECRETS-os.patch.md).

## 9. Files

| Path | What |
|---|---|
| `core/onemind_core/appsecrets/` | `spec.py` declarations, `crypto.py` store key and sealed input, `store.py` tables, `service.py` logic, `api.py` bodies, `cli.py` `onemind-secrets` |
| `core/onemind_core/override.py`, `routers/override.py` | F-7 override and its card info route |
| `core/onemind_core/routers/secrets.py` | secrets routes |
| `core/onemind_core/actions.py` | `ApprovalInput`, `app.configure`, the two hooks (prepare before acceptance, commit after) |
| `core/onemind_core/executors.py` | `AppSecret`, server-side apply, configure restart, scrubbing |
| `core/onemind_core/scan.py` | ClamAV count on scan records |
| `sdk/schema/onemind.app.schema.json`, `sdk/tools/` | schema, README row, smoke placeholders |
| `apps/hermes-agent/` | the declaration and the README without the kubectl command |
| `ui/src/secrets/`, `ui/demo/src/secrets/` | form, dialog, mark, sealing; demo `#/secrets/<state>` |
