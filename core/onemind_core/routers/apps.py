# SPDX-License-Identifier: Apache-2.0
"""Contract §3 and §11.4: GET /v1/apps, the catalog joined with each app's install state."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..models import CatalogApp


def app_rows(gw: Gateway) -> list[dict]:
    states = gw.repo.list_app_states()
    rows = []
    for app_id, entry in gw.catalog.load().items():
        st = states.get(app_id)
        status = st.status if st else "not_installed"
        rows.append({**entry.summary(), "installed": status == "installed", "status": status})
    return rows


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal

    @app.get("/v1/apps", tags=["apps"], operation_id="apps.list", response_model=list[CatalogApp], responses=error_responses(401))
    def list_apps(request: Request, p: Principal = Depends(principal)):
        rows = app_rows(gw)
        # §12.6 per-app sharing: a feature filter (identity) may hide apps not shared with this person.
        return [r for r in rows if all(f(request, p, r["id"]) for f in gw.app_filters)]
