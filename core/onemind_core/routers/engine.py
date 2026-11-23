# SPDX-License-Identifier: Apache-2.0
"""GET /v1/engine: the Engine feed (issue #619, engine/), read by Settings > Engine and `onemind nats status`.

Read-only: the gateway asks the hub nats-server's loopback monitor (127.0.0.1:8222) at most once
every 2 seconds and answers from that, the JetStream state of #601 (`gw.jetstream`) and the
heartbeat registry. The route needs `monitoring:read` (a child or teen has none) or, for a machine,
`nodes:report`; the scope rules are in engine/feed.py. With NATS down it still answers 200, with
`monitor.state` down: the feed exists to show that.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..engine import EngineView, MonitorReader, scope_for, view
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope

ORDER = 340   # after jetstream (339), whose state this reads

SCOPES = ("monitoring:read", "nodes:report")
register_route_scope("GET,HEAD", r"/v1/engine", SCOPES)


class EngineFeed:
    """Kept on app.state.engine; `reader` can be pointed at another loopback monitor (tests)."""

    def __init__(self, gw: Gateway, reader: MonitorReader):
        self.gw, self.reader = gw, reader

    def answer(self, p: Principal) -> dict:
        scope = scope_for(p)
        if scope is None:
            self.gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read the engine feed",
                                                                     "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "the engine feed is for people and machines on this box")
        core = self.gw.jetstream.view() if self.gw.jetstream is not None else None
        return view(self.reader.read(), scope, jetstream=core, nodes=self.gw.registry.list(),
                    hub_node_id=self.gw.settings.node_id)


def register(app: FastAPI, gw: Gateway) -> None:
    feed = EngineFeed(gw, MonitorReader(clock=gw.clock))
    app.state.engine = feed

    @gw.on_shutdown
    def _close() -> None:
        feed.reader.close()

    @app.get("/v1/engine", operation_id="engine.get", tags=["engine"],
             responses={200: {"model": EngineView}, **error_responses(401, 403)},
             openapi_extra={"security": [{"bearer": list(SCOPES)}]})
    def engine(p: Principal = Depends(gw.principal)):
        """Connections per account, leaf links and outbox lag per machine, JetStream used against its cap,
        slow consumers. Cut to the caller: the owner sees all, a machine its own, everyone else a summary."""
        return feed.answer(p)

    build = app.openapi

    def openapi() -> dict:
        doc = build()
        # The bearer token every signed-in route takes (contract §3); named so this route can list its scopes.
        schemes = doc.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes.setdefault("bearer", {"type": "http", "scheme": "bearer",
                                      "description": "A OneMind API token or session (contract §3, §12.6)"})
        return doc

    app.openapi = openapi  # type: ignore[method-assign]
