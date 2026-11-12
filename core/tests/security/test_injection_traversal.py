# SPDX-License-Identifier: Apache-2.0
"""Injection and traversal attacks on the gateway (threat model T/I/D rows; H-18, H-20, H-29).

- Path traversal on the dashboard's static files and SPA fallback, sent as raw ASGI requests so
  no HTTP client "fixes" the path first: dot segments, encoded and double-encoded separators,
  overlong UTF-8, absolute paths, symlinks inside dist pointing out of it, NUL bytes.
- Header injection: CR/LF reflected into response headers, spoofed identity headers, the session
  cookie or a query-string token trying to stand in for the bearer token, duplicate and oversized
  Authorization headers, Host reflection; security headers (pending the security P0 stream).
- SSRF on every URL-taking setting: the Headscale coordinator URL (loopback only, and no redirect
  may carry its API key elsewhere), the app proxy's upstream (never derived from the request) and
  ONEMIND_PUBLIC_URL; URL settings that later become reachable through the API must bring a probe.
- Oversized bodies and JSON bombs on every route that takes a body, and on NATS heartbeats.

A defect found on main is a strict xfail naming it: the fix turns it into a failure, so the marker
is removed in the fixing PR.
"""

from __future__ import annotations

import asyncio
import http.server
import importlib.util
import json
import secrets
import threading
import typing
from pathlib import Path
from urllib.parse import unquote

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import AGENT, GUEST, OWNER, make_client
from onemind_core import actions as actions_mod
from onemind_core import proxy as proxy_mod
from onemind_core.auth import TokenStore
from onemind_core.catalog import Catalog
from onemind_core.config import Settings
from onemind_core.mesh import HeadscaleClient, urllib_transport
from onemind_core.proxy import AppProxy, AppProxyMiddleware, Timeouts, token_session_resolver
from sec_policy import POLICY
from sec_world import World, route_methods

GUARD_STREAM = "request limits and security headers arrive with feat/sec-p0 (PR #40, CORE-SEC-9, H-18, H-20)"
HAS_GUARD = importlib.util.find_spec("onemind_core.guard") is not None
TOKENS = {"dev-owner-token-change-me", "dev-adult-token-change-me", "dev-guest-token-change-me", "dev-agent-token-change-me"}


# ---- raw ASGI: send exactly the bytes an attacker would put on the wire -----------------------------------
def raw_request(app, method: str, target: bytes, headers: list[tuple[bytes, bytes]] | None = None, body: bytes = b""):
    """(status, headers, body) for one request whose path is decoded the way uvicorn does it."""
    raw_path, _, query = target.partition(b"?")
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
        "path": unquote(raw_path.decode("ascii")), "raw_path": raw_path, "query_string": query, "root_path": "",
        "headers": [(b"host", b"onemind.local"), *(headers or [])],
        "client": ("127.0.0.1", 50000), "server": ("onemind.local", 8080),
    }
    sent: dict = {"status": None, "headers": [], "body": b""}

    async def run():
        done = asyncio.Event()
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            await done.wait()  # like a real server: the client disconnects only after the response
            return {"type": "http.disconnect"}

        async def send(msg):
            if msg["type"] == "http.response.start":
                sent["status"], sent["headers"] = msg["status"], msg.get("headers", [])
            elif msg["type"] == "http.response.body":
                sent["body"] += msg.get("body", b"")
                if not msg.get("more_body"):
                    done.set()

        await asyncio.wait_for(app(scope, receive, send), timeout=30)

    try:
        asyncio.run(run())
    except Exception:  # noqa: BLE001 - Starlette re-raises after sending its 500
        if sent["status"] is None:
            sent["status"] = 500
    return sent["status"], sent["headers"], sent["body"]


