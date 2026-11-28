# SPDX-License-Identifier: Apache-2.0
"""Installed Market apps in the surface registry (#605, slice 2): read from the approved receipt, live."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from conftest import OWNER, make_client
from onemind_core.builtins import Builtins
from onemind_core.identity.models import TokenRow, UserRow
from onemind_core.identity.crypto import new_secret, sha256_hex
from onemind_core.plugins.models import PluginInstallRow
from onemind_core.surfaces.registry import TOOL_NAME_RE, MarketApp, SurfaceRegistry, market_tool_name
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
    doc["spec"]["mapLayers"] = [{"id": "peek", "title": "Peek", "source": "GET /v1/audit"},
                                {"id": "poke", "title": "Poke", "source": "POST /v1/actions"},
                                {"id": "pins", "title": "Pins", "source": "emits"}]
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
    assert set(tools) == {f"{APP}__status", f"{APP}__plain", f"{APP}__change", f"{APP}__erase"}
    assert tools[f"{APP}__status"] == {
        "name": f"{APP}__status", "app_id": APP, "title": "Status", "effect": "read", "exposure": ["rest"],
        "route": f"POST /v1/plugins/{APP}/tools/status", "action_type": None,
        "scope": "actions:request:plugin.invoke"}
    assert tools[f"{APP}__change"]["action_type"] == "plugin.invoke"
    assert tools[f"{APP}__erase"]["effect"] == "destructive"
    assert mine(body, "cards") == [{
        "app_id": APP, "id": "up", "title": "Monitors up", "template": "stat",
        "source": f"POST /v1/plugins/{APP}/tools/status", "tool": f"{APP}__status", "args": {}}]
    assert mine(body, "backup_units") == [{"app_id": APP, "kind": "app", "name": APP}]


def test_unserved_tools_and_cards_without_observed_at_are_refused(market):
    refused = {(r["kind"], r["id"]): r["reason"] for r in mine(surfaces(market), "refused")}
    assert "is not served" in refused[("tool", f"{APP}__hidden")]
    assert "declares no observed_at" in refused[("card", "unstamped")]
    assert "is not emits" in refused[("layer", "peek")] and "is not emits" in refused[("layer", "poke")]
    assert len(refused) == 4


def test_a_market_layer_is_served_only_from_its_own_emits(market):
    # A call source would make the host fetch a core route of the app's choosing with the viewer's token.
    body = surfaces(market)
    assert mine(body, "map_layers") == [{"app_id": APP, "id": "pins", "title": "Pins", "source": "emits"}]
    assert not [x for x in body["map_layers"] if x["source"].startswith(("GET /v1/audit", "POST"))]


def test_every_tool_name_on_the_list_is_mcp_safe(market):
    body = surfaces(market)
    names = [t["name"] for t in body["tools"]]
    assert names and all(TOOL_NAME_RE.match(n) for n in names), names
    assert len(names) == len(set(names))
    assert {n for n in names if "__" in n} == {t["name"] for t in mine(body, "tools")}


def test_market_tool_names_stay_mcp_safe_distinct_and_stable_at_the_longest_ids():
    longest_app, longest_tool = "a" * 59, "t" * 40  # schema maxima: metadata.id 59, tool name 40
    assert market_tool_name(APP, "status") == f"{APP}__status"
    names = {market_tool_name(longest_app, longest_tool), market_tool_name(longest_app, "t" * 39 + "u"),
             market_tool_name("a" * 58 + "b", longest_tool), market_tool_name(longest_app, "x")}
    assert len(names) == 4
    for n in names:
        assert TOOL_NAME_RE.match(n) and len(n) <= 64 and "." not in n, n
    assert market_tool_name(longest_app, longest_tool) == market_tool_name(longest_app, longest_tool)
    assert market_tool_name(longest_app, longest_tool).endswith("__" + longest_tool)


def test_the_receipt_not_the_catalog_file_is_what_is_served(market):
    path = Path(market.app.state.settings.apps_dir) / APP / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["extensions"]["tools"].append(tool("sneaky", "destructive"))
    path.write_text(yaml.safe_dump(doc))
    assert f"{APP}__sneaky" not in {t["name"] for t in surfaces(market)["tools"]}


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
        "mapLayers": [{"id": "audit", "title": "Audit", "source": "GET /v1/audit"},
                      {"id": "pins", "title": "Pins", "source": "emits"}],
        "extensions": {"settings": {"schema": "settings.json"},
                       "widgets": [{"id": "frame", "title": "Frame", "render": "iframe", "entry": "w.html",
                                    "surfaces": ["dashboard"]}]},
    })
    reg = SurfaceRegistry(Builtins({}, frozenset), known_action=lambda t: False,
                          event_topic=lambda e: None, openapi=dict, market=lambda: [m])
    view = reg.view(lambda _: True)
    assert view["notifications"] == [] and view["cards"] == []
    assert [(r["kind"], r["id"]) for r in view["refused"]] == [("topic", "down"), ("layer", "audit")]
    assert view["map_layers"] == [{"app_id": "kuma", "id": "pins", "title": "Pins", "source": "emits"}]
    assert view["settings_pages"] == [{"app_id": "kuma", "id": "settings", "title": "Kuma settings",
                                       "source": "GET /v1/plugins/kuma/settings"}]
    assert reg.view(lambda _: False)["apps"] == []
