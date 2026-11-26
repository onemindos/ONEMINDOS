# SPDX-License-Identifier: Apache-2.0
"""Contract §12.8: GET /v1/events, Server-Sent Events (logic in eventstream.py, fan-out in fanout.py).

#606: asset values from the hub's asset-state bucket ride the same stream (opt-in, `types=asset.*`),
with a snapshot on connect, `?kind=` and `?bbox=` for the map, and `assets:read` plus every
`gw.asset_filters` check on each asset. NATS credentials never leave the gateway: browsers and
phones read the bus only through this route.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import Principal
from ..context import Gateway
from ..dashboard_cards import SubjectCard, SubjectCards, can_read_subject, event_pattern
from ..errors import ApiError, error_responses
from ..eventstream import ASSET_SCOPE, EventStream, StreamSlots, may_read_assets
from ..fanout import ASSET_BUCKET, AssetState, parse_bbox, parse_kinds
from ..files.service import FilesService
from ..identity import ctx_of
from ..identity.scopes import ALL, has_any, register_route_scope
from ..work.access import delegated_reader
from ..work.service import WORK_EVENTS
from .audit import owned_action_ids

# §12.9: events:read for household accounts and identity tokens (not a guest or child scope).
register_route_scope("GET,HEAD", r"/v1/events", ("events:read",))
register_route_scope("GET,HEAD,PUT", r"/v1/me/dashboard-card", None)
register_route_scope("GET,HEAD", r"/v1/me/dashboard-card/events", None)

# OpenAPI 3.1 describes one parsed SSE record, NOT a JSON HTTP response.
# `data` remains the serialized §12.8 envelope; id is absent on transient events.
SSE_RECORD_SCHEMA = {
    "type": "object", "required": ["event", "data"],
    "properties": {
        "event": {"type": "string"}, "id": {"type": "string"}, "retry": {"type": "integer"},
        "data": {"type": "string", "contentMediaType": "application/json", "contentSchema": {
            "type": "object", "required": ["schema", "id", "type", "ts", "subject", "severity", "data"],
            "properties": {
                "schema": {"const": "onemind.event/v1"}, "id": {"type": "string"},
                "type": {"type": "string"}, "ts": {"type": "string", "format": "date-time"},
                "subject": {"type": "object"}, "severity": {"type": "string"},
                "data": {"type": "object"}, "actor_id": {"type": "string"},
            },
        }},
    },
}


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 230


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    files = FilesService(gw)

    def root_revisions(p: Principal) -> dict[str, int]:
        return files.index.revisions(files.readable_roots(p))

    assets = AssetState()
    gw.assets = assets
    app.state.assets = assets
    stream = EventStream(gw.settings.audit_path, gw.registry.list, owned_action_ids(gw), gw.clock,
                         root_revisions=root_revisions, assets=assets, next_node_change=gw.registry.next_change_in)
    gw.registry.change_listeners.append(stream.wake_nodes)
    gw.audit.listeners.append(stream.pump.kick)
    slots = StreamSlots()
    task: dict[str, asyncio.Task] = {}
    cards = SubjectCards(gw.db)

    def start_stream(request: Request, p: Principal, **options):
        key = f"{p.kind}:{p.id}"
        if not slots.take(key):
            return JSONResponse(
                {"error": "rate_limited", "message": "too many open event streams", "retry_after_s": 30},
                status_code=429, headers={"Retry-After": "30"},
            )

        async def body():
            try:
                async for chunk in stream.stream(p, is_disconnected=request.is_disconnected, **options):
                    yield chunk
            finally:
                slots.give(key)

        return StreamingResponse(
            body(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def own_card(p: Principal = Depends(principal)) -> Principal:
        if p.kind != "person":
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "access a dashboard card", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only a person has a dashboard card")
        return p

    def allowed_subject(request: Request, p: Principal, pattern: str) -> bool:
        ctx = ctx_of(request)
        return can_read_subject(p, ctx.scopes if ctx is not None else None, pattern)

    def require_subject(request: Request, p: Principal, subject: str) -> str:
        pattern = event_pattern(subject)
        if not allowed_subject(request, p, pattern):
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "access a dashboard card subject", "reason": "subject_scope"})
            raise ApiError(403, "permission_denied", "your account does not have access to this subject",
                           reason="subject_scope")
        return pattern

    @app.get("/v1/me/dashboard-card", operation_id="me.dashboard_card.get", tags=["me"],
             response_model=SubjectCard | None, responses=error_responses(401, 403))
    def read_card(request: Request, response: Response, p: Principal = Depends(own_card)):
        response.headers["Cache-Control"] = "no-store"
        subject = cards.get(p.id)
        if subject is None:
            return None
        require_subject(request, p, subject)
        return {"source": {"kind": "subject", "subject": subject}}

    @app.put("/v1/me/dashboard-card", operation_id="me.dashboard_card.save", tags=["me"],
             response_model=SubjectCard, responses=error_responses(401, 403, 422))
    def save_card(card: SubjectCard, request: Request, response: Response, p: Principal = Depends(own_card)):
        subject = card.source.subject
        require_subject(request, p, subject)
        if cards.save(p.id, subject):
            gw.audit.append("dashboard_card.updated", p.as_dict(), None, {"changed": ["source"]})
        response.headers["Cache-Control"] = "no-store"
        return card

    @app.get("/v1/me/dashboard-card/events", operation_id="me.dashboard_card.events", tags=["me"],
             response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {"schema": SSE_RECORD_SCHEMA}},
                              "description": "The person's authorized card events"},
                        **error_responses(401, 403, 404, 429)})
    async def card_events(request: Request, last_event_id: str | None = Header(None, alias="Last-Event-ID", max_length=40),
                          p: Principal = Depends(own_card)):
        subject = cards.get(p.id)
        if subject is None:
            raise ApiError(404, "not_found", "save a subject card first")
        pattern = require_subject(request, p, subject)

        def still_allowed() -> bool:
            # Resolve the live credential, including current scopes and user state. An identity
            # context from the first request or a previously authorized event cannot grant access.
            request.state.identity = None
            try:
                current = principal(request)
            except ApiError:
                return False
            return (current.id == p.id and allowed_subject(request, current, pattern)
                    and cards.get(p.id) == subject)

        resume = int(last_event_id) if last_event_id and last_event_id.isascii() and last_event_id.isdigit() else None
        return start_stream(request, p, types=None, since_id=resume, subject_card=(pattern, still_allowed))

    def bucket_ready() -> bool:
        core = gw.jetstream
        return core is not None and core.state == "ready" and core.plan is not None and any(
            b.bucket == ASSET_BUCKET for b in core.plan.buckets)

    @gw.on_startup
    async def _start_assets() -> None:
        core = gw.jetstream
        if gw.bus.url and core is not None and core.plan is not None:
            task["assets"] = asyncio.create_task(assets.run(gw.bus, bucket_ready), name="asset-state")

    @gw.on_shutdown
    async def _stop_assets() -> None:
        t = task.pop("assets", None)
        if t is not None:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

    @app.get(
        "/v1/events", tags=["events"], operation_id="events.stream",
        response_class=StreamingResponse,
        summary="Live events (text/event-stream)",
        description=(
            "Server-Sent Events with the onemind.event/v1 envelope. `id` is the audit seq; resume with "
            "Last-Event-ID or since_id. node.status events carry no id. `: keepalive` every 15 s. "
            "At most 5 open streams per principal (429 rate_limited). Asset values are sent only when "
            "types names them (asset.*): first the current value of each asset the caller may see "
            "(asset.value, data.snapshot true), then stream.snapshot {count, state}, then changes, "
            "latest-wins per key; kind and bbox narrow them. A stream that falls too far behind gets "
            "stream.reset {reason: slow_client} and ends."
        ),
        responses={
            200: {"content": {"text/event-stream": {"schema": SSE_RECORD_SCHEMA}},
                  "description": "The event stream"},
            **error_responses(401, 422, 429),
        },
    )
    async def events(
        request: Request,
        types: str | None = Query(None, max_length=500, description="comma-separated globs, e.g. action.*,node.status"),
        since_id: int | None = Query(None, ge=0),
        last_event_id: str | None = Header(None, alias="Last-Event-ID", max_length=40),
        kind: str | None = Query(None, max_length=600, description=(
            "asset.* only: comma-separated asset classes (the asset_class token of "
            "onemind.asset.<asset_class>.<asset_id>.<field>), e.g. camera,sensor")),
        bbox: str | None = Query(None, max_length=120, description=(
            "asset.* only: min_lon,min_lat,max_lon,max_lat in WGS-84 degrees; an asset is sent while "
            "its last known position is inside, and once more when it leaves")),
        p: Principal = Depends(principal),
    ):
        ctx = ctx_of(request)
        try:
            kinds, box = parse_kinds(kind), parse_bbox(bbox)
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None

        def asset_allowed(v) -> bool:  # every gateway asset filter, on the value itself (class, id, field, datapoint)
            return all(f(request, p, v) for f in gw.asset_filters)

        def resource_allowed(ev: dict) -> bool:
            t, subject = ev["type"], ev["subject"]
            if ctx is not None and subject.get("action_id"):
                action_scopes = ("actions:read", "actions:read:own") if p.kind == "agent" else ("actions:read",)
                if not has_any(ctx.scopes, action_scopes):
                    return False
            scope = {"alert": "alerts:read", "notification": "notifications:read",
                     "app": "apps:read", "action": "actions:read", "audit": "audit:read",
                     "node": "nodes:read", "asset": ASSET_SCOPE}.get(t.split(".")[0])
            required: tuple[str, ...] = (scope,) if scope else ()
            # Only agent actions have an ownership filter here. Never treat a person's
            # narrowed :own grant as broad audit/action access based on their owner role.
            if p.kind == "agent" and scope == "actions:read":
                required += ("actions:read:own",)
            if ctx is not None and scope and not has_any(ctx.scopes, required):
                return False
            if t in WORK_EVENTS:
                # The stream can outlive the credential; re-evaluate its scopes and task visibility.
                request.state.identity = None
                try:
                    current = principal(request)
                except ApiError:
                    return False
                live = ctx_of(request)
                return (current.id == p.id and current.kind == p.kind
                        and (live is None or has_any(live.scopes, ("work:read",)))
                        and app.state.work.event_visible(current, ev, delegated=delegated_reader(request, current)))
            if t.startswith("alert."):
                from .notifications import _can_see
                row = app.state.notify.repo.get_alert(subject.get("alert_id"))
                return row is not None and _can_see(p, json.loads(row.audience_json or "{}"))
            if t in ("notification.created", "notification.read"):
                service = app.state.notify
                row = service.repo.get_notification(subject.get("notification_id"))
                return (p.kind == "person" and row is not None and row.person_id == p.id
                        and (t != "notification.created" or not service.muted(p.id, row.topic)))
            if t == "notification.read_all":
                return p.kind == "person" and subject.get("person_id") == p.id
            if t.startswith("notification."):
                return False  # an inbox event without its own rule here reaches nobody
            if t.startswith("asset."):  # each value is also judged by asset_allowed below
                return may_read_assets(p, ctx.scopes if ctx is not None else None)
            if t.startswith("sync."):  # like GET /v1/sync/changes: no narrower scope covers files yet
                return ctx is None or has_any(ctx.scopes, (ALL,))
            if t.startswith("app.") or t == "action.progress":
                app_id = subject.get("app_id")
                return app_id in gw.catalog.load() and app_id not in gw.disabled_apps() and all(f(request, p, app_id) for f in gw.app_filters)
            return True

        resume = since_id
        if resume is None and last_event_id and last_event_id.isascii() and last_event_id.isdigit():
            resume = int(last_event_id)
        return start_stream(request, p, types=types, since_id=resume, resource_allowed=resource_allowed,
                            kinds=kinds, bbox=box, asset_allowed=asset_allowed)
