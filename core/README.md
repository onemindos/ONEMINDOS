# OneMind Core gateway (v0)

The **gateway** is the front door of a OneMind hub. Every screen of the dashboard, every node
heartbeat and every AI agent talks to the box through it. It implements
[`sdk/contracts/poc-v0.md`](../sdk/contracts/poc-v0.md) **section 3** exactly and is the v0
subset of workstream **B9** (D-B9.5 ledger, D-B9.6 approvals, D-B9.7 audit, D-B9.8 routes) in
[brief 30](../research-output/30-NEXT-ULTRACODE-BUILD-BRIEF.md). Language and framework follow
**BD-02** (Python + FastAPI for the Core); the datastore follows **BD-04** (PostgreSQL target).

## Why it exists (plain English)

OneMind's rule is **"AI never actuates without human approval"** (CLAUDE.md, D-B9.6). The gateway
is where that rule is enforced in code, not in a prompt:

1. Anyone who wants to change something (install an app, remove one) does not *do* it. They file
   an **action**: a written request with exact parameters, an expiry time and an idempotency key.
2. The action waits in **`awaiting_approval`**. Only a **person whose role is owner** may approve
   or deny it. An AI agent may file requests, but if it tries to approve one it gets
   `403 permission_denied`, and that attempt is itself written to the audit log.
3. Only after approval does the **executor** run (for real: `kubectl apply -k`). The executor is
   the only part of the gateway that touches the outside world.
4. Every decision lands in a **hash-chained audit log**: each line carries the hash of the line
   before it, so editing, deleting or reordering any past line is detectable (`make audit-verify`).

**Terms**
- **Principal:** who is calling (a person or an agent), with a role (owner, adult, guest, agent).
- **Bearer token:** a secret string sent as `Authorization: Bearer <token>` that identifies the principal.
- **Idempotency key:** a client-chosen ID. Sending the same request twice (say, after a network
  blip) returns the same action instead of creating a second one.
- **Ledger:** the database table of actions and their state history.
- **Compare-and-swap:** "change the state from A to B *only if* it is still A". Two owners clicking
  approve at the same moment cannot both trigger an install.
- **Hash chain:** `hash = sha256(prev_hash + canonical_json(line))`. Same idea as git commits.
- **NATS:** the message bus. Nodes publish heartbeats to `onemind.node.<id>.status`; the gateway
  listens and builds the node list. The gateway also publishes each audit line to `onemind.audit`.

## What is in here

| File | Job |
|---|---|
| `onemind_core/app.py` | FastAPI routes of contract §3, dashboard static files with SPA fallback |
| `onemind_core/auth.py` | Token file → principals; agents can never be owners |
| `onemind_core/actions.py` | Request / approve / deny, expiry, preconditions, dispatch |
| `onemind_core/ledger.py` | `ActionRepository` interface + SQLAlchemy implementation (SQLite or PostgreSQL) |
| `onemind_core/executors.py` | `noop` and `kubernetes` executors and their outcome rules |
| `onemind_core/audit.py` | Hash-chained JSONL log, `verify()`, `onemind-audit-verify` CLI |
| `onemind_core/nodes.py`, `bus.py` | Heartbeat registry (online/stale/offline) and the NATS connection |
| `onemind_core/catalog.py` | App catalog from `ONEMIND_APPS_DIR/*/onemind.app.yaml` |

### Action states
```
requested → awaiting_approval ─┬→ accepted → dispatched ─┬→ succeeded
                               │                         ├→ failed
                               │                         └→ outcome_unknown
                               ├→ expired     (expires_at passed; approving then → 409 expired)
                               └→ cancelled   (owner denied)
```
- Executor exit 0 → `succeeded`; non-zero exit or missing kubectl → `failed`;
  timeout or crash → `outcome_unknown` (we cannot know what was applied). **Nothing is ever
  re-dispatched automatically**; a person decides.
- Preconditions are checked twice: when the request is filed and again at approval
  (e.g. two install requests for the same app: approving the second returns
  `409 stale_precondition` and leaves it in `awaiting_approval`, for the owner to deny or let expire).
  At approval the app is claimed (`installing`/`removing`) by a compare-and-swap in the same
  transaction as `accepted`, so two different actions for one app cannot both reach the executor.

### Node status
`last_seen` is when the *gateway* received the heartbeat (its own clock, so a node with a wrong
clock cannot look fresh). `online` ≤ 30 s, `stale` ≤ 120 s, `offline` after. Heartbeats whose
`node_id` does not match the subject, that are not JSON, lack the schema tag or exceed 64 KiB are
dropped. Fields the contract forbids (MAC, serial, IP, user names) are stripped if a node sends them.

### Kubernetes executor (exact commands)
```
install: kubectl apply -f -   (Namespace app-<id>, label onemind.io/app=<id>)
         kubectl apply -k <apps_dir>/<id>/manifests -n app-<id>
remove:  kubectl delete -k <apps_dir>/<id>/manifests -n app-<id> --ignore-not-found=true
         kubectl delete namespace app-<id> --ignore-not-found=true
```