# ---- path traversal on static files and the SPA fallback --------------------------------------------------
@pytest.fixture
def dist_app(settings, clock, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("SPA-SHELL")
    (dist / "assets" / "app.js").write_text("ASSET-IN-DIST")
    (tmp_path / "secret.txt").write_text("SENTINEL-outside-dist")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret2.txt").write_text("SENTINEL-linked-dir")
    (dist / "assets" / "leak.js").symlink_to(tmp_path / "secret.txt")
    (dist / "linkdir").symlink_to(tmp_path / "outside", target_is_directory=True)
    with make_client(settings, clock, dashboard_dist=dist) as c:
        yield c.app, tmp_path


TRAVERSALS = [
    b"/../secret.txt", b"/../../secret.txt", b"/assets/../../secret.txt", b"/./../secret.txt",
    b"/index.html/../../secret.txt", b"/%2e%2e/secret.txt", b"/%2E%2E/secret.txt", b"/.%2e/secret.txt",
    b"/..%2fsecret.txt", b"/..%2Fsecret.txt", b"/assets/..%2f..%2fsecret.txt", b"/%2e%2e%2fsecret.txt",
    b"/%252e%252e/secret.txt", b"/%252e%252e%252fsecret.txt", b"/..%5csecret.txt", b"/..\\secret.txt",
    b"/assets\\..\\..\\secret.txt", b"/%c0%ae%c0%ae/secret.txt", b"/%e2%80%a5/secret.txt",
    b"/%ef%bc%8e%ef%bc%8e/secret.txt", b"/assets/leak.js", b"/linkdir/secret2.txt", b"/linkdir/",
    b"/linkdir/%2e%2e/secret.txt", b"/.env", b"/.git/config", b"/assets/", b"/assets/app.js/..",
]
NUL_TRAVERSALS = [b"/%00", b"/assets/app.js%00.html", b"/secret.txt%00/index.html"]
NUL_BUG = ("finding on main: a NUL byte in a dashboard path makes Path.resolve() raise ValueError in "
           "routers/static.py, so any unauthenticated caller gets a 500 instead of a 404")


def _check_static(app, tmp_path: Path, target: bytes):
    status, _, body = raw_request(app, "GET", target)
    text = body.decode("utf-8", "replace")
    assert "SENTINEL" not in text, f"{target!r} leaked a file outside dist"
    assert not any(t in text for t in TOKENS), f"{target!r} leaked a token"
    assert status < 500, f"{target!r}: {status}"
    if status == 200:
        assert text in ("SPA-SHELL", "ASSET-IN-DIST"), f"{target!r} served something else: {text[:80]}"
    return status


@pytest.mark.parametrize("target", TRAVERSALS, ids=lambda t: t.decode())
def test_static_traversal_never_leaves_dist(dist_app, target):
    app, tmp_path = dist_app
    _check_static(app, tmp_path, target)


def test_static_absolute_paths_never_leave_dist(dist_app):
    app, tmp_path = dist_app
    secret = str(tmp_path / "secret.txt").encode()
    for target in (b"/" + secret, b"//" + secret.lstrip(b"/"), b"/%2f" + secret.lstrip(b"/"), b"/assets/" + secret):
        _check_static(app, tmp_path, target)


@pytest.mark.parametrize("target", NUL_TRAVERSALS, ids=lambda t: t.decode())
@pytest.mark.xfail(strict=True, reason=NUL_BUG)
def test_static_nul_byte_is_a_clean_404(dist_app, target):
    app, tmp_path = dist_app
    assert _check_static(app, tmp_path, target) == 404


def test_static_files_still_work(dist_app):
    app, tmp_path = dist_app
    assert raw_request(app, "GET", b"/assets/app.js")[2] == b"ASSET-IN-DIST"
    assert raw_request(app, "GET", b"/some/client/route")[2] == b"SPA-SHELL"


# ---- header injection ------------------------------------------------------------------------------------------
@pytest.fixture
def world(settings, clock, tmp_path):
    with World(settings, clock, tmp_path) as w:
        yield w


CRLF = ["%0d%0aSet-Cookie:%20pwned=1", "%0aX-Injected:%201", "%E5%98%8A%E5%98%8DSet-Cookie:%20pwned=1"]


@pytest.mark.parametrize("payload", CRLF)
def test_crlf_in_path_or_query_never_reaches_response_headers(world, payload):
    for target in (f"/v1/instance?x={payload}", f"/{payload}", f"/v1/nodes/{payload}", f"/v1/actions/{payload}"):
        for headers in ({}, world.static("owner")):
            r = world.client.get(target, headers=headers)
            assert r.status_code < 500, (target, r.status_code)
            assert "set-cookie" not in r.headers and "x-injected" not in r.headers, (target, dict(r.headers))
            for name, value in r.headers.items():
                assert "\r" not in value and "\n" not in value and "pwned" not in value, (target, name, value)


SPOOFED = {
    "X-OneMind-Principal": "person:owner", "X-OneMind-Role": "owner", "X-Forwarded-User": "owner",
    "X-Remote-User": "owner", "X-Auth-Request-User": "owner", "Remote-User": "owner",
    "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1", "Forwarded": "for=127.0.0.1;host=onemind.local",
}


def test_identity_headers_cannot_stand_in_for_a_token(world):
    """Only the bearer token authenticates the API; headers a proxy might set are ignored."""
    action = world.owner_action()
    assert world.client.get("/v1/instance", headers=SPOOFED).status_code == 401
    r = world.client.post(f"/v1/actions/{action}/approve", headers={**SPOOFED, **world.static("guest")})
    assert r.status_code == 403
    r = world.client.post(f"/v1/actions/{action}/approve", headers={**SPOOFED, **world.static("agent")})
    assert r.status_code == 403
    assert world.client.get(f"/v1/actions/{action}", headers=world.static("owner")).json()["state"] == "awaiting_approval"


def test_session_cookie_and_query_token_never_authenticate_the_api(world):
    """The REST API reads only Authorization, so a cross-site form post (CSRF) carries no credential."""
    owner = world.tokens["owner"]
    action = world.owner_action()
    for (method, path), row in POLICY.items():
        if (method, path) not in world.routes() or row.expect["none"] != 401:
            continue
        req = row.probe(world)
        for attempt in ({"cookies": {"onemind_session": owner}}, {"params": {"access_token": owner, "token": owner}}):
            c = TestClient(world.app, raise_server_exceptions=False, **({"cookies": attempt["cookies"]} if "cookies" in attempt else {}))
            r = c.request(method, req.path, params=attempt.get("params"), json=req.json, content=req.content)
            target = req.path
            assert r.status_code == 401, (method, target, attempt.keys(), r.status_code)
    assert world.client.get(f"/v1/actions/{action}", headers=world.static("owner")).json()["state"] == "awaiting_approval"


@pytest.mark.parametrize("auth", [
    "Basic ZGV2LW93bmVyLXRva2VuLWNoYW5nZS1tZQ==", "Token {owner}", "Bearer:{owner}", "Bearer\t{owner}",
    "Bearer {owner} extra", "Bearer {owner}\u0000", "{owner}", "Bearer " + "a" * (1 << 20), "Bearer é{owner}",
])
def test_malformed_authorization_is_401_not_5xx(world, auth):
    value = auth.format(owner=world.tokens["owner"])
    r = world.client.get("/v1/instance", headers=[(b"authorization", value.encode("latin-1", "replace"))])
    assert r.status_code == 401, r.status_code


def test_duplicate_authorization_never_escalates(world):
    """Two Authorization headers: the gateway must not take the stronger of them."""
    action = world.owner_action()
    r = world.client.post(f"/v1/actions/{action}/approve", headers=[
        ("authorization", f"Bearer {world.tokens['guest']}"), ("authorization", f"Bearer {world.tokens['owner']}")])
    assert r.status_code in (400, 401, 403), r.status_code
    assert world.client.get(f"/v1/actions/{action}", headers=world.static("owner")).json()["state"] == "awaiting_approval"


def test_host_header_is_never_reflected(world):
    for path, headers in (("/v1/instance", {}), ("/v1/instance", world.static("owner")), ("/v1/nope", world.static("owner")),
                          ("/", {}), ("/openapi.json", {})):
        r = world.client.get(path, headers={**headers, "Host": "evil.example"})
        assert "evil.example" not in r.text and "evil.example" not in json.dumps(dict(r.headers)), path


@pytest.mark.skipif(not HAS_GUARD, reason=GUARD_STREAM)
def test_every_response_carries_security_headers(world):
    action = world.owner_action()
    for path, headers in (("/v1/instance", world.static("owner")), ("/v1/instance", {}), (f"/v1/actions/{action}", world.static("guest")),
                          ("/", {}), ("/assets/missing.js", {}), ("/openapi.json", {}), ("/healthz", {})):
        r = world.client.get(path, headers=headers)
        h = {k.lower(): v for k, v in r.headers.items()}
        assert "frame-ancestors 'none'" in h.get("content-security-policy", ""), (path, h)
        assert h.get("x-content-type-options") == "nosniff", path
        assert h.get("referrer-policy") == "no-referrer", path


# ---- SSRF ------------------------------------------------------------------------------------------------------
REFUSED_COORDINATORS = [
    "http://169.254.169.254/", "http://metadata.google.internal/", "http://10.0.0.1:8080", "http://192.168.1.1",
    "http://172.16.0.1", "http://100.64.0.1", "http://[::ffff:169.254.169.254]/", "http://0.0.0.0:8080",
    "http://127.0.0.1.nip.io:8080", "http://localhost.evil.example", "http://127.0.0.1@evil.example/",
    "http://evil.example#@127.0.0.1", "http://2130706433/", "http://0x7f000001/",
    "http://127.1/", "file:///etc/passwd", "gopher://127.0.0.1:6379/_FLUSHALL", "ftp://127.0.0.1/", "dict://127.0.0.1:11211/",
    "//127.0.0.1:8080", "127.0.0.1:8080", "", "http://", "https://[::]:8443",
]


@pytest.mark.parametrize("url", REFUSED_COORDINATORS)
def test_headscale_url_must_be_loopback_http(url):
    with pytest.raises(ValueError):
        HeadscaleClient(url, "key")


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080", "http://localhost:8080", "https://[::1]:8443", "http://LOCALHOST:8080"])
def test_headscale_loopback_urls_still_work(url):
    assert HeadscaleClient(url, "key").base_url == url.rstrip("/")


def _serve(handler) -> http.server.HTTPServer:
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.xfail(strict=True, reason=(
    "finding on main: mesh.urllib_transport follows HTTP redirects and re-sends the Headscale API key "
    "(Authorization) to the redirect target, so the loopback-only URL check does not bound where the key goes"))
def test_headscale_transport_does_not_follow_redirects_with_the_key():
    seen: list[dict] = []

    class Thief(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *a):
            pass

    thief = _serve(Thief)

    class Redirector(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{thief.server_port}/steal")
            self.end_headers()

        def log_message(self, *a):
            pass

    hop = _serve(Redirector)
    try:
        key = secrets.token_hex(16)
        status, _ = urllib_transport("GET", f"http://127.0.0.1:{hop.server_port}/api/v1/node", {"Authorization": f"Bearer {key}"}, None, 3)
        assert all(key not in json.dumps(h) for h in seen), "the API key reached the redirect target"
        assert status in (301, 302, 303, 307, 308)
    finally:
        hop.shutdown()
        thief.shutdown()


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "gopher://gw:70/", "http://", "ftp://gw/", "gw:8080"])
def test_public_url_setting_refuses_non_http(url):
    with pytest.raises(ValueError):
        Settings.from_env({"ONEMIND_PUBLIC_URL": url})


