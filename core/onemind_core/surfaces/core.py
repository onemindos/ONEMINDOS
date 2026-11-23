# SPDX-License-Identifier: Apache-2.0
"""The gateway's own tools, each declared once with its REST route, effect, exposure and scope (#605).

One `ToolSurface` per tool. From this list the gateway builds the MCP catalogue (mcp/tools.py
`TOOLS`), the per-tool scopes on /mcp (mcp/authz.py `TOOL_SCOPES`), the tools in GET /v1/surfaces
and the route side of the parity test (tests/test_surfaces.py). Adding a tool means adding one entry
here; there is no second list to edit by hand.

A read tool returns the same body as its REST route for the same caller: the REST object itself, or,
for a route that answers a JSON array, that array under `body_key` (an MCP result is always an
object). `row_of` names the argument that picks one row (by `id`) of a list route, `adds` the keys a tool
puts beside the REST body, and `projection` a filter the REST route does not apply (`ai_policy`: rows
whose aiPolicy keeps them away from AI are left out).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Effect = Literal["read", "write", "destructive"]
Exposure = Literal["mcp", "rest", "cli"]
EFFECTS: tuple[str, ...] = ("read", "write", "destructive")
EXPOSURES: tuple[str, ...] = ("mcp", "rest", "cli")

LIST_ACTIONS_MAX = 50
AUDIT_MAX = 100
MAX_REASON = 500


def obj(props: dict | None = None, required: list[str] | None = None) -> dict:
    s: dict[str, Any] = {"type": "object", "properties": props or {}, "additionalProperties": False}
    if required:
        s["required"] = required
    return s


def list_of(key: str) -> dict:
    return {"type": "object", "properties": {key: {"type": "array", "items": {"type": "object"}},
                                             "next_cursor": {"type": ["string", "null"]}}, "required": [key]}


ID = {"type": "string", "minLength": 1, "maxLength": 200}
ANY_OBJ = {"type": "object"}
FILED = {"type": "object", "properties": {"action_id": {"type": "string"}, "state": {"type": "string"}},
         "required": ["action_id", "state"]}


@dataclass(frozen=True)
class ToolSurface:
    name: str
    title: str
    description: str
    effect: Effect
    route: str  # "METHOD /path": the REST operation this tool is a thin call into
    scope: str  # the token scope /mcp needs; "actions:request:*" means the requested type's own scope
    input: dict
    output: dict = field(default_factory=lambda: dict(ANY_OBJ))
    exposure: tuple[Exposure, ...] = ("mcp", "rest")
    body_key: str | None = None
    row_of: str | None = None
    adds: tuple[str, ...] = ()
    projection: Literal["ai_policy"] | None = None

    def __post_init__(self) -> None:
        if self.effect not in EFFECTS or not set(self.exposure) <= set(EXPOSURES):
            raise ValueError(f"tool {self.name}: undeclared effect or exposure")

    def annotations(self) -> dict:
        if self.effect == "read":
            return {"readOnlyHint": True, "openWorldHint": False}
        return {"readOnlyHint": False, "destructiveHint": self.effect == "destructive",
                "idempotentHint": False, "openWorldHint": False}

    def mcp_tool(self) -> dict:
        return {"name": self.name, "title": self.title, "description": self.description,
                "inputSchema": self.input, "outputSchema": self.output, "annotations": self.annotations()}


CORE_TOOLS: tuple[ToolSurface, ...] = (
    ToolSurface(
        "get_instance", "About this OneMind",
        "The box name, gateway version, hub node id and the MCP revisions it speaks. "
        "Same data as GET /v1/instance. Read-only.",
        "read", "GET /v1/instance", "instance:read", obj(), adds=("mcp",),
    ),
    ToolSurface(
        "list_nodes", "List OneMind nodes",
        "Every machine that has joined this OneMind, with its hardware, OS, k3s state and "
        "status (online, stale or offline). Same data as GET /v1/nodes. Read-only.",
        "read", "GET /v1/nodes", "nodes:read", obj(), list_of("nodes"), body_key="nodes",
    ),
    ToolSurface(
        "get_node", "One node",
        "One machine by node_id. Same data as GET /v1/nodes/{node_id}. Read-only.",
        "read", "GET /v1/nodes/{node_id}", "nodes:read", obj({"node_id": ID}, ["node_id"]),
    ),
    ToolSurface(
        "list_apps", "List Market apps",
        "The app catalog with install status, links, licence, tier and last scan. Same data "
        "as GET /v1/apps. Optional filters: category, installed. Read-only.",
        "read", "GET /v1/apps", "apps:read",
        obj({"category": {"type": "string", "maxLength": 80}, "installed": {"type": "boolean"},
             "cursor": {"type": "string", "maxLength": 20}}),
        list_of("apps"), body_key="apps", projection="ai_policy",
    ),
    ToolSurface(
        "get_app", "One Market app",
        "One catalog entry with its links, tier, scan result and requirements. Read-only.",
        "read", "GET /v1/apps", "apps:read", obj({"app_id": ID}, ["app_id"]), row_of="app_id",
        projection="ai_policy",
    ),
    ToolSurface(
        "list_actions", "List my requests",
        "Actions this agent requested, newest first, with their state "
        "(awaiting_approval, accepted, succeeded, cancelled, expired, ...). Read-only.",
        "read", "GET /v1/actions", "actions:read:own",
        obj({"state": {"type": "string", "maxLength": 40}, "type": {"type": "string", "maxLength": 40},
             "limit": {"type": "integer", "minimum": 1, "maximum": LIST_ACTIONS_MAX}}),
        list_of("actions"), body_key="actions",
    ),
    ToolSurface(
        "get_action", "One of my requests",
        "One action this agent requested, by id: its state, who decided it and the result. "
        "Use it to see whether the owner approved a request. Read-only.",
        "read", "GET /v1/actions/{action_id}", "actions:read:own", obj({"action_id": ID}, ["action_id"]),
    ),
    ToolSurface(
        "search_audit", "Search my audit records",
        "Hash-chained audit records about this agent and its requests, oldest first. "
        "Filters: event (glob, e.g. action.*), since/until (RFC 3339), after_seq. Read-only.",
        "read", "GET /v1/audit/events", "audit:read:own",
        obj({"event": {"type": "string", "maxLength": 200}, "since": {"type": "string", "maxLength": 40},
             "until": {"type": "string", "maxLength": 40}, "after_seq": {"type": "integer", "minimum": 0},
             "limit": {"type": "integer", "minimum": 1, "maximum": AUDIT_MAX}}),
        list_of("entries"), body_key="entries",
    ),
    ToolSurface(
        "request_action", "Request an app install or removal",
        "Files a request to install, remove, start, stop, restart or update an app. Removing keeps its data. "
        "Nothing changes until the owner approves it in the OneMind app; you cannot approve it yourself. "
        "The request expires after 24 hours. Returns the action id and its state (awaiting_approval); check "
        "it later with get_action. If the same request is already waiting, its id is returned instead of a new one.",
        "write", "POST /v1/actions", "actions:request:*",
        obj({"type": {"type": "string",
                      "enum": ["app.install", "app.remove", "app.start", "app.stop", "app.restart", "app.update"]},
             "app_id": {"type": "string", "minLength": 1, "maxLength": 59},
             "reason": {"type": "string", "maxLength": MAX_REASON,
                        "description": "Why you ask; shown to the owner, marked as written by an agent."}},
            ["type", "app_id"]),
        FILED,
    ),
)

CORE_TOOL_NAMES: tuple[str, ...] = tuple(t.name for t in CORE_TOOLS)
