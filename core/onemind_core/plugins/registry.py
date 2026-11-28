# SPDX-License-Identifier: Apache-2.0
"""Read-only projection of installed apps with plugin declarations (#178).

Versions come from persisted runtime receipts, never mutable catalog metadata.
This view grants no runtime capability.
"""
from __future__ import annotations

from typing import Literal

from fastapi import Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .models import PluginInstallRow

from ..auth import Principal
from ..context import Gateway


class PluginSlot(BaseModel):
    """One of the five defined places a plugin can show up. `declared` is false when its manifest names nothing for it."""
    slot: Literal["home_tile", "map_layer", "settings_panel", "commands", "dock_item"]
    declared: bool
    names: list[str] = Field(default_factory=list, description="Ids or names the plugin declares for this slot.")
    approval: Literal["none", "each_time"] = Field(
        default="none", description="each_time when a command can change something: a person approves every call.")


class PluginSummary(BaseModel):
    id: str
    name: str
    installed_version: str | None = Field(description="Persisted installed version; null when no runtime receipt exists.")
    status: Literal["installed", "stopped", "failed"]
    slots: list[PluginSlot] = Field(default_factory=list, description="The five defined places, in a fixed order.")


def _names(items, key: str) -> list[str]:
    return [str(x[key]) for x in items if isinstance(x, dict) and isinstance(x.get(key), str)] if isinstance(items, list) else []


def plugin_slots(spec: dict, settings_schema: dict | None) -> list[PluginSlot]:
    """Project the manifest into the design's five places. Names only: no schema, backend or secret leaves."""
    ext = spec.get("extensions") or {}
    tools = [t for t in ext.get("tools", []) if isinstance(t, dict)]
    widgets = _names(ext.get("widgets"), "id")
    layers = _names(spec.get("mapLayers"), "id")
    props = (settings_schema or {}).get("properties") if isinstance((settings_schema or {}).get("properties"), dict) else {}
    asks = any(t.get("effect") in ("write", "destructive") for t in tools)
    return [
        PluginSlot(slot="home_tile", declared=bool(widgets), names=widgets),
        PluginSlot(slot="map_layer", declared=bool(layers), names=layers),
        PluginSlot(slot="settings_panel", declared=bool(props), names=sorted(str(k) for k in props)),
        PluginSlot(slot="commands", declared=bool(tools), names=_names(tools, "name"),
                   approval="each_time" if asks else "none"),
        PluginSlot(slot="dock_item", declared=bool(spec.get("web")), names=[]),
    ]


def installed_plugins(gw: Gateway, request: Request, principal: Principal) -> list[PluginSummary]:
    """Use the same sharing filters as the Market; never expose raw manifests or secrets."""
    states = gw.repo.list_app_states()
    rows = []
    catalog = gw.catalog.load()
    with gw.db.session() as session:
        installs = list(session.scalars(select(PluginInstallRow)))
        receipts = {row.app_id: row.manifest for row in installs}
        schemas = {row.app_id: row.settings_schema for row in installs}
    for app_id in sorted(catalog.keys() | receipts.keys()):
        state = states.get(app_id)
        if state is None or state.status not in {"installed", "stopped", "failed"}:
            continue
        manifest = receipts.get(app_id) or catalog[app_id].manifest
        spec = manifest.get("spec") or {}
        plugin = spec.get("plugin")
        extensions = spec.get("extensions")
        if (not isinstance(extensions, dict) or not extensions
                or (plugin is not None and (not isinstance(plugin, dict) or plugin.get("principal") is not True))):
            continue
        if not all(check(request, principal, app_id) for check in gw.app_filters):
            continue
        # Catalog validation owns declaration validity. This response only projects
        # safe identity/status fields; no credential, backend or filesystem path escapes.
        tools = extensions.get("tools", [])
        widgets = extensions.get("widgets", [])
        if not isinstance(tools, list) or not isinstance(widgets, list):
            continue
        if tools and plugin is None:
            continue
        metadata = manifest["metadata"]
        runtime = gw.repo.get_runtime(app_id)
        rows.append(PluginSummary(
            id=app_id, name=str(metadata["name"]), installed_version=runtime.version if runtime else None,
            status=state.status, slots=plugin_slots(spec, schemas.get(app_id)),
        ))
    return rows
