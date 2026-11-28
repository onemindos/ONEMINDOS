# SPDX-License-Identifier: Apache-2.0
"""Reverse proxy for installed apps, with gateway sign-in in front (H-29; NETWORKING.md §9).

Mounted by routers/net.py (CORE-NET-8), which adds AppProxyMiddleware in front of every route.
Routing (written as an ASGI middleware, so HTTP and WebSocket share one code path):
- by host: <app>.<box-domain> (for example uptime-kuma.onemind.local or <app>.apps.onemind.internal);
- by path, as a fallback for clients without multi-label mDNS: /apps/<app>/... on any host the
  gateway answers, with the /apps/<app> prefix removed before the request goes upstream. **Off by
  default** (`path_routes=True` turns it on): a path route serves the app on the gateway's own
  origin, so the app's scripts could read the dashboard's token from sessionStorage and call the
  gateway API as the person. Only host routes give each app its own origin.

What it refuses (no open proxy):
- the upstream is never taken from the request. It is the app's Service in namespace app-<id>,
  found by the port the catalog declares (spec.web.port), and only for an app the ledger says is
  installed; any other name gets 404;
- every request needs a signed-in *person*: the session cookie first, or else a OneMind bearer token
  (scripts and the CLI). Agent tokens are refused on app hosts. The app's access level
  (owner | adults | signed_in, default adults) decides 403;
- the client's Authorization header belongs to the app only behind a valid session cookie (#824):
  then it is the app's own credential (Fleetbase, for example, sends its own bearer token), it never
  signs anyone in to OneMind and it is forwarded to that app's upstream only. A OneMind credential in
  it (anything the session resolver knows, or any `om_` token, even a revoked one) is never forwarded,
  and with no session cookie the header is OneMind's and is removed. The gateway session cookie and
  any X-OneMind-* header are always removed; the proxy adds X-OneMind-Principal and X-OneMind-Role;
- an app's response cannot set or overwrite the gateway session cookie (Set-Cookie for that name
  is dropped), so one app cannot plant a session for every *.onemind.local name;
- a WebSocket, or a request with an unsafe method (anything but GET/HEAD/OPTIONS), whose Origin
  is not the host it is sent to is refused (cross-site hijacking and CSRF: app names share one
  site, so SameSite=Lax alone would let one app post to another as the person);
- an app that is not shared with the person (contract §12.6, the same `app_filters` as
  GET /v1/apps) and an app whose exposure tier (§12.22) does not include the name used (a private
  app on its mesh name) are 404, as if they did not exist. The tier is also enforced by the network
  path the request came by (netpath.py), not only the Host header, so a LAN-only app cannot be
  reached from the internet by sending its LAN name; an unknown path is refused;
- an unauthenticated request gets 401 whether or not the app exists, so installed apps cannot be
  listed without signing in;
- a browser app (`spec.browser`, browsers.py) is never served on its own name, where one shared
  profile would live (403). It is served on `<app>--<key>.<box domain>`, to the person whose
  person_key is <key> only (anyone else 403), from that person's own Service (#692).

Honest pages (UMB-P02): a signed-in person who may open an app that is stopped, starting, being
updated or failed gets 503 with a page that says so (and reloads itself while the app is changing),
not a bare 404; an app that is installed but does not answer gets 502 saying that. A browser gets a
small HTML page, any other client plain text. 404 stays for names that are not an app at all.

Timeouts: connect, idle read and total request body size are bounded (H-20). The decision
`AppProxy.decide()` is the same one the Go edge will ask for through /v1/auth/forward (§9.3;
that route is in routers/net.py).
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import html
import ipaddress
import json
import logging
import subprocess
import threading
import time
from collections.abc import Awaitable, Callable, MutableMapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote, urlsplit

import h11
from websockets.asyncio.client import connect as ws_connect
from starlette.requests import Request
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from .auth import Principal, TokenStore
from .browsers import BrowserProfiles, BrowserSpec, browser_spec, split_host_label
from .catalog import APP_ID_RE, Catalog
from .errors import ApiError
from .netpath import EDGE_PATHS, SCOPE_PATH_KEY, NetPath, PathClassifier, tier_admits

log = logging.getLogger("onemind.proxy")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[dict]]
Send = Callable[[dict], Awaitable[None]]

SESSION_COOKIE = "onemind_session"
# Identity's cookies are __Host-onemind_session and __Host-onemind_csrf; the gateway's own is
# onemind_session. Apps never receive or set any cookie in the onemind namespace (hardening H-34).
IDENTITY_COOKIE_PREFIXES = ("onemind_", "__host-onemind_")


def is_identity_cookie(name: str) -> bool:
    return name.strip().lower().startswith(IDENTITY_COOKIE_PREFIXES)
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ACCESS_LEVELS = ("owner", "adults", "signed_in")
DEFAULT_ACCESS = "adults"
PATH_PREFIX = "/apps/"

# RFC 9110 §7.6.1 hop-by-hop headers, plus framing headers the proxy sets itself.
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-connection", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
})
# Never forwarded upstream as the client sent them: credentials for the gateway and identity headers only
# we may set. Authorization goes back in only as Session.app_authorization (the app's own credential).
STRIP_UP = frozenset({"authorization", "host", "forwarded"})
ONEMIND_TOKEN_PREFIX = "om_"  # identity/crypto.py: om_ses_, om_pat_... (gateway sessions and API tokens)
WS_HANDSHAKE = frozenset({
    "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol",
    "sec-websocket-accept",
})


SessionResolver = Callable[[dict[str, str], dict[str, str]], Principal | None]
"""(lower-cased request headers, cookies) -> the signed-in principal, or None."""
PathSessionResolver = Callable[[dict[str, str], dict[str, str], NetPath], Principal | None]
SharingCheck = Callable[[Principal, str, dict[str, str]], bool]
PathSharingCheck = Callable[[Principal, str, dict[str, str], NetPath], bool]

ServiceResolver = Callable[[str, int], str | None]
"""(namespace, port) -> the address of the Service in that namespace exposing that port."""


def _bearer_or_cookie(headers: dict[str, str], cookies: dict[str, str], cookie: str) -> str:
    scheme, _, token = headers.get("authorization", "").partition(" ")
    token = token.strip() if scheme.lower() == "bearer" else ""
    return token or cookies.get(cookie, "").strip()


def token_session_resolver(tokens: TokenStore, cookie: str = SESSION_COOKIE) -> SessionResolver:
    """v0 sessions: a bearer token in the Authorization header or in the session cookie.

    The cookie holds the same token the dashboard already uses. CORE-SEC sessions (passkeys,
    revocable session ids) replace this behind the same SessionResolver signature.
    """

    def resolve(headers: dict[str, str], cookies: dict[str, str]) -> Principal | None:
        token = _bearer_or_cookie(headers, cookies, cookie)
        return tokens.lookup(token) if token else None

    return resolve


def _probe(token: str, authenticators: list, path: NetPath) -> tuple[Request, Principal | None]:
    """The gateway's own authenticators asked about a household session token (`om_ses_`, §12.6).

    Only sessions open apps. An API token is scoped to routes (`instance:read`, `apps:read`...),
    while an app host is whole-app interactive access, so a scoped token must not open one; it is
    simply "not signed in" here. Probe the app-session route so the same authentication checks
    apply to creating an app cookie and using an existing one. A refusal is also "not signed in".
    The returned request carries `state.identity` for the sharing filters.
    """
    request = Request({"type": "http", "method": "POST", "path": "/v1/auth/app-session",
                       "raw_path": b"/v1/auth/app-session",
                       "query_string": b"", "scheme": "https", "client": None, "server": None,
                       SCOPE_PATH_KEY: path,
                       "headers": [(b"authorization", f"Bearer {token}".encode("latin-1"))]})
    if not token.startswith("om_ses_"):
        return request, None
    for authenticate in authenticators:
        try:
            principal = authenticate(request, token)
        except ApiError:  # disabled account: not signed in for an app
            return request, None
        if principal is not None:
            return request, principal
    return request, None


def gateway_session_resolver(tokens: TokenStore, authenticators: list, cookie: str = SESSION_COOKIE) -> PathSessionResolver:
    """token_session_resolver plus the gateway's authenticators, so a household member's session
    token (the one the dashboard sends to POST /v1/auth/app-session) opens apps too."""

    def resolve(headers: dict[str, str], cookies: dict[str, str], path: NetPath = "unknown") -> Principal | None:
        token = _bearer_or_cookie(headers, cookies, cookie)
        if not token:
            return None
        return tokens.lookup(token) or _probe(token, authenticators, path)[1]

    return resolve


def sharing_check(authenticators: list, filters: list, cookie: str = SESSION_COOKIE) -> PathSharingCheck:
    """AppProxy(shared=...): the gateway's `app_filters` (per-app sharing, §12.6) for this request.

    Both lists are the gateway's live ones, so a feature that registers later still counts.
    """

    def shared(principal: Principal, app_id: str, headers: dict[str, str], path: NetPath = "unknown") -> bool:
        token = _bearer_or_cookie(headers, parse_cookies(headers.get("cookie", "")), cookie)
        request, resolved = _probe(token, authenticators, path)
        if token.startswith("om_ses_") and (resolved is None or resolved.id != principal.id):
            return False
        return all(f(request, principal, app_id) for f in list(filters))

    return shared


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
class Session:
    """Who the request is, and which Authorization header (if any) is the app's own (#824)."""

    principal: Principal | None
    headers: dict[str, str]  # the request headers with only the credential that named the principal
    app_authorization: str | None = None  # forwarded to the app's upstream, nowhere else


