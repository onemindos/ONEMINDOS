"""FastAPI application: the REST surface of contract §3, the MCP endpoint of §11.3, and the dashboard.

Route groups live in routers/<area>.py; ROUTERS below is the one registry (one import and one
entry per feature, `static` last). How to add a feature: docs/leap/core/PLUMBING.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from . import __version__, ledger
from .actions import ActionService
from .audit import AuditLog
from .auth import TokenStore
from .bus import NatsBus
from .catalog import Catalog
from .config import Settings
from .context import UNAUTH_AUDIT_INTERVAL_S, Gateway, principal_dependency
from .errors import install_handlers
from .events import EventHub
from .executors import Executor, NoopExecutor, make_executor
from .ledger import ActionRepository, SqlActionRepository
from .nodes import NodeRegistry
from .routers import Register
from .routers import actions as actions_routes
from .routers import apps as apps_routes
from .routers import instance as instance_routes
from .routers import mcp as mcp_routes
from .routers import nodes as nodes_routes
from .routers import override as override_routes
from .routers import secrets as secrets_routes
from .routers import static as static_routes
from .routers.static import API_EXACT, API_TREES, is_api_path
from .store import Database, migrate

__all__ = ["API_EXACT", "API_TREES", "ROUTERS", "UNAUTH_AUDIT_INTERVAL_S", "create_app", "is_api_path", "utcnow"]

log = logging.getLogger("onemind.gateway")

# The router registry. Order is route order (and /openapi.json order); static must stay last.
ROUTERS: list[Register] = [
    instance_routes.register,
    nodes_routes.register,
    apps_routes.register,
    mcp_routes.register,
    actions_routes.register,
    secrets_routes.register,
    override_routes.register,
    static_routes.register,
]


def utcnow() -> datetime:
    return datetime.now(UTC)


def create_app(
    settings: Settings | None = None,
    *,
    clock: Callable[[], datetime] = utcnow,
    executor: Executor | None = None,
    repo: ActionRepository | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.check()  # refuses ONEMIND_ALLOW_UNSCANNED with the kubernetes executor
    tokens = TokenStore(settings.tokens_file)
    registry = NodeRegistry(clock)
    bus = NatsBus(settings.nats_url, registry)
    audit = AuditLog(settings.audit_path, clock, publish=bus.publish_threadsafe)
    catalog = Catalog(settings.apps_dir, settings.app_schema_path)
    owns_repo = repo is None
    repo = repo or SqlActionRepository.from_url(settings.db_url)
    # Feature tables share the ledger's engine; a repo without one (a test double) gets its own.
    engine = getattr(repo, "engine", None)
    owns_engine = engine is None
    db = Database(engine if engine is not None else ledger.make_engine(settings.db_url))
    migrate(db.engine)
    executor = executor or make_executor(settings.executor, settings.kubectl, settings.executor_timeout_s)
    # §11.1: the scan check is skipped only on explicit request, and only when nothing real runs.
    skip_scan = settings.allow_unscanned and settings.executor == "noop" and isinstance(executor, NoopExecutor)
    if settings.allow_unscanned and not skip_scan:
        raise ValueError("ONEMIND_ALLOW_UNSCANNED=1 is honoured only with the noop executor")
    if skip_scan:
        log.warning(
            "ONEMIND_ALLOW_UNSCANNED=1: installs are approved WITHOUT a passing scan (dev only, noop executor)"
        )
    gateway_url = settings.gateway_url()
    if settings.public_url is None:
        log.info("ONEMIND_PUBLIC_URL not set; app agent Secrets will use %s", gateway_url)
    actions = ActionService(
        repo, catalog, executor, audit, clock, gateway_url=gateway_url, require_scan=not skip_scan
    )
    actions.reconcile_interrupted()  # finish what a crashed or killed process left mid-dispatch
    gw = Gateway(
        settings=settings, clock=clock, tokens=tokens, registry=registry, bus=bus, audit=audit,
        events=EventHub(audit, clock, publish=bus.publish_threadsafe, instance_id=settings.node_id),
        catalog=catalog, repo=repo, db=db, executor=executor, actions=actions, skip_scan=skip_scan,
    )
    gw.principal = principal_dependency(gw)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await bus.start()
        audit.append(
            "gateway.started", None, None,
            {"version": __version__, "executor": executor.name, "scan_check": not skip_scan},
        )
        try:
            await gw.run_startup()
            yield
        finally:
            await gw.run_shutdown()
            await bus.stop()
            if owns_repo and hasattr(repo, "close"):
                repo.close()
            if owns_engine:
                db.engine.dispose()

    app = FastAPI(
        title="OneMind OS Core gateway",
        version=__version__,
        description="Contract: sdk/contracts/poc-v0.md section 3. AI never actuates without human approval.",
        lifespan=lifespan,
        # Contract section 3: only /healthz (and /openapi.json) are open; no Swagger/ReDoc UIs.
        docs_url=None,
        redoc_url=None,
    )
    install_handlers(app)
    app.state.settings = settings
    app.state.registry = registry
    app.state.audit = audit
    app.state.catalog = catalog
    app.state.actions = actions
    app.state.repo = repo
    app.state.bus = bus
    app.state.tokens = tokens
    app.state.gateway = gw
    app.state.events = gw.events

    for register in ROUTERS:
        register(app, gw)
    return app
