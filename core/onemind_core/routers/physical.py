# SPDX-License-Identifier: Apache-2.0
"""Physical actions (#723): the owner's motion lockout and the passkey guard on physical approvals.

GET /v1/physical/lockout   owner: {locked, changed_by, changed_at, reason}
PUT /v1/physical/lockout   owner: {locked, reason?}; turning it off needs a fresh passkey once active

The rules themselves live in the action service (actions.py, FeatureAction.physical): passkey and
hold-to-approve, plan-bound, never a standing approval or an automation, refused while locked.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..physical import MotionLockout, MotionLockoutChange, MotionLockoutState

# After the action routes (150): it plugs the lockout into the action service they serve.
ORDER = 155

# Minted to no one: only the owner role (every scope) holds it, never an agent, automation or plugin.
register_route_scope("GET,HEAD,PUT", r"/v1/physical/lockout", ("physical:admin",))


def physical_step_up(gw: Gateway):
    """Approval guard: a physical action is approved only with a passkey assertion the identity guard
    verified (signed over this action and plan, by an active owner), whatever
    `require_passkey_approval` says. Same shape as destructive storage actions (routers/storage.py)."""

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        if not gw.actions.is_physical(str(action.get("type"))):
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if not (body.get("webauthn") or body.get("password_totp")) or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": action.get("type"),
                 "reason": "physical_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "this action moves something physical: it needs L2 verification",
                           reason="step_up_required")

    return guard


def register(app: FastAPI, gw: Gateway) -> None:
    lockout = MotionLockout(gw.db, gw.audit, gw.clock)
    gw.actions.motion_lockout = lockout.locked
    gw.approval_guards.append(physical_step_up(gw))
    app.state.motion_lockout = lockout
    principal = gw.principal
    tags = ["physical"]

    @app.get("/v1/physical/lockout", tags=tags, operation_id="physical.lockout.get",
             response_model=MotionLockoutState, responses=error_responses(401, 403))
    def get_lockout(p: Principal = Depends(principal)):
        """Whether the owner's motion lockout refuses every physical action right now."""
        lockout.owner_only(p, "read the motion lockout")
        return lockout.state()

    @app.put("/v1/physical/lockout", tags=tags, operation_id="physical.lockout.set",
             response_model=MotionLockoutState, responses=error_responses(401, 403, 422))
    def set_lockout(body: MotionLockoutChange, request: Request, p: Principal = Depends(principal)):
        """Turn the motion lockout on (at once) or off (with a fresh passkey once passkeys are active)."""
        lockout.owner_only(p, "set the motion lockout")
        via = "token"
        ident = getattr(app.state, "identity", None)
        if not body.locked and ident is not None:
            via = ident.require_step_up(ctx_of(request), p, "turn off the motion lockout", op="physical.lockout.set",
                                        body=body.model_dump(mode="json"))
        return lockout.set(p, body.locked, body.reason, via)
