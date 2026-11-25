# SPDX-License-Identifier: Apache-2.0
"""The gateway creates the hub's core JetStream streams and KV buckets (issue #601, jetstream.py).

No route of its own: the state is kept on `gw.jetstream` (and `app.state.jetstream`) for the Engine
feed, GET /v1/engine (#619), including each joined node's hub source stream (#747). The work runs in a background task that watches the NATS connection, so
the gateway serves with NATS down and creates the streams again after NATS comes back.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import FastAPI

from ..context import Gateway
from ..jetstream import JetStreamCore
from ..netconf import FabricSettings

ORDER = 339


def register(app: FastAPI, gw: Gateway) -> None:
    fab = gw.settings.section(FabricSettings)
    core = JetStreamCore(fab.jetstream_max_bytes, fab.jetstream_path, clock=gw.clock)
    gw.jetstream = core
    app.state.jetstream = core
    # #747: each approved node gets its hub source stream. routers/net.py (ORDER 270) registers the
    # node.join handler (fabric.FabricService) before this router runs.
    fabric = gw.actions.handlers.get("node.join")
    if fabric is not None:
        fabric.approved_hooks.append(core.want_source)
    task: dict[str, asyncio.Task] = {}

    @gw.on_startup
    async def _start() -> None:
        if core.plan is not None and fabric is not None:
            for node_id in fabric.node_ids():  # nodes approved before this start keep their source
                core.want_source(node_id)
        if core.plan is not None and gw.bus.url:
            task["run"] = asyncio.create_task(core.run(gw.bus), name="jetstream-core")
        elif core.state == "refused":
            gw.audit.append("jetstream.refused", None, None, {"reason": core.reason})

    @gw.on_shutdown
    async def _stop() -> None:
        t = task.pop("run", None)
        if t is not None:
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
