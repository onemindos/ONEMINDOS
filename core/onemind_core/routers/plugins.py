# SPDX-License-Identifier: Apache-2.0
"""DEV-PLG-3 registry: read-only installed plugin declarations, with app sharing."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..plugins.registry import PluginSummary, installed_plugins
from ..plugins.auth import plugin_app_id

ORDER = 125

register_route_scope("GET,HEAD", r"/v1/plugins", ("apps:read",))
register_route_scope("GET,HEAD", r"/v1/plugins/[^/]+", ("apps:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    def live_plugin_request(p: Principal, _type: str) -> bool:
        if p.kind != "plugin":
            return True
        app_id = plugin_app_id(p.id)
        state = gw.repo.get_app_state(app_id) if app_id else None
        return state is not None and state.status in {"installed", "stopped"}

    gw.actions.request_checks.append(live_plugin_request)

    @app.get("/v1/plugins", tags=["plugins"], operation_id="plugins.list",
             response_model=list[PluginSummary], responses=error_responses(401, 403))
    def list_plugins(request: Request, p: Principal = Depends(gw.principal)):
        """Installed tool-backed plugins this caller may see; no execution authority."""
        return installed_plugins(gw, request, p)

    @app.get("/v1/plugins/{plugin_id}", tags=["plugins"], operation_id="plugins.get",
             response_model=PluginSummary, responses=error_responses(401, 403, 404))
    def get_plugin(plugin_id: str, request: Request, p: Principal = Depends(gw.principal)):
        """One visible plugin; absent, uninstalled and unshared IDs all return 404."""
        for row in installed_plugins(gw, request, p):
            if row.id == plugin_id:
                return row
        raise ApiError(404, "not_found", "no such plugin")
