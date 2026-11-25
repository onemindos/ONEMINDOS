# SPDX-License-Identifier: Apache-2.0
"""Tips routes: /v1/tips/... (#669). The pack ships in the image; tips/service.py filters it by role.

Every route is for a person (a tip is how-to text for someone at a screen); an agent is refused. While
the owner has Tips switched off, the built-in gate (builtins.py) answers 409 app_disabled before these
handlers run.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..tips import TipsRepository, TipsService, TipsSettings
from ..tips.pack import SLUG

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 185

# Self-service like /v1/me/home: the handler checks the caller is a person; the tips shown follow the role.
register_route_scope("GET,HEAD,POST", r"/v1/tips(/.*)?", None)


class TipOpens(BaseModel):
    dashboard: str = Field(description="Dashboard path the Open button goes to")
    phone: str = Field(description="Phone deep link (onemind://...)")


class TipClip(BaseModel):
    release: str
    caption: str


class TipView(BaseModel):
    id: str
    title: str
    collection: str
    body: str = Field(description="The tip text (Markdown)")
    opens: TipOpens
    skip_if_done: list[str] = Field(description="Audit events that make this tip unnecessary")
    clip: TipClip | None
    state: Literal["new", "seen", "dismissed", "done"] = Field(description="This person's state for the tip")
    state_updated_at: str | None


class TipsPackInfo(BaseModel):
    version: str
    source: Literal["image"] = Field(description="Where the pack came from (v1: the OS image)")


class TipList(BaseModel):
    pack: TipsPackInfo | None = Field(description="None when no signed pack for this OS version was found")
    tips: list[TipView]


class TipCollection(BaseModel):
    id: str
    title: str
    count: int = Field(description="Tips in this collection that the caller may see")


class TipCollections(BaseModel):
    collections: list[TipCollection]
    checklist: list[str] = Field(description="Ids of the getting-started checklist tips the caller may see")


class TipWhatsNewEntry(BaseModel):
    version: str
    title: str
    body: str


class TipWhatsNew(BaseModel):
    os_version: str = Field(description="The running OneMind version (MAJOR.MINOR.PATCH)")
    entries: list[TipWhatsNewEntry]


class TipStateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["new", "seen", "dismissed", "done"] = Field(description="new clears the stored state")


class TipStateOut(BaseModel):
    tip_id: str
    state: Literal["new", "seen", "dismissed", "done"]
    updated_at: str | None


def register(app: FastAPI, gw: Gateway) -> None:
    svc = TipsService.from_settings(gw.settings.section(TipsSettings), TipsRepository(gw.db))
    app.state.tips = svc

    def person(p: Principal = Depends(gw.principal)) -> Principal:
        if p.kind != "person":
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "tips", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "tips are for a person")
        return p

    # The two fixed paths come before /v1/tips/{tip_id}; the pack format refuses them as tip ids.
    @app.get("/v1/tips", tags=["tips"], operation_id="tips.list", response_model=TipList,
             responses=error_responses(401, 403, 409, 422))
    def list_tips(collection: str | None = Query(default=None, pattern=SLUG, max_length=64),
                  p: Principal = Depends(person)):
        return svc.list(p, collection)

    @app.get("/v1/tips/collections", tags=["tips"], operation_id="tips.collections", response_model=TipCollections,
             responses=error_responses(401, 403, 409))
    def collections(p: Principal = Depends(person)):
        return svc.collections(p)

    @app.get("/v1/tips/whats-new", tags=["tips"], operation_id="tips.whats_new", response_model=TipWhatsNew,
             responses=error_responses(401, 403, 409))
    def whats_new(p: Principal = Depends(person)):
        return svc.whats_new()

    @app.get("/v1/tips/{tip_id}", tags=["tips"], operation_id="tips.get", response_model=TipView,
             responses=error_responses(401, 403, 404, 409))
    def get_tip(tip_id: str, p: Principal = Depends(person)):
        return svc.get(p, tip_id)

    @app.post("/v1/tips/{tip_id}/state", tags=["tips"], operation_id="tips.set_state", response_model=TipStateOut,
              responses=error_responses(401, 403, 404, 409, 422))
    def set_state(tip_id: str, body: TipStateIn, p: Principal = Depends(person)):
        return svc.set_state(p, tip_id, body.state, gw.clock())