def test_app_proxy_upstream_never_comes_from_the_request(tmp_path, monkeypatch):
    """Host, absolute-form targets, X-Forwarded-Host, Forwarded and path tricks never pick the upstream."""
    token = secrets.token_urlsafe(24)
    (tmp_path / "tokens.yaml").write_text(yaml.safe_dump({"tokens": {token: {"id": "owner", "kind": "person", "role": "owner"}}}))
    app_dir = tmp_path / "apps" / "kuma"
    app_dir.mkdir(parents=True)
    (app_dir / "onemind.app.yaml").write_text(yaml.safe_dump({
        "apiVersion": "onemind.app/v1alpha1", "kind": "App", "metadata": {"id": "kuma", "name": "kuma", "version": "1.0.0"},
        "spec": {"archs": ["amd64"], "manifests": "manifests/", "web": {"port": 3001}}}))
    resolved, connects = [], []

    def resolver(namespace, port):
        resolved.append((namespace, port))
        return "127.0.0.1"

    async def fake_connect(host, port, *a, **kw):
        connects.append((host, port))
        raise ConnectionRefusedError

    monkeypatch.setattr(proxy_mod.asyncio, "open_connection", fake_connect)
    proxy = AppProxy(Catalog(tmp_path / "apps"), {"kuma": "installed"}.get, token_session_resolver(TokenStore(tmp_path / "tokens.yaml")),
                     resolver, box_domains=("onemind.local",), timeouts=Timeouts(connect=1, read=1, ws_open=1),
                     route_ttl=0, path_routes=True)
    gw = FastAPI()

    @gw.get("/{rest:path}")
    def gateway(rest: str):
        return {"gateway": rest}

    gw.add_middleware(AppProxyMiddleware, proxy=proxy)
    auth = {"Authorization": f"Bearer {token}"}
    attempts = [
        ("169.254.169.254", "/latest/meta-data/", {}), ("169.254.169.254.onemind.local", "/", {}),
        ("kuma.onemind.local", "/", {"X-Forwarded-Host": "169.254.169.254"}),
        ("kuma.onemind.local", "/", {"Forwarded": "host=169.254.169.254;proto=http"}),
        ("kuma.onemind.local:80@169.254.169.254", "/", {}), ("localhost.onemind.local", "/", {}),
        ("onemind.local", "/apps/kuma/..%2f..%2f169.254.169.254/x", {}), ("onemind.local", "/apps/%2e%2e/v1/instance", {}),
        ("onemind.local", "/apps/localhost/x", {}), ("onemind.local", "/apps/169.254.169.254/x", {}),
    ]
    for host, path, extra in attempts:
        c = TestClient(gw, base_url=f"http://{host.split('@')[0]}", raise_server_exceptions=False)
        r = c.get(path, headers={**auth, **extra, "Host": host})
        assert r.status_code < 500 or r.status_code in (502, 504), (host, path, r.status_code)
    r = TestClient(gw, base_url="http://kuma.onemind.local", raise_server_exceptions=False).get(
        "http://169.254.169.254/latest/meta-data/", headers={**auth, "Host": "kuma.onemind.local"})
    assert all(ns == "app-kuma" and port == 3001 for ns, port in resolved), resolved
    assert connects and all(target == ("127.0.0.1", 3001) for target in connects), connects


