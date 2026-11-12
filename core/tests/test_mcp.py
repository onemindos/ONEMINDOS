# SPDX-License-Identifier: Apache-2.0
"""Contract §11.3: POST /mcp, MCP Streamable HTTP (2025-06-18), agent principals only."""

import asyncio
import json
import socket
import threading
import time
from datetime import timedelta

import pytest

from conftest import ADULT, AGENT, OWNER, action_body
from onemind_core.mcp import PROTOCOL_VERSION

H = {**AGENT, "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL_VERSION}


def rpc(client, method, params=None, id_=1, headers=H):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return client.post("/mcp", json=msg, headers=headers)


def call(client, name, arguments=None):
    r = rpc(client, "tools/call", {"name": name, "arguments": arguments or {}})
    assert r.status_code == 200, r.text
    return r.json()


def test_initialize(client):
    r = rpc(client, "initialize", {
        "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    }, headers={k: v for k, v in H.items() if k != "MCP-Protocol-Version"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["jsonrpc"] == "2.0" and body["id"] == 1
    res = body["result"]
    assert res["protocolVersion"] == "2025-06-18"
    assert res["capabilities"] == {"tools": {"listChanged": False}}
    assert res["serverInfo"]["name"] == "onemind-gateway"
    assert "mcp-session-id" not in r.headers


def test_initialize_with_unknown_version_gets_ours(client):
    res = rpc(client, "initialize", {"protocolVersion": "1999-01-01"}).json()["result"]
    assert res["protocolVersion"] == PROTOCOL_VERSION


def test_initialized_notification_is_202(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=H)
    assert r.status_code == 202 and r.content == b""


def test_ping(client):
    assert rpc(client, "ping").json() == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_tools_list_is_exactly_the_contract_set(client):
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["list_nodes", "list_apps", "request_action"]
    for t in tools:
        assert t["inputSchema"]["type"] == "object"
    names = json.dumps(tools)
    assert "approve" not in [t["name"] for t in tools] and "deny" not in names.replace("denied", "")
    req = next(t for t in tools if t["name"] == "request_action")
    assert req["inputSchema"]["required"] == ["type", "app_id"]
    assert set(req["inputSchema"]["properties"]) == {"type", "app_id", "reason"}


def test_list_nodes_and_apps_match_rest(client):
    nodes = call(client, "list_nodes")["result"]
    assert nodes["isError"] is False
    assert nodes["structuredContent"] == {"nodes": client.get("/v1/nodes", headers=OWNER).json()}
    apps = call(client, "list_apps")["result"]
    assert apps["structuredContent"] == {"apps": client.get("/v1/apps", headers=OWNER).json()}
    assert json.loads(apps["content"][0]["text"]) == apps["structuredContent"]


def test_request_action_creates_an_awaiting_action(client, clock, settings, executor):
    res = call(client, "request_action", {"type": "app.install", "app_id": "uptime-kuma", "reason": "user asked"})
    out = res["result"]["structuredContent"]
    assert res["result"]["isError"] is False
    assert out["state"] == "awaiting_approval"
    a = client.get(f"/v1/actions/{out['action_id']}", headers=OWNER).json()
    assert a["type"] == "app.install" and a["params"] == {"app_id": "uptime-kuma"}
    assert a["requested_by"] == {"id": "hermes", "kind": "agent"}
    assert a["idempotency_key"].startswith("mcp-")
    assert a["expires_at"] == (clock.now + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    requested = [json.loads(x) for x in settings.audit_path.read_text().splitlines()
                 if '"action.requested"' in x][-1]
    assert requested["data"]["reason"] == "user asked"
    assert executor.calls == []  # nothing ran; the owner still has to approve
    # each call is a new request (generated idempotency key)
    again = call(client, "request_action", {"type": "app.install", "app_id": "whoami"})
    assert again["result"]["structuredContent"]["action_id"] != out["action_id"]


def test_request_action_refusals_are_tool_errors(client):
    res = call(client, "request_action", {"type": "app.install", "app_id": "no-such-app"})["result"]
    assert res["isError"] is True
    assert res["structuredContent"]["error"] == "not_found"


@pytest.mark.parametrize(
    "args",
    [
        {"type": "app.approve", "app_id": "uptime-kuma"},
        {"type": "app.install"},
        {"type": "app.install", "app_id": "../etc"},
        {"type": "app.install", "app_id": "uptime-kuma", "expires_at": "x"},
        {"type": "app.install", "app_id": "uptime-kuma", "reason": "x" * 501},
    ],
)
def test_request_action_bad_arguments(client, args):
    body = call(client, "request_action", args)
    assert body["error"]["code"] == -32602


def test_unknown_tool_and_method(client):
    assert call(client, "approve_action", {"action_id": "x"})["error"]["code"] == -32602
    assert rpc(client, "resources/list").json()["error"]["code"] == -32601


def test_agent_cannot_approve_through_rest_either(client, clock):
    out = call(client, "request_action", {"type": "app.install", "app_id": "uptime-kuma"})["result"]
    r = client.post(f"/v1/actions/{out['structuredContent']['action_id']}/approve", headers=AGENT)
    assert r.status_code == 403


@pytest.mark.parametrize("headers", [OWNER, ADULT])
def test_people_get_403(client, headers):
    r = rpc(client, "ping", headers=headers)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-real-token-at-all"}])
def test_missing_or_unknown_token_401(client, headers):
    r = rpc(client, "ping", headers=headers)
    assert r.status_code == 401 and r.json()["error"] == "unauthenticated"


def test_transport_edges(client):
    assert client.get("/mcp", headers=H).status_code == 405
    assert client.delete("/mcp", headers=H).status_code == 405
    assert client.get("/mcp").status_code == 401
    r = client.post("/mcp", content=b"{nope", headers={**H, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    r = client.post("/mcp", json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}], headers=H)
    assert r.status_code == 400 and r.json()["error"]["code"] == -32600
    r = rpc(client, "ping", headers={**H, "MCP-Protocol-Version": "2024-01-01"})
    assert r.status_code == 400
    r = rpc(client, "ping", headers={**H, "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "result": {}}, headers=H)
    assert r.status_code == 202


def test_oversized_body_is_413_even_when_chunked(client):
    from onemind_core.mcp import MAX_BODY

    big = b'{"jsonrpc": "2.0", "id": 1, "method": "ping", "pad": "' + b"x" * MAX_BODY + b'"}'
    hdrs = {**H, "Content-Type": "application/json"}
    assert client.post("/mcp", content=big, headers=hdrs).status_code == 413

    def chunks():  # no Content-Length: the cap must hold while streaming
        for i in range(0, len(big), 4096):
            yield big[i:i + 4096]

    assert client.post("/mcp", content=chunks(), headers=hdrs).status_code == 413


def test_spa_fallback_never_answers_mcp(client):
    assert client.get("/mcp/x", headers=OWNER).status_code == 200  # SPA route, not the API
    assert client.get("/mcp", headers=OWNER).status_code == 405


# ---- the official MCP Python SDK as a real client ------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_gateway(settings, clock, executor):
    import uvicorn

    from onemind_core.app import create_app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        create_app(settings, clock=clock, executor=executor), host="127.0.0.1", port=port, log_level="warning",
    ))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


def test_official_mcp_client(live_gateway, executor):
    pytest.importorskip("mcp")
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def scenario():
        headers = {"Authorization": AGENT["Authorization"]}
        async with streamablehttp_client(f"{live_gateway}/mcp", headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.protocolVersion == PROTOCOL_VERSION
                await session.send_ping()
                tools = await session.list_tools()
                assert [t.name for t in tools.tools] == ["list_nodes", "list_apps", "request_action"]
                apps = await session.call_tool("list_apps", {})
                assert not apps.isError
                assert "uptime-kuma" in {a["id"] for a in apps.structuredContent["apps"]}
                res = await session.call_tool("request_action", {"type": "app.install", "app_id": "uptime-kuma"})
                assert not res.isError
                assert res.structuredContent["state"] == "awaiting_approval"
                bad = await session.call_tool("request_action", {"type": "app.install", "app_id": "no-such-app"})
                assert bad.isError
                return res.structuredContent["action_id"]

    action_id = asyncio.run(scenario())
    assert action_id
    assert executor.calls == []


def test_official_mcp_client_rejected_for_owner(live_gateway):
    pytest.importorskip("mcp")
    import httpx

    r = httpx.post(f"{live_gateway}/mcp", headers={**OWNER, "Accept": "application/json, text/event-stream"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 403

