# SPDX-License-Identifier: Apache-2.0
"""Offline content manager (NMD-02, #127): the Kiwix library by pack, Wikipedia size and language.

Reads show the library and the packs (no network) or the live catalogue with sizes. The only write
that changes content is POST /v1/content/changes: it files an `app.configure` of the Kiwix app,
which waits for an owner's approval like every app change (content/service.py has the rules).
Everything here is the owner's: the library is shared by the household and costs disk space.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Query, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from ..apimodels import Action
from ..auth import Principal
from ..content.kiwix import FLAVOUR_RE, NAME_RE
from ..content.service import ContentService
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..jsonbody import JsonBody
from ..identity.scopes import register_route_scope

# Route order in the app and in /openapi.json (routers/__init__.py): after automation (280), whose
# maintenance windows the auto-update uses.
ORDER = 290

# `content:admin` is minted to no one, so only the owner role (every scope) holds it.
register_route_scope("GET,HEAD", r"/v1/content", ("content:admin",))
register_route_scope("GET,HEAD", r"/v1/content/wikipedia", ("content:admin",))
register_route_scope("GET,HEAD", r"/v1/content/updates", ("content:admin",))
register_route_scope("POST", r"/v1/content/plan", ("content:admin",))
register_route_scope("POST", r"/v1/content/changes", ("content:admin",))
register_route_scope("PUT", r"/v1/content/auto-update", ("content:admin",))

BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description=(
    "A OneMind bearer token or session. Every /v1/content operation needs the `content:admin` scope, "
    "which only the owner role holds (contract §12.6)."))
OWNER_ONLY = [Security(BEARER, scopes=["content:admin"])]

LANG = r"^[a-z]{2,12}(-[a-z]{2,8})?$"


class BookRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=NAME_RE.pattern)
    flavour: str = Field(default="", max_length=20, pattern=FLAVOUR_RE.pattern)


class ContentChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    add: list[BookRef] = Field(default_factory=list, max_length=40)
    remove: list[BookRef] = Field(default_factory=list, max_length=200)


class ContentChangeRequest(ContentChange, JsonBody):
    # The download size the owner was shown (POST /v1/content/plan). A different size now is refused.
    download_bytes: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=200)


class AutoUpdateBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    window_id: str = Field(default="win_nightly", pattern=r"^win_[a-z0-9_]{1,36}$")


class CatalogBook(BaseModel):
    name: str
    flavour: str
    title: str
    language: str
    path: str
    size_bytes: int
    issued: str


class ContentPlan(BaseModel):
    zims_before: list[str]
    zims_after: list[str]
    downloads: list[CatalogBook]
    removed: list[str]
    download_bytes: int
    changed: bool


class PackBook(BaseModel):
    name: str
    flavour: str
    in_library: bool


class Pack(BaseModel):
    id: str
    title: str
    description: str
    books: list[PackBook]


class LibraryBook(BaseModel):
    path: str
    name: str
    flavour: str
    date: str | None


class KiwixState(BaseModel):
    id: str
    in_catalog: bool
    status: str


class AutoUpdate(BaseModel):
    enabled: bool
    window_id: str
    window_open: bool
    last_checked_at: str | None
    last_result: str | None
    last_action_id: str | None
    last_download_bytes: int | None


class ContentView(BaseModel):
    app: KiwixState
    library: list[LibraryBook]
    packs: list[Pack]
    pending_action_id: str | None
    auto_update: AutoUpdate


class WikipediaChoices(BaseModel):
    lang: str
    books: list[CatalogBook]


class ContentChangeResult(BaseModel):
    action: Action
    plan: ContentPlan


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    policies = app.state.automation.policies
    svc = ContentService(
        gw, app.state.appstore,
        window_open=policies.window_is_open,
        window_exists=lambda w: policies.repo.get_window(w) is not None,
    )
    gw.on_startup(svc.start)
    gw.on_shutdown(svc.stop)
    app.state.content = svc
    tags = ["content"]

    def owner(p: Principal, what: str) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"only an owner may {what}")

    @app.get("/v1/content", tags=tags, dependencies=OWNER_ONLY, operation_id="content.get", response_model=ContentView,
             responses=error_responses(401, 403))
    def content_get(p: Principal = Depends(principal)):
        """The Kiwix library, the curated packs and the auto-update setting. No network."""
        owner(p, "manage offline content")
        return svc.view()

    @app.get("/v1/content/wikipedia", tags=tags, dependencies=OWNER_ONLY, operation_id="content.wikipedia", response_model=WikipediaChoices,
             responses=error_responses(401, 403, 409, 503))
    def content_wikipedia(lang: str = Query(min_length=2, max_length=21, pattern=LANG), p: Principal = Depends(principal)):
        """Wikipedia in one language, in each size the catalogue has, with the download size."""
        owner(p, "manage offline content")
        return {"lang": lang, "books": svc.wikipedia(lang)}

    @app.get("/v1/content/updates", tags=tags, dependencies=OWNER_ONLY, operation_id="content.updates", response_model=ContentPlan,
             responses=error_responses(401, 403, 409, 503))
    def content_updates(p: Principal = Depends(principal)):
        """Newer releases of the books in the library, with their download size. Files nothing."""
        owner(p, "manage offline content")
        return svc.updates()

    @app.post("/v1/content/plan", tags=tags, dependencies=OWNER_ONLY, operation_id="content.plan", response_model=ContentPlan,
              responses=error_responses(401, 403, 409, 422, 503))
    def content_plan(body: ContentChange, p: Principal = Depends(principal)):
        """What a change would download (with sizes) and stop serving. Files nothing."""
        owner(p, "manage offline content")
        return svc.plan([b.model_dump() for b in body.add], [b.model_dump() for b in body.remove])

    @app.post("/v1/content/changes", tags=tags, dependencies=OWNER_ONLY, operation_id="content.changes", status_code=201,
              response_model=ContentChangeResult, responses=error_responses(401, 403, 409, 422, 429, 503))
    def content_changes(body: ContentChangeRequest, p: Principal = Depends(principal)):
        """Request the change as an app.configure of Kiwix; it waits for an owner's approval."""
        owner(p, "manage offline content")
        out = svc.request_change(p, [b.model_dump() for b in body.add], [b.model_dump() for b in body.remove],
                                 body.download_bytes, body.idempotency_key)
        return JSONResponse(status_code=201, content=out)

    @app.put("/v1/content/auto-update", tags=tags, dependencies=OWNER_ONLY, operation_id="content.auto_update", response_model=AutoUpdate,
             responses=error_responses(401, 403, 422))
    def content_auto_update(body: AutoUpdateBody, p: Principal = Depends(principal)):
        """Turn the auto-update check on or off, and pick the maintenance window it runs in."""
        owner(p, "manage offline content")
        return svc.set_prefs(p, body.enabled, body.window_id)
