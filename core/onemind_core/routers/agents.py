# SPDX-License-Identifier: Apache-2.0
"""CORE-SEC-6 (#159): the agent kill switch, GET and PUT /v1/agents/kill-switch (agent_stop.py).
AIG-03 (#167): owner controls for AI agent principals (budget, cancel, resume), owner only.
#627: the owner registers or removes an agent's NATS public key (account AGENTS, agents_nats.py);
cancelling an agent removes its key too, so it is refused on its next NATS connect.

Any signed-in person may read it (an adult or guest should see why the AI went quiet); only the
owner changes it. While it is on, every agent principal is refused at the door, this route included.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agent_principals import MAX_BUDGET_PER_DAY, AgentPrincipals
from ..agents_nats import AgentNatsKeys, agent_users
from ..agent_stop import AgentStop
from ..apimodels import Action, PrincipalRef
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..natsconf import agent_keys_digest
from ..netconf import FabricSettings
from ..permissions.changes import QUEUED, register_change, request_change, require_owner_passkey
from ..principals import PrincipalRegistry, display_key
from ..taint_store import INPUT_KINDS, MAX_ACCEPT, AgentInputs, TaintStore

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 155  # right after actions: its approval guard must see the actions it refuses

TAGS = ["agents"]
RESUME = "policy.agent.resume"
RAISE_BUDGET = "policy.agent.budget.raise"
SET_NATS_KEY = "policy.agent.nats_key.set"

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
    principal_uid: str | None = Field(default=None, description="the agent's permanent principal id (prn_...); a new one "
                                      "after a token is revoked or its app reinstalled, and standing approvals bind to it")


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

    def rewrite_accounts() -> None:  # the fabric service writes the one accounts file (routers/net.py)
        fabric = gw.actions.handlers.get("node.join")
        if fabric is not None:
            fabric.write_accounts()

    def sync_broker(on: bool, stopped_at: str) -> None:
        rewrite_accounts()
        if (on and gw.settings.section(FabricSettings).nats_accounts_file is not None
                and not app.state.engine.reader.wait_for_agent_cutoff(stopped_at)):
            raise TimeoutError("NATS did not confirm the agent cutoff")

    stop.sync_broker = sync_broker

    @app.get("/v1/agents/kill-switch", operation_id="agents.kill_switch.get", tags=TAGS,
             response_model=KillSwitch, responses=error_responses(401, 403))
    def get_kill_switch(_: Principal = Depends(principal)):
        return stop.state()

    register_change(app, gw, "policy.agents.resume", lambda p, params: stop.set(
        p, False, params["reason"], expected_changed_at=params["changed_at"]))

    @app.put("/v1/agents/kill-switch", operation_id="agents.kill_switch.set", tags=TAGS,
             response_model=KillSwitch, responses={**QUEUED, **error_responses(401, 403, 409, 422, 429, 503)})
    def set_kill_switch(body: KillSwitchBody, p: Principal = Depends(principal)):
        if body.on:
            return stop.set(p, True, body.reason)
        stop.owner_only(p, False)
        current = stop.state()
        if not current["on"]:
            return current
        return request_change(app, gw, p, "policy.agents.resume",
                              {"reason": body.reason, "changed_at": current["changed_at"]})

    # AIG-03 routes come after the kill switch so /v1/agents/kill-switch is not read as an agent name.
    svc = AgentPrincipals(gw.db, gw.actions, gw.audit, gw.clock)

    def broker_status() -> bool | None:
        config = gw.settings.section(FabricSettings)
        if config.nats_accounts_file is None:
            return None
        reader = app.state.engine.reader
        if stop.on:
            marker = stop.state()["changed_at"]
            return False if marker is not None and reader.wait_for_agent_cutoff(marker) else None
        if config.nats_callout:
            return None
        digest = agent_keys_digest(agent_users(gw.db))
        return True if reader.wait_for_agent_keys(digest) else None

    keys = AgentNatsKeys(gw.db, gw.audit, gw.clock, rewrite_accounts, broker_status)

    @app.get("/v1/agents", operation_id="agents.list", tags=TAGS,
             responses={200: {"model": list[AgentView]}, **error_responses(401, 403)})
    def list_agents(p: Principal = Depends(principal)):
        return svc.list(p)

    @app.get("/v1/agents/{name}", operation_id="agents.get", tags=TAGS,
             responses={200: {"model": AgentView}, **error_responses(401, 403, 422)})
    def get_agent(name: str, p: Principal = Depends(principal)):
        return svc.get(p, name)

    # Gateway permissions PR 7: permanent principal ids, and no app takes an agent id a person or the
    # tokens file already holds (it would inherit that agent's standing approvals and audit trail).
    registry = PrincipalRegistry(gw.db, gw.audit, gw.clock,
                                 lambda: {fp.id for _, fp in gw.tokens.entries() if fp.kind == "agent"})
    gw.actions.principals = registry
    registry.listeners.append(keys.principal_retired)

    def no_agent_id_collision(action_type: str, app_id: str) -> None:
        if action_type != "app.install":
            return
        name = f"agent:{app_id}"
        held = registry.collision(name)
        if held is not None:
            gw.audit.append("authz.denied", None, None, {"attempted": f"install {app_id}", "principal_id": name,
                                                         "reason": "agent_id_taken", "held_by": held})
            raise ApiError(409, "conflict", f"the agent id {name!r} is held by {held}; revoke it before installing "
                                            f"this app, so the app never inherits its rules", reason="agent_id_taken")

    gw.actions.id_checks.append(no_agent_id_collision)

    def input_identity(name: str, *, adopt: bool = False) -> str | None:
        record = registry.resolve(name, adopt=adopt)
        return record["uid"] if record is not None else None

    inputs = AgentInputs(gw.db, gw.audit, gw.catalog, gw.clock, input_identity,
                         lambda name: input_identity(name, adopt=True))
    app.state.agent_inputs = inputs
    gw.actions.agent_forgotten = inputs.forget
    gw.actions.taint.attach(
        TaintStore(gw.db), inputs.exposure,
        lambda event, pid, data: gw.audit.append(event, {"id": pid, "kind": "agent"}, None, data))

    def gained_exposure(pid: str) -> None:
        kind = "plugin" if pid.startswith("plugin:") else "agent"
        registry.notify(display_key({"id": pid, "kind": kind}), "became_exposed")

    def apply_inputs(p: Principal, params: dict) -> None:
        pid = params["principal"]
        inputs.set(p, pid, params["external_inputs"], params["accept_injection_risk"],
                   approved_before=params["before"], on_exposure=lambda: gained_exposure(pid))

    register_change(app, gw, "policy.agent_inputs.change", apply_inputs)

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
             responses={200: {"model": AgentInputsView}, **QUEUED, **error_responses(401, 403, 409, 422, 429)},
             openapi_extra={"security": [{"bearer": ["*"]}]})
    def set_inputs(name: str, body: AgentInputsBody, p: Principal = Depends(principal)):
        pid = AgentPrincipals.principal_id(name)
        return inputs.set(p, pid, body.external_inputs, body.accept_injection_risk,
                          request_loosen=lambda params: request_change(app, gw, p, "policy.agent_inputs.change", params),
                          on_exposure=lambda: gained_exposure(pid))

    # Identity retirement and credential replacement take this same lock.
    controls = registry.lifecycle

    def nats_state(pid: str) -> dict:
        key = keys.view(pid)
        return {**svc.control_state(pid), "nkey": key["nkey"], "added_at": key["added_at"]}

    def register_agent_change(kind: str, state: Callable[[str], dict],
                              apply: Callable[[Principal, dict, str], object]) -> None:
        def checked(p: Principal, params: dict) -> object:
            with controls:
                uid = params["before"].get("principal_uid")
                if uid is None or state(params["agent"]) != params["before"]:
                    raise ApiError(409, "conflict", "agent settings changed since the request; file a new one")
                return apply(p, params, uid)

        register_change(app, gw, kind, checked)

    def require_live_agent(before: dict) -> None:
        if before["principal_uid"] is None:
            require_owner_passkey(app)
            raise ApiError(409, "conflict", "the agent needs a live principal before increasing its permissions",
                           reason="unknown_principal")

    register_agent_change(RESUME, svc.control_state, lambda p, params, uid: svc.resume(p, params["agent"], uid=uid))
    register_agent_change(RAISE_BUDGET, svc.control_state,
                          lambda p, params, uid: svc.set_budget(p, params["agent"], params["budget_per_day"], uid=uid))
    register_agent_change(SET_NATS_KEY, nats_state,
                          lambda p, params, uid: keys.set(p, params["agent"], params["nkey"], uid=uid))

    @app.put("/v1/agents/{name}/budget", operation_id="agents.budget.set", tags=TAGS,
             responses={200: {"model": AgentView}, **QUEUED, **error_responses(401, 403, 409, 422, 429)})
    def set_budget(name: str, body: BudgetBody, p: Principal = Depends(principal)):
        svc.owner_only(p, "set an agent budget")
        pid = svc.principal_id(name)
        with controls:
            before = svc.control_state(pid)
            if body.budget_per_day <= before["budget_per_day"]:
                return svc.set_budget(p, pid, body.budget_per_day, uid=before["principal_uid"], tighten=True)
            require_live_agent(before)
        return request_change(app, gw, p, RAISE_BUDGET,
                              {"agent": pid, "budget_per_day": body.budget_per_day, "before": before})

    @app.post("/v1/agents/{name}/cancel", operation_id="agents.cancel", tags=TAGS,
              responses={200: {"model": AgentCancelled}, **error_responses(401, 403, 422, 503)})
    def cancel_agent(name: str, p: Principal = Depends(principal)):
        with controls:
            out = svc.cancel(p, name)
            try:
                keys.remove(None, display_key({"id": name, "kind": "agent"}), why="agent_cancelled")
            except ApiError as exc:  # the cancel stands; a dotted name never had a NATS user
                if exc.status != 422:
                    raise
        return out

    @app.post("/v1/agents/{name}/resume", operation_id="agents.resume", tags=TAGS,
              responses={200: {"model": AgentView}, **QUEUED, **error_responses(401, 403, 409, 422, 429)})
    def resume_agent(name: str, p: Principal = Depends(principal)):
        svc.owner_only(p, "resume an agent")
        pid = svc.principal_id(name)
        with controls:
            before = svc.control_state(pid)
            if before["cancelled_at"] is None:
                return svc.view(pid)
            require_live_agent(before)
        return request_change(app, gw, p, RESUME, {"agent": pid, "before": before})

    @app.get("/v1/agents/{name}/nats-key", operation_id="agents.nats_key.get", tags=TAGS,
             responses={200: {"model": AgentNatsKey}, **error_responses(401, 403, 422)})
    def get_nats_key(name: str, p: Principal = Depends(principal)):
        return keys.get(p, name)

    @app.put("/v1/agents/{name}/nats-key", operation_id="agents.nats_key.set", tags=TAGS,
             response_model=Action, status_code=202, responses={**QUEUED, **error_responses(401, 403, 409, 422, 429)})
    def set_nats_key(name: str, body: NatsKeyBody, p: Principal = Depends(principal),
                     idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        pid = keys.validate_set(p, name, body.nkey)
        with controls:
            previous = gw.actions.repo.get_by_idempotency_key(idem) if idem else None
            # Replay the original reviewed snapshot even if the first request was already approved.
            before = previous.params["before"] if previous and previous.type == SET_NATS_KEY else nats_state(pid)
            if previous is None or previous.type != SET_NATS_KEY:
                require_live_agent(before)
            return request_change(app, gw, p, SET_NATS_KEY, {"agent": pid, "nkey": body.nkey, "before": before},
                                  idempotency_key=idem)

    @app.delete("/v1/agents/{name}/nats-key", operation_id="agents.nats_key.delete", tags=TAGS,
                responses={200: {"model": AgentNatsKey}, **error_responses(401, 403, 422, 503)})
    def delete_nats_key(name: str, p: Principal = Depends(principal)):
        with controls:
            return keys.remove(p, name)
