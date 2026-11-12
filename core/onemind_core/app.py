"""FastAPI application: the REST surface of contract section 3, plus the dashboard static files."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from . import __version__
from .actions import ActionRequest, ActionService
from .audit import AuditLog
from .auth import Principal, TokenStore
from .bus import NatsBus
from .catalog import Catalog
from .config import Settings
from .errors import ApiError, install_handlers
from .executors import Executor, make_executor
from .ledger import ActionRepository, SqlActionRepository
from .nodes import NodeRegistry

log = logging.getLogger("onemind.gateway")

UNAUTH_AUDIT_INTERVAL_S = 60

# Paths the SPA fallback never answers: the API tree (whole segment) and the open meta routes.
API_TREES = ("v1",)
API_EXACT = ("healthz", "openapi.json")


def is_api_path(full_path: str) -> bool:
    return full_path in API_EXACT or any(full_path == p or full_path.startswith(p + "/") for p in API_TREES)


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
    tokens = TokenStore(settings.tokens_file)
    registry = NodeRegistry(clock)
    bus = NatsBus(settings.nats_url, registry)
    audit = AuditLog(settings.audit_path, clock, publish=bus.publish_threadsafe)
    catalog = Catalog(settings.apps_dir, settings.app_schema_path)
    repo = repo or SqlActionRepository.from_url(settings.db_url)
    executor = executor or make_executor(settings.executor, settings.kubectl, settings.executor_timeout_s)
    actions = ActionService(repo, catalog, executor, audit, clock)
    actions.reconcile_interrupted()  # finish what a crashed or killed process left mid-dispatch

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await bus.start()
        audit.append("gateway.started", None, None, {"version": __version__, "executor": executor.name})
        try:
            yield
        finally:
            await bus.stop()

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

    # 401s are decisions too, but an unauthenticated poller must not flood the log: at most one
    # auth.rejected line per minute, carrying how many were suppressed since the previous one.
    unauth = {"last": None, "suppressed": 0}
    unauth_lock = threading.Lock()

    def reject_unauthenticated(request: Request, message: str) -> ApiError:
        now = clock()
        with unauth_lock:
            last = unauth["last"]
            if last is not None and (now - last).total_seconds() < UNAUTH_AUDIT_INTERVAL_S:
                unauth["suppressed"] += 1
                return ApiError(401, "unauthenticated", message)
            suppressed, unauth["last"], unauth["suppressed"] = unauth["suppressed"], now, 0
        audit.append(
            "auth.rejected", None, None,
            {"reason": message, "method": request.method, "path": request.url.path, "suppressed_since_last": suppressed},
        )
        return ApiError(401, "unauthenticated", message)

    def principal(request: Request) -> Principal:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise reject_unauthenticated(request, "missing bearer token")
        p = tokens.lookup(token.strip())
        if p is None:
            raise reject_unauthenticated(request, "unknown token")
        return p

    # ---- open ---------------------------------------------------------------------------
    @app.get("/healthz", tags=["meta"])
    def healthz():
        return {"ok": True}

    # ---- instance and nodes ---------------------------------------------------------------
    @app.get("/v1/instance", tags=["instance"])
    def instance(_: Principal = Depends(principal)):
        return {"name": settings.instance_name, "version": __version__, "hub_node_id": settings.node_id}

    @app.get("/v1/nodes", tags=["nodes"])
    def list_nodes(_: Principal = Depends(principal)):
        return registry.list()

    @app.get("/v1/nodes/{node_id}", tags=["nodes"])
    def get_node(node_id: str, _: Principal = Depends(principal)):
        node = registry.get(node_id)
        if node is None:
            raise ApiError(404, "not_found", "no such node")
        return node

    # ---- apps ---------------------------------------------------------------------------
    def _app_rows() -> list[dict]:
        states = repo.list_app_states()
        rows = []
        for app_id, entry in catalog.load().items():
            st = states.get(app_id)
            status = st.status if st else "not_installed"
            rows.append({**entry.summary(), "installed": status == "installed", "status": status})
        return rows

    @app.get("/v1/apps", tags=["apps"])
    def list_apps(_: Principal = Depends(principal)):
        return _app_rows()

    # ---- actions ------------------------------------------------------------------------
    @app.post("/v1/actions", tags=["actions"], status_code=201)
    def create_action(req: ActionRequest, p: Principal = Depends(principal)):
        body, created = actions.create(p, req)
        return JSONResponse(status_code=201 if created else 200, content=body)

    @app.get("/v1/actions", tags=["actions"])
    def list_actions(_: Principal = Depends(principal)):
        return actions.list()

    @app.get("/v1/actions/{action_id}", tags=["actions"])
    def get_action(action_id: str, _: Principal = Depends(principal)):
        return actions.get(action_id)

    @app.post("/v1/actions/{action_id}/approve", tags=["actions"])
    def approve_action(action_id: str, p: Principal = Depends(principal)):
        return actions.approve(p, action_id)

    @app.post("/v1/actions/{action_id}/deny", tags=["actions"])
    def deny_action(action_id: str, p: Principal = Depends(principal)):
        return actions.deny(p, action_id)

    # ---- dashboard static with SPA fallback (registered last) ----------------------------
    dist = settings.dashboard_dist.resolve() if settings.dashboard_dist else None

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if is_api_path(full_path) or dist is None or not dist.is_dir():
            raise ApiError(404, "not_found", "no such resource")
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_relative_to(dist) and candidate.is_file():
            return FileResponse(candidate)
        # A missing file that looks like an asset is a real 404, not the SPA shell.
        if "." in Path(full_path).name:
            raise ApiError(404, "not_found", "no such file")
        index = dist / "index.html"
        if not index.is_file():
            raise ApiError(404, "not_found", "dashboard not built")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app
