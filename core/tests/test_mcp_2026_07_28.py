# SPDX-License-Identifier: Apache-2.0
"""MCP revision 2026-07-28 on POST /mcp (DEV-MCP-10, MCP-T13/T14).

Spec: https://modelcontextprotocol.io/specification/2026-07-28/changelog (stateless requests,
server/discover, resultType, ttlMs + cacheScope, header validation, error codes -32020 and -32022)
and the tasks extension io.modelcontextprotocol/tasks (SEP-2663).
"""

import base64
import hashlib

import pytest
import yaml

from conftest import AGENT, OWNER, make_client
from onemind_core.mcp import TOOL_NAMES

V = "2026-07-28"
META = {"io.modelcontextprotocol/protocolVersion": V,
        "io.modelcontextprotocol/clientInfo": {"name": "spec-test", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {}}
TASKS_META = {**META, "io.modelcontextprotocol/clientCapabilities": {"extensions": {"io.modelcontextprotocol/tasks": {}}}}
ACCEPT = {"Accept": "application/json, text/event-stream"}


def mrpc(client, method, params=None, meta=META, headers=None, auth=AGENT, name=None):
    params = dict(params or {})
    params["_meta"] = meta
    h = {**auth, **ACCEPT, "MCP-Protocol-Version": V, "Mcp-Method": method}
    key = {"tools/call": "name", "resources/read": "uri"}.get(method)
    if key:
        h["Mcp-Name"] = name or params[key]
    h.update(headers or {})
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, headers=h)


def test_discover_lists_versions_tasks_and_cache_hints(client):
    r = mrpc(client, "server/discover")
    assert r.status_code == 200 and "mcp-session-id" not in r.headers
    res = r.json()["result"]
    assert res["resultType"] == "complete"
    assert res["supportedVersions"][0] == V and "2025-06-18" in res["supportedVersions"]
    assert res["capabilities"]["extensions"] == {"io.modelcontextprotocol/tasks": {}}
    assert res["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "onemind-gateway"
    assert res["ttlMs"] > 0 and res["cacheScope"] == "private"


def test_no_handshake_calls_work_without_initialize(client):
    res = mrpc(client, "tools/call", {"name": "get_instance", "arguments": {}}).json()["result"]
    assert res["resultType"] == "complete" and res["isError"] is False
    assert res["structuredContent"]["mcp"]["revisions"][-1] == V


def test_initialize_and_ping_are_gone_404(client):
    for m in ("initialize", "ping"):
        r = mrpc(client, m)
        assert r.status_code == 404 and r.json()["error"]["code"] == -32601
        assert V in r.json()["error"]["message"] or m == "ping"


def test_tools_list_deterministic_order_with_cache_hints(client):
    a = mrpc(client, "tools/list").json()["result"]
    b = mrpc(client, "tools/list").json()["result"]
    assert [t["name"] for t in a["tools"]] == TOOL_NAMES == [t["name"] for t in b["tools"]]
    assert a["ttlMs"] > 0 and a["cacheScope"] == "private" and a["resultType"] == "complete"
    for m in ("resources/list", "resources/templates/list"):
        assert mrpc(client, m).json()["result"]["cacheScope"] == "private"


def test_resources_read_not_cached_and_unknown_is_invalid_params(client):
    ok = mrpc(client, "resources/read", {"uri": "onemind://nodes"}).json()["result"]
    assert ok["ttlMs"] == 0 and ok["cacheScope"] == "private"
    bad = mrpc(client, "resources/read", {"uri": "onemind://nope"}).json()
    assert bad["error"]["code"] == -32602  # SEP-2164: was -32002 before 2026-07-28


def test_unsupported_version_header_is_32022_with_supported_list(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
                    headers={**AGENT, **ACCEPT, "MCP-Protocol-Version": "1900-01-01"})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == -32022 and err["data"]["requested"] == "1900-01-01" and V in err["data"]["supported"]


@pytest.mark.parametrize("headers", [
    {"MCP-Protocol-Version": "2025-06-18"},   # body says 2026-07-28, header older: mismatch
    {"Mcp-Method": "tools/list"},             # method header differs from body
    {"Mcp-Name": "list_nodes"},               # name header differs from params.name
])
def test_header_body_mismatch_is_400_32020(client, headers):
    r = mrpc(client, "tools/call", {"name": "get_instance", "arguments": {}}, headers=headers)
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020


def test_missing_method_header_and_missing_meta_version(client):
    h = {**AGENT, **ACCEPT, "MCP-Protocol-Version": V}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}}
    assert client.post("/mcp", json=body, headers=h).json()["error"]["code"] == -32020
    r = mrpc(client, "tools/list", meta={})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020


