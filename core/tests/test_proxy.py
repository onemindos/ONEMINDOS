# SPDX-License-Identifier: Apache-2.0
"""proxy.py against a real fake upstream (uvicorn on loopback): routing, sign-in, header hygiene,
streaming, limits, timeouts and WebSockets."""

from __future__ import annotations

import asyncio
import json
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from onemind_core.auth import TokenStore
from onemind_core.catalog import Catalog
from onemind_core.proxy import (
    AppProxy, AppProxyMiddleware, KubectlServiceResolver, Timeouts, token_session_resolver,
)

# ---- fake upstream ----------------------------------------------------------------------------------


async def echo(request: Request):
    body = await request.body()
    return JSONResponse({
        "method": request.method, "path": request.url.path, "query": request.url.query,
        "headers": {k: v for k, v in request.headers.items()}, "body": body.decode(),
    })


async def stream(_: Request):
    async def gen():
        for i in range(3):
            yield f"chunk{i}\n".encode()
            await asyncio.sleep(0.01)
    return StreamingResponse(gen(), media_type="text/plain")


async def slow(_: Request):
    await asyncio.sleep(2)
    return JSONResponse({"late": True})


async def ws_echo(ws: WebSocket):
    await ws.accept(subprotocol="chat" if "chat" in ws.scope.get("subprotocols", []) else None)
    await ws.send_json({"principal": ws.headers.get("x-onemind-principal"),
                        "authorization": ws.headers.get("authorization"), "path": ws.url.path})
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("text") is not None:
                await ws.send_text("echo:" + msg["text"])
            else:
                await ws.send_bytes(b"echo:" + msg["bytes"])
    except WebSocketDisconnect:
        return


UPSTREAM = Starlette(routes=[
    Route("/stream", stream), Route("/slow", slow), WebSocketRoute("/ws", ws_echo),
    Route("/{path:path}", echo, methods=["GET", "POST", "PUT", "DELETE", "HEAD"]),
])


