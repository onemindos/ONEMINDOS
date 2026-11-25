<!-- SPDX-License-Identifier: Apache-2.0 -->
# Client protocol versions (issue 697)

**Why this exists.** A phone app in someone's pocket is often months older than the hub it talks to. If the hub changes an answer the app reads, the old app does not fail politely: it crashes or shows wrong data. This contract makes that impossible to do by accident. Every client states which protocol generation it speaks, the hub serves the current generation and the one before it (N and N-1) for at least 12 months, refuses anything older with a clear "Update needed" answer, and CI replays recorded requests of every older generation still served so a breaking change fails a test instead of a phone.

Code: `core/onemind_core/protocol.py` (policy and table), `core/onemind_core/routers/protocol.py` (middleware, route), `core/tests/test_protocol.py` and `core/tests/fixtures/protocol/v<n>.json` (the recorded corpus). Clients: `@onemind/sdk` (`PROTOCOL_VERSION`, `UpgradeRequiredError`), the dashboard and the mobile app ("Update needed" screen).

## Terms

- **Generation** (protocol version): a whole number, 1, 2, 3, ... It moves by one each time a change would break a request an existing client sends or an answer it reads. Adding a route, an optional request field or a new answer key is not breaking and does not move it.
- **N**: the current generation, `PROTOCOL_CURRENT`. **N-1**: the one before it.
- **Minimum**: the oldest generation this hub still serves, `PROTOCOL_MINIMUM` (raised only by a reviewed code change) or a higher owner setting.

This is not the same as `OneMind-API-Version: 1` (contract poc-v0 section 12.1), which names the API major version (the `/v1/` path). All generations here live inside `/v1/`. Clients keep sending both headers.

## Wire rules

1. **Request.** A client sends `X-OneMind-Protocol: <n>` (one whole number, 1 to 9999) on every request. A request without the header speaks generation 1: every client released before this contract.
2. **Every answer** (any status, any path, including `/healthz` and errors) carries `X-OneMind-Protocol-Min: <minimum>` and `X-OneMind-Protocol-Max: <current>`. A client can learn it is too old from any answer, without parsing a body.
3. **Too old.** A request to `/v1/...` that declares a generation below the minimum gets `400` with the section 12.2 error body: `{"error": "upgrade_required", "reason": "protocol_too_old", "message": "...", "details": [{"field": "X-OneMind-Protocol", "sent": <n>, "minimum": <min>, "maximum": <max>}]}`. The client shows "Update needed" (the app is too old) and stops calling. 426 is not used because HTTP requires it to name a transport in an `Upgrade` header.
4. **Malformed.** A header that is not one whole number, or sent twice, gets `422 conflict` with reason `protocol_header_invalid`.
5. **Newer than the hub.** A client that declares a generation above the maximum is served (the hub answers at its maximum). The client reads `X-OneMind-Protocol-Max`, steps down if it can, or shows "Update the hub".
6. **Always open to old clients.** `/healthz`, `/openapi.json`, `GET /v1/protocol` and `/mcp` (which has its own `MCP-Protocol-Version`) are never refused, and paths outside `/v1/` (the dashboard files) are not checked, so an old app can always read what it needs to explain itself.
7. **Discovery.** `GET /v1/protocol` (open, no token) answers `{header, current, minimum, maximum, versions: [{version, released, summary, supported, supported_until}]}`. `/openapi.json` carries `info.x-onemind-protocol: {header, current}`.

## Support window: N and N-1 for 12 months

- A generation stays served for at least 12 months after its successor is released: `supported_until(n) = released(n+1) + 12 months` (end of month clamps, so a 29 February release gives 28 February).
- The minimum never moves by the clock. Dropping a generation is a reviewed change to `PROTOCOL_MINIMUM`, and `test_the_version_table_keeps_n_minus_1_for_twelve_months` refuses a minimum that drops a generation before its date.
- An owner may refuse old clients early with `ONEMIND_PROTOCOL_MINIMUM` (between `PROTOCOL_MINIMUM` and `PROTOCOL_CURRENT`; anything else stops the gateway at start). It can only raise the minimum.

## Making a breaking change (refuse silent breaks)

1. Append a generation to `PROTOCOL_VERSIONS` with today's date and a one-line summary. Never edit or remove an old row.
2. Record the corpus of the generation you are leaving: copy the newest `v<n>.json` to `v<N>.json`, set `version`, list the requests the current clients send, and run `ONEMIND_RECORD_PROTOCOL_CORPUS=1 make -C core test` once to fill in status and shape. Commit it. From then on `test_recorded_old_requests_still_work` replays it on every change.
3. Keep serving the old shape to clients that declare the old generation for the 12 months (branch on the declared generation in the route), so the old corpus keeps passing.
4. Bump `PROTOCOL_VERSION` in the SDK and the mobile app, run `make -C sdk gen`, and add a `changes/` fragment that names the new generation.

What the corpus checks, per recorded request: the same status, the same JSON type, and every key the old answer had is still there. New keys are allowed. A change that renames or drops a key, changes a type or turns a 200 into an error fails CI.

## Generations

| Generation | Released | What changed | Served until at least |
|---|---|---|---|
| 1 | 2026-11-11 | contract poc-v0 sections 3 and 12; no `X-OneMind-Protocol` header | 2027-11-21 |
| 2 | 2026-11-21 | clients send `X-OneMind-Protocol`; every answer carries the range; `upgrade_required` | current |

The table in `protocol.py` is the source; `GET /v1/protocol` serves it.

## Proving it on a phone (lab kit)

1. Start a hub that refuses generation 1: `ONEMIND_PROTOCOL_MINIMUM=2 make -C core run`.
2. Build the phone app as an older build would be: `EXPO_PUBLIC_ONEMIND_PROTOCOL=1 npx expo start` in `mobile/` and open it on the iPhone with Expo Go.
3. Connect to the hub. Expected: the "Update needed" screen naming generation 1 and the hub's range 2 to 2, not a crash or an error toast. Unset the variable and reload: the app connects normally.
4. Dashboard: on the same hub, the browser tab shows "Update needed" only if it declares an older generation; a dashboard served by the hub always matches it.
