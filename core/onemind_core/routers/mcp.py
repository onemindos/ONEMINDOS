# SPDX-License-Identifier: Apache-2.0
"""Contract §11.3: POST /mcp, MCP Streamable HTTP for agent principals only."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..mcp import McpEndpoint
from .apps import app_rows


def register(app: FastAPI, gw: Gateway) -> None:
    actions = gw.actions
    principal = gw.principal
    mcp = McpEndpoint(
        list_nodes=gw.registry.list, list_apps=lambda: app_rows(gw), actions=actions, clock=gw.clock,
        deny=lambda p, what: actions._deny(p, what),
    )

    @app.post(
        "/mcp",
        tags=["mcp"],
        summary="MCP Streamable HTTP endpoint (protocol 2025-06-18), agents only",
        description=(
            "One JSON-RPC 2.0 message per request: initialize, ping, tools/list, tools/call. "
            "Tools: list_nodes, list_apps, request_action. No approve tool. Notifications get 202."
        ),
        openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}},
        responses={202: {"description": "Notification or response accepted"}, **error_responses(401, 403)},
    )
    async def mcp_post(request: Request, p: Principal = Depends(principal)):
        return await mcp.handle(request, p)

    @app.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
    def mcp_other(_: Principal = Depends(principal)):
        # No server-initiated SSE stream and no sessions (Streamable HTTP allows 405 for both).
        return Response(status_code=405, headers={"Allow": "POST"})
