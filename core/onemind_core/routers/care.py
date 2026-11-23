# SPDX-License-Identifier: Apache-2.0
"""FD-08: owner check-up in Settings > Care."""
from fastapi import Depends, FastAPI

from ..auth import Principal
from ..care import CareCheck, checkup
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope

ORDER = 341
register_route_scope("GET,HEAD", r"/v1/care/checkup", ("monitoring:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    @app.get("/v1/care/checkup", tags=["care"], operation_id="care.checkup",
             response_model=list[CareCheck], responses=error_responses(401, 403))
    def get_checkup(p: Principal = Depends(gw.principal)):
        """Inspect seven sources of box drift without making any changes."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read care", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "Only the owner may inspect the box check-up.")
        return checkup(gw, app.state)