## Run it

Needs [uv](https://docs.astral.sh/uv/) (it downloads Python 3.12 itself).

```sh
make -C core test               # 117 tests, SQLite, no NATS (1 NATS test skipped)
make -C core test-integration   # all 118 tests on PostgreSQL 17 + real NATS 2.10 (needs Docker)
make -C core run                # gateway on http://127.0.0.1:8080, noop executor, DEV tokens
curl -s localhost:8080/healthz
TOKEN=...   # the owner token from examples/tokens.example.yaml (dev only)
curl -s -H "Authorization: Bearer $TOKEN" localhost:8080/v1/apps
make -C core audit-verify       # verify ./data/audit.jsonl
make -C core image              # docker image for this machine
make -C core image-multiarch    # amd64 + arm64 via buildx
```
`make run` uses `apps/` and `dashboard/dist/` from the repo when those streams have landed them,
else the test fixtures in `core/tests/fixtures/`.

Container (build context is the repo root, so `sdk/schema` gets copied in when it exists):
```sh
# Loopback only: the example tokens are public, so never publish them on a LAN-facing port.
docker run --rm -p 127.0.0.1:8080:8080 \
  -v "$PWD/core/examples/tokens.example.yaml:/cfg/tokens.yaml:ro" -e ONEMIND_TOKENS_FILE=/cfg/tokens.yaml \
  -v "$PWD/apps:/opt/onemind/apps:ro" onemind-core:dev
```
Runs as uid 10001 (non-root), data in `/var/lib/onemind`, kubectl v1.37.2 (sha256-pinned) included.

### Environment
| Var | Default | Meaning |
|---|---|---|
| `ONEMIND_TOKENS_FILE` | none (everything 401) | YAML token → principal map, see `examples/tokens.example.yaml` |
| `ONEMIND_DB_URL` | `sqlite:///./data/onemind.db` | or `postgresql://user:pw@host/db` (psycopg 3) |
| `ONEMIND_APPS_DIR` | `./apps` | Market folder |
| `ONEMIND_DASHBOARD_DIST` | none | built dashboard served at `/` |
| `ONEMIND_EXECUTOR` | `noop` | `noop` or `kubernetes` |
| `ONEMIND_NATS_URL` | `nats://127.0.0.1:4222` | empty string disables NATS |
| `ONEMIND_AUDIT_PATH` | `./data/audit.jsonl` | audit log |
| `ONEMIND_NODE_ID` | sha256(`/etc/machine-id`)[:12] | hub id in `/v1/instance` (null if neither exists) |
| `ONEMIND_APP_SCHEMA` | `sdk/schema/onemind.app.schema.json` if present | manifest JSON Schema |
| `ONEMIND_DATA_DIR`, `ONEMIND_HOST`, `ONEMIND_PORT`, `ONEMIND_INSTANCE_NAME`, `ONEMIND_KUBECTL`, `ONEMIND_EXECUTOR_TIMEOUT_S` | `./data`, `0.0.0.0`, `8080`, `OneMind`, `kubectl`, `300` | |

## v0 shortcuts (from the contract; must be removed before a box ships)
- **Static bearer tokens** from a YAML file (Kanidm + OIDC/passkeys replace this: BD-03, D-B9.1/2).
  The example tokens are public placeholders: **never use them on a reachable box.** Prefer
  `sha256:<hex>` keys so the file holds no secret.
- **SQLite by default** behind the repository interface; PostgreSQL works (tested) and is the target (BD-04).
- **Nodes publish straight to the hub's NATS**, no leaf nodes, no NATS auth/TLS yet.
- Audit is a local JSONL file + best-effort NATS publish, not yet a JetStream stream (D-B9.7).
- Dispatch runs synchronously inside the approve request (no transactional outbox yet, D-B9.5).

## v0 deviations (flagged for the contract owner)
- §3 has no error code for a malformed body or a wrong method. The gateway uses only §3 codes:
  a body that fails validation gets HTTP 422 `{"error": "conflict"}` with the bad fields named in
  `message`; a wrong method gets HTTP 405 `{"error": "not_found"}`. A dedicated code
  (e.g. `invalid_request`) needs a poc-v0.md amendment PR that the dashboard adopts too.
- `401` responses carry `WWW-Authenticate: Bearer`.

## Known gaps
- No `expected_version` on `POST /v1/actions` (D-B9.5 asks for it; contract v0 does not).
- No policy engine (D-B9.4), MCP façade (D-B9.2), approvals push to phone (D-B9.6) or offline sync.
- The kubernetes executor is tested with a fake runner and a missing binary, not against a live k3s yet.
- 401s are audited at most once a minute (`auth.rejected`, with a `suppressed_since_last` count),
  so an unauthenticated poller cannot flood the log. Refused action requests, approvals and
  denials are audited as `action.rejected` (403s as `authz.denied`).
