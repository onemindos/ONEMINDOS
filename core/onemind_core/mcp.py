# SPDX-License-Identifier: Apache-2.0
"""Minimal MCP server for agent principals (contract §7 and §11.3; the v0 slice of D-B9.2).

Transport: MCP Streamable HTTP, protocol revision 2025-06-18, at POST /mcp. Every request is one
JSON-RPC 2.0 message and is answered with one application/json body (the transport allows JSON
instead of an SSE stream). The server keeps no session state, so it issues no Mcp-Session-Id.
GET and DELETE /mcp answer 405: there is no server-initiated stream and no session to end.

Who may call it: only principals with kind "agent" (bearer token, as for /v1). A person gets
403 permission_denied, a missing or unknown token 401 (the §3 error envelope, before any JSON-RPC).

Tools:
- list_nodes      = GET /v1/nodes
- list_apps       = GET /v1/apps
- request_action  {type, app_id, reason?} -> creates an action exactly like POST /v1/actions,
                  with a generated idempotency key and a 24 h expiry; returns {action_id, state}.
There is deliberately no approve or deny tool: an agent requests, a person approves.

Terms: "JSON-RPC" is the request/response format MCP uses ({"jsonrpc": "2.0", "id", "method",
"params"}). A "notification" is a message without an id; it gets HTTP 202 and no body.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from . import __version__
from .actions import ActionParams, ActionRequest, ActionService
from .auth import Principal
from .errors import ApiError

PROTOCOL_VERSION = "2025-06-18"
# Older revisions whose wire format for these four methods is the same; a client that asks for
# one of them gets it back, anything else gets PROTOCOL_VERSION (MCP lifecycle negotiation).
COMPATIBLE_VERSIONS = (PROTOCOL_VERSION, "2025-03-26")
REQUEST_TTL = timedelta(hours=24)
MAX_BODY = 256 * 1024
MAX_REASON = 500

# JSON-RPC 2.0 error codes.
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = (
    -32700, -32600, -32601, -32602, -32603,
)

TOOLS: list[dict] = [
    {
        "name": "list_nodes",
        "title": "List OneMind nodes",
        "description": (
            "Every machine that has joined this OneMind, with its hardware, OS, k3s state and "
            "status (online, stale or offline). Same data as GET /v1/nodes. Read-only."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "outputSchema": {
            "type": "object",
            "properties": {"nodes": {"type": "array", "items": {"type": "object"}}},
            "required": ["nodes"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "list_apps",
        "title": "List Market apps",
        "description": (
            "The app catalog with install status, links, licence, tier and last scan. Same data "
            "as GET /v1/apps. Read-only."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "outputSchema": {
            "type": "object",
            "properties": {"apps": {"type": "array", "items": {"type": "object"}}},
            "required": ["apps"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "request_action",
        "title": "Request an app install or removal",
        "description": (
            "Files a request to install or remove an app. Nothing changes until the owner approves "
            "it in the OneMind dashboard; you cannot approve it yourself. The request expires "
            "after 24 hours. Returns the action id and its state (awaiting_approval)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["app.install", "app.remove"]},
                "app_id": {"type": "string", "minLength": 1, "maxLength": 59},
                "reason": {
                    "type": "string", "maxLength": MAX_REASON,
                    "description": "Why you ask; shown to the owner in the audit log.",
                },
            },
            "required": ["type", "app_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {"action_id": {"type": "string"}, "state": {"type": "string"}},
            "required": ["action_id", "state"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False,
                        "openWorldHint": False},
    },
]
TOOL_NAMES = {t["name"] for t in TOOLS}


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _rpc_error(id_: Any, code: int, message: str, status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}},
    )


def _tool_result(structured: dict, is_error: bool = False) -> dict:
    # structuredContent plus the same JSON as text, for clients that read only `content`.
    return {
        "content": [{"type": "text", "text": json.dumps(structured, separators=(",", ":"))}],
        "structuredContent": structured,
        "isError": is_error,
    }


class McpEndpoint:
    def __init__(
        self,
        *,
        list_nodes: Callable[[], list[dict]],
        list_apps: Callable[[], list[dict]],
        actions: ActionService,
        clock: Callable[[], datetime],
        deny: Callable[[Principal, str], ApiError],
    ):
        self.list_nodes = list_nodes
        self.list_apps = list_apps
        self.actions = actions
        self.clock = clock
        self.deny = deny

    # ---- HTTP layer ---------------------------------------------------------------------
    async def handle(self, request: Request, principal: Principal) -> Response:
        if principal.kind != "agent":
            raise self.deny(principal, "use the MCP endpoint (agents only)")
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc.lower() != (request.headers.get("host") or "").lower():
            # Streamable HTTP: servers must validate Origin (DNS rebinding). Agents are not
            # browsers; a cross-origin browser request is refused.
            raise ApiError(403, "permission_denied", "cross-origin requests to /mcp are not allowed")
        version = request.headers.get("mcp-protocol-version")
        if version and version not in COMPATIBLE_VERSIONS:
            return _rpc_error(None, INVALID_REQUEST, f"unsupported MCP-Protocol-Version {version}", 400)
        # Read at most MAX_BODY bytes: the cap holds for chunked bodies and lying Content-Length too.
        raw = bytearray()
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAX_BODY:
                return _rpc_error(None, INVALID_REQUEST, "message too large", 413)
        try:
            msg = json.loads(raw)
        except ValueError:
            return _rpc_error(None, PARSE_ERROR, "body is not JSON", 400)
        if isinstance(msg, list):  # batching was removed in 2025-06-18
            return _rpc_error(None, INVALID_REQUEST, "JSON-RPC batches are not supported", 400)
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return _rpc_error(None, INVALID_REQUEST, "not a JSON-RPC 2.0 message", 400)
        if "method" not in msg:  # a response from the client: nothing was asked, accept it
            return Response(status_code=202)
        id_ = msg.get("id")
        if "id" not in msg:  # notification, e.g. notifications/initialized
            return Response(status_code=202)
        if not isinstance(msg.get("method"), str) or not isinstance(id_, (str, int)) or isinstance(id_, bool):
            return _rpc_error(None, INVALID_REQUEST, "method must be a string and id a string or integer", 400)
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            return _rpc_error(id_, INVALID_PARAMS, "params must be an object")
        try:
            result = self.dispatch(principal, msg["method"], params)
        except _RpcError as e:
            return _rpc_error(id_, e.code, e.message)
        return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})

    # ---- JSON-RPC methods ---------------------------------------------------------------
    def dispatch(self, principal: Principal, method: str, params: dict) -> dict:
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {
                "protocolVersion": asked if asked in COMPATIBLE_VERSIONS else PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "onemind-gateway", "title": "OneMind gateway", "version": __version__},
                "instructions": (
                    "OneMind hub tools. You can read nodes and apps and request app installs or "
                    "removals. Every request waits for the owner's approval; you cannot approve."
                ),
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            return self.call_tool(principal, params.get("name"), params.get("arguments") or {})
        raise _RpcError(METHOD_NOT_FOUND, f"method {method!r} not found")

    def call_tool(self, principal: Principal, name: object, args: object) -> dict:
        if name not in TOOL_NAMES:
            raise _RpcError(INVALID_PARAMS, f"unknown tool {name!r}")
        if not isinstance(args, dict):
            raise _RpcError(INVALID_PARAMS, "arguments must be an object")
        if name in ("list_nodes", "list_apps"):
            if args:
                raise _RpcError(INVALID_PARAMS, f"{name} takes no arguments")
            if name == "list_nodes":
                return _tool_result({"nodes": self.list_nodes()})
            return _tool_result({"apps": self.list_apps()})
        return self._request_action(principal, args)

    def _request_action(self, principal: Principal, args: dict) -> dict:
        extra = set(args) - {"type", "app_id", "reason"}
        reason = args.get("reason")
        if extra:
            raise _RpcError(INVALID_PARAMS, f"unknown arguments: {sorted(extra)}")
        if reason is not None and (not isinstance(reason, str) or len(reason) > MAX_REASON):
            raise _RpcError(INVALID_PARAMS, f"reason must be a string of at most {MAX_REASON} characters")
        try:
            req = ActionRequest(
                type=args.get("type"),
                params=ActionParams(app_id=args.get("app_id")),
                idempotency_key=f"mcp-{uuid.uuid4()}",
                expires_at=self.clock() + REQUEST_TTL,
            )
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
            raise _RpcError(INVALID_PARAMS, f"invalid arguments: {problems}") from exc
        try:
            body, _ = self.actions.create(principal, req, reason=reason or None)
        except ApiError as e:
            # A refusal is a tool result the model can read and act on, not a protocol error.
            return _tool_result({"error": e.error, "message": e.message}, is_error=True)
        return _tool_result({"action_id": body["id"], "state": body["state"]})
