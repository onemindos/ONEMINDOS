# SPDX-License-Identifier: Apache-2.0
"""The "OneMind is starting" page: answers on the gateway's HTTPS ports until the gateway is ready, then leaves.

Why it exists: the hub's gateway needs a while after power-on (Python start, database, NATS retry), and a
browser that visits earlier gets "connection refused", which looks like a broken box. This tiny process starts
first, holds :443 and :8443 with the box's own certificate, and answers every request with HTTP 503 and a page
that reloads itself every few seconds. 503 (not 200) so nothing mistakes it for the dashboard: the health gate
and monitors keep waiting for the real /healthz.

Hand-over: the page and the gateway both bind with SO_REUSEPORT (core/onemind_core/serve.py _bind), same user.
A bound socket that does not listen() gets no connections, so the gateway takes traffic only when it really
listens (after its own startup finished). The page watches the gateway's loopback /healthz; once it answers 200
it keeps serving for a short grace period (so the two listeners overlap and no connection finds none), then exits.

Stdlib plus onemind_core.ca (the same code the gateway uses to make its HTTPS certificate). Tied to
unit onemind-starting.service; test: test/unit/test_starting.py; battery: test/qemu F10.
"""
from __future__ import annotations

import os
import socket
import ssl
import sys
import threading
import time
import urllib.request
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3"><title>OneMind is starting</title>
<style>:root{color-scheme:light dark;--bg:#fff;--fg:#14171f;--mut:#5b6472;--ac:#4f46e5}
@media (prefers-color-scheme:dark){:root{--bg:#0e1118;--fg:#eef0f5;--mut:#9aa3b2;--ac:#818cf8}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);
font:16px/1.5 system-ui,sans-serif}main{padding:0 16px;max-width:30rem;text-align:center}
h1{font-size:1.5rem;margin:1rem 0 .25rem}p{color:var(--mut);margin:.25rem 0}
.d{width:2.5rem;height:2.5rem;margin:auto;border-radius:50%;border:3px solid var(--mut);border-top-color:var(--ac);
animation:s 1s linear infinite}@keyframes s{to{transform:rotate(1turn)}}
@media (prefers-reduced-motion:reduce){.d{animation:none}}</style></head>
<body><main><div class="d" role="img" aria-label="Loading"></div><h1>OneMind is starting</h1>
<p>Your box is waking up. This page reloads by itself and the dashboard appears when it is ready.</p>
<p>This usually takes about a minute after power-on.</p></main></body></html>
"""
PAGE_BYTES = PAGE.encode()
RESPONSE = (b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: " + str(len(PAGE_BYTES)).encode() + b"\r\nRetry-After: 3\r\nCache-Control: no-store\r\n"
            b"X-OneMind-Starting: 1\r\nConnection: close\r\n\r\n")
HEAD_RESPONSE = RESPONSE
GRACE_S = 3.0
POLL_S = 0.5


def bind(host: str, port: int) -> socket.socket:
    """Same options as the gateway's _bind (SO_REUSEPORT is what lets the two share the port)."""
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind((host, port))
    sock.listen(128)
    return sock


def answer(conn: socket.socket, ctx: ssl.SSLContext | None) -> None:
    try:
        conn.settimeout(5)
        if ctx is not None:
            conn = ctx.wrap_socket(conn, server_side=True)
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = conn.recv(2048)
            if not chunk:
                break
            data += chunk
        conn.sendall(HEAD_RESPONSE if data.startswith(b"HEAD ") else RESPONSE + PAGE_BYTES)
    except (OSError, ssl.SSLError):
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def serve(sock: socket.socket, ctx: ssl.SSLContext | None, stop: threading.Event) -> None:
    sock.settimeout(0.2)
    while not stop.is_set():
        try:
            conn, _ = sock.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        threading.Thread(target=answer, args=(conn, ctx), daemon=True).start()


def gateway_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as r:  # loopback only
            return r.status == 200
    except (OSError, ValueError):
        return False


def notify(state: str) -> None:
    """sd_notify without libsystemd: Type=notify makes the gateway wait (After=) until the page listens."""
    path = os.environ.get("NOTIFY_SOCKET", "")
    if not path:
        return
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        s.sendto(state.encode(), "\0" + path[1:] if path.startswith("@") else path)
    except OSError:
        pass
    finally:
        s.close()


def run(env: dict[str, str], ready=gateway_ready, grace: float = GRACE_S, poll: float = POLL_S) -> int:
    if env.get("ONEMIND_NET_TLS") != "1":       # no HTTPS on this box: nothing to hold
        notify("READY=1")
        return 0
    from onemind_core.ca import BoxCA          # the gateway venv
    tls_dir = env.get("ONEMIND_NET_TLS_DIR") or os.path.join(env.get("ONEMIND_DATA_DIR", "."), "tls")
    from onemind_core.ca import existing_box_name
    # The CA's own box name wins over ONEMIND_NET_BOX_NAME (the first-boot name) so this stays in step with the gateway.
    box = existing_box_name(Path(tls_dir)) or env.get("ONEMIND_NET_BOX_NAME") or "onemind"
    cert = BoxCA(Path(tls_dir), box).ensure_https_cert()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert.cert_path), str(cert.key_path))
    host = env.get("ONEMIND_NET_HTTPS_HOST", "0.0.0.0")
    ports = [int(p) for p in env.get("ONEMIND_NET_HTTPS_PORTS", "443,8443").split(",") if p.strip()]
    socks = [bind(host, p) for p in ports]
    stop = threading.Event()
    threads = [threading.Thread(target=serve, args=(s, ctx, stop), daemon=True) for s in socks]
    for t in threads:
        t.start()
    notify("READY=1")
    url = f"http://127.0.0.1:{env.get('ONEMIND_PORT', '8080')}/healthz"
    while not ready(url):
        time.sleep(poll)
    time.sleep(grace)                            # overlap with the gateway's own listener
    stop.set()
    for t in threads:
        t.join(1)
    for s in socks:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(run(dict(os.environ)))
