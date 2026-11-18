# SPDX-License-Identifier: Apache-2.0
"""UMB-P07 (#144): `/v1/me/home`, the caller's own Home document (docs/umbrel2/desktop-ui.md §4.3).

A person reads and writes only their own document. A write is a direct self write (API.md P3), audited as
`home.updated` with the names of the changed fields (never their values). `If-Match` is required on a write.
"""
from fastapi import Depends, FastAPI, Request, Response

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..home import (HomeBody, HomeService, HomeView, drop_invisible, etag_of, item_ids, normalise)
from ..identity.scopes import register_route_scope

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 215

# Self-service like /v1/auth/*: the handler checks the caller is a person.
register_route_scope("GET,HEAD,PUT", r"/v1/me/home", None)


def register(app: FastAPI, gw: Gateway) -> None:
    svc = HomeService(gw.db)
    app.state.home = svc

    def person(p: Principal = Depends(gw.principal)) -> Principal:
        if p.kind != "person":
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "me.home", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only a person has a Home")
        return p

    def visible_fn(request: Request, p: Principal):
        apps = gw.catalog.load()
        nodes = {n["node_id"] for n in gw.registry.list()}

        def visible(item: str) -> bool:
            kind, _, ident = item.partition(":")
            if kind == "app":
                return ident in apps and all(f(request, p, ident) for f in gw.app_filters)
            if kind == "node":
                return ident in nodes
            return kind == "sys"

        return visible

    def resolved(request: Request, p: Principal) -> dict:
        doc = svc.stored(p.id) or HomeBody().model_dump()
        doc = normalise(doc, owner=p.is_owner)
        return drop_invisible(doc, visible_fn(request, p))

    def send(response: Response, doc: dict) -> dict:
        response.headers["ETag"] = etag_of(doc)
        response.headers["Cache-Control"] = "no-store"
        return doc

    @app.get("/v1/me/home", operation_id="me.home.get", tags=["me"], response_model=HomeView,
             responses=error_responses(401, 403))
    def read(request: Request, response: Response, p: Principal = Depends(person)):
        return send(response, resolved(request, p))

    @app.put("/v1/me/home", operation_id="me.home.save", tags=["me"], response_model=HomeView,
             responses=error_responses(401, 403, 412, 422, 428))
    def save(body: HomeBody, request: Request, response: Response, p: Principal = Depends(person)):
        match = request.headers.get("if-match")
        if match is None:
            raise ApiError(428, "conflict", "send the ETag you read in If-Match", reason="precondition_required")
        current = resolved(request, p)
        if match.strip() != "*" and match.strip().removeprefix("W/") != etag_of(current):
            raise ApiError(412, "stale_precondition", "Home changed elsewhere; read it again", reason="etag_mismatch")
        doc = normalise(body.model_dump(exclude={"updated_at"}), owner=p.is_owner)
        visible = visible_fn(request, p)
        # A stored id must never reveal an app this person may not see: refuse it, as if it did not exist.
        bad = [i for i in item_ids(doc) if not visible(i)]
        if bad:
            raise ApiError(422, "conflict", "unknown or hidden item: " + ", ".join(sorted(set(bad))), reason="unknown_item")
        changed = sorted(k for k in doc if k != "updated_at" and doc[k] != current.get(k))
        stored = svc.save(p.id, doc, gw.clock())
        gw.audit.append("home.updated", p.as_dict(), None, {"changed": changed})
        return send(response, stored)
