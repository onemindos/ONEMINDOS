# SPDX-License-Identifier: Apache-2.0
"""MCP revision differences, in one place (docs/leap/dev/MCP.md §8.1, REC-W9-02; DEV-MCP-10).

Revision 2026-07-28 (https://modelcontextprotocol.io/specification/2026-07-28/changelog) is stateless:
no `initialize`, no `ping`, every request carries its protocol version in `_meta` and in the
`MCP-Protocol-Version` header, plus `Mcp-Method` and `Mcp-Name` headers that must match the body.
`server/discover` is mandatory, results carry `resultType`, list results carry `ttlMs` and
`cacheScope`, and long waits use the tasks extension `io.modelcontextprotocol/tasks`.
Tool handlers never see any of this; they get the same arguments as under 2025-06-18.
"""

from __future__ import annotations

import base64
import binascii

MODERN = "2026-07-28"
LEGACY = ("2025-06-18", "2025-03-26")  # handshake era; same wire format for the methods we serve
SUPPORTED = (MODERN, *LEGACY)

K_VERSION = "io.modelcontextprotocol/protocolVersion"
K_CAPS = "io.modelcontextprotocol/clientCapabilities"
K_SERVER = "io.modelcontextprotocol/serverInfo"
TASKS_EXT = "io.modelcontextprotocol/tasks"

# Error codes reserved for the MCP specification (-32020..-32099) in 2026-07-28.
HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022

# Freshness hints (ms) for CacheableResult. Lists depend on the calling agent's scopes: private.
LIST_TTL_MS = 60_000
READ_TTL_MS = 0  # resources/read shows live hub state
CACHEABLE = {"server/discover": LIST_TTL_MS, "tools/list": LIST_TTL_MS, "resources/list": LIST_TTL_MS,
             "resources/templates/list": LIST_TTL_MS, "resources/read": READ_TTL_MS}

# Action state -> task status (the approval wait stays out of band: never input_required).
TASK_DONE = {"succeeded": "completed", "failed": "failed", "outcome_unknown": "failed",
             "cancelled": "cancelled", "expired": "cancelled", "denied": "cancelled", "rejected": "cancelled"}


def decode_header_value(v: str) -> str | None:
    """Mcp-Name may be `=?base64?...?=` when not plain ASCII. None if malformed."""
    if v.startswith("=?base64?") and v.endswith("?="):
        try:
            return base64.b64decode(v[9:-2], validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            return None
    return v


def header_problem(headers, method: str, params: dict) -> str | None:
    """Why a modern request's headers do not match its body, or None (server validation rule)."""
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    if meta.get(K_VERSION) != MODERN:
        return f"_meta {K_VERSION} must be {MODERN}"
    if headers.get("mcp-method") != method:
        return f"Mcp-Method header does not match method {method!r}"
    key = {"tools/call": "name", "resources/read": "uri"}.get(method)
    if key:
        got = decode_header_value(headers.get("mcp-name") or "")
        if got is None or got != params.get(key):
            return f"Mcp-Name header does not match params.{key}"
    return None


def client_supports_tasks(params: dict) -> bool:
    meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
    caps = meta.get(K_CAPS) if isinstance(meta.get(K_CAPS), dict) else {}
    ext = caps.get("extensions")
    return isinstance(ext, dict) and TASKS_EXT in ext


def decorate(method: str, result: dict, server_info: dict) -> dict:
    """Add what every 2026-07-28 result carries."""
    out = dict(result)
    out.setdefault("resultType", "complete")
    meta = dict(out.get("_meta") or {})
    meta[K_SERVER] = server_info
    out["_meta"] = meta
    if method in CACHEABLE:
        out["ttlMs"], out["cacheScope"] = CACHEABLE[method], "private"
    return out
