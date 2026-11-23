# SPDX-License-Identifier: Apache-2.0
"""Installed Market apps in the surface registry (#605, slice 2): read from the approved receipt, live."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from conftest import OWNER, make_client
from onemind_core.identity.models import TokenRow, UserRow
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.plugins.models import PluginInstallRow
from onemind_core.surfaces.registry import MarketApp, SurfaceRegistry
from test_plugin_credentials import approve, request
from test_plugin_workload import plugin_settings  # noqa: F401
from test_identity import id_settings

APP = "uptime-kuma"
CLOSED = {"type": "object", "additionalProperties": False}
OBSERVED = {"type": "object", "additionalProperties": False,
            "properties": {"up": {"type": "integer"}, "observed_at": {"type": "string"}}}


def tool(name, effect, output=None, exposure=None):
    return {"name": name, "title": name.title(), "description": "plugin text", "effect": effect,
            "input": deepcopy(CLOSED), "output": deepcopy(output or CLOSED), "exposure": exposure or {"rest": True}}


@pytest.fixture
def market(plugin_settings, clock):  # noqa: F811
    path = Path(plugin_settings.apps_dir) / APP / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["extensions"] = {
        "tools": [tool("status", "read", OBSERVED), tool("plain", "read"), tool("change", "write"),
                  tool("erase", "destructive"), tool("hidden", "read", exposure={"mcp": True, "rest": False})],
        "widgets": [
            {"id": "up", "title": "Monitors up", "render": "template", "template": "stat",
             "source": {"tool": "status", "args": {}}, "surfaces": ["dashboard"]},
            {"id": "unstamped", "title": "No time", "render": "template", "template": "stat",
             "source": {"tool": "plain"}, "surfaces": ["dashboard"]},
        ],
    }
    path.write_text(yaml.safe_dump(doc))
    with make_client(id_settings(plugin_settings, require_passkey_approval=False), clock) as client:
        approve(client, request(client, clock, "app.install"))
        yield client


def surfaces(client, headers=OWNER):
    r = client.get("/v1/surfaces", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def mine(body, key):
    return [x for x in body[key] if x.get("app_id") == APP]


def test_an_installed_market_app_joins_from_its_receipt(market):
    body = surfaces(market)
    assert {"id": APP, "name": body["apps"][-1]["name"], "description": body["apps"][-1]["description"],
            "origin": "market", "phone": {"entry": "web"}} in body["apps"]
    tools = {t["name"]: t for t in mine(body, "tools")}
    assert set(tools) == {f"{APP}.status", f"{APP}.plain", f"{APP}.change", f"{APP}.erase"}
    assert tools[f"{APP}.status"] == {
        "name": f"{APP}.status", "app_id": APP, "title": "Status", "effect": "read", "exposure": ["rest"],
        "route": f"POST /v1/plugins/{APP}/tools/status", "action_type": None,
        "scope": "actions:request:plugin.invoke"}
    assert tools[f"{APP}.change"]["action_type"] == "plugin.invoke"
    assert tools[f"{APP}.erase"]["effect"] == "destructive"
    assert mine(body, "cards") == [{
        "app_id": APP, "id": "up", "title": "Monitors up", "template": "stat",
        "source": f"POST /v1/plugins/{APP}/tools/status", "tool": f"{APP}.status", "args": {}}]
    assert mine(body, "backup_units") == [{"app_id": APP, "kind": "app", "name": APP}]


def test_unserved_tools_and_cards_without_observed_at_are_refused(market):
    refused = {(r["kind"], r["id"]): r["reason"] for r in mine(surfaces(market), "refused")}
    assert "is not served" in refused[("tool", f"{APP}.hidden")]
    assert "declares no observed_at" in refused[("card", "unstamped")]
    assert len(refused) == 2


def test_the_receipt_not_the_catalog_file_is_what_is_served(market):
    path = Path(market.app.state.settings.apps_dir) / APP / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["extensions"]["tools"].append(tool("sneaky", "destructive"))
    path.write_text(yaml.safe_dump(doc))
    assert f"{APP}.sneaky" not in {t["name"] for t in surfaces(market)["tools"]}


def test_stopping_the_app_removes_it_at_once_and_starting_brings_it_back(market, clock):
    repo = market.app.state.repo
    repo.set_app_state(APP, "stopped", clock())
    body = surfaces(market)
    assert not [a for a in body["apps"] if a["id"] == APP]
    for key in ("tools", "cards", "backup_units", "refused"):
        assert mine(body, key) == [], key
    repo.set_app_state(APP, "installed", clock())
    assert len(mine(surfaces(market), "tools")) == 4


def test_a_changed_bundle_serves_nothing(market):
    market.app.state.identity.repo.update(PluginInstallRow, [PluginInstallRow.app_id == APP],
                                          {"bundle_sha256": "sha256:" + "f" * 64})
    body = surfaces(market)
    assert mine(body, "tools") == [] and not [a for a in body["apps"] if a["id"] == APP]


def test_a_guest_does_not_see_an_app_not_shared_with_them(market, clock):
    token = new_secret("pat")
    repo = market.app.state.identity.repo
    repo.add(UserRow(id="g", display_name="Guest", role="guest", created_at=clock(), updated_at=clock()))
    repo.add(TokenRow(id="g-token", prefix=token[:11], hash=sha256_hex(token), name="Read apps", kind="person",
                      principal_id="g", owner_user_id="g", scopes=["apps:read"], source="api", created_by="owner",
                      created_at=clock()))
    body = surfaces(market, {"Authorization": "Bearer " + token})
    assert mine(body, "tools") == [] and not [a for a in body["apps"] if a["id"] == APP]


def test_market_topics_must_route_and_pages_follow_the_settings_block():
    m = MarketApp(id="kuma", name="Kuma", description=None, spec={
        "web": {"port": 1},
        "notifications": {"topics": [{"id": "down", "events": ["kuma.down"]}]},
        "extensions": {"settings": {"schema": "settings.json"},
                       "widgets": [{"id": "frame", "title": "Frame", "render": "iframe", "entry": "w.html",
                                    "surfaces": ["dashboard"]}]},
    })
    reg = SurfaceRegistry(type("B", (), {"enabled": lambda self: []})(), known_action=lambda t: False,
                          event_topic=lambda e: None, openapi=dict, market=lambda: [m])
    view = reg.view(lambda _: True)
    assert view["notifications"] == [] and view["cards"] == []
    assert [r["kind"] for r in view["refused"]] == ["topic"]
    assert view["settings_pages"] == [{"app_id": "kuma", "id": "settings", "title": "Kuma settings",
                                       "source": "GET /v1/plugins/kuma/settings"}]
    assert reg.view(lambda _: False)["apps"] == []
