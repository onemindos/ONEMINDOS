# SPDX-License-Identifier: Apache-2.0
"""Built-in descriptors and the conformance rules CI enforces on them (builtins.py, #603).

Every id on the signed system apps list must have a descriptor that the running gateway agrees with:
each route it calls is in the public OpenAPI, each prefix it owns is real and owned by nobody else,
each backup table exists, each action type is registered and each notification event is in the
notify catalogue. A switched-off built-in is refused by one gate and leaves every list.
"""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from sqlalchemy import inspect
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocket

from conftest import AGENT, OWNER, make_client
from onemind_core import builtins, systemlist
from onemind_core.actions import APP_CLAIMS
from onemind_core.errors import ApiError
from onemind_core.mcp import Catalogue, Limits, McpEndpoint, McpSettings, Services
from onemind_core.notify.catalogue import lookup
from test_appstore import request, run

REPO = Path(__file__).resolve().parents[2]
OPENAPI = json.loads((REPO / "sdk" / "openapi" / "onemind-v1.json").read_text())
SIGNED = systemlist.load(systemlist.REPO_FILE)
METHODS = ("get", "post", "put", "patch", "delete")
APP_SCHEMA = json.loads((REPO / "sdk" / "schema" / "onemind.app.schema.json").read_text())
BUILTIN_SCHEMA = json.loads(builtins.REPO_SCHEMA.read_text())
BOGUS = [{"Authorization": "Bearer om_made_up_token"}, {"Authorization": "Basic Zm9vOmJhcg=="},
         {"Cookie": "__Host-onemind_session=made-up"}]


def problems(d: builtins.Descriptor, others: list[builtins.Descriptor], tables: set[str], types: set[str]) -> list[str]:
    """The conformance rules a JSON Schema cannot say, checked against the live gateway."""
    out = []
    for call in d.calls():
        method, path = call.split(" ", 1)
        if method.lower() not in OPENAPI["paths"].get(path, {}):
            out.append(f"{d.id} calls {call}, which is not in the public OpenAPI")
    for prefix in d.owns():
        if not any(builtins.under(p, prefix) for p in OPENAPI["paths"]):
            out.append(f"{d.id} owns {prefix}, but no public route is under it")
        for e in others:
            if e.id != d.id and any(builtins.under(prefix, q) or builtins.under(q, prefix) for q in e.owns()):
                out.append(f"{d.id} and {e.id} both own routes under {prefix}")
    for unit in d.spec["backup"]["units"]:
        if unit["kind"] == "table" and unit["name"] not in tables:
            out.append(f"{d.id} backs up table {unit['name']}, which the gateway does not have")
    if not d.spec["backup"]["units"] and not d.spec["backup"].get("none", "").strip():
        out.append(f"{d.id} declares no backup unit or reason")
    for a in d.spec.get("actions", []):
        if a["type"] not in types:
            out.append(f"{d.id} declares action {a['type']}, which the gateway has not registered")
    for topic in (d.spec.get("notifications") or {}).get("topics", []):
        if len(f"app.{d.id}.{topic['id']}") > 80:
            out.append(f"{d.id} topic {topic['id']} makes app.{d.id}.{topic['id']}, longer than 80 characters")
        for ev in topic.get("events", []):
            spec = lookup(ev)
            if spec is None or spec.topic != topic["id"]:
                out.append(f"{d.id} declares {ev} under topic {topic['id']}, which the notify catalogue does not")
    return out


@pytest.fixture
def c(settings, clock):
    with make_client(settings, clock) as client:
        yield client


def live(c) -> tuple[set[str], set[str]]:
    gw = c.app.state.gateway
    return set(inspect(gw.db.engine).get_table_names()), set(gw.actions.feature_types) | set(APP_CLAIMS)


def doc_of(app_id: str) -> dict:
    return yaml.safe_load((builtins.PACKAGE_DIR / app_id / builtins.DESCRIPTOR).read_text())


def load_one(tmp_path: Path, app_id: str, doc: dict) -> tuple[dict, dict]:
    (tmp_path / app_id).mkdir()
    (tmp_path / app_id / builtins.DESCRIPTOR).write_text(yaml.safe_dump(doc))
    lst = systemlist.SystemList({app_id: systemlist.SystemApp(app_id, app_id, "native", "os", "allowed")})
    return builtins.load(lst, root=tmp_path)


