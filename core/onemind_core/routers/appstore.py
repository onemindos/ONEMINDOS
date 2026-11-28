# SPDX-License-Identifier: Apache-2.0
"""Contract §12.22 app store depth: settings, dependencies, host ports, exposure, Compose
conversion and community sources (app logs are §12.15, routers/monitoring.py). The writes are action types (appstore/service.py); these routes
only read, except POST /v1/deploy/compose, which converts and writes nothing."""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Query, Request, Security
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from ..apimodels import AppPlacement
from ..appstore.compose import MAX_COMPOSE_BYTES
from ..appstore.service import AppStore
from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..jsonbody import JsonBody
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from .apps import app_visible


class ComposeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    compose: str = Field(min_length=1, max_length=MAX_COMPOSE_BYTES)


class CustomPlanBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=9, max_length=500)
    ref: str = Field(min_length=1, max_length=100)


class ScanChecks(BaseModel):
    result: str
    scanned_at: str | None = None
    checks: dict | None = None


class CustomRevisionOut(BaseModel):
    """One recorded revision of a custom app (appstore/custom.py revision_json)."""

    revision: int
    commit: str
    ref: str
    version: str | None = None
    scan: ScanChecks
    created_by: str
    created_at: str | None = None
    deployed_at: str | None = None
    action_id: str | None = None
    current: bool
    deployed: bool


class CustomAppRow(BaseModel):
    """A linked repository with its revisions, newest first."""

    app_id: str
    url: str
    ref: str
    added_at: str | None = None
    status: str
    current_revision: int | None = None
    deployed_revision: int | None = None
    rollback_to: int | None = None
    revisions: list[CustomRevisionOut]


class CustomSignature(BaseModel):
    policy: str
    status: str
    detail: str


class CustomPlanResult(BaseModel):
    """POST /v1/custom-apps/plan: what was fetched and checked. Nothing is installed."""

    url: str
    ref: str
    commit: str
    app_id: str | None = None
    name: str | None = None
    version: str | None = None
    revision: int | None = None
    verdict: Literal["ready", "blocked"]
    problems: list[str]
    notes: list[str]
    images: list[str] = []
    scan: ScanChecks | None = None
    signature: CustomSignature | None = None
    action_type: Literal["app.install", "app.update"] | None = None
    next: str | None = None


class CustomRollbackResult(BaseModel):
    app_id: str
    from_revision: int | None = None
    to_revision: int
    commit: str
    version: str | None = None
    verdict: Literal["ready"]
    action_type: Literal["app.update"]
    scan: ScanChecks
    next: str


class CustomRollbackBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    revision: int | None = Field(default=None, ge=1)


class SystemAppRow(BaseModel):
    """One built-in app (appstore/system.py): the signed list joined with its catalog entry and switch."""

    id: str
    name: str
    kind: Literal["container", "native"]
    update: Literal["os", "own"]
    disable: Literal["allowed", "never"]
    enabled: bool
    can_disable: bool
    status: str | None = None          # the app's install state; null for a native app
    version: str | None = None
    license: str | None = None
    update_channel: str | None = None  # os | security | stable
    disabled_at: str | None = None
    action_id: str | None = None


# Same scope as the rest of the app list: `/v1/apps(/.*)?` does not match this path.
register_route_scope("GET,HEAD", r"/v1/system-apps", ("apps:read",))

# PLG-GIT-01: reading custom apps is the app list's scope; planning one fetches a repository and a
# rollback moves what the catalog serves, so both need the approver's scope (the handler also checks owner).
register_route_scope("GET,HEAD", r"/v1/custom-apps(/.*)?", ("actions:approve",))  # repository URLs: the owner's
register_route_scope("POST", r"/v1/custom-apps/plan", ("actions:approve",))
register_route_scope("POST", r"/v1/custom-apps/[^/]+/rollback", ("actions:approve",))

_BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description="A gateway token or a signed-in session (contract §3)")
CUSTOM_READ = [Security(_BEARER, scopes=["actions:approve"])]
CUSTOM_WRITE = [Security(_BEARER, scopes=["actions:approve"])]

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 130

