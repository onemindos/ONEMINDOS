# SPDX-License-Identifier: Apache-2.0
"""Contract §12.14: alerts, the inbox, channels, preferences, agent sends and push registrations.

Who may do what (the handlers; household accounts and identity tokens also need the scope below):
- alerts: any principal reads the alerts addressed to it (owners: all; others: their role or id
  in the alert's audience); owners and adults acknowledge; owners resolve the alerts that have
  no automatic resolve condition; owners and agents file an alert's fix as a normal request.
- inbox, channels, preferences, push devices: people only, each their own (owners also list all
  channels). These are personal settings: direct writes, audited, never actions.
- send: agents only, under their own `plugin.<id>` topic, rate-limited; recipients are the owners.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict, deque
from datetime import timedelta
from typing import Literal

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from ..actions import ActionRequest
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..ledger import TERMINAL, utc
from ..notify import NotifyService, RateLimited
from ..notify import routing
from ..notify.channels import (
    CHANNEL_KINDS, DEFAULT_LEVEL, KIND_ALIASES, DeliveryError, check_host, check_url,
    validate_config, validate_device,
)
from ..notify.ids import new_id
from ..notify.store import (
    ChannelRow, DeviceRow, alert_json, channel_json, decode_cursor, device_json, encode_cursor,
    notification_json,
)
from ..identity.scopes import ALL, has_any, register_route_scope

TAG = "notifications"

# Scopes for household accounts and identity-issued tokens (§12.6 table, "Who" column of §12.14).
# Static-file principals skip this table (v0 behaviour); the handlers still check who may call.
# Registered once at import: later registrations win, so these override nothing of identity's.
for _methods, _path, _scopes in (
    ("GET,HEAD", r"/v1/alerts(/[^/]+)?", ("alerts:read",)),
    ("POST", r"/v1/alerts/[^/]+/ack", ("alerts:read",)),  # owner, adult (handler)
    ("POST", r"/v1/alerts/[^/]+/resolve", (ALL,)),  # owner only
    ("POST", r"/v1/alerts/[^/]+/fix", ("actions:request",)),  # files a normal request
    ("GET,HEAD", r"/v1/notifications(/.*)?", ("notifications:read",)),
    ("POST", r"/v1/notifications/read-all", ("notifications:read", "notifications:write")),
    ("POST", r"/v1/notifications/[^/]+/read", ("notifications:read", "notifications:write")),
    ("POST,PATCH,DELETE", r"/v1/notifications/channels(/.*)?", ("notifications:write",)),
    ("PUT", r"/v1/notifications/preferences", ("notifications:write",)),
    ("POST", r"/v1/notifications/send", ("notifications:send",)),
    ("GET,HEAD", r"/v1/push/vapid-public-key", None),  # any principal: a public key
    ("GET,HEAD", r"/v1/push/registrations", ("notifications:read",)),
    ("POST,DELETE", r"/v1/push/registrations(/[^/]+)?", ("notifications:write",)),
):
    register_route_scope(_methods, _path, _scopes)
MAX_FIX_ATTEMPTS = 20  # fix requests per alert and requester
TESTS_PER_MIN = 5  # POST …/channels/{id}/test per person: each one is a synchronous outbound request


class ChannelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    label: str = Field(min_length=1, max_length=120)
    config: dict
    content_level: Literal["opaque", "title", "full"] | None = None
    secret: str | None = Field(default=None, min_length=1, max_length=4096)


class ChannelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, min_length=1, max_length=120)
    config: dict | None = None
    content_level: Literal["opaque", "title", "full"] | None = None
    secret: str | None = Field(default=None, max_length=4096)


class SendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Literal["info", "warning", "critical"]
    topic: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=4096)
    dedupe_key: str | None = Field(default=None, max_length=200)


class PushIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str
    endpoint: str | None = Field(default=None, max_length=2000)
    token: str | None = Field(default=None, max_length=2000)
    keys: dict | None = None
    label: str = Field(default="device", min_length=1, max_length=120)


class FixIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool = False
    reason: str | None = Field(default=None, max_length=500)


def _check_secret(secret: str | None) -> None:
    # Secrets go into HTTP headers and SMTP AUTH: a CR/LF or other control character there is
    # header injection (and http.client raises on it), so refuse it here.
    if secret and any(ord(ch) < 32 or ord(ch) == 127 for ch in secret):
        raise ApiError(422, "conflict", "secret must not contain control characters")


def _denied(gw: Gateway, p: Principal, what: str, message: str) -> ApiError:
    """A 403 with its authz.denied audit record (contract §3: every decision is audited)."""
    gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
    return ApiError(403, "permission_denied", message)


def _can_see(p: Principal, audience: dict) -> bool:
    if p.is_owner:
        return True
    if p.kind == "agent":  # agents see owner-addressed system alerts read-only (MCP list_alerts, §12.19)
        return "owner" in audience.get("roles", [])
    return p.role in audience.get("roles", []) or p.id in audience.get("persons", [])


def _rate_limited(retry: int) -> JSONResponse:
    return JSONResponse(
        status_code=429, headers={"Retry-After": str(retry)},
        content={"error": "rate_limited", "message": "too many notifications; slow down", "retry_after_s": retry},
    )


def _list_params(limit: int | None) -> int:
    return 100 if limit is None else limit


def register(app: FastAPI, gw: Gateway) -> None:
    svc = NotifyService(gw)
    svc.attach()
    app.state.notify = svc
    principal = gw.principal
    repo = svc.repo
    tests: dict[str, deque] = defaultdict(deque)
    tests_lock = threading.Lock()

    def _person(p: Principal) -> None:
        if p.kind != "person":
            raise _denied(gw, p, "use a personal inbox, channel or preference", "only people have an inbox, channels and preferences")

    def audit(p: Principal, name: str, payload: dict) -> None:
        gw.events.publish_event("notify", name, payload, principal=p.as_dict())

    def alert_for(p: Principal, alert_id: str):
        row = repo.get_alert(alert_id)
        if row is None or not _can_see(p, json.loads(row.audience_json or "{}")):
            raise ApiError(404, "not_found", "no such alert")
        return row

    # ---- alerts -------------------------------------------------------------------------
    @app.get("/v1/alerts", operation_id="alerts.list", tags=["alerts"], responses=error_responses(401))
    def list_alerts(
        state: str | None = Query(default=None, description="open (open + acknowledged), acknowledged, resolved; comma = OR"),
        p: Principal = Depends(principal),
    ):
        states = None
        if state:
            wanted = set(state.split(","))
            states = set()
            if "open" in wanted:
                states |= {"open", "acknowledged"}
            states |= wanted & {"acknowledged", "resolved"}
        rows = repo.list_alerts(states)
        return [alert_json(r) for r in rows if _can_see(p, json.loads(r.audience_json or "{}"))]

    @app.get("/v1/alerts/{alert_id}", operation_id="alerts.get", tags=["alerts"], responses=error_responses(401, 404))
    def get_alert(alert_id: str, p: Principal = Depends(principal)):
        return alert_json(alert_for(p, alert_id))

    @app.post("/v1/alerts/{alert_id}/ack", operation_id="alerts.ack", tags=["alerts"], responses=error_responses(401, 403, 404, 409))
    def ack_alert(alert_id: str, p: Principal = Depends(principal)):
        if not (p.kind == "person" and p.role in ("owner", "adult")):
            raise _denied(gw, p, "acknowledge an alert", "only owners and adults acknowledge alerts")
        with svc._lock:
            row = alert_for(p, alert_id)
            if row.state != "open":
                raise ApiError(409, "conflict", f"alert is {row.state}")
            now = gw.clock()
            row.state, row.acked_by, row.acked_at, row.updated_at = "acknowledged", p.id, now, now
            repo.save_alert(row)
            svc._alert_event("acknowledged", row, by=p.id)
        return alert_json(row)

    @app.post("/v1/alerts/{alert_id}/resolve", operation_id="alerts.resolve", tags=["alerts"], responses=error_responses(401, 403, 404, 409))
    def resolve_alert(alert_id: str, p: Principal = Depends(principal)):
        if not p.is_owner:
            raise _denied(gw, p, "resolve an alert", "only owners resolve alerts")
        with svc._lock:
            row = alert_for(p, alert_id)
            if row.state == "resolved":
                raise ApiError(409, "conflict", "alert is already resolved")
            if row.auto_resolve:
                raise ApiError(409, "conflict", "this alert resolves by itself when its condition clears")
            row = svc._resolve(row, by=p.id)
        return alert_json(row)

    @app.post("/v1/alerts/{alert_id}/fix", operation_id="alerts.fix", tags=["alerts"], status_code=202,
              responses=error_responses(401, 403, 404, 409, 422))
    def fix_alert(alert_id: str, request: Request, body: FixIn | None = None, p: Principal = Depends(principal)):
        body = body or FixIn()
        if not (p.is_owner or p.kind == "agent"):
            raise _denied(gw, p, "request an alert's fix", "only owners and agents request fixes")
        if body.approve and not p.is_owner:
            raise _denied(gw, p, "approve an alert's fix", "only an owner may approve in the same call")
        ctx = getattr(request.state, "identity", None)
        if body.approve and ctx is not None and not has_any(ctx.scopes, ("actions:approve",)):
            # The route table only asks for actions:request here; an approval needs the approve scope
            # exactly as POST /v1/actions/{id}/approve does (a narrowed owner token must not approve).
            raise _denied(gw, p, "approve an alert's fix", "this credential may request fixes but not approve them")
        row = alert_for(p, alert_id)
        fix = json.loads(row.fix_json) if row.fix_json else None
        if fix is None:
            raise ApiError(409, "conflict", "this alert has no fix")
        if row.state == "resolved":
            raise ApiError(409, "conflict", "the alert is resolved")
        who = hashlib.sha256(p.id.encode()).hexdigest()[:16]  # keeps the key under 200 chars
        # A repeat tap returns the pending fix; once it failed, was denied or expired, the next
        # generation of the key files a fresh one.
        for gen in range(1, MAX_FIX_ATTEMPTS + 1):
            key = f"fix:{row.id}:{who}" + (f":{gen}" if gen > 1 else "")
            existing = gw.repo.get_by_idempotency_key(key)
            if existing is None:
                break
            if existing.state not in TERMINAL:
                return JSONResponse(status_code=202, content=gw.actions.get(existing.id),
                                    headers={"Location": f"/v1/actions/{existing.id}"})
        else:
            raise ApiError(409, "conflict", "this alert's fix was already tried too many times")
        try:
            req = ActionRequest(type=fix["type"], params=fix["params"], idempotency_key=key,
                                expires_at=gw.clock() + timedelta(hours=24))
        except ValidationError:
            raise ApiError(409, "conflict", f"the fix {fix['type']!r} cannot be requested on this box yet") from None
        action, _ = gw.actions.create(p, req, reason=body.reason or f"fix for alert {row.id}")
        if body.approve:
            # Same gates as POST /v1/actions/{id}/approve: once an owner has a passkey, an approval
            # needs a passkey assertion, which this call cannot carry, so it is refused (401
            # step_up_required) and the fix stays a pending request to approve the normal way.
            for guard in gw.approval_guards:
                guard(p, action["id"], {}, request)
            action = gw.actions.approve(p, action["id"])
        return JSONResponse(status_code=202, content=action, headers={"Location": f"/v1/actions/{action['id']}"})

    # ---- channels (before /v1/notifications/{id}) ----------------------------------------
    @app.get("/v1/notifications/channels", operation_id="notifications.channels.list", tags=[TAG], responses=error_responses(401, 403))
    def list_channels(p: Principal = Depends(principal)):
        _person(p)
        out = []
        for c in repo.list_channels(None if p.is_owner else p.id):
            doc = channel_json(c)
            if c.person_id != p.id:  # another person's URL or address can be a capability (ntfy topic)
                doc.pop("config", None)
            out.append(doc)
        return out

    def own_channel(p: Principal, cid: str) -> ChannelRow:
        _person(p)
        ch = repo.get_channel(cid)
        if ch is None or ch.person_id != p.id:
            raise ApiError(404, "not_found", "no such channel")
        return ch

    def check_destination(kind: str, cfg: dict, lan_ok: bool) -> None:
        try:
            if kind == "email":
                check_host(cfg["host"], lan_ok)
            else:
                check_url(cfg["url"], lan_ok)
        except DeliveryError as exc:
            raise ApiError(422, "conflict", f"config: {exc}") from None

    @app.post("/v1/notifications/channels", operation_id="notifications.channels.create", tags=[TAG], status_code=201, responses=error_responses(401, 403, 422))
    def add_channel(body: ChannelIn, p: Principal = Depends(principal)):
        _person(p)
        _check_secret(body.secret)
        kind = KIND_ALIASES.get(body.kind, body.kind)
        if kind not in CHANNEL_KINDS:
            raise ApiError(422, "conflict", f"kind must be one of {CHANNEL_KINDS} (or ntfy)")
        try:
            cfg = validate_config(kind, body.config)
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        if p.is_owner:
            cfg["lan"] = True  # owners may point a channel at the box's own ntfy or a LAN relay
        check_destination(kind, cfg, p.is_owner)
        now = gw.clock()
        cid = new_id("chn")
        row = ChannelRow(
            id=cid, person_id=p.id, kind=kind, label=body.label, config_json=json.dumps(cfg, sort_keys=True),
            secret_enc=svc.box.seal(body.secret, cid) if body.secret else None,
            content_level=body.content_level or DEFAULT_LEVEL[kind], verified=False, state="ok",
            created_at=now, updated_at=now,
        )
        repo.add_channel(row)
        audit(p, "channel.added", {"channel_id": cid, "kind": kind, "content_level": row.content_level,
                                   "credentials": "provided" if body.secret else "none"})
        return channel_json(row)

    @app.patch("/v1/notifications/channels/{channel_id}", operation_id="notifications.channels.update", tags=[TAG], responses=error_responses(401, 403, 404, 422))
    def patch_channel(channel_id: str, body: ChannelPatch, p: Principal = Depends(principal)):
        ch = own_channel(p, channel_id)
        _check_secret(body.secret)
        if body.config is not None:
            try:
                cfg = validate_config(ch.kind, body.config)
            except ValueError as exc:
                raise ApiError(422, "conflict", str(exc)) from None
            if p.is_owner:
                cfg["lan"] = True
            check_destination(ch.kind, cfg, p.is_owner)
            ch.config_json, ch.verified = json.dumps(cfg, sort_keys=True), False
        if body.label is not None:
            ch.label = body.label
        if body.content_level is not None:
            ch.content_level = body.content_level
        if body.secret is not None:  # "" clears it
            ch.secret_enc = svc.box.seal(body.secret, ch.id) if body.secret else None
        ch.updated_at = gw.clock()
        repo.save_channel(ch)
        audit(p, "channel.updated", {"channel_id": ch.id, "fields": sorted(body.model_fields_set),
                                     **({"credentials": "provided"} if body.secret else {})})
        return channel_json(ch)

    @app.delete("/v1/notifications/channels/{channel_id}", operation_id="notifications.channels.delete", tags=[TAG], status_code=204,
                responses=error_responses(401, 403, 404))
    def delete_channel(channel_id: str, p: Principal = Depends(principal)):
        ch = own_channel(p, channel_id)
        repo.delete_channel(ch.id)
        svc.resolve_key(f"channel:{ch.id}", by=p.id)
        audit(p, "channel.removed", {"channel_id": ch.id})
        return Response(status_code=204)

    @app.post("/v1/notifications/channels/{channel_id}/test", operation_id="notifications.channels.test", tags=[TAG],
              responses={429: {"description": "rate_limited (Retry-After)"}, **error_responses(401, 403, 404)})
    def test_channel(channel_id: str, p: Principal = Depends(principal)):
        ch = own_channel(p, channel_id)
        now = gw.clock()
        with tests_lock:
            q = tests[p.id]
            while q and (now - q[0]).total_seconds() >= 60:
                q.popleft()
            if len(q) >= TESTS_PER_MIN:
                return _rate_limited(max(1, int(60 - (now - q[0]).total_seconds())))
            q.append(now)
        return svc.test_target(ch.id, p.id)

    # ---- preferences --------------------------------------------------------------------
    @app.get("/v1/notifications/preferences", operation_id="notifications.preferences.get", tags=[TAG], responses=error_responses(401, 403))
    def get_preferences(p: Principal = Depends(principal)):
        _person(p)
        doc, tag = svc.preferences(p.id)
        return JSONResponse(content=doc, headers={"ETag": tag})

    @app.put("/v1/notifications/preferences", operation_id="notifications.preferences.set", tags=[TAG], responses=error_responses(401, 403, 409, 422),
             openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object"}}}}})
    async def put_preferences(request: Request, if_match: str | None = Header(default=None),
                              p: Principal = Depends(principal)):
        _person(p)
        try:
            doc = routing.validate(await request.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise ApiError(422, "conflict", f"preferences: {exc}") from None
        mine = set(svc._targets_of(p.id))
        unknown = sorted({c for r in doc["routes"] for c in r["channels"] if c != "*"} - mine)
        if unknown:
            raise ApiError(422, "conflict", f"preferences: not your channels or devices: {unknown}")
        _, current = svc.preferences(p.id)
        if if_match is not None and if_match != current:
            raise ApiError(409, "conflict", "preferences changed since you read them (ETag mismatch)")
        tag = routing.etag(doc)
        repo.put_preferences(p.id, doc, tag, gw.clock())
        audit(p, "preferences.updated", {"person_id": p.id, "etag": tag})
        return JSONResponse(content=doc, headers={"ETag": tag})

    # ---- send (agents) ------------------------------------------------------------------
    @app.post("/v1/notifications/send", operation_id="notifications.send", tags=[TAG], status_code=202,
              responses={429: {"description": "rate_limited (Retry-After)"}, **error_responses(401, 403, 422)})
    def send(body: SendIn, p: Principal = Depends(principal)):
        try:
            out = svc.send_from(p, body.severity, body.topic, body.title, body.body, body.dedupe_key)
        except PermissionError as exc:
            raise _denied(gw, p, "send a notification", str(exc)) from None
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        except RateLimited as exc:
            audit(p, "send.rate_limited", {"topic": body.topic})
            return _rate_limited(exc.retry_after_s)
        audit(p, "sent", {"topic": body.topic, "severity": body.severity, "dedupe_key": body.dedupe_key, **out})
        return JSONResponse(status_code=202, content={"accepted": True, **out})

    # ---- inbox --------------------------------------------------------------------------
    @app.get("/v1/notifications", operation_id="notifications.list", tags=[TAG], responses=error_responses(401, 403, 422))
    def inbox(
        response: Response,
        unread: bool | None = None,
        severity: str | None = None,
        topic: str | None = None,
        since: AwareDatetime | None = None,
        limit: int | None = Query(default=None, ge=1, le=500),
        cursor: str | None = None,
        p: Principal = Depends(principal),
    ):
        _person(p)
        n = _list_params(limit)
        cur = None
        if cursor:
            cur = decode_cursor(cursor)
            if cur is None:
                raise ApiError(422, "conflict", "bad cursor")
        rows = repo.list_notifications(
            p.id, unread=unread, severities=severity.split(",") if severity else None,
            topics=topic.split(",") if topic else None, since=utc(since) if since else None,
            limit=n + 1, cursor=cur,
        )
        if len(rows) > n:
            rows = rows[:n]
            nxt = encode_cursor(rows[-1].created_at, rows[-1].id)
            response.headers["Link"] = f'</v1/notifications?limit={n}&cursor={nxt}>; rel="next"'
        return [notification_json(r) for r in rows]

    @app.post("/v1/notifications/read-all", operation_id="notifications.read_all", tags=[TAG], responses=error_responses(401, 403))
    def read_all(p: Principal = Depends(principal)):
        _person(p)
        return {"marked": repo.mark_read(p.id, None, gw.clock())}

    @app.get("/v1/notifications/{notification_id}", operation_id="notifications.get", tags=[TAG], responses=error_responses(401, 403, 404))
    def get_notification(notification_id: str, p: Principal = Depends(principal)):
        _person(p)
        row = repo.get_notification(notification_id)
        if row is None or row.person_id != p.id:
            raise ApiError(404, "not_found", "no such notification")
        return notification_json(row)

    @app.post("/v1/notifications/{notification_id}/read", operation_id="notifications.read", tags=[TAG], responses=error_responses(401, 403, 404))
    def read_one(notification_id: str, p: Principal = Depends(principal)):
        _person(p)
        row = repo.get_notification(notification_id)
        if row is None or row.person_id != p.id:
            raise ApiError(404, "not_found", "no such notification")
        repo.mark_read(p.id, row.id, gw.clock())
        return notification_json(repo.get_notification(row.id))

    # ---- push registrations -------------------------------------------------------------
    @app.get("/v1/push/vapid-public-key", operation_id="push.vapid_key", tags=["push"], responses=error_responses(401))
    def vapid_key(_: Principal = Depends(principal)):
        return {"key": svc.vapid.public_key}

    @app.post("/v1/push/registrations", operation_id="push.registrations.create", tags=["push"], status_code=201, responses=error_responses(401, 403, 422))
    def add_device(body: PushIn, p: Principal = Depends(principal)):
        _person(p)
        try:
            endpoint, keys = validate_device(body.platform, body.endpoint or body.token, body.keys)
            check_url(endpoint, p.is_owner)
        except (ValueError, DeliveryError) as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        now = gw.clock()
        did = new_id("dev")
        row = DeviceRow(
            id=did, person_id=p.id, platform=body.platform, endpoint_enc=svc.box.seal(endpoint, did),
            keys_enc=svc.box.seal(json.dumps({"keys": keys, "lan": p.is_owner}), did),
            label=body.label, state="ok", created_at=now, last_seen_at=now,
        )
        repo.add_device(row)
        audit(p, "device.added", {"device_id": did, "platform": body.platform})
        return device_json(row)

    @app.get("/v1/push/registrations", operation_id="push.registrations.list", tags=["push"], responses=error_responses(401, 403))
    def list_devices(p: Principal = Depends(principal)):
        _person(p)
        return [device_json(d) for d in repo.list_devices(p.id)]

    @app.delete("/v1/push/registrations/{device_id}", operation_id="push.registrations.delete", tags=["push"], status_code=204,
                responses=error_responses(401, 403, 404))
    def delete_device(device_id: str, p: Principal = Depends(principal)):
        _person(p)
        row = repo.get_device(device_id)
        if row is None or row.person_id != p.id:
            raise ApiError(404, "not_found", "no such device")
        repo.delete_device(row.id)
        audit(p, "device.removed", {"device_id": row.id})
        return Response(status_code=204)

