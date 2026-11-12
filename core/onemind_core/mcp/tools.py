# SPDX-License-Identifier: Apache-2.0
"""The MCP catalogue: read tools, the one request-only tool, and resources (MCP.md §4).

Every tool is a thin call into the same service functions as a /v1 route (MCP.md §3 rule 2).
There is no approve, deny, grant, token or policy tool, and nothing in this package can reach
the approve or deny path: the router hands it a `Services` object that has no such function
(checked by tests/test_mcp_catalogue.py).

Agents read only their own actions and audit records (`actions:read:own`, `audit:read:own`, F-19).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError

from .. import __version__
from ..actions import ActionParams, ActionRequest
from ..auth import Principal
from ..errors import ApiError
from .limits import Limits
from .untrusted import META_KEY, mark

CATALOG_VERSION = "1.1.0"
REQUEST_TTL = timedelta(hours=24)
MAX_REASON = 500
POLL_AFTER_S = 10
LIST_ACTIONS_MAX = 50
AUDIT_MAX = 100
APPS_PAGE = 100
INVALID_PARAMS = -32602


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Services:
    """What the MCP layer may call. Built by routers/mcp.py from the gateway; read and request only."""

    instance: Callable[[], dict]
    list_nodes: Callable[[], list[dict]]
    get_node: Callable[[str], dict | None]
    list_apps: Callable[[], list[dict]]
    own_actions: Callable[[str], list[dict]]
    get_action: Callable[[str], dict]
    request: Callable[[Principal, ActionRequest, str | None], tuple[dict, bool]]
    audit_list: Callable[..., tuple[list[dict], bool]]
    clock: Callable[[], datetime]


# ---- schemas ---------------------------------------------------------------------------------
def _obj(props: dict | None = None, required: list[str] | None = None) -> dict:
    s: dict[str, Any] = {"type": "object", "properties": props or {}, "additionalProperties": False}
    if required:
        s["required"] = required
    return s


READ = {"readOnlyHint": True, "openWorldHint": False}
ID = {"type": "string", "minLength": 1, "maxLength": 200}
LIST_OF = lambda key: {"type": "object", "properties": {key: {"type": "array", "items": {"type": "object"}},  # noqa: E731
                                                        "next_cursor": {"type": ["string", "null"]}}, "required": [key]}
ANY_OBJ = {"type": "object"}

TOOLS: list[dict] = [
    {
        "name": "get_instance", "title": "About this OneMind",
        "description": "The box name, gateway version, hub node id and the MCP revisions it speaks. "
                       "Same data as GET /v1/instance. Read-only.",
        "inputSchema": _obj(), "outputSchema": ANY_OBJ, "annotations": READ,
    },
    {
        "name": "list_nodes", "title": "List OneMind nodes",
        "description": "Every machine that has joined this OneMind, with its hardware, OS, k3s state and "
                       "status (online, stale or offline). Same data as GET /v1/nodes. Read-only.",
        "inputSchema": _obj(), "outputSchema": LIST_OF("nodes"), "annotations": READ,
    },
    {
        "name": "get_node", "title": "One node",
        "description": "One machine by node_id. Same data as GET /v1/nodes/{node_id}. Read-only.",
        "inputSchema": _obj({"node_id": ID}, ["node_id"]), "outputSchema": ANY_OBJ, "annotations": READ,
    },
    {
        "name": "list_apps", "title": "List Market apps",
        "description": "The app catalog with install status, links, licence, tier and last scan. Same data "
                       "as GET /v1/apps. Optional filters: category, installed. Read-only.",
        "inputSchema": _obj({
            "category": {"type": "string", "maxLength": 80},
            "installed": {"type": "boolean"},
            "cursor": {"type": "string", "maxLength": 20},
        }),
        "outputSchema": LIST_OF("apps"), "annotations": READ,
    },
    {
        "name": "get_app", "title": "One Market app",
        "description": "One catalog entry with its links, tier, scan result and requirements. Read-only.",
        "inputSchema": _obj({"app_id": ID}, ["app_id"]), "outputSchema": ANY_OBJ, "annotations": READ,
    },
    {
        "name": "list_actions", "title": "List my requests",
        "description": "Actions this agent requested, newest first, with their state "
                       "(awaiting_approval, accepted, succeeded, cancelled, expired, ...). Read-only.",
        "inputSchema": _obj({
            "state": {"type": "string", "maxLength": 40},
            "type": {"type": "string", "maxLength": 40},
            "limit": {"type": "integer", "minimum": 1, "maximum": LIST_ACTIONS_MAX},
        }),
        "outputSchema": LIST_OF("actions"), "annotations": READ,
    },
    {
        "name": "get_action", "title": "One of my requests",
        "description": "One action this agent requested, by id: its state, who decided it and the result. "
                       "Use it to see whether the owner approved a request. Read-only.",
        "inputSchema": _obj({"action_id": ID}, ["action_id"]), "outputSchema": ANY_OBJ, "annotations": READ,
    },
    {
        "name": "search_audit", "title": "Search my audit records",
        "description": "Hash-chained audit records about this agent and its requests, oldest first. "
                       "Filters: event (glob, e.g. action.*), since/until (RFC 3339), after_seq. Read-only.",
        "inputSchema": _obj({
            "event": {"type": "string", "maxLength": 200},
            "since": {"type": "string", "maxLength": 40},
            "until": {"type": "string", "maxLength": 40},
            "after_seq": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": AUDIT_MAX},
        }),
        "outputSchema": LIST_OF("entries"), "annotations": READ,
    },
    {
        "name": "request_action", "title": "Request an app install or removal",
        "description": (
            "Files a request to install or remove an app. Nothing changes until the owner approves "
            "it in the OneMind app; you cannot approve it yourself. The request expires after 24 hours. "
            "Returns the action id and its state (awaiting_approval); check it later with get_action. "
            "If the same request is already waiting, its id is returned instead of a new one."
        ),
        "inputSchema": _obj({
            "type": {"type": "string", "enum": ["app.install", "app.remove"]},
            "app_id": {"type": "string", "minLength": 1, "maxLength": 59},
            "reason": {"type": "string", "maxLength": MAX_REASON,
                       "description": "Why you ask; shown to the owner, marked as written by an agent."},
        }, ["type", "app_id"]),
        "outputSchema": {
            "type": "object",
            "properties": {"action_id": {"type": "string"}, "state": {"type": "string"}},
            "required": ["action_id", "state"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    },
]
TOOL_NAMES = [t["name"] for t in TOOLS]
READ_TOOLS = set(TOOL_NAMES) - {"request_action"}

RESOURCES = [
    {"uri": "onemind://catalog", "name": "catalog", "title": "App catalog",
     "description": "Every Market app: id, name, version, category, tier, scan, install status.",
     "mimeType": "application/json"},
    {"uri": "onemind://nodes", "name": "nodes", "title": "Nodes", "description": "Every machine in this OneMind.",
     "mimeType": "application/json"},
    {"uri": "onemind://audit/recent", "name": "audit-recent", "title": "My recent audit records",
     "description": "The last 100 audit records about this agent and its requests.", "mimeType": "application/json"},
]
RESOURCE_TEMPLATES = [
    {"uriTemplate": "onemind://catalog/{app_id}", "name": "app", "title": "One app", "mimeType": "application/json"},
    {"uriTemplate": "onemind://nodes/{node_id}", "name": "node", "title": "One node", "mimeType": "application/json"},
    {"uriTemplate": "onemind://actions/{action_id}", "name": "action", "title": "One of my requests",
     "mimeType": "application/json"},
]

# Where third-party text lives in each result (MCP.md §6.1).
APP_FIELDS = ["name", "description", "category", "source", "license", "links.*"]
NODE_FIELDS = ["hostname", "os.pretty"]
AUDIT_FIELDS = ["data.reason", "data.message"]
ACTION_FIELDS = ["result.message"]


def _under(prefix: str, fields: list[str]) -> list[str]:
    return [f"{prefix}.*.{f}" for f in fields] if prefix else list(fields)


def _source(structured: dict, coll: str, id_field: str, kind: str):
    """Name the wrapper source after the item's id: apps[2].description -> app:ntfy:description."""

    def name(path: str) -> str:
        if coll and path.startswith(coll + "["):
            idx = int(path[len(coll) + 1: path.index("]")])
            rest = path[path.index("]") + 2:]
            item = structured.get(coll, [])[idx]
            return f"{kind}:{item.get(id_field)}:{rest}"
        if not coll:
            return f"{kind}:{structured.get(id_field)}:{path}"
        return path

    return name


