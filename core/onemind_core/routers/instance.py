# SPDX-License-Identifier: Apache-2.0
"""Contract §3: the open health check and GET /v1/instance."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .. import __version__
from ..apimodels import Healthz, Instance
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings
    principal = gw.principal

    # ---- open ---------------------------------------------------------------------------
    @app.get("/healthz", tags=["meta"], operation_id="meta.healthz", responses={200: {"model": Healthz}})
    def healthz():
        return {"ok": True}

    # ---- instance -----------------------------------------------------------------------
    @app.get(
        "/v1/instance", tags=["instance"], operation_id="instance.get",
        responses={200: {"model": Instance}, **error_responses(401)},
    )
    def instance(_: Principal = Depends(principal)):
        return {"name": settings.instance_name, "version": __version__, "hub_node_id": settings.node_id}
