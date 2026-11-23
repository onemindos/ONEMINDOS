# SPDX-License-Identifier: Apache-2.0
"""Send to (#612): `GET /v1/share/types`, `GET /v1/share/targets` and `POST /v1/share`.

The share type registry and the deep links are share/types.py; who may receive what is
share/service.py. After builtins (ORDER 135), whose descriptor registry it reads.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope
from ..share import ShareService

ORDER = 136

ShareTypeName = Literal["note", "task", "event", "person", "file", "place", "track", "alert", "clip"]

register_route_scope("GET,HEAD", r"/v1/share/(types|targets)", ("apps:read",))
# Every scope (as Files): a scoped token is refused; the handler lets only an owner or adult send.
register_route_scope("POST", r"/v1/share", ("*",))


class ShareTypeOut(BaseModel):
    name: ShareTypeName
    title: str
    data_class: str   # the descriptor data class a receiving app must own or read
    ref: str          # what an object's ref names


class ShareTypesOut(BaseModel):
    types: list[ShareTypeOut]


class ShareTarget(BaseModel):
    app_id: str
    name: str
    verbs: list[Literal["open", "add"]]


class ShareTargetsOut(BaseModel):
    type: ShareTypeName
    targets: list[ShareTarget]


class ShareObject(BaseModel):
    """A reference to one object; never its content."""

    model_config = ConfigDict(extra="forbid")
    type: ShareTypeName
    ref: str = Field(min_length=1, max_length=1024, pattern=r"^[^\x00-\x1f\x7f]+$")
    source: str | None = Field(default=None, max_length=59, pattern=APP_ID_RE.pattern,
                               description="The app the object comes from.")


class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: str = Field(min_length=1, max_length=59, description="The receiving app's id.")
    verb: Literal["open", "add"] = "open"
    object: ShareObject


class ShareOut(BaseModel):
    id: str           # the share.sent event id
    to: str
    verb: Literal["open", "add"]
    object: ShareObject
    link: str         # onemind://<app>/<type>/<ref>: the object in the receiving app
    sent_at: str


def register(app: FastAPI, gw: Gateway) -> None:
    svc = ShareService(gw, lambda: getattr(app.state, "builtins", None))
    app.state.share = svc

    @app.get("/v1/share/types", operation_id="share.types", tags=["share"], response_model=ShareTypesOut,
             responses=error_responses(401, 403))
    def share_types(p: Principal = Depends(gw.principal)):
        """The share types: what one app can hand another, and the data grant each needs."""
        return {"types": svc.types()}

    @app.get("/v1/share/targets", operation_id="share.targets", tags=["share"], response_model=ShareTargetsOut,
             responses=error_responses(401, 403, 422))
    def share_targets(request: Request, type: ShareTypeName = Query(...), p: Principal = Depends(gw.principal)):
        """The Send to list: switched-on apps you can see that accept this type and hold its grant."""
        return {"type": type, "targets": svc.targets(request, p, type)}

    @app.post("/v1/share", operation_id="share.send", tags=["share"], status_code=201, response_model=ShareOut,
              responses=error_responses(401, 403, 404, 409, 422))
    def share_send(body: ShareIn, request: Request, p: Principal = Depends(gw.principal)):
        """Hand one object to one app. Refused (409) when the app does not accept the type or verb
        (`type_not_accepted`, `verb_not_accepted`) or lacks the type's data grant (`no_grant`);
        404 when you cannot see the app. Only an owner or adult sends."""
        return svc.send(request, p, body.to, body.verb, body.object.model_dump())