def result(structured: dict, patterns: list[str] | None = None, source=None, is_error: bool = False) -> dict:
    """structuredContent plus the same JSON as text; untrusted values marked when patterns are given."""
    if patterns:
        structured, text, paths = mark(structured, patterns, source)
    else:
        text, paths = json.dumps(structured, separators=(",", ":"), ensure_ascii=False), []
    out = {"content": [{"type": "text", "text": text}], "structuredContent": structured, "isError": is_error}
    if paths:
        out["_meta"] = {META_KEY: paths}
    return out


def refusal(error: str, message: str, **extra) -> dict:
    return result({"error": error, "message": message, "docs": f"onemind://docs/errors/{error}", **extra},
                  is_error=True)


def _args(args: dict, allowed: set[str]) -> dict:
    extra = set(args) - allowed
    if extra:
        raise RpcError(INVALID_PARAMS, f"unknown arguments: {sorted(extra)}")
    return args


def _str(args: dict, key: str, required: bool = False, max_len: int = 200) -> str | None:
    v = args.get(key)
    if v is None and not required:
        return None
    if not isinstance(v, str) or not v or len(v) > max_len:
        raise RpcError(INVALID_PARAMS, f"{key} must be a non-empty string of at most {max_len} characters")
    return v


def _int(args: dict, key: str, lo: int, hi: int | None) -> int | None:
    v = args.get(key)
    if v is None:
        return None
    if not isinstance(v, int) or isinstance(v, bool) or v < lo or (hi is not None and v > hi):
        raise RpcError(INVALID_PARAMS, f"{key} must be an integer in [{lo}, {hi if hi is not None else '∞'}]")
    return v


