# SPDX-License-Identifier: Apache-2.0
"""Contract §10.3 + §11.1 (no install without a fresh passing scan) and §11.4 (catalog fields)."""

import logging
from dataclasses import replace
from datetime import timedelta

import pytest

from conftest import GUEST, OWNER, action_body, make_client, write_scan
from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core.executors import NoopExecutor


def request_install(client, clock, app_id="uptime-kuma", key="k1"):
    r = client.post("/v1/actions", json=action_body(clock, app_id=app_id, key=key), headers=OWNER)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---- §10.3 approve check -----------------------------------------------------------------

@pytest.mark.parametrize(
    "setup,needle",
    [
        (lambda d, now: write_scan(d, None), "no valid scan record"),
        (lambda d, now: write_scan(d, now - timedelta(hours=1), result="fail"), "failed its last scan"),
        (lambda d, now: write_scan(d, now - timedelta(days=7, seconds=1)), "7 days"),
        (lambda d, now: write_scan(d, now + timedelta(days=30)), "future"),
        (lambda d, now: (d / "scan.json").write_text("{not json"), "no valid scan record"),
        (lambda d, now: (d / "scan.json").write_text('{"result": "pass", "scanned_at": "yesterday"}'),
         "no valid scan record"),
        (lambda d, now: (d / "scan.json").write_text('{"result": "pass", "scanned_at": "2026-11-11T10:00:00"}'),
         "no valid scan record"),  # no timezone
        (lambda d, now: (d / "scan.json").write_text('{"result": "PASS", "scanned_at": "2026-11-11T10:00:00Z"}'),
         "no valid scan record"),
    ],
)
def test_approve_install_refused_without_fresh_passing_scan(client, clock, executor, settings, setup, needle):
    action_id = request_install(client, clock)
    setup(settings.apps_dir / "uptime-kuma", clock.now)
    r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "stale_precondition"
    assert needle in r.json()["message"]
    assert executor.calls == []
    assert client.get(f"/v1/actions/{action_id}", headers=OWNER).json()["state"] == "awaiting_approval"
    # the refusal is audited
    assert "stale_precondition" in settings.audit_path.read_text()


def test_scan_exactly_seven_days_old_still_passes(client, clock, executor, settings):
    write_scan(settings.apps_dir / "uptime-kuma", clock.now - timedelta(days=7))
    action_id = request_install(client, clock)
    r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "succeeded"


def test_scan_ages_out_between_request_and_approval(client, clock, executor):
    body = action_body(clock, ttl=8 * 86400)
    action_id = client.post("/v1/actions", json=body, headers=OWNER).json()["id"]  # scan is 1 day old
    clock.advance(6 * 86400 + 1)  # the scan is now 7 days + 1 s old; the action has not expired
    r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"
    assert executor.calls == []


def test_request_is_allowed_without_scan_only_approval_is_gated(client, clock, settings):
    write_scan(settings.apps_dir / "uptime-kuma", None)
    request_install(client, clock)


def test_remove_is_not_gated_by_scan(client, clock, executor, settings):
    action_id = request_install(client, clock)
    assert client.post(f"/v1/actions/{action_id}/approve", headers=OWNER).json()["state"] == "succeeded"
    write_scan(settings.apps_dir / "uptime-kuma", clock.now - timedelta(days=1), result="fail")
    r = client.post("/v1/actions", json=action_body(clock, type_="app.remove", key="k2"), headers=OWNER)
    r = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "succeeded"


# ---- §11.1 ONEMIND_ALLOW_UNSCANNED --------------------------------------------------------

def test_allow_unscanned_with_noop_skips_check_and_warns(settings, clock, caplog):
    write_scan(settings.apps_dir / "uptime-kuma", None)
    with caplog.at_level(logging.WARNING, logger="onemind.gateway"):
        c = make_client(settings, clock, allow_unscanned=True)
    assert any("ONEMIND_ALLOW_UNSCANNED" in r.message for r in caplog.records)
    with c:
        action_id = request_install(c, clock)
        r = c.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
        assert r.status_code == 200 and r.json()["state"] == "succeeded"
    assert '"scan_check":false' in settings.audit_path.read_text()


