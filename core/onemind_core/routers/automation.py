# SPDX-License-Identifier: Apache-2.0
"""Contract §12.17: automation rules, runs, schedules, standing approvals, windows, kill switch."""

from __future__ import annotations

import re
from datetime import timedelta

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..automation import AutomationService
from ..automation.cron import parse_ranges, window_minutes
from ..automation.engine import DryRunBody, PauseBody, RuleBody, RulePatch
from ..automation.policies import ApprovalPolicy, PolicyBody, PolicyPatch
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..ledger import iso
from ..permissions.changes import QUEUED, register_change, request_change

WINDOW_ID_RE = re.compile(r"^win_[a-z0-9_]{1,36}$")


class RevokeAllBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principal: str | None = Field(default=None, max_length=100,
                                  description="revoke every rule naming this principal; null (owner only) revokes every rule")


class RevokeAllResult(BaseModel):
    revoked: list[str] = Field(description="the ids of the rules revoked")


ONE = {200: {"model": ApprovalPolicy}}  # response documentation: the Rules screen reads these fields


class WindowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    tz: str = Field(default="box", max_length=64)
    ranges: list[dict]


class WindowView(WindowBody):
    id: str
    updated_at: str
    open_now: bool


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 280

# Gateway permissions PR 9. Revoking only narrows: the owner, or a person for rules naming only agents they
# own (the handler checks). Editing, re-confirming and keeping are the owner's (the handler checks too).
register_route_scope("PATCH", r"/v1/approval-policies/[^/]+", ("*",))
register_route_scope("POST", r"/v1/approval-policies/[^/]+/(reconfirm|keep)", ("*",))
register_route_scope("POST", r"/v1/approval-policies/([^/]+/revoke|revoke-all)", ("tokens:self",))


