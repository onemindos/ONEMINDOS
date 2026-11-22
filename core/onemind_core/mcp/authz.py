# SPDX-License-Identifier: Apache-2.0
"""Per-tool authorization on /mcp (docs/leap/dev/MCP.md §4; DEV-MCP-10).

An agent token holds a set of scopes (`scopes` in the tokens file). A tool or resource is listed
and callable only when its scope is held; otherwise tools/list leaves it out and a call gets a
`permission_denied` tool error, audited as authz.denied. A token with no `scopes` keeps the v0
bundle, so existing agents are unchanged. Scopes only narrow: no scope lets an agent
approve or deny, because no such tool exists.
"""

from __future__ import annotations

from ..auth import MCP_BUNDLES, MCP_SCOPES, Principal

TOOL_SCOPES = {
    "get_instance": "instance:read",
    "list_nodes": "nodes:read",
    "get_node": "nodes:read",
    "list_apps": "apps:read",
    "get_app": "apps:read",
    "list_actions": "actions:read:own",
    "get_action": "actions:read:own",
    "search_audit": "audit:read:own",
    "request_action": "actions:request:*",  # any actions:request:<type>; the call needs its own type's
}
RESOURCE_SCOPES = {"catalog": "apps:read", "nodes": "nodes:read",
                   "actions": "actions:read:own", "audit": "audit:read:own"}
TASK_SCOPE = "actions:read:own"


def granted(p: Principal) -> frozenset[str]:
    return MCP_BUNDLES["v0"] if p.scopes is None else p.scopes


def request_scope(action_type: object) -> str:
    return f"actions:request:{action_type}"


def may_request(p: Principal, action_type: str) -> bool:
    """A request-only tool built from a built-in descriptor (#603) needs its own type's scope. Feature
    types are not in MCP_SCOPES yet, so no token can hold one until the scope list grants it."""
    return request_scope(action_type) in granted(p)


def may_call(p: Principal, tool: str, args: dict | None = None) -> bool:
    need = TOOL_SCOPES.get(tool)
    if need == "actions:request:*":
        have = granted(p)
        if args is not None and request_scope(args.get("type")) in MCP_SCOPES:  # a bad type is the tool's to refuse
            return request_scope(args["type"]) in have
        return any(x.startswith("actions:request:") for x in have)
    return need in granted(p)


def resource_scope(uri: str) -> str | None:
    return RESOURCE_SCOPES.get(uri.removeprefix("onemind://").split("/")[0])


def may_read(p: Principal, uri: str) -> bool:
    return resource_scope(uri) in granted(p)


def may_see_resource(p: Principal, item: dict) -> bool:
    return may_read(p, item.get("uri") or item.get("uriTemplate", "").replace("{", "x").replace("}", "x"))
