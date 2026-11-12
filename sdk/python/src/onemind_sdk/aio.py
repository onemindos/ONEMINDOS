# SPDX-License-Identifier: Apache-2.0
"""The asyncio client: the same surface as onemind_sdk.Client, with `await`.

Derived from client.py by sdk/python/scripts/make_aio.py; edit client.py and rerun it."""

from __future__ import annotations

import asyncio
import time
import warnings
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from . import _core as core
from ._gen.models import Action, AuditRecord, AuditVerify, CatalogApp, Instance, Node
from .errors import AmbiguousResult, NetworkError, OneMindError, Unauthenticated


class Client:
    """A OneMind gateway client. The token is sent only in the Authorization header and is never
    part of repr(), errors or logs."""

    def __init__(self, base_url: str, token: str = "", *, timeout: float = core.DEFAULT_TIMEOUT_S, retries: int = 3,
                 principal: str | None = None, transport: httpx.AsyncBaseTransport | None = None,
                 refresh: Callable[[], Awaitable[str | None]] | None = None, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 trace: Callable[[str, str, int, float], None] | None = None):
        self.base_url = core.normalize_hub_url(base_url)
        self._token = token
        self._attempts = max(1, retries)
        self._principal = principal
        self._refresh = refresh
        self._sleep = sleep
        self._trace = trace
        self._offset = timedelta(0)
        self._warned = False
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=transport,
                                  headers={"User-Agent": f"onemind-sdk-python/{core.VERSION}"})
        self.instance = _Instance(self)
        self.nodes = _Nodes(self)
        self.apps = _Apps(self)
        self.actions = _Actions(self)
        self.audit = _Audit(self)
        self.events = _Events(self)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, **kw: Any) -> Client:
        hub, token = core.from_env(env)
        return cls(hub, token, **kw)

    def __repr__(self) -> str:
        return f"OneMind(hub={self.base_url}, principal={self._principal or '?'})"

    async def __aenter__(self) -> Client:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    def hub_now(self) -> datetime:
        return datetime.now(UTC) + self._offset

    async def healthz(self) -> bool:
        return bool((await self.call(core.Req("GET", "/healthz", retry=True)) or {}).get("ok"))

    # ---- transport ---------------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        h = {"Accept": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _check(self) -> None:
        msg = core.plain_http_warning(self.base_url)
        if msg and not self._warned:
            self._warned = True
            warnings.warn(f"onemind: {msg}", stacklevel=3)

    async def _once(self, r: core.Req) -> tuple[Any, httpx.Headers]:
        start = time.monotonic()
        try:
            resp = await self._http.request(r.method, r.path, json=r.body, headers={**self._headers(), **r.headers})
        except httpx.HTTPError as exc:
            if self._trace:
                self._trace(r.method, r.path.split("?")[0], 0, time.monotonic() - start)
            raise core.network_error(exc, self._token) from None
        if self._trace:
            self._trace(r.method, r.path.split("?")[0], resp.status_code, time.monotonic() - start)
        off = core.hub_offset(resp)
        if off is not None:
            self._offset = off
        return core.parse(resp), resp.headers

    async def request(self, r: core.Req) -> tuple[Any, httpx.Headers]:
        self._check()
        attempts = self._attempts if r.retry else 1
        refreshed, last = False, None
        i = 0
        while i < attempts:
            if i:
                await self._sleep(core.backoff(i, getattr(last, "retry_after_s", None)))
            try:
                return await self._once(r)
            except OneMindError as e:
                last = e
                if isinstance(e, Unauthenticated) and not refreshed and self._refresh:
                    refreshed = True
                    new = await self._refresh()
                    if new:
                        self._token = new
                        continue
                if not (isinstance(e, NetworkError) or e.status in core.RETRY_STATUSES):
                    raise
            i += 1
        assert last is not None
        raise last

    async def call(self, r: core.Req) -> Any:
        return (await self.request(r))[0]


class _Ns:
    def __init__(self, c: Client):
        self.c = c


class _Instance(_Ns):
    async def get(self) -> Instance:
        return Instance.model_validate(await self.c.call(core.Req("GET", "/v1/instance", retry=True)))


class _Nodes(_Ns):
    async def list(self) -> list[Node]:
        return [Node.model_validate(n) for n in await self.c.call(core.Req("GET", "/v1/nodes", retry=True))]

    async def get(self, node_id: str) -> Node:
        return Node.model_validate(await self.c.call(core.Req("GET", f"/v1/nodes/{core.pid(node_id)}", retry=True)))


