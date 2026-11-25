# SPDX-License-Identifier: Apache-2.0
"""Installed schema reads and approval-bound plugin settings requests."""
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..actions import ActionRequest
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope
from ..plugins.settings import PluginSettings

ORDER = 270
register_route_scope("GET,HEAD", r"/v1/plugins/[^/]+/settings", ("apps:read",))
register_route_scope("POST", r"/v1/plugins/[^/]+/settings", ("actions:request",))


class SettingsView(BaseModel):
    schema_: dict[str, Any] = Field(alias="schema")
    settings: dict[str, Any]
    bundle_sha256: str


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settings: dict[str, Any]
    bundle_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime


def register(app: FastAPI, gw: Gateway) -> None:
    service = PluginSettings(gw, app.state.identity)

    @app.get("/v1/plugins/{plugin_id}/settings", operation_id="plugins.settings.get", tags=["plugins"],
             response_model=SettingsView, responses=error_responses(401, 403, 404, 409))
    def get_settings(plugin_id: str, p: Principal = Depends(gw.principal)):
        return service.view(plugin_id, p)

    @app.post("/v1/plugins/{plugin_id}/settings", operation_id="plugins.settings.request", tags=["plugins"],
              responses={202: {"model": Action}, **error_responses(401, 403, 404, 409, 422)}, status_code=202)
    def request_settings(plugin_id: str, body: SettingsRequest, p: Principal = Depends(gw.principal)):
        req = ActionRequest(type="plugin.configure", params={"app_id": plugin_id, "settings": body.settings,
                            "bundle_sha256": body.bundle_sha256}, idempotency_key=body.idempotency_key,
                            expires_at=body.expires_at)
        result, _ = gw.actions.create(p, req)
        return JSONResponse(status_code=202, content=result)
