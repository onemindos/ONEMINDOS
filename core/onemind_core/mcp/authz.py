# SPDX-License-Identifier: Apache-2.0
"""Per-tool authorization on /mcp (docs/leap/dev/MCP.md §4; DEV-MCP-10).

An agent token holds a set of scopes (`mcp_scopes` in the tokens file). A tool or resource is listed
and callable only when its scope is held; otherwise tools/list leaves it out and a call gets a
`permission_denied` tool error, audited as authz.denied. A token with no `mcp_scopes` keeps the v0
bundle (every scope), so existing agents are unchanged. Scopes only narrow: no scope lets an agent
approve or deny, because no such tool exists.
"""

from __future__ import annotations

from ..auth import MCP_SCOPES, Principal

TOOL_SCOPES = {
    "get_instance": "mcp:instance:read",
    "list_nodes": "mcp:nodes:read",
    "get_node": "mcp:nodes:read",
    "list_apps": "mcp:apps:read",
    "get_app": "mcp:apps:read",
    "list_actions": "mcp:actions:read:own",
    "get_action": "mcp:actions:read:own",
    "search_audit": "mcp:audit:read:own",
    "request_action": "mcp:actions:request",
}
RESOURCE_SCOPES = {"catalog": "mcp:apps:read", "nodes": "mcp:nodes:read",
                   "actions": "mcp:actions:read:own", "audit": "mcp:audit:read:own"}
TASK_SCOPE = "mcp:actions:read:own"


def granted(p: Principal) -> frozenset[str]:
    return frozenset(MCP_SCOPES) if p.scopes is None else p.scopes


def may_call(p: Principal, tool: str) -> bool:
    return TOOL_SCOPES.get(tool) in granted(p)


def resource_scope(uri: str) -> str | None:
    return RESOURCE_SCOPES.get(uri.removeprefix("onemind://").split("/")[0])


def may_read(p: Principal, uri: str) -> bool:
    return resource_scope(uri) in granted(p)


def may_see_resource(p: Principal, item: dict) -> bool:
    return may_read(p, item.get("uri") or item.get("uriTemplate", "").replace("{", "x").replace("}", "x"))
