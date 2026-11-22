# SPDX-License-Identifier: Apache-2.0
"""GET /v1/builtins and the one switch-off gate for built-in apps (builtins.py, #603).

After the app store (ORDER 130), because the signed list and the on/off switch live there; before
/mcp (ORDER 140), which builds its request-only built-in tools from the same registry.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel
from starlette.middleware import Middleware

from .. import builtins
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope


class BuiltinApp(BaseModel):
    id: str
    name: str
    description: str | None = None
    spec: dict[str, Any]  # the descriptor's spec (sdk/schema/onemind.builtin.schema.json)


class BuiltinSettingsPage(BaseModel):
    app_id: str
    id: str
    title: str
    source: str  # METHOD /v1/path the page reads


class BuiltinBackupUnit(BaseModel):
    app_id: str
    kind: str    # table | dir
    name: str


class BuiltinTool(BaseModel):
    name: str          # the MCP tool name, request_<type with _>
    app_id: str
    action_type: str
    title: str


class BuiltinsOut(BaseModel):
    """Every switched-on built-in the caller may see, and what the gateway built from their descriptors."""

    apps: list[BuiltinApp]
    settings_pages: list[BuiltinSettingsPage]
    backup_units: list[BuiltinBackupUnit]
    tools: list[BuiltinTool]


register_route_scope("GET,HEAD", r"/v1/builtins", ("apps:read",))

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 135


def register(app: FastAPI, gw: Gateway) -> None:
    system = app.state.appstore.system.list
    found, errors = builtins.load(system, schema=builtins.schema_path(gw.settings.app_schema_path))
    registry = builtins.Builtins(found, lambda: gw.disabled_apps(), errors)
    app.state.builtins = registry
    # Innermost (appended, not inserted): the guard's limits and headers still wrap a 409 from the gate.
    app.user_middleware.append(Middleware(builtins.BuiltinGate, builtins=registry))

    @app.get("/v1/builtins", operation_id="builtins.list", tags=["apps"], response_model=BuiltinsOut,
             responses=error_responses(401))
    def list_builtins(request: Request, p: Principal = Depends(gw.principal)):
        """The descriptors of the switched-on built-in apps, with the Settings pages, backup units and
        request-only MCP tools built from them. A switched-off built-in is left out of every list."""
        return registry.view(lambda app_id: all(f(request, p, app_id) for f in gw.app_filters))
