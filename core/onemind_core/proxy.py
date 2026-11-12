# SPDX-License-Identifier: Apache-2.0
"""Reverse proxy for installed apps, with gateway sign-in in front (H-29; NETWORKING.md §9).

Routing (an ASGI middleware, so HTTP and WebSocket share one code path):
- by host: <app>.<box-domain> (for example uptime-kuma.onemind.local or <app>.apps.onemind.internal);
- by path, as a fallback for clients without multi-label mDNS: /apps/<app>/... on any host the
  gateway answers, with the /apps/<app> prefix removed before the request goes upstream.

What it refuses (no open proxy):
- the upstream is never taken from the request. It is the app's Service in namespace app-<id>,
  found by the port the catalog declares (spec.web.port), and only for an app the ledger says is
  installed; any other name gets 404;
- every request needs a signed-in *person* (bearer token or the session cookie). Agent tokens
  are refused on app hosts. The app's access level (owner | adults | signed_in, default adults)
  decides 403;
- the client's Authorization header, the gateway session cookie and any X-OneMind-* header are
  removed; the proxy adds X-OneMind-Principal and X-OneMind-Role itself;
- a WebSocket whose Origin is not the host it connects to is refused (cross-site hijacking).

Timeouts: connect, idle read and total request body size are bounded (H-20). The decision
`AppProxy.decide()` is the same one the Go edge will ask for through /v1/auth/forward (§9.3).
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import logging
import subprocess
import threading
import time
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import h11
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from .auth import Principal, TokenStore
from .catalog import APP_ID_RE, Catalog

log = logging.getLogger("onemind.proxy")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]

SESSION_COOKIE = "onemind_session"
ACCESS_LEVELS = ("owner", "adults", "signed_in")
DEFAULT_ACCESS = "adults"
PATH_PREFIX = "/apps/"

# RFC 9110 §7.6.1 hop-by-hop headers, plus framing headers the proxy sets itself.
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-connection", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
})
# Never forwarded upstream: credentials for the gateway and identity headers only we may set.
STRIP_UP = frozenset({"authorization", "host", "forwarded"})
WS_HANDSHAKE = frozenset({
    "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol",
    "sec-websocket-accept",
})


SessionResolver = Callable[[dict[str, str], dict[str, str]], Principal | None]
"""(lower-cased request headers, cookies) -> the signed-in principal, or None."""

ServiceResolver = Callable[[str, int], str | None]
"""(namespace, port) -> the address of the Service in that namespace exposing that port."""


def token_session_resolver(tokens: TokenStore, cookie: str = SESSION_COOKIE) -> SessionResolver:
    """v0 sessions: a bearer token in the Authorization header or in the session cookie.

    The cookie holds the same token the dashboard already uses. CORE-SEC sessions (passkeys,
    revocable session ids) replace this behind the same SessionResolver signature.
    """

    def resolve(headers: dict[str, str], cookies: dict[str, str]) -> Principal | None:
        scheme, _, token = headers.get("authorization", "").partition(" ")
        token = token.strip() if scheme.lower() == "bearer" else ""
        token = token or cookies.get(cookie, "").strip()
        return tokens.lookup(token) if token else None

    return resolve


class KubectlServiceResolver:
    """Finds the ClusterIP of the Service in a namespace that exposes a port.

    The gateway runs on the hub host, where cluster DNS names do not resolve but ClusterIPs are
    reachable (kube-proxy). Results are cached for `ttl` seconds.
    """

    def __init__(self, kubectl: str = "kubectl", *, timeout_s: float = 10, ttl: float = 30,
                 runner: Callable[..., subprocess.CompletedProcess] = subprocess.run):
        self.kubectl, self.timeout_s, self.ttl, self.runner = kubectl, timeout_s, ttl, runner
        self._cache: dict[tuple[str, int], tuple[float, str | None]] = {}
        self._lock = threading.Lock()

    def __call__(self, namespace: str, port: int) -> str | None:
        key, now = (namespace, port), time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        try:
            proc = self.runner([self.kubectl, "get", "services", "-n", namespace, "-o", "json"],
                               capture_output=True, timeout=self.timeout_s, check=False)
            items = json.loads(proc.stdout or b"{}").get("items") or [] if proc.returncode == 0 else []
        except (OSError, subprocess.SubprocessError, ValueError):
            items = []
        found: str | None = None
        for svc in sorted(items, key=lambda s: (s.get("metadata") or {}).get("name", "")):
            spec = svc.get("spec") or {}
            ip = spec.get("clusterIP")
            if spec.get("type", "ClusterIP") != "ClusterIP" or not ip or ip == "None":
                continue
            if any(p.get("port") == port and p.get("protocol", "TCP") == "TCP" for p in spec.get("ports") or []):
                try:
                    found = str(ipaddress.ip_address(ip))
                except ValueError:
                    continue
                break
        with self._lock:
            self._cache[key] = (now, found)
        return found


@dataclass(frozen=True)
class AppRoute:
    app_id: str
    host: str
    port: int
    access: str


@dataclass(frozen=True)
class Timeouts:
    connect: float = 5.0
    read: float = 60.0  # idle time between upstream bytes; long polls and streams keep going
    ws_open: float = 10.0


class Decision:
    ALLOW, UNAUTHENTICATED, FORBIDDEN, NOT_FOUND = 204, 401, 403, 404


def allowed(principal: Principal, access: str) -> bool:
    if principal.kind != "person":
        return False  # agent tokens are never accepted on app hosts (§9.3)
    if access == "owner":
        return principal.role == "owner"
    if access == "adults":
        return principal.role in ("owner", "adult")
    return principal.role in ("owner", "adult", "guest")


def parse_cookies(header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name and name not in out:
            out[name] = value
    return out


class AppProxy:
    def __init__(
        self,
        catalog: Catalog,
        app_status: Callable[[str], str | None],
        resolve_session: SessionResolver,
        resolve_service: ServiceResolver,
        *,
        box_domains: tuple[str, ...],
        timeouts: Timeouts = Timeouts(),
        max_body: int = 64 * 1024 * 1024,
        max_ws_message: int = 16 * 1024 * 1024,
        route_ttl: float = 5.0,
        audit: Callable[[str, dict | None, str | None, dict], Any] | None = None,
    ):
        """app_status(app_id) returns the ledger status ("installed", ...) or None.

        box_domains: the suffixes app hosts live under, for example ("onemind.local",
        "box1.local", "apps.onemind.internal").
        """
        self.catalog = catalog
        self.app_status = app_status
        self.resolve_session = resolve_session
        self.resolve_service = resolve_service
        self.box_domains = tuple(d.lower().strip(".") for d in box_domains)
        self.timeouts = timeouts
        self.max_body = max_body
        self.max_ws_message = max_ws_message
        self.route_ttl = route_ttl
        self.audit = audit
        self._routes: dict[str, tuple[float, AppRoute | None]] = {}
        self._lock = threading.Lock()

    # ---- routing -------------------------------------------------------------------------------
    def match(self, scope: Scope) -> tuple[str, str] | None:
        """(app id, path prefix to strip) when this request is for an app, else None."""
        host = _host(scope)
        for domain in self.box_domains:
            if host.endswith("." + domain):
                label = host[: -len(domain) - 1]
                return (label, "") if "." not in label else None
        path = scope.get("path", "")
        if path.startswith(PATH_PREFIX):
            app_id = path[len(PATH_PREFIX):].split("/", 1)[0]
            return app_id, PATH_PREFIX + app_id
        return None

    def route_for(self, app_id: str) -> AppRoute | None:
        """The upstream for an installed app with a web port; None for anything else."""
        if not APP_ID_RE.match(app_id):
            return None
        now = time.monotonic()
        with self._lock:
            hit = self._routes.get(app_id)
            if hit and now - hit[0] < self.route_ttl:
                return hit[1]
        route = self._resolve(app_id)
        with self._lock:
            self._routes[app_id] = (now, route)
        return route

    def _resolve(self, app_id: str) -> AppRoute | None:
        if self.app_status(app_id) != "installed":
            return None
        entry = self.catalog.get(app_id)
        if entry is None:
            return None
        web = (entry.manifest.get("spec") or {}).get("web")
        port = web.get("port") if isinstance(web, dict) else None
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            return None
        access = web.get("access", DEFAULT_ACCESS)
        if access not in ACCESS_LEVELS:
            access = DEFAULT_ACCESS
        host = self.resolve_service(f"app-{app_id}", port)
        if not host:
            return None
        return AppRoute(app_id=app_id, host=host, port=port, access=access)

    def decide(self, headers: dict[str, str], app_id: str) -> tuple[int, Principal | None, AppRoute | None]:
        """Forward-auth decision: 204 allow, 401 not signed in, 403 not allowed, 404 no such app."""
        route = self.route_for(app_id)
        if route is None:
            return Decision.NOT_FOUND, None, None
        principal = self.resolve_session(headers, parse_cookies(headers.get("cookie", "")))
        if principal is None:
            return Decision.UNAUTHENTICATED, None, route
        if not allowed(principal, route.access):
            return Decision.FORBIDDEN, principal, route
        return Decision.ALLOW, principal, route

    def _audit_denied(self, principal: Principal | None, app_id: str, status: int, scope: Scope) -> None:
        if self.audit is not None and principal is not None and status == Decision.FORBIDDEN:
            self.audit("proxy.denied", principal.as_dict(), None,
                       {"app_id": app_id, "method": scope.get("method", "WS"), "path": scope.get("path", "")})

    # ---- upstream headers ------------------------------------------------------------------------
    def upstream_headers(self, scope: Scope, principal: Principal, route: AppRoute, prefix: str,
                         *, websocket: bool) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
            if name in HOP_BY_HOP or name in STRIP_UP or name.startswith("x-onemind-"):
                continue
            if name.startswith("x-forwarded-") or (websocket and name in WS_HANDSHAKE | {"origin"}):
                continue
            if name == "cookie":
                kept = [c for c in value.split(";") if c.strip().partition("=")[0] != SESSION_COOKIE]
                if not any(c.strip() for c in kept):
                    continue
                value = ";".join(kept).strip()
            out.append((name, value))
        client = scope.get("client") or ("", 0)
        out += [
            ("x-forwarded-for", str(client[0])),
            ("x-forwarded-host", _host(scope)),
            ("x-forwarded-proto", "https" if scope.get("scheme") in ("https", "wss") else "http"),
            ("x-onemind-principal", f"person:{principal.id}"),
            ("x-onemind-role", principal.role),
        ]
        if prefix:
            out.append(("x-forwarded-prefix", prefix))
        return out


def _host(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name == b"host":
            host = value.decode("latin-1").strip().lower()
            if host.startswith("["):
                return host.split("]", 1)[0] + "]"
            return host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    server = scope.get("server")
    return str(server[0]).lower() if server else ""


def _upstream_target(scope: Scope, prefix: str) -> bytes:
    raw = scope.get("raw_path") or scope.get("path", "/").encode()
    if prefix:
        raw = raw[len(prefix.encode()):]
    if not raw.startswith(b"/"):
        raw = b"/" + raw
    qs = scope.get("query_string") or b""
    return raw + (b"?" + qs if qs else b"")


async def _plain(send: Send, status: int, text: str, headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = text.encode()
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"), *(headers or []),
    ]})
    await send({"type": "http.response.body", "body": body})


DENY_TEXT = {401: "Sign in to OneMind to open this app.", 403: "You do not have access to this app.",
             404: "No such app."}


class AppProxyMiddleware:
    """ASGI middleware: app requests are proxied, everything else goes to the gateway app."""

    def __init__(self, app: Callable, proxy: AppProxy):
        self.app = app
        self.proxy = proxy

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        matched = self.proxy.match(scope)
        if matched is None:
            return await self.app(scope, receive, send)
        app_id, prefix = matched
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        status, principal, route = self.proxy.decide(headers, app_id)
        if scope["type"] == "websocket":
            return await self._websocket(scope, receive, send, app_id, status, principal, route, prefix, headers)
        if status != Decision.ALLOW:
            self.proxy._audit_denied(principal, app_id, status, scope)
            extra = [(b"www-authenticate", b"Bearer")] if status == 401 else None
            return await _plain(send, status, DENY_TEXT[status], extra)
        if prefix and scope.get("path") == prefix:  # /apps/<id> -> /apps/<id>/
            qs = scope.get("query_string") or b""
            loc = (prefix + "/").encode() + (b"?" + qs if qs else b"")
            return await _plain(send, 308, "Moved", [(b"location", loc)])
        assert principal is not None and route is not None
        await self._http(scope, receive, send, principal, route, prefix)

    # ---- HTTP --------------------------------------------------------------------------------------
    async def _http(self, scope: Scope, receive: Receive, send: Send, principal: Principal,
                    route: AppRoute, prefix: str) -> None:
        p, t = self.proxy, self.proxy.timeouts
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(route.host, route.port), t.connect)
        except (OSError, asyncio.TimeoutError):
            return await _plain(send, 502, "The app is not answering.")
        conn = h11.Connection(h11.CLIENT)
        started = False
        try:
            client_headers = {k.decode("latin-1").lower(): v for k, v in scope.get("headers", [])}
            headers = p.upstream_headers(scope, principal, route, prefix, websocket=False)
            if "transfer-encoding" in client_headers and not any(k == "content-length" for k, _ in headers):
                headers.append(("transfer-encoding", "chunked"))
            headers += [("host", f"{route.host}:{route.port}"), ("connection", "close")]
            writer.write(conn.send(h11.Request(method=scope["method"], target=_upstream_target(scope, prefix),
                                               headers=headers)))
            # Request body, streamed and bounded.
            sent = 0
            while True:
                msg = await receive()
                if msg["type"] == "http.disconnect":
                    return
                chunk = msg.get("body", b"")
                sent += len(chunk)
                if sent > p.max_body:
                    return await _plain(send, 413, "Request body too large.")
                if chunk:
                    writer.write(conn.send(h11.Data(data=chunk)))
                    await writer.drain()
                if not msg.get("more_body", False):
                    break
            writer.write(conn.send(h11.EndOfMessage()))
            await writer.drain()
            # Response, streamed back as it arrives.
            while True:
                event = conn.next_event()
                if event is h11.NEED_DATA:
                    data = await asyncio.wait_for(reader.read(65536), t.read)
                    conn.receive_data(data)
                    continue
                if isinstance(event, h11.InformationalResponse):
                    continue
                if isinstance(event, h11.Response):
                    out = [(k.lower(), v) for k, v in event.headers if k.lower().decode("latin-1") not in HOP_BY_HOP]
                    await send({"type": "http.response.start", "status": event.status_code, "headers": out})
                    started = True
                elif isinstance(event, h11.Data):
                    await send({"type": "http.response.body", "body": bytes(event.data), "more_body": True})
                elif isinstance(event, (h11.EndOfMessage, h11.ConnectionClosed)):
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                    return
        except asyncio.TimeoutError:
            if not started:
                return await _plain(send, 504, "The app took too long to answer.")
            raise
        except (OSError, h11.ProtocolError):
            if not started:
                return await _plain(send, 502, "The app sent a broken response.")
            raise
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    # ---- WebSocket ---------------------------------------------------------------------------------
    async def _websocket(self, scope: Scope, receive: Receive, send: Send, app_id: str, status: int,
                         principal: Principal | None, route: AppRoute | None, prefix: str,
                         headers: dict[str, str]) -> None:
        msg = await receive()
        if msg["type"] != "websocket.connect":
            return
        origin = headers.get("origin")
        if status == Decision.ALLOW and origin is not None and (urlsplit(origin).hostname or "") != _host(scope):
            status = Decision.FORBIDDEN
        if status != Decision.ALLOW:
            self.proxy._audit_denied(principal, app_id, status, scope)
            return await send({"type": "websocket.close", "code": 1008})
        assert principal is not None and route is not None
        p, t = self.proxy, self.proxy.timeouts
        uri = f"ws://{route.host}:{route.port}{_upstream_target(scope, prefix).decode('latin-1')}"
        up_headers = p.upstream_headers(scope, principal, route, prefix, websocket=True)
        try:
            upstream = await ws_connect(
                uri, additional_headers=up_headers, subprotocols=scope.get("subprotocols") or None,
                proxy=None, open_timeout=t.ws_open, max_size=p.max_ws_message, compression=None,
                user_agent_header=None, ping_interval=None,
            )
        except (OSError, asyncio.TimeoutError, InvalidHandshake, InvalidStatus):
            return await send({"type": "websocket.close", "code": 1011})
        await send({"type": "websocket.accept", "subprotocol": upstream.subprotocol})

        async def client_to_app() -> None:
            while True:
                m = await receive()
                if m["type"] == "websocket.disconnect":
                    await upstream.close(code=m.get("code", 1000))
                    return
                if m.get("text") is not None:
                    await upstream.send(m["text"])
                elif m.get("bytes") is not None:
                    await upstream.send(m["bytes"])

        async def app_to_client() -> None:
            try:
                async for data in upstream:
                    key = "text" if isinstance(data, str) else "bytes"
                    await send({"type": "websocket.send", key: data})
            except ConnectionClosed:
                pass
            code = upstream.close_code or 1000
            with contextlib.suppress(Exception):
                await send({"type": "websocket.close", "code": code if code != 1005 else 1000})

        tasks = [asyncio.ensure_future(client_to_app()), asyncio.ensure_future(app_to_client())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            with contextlib.suppress(Exception):
                await upstream.close()
