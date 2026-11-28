# SPDX-License-Identifier: Apache-2.0
"""Service cards (#623) and service actions (#636), from the host service (hostservices.py).

- GET /v1/system/services: every systemd unit the OS ships with its plain name, description, docs link,
  risk, state, memory and version. Owner only, like the other /v1/system reads.
- GET /v1/system/services/{unit}/logs: a registry unit's journal, every line through the app-log
  redaction filter (monitoring/redact.py); `follow=true` is an SSE stream of at most 15 minutes. Owner
  only and audited.
- POST /v1/system/services/{unit}/restart: files a service.restart action for a unit the registry marks
  restartable. An owner or an agent may ask; only an owner approves, with a passkey. The host service
  checks the registry again and journals the restart by action id (hostlink.py, internal/host). A unit
  that is not restartable answers 403, and rescue, first-boot, host and data-layout units never are.
"""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..executors import ExecResult
from ..hostservices import UNIT_RE, HostServicesClient, ServicesView, find_card, never_restart, read_view
from ..identity.scopes import register_route_scope
from ..monitoring.redact import Redactor
from ..netconf import NetSettings
from ..storage import StorageTimeout, StorageUnavailable

# Route order in the app and in /openapi.json (routers/__init__.py): right after routers/system.py.
ORDER = 341
ACTION = "service.restart"
REQUESTERS = frozenset({"agent"})  # besides the owner; an agent asks, only an owner approves
REQUEST_TTL = timedelta(hours=24)
MAX_LINES = 2000
FOLLOW_MAX_S = 15 * 60
STREAMS_PER_PRINCIPAL = 3

# Same scope as /v1/system/controls: minted to no one, so only the owner role (every scope) reads it.
register_route_scope("GET,HEAD", r"/v1/system/services", ("system:admin",))
register_route_scope("GET,HEAD", r"/v1/system/services/[^/]+/logs", ("system:admin",))
register_route_scope("POST", r"/v1/system/services/[^/]+/restart", ("actions:request",))


