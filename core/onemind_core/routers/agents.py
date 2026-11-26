# SPDX-License-Identifier: Apache-2.0
"""CORE-SEC-6 (#159): the agent kill switch, GET and PUT /v1/agents/kill-switch (agent_stop.py).
AIG-03 (#167): owner controls for AI agent principals (budget, cancel, resume), owner only.
#627: the owner registers or removes an agent's NATS public key (account AGENTS, agents_nats.py);
cancelling an agent removes its key too, so it is refused on its next NATS connect.

Any signed-in person may read it (an adult or guest should see why the AI went quiet); only the
owner changes it. While it is on, every agent principal is refused at the door, this route included.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agent_principals import MAX_BUDGET_PER_DAY, AgentPrincipals
from ..agents_nats import AgentNatsKeys
from ..agent_stop import AgentStop
from ..apimodels import PrincipalRef
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..taint_store import INPUT_KINDS, MAX_ACCEPT, NAME_RE, AgentInputs, TaintStore

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
register_route_scope("GET,HEAD", r"/v1/agents/[^/]+/inputs", ("users:admin",))
register_route_scope("PUT", r"/v1/agents/[^/]+/inputs", ("*",))  # owner only: it can loosen an agent


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


class AgentInputsView(BaseModel):
    """What an agent can read that the gateway cannot see, and the taint that follows from it."""

    id: str
    external_inputs: list[str] = Field(description="web, email, files, chat (a host with many chats), app, plugin or agent")
    declared: bool = Field(description="false: the list is the default for this kind of principal (every agent and plugin is exposed until the owner declares otherwise)")
    exposed: bool = Field(description="true when external_inputs is not empty")
    permanently_tainted: bool = Field(description="an exposed agent is tainted all the time: no standing approval accepts its requests")
    accept_injection_risk: list[str] = Field(description="write types the owner accepted the risk for; recorded, not yet in effect")
    accept_injection_risk_effective: bool = Field(description="always false until the permission engine reads the flag")
    updated_at: str | None = None
    updated_by: str | None = None


class AgentInputsBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    external_inputs: list[Literal["web", "email", "files", "chat"]] = Field(
        max_length=len(INPUT_KINDS), description="the outside text this agent can read; empty means none (owner only)")
    accept_injection_risk: list[str] = Field(default_factory=list, max_length=MAX_ACCEPT,
                                             description="write action types the owner accepts the injection risk for")


class BudgetBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    budget_per_day: int = Field(ge=0, le=MAX_BUDGET_PER_DAY)


def register(app: FastAPI, gw: Gateway) -> None:
    stop = AgentStop(gw)
    gw.principal_guards.append(stop.refuse_agent_request)
    gw.approval_guards.append(stop.refuse_agent_approval)
    app.state.agent_stop = stop
    principal = gw.principal

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

    def rewrite_accounts() -> None:  # the fabric service writes the one accounts file (routers/net.py)
        fabric = gw.actions.handlers.get("node.join")
        if fabric is not None:
            fabric.write_accounts()

    keys = AgentNatsKeys(gw.db, gw.audit, gw.clock, rewrite_accounts)

    @app.get("/v1/agents", operation_id="agents.list", tags=TAGS,
             responses={200: {"model": list[AgentView]}, **error_responses(401, 403)})
    def list_agents(p: Principal = Depends(principal)):
        return svc.list(p)

    @app.get("/v1/agents/{name}", operation_id="agents.get", tags=TAGS,
             responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def get_agent(name: str, p: Principal = Depends(principal)):
        return svc.get(p, name)

    inputs = AgentInputs(gw.db, gw.audit, gw.catalog, gw.clock)
    app.state.agent_inputs = inputs
    gw.actions.agent_forgotten = inputs.forget
    gw.actions.taint.attach(
        TaintStore(gw.db), inputs.exposure,
        lambda event, pid, data: gw.audit.append(event, {"id": pid, "kind": "agent"}, None, data))

    @app.get("/v1/agents/{name}/inputs", operation_id="agents.inputs.get", tags=TAGS,
             responses={200: {"model": AgentInputsView}, **error_responses(401, 403, 422)},
             openapi_extra={"security": [{"bearer": ["users:admin"]}]})
    def get_inputs(name: str, p: Principal = Depends(principal)):
        if not p.is_owner:  # an agent that could read its own rules and taint could shape requests to fit
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "read agent inputs", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not read what an agent reads")
        return inputs.view(AgentPrincipals.principal_id(name))

    @app.put("/v1/agents/{name}/inputs", operation_id="agents.inputs.set", tags=TAGS,
             responses={200: {"model": AgentInputsView}, **error_responses(401, 403, 422)},
             openapi_extra={"security": [{"bearer": ["*"]}]})
    def set_inputs(name: str, body: AgentInputsBody, request: Request, p: Principal = Depends(principal)):
        # Declaring fewer inputs loosens an agent, and accepting a risk does too: owner only, and a
        # fresh passkey sign-in once passkeys are active, like a standing approval (F-2). Adding an
        # input or removing an accepted risk only tightens, which stays at L0 (D-028).
        pid = AgentPrincipals.principal_id(name)
        ident = getattr(request.app.state, "identity", None)
        via = None  # how the owner proved presence; only asked (and audited) when this loosens
        if (ident is not None and p.is_owner and NAME_RE.fullmatch(pid)
                and inputs.loosens(pid, body.external_inputs, body.accept_injection_risk)):
            via = ident.require_step_up(ctx_of(request), p, "declare what an agent reads")
        return inputs.set(p, pid, body.external_inputs, body.accept_injection_risk, via=via)

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
