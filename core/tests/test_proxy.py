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

from conftest import OWNER, make_client
from onemind_core.app import create_app
from onemind_core.auth import Principal, TokenStore
from onemind_core.ca import MESH_NETS
from onemind_core.catalog import Catalog
from onemind_core.proxy import (
    AppProxy, AppProxyMiddleware, AppRoute, KubectlServiceResolver, Timeouts, gateway_session_resolver, sharing_check,
    token_session_resolver,
)
from test_identity import LOCAL_PEER, PASSWORD, id_settings, setup_owner

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


async def set_cookies(_: Request):
    r = JSONResponse({"ok": True})
    r.set_cookie("onemind_session", "planted", domain="onemind.local")
    r.set_cookie("theme", "dark")
    r.set_cookie("__Host-onemind_session", "planted", path="/", secure=True)
    r.set_cookie("__Host-onemind_csrf", "planted", path="/", secure=True)
    r.set_cookie("onemind_csrf", "planted")
    return r


UPSTREAM = Starlette(routes=[
    Route("/set-cookies", set_cookies), Route("/stream", stream), Route("/slow", slow), WebSocketRoute("/ws", ws_echo),
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
              "down": "installed", "notinst": "removed"}
    resolved: list[tuple[str, int]] = []

    def resolver(ns, port):
        resolved.append((ns, port))
        return "127.0.0.1"

    audit_lines: list[tuple] = []
    proxy = AppProxy(
        Catalog(apps), status.get, token_session_resolver(TokenStore(tmp_path / "tokens.yaml")), resolver,
        box_domains=("onemind.local", "box1.local", "apps.onemind.internal"),
        timeouts=Timeouts(connect=1, read=0.5, ws_open=2), max_body=1024, route_ttl=0,
        audit=lambda *a: audit_lines.append(a), path_routes=True,
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


def test_path_routes_off_by_default(env):
    proxy = env["app"].user_middleware[0].kwargs["proxy"]
    default = AppProxy(proxy.catalog, proxy.app_status, proxy.resolve_session, proxy.resolve_service,
                       box_domains=("onemind.local",))
    gw = FastAPI()

    @gw.get("/{rest:path}")
    def gateway(rest: str):
        return {"gateway": rest}

    gw.add_middleware(AppProxyMiddleware, proxy=default)
    c = TestClient(gw, base_url="http://onemind.local")
    # same origin as the dashboard: not proxied unless path_routes=True
    assert c.get("/apps/kuma/x", headers=bearer(env, "owner")).json() == {"gateway": "apps/kuma/x"}
    assert TestClient(gw, base_url="http://kuma.onemind.local").get(
        "/x", headers=bearer(env, "owner")).json()["path"] == "/x"


def test_raw_path_not_matching_prefix(env):
    # %61 decodes to "a": the route matches /apps/kuma, and the upstream still gets the right remainder
    r = client(env, host="onemind.local").get("/apps/kum%61/x/y", headers=bearer(env, "adult"))
    assert r.status_code == 200 and r.json()["path"] == "/x/y"


def test_app_cannot_set_session_cookie(env):
    r = client(env).get("/set-cookies", headers=bearer(env, "owner"))
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    assert any(c.startswith("theme=") for c in cookies)
    assert not any("onemind_" in c.lower() for c in cookies)


def test_identity_cookies_never_reach_the_app(env):
    """H-34: identity's __Host- cookies and every onemind_* cookie are stripped; others pass through."""
    r = client(env).get("/x", headers={**bearer(env, "owner"), "Cookie": (
        "__Host-onemind_session=a; __Host-onemind_csrf=b; onemind_session=c; onemind_csrf=d; "
        "__host-ONEMIND_x=e; keep=1; onemindful=2")})
    assert r.status_code == 200, r.text
    assert r.json()["headers"]["cookie"] == "keep=1; onemindful=2"
    r = client(env).get("/x", headers={**bearer(env, "owner"), "Cookie": "__Host-onemind_session=a"})
    assert "cookie" not in r.json()["headers"]


def test_cross_origin_unsafe_method_refused(env):
    c = client(env)
    c.cookies.set("onemind_session", env["tokens"]["owner"])
    # another app (same site, different origin) posting as the person
    assert c.post("/form", content=b"a=1", headers={"Origin": "http://evil.onemind.local"}).status_code == 403
    assert c.post("/form", content=b"a=1", headers={"Origin": "null"}).status_code == 403
    assert env["audit"][-1][0] == "proxy.denied"
    # same origin and non-browser clients (no Origin) still work; safe methods are not checked
    assert c.post("/form", content=b"a=1", headers={"Origin": "http://kuma.onemind.local"}).status_code == 200
    assert c.post("/form", content=b"a=1").status_code == 200
    assert c.get("/x", headers={"Origin": "http://evil.onemind.local"}).status_code == 200


def test_unauthenticated_cannot_list_apps(env):
    for host in ("kuma.onemind.local", "nosuch.onemind.local", "notinst.onemind.local"):
        assert client(env, host).get("/").status_code == 401


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
    assert c.get("/", headers=bearer(env, "owner")).status_code == 503
    env["status"]["kuma"] = "removed"
    assert c.get("/", headers=bearer(env, "owner")).status_code == 404


def test_post_body_and_limit(env):
    c = client(env)
    r = c.post("/form", content=b"a=1&b=2", headers=bearer(env, "owner"))
    assert r.json()["body"] == "a=1&b=2" and r.json()["method"] == "POST"
    assert c.post("/form", content=b"x" * 2048, headers=bearer(env, "owner")).status_code == 413


def test_proxy_body_cap_holds_for_chunked_bodies(env):
    """proxy.py reads the request itself (its own receive loop): the cap holds with no Content-Length."""
    c = client(env)

    def chunks(n):
        for _ in range(0, n, 256):
            yield b"x" * 256

    assert c.post("/form", content=chunks(1024), headers=bearer(env, "owner")).json()["body"] == "x" * 1024
    assert c.post("/form", content=chunks(1280), headers=bearer(env, "owner")).status_code == 413


def test_streaming_response(env):
    r = client(env).get("/stream", headers=bearer(env, "owner"))
    assert r.status_code == 200 and r.text == "chunk0\nchunk1\nchunk2\n"


def test_timeout_and_down(env):
    assert client(env).get("/slow", headers=bearer(env, "owner")).status_code == 504
    r = client(env, "down.onemind.local").get("/", headers=bearer(env, "owner"))
    assert r.status_code == 502 and r.text == "down is installed but not answering. It may still be starting."
    assert r.headers["retry-after"] == "5"


# ---- honest pages for an app that is not running (UMB-P02) ---------------------------------------------
@pytest.mark.parametrize("status,said,changing", [
    ("stopped", "kuma is stopped. Start it from the OneMind dashboard.", False),
    ("starting", "kuma is starting.", True),
    ("installing", "kuma is being installed.", True),
    ("updating", "kuma is being updated.", True),
    ("failed", "kuma is not running: its last change failed. The OneMind dashboard shows why.", False),
])
def test_not_running_app_says_so(env, status, said, changing):
    env["status"]["kuma"] = status
    r = client(env).get("/", headers=bearer(env, "adult"))
    assert r.status_code == 503 and r.text == said
    assert r.headers["content-type"].startswith("text/plain")
    assert ("retry-after" in r.headers) is changing


def test_not_running_page_for_a_browser(env):
    env["status"]["kuma"] = "starting"
    r = client(env).get("/", headers={**bearer(env, "owner"), "Accept": "text/html,*/*;q=0.8"})
    assert r.status_code == 503 and r.headers["content-type"].startswith("text/html")
    assert "<p>kuma is starting.</p>" in r.text and 'http-equiv="refresh" content="5"' in r.text
    assert r.headers["content-security-policy"] == "default-src 'none'; style-src 'unsafe-inline'"
    assert "<script" not in r.text
    env["status"]["kuma"] = "stopped"
    r = client(env).get("/", headers={**bearer(env, "owner"), "Accept": "text/html"})
    assert "refresh" not in r.text and "retry-after" not in r.headers


def test_not_running_tells_only_who_could_open_it(env):
    env["status"]["private"] = "stopped"  # access: owner
    assert client(env, "private.onemind.local").get("/", headers=bearer(env, "owner")).status_code == 503
    assert client(env, "private.onemind.local").get("/", headers=bearer(env, "adult")).status_code == 404
    # signed out: 401 whatever the state, so nobody can list apps or their states
    assert client(env, "private.onemind.local").get("/").status_code == 401
    # agents never open apps, running or not
    assert client(env, "private.onemind.local").get("/", headers=bearer(env, "agent")).status_code == 404


def test_not_running_respects_mesh_exposure(env):
    proxy = env["app"].user_middleware[0].kwargs["proxy"]
    proxy.exposure = lambda app_id: "private"
    env["status"]["kuma"] = "stopped"
    assert client(env, "kuma.apps.onemind.internal").get("/", headers=bearer(env, "owner")).status_code == 404
    assert client(env, "kuma.onemind.local").get("/", headers=bearer(env, "owner")).status_code == 503


def test_forward_auth_decision_unchanged_for_a_stopped_app(env):
    """decide() keeps 204/401/403/404: /v1/auth/forward maps exactly those."""
    proxy = env["app"].user_middleware[0].kwargs["proxy"]
    env["status"]["kuma"] = "stopped"
    status, _, _ = proxy.decide({"host": "kuma.onemind.local", "authorization": bearer(env, "owner")["Authorization"]}, "kuma")
    assert status == 404


def test_page_escapes_the_app_name(env, tmp_path):
    proxy = env["app"].user_middleware[0].kwargs["proxy"]
    m = manifest("kuma", 1)
    m["metadata"]["name"] = "<img src=x onerror=alert(1)>"
    (tmp_path / "apps" / "kuma" / "onemind.app.yaml").write_text(yaml.safe_dump(m))
    proxy.catalog = Catalog(tmp_path / "apps")
    env["status"]["kuma"] = "stopped"
    r = client(env).get("/", headers={**bearer(env, "owner"), "Accept": "text/html"})
    assert "<img" not in r.text and "&lt;img src=x onerror=alert(1)&gt; is stopped." in r.text


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


# ---- an app's own Authorization header (#824) ----------------------------------------------------------
# An app such as Fleetbase sends its own bearer token. Behind a valid OneMind session cookie that header
# belongs to the app: it goes to that app's upstream only, and it never signs anyone in to OneMind.
APP_TOKEN = "Bearer fleetbase-own-token-1"


def signed_in(env, role="owner", host="kuma.onemind.local"):
    c = client(env, host)
    c.cookies.set("onemind_session", env["tokens"][role])
    return c


def test_app_authorization_reaches_that_app_behind_a_session(env):
    r = signed_in(env).get("/api/v1/me", headers={"Authorization": APP_TOKEN})
    assert r.status_code == 200, r.text
    h = r.json()["headers"]
    assert h["authorization"] == APP_TOKEN
    assert h["x-onemind-principal"] == "person:owner" and "cookie" not in h
    assert env["resolved"][-1][0] == "app-kuma"  # the app the name points at, nothing else
    r = signed_in(env, host="open.onemind.local").get("/", headers={"Authorization": "Basic YTpi"})
    assert r.json()["headers"]["authorization"] == "Basic YTpi" and env["resolved"][-1][0] == "app-open"
    r = signed_in(env, host="onemind.local").get("/apps/kuma/x", headers={"Authorization": APP_TOKEN})
    assert r.status_code == 200 and r.json()["headers"]["authorization"] == APP_TOKEN


def test_app_token_without_a_session_is_refused(env):
    for host in ("kuma.onemind.local", "nosuch.onemind.local"):
        assert client(env, host).get("/", headers={"Authorization": APP_TOKEN}).status_code == 401
    c = client(env)
    c.cookies.set("onemind_session", "not-a-session")
    assert c.get("/", headers={"Authorization": APP_TOKEN}).status_code == 401
    proxy = env["app"].user_middleware[0].kwargs["proxy"]
    assert proxy.decide({"host": "kuma.onemind.local", "authorization": APP_TOKEN}, "kuma")[0] == 401


def test_session_cookie_decides_who_you_are(env):
    """The cookie is the OneMind identity; a bearer next to it cannot change who the person is."""
    proxy = env["app"].user_middleware[0].kwargs["proxy"]
    cookie = f"onemind_session={env['tokens']['guest']}"
    owner = bearer(env, "owner")["Authorization"]
    assert signed_in(env, "guest", "private.onemind.local").get("/", headers={"Authorization": owner}).status_code == 403
    assert proxy.decide({"host": "kuma.onemind.local", "cookie": cookie, "authorization": APP_TOKEN}, "open")[0] == 204
    # the forward-auth decision (/v1/auth/forward) takes the same cookie-first view
    assert proxy.decide({"host": "kuma.onemind.local", "cookie": cookie, "authorization": APP_TOKEN}, "kuma")[0] == 403


@pytest.mark.parametrize("token", ["adult", "agent", "om_ses_revoked-or-unknown", "om_pat_whatever"])
def test_onemind_token_never_forwarded_to_an_app(env, token):
    value = bearer(env, token)["Authorization"] if token in env["tokens"] else f"Bearer {token}"
    r = signed_in(env).get("/x", headers={"Authorization": value})
    assert r.status_code == 200, r.text
    h = r.json()["headers"]
    assert "authorization" not in h and h["x-onemind-principal"] == "person:owner"


def test_bearer_only_session_is_never_forwarded(env):
    r = client(env).get("/x", headers=bearer(env, "adult"))
    assert r.status_code == 200 and "authorization" not in r.json()["headers"]


def test_websocket_carries_the_app_authorization(env):
    cookie = f"onemind_session={env['tokens']['owner']}"
    headers = ws_headers(Origin="http://kuma.onemind.local", Cookie=cookie, Authorization=APP_TOKEN)
    with client(env).websocket_connect("/ws", headers=headers) as ws:
        assert ws.receive_json() == {"principal": "person:owner", "authorization": APP_TOKEN, "path": "/ws"}
    headers = ws_headers(Origin="http://kuma.onemind.local", Cookie=cookie, **bearer(env, "adult"))
    with client(env).websocket_connect("/ws", headers=headers) as ws:
        assert ws.receive_json()["authorization"] is None


def test_household_session_cookie_with_app_bearer(env, tmp_path):
    """The gateway's own resolver and sharing check (routers/net.py): a household session in the cookie
    opens a shared app while the app's bearer rides along; the same session as a bearer is never sent."""
    ses = "om_ses_" + secrets.token_urlsafe(16)
    person = Principal(id="u1", kind="person", role="adult")

    def authenticate(request, token):
        return person if token == ses else None

    def shared_with_session(request, principal, app_id):  # proves the sharing check saw the session
        return request.headers.get("authorization") == f"Bearer {ses}"

    proxy = env["app"].user_middleware[0].kwargs["proxy"]
    proxy.resolve_session = gateway_session_resolver(TokenStore(tmp_path / "no-static-tokens.yaml"), [authenticate])
    proxy.shared = sharing_check([authenticate], [shared_with_session])
    c = client(env)
    c.cookies.set("onemind_session", ses)
    r = c.get("/x", headers={"Authorization": APP_TOKEN})
    assert r.status_code == 200, r.text
    assert r.json()["headers"]["authorization"] == APP_TOKEN
    r = c.get("/x", headers={"Authorization": f"Bearer {ses}"})
    assert r.status_code == 200 and "authorization" not in r.json()["headers"]
    assert client(env).get("/x", headers={"Authorization": APP_TOKEN}).status_code == 401


def test_app_token_is_not_a_gateway_credential(settings, clock):
    """OneMind API routes keep their own rules: an app's token never signs in to the gateway, even next
    to the app-host session cookie."""
    with make_client(settings, clock) as gw:
        gw.cookies.set("onemind_session", OWNER["Authorization"].split(" ", 1)[1])
        assert gw.get("/v1/me", headers={"Authorization": APP_TOKEN}).status_code == 401
        assert gw.get("/v1/me", headers=OWNER).status_code == 200


def test_actual_password_session_opens_lan_app_and_stays_off_mesh(settings, clock, executor):
    app = create_app(id_settings(settings), clock=clock, executor=executor)
    with TestClient(app, client=LOCAL_PEER) as lan:
        setup_owner(lan)
        login = lan.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD, "client": "app"})
        assert login.status_code == 200, login.text
        cookie = f"onemind_session={login.json()['access_token']}"
        proxy = next(m.kwargs["proxy"] for m in app.user_middleware if m.cls is AppProxyMiddleware)
        proxy.route_for = lambda _: AppRoute(app_id="uptime-kuma", host="upstream", port=80,
                                             access="adults", name="Test app")
        proxy.exposure = lambda _: "mesh"  # either path reaches this app when the person's proof permits
        host = f"uptime-kuma.{proxy.box_domains[0]}"
        headers = {"host": host, "cookie": cookie}
        peer = (str(MESH_NETS[0].network_address + 1), 50000)
        assert proxy.decide(headers, "uptime-kuma", proxy.path_of({"client": LOCAL_PEER}, headers))[0] == 204
        assert proxy.decide(headers, "uptime-kuma", proxy.path_of({"client": peer}, headers))[0] == 401

        edge = TestClient(app, client=("127.0.0.1", 50000))
        forwarded = {"X-Forwarded-Host": host, "Cookie": cookie}
        assert edge.get("/v1/auth/forward", headers={**forwarded, "X-OneMind-Path": "lan"}).status_code == 204
        assert edge.get("/v1/auth/forward", headers={**forwarded, "X-OneMind-Path": "mesh"}).status_code == 401
        assert edge.get("/v1/auth/forward", headers=forwarded).status_code == 401


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