# URL-taking settings that become reachable through the API. Each needs an SSRF probe here before
# it ships: loopback, link-local metadata, the LAN, the tailnet and non-http(s) schemes refused.
URL_SURFACES = {
    ("POST", "/v1/notifications/channels"): "webhook, ntfy and matrix channel URLs (feat/notifications, CORE-NOTIFY-1, §12.14)",
}
URL_ACTION_TYPES = {
    "backup.destination.add": "s3 and rest destination endpoints (feat/backup-api, CORE-BACKUP-8, §12.12)",
    "tls.acme.set": "ACME directory and DNS provider endpoints (CORE-SEC-1, §12.7)",
}


def test_api_reachable_url_settings_bring_an_ssrf_probe(world):
    live = world.routes()
    arrived = [why for key, why in URL_SURFACES.items() if key in live]
    types = set(typing.get_args(actions_mod.ActionType))
    arrived += [why for t, why in URL_ACTION_TYPES.items() if t in types]
    assert not arrived, f"write an SSRF probe in core/tests/security for: {arrived}"


# ---- oversized bodies and JSON bombs ----------------------------------------------------------------------------
def body_routes(world) -> list[tuple[str, str, str]]:
    """(method, concrete path, principal kind allowed to call it) for every route that takes a body."""
    out = []
    for (method, path) in sorted(route_methods(world.app)):
        if method not in ("POST", "PUT", "PATCH") or (method, path) not in POLICY:
            continue
        row = POLICY[(method, path)]
        kind = next((k for k in ("agent", "owner") if isinstance(row.expect.get(k), int) and row.expect[k] < 400), "owner")
        out.append((method, row.probe(world).path, kind))
    return out


