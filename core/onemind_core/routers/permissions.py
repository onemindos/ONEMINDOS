# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 8: decide() on every filing path, the hard floor, deny rules, the clock guard.

Routes (gateway permissions design §3.12):
- GET /v1/approval-denies: the owner sees every deny rule; a person sees those on agents they own.
- POST /v1/approval-denies: add a "never" for one principal and one type or tier. It only tightens,
  so the owner or the person who owns that agent may add one, with no step-up (D-028: L0).
- DELETE /v1/approval-denies/{deny_id}: removing one loosens: the owner only, behind the passkey
  step-up (L1 today; D-028 sets L2 as the target, which arrives with design PR 11).

Agents never reach these routes: deny rules are about them, and an agent that could read its own
denies could shape its requests around them.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..auth import Principal
from ..catalog import GREEN_LICENCE_CLASSES
from ..context import Gateway
from ..errors import error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..permissions.clock import ClockGuard
from ..permissions.denies import DenyStore
from ..permissions.engine import PermissionEngine

ORDER = 290  # after identity (260) and automation (280): the engine reads both
TAGS = ["permissions"]

register_route_scope("GET,HEAD,POST", r"/v1/approval-denies", ("tokens:self",))
register_route_scope("DELETE", r"/v1/approval-denies/[^/]+", ("*",))  # owner only: removing a deny loosens


class ApprovalDeny(BaseModel):
    """A deny rule: `principal` may never have `action_type` (or any request of `tier`) approved."""

    id: str
    principal: str
    action_type: str | None = None
    tier: str | None = Field(default=None, description="T0 read, T1 write, T2 sensitive, T3 destructive, T4 actuate, P physical")
    reason: str | None = None
    created_by: dict
    created_at: str


class ApprovalDenyBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    principal: str = Field(max_length=100, description="the principal it refuses, e.g. agent:notes-helper")
    action_type: str | None = Field(default=None, max_length=80, description="one action type; or name a tier")
    tier: Literal["T0", "T1", "T2", "T3", "T4", "P"] | None = Field(default=None, description="every request of this tier")
    reason: str | None = Field(default=None, max_length=200, description="why, shown to the owner and in the audit")


def register(app: FastAPI, gw: Gateway) -> None:
    denies = DenyStore(gw.db, gw.audit, gw.clock)
    engine = PermissionEngine(denies, ClockGuard(gw.db, gw.audit, gw.clock), gw.audit)
    engine.taint = gw.actions.taint
    engine.motion_lockout = lambda: gw.actions.motion_lockout()  # read at call time: physical.py sets it

    def agents_stopped() -> bool:
        stop = getattr(app.state, "agent_stop", None)
        return bool(stop and stop.on)

    def automation_paused() -> bool:
        svc = getattr(app.state, "automation", None)
        return bool(svc and svc.paused())

    def floor_settings_on() -> bool:
        ident = getattr(app.state, "identity", None)
        if ident is None:  # no household accounts: the static tokens file and its owner only
            return True
        return bool(ident.cfg.enforce_role_scopes and ident.cfg.require_passkey_approval)

    def rule_for(action_type: str, params: dict, requested_by: dict) -> str | None:
        svc = getattr(app.state, "automation", None)
        if svc is None:
            return None
        v = svc.policies.evaluate(action_type, params, requested_by, gw.clock(), paused=svc.paused())
        return v.approver if v.outcome == "auto_approved" else None

    def licence_green(action_type: str, params: dict) -> bool:
        if action_type not in ("app.install", "app.update"):
            return True
        app_entry = gw.catalog.get(params.get("app_id")) if isinstance(params.get("app_id"), str) else None
        return app_entry is not None and app_entry.licence_class in GREEN_LICENCE_CLASSES

    def owned_by(user_id: str) -> set[str]:
        try:
            from ..identity.models import TokenRow
        except Exception:
            return set()
        with gw.db.session() as s:
            return set(s.scalars(select(TokenRow.principal_id).where(
                TokenRow.owner_user_id == user_id, TokenRow.kind.in_(("agent", "plugin")), TokenRow.revoked_at.is_(None))))

    engine.agents_stopped = agents_stopped
    engine.automation_paused = automation_paused
    engine.floor_settings_on = floor_settings_on
    engine.rule_for = rule_for
    engine.licence_green = licence_green
    denies.owned_by = owned_by
    gw.actions.permissions = engine
    app.state.permissions = engine

    def user_id(request: Request) -> str | None:
        ctx = ctx_of(request)
        return ctx.user.id if ctx is not None and ctx.user is not None else None

    @app.get("/v1/approval-denies", operation_id="approvals.denies.list", tags=TAGS,
             responses={200: {"model": list[ApprovalDeny]}, **error_responses(401, 403)},
             openapi_extra={"security": [{"bearer": ["tokens:self"]}]})
    def list_denies(request: Request, p: Principal = Depends(gw.principal)):
        if not denies.may_hold_agents(p):  # agents never; guests and children own no agent
            denies._denied(p, "list deny rules")
        return denies.visible_to(p, user_id(request))

    @app.post("/v1/approval-denies", operation_id="approvals.denies.create", tags=TAGS, status_code=201,
              responses={201: {"model": ApprovalDeny}, **error_responses(401, 403, 409, 422)},
              openapi_extra={"security": [{"bearer": ["tokens:self"]}]})
    def create_deny(body: ApprovalDenyBody, request: Request, p: Principal = Depends(gw.principal)):
        out = denies.add(p, user_id(request), body.principal, body.action_type, body.tier, body.reason)
        return JSONResponse(status_code=201, content=out)

    @app.delete("/v1/approval-denies/{deny_id}", operation_id="approvals.denies.delete", tags=TAGS, status_code=204,
                responses=error_responses(401, 403, 404), openapi_extra={"security": [{"bearer": ["*"]}]})
    def delete_deny(deny_id: str, request: Request, p: Principal = Depends(gw.principal)):
        if not p.is_owner:
            denies._denied(p, "remove a deny rule")
        ident = getattr(app.state, "identity", None)
        via = ident.require_step_up(ctx_of(request), p, "remove a deny rule") if ident is not None else "token"
        denies.remove(p, deny_id, via)
        return Response(status_code=204)