def test_base64_mcp_name_is_decoded(client):
    enc = "=?base64?" + base64.b64encode(b"get_instance").decode() + "?="
    r = mrpc(client, "tools/call", {"name": "get_instance", "arguments": {}}, name=enc)
    assert r.status_code == 200 and "result" in r.json()


def test_legacy_header_or_none_still_works_and_modern_meta_without_header_is_refused(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={**AGENT, **ACCEPT})
    assert r.json()["result"] == {}  # 2025-06-18 behaviour is unchanged
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": META}},
                    headers={**AGENT, **ACCEPT})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020


def test_people_still_403_and_get_405_under_modern(client):
    assert mrpc(client, "server/discover", auth=OWNER).status_code == 403
    assert client.get("/mcp", headers={**AGENT, "MCP-Protocol-Version": V}).status_code == 405


# ---- tasks extension over the approval wait ------------------------------------------------------
REQ = {"name": "request_action", "arguments": {"type": "app.install", "app_id": "uptime-kuma"}}


def test_without_tasks_capability_request_action_stays_a_fast_call(client):
    res = mrpc(client, "tools/call", REQ).json()["result"]
    assert res["resultType"] == "complete" and res["structuredContent"]["state"] == "awaiting_approval"


def test_request_action_returns_a_task_that_follows_the_owner_decision(client, clock):
    created = mrpc(client, "tools/call", REQ, meta=TASKS_META).json()["result"]
    assert created["resultType"] == "task" and created["status"] == "working"
    assert created["pollIntervalMs"] > 0 and created["ttlMs"] > 0
    tid = created["taskId"]
    got = mrpc(client, "tasks/get", {"taskId": tid}, meta=TASKS_META).json()["result"]
    assert got["resultType"] == "complete" and got["status"] == "working" and "awaiting" not in got.get("status")
    assert "inputRequests" not in got  # approval is out of band, never MRTR
    # tasks/update and tasks/cancel acknowledge but never move the action
    assert mrpc(client, "tasks/update", {"taskId": tid, "inputResponses": {}}, meta=TASKS_META).json()["result"]
    assert mrpc(client, "tasks/cancel", {"taskId": tid}, meta=TASKS_META).json()["result"]["resultType"] == "complete"
    assert client.get(f"/v1/actions/{tid}", headers=OWNER).json()["state"] == "awaiting_approval"
    # the owner decides on the phone or dashboard; the task follows
    assert client.post(f"/v1/actions/{tid}/deny", headers=OWNER).status_code == 200
    done = mrpc(client, "tasks/get", {"taskId": tid}, meta=TASKS_META).json()["result"]
    assert done["status"] == "cancelled"


def test_tasks_of_other_agents_and_unknown_ids_look_missing(client, clock):
    owners = client.post("/v1/actions", json={"type": "app.install", "params": {"app_id": "whoami"},
                         "idempotency_key": "o", "expires_at": "2026-11-12T00:00:00Z"}, headers=OWNER).json()
    for tid in (owners["id"], "nope"):
        r = mrpc(client, "tasks/get", {"taskId": tid}, meta=TASKS_META).json()
        assert r["error"]["code"] == -32602
    assert mrpc(client, "tasks/list").status_code == 404  # removed from the extension


