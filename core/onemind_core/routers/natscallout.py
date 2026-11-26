# SPDX-License-Identifier: Apache-2.0
"""D-029 hybrid: the gateway answers the hub NATS's auth callout for agents (callout.py).

No route of its own: the switch is the installer setting ONEMIND_FABRIC_NATS_CALLOUT (off by default,
D-029 "static config now"), the agent keys are the owner's existing PUT/DELETE /v1/agents/{name}/nats-key,
and "Stop everything" for agents is the existing PUT /v1/agents/kill-switch. While it runs, removing a
key or turning the kill switch on refuses that agent's next connect without a NATS reload.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI

from ..agents_nats import agent_users
from ..backups.jobs import gateway_job_key_path
from ..callout import CalloutResponder, load_keys
from ..context import Gateway
from ..netconf import FabricSettings

ORDER = 343  # after net (270, writes the accounts file with the callout block) and agents (155, kill switch)


def register(app: FastAPI, gw: Gateway) -> None:
    fab = gw.settings.section(FabricSettings)
    if not fab.nats_callout or not fab.nats_service_keys or not gw.bus.url:
        return  # the static accounts file decides alone (D-029 "now")
    task: dict[str, asyncio.Task] = {}

    def stopped() -> bool:
        stop = getattr(app.state, "agent_stop", None)
        return True if stop is None else bool(stop.on)  # no kill switch to read: fail closed

    @gw.on_startup
    async def _start() -> None:
        keys = load_keys(gateway_job_key_path(gw.settings).parent)
        responder = CalloutResponder(gw.bus.url, keys, lambda: agent_users(gw.db), stopped, gw.audit,
                                     ttl_s=fab.nats_callout_ttl_s)
        app.state.nats_callout = responder
        task["run"] = asyncio.create_task(responder.run(), name="nats-callout")

    @gw.on_shutdown
    async def _stop() -> None:
        t = task.pop("run", None)
        if t is not None:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
