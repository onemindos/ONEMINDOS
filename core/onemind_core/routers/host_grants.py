# SPDX-License-Identifier: Apache-2.0
"""Host grants (#186 E2): request one, list them, revoke one. Approval is POST /v1/actions/{id}/approve."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import Depends, FastAPI, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..apimodels import Action
from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import error_responses
from ..hostgrants.broker import HostGrantBroker
from ..identity.scopes import register_route_scope

ORDER = 282
register_route_scope("GET,HEAD", r"/v1/host-grants", ("actions:approve",))
register_route_scope("POST", r"/v1/host-grants/requests", ("actions:request:host.grant",))
register_route_scope("POST", r"/v1/host-grants/[^/]+/revoke", ("actions:approve",))


class HostGrant(BaseModel):
    id: str
    app_id: str
    kind: Literal["device", "gpu", "host-network", "realtime"]
    device_class: str | None
    path: str | None
    reason: str
    active: bool
    granted_at: datetime
    approved_by: str
    action_id: str
    revoked_at: datetime | None
    revoked_by: str | None


class HostGrants(BaseModel):
    grants: list[HostGrant]


class HostGrantRequest(BaseModel):
    """One thing for one app. The owner sees exactly these fields on the approval card."""

    model_config = ConfigDict(extra="forbid")
    app_id: str = Field(pattern=APP_ID_RE.pattern, max_length=59)
    kind: Literal["device", "gpu", "host-network", "realtime"]
    device_class: Literal["usb-serial", "usb", "video"] | None = None
    path: str | None = Field(default=None, min_length=1, max_length=220)
    reason: str = Field(min_length=1, max_length=300)
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime


def register(app: FastAPI, gw: Gateway) -> None:
    broker = HostGrantBroker(gw)
    app.state.host_grants = broker

    @app.get("/v1/host-grants", operation_id="plugins.host_grants.list", tags=["plugins"],
             response_model=HostGrants, responses=error_responses(401, 403, 422))
    def grants(app_id: str | None = Query(default=None, pattern=APP_ID_RE.pattern, max_length=59),
               p: Principal = Depends(gw.principal)):
        return {"grants": broker.grants(p, app_id)}

    @app.post("/v1/host-grants/requests", operation_id="plugins.host_grants.request", tags=["plugins"],
              response_model=Action, status_code=202, responses=error_responses(401, 403, 404, 409, 422))
    def request(body: HostGrantRequest, p: Principal = Depends(gw.principal)):
        return broker.request(p, body)

    @app.post("/v1/host-grants/{grant_id}/revoke", operation_id="plugins.host_grants.revoke", tags=["plugins"],
              response_model=HostGrant, responses=error_responses(401, 403, 404))
    def revoke(grant_id: str, p: Principal = Depends(gw.principal)):
        return broker.revoke(p, grant_id)
