# SPDX-License-Identifier: Apache-2.0
"""Run the gateway's listeners (contract §12.7, H-05; NETWORKING.md §9).

Without ONEMIND_NET_TLS: one plain HTTP listener on ONEMIND_HOST:ONEMIND_PORT, as before.

With ONEMIND_NET_TLS=1, one process serves the same app on:
- HTTPS on ONEMIND_NET_HTTPS_PORTS (default 443 and 8443) with a box-CA certificate for the box's
  names and every app name (<app>.onemind.local, <app>.<box>.local, <app>.apps.onemind.internal);
- plain HTTP on ONEMIND_PORT, bound to loopback only (plain_http_host, H-05): local tools and the health gate;
  the LAN is served by HTTPS only;
- optionally ONEMIND_NET_HTTP_REDIRECT_PORT (80), which only redirects to HTTPS.

Lifespan (NATS, startup hooks) runs once, on the plain listener; the others start after it.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import ipaddress
import logging
import re
import signal
import socket
from collections.abc import Iterator
from typing import Any

import uvicorn

from .ca import BoxCA
from .config import Settings
from .netconf import MeshSettings, NetSettings
from .netpath import SCOPE_PATH_KEY, parse_networks

log = logging.getLogger("onemind.serve")

# A query-string secret uvicorn's access log must never write: WOPI hands the office engine its
# om_wopi_ bearer token as ?access_token= (routers/wopi.py), and the access log prints each path
# with its query string to stdout and so to journald.
_SECRET_QUERY = re.compile(r"(?i)((?:^|[?&])access_token=)[^&\s\"]*")


def redact_query(text: str) -> str:
    """The text with every access_token query value replaced by [redacted]."""
    return _SECRET_QUERY.sub(r"\1[redacted]", text)


class RedactAccessToken(logging.Filter):
    """Redacts access_token query values from uvicorn.access records before any handler sees them."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(redact_query(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact_query(v) if isinstance(v, str) else v for k, v in record.args.items()}
        if isinstance(record.msg, str):
            record.msg = redact_query(record.msg)
        return True


def log_config() -> dict[str, Any]:
    """uvicorn's default logging config with RedactAccessToken on the uvicorn.access logger.

    Every uvicorn.Config and uvicorn.run here takes it (log_config=...), so no listener writes a
    WOPI access token, whichever port or handler the record reaches."""
    cfg = copy.deepcopy(uvicorn.config.LOGGING_CONFIG)
    cfg.setdefault("filters", {})["redact_access_token"] = {"()": RedactAccessToken}
    access = cfg["loggers"].setdefault("uvicorn.access", {})
    access["filters"] = [*access.get("filters", []), "redact_access_token"]
    return cfg


