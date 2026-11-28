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
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from .fanout import AssetValue

log = logging.getLogger("onemind.gateway")

UNAUTH_AUDIT_INTERVAL_S = 60

Hook = Callable[[], Awaitable[None] | None]
# A credential resolver a feature adds (identity: sessions, API tokens). Given the request and the
# bearer token (None when there is no Authorization header), it returns a Principal, None when the
# credential is not its own, or raises ApiError to refuse (scope, CSRF).
Authenticator = Callable[[Request, str | None], Principal | None]
# Runs before an owner approval; raises ApiError to refuse it (identity: passkey step-up, F-2).
ApprovalGuard = Callable[[Principal, str, dict, Request], None]
# Given the id an approval guard was called with, who asked for it ({"id", "kind", ...}), or None
# when the id is not this feature's. Every feature with its own approvable requests (files: frq_...)
# registers one, so a guard can judge the requester, not only the approver (CORE-SEC-6).
RequesterLookup = Callable[[str], dict | None]
# Resolves a feature's approval request for the shared step-up challenge.
ApprovalLookup = Callable[[Principal, str], dict | None]
# Whether this principal may see and open an installed app (identity: per-app sharing, §12.6).
AppFilter = Callable[[Request, Principal, str], bool]
# (request, principal, value) -> may this caller see that asset value? `value` is a fanout.AssetValue:
# asset_class, asset_id, field, revision and the stored onemind.datapoint/v1, so a data class can be
# judged per stream (e.g. location on a position field) without changing this signature (#606).
# Every filter must say yes before an asset value reaches a stream; data classes and grants add theirs.
AssetFilter = Callable[[Request, Principal, "AssetValue"], bool]
# Person id -> role of every active person a feature knows, beyond the tokens file (identity:
# household accounts, §12.6). Notifications use it to find who to notify.
PeopleSource = Callable[[], dict[str, str]]
# Runs on every authenticated request after the caller is known; raises ApiError to refuse it
# (agent kill switch, CORE-SEC-6: every agent principal is refused while the owner has it on).
PrincipalGuard = Callable[[Request, Principal], None]


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
    # CORE-DEPLOY-2: the on-box image scanner (appstore/imagescan.py); None means none is installed.
    image_scanner: Any = None
    # #601: the hub's core JetStream streams and buckets (jetstream.JetStreamCore), set by routers/jetstream.py.
    jetstream: Any = None
    authenticators: list[Authenticator] = field(default_factory=list)
    approval_guards: list[ApprovalGuard] = field(default_factory=list)
    requester_lookups: list[RequesterLookup] = field(default_factory=list)
    approval_lookups: list[ApprovalLookup] = field(default_factory=list)
    app_filters: list[AppFilter] = field(default_factory=list)
    asset_filters: list[AssetFilter] = field(default_factory=list)
    # #606: the current asset values from the hub's asset-state bucket (fanout.AssetState), set by routers/events.py.
    assets: Any = None
    # Ids of built-in apps the owner switched off (appstore/system.py). They are left out of
    # GET /v1/apps (so the dock, search, MCP tools and phone) and their routes answer 409 app_disabled.
    disabled_apps: Callable[[], frozenset[str]] = lambda: frozenset()
    people_sources: list[PeopleSource] = field(default_factory=list)
    principal_guards: list[PrincipalGuard] = field(default_factory=list)
    # Per event domain: adds display fields (a task title) to an ids-only event when the notifier renders it.
    # Events and the audit log carry ids only, because every adult can read the audit log.
    notify_enrichers: dict[str, Callable[[dict], dict]] = field(default_factory=dict)
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

    def from_features(request: Request, token: str | None) -> Principal | None:
        for authenticate in gw.authenticators:
            p = authenticate(request, token)
            if p is not None:
                return p
        return None

    def principal(request: Request) -> Principal:
        p = authenticate(request)
        for guard in gw.principal_guards:  # e.g. the agent kill switch; raises to refuse
            guard(request, p)
        return p

    def authenticate(request: Request) -> Principal:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            p = from_features(request, None)  # e.g. a session cookie (identity, §12.6)
            if p is None:
                raise reject_unauthenticated(request, "missing bearer token")
            return p
        token = token.strip()
        p = gw.tokens.lookup(token)
        if p is None:  # §11.2: agent principals issued to apps, stored hashed in the database
            principal_id = gw.repo.agent_principal_for(token_hash(token))
            p = agent_principal(principal_id) if principal_id else None
        if p is None:
            p = from_features(request, token)
        if p is None:
            raise reject_unauthenticated(request, "unknown token")
        return p

    return principal
