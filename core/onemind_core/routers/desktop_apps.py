# SPDX-License-Identifier: Apache-2.0
"""Desktop apps from Flathub (issue #1097): `GET /v1/desktop-apps`, `GET /v1/desktop-apps/search` and
`POST /v1/desktop-apps/{app_id}/launch`. Installing, updating and removing are the `desktop.app.install|update|remove`
actions, filed through `POST /v1/actions` and approved by an owner (desktopapps.py)."""

from __future__ import annotations

import re

from fastapi import Depends, FastAPI, Query

from ..auth import Principal
from ..context import Gateway
from ..desktopapps import APP_ID_RE, DesktopAppsService, DesktopAppsView, LaunchResult, SearchResult
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope

ORDER = 338
# Owner only, like the other /v1/system reads: minted to no one, so only the owner role (every scope) reads it.
register_route_scope("GET,HEAD", r"/v1/desktop-apps(/search)?", ("system:admin",))
register_route_scope("POST", r"/v1/desktop-apps/[^/]+/launch", ("system:admin",))


def register(app: FastAPI, gw: Gateway) -> None:
    svc = DesktopAppsService(gw)
    svc.register()
    app.state.desktop_apps = svc

    def owner(p: Principal, what: str) -> Principal:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may manage desktop apps")
        return p

    @app.get("/v1/desktop-apps", tags=["apps"], operation_id="desktop_apps.list", response_model=DesktopAppsView, responses=error_responses(401, 403))
    def desktop_apps_list(p: Principal = Depends(gw.principal)):
        """Whether the box can run Flathub desktop apps, the installed ones (with their folder and whether an
        update is waiting), the sandbox every app gets, and whether the streaming session app is installed."""
        owner(p, "read desktop apps")
        return svc.view()

    @app.get("/v1/desktop-apps/search", tags=["apps"], operation_id="desktop_apps.search", response_model=SearchResult, responses=error_responses(401, 403, 409, 422))
    def desktop_apps_search(q: str = Query(min_length=2, max_length=64), p: Principal = Depends(gw.principal)):
        """Flathub apps whose id, name or summary contains `q`, best name matches first (at most 50)."""
        owner(p, "search desktop apps")
        return svc.search(q)

    @app.post("/v1/desktop-apps/{app_id}/launch", tags=["apps"], operation_id="desktop_apps.launch",
              response_model=LaunchResult, responses=error_responses(401, 403, 404, 409))
    def desktop_apps_launch(app_id: str, p: Principal = Depends(gw.principal)):
        """Start an installed app in the streaming session. Owner only, audited. It is not an approval:
        the owner already approved the install, and the app stays inside its sandbox."""
        owner(p, "launch a desktop app")
        if not re.fullmatch(APP_ID_RE, app_id) or len(app_id) > 255:
            raise ApiError(404, "not_found", "that is not a Flatpak application id")
        return svc.launch(app_id, p)
