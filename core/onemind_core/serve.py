# SPDX-License-Identifier: Apache-2.0
"""Run the gateway's listeners (contract §12.7, H-05; NETWORKING.md §9).

Without ONEMIND_NET_TLS: one plain HTTP listener on ONEMIND_HOST:ONEMIND_PORT, as before.

With ONEMIND_NET_TLS=1, one process serves the same app on:
- HTTPS on ONEMIND_NET_HTTPS_PORTS (default 443 and 8443) with a box-CA certificate for the box's
  names and every app name (<app>.onemind.local, <app>.<box>.local, <app>.apps.onemind.internal);
- plain HTTP on ONEMIND_HOST:ONEMIND_PORT for local tools, the health gate and in-cluster callers
  (the installer keeps it where it was; H-05 wants it on loopback once app pods use HTTPS);
- optionally ONEMIND_NET_HTTP_REDIRECT_PORT (80), which only redirects to HTTPS.

Lifespan (NATS, startup hooks) runs once, on the plain listener; the others start after it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import socket
from collections.abc import Iterator

import uvicorn

from .ca import BoxCA
from .config import Settings
from .netconf import NetSettings

log = logging.getLogger("onemind.serve")


class _Server(uvicorn.Server):
    """A uvicorn server that leaves signal handling to serve_all (several servers, one process)."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _bind(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.set_inheritable(True)
    return sock


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


def https_cert(settings: Settings, net: NetSettings) -> tuple[str, str]:
    tls_dir = net.tls_dir or settings.audit_path.parent / "tls"
    cert = BoxCA(tls_dir, net.box()).ensure_https_cert()
    return str(cert.cert_path), str(cert.key_path)


async def serve_all(app, settings: Settings) -> None:
    net = settings.section(NetSettings)
    certfile, keyfile = https_cert(settings, net)
    ports = [int(p) for p in net.https_ports]
    main = _Server(uvicorn.Config(app, host=settings.host, port=settings.port, proxy_headers=False, lifespan="on"))
    https = _Server(uvicorn.Config(app, lifespan="off", proxy_headers=False, ssl_certfile=certfile, ssl_keyfile=keyfile))
    https_socks = [_bind(net.https_host, p) for p in ports]
    extra: list[tuple[_Server, list[socket.socket] | None]] = [(https, https_socks)]
    if net.http_redirect_port:
        redirect = _Server(uvicorn.Config(redirect_app(ports[0]), lifespan="off", proxy_headers=False))
        extra.append((redirect, [_bind(net.https_host, net.http_redirect_port)]))
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
        uvicorn.run(app, host=settings.host, port=settings.port, proxy_headers=False)
        return
    asyncio.run(serve_all(app, settings))
