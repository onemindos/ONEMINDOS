<!-- SPDX-License-Identifier: Apache-2.0 -->
# Property tests and fuzzing

**Date:** 2026-11-12 · Branch `feat/test-property-fuzz`, PR #55. Other files in `docs/testing/` belong to other streams.

**Agent A revalidation:** #40's checker/rules are required at collection. Production fixes accompany removal of the thirteen expanded F-LIC-1/F-AUD-1..3/F-SBX-1 expected failures: strict UTF-8/object/duplicate-key audit decoding (verification and resume), conservative licence confirmation plus full token coverage, and policy-v3 pod/container checks. Core/API/Go fuzz test jobs check out the PR head explicitly. The temporal oracle rejects dispatch-before-approval, duplicates and ledger/audit decider mismatch. Action properties now predict exact request/decision results independently before each call, mandate successful owner decisions and agent refusals in every machine, and compare per-action dispatch identities with executor type/app calls. Fresh retained SQL resources replace hard-coded SQLite/shared HTTP state: PostgreSQL legs require the actual psycopg dialect and verify isolated schemas on two simultaneous connections. Boundary and mutation controls cover pending caps, expiry equality, replay ordering, scan-age/skew limits, crashes, and blanket-refusal mutants. These changes are not full-suite acceptance: exact-final-head backend/API/Go CI and independent review remain required. Existing broad-suite setup and successful remove paths delete test data; restricted local diagnostics do not replace those full suites.

> **Explain it like I am the founder**
> A normal test checks one example: "an agent that approves action 42 gets 403". A **property test** states a rule and lets a tool invent hundreds of examples to break it: "whoever the principal is, whatever happened before, an action is only ever approved by a person with role owner". When it finds a counter-example it **shrinks** it to the smallest one that still fails, so the bug report is short.
> **Fuzzing** is the same idea aimed at parsers and APIs: feed them random, broken and hostile input and check they never crash or accept something they should refuse.
> The **oracle** is how the test knows the right answer. It must come from the contract, not from the code under test, or a bug in the code also bends the test. Mutation controls deliberately break selected behaviors and require the oracle to reject them; they do not establish that every possible bug is caught.

## What runs where

| Suite | Tool | Files | When | Budget |
|---|---|---|---|---|
| Gateway and SDK properties | Hypothesis 6.170.15 | `core/tests/test_properties_*.py`, resource and action-model controls | every `make -C core test`, so every PR touching `core/` or `sdk/` (`ci-core.yml`, actual SQLite and PostgreSQL legs) | PR example budgets; runtime depends on backend |
| Same, deep | Hypothesis | same | nightly, `api-fuzz.yml` job `properties` (SQLite; PostgreSQL runs at PR depth in `ci-core`) | 20x property examples; deterministic boundary controls unchanged |
| API fuzzing | Schemathesis 4.33.1 | `.github/workflows/api-fuzz.yml`, `core/tests/api_fuzz_check.py` | PRs touching `core/`, `sdk/schema/`, `sdk/tools/applib/` or app manifests; nightly | 40 cases per operation on a PR, 400 at night |
| Go fuzz targets | `go test -fuzz` | `internal/{heartbeat,detect,update}/fuzz_test.go` | seed corpus in every `go test` (`ci-onemindd.yml`); exploration in `go-fuzz.yml` on PRs touching `internal/` or `go.mod`, and nightly | 30 s per target on a PR, 8 min at night |
| Dependency licences | pytest | `core/tests/test_dependency_licences.py` | every core test run; again after the fuzz group is installed | – |

## How to run them

### Backend isolation and retained diagnostics

`property_resources.py` allocates a new file-backed SQLite database or PostgreSQL
schema **inside each generated example** (including replay/shrinking). Gateway
restarts within that example keep the same ledger and audit. HTTP discovery caches
only the OpenAPI operation description; generated requests get fresh app/guard state.
PostgreSQL uses a validated random schema and connection-startup `search_path` with
no `public` fallback, verifies the live database/schema on two simultaneous connections,
and verifies registered tables resolve there. It never resets or drops schemas.
`ONEMIND_TEST_DB_URL` must identify a designated test PostgreSQL database with CREATE
SCHEMA permission. `ONEMIND_PROPERTY_BACKEND=postgresql` fails if the URL is absent or
selects another backend; it never silently falls back. This namespace isolation is
not a security boundary against hostile SQL under the same database role.

