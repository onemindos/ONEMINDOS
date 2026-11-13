# SPDX-License-Identifier: Apache-2.0
"""Contract §12.8: GET /v1/events, Server-Sent Events (logic in eventstream.py)."""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..eventstream import EventStream, StreamSlots
from ..identity import ctx_of
from ..identity.scopes import has_any, register_route_scope
from .audit import owned_action_ids

# §12.9: events:read for household accounts and identity tokens (not a guest or child scope).
register_route_scope("GET,HEAD", r"/v1/events", ("events:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    stream = EventStream(gw.settings.audit_path, gw.registry.list, owned_action_ids(gw), gw.clock)
    slots = StreamSlots()

    @app.get(
        "/v1/events", tags=["events"], operation_id="events.stream",
        summary="Live events (text/event-stream)",
        description=(
            "Server-Sent Events with the onemind.event/v1 envelope. `id` is the audit seq; resume with "
            "Last-Event-ID or since_id. node.status events carry no id. `: keepalive` every 15 s. "
            "At most 5 open streams per principal (429 rate_limited)."
        ),
        responses={
            200: {"content": {"text/event-stream": {"schema": {"type": "string"}}},
                  "description": "The event stream"},
            **error_responses(401, 422, 429),
        },
    )
    async def events(
        request: Request,
        types: str | None = Query(None, max_length=500, description="comma-separated globs, e.g. action.*,node.status"),
        since_id: int | None = Query(None, ge=0),
        last_event_id: str | None = Header(None, alias="Last-Event-ID", max_length=40),
        p: Principal = Depends(principal),
    ):
        ctx = ctx_of(request)

        def resource_allowed(ev: dict) -> bool:
            t, subject = ev["type"], ev["subject"]
            scope = {"alert": "alerts:read", "notification": "notifications:read",
                     "app": "apps:read", "action": "actions:read", "audit": "audit:read",
                     "node": "nodes:read"}.get(t.split(".")[0])
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
            if t.startswith("app.") or t == "action.progress":
                app_id = subject.get("app_id")
                return app_id in gw.catalog.load() and all(f(request, p, app_id) for f in gw.app_filters)
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
                                                 resource_allowed=resource_allowed):
                    yield chunk
            finally:
                slots.give(key)

        return StreamingResponse(
            body(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
