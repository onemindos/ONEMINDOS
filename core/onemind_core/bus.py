"""NATS connection for the gateway: heartbeat subscription in, audit publication out.

The gateway must work with NATS down (empty node list, audit still written to disk). So the
connection runs as a background task that keeps retrying, and nothing else waits on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

import nats

from .nodes import NodeRegistry

log = logging.getLogger("onemind.bus")

HEARTBEAT_SUBJECT = "onemind.node.*.status"
RETRY_S = 5.0


class NatsBus:
    def __init__(self, url: str | None, registry: NodeRegistry):
        self.url = url
        self.registry = registry
        self.nc = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    @property
    def connected(self) -> bool:
        return self.nc is not None and self.nc.is_connected

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        if self.url:
            self._task = asyncio.create_task(self._run(), name="nats-bus")
        else:
            log.info("ONEMIND_NATS_URL empty; running without NATS")

    async def _on_msg(self, msg) -> None:
        self.registry.ingest(msg.subject, msg.data)

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                nc = await nats.connect(
                    self.url,
                    connect_timeout=2,
                    allow_reconnect=True,
                    max_reconnect_attempts=-1,
                    reconnect_time_wait=2,
                    name="onemind-gateway",
                )
                await nc.subscribe(HEARTBEAT_SUBJECT, cb=self._on_msg)
                self.nc = nc
                log.info("connected to NATS")
                await self._stop.wait()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # NATS down: keep serving, retry later
                log.warning("NATS not reachable (%s); retrying in %.0fs", exc.__class__.__name__, RETRY_S)
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=RETRY_S)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        if self.nc is not None:
            with contextlib.suppress(Exception):
                await self.nc.drain()
            self.nc = None

    def publish_threadsafe(self, subject: str, data: bytes) -> None:
        """Fire-and-forget publish, callable from request worker threads."""
        if not self.connected or self._loop is None:
            return
        nc = self.nc
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._loop.create_task(nc.publish(subject, data))
        else:
            asyncio.run_coroutine_threadsafe(nc.publish(subject, data), self._loop)