def test_allow_unscanned_refused_with_kubernetes_executor(settings, clock):
    with pytest.raises(ValueError, match="ALLOW_UNSCANNED"):
        create_app(replace(settings, executor="kubernetes", allow_unscanned=True), clock=clock)
    with pytest.raises(ValueError, match="ALLOW_UNSCANNED"):
        Settings.from_env({"ONEMIND_EXECUTOR": "kubernetes", "ONEMIND_ALLOW_UNSCANNED": "1", "ONEMIND_NODE_ID": "x"})


def test_allow_unscanned_refused_with_a_real_executor_object(settings, clock, executor):
    # settings say noop, but the executor that would run is not the noop one: still refused
    with pytest.raises(ValueError, match="ALLOW_UNSCANNED"):
        create_app(replace(settings, allow_unscanned=True), clock=clock, executor=executor)


def test_allow_unscanned_env_parsing():
    base = {"ONEMIND_NODE_ID": "x"}
    assert Settings.from_env({**base, "ONEMIND_ALLOW_UNSCANNED": "1"}).allow_unscanned is True
    assert Settings.from_env({**base, "ONEMIND_ALLOW_UNSCANNED": "0"}).allow_unscanned is False
    assert Settings.from_env(base).allow_unscanned is False
    with pytest.raises(ValueError):
        Settings.from_env({**base, "ONEMIND_ALLOW_UNSCANNED": "maybe"})


def test_scan_check_on_by_default(settings, clock):
    write_scan(settings.apps_dir / "uptime-kuma", None)
    with make_client(settings, clock) as c:
        action_id = request_install(c, clock)
        assert c.post(f"/v1/actions/{action_id}/approve", headers=OWNER).status_code == 409


# ---- §11.4 catalog fields ---------------------------------------------------------------

def test_catalog_links_tier_scan(client, clock, settings):
    apps = {a["id"]: a for a in client.get("/v1/apps", headers=GUEST).json()}
    h = apps["hermes-like"]
    assert h["links"] == {
        "docs": "https://example.com/docs",
        "github": "https://github.com/example/hermes-like",
        "website": None,  # javascript: URL is dropped
        "support": None,
    }
    assert h["tier"] == "community"
    assert h["scan"] == {"scanned_at": "2026-11-10T22:00:00Z", "result": "pass"}
    ku = apps["uptime-kuma"]
    assert ku["links"] == {"docs": None, "github": None, "website": None, "support": None}
    assert ku["tier"] is None


def test_catalog_scan_null_when_missing_and_shows_fail(client, clock, settings):
    write_scan(settings.apps_dir / "uptime-kuma", None)
    write_scan(settings.apps_dir / "whoami", clock.now, result="fail")
    apps = {a["id"]: a for a in client.get("/v1/apps", headers=GUEST).json()}
    assert apps["uptime-kuma"]["scan"] is None
    assert apps["whoami"]["scan"]["result"] == "fail"


def test_unknown_tier_is_null(client, settings):
    p = settings.apps_dir / "whoami" / "onemind.app.yaml"
    p.write_text(p.read_text().replace("metadata:\n", "metadata:\n  tier: gold\n", 1))
    apps = {a["id"]: a for a in client.get("/v1/apps", headers=GUEST).json()}
    assert apps["whoami"]["tier"] is None


def test_openapi_documents_catalog_fields_and_mcp(client):
    doc = client.get("/openapi.json").json()
    item = doc["components"]["schemas"]["CatalogApp"]
    assert {"links", "tier", "scan"} <= set(item["properties"])
    assert set(doc["components"]["schemas"]["AppLinks"]["properties"]) == {"docs", "github", "website", "support"}
    get_apps = doc["paths"]["/v1/apps"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert get_apps["items"]["$ref"].endswith("/CatalogApp")
    assert {"200", "202", "401", "403"} <= set(doc["paths"]["/mcp"]["post"]["responses"])


def test_noop_executor_is_default_for_make_client(settings, clock):
    # guard for the tests above: make_client builds a real NoopExecutor
    with make_client(settings, clock) as c:
        assert isinstance(c.app.state.actions.executor, NoopExecutor)
