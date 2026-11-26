# SPDX-License-Identifier: Apache-2.0
"""D-029 N7: the gateway keeps every joined machine's signed stop and revoke snapshot current
(fabric_policy.py). GET /v1/fabric/policy shows it (read-only: the switches are the existing motion
lockout, PUT /v1/physical/lockout, and agent kill switch, PUT /v1/agents/kill-switch); `onemind fabric
policy` prints it. Jobs signed for machines carry its epoch (rollouts.py)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import Depends, FastAPI
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..backups.jobs import gateway_job_key_path, lazy_job_key
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope
from ..fabric_policy import EpochStore, PolicyPublisher, PolicyState

log = logging.getLogger("onemind.policy")

ORDER = 344  # after net (270: the node list), physical and agents (the switches) and jetstream (339)

SCOPES = ("nodes:read",)  # like GET /v1/fabric and /v1/nodes: what every machine is told
register_route_scope("GET,HEAD", r"/v1/fabric/policy", SCOPES)


class PolicyStop(BaseModel):
    model_config = ConfigDict(extra="forbid")
    motion_lockout: bool
    agents: bool


class FabricPolicy(BaseModel):
    """What every joined machine enforces on its own, also while cut off from the hub."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_: str = Field(alias="schema")
    epoch: int
    stop: PolicyStop
    revoked_kids: list[str]
    allowed_kinds: list[str] | None
    published: dict[str, int]
    error: str | None


def register(app: FastAPI, gw: Gateway) -> None:
    def state() -> PolicyState:
        lockout = getattr(app.state, "motion_lockout", None)
        stop = getattr(app.state, "agent_stop", None)
        # A switch that cannot be read counts as on: the snapshot only ever adds a "no".
        return PolicyState(motion_lockout=True if lockout is None else bool(lockout.locked()),
                           agents_stopped=True if stop is None else bool(stop.on))

    def node_ids() -> list[str]:
        fabric = gw.actions.handlers.get("node.join")
        return list(fabric.node_ids()) if fabric is not None else []

    key_path = gateway_job_key_path(gw.settings)
    pub = PolicyPublisher(key=lazy_job_key(key_path), store=EpochStore(key_path.parent / "policy-epoch.json"),
                          state=state, node_ids=node_ids, clock=gw.clock)
    gw.policy = pub
    app.state.fabric_policy = pub
    task: dict[str, asyncio.Task] = {}

    def push(on: bool) -> None:
        """A stop switch changed: the hub holds the new notes before the switch call returns (#1210)."""
        if not gw.bus.url:
            return  # no NATS on this box: no machine to tell
        if pub.push_now(gw.bus):
            return
        log.error("stop switch changed but the machines' notes are not on the hub yet (%s); retrying", pub.error)
        gw.audit.append("fabric.policy.push_failed", None, None, {"stop": on, "error": pub.error or None})
        gw.events.publish_event("fabric", "policy.not_delivered", {"stop": on, "error": pub.error or None},
                                severity="warning", resource={"kind": "fabric", "id": "policy"},
                                dedupe_key="fabric:policy:not_delivered")

    # The two stop switches (routers/physical.py and routers/agents.py, both ORDER 155, registered first).
    for switch in (getattr(app.state, "motion_lockout", None), getattr(app.state, "agent_stop", None)):
        if switch is not None:
            switch.listeners.append(push)

    @gw.on_startup
    async def _start() -> None:
        if gw.bus.url:
            task["run"] = asyncio.create_task(pub.run(gw.bus), name="fabric-policy")

    @gw.on_shutdown
    async def _stop() -> None:
        t = task.pop("run", None)
        if t is not None:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

    @app.get("/v1/fabric/policy", operation_id="fabric.policy", tags=["fabric"],
             responses={200: {"model": FabricPolicy}, **error_responses(401, 403)},
             openapi_extra={"security": [{"bearer": list(SCOPES)}]})
    def fabric_policy(_: Principal = Depends(gw.principal)):
        """The stop and revoke snapshot every machine keeps: the epoch, the stop switches, revoked job keys,
        and which machine has the newest one on the hub."""
        return pub.view()