# ---- per-tool authorization ----------------------------------------------------------------------
@pytest.fixture
def scoped(settings, clock, tmp_path):
    tok = "scoped-agent-token-0123456789"
    f = tmp_path / "tokens.yaml"
    f.write_text(yaml.safe_dump({"tokens": {
        "sha256:" + hashlib.sha256(tok.encode()).hexdigest(): {
            "id": "reader", "kind": "agent", "role": "agent",
            "scopes": ["nodes:read", "actions:read:own"]},
        "dev-owner-token-change-me-0123": {"id": "owner", "kind": "person", "role": "owner"},
    }}))
    c = make_client(settings, clock, tokens_file=f)
    return c, {"Authorization": f"Bearer {tok}"}


def test_scopes_filter_tools_list_and_resources(scoped):
    c, auth = scoped
    names = [t["name"] for t in mrpc(c, "tools/list", auth=auth).json()["result"]["tools"]]
    assert names == ["get_instance", "list_nodes", "get_node", "list_actions", "get_action"]  # instance:read is always granted
    uris = [r["uri"] for r in mrpc(c, "resources/list", auth=auth).json()["result"]["resources"]]
    assert uris == ["onemind://nodes"]


def test_call_without_scope_is_a_denied_tool_error_and_audited(scoped, settings):
    c, auth = scoped
    res = mrpc(c, "tools/call", REQ, auth=auth, meta=TASKS_META).json()["result"]
    assert res["isError"] and res["structuredContent"]["error"] == "permission_denied"
    assert res["structuredContent"]["scope"] == "actions:request:app.install"
    assert '"authz.denied"' in settings.audit_path.read_text()
    assert mrpc(c, "tools/call", {"name": "list_nodes", "arguments": {}}, auth=auth).json()["result"]["isError"] is False
    r = mrpc(c, "resources/read", {"uri": "onemind://catalog"}, auth=auth).json()
    assert r["error"]["code"] == -32602


def test_legacy_revision_enforces_the_same_scopes(scoped):
    c, auth = scoped
    h = {**auth, **ACCEPT, "MCP-Protocol-Version": "2025-06-18"}
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "request_action", "arguments": REQ["arguments"]}}
    assert c.post("/mcp", json=msg, headers=h).json()["result"]["structuredContent"]["error"] == "permission_denied"


def test_unknown_scope_in_tokens_file_is_refused():
    from onemind_core.auth import parse_tokens

    with pytest.raises(ValueError, match="unknown scopes"):
        parse_tokens({"tokens": {"x" * 20: {"id": "a", "kind": "agent", "role": "agent", "scopes": ["approve"]}}})
    with pytest.raises(ValueError, match="agents only"):
        parse_tokens({"tokens": {"x" * 20: {"id": "o", "kind": "person", "role": "owner", "scopes": []}}})


def test_plan_bundles_and_the_old_field_name():
    from onemind_core.auth import parse_tokens

    def tok(**kw):
        doc = {"tokens": {"x" * 20: {"id": "a", "kind": "agent", "role": "agent", **kw}}}
        return next(iter(parse_tokens(doc).values()))

    reader = tok(scopes=["reader"])
    assert "actions:request:app.install" not in reader.scopes and "instance:read" in reader.scopes
    assert "actions:request:app.remove" in tok(scopes=["requester"]).scopes
    assert tok(scopes=["actions:request:app.remove"]).scopes >= {"instance:read", "actions:request:app.remove"}
    with pytest.raises(ValueError, match="not `mcp_scopes`"):
        tok(mcp_scopes=["reader"])


def test_request_scope_is_per_action_type(settings, clock, tmp_path):
    tok = "remove-only-agent-token-0123456789"
    f = tmp_path / "tokens.yaml"
    f.write_text(yaml.safe_dump({"tokens": {tok: {"id": "r", "kind": "agent", "role": "agent",
                                                  "scopes": ["actions:request:app.remove"]}}}))
    c = make_client(settings, clock, tokens_file=f)
    auth = {"Authorization": f"Bearer {tok}"}
    names = [t["name"] for t in mrpc(c, "tools/list", auth=auth).json()["result"]["tools"]]
    assert "request_action" in names
    res = mrpc(c, "tools/call", REQ, auth=auth).json()["result"]  # app.install
    assert res["structuredContent"]["error"] == "permission_denied"