@dataclass(frozen=True)
class AppRoute:
    app_id: str
    host: str
    port: int
    access: str
    name: str = ""


@dataclass(frozen=True)
class Timeouts:
    connect: float = 5.0
    read: float = 60.0  # idle time between upstream bytes; long polls and streams keep going
    ws_open: float = 10.0


class Decision:
    ALLOW, UNAUTHENTICATED, FORBIDDEN, NOT_FOUND, UNAVAILABLE = 204, 401, 403, 404, 503


# Ledger states of an app that exists but is not serving (lifecycle.py), and what the page says.
# True: the app is changing, so the page asks the browser to reload in a few seconds.
NOT_RUNNING: dict[str, tuple[str, bool]] = {
    "installing": ("is being installed.", True),
    "starting": ("is starting.", True),
    "restarting": ("is restarting.", True),
    "updating": ("is being updated.", True),
    "configuring": ("is applying new settings.", True),
    "stopping": ("is stopping.", True),
    "removing": ("is being removed.", False),
    "stopped": ("is stopped. Start it from the OneMind dashboard.", False),
    "failed": ("is not running: its last change failed. The OneMind dashboard shows why.", False),
    "unknown": ("may not be running: OneMind cannot tell right now. The OneMind dashboard shows its state.", False),
}
RETRY_AFTER_S = 5


