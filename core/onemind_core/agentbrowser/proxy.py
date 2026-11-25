# SPDX-License-Identifier: Apache-2.0
"""The agent browser's only way out: an HTTPS CONNECT proxy inside the gateway (#694).

The browser pod's NetworkPolicy lets it reach nothing but this port (pods.py). Each CONNECT names a
host; the proxy asks the session service whether this session's agent may reach it (authorize),
then resolves the name itself and connects only to a global unicast address, so an approved name
that points into the box or the LAN is still refused. Plain-HTTP proxying is refused (https only).
A session that ends (owner, agent, budget, lifetime, kill switch) has its open tunnels closed.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import socket
from collections.abc import Awaitable, Callable

from .policy import public_address

log = logging.getLogger("onemind.agentbrowser.proxy")

HEAD_LIMIT = 8192
IDLE_S = 120.0
# authorize(session_id, proxy_token, host, port) -> None to allow, else the refusal reason.
Authorize = Callable[[str, str, str, int], str | None]
Dial = Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


async def _resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [i[4][0] for i in infos]


class EgressRefused(Exception):
    pass


class EgressProxy:
    def __init__(self, authorize: Authorize, *, resolve: Callable[[str, int], Awaitable[list[str]]] = _resolve,
                 dial: Dial | None = None):
        self.authorize = authorize
        self.resolve = resolve
        self.dial = dial or self._dial_public
        self.server: asyncio.base_events.Server | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._tunnels: dict[str, set[asyncio.StreamWriter]] = {}

    @property
    def port(self) -> int | None:
        if self.server is None or not self.server.sockets:
            return None
        return self.server.sockets[0].getsockname()[1]

    async def start(self, host: str, port: int) -> None:
        self.loop = asyncio.get_running_loop()
        self.server = await asyncio.start_server(self._handle, host, port, limit=HEAD_LIMIT)

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            for sid in list(self._tunnels):
                self._close_now(sid)
            await self.server.wait_closed()
            self.server = None

    def close_session(self, session_id: str) -> None:
        """Close every open tunnel of a session; safe to call from any thread."""
        if self.loop is None or self.loop.is_closed():
            return
        try:
            self.loop.call_soon_threadsafe(self._close_now, session_id)
        except RuntimeError:  # the loop stopped meanwhile
            pass

    def _close_now(self, session_id: str) -> None:
        for w in self._tunnels.pop(session_id, set()):
            w.close()

    async def _dial_public(self, host: str, port: int):
        addrs = [a for a in await self.resolve(host, port) if public_address(a)]
        if not addrs:
            raise EgressRefused("not_public")
        return await asyncio.wait_for(asyncio.open_connection(addrs[0], port), 10)

    @staticmethod
    def _credentials(lines: list[str]) -> tuple[str, str]:
        for line in lines:
            name, _, value = line.partition(":")
            if name.strip().lower() == "proxy-authorization":
                scheme, _, b64 = value.strip().partition(" ")
                if scheme.lower() == "basic":
                    try:
                        user, _, pw = base64.b64decode(b64, validate=True).decode().partition(":")
                    except (ValueError, UnicodeDecodeError):
                        break
                    return user, pw
        return "", ""

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async def refuse(status: str) -> None:
            writer.write(f"HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
            try:
                await writer.drain()
            finally:
                writer.close()

        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            writer.close()
            return
        lines = head.decode("latin-1").split("\r\n")
        method, _, rest = lines[0].partition(" ")
        target = rest.partition(" ")[0]
        if method != "CONNECT":
            return await refuse("405 Method Not Allowed")
        host, _, port_s = target.rpartition(":")
        sid, token = self._credentials(lines[1:])
        if not sid:
            return await refuse("407 Proxy Authentication Required")
        try:
            port = int(port_s)
        except ValueError:
            return await refuse("400 Bad Request")
        if self.authorize(sid, token, host.lower(), port) is not None:
            return await refuse("403 Forbidden")
        try:
            up_r, up_w = await self.dial(host.lower(), port)
        except EgressRefused:
            return await refuse("403 Forbidden")
        except (OSError, asyncio.TimeoutError):
            return await refuse("502 Bad Gateway")
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        tunnels = self._tunnels.setdefault(sid, set())
        tunnels.update((writer, up_w))
        try:
            await asyncio.gather(self._pipe(reader, up_w), self._pipe(up_r, writer))
        finally:
            tunnels.discard(writer)
            tunnels.discard(up_w)
            for w in (writer, up_w):
                w.close()

    @staticmethod
    async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while data := await asyncio.wait_for(src.read(65536), IDLE_S):
                dst.write(data)
                await dst.drain()
        except (asyncio.TimeoutError, ConnectionError, OSError):
            pass
        finally:
            dst.close()