@pytest.fixture(scope="module")
def upstream_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(UPSTREAM, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started
    yield port
    server.should_exit = True
    thread.join(5)


def closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---- gateway with the proxy in front ------------------------------------------------------------------
def manifest(app_id: str, port: int | None, access: str | None = None) -> dict:
    spec = {"archs": ["arm64"], "manifests": "manifests/"}
    if port is not None:
        spec["web"] = {"port": port, **({"access": access} if access else {})}
    return {"apiVersion": "onemind.app/v1alpha1", "kind": "App",
            "metadata": {"id": app_id, "name": app_id, "version": "1.0.0"}, "spec": spec}


@pytest.fixture
def env(tmp_path: Path, upstream_port):
    toks = {role: secrets.token_urlsafe(24) for role in ("owner", "adult", "guest", "agent")}
    (tmp_path / "tokens.yaml").write_text(yaml.safe_dump({"tokens": {
        toks["owner"]: {"id": "owner", "kind": "person", "role": "owner"},
        toks["adult"]: {"id": "ab12", "kind": "person", "role": "adult"},
        toks["guest"]: {"id": "g1", "kind": "person", "role": "guest"},
        toks["agent"]: {"id": "hermes", "kind": "agent", "role": "agent"},
    }}))
    apps = tmp_path / "apps"
    down = closed_port()
    for app_id, port, access in [("kuma", upstream_port, None), ("private", upstream_port, "owner"),
                                 ("open", upstream_port, "signed_in"), ("noweb", None, None),
                                 ("notinst", upstream_port, None), ("down", down, None)]:
        (apps / app_id).mkdir(parents=True)
        (apps / app_id / "onemind.app.yaml").write_text(yaml.safe_dump(manifest(app_id, port, access)))
    status = {"kuma": "installed", "private": "installed", "open": "installed", "noweb": "installed",
              "down": "installed", "notinst": "failed"}
    resolved: list[tuple[str, int]] = []

    def resolver(ns, port):
        resolved.append((ns, port))
        return "127.0.0.1"

    audit_lines: list[tuple] = []
    proxy = AppProxy(
        Catalog(apps), status.get, token_session_resolver(TokenStore(tmp_path / "tokens.yaml")), resolver,
        box_domains=("onemind.local", "box1.local", "apps.onemind.internal"),
        timeouts=Timeouts(connect=1, read=0.5, ws_open=2), max_body=1024, route_ttl=0,
        audit=lambda *a: audit_lines.append(a),
    )
    gw = FastAPI()

    @gw.get("/{rest:path}")
    def gateway(rest: str):
        return {"gateway": rest}

    gw.add_middleware(AppProxyMiddleware, proxy=proxy)
    return {"app": gw, "tokens": toks, "status": status, "resolved": resolved, "audit": audit_lines}


def client(env, host="kuma.onemind.local"):
    return TestClient(env["app"], base_url=f"http://{host}")


def bearer(env, role):
    return {"Authorization": f"Bearer {env['tokens'][role]}"}


# ---- HTTP ---------------------------------------------------------------------------------------------
def test_host_route_forwards_and_scrubs(env):
    c = client(env)
    r = c.get("/some/page?q=1", headers={**bearer(env, "owner"), "X-OneMind-Principal": "person:evil",
                                        "X-OneMind-Role": "owner", "Cookie": f"onemind_session=x; theme=dark"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["path"] == "/some/page" and got["query"] == "q=1"
    h = got["headers"]
    assert "authorization" not in h
    assert h["x-onemind-principal"] == "person:owner" and h["x-onemind-role"] == "owner"
    assert h["cookie"] == "theme=dark"
    assert h["x-forwarded-host"] == "kuma.onemind.local"
    assert env["resolved"][-1][0] == "app-kuma"


def test_path_route_fallback(env):
    c = client(env, host="onemind.local")
    r = c.get("/apps/kuma/x/y", headers=bearer(env, "adult"))
    assert r.status_code == 200
    assert r.json()["path"] == "/x/y" and r.json()["headers"]["x-forwarded-prefix"] == "/apps/kuma"
    r = c.get("/apps/kuma", headers=bearer(env, "adult"), follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/apps/kuma/"
    # the gateway still answers everything else
    assert c.get("/v1/instance").json() == {"gateway": "v1/instance"}


def test_other_box_domains(env):
    for host in ("kuma.box1.local", "kuma.apps.onemind.internal"):
        assert client(env, host).get("/", headers=bearer(env, "owner")).status_code == 200


def test_session_cookie_signs_in(env):
    c = client(env)
    c.cookies.set("onemind_session", env["tokens"]["adult"])
    r = c.get("/")
    assert r.status_code == 200 and "onemind_session" not in r.json()["headers"].get("cookie", "")


@pytest.mark.parametrize("app,role,status", [
    ("kuma", None, 401), ("kuma", "guest", 403), ("kuma", "agent", 403), ("kuma", "adult", 200),
    ("private", "adult", 403), ("private", "owner", 200), ("open", "guest", 200),
])
def test_access_levels(env, app, role, status):
    r = client(env, f"{app}.onemind.local").get("/", headers=bearer(env, role) if role else {})
    assert r.status_code == status
    if status == 401:
        assert r.headers["www-authenticate"] == "Bearer"
    if status == 403 and role == "guest":
        assert env["audit"][-1][0] == "proxy.denied"


@pytest.mark.parametrize("host,path", [
    ("noweb.onemind.local", "/"), ("notinst.onemind.local", "/"), ("nosuch.onemind.local", "/"),
    ("UPPER_case.onemind.local", "/"), ("onemind.local", "/apps/nosuch/"), ("onemind.local", "/apps/Kuma/"),
])
def test_unknown_or_uninstalled_is_404(env, host, path):
    assert client(env, host).get(path, headers=bearer(env, "owner")).status_code == 404


def test_no_open_proxy(env):
    before = len(env["resolved"])
    # nested labels and foreign hosts go to the gateway, never upstream
    for host in ("a.kuma.onemind.local", "example.com", "kuma.onemind.local.example.com"):
        r = client(env, host).get("/x", headers=bearer(env, "owner"))
        assert r.json() == {"gateway": "x"}
    # an absolute-form target cannot pick the upstream either
    r = client(env).get("http://kuma.onemind.local/abs", headers={**bearer(env, "owner"), "Host": "kuma.onemind.local"})
    assert r.json()["path"] == "/abs"
    assert all(ns == "app-kuma" for ns, _ in env["resolved"][before:])


def test_uninstall_takes_effect(env):
    c = client(env)
    assert c.get("/", headers=bearer(env, "owner")).status_code == 200
    env["status"]["kuma"] = "removing"
    assert c.get("/", headers=bearer(env, "owner")).status_code == 404


def test_post_body_and_limit(env):
    c = client(env)
    r = c.post("/form", content=b"a=1&b=2", headers=bearer(env, "owner"))
    assert r.json()["body"] == "a=1&b=2" and r.json()["method"] == "POST"
    assert c.post("/form", content=b"x" * 2048, headers=bearer(env, "owner")).status_code == 413


def test_streaming_response(env):
    r = client(env).get("/stream", headers=bearer(env, "owner"))
    assert r.status_code == 200 and r.text == "chunk0\nchunk1\nchunk2\n"


def test_timeout_and_down(env):
    assert client(env).get("/slow", headers=bearer(env, "owner")).status_code == 504
    assert client(env, "down.onemind.local").get("/", headers=bearer(env, "owner")).status_code == 502


# ---- WebSocket --------------------------------------------------------------------------------------
def ws_headers(host="kuma.onemind.local", **extra):
    # TestClient always sends Host: testserver on WebSockets, and no cookie jar; set both here.
    return {"host": host, **extra}


def test_websocket_proxied(env):
    c = client(env)
    headers = ws_headers(Origin="http://kuma.onemind.local", Cookie=f"onemind_session={env['tokens']['owner']}")
    with c.websocket_connect("/ws", subprotocols=["chat"], headers=headers) as ws:
        hello = ws.receive_json()
        assert hello == {"principal": "person:owner", "authorization": None, "path": "/ws"}
        assert ws.accepted_subprotocol == "chat"
        ws.send_text("hi")
        assert ws.receive_text() == "echo:hi"
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_bytes() == b"echo:\x00\x01"


def test_websocket_path_mode(env):
    c = client(env, "onemind.local")
    with c.websocket_connect("/apps/kuma/ws", headers=ws_headers("onemind.local", **bearer(env, "adult"))) as ws:
        assert ws.receive_json()["path"] == "/ws"


@pytest.mark.parametrize("headers", [
    {},  # not signed in
    {"Origin": "http://evil.example"},  # cross-site
])
def test_websocket_refused(env, headers):
    c = client(env)
    if headers:
        headers = {**headers, "Cookie": f"onemind_session={env['tokens']['owner']}"}
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/ws", headers=ws_headers(**headers)) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


# ---- Service resolver ---------------------------------------------------------------------------------
def test_kubectl_resolver_picks_clusterip_with_port():
    services = {"items": [
        {"metadata": {"name": "a-headless"}, "spec": {"clusterIP": "None", "ports": [{"port": 3001}]}},
        {"metadata": {"name": "b-nodeport"}, "spec": {"type": "NodePort", "clusterIP": "198.51.100.9", "ports": [{"port": 3001}]}},
        {"metadata": {"name": "c-other"}, "spec": {"clusterIP": "198.51.100.8", "ports": [{"port": 80}]}},
        {"metadata": {"name": "d-web"}, "spec": {"clusterIP": "198.51.100.7", "ports": [{"port": 3001, "protocol": "TCP"}]}},
    ]}
    calls = []

    def runner(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(services).encode(), b"")

    r = KubectlServiceResolver("kubectl", runner=runner, ttl=60)
    assert r("app-kuma", 3001) == "198.51.100.7"
    assert r("app-kuma", 3001) == "198.51.100.7" and len(calls) == 1  # cached
    assert calls[0] == ["kubectl", "get", "services", "-n", "app-kuma", "-o", "json"]
    assert r("app-kuma", 9999) is None

    def failing(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, b"", b"forbidden")

    assert KubectlServiceResolver(runner=failing)("app-x", 80) is None
