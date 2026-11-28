# SPDX-License-Identifier: Apache-2.0
"""System controls (UMB-P09, #146): /v1/system/controls, /v1/system/diagnostics, /v1/system/actions.

Reads are owner-only. Restart, shutdown and factory reset are requests filed in the action ledger;
the owner approves them at /v1/actions/{id}/approve, and a factory reset only with a passkey.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..system import (CONTROLS, RESET_PHRASE, DiagnosticsBundle, HostLinkExecutor, SystemActionRequest, SystemControls,
                      SystemService)

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 340
REQUEST_TTL = timedelta(hours=24)


def passkey_step_up(gw: Gateway):
    """Approval guard: a control marked needs_passkey (factory reset) is approved only with a passkey.

    The identity guard (registered earlier, so it runs first) verifies the assertion: signed over this
    action, by an active owner. This guard makes the assertion mandatory for these types, whatever
    `require_passkey_approval` says. Same rule as destructive storage actions (routers/storage.py)."""

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        spec = CONTROLS.get(action.get("type"))
        if spec is None or not spec[3]:
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if not (body.get("webauthn") or body.get("password_totp")) or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": action.get("type"), "reason": "factory_reset_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "a factory reset needs a proven passkey or a sign-in check "
                           "with the code from the box's screen",
                           reason="step_up_required")

    return guard


# Registered once at import, not per app (CORE-HYG-01, #323).
# machines:admin-style scope minted to no one: only the owner role (every scope) holds system:admin.
register_route_scope("GET,HEAD", r"/v1/system/(controls|diagnostics)", ("system:admin",))
register_route_scope("POST", r"/v1/system/actions", ("actions:request",))


def register(app: FastAPI, gw: Gateway) -> None:
    svc = SystemService(gw, HostLinkExecutor(app.state.hostlink))
    for action_type, (_, risk, requesters, _) in CONTROLS.items():
        gw.actions.register_type(action_type, FeatureAction(risk, svc.run, requesters))
    gw.approval_guards.append(passkey_step_up(gw))
    app.state.system = svc
    principal = gw.principal

    def owner(p: Principal, what: str) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may do this")

    @app.get("/v1/system/controls", tags=["system"], operation_id="system.controls", response_model=SystemControls,
             responses=error_responses(401, 403))
    def system_controls(p: Principal = Depends(principal)):
        """Restart, shutdown and factory reset: whether this box can perform them, and the requests waiting."""
        owner(p, "read system controls")
        return svc.controls()

    @app.get("/v1/system/diagnostics", tags=["system"], operation_id="system.diagnostics", response_model=DiagnosticsBundle,
             responses=error_responses(401, 403))
    def system_diagnostics(p: Principal = Depends(principal)):
        """A redacted diagnostic bundle for support: versions, node health, recent actions and audit events."""
        owner(p, "export diagnostics")
        bundle = svc.diagnostics()
        gw.audit.append("system.diagnostics.exported", p.as_dict(), None, {"redaction": bundle["redaction"]["found"]})
        return JSONResponse(content=bundle, headers={
            "Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="onemind-diagnostics.json"'})

    @app.post(
        "/v1/system/actions", tags=["system"], operation_id="system.actions.create", status_code=202,
        response_model=Action,
        responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 409, 422, 429)},
    )
    def system_request(req: SystemActionRequest, p: Principal = Depends(principal)):
        """Request a restart, shutdown or factory reset. It waits for the owner's approval.

        409 host_unavailable while this box cannot perform the control (nothing is filed: an approval
        that can only fail would be noise); 429 too_many_pending when an agent has too many waiting."""
        requesters = CONTROLS[req.type][2]
        why = svc.executor.unavailable(req.type)
        if why and p.can_request_actions and (p.is_owner or p.kind in requesters):  # others get request_feature's 403
            raise ApiError(409, "conflict", why, reason="host_unavailable")
        params: dict = {}
        if req.type == "system.factory_reset":
            if req.confirm != RESET_PHRASE:
                raise ApiError(422, "conflict", f'a factory reset needs confirm set to "{RESET_PHRASE}", typed by the owner',
                               reason="confirm_mismatch")
            # The wipe is bound to the plan the host showed now: it refuses a plan that changed before it runs.
            plan = svc.executor.reset_plan_hash() if isinstance(svc.executor, HostLinkExecutor) else None
            if isinstance(svc.executor, HostLinkExecutor) and plan is None:
                raise ApiError(409, "conflict", "the host service could not give the factory-reset plan; nothing was filed",
                               reason="host_unavailable")
            params = {"confirm": RESET_PHRASE, **({"plan_sha256": plan} if plan else {})}
        elif req.confirm is not None:
            raise ApiError(422, "conflict", "confirm is only for system.factory_reset")
        body, created = gw.actions.request_feature(
            p, req.type, params, idempotency_key=req.idempotency_key or f"system:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=req.reason, pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body,
                            headers={"Location": f"/v1/actions/{body['id']}"})
