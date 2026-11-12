# SPDX-License-Identifier: Apache-2.0
"""Contract §12.17: automation rules, runs, schedules, standing approvals, windows, kill switch."""

from __future__ import annotations

import re

from fastapi import Depends, FastAPI, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..automation import AutomationService
from ..automation.cron import parse_ranges
from ..automation.engine import DryRunBody, PauseBody, RuleBody, RulePatch
from ..automation.policies import PolicyBody
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..ledger import iso

WINDOW_ID_RE = re.compile(r"^win_[a-z0-9_]{1,36}$")


class WindowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    tz: str = Field(default="box", max_length=64)
    ranges: list[dict]


def register(app: FastAPI, gw: Gateway) -> None:
    svc = AutomationService(gw)
    policies = svc.policies
    principal = gw.principal
    gw.actions.standing_approvals.append(lambda a: policies.decide(a, svc.paused()))
    gw.events.subscribe(">", svc.on_event)
    gw.on_startup(svc.start)
    gw.on_shutdown(svc.stop)
    app.state.automation = svc

    tags = ["automation"]

    # ---- rules ---------------------------------------------------------------------------------
    @app.get("/v1/automation/rules", tags=tags, responses=error_responses(401))
    def list_rules(_: Principal = Depends(principal)):
        return svc.list()

    @app.post("/v1/automation/rules", tags=tags, status_code=201, responses=error_responses(401, 403, 404, 422))
    def create_rule(body: RuleBody, p: Principal = Depends(principal)):
        return JSONResponse(status_code=201, content=svc.create(p, body))

    @app.get("/v1/automation/rules/{rule_id}", tags=tags, responses=error_responses(401, 404))
    def get_rule(rule_id: str, _: Principal = Depends(principal)):
        return svc.get(rule_id)

    @app.patch("/v1/automation/rules/{rule_id}", tags=tags, responses=error_responses(401, 403, 404, 409, 422))
    def update_rule(rule_id: str, body: RulePatch, p: Principal = Depends(principal)):
        return svc.update(p, rule_id, body)

    @app.post("/v1/automation/rules/{rule_id}/enable", tags=tags, responses=error_responses(401, 403, 404, 409))
    def enable_rule(rule_id: str, p: Principal = Depends(principal)):
        return svc.enable(p, rule_id)

    @app.post("/v1/automation/rules/{rule_id}/disable", tags=tags, responses=error_responses(401, 403, 404))
    def disable_rule(rule_id: str, p: Principal = Depends(principal)):
        return svc.disable(p, rule_id)

    @app.delete("/v1/automation/rules/{rule_id}", tags=tags, status_code=204, responses=error_responses(401, 403, 404))
    def delete_rule(rule_id: str, p: Principal = Depends(principal)):
        svc.delete(p, rule_id)
        return Response(status_code=204)

    @app.post("/v1/automation/rules/{rule_id}/dry-run", tags=tags, responses=error_responses(401, 404, 422))
    def dry_run(rule_id: str, body: DryRunBody | None = None, p: Principal = Depends(principal)):
        return svc.dry_run(p, rule_id, body or DryRunBody())

    @app.get("/v1/automation/runs", tags=tags, responses=error_responses(401, 422))
    def list_runs(rule_id: str | None = None, limit: int = Query(100, ge=1, le=500),
                  _: Principal = Depends(principal)):
        return svc.runs(rule_id, limit)

    @app.get("/v1/automation/schedules", tags=tags, responses=error_responses(401))
    def list_schedules(_: Principal = Depends(principal)):
        return svc.schedules()

    # ---- kill switch ---------------------------------------------------------------------------
    @app.get("/v1/automation/state", tags=tags, responses=error_responses(401))
    def get_state(_: Principal = Depends(principal)):
        return svc.state()

    @app.post("/v1/automation/pause", tags=tags, responses=error_responses(401, 403, 422))
    def pause(body: PauseBody | None = None, p: Principal = Depends(principal)):
        return svc.set_paused(p, True, (body or PauseBody()).reason)

    @app.post("/v1/automation/resume", tags=tags, responses=error_responses(401, 403, 422))
    def resume(body: PauseBody | None = None, p: Principal = Depends(principal)):
        return svc.set_paused(p, False, (body or PauseBody()).reason)

    # ---- standing approvals --------------------------------------------------------------------
    @app.get("/v1/approval-policies", tags=tags, responses=error_responses(401))
    def list_policies(_: Principal = Depends(principal)):
        return [policies.to_json(x) for x in svc.repo.list_policies()]

    @app.post("/v1/approval-policies", tags=tags, status_code=201, responses=error_responses(401, 403, 404, 422))
    def create_policy(body: PolicyBody, p: Principal = Depends(principal)):
        return JSONResponse(status_code=201, content=policies.create(p, body))

    @app.delete("/v1/approval-policies/{policy_id}", tags=tags, status_code=204,
                responses=error_responses(401, 403, 404))
    def delete_policy(policy_id: str, p: Principal = Depends(principal)):
        policies.delete(p, policy_id)
        return Response(status_code=204)

    # ---- maintenance windows -------------------------------------------------------------------
    def window_json(w: dict) -> dict:
        return {"id": w["id"], "name": w["name"], "tz": w["tz"], "ranges": w["ranges"],
                "updated_at": iso(w["updated_at"]), "open_now": policies.window_is_open(w["id"], gw.clock())}

    @app.get("/v1/windows", tags=tags, responses=error_responses(401))
    def list_windows(_: Principal = Depends(principal)):
        return [window_json(w) for w in svc.repo.list_windows()]

    @app.put("/v1/windows/{window_id}", tags=tags, responses=error_responses(401, 403, 422))
    def put_window(window_id: str, body: WindowBody, p: Principal = Depends(principal)):
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "edit windows", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not edit windows")
        if not WINDOW_ID_RE.match(window_id):
            raise ApiError(422, "conflict", "window ids look like win_<lower-case name>")
        try:
            parse_ranges(body.ranges)
            svc.tz(body.tz)
        except ValueError as exc:
            raise ApiError(422, "conflict", str(exc)) from None
        svc.repo.put_window(window_id, body.name, body.tz, body.ranges, gw.clock())
        # §12.17: editing a window a standing approval uses bumps that approval's revision.
        bumped = svc.repo.bump_policies_for_window(window_id)
        gw.audit.append("automation.window.updated", p.as_dict(), None,
                        {"window_id": window_id, "tz": body.tz, "ranges": body.ranges, "policies_bumped": bumped})
        return window_json(svc.repo.get_window(window_id))  # type: ignore[arg-type]
