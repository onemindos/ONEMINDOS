# SPDX-License-Identifier: Apache-2.0
"""OS updates (UMB-P05, #142; PD-19): what each node runs, a pending update, and the history.

`GET /v1/os/updates` and `GET /v1/os/updates/history` read what the nodes' heartbeats report about
`internal/update` and RAUC (osupdate.py). Installing is the `os.update.install` action, requested
through `POST /v1/actions` and approved by an owner; the approved version goes to the host service
(hostlink.py), and a box without it reports `engine_unreachable` instead of running.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope
from ..osupdate import OsUpdateService

ORDER = 335

# Registered once, at import (#323): the same facts /v1/nodes shows (version, slots), so the same scope reads them.
register_route_scope("GET,HEAD", r"/v1/os/updates", ("nodes:read",))
register_route_scope("GET,HEAD", r"/v1/os/updates/history", ("nodes:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    svc = OsUpdateService(gw, app.state.hostlink)
    svc.register()
    app.state.osupdate = svc

    @app.get("/v1/os/updates", tags=["os"], operation_id="os.updates.status", responses=error_responses(401))
    def os_updates(_: Principal = Depends(gw.principal)):
        """Per node: running version, booted A/B slot, the update on offer, and whether installing can run."""
        return svc.status()

    @app.get("/v1/os/updates/history", tags=["os"], operation_id="os.updates.history", responses=error_responses(401))
    def os_updates_history(_: Principal = Depends(gw.principal)):
        """Commits and rollbacks the nodes reported, newest first, and the install requests filed."""
        return svc.history()