def _send(world, method, path, kind, content: bytes):
    return world.client.request(method, path, content=content, headers={**world.mint(kind), "Content-Type": "application/json"})


def test_oversized_bodies_never_crash(world):
    big = json.dumps({"pad": "x" * (300 * 1024)}).encode()
    routes = body_routes(world)
    assert len(routes) >= 4
    for method, path, kind in routes:
        r = _send(world, method, path, kind, big)
        assert r.status_code < 500, (method, path, r.status_code)
        if HAS_GUARD or path == "/mcp":
            assert r.status_code == 413, (method, path, r.status_code, r.text[:200])


@pytest.mark.skipif(not HAS_GUARD, reason=GUARD_STREAM)
def test_oversized_chunked_bodies_are_413(world):
    def chunks():
        for _ in range(40):
            yield b"x" * 10240

    for method, path, kind in body_routes(world):
        r = world.client.request(method, path, content=chunks(), headers={**world.mint(kind), "Content-Type": "application/json"})
        assert r.status_code == 413, (method, path, r.status_code)


MCP_BOMB = ("finding on main: mcp.py parses with json.loads and catches only ValueError; a 100k-deep array raises "
            "RecursionError, so any agent token gets a 500 instead of a JSON-RPC parse error")


@pytest.mark.parametrize("bomb", ["deep-array", "deep-object", "huge-int", "nan", "lone-surrogate-key"])
def test_json_bombs_never_crash_a_route(world, bomb, request):
    payload = {
        "deep-array": b"[" * 100_000 + b"]" * 100_000,
        "deep-object": b'{"a":' * 40_000 + b"1" + b"}" * 40_000,  # under the 256 KiB /mcp cap
        "huge-int": b'{"jsonrpc":"2.0","id":' + b"9" * 200_000 + b',"method":"ping"}',
        "nan": b'{"jsonrpc":"2.0","id":NaN,"method":"ping","type":"app.install","idempotency_key":Infinity}',
        "lone-surrogate-key": b'{"\\ud800":1,"jsonrpc":"2.0","id":1,"method":"ping"}',
    }[bomb]
    if bomb.startswith("deep"):
        request.applymarker(pytest.mark.xfail(strict=True, reason=MCP_BOMB))
    for method, path, kind in body_routes(world):
        r = _send(world, method, path, kind, payload)
        assert r.status_code < 500, (bomb, method, path, r.status_code)


