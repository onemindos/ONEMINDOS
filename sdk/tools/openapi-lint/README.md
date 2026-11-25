<!-- SPDX-License-Identifier: Apache-2.0 -->
# openapi-lint (#874)

`python3 -I sdk/tools/openapi-lint` checks the committed API contract, [`sdk/openapi/onemind-v1.json`](../../openapi/onemind-v1.json), against five rules. `make -C sdk check-stale` runs it (so the `ci-sdk` job does), and `make -C sdk contract-lint` runs it alone. It is stdlib Python and reads only the spec: it changes no route.

**Why.** The SDKs, the `onemind` CLI and the MCP catalogue are all made from this one file. Without rules each new route picks its own auth, paging and error shape, and every client has to special-case it. A lint turns "please keep the contract one shape" into a check that fails the pull request.

| Rule | What it asks of every operation | Source |
|---|---|---|
| `security` | Names a security scheme that `components.securitySchemes` declares, or is on `public.txt` with a reason | contract §3 (who may call what), `core/tests/sec_policy.py` |
| `scopes` | A secured operation lists at least one scope; for an `oauth2` scheme the scope is declared by the scheme | contract §12.6 (roles, scopes, tokens) |
| `paging` | A list route (it takes `limit`, `cursor`, `offset`, `page`, or returns `next_cursor`) returns a JSON array, takes `?limit=` (integer) and `?cursor=`, and declares a `Link` header (`rel="next"`) | contract §12.1 Lists |
| `error-schema` | Every 4xx, 5xx and `default` response has a body, and that body is `ErrorBody` | contract §3 error envelope, §12.1 |
| `idempotency` | Every POST, PUT, PATCH and DELETE takes an `Idempotency-Key` header (any letter case), or is on `idempotency-exempt.txt` with a reason | contract §12.1 Idempotency |

## The files

- `public.txt`: routes that are public on purpose. Each matches a `sec_policy.py` row whose unauthenticated cell is 2xx. Adding one is a security review.
- `idempotency-exempt.txt`: unsafe routes that take no key on purpose (a replay store must never keep fresh tokens; tus uploads use `Upload-Offset`; `POST /v1/actions` keeps its §3 body field).
- `baseline.txt`: the violations already in the spec when the lint landed, one line each, `rule METHOD /path owner=<area>`. The lint fails on any violation that is not listed, and on a listed line that no longer fails (delete it in the PR that fixes the route). Never add a line to get green.

`python3 -I sdk/tools/openapi-lint --print-baseline` prints every current violation in baseline format, for review. Output names the rule and the route: `openapi-lint: scopes: GET /v1/things: secured by 'bearer' but lists no scope`. Exit codes: 0 clean, 1 a rule failed, 2 an input file cannot be read.

Tests: `python3 -I -m unittest discover -s sdk/tools/tests -p 'test_openapi_lint.py'` (one bad fixture per rule, the committed spec with its baseline, and a new route without scopes).
