# SPDX-License-Identifier: Apache-2.0
"""Read-only projection of installed apps with plugin declarations (#178).

Versions come from persisted runtime receipts, never mutable catalog metadata.
This view grants no runtime capability.
"""
from __future__ import annotations

from typing import Literal

from fastapi import Request
from pydantic import BaseModel, Field

from ..auth import Principal
from ..context import Gateway


class PluginSummary(BaseModel):
    id: str
    name: str
    installed_version: str | None = Field(description="Persisted installed version; null when no runtime receipt exists.")
    status: Literal["installed", "stopped"]


def installed_plugins(gw: Gateway, request: Request, principal: Principal) -> list[PluginSummary]:
    """Use the same sharing filters as the Market; never expose raw manifests or secrets."""
    states = gw.repo.list_app_states()
    rows = []
    for app_id, entry in sorted(gw.catalog.load().items()):
        state = states.get(app_id)
        if state is None or state.status not in {"installed", "stopped"}:
            continue
        spec = entry.manifest.get("spec") or {}
        plugin = spec.get("plugin")
        extensions = spec.get("extensions")
        if not isinstance(plugin, dict) or plugin.get("principal") is not True or not isinstance(extensions, dict):
            continue
        if not all(check(request, principal, app_id) for check in gw.app_filters):
            continue
        # Catalog validation owns declaration validity. This response only projects
        # safe identity/status fields; no credential, backend or filesystem path escapes.
        tools = extensions.get("tools")
        widgets = extensions.get("widgets", [])
        if not isinstance(tools, list) or not tools or not isinstance(widgets, list):
            continue
        metadata = entry.manifest["metadata"]
        runtime = gw.repo.get_runtime(app_id)
        rows.append(PluginSummary(
            id=app_id, name=str(metadata["name"]), installed_version=runtime.version if runtime else None,
            status=state.status,
        ))
    return rows
