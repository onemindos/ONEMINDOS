# SPDX-License-Identifier: Apache-2.0
"""AIG-01 (#165): exercise the real HTTP MCP boundary, not a policy stub."""

from pathlib import Path

import yaml

from conftest import AGENT, OWNER, conform_to_schema
from onemind_core.catalog import Catalog


def test_ai_policy_declaration_is_accepted_by_manifest_schema(settings):
    app_dir = settings.apps_dir / "whoami"
    conform_to_schema(app_dir)
    doc = yaml.safe_load((app_dir / "onemind.app.yaml").read_text())
    doc["metadata"]["icon"] = "icon.svg"
    doc["spec"]["manifests"] = "manifests/"
    schema = Path(__file__).resolve().parents[2] / "sdk/schema/onemind.app.schema.json"
    catalog = Catalog(settings.apps_dir, schema)
    assert catalog.validate(doc) == []
    doc["spec"]["aiPolicy"] = "display-only"
    assert catalog.validate(doc) == []


def test_display_only_app_data_does_not_leave_through_mcp(client, settings):
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["aiPolicy"] = "display-only"
    doc["metadata"]["description"] = "owner-visible-ai-no-boundary-marker"
    path.write_text(yaml.safe_dump(doc))

    # The owner's display still works; this is a restriction on AI egress.
    rows = client.get("/v1/apps", headers=OWNER).json()
    assert next(row for row in rows if row["id"] == "whoami")["description"] == doc["metadata"]["description"]

    response = client.post("/mcp", headers=AGENT, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_app", "arguments": {"app_id": "whoami"}},
    })
    assert response.status_code == 200
    # Check the entire wire response: neither structuredContent nor text may leak.
    assert doc["metadata"]["description"] not in response.text
    assert response.json()["result"]["isError"] is True
