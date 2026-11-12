"""Contract §3: /healthz, /openapi.json, auth (401), /v1/instance, static dashboard."""

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER, make_client


def test_healthz_is_open(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_openapi_published_with_contract_paths(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    for p in [
        "/healthz",
        "/v1/instance",
        "/v1/nodes",
        "/v1/nodes/{node_id}",
        "/v1/apps",
        "/v1/actions",
        "/v1/actions/{action_id}",
        "/v1/actions/{action_id}/approve",
        "/v1/actions/{action_id}/deny",
    ]:
        assert p in paths, p


@pytest.mark.parametrize(
    "path",
    ["/v1/instance", "/v1/nodes", "/v1/nodes/x", "/v1/apps", "/v1/actions", "/v1/actions/x"],
)
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer nope-not-a-real-token"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}],
)
def test_missing_or_unknown_token_is_401(client, path, headers):
    r = client.get(path, headers=headers)
    assert r.status_code == 401
    assert r.json()["error"] == "unauthenticated"
    assert r.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("path", ["/v1/actions", "/v1/actions/x/approve", "/v1/actions/x/deny"])
def test_post_without_token_is_401(client, path):
    r = client.post(path, json={})
    assert r.status_code == 401
    assert r.json()["error"] == "unauthenticated"


@pytest.mark.parametrize("headers", [OWNER, ADULT, GUEST, AGENT])
def test_instance_for_any_principal(client, headers):
    r = client.get("/v1/instance", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {"name": "Test OneMind", "version": "0.1.0", "hub_node_id": "abc123def456"}


def test_spa_serves_index_and_assets(client):
    r = client.get("/")
    assert r.status_code == 200 and "onemind-test-dist" in r.text
    r = client.get("/nodes/abc")  # client-side route -> index.html
    assert r.status_code == 200 and "onemind-test-dist" in r.text
    r = client.get("/assets/app.js")
    assert r.status_code == 200 and "asset" in r.text
    r = client.get("/assets/missing.js")
    assert r.status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
def test_no_open_docs_uis(client, path):
    # Only /healthz and /openapi.json are open (section 3); /docs is just a dashboard route now.
    r = client.get(path)
    assert "swagger" not in r.text.lower() and "redoc" not in r.text.lower()


@pytest.mark.parametrize("path", ["/v1x", "/healthzone", "/docs-page", "/redocs/a"])
def test_spa_reserves_whole_segments_only(client, path):
    r = client.get(path)
    assert r.status_code == 200 and "onemind-test-dist" in r.text


def test_spa_does_not_swallow_api_routes(client):
    r = client.get("/v1/does-not-exist", headers=OWNER)
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


def test_spa_blocks_path_traversal(client):
    r = client.get("/..%2F..%2Fpyproject.toml")
    assert r.status_code == 404 or "onemind-test-dist" in r.text
    assert "[project]" not in r.text


def test_no_dashboard_dist_means_404(settings, clock):
    with make_client(settings, clock, dashboard_dist=None) as c:
        r = c.get("/")
        assert r.status_code == 404
        assert r.json()["error"] == "not_found"


def test_tokens_file_missing_means_everything_401(settings, clock, tmp_path):
    with make_client(settings, clock, tokens_file=tmp_path / "nope.yaml") as c:
        assert c.get("/v1/instance", headers=OWNER).status_code == 401
        assert c.get("/healthz").status_code == 200
