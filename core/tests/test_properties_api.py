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

import shutil
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from conftest import AGENT, EXAMPLES, FIXTURES, OWNER, Clock, write_scan
from onemind_core.app import create_app
from onemind_core.config import Settings
from props import budget

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "TRACE"]


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    shutil.copytree(FIXTURES / "apps", root / "apps")
    clock = Clock()
    for app_id in ("uptime-kuma", "whoami", "hermes-like"):
        write_scan(root / "apps" / app_id, clock.now - timedelta(days=1))
    settings = Settings(
        tokens_file=EXAMPLES / "tokens.example.yaml", db_url=f"sqlite:///{root / 'db.sqlite'}",
        apps_dir=root / "apps", dashboard_dist=None, executor="noop", nats_url=None,
        audit_path=root / "audit.jsonl", node_id="abc123def456", instance_name="Test OneMind",
        app_schema_path=None, kubectl="kubectl", executor_timeout_s=5, host="127.0.0.1", port=8080,
    )
    with TestClient(create_app(settings, clock=clock), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture(scope="module")
def operations(gateway):
    """(concrete path, {METHOD: documented statuses}) for every documented path but /mcp."""
    spec = gateway.get("/openapi.json").json()
    out = []
    for path, ops in spec["paths"].items():
        if path == "/mcp":  # JSON-RPC over one POST; api-fuzz.yml checks it for server errors only
            continue
        concrete = path.replace("{node_id}", "node-x").replace("{action_id}", "no-such-action")
        out.append((concrete, {m.upper(): {int(s) for s in op["responses"]} for m, op in ops.items()}))
    return out


def test_every_undocumented_method_is_405_with_allow(gateway, operations):
    for path, documented in operations:
        for method in METHODS:
            if method in documented:
                continue
            r = gateway.request(method, path, headers=OWNER)
            assert r.status_code == 405, (method, path, r.status_code)
            allow = {m.strip() for m in r.headers.get("allow", "").split(",") if m.strip()}
            assert allow - {"HEAD"} == set(documented), (method, path, r.headers.get("allow"))
            assert r.json()["error"] == "not_found"  # §12.2: method_not_allowed is opt-in


@budget(150)
@given(data=st.data(), body=st.binary(max_size=300) | st.text(max_size=200).map(str.encode), who=st.sampled_from([OWNER, AGENT]))
def test_any_body_gets_a_documented_status(gateway, operations, data, body, who):
    posts = [(p, d["POST"]) for p, d in operations if "POST" in d]
    path, documented = data.draw(st.sampled_from(posts), label="operation")
    r = gateway.post(path, content=body, headers={**who, "Content-Type": "application/json"})
    assert r.status_code < 500, (path, body, r.text)
    assert r.status_code in documented, (path, body, r.status_code, r.text)
    if r.status_code >= 400:
        assert r.json()["error"], r.text  # always the §3 envelope
