# SPDX-License-Identifier: Apache-2.0
"""OneMind Sync routes for app records (F1, docs/design/SYNC.md): /v1/sync/<app>/changes and /push.

Each app on the contract gets its own two routes, typed with its own record, so the SDK knows the
record and BuiltinGate can switch one app off by its prefix (/v1/sync/<app>). The file-sync routes
of routers/sync.py (/v1/sync/changes, chunks, commit, locks) are a different contract.

Only a person syncs their own items; an agent is refused and audited. AI never writes through these
routes: an AI change to a person's items will be a request the person approves (SYNC.md §6).
"""

# No `from __future__ import annotations`: the push body's type is made per app at run time, and FastAPI
# must see the class itself, not its name.
from typing import Literal

from fastapi import Depends, FastAPI, Query, Request, Response, Security
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import ALL, register_route_scope
from ..jsonbody import JsonBody
from ..reminders import SYNC as REMINDERS
from ..sync import CURSOR_RE, ITEM_RE, KEY_RE, PUSH_MAX, SyncApp, SyncLog

APPS: tuple[SyncApp, ...] = (REMINDERS,)
ORDER = 306  # after file sync (305)
PAGE_MAX = 500
_APP_IDS = "|".join(a.id for a in APPS)
# Like /v1/sync/* for files: no narrower scope covers sync yet, so a scoped token needs every scope ("*").
register_route_scope("GET,HEAD", rf"/v1/sync/({_APP_IDS})/changes", (ALL,))
register_route_scope("POST", rf"/v1/sync/({_APP_IDS})/push", (ALL,))
_BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description="A gateway token or a signed-in session (contract §3)")
SECURED = [Security(_BEARER, scopes=[ALL])]
LINK = {"Link": {"description": 'More changes wait: `<...?cursor=...>; rel="next"` (contract §12.1)', "schema": {"type": "string"}}}


class _OpBase(JsonBody):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(max_length=80, pattern=KEY_RE, description="Idempotency key: the same key again is answered, never applied twice")
    item_id: str = Field(max_length=64, pattern=ITEM_RE, description="Made by the client, so items can be created offline")
    op: Literal["upsert", "delete"]
    base_version: int | None = Field(ge=0, description="The version this device last saw; null for a new item")

    @model_validator(mode="after")
    def _data_matches_op(self):
        if (self.op == "upsert") != (getattr(self, "data", None) is not None):
            raise ValueError("an upsert carries data and a delete does not")
        return self


class _PushBase(JsonBody):
    model_config = ConfigDict(extra="forbid")


class SyncPushResult(BaseModel):
    key: str
    status: Literal["applied", "conflict"] = Field(description="conflict: nothing was overwritten (SYNC.md §5)")
    item_id: str = Field(description="Where the data went: the item, or its new conflict copy")
    version: int | None = Field(description="That item's version now; null if it never existed")
    conflict_of: str | None = Field(description="Set on a conflict copy: the item it was copied from")
    replayed: bool = Field(description="true: this key was applied before; this is the first answer again")


class SyncPushResults(BaseModel):
    results: list[SyncPushResult]


def _models(a: SyncApp) -> tuple[type[BaseModel], type[BaseModel]]:
    """(change model, push body model) for one app, named after it in /openapi.json."""
    name = a.id.title().replace("-", "")
    fields = {n: (f.annotation, f) for n, f in a.record.model_fields.items()}
    record = create_model(f"Sync{name}Record", id=(str, ...), updated_at=(str, ...), **fields)
    change = create_model(f"Sync{name}Change", cursor=(str, Field(description="Resume after this change with ?cursor=")),
                          item_id=(str, ...), version=(int, ...), deleted=(bool, Field(description="A tombstone: forget the item")),
                          conflict_of=(str | None, ...), changed_at=(str, ...), data=(record | None, ...))
    op = create_model(f"Sync{name}Op", __base__=_OpBase, data=(a.record | None, None))
    body = create_model(f"Sync{name}Push", __base__=_PushBase, ops=(list[op], Field(min_length=1, max_length=PUSH_MAX)))
    return change, body


def register(app: FastAPI, gw: Gateway) -> None:
    log = SyncLog(gw.db)

    def person(p: Principal = Depends(gw.principal)) -> Principal:
        if p.kind != "person":
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "sync", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only a person syncs their own items")
        return p

    for a in APPS:
        _routes(app, gw, log, a, person)


def _routes(app: FastAPI, gw: Gateway, log: SyncLog, a: SyncApp, person) -> None:
    change, body_model = _models(a)
    base = f"/v1/sync/{a.id}"

    @app.get(f"{base}/changes", operation_id=f"sync.{a.id}.changes", tags=["sync"], response_model=list[change],
             dependencies=SECURED, summary=f"Your {a.id} changes after a cursor",
             description="Oldest first; no cursor: from the start. Keep the last change's cursor and resume from it.",
             responses={200: {"description": "Changes after the cursor", "headers": LINK},
                        **error_responses(401, 403, 409, 422)})
    def changes(request: Request, response: Response, p: Principal = Depends(person),
                cursor: str | None = Query(None, max_length=18, pattern=CURSOR_RE),
                limit: int = Query(200, ge=1, le=PAGE_MAX)):
        rows, more = log.changes(a, p.id, cursor, limit)
        if more:
            response.headers["Link"] = f'<{request.url.path}?limit={limit}&cursor={rows[-1]["cursor"]}>; rel="next"'
        return rows

    @app.post(f"{base}/push", operation_id=f"sync.{a.id}.push", tags=["sync"], response_model=SyncPushResults,
              dependencies=SECURED, summary=f"Send this device's {a.id} changes",
              description=("Each operation is applied once per key, in order, all or none. A stale base_version never "
                           "overwrites: an edit is kept as a conflict copy, a delete is dropped."),
              responses=error_responses(401, 403, 409, 422))
    def push(body: body_model, p: Principal = Depends(person)):  # type: ignore[valid-type]
        ops = [o.model_dump(mode="json") for o in body.ops]
        return {"results": log.push(a, p.id, ops, gw.clock())}
