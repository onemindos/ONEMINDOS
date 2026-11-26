# SPDX-License-Identifier: Apache-2.0
"""The data commons (#615): `GET /v1/data/classes`, the grants list and revoke, and each class's records.

Logic in datagrants/. A grant is asked for with `POST /v1/actions` type `data.grant` (the approval card)
and only an owner approves it. Every data route answers what the caller's grant allows: without one
the records list is empty and the stream ends at once, never an error that tells more.
"""

from __future__ import annotations

import asyncio
import json
from typing import get_args

from fastapi import Depends, FastAPI, Header, Path, Query, Request, Response, Security
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..datagrants import STREAM_POLL_S, DataClass, DataGrants, RecordIn
from ..errors import ApiError, error_responses
from ..eventstream import KEEPALIVE_S, StreamSlots
from ..identity import ctx_of
from ..identity.scopes import register_route_scope

ORDER = 320
TAG = "data"
# No token scope opens the data doors: everybody signed in reaches them and reads `public`. Beyond that
# the caller's data grant decides, capped by its token (scopes() below): grants reach read and aggregate
# only with data:read, write only with data:write (datagrants/ ceiling()). Household sessions carry
# both, so a child, an agent and an installed plugin see only what was granted; a person or agent token
# narrowed to, say, instance:read sees `public` only, whatever its grants (and the owner's standing
# access needs them too). Revoking asks for the approver's scope; the handler also checks for an owner.
register_route_scope("GET,HEAD", r"/v1/data/(classes|grants)(/.*)?", None)
register_route_scope("POST", r"/v1/data/classes/[^/]+/records", None)
register_route_scope("DELETE", r"/v1/data/grants/[^/]+", ("actions:approve",))
BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description=(
    "A OneMind bearer token or session. Each operation's scopes name what it needs: a token scope "
    "(contract §12.6) and `data.grant`, a data grant an owner approved (POST /v1/actions type data.grant). "
    "Without the token scope or the grant the answer is `public` only (empty data, or 403 on a write)."))
READ = [Security(BEARER, scopes=["data:read", "data.grant"])]
WRITE = [Security(BEARER, scopes=["data:write", "data.grant"])]
PAGE = 100


class AccessOut(BaseModel):
    read: bool
    write: bool
    aggregate: bool


class ClassOut(BaseModel):
    id: DataClass
    description: str
    owned_by: list[str]
    read_by: list[str]
    access: AccessOut
    count: int | None = None


class GranteeOut(BaseModel):
    kind: str
    id: str


class GrantOut(BaseModel):
    id: str
    data_class: DataClass
    grantee: GranteeOut
    read: bool
    write: bool
    aggregate: bool
    created_at: str
    expires_at: str
    requested_by: str
    approved_by: str | None
    action_id: str | None
    revoked_at: str | None
    revoked_by: str | None
    active: bool


class RecordOut(BaseModel):
    id: int
    data_class: DataClass
    kind: str
    value: object
    source: str
    created_at: str


LINK = {"Link": {"description": 'The next page: `<...?cursor=...>; rel="next"` (contract §12.1)',
                 "schema": {"type": "string"}}}
IDEMPOTENCY = Header(None, alias="Idempotency-Key", min_length=1, max_length=80,
                     description="Sending the same key again returns the first answer")
CLASS = Path(description="public, owner, private, location or activity")
STREAM_END_REASONS = ("no_grant", "revoked")
# One Server-Sent Event of GET /v1/data/classes/{data_class}/stream: `record` carries a record (RecordOut) as
# JSON with its id, `end` carries {"reason": ...} as JSON. `retry:` and `: keepalive` frames are not events.
DATA_SSE_EVENT_SCHEMA = {
    "type": "object", "required": ["event", "data"],
    "oneOf": [
        {"properties": {
            "event": {"const": "record"}, "id": {"type": "string", "pattern": "^[0-9]+$"},
            "data": {"type": "string", "contentMediaType": "application/json", "contentSchema": {
                "type": "object", "required": ["id", "data_class", "kind", "value", "source", "created_at"],
                "properties": {
                    "id": {"type": "integer"}, "data_class": {"enum": list(get_args(DataClass))},
                    "kind": {"type": "string"}, "value": {}, "source": {"type": "string"},
                    "created_at": {"type": "string"},
                },
            }},
        }, "required": ["id"]},
        {"properties": {
            "event": {"const": "end"},
            "data": {"type": "string", "contentMediaType": "application/json", "contentSchema": {
                "type": "object", "required": ["reason"], "additionalProperties": False,
                "properties": {"reason": {"enum": list(STREAM_END_REASONS)}},
            }},
        }},
    ],
}


