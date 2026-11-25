# SPDX-License-Identifier: Apache-2.0
"""The console broker: the owner's browser reaches a machine's screen through the gateway (MACH-4, #281).

The browser (noVNC, unmodified) opens `GET /v1/machines/<name>/console/ws?ticket=...` as a WebSocket.
The ticket is the one `POST /v1/machines/<name>/console` gave an owner: one minute, single use, bound
to the machine. The broker then pumps bytes between the browser and the machine's VNC display.

Rules, each with a test (core/tests/test_machines_console.py):
- a ticket works once, for its machine, inside its minute; anything else closes with 1008;
- one controlling console per machine: a second one takes over and the first closes with 4001;
- `view=1` is a screen with no hands: keyboard, pointer and clipboard messages are dropped, and
  anything the broker cannot parse closes the session (fail closed);
- a client too slow to keep up is cut at a byte cap instead of growing the gateway's memory;
- nothing is recorded but who opened and closed it (no screen content, no keystrokes).

The VNC display comes from a `ConsoleUpstream`. The real one asks the Kubernetes API (through a
loopback `kubectl proxy`) for KubeVirt's VNC subresource, which is how `virtctl vnc` reaches it. That
path is UNVERIFIED on hardware until LT-MACH-2 runs on a KVM box; the broker above it is not.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import struct
from collections.abc import Callable
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket, WebSocketState

from .spec import NAMESPACE

PATH = re.compile(r"^/v1/machines/([a-z][a-z0-9-]{0,38}[a-z0-9])/console/ws$")
HIGH_WATER = 8 * 1024 * 1024  # bytes queued for a client that is not reading: past this it is cut
CLOSE_SUPERSEDED = 4001
CLOSE_TOO_SLOW = 4002


class Upstream(Protocol):
    async def recv(self) -> bytes | None: ...  # None when the display closed

    async def send(self, data: bytes) -> None: ...

    async def close(self) -> None: ...


class ConsoleUpstream(Protocol):
    async def open(self, machine: str) -> Upstream: ...


# ---- view-only: drop what a person would type -----------------------------------------------------
class ViewOnlyFilter:
    """Reads the RFB client stream (RFC 6143 §7) and passes only what cannot touch the guest.

    Phases: 12-byte version, 1-byte security choice (only 1, "None", is understood), 1-byte ClientInit,
    then client messages. SetPixelFormat, SetEncodings and FramebufferUpdateRequest go through; key,
    pointer and cut-text messages are dropped. A byte the filter cannot place raises `Refused`.
    """

    class Refused(Exception):
        pass

    def __init__(self) -> None:
        self.buf = b""
        self.phase = "version"

    def feed(self, data: bytes) -> bytes:
        self.buf += data
        out = bytearray()
        while True:
            n = self._next_len()
            if n is None or len(self.buf) < n:
                return bytes(out)
            msg, self.buf = self.buf[:n], self.buf[n:]
            if self._passes(msg):
                out += msg

    def _next_len(self) -> int | None:
        if self.phase == "version":
            return 12
        if self.phase in ("security", "init"):
            return 1
        if not self.buf:
            return None
        t = self.buf[0]
        if t == 0:
            return 20
        if t == 2:
            return 4 + 4 * struct.unpack(">H", self.buf[2:4])[0] if len(self.buf) >= 4 else None  # SetEncodings
        if t == 3:
            return 10
        if t == 5:
            return 6
        if t == 4:
            return 8
        if t == 6:
            return 8 + struct.unpack(">I", self.buf[4:8])[0] if len(self.buf) >= 8 else None
        if t == 255 and len(self.buf) >= 2 and self.buf[1] == 0:
            return 12  # QEMU extended key event
        raise self.Refused(f"unknown RFB message type {t}")

    def _passes(self, msg: bytes) -> bool:
        if self.phase == "version":
            self.phase = "security"
            return True
        if self.phase == "security":
            if msg[0] != 1:
                raise self.Refused("view-only needs a console without a password")
            self.phase = "init"
            return True
        if self.phase == "init":
            self.phase = "messages"
            return True
        return msg[0] in (0, 2, 3)


# ---- the broker -----------------------------------------------------------------------------------
class Session:
    def __init__(self, ws: WebSocket, view_only: bool):
        self.ws, self.view_only = ws, view_only
        self.superseded = False
        self.stop = asyncio.Event()  # set when another console takes over


class ConsoleBroker:
    def __init__(self, redeem: Callable[[str, str], dict | None], upstream: ConsoleUpstream | None,
                 audit: Callable[[str, dict | None, dict], None], high_water: int = HIGH_WATER):
        self.redeem, self.upstream, self.audit, self.high_water = redeem, upstream, audit, high_water
        self.controlling: dict[str, Session] = {}
        self._closing: set[asyncio.Task] = set()

    async def handle(self, scope: Scope, receive: Receive, send: Send, name: str) -> None:
        ws = WebSocket(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        ticket = (query.get("ticket") or [""])[0]
        view_only = (query.get("view") or ["0"])[0] == "1"
        origin = headers.get("origin")
        if origin is not None and (urlsplit(origin).netloc.lower() != headers.get("host", "").lower()):
            return await ws.close(1008)  # a page of another site cannot borrow the owner's ticket
        granted = self.redeem(ticket, name)
        if granted is None:
            return await ws.close(1008)
        if self.upstream is None:
            return await ws.close(1013, "This box has no machine runtime, so there is no screen to show.")
        try:
            display = await self.upstream.open(name)
        except Exception:  # the cluster said no, or is not there: the owner sees one plain close
            return await ws.close(1011, "The machine's screen is not available right now.")
        await ws.accept(subprotocol=_binary_subprotocol(scope))
        session = Session(ws, view_only)
        previous = self.controlling.get(name)
        self.controlling[name] = session
        if previous is not None:
            previous.superseded = True
            previous.stop.set()
            with contextlib.suppress(Exception):
                await previous.ws.close(CLOSE_SUPERSEDED, "Another console took over.")
        self.audit("machines.console.opened", granted, {"machine": name, "view_only": view_only})
        try:
            await self._pump(session, display)
        finally:
            # No await in here that a cancelled request could skip: the server cancels a handler on
            # shutdown, and the record and the display must still be let go.
            if self.controlling.get(name) is session:
                del self.controlling[name]
            self.audit("machines.console.closed", granted, {"machine": name})
            task = asyncio.ensure_future(display.close())
            self._closing.add(task)
            task.add_done_callback(self._closing.discard)

    async def _pump(self, s: Session, display: Upstream) -> None:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        queued = 0
        cut = asyncio.Event()

        async def from_display() -> None:
            nonlocal queued
            while (chunk := await display.recv()) is not None:
                queued += len(chunk)
                if queued > self.high_water:
                    cut.set()
                    return
                queue.put_nowait(chunk)
            queue.put_nowait(None)

        async def to_client() -> None:
            nonlocal queued
            while (chunk := await queue.get()) is not None:
                queued -= len(chunk)
                await s.ws.send_bytes(chunk)

        async def from_client() -> None:
            filt = ViewOnlyFilter() if s.view_only else None
            while True:
                msg = await s.ws.receive()
                if msg["type"] == "websocket.disconnect":
                    return
                data = msg.get("bytes")
                if data is None:
                    continue  # RFB is binary; text frames carry nothing for the display
                if filt is not None:
                    data = filt.feed(data)  # may raise Refused: the session ends
                if data:
                    await display.send(data)

        feeder = asyncio.create_task(from_display())
        ending = [asyncio.create_task(c) for c in (to_client(), from_client(), cut.wait(), s.stop.wait())]
        for t in (feeder, *ending):
            t.add_done_callback(lambda t: t.cancelled() or t.exception())  # a failed pump half ends the session, quietly
        try:
            await asyncio.wait(ending, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (feeder, *ending):
                t.cancel()
        if s.ws.application_state == WebSocketState.CONNECTED and not s.superseded:
            with contextlib.suppress(Exception):
                await s.ws.close(CLOSE_TOO_SLOW if cut.is_set() else 1000)


def _binary_subprotocol(scope: Scope) -> str | None:
    offered = scope.get("subprotocols") or []
    return "binary" if "binary" in offered else None  # noVNC offers "binary"


class ConsoleMiddleware:
    """ASGI middleware: console WebSockets go to the broker, everything else to the gateway app.

    A middleware, not a route: the ticket is the credential here (a browser cannot set headers on a
    WebSocket), so the route-by-principal matrix of core/tests/sec_policy.py does not describe it.
    The ticket itself is only ever minted by an owner (routers/machines.py)."""

    def __init__(self, app: ASGIApp, broker: ConsoleBroker):
        self.app, self.broker = app, broker

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            m = PATH.match(scope.get("path", ""))
            if m:
                return await self.broker.handle(scope, receive, send, m.group(1))
        await self.app(scope, receive, send)


# ---- the real display: KubeVirt's VNC subresource through a loopback `kubectl proxy` ----------------
VNC_PATH = "/apis/subresources.kubevirt.io/v1/namespaces/{ns}/virtualmachineinstances/{name}/vnc"
PROXY_LINE = re.compile(r"Starting to serve on 127\.0\.0\.1:(\d+)")


def vnc_url(port: int, name: str) -> str:
    return f"ws://127.0.0.1:{port}" + VNC_PATH.format(ns=NAMESPACE, name=name)


class KubectlProxyUpstream:
    """UNVERIFIED on hardware (LT-MACH-2): spawns `kubectl proxy --port=0 --address=127.0.0.1`, which
    only the gateway can reach, and opens the VNC subresource with KubeVirt's `plain.kubevirt.io`
    subprotocol. One proxy per open console, killed when the console closes."""

    def __init__(self, kubectl: str = "kubectl", start_timeout_s: float = 10):
        self.kubectl, self.start_timeout_s = kubectl, start_timeout_s

    async def open(self, machine: str) -> Upstream:
        from websockets.asyncio.client import connect

        proc = await asyncio.create_subprocess_exec(
            self.kubectl, "proxy", "--port=0", "--address=127.0.0.1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            assert proc.stdout is not None
            line = await asyncio.wait_for(proc.stdout.readline(), self.start_timeout_s)
            m = PROXY_LINE.search(line.decode("latin-1"))
            if not m:
                raise RuntimeError("kubectl proxy did not report a port")
            ws = await connect(vnc_url(int(m.group(1)), machine), subprotocols=["plain.kubevirt.io"],
                               proxy=None, max_size=8 * 1024 * 1024, compression=None, open_timeout=self.start_timeout_s)
        except BaseException:
            proc.kill()
            await proc.wait()
            raise
        return _WsUpstream(ws, proc)


class _WsUpstream:
    def __init__(self, ws, proc):
        self.ws, self.proc = ws, proc

    async def recv(self) -> bytes | None:
        from websockets.exceptions import ConnectionClosed
        try:
            data = await self.ws.recv()
        except ConnectionClosed:
            return None
        return data if isinstance(data, bytes) else data.encode()

    async def send(self, data: bytes) -> None:
        await self.ws.send(data)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.ws.close()
        if self.proc.returncode is None:
            self.proc.kill()
        await self.proc.wait()

