# SPDX-License-Identifier: Apache-2.0
"""CORE-SEC-6 (#159): the agent kill switch, GET and PUT /v1/agents/kill-switch (agent_stop.py).
AIG-03 (#167): owner controls for AI agent principals (budget, cancel, resume), owner only.
#627: the owner registers or removes an agent's NATS public key (account AGENTS, agents_nats.py);
cancelling an agent removes its key too, so it is refused on its next NATS connect.

Any signed-in person may read it (an adult or guest should see why the AI went quiet); only the
owner changes it. While it is on, every agent principal is refused at the door, this route included.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agent_principals import MAX_BUDGET_PER_DAY, AgentPrincipals
from ..agents_nats import AgentNatsKeys
from ..agent_stop import AgentStop
from ..apimodels import PrincipalRef
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 155  # right after actions: its approval guard must see the actions it refuses

TAGS = ["agents"]

# Scope rows are registered once, at import (#323): register() runs per app and must not grow the
# global registry. PUT is owner only: its row asks for every scope. Later rows override earlier
# ones (scopes.required_scopes), so the AIG-03 catch-all comes first and the kill-switch rows win.
register_route_scope("GET,HEAD,PUT,POST", r"/v1/agents(/.*)?", ("users:admin",))
register_route_scope("GET,HEAD", r"/v1/agents/kill-switch", ("instance:read",))
register_route_scope("PUT", r"/v1/agents/kill-switch", ("*",))
register_route_scope("DELETE", r"/v1/agents/[^/]+/nats-key", ("users:admin",))


class KillSwitch(BaseModel):
    """The agent kill switch. `on: true` means every AI agent is refused until the owner turns it off."""

    model_config = ConfigDict(extra="allow")
    on: bool
    changed_by: PrincipalRef | None = None
    changed_at: str | None = Field(default=None, description="RFC 3339 time of the last change; null if never changed")
    reason: str | None = None


class KillSwitchBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    # JsonBody: JSON true/false only; lax mode took 0 and 1 (found by api-fuzz).
    on: bool = Field(description="true stops every AI agent; false lets them work again")
    reason: str | None = Field(default=None, description="Why, for the audit record (at most 500 characters)")

    # Checked here rather than as maxLength in the schema: a constrained `reason` would renumber the
    # shared generated `Reason` type in the Python SDK for every other route.
    @field_validator("reason")
    @classmethod
    def _short(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 500:
            raise ValueError("reason is at most 500 characters")
        return v


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


class AgentNatsKey(BaseModel):
    """An agent's NATS user in account AGENTS (#627). `nkey` null: the agent has no NATS user."""

    id: str
    account: str
    nkey: str | None = None
    added_at: str | None = None
    inbox_prefix: str
    subjects: list[str] = Field(description="what the agent may publish and subscribe on, besides replies")
    request_subject: str | None = None
    tools: list[str] = Field(description="always empty: talking on the bus grants no tool")


class NatsKeyBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    nkey: str = Field(description="the agent's NATS user public key (U...); the seed stays with the agent")


class BudgetBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    budget_per_day: int = Field(ge=0, le=MAX_BUDGET_PER_DAY)


def register(app: FastAPI, gw: Gateway) -> None:
    stop = AgentStop(gw)
    gw.principal_guards.append(stop.refuse_agent_request)
    gw.approval_guards.append(stop.refuse_agent_approval)
    app.state.agent_stop = stop
    principal = gw.principal

    def rewrite_accounts() -> None:  # the fabric service writes the one accounts file (routers/net.py)
        fabric = gw.actions.handlers.get("node.join")
        if fabric is not None:
            fabric.write_accounts()

    # D-029: "Stop everything" also cuts agents already on the bus: the file loses AGENTS, NATS reloads.
    stop.listeners.append(lambda _on: rewrite_accounts())

    @app.get("/v1/agents/kill-switch", operation_id="agents.kill_switch.get", tags=TAGS,
             response_model=KillSwitch, responses=error_responses(401, 403))
    def get_kill_switch(_: Principal = Depends(principal)):
        return stop.state()

    @app.put("/v1/agents/kill-switch", operation_id="agents.kill_switch.set", tags=TAGS,
             response_model=KillSwitch, responses=error_responses(401, 403, 422))
    def set_kill_switch(body: KillSwitchBody, p: Principal = Depends(principal)):
        return stop.set(p, body.on, body.reason)

    # AIG-03 routes come after the kill switch so /v1/agents/kill-switch is not read as an agent name.
    svc = AgentPrincipals(gw.db, gw.actions, gw.audit, gw.clock)

    keys = AgentNatsKeys(gw.db, gw.audit, gw.clock, rewrite_accounts)

    @app.get("/v1/agents", operation_id="agents.list", tags=TAGS,
             responses={200: {"model": list[AgentView]}, **error_responses(401, 403)})
    def list_agents(p: Principal = Depends(principal)):
        return svc.list(p)

    @app.get("/v1/agents/{name}", operation_id="agents.get", tags=TAGS,
             responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def get_agent(name: str, p: Principal = Depends(principal)):
        return svc.get(p, name)

    @app.put("/v1/agents/{name}/budget", operation_id="agents.budget.set", tags=TAGS,
             responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def set_budget(name: str, body: BudgetBody, p: Principal = Depends(principal)):
        return svc.set_budget(p, name, body.budget_per_day)

    @app.post("/v1/agents/{name}/cancel", operation_id="agents.cancel", tags=TAGS,
              responses={200: {"model": AgentCancelled}, **error_responses(401, 403, 422, 503)})
    def cancel_agent(name: str, p: Principal = Depends(principal)):
        out = svc.cancel(p, name)
        if name.startswith("agent:"):
            try:
                keys.remove(None, name, why="agent_cancelled")
            except ApiError as exc:  # the cancel stands; a dotted name never had a NATS user
                if exc.status != 422:
                    raise
        return out

    @app.post("/v1/agents/{name}/resume", operation_id="agents.resume", tags=TAGS,
              responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def resume_agent(name: str, p: Principal = Depends(principal)):
        return svc.resume(p, name)

    @app.get("/v1/agents/{name}/nats-key", operation_id="agents.nats_key.get", tags=TAGS,
             responses={200: {"model": AgentNatsKey}, **error_responses(401, 403, 422)})
    def get_nats_key(name: str, p: Principal = Depends(principal)):
        return keys.get(p, name)

    @app.put("/v1/agents/{name}/nats-key", operation_id="agents.nats_key.set", tags=TAGS,
             responses={200: {"model": AgentNatsKey}, **error_responses(401, 403, 422, 503)})
    def set_nats_key(name: str, body: NatsKeyBody, p: Principal = Depends(principal)):
        return keys.set(p, name, body.nkey)

    @app.delete("/v1/agents/{name}/nats-key", operation_id="agents.nats_key.delete", tags=TAGS,
                responses={200: {"model": AgentNatsKey}, **error_responses(401, 403, 422, 503)})
    def delete_nats_key(name: str, p: Principal = Depends(principal)):
        return keys.remove(p, name)