# ---- every built-in on the signed list conforms ---------------------------------------------------------

def test_every_signed_built_in_has_a_valid_descriptor():
    found, errors = builtins.load(SIGNED)
    assert errors == {}
    assert set(found) == SIGNED.ids()


def test_every_descriptor_agrees_with_the_running_gateway(c):
    tables, types = live(c)
    found = c.app.state.builtins.descriptors
    assert set(found) == SIGNED.ids()
    assert [p for d in found.values() for p in problems(d, list(found.values()), tables, types)] == []


def test_the_signed_list_holds_the_wave_1_built_ins_and_the_never_off_set():
    assert {"files", "approvals", "settings", "market", "updates", "backups", "notifications", "photos"} <= SIGNED.ids()
    assert {"work", "dashboards", "search"} <= SIGNED.ids()
    for app_id in ("updates", "backups", "notifications"):
        assert app_id in systemlist.NEVER_DISABLE and not SIGNED.get(app_id).can_disable
    assert SIGNED.get("photos").can_disable


# ---- what fails CI ---------------------------------------------------------------------------------------

def test_removing_a_backup_unit_fails(tmp_path):
    doc = doc_of("files")
    doc["spec"]["backup"]["units"] = []
    found, errors = load_one(tmp_path, "files", doc)
    assert "files" not in found and any("backup" in e for e in errors["files"])


def test_empty_backup_units_with_a_reason_pass(tmp_path):
    doc = doc_of("search")
    assert doc["spec"]["backup"] == {
        "units": [], "none": "index is rebuilt from providers; excluded from backups on purpose",
    }
    found, errors = load_one(tmp_path, "search", doc)
    assert set(found) == {"search"} and errors == {}


@pytest.mark.parametrize("reason", ["", " \t "])
def test_empty_backup_units_with_a_blank_reason_fail(tmp_path, reason):
    doc = doc_of("search")
    doc["spec"]["backup"]["none"] = reason
    found, errors = load_one(tmp_path, "search", doc)
    assert "search" not in found and any("backup/none" in e for e in errors["search"])


def test_dropping_the_backup_block_fails(tmp_path):
    doc = doc_of("photos")
    del doc["spec"]["backup"]
    found, errors = load_one(tmp_path, "photos", doc)
    assert "photos" not in found and any("backup" in e for e in errors["photos"])


def test_a_call_to_a_route_missing_from_the_public_openapi_fails(c):
    tables, types = live(c)
    d = c.app.state.builtins.descriptors["files"]
    spec = copy.deepcopy(d.spec)
    spec["routes"]["calls"].append("GET /v1/files/secret-door")
    bad = replace(d, spec=spec)
    assert any("not in the public OpenAPI" in p for p in problems(bad, [bad], tables, types))


def test_unknown_table_action_event_and_overlap_fail(c):
    tables, types = live(c)
    found = c.app.state.builtins.descriptors
    spec = copy.deepcopy(found["photos"].spec)
    spec["backup"]["units"].append({"kind": "table", "name": "photos_nowhere"})
    spec["actions"] = [{"type": "photos.erase_everything", "title": "Erase", "mcp": True}]
    spec["notifications"] = {"topics": [{"id": "backups", "events": ["photos.invented"]}]}
    spec["routes"]["owns"].append("/v1/files/list")
    bad = replace(found["photos"], spec=spec)
    out = problems(bad, [bad, found["files"]], tables, types)
    for what in ("photos_nowhere", "photos.erase_everything", "photos.invented", "both own"):
        assert any(what in p for p in out), (what, out)


def test_a_descriptor_for_an_id_not_on_the_signed_list_is_ignored(tmp_path):
    doc = doc_of("photos")
    doc["metadata"]["id"] = "sneaky"
    (tmp_path / "sneaky").mkdir()
    (tmp_path / "sneaky" / builtins.DESCRIPTOR).write_text(yaml.safe_dump(doc))
    assert builtins.load(SIGNED, root=tmp_path) == ({}, {})


def test_no_schema_loads_nothing(tmp_path):
    assert builtins.load(SIGNED, schema=tmp_path / "missing.json") == ({}, {})


# ---- switched off: one gate, gone from every list ----------------------------------------------------------

def owned_operations(prefix: str):
    for path, ops in OPENAPI["paths"].items():
        if builtins.under(path, prefix):
            for method in ops:
                if method in METHODS:
                    yield method, path.replace("{", "").replace("}", "")