def register(app: FastAPI, gw: Gateway) -> None:
    svc = AutomationService(gw)
    policies = svc.policies
    principal = gw.principal
    gw.actions.standing_approvals.append(lambda a: policies.decide(a, svc.paused()))
    policies.can_file = gw.actions.can_file
    # Gateway permissions PR 7: rules bind agents and plugins to their permanent principal id.
    policies.principals = gw.actions.principals
    gw.on_startup(policies.adopt_unbound)
    # Gateway permissions PR 9: what a request writes to and how much (FeatureAction.target_for / size_for),
    # and the triggers that suspend a rule (design §3.6.2 item 7).

    def target_of(action_type: str, params: dict | None):
        spec = gw.actions.feature_types.get(action_type)
        if spec is None or spec.target_for is None:
            return None
        return ("?", "?") if params is None else spec.target_for(params)

    def size_of(action_type: str, params: dict) -> tuple[int, int]:
        spec = gw.actions.feature_types.get(action_type)
        return spec.size_for(params) if spec is not None and spec.size_for is not None else (0, 1)

    policies.target_of = target_of
    policies.size_of = size_of
    if gw.actions.principals is not None:
        gw.actions.principals.listeners.append(policies.suspend_for)

    def owned_agents(user_id: str | None) -> set[str]:
        if not user_id:
            return set()
        try:
            from ..identity.models import TokenRow
        except Exception:
            return set()
        from sqlalchemy import select

        with gw.db.session() as s:
            return set(s.scalars(select(TokenRow.principal_id).where(
                TokenRow.owner_user_id == user_id, TokenRow.kind.in_(("agent", "plugin")), TokenRow.revoked_at.is_(None))))

    def on_role_change(user_id: str, _role: str, _by) -> None:
        for name in owned_agents(user_id) | {f"person:{user_id}"}:
            policies.suspend_for(name, "owner_role_changed")

    def wire_identity() -> None:
        ident = getattr(app.state, "identity", None)
        if ident is not None and on_role_change not in ident.role_hooks:
            ident.role_hooks.append(on_role_change)

    wire_identity()
    gw.events.subscribe(">", svc.on_event)
    gw.on_startup(svc.start)
    gw.on_shutdown(svc.stop)
    app.state.automation = svc

    tags = ["automation"]

    # ---- rules ---------------------------------------------------------------------------------
    @app.get("/v1/automation/rules", operation_id="automation.rules.list", tags=tags, responses=error_responses(401))
    def list_rules(_: Principal = Depends(principal)):
        return svc.list()

    @app.post("/v1/automation/rules", operation_id="automation.rules.create", tags=tags, status_code=201, responses=error_responses(401, 403, 404, 422))
    def create_rule(body: RuleBody, p: Principal = Depends(principal)):
        return JSONResponse(status_code=201, content=svc.create(p, body))

    @app.get("/v1/automation/rules/{rule_id}", operation_id="automation.rules.get", tags=tags, responses=error_responses(401, 404))
    def get_rule(rule_id: str, _: Principal = Depends(principal)):
        return svc.get(rule_id)

    @app.patch("/v1/automation/rules/{rule_id}", operation_id="automation.rules.update", tags=tags, responses=error_responses(401, 403, 404, 409, 422))
    def update_rule(rule_id: str, body: RulePatch, p: Principal = Depends(principal)):
        return svc.update(p, rule_id, body)

    @app.post("/v1/automation/rules/{rule_id}/enable", operation_id="automation.rules.enable", tags=tags, responses=error_responses(401, 403, 404, 409))
    def enable_rule(rule_id: str, p: Principal = Depends(principal)):
        return svc.enable(p, rule_id)

    @app.post("/v1/automation/rules/{rule_id}/disable", operation_id="automation.rules.disable", tags=tags, responses=error_responses(401, 403, 404))
    def disable_rule(rule_id: str, p: Principal = Depends(principal)):
        return svc.disable(p, rule_id)

    @app.delete("/v1/automation/rules/{rule_id}", operation_id="automation.rules.delete", tags=tags, status_code=204, responses=error_responses(401, 403, 404))
    def delete_rule(rule_id: str, p: Principal = Depends(principal)):
        svc.delete(p, rule_id)
        return Response(status_code=204)

    @app.post("/v1/automation/rules/{rule_id}/dry-run", operation_id="automation.rules.dry_run", tags=tags, responses=error_responses(401, 404, 422))
    def dry_run(rule_id: str, body: DryRunBody | None = None, p: Principal = Depends(principal)):
        return svc.dry_run(p, rule_id, body or DryRunBody())

    @app.get("/v1/automation/runs", operation_id="automation.runs.list", tags=tags, responses=error_responses(401, 422))
    def list_runs(rule_id: str | None = None, limit: int = Query(100, ge=1, le=500),
                  _: Principal = Depends(principal)):
        return svc.runs(rule_id, limit)

    @app.get("/v1/automation/schedules", operation_id="automation.schedules.list", tags=tags, responses=error_responses(401))
    def list_schedules(_: Principal = Depends(principal)):
        return svc.schedules()

    # ---- kill switch ---------------------------------------------------------------------------
    @app.get("/v1/automation/state", operation_id="automation.state.get", tags=tags, responses=error_responses(401))
    def get_state(_: Principal = Depends(principal)):
        return svc.state()

    @app.post("/v1/automation/pause", operation_id="automation.pause", tags=tags, responses=error_responses(401, 403, 422))
    def pause(body: PauseBody | None = None, p: Principal = Depends(principal)):
        return svc.set_paused(p, True, (body or PauseBody()).reason)

    @app.post("/v1/automation/resume", operation_id="automation.resume", tags=tags, responses=error_responses(401, 403, 422))
    def resume(body: PauseBody | None = None, p: Principal = Depends(principal)):
        return svc.set_paused(p, False, (body or PauseBody()).reason)

    # ---- standing approvals --------------------------------------------------------------------
    def reviewed_window(params: dict):
        if "window" not in params and params["rule"].get("window_id") is not None:
            raise ApiError(409, "stale_precondition", "the request lacks a reviewed maintenance window; file it again")
        return params.get("window")

    register_change(app, gw, "policy.rule.create", lambda p, params: policies.create(
        p, PolicyBody.model_validate(params["rule"]), "L2", expected_bindings=params["principals"],
        expected_window=reviewed_window(params)))
    register_change(app, gw, "policy.rule.widen", lambda p, params: policies.revise(
        p, params["id"], PolicyPatch.model_validate(params["patch"]), "L2", expected_bindings=params["principals"],
        expected_window=reviewed_window(params)))
    register_change(app, gw, "policy.rule.confirm", lambda p, params: policies.confirm(
        p, params["id"], revision=params["revision"]))
    register_change(app, gw, "policy.rule.reconfirm", lambda p, params: policies.reconfirm(
        p, params["id"], "L2", expected=params))
    register_change(app, gw, "policy.rule.keep", policies.keep)

    @app.get("/v1/approval-policies", operation_id="approvals.policies.list", tags=tags,
             responses={200: {"model": list[ApprovalPolicy]}, **error_responses(401, 403)})
    def list_policies(p: Principal = Depends(principal)):
        # Gateway permissions design gap 3: the rules are the owner's. An agent that can read them can shape its
        # requests to fit one, so every other principal is refused (and the refusal is audited).
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "list standing approvals", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not list standing approvals")
        policies.lapse_due(gw.clock())
        return [policies.to_json(x) for x in svc.repo.list_policies(with_paused=True)]

    @app.post("/v1/approval-policies", operation_id="approvals.policies.create", tags=tags, status_code=202,
              responses={**QUEUED, **error_responses(401, 403, 404, 409, 422, 429)})
    def create_policy(body: PolicyBody, p: Principal = Depends(principal)):
        preview = policies.prepare_create(p, body)
        return request_change(app, gw, p, "policy.rule.create",
                              {"rule": body.model_dump(mode="json"), "principals": preview["principals"],
                               "window": policies.window_snapshot(body.window_id)})

    @app.post("/v1/approval-policies/{policy_id}/confirm", operation_id="approvals.policies.confirm", tags=tags,
              responses={**QUEUED, **error_responses(401, 403, 404, 409, 429)}, status_code=202,
              openapi_extra={"security": [{"bearer": ["*"]}]})
    def confirm_policy(policy_id: str, p: Principal = Depends(principal)):
        policies._owner_only(p, "confirm standing approval")
        current = policies._get(policy_id)
        if current["state"] != "paused":
            raise ApiError(404, "not_found", "no paused standing approval with that id")
        return request_change(app, gw, p, "policy.rule.confirm", {"id": policy_id, "revision": current["revision"],
                               "rule": policies._body_of(current).model_dump(mode="json")})

    def caller_user(request: Request) -> str | None:
        ctx = ctx_of(request)
        return ctx.user.id if ctx is not None and ctx.user is not None else None

    @app.patch("/v1/approval-policies/{policy_id}", operation_id="approvals.policies.update", tags=tags,
               responses={**ONE, **QUEUED, **error_responses(401, 403, 404, 409, 422, 429)},
               openapi_extra={"security": [{"bearer": ["*"]}]})
    def update_policy(policy_id: str, body: PolicyPatch, p: Principal = Depends(principal)):
        policies._owner_only(p, "edit standing approvals")
        direction, rule, patch = policies.revision_request(policy_id, body)
        if direction != "widen":
            return policies.revise(p, policy_id, patch, None)
        policies._check_loosen()
        updated = PolicyBody.model_validate(rule)
        policies.validate(updated)
        if updated.forever:
            policies._require_proven("making a rule Forever")
        return request_change(app, gw, p, "policy.rule.widen",
                              {"id": policy_id, "rule": rule, "patch": patch.model_dump(mode="json", exclude_unset=True),
                               "principals": policies._bindings(updated.allow.requested_by),
                               "window": policies.window_snapshot(updated.window_id)})

    @app.post("/v1/approval-policies/{policy_id}/revoke", operation_id="approvals.policies.revoke", tags=tags,
              responses={**ONE, **error_responses(401, 403, 404)}, openapi_extra={"security": [{"bearer": ["tokens:self"]}]})
    def revoke_policy(policy_id: str, request: Request, p: Principal = Depends(principal)):
        # One tap, no step-up (L0): ending a rule only narrows (design §3.6.2 item 3).
        if not (p.kind == "person" and p.role in ("owner", "adult")):  # people who can own an agent
            policies._owner_only(p, "revoke standing approvals")
        return policies.revoke(p, policy_id, owned_agents(caller_user(request)))

    @app.post("/v1/approval-policies/revoke-all", operation_id="approvals.policies.revoke_all", tags=tags,
              responses={200: {"model": RevokeAllResult}, **error_responses(401, 403, 422)}, openapi_extra={"security": [{"bearer": ["tokens:self"]}]})
    def revoke_all(body: RevokeAllBody, request: Request, p: Principal = Depends(principal)):
        if not (p.kind == "person" and p.role in ("owner", "adult")):
            policies._owner_only(p, "revoke standing approvals")
        return {"revoked": policies.revoke_all(p, body.principal, owned_agents(caller_user(request)))}

    @app.post("/v1/approval-policies/{policy_id}/reconfirm", operation_id="approvals.policies.reconfirm", tags=tags,
              responses={**QUEUED, **error_responses(401, 403, 404, 409, 422, 429)}, status_code=202,
              openapi_extra={"security": [{"bearer": ["*"]}]})
    def reconfirm_policy(policy_id: str, p: Principal = Depends(principal)):
        policies._owner_only(p, "re-confirm standing approvals")
        current = policies._get(policy_id)
        if not current.get("suspended_at"):
            raise ApiError(409, "conflict", "this rule is not suspended")
        return request_change(app, gw, p, "policy.rule.reconfirm", {"id": policy_id, "revision": current["revision"],
                               "rule": policies._body_of(current).model_dump(mode="json"),
                               "principals": policies._bindings(current["allow"]["requested_by"])})

    @app.post("/v1/approval-policies/{policy_id}/keep", operation_id="approvals.policies.keep", tags=tags,
              status_code=202, responses={**QUEUED, **error_responses(401, 403, 404, 409, 429)},
              openapi_extra={"security": [{"bearer": ["*"]}]})
    def keep_policy(policy_id: str, p: Principal = Depends(principal)):
        return request_change(app, gw, p, "policy.rule.keep", policies.keep_preview(p, policy_id))

    @app.delete("/v1/approval-policies/{policy_id}", operation_id="approvals.policies.delete", tags=tags, status_code=204,
                responses=error_responses(401, 403, 404))
    def delete_policy(policy_id: str, p: Principal = Depends(principal)):
        policies.delete(p, policy_id)
        return Response(status_code=204)

    # ---- maintenance windows -------------------------------------------------------------------
    def window_json(w: dict) -> dict:
        return {"id": w["id"], "name": w["name"], "tz": w["tz"], "ranges": w["ranges"],
                "updated_at": iso(w["updated_at"]), "open_now": policies.window_is_open(w["id"], gw.clock())}

    @app.get("/v1/windows", operation_id="windows.list", tags=tags, response_model=list[WindowView], responses=error_responses(401))
    def list_windows(_: Principal = Depends(principal)):
        return [window_json(w) for w in svc.repo.list_windows()]

    def write_window(p: Principal, window_id: str, body: WindowBody, current: dict | None, approval: str) -> dict:
        now = gw.clock()
        if current is not None and now <= current["updated_at"]:
            now = current["updated_at"] + timedelta(microseconds=1)
        bumped = svc.repo.put_window(window_id, body.name, body.tz, body.ranges, now)
        gw.audit.append("automation.window.updated", p.as_dict(), None,
                        {"window_id": window_id, "tz": body.tz, "ranges": body.ranges, "policies_bumped": bumped,
                         "approval": approval})
        return window_json(svc.repo.get_window(window_id))  # type: ignore[arg-type]

    def apply_window(p: Principal, params: dict) -> None:
        window_id = params["id"]
        with svc.repo.policy_windows:
            current = svc.repo.get_window(window_id)
            if (current is None or iso(current["updated_at"]) != params["updated_at"]
                    or svc.repo.window_policies(window_id) != params["policies"]):
                raise ApiError(409, "stale_precondition", "the window or its rules changed; request the edit again")
            write_window(p, window_id, WindowBody.model_validate(params["window"]), current, "L2")

    register_change(app, gw, "policy.window.widen", apply_window)

    @app.put("/v1/windows/{window_id}", operation_id="windows.put", tags=tags, response_model=WindowView,
             responses={**QUEUED, **error_responses(401, 403, 409, 422, 429)})
    def put_window(window_id: str, body: WindowBody, request: Request, p: Principal = Depends(principal)):
        policies._owner_only(p, "edit windows")
        if not WINDOW_ID_RE.match(window_id):
            raise ApiError(422, "conflict", "window ids look like win_<lower-case name>")
        try:
            proposed = parse_ranges(body.ranges)
            svc.tz(body.tz)
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        with svc.repo.policy_windows:
            current = svc.repo.get_window(window_id)
            affected = svc.repo.window_policies(window_id)
            if not affected:
                ident = getattr(app.state, "identity", None)
                via = ident.require_step_up(ctx_of(request), p, "edit a maintenance window") if ident else "token"
                return write_window(p, window_id, body, current, via)
            if (current is not None and body.tz == current["tz"]
                    and window_minutes(proposed) <= window_minutes(parse_ranges(current["ranges"]))):
                return write_window(p, window_id, body, current, "none")
            if current is None:
                raise ApiError(409, "conflict", "a standing approval refers to a missing window")
            snapshot = {"id": window_id, "updated_at": iso(current["updated_at"]),
                        "window": body.model_dump(mode="json"), "policies": affected}
        return request_change(app, gw, p, "policy.window.widen", snapshot)
