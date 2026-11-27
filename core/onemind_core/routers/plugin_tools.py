# SPDX-License-Identifier: Apache-2.0
"""REST calls to installed tools, with exact request scopes and owner approval."""
from datetime import timedelta
from typing import Any
import uuid

from fastapi import Depends, FastAPI, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..actions import FeatureActionRequest
from ..ai_policy import actions_for_agent, app_data_to_agent, app_policy, is_agent
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import has_any, register_route_scope
from ..plugins.tools import Tools
from .apps import app_rows

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

    # Identity verifies the action-bound factor after this guard. Existing install-token
    # workflows may run before the household has an account.
    def destructive_step_up(principal, action_id, body, request):
        action = gw.repo.get(action_id)
        if (principal.is_owner and action and action.type == "plugin.invoke" and action.risk == "destructive"
                and app.state.identity.account_setup_exists()
                and not (body.get("webauthn") or body.get("password_totp"))):
            raise ApiError(401, "unauthenticated", "destructive plugin tools require an action-bound sign-in check",
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
            if p.kind != "person" and not (ctx and has_any(ctx.scopes, (_SCOPE,))):
                # The plugin author labels its own tools. A read runs with no approval, so an
                # agent or rule may run one only with the exact grant its owner issued for tools.
                raise ApiError(403, "permission_denied",
                               "agents and automations need the exact plugin.invoke grant to run any plugin tool")
            if is_agent(p):
                # aiPolicy (#165): a read tool returns the app's own data at once, so an agent may run
                # it only when the app lets app data go to an AI. Checked before the backend is called.
                decision = app_data_to_agent(app_policy(app_rows(gw), plugin_id))
                if not decision.allowed:
                    raise ApiError(403, "permission_denied",
                                   f"this app's data may not go to an AI: {decision.reason}", reason="ai_policy")
            return {"output": tools.read(p, plugin_id, tool_name, body.arguments)}
        if ctx and not has_any(ctx.scopes, (_SCOPE,)):
            raise ApiError(403, "permission_denied", "mutating tools require an exact action request grant")
        params = tools.params(plugin_id, tool_name, body.arguments)
        action, created = gw.actions.create(p, FeatureActionRequest(
            type="plugin.invoke", params=params, idempotency_key=body.idempotency_key or uuid.uuid4().hex,
            expires_at=body.expires_at or gw.clock() + timedelta(minutes=10),
        ))
        response.status_code = 201 if created else 200
        # An idempotent replay returns the stored action, a finished tool's output included.
        return actions_for_agent([action], lambda: app_rows(gw))[0] if is_agent(p) else action