def surface_tools_under(c, prefix: str) -> list[str]:
    """Names of the tools GET /v1/surfaces lists whose route is under the app's prefix."""
    out = c.get("/v1/surfaces", headers=OWNER).json()
    return [t["name"] for t in out["tools"] if t["route"] and builtins.under(t["route"].split(" ", 1)[1], prefix)]


@pytest.mark.parametrize(("app_id", "prefix", "min_ops", "probe", "has_backup"), [
    ("photos", "/v1/photos", 5, "/v1/photos/library", True),
    ("work", "/v1/work", 7, "/v1/work/tasks", True),
    ("dashboards", "/v1/me/dashboard-card", 3, "/v1/me/dashboard-card", True),
    ("search", "/v1/search", 1, "/v1/search?q=test", False),
])
def test_a_switched_off_built_in_answers_409_on_every_route_and_leaves_every_list(
    c, clock, app_id, prefix, min_ops, probe, has_backup,
):
    before = c.get("/v1/builtins", headers=OWNER).json()
    assert app_id in {a["id"] for a in before["apps"]}
    assert any(u["app_id"] == app_id for u in before["backup_units"]) == has_backup
    tools_before = len(surface_tools_under(c, prefix))
    if app_id == "work":
        assert tools_before >= 2  # work_tasks_list and work_task_get are core tools on /v1/work
    assert run(c, clock, "app.disable", {"app_id": app_id}).json()["state"] == "succeeded"

    ops = list(owned_operations(prefix))
    assert len(ops) >= min_ops
    for method, path in ops:
        r = c.request(method.upper(), path, headers=OWNER)
        assert r.status_code == 409 and r.json()["reason"] == "app_disabled", (method, path, r.text)
    assert c.get(probe).status_code == 401  # no sign-in: not told it is off

    after = c.get("/v1/builtins", headers=OWNER).json()
    assert app_id not in {a["id"] for a in after["apps"]}
    assert not any(u["app_id"] == app_id for u in after["backup_units"])
    assert not surface_tools_under(c, prefix)

    assert run(c, clock, "app.enable", {"app_id": app_id}).json()["state"] == "succeeded"
    assert app_id in {a["id"] for a in c.get("/v1/builtins", headers=OWNER).json()["apps"]}
    assert c.get(probe, headers=OWNER).status_code != 409
    assert len(surface_tools_under(c, prefix)) == tools_before


def test_builtins_lists_settings_pages_backup_units_and_tools(c):
    out = c.get("/v1/builtins", headers=OWNER).json()
    assert {"app_id": "updates", "id": "update-policy", "title": "Automatic updates",
            "source": "GET /v1/update-policy"} in out["settings_pages"]
    assert {"app_id": "backups", "kind": "table", "name": "backups_runs"} in out["backup_units"]
    assert {"name": "request_backup_run", "app_id": "backups", "action_type": "backup.run",
            "title": "Back up now"} in out["tools"]


@pytest.mark.parametrize("app_id", ["updates", "backups", "notifications"])
def test_the_new_never_off_built_ins_cannot_be_switched_off(c, clock, app_id):
    r = request(c, clock, "app.disable", {"app_id": app_id})
    assert r.status_code == 409 and r.json()["reason"] == "system_app_protected", r.text


@pytest.mark.parametrize("who", [OWNER, AGENT], ids=["owner", "agent"])
def test_no_system_id_can_be_uninstalled(c, clock, who):
    for app_id in sorted(SIGNED.ids()):
        r = request(c, clock, "app.remove", {"app_id": app_id}, headers=who)
        assert r.status_code == 409 and r.json()["reason"] == "system_app_protected", (app_id, r.text)


# ---- MCP tools come from the descriptors of switched-on built-ins ------------------------------------------

def endpoint(c, clock, registry):
    gw = c.app.state.gateway
    svc = Services(
        instance=dict, list_nodes=list, get_node=lambda _: None, list_apps=list,
        own_actions=lambda pid: [a for a in gw.actions.list() if a["requested_by"]["id"] == pid],
        get_action=gw.actions.get, request=lambda p, req, reason: gw.actions.create(p, req, reason=reason),
        audit_list=lambda **_: ([], False), clock=clock,
        builtin_actions=lambda: {n: (t, title, d.name) for n, (t, title, d) in registry.mcp_actions().items()},
    )
    limits = Limits(McpSettings(), clock)
    return McpEndpoint(Catalogue(svc, limits), limits, refuse=lambda p, what: None)


