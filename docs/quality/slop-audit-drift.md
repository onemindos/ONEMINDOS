<!-- SPDX-License-Identifier: Apache-2.0 -->
# Slop audit: contract and interface drift

**Date:** 2026-11-12 · **Base:** `main` at `1c278f5` (after #38 core plumbing and #39 contract §12) · **Lens:** contract and interface drift only · **Serves:** the founder's "no slop" quality pass; feeds C12-A, DEV-API-1, DEV-CLI-1, CORE-BACKUP-1 and the wave-2 streams ([`docs/leap/STATUS.md`](../leap/STATUS.md)).

> **Explain it like I am the founder**
> A *contract* is the written agreement between parts of the system: which URL the dashboard calls, which fields come back, which words an enum may contain. *Drift* is when two parts that should agree have quietly stopped agreeing. Tests stay green because each side tests itself, not the other side. This file lists every place where code and the binding contract ([`sdk/contracts/poc-v0.md`](../../sdk/contracts/poc-v0.md) §1–§12), or code and its own spec, disagree today. Each one was checked by running the code or reading both sides; nothing here is a guess or a style opinion.

## How this was checked

- **Surfaces compared:** gateway routes and payloads (`core/onemind_core/`) against §1–§12; the `onemind` CLI against [`docs/leap/dev/CLI.md`](../leap/dev/CLI.md); dashboard, mobile and `@onemind/ui` clients against the gateway; heartbeat producers (`internal/*`) against §2 and §12.10; NATS subjects against §12.9; the manifest schema against all 9 apps; `scan.json` producer (`sdk/tools/app-gate`) against its consumers (gateway, `app-readme`, `site/`).
- **Run, not just read:** the gateway was built in-process with `create_app()` and a FastAPI `TestClient` (noop executor, SQLite, the real `apps/` folder) to dump `/openapi.json`, create and approve actions, and call `/mcp`; `EventHub.publish_event` was called directly to capture the NATS envelope; the `onemind` binary was built with `go build ./cmd/onemind` and run.
- **Baseline:** on this commit `go test ./cmd/... ./internal/{heartbeat,backup,mesh,leaf}/` passes and `pytest` in `core/` passes (304 passed, 2 skipped). Every finding below exists with all tests green.
- **Not present on `main`, so not audited:** client SDKs (`sdk/go`, `sdk/ts`, `sdk/python` do not exist yet) and a desktop client.

**Severity.** *High:* can lose user data, or several streams are building on the wrong interface right now. *Medium:* two components disagree on a path, field or enum that exists or is being built. *Low:* misleading or not forward-compatible, with no wrong behaviour today.

## Summary

| ID | Sev | Area | Finding |
|---|---|---|---|
| [D1](#d1) | High | gateway executor, clients | `app.remove` deletes the app's data; §12.5 says plain `app.remove` keeps it |
| [D2](#d2) | High | gateway events | `publish_event` emits an envelope that is not `onemind.event/v1` (§12.8) |
| [D3](#d3) | Medium | action object | Gateway and clients use `decided_by`; the binding decider field is `approved_by` |
| [D4](#d4) | Medium | principals | Static-token principals are `owner`, `hermes`, not `person:owner`, `agent:hermes` (§12.1, §7) |
| [D5](#d5) | Medium | CLI | `onemind mesh`, `onemind storage`, `onemindd mesh` are merged and tested but unreachable |
| [D6](#d6) | Medium | contract | §12.11 adds `role` to `/v1/nodes`, which already has §2 `role` with other values |
| [D7](#d7) | Medium | catalog | `icon` is a relative file name that nothing serves; no client can show an app icon |
| [D8](#d8) | Medium | catalog | App `status` has no enum in the contract; gateway and `@onemind/ui` use different vocabularies |
| [D9](#d9) | Medium | `@onemind/ui`, specs | UI library and two feature specs use names that §12.21 rejected |
| [D10](#d10) | Medium | actions, MCP | An agent's `reason` is dropped from the action; REST rejects `reason` with 422 |
| [D11](#d11) | Low | heartbeat producers | `backup.last_result` can be `refused`; leaf health `no_server`; `target_id` vs `destination_id` |
| [D12](#d12) | Low | errors | Closed error-code enums in OpenAPI and both clients; unknown codes lose their message |
| [D13](#d13) | Low | CLI.md | "What exists today" and the code-layout table point at moved files and "in flight" work that is merged |

---

<a id="d1"></a>
## D1 (High). `app.remove` deletes the app's data; the contract says it keeps it

**Contract.** §12.5 ([`poc-v0.md:324`](../../sdk/contracts/poc-v0.md)): `app.remove` takes `{app_id, delete_data?: false}`; risk `write` ("reversible, adds no power", :282), and only `destructive` "with `delete_data`" (:284).

**Code.** The kubernetes executor's remove plan runs `kubectl delete -k <manifests>` and then `kubectl delete namespace app-<id>` ([`core/onemind_core/executors.py:152-158`](../../core/onemind_core/executors.py)). Every app's `manifests/kustomization.yaml` lists its `pvc.yaml` (all 9 apps), so the PVC is deleted explicitly. The PVCs use k3s's default `local-path` class, whose reclaim policy is `Delete` (verified claim C-W5-019 in `research-output/evidence/claims.csv`; acknowledged in [`docs/leap/core/BACKUPS.md:28`](../leap/core/BACKUPS.md)). So approving "Remove Vaultwarden" deletes the vault from disk. The request body cannot even say otherwise: `ActionParams` forbids any field but `app_id` ([`actions.py:41-43`](../../core/onemind_core/actions.py)).

**What people are told.** The dashboard and phone approval cards say only "Remove" ([`dashboard/src/pages/Approvals.tsx:9`](../../dashboard/src/pages/Approvals.tsx), [`mobile/src/lib/approvals.ts:12`](../../mobile/src/lib/approvals.ts)). `@onemind/ui` goes further and promises the opposite of what happens: "Remove X (its data is kept)" ([`ui/src/store/logic.ts:205`](../../ui/src/store/logic.ts)) and "Keep the data (recommended). Reinstalling later picks it up again" ([`ui/src/store/Installed.tsx:550`](../../ui/src/store/Installed.tsx)).

**Fix.** Until `delete_data` and the `Retain` class (CORE-BACKUP-1) land, make the v0 remove plan keep data: render the kustomization, delete every object except `PersistentVolumeClaim`, and do not delete the namespace. Add a test in `core/tests/test_audit_auth_exec.py` that the remove plan never deletes a PVC or the namespace. When `delete_data: true` is added (§12.5), it is the only path that deletes the PVCs, it is `destructive` (step-up), and the approval cards show "and delete its data".

<a id="d2"></a>
## D2 (High). The shared event hook emits an off-contract envelope

**Contract.** §12.8 ([`poc-v0.md:446-451`](../../sdk/contracts/poc-v0.md)): envelope `schema: "onemind.event/v1"` with `id`, `type`, `ts`, `subject` (the ids it concerns) and `data`; optional `severity` is `info|warning|critical`; `id` is monotonic and audit-derived events use the audit `seq`. §12.9 (:465): "The same envelope is used on NATS."

**Code.** [`core/onemind_core/events.py`](../../core/onemind_core/events.py): `EVENT_SCHEMA = "onemind.event.v1"` (:29, a dot where the contract has a slash), `SEVERITIES` adds `error` and `debug` (:31), `id` is `evt_<random hex>` (:119), and the envelope (:127-143) has `occurred_at` instead of `ts` and `resource` instead of `subject`. A probe of `publish_event` on this commit returned keys `actor_id, causation_id, correlation_id, data, dedupe_key, id, instance_id, observed_at, occurred_at, resource, schema, severity, site_id, source_id, type`: both required fields `ts` and `subject` are missing. [`core/tests/test_plumbing.py:258-263`](../../core/tests/test_plumbing.py) pins the drift (`severity="error"`, `id.startswith("evt_")`).

**Why it is High.** [`docs/leap/core/PLUMBING.md`](../leap/core/PLUMBING.md) §5 (merged in #38, one merge before §12 in #39) tells every stream to use this hook, cites "the contract §12.3 draft" (:129), and its example uses `severity="error"` and `resource` (:122). Notifications, monitoring and automation consumers written against it now will disagree with the SSE stream and any other NATS consumer that follows §12.8.

**Fix.** In `events.py`: `EVENT_SCHEMA = "onemind.event/v1"`; emit `ts` and `subject` (map `resource` and `action_id` into `subject: {action_id?, node_id?, app_id?, …}`); restrict severities to `info|warning|critical`; use the audit line's `seq` as `id` (the audit append already happens first). Update PLUMBING.md §5 (the §12.8 reference, the example) and the test.

<a id="d3"></a>
## D3 (Medium). The decider is `decided_by`; the binding name is `approved_by`

**Contract.** §12.4 action object has `approved_by` (a person id or `policy:<id>@<rev>`), `approved_via` and `approval` ([`poc-v0.md:295`](../../sdk/contracts/poc-v0.md), :239); §12.21 binds the decider field as `approved_by` (:652).

**Code.** The gateway returns `decided_by` (an object `{id, kind, role}`) and `decided_at`, set on approve and on deny alike ([`ledger.py:81`](../../core/onemind_core/ledger.py), :277; [`actions.py:211`](../../core/onemind_core/actions.py)). A live approve returned `decided_by: {id: owner, kind: person, role: owner}` and no `approved_by`. All three clients are coded to the non-contract name: [`dashboard/src/api/types.ts:151`](../../dashboard/src/api/types.ts), [`mobile/src/api/types.ts:178`](../../mobile/src/api/types.ts), [`ui/src/components/ApprovalCard.tsx:32`](../../ui/src/components/ApprovalCard.tsx) (rendered at :159-161). [`core/README.md:126`](../../core/README.md) calls the audit field `approved_by` while the API calls it `decided_by`.

**Fix.** Add `approved_by` (string id, set only when the action was approved), `approved_via` and `approval: "token"` to `Action.to_json`; keep `decided_by` for one release as a documented alias; move the three clients to `approved_by`.

<a id="d4"></a>
## D4 (Medium). Principal ids are not `<kind>:<id>`

**Contract.** §12.1 ([`poc-v0.md:231-237`](../../sdk/contracts/poc-v0.md)): a person's id is `person:<id>`, an agent's `agent:<id>`. The §7 demo (:122) expects the audit chain to record approver `person:owner`.

**Code.** `auth.py` takes the `id` from the tokens file verbatim ([`auth.py:70-81`](../../core/onemind_core/auth.py)), and every generator writes bare ids: [`deploy/install.sh:496`](../../deploy/install.sh) `{id: owner, …}`, [`deploy/compose/gen-tokens.sh:21-22`](../../deploy/compose/gen-tokens.sh) `owner` and `dev-agent`, [`core/examples/tokens.example.yaml:7,13`](../../core/examples/tokens.example.yaml) `owner` and `hermes`. A live request with a static agent token recorded `requested_by: {id: hermes, kind: agent}`. Only app-issued agents get the prefix (`agent:<app-id>`, §11.2). The contract also contradicts itself: §7 (:122) says the requester is `agent:hermes`, while §11.2 (:213), §12.4 (:294) and the gateway use `agent:hermes-agent`.

**Fix.** Write `person:owner` and `agent:<name>` in all three generators; make `auth.py` reject (or, for one release, prefix with a warning) an id whose prefix does not match its `kind`. Contract fix-up PR: §7 line 122 → `agent:hermes-agent`.

<a id="d5"></a>
## D5 (Medium). Three command groups are merged, tested and unreachable

**Code.** `cmd/onemind/mesh.go:27` (`meshCmd`) and `cmd/onemind/storage.go:38` (`storageCmd`) live in package `main` and are called only by their tests. The command registry is `groups` in [`cmd/onemind/cli/root.go:32-36`](../../cmd/onemind/cli/root.go) (node, update, version). `onemindd mesh enroll|wait-ip|status` exists as `mesh.RunCLI` ([`internal/mesh/cli.go:25-27`](../../internal/mesh/cli.go)), but `subcommands` in [`cmd/onemindd/registry.go:9-11`](../../cmd/onemindd/registry.go) has only `update`. Running the built binary: `onemind mesh status` and `onemind storage disks` both print the global usage and exit 2.

**Docs that say otherwise.** [`docs/architecture/NETWORKING.md:555`](../architecture/NETWORKING.md) lists the `onemindd mesh` CLI as **built**, and :245 makes `ExecStartPre=onemindd mesh wait-ip` a k3s start dependency. The recorded wiring ([`NETWORKING.md:595,600`](../architecture/NETWORKING.md), [`internal/storage/README.md:68-74`](../../internal/storage/README.md)) says to add a `case` to the `switch` in `cmd/onemind/main.go`'s `run`, which no longer exists after #38. The CLI spec tree ([`CLI.md:49-80`](../leap/dev/CLI.md)) has no `storage` or `mesh` group, and the docs name three different storage verb sets: code `disks|health|status|plan create|protect|repair`, [`docs/umbrel2/storage.md:263`](../umbrel2/storage.md) `status|disks|scrub|protect|add|replace|remove`, [`docs/umbrel2/files-backups.md:265`](../umbrel2/files-backups.md) `devices|mount|format`.

**Fix.** Move both files to `cmd/onemind/cli/{mesh,storage}.go` as `meshCommands()` and `storageCommands()` and add them to `groups`; add `"mesh": func(a []string) int { return mesh.RunCLI(a, os.Stdout, os.Stderr) }` to `subcommands`; add a test that `Usage()` lists them; update the two wiring notes; add `mesh` and `storage` to the CLI.md §3 tree with one verb set that the umbrel2 storage specs then reference.

<a id="d6"></a>
## D6 (Medium). §12.11 gives `/v1/nodes` a second `role`

**Contract.** Each `/v1/nodes` item is the §2 heartbeat plus `status` and `last_seen`, and the heartbeat already has `role: hub|node` ([`poc-v0.md:27`](../../sdk/contracts/poc-v0.md)); §12.10 confirms "the top-level §2 `role` stays `hub|node`" (:486). §12.11 then says `/v1/nodes` and `/v1/nodes/{id}` "gain `role`, `state` …" with a `?role` filter (:503), and `GET /v1/fabric` uses `role` for `hub|worker|leaf`.

**Why it matters.** One JSON object cannot have two `role` fields. Either the field changes meaning (which §12's compatibility rule forbids) or the addition is a no-op and the filter is ambiguous. Today's clients type it as `hub|node`: [`dashboard/src/api/types.ts:21`](../../dashboard/src/api/types.ts), [`mobile/src/api/types.ts:24`](../../mobile/src/api/types.ts), and the CLI's ROLE column ([`cmd/onemind/cli/node.go:84,126`](../../cmd/onemind/cli/node.go)).

**Fix.** Contract fix-up PR: in §12.11, name the addition `fabric_role` (`hub|worker|leaf`) and the filter `?fabric_role`, or state that `/v1/nodes` gets no new role field and fabric roles come from the heartbeat's `fabric.role` and `GET /v1/fabric`.

<a id="d7"></a>
## D7 (Medium). App icons cannot be shown anywhere

**Contract.** §4 manifest `icon: icon.svg` ([`poc-v0.md:83`](../../sdk/contracts/poc-v0.md)); the schema calls it a "file path relative to apps/<id>/". §3 puts `icon` in each `GET /v1/apps` entry.

**Code.** The catalog copies the manifest value as is ([`catalog.py:97`](../../core/onemind_core/catalog.py)), so all 9 apps return `"icon": "icon.svg"`, and no route serves `apps/<id>/icon.svg`. The dashboard and phone never render `icon`. `@onemind/ui` expects "an http(s) URL" (`types.ts:70` in [`ui/src/home`](../../ui/src/home)) and drops anything else (`parts.tsx:37` in [`ui/src/home`](../../ui/src/home)), so it always shows a monogram. Nine committed `icon.svg` files are never seen.

**Fix.** Contract PR: `GET /v1/apps/{id}/icon` (any principal, served from the validated relative path with `image/svg+xml` and `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`), and the catalog's `icon` becomes that path. The clients render it.

<a id="d8"></a>
## D8 (Medium). App `status` has no shared vocabulary

**Contract.** §3 lists `status` in each catalog entry ([`poc-v0.md:61`](../../sdk/contracts/poc-v0.md)) but never says which values it takes; §12.15 says the values "gain `updating`, `reverting`, `drifted`, `stopped`" (:586), additions to a list that was never written down.

**Code.** The gateway uses install-state words, documented only in an OpenAPI description: `not_installed | installing | installed | removing | failed | unknown` ([`models.py:42`](../../core/onemind_core/models.py), [`routers/apps.py:19-20`](../../core/onemind_core/routers/apps.py)); the dashboard keys on those ([`AppTrust.tsx:69`](../../dashboard/src/components/AppTrust.tsx), [`Market.tsx:14`](../../dashboard/src/pages/Market.tsx)). `@onemind/ui` puts run-state words in a field it calls the contract `status`: `running | starting | updating | stopped | unhealthy | unknown` (`types.ts:31,65` in [`ui/src/home`](../../ui/src/home), [`ui/src/store/types.ts:141-142`](../../ui/src/store/types.ts)). Only `unknown` overlaps, so a ui Home fed by the real gateway shows every app in the wrong state.

**Fix.** Contract PR: enumerate §3 `status` as the gateway's six values plus the §12.15 four; state that run health lives in §12.15 `health.state` (`healthy|unhealthy|starting|stopped|unknown`). In `ui/`, read run state from `health.state` and keep `status` for the install lifecycle.

<a id="d9"></a>
## D9 (Medium). `@onemind/ui` and two feature specs still use names §12.21 rejected

§12 says "Feature specs own behaviour; this section owns names, paths, bodies" ([`poc-v0.md:222`](../../sdk/contracts/poc-v0.md)), and §12.21 records each renaming. These were not carried over. In `ui/`, most of them are API strings shown to the owner as "the call this button makes" (UX-B2), so they teach wrong endpoints; the types will be wired to the real API as written.

| Where | Uses | Binding name (§) |
|---|---|---|
| [`ui/src/settings/ApprovalsBoard.tsx:222`](../../ui/src/settings/ApprovalsBoard.tsx), [`settings/types.ts:274`](../../ui/src/settings/types.ts), `ApprovalsBoard.tsx:82` | `GET /v1/actions/{id}/plan`, `plan_hash` | `GET /v1/actions/{id}/preview`, `plan_sha256` (§12.4) |
| [`ui/src/settings/types.ts:269`](../../ui/src/settings/types.ts) | risk `low\|medium\|high` drives the approval risk pill | `read\|write\|sensitive\|destructive\|actuate`; §12.21 retires the low/medium/high scale |
| [`ui/src/settings/AuditTimeline.tsx:83,119`](../../ui/src/settings/AuditTimeline.tsx), `widgets.tsx:271` in [`ui/src/home`](../../ui/src/home) | `GET /v1/audit?after=`, `?limit=8` | `GET /v1/audit/events?after_seq=`, `GET /v1/activity` (§12.16) |
| `widgets.tsx:343,387` in [`ui/src/home`](../../ui/src/home) | `GET /v1/updates`, `GET /v1/fabric/links` | `GET /v1/os/status` (§12.13), `GET /v1/fabric` (§12.11) |
| [`ui/src/settings/SectionsAccess.tsx:223,262`](../../ui/src/settings/SectionsAccess.tsx) | `GET/PUT /v1/people`, "a request the owner approves" | `GET /v1/users`, `PATCH /v1/users/{id}`, a direct owner write with step-up (§12.6) |
| [`SectionsAccess.tsx:332,409`](../../ui/src/settings/SectionsAccess.tsx) | `POST /v1/agents/{id}/resume` | action `agent.resume` through `POST /v1/actions` (§12.6) |
| [`ui/src/settings/SectionsCare.tsx:389,439`](../../ui/src/settings/SectionsCare.tsx) | `/v1/notify/routes`, `/v1/notify/quiet`, `/v1/automations` | `/v1/notifications/{channels,preferences}`, `/v1/automation/rules` (§12.14, §12.17; §12.21 "`/v1/notify/*` … not used") |
| [`ui/src/store/types.ts:195-203`](../../ui/src/store/types.ts), [`Installed.tsx:542`](../../ui/src/store/Installed.tsx), [`logic.ts:188`](../../ui/src/store/logic.ts) | `app.delete_data`, `app.start`, `app.stop`; "contract actions" = install, remove | `app.remove {delete_data: true}`; no start/stop in §12.5; §12.5 also has `app.update`, `app.restart`, `app.configure`, `app.rollback` |
| [`docs/leap/core/NOTIFICATIONS.md:77,106`](../leap/core/NOTIFICATIONS.md), [`docs/leap/core/DASHBOARD.md:63-64`](../leap/core/DASHBOARD.md) | `/v1/notify/routes`, `/v1/notify`, `/v1/automations`, `/v1/policies` | as above; `/v1/approval-policies` (§12.17) |

**Fix.** One PR per surface: rename the strings and types in `ui/` (and update the affected tests), and add a "names follow contract §12.21" line plus the renames to the two feature specs. A CI grep for the rejected paths in `ui/src` and `docs/leap/core` stops them coming back.

<a id="d10"></a>
## D10 (Medium). An agent's `reason` never reaches the approval card

**Contract.** §11.3 `request_action` takes `reason?`; §12.4's action object carries `reason` (:293) and §12.1 says every request endpoint accepts `reason` (≤ 500 chars, :242).

**Code.** `/mcp` accepts `reason` ([`mcp.py:98-101`](../../core/onemind_core/mcp.py)) but `ActionService.create` writes it only to the audit log; its docstring says "the §3 action shape has no field for it" ([`actions.py:131-136`](../../core/onemind_core/actions.py)), which §12.4 has since changed. Probe: an MCP request with `reason` produced an action without a `reason` field, while the audit line had it. The REST body forbids extra fields ([`actions.py:46-51`](../../core/onemind_core/actions.py)), so `POST /v1/actions` with `reason` returns `422 conflict` ("Extra inputs are not permitted"). The owner deciding on an agent's request sees the request but not why it was made; `@onemind/ui`'s card has a `reason` slot ("agents must say") that the gateway never fills.

**Fix.** Add optional `reason: str | None = Field(None, max_length=500)` to `ActionRequest` and a `reason` column (a `core` schema step, PLUMBING §3) returned by `Action.to_json`; MCP passes it through; the dashboard and phone show it on the approval card.

<a id="d11"></a>
## D11 (Low). Node-side heartbeat producers step outside the §12.10 enums

These packages are the designated producers of the §12.10 objects (NETWORKING.md:514), but none is in the heartbeat yet (`heartbeat.Status` carries only `update`), so nothing is wrong on the wire today.

- `backup.last_result` must be `succeeded|failed|partial|none` ([`poc-v0.md:484`](../../sdk/contracts/poc-v0.md)). `Agent.Heartbeat` copies the last run's state ([`internal/backup/agent.go:476-488`](../../internal/backup/agent.go)), and runs end `refused` when the fence or space check stops them ([`state.go:29`](../../internal/backup/state.go)). Fix: map `refused` to `failed` in `Heartbeat()`.
- `fabric.leaf_link` must be `up|down|none` (:486). `leaf.Health.State` adds `no_server` ([`internal/leaf/supervise.go:19-22`](../../internal/leaf/supervise.go)). Fix: map `no_server` to `down`, and keep `none` for "no leaf configured".
- §12.21 binds `destinations`, not `targets` (:648), and §12.12 snapshots and runs carry `destination_id` (:513-514). The node API and run records use `target_id` ([`internal/backup/api.go:29`](../../internal/backup/api.go), [`state.go:38`](../../internal/backup/state.go)). Fix: accept `destination_id` on `POST :7480/api/v1/backup/run` and rename the field in run records (keep reading `target_id` from existing state files).
- The comments cite the pre-binding numbering: `internal/mesh/state.go:66-67` says "§12.16" (now Audit; the mesh object is §12.10), and `internal/backup/state.go:33,182,246` and `api.go:13` cite "CONTRACT-12-DRAFT §12.5/§12.11" (now §12.12 and §12.10). Fix: update them in the same PR.

<a id="d12"></a>
## D12 (Low). Error codes are closed enums everywhere

**Contract.** §12.2: new codes exist (`rate_limited`, `unavailable`, `payload_too_large`, `policy_refused`, opt-in `invalid_request`, `method_not_allowed`), and "an unknown code must be handled by its HTTP status class" ([`poc-v0.md:257,263`](../../sdk/contracts/poc-v0.md)).

**Code.** The gateway publishes `ErrorBody.error` as a closed seven-value enum in `/openapi.json` ([`errors.py:29-33`](../../core/onemind_core/errors.py)), so an SDK generated from it (SDK.md) will reject the §12.2 codes; the comment at :13-14 still says adding a code "needs a contract PR", which #39 was. The dashboard and phone accept an error body only if its code is one of the seven ([`dashboard/src/api/client.ts:30-47`](../../dashboard/src/api/client.ts), [`mobile/src/api/client.ts:33-48`](../../mobile/src/api/client.ts)); for any other code they replace the gateway's message with `HTTP <status>` and code `unknown` (:97-100, :128-129).

**Fix.** Publish `error` as an open string with the known values in the description (or `anyOf` enum and string); in both clients keep any string code and its `message`, and branch on the status class when the code is unknown.

<a id="d13"></a>
## D13 (Low). CLI.md describes a tree that moved

- §2 "What exists today" places the commands in `cmd/onemind/main.go` and `cmd/onemind/update.go` ([`CLI.md:36,38`](../leap/dev/CLI.md)); since #38 they are in `cmd/onemind/cli/{node,update,version}.go`, and `main.go` only calls `cli.Run`. Rows :41-42 say the scan gate, `/mcp`, `app-gate`, `app-scaffold` and `app-readme` are "in flight" in worktrees; all are on `main`. §11 (:601) says `update.go` "moves to `cli/update.go` in DEV-CLI-6"; it already has.
- §6.7 (:330) audits on-box updates "as `local:root`". §12.13 (:537) says `onemind update apply` at the console is audited as an owner approval with `approved_via: console`, and §12.1 has no `local` principal kind. One of the two must change; the contract is binding.

**Fix.** Refresh §2 and the §11 row from `git ls-files cmd/onemind sdk/tools core/onemind_core`; align §6.7 with §12.13 (or file a contract PR adding a console principal).

---

## Checked and consistent

These were compared side by side and agree; they need no work.

- **Heartbeat §2:** `internal/heartbeat.Status` field names, nullability and the board and Secure Boot enums match §2 and the dashboard and phone types; the optional `update` object matches §12.10 and `internal/update` writes only its eight states; node-id derivation (sha256 of `/etc/machine-id`, first 12 hex) is identical in Go (`internal/detect`) and Python (`config.derive_node_id`); `storage.state` values in `internal/storage` match §12.10.
- **NATS §12.9:** every subject in code is `onemind.node.<id>.status`, `onemind.audit` or `onemind.event.<type>`; no feature code publishes elsewhere under `onemind.>`.
- **§3 routes:** the 11 routes, the 401/403/404/409/422 mappings, the 405-as-`not_found` rule (§12.2) and idempotent replay behave as written; the dashboard and phone call only these routes, with matching paths and bodies.
- **MCP §11.3 and Hermes §7:** `/mcp` exposes the three tools, refuses non-agents with 403 and has no approve tool; the Hermes seed points `mcp_servers.onemind` at `${ONEMIND_GATEWAY_URL}/mcp` with the §11.2 Secret.
- **Manifests §4/§9.3/§11.2:** all 9 apps load through the gateway's `Catalog` in `schema` mode with no errors; `APP_ID_RE` and the schema agree on the 59-character id.
- **`scan.json` §11.1:** `app-gate` writes exactly the §11.1 shape; the gateway, `app-readme` and `site/src/lib/apps.ts` read only fields it writes; every app's `metadata.tier` agrees with its committed scan result.
- **restic tags §12.12:** `onemind`, `box=`, `gen=`, `unit=`, `node=`, `run=`, `reason=` are written as specified (plus `keep=`).
- **Update enums §12.13:** channel `security|stable` and policy `auto|notify|off` match `internal/update`.

## Known and already tracked (not counted above)

- `/openapi.json` has a response schema only for `GET /v1/apps`; the other eight data routes publish `{}`. [`docs/leap/dev/SDK.md`](../leap/dev/SDK.md) §2 already records it; it must be fixed before any SDK is generated (DEV-SDK-1).
- §12 modules that have not shipped (the `OneMind-Request-Id` and `OneMind-API-Version` headers, `/v1/me`, `/v1/events`, `/v1/plans`, step-up approvals, HTTPS on `:8443`, the `child` role, the `plugin`, `automation` and `node` kinds, `spec.agent.scopes`) are absent by design: §12 says a route "exists only once its module ships". They are tracked as C12-A … C12-H and the CORE/DEV epics in STATUS.md.

## Noticed outside this lens (not audited)

Doc staleness that is not interface drift, for whoever owns those files: the CHANGELOG's "Unreleased" table still lists merged branches (`feat/core-plumbing`, `feat/app-pipeline`, `feat/core-net`, …); `docs/security/THREAT-MODEL.md:120-126` cites `app.py` line numbers that moved to `routers/` and `context.py` in #38; STATUS.md lists CORE-NET-3 and CORE-NET-4 as `todo` although part 1 of each is merged (73fa890).
