# SPDX-License-Identifier: Apache-2.0
"""#632: MCP read tools for backups, OS updates, file metadata, machines, storage, alerts, settings and logs.

Acceptance: planted secrets never appear; 600 requested log lines return 500 with truncated; every read
area in the parity list has a tool.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
import yaml
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.auth import MCP_BUNDLES
from onemind_core.monitoring import MonitoringSettings
from onemind_core.mcp.read_tools import AREA_TOOL_NAMES, redact
from onemind_core.notify import NotifySettings
from onemind_core.notify.store import AlertRow
from onemind_core.surfaces import parity
from onemind_core.surfaces.core import AREA_PAGE_MAX, AREA_TOOLS, CORE_TOOLS, LOG_LINES_MAX
from test_mcp import H, rpc
from test_monitoring import FakeKube, pod

AREA_TOKEN = "area-reader-agent-token-0123456789"
AREA = {**H, "Authorization": f"Bearer {AREA_TOKEN}"}

# Planted secrets: none of these may reach the model, in the text or in structuredContent.
# Split so secret scanners do not flag the test file itself.
PLANTED = [
    "hunter2-" + "planted",
    "AKIA" + "PLANTEDKEY123456",
    "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjMifQ" + ".plantedsig99",
    "om_pat_" + "PLANTEDTOKEN0001",
    "s3cret-" + "in-url",
    "fake-" + "pem-body-line",
    "ghp_" + "P" * 36,
    "owner" + "@" + "example.org",
    "203.0.113." + "77",
    "Zm9vYmFy" + "planted",
]


@pytest.fixture
def c(settings, clock, executor, tmp_path):
    f = tmp_path / "tokens.yaml"
    doc = yaml.safe_load(settings.tokens_file.read_text())
    doc["tokens"][AREA_TOKEN] = {"id": "area-agent", "kind": "agent", "role": "agent",
                                 "scopes": ["v0", "files:read", "logs:read"]}
    f.write_text(yaml.safe_dump(doc))
    s = replace(settings, tokens_file=f, sections={**settings.sections,
                                                   "notify": NotifySettings(worker=False, dir=tmp_path / "keys"),
                                                   "monitoring": MonitoringSettings(enabled=False)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as client:
        client.app.state.monitoring.kube = FakeKube()
        yield client


def call(c, name, args=None, headers=AREA):
    r = rpc(c, "tools/call", {"name": name, "arguments": args or {}}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "result" in body, body
    return body["result"]


def install(c, clock, app_id="uptime-kuma"):
    a = c.post("/v1/actions", headers=OWNER, json=action_body(clock, app_id=app_id, key=f"i-{app_id}")).json()
    assert c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).json()["state"] == "succeeded"


def plant_alert(c, clock, n=0, title="disk", body="ok", roles=("owner",)):
    now = clock.now
    c.app.state.notify.repo.insert_alert(AlertRow(
        id=f"al_{n:04d}", type="node.disk", severity="warning", title=title, body=body, subject_json="{}",
        source_id="gateway", state="open", dedupe_key=f"k{n}", open_key=f"k{n}",
        audience_json=json.dumps({"roles": list(roles)}), topic="system", opened_at=now, updated_at=now))


# ---- every read area in the parity list has a tool ------------------------------------------------

def test_every_read_area_in_the_parity_list_has_a_tool():
    tools = {t.route: t for t in CORE_TOOLS}
    assert set(parity.READ_AREAS) == {"backups", "os_updates", "files_metadata", "machines", "storage", "alerts",
                                      "settings", "logs"}
    for area, routes in parity.READ_AREAS.items():
        have = [tools[r].name for r in routes if r in tools]
        assert have, f"read area {area} has no MCP tool"
        for r in routes:  # every other route of the area is still accounted for, never forgotten
            assert r in tools or r in parity.AWAITING_TOOL or r in parity.HUMAN_ONLY, r
    for t in AREA_TOOLS:
        assert t.effect == "read" and t.route not in parity.AWAITING_TOOL, t.name
        assert t.route.startswith("GET "), t.name
    assert {t.name for t in AREA_TOOLS} == AREA_TOOL_NAMES


def test_area_routes_in_the_parity_list_are_served(c):
    keys = parity.route_keys(c.app)
    missing = [r for routes in parity.READ_AREAS.values() for r in routes if r not in keys]
    assert missing == []


def test_area_tools_are_listed_with_their_scopes(c):
    listed = {t["name"]: t for t in rpc(c, "tools/list", headers=AREA).json()["result"]["tools"]}
    assert AREA_TOOL_NAMES <= set(listed)
    for name in AREA_TOOL_NAMES:
        assert listed[name]["annotations"]["readOnlyHint"] is True
    # Logs and file details need a scope granted by name: the default (v0) agent does not get them.
    v0 = {t["name"] for t in rpc(c, "tools/list").json()["result"]["tools"]}
    assert "read_app_logs" not in v0 and "stat_file" not in v0
    assert {"get_backup_status", "get_os_updates", "list_machines", "get_storage", "list_alerts",
            "get_update_settings"} <= v0
    assert "logs:read" not in MCP_BUNDLES["v0"] and "files:read" not in MCP_BUNDLES["reader"]
    res = call(c, "read_app_logs", {"app_id": "uptime-kuma"}, headers=H)
    assert res["isError"] and res["structuredContent"]["error"] == "permission_denied"
    assert res["structuredContent"]["scope"] == "logs:read"


# ---- 600 requested log lines return 500 with truncated --------------------------------------------

def test_600_requested_log_lines_return_500_with_truncated(c, clock):
    install(c, clock)
    k = c.app.state.monitoring.kube
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1")]
    k.log_lines = [f"line {i}" for i in range(1000)]
    res = call(c, "read_app_logs", {"app_id": "uptime-kuma", "tail": 600})
    s = res["structuredContent"]
    assert res["isError"] is False
    assert len(s["lines"]) == LOG_LINES_MAX == 500 and s["truncated"] is True
    assert s["lines"][-1] == "line 999" and s["lines"][0] == "line 500"
    assert k.calls[-1] == ("logs", "app-uptime-kuma", "web-1", 501, None)
    # Fewer lines than asked: nothing left out, not truncated.
    k.log_lines = ["a", "b"]
    s = call(c, "read_app_logs", {"app_id": "uptime-kuma", "tail": 600})["structuredContent"]
    assert s["lines"] == ["a", "b"] and s["truncated"] is False
    # Each line is untrusted text, wrapped and listed in _meta.
    res = call(c, "read_app_logs", {"app_id": "uptime-kuma", "tail": 2})
    assert res["_meta"]["onemind/untrusted"] == ["lines[0]", "lines[1]"]
    assert json.loads(res["content"][0]["text"])["lines"][0] == '<untrusted source="app:uptime-kuma:lines[0]">a</untrusted>'


def test_log_tool_refuses_bad_arguments_and_unknown_apps(c, clock):
    r = rpc(c, "tools/call", {"name": "read_app_logs", "arguments": {"app_id": "uptime-kuma", "tail": 2001}},
            headers=AREA).json()
    assert r["error"]["code"] == -32602
    r = rpc(c, "tools/call", {"name": "read_app_logs", "arguments": {"app_id": "x", "follow": True}},
            headers=AREA).json()
    assert r["error"]["code"] == -32602
    res = call(c, "read_app_logs", {"app_id": "whoami"})
    assert res["isError"] and res["structuredContent"]["error"] == "not_found"


# ---- planted secrets never appear -----------------------------------------------------------------

def _evil_line(i: int) -> str:
    return [
        "login password=" + PLANTED[0],
        "aws " + PLANTED[1],
        "Authorization: Bearer " + PLANTED[2],
        "issued " + PLANTED[3],
        "connect postgres://app:" + PLANTED[4] + "@db:5432/app",
        "-----BEGIN OPENSSH " + "PRIVATE KEY-----",
        PLANTED[5],
        "-----END OPENSSH " + "PRIVATE KEY-----",
        "push " + PLANTED[6],
        "mail " + PLANTED[7] + " from " + PLANTED[8],
        "Authorization: Basic " + PLANTED[9],
    ][i]


def _evil_obj() -> dict:
    return {"note": "Authorization: Bearer " + PLANTED[2], "api_key": PLANTED[0], "password": PLANTED[4],
            "nested": [{"client_secret": PLANTED[3], "url": "https://u:" + PLANTED[4] + "@x/"}],
            "who": PLANTED[7], "addr": PLANTED[8], "aws": PLANTED[1], "gh": PLANTED[6], "private_key": PLANTED[5],
            "session_id": PLANTED[9], "kept": "plain text stays", "count": 3, "has_password": True}


def _assert_clean(res: dict) -> None:
    blob = json.dumps(res)
    for secret in PLANTED:
        assert secret not in blob, (secret, blob[:2000])


def test_planted_secrets_never_appear(c, clock, monkeypatch):
    install(c, clock)
    k = c.app.state.monitoring.kube
    k.pods_by_ns["app-uptime-kuma"] = [pod("web-1")]
    k.log_lines = [_evil_line(i) for i in range(11)]
    res = call(c, "read_app_logs", {"app_id": "uptime-kuma", "tail": 50})
    assert res["isError"] is False and len(res["structuredContent"]["lines"]) == 11
    _assert_clean(res)

    plant_alert(c, clock, title="token " + PLANTED[3], body="password=" + PLANTED[0] + " at " + PLANTED[8])
    for name, args in (("list_alerts", {}), ("get_alert", {"alert_id": "al_0000"})):
        res = call(c, name, args)
        assert res["isError"] is False
        _assert_clean(res)

    # The services behind the other areas answer with secrets planted in every shape.
    state = c.app.state
    monkeypatch.setattr(state.osupdate, "status", lambda: {"nodes": [_evil_obj()], "install": _evil_obj()})
    monkeypatch.setattr(state.osupdate, "history", lambda: {"events": [_evil_obj()], "requests": [_evil_obj()]})
    monkeypatch.setattr(state.update_policy, "to_json", _evil_obj)
    monkeypatch.setattr(state.machines.repo, "all", lambda: [{"name": "vm1", **_evil_obj()}])
    monkeypatch.setattr(state.machines.repo, "get", lambda name: {"name": name, **_evil_obj()})
    monkeypatch.setattr(state.backups, "status", _evil_obj)
    monkeypatch.setattr(state.backups, "runs", lambda: [_evil_obj()])
    monkeypatch.setattr(state.backups, "snapshots", lambda app_id=None, unit=None: [_evil_obj()])
    monkeypatch.setattr(state.storage, "summary", lambda: {"node_id": "n1", "enabled": True, "available": True,
                                                           "error": "Bearer " + PLANTED[2],
                                                           "members": [_evil_obj()]})
    monkeypatch.setattr(state.files_service, "stat", lambda p, root, path: {"name": "x", **_evil_obj()})
    for name, args in (("get_os_updates", {}), ("get_os_update_history", {}), ("get_update_settings", {}),
                       ("list_machines", {}), ("get_machine", {"name": "vm1"}), ("get_backup_status", {}),
                       ("list_backup_runs", {}), ("list_backup_snapshots", {}), ("get_storage", {}),
                       ("stat_file", {"root": "shared", "path": "/a"})):
        res = call(c, name, args)
        assert res["isError"] is False, (name, res)
        _assert_clean(res)
        assert "plain text stays" in json.dumps(res) or name == "get_storage", name


def test_redact_keeps_shape_and_harmless_values():
    out = redact(_evil_obj())
    assert out["api_key"] == out["password"] == out["private_key"] == out["session_id"] == "[redacted]"
    assert out["nested"][0]["client_secret"] == "[redacted]"
    assert out["kept"] == "plain text stays" and out["count"] == 3 and out["has_password"] is True
    assert out["note"] == "Authorization: Bearer [redacted]" and out["who"] == "[email]" and out["addr"] == "[ip]"


# ---- same data as REST, caps and pagination -------------------------------------------------------

def test_area_tools_return_the_rest_body(c, clock, monkeypatch):
    # Rows for the list routes, so the comparison is about real rows, not two empty lists.
    machines = [{"name": "vm1", "state": "running", "cpus": 2}, {"name": "vm2", "state": "stopped", "cpus": 1}]
    monkeypatch.setattr(c.app.state.machines.repo, "all", lambda: machines)
    monkeypatch.setattr(c.app.state.backups, "runs", lambda: [{"id": "r1", "state": "succeeded", "bytes": 10}])
    plant_alert(c, clock, title="disk almost full")
    for name, path in (("get_os_updates", "/v1/os/updates"), ("get_os_update_history", "/v1/os/updates/history"),
                       ("get_update_settings", "/v1/update-policy"), ("get_storage", "/v1/storage"),
                       ("get_backup_status", "/v1/backups/status")):
        res = call(c, name)
        assert res["isError"] is False, (name, res)
        body = c.get(path, headers=AGENT).json()
        assert body and res["structuredContent"] == body, name
    for name, key, path in (("list_machines", "machines", "/v1/machines"), ("list_backup_runs", "runs", "/v1/backups/runs"),
                            ("list_alerts", "alerts", "/v1/alerts")):
        body = c.get(path, headers=AGENT).json()
        assert body and call(c, name)["structuredContent"] == {key: body}, name
    assert call(c, "get_machine", {"name": "vm1"})["isError"] is True  # repo.get is not planted: the real 404


def test_alerts_page_with_cursor_and_limit_and_follow_the_rest_audience(c, clock):
    for n in range(AREA_PAGE_MAX + 20):
        plant_alert(c, clock, n=n, title=f"alert {n}")
    plant_alert(c, clock, n=999, title="adults only", roles=("adult",))
    rest = c.get("/v1/alerts", headers=AGENT).json()
    assert len(rest) == AREA_PAGE_MAX + 20  # the adult-only alert is not the agent's
    first = call(c, "list_alerts", {"limit": 50})["structuredContent"]
    assert len(first["alerts"]) == 50 and first["next_cursor"] == "50"
    assert first["alerts"] == rest[:50]
    last = call(c, "list_alerts", {"cursor": "100", "limit": 50})["structuredContent"]
    assert last["alerts"] == rest[100:] and "next_cursor" not in last
    full = call(c, "list_alerts")["structuredContent"]
    assert len(full["alerts"]) == AREA_PAGE_MAX and full["next_cursor"] == str(AREA_PAGE_MAX)
    res = call(c, "list_alerts", {"limit": 2})
    assert res["_meta"]["onemind/untrusted"] == ["alerts[0].body", "alerts[0].title", "alerts[1].body",
                                                 "alerts[1].title"]
    assert call(c, "get_alert", {"alert_id": "al_0999"})["structuredContent"]["error"] == "not_found"
    r = rpc(c, "tools/call", {"name": "list_alerts", "arguments": {"limit": AREA_PAGE_MAX + 1}}, headers=AREA).json()
    assert r["error"]["code"] == -32602


def test_lists_inside_an_object_are_capped_and_marked_truncated(c, monkeypatch):
    monkeypatch.setattr(c.app.state.osupdate, "history",
                        lambda: {"events": [{"n": i} for i in range(AREA_PAGE_MAX + 5)], "requests": []})
    s = call(c, "get_os_update_history")["structuredContent"]
    assert len(s["events"]) == AREA_PAGE_MAX and s["truncated"] is True


def test_service_refusals_are_tool_errors(c, clock):
    res = call(c, "get_machine", {"name": "nope"})
    assert res["isError"] and res["structuredContent"]["error"] == "not_found"
    res = call(c, "stat_file", {"root": "shared", "path": "/nothing-here"})
    assert res["isError"] and res["structuredContent"]["error"] in ("not_found", "permission_denied", "unavailable")
    r = rpc(c, "tools/call", {"name": "stat_file", "arguments": {"root": "/etc"}}, headers=AREA).json()
    assert r["error"]["code"] == -32602


def test_area_reads_count_against_the_read_limit(settings, clock, executor, tmp_path):
    from onemind_core.mcp import McpSettings

    s = replace(settings, sections={**settings.sections, "mcp": McpSettings(reads_per_minute=2)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        assert call(c, "get_storage", headers=H)["isError"] is False
        assert call(c, "get_update_settings", headers=H)["isError"] is False
        res = call(c, "get_os_updates", headers=H)
        assert res["isError"] and res["structuredContent"]["error"] == "rate_limited"
        clock.advance(61)
        assert call(c, "get_os_updates", headers=H)["isError"] is False