Set `ONEMIND_PROPERTY_ARTIFACTS` to an explicitly retained directory for diagnostic
runs. The allocator records sanitized per-example manifests, closes handles only,
and retains files, schemas and rows. A factory stops at
`ONEMIND_PROPERTY_MAX_ALLOCATIONS` (default 25000) rather than reusing or pruning old
examples. With this directory set, Hypothesis cache persistence is disabled, not its
budgets/assertions/shrinking. CI uploads **only allocation manifests**, never database
files or notification key files. The HTTP protocol harness uses the supported
`notify.worker=false` setting: it does not cover delivery/retention worker behavior.

Retention is **not** permission to run deleting application paths. The full state
machine still exercises successful remove (which deletes a test-created app-state
row); ordinary PostgreSQL suite fixtures still drop tables. Obtain explicit bounded
deletion authority before running those locally, or use the exact-head existing CI.
Non-deleting `test_property_resources.py` and `test_action_model_controls.py` canaries
prove backend isolation, functional HTTP decisions, model positive/negative controls
and boundaries, not the complete state machine or complete backend suite.

Nothing here needs a tool installed on the Mac beyond what the repo already uses (uv, Go). Schemathesis is never installed on the Mac: it runs in CI, or in a Lima VM you create and delete.

```sh
# Hypothesis properties (uv installs the dev group, Hypothesis included, into core/.venv)
make -C core test                                     # whole suite, properties included
cd core && uv run pytest -q tests/test_properties_actions.py
cd core && ONEMIND_PROPERTY_DEPTH=deep uv run pytest -q tests/test_properties_*.py   # nightly budget
cd core && uv run pytest -q tests/test_properties_actions.py --hypothesis-show-statistics  # coverage events

# A failure prints the smallest example and a line @reproduce_failure('6.170.15', b'...'):
# paste it above the test to replay exactly that case. Failing examples are also kept in
# core/.hypothesis/ (gitignored) and tried first on the next run.

# Go: seed corpus only (fast, what CI's unit job does), then explore one target
go test ./internal/...
go test -run '^$' -fuzz '^FuzzTUFMetadataTampering$' -fuzztime 60s ./internal/update
# A failing input is saved under internal/<pkg>/testdata/fuzz/<Target>/; commit it with the fix
# and it becomes a permanent regression case of `go test`.

# API fuzzing: in CI
gh workflow run api-fuzz.yml --ref <branch>
# or inside a throwaway Lima VM (not on the Mac): uv sync --locked --group fuzz in core/, then
# follow the steps of .github/workflows/api-fuzz.yml (tokens, gateway, two schemathesis runs, checks).
```

## The properties