class Catalogue:
    def __init__(self, svc: Services, limits: Limits):
        self.svc = svc
        self.limits = limits

    # ---- tools -----------------------------------------------------------------------------
    def call(self, p: Principal, name: object, args: object) -> dict:
        if name not in TOOL_NAMES:
            raise RpcError(INVALID_PARAMS, f"unknown tool {name!r}")
        if not isinstance(args, dict):
            raise RpcError(INVALID_PARAMS, "arguments must be an object")
        if name in READ_TOOLS:
            wait = self.limits.reads.hit(p.id)
            if wait:
                return refusal("rate_limited", "too many read calls; slow down", retry_after_s=wait)
        return getattr(self, f"t_{name}")(p, args)

    def t_get_instance(self, p, args):
        _args(args, set())
        inst = dict(self.svc.instance())
        from .server import COMPATIBLE_VERSIONS

        inst["mcp"] = {"revisions": list(COMPATIBLE_VERSIONS), "catalog_version": CATALOG_VERSION}
        return result(inst)

    def t_list_nodes(self, p, args):
        _args(args, set())
        s = {"nodes": self.svc.list_nodes()}
        return result(s, _under("nodes", NODE_FIELDS), _source(s, "nodes", "node_id", "node"))

    def t_get_node(self, p, args):
        node_id = _str(_args(args, {"node_id"}), "node_id", True)
        node = self.svc.get_node(node_id)
        if node is None:
            return refusal("not_found", "no such node")
        return result(node, NODE_FIELDS, _source(node, "", "node_id", "node"))

    def _apps(self, category=None, installed=None) -> list[dict]:
        rows = self.svc.list_apps()
        if category is not None:
            rows = [a for a in rows if a.get("category") == category]
        if installed is not None:
            rows = [a for a in rows if bool(a.get("installed")) is installed]
        return rows

    def t_list_apps(self, p, args):
        _args(args, {"category", "installed", "cursor"})
        installed = args.get("installed")
        if installed is not None and not isinstance(installed, bool):
            raise RpcError(INVALID_PARAMS, "installed must be a boolean")
        cursor = _str(args, "cursor", max_len=20)
        start = int(cursor) if cursor and cursor.isdigit() else 0
        rows = self._apps(_str(args, "category", max_len=80), installed)
        page = rows[start: start + APPS_PAGE]
        s: dict[str, Any] = {"apps": page}
        if start + APPS_PAGE < len(rows):
            s["next_cursor"] = str(start + APPS_PAGE)
        return result(s, _under("apps", APP_FIELDS), _source(s, "apps", "id", "app"))

    def t_get_app(self, p, args):
        app_id = _str(_args(args, {"app_id"}), "app_id", True)
        app = next((a for a in self.svc.list_apps() if a.get("id") == app_id), None)
        if app is None:
            return refusal("not_found", f"app {app_id!r} is not in the catalog")
        return result(app, APP_FIELDS, _source(app, "", "id", "app"))

    def t_list_actions(self, p, args):
        _args(args, {"state", "type", "limit"})
        state, type_ = _str(args, "state", max_len=40), _str(args, "type", max_len=40)
        limit = _int(args, "limit", 1, LIST_ACTIONS_MAX) or LIST_ACTIONS_MAX
        rows = [a for a in self.svc.own_actions(p.id)
                if (state is None or a["state"] == state) and (type_ is None or a["type"] == type_)]
        rows.sort(key=lambda a: a["created_at"], reverse=True)
        s = {"actions": rows[:limit]}
        return result(s, _under("actions", ACTION_FIELDS), _source(s, "actions", "id", "action"))

    def _own_action(self, p: Principal, action_id: str) -> dict | None:
        try:
            a = self.svc.get_action(action_id)
        except ApiError:
            return None
        return a if (a.get("requested_by") or {}).get("id") == p.id else None

    def t_get_action(self, p, args):
        action_id = _str(_args(args, {"action_id"}), "action_id", True)
        a = self._own_action(p, action_id)
        if a is None:  # someone else's action looks exactly like a missing one
            return refusal("not_found", "no such action among your requests")
        return result(a, ACTION_FIELDS, _source(a, "", "id", "action"))

    def t_search_audit(self, p, args):
        _args(args, {"event", "since", "until", "after_seq", "limit"})
        rows, more = self.svc.audit_list(
            p, event=_str(args, "event"), since=_str(args, "since", max_len=40), until=_str(args, "until", max_len=40),
            after_seq=_int(args, "after_seq", 0, None), limit=_int(args, "limit", 1, AUDIT_MAX) or AUDIT_MAX,
        )
        s: dict[str, Any] = {"entries": rows}
        if more and rows:
            s["next_cursor"] = str(rows[-1]["seq"])
        return result(s, _under("entries", AUDIT_FIELDS), _source(s, "entries", "seq", "audit"))

    def t_request_action(self, p, args):
        _args(args, {"type", "app_id", "reason"})
        reason = args.get("reason")
        if reason is not None and (not isinstance(reason, str) or len(reason) > MAX_REASON):
            raise RpcError(INVALID_PARAMS, f"reason must be a string of at most {MAX_REASON} characters")
        try:
            req = ActionRequest(
                type=args.get("type"),
                params=ActionParams(app_id=args.get("app_id")),
                idempotency_key=f"mcp-{uuid.uuid4()}",
                expires_at=self.svc.clock() + REQUEST_TTL,
            )
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors())
            raise RpcError(INVALID_PARAMS, f"invalid arguments: {problems}") from exc
        pending = [a for a in self.svc.own_actions(p.id) if a["state"] in ("requested", "awaiting_approval")]
        same = next((a for a in pending if a["type"] == req.type and a["params"].get("app_id") == req.params.app_id), None)
        if same is not None:  # no duplicate approval cards
            return result(self._filed(same) | {"duplicate": True})
        cap = self.limits.settings.pending_max
        if len(pending) >= cap:
            return refusal("rate_limited", f"{cap} requests already wait for the owner", reason="too_many_pending")
        wait = self.limits.requests.hit(p.id)
        if wait:
            return refusal("rate_limited", "too many requests this hour", retry_after_s=wait)
        clean_reason = None
        if reason:
            from .untrusted import clean

            clean_reason = clean(reason, "reason") or None
        try:
            body, _ = self.svc.request(p, req, clean_reason)
        except ApiError as e:
            # A refusal is a tool result the model can read and act on, not a protocol error.
            return refusal(e.error, e.message)
        return result(self._filed(body))

    @staticmethod
    def _filed(a: dict) -> dict:
        return {
            "action_id": a["id"], "state": a["state"], "expires_at": a.get("expires_at"),
            "poll_after_s": POLL_AFTER_S,
            "next": "The owner must approve this in the OneMind app. Check it with get_action.",
        }

    # ---- resources -------------------------------------------------------------------------
    def read_resource(self, p: Principal, uri: object) -> dict:
        if not isinstance(uri, str) or not uri.startswith("onemind://"):
            raise RpcError(INVALID_PARAMS, "uri must be an onemind:// resource")
        wait = self.limits.reads.hit(p.id)
        if wait:
            raise RpcError(-32000, f"rate_limited: retry after {wait} s")
        path = uri[len("onemind://"):]
        parts = path.split("/")
        if path == "catalog":
            s = {"apps": [{k: a.get(k) for k in ("id", "name", "version", "category", "tier", "scan", "status")}
                          for a in self.svc.list_apps()]}
            r = result(s, _under("apps", ["name", "category"]), _source(s, "apps", "id", "app"))
        elif len(parts) == 2 and parts[0] == "catalog":
            r = self.t_get_app(p, {"app_id": parts[1]})
        elif path == "nodes":
            r = self.t_list_nodes(p, {})
        elif len(parts) == 2 and parts[0] == "nodes":
            r = self.t_get_node(p, {"node_id": parts[1]})
        elif len(parts) == 2 and parts[0] == "actions":
            r = self.t_get_action(p, {"action_id": parts[1]})
        elif path == "audit/recent":
            rows, _ = self.svc.audit_list(p, limit=100_000)
            s = {"entries": rows[-100:]}
            r = result(s, _under("entries", AUDIT_FIELDS), _source(s, "entries", "seq", "audit"))
        else:
            raise RpcError(-32002, f"resource not found: {uri}")
        if r["isError"]:
            raise RpcError(-32002, f"resource not found: {uri}")
        content = {"uri": uri, "mimeType": "application/json", "text": r["content"][0]["text"]}
        if "_meta" in r:
            content["_meta"] = r["_meta"]
        return {"contents": [content]}
