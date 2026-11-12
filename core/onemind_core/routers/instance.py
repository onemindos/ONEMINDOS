# SPDX-License-Identifier: Apache-2.0
"""Contract §3: the open health check and GET /v1/instance."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .. import __version__
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings
    principal = gw.principal

    # ---- open ---------------------------------------------------------------------------
    @app.get("/healthz", tags=["meta"])
    def healthz():
        return {"ok": True}

    # ---- instance -----------------------------------------------------------------------
    @app.get("/v1/instance", tags=["instance"], responses=error_responses(401))
    def instance(_: Principal = Depends(principal)):
        return {"name": settings.instance_name, "version": __version__, "hub_node_id": settings.node_id}