class _Server(uvicorn.Server):
    """A uvicorn server that leaves signal handling to serve_all (several servers, one process)."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _bind(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        # Lets onemind-starting (same user) hold the port until this gateway listens (onemind_starting.py).
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


LOOPBACK_HOST = "127.0.0.1"


def plain_http_host(host: str) -> str:
    """The address the plain-HTTP listener binds to once HTTPS is on (H-05, §12.7).

    Plain HTTP never serves the LAN: a wildcard or LAN address is replaced by loopback, which is
    where local tools, the health gate and the installer's checks reach it. The LAN gets HTTPS
    (and, optionally, a redirect). Only an explicit loopback address is kept as it is.
    """
    h = host.strip("[]")
    if h == "localhost":
        return h
    try:
        if ipaddress.ip_address(h).is_loopback:
            return host
    except ValueError:
        pass
    log.warning("ONEMIND_HOST=%r is not loopback: with HTTPS on, plain HTTP is bound to %s only (H-05)", host, LOOPBACK_HOST)
    return LOOPBACK_HOST


def redirect_app(https_port: int):
    """ASGI app: every request -> 308 to the same host and path over HTTPS."""

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                msg = await receive()
                if msg["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif msg["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        host = ""
        for k, v in scope.get("headers", []):
            if k == b"host":
                host = v.decode("latin-1")
                break
        host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        if not host or any(c in host for c in "/\\@ \r\n"):
            host = scope.get("server", ("localhost", 0))[0]
        port = "" if https_port == 443 else f":{https_port}"
        target = scope.get("raw_path") or scope.get("path", "/").encode()
        qs = scope.get("query_string") or b""
        location = f"https://{host}{port}".encode() + target + (b"?" + qs if qs else b"")
        await send({"type": "http.response.start", "status": 308, "headers": [
            (b"location", location), (b"content-length", b"0"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": b""})

    return app


TOR_APP_ID = "tor-remote-access"
# Who may reach the Tor listener: the Tor pod (k3s default pod CIDR, or the flannel gateway address
# in it), the hub itself, and mesh peers. The home LAN is not in this list.
TOR_PEER_NETWORKS = parse_networks("127.0.0.0/8,10.42.0.0/16,100.64.0.0/10")


def tor_bind_host(settings: Settings) -> str | None:
    """The one address the plain-HTTP Tor listener binds to: the hub's mesh address, else None.

    That is the address gateway_path() hands the Tor pod (hub.onemind.internal). It is never a
    wildcard and never a LAN address: this listener is plain HTTP and carries sign-in, so the home
    Wi-Fi must not be able to reach it (contract sdk/contracts/poc-v0.md section 12.7, H-05).
    """
    mesh = settings.section(MeshSettings)
    if not mesh.enabled or not mesh.hub_ip:
        return None
    try:
        ip = ipaddress.ip_address(mesh.hub_ip)
    except ValueError:
        return None
    if ip.version != 4 or ip not in ipaddress.ip_network("100.64.0.0/10"):
        return None
    return str(ip)


def pinned_path_app(app, path: str, *, peers=None, enabled=None):
    """ASGI wrapper: every connection this listener accepts is on `path` (netpath.SCOPE_PATH_KEY).

    peers: networks allowed to connect; any other peer gets 403 (None = no check).
    enabled: callable; while it returns False the listener answers 503 (the Tor app is not installed).
    """

    async def deny(scope, send, status: int):
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": status, "headers": [
                (b"content-length", b"0"), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b""})
        else:
            await send({"type": "websocket.close", "code": 1008})

    async def wrapped(scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            if peers is not None:
                client = scope.get("client")
                try:
                    ok = bool(client) and any(ipaddress.ip_address(client[0].split("%", 1)[0]) in n for n in peers)
                except ValueError:
                    ok = False
                if not ok:
                    return await deny(scope, send, 403)
            if enabled is not None and not enabled():
                return await deny(scope, send, 503)
            scope = {**scope, SCOPE_PATH_KEY: path}
        await app(scope, receive, send)

    return wrapped


def https_cert(settings: Settings, net: NetSettings) -> tuple[str, str]:
    tls_dir = net.tls_dir or settings.audit_path.parent / "tls"
    cert = BoxCA(tls_dir, net.tls_box(tls_dir)).ensure_https_cert()
    return str(cert.cert_path), str(cert.key_path)


async def serve_all(app, settings: Settings) -> None:
    net = settings.section(NetSettings)
    certfile, keyfile = https_cert(settings, net)
    ports = [int(p) for p in net.https_ports]
    main = _Server(uvicorn.Config(app, host=plain_http_host(settings.host), port=settings.port,
                                  proxy_headers=False, lifespan="on", log_config=log_config()))
    https = _Server(uvicorn.Config(app, lifespan="off", proxy_headers=False, ssl_certfile=certfile, ssl_keyfile=keyfile,
                                   log_config=log_config()))
    https_socks = [_bind(net.https_host, p) for p in ports]
    extra: list[tuple[_Server, list[socket.socket] | None]] = [(https, https_socks)]
    if net.http_redirect_port:
        redirect = _Server(uvicorn.Config(redirect_app(ports[0]), lifespan="off", proxy_headers=False,
                                         log_config=log_config()))
        extra.append((redirect, [_bind(net.https_host, net.http_redirect_port)]))
    if net.tor_port:
        # Plain HTTP on purpose: the onion address already encrypts and authenticates the link, and
        # Tor forwards raw TCP, so a TLS listener here would fail the browser's plain request.
        # Because it is plain HTTP it binds only to the hub's mesh address, never to net.https_host.
        host = tor_bind_host(settings)
        sock = None
        if host is None:
            log.warning("Tor listener :%s not started: it needs the mesh on with a hub mesh address", net.tor_port)
        else:
            try:
                sock = _bind(host, net.tor_port)
            except OSError as e:
                log.warning("Tor listener %s:%s not started: %s", host, net.tor_port, e)
        if sock is not None:
            def tor_installed() -> bool:
                repo = getattr(getattr(app, "state", None), "repo", None)
                try:
                    st = repo.get_app_state(TOR_APP_ID) if repo is not None else None
                except Exception:
                    return False
                return bool(st and st.status == "installed")

            tor = _Server(uvicorn.Config(pinned_path_app(app, "tor", peers=TOR_PEER_NETWORKS, enabled=tor_installed),
                                         lifespan="off", proxy_headers=False))
            extra.append((tor, [sock]))
    servers = [main] + [s for s, _ in extra]

    loop = asyncio.get_running_loop()

    def stop(*_):
        for s in servers:
            s.should_exit = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop)

    tasks = [asyncio.create_task(main.serve())]
    while not main.started and not tasks[0].done():
        await asyncio.sleep(0.05)
    if not tasks[0].done():
        tasks += [asyncio.create_task(s.serve(sockets=socks)) for s, socks in extra]
        log.info("HTTPS on %s ports %s (box CA)%s", net.https_host, ",".join(net.https_ports),
                 f"; HTTP :{net.http_redirect_port} redirects" if net.http_redirect_port else "")
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    stop()
    await asyncio.gather(*tasks, return_exceptions=True)
    for t in done:
        if t.exception() is not None:
            raise t.exception()


def run(app, settings: Settings) -> None:
    net = settings.section(NetSettings)
    if not net.tls:
        uvicorn.run(app, host=settings.host, port=settings.port, proxy_headers=False, log_config=log_config())
        return
    asyncio.run(serve_all(app, settings))
