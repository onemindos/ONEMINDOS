# SPDX-License-Identifier: Apache-2.0
"""Fleet view of OS versions and fleet-staged rollouts (CORE-UPDATE-9, #156; rollouts.py).

`GET /v1/os/fleet` shows which version every machine runs. A rollout is started and resumed only
through the action ledger (`os.rollout.start`, `os.rollout.resume` on `POST /v1/actions`), so an
owner approves each one; `GET /v1/os/rollouts[/{id}]` follows it and the owner may cancel it.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..rollouts import RolloutService

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 335

# Reading versions and rollouts is updates:read (contract §12.6). Cancelling is owner-only:
# updates:admin is minted to no one, so only the owner role (every scope) holds it.
register_route_scope("GET,HEAD", r"/v1/os/fleet", ("updates:read",))
register_route_scope("GET,HEAD", r"/v1/os/rollouts", ("updates:read",))
register_route_scope("GET,HEAD", r"/v1/os/rollouts/[^/]+", ("updates:read",))
register_route_scope("POST", r"/v1/os/rollouts/[^/]+/cancel", ("updates:admin",))


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    svc = RolloutService(gw)
    svc.register()  # os.rollout.start|resume: requested by an owner or an agent, approved by an owner
    app.state.rollouts = svc
    gw.on_startup(svc.start)
    gw.on_shutdown(svc.stop)

    def one(rollout_id: str) -> dict:
        row = svc.repo.get(rollout_id)
        if row is None:
            raise ApiError(404, "not_found", f"There is no rollout {rollout_id}.")
        return row

    @app.get("/v1/os/fleet", tags=["os"], operation_id="os.fleet", responses=error_responses(401, 403))
    def os_fleet(_: Principal = Depends(principal)):
        """Every machine's OS version and update state, and how many machines run each version."""
        return svc.fleet()

    @app.get("/v1/os/rollouts", tags=["os"], operation_id="os.rollouts.list", responses=error_responses(401, 403))
    def os_rollouts(_: Principal = Depends(principal)):
        """Fleet-staged rollouts, newest first."""
        return svc.repo.all()

    @app.get("/v1/os/rollouts/{rollout_id}", tags=["os"], operation_id="os.rollouts.get",
             responses=error_responses(401, 403, 404))
    def os_rollout(rollout_id: str, _: Principal = Depends(principal)):
        """One rollout: its stage, each machine's state, and why it paused."""
        return one(rollout_id)

    @app.post("/v1/os/rollouts/{rollout_id}/cancel", tags=["os"], operation_id="os.rollouts.cancel",
              responses=error_responses(401, 403, 404, 409))
    def os_rollout_cancel(rollout_id: str, p: Principal = Depends(principal)):
        """Stop offering the version to more machines. Owner only; machines already updated stay updated."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "cancel a rollout", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may cancel a rollout")
        return svc.cancel(rollout_id, p)
