# SPDX-License-Identifier: Apache-2.0
"""Contract §12.22 app store depth: settings, dependencies, host ports, exposure, Compose
conversion and community sources (app logs are §12.15, routers/monitoring.py). The writes are action types (appstore/service.py); these routes
only read, except POST /v1/deploy/compose, which converts and writes nothing."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..appstore.compose import MAX_COMPOSE_BYTES
from ..appstore.service import AppStore
from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import error_responses
from .apps import app_visible


class ComposeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(min_length=1, max_length=59, pattern=APP_ID_RE.pattern)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    compose: str = Field(min_length=1, max_length=MAX_COMPOSE_BYTES)


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

    @app.get("/v1/apps/{app_id}/exposure", operation_id="apps.exposure", tags=["apps"], responses=error_responses(401, 404))
    def app_exposure(app_id: str, request: Request, p: Principal = Depends(principal)):
        app_visible(gw, app_id, request, p)
        return store.exposure_view(app_id)

    @app.post("/v1/deploy/compose", operation_id="deploy.compose", tags=["deploy"], responses=error_responses(401, 403, 409, 422))
    def deploy_compose(body: ComposeBody, p: Principal = Depends(principal)):
        return store.convert_compose(p, body.app_id, body.name, body.compose)

    @app.get("/v1/sources", operation_id="sources.list", tags=["sources"], responses=error_responses(401))
    def list_sources(_: Principal = Depends(principal)):
        return store.sources_view()

    @app.get("/v1/sources/{source_id}", operation_id="sources.get", tags=["sources"], responses=error_responses(401, 404))
    def get_source(source_id: str, _: Principal = Depends(principal)):
        return store.source_view(source_id)
