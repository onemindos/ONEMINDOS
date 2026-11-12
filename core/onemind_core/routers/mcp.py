# SPDX-License-Identifier: Apache-2.0
"""Contract §11.3: POST /mcp, MCP Streamable HTTP for agent principals only."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from .. import __version__
from ..auditread import AuditReader
from ..mcp import Catalogue, Limits, McpEndpoint, McpSettings, Services
from .apps import app_rows
from .audit import owned_action_ids


def register(app: FastAPI, gw: Gateway) -> None:
    actions = gw.actions
    principal = gw.principal
    reader = AuditReader(gw.settings.audit_path, gw.clock, owned_action_ids(gw))
    own_ids = owned_action_ids(gw)
    services = Services(
        instance=lambda: {"name": gw.settings.instance_name, "version": __version__,
                          "hub_node_id": gw.settings.node_id},
        list_nodes=gw.registry.list,
        get_node=gw.registry.get,
        list_apps=lambda: app_rows(gw),
        own_actions=lambda pid: [a for a in actions.list() if a["id"] in own_ids(pid)],
        get_action=actions.get,
        request=lambda p, req, reason: actions.create(p, req, reason=reason),
        audit_list=reader.list,
        clock=gw.clock,
    )
    limits = Limits(gw.settings.section(McpSettings), gw.clock)
    mcp = McpEndpoint(Catalogue(services, limits), limits, refuse=lambda p, what: actions._deny(p, what))

    @app.post(
        "/mcp",
        tags=["mcp"],
        operation_id="mcp.post",
        summary="MCP Streamable HTTP endpoint (protocol 2025-06-18), agents only",
        description=(
            "One JSON-RPC 2.0 message per request: initialize, ping, tools/list, tools/call. "
            "Read tools (get_instance, list_nodes, get_node, list_apps, get_app, list_actions, get_action, "
            "search_audit), one request-only tool (request_action) and onemind:// resources. No approve tool. "
            "Notifications get 202; over the per-agent message limit, 429."
        ),
        openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}},
        responses={202: {"description": "Notification or response accepted"}, **error_responses(401, 403, 429)},
    )
    async def mcp_post(request: Request, p: Principal = Depends(principal)):
        return await mcp.handle(request, p)

    @app.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
    def mcp_other(_: Principal = Depends(principal)):
        # No server-initiated SSE stream and no sessions (Streamable HTTP allows 405 for both).
        return Response(status_code=405, headers={"Allow": "POST"})
