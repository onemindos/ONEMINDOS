# SPDX-License-Identifier: Apache-2.0
"""Property tests: the gateway's HTTP surface against its own /openapi.json (contract §3, §12.2).

The quick, in-process part of what .github/workflows/api-fuzz.yml does with Schemathesis, so it
runs in every `make -C core test`:

- every method an operation does not document gets 405 with an Allow header that lists exactly
  the documented methods (RFC 9110 §15.5.6; finding F-API-2, found by api-fuzz.yml);
- any bytes as the JSON body of any POST operation, from the owner or the agent, get a status the
  operation documents: never 400 (finding F-API-3: a body that is not UTF-8 was an undocumented 400)
  and never a 5xx.
"""

from __future__ import annotations

import re

import pytest

from hypothesis import given
from hypothesis import strategies as st

from conftest import AGENT, OWNER
from props import budget

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "TRACE"]


@pytest.fixture(scope="module")
def operations(property_resources):
    """(concrete path, template, {METHOD: documented statuses}) for every documented path but /mcp."""
    # Cache only the operation description, never a live client's mutable state.
    with property_resources.example() as sample, sample.http() as gateway:
        spec = gateway.get("/openapi.json").json()
    out = []
    for path, ops in spec["paths"].items():
        if path == "/mcp":  # JSON-RPC over one POST; api-fuzz.yml checks it for server errors only
            continue
        concrete = path.replace("{node_id}", "node-x").replace("{action_id}", "no-such-action")
        out.append((concrete, path, {m.upper(): {int(s) for s in op["responses"]} for m, op in ops.items()}))
    return out


def test_every_undocumented_method_is_405_with_allow(property_resources, operations):
    def matching(path):
        """Methods of every documented template that matches this concrete path: a sibling route with
        a path parameter also answers it (GET /v1/notifications/{id} takes "send"), so its methods
        are neither 405 here nor missing from Allow."""
        return {m for _, t, d in operations if re.fullmatch(re.sub(r"\{[^/]+\}", "[^/]+", t), path) for m in d}

    with property_resources.example() as sample, sample.http() as gateway:
        for path, _, documented in operations:
            methods = matching(path)
            for method in METHODS:
                if method in methods:
                    continue
                r = gateway.request(method, path, headers=OWNER)
                assert r.status_code == 405, (method, path, r.status_code)
                allow = {m.strip() for m in r.headers.get("allow", "").split(",") if m.strip()}
                assert allow - {"HEAD"} == methods, (method, path, r.headers.get("allow"))
                assert r.json()["error"] == "not_found"  # §12.2: method_not_allowed is opt-in


@budget(150)
@given(data=st.data(), body=st.binary(max_size=300) | st.text(max_size=200).map(str.encode), who=st.sampled_from([OWNER, AGENT]))
def test_any_body_gets_a_documented_status(property_resources, operations, data, body, who):
    posts = [(p, d["POST"]) for p, _, d in operations if "POST" in d]
    path, documented = data.draw(st.sampled_from(posts), label="operation")
    # Allocate inside @given: shrinking/replay must not reuse database/guard state.
    with property_resources.example() as sample, sample.http() as gateway:
        r = gateway.post(path, content=body, headers={**who, "Content-Type": "application/json"})
    assert r.status_code < 500, (path, body, r.text)
    assert r.status_code in documented, (path, body, r.status_code, r.text)
    if r.status_code >= 400:
        assert r.json()["error"], r.text  # always the §3 envelope