| Area | Property (holds for every generated case) | Test |
|---|---|---|
| Audit hash chain (§3) | The log AuditLog writes verifies. Changing one record (any value, a key added or removed, `seq`, `prev_hash`, `hash`), deleting any record but the last, swapping or duplicating records is reported **at the first line that differs**, with every earlier line counted as verified. After any one-character edit, verify() reports it or no record's content changed (e.g. `1e+16` written `1E+16`) | `test_properties_audit.py` |
| Action state machine (§3, CLAUDE.md "AI never actuates without human approval") | Table: no edge out of a terminal state, nothing returns to `awaiting_approval`, `accepted` is entered only from `awaiting_approval`, and the repository refuses every pair the table does not list. Stateful model (random requests, approvals, denials, clock jumps, executor outcomes and crashes, gateway restarts, from owners, adults, guests, an operator agent, an app's agent principal, an agent configured with role owner and a person with role agent): every observed state follows the table; every approved, denied or executed action was decided by a person with role owner, and the audit log agrees; the executor ran exactly once per owner-approved dispatch; nothing is left half-dispatched; an app's agent token is live exactly while the app is installed; the audit chain verifies | `test_properties_actions.py` |
| Any expiry | Any `expires_at` the request model accepts gets an action or a 4xx, never an unhandled exception | `test_properties_actions.py` |
| Idempotency keys (§3) | A replay returns the same action with `created=False`; the same key with any other type, app, requester or expiry is 409 `conflict`; a refused key stays free; the same instant written with another UTC offset is the same request; every refusal is in the audit log with who asked | `test_properties_actions.py` |
| Licence classifier (§9.4) | `classify()` equals a reference evaluator (OR = best, AND = worst) on every generated expression, fully parenthesised or with minimal parentheses (precedence WITH > AND > OR); OR and AND are commutative, associative, idempotent, absorptive and distributive; OR never worsens and AND never improves a class; any malformed expression is `blocked`; no input raises; `gate()` without a matrix row is capped by GitHub's one confirmed term; `normalise()` keeps the class of an expression written the usual way | `test_properties_licence.py` |
| Install sandbox (H-01..H-04) | Generated sets of allowed objects (every allowed kind, restricted pod specs, init containers, allowed volumes and storage classes, namespaced RBAC) pass. Adding any one forbidden field to any one of them is refused with that rule's id and that object's kind and name: host namespaces, hostPath, hostPort, privileged, a capability not on the list, hostProcess, root, privilege escalation, kept capabilities, unconfined seccomp, a volume type restricted forbids, an image without a digest, a foreign namespace, NodePort or LoadBalancer, externalIPs, a storage class not on the list, wildcard or escalating Role rules, a ClusterRole binding, a foreign subject, a kind not on the list, a List wrapper. At the reviewed PSA baseline level the host-level rules still hold. Active now that #40 shipped; missing checker or rules fails collection | `test_properties_sandbox.py` |
| Heartbeat ingest (§2) | A heartbeat is kept only for exactly `onemind.node.<id>.status` with a valid id, at most 64 KiB, a JSON object with schema v1 and `node_id` equal to the subject's id; the registry holds the last kept heartbeat per node and nothing else; kept heartbeats never carry the privacy-forbidden keys; `status` and `last_seen` come from the hub's clock; the hub's node id rule equals onemindd's (`internal/heartbeat` `nodeIDRe`) | `test_properties_heartbeat.py` |
| HTTP surface (in-process) | Every method an operation does not document gets 405 with an Allow header listing exactly the documented ones; any bytes as a POST body, from the owner or the agent, get a documented status, never 400 or 5xx | `test_properties_api.py` |
| API (whole gateway) | First the agent requests one install per catalog app, and Schemathesis's dictionaries aim `action_id` at those actions (80 %) and `app_id` at real apps (60 %), so approve and deny are tried on actions that exist. Then Schemathesis, all checks, every operation except `/mcp`: no 5xx, documented status codes, content types and bodies, invalid input refused, valid input accepted; `/mcp` for server errors only (its JSON-RPC answers are outside OpenAPI). After the agent-only run nothing was approved, denied or dispatched; after the owner run every decision is the owner's; the audit chain verifies; the gateway log has no traceback | `api-fuzz.yml` |
| Node id → NATS subject | An id ValidateNodeID accepts gives a literal four-token subject (no `*` or `>`) whose third token is the id; accepted exactly when it is 1-64 of `A-Za-z0-9_-` | `FuzzNodeIDSubject` |
| Heartbeat object | Decoding then encoding a Status is a fixed point; every §2 key is present; `update` only when set; no serial, MAC, IP, user, device or path key survives | `FuzzStatusJSON` |
| RAUC status parser | Never panics; slots always an array, names sorted per entry, no device path in the output | `FuzzParseRAUC` |
| os-release parser | Never panics; keys trimmed, no `=`, newline or leading `#`; writing the map back and parsing it again gives the same map | `FuzzParseKV` |
| Release versions | Reflexive, antisymmetric, transitive; a leading `v` or `+build` never changes the order | `FuzzCompareVersions` |
| Target selection | Only an eligible target is offered (board, compatible, canonical path, newer than the running version, `min_from_version`, security flag on the security channel, not refused by the health gate), the newest eligible one, every other target skipped with a reason, and the bundle lands inside the download directory | `FuzzSelect` |
| Tampered TUF channel | One metadata file the box fetches is edited (bytes overwritten, inserted or deleted, the file replaced or removed); the TUF client either refuses the channel or ends with exactly the signed index. `TestTUFTamperingHarness` proves the harness accepts an untouched or whitespace-only file and refuses a changed version | `FuzzTUFMetadataTampering` |

### Mutation checks (do the tests have teeth?)

The older rows below record original branch mutation experiments, not fresh final-head
acceptance. Current executable controls in `test_property_resources.py` and
`test_action_model_controls.py` require the model to reject blanket request 404/409
and owner decision 409 mutants, alongside real owner-success and failed-agent controls.

| Broken on purpose | Caught by |
|---|---|
| An agent with role owner counts as an owner (`Principal.is_owner`) | state machine and idempotency tests. The first version used `is_owner` as its own oracle and missed it; the oracle is now written from the contract |
| The approve path skips the owner check for agents | state machine |
| The ledger allows `cancelled → accepted` | table test |
| A failed install keeps the app's agent token | state machine |
| An idempotent replay ignores who asked | idempotency |
| verify() skips the `prev_hash` check | two audit properties |
| OR takes the worst class; trailing tokens ignored; an unknown WITH exception keeps the class; the gate drops the GitHub cap | licence properties (each one) |
| The sandbox ignores hostPID; skips init containers; accepts a 63-hex digest; lets Roles name the RBAC group | sandbox properties (each one) |
| Ingest stops matching `node_id` to the subject; keeps forbidden keys; lets a dot into the node id | heartbeat properties (each one) |

One mutation survived and is harmless: ingest no longer dropping a sender's `last_seen`, because the registry's view always overwrites it with the hub's clock.

## Findings

| Id | Severity | What | Status | Owner |
|---|---|---|---|---|
| F-API-1 | Medium | `POST /v1/actions` with `expires_at` near year 1 or 9999 and a UTC offset (e.g. `9999-12-31T23:59:59-23:59`) crashed with OverflowError: a 500 for owners and agents alike, with nothing in the audit log | **Fixed in this branch**: the request model refuses it (422). Regression: `test_any_expiry_gets_an_answer_not_a_crash` with both edges as explicit examples | gateway core (`actions.py`) |
| F-API-2 | Low (RFC 9110 conformance) | Found by Schemathesis on its first run: every 405 lacked the `Allow` header (the error handler rebuilt the response without Starlette's), Starlette's own header named only the first route of a path (`/v1/actions` is GET and POST), and GET on a POST-only path (`/v1/actions/{id}/approve`) answered 404 because the dashboard's fallback claims every GET | **Fixed in this branch**: `errors.py` lists every documented method for the path; the fallback answers 405 on API paths that exist for other methods | gateway core (`errors.py`, `routers/static.py`) |
| F-API-3 | Low | Found by Schemathesis: a POST body that is not UTF-8 got an undocumented 400 (FastAPI's "error parsing the body") instead of the 422 every other malformed body gets (§3, §12.2) | **Fixed in this branch**: 422 `conflict` | gateway core (`errors.py`) |
| F-LIC-1 | Medium (gate bypass) | Historical: lossy normalization let different parenthesised licence expressions share a research confirmation | Fixed here: preserve groups and arbitrary prose, retain only the reviewed EDL/BSD alias; ordinary regression | app pipeline (`sdk/tools/applib/licence.py`) |
| F-AUD-1 | Low | Historical: non-UTF-8 audit bytes raised instead of reporting the damaged line | Fixed here: binary per-line UTF-8 decoding; ordinary regressions | security (CORE-SEC-6, `audit.py`) |
| F-AUD-2 | Low | Historical: non-object JSON records raised AttributeError or TypeError | Fixed here: require a JSON object in the shared verification/resume decoder; ordinary regressions | security (CORE-SEC-6) |
| F-AUD-3 | Low | Historical: last-key-wins JSON hid a forged earlier duplicate value | Fixed here: reject duplicate keys at every object level, without requiring canonical input serialization | security (CORE-SEC-6) |
| F-SBX-1 | Low (defence in depth) | Historical: pod UID 0, pod seccomp Unconfined, procMount, AppArmor, SELinux and sysctls were missed before apply | Fixed here: version-3 rule checks and ordinary negative/positive/malformed-input regressions; not complete future PSA parity | install sandbox (PR #40, CORE-SANDBOX-1) |
| Note | – | Tail truncation: a hash chain alone cannot see its last records removed. Signed, anchored checkpoints close it (H-10, contract §12.16); `test_removing_the_last_record_needs_a_checkpoint` documents the limit | By design | security (H-10) |
| Note | – | Audit lines hold U+0085 and U+2028 raw (canonical JSON with `ensure_ascii=False`). Readers must split the file on `\n` only; Python's `str.splitlines()` breaks such a record in two | For the audit readers (`onemind audit tail`, DEV-API-9) | CLI, gateway |
| Note | – | `BadReleases.Excluded` matches the exact version string, while the version order treats `v0.2.0`, `0.2.0.0` and `0.2.0+b1` as equal to `0.2.0`: a signed re-release under an equivalent string is offered again after the gate marked `0.2.0` image-bad. Only the release signer can publish one; whether a rebuild should be retried is a policy question | For the updater owner | updater (`internal/update`) |

All thirteen expanded cases now have production fixes and ordinary regression tests, with no expected-failure markers in these three property modules. This does not certify unrelated expected failures on other branches. The stricter licence normalizer deliberately does not treat arbitrary research prose as confirmation of a shorter expression; only the reviewed EDL/BSD alias remains. The sandbox rule version is 3, based on the Kubernetes v1.37 baseline values; it is not a promise of complete parity with future PSA versions. No existing app manifest changes are bundled. A real Kustomize v5.8.3 render of all nine current apps and live upstream SPDX metadata produced no policy-result or licence-class change relative to main during revalidation; this is not a complete scan or live-cluster gate, and final-head CI remains required.

## Test-only dependencies

| Package | Version | Licence | Group | Why |
|---|---|---|---|---|
| hypothesis | 6.170.15 | MPL-2.0 (L1 in the Market list; file-level copyleft, used unmodified) | `dev` | property tests; never in the gateway image (`core/Dockerfile` syncs with `--no-dev`) |
| sortedcontainers | 2.4.0 | Apache-2.0 (reviewed: its metadata says "Apache 2.0") | `dev`, via hypothesis | – |
| schemathesis | 4.33.1 | MIT | `fuzz`, CI only | API fuzzing. Not a default group: `make -C core test` and the image never install it |
| its dependencies | see `core/uv.lock` | MIT, BSD-3-Clause, Apache-2.0 (all L1) | `fuzz` | graphql-core, harfile, hypothesis-graphql, jsonschema-rs, markdown-it-py, mdurl, pyrate-limiter, requests, rich, urllib3, werkzeug, charset-normalizer |

Versions and file hashes are pinned in `core/uv.lock` (`uv sync --locked` in CI). Both versions were at least six days old when pinned. `test_dependency_licences.py` reads every installed distribution's licence (PEP 639 expression, then an SPDX `License` field, then a single unambiguous classifier, then a reviewed table with the licence file's URL) and runs it through the Market classifier: L1 passes, anything else needs a reviewed entry. Reviewed today: psycopg and psycopg-binary (LGPL-3.0-only, used unmodified as a separate library), typing-extensions (PSF-2.0), sortedcontainers (Apache-2.0), uvloop (MIT OR Apache-2.0).

## Adding a property or a fuzz target

- Write the oracle from the contract or the spec, never by calling the function under test (see the first mutation row above).
- Check coverage, not only the pass: `event()` labels plus `--hypothesis-show-statistics` show whether the interesting branches (an approval that succeeds, a heartbeat that is kept) are actually reached.
- Use `@budget(n)` from `core/tests/props.py` so the nightly run scales it. Keep the PR budget small; the nightly run is where depth goes.
- A bug the tests find in another stream's file: report the unresolved blocker and coordinate ownership. Do not add an expected-failure marker to claim an all-green delivery. Remove an existing marker only alongside the production fix and exercised regression.
- Go: one property per target, seeds that reach the interesting paths, and inputs that mean the same thing in every fuzz worker (the TUF target fuzzes edits of signed files, not whole files, because each worker signs with its own keys).