def tool_names(ep, p) -> set[str]:
    return {t["name"] for t in ep.dispatch(p, "tools/list", {})["tools"]}


def test_descriptor_tools_need_their_scope_file_requests_only_and_vanish_when_off(c, clock):
    gw = c.app.state.gateway
    agent = next(p for p in gw.tokens.principals() if p.kind == "agent")
    registry = c.app.state.builtins
    ep = endpoint(c, clock, registry)
    assert "request_app_disable" not in tool_names(ep, agent)  # the v0 bundle holds no feature type
    scoped = replace(agent, scopes=frozenset({"apps:read", "actions:read:own", "actions:request:app.disable"}))
    assert "request_app_disable" in tool_names(ep, scoped)
    denied = ep.dispatch(agent, "tools/call", {"name": "request_app_disable", "arguments": {"params": {"app_id": "photos"}}})
    assert denied["structuredContent"]["error"] == "permission_denied"

    out = ep.dispatch(scoped, "tools/call", {"name": "request_app_disable", "arguments": {"params": {"app_id": "photos"}}})
    action_id = out["structuredContent"]["action_id"]
    assert out["structuredContent"]["state"] == "awaiting_approval"
    assert c.post(f"/v1/actions/{action_id}/approve", headers=AGENT).status_code == 403  # never its own approver
    photos = next(r for r in c.get("/v1/system-apps", headers=OWNER).json() if r["id"] == "photos")
    assert photos["enabled"] is True

    off = builtins.Builtins(registry.descriptors, lambda: frozenset({"market"}))
    assert "request_app_disable" not in tool_names(endpoint(c, clock, off), scoped)


# ---- one manifest: the descriptor is the built-in profile of the App manifest -----------------------------

def app_block_validator(name: str) -> Draft202012Validator:
    """The App schema's own definition of spec.<name>, with the App schema's $defs."""
    return Draft202012Validator({**APP_SCHEMA["properties"]["spec"]["properties"][name], "$defs": APP_SCHEMA["$defs"]})


def test_descriptors_use_the_app_manifest_api_version_kind_and_file_name():
    assert BUILTIN_SCHEMA["properties"]["apiVersion"]["const"] in APP_SCHEMA["properties"]["apiVersion"]["enum"]
    assert BUILTIN_SCHEMA["properties"]["kind"] == APP_SCHEMA["properties"]["kind"] == {"const": "App"}
    assert builtins.DESCRIPTOR == "onemind.app.yaml"
    for app_id in sorted(SIGNED.ids()):
        doc = doc_of(app_id)
        assert (doc["apiVersion"], doc["kind"]) == ("onemind.app/v1", "App"), app_id


def test_no_descriptor_block_reuses_an_app_spec_name_with_another_shape():
    shared = set(BUILTIN_SCHEMA["properties"]["spec"]["properties"]) & set(APP_SCHEMA["properties"]["spec"]["properties"])
    # #604 moved search, share, notifications, mapLayers and data into the App spec; every descriptor block
    # of those names must still validate against the App block, and the rest stay descriptor-only.
    assert shared == {"backup", "search", "share", "notifications", "mapLayers", "data"}
    assert set(BUILTIN_SCHEMA["properties"]["spec"]["properties"]) - shared == {"routes", "cards", "actions",
                                                                                "settingsPages", "phone"}
    for app_id in sorted(SIGNED.ids()):
        spec = doc_of(app_id)["spec"]
        for name in sorted(shared & set(spec)):
            errs = [e.message for e in app_block_validator(name).iter_errors(spec[name])]
            assert errs == [], (app_id, name, errs)
    def strip(d: dict) -> dict:
        return {k: v for k, v in d.items() if k != "description"}
    assert strip(BUILTIN_SCHEMA["$defs"]["backupUnit"]) == strip(APP_SCHEMA["$defs"]["backupUnit"])


@pytest.mark.parametrize("change", ["kind-builtin", "settings-pages-block"])
def test_the_old_clashing_names_are_refused(tmp_path, change):
    doc = doc_of("updates")
    if change == "kind-builtin":
        doc["kind"] = "Builtin"
    else:
        doc["spec"]["settings"] = {"pages": doc["spec"].pop("settingsPages")}
    found, errors = load_one(tmp_path, "updates", doc)
    assert "updates" not in found and errors["updates"]


