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
from ..permissions.modes import HOUSEHOLD, ModeStore
from ..principals import display_key

ORDER = 290  # after identity (260) and automation (280): the engine reads both
TAGS = ["permissions"]

register_route_scope("GET,HEAD,POST", r"/v1/approval-denies", ("tokens:self",))
# PR 10: modes. Reading is open to anyone signed in (an agent reads only its own: the handler checks);
# changing one needs a person (tightening: anyone with a say; loosening: the owner, with a passkey).
register_route_scope("GET,HEAD", r"/v1/permission-modes(/[^/]+)?", ("instance:read",))
register_route_scope("PUT", r"/v1/permission-modes(/[^/]+)?", ("tokens:self",))
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


class PermissionMode(BaseModel):
    """A principal's permission mode (design §3.5). `own: false` means it follows the household default."""

    principal: str
    mode: str = Field(description="locked, ask (Always ask), remember, auto (Auto within rules), headless or bypass")
    own: bool
    set_by: dict | None = None
    set_at: str | None = None
    reason: str | None = None
    household_default: str
    owner_passkey: bool = Field(description="false: nothing can be loosened yet and every mode behaves as Always ask (F-8)")


class PermissionModeBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["locked", "ask", "remember", "auto", "headless", "bypass"]
    reason: str | None = Field(default=None, max_length=200, description="why, for the audit record")


def owner_has_passkey(app: FastAPI) -> bool:
    """F-8: has any active owner a passkey? Without identity (static tokens only) there is no passkey to add,
    so nothing can be loosened either."""
    ident = getattr(app.state, "identity", None)
    return bool(ident is not None and ident.passkeys_active())


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
    # ---- PR 10: modes --------------------------------------------------------------------------
    modes = ModeStore(gw.db, gw.audit, gw.clock)
    modes.owned_by = owned_by
    modes.owner_passkey = lambda: owner_has_passkey(app)

    def cancel_pending(name: str, by: Principal) -> int:
        """Locked: the principal's requests waiting for a person are cancelled (as an agent cancel does)."""
        now, n = gw.clock(), 0
        for a in gw.actions.repo.list({"awaiting_approval"}):
            if display_key(a.requested_by) != name:
                continue
            if gw.actions.repo.transition(a.id, {"awaiting_approval"}, "cancelled", now,
                                          decided_by=by.as_dict(), decided_at=now) is not None:
                n += 1
                gw.actions._release_feature(a)
                gw.audit.append("action.denied", by.as_dict(), a.id, {"params": a.params, "reason": "mode_locked"})
        return n

    modes.cancel_pending = cancel_pending

    def is_owner_id(pid: str) -> bool:
        """§3.5.1: is this person an owner? Static-file tokens first, then each people source."""
        if any(fp.kind == "person" and fp.id == pid and fp.role == "owner" for _, fp in gw.tokens.entries()):
            return True
        return any(source().get(pid) == "owner" for source in gw.people_sources)

    modes.is_owner = lambda name: name.startswith("person:") and is_owner_id(name.partition(":")[2])
    engine.is_owner = lambda rb: str(rb.get("kind") or "") == "person" and is_owner_id(str(rb.get("id") or ""))
    engine.mode_of = modes.effective
    engine.owner_passkey = modes.owner_passkey
    engine.modes = modes

    def no_rule_before_a_passkey() -> str | None:  # F-8: creating or widening a rule loosens too
        return None if owner_has_passkey(app) else "no_owner_passkey"

    svc = getattr(app.state, "automation", None)
    if svc is not None:
        svc.policies.loosen_guard = no_rule_before_a_passkey
        svc.policies.mode_of = modes.effective  # each rule shows whether its principal's mode lets it fire

        def live_rule_principals() -> set[str]:
            return {w for p in svc.repo.list_policies() for w in p["allow"]["requested_by"] if not w.endswith(":*")}

        def wildcard_rules() -> list[str]:
            return [p["id"] for p in svc.repo.list_policies() if any(w.endswith(":*") for w in p["allow"]["requested_by"])]

        gw.on_startup(lambda: modes.migrate(live_rule_principals, wildcard_rules))

    notify = getattr(app.state, "notify", None)
    if notify is not None and svc is not None:  # PR 13: approval.auto notices
        notify.auto_push_failed = svc.policies.pause
        notify.rules_in_force = lambda: [svc.policies.to_json(p) for p in svc.repo.list_policies()]

    gw.actions.permissions = engine
    app.state.permissions = engine

    def user_id(request: Request) -> str | None:
        ctx = ctx_of(request)
        return ctx.user.id if ctx is not None and ctx.user is not None else None

    def name_of(raw: str) -> str:
        return HOUSEHOLD if raw in ("default", HOUSEHOLD) else raw

    @app.get("/v1/permission-modes", operation_id="permissions.modes.list", tags=TAGS,
             responses={200: {"model": list[PermissionMode]}, **error_responses(401, 403)},
             openapi_extra={"security": [{"bearer": ["instance:read"]}]})
    def list_modes(request: Request, p: Principal = Depends(gw.principal)):
        """The household default first, then every principal with a mode of its own (owner: all; a person:
        the agents they own; an agent: only its own)."""
        uid = user_id(request)
        rows = [modes.household_view()] + modes.list()
        return [r for r in rows if r["principal"] == HOUSEHOLD or modes.may_read(p, r["principal"], uid)]

    @app.get("/v1/permission-modes/{principal}", operation_id="permissions.modes.get", tags=TAGS,
             responses={200: {"model": PermissionMode}, **error_responses(401, 403, 422)},
             openapi_extra={"security": [{"bearer": ["instance:read"]}]})
    def get_mode(principal: str, request: Request, p: Principal = Depends(gw.principal)):
        name = name_of(principal)
        if name == HOUSEHOLD:
            return modes.household_view()
        if not modes.may_read(p, name, user_id(request)):
            modes._denied(p, f"read the mode of {name}")
        return modes.view(name)

    def put(name: str, body: PermissionModeBody, request: Request, p: Principal):
        direction = modes.check_change(p, name, body.mode, user_id(request))
        via = None
        if direction == "loosen":
            ident = getattr(app.state, "identity", None)
            via = ident.require_step_up(ctx_of(request), p, "loosen a permission mode") if ident is not None else "token"
        return modes.set(p, name, body.mode, body.reason, direction, via)

    @app.put("/v1/permission-modes", operation_id="permissions.modes.set_default", tags=TAGS,
             responses={200: {"model": PermissionMode}, **error_responses(401, 403, 409, 422)},
             openapi_extra={"security": [{"bearer": ["tokens:self"]}]})
    def set_default_mode(body: PermissionModeBody, request: Request, p: Principal = Depends(gw.principal)):
        return put(HOUSEHOLD, body, request, p)

    @app.put("/v1/permission-modes/{principal}", operation_id="permissions.modes.set", tags=TAGS,
             responses={200: {"model": PermissionMode}, **error_responses(401, 403, 409, 422)},
             openapi_extra={"security": [{"bearer": ["tokens:self"]}]})
    def set_mode(principal: str, body: PermissionModeBody, request: Request, p: Principal = Depends(gw.principal)):
        return put(name_of(principal), body, request, p)

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