# CORE-FABRIC-4 (#171): the placement names every machine with its board, memory, role and GPU, which
# is what /v1/nodes shows, so it needs that route's scope, not only apps:read. A child (no nodes:read,
# contract §12.6) is refused rather than shown the machines through an app it can see.
register_route_scope("GET,HEAD", r"/v1/apps/[^/]+/placement", ("nodes:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    store = AppStore(gw)
    store.install()
    app.state.appstore = store
    principal = gw.principal

    @app.get("/v1/apps/{app_id}/settings", operation_id="apps.settings", tags=["apps"], responses=error_responses(401, 404, 409))
    def app_settings(app_id: str, request: Request, p: Principal = Depends(principal)):
        app_visible(gw, app_id, request, p)
        return store.settings_view(p, app_id)

    @app.get("/v1/apps/{app_id}/dependencies", operation_id="apps.dependencies", tags=["apps"], responses=error_responses(401, 404))
    def app_dependencies(app_id: str, request: Request, p: Principal = Depends(principal)):
        app_visible(gw, app_id, request, p)
        return store.dependencies_view(app_id)

    @app.get("/v1/apps/{app_id}/host-ports", operation_id="apps.host_ports", tags=["apps"], responses=error_responses(401, 404))
    def app_host_ports(app_id: str, request: Request, node_id: str | None = Query(default=None, pattern=r"^[a-z0-9-]{1,64}$"),
                       p: Principal = Depends(principal)):
        app_visible(gw, app_id, request, p)
        return store.host_ports_view(app_id, node_id)

    @app.get("/v1/apps/{app_id}/placement", operation_id="apps.placement", tags=["apps"],
             responses={200: {"model": AppPlacement}, **error_responses(401, 403, 404)})
    def app_placement(app_id: str, request: Request, p: Principal = Depends(principal)):
        """Where the app would run (CORE-FABRIC-4): here, on another machine, or nowhere, with each node's reasons."""
        app_visible(gw, app_id, request, p)
        return store.placement_view(app_id)

    @app.get("/v1/apps/{app_id}/exposure", operation_id="apps.exposure", tags=["apps"], responses=error_responses(401, 404))
    def app_exposure(app_id: str, request: Request, p: Principal = Depends(principal)):
        app_visible(gw, app_id, request, p)
        return store.exposure_view(app_id)

    @app.post("/v1/deploy/compose", operation_id="deploy.compose", tags=["deploy"], responses=error_responses(401, 403, 409, 422))
    def deploy_compose(body: ComposeBody, p: Principal = Depends(principal)):
        return store.convert_compose(p, body.app_id, body.name, body.compose)

    @app.get("/v1/system-apps", operation_id="apps.system", tags=["apps"], response_model=list[SystemAppRow],
             responses=error_responses(401))
    def system_apps(request: Request, p: Principal = Depends(principal)):
        """The Built in area: every system app on the signed list, whether it is on, and its version,
        licence and update channel. A switched-off app is only listed here, not in GET /v1/apps."""
        # §12.6 sharing, as in GET /v1/apps: a child or agent sees only the apps shared with them.
        return [r for r in store.system.view() if all(f(request, p, r["id"]) for f in gw.app_filters)]

    def owner_only(p: Principal, what: str) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not {what}")

    @app.get("/v1/custom-apps", operation_id="customapps.list", tags=["custom-apps"], dependencies=CUSTOM_READ,
             response_model=list[CustomAppRow],
             responses=error_responses(401, 403))
    def list_custom_apps(p: Principal = Depends(principal)):
        """Apps linked from a Git repository, each with its revisions and what a rollback would go back to."""
        owner_only(p, "read custom apps")
        return store.custom.view()

    @app.get("/v1/custom-apps/{app_id}", operation_id="customapps.get", tags=["custom-apps"], dependencies=CUSTOM_READ,
             response_model=CustomAppRow,
             responses=error_responses(401, 403, 404))
    def get_custom_app(app_id: str, p: Principal = Depends(principal)):
        owner_only(p, "read a custom app")
        if not APP_ID_RE.match(app_id):
            raise ApiError(404, "not_found", "no such custom app")
        return store.custom.view_one(app_id)

    @app.post("/v1/custom-apps/plan", operation_id="customapps.plan", tags=["custom-apps"], dependencies=CUSTOM_WRITE,
              response_model=CustomPlanResult,
              responses=error_responses(401, 403, 409, 422))
    def plan_custom_app(body: CustomPlanBody, p: Principal = Depends(principal)):
        """Fetch a repository at a ref in a sandbox, check it like a Market app and record a revision.
        Installs nothing: the install or update that follows is an ordinary action an owner approves."""
        owner_only(p, "plan a custom app")
        return store.custom.plan(p, body.url, body.ref)

    @app.post("/v1/custom-apps/{app_id}/rollback", operation_id="customapps.rollback", tags=["custom-apps"],
              dependencies=CUSTOM_WRITE, response_model=CustomRollbackResult,
              responses=error_responses(401, 403, 404, 409, 422))
    def rollback_custom_app(app_id: str, body: CustomRollbackBody, p: Principal = Depends(principal)):
        """Point the catalog at the previously deployed revision. The app.update that applies it waits for an owner."""
        owner_only(p, "roll back a custom app")
        if not APP_ID_RE.match(app_id):
            raise ApiError(404, "not_found", "no such custom app")
        return store.custom.rollback(p, app_id, body.revision)

    @app.get("/v1/sources", operation_id="sources.list", tags=["sources"], responses=error_responses(401))
    def list_sources(_: Principal = Depends(principal)):
        return store.sources_view()

    @app.get("/v1/sources/{source_id}", operation_id="sources.get", tags=["sources"], responses=error_responses(401, 404))
    def get_source(source_id: str, _: Principal = Depends(principal)):
        return store.source_view(source_id)
