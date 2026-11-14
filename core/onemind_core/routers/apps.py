# SPDX-License-Identifier: Apache-2.0
"""Contract §3 and §11.4: GET /v1/apps, the catalog joined with each app's install state."""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from .. import lifecycle as lc
from ..actions import ActionParams, PlanRequest, PlanRequestBody
from ..apimodels import AppCredentials, PlanPreview
from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..models import CatalogApp


def app_rows(gw: Gateway) -> list[dict]:
    states = gw.repo.list_app_states()
    rows = []
    for app_id, entry in gw.catalog.load().items():
        st = states.get(app_id)
        status = st.status if st else "not_installed"
        # A removed app keeps its data (contract §12.5): clients see not_installed plus data_kept.
        data_kept = status == "removed"
        if data_kept:
            status = "not_installed"
        rows.append({**entry.summary(), "installed": status == "installed", "status": status, "data_kept": data_kept})
    return rows


def app_visible(gw: Gateway, app_id: str, request: Request, p: Principal) -> None:
    """§12.6 sharing: an app hidden from this principal in GET /v1/apps does not exist here either (404)."""
    if not APP_ID_RE.match(app_id) or app_id not in gw.catalog.load() or not all(
        f(request, p, app_id) for f in gw.app_filters
    ):
        raise ApiError(404, "not_found", "no such app")


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal

    @app.get("/v1/apps", tags=["apps"], operation_id="apps.list", response_model=list[CatalogApp], responses=error_responses(401))
    def list_apps(request: Request, p: Principal = Depends(principal)):
        rows = app_rows(gw)
        # §12.6 per-app sharing: a feature filter (identity) may hide apps not shared with this person.
        return [r for r in rows if all(f(request, p, r["id"]) for f in gw.app_filters)]

    def visible(app_id: str, request: Request, p: Principal) -> None:
        app_visible(gw, app_id, request, p)

    @app.get(
        "/v1/apps/{app_id}/plan", tags=["apps"], operation_id="apps.plan", response_model=PlanPreview,
        responses=error_responses(401, 403, 404, 422),
    )
    def app_plan(
        app_id: str, request: Request,
        type: Literal[lc.ACTION_TYPES] = "app.install",  # type: ignore[valid-type]  # noqa: A002
        p: Principal = Depends(principal),
    ):
        """What `type` would do to this app, and the fingerprint (`plan_sha256`) an approval binds to."""
        visible(app_id, request, p)
        return gw.actions.preview(p, type, ActionParams(app_id=app_id).model_dump(exclude_none=True))

    @app.post(
        "/v1/plans", tags=["actions"], operation_id="plans.create", response_model=PlanPreview,
        responses=error_responses(401, 403, 404, 422),
    )
    def create_plan(body: PlanRequestBody, request: Request, p: Principal = Depends(principal)):
        """Preview any app action with its params (for example the settings of app.configure). Files nothing."""
        req = PlanRequest.model_validate(body.model_dump())
        if not p.can_request_actions:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "preview an action", "type": req.type,
                                                                  "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not request actions")
        visible(req.params.app_id, request, p)
        return gw.actions.preview(p, req.type, req.params.model_dump(exclude_none=True))

    @app.get(
        "/v1/apps/{app_id}/credentials", tags=["apps"], operation_id="apps.credentials", response_model=AppCredentials,
        responses=error_responses(401, 403, 404),
    )
    def app_credentials(app_id: str, request: Request, p: Principal = Depends(principal)):
        """The app's generated login. Only the owner; every look is audited; never an agent."""
        store = gw.actions.credentials
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read app credentials", "app_id": app_id,
                                                                  "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not read app credentials")
        visible(app_id, request, p)
        try:
            revealed = store.reveal(app_id) if store is not None else None
        except Exception:  # key file lost or changed: say so plainly instead of a 500
            raise ApiError(409, "conflict", "the sealed credentials cannot be opened (credentials.key missing or replaced)") from None
        if revealed is None:
            raise ApiError(404, "not_found", "this app has no stored credentials")
        gw.audit.append("app.credentials.revealed", p.as_dict(), None, {"app_id": app_id})  # never the value
        return JSONResponse(revealed, headers={"Cache-Control": "no-store"})
