# SPDX-License-Identifier: Apache-2.0
"""Contract §11.3: POST /mcp, MCP Streamable HTTP for agent principals only."""

from __future__ import annotations

from dataclasses import replace

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response

from ..auth import Principal
from ..context import Gateway
from ..guard import reads_body
from ..errors import error_responses
from ..identity import ctx_of
from .. import __version__
from ..auditread import AuditReader
from ..mcp import Catalogue, Limits, McpEndpoint, McpSettings, Services
from ..mcp.read_tools import AreaReads
from ..surfaces.core import CORE_TOOLS
from ..work.access import work_reader_context
from .apps import app_rows
from .audit import owned_action_ids
from .notifications import _can_see as can_see_alert


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 140

# Named from the one declaration of each tool (surfaces/core.py), not by hand.
READS = [t.name for t in CORE_TOOLS if t.effect == "read" and "mcp" in t.exposure]
REQUESTS = [t.name for t in CORE_TOOLS if t.effect != "read" and "mcp" in t.exposure]


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
        mark_tainted=lambda p, source: actions.taint.mark(p.id, source),
        # Request-only tools of switched-on built-ins, from the surface registry (#605): read on every
        # call, so a switched-off app's tools leave tools/list at once; refused declarations never appear.
        builtin_actions=app.state.surfaces.mcp_actions,
        area_reads=AreaReads(app.state, gw, lambda: app_rows(gw), can_see_alert),  # backups, logs, ... (#632)
    )
    limits = Limits(gw.settings.section(McpSettings), gw.clock)
    catalogue = Catalogue(services, limits, route_enabled=app.state.surfaces.route_enabled)
    mcp = McpEndpoint(catalogue, limits, refuse=lambda p, what: actions._deny(p, what))

    @app.post(
        "/mcp",
        tags=["mcp"],
        operation_id="mcp.post",
        summary="MCP Streamable HTTP endpoint (protocol 2025-06-18), agents only",
        description=(
            "One JSON-RPC 2.0 message per request: initialize, ping, tools/list, tools/call. "
            f"Read tools ({', '.join(READS)}), one request-only tool ({', '.join(REQUESTS)}) and onemind:// "
            "resources. No approve tool. Notifications get 202; over the per-agent message limit, 429."
        ),
        openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}},
        responses={202: {"description": "Notification or response accepted"}, **error_responses(401, 403, 429)},
    )
    @reads_body
    async def mcp_post(request: Request, p: Principal = Depends(principal)):
        with work_reader_context(request, p):
            ctx = ctx_of(request)
            if p.kind == "agent" and ctx is not None:
                # An identity credential never inherits the static-token v0 bundle (design PR 4, gap 4): its MCP
                # scopes are rebuilt from the scopes it was minted with, every time. A broad scope covers its
                # narrowed forms (actions:request covers actions:request:app.install); a narrowed scope covers
                # only itself, so an actions:request:app.install token reaches /mcp for that one type.
                from ..auth import ALWAYS_GRANTED, MCP_SCOPES
                from ..identity.scopes import within

                p = replace(p, scopes=ALWAYS_GRANTED | frozenset(
                    scope for scope in MCP_SCOPES if within(scope, ctx.scopes)
                ))
            return await mcp.handle(request, p)

    @app.api_route("/mcp", methods=["GET", "DELETE"], include_in_schema=False)
    def mcp_other(_: Principal = Depends(principal)):
        # No server-initiated SSE stream and no sessions (Streamable HTTP allows 405 for both).
        return Response(status_code=405, headers={"Allow": "POST"})
