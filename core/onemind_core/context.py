# SPDX-License-Identifier: Apache-2.0
"""The shared services every router and feature module is handed (docs/leap/core/PLUMBING.md).

`create_app` builds one `Gateway` and passes it to each entry of the router registry in app.py.
A feature reads what it needs from it (settings, clock, audit, events, db, ...) and may register
startup and shutdown hooks. Features never reach into each other's closures.
"""

from __future__ import annotations

import inspect
import logging
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import Request

from .actions import ActionService
from .audit import AuditLog
from .auth import Principal, TokenStore, agent_principal, token_hash
from .bus import NatsBus
from .catalog import Catalog
from .config import Settings
from .errors import ApiError
from .events import EventHub
from .executors import Executor
from .ledger import ActionRepository
from .nodes import NodeRegistry
from .store import Database

log = logging.getLogger("onemind.gateway")

UNAUTH_AUDIT_INTERVAL_S = 60

Hook = Callable[[], Awaitable[None] | None]


@dataclass
class Gateway:
    settings: Settings
    clock: Callable[[], datetime]
    tokens: TokenStore
    registry: NodeRegistry
    bus: NatsBus
    audit: AuditLog
    events: EventHub
    catalog: Catalog
    repo: ActionRepository
    db: Database
    executor: Executor
    actions: ActionService
    skip_scan: bool
    # FastAPI dependency resolving the caller's Principal (401 otherwise). Set by create_app.
    principal: Callable[..., Principal] = None  # type: ignore[assignment]
    _startup: list[Hook] = field(default_factory=list)
    _shutdown: list[Hook] = field(default_factory=list)

    def on_startup(self, hook: Hook) -> Hook:
        """Run hook (sync or async) at startup, after NATS is started and gateway.started is logged."""
        self._startup.append(hook)
        return hook

    def on_shutdown(self, hook: Hook) -> Hook:
        """Run hook at shutdown, in reverse registration order, before NATS stops."""
        self._shutdown.append(hook)
        return hook

    async def run_startup(self) -> None:
        for hook in self._startup:
            res = hook()
            if inspect.isawaitable(res):
                await res

    async def run_shutdown(self) -> None:
        for hook in reversed(self._shutdown):
            try:
                res = hook()
                if inspect.isawaitable(res):
                    await res
            except Exception:  # one feature failing to stop must not keep the others running
                log.exception("shutdown hook %r failed", hook)


def principal_dependency(gw: Gateway) -> Callable[[Request], Principal]:
    """The bearer-token dependency of contract §3 and §11.2.

    401s are decisions too, but an unauthenticated poller must not flood the log: at most one
    auth.rejected line per minute, carrying how many were suppressed since the previous one.
    """
    unauth: dict[str, Any] = {"last": None, "suppressed": 0}
    unauth_lock = threading.Lock()

    def reject_unauthenticated(request: Request, message: str) -> ApiError:
        now = gw.clock()
        with unauth_lock:
            last = unauth["last"]
            if last is not None and (now - last).total_seconds() < UNAUTH_AUDIT_INTERVAL_S:
                unauth["suppressed"] += 1
                return ApiError(401, "unauthenticated", message)
            suppressed, unauth["last"], unauth["suppressed"] = unauth["suppressed"], now, 0
        gw.audit.append(
            "auth.rejected", None, None,
            {"reason": message, "method": request.method, "path": request.url.path, "suppressed_since_last": suppressed},
        )
        return ApiError(401, "unauthenticated", message)

    def principal(request: Request) -> Principal:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise reject_unauthenticated(request, "missing bearer token")
        token = token.strip()
        p = gw.tokens.lookup(token)
        if p is None:  # §11.2: agent principals issued to apps, stored hashed in the database
            principal_id = gw.repo.agent_principal_for(token_hash(token))
            p = agent_principal(principal_id) if principal_id else None
        if p is None:
            raise reject_unauthenticated(request, "unknown token")
        return p

    return principal
