# SPDX-License-Identifier: Apache-2.0
"""FD-01 (#498, D-018): `GET /v1/status`, what needs attention on this box, per source (status.py)."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..status import StatusView, build_status

ORDER = 340  # after every route group whose service it reads (it looks them up when asked)

# Registered once, at import (#323). The same read scope as /v1/monitoring/summary.
register_route_scope("GET,HEAD", r"/v1/status", ("monitoring:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    def reader(p: Principal = Depends(gw.principal)) -> Principal:
        # Like backups: owner, adult and agent read; guests and children do not see the box's health.
        if not (p.is_owner or p.role in ("adult", "agent")):
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read status", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not read the box status")
        return p

    @app.get("/v1/status", tags=["status"], operation_id="status.get", response_model=StatusView,
             response_model_by_alias=True, responses=error_responses(401, 403))
    def get_status(_: Principal = Depends(reader)):
        """Alerts, approvals, app health, storage, backups, updates and mesh, each with a state and when it was read.

        A source that cannot be read is `unknown`, never `ok`.
        """
        return build_status(gw, app.state)
