# SPDX-License-Identifier: Apache-2.0
"""Service cards (#623): GET /v1/system/services, every systemd unit the OS ships with its plain name,
description, docs link, risk, state, memory and version, from the host service (hostservices.py).

Owner only, like the other /v1/system reads: the list shows what runs on the box. Read only: a restart
button is later work and will be an owner-approved action in the ledger.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..hostservices import HostServicesClient, ServicesView, read_view
from ..identity.scopes import register_route_scope
from ..netconf import NetSettings

# Route order in the app and in /openapi.json (routers/__init__.py): right after routers/system.py.
ORDER = 341

# Same scope as /v1/system/controls: minted to no one, so only the owner role (every scope) reads it.
register_route_scope("GET,HEAD", r"/v1/system/services", ("system:admin",))


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostServicesClient(str(cfg.host_socket), cfg.host_timeout_s)

    @app.get("/v1/system/services", tags=["system"], operation_id="system.services.list", response_model=ServicesView,
             responses=error_responses(401, 403))
    def system_services(p: Principal = Depends(gw.principal)) -> ServicesView:
        """Every systemd unit this OS ships, as a service card: plain name and description, docs page,
        risk, restartable flag, dependencies, and systemd's state, memory and version (read only).

        A OneMind unit the image's registry does not list comes back with `known` false. `available` is
        false, with a reason, when the host service cannot be reached: the screen says so instead of
        showing nothing."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read services", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may see the services on this box")
        return read_view(client)