def test_heartbeat_nesting_does_not_break_node_reads(world):
    """Heartbeats come from the bus (unauthenticated in v0): deep but parseable JSON stays harmless."""
    nested = json.loads("[" * 900 + "]" * 900)
    world.heartbeat(extra=nested)
    assert world.client.get("/v1/nodes", headers=world.static("owner")).status_code == 200
    r = world.client.post("/mcp", headers=world.static("agent"), json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_nodes", "arguments": {}}})
    assert r.status_code == 200 and "result" in r.json()


@pytest.mark.xfail(strict=True, reason=(
    "finding on main: NodeRegistry.ingest catches only JSONDecodeError and UnicodeDecodeError; a heartbeat "
    "nested deeper than the parser's recursion limit raises RecursionError out of the NATS callback instead of "
    "being dropped (its docstring promises False)"))
def test_heartbeat_json_bomb_is_dropped(world):
    n = 30_000  # 60 KB, under the 64 KiB heartbeat limit
    assert world.app.state.registry.ingest("onemind.node.a1b2c3d4e5f6.status", b"[" * n + b"]" * n) is False


# ---- field limits on the request path -----------------------------------------------------------------------------
@pytest.mark.parametrize(("field", "value"), [
    ("idempotency_key", "k" * 201), ("app_id", "a" * 60), ("app_id", "../../etc"), ("app_id", "Uptime-Kuma"),
    ("app_id", "uptime-kuma\n"), ("app_id", "uptime-kuma;rm -rf /"), ("app_id", "-uptime"), ("type", "app.approve"),
])
def test_request_fields_are_bounded(world, field, value):
    body = world.action_body()
    if field == "app_id":
        body["params"]["app_id"] = value
    else:
        body[field] = value
    r = world.client.post("/v1/actions", json=body, headers=world.static("owner"))
    assert r.status_code == 422, (field, value, r.status_code)
    assert world.snapshot()[0] == []


def test_spoofed_conftest_tokens_are_not_the_matrix_tokens(world):
    """The world uses random tokens, so the public example tokens do not work against it."""
    for headers in (OWNER, AGENT, GUEST):
        assert world.client.get("/v1/instance", headers=headers).status_code == 401
