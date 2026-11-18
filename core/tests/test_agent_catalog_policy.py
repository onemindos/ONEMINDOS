# SPDX-License-Identifier: Apache-2.0
"""Agent REST catalog reads must not bypass the AI boundary (#165)."""

from pathlib import Path

import pytest
import yaml

from conftest import AGENT, OWNER, conform_to_schema, make_client


@pytest.mark.parametrize("category", ["health", "wellness"])
def test_sensitive_rest_reads_use_production_schema(settings, clock, executor, category):
    folder = settings.apps_dir / "whoami"
    conform_to_schema(folder)
    path = folder / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"].update(category=category, name="restricted-rest-canary", icon="icon.svg")
    doc["spec"]["manifests"] = "manifests/"
    path.write_text(yaml.safe_dump(doc))
    schema = Path(__file__).resolve().parents[2] / "sdk/schema/onemind.app.schema.json"
    with make_client(settings, clock, executor, app_schema_path=schema) as client:
        assert "restricted-rest-canary" in client.get("/v1/apps/whoami", headers=OWNER).text
        response = client.get("/v1/apps", headers=AGENT)
        assert response.status_code == 200
        assert "restricted-rest-canary" not in response.text
        for url in ("/v1/apps/whoami", "/v1/apps/whoami/plan", "/v1/apps/whoami/settings",
                    "/v1/apps/whoami/dependencies", "/v1/apps/whoami/host-ports", "/v1/apps/whoami/exposure"):
            response = client.get(url, headers=AGENT)
            assert response.status_code == 404
            assert "restricted-rest-canary" not in response.text
        response = client.post("/v1/plans", headers=AGENT, json={
            "type": "app.install", "params": {"app_id": "whoami"},
        })
        assert response.status_code == 404
        assert executor.calls == []


@pytest.mark.parametrize("policy", ["prohibited", "display-only", "local-only", "consent-required",
                                    "official-mcp-only", "unknown", False, None, {"allowed": True}])
def test_explicit_restrictions_fail_closed(client, settings, policy):
    # Explicit policies await the held production schema. Built-in validation
    # exercises refusal now, without changing or weakening the shared schema.
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["aiPolicy"] = policy
    doc["metadata"]["description"] = "restricted-rest-canary"
    path.write_text(yaml.safe_dump(doc))
    assert "restricted-rest-canary" in client.get("/v1/apps/whoami", headers=OWNER).text
    assert "restricted-rest-canary" not in client.get("/v1/apps", headers=AGENT).text
    assert client.get("/v1/apps/whoami", headers=AGENT).status_code == 404
    assert client.get("/v1/apps/whoami/plan", headers=AGENT).status_code == 404


def test_request_cannot_override_manifest_policy(client, settings):
    path = settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"]["category"] = "health"
    path.write_text(yaml.safe_dump(doc))
    response = client.get("/v1/apps/whoami?aiPolicy=allowed", headers={**AGENT, "X-AI-Policy": "allowed"})
    assert response.status_code == 404


@pytest.mark.parametrize("policy", ["legacy", "allowed"])
def test_non_health_catalog_metadata_remains_visible(client, settings, policy):
    if policy == "allowed":
        path = settings.apps_dir / "whoami" / "onemind.app.yaml"
        doc = yaml.safe_load(path.read_text())
        doc["spec"]["aiPolicy"] = policy
        path.write_text(yaml.safe_dump(doc))
    assert client.get("/v1/apps/whoami", headers=AGENT).status_code == 200
    assert "whoami" in {r["id"] for r in client.get("/v1/apps", headers=AGENT).json()}
