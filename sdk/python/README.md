<!-- SPDX-License-Identifier: Apache-2.0 -->
# onemind-sdk (Python)

Python client for the OneMind gateway API, sync and async, generated from `sdk/openapi/onemind-v1.json` (design: [`docs/leap/dev/SDK.md`](../../docs/leap/dev/SDK.md)).

```python
from onemind_sdk import Client, PermissionDenied

om = Client.from_env()          # ONEMIND_HUB + ONEMIND_TOKEN, or ONEMIND_GATEWAY_URL + ONEMIND_AGENT_TOKEN
for node in om.nodes.list():
    print(node.node_id, node.status)

a = om.actions.request("app.install", "ntfy")   # waits in awaiting_approval for the owner
a = om.actions.wait(a.id, timeout=600)
for ev in om.events.subscribe(types=["action.*"]):
    print(ev["type"], ev["subject"])
```

`onemind_sdk.aio.Client` is the same surface with `await` (it is derived from `client.py` by `scripts/make_aio.py`).

What the transport guarantees: GETs retry on network errors and 429/502/503/504 with full-jitter backoff and `Retry-After`; `actions.request` retries with one idempotency key; `approve`/`deny` are never retried blindly (a lost reply is read back, else `AmbiguousResult`); every error is a typed subclass of `OneMindError` whose `code` is the gateway's; the token never appears in `repr`, errors or logs; plain `http://` to a non-local hub warns once.

Generated code: `src/onemind_sdk/_gen/models.py` (datamodel-code-generator 0.87.0, MIT). Regenerate with `make -C sdk gen`. Tests: `make -C sdk test-py`; live conformance runs from `core/tests/test_sdk_conformance.py`.