class _Apps(_Ns):
    async def list(self) -> list[CatalogApp]:
        return [CatalogApp.model_validate(a) for a in await self.c.call(core.Req("GET", "/v1/apps", retry=True))]


class _Actions(_Ns):
    async def request(self, type: str, app_id: str, *, expires_in: timedelta | None = None,
                idempotency_key: str | None = None) -> Action:
        """actions.create: files the action in awaiting_approval; retried with one idempotency key."""
        await self.c.instance.get()  # learn the hub clock first
        r = core.action_request(type, app_id, self.c.hub_now(), expires_in, idempotency_key)
        return Action.model_validate(await self.c.call(r))

    async def list(self) -> list[Action]:
        return [Action.model_validate(a) for a in await self.c.call(core.Req("GET", "/v1/actions", retry=True))]

    async def get(self, action_id: str) -> Action:
        return Action.model_validate(await self.c.call(core.Req("GET", f"/v1/actions/{core.pid(action_id)}", retry=True)))

    async def approve(self, action_id: str) -> Action:
        return await self._decide(action_id, "approve")

    async def deny(self, action_id: str) -> Action:
        return await self._decide(action_id, "deny")

    async def _decide(self, action_id: str, verb: str) -> Action:
        try:
            return Action.model_validate(await self.c.call(core.Req("POST", f"/v1/actions/{core.pid(action_id)}/{verb}")))
        except OneMindError as e:
            if e.status and e.status < 500:
                raise
        try:
            got = await self.get(action_id)
        except OneMindError:
            raise AmbiguousResult(f"{verb} may or may not have been applied; check the action") from None
        if got.state != "awaiting_approval" and self.c._principal and got.decided_by and got.decided_by.id == self.c._principal:
            return got
        raise AmbiguousResult(f"{verb} may or may not have been applied; the action is now {got.state}", got)

    async def wait(self, action_id: str, *, every: float = 2.0, timeout: float | None = None,
             on_change: Callable[[Action], None] | None = None) -> Action:
        deadline = None if timeout is None else time.monotonic() + timeout
        last = ""
        while True:
            a = await self.get(action_id)
            if a.state != last:
                last = a.state
                if on_change:
                    on_change(a)
            if a.state in core.TERMINAL or (deadline is not None and time.monotonic() >= deadline):
                return a
            await self.c._sleep(every)


class _Audit(_Ns):
    async def list(self, **q: Any) -> tuple[list[AuditRecord], bool]:
        """audit.events.list; the bool is True when more records follow (Link rel=next)."""
        body, headers = await self.c.request(core.Req("GET", core.audit_query(**q), retry=True))
        return [AuditRecord.model_validate(x) for x in body], 'rel="next"' in headers.get("link", "")

    async def get(self, seq: int) -> AuditRecord:
        return AuditRecord.model_validate(await self.c.call(core.Req("GET", f"/v1/audit/events/{int(seq)}", retry=True)))

    async def verify(self) -> AuditVerify:
        return AuditVerify.model_validate(await self.c.call(core.Req("GET", "/v1/audit/verify", retry=True)))


class _Events(_Ns):
    async def subscribe(self, types: list[str] | None = None, since_id: str | None = None,
                  silence_s: float = 45.0) -> AsyncIterator[dict]:
        """Yield onemind.event/v1 dicts forever, reconnecting with backoff and Last-Event-ID.
        A 401/403/404 raises (404: this hub has no event stream yet; poll instead)."""
        last, delay = since_id or "", 1.0
        params = {"types": ",".join(types)} if types else None
        while True:
            self.c._check()
            headers = {**self.c._headers(), "Accept": "text/event-stream"}
            if last:
                headers["Last-Event-ID"] = last
            parser = core.SseParser()
            try:
                async with self.c._http.stream("GET", "/v1/events", params=params, headers=headers,
                                         timeout=httpx.Timeout(10.0, read=silence_s)) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        core.parse(resp)
                    delay = 1.0
                    async for text in resp.aiter_text():
                        for id_, ev in parser.feed(text):
                            if id_:
                                last = id_
                            yield ev
            except httpx.HTTPError:
                pass
            except OneMindError as e:
                if 400 <= e.status < 500 and e.status != 429:
                    raise
            if parser.retry_ms:
                delay = parser.retry_ms / 1000
            await self.c._sleep(delay / 2 + core.random.uniform(0, delay / 2))
            delay = min(30.0, delay * 2)