def test_a_market_app_may_not_declare_backup_units():
    manifest = yaml.safe_load((REPO / "apps" / "actual-budget" / "onemind.app.yaml").read_text())
    validator = Draft202012Validator(APP_SCHEMA)
    assert list(validator.iter_errors(manifest)) == []
    manifest["spec"].setdefault("backup", {})["units"] = [{"kind": "table", "name": "actions"}]
    assert any("system" in e.message for e in validator.iter_errors(manifest))
    manifest["spec"]["backup"].update(units=[], none="rebuildable cache")
    assert any("system" in e.message for e in validator.iter_errors(manifest))


# ---- the gate: no oracle for made-up credentials, no way round it for public or websocket routes -----------

def add_probe_routes(app):
    """A public HTTP route and a websocket route under /v1/photos, like ones a later slice may add."""
    @app.get("/v1/photos/public-probe", include_in_schema=False)
    def public_probe():
        return {"ok": True}

    @app.websocket("/v1/photos/live-probe")
    async def live_probe(ws: WebSocket):
        await ws.accept()
        await ws.send_json({"ok": True})
        await ws.close()

    # Ahead of the photo routes and the /v1 fallback, which would otherwise answer first.
    app.router.routes[:0] = [app.router.routes.pop(), app.router.routes.pop()]


@pytest.mark.parametrize("headers", BOGUS, ids=["bearer", "basic", "cookie"])
def test_a_made_up_credential_is_not_told_the_app_is_off(c, clock, headers):
    assert run(c, clock, "app.disable", {"app_id": "photos"}).json()["state"] == "succeeded"
    r = c.get("/v1/photos/library", headers=headers)
    assert r.status_code == 401 and r.json().get("reason") != "app_disabled", r.text
    assert c.get("/v1/photos/library", headers=OWNER).json()["reason"] == "app_disabled"


def test_public_and_websocket_routes_under_an_owned_prefix_are_shut_when_off(c, clock):
    add_probe_routes(c.app)
    assert c.get("/v1/photos/public-probe").status_code == 200
    with c.websocket_connect("/v1/photos/live-probe", headers=OWNER) as ws:
        assert ws.receive_json() == {"ok": True}

    assert run(c, clock, "app.disable", {"app_id": "photos"}).json()["state"] == "succeeded"
    assert c.get("/v1/photos/public-probe").status_code == 401
    r = c.get("/v1/photos/public-probe", headers=OWNER)
    assert r.status_code == 409 and r.json()["reason"] == "app_disabled"
    for headers, status in ((OWNER, 409), ({}, 401), (BOGUS[0], 401)):
        with pytest.raises(WebSocketDenialResponse) as denied, \
                c.websocket_connect("/v1/photos/live-probe", headers=headers):
            pass
        assert denied.value.status_code == status, headers

    assert run(c, clock, "app.enable", {"app_id": "photos"}).json()["state"] == "succeeded"
    assert c.get("/v1/photos/public-probe").status_code == 200


def test_a_websocket_without_the_denial_extension_is_closed(c):
    registry = builtins.Builtins(c.app.state.builtins.descriptors, lambda: frozenset({"photos"}))

    async def never(scope, receive, send):
        raise AssertionError("the route must not run")

    def go(principal):
        sent = []
        gate = builtins.BuiltinGate(never, builtins=registry, principal=principal)
        scope = {"type": "websocket", "path": "/v1/photos/live-probe", "headers": [], "query_string": b""}

        async def receive():
            return {"type": "websocket.connect"}

        async def send(message):
            sent.append(message)
        asyncio.run(gate(scope, receive, send))
        return sent

    def refuse(_request):
        raise ApiError(401, "unauthenticated", "missing bearer token")

    assert go(lambda _request: object()) == [{"type": "websocket.close", "code": 4409, "reason": "app_disabled"}]
    assert go(refuse) == [{"type": "websocket.close", "code": 4401, "reason": ""}]


# ---- GET /v1/builtins is provisional: it folds into the surface registry -----------------------------------

def test_builtins_route_is_marked_provisional_in_the_public_openapi(c):
    for spec in (OPENAPI, c.get("/openapi.json").json()):
        op = spec["paths"]["/v1/builtins"]["get"]
        assert "/v1/surfaces" in op["x-onemind-provisional"], op
