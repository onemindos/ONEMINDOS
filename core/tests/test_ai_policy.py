# SPDX-License-Identifier: Apache-2.0
"""First #165 slice: no restricted catalog text crosses the actual MCP HTTP boundary."""

import json
from pathlib import Path

import pytest
import yaml

from conftest import AGENT, OWNER, conform_to_schema


@pytest.mark.parametrize("policy", ["display-only", "official-mcp-only", "prohibited", "consent-required", "local-only", "unknown", False])
@pytest.mark.parametrize("method,params", [
    ("tools/call", {"name": "list_apps"}),
    ("tools/call", {"name": "get_app", "arguments": {"app_id": "whoami"}}),
    ("resources/read", {"uri": "onemind://catalog"}),
    ("resources/read", {"uri": "onemind://catalog/whoami"}),
])
def test_restricted_catalog_text_never_leaves_mcp(client, settings, policy, method, params):
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["aiPolicy"] = policy
    doc["metadata"]["description"] = "restricted-catalog-canary"
    doc["metadata"]["name"] = "restricted-catalog-canary"
    path.write_text(yaml.safe_dump(doc))
    # The owner may still display it; AI restrictions are not owner display permissions.
    assert "restricted-catalog-canary" in client.get("/v1/apps/whoami", headers=OWNER).text
    response = client.post("/mcp", headers=AGENT, json={
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    })
    assert response.status_code == 200
    assert "restricted-catalog-canary" not in response.text
    if params.get("name") == "get_app":
        assert response.json()["result"]["isError"] is True
    if params.get("uri") == "onemind://catalog/whoami":
        assert "error" in response.json()


@pytest.mark.parametrize("category", ["health", "wellness"])
def test_sensitive_default_works_with_real_manifest_schema(settings, clock, executor, category):
    from conftest import make_client

    folder = settings.apps_dir / "whoami"
    conform_to_schema(folder)
    path = folder / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"].update(category=category, description="health-default-canary", icon="icon.svg")
    doc["spec"]["manifests"] = "manifests/"
    path.write_text(yaml.safe_dump(doc))
    schema = Path(__file__).resolve().parents[2] / "sdk/schema/onemind.app.schema.json"
    with make_client(settings, clock, executor, app_schema_path=schema) as client:
        owner = client.get("/v1/apps/whoami", headers=OWNER)
        assert owner.status_code == 200
        assert owner.json()["aiPolicy"] == "display-only"
        response = client.post("/mcp", headers=AGENT, json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_apps"},
        })
        assert "health-default-canary" not in response.text


def test_allowed_catalog_entry_is_visible(client, settings):
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["aiPolicy"] = "allowed"
    path.write_text(yaml.safe_dump(doc))
    response = client.post("/mcp", headers=AGENT, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_app", "arguments": {"app_id": "whoami"}},
    })
    result = response.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["aiPolicy"] == "allowed"
    assert json.loads(result["content"][0]["text"])["id"] == "whoami"
