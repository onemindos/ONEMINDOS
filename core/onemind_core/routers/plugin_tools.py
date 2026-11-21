# SPDX-License-Identifier: Apache-2.0
"""REST calls to installed tools, with exact request scopes and owner approval."""
from datetime import timedelta
from typing import Any
import uuid

from fastapi import Depends, FastAPI, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..actions import FeatureActionRequest
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import has_any, register_route_scope
from ..plugins.tools import Tools

ORDER = 275
_SCOPE = "actions:request:plugin.invoke"
register_route_scope("GET,HEAD", r"/v1/plugins/[^/]+/tools", ("apps:read",))
register_route_scope("POST", r"/v1/plugins/[^/]+/tools/[^/]+", ("apps:read", _SCOPE))


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    expires_at: AwareDatetime | None = None


def register(app: FastAPI, gw: Gateway):
    tools = Tools(gw, app.state.identity)
    app.state.plugin_tools = tools

    def destructive_step_up(principal, action_id, body, request):
        action = gw.repo.get(action_id)
        if (principal.is_owner and action and action.type == "plugin.invoke" and action.risk == "destructive"
                and body.get("webauthn") is None):
            raise ApiError(401, "unauthenticated", "destructive plugin tools require an action-bound passkey",
                           reason="step_up_required")
        # Identity's following guard cryptographically verifies every supplied assertion,
        # consumes its challenge and binds it to this exact action, even with the global option off.
    gw.approval_guards.insert(0, destructive_step_up)

    @app.get("/v1/plugins/{plugin_id}/tools", tags=["plugins"], operation_id="plugins.tools",
             response_model=list[dict[str, Any]], responses=error_responses(401, 403, 404))
    def list_tools(plugin_id: str, p: Principal = Depends(gw.principal)):
        tools.visible(plugin_id, p)
        record = tools.installed(plugin_id)
        rows = []
        for item in record.manifest.get("spec", {}).get("extensions", {}).get("tools", []):
            try:
                _, _, tool = tools.lookup(plugin_id, item.get("name", ""))
            except ApiError:
                continue
            rows.append({"name": tool["name"], "title": str(tool.get("title", tool["name"]))[:128],
                         "effect": tool["effect"], "input": tool["input"],
                         "description": ("Returns data immediately. " if tool["effect"] == "read" else
                                         "Creates a request that waits for owner approval. ") +
                                        "From the plugin: " + str(tool.get("description", ""))[:500]})
        return rows

    @app.post("/v1/plugins/{plugin_id}/tools/{tool_name}", tags=["plugins"], operation_id="plugins.call",
              response_model=dict[str, Any], responses=error_responses(401, 403, 404, 409, 413, 422, 429, 503))
    def call(plugin_id: str, tool_name: str, body: ToolCall, request: Request, response: Response,
             p: Principal = Depends(gw.principal)):
        tools.visible(plugin_id, p)
        _, _, tool = tools.lookup(plugin_id, tool_name)
        ctx = ctx_of(request)
        if tool["effect"] == "read":
            if ctx and not has_any(ctx.scopes, ("apps:read",)):
                raise ApiError(403, "permission_denied", "read tools require apps:read")
            return {"output": tools.read(p, plugin_id, tool_name, body.arguments)}
        if ctx and not has_any(ctx.scopes, (_SCOPE,)):
            raise ApiError(403, "permission_denied", "mutating tools require an exact action request grant")
        params = tools.params(plugin_id, tool_name, body.arguments)
        action, created = gw.actions.create(p, FeatureActionRequest(
            type="plugin.invoke", params=params, idempotency_key=body.idempotency_key or uuid.uuid4().hex,
            expires_at=body.expires_at or gw.clock() + timedelta(minutes=10),
        ))
        response.status_code = 201 if created else 200
        return action
