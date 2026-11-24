# SPDX-License-Identifier: Apache-2.0
"""Contract §3: the open health check and GET /v1/instance."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .. import __version__
from ..apimodels import Healthz, Instance, InstanceName
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..onboarding import OnboardingService


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 100


def register(app: FastAPI, gw: Gateway) -> None:
    settings = gw.settings
    principal = gw.principal

    # ---- open ---------------------------------------------------------------------------
    @app.get("/healthz", tags=["meta"], operation_id="meta.healthz", responses={200: {"model": Healthz}})
    def healthz():
        return {"ok": True}

    # The sign-in screen says which box it belongs to ("Home OneMind"). Only the display name the
    # owner chose is served, nothing else: no version, no node id (those stay behind sign-in).
    @app.get(
        "/v1/instance/name", tags=["instance"], operation_id="instance.name",
        responses={200: {"model": InstanceName}},
    )
    def instance_name():
        return {"name": OnboardingService(gw.db).read()["box_name"] or settings.instance_name}

    # ---- instance -----------------------------------------------------------------------
    @app.get(
        "/v1/instance", tags=["instance"], operation_id="instance.get",
        responses={200: {"model": Instance}, **error_responses(401)},
    )
    def instance(_: Principal = Depends(principal)):
        name = OnboardingService(gw.db).read()["box_name"] or settings.instance_name
        return {"name": name, "version": __version__, "hub_node_id": settings.node_id}