def allowed(principal: Principal, access: str) -> bool:
    if principal.kind != "person":
        return False  # agent tokens are never accepted on app hosts (§9.3)
    if access == "owner":
        return principal.role == "owner"
    if access == "adults":
        return principal.role in ("owner", "adult")
    return principal.role in ("owner", "adult", "guest", "child", "teen")


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
        resolve_session: SessionResolver | PathSessionResolver,
        resolve_service: ServiceResolver,
        *,
        box_domains: tuple[str, ...],
        timeouts: Timeouts = Timeouts(),
        max_body: int = 64 * 1024 * 1024,
        max_ws_message: int = 16 * 1024 * 1024,
        route_ttl: float = 5.0,
        audit: Callable[[str, dict | None, str | None, dict], Any] | None = None,
        path_routes: bool = False,
        exposure: Callable[[str], str] | None = None,
        mesh_domains: tuple[str, ...] = ("apps.onemind.internal",),
        shared: SharingCheck | PathSharingCheck | None = None,
        classify: PathClassifier | None = None,
        path_aware_sessions: bool = False,
        browsers: BrowserProfiles | None = None,
    ):
        """app_status(app_id) returns the ledger status ("installed", ...) or None.

        box_domains: the suffixes app hosts live under, for example ("onemind.local",
        "box1.local", "apps.onemind.internal").
        path_routes: also serve /apps/<id>/ on the gateway host (same origin as the dashboard;
        see the module docstring before turning it on).
        exposure(app_id) -> private | mesh | public (contract §12.22): a request on a mesh_domains
        name is answered 404 unless the app's tier includes the mesh.
        shared(principal, app_id, headers) -> whether the app is shared with this person (§12.6);
        False is 404, like GET /v1/apps. None: every signed-in person (the v0 behaviour).
        classify: the network path a request really came from (netpath.py). When set, the tier is
        also enforced by path, not only by Host: a private app answers only to the LAN, a mesh app
        to LAN and mesh, and a path that cannot be told is refused (fails closed). None: host only.
        path_aware_sessions: pass this same trusted path to the gateway session and sharing resolvers.
        browsers: the per-person browser Services (browsers.py). None: browser hosts answer 404.
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
        self.path_routes = path_routes
        self.exposure = exposure
        self.mesh_domains = tuple(d.lower().strip(".") for d in mesh_domains)
        self.shared = shared
        self.classify = classify
        self.path_aware_sessions = path_aware_sessions
        self.browsers = browsers
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
        if self.path_routes and path.startswith(PATH_PREFIX):
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

    def _web(self, app_id: str) -> tuple[int, str, str] | None:
        """(web port, access level, display name) from the catalog, or None for an app without a web UI."""
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
        name = (entry.manifest.get("metadata") or {}).get("name")
        return port, access, name if isinstance(name, str) and name.strip() else app_id

    def _resolve(self, app_id: str) -> AppRoute | None:
        if self.app_status(app_id) != "installed":
            return None
        web = self._web(app_id)
        if web is None:
            return None
        port, access, name = web
        host = self.resolve_service(f"app-{app_id}", port)
        if not host:
            return None
        return AppRoute(app_id=app_id, host=host, port=port, access=access, name=name)

    def path_of(self, scope: Scope, headers: dict[str, str]) -> NetPath:
        """The path this connection came by (unknown when no classifier is set: nothing is enforced)."""
        if self.classify is None:
            return "unknown"
        pinned = scope.get(SCOPE_PATH_KEY)  # set by the listener itself (the Tor listener), never by a client
        if pinned in EDGE_PATHS:
            return pinned
        client = scope.get("client")
        return self.classify(client[0] if client else None, headers)

    def not_running(self, principal: Principal, host: str, app_id: str,
                    headers: dict[str, str] | None = None, path: NetPath = "unknown") -> tuple[str, str] | None:
        """(display name, ledger status) of a web app that exists but is not serving, else None.

        Asked only after decide() said 404 to a signed-in person, and answered only when that person
        could open the app if it were running (same access level, same exposure rule), so nobody
        learns of an app they may not open. decide() itself keeps its four answers: /v1/auth/forward
        maps them one to one.
        """
        if not APP_ID_RE.match(app_id) or not self._exposed(host, app_id, path) \
                or not self._shared_with(principal, app_id, headers or {}, path):
            return None
        status = self.app_status(app_id)
        if status not in NOT_RUNNING:
            return None
        web = self._web(app_id)
        if web is None or not allowed(principal, web[1]):
            return None
        return web[2], status

    def _resolve_session(self, headers: dict[str, str], cookies: dict[str, str], path: NetPath) -> Principal | None:
        if self.path_aware_sessions:
            return self.resolve_session(headers, cookies, path)
        return self.resolve_session(headers, cookies)

    def session(self, headers: dict[str, str], path: NetPath = "unknown") -> Session:
        """The OneMind session of an app request: the session cookie first, a OneMind bearer second (#824).

        Behind a valid cookie the Authorization header is the app's own: it is never asked to sign
        anyone in, so an app's token cannot stand in for a OneMind one, and it is kept for the app
        unless it is a OneMind credential. Without a valid cookie a OneMind bearer still signs in
        (scripts, the CLI); that header is OneMind's and is never forwarded.
        """
        cookies = parse_cookies(headers.get("cookie", ""))
        given = headers.get("authorization")
        if given is None:
            return Session(self._resolve_session(headers, cookies, path), headers)
        bare = {k: v for k, v in headers.items() if k != "authorization"}
        principal = self._resolve_session(bare, cookies, path) if cookies else None
        if principal is not None:
            return Session(principal, bare, None if self.onemind_credential(given) else given)
        return Session(self._resolve_session(headers, cookies, path), headers)

    def onemind_credential(self, authorization: str) -> bool:
        """True for an Authorization value that carries a OneMind token, valid or not: never forwarded."""
        scheme, _, token = authorization.strip().partition(" ")
        if scheme.startswith(ONEMIND_TOKEN_PREFIX) or token.strip().startswith(ONEMIND_TOKEN_PREFIX):
            return True
        return self._resolve_session({"authorization": authorization}, {}, "unknown") is not None

    def decide(self, headers: dict[str, str], app_id: str,
               path: NetPath = "unknown") -> tuple[int, Principal | None, AppRoute | None]:
        """Forward-auth decision: 204 allow, 401 not signed in, 403 not allowed, 404 no such app.

        Sign-in is checked first, so a caller without a session cannot tell installed apps apart.
        `path` is the network path of the request (path_of); it matters only when a classifier is set.
        """
        status, session, route = self.decide_session(headers, app_id, path)
        return status, session.principal, route

    def decide_session(self, headers: dict[str, str], app_id: str,
                       path: NetPath = "unknown") -> tuple[int, Session, AppRoute | None]:
        """decide(), returning the whole Session (the proxy needs the app's own Authorization)."""
        session = self.session(headers, path)
        status, route = self._decide(session, headers.get("host", ""), app_id, path)
        return status, session, route

    def _decide(self, session: Session, host_header: str, app_id: str,
                path: NetPath) -> tuple[int, AppRoute | None]:
        principal, headers = session.principal, session.headers
        if principal is None:
            return Decision.UNAUTHENTICATED, None
        split = split_host_label(app_id)
        key = None
        if split is not None and self.browser_of(split[0]) is not None:
            app_id, key = split  # <app>--<key>: a person's browser host (#692)
        route = self.route_for(app_id)
        if route is None or not self._exposed(host_header, app_id, path) \
                or not self._shared_with(principal, app_id, headers, path):
            return Decision.NOT_FOUND, None
        if not allowed(principal, route.access):
            return Decision.FORBIDDEN, route
        spec = self.browser_of(app_id)
        if spec is None:
            return Decision.ALLOW, route
        if key is None or principal.kind != "person" or self.browsers is None \
                or not hmac.compare_digest(key, self.browsers.key_of(principal.id)):
            return Decision.FORBIDDEN, route  # the shared template, or another person's browser
        host = self.browsers.service_host(app_id, key, spec.port) if self.browsers is not None else None
        if host is None:
            return Decision.NOT_FOUND, None
        return Decision.ALLOW, replace(route, host=host, port=spec.port)

    def browser_of(self, app_id: str) -> BrowserSpec | None:
        """`spec.browser` of a catalog app (browsers.py), or None."""
        entry = self.catalog.get(app_id)
        return browser_spec(entry.manifest) if entry is not None else None

    def _shared_with(self, principal: Principal, app_id: str, headers: dict[str, str], path: NetPath) -> bool:
        """False for an app the owner has not shared with this person (§12.6)."""
        if self.shared is None:
            return True
        if self.path_aware_sessions:
            return self.shared(principal, app_id, headers, path)
        return self.shared(principal, app_id, headers)

    def _exposed(self, host: str, app_id: str, path: NetPath = "unknown") -> bool:
        """False when the tier (§12.22) does not admit this request: by the name used, and by the path.

        The Host header is the client's word, so it only closes doors (a mesh name of a private app);
        the network path is what keeps a LAN-only app off the internet.
        """
        if self.exposure is None:
            return True
        if self.classify is not None and not tier_admits(self.exposure(app_id), path):
            return False
        name = host.lower().rsplit(":", 1)[0] if not host.startswith("[") else host.lower()
        name = name.rstrip(".")
        if not any(name.endswith("." + d) for d in self.mesh_domains):
            return True
        return self.exposure(app_id) in ("mesh", "public")

    def _audit_denied(self, principal: Principal | None, app_id: str, status: int, scope: Scope) -> None:
        if self.audit is not None and principal is not None and status == Decision.FORBIDDEN:
            self.audit("proxy.denied", principal.as_dict(), None,
                       {"app_id": app_id, "method": scope.get("method", "WS"), "path": scope.get("path", "")})

    # ---- upstream headers ------------------------------------------------------------------------
    def upstream_headers(self, scope: Scope, principal: Principal, route: AppRoute, prefix: str,
                         *, websocket: bool, app_authorization: str | None = None) -> list[tuple[str, str]]:
        """Headers for the app's upstream. app_authorization: Session.app_authorization, the only way an
        Authorization header reaches an app (the client's own copy is in STRIP_UP)."""
        out: list[tuple[str, str]] = []
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.decode("latin-1").lower()
            value = raw_value.decode("latin-1")
            if name in HOP_BY_HOP or name in STRIP_UP or name.startswith("x-onemind-"):
                continue
            if name.startswith("x-forwarded-") or (websocket and name in WS_HANDSHAKE | {"origin"}):
                continue
            if name == "cookie":
                kept = [c for c in value.split(";") if not is_identity_cookie(c.partition("=")[0])]
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
        if app_authorization:
            out.append(("authorization", app_authorization))
        return out


def _same_origin(origin: str | None, scope: Scope) -> bool:
    """True when there is no Origin header (not a browser cross-site request) or it names this host."""
    return origin is None or (urlsplit(origin).hostname or "") == _host(scope)


def _sets_session_cookie(name: bytes, value: bytes) -> bool:
    if name.lower() != b"set-cookie":
        return False
    cookie_name = value.decode("latin-1").split(";", 1)[0].partition("=")[0].strip()
    return is_identity_cookie(cookie_name)


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
    raw = scope.get("raw_path") or quote(scope.get("path", "/")).encode()
    if prefix:
        # The route matched the decoded path; strip the prefix from the raw path only when the
        # raw form starts with it, else re-encode the decoded remainder.
        raw = raw[len(prefix.encode()):] if raw.startswith(prefix.encode()) else \
            quote(scope.get("path", "/")[len(prefix):]).encode()
    if not raw.startswith(b"/"):
        raw = b"/" + raw
    qs = scope.get("query_string") or b""
    return raw + (b"?" + qs if qs else b"")


async def _plain(send: Send, status: int, text: str, headers: list[tuple[bytes, bytes]] | None = None,
                 *, page: bool = False, refresh: bool = False) -> None:
    """A response the proxy writes itself. page=True: a small HTML page for a browser.

    The page has no script and no outside resource (its CSP says so); refresh=True makes it reload
    itself after RETRY_AFTER_S, for an app that is starting or changing.
    """
    extra = list(headers or [])
    if refresh:
        extra.append((b"retry-after", str(RETRY_AFTER_S).encode()))
    if page:
        meta = f'<meta http-equiv="refresh" content="{RETRY_AFTER_S}">' if refresh else ""
        body = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"{meta}<title>OneMind</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:32rem;"
            "margin:15vh auto;padding:0 1rem;color:#222;background:#fff}}@media(prefers-color-scheme:dark)"
            "{body{color:#eee;background:#111}}</style></head>"
            f"<body><p>{html.escape(text)}</p></body></html>"
        ).encode()
        ctype = b"text/html; charset=utf-8"
        extra += [(b"content-security-policy", b"default-src 'none'; style-src 'unsafe-inline'"),
                  (b"x-content-type-options", b"nosniff")]
    else:
        body = text.encode()
        ctype = b"text/plain; charset=utf-8"
    await send({"type": "http.response.start", "status": status, "headers": [
        (b"content-type", ctype), (b"content-length", str(len(body)).encode()),
        (b"cache-control", b"no-store"), *extra,
    ]})
    await send({"type": "http.response.body", "body": body})


def _wants_page(headers: dict[str, str]) -> bool:
    return "text/html" in headers.get("accept", "")


DENY_TEXT = {401: "Sign in to OneMind to open this app.", 403: "You do not have access to this app.",
             404: "No such app."}


def unavailable_text(name: str, status: str) -> tuple[str, bool]:
    said, changing = NOT_RUNNING[status]
    return f"{name} {said}", changing


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
        path = self.proxy.path_of(scope, headers)
        status, session, route = self.proxy.decide_session(headers, app_id, path)
        principal = session.principal
        if scope["type"] == "websocket":
            return await self._websocket(scope, receive, send, app_id, status, session, route, prefix, headers)
        if status == Decision.ALLOW and scope.get("method", "GET") not in SAFE_METHODS \
                and not _same_origin(headers.get("origin"), scope):
            status = Decision.FORBIDDEN
        page = _wants_page(headers)
        if status == Decision.NOT_FOUND and principal is not None:
            down = self.proxy.not_running(principal, headers.get("host", ""), app_id, session.headers, path)
            if down is not None:
                text, changing = unavailable_text(*down)
                return await _plain(send, Decision.UNAVAILABLE, text, page=page, refresh=changing)
        if status != Decision.ALLOW:
            self.proxy._audit_denied(principal, app_id, status, scope)
            extra = [(b"www-authenticate", b"Bearer")] if status == 401 else None
            return await _plain(send, status, DENY_TEXT[status], extra, page=page)
        if prefix and scope.get("path") == prefix:  # /apps/<id> -> /apps/<id>/
            qs = scope.get("query_string") or b""
            loc = (prefix + "/").encode() + (b"?" + qs if qs else b"")
            return await _plain(send, 308, "Moved", [(b"location", loc)])
        assert principal is not None and route is not None
        await self._http(scope, receive, send, principal, route, prefix, page, session.app_authorization)

    # ---- HTTP --------------------------------------------------------------------------------------
    async def _http(self, scope: Scope, receive: Receive, send: Send, principal: Principal,
                    route: AppRoute, prefix: str, page: bool = False, app_authorization: str | None = None) -> None:
        p, t = self.proxy, self.proxy.timeouts
        name = route.name or route.app_id
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(route.host, route.port), t.connect)
        except (OSError, asyncio.TimeoutError):
            return await _plain(send, 502, f"{name} is installed but not answering. It may still be starting.",
                                page=page, refresh=True)
        conn = h11.Connection(h11.CLIENT)
        started = False
        try:
            client_headers = {k.decode("latin-1").lower(): v for k, v in scope.get("headers", [])}
            headers = p.upstream_headers(scope, principal, route, prefix, websocket=False,
                                         app_authorization=app_authorization)
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
                    out = [(k.lower(), v) for k, v in event.headers
                           if k.lower().decode("latin-1") not in HOP_BY_HOP and not _sets_session_cookie(k, v)]
                    await send({"type": "http.response.start", "status": event.status_code, "headers": out})
                    started = True
                elif isinstance(event, h11.Data):
                    await send({"type": "http.response.body", "body": bytes(event.data), "more_body": True})
                elif isinstance(event, (h11.EndOfMessage, h11.ConnectionClosed)):
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
                    return
        except asyncio.TimeoutError:
            if not started:
                return await _plain(send, 504, f"{name} took too long to answer.", page=page)
            raise
        except (OSError, h11.ProtocolError):
            if not started:
                return await _plain(send, 502, f"{name} sent a broken response.", page=page)
            raise
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    # ---- WebSocket ---------------------------------------------------------------------------------
    async def _websocket(self, scope: Scope, receive: Receive, send: Send, app_id: str, status: int,
                         session: Session, route: AppRoute | None, prefix: str,
                         headers: dict[str, str]) -> None:
        principal = session.principal
        msg = await receive()
        if msg["type"] != "websocket.connect":
            return
        origin = headers.get("origin")
        if status == Decision.ALLOW and not _same_origin(origin, scope):
            status = Decision.FORBIDDEN
        if status != Decision.ALLOW:
            self.proxy._audit_denied(principal, app_id, status, scope)
            return await send({"type": "websocket.close", "code": 1008})
        assert principal is not None and route is not None
        p, t = self.proxy, self.proxy.timeouts
        uri = f"ws://{route.host}:{route.port}{_upstream_target(scope, prefix).decode('latin-1')}"
        up_headers = p.upstream_headers(scope, principal, route, prefix, websocket=True,
                                        app_authorization=session.app_authorization)
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