class ServiceRestartRequest(BaseModel):
    """POST /v1/system/services/{unit}/restart."""

    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostServicesClient(str(cfg.host_socket), cfg.host_timeout_s)
    streams: dict[str, int] = defaultdict(int)
    streams_lock = threading.Lock()

    def deny(p: Principal, what: str, msg: str, reason: str = "permission_denied") -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": reason})
        return ApiError(403, "permission_denied", msg, reason=None if reason == "permission_denied" else reason)

    def unit_or_404(unit: str) -> str:
        if not UNIT_RE.fullmatch(unit):
            raise ApiError(404, "not_found", "no service with that unit name")
        return unit

    def restartable_problem(unit: str) -> tuple[int, str] | None:
        """(status, message) when unit may not be restarted now, else None. Read from the host each time."""
        view = read_view(client)
        if not view.available:
            return 409, view.message or "the host service is not reachable"
        card = find_card(view, unit)
        if card is None or not card.known:
            return 404, "the services registry on this box does not list that unit"
        if not card.restartable or never_restart(unit):
            return 403, f"{unit} is not restartable from OneMind (rescue, first boot, host and data-layout units never are)"
        return None

    def recheck(a) -> str | None:
        problem = restartable_problem((a.params or {}).get("unit", ""))
        return problem[1] if problem else None

    def run(a, finish) -> None:
        link = app.state.hostlink
        why = link.problem(ACTION)
        if why is not None:
            finish(ExecResult("failed", why[1], steps=[{"step": "host", "result": why[0]}]))
            return
        link.run(a, finish)

    gw.actions.register_type(ACTION, FeatureAction("actuate", run, REQUESTERS, check=recheck))
    gw.approval_guards.append(passkey_step_up(gw))

    @app.get("/v1/system/services", tags=["system"], operation_id="system.services.list", response_model=ServicesView,
             responses=error_responses(401, 403))
    def system_services(p: Principal = Depends(gw.principal)) -> ServicesView:
        """Every systemd unit this OS ships, as a service card: plain name and description, docs page,
        risk, restartable flag, dependencies, and systemd's state, memory and version (read only).

        A OneMind unit the image's registry does not list comes back with `known` false. `available` is
        false, with a reason, when the host service cannot be reached: the screen says so instead of
        showing nothing."""
        if not p.is_owner:
            raise deny(p, "read services", "only an owner may see the services on this box")
        return read_view(client)

    @app.get("/v1/system/services/{unit}/logs", tags=["system"], operation_id="system.services.logs",
             response_class=PlainTextResponse,
             responses={200: {"content": {"text/plain": {}, "text/event-stream": {}}},
                        **error_responses(401, 403, 404, 409, 429)})
    def system_service_logs(unit: str, tail: int = Query(default=200, ge=1, le=MAX_LINES), follow: bool = False,
                            p: Principal = Depends(gw.principal)):
        """The last `tail` journal lines of a unit the registry lists, every line redacted (tokens, keys,
        passwords, e-mail and IP addresses). `follow=true` streams new lines as server-sent events for at
        most 15 minutes. Owner only."""
        if not p.is_owner:
            raise deny(p, "read service logs", "only an owner may read service logs")
        unit_or_404(unit)
        gw.events.publish_event("logs", "opened", {"unit": unit, "tail": tail, "follow": follow}, principal=p.as_dict())
        if follow:
            with streams_lock:
                if streams[p.id] >= STREAMS_PER_PRINCIPAL:
                    return JSONResponse(status_code=429, headers={"Retry-After": "60"},
                                        content={"error": "rate_limited", "message": "too many open log streams",
                                                 "reason": "limit_reached", "retry_after_s": 60})
                streams[p.id] += 1
        try:
            stream = client.logs(unit, tail, follow, FOLLOW_MAX_S)
        except (StorageUnavailable, StorageTimeout):
            release(p, follow)
            raise ApiError(409, "conflict", "the host service is not reachable, so the logs cannot be read",
                           reason="host_unavailable") from None
        if stream.status != 200:
            stream.close()
            release(p, follow)
            if stream.status == 404:
                raise ApiError(404, "not_found", "the services registry on this box does not list that unit")
            raise ApiError(409, "conflict", f"the host service answered {stream.status}", reason="host_unavailable")
        r = Redactor()  # the app-log filter (#543): stateful, so a PEM block across lines stays hidden
        if not follow:
            try:
                out = [r.line(x) for x in stream.lines()]
            finally:
                stream.close()
            return PlainTextResponse("\n".join(out) + ("\n" if out else ""), headers={"Cache-Control": "no-store"})

        def gen():
            try:
                for line in stream.lines():
                    yield f"data: {r.line(line)}\n\n"
                yield "event: end\ndata: stream closed\n\n"
            finally:
                stream.close()
                release(p, True)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    def release(p: Principal, follow: bool) -> None:
        if follow:
            with streams_lock:
                streams[p.id] -= 1

    @app.post("/v1/system/services/{unit}/restart", tags=["system"], operation_id="system.services.restart",
              status_code=202, response_model=Action,
              responses={200: {"model": Action, "description": "Idempotent replay"},
                         **error_responses(401, 403, 404, 409, 422, 429)})
    def system_service_restart(unit: str, req: ServiceRestartRequest | None = None, p: Principal = Depends(gw.principal),
                               idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Ask for a restart of one service. It waits for the owner, who approves it with a passkey; the
        response is the action, whose id is the approval to look for. An agent may ask, never approve.

        403 not_restartable for a unit the registry does not mark restartable (rescue, first-boot, host and
        data-layout units never are); 404 for a unit the registry does not list; 409 host_unavailable while
        the host service cannot restart services (nothing is filed). The `Idempotency-Key` header (or the body's
        `idempotency_key`, the §3 field) makes a retry replay the same action."""
        req = req or ServiceRestartRequest()
        if not p.can_request_actions or not (p.is_owner or p.kind in REQUESTERS):
            raise deny(p, f"request {ACTION}", "only an owner or an agent may ask for a service restart")
        unit_or_404(unit)
        problem = restartable_problem(unit)
        if problem is not None:
            status, msg = problem
            if status == 403:
                raise deny(p, f"request {ACTION} of {unit}", msg, reason="not_restartable")
            if status == 404:
                raise ApiError(404, "not_found", msg)
            raise ApiError(409, "conflict", msg, reason="host_unavailable")
        why = app.state.hostlink.problem(ACTION)
        if why is not None:
            raise ApiError(409, "conflict", why[1], reason="host_unavailable")
        body, created = gw.actions.request_feature(
            p, ACTION, {"unit": unit}, idempotency_key=idem or req.idempotency_key or f"service:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=req.reason, pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body, headers={"Location": f"/v1/actions/{body['id']}"})


def passkey_step_up(gw: Gateway):
    """Approval guard: a service restart is approved only with the owner's passkey (#636), whatever
    `require_passkey_approval` says. The identity guard (registered earlier, so it runs first) verifies the
    assertion: signed over this action, by an active owner. Same rule as a factory reset (routers/system.py)."""

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        if action.get("type") != ACTION:
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if not (body.get("webauthn") or body.get("password_totp")) or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": ACTION, "reason": "service_restart_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "confirm the restart with your passkey or your password and "
                           "authenticator code",
                           reason="step_up_required")

    return guard

