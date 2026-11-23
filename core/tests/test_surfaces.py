# SPDX-License-Identifier: Apache-2.0
"""The surface registry (#605): generated MCP catalogue, route parity, GET /v1/surfaces and refusals."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import replace

import pytest

from conftest import AGENT, OWNER, action_body, make_client
from onemind_core import builtins
from onemind_core.auth import MCP_BY_NAME_ONLY
from onemind_core.ai_policy import catalog_visible_to_ai
from onemind_core.mcp import TOOLS, Catalogue, Limits, McpEndpoint, McpSettings, Services
from onemind_core.mcp.authz import TOOL_SCOPES
from onemind_core.mcp.tools import RpcError
from onemind_core.notify.catalogue import lookup
from onemind_core.surfaces import parity
from onemind_core.surfaces.core import AREA_TOOLS, CORE_TOOLS, ToolSurface
from onemind_core.surfaces.registry import SurfaceRegistry, card_problem
from test_appstore import run
from test_builtin_conformance import doc_of, load_one
from test_mcp import call, rpc
from test_nodes_catalog import heartbeat


@pytest.fixture
def c(settings, clock):
    with make_client(settings, clock) as client:
        yield client


def tool_routes() -> dict[str, str]:
    out: dict[str, str] = {}
    for t in CORE_TOOLS:
        out[t.route] = f"{out[t.route]}, {t.name}" if t.route in out else t.name
    return out


def registry_for(c, found: dict, off: frozenset[str] = frozenset()) -> SurfaceRegistry:
    gw = c.app.state.gateway
    return SurfaceRegistry(builtins.Builtins(found, lambda: off),
                           known_action=lambda t: t in gw.actions.feature_types,
                           event_topic=lambda e: (lookup(e).topic if lookup(e) else None), openapi=c.app.openapi)


# ---- the MCP catalogue is generated from one declaration per tool ------------------------------------

def test_mcp_tools_and_scopes_are_generated_from_the_registry(c):
    assert [t["name"] for t in TOOLS] == [t.name for t in CORE_TOOLS if "mcp" in t.exposure]
    assert TOOL_SCOPES == {t.name: t.scope for t in CORE_TOOLS}
    for t in CORE_TOOLS:
        tool = next(x for x in TOOLS if x["name"] == t.name)
        assert tool["annotations"]["readOnlyHint"] is (t.effect == "read")
    listed = rpc(c, "tools/list").json()["result"]["tools"]
    # A token with no `scopes:` (v0) lists every tool but those granted by name only (logs, file details, #632).
    by_name = {t.name for t in CORE_TOOLS if t.scope in MCP_BY_NAME_ONLY}
    assert by_name == {"read_app_logs", "stat_file"}
    assert {t["name"] for t in listed} == {t.name for t in CORE_TOOLS} - by_name
    described = c.app.openapi()["paths"]["/mcp"]["post"]["description"]
    assert all(t.name in described for t in CORE_TOOLS)


def test_a_tool_with_an_undeclared_effect_or_exposure_is_refused():
    with pytest.raises(ValueError):
        ToolSurface("x", "X", "x", "actuate", "GET /v1/x", "instance:read", {})
    with pytest.raises(ValueError):
        ToolSurface("x", "X", "x", "read", "GET /v1/x", "instance:read", {}, exposure=("mcp", "sms"))


# ---- parity: every route has a tool or a named human-only entry --------------------------------------

def test_every_route_has_a_tool_or_a_human_only_entry(c):
    assert parity.problems(parity.route_keys(c.app), tool_routes()) == []


def test_a_new_route_with_no_tool_and_no_human_only_entry_fails_ci(c):
    @c.app.get("/v1/brand-new")
    def brand_new():
        return {}

    out = parity.problems(parity.route_keys(c.app), tool_routes())
    assert len(out) == 1 and out[0].startswith("GET /v1/brand-new has no tool and no human-only entry"), out


def test_the_gateway_names_unlisted_routes_in_its_log_at_startup(settings, clock, monkeypatch, caplog):
    with make_client(settings, clock):
        pass
    assert "surface parity" not in caplog.text
    monkeypatch.delitem(parity.HUMAN_ONLY, "POST /v1/tokens")
    with make_client(settings, clock):
        pass
    assert "surface parity: 1 route(s) have no tool and no human-only entry: POST /v1/tokens" in caplog.text


def test_stale_double_and_unknown_entries_fail(c, monkeypatch):
    keys = parity.route_keys(c.app)
    monkeypatch.setitem(parity.HUMAN_ONLY, "GET /v1/gone", parity.WRITE)
    monkeypatch.setitem(parity.HUMAN_ONLY, "GET /v1/nodes", parity.DOOR)
    monkeypatch.setitem(parity.HUMAN_ONLY, "POST /v1/actions/{action_id}/approve", "because")
    out = parity.problems(keys, {**tool_routes(), "GET /v1/missing": "ghost"})
    for what in ("GET /v1/gone is listed", "GET /v1/nodes is in a tool and HUMAN_ONLY",
                 "reason 'because'", "tool ghost projects GET /v1/missing"):
        assert any(what in p for p in out), (what, out)


def test_approve_deny_and_credentials_are_human_only():
    for key in ("POST /v1/actions/{action_id}/approve", "POST /v1/actions/{action_id}/deny",
                "POST /v1/approval-policies", "PUT /v1/agents/kill-switch", "POST /v1/tokens"):
        assert parity.HUMAN_ONLY[key] in (parity.OVERSIGHT, parity.CREDENTIAL), key
    assert not [k for k in parity.AWAITING_TOOL if not k.startswith(("GET ", "POST /v1/plans", "POST /v1/notifications/send"))]


# AWAITING_TOOL is a ratchet: it may only lose entries. This snapshot is the list as it stood when the
# ratchet was frozen; an entry leaves both when its tool lands, and a new route never joins either.
AWAITING_TOOL_SNAPSHOT = frozenset({
    "GET /v1/agents",
    "GET /v1/agents/{name}",
    "GET /v1/alerts",
    "GET /v1/alerts/{alert_id}",
    "GET /v1/apps/{app_id}",
    "GET /v1/apps/{app_id}/access",
    "GET /v1/apps/{app_id}/dependencies",
    "GET /v1/apps/{app_id}/exposure",
    "GET /v1/apps/{app_id}/host-ports",
    "GET /v1/apps/{app_id}/logs",
    "GET /v1/apps/{app_id}/metrics",
    "GET /v1/apps/{app_id}/owner-override",
    "GET /v1/apps/{app_id}/placement",
    "GET /v1/apps/{app_id}/plan",
    "GET /v1/apps/{app_id}/settings",
    "GET /v1/audit/events/{seq}",
    "GET /v1/audit/verify",
    "GET /v1/automation/rules",
    "GET /v1/automation/rules/{rule_id}",
    "GET /v1/automation/runs",
    "GET /v1/automation/schedules",
    "GET /v1/automation/state",
    "GET /v1/backups/content",
    "GET /v1/backups/destinations",
    "GET /v1/backups/runs",
    "GET /v1/backups/runs/{run_id}",
    "GET /v1/backups/snapshots",
    "GET /v1/backups/snapshots/{snapshot_id}",
    "GET /v1/backups/snapshots/{snapshot_id}/tree",
    "GET /v1/backups/status",
    "GET /v1/backups/verifications",
    "GET /v1/builtins",
    "GET /v1/databases",
    "GET /v1/domains",
    "GET /v1/fabric",
    "GET /v1/family/apps/{app_id}",
    "GET /v1/family/profiles/{user_id}",
    "GET /v1/files/grants",
    "GET /v1/files/list",
    "GET /v1/files/quotas",
    "GET /v1/files/requests",
    "GET /v1/files/requests/{request_id}",
    "GET /v1/files/roots",
    "GET /v1/files/stat",
    "GET /v1/files/trash",
    "GET /v1/instance/kiosk",
    "GET /v1/instance/name",
    "GET /v1/machines",
    "GET /v1/machines/capabilities",
    "GET /v1/machines/{name}",
    "GET /v1/machines/{name}/snapshots",
    "GET /v1/mesh",
    "GET /v1/migrate/plans",
    "GET /v1/migrate/plans/{plan_id}",
    "GET /v1/migrate/plans/{plan_id}/helper",
    "GET /v1/monitoring/summary",
    "GET /v1/network",
    "GET /v1/nodes/{node_id}/metrics",
    "GET /v1/nodes/{node_id}/wake",
    "GET /v1/notifications/channels",
    "POST /v1/notifications/send",
    "GET /v1/notifications/sources",
    "GET /v1/onboarding/settings",
    "GET /v1/onboarding/state",
    "GET /v1/os/about",
    "GET /v1/os/updates",
    "GET /v1/os/updates/history",
    "GET /v1/photos/library",
    "GET /v1/photos/sources/{source_id}/coverage",
    "GET /v1/photos/sources/{source_id}/receipts",
    "GET /v1/physical/lockout",
    "POST /v1/plans",
    "GET /v1/plugins",
    "GET /v1/plugins/{plugin_id}",
    "GET /v1/plugins/{plugin_id}/settings",
    "GET /v1/plugins/{plugin_id}/tools",
    "GET /v1/radios",
    "GET /v1/restores",
    "GET /v1/restores/{restore_id}",
    "GET /v1/search",
    "GET /v1/series",
    "GET /v1/shares/smb",
    "GET /v1/sources",
    "GET /v1/sources/{source_id}",
    "GET /v1/status",
    "GET /v1/storage",
    "GET /v1/storage/devices",
    "GET /v1/storage/operations/{action_id}",
    "GET /v1/subjects",
    "GET /v1/subjects/check",
    "GET /v1/system-apps",
    "GET /v1/system/controls",
    "GET /v1/system/diagnostics",
    "GET /v1/system/services",
    "GET /v1/tls",
    "GET /v1/update-policy",
    "GET /v1/update-policy/dry-run",
    "GET /v1/usage",
    "GET /v1/users",
})


def ratchet_problems(awaiting, snapshot=AWAITING_TOOL_SNAPSHOT) -> list[str]:
    return [f"{k} was added to AWAITING_TOOL, which may only shrink: give it a ToolSurface or a HUMAN_ONLY reason"
            for k in sorted(set(awaiting) - snapshot)]


def test_awaiting_tool_only_shrinks():
    assert ratchet_problems(parity.AWAITING_TOOL) == []


def test_parking_a_new_route_in_awaiting_tool_fails_ci(c, monkeypatch):
    @c.app.get("/v1/brand-new")
    def brand_new():
        return {}

    monkeypatch.setattr(parity, "AWAITING_TOOL", parity.AWAITING_TOOL | {"GET /v1/brand-new"})
    assert parity.problems(parity.route_keys(c.app), tool_routes()) == []  # parity alone would let it through
    assert ratchet_problems(parity.AWAITING_TOOL) == [
        "GET /v1/brand-new was added to AWAITING_TOOL, which may only shrink: give it a ToolSurface or a "
        "HUMAN_ONLY reason"]
    assert ratchet_problems(parity.AWAITING_TOOL - {"GET /v1/radios", "GET /v1/brand-new"}) == []


def test_the_registry_route_and_radio_confirm_are_not_parked():
    assert "GET /v1/surfaces" not in parity.AWAITING_TOOL
    assert parity.HUMAN_ONLY["GET /v1/surfaces"] == parity.DOOR
    assert parity.HUMAN_ONLY["POST /v1/radios/{radio_id}/confirm"] == parity.OVERSIGHT
    assert {"GET /v1/radios", "GET /v1/search"} <= parity.AWAITING_TOOL  # reads served before the freeze


# ---- read tools return the same body as their REST route ---------------------------------------------

def _rows(value):
    return sorted(value, key=lambda r: json.dumps(r, sort_keys=True)) if isinstance(value, list) else value


def test_read_tools_return_the_same_body_as_their_rest_route(c, clock):
    gw = c.app.state.gateway
    assert gw.registry.ingest("onemind.node.3f9c2a1b7d4e.status", heartbeat())
    filed = c.post("/v1/actions", json=action_body(clock, key="parity"), headers=AGENT).json()
    ids = {"node_id": "3f9c2a1b7d4e", "app_id": "whoami", "action_id": filed["id"]}
    # The area read tools (#632) redact, cap and page: tests/test_mcp_read_tools.py compares them with REST.
    for t in (t for t in CORE_TOOLS if t.effect == "read" and t not in AREA_TOOLS):
        method, path = t.route.split(" ", 1)
        args = {k: ids[k] for k in re.findall(r"{(\w+)}", path)}
        rest = c.request(method, path.format(**args), headers=AGENT)
        if t.row_of:
            args[t.row_of] = ids[t.row_of]
        assert rest.status_code == 200, (t.name, rest.text)
        body = rest.json()
        if t.projection == "ai_policy":
            body = [a for a in body if catalog_visible_to_ai(a)] if isinstance(body, list) else body
        if t.row_of:
            body = next(row for row in body if row["id"] == args[t.row_of])
        got = call(c, t.name, args)["result"]
        assert not got["isError"], (t.name, got)
        out = got["structuredContent"]
        if t.body_key:
            assert set(out) <= {t.body_key, "next_cursor"}, t.name
            out = out[t.body_key]
        else:
            assert set(out) - set(body) == set(t.adds), t.name
            out = {k: v for k, v in out.items() if k not in t.adds}
        assert _rows(out) == _rows(body), t.name
        assert body, f"{t.name}: compare real data, not an empty body"


# ---- GET /v1/surfaces --------------------------------------------------------------------------------

def test_surfaces_lists_every_switched_on_built_in_and_its_tools(c):
    r = c.get("/v1/surfaces", headers=OWNER)
    assert r.status_code == 200, r.text
    out = r.json()
    assert {"photos", "backups", "files", "market"} <= {a["id"] for a in out["apps"]}
    tools = {t["name"]: t for t in out["tools"]}
    assert tools["list_nodes"] == {"name": "list_nodes", "app_id": None, "title": "List OneMind nodes",
                                   "effect": "read", "exposure": ["mcp", "rest"], "route": "GET /v1/nodes",
                                   "action_type": None, "scope": "nodes:read"}
    assert tools["request_backup_run"]["action_type"] == "backup.run"
    assert tools["request_backup_run"]["scope"] == "actions:request:backup.run"
    assert {"app_id": "files", "provider": "files", "types": ["file", "folder"]} in out["search"]
    assert {"app_id": "photos", "accepts": ["file"], "verbs": ["add"]} in out["share"]
    assert {"app_id": "updates", "id": "update-policy", "title": "Automatic updates",
            "source": "GET /v1/update-policy"} in out["settings_pages"]
    assert any(t["app_id"] == "backups" and t["id"] == "backups" for t in out["notifications"])
    # The one built-in card reads a route whose response declares no observed_at: refused, never drawn.
    assert out["cards"] == []
    assert {"app_id": "backups", "kind": "card", "id": "last-backup",
            "reason": "source GET /v1/backups/status declares no observed_at, so the card could not say "
                      "when its value was read"} in out["refused"]
    assert c.get("/v1/surfaces").status_code == 401


def test_switching_an_app_off_removes_it_from_every_list_and_on_brings_it_back(c, clock):
    def photos_in(out):
        return [k for k, rows in out.items() if any((r.get("app_id") or r.get("id")) == "photos" for r in rows)]

    before = c.get("/v1/surfaces", headers=OWNER).json()
    assert set(photos_in(before)) == {"apps", "search", "share", "backup_units"}
    assert run(c, clock, "app.disable", {"app_id": "photos"}).json()["state"] == "succeeded"
    assert photos_in(c.get("/v1/surfaces", headers=OWNER).json()) == []
    assert run(c, clock, "app.enable", {"app_id": "photos"}).json()["state"] == "succeeded"
    assert photos_in(c.get("/v1/surfaces", headers=OWNER).json()) == photos_in(before)


def test_disabling_an_app_removes_its_mcp_tools_at_once(c, clock):
    gw = c.app.state.gateway
    live = c.app.state.surfaces
    assert {"request_backup_run", "request_backup_verify", "request_app_disable"} <= set(live.mcp_actions())
    agent = next(p for p in gw.tokens.principals() if p.kind == "agent")
    scoped = replace(agent, scopes=frozenset({"apps:read", "actions:read:own", "actions:request:backup.run"}))
    reg = registry_for(c, c.app.state.builtins.descriptors)
    svc = Services(instance=dict, list_nodes=list, get_node=lambda _: None, list_apps=list,
                   own_actions=lambda pid: [], get_action=gw.actions.get,
                   request=lambda p, req, reason: gw.actions.create(p, req, reason=reason),
                   audit_list=lambda *a, **k: ([], False), clock=clock, builtin_actions=lambda: reg.mcp_actions())
    ep = McpEndpoint(Catalogue(svc, Limits(McpSettings(), clock)), Limits(McpSettings(), clock), refuse=lambda p, w: None)
    names = lambda: {t["name"] for t in ep.dispatch(scoped, "tools/list", {})["tools"]}  # noqa: E731
    assert "request_backup_run" in names()
    reg.builtins.disabled = lambda: frozenset({"backups"})
    assert "request_backup_run" not in names()
    assert "backups" not in {t["app_id"] for t in reg.view(lambda _: True)["tools"]}
    with pytest.raises(RpcError, match="unknown tool"):
        ep.dispatch(scoped, "tools/call", {"name": "request_backup_run", "arguments": {}})


# ---- refusals: undeclared tools and topics, cards without observed_at --------------------------------

def test_undeclared_tools_topics_and_cards_without_observed_at_are_refused(c, tmp_path):
    doc = copy.deepcopy(doc_of("photos"))
    doc["spec"]["actions"] = [{"type": "photos.erase_everything", "title": "Erase", "mcp": True}]
    doc["spec"]["notifications"] = {"topics": [{"id": "backups", "events": ["photos.invented"]},
                                               {"id": "reminders", "title": "Reminders"}]}
    doc["spec"]["cards"] = [{"id": "health", "title": "Box health", "template": "status", "source": "GET /v1/status"},
                            {"id": "bare", "title": "Bare", "template": "stat", "source": "GET /v1/backups/status"},
                            {"id": "write", "title": "Write", "template": "stat", "source": "POST /v1/plans"}]
    found, errors = load_one(tmp_path, "photos", doc)
    assert errors == {}
    reg = registry_for(c, found)
    out = reg.view(lambda _: True)
    refused = {(r["kind"], r["id"]): r["reason"] for r in out["refused"]}
    assert "not registered" in refused[("tool", "request_photos_erase_everything")]
    assert "photos.invented" in refused[("topic", "backups")]
    assert "observed_at" in refused[("card", "bare")]
    assert "not a public read operation" in refused[("card", "write")]
    assert [x["id"] for x in out["cards"]] == ["health"]
    assert [t["id"] for t in out["notifications"]] == ["reminders"]
    assert "request_photos_erase_everything" not in reg.mcp_actions()
    assert "request_photos_erase_everything" not in {t["name"] for t in out["tools"]}
    assert card_problem(c.app.openapi(), "GET /v1/nowhere") is not None
