# SPDX-License-Identifier: Apache-2.0
"""REST and MCP must apply the same catalog policy (#165, partial slice)."""

import json
from pathlib import Path

import pytest
import yaml

from conftest import AGENT, OWNER, conform_to_schema, make_client
from onemind_core import ai_policy


@pytest.mark.parametrize("category,policy,visible", [
    ("productivity", "absent", True),
    ("health", "absent", False),
    ("wellness", "absent", False),
    ("health", "allowed", True),
    ("productivity", "display-only", False),
    ("productivity", "prohibited", False),
    ("productivity", "local-only", False),
    ("productivity", "consent-required", False),
    ("productivity", "official-mcp-only", False),
    ("productivity", "unknown", False),
    ("productivity", None, False),
    ("productivity", False, False),
    ("productivity", {"allowed": True}, False),
])
def test_rest_mcp_policy_parity(client, settings, category, policy, visible):
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"].update(category=category, name="policy-parity-canary", description="policy-parity-canary")
    if policy != "absent":
        doc["spec"]["aiPolicy"] = policy
    path.write_text(yaml.safe_dump(doc))
    assert_surface_parity(client, visible)


def assert_surface_parity(client, visible):
    owner = client.get("/v1/apps/whoami", headers=OWNER)
    assert owner.status_code == 200
    assert "policy-parity-canary" in owner.text
    rest = client.get("/v1/apps", headers=AGENT)
    assert rest.status_code == 200
    rest_ids = {row["id"] for row in rest.json()}
    for method, params in [
        ("tools/call", {"name": "list_apps"}),
        ("resources/read", {"uri": "onemind://catalog"}),
    ]:
        response = client.post("/mcp", headers=AGENT, json={
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        })
        assert response.status_code == 200
        result = response.json()["result"]
        rows = (result["structuredContent"]["apps"] if method == "tools/call"
                else json.loads(result["contents"][0]["text"])["apps"])
        assert rest_ids == {row["id"] for row in rows}
        assert ("policy-parity-canary" in response.text) is visible
    assert ("whoami" in rest_ids) is visible
    assert client.get("/v1/apps/whoami", headers=AGENT).status_code == (200 if visible else 404)
    response = client.post("/mcp", headers=AGENT, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "get_app", "arguments": {"app_id": "whoami"}},
    })
    assert response.status_code == 200
    assert response.json()["result"]["isError"] is (not visible)
    assert ("policy-parity-canary" in response.text) is visible


def test_shared_sensitive_category_policy_reaches_both_http_surfaces(settings, clock, executor, monkeypatch):
    # A central policy change must not require a second REST-only category list.
    # Only the policy input changes: catalog loading and both HTTP handlers are real.
    monkeypatch.setattr(ai_policy, "SENSITIVE_CATEGORIES", ai_policy.SENSITIVE_CATEGORIES | {"productivity"})
    folder = settings.apps_dir / "whoami"
    conform_to_schema(folder)
    path = folder / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"].update(category="productivity", description="policy-parity-canary", icon="icon.svg")
    doc["spec"]["manifests"] = "manifests/"
    path.write_text(yaml.safe_dump(doc))
    schema = Path(__file__).resolve().parents[2] / "sdk/schema/onemind.app.schema.json"
    with make_client(settings, clock, executor, app_schema_path=schema) as client:
        assert_surface_parity(client, False)
