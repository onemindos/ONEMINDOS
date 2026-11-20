# SPDX-License-Identifier: Apache-2.0
"""Read-only plugin token policy foundation (PLUGIN-SDK.md §7.1).

No credentials are issued here. Only installation-owned plugin tokens with an
explicit stored read grant may use a small known route set. New routes and token
grants fail closed until their resource-specific policies are implemented.
"""

from __future__ import annotations

import re

_APP_ID = re.compile(r"plugin:([a-z0-9](?:[-a-z0-9]*[a-z0-9])?)\Z")
_READ_GRANTS = frozenset({"nodes:read", "apps:read"})


def plugin_app_id(principal_id: str) -> str | None:
    """The plugin principal is bound to one DNS-label app id, at most 59 chars."""
    match = _APP_ID.fullmatch(principal_id)
    return match[1] if match and len(match[1]) <= 59 else None


def allows_read(*, method: str, path: str, principal_id: str, source: str,
                scopes: object, app_status: str | None, operation_id: str | None = None) -> bool:
    """Use only the stored token snapshot; never widen from a mutable catalog.

    This initial policy accepts read-only snapshots. Other plugin permission
    vocabulary, including request grants, needs its own policy before issuance.
    A wildcard/admin/unknown grant invalidates the whole snapshot, not just the
    offending entry. The general identity filter must not hide malformed grants.
    """
    if source != "app-install" or plugin_app_id(principal_id) is None:
        return False
    if app_status not in {"installed", "stopped"} or method != "GET":
        return False
    if not isinstance(scopes, list) or any(not isinstance(s, str) or s not in _READ_GRANTS for s in scopes):
        return False
    if path == "/v1/apps" and operation_id == "apps.list":
        return "apps:read" in scopes
    if path == "/v1/nodes" and operation_id == "nodes.list":
        return "nodes:read" in scopes
    if operation_id == "nodes.get" and re.fullmatch(r"/v1/nodes/[A-Za-z0-9_-]{1,64}", path):
        return "nodes:read" in scopes
    # No /apps/* wildcard: that tree includes credentials, access and plans.
    return False
