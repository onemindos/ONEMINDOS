"""NATS connection for the gateway: heartbeat subscription in, audit publication out.

The gateway must work with NATS down (empty node list, audit still written to disk). So the
connection runs as a background task that keeps retrying, and nothing else waits on it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging

from nats.aio.client import Client

from .natsconf import load_seed
from .nodes import NodeRegistry

log = logging.getLogger("onemind.bus")

HEARTBEAT_SUBJECT = "onemind.node.*.status"
RETRY_S = 5.0


class SeedClient(Client):
    """nats-py's client, signing in with a user nkey seed file (`nkeys_seed=`) through `cryptography`.

    nats-py would import the `nkeys` package for that, which ships no wheel, so the image's
    --require-hashes --only-binary install cannot have it (#269). nats-py calls this hook when
    `nkeys_seed` is given and then sends `nkey` and `sig` in CONNECT, the same as with `nkeys`.
    """

    def _setup_nkeys_seed_connect(self) -> None:
        pub, sign = load_seed(self._nkeys_seed)
        self._public_nkey = pub
        self._signature_cb = lambda nonce: base64.b64encode(sign(nonce.encode()))


class NatsBus:
    def __init__(self, url: str | None, registry: NodeRegistry, nkey_seed=None):
        self.url = url
        self.nkey_seed = nkey_seed  # path of the gateway's NATS seed file, or None
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
                nc = SeedClient()
                await nc.connect(
                    self.url,
                    # CORE-SEC-4 (#161): the gateway's own service nkey on a strict hub.
                    **({"nkeys_seed": str(self.nkey_seed)} if self.nkey_seed else {}),
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

    def run_threadsafe(self, make, timeout_s: float):
        """Run the coroutine `make(nc)` on the bus loop from a request worker thread and wait for it, up
        to `timeout_s` (raises TimeoutError, or RuntimeError when NATS is not connected or this is the
        loop's own thread, where waiting would deadlock)."""
        if not self.connected or self._loop is None:
            raise RuntimeError("NATS is not connected")
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            raise RuntimeError("run_threadsafe called on the bus loop itself")
        fut = asyncio.run_coroutine_threadsafe(make(self.nc), self._loop)
        try:
            return fut.result(timeout_s)
        except BaseException:
            fut.cancel()
            raise

    def publish_threadsafe(self, subject: str, data: bytes, headers: dict[str, str] | None = None) -> None:
        """Fire-and-forget publish, callable from request worker threads. `headers` go with the message
        (a job carries Nats-Msg-Id = its job id, so the hub's job stream keeps one copy of a retry)."""
        if not self.connected or self._loop is None:
            return
        nc = self.nc
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        coro = nc.publish(subject, data, headers=headers) if headers else nc.publish(subject, data)
        if running is self._loop:
            self._loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
