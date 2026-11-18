# SPDX-License-Identifier: Apache-2.0
"""CORE-SEC-6 (#159): the agent kill switch, GET and PUT /v1/agents/kill-switch (agent_stop.py).

Any signed-in person may read it (an adult or guest should see why the AI went quiet); only the
owner changes it. While it is on, every agent principal is refused at the door, this route included.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..agent_stop import AgentStop
from ..apimodels import PrincipalRef
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 155  # right after actions: its approval guard must see the actions it refuses

TAGS = ["agents"]


class KillSwitch(BaseModel):
    """The agent kill switch. `on: true` means every AI agent is refused until the owner turns it off."""

    model_config = ConfigDict(extra="allow")
    on: bool
    changed_by: PrincipalRef | None = None
    changed_at: str | None = Field(default=None, description="RFC 3339 time of the last change; null if never changed")
    reason: str | None = None


class KillSwitchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


def register(app: FastAPI, gw: Gateway) -> None:
    stop = AgentStop(gw)
    gw.principal_guards.append(stop.refuse_agent_request)
    gw.approval_guards.append(stop.refuse_agent_approval)
    app.state.agent_stop = stop
    principal = gw.principal
    register_route_scope("GET,HEAD", r"/v1/agents/kill-switch", ("instance:read",))
    # PUT has no scope row: an unknown route needs every scope, so only the owner role reaches it.

    @app.get("/v1/agents/kill-switch", operation_id="agents.kill_switch.get", tags=TAGS,
             response_model=KillSwitch, responses=error_responses(401, 403))
    def get_kill_switch(_: Principal = Depends(principal)):
        return stop.state()

    @app.put("/v1/agents/kill-switch", operation_id="agents.kill_switch.set", tags=TAGS,
             response_model=KillSwitch, responses=error_responses(401, 403, 422))
    def set_kill_switch(body: KillSwitchBody, p: Principal = Depends(principal)):
        return stop.set(p, body.on, body.reason)
