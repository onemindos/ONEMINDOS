<!-- SPDX-License-Identifier: Apache-2.0 -->
# Security attack suite

Tests that attack the gateway the way a hostile app, a tricked AI agent or a stranger on the LAN would (threat model: [`docs/security/THREAT-MODEL.md`](../../../docs/security/THREAT-MODEL.md)). They run in the normal core CI (`make -C core test`, SQLite then PostgreSQL), so no extra job is needed.

> **Explain it like I am the founder**
> Unit tests check that a feature works. These check that it cannot be abused. The most important one reads the list of routes from the running gateway itself and tries every route as every kind of caller. If someone adds a route and forgets to say who may call it, the build fails. Nobody has to remember to write that test.

| File | What it attacks | Contract |
|---|---|---|
| `test_authz_matrix.py` + `sec_policy.py` | Every route x every principal kind against **one policy table**. It checks the exact status, the error body, that a refused request changed nothing, and that every 403 is audited | §3, §11.2-§11.3, §12.1, §12.6 |
| `test_sandbox_escapes.py` + `fixtures/sandbox/` | Every Kubernetes escape we know of, each refused with the right rule id of `sdk/policy/app-objects.yaml` | H-01..H-04, §12.2 `policy_refused` |
| `test_injection_traversal.py` | Path traversal on the dashboard files, header injection, SSRF on URL settings, oversized bodies, JSON bombs | H-18, H-20, H-29 |
| `test_mcp_injection.py` | A scripted agent that obeys injected text. It cannot approve or widen its rights, and what it writes stays untrusted | §11.3, §12.19, MCP.md §6 |
| `sec_world.py` | Helpers: a fresh gateway per test, how to mint each principal kind, and one valid request per route (a "probe") | |

## Principal kinds (matrix columns)

`none`, `owner`, `adult`, `guest`, `child`, `agent` (tokens file), `app-agent` (issued at install, §11.2), `plugin`, `automation`, `node`, `expired`, `revoked` (deleted from the tokens file while the gateway runs) and `revoked-agent` (after `app.remove`). A kind that cannot exist on the current tree skips, and the skip reason names the stream that adds it. `child` and `expired` become live with household identity (PR #41). `plugin`, `automation` and `node` stay pending until their streams write a `mint()`. If `onemind_core.auth` learns a kind or role that has no minted column, `test_every_principal_kind_has_a_column` fails.

## Three markers

- **pending** (a policy row's `pending`, or a skip naming a stream): the route or feature is in flight on another branch. The cells skip until it lands, then run with the statuses already written. The identity rows were checked against PR #41's tree, and the sandbox fixtures against PR #40's.
- **DECIDE** (policy cell): the contract leaves the status to the stream that creates the kind. The cell fails as soon as that kind exists, so the stream must write the status down.
- **gap / finding** (strict `xfail` with a reason): a real escape or defect found by this suite and not fixed yet. Fixing it makes the test pass unexpectedly, and strict mode turns that into a failure. The fixing PR then removes the marker (for a sandbox gap, it writes the new rule id into the fixture).

## How to add things

- **A new route:** add a row to `POLICY` in `sec_policy.py`. Give the status for every kind, a probe (a valid request for the route) and the contract section it follows.
- **A new principal kind:** write its `mint()` branch in `sec_world.py`, add it to `MINTABLE` and replace its `DECIDE` cells.
- **A new sandbox rule:** add an escape fixture with `Expected: <rule>.`. `test_every_object_rule_has_an_escape_fixture` fails until you do.
- **A new URL setting reachable through the API:** add an SSRF probe. `test_api_reachable_url_settings_bring_an_ssrf_probe` lists the routes and action types it watches.

Run only this suite with `cd core && uv run pytest -q tests/security`.

## Narrowed A5 integration checkpoint

Main's H-31 alert-fix scope and passkey approval guards are retained alongside the
handler's denial audit. H-32's node cap and the canonical
`core/tests/test_route_authz.py` are retained; this suite does not replace that inventory
or add a second public-route allowlist. The shipped sandbox checker and its rules are
required rather than optional imports/skips.

`test_notify_boundaries.py` exercises the production address checks (including
embedded IPv4 and a positive public-address control), depth-bounded MCP copying and
handler denial audit without external requests or database cleanup. These narrow
tests are not a full HTTP authorization matrix or a full backend suite.

Known strict-xfail findings and pending principal kinds remain visible, not accepted
as an all-green delivery. Full SQLite/PostgreSQL, H-31 runtime, canonical inventory
and Go execution still need final-head evidence. Existing tests explicitly drop
tables, remove temporary trees or delete application/test rows; running them requires
the corresponding bounded cleanup authorization. No production/shared resource
should be used. Owner merge authorization is a separate gate, not a test failure.
