# SPDX-License-Identifier: Apache-2.0
"""GET /v1/surfaces: the surface registry (surfaces/registry.py, #605).

One list of everything the enabled apps plug into: the tools agents and buttons call (with effect,
exposure and the scope each needs), cards, search providers, share targets, notification topics, map
layers, Settings pages and backup units, plus what was refused and why. Built-ins come from their
descriptors; installed Market apps from their approved installation receipts. Every client reads this one
list, so a new built-in needs no client release for its declared surfaces. It replaces GET /v1/builtins
(provisional) for new clients.

After builtins (ORDER 135, which loads the descriptors and the on/off switch) and before /mcp (ORDER 140),
whose request-only built-in tools come from this registry.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel
from sqlalchemy import select

from ..actions import APP_CLAIMS
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..notify.catalogue import lookup
from ..plugins.models import PluginInstallRow
from ..surfaces import parity
from ..surfaces.core import CORE_TOOLS
from ..surfaces.registry import MarketApp, SurfaceRegistry

log = logging.getLogger("onemind.surfaces")

register_route_scope("GET,HEAD", r"/v1/surfaces", ("apps:read",))

ORDER = 137


class SurfaceApp(BaseModel):
    id: str
    name: str
    description: str | None = None
    origin: Literal["builtin", "market"]
    phone: dict  # built-in: the descriptor's spec.phone (entry native | web | none, screen); Market: entry web | none


class SurfaceTool(BaseModel):
    name: str            # core and built-in: the MCP tool name; Market: <app_id>__<tool> (market_tool_name)
    app_id: str | None   # null for the gateway's own tools
    title: str
    effect: Literal["read", "write", "destructive"]
    exposure: list[Literal["mcp", "rest", "cli"]]
    route: str | None        # "METHOD /path" the tool calls; a core read tool's body equals the route's
    action_type: str | None  # the action type a request-only or Market write tool files; a person approves it
    scope: str               # the token scope the tool needs (on /mcp, or on the Market tool route)


class SurfaceCard(BaseModel):
    app_id: str
    id: str
    title: str
    template: Literal["stat", "list", "progress", "status", "series"]
    source: str  # built-in: GET /v1/path; Market: POST /v1/plugins/{id}/tools/{tool}. Its output declares observed_at
    tool: str | None = None   # Market: the read tool the card calls (<app_id>__<tool>)
    args: dict | None = None  # Market: the arguments the widget passes to that tool


class SurfaceSearch(BaseModel):
    app_id: str
    provider: str
    types: list[str]


class SurfaceShare(BaseModel):
    app_id: str
    accepts: list[str]
    verbs: list[Literal["open", "add"]]


class SurfaceTopic(BaseModel):
    app_id: str
    id: str
    title: str | None = None
    events: list[str]


class SurfaceSource(BaseModel):
    """A map layer or Settings page: drawn by the host from one public read operation ("GET /v1/..."), or,
    for a Market app's map layer, `emits`: the layer emits of that app's own bridge, served by the gateway."""

    app_id: str
    id: str
    title: str
    source: str


class SurfaceBackupUnit(BaseModel):
    app_id: str
    kind: str  # table | dir (a built-in's own); app (a whole Market app, copied by the backup service)
    name: str


class SurfaceRefusal(BaseModel):
    app_id: str
    kind: Literal["tool", "card", "topic", "layer"]
    id: str
    reason: str


class SurfacesOut(BaseModel):
    apps: list[SurfaceApp]
    tools: list[SurfaceTool]
    cards: list[SurfaceCard]
    search: list[SurfaceSearch]
    share: list[SurfaceShare]
    notifications: list[SurfaceTopic]
    map_layers: list[SurfaceSource]
    settings_pages: list[SurfaceSource]
    backup_units: list[SurfaceBackupUnit]
    refused: list[SurfaceRefusal]


def register(app: FastAPI, gw: Gateway) -> None:
    def event_topic(event: str) -> str | None:
        spec = lookup(event)
        return spec.topic if spec else None

    def market_apps() -> list[MarketApp]:
        """Installed Market apps running their approved receipt, read now. Tools are what the plugin
        tool route serves (plugins/tools.py), so a stopped or removed app, or a changed bundle, has none."""
        tools = getattr(app.state, "plugin_tools", None)  # mounted later (ORDER 275); looked up per call
        if tools is None:
            return []
        with gw.db.session() as session:
            ids = sorted(session.scalars(select(PluginInstallRow.app_id)))
        out = []
        for app_id in ids:
            try:
                row = tools.installed(app_id)
                meta, spec = row.manifest["metadata"], row.manifest["spec"]
                declared = (spec.get("extensions") or {}).get("tools") or []
            except (ApiError, KeyError, TypeError):
                continue
            served = {}
            for item in declared if isinstance(declared, list) else []:
                try:
                    served[item["name"]] = tools.lookup(app_id, item["name"])[2]
                except (ApiError, KeyError, TypeError):
                    continue
            out.append(MarketApp(id=app_id, name=str(meta.get("name", app_id)),
                                 description=meta.get("description") if isinstance(meta.get("description"), str) else None, spec=spec, served=served))
        return out

    registry = SurfaceRegistry(
        app.state.builtins,
        known_action=lambda t: t in gw.actions.feature_types or t in APP_CLAIMS,
        event_topic=event_topic,
        openapi=app.openapi,
        market=market_apps,
    )
    app.state.surfaces = registry

    def check_parity() -> None:
        """Once every route is mounted: name any route with no tool and no human-only entry (CI fails
        on these; a box built with an extra router says so in its log instead of serving it silently)."""
        keys = parity.route_keys(app)
        gaps = [p for p in parity.problems(keys, {t.route: t.name for t in CORE_TOOLS}) if p.split(" has no tool")[0] in keys]
        if gaps:
            log.warning("surface parity: %d route(s) have no tool and no human-only entry: %s", len(gaps),
                        "; ".join(g.split(" has no tool")[0] for g in gaps))
    gw.on_startup(check_parity)

    @app.get("/v1/surfaces", operation_id="surfaces.list", tags=["apps"], response_model=SurfacesOut,
             responses=error_responses(401, 403))
    def list_surfaces(request: Request, p: Principal = Depends(gw.principal)):
        """Everything the switched-on built-ins and running Market apps plug into, read live: a
        switched-off built-in, or a stopped or removed Market app, is in no list.
        Declarations the gateway cannot prove (an unregistered action type, an event the notify
        catalogue does not route to the topic, a card whose source declares no observed_at) are
        under `refused` and served nowhere."""
        return registry.view(lambda app_id: all(f(request, p, app_id) for f in gw.app_filters))