def register(app: FastAPI, gw: Gateway) -> None:
    svc = DataGrants(gw)
    app.state.datagrants = svc
    slots = StreamSlots()

    def scopes(request: Request) -> frozenset[str] | None:
        """The caller's ceiling: its session or token scopes; None for a static-file token (v0)."""
        ctx = ctx_of(request)
        return ctx.scopes if ctx is not None else None

    def descriptors() -> dict:
        reg = getattr(app.state, "builtins", None)
        return getattr(reg, "descriptors", None) or {}

    @app.get("/v1/data/classes", tags=[TAG], operation_id="data.classes.list", dependencies=READ,
             response_model=list[ClassOut], responses=error_responses(401, 403))
    def classes(request: Request, p: Principal = Depends(gw.principal)):
        """The five data classes, which built-ins keep and read each, and what you may do with each."""
        return svc.classes(p, descriptors(), scopes=scopes(request))

    @app.get("/v1/data/classes/{data_class}", tags=[TAG], operation_id="data.classes.get", dependencies=READ,
             response_model=ClassOut, responses=error_responses(401, 403, 422))
    def one_class(request: Request, data_class: DataClass = CLASS, p: Principal = Depends(gw.principal)):
        """One class with your access; `count` (how many records) needs read or aggregate, else null."""
        ceiling = scopes(request)
        out = next(c for c in svc.classes(p, descriptors(), scopes=ceiling) if c["id"] == data_class)
        out["count"] = svc.read(p, data_class, limit=0, scopes=ceiling)["count"]
        return out

    @app.get("/v1/data/classes/{data_class}/records", tags=[TAG], operation_id="data.records.list",
             dependencies=READ, response_model=list[RecordOut],
             responses={200: {"description": "Records, oldest first", "headers": LINK},
                        **error_responses(401, 403, 422)})
    def records(response: Response, request: Request, data_class: DataClass = CLASS,
                limit: int = Query(PAGE, ge=1, le=500), cursor: str | None = Query(None, max_length=20),
                p: Principal = Depends(gw.principal)):
        """The class's records after `cursor`. Empty without a read grant (aggregate sees only the count)."""
        if cursor is not None and not (cursor.isascii() and cursor.isdigit()):
            raise ApiError(422, "conflict", "bad cursor", reason="invalid_cursor")
        rows = svc.read(p, data_class, after_id=int(cursor or 0), limit=limit + 1, scopes=scopes(request))["records"]
        if len(rows) > limit:
            rows = rows[:limit]
            response.headers["Link"] = f'<{request.url.path}?limit={limit}&cursor={rows[-1]["id"]}>; rel="next"'
        return rows

    @app.post("/v1/data/classes/{data_class}/records", tags=[TAG], operation_id="data.records.create",
              status_code=201, response_model=RecordOut, dependencies=WRITE,
              responses=error_responses(401, 403, 409, 422))
    def write(body: RecordIn, request: Request, data_class: DataClass = CLASS,
              idempotency_key: str | None = IDEMPOTENCY, p: Principal = Depends(gw.principal)):
        """Add one record to the class. Needs a write grant and a session or token holding data:write
        (the owner needs only data:write). Each writer keeps its newest 10,000 records per class."""
        return svc.write(p, data_class, body, idempotency_key, scopes=scopes(request))

    @app.get("/v1/data/classes/{data_class}/stream", tags=[TAG], operation_id="data.records.stream",
             dependencies=READ, response_class=StreamingResponse, summary="New records (text/event-stream)",
             description=("Server-Sent Events: `record` for each new record (id = record id; resume with "
                          "Last-Event-ID), then `end` with a reason when the stream stops: no_grant at once "
                          f"without read, revoked within {int(STREAM_POLL_S) + 1} s of a revoke or expiry. "
                          "At most 5 open streams per principal (429)."),
             responses={200: {"content": {"text/event-stream": {"schema": DATA_SSE_EVENT_SCHEMA}},
                              "description": "The record stream"}, **error_responses(401, 403, 422, 429)})
    async def stream(request: Request, data_class: DataClass = CLASS,
                     last_event_id: str | None = Header(None, alias="Last-Event-ID", max_length=20),
                     p: Principal = Depends(gw.principal)):
        key = f"{p.kind}:{p.id}"
        ceiling = scopes(request)
        if not slots.take(key):
            return JSONResponse({"error": "rate_limited", "message": "too many open data streams", "retry_after_s": 30},
                                status_code=429, headers={"Retry-After": "30"})
        last = int(last_event_id) if last_event_id and last_event_id.isascii() and last_event_id.isdigit() else 0

        def end(reason: str) -> bytes:
            return f"event: end\ndata: {json.dumps({'reason': reason})}\n\n".encode()

        async def body():
            nonlocal last
            try:
                yield b"retry: 5000\n\n"
                quiet, first = 0.0, True
                while True:
                    if not svc.access(p, data_class, scopes=ceiling).read:
                        yield end("no_grant" if first else "revoked")
                        return
                    first = False
                    rows = svc.read(p, data_class, after_id=last, limit=PAGE, scopes=ceiling)["records"]
                    for r in rows:
                        last = r["id"]
                        yield f"event: record\nid: {r['id']}\ndata: {json.dumps(r)}\n\n".encode()
                    quiet = 0.0 if rows else quiet + STREAM_POLL_S
                    if quiet >= KEEPALIVE_S:
                        yield b": keepalive\n\n"
                        quiet = STREAM_POLL_S
                    if await request.is_disconnected():
                        return
                    await asyncio.sleep(STREAM_POLL_S)
            finally:
                slots.give(key)

        return StreamingResponse(body(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/v1/data/grants", tags=[TAG], operation_id="data.grants.list", dependencies=READ,
             response_model=list[GrantOut], responses=error_responses(401, 403))
    def grants(request: Request, p: Principal = Depends(gw.principal)):
        """Every grant, newest first, for the owner (the Privacy screen); anyone else sees their own."""
        return svc.grants(p, scopes=scopes(request))

    @app.delete("/v1/data/grants/{grant_id}", tags=[TAG], operation_id="data.grants.revoke",
                response_model=GrantOut, dependencies=[Security(BEARER, scopes=["actions:approve"])],
                responses=error_responses(401, 403, 404))
    def revoke(grant_id: str = Path(max_length=40), idempotency_key: str | None = IDEMPOTENCY,
               p: Principal = Depends(gw.principal)):
        """Revoke a grant now (owner only, no approval: it only takes access away). Revoking twice is a no-op."""
        return svc.revoke(p, grant_id)
