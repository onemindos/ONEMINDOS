# SPDX-License-Identifier: Apache-2.0
"""AIG-03 (#167): owner controls for AI agent principals (budget, cancel, resume). Owner only."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field

from ..agent_principals import MAX_BUDGET_PER_DAY, AgentPrincipals
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope

ORDER = 160
register_route_scope("GET,HEAD,PUT,POST", r"/v1/agents(/.*)?", ("users:admin",))


class AgentView(BaseModel):
    id: str
    budget_per_day: int
    used_24h: int
    pending_approvals: int
    cancelled: bool
    cancelled_at: str | None = None


class AgentCancelled(AgentView):
    requests_cancelled: int
    tokens_revoked: int


class BudgetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    budget_per_day: int = Field(ge=0, le=MAX_BUDGET_PER_DAY)


def register(app: FastAPI, gw: Gateway) -> None:
    svc = AgentPrincipals(gw.db, gw.actions, gw.audit, gw.clock)
    principal = gw.principal
    tags = ["agents"]

    @app.get("/v1/agents", operation_id="agents.list", tags=tags,
             responses={200: {"model": list[AgentView]}, **error_responses(401, 403)})
    def list_agents(p: Principal = Depends(principal)):
        return svc.list(p)

    @app.get("/v1/agents/{name}", operation_id="agents.get", tags=tags,
             responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def get_agent(name: str, p: Principal = Depends(principal)):
        return svc.get(p, name)

    @app.put("/v1/agents/{name}/budget", operation_id="agents.budget.set", tags=tags,
             responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def set_budget(name: str, body: BudgetBody, p: Principal = Depends(principal)):
        return svc.set_budget(p, name, body.budget_per_day)

    @app.post("/v1/agents/{name}/cancel", operation_id="agents.cancel", tags=tags,
              responses={200: {"model": AgentCancelled}, **error_responses(401, 403, 422)})
    def cancel_agent(name: str, p: Principal = Depends(principal)):
        return svc.cancel(p, name)

    @app.post("/v1/agents/{name}/resume", operation_id="agents.resume", tags=tags,
              responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def resume_agent(name: str, p: Principal = Depends(principal)):
        return svc.resume(p, name)
