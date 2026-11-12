# SPDX-License-Identifier: Apache-2.0
"""Contract §12.22 app store depth: logs, settings, dependencies, host ports, exposure, Compose
conversion and community sources. The writes are action types (appstore/service.py); these routes
only read, except POST /v1/deploy/compose, which converts and writes nothing."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from ..appstore.compose import MAX_COMPOSE_BYTES
from ..appstore.logs import DEFAULT_TAIL
from ..appstore.service import AppStore
from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import error_responses


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

    @app.get("/v1/apps/{app_id}/logs", tags=["apps"], response_class=PlainTextResponse,
             responses=error_responses(401, 403, 404, 422, 503))
    def app_logs(
        app_id: str,
        component: str | None = Query(default=None, max_length=63),
        tail: int = Query(default=DEFAULT_TAIL),
        since: str | None = Query(default=None, max_length=64),
        follow: bool = Query(default=False),
        p: Principal = Depends(principal),
    ):
        result = store.logs(p, app_id, component, tail, since, follow)
        headers = {"OneMind-Log-Lines": str(len(result.lines)), "OneMind-Log-Redactions": str(result.redactions),
                   "OneMind-Log-Truncated": "true" if result.truncated else "false", "Cache-Control": "no-store"}
        return PlainTextResponse(result.text(), headers=headers)

    @app.get("/v1/apps/{app_id}/settings", tags=["apps"], responses=error_responses(401, 404, 409))
    def app_settings(app_id: str, p: Principal = Depends(principal)):
        return store.settings_view(p, app_id)

    @app.get("/v1/apps/{app_id}/dependencies", tags=["apps"], responses=error_responses(401, 404))
    def app_dependencies(app_id: str, _: Principal = Depends(principal)):
        return store.dependencies_view(app_id)

    @app.get("/v1/apps/{app_id}/host-ports", tags=["apps"], responses=error_responses(401, 404))
    def app_host_ports(app_id: str, node_id: str | None = Query(default=None, pattern=r"^[a-z0-9-]{1,64}$"),
                       _: Principal = Depends(principal)):
        return store.host_ports_view(app_id, node_id)

    @app.get("/v1/apps/{app_id}/exposure", tags=["apps"], responses=error_responses(401, 404))
    def app_exposure(app_id: str, _: Principal = Depends(principal)):
        return store.exposure_view(app_id)

    @app.post("/v1/deploy/compose", tags=["deploy"], responses=error_responses(401, 403, 409, 422))
    def deploy_compose(body: ComposeBody, p: Principal = Depends(principal)):
        return store.convert_compose(p, body.app_id, body.name, body.compose)

    @app.get("/v1/sources", tags=["sources"], responses=error_responses(401))
    def list_sources(_: Principal = Depends(principal)):
        return store.sources_view()

    @app.get("/v1/sources/{source_id}", tags=["sources"], responses=error_responses(401, 404))
    def get_source(source_id: str, _: Principal = Depends(principal)):
        return store.source_view(source_id)
