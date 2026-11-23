# SPDX-License-Identifier: Apache-2.0
"""GET /v1/surfaces: the surface registry (surfaces/registry.py, #605).

One list of everything the enabled apps plug into: the tools agents and buttons call (with effect,
exposure and the scope each needs), cards, search providers, share targets, notification topics, map
layers, Settings pages and backup units, plus what was refused and why. Every client reads this one
list, so a new built-in needs no client release for its declared surfaces. It replaces GET /v1/builtins
(provisional) for new clients.

After builtins (ORDER 135, which loads the descriptors and the on/off switch) and before /mcp (ORDER 140),
whose request-only built-in tools come from this registry.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel

from ..actions import APP_CLAIMS
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope
from ..notify.catalogue import lookup
from ..surfaces.registry import SurfaceRegistry

register_route_scope("GET,HEAD", r"/v1/surfaces", ("apps:read",))

ORDER = 137


class SurfaceApp(BaseModel):
    id: str
    name: str
    description: str | None = None
    origin: Literal["builtin", "market"]
    phone: dict  # the descriptor's spec.phone: entry (native | web | none) and screen


class SurfaceTool(BaseModel):
    name: str            # the MCP tool name
    app_id: str | None   # null for the gateway's own tools
    title: str
    effect: Literal["read", "write", "destructive"]
    exposure: list[Literal["mcp", "rest", "cli"]]
    route: str | None        # "METHOD /path" a core tool projects; its read body equals the route's
    action_type: str | None  # the action type a request-only tool files; a person approves it
    scope: str               # the token scope the tool needs on /mcp


class SurfaceCard(BaseModel):
    app_id: str
    id: str
    title: str
    template: Literal["stat", "list", "progress", "status", "series"]
    source: str  # GET /v1/path; its response declares observed_at


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
    """A map layer or Settings page: drawn by the host from one public read operation."""

    app_id: str
    id: str
    title: str
    source: str


class SurfaceBackupUnit(BaseModel):
    app_id: str
    kind: str  # table | dir
    name: str


class SurfaceRefusal(BaseModel):
    app_id: str
    kind: Literal["tool", "card", "topic"]
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

    registry = SurfaceRegistry(
        app.state.builtins,
        known_action=lambda t: t in gw.actions.feature_types or t in APP_CLAIMS,
        event_topic=event_topic,
        openapi=app.openapi,
    )
    app.state.surfaces = registry

    @app.get("/v1/surfaces", operation_id="surfaces.list", tags=["apps"], response_model=SurfacesOut,
             responses=error_responses(401, 403))
    def list_surfaces(request: Request, p: Principal = Depends(gw.principal)):
        """Everything the switched-on apps plug into, read live: a switched-off app is in no list.
        Declarations the gateway cannot prove (an unregistered action type, an event the notify
        catalogue does not route to the topic, a card whose source declares no observed_at) are
        under `refused` and served nowhere."""
        return registry.view(lambda app_id: all(f(request, p, app_id) for f in gw.app_filters))
