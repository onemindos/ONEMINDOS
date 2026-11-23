# SPDX-License-Identifier: Apache-2.0
"""Bridge intake and status (#610): POST /v1/bridges/{bridge_id}/events and the reads behind
`onemind bridge list|status|resume`. The rules live in core/onemind_core/bridges.py."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request

from ..auth import Principal
from ..bridges import BridgeIntake, BridgeSettings, BridgeStatus, IntakeBatch, IntakeResult, LatestValue
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope

ORDER = 342
TAGS = ["bridges"]

# A plugin token reaches the intake only through plugins/auth.allows_bridge_intake; a person never
# posts events (the service refuses), so the route needs no person scope.
register_route_scope("POST", r"/v1/bridges/[^/]+/events", None)
register_route_scope("GET,HEAD", r"/v1/bridges(/[^/]+(/latest)?)?", ("monitoring:read",))
register_route_scope("POST", r"/v1/bridges/[^/]+/resume", ("actions:approve",))


def register(app: FastAPI, gw: Gateway) -> None:
    svc = BridgeIntake(gw, gw.settings.section(BridgeSettings), gw.clock)
    app.state.bridges = svc

    @app.post("/v1/bridges/{bridge_id}/events", operation_id="bridges.events.post", tags=TAGS,
              response_model=IntakeResult, responses=error_responses(401, 403, 409, 413, 422, 429))
    def post_events(bridge_id: str, body: IntakeBatch, request: Request, p: Principal = Depends(gw.principal)):
        """A bridge posts up to 100 events for its own app id. Each is checked, stamped with the app id
        as source and the provider's licence, deduped by id and revision and published; refused events
        are listed. 429 when over the bridge's rate (nothing taken), 409 while it is paused. Retrying a
        batch is safe: an id and revision already taken counts as a duplicate."""
        return svc.intake(p, getattr(request.state, "identity", None), bridge_id, body)

    @app.get("/v1/bridges", operation_id="bridges.list", tags=TAGS, response_model=list[BridgeStatus],
             responses=error_responses(401, 403))
    def list_bridges(p: Principal = Depends(gw.principal)):
        """Every approved bridge with its limits, state and counters (owners and adults)."""
        return svc.list_bridges(p)

    @app.get("/v1/bridges/{bridge_id}", operation_id="bridges.get", tags=TAGS, response_model=BridgeStatus,
             responses=error_responses(401, 403, 404))
    def get_bridge(bridge_id: str, p: Principal = Depends(gw.principal)):
        return svc.get(p, bridge_id)

    @app.get("/v1/bridges/{bridge_id}/latest", operation_id="bridges.latest", tags=TAGS,
             response_model=list[LatestValue], responses=error_responses(401, 403, 404))
    def latest(bridge_id: str, p: Principal = Depends(gw.principal)):
        """The newest 500 latest-per-entity values. Public data: owners and adults; any other data
        class: owners only (the same check a live subscription makes when it starts)."""
        return svc.latest(p, bridge_id)

    @app.post("/v1/bridges/{bridge_id}/resume", operation_id="bridges.resume", tags=TAGS,
              response_model=BridgeStatus, responses=error_responses(401, 403, 404))
    def resume(bridge_id: str, p: Principal = Depends(gw.principal)):
        """An owner lets a paused bridge in again (it was paused after 20 refused events in 5 minutes)."""
        return svc.resume(p, bridge_id)
