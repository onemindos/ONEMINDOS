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

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..errors import ApiError
from ..eventstream import ASSET_SCOPE, EventStream, StreamSlots, may_read_assets
from ..fanout import ASSET_BUCKET, AssetState, parse_bbox, parse_kinds
from ..files.service import FilesService
from ..identity import ctx_of
from ..identity.scopes import ALL, has_any, register_route_scope
from .audit import owned_action_ids

# §12.9: events:read for household accounts and identity tokens (not a guest or child scope).
register_route_scope("GET,HEAD", r"/v1/events", ("events:read",))

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
                         root_revisions=root_revisions, assets=assets)
    gw.audit.listeners.append(stream.pump.kick)
    slots = StreamSlots()
    task: dict[str, asyncio.Task] = {}

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
            if t.startswith("alert."):
                from .notifications import _can_see
                row = app.state.notify.repo.get_alert(subject.get("alert_id"))
                return row is not None and _can_see(p, json.loads(row.audience_json or "{}"))
            if t == "notification.created":
                row = app.state.notify.repo.get_notification(subject.get("notification_id"))
                return p.kind == "person" and row is not None and row.person_id == p.id
            if t.startswith("asset."):
                if not may_read_assets(p, ctx.scopes if ctx is not None else None):
                    return False
                cls, aid = subject.get("asset_class"), subject.get("asset_id")
                return all(f(request, p, cls, aid) for f in gw.asset_filters)
            if t.startswith("sync."):  # like GET /v1/sync/changes: no narrower scope covers files yet
                return ctx is None or has_any(ctx.scopes, (ALL,))
            if t.startswith("app.") or t == "action.progress":
                app_id = subject.get("app_id")
                return app_id in gw.catalog.load() and app_id not in gw.disabled_apps() and all(f(request, p, app_id) for f in gw.app_filters)
            return True

        resume = since_id
        if resume is None and last_event_id and last_event_id.isdigit():
            resume = int(last_event_id)
        key = f"{p.kind}:{p.id}"
        if not slots.take(key):
            return JSONResponse(
                {"error": "rate_limited", "message": "too many open event streams", "retry_after_s": 30},
                status_code=429, headers={"Retry-After": "30"},
            )

        async def body():
            try:
                async for chunk in stream.stream(p, types, resume, request.is_disconnected,
                                                 resource_allowed=resource_allowed, kinds=kinds, bbox=box):
                    yield chunk
            finally:
                slots.give(key)

        return StreamingResponse(
            body(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
