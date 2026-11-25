# SPDX-License-Identifier: Apache-2.0
"""The Network screen's read-only route (NET-UI-01, #239): interfaces, addresses, gateway, DNS, Wi-Fi
signal and listening ports of this box, from the host service (hostnet.py).

Owner only: the answer names every address, MAC and open port of the box. Changing the network
(static IP, Wi-Fi, firewall, with automatic revert) is a later PR and will be an owner-approved action.
`GET /v1/network/firewall` (P-09 part 1) shows the live firewall in plain words, read only.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..hostfw import FirewallView
from ..hostfw import read_view as read_firewall
from ..hostnet import HostNetClient, NetworkView, read_view
from ..identity.scopes import register_route_scope
from ..netconf import NetSettings

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 275

# Owner only (the handler checks too): the row asks for every scope, so no scoped token reads it (#323).
register_route_scope("GET,HEAD", r"/v1/network", ("*",))
register_route_scope("GET,HEAD", r"/v1/network/firewall", ("*",))


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostNetClient(str(cfg.host_socket), cfg.host_timeout_s)

    @app.get("/v1/network", tags=["net"], operation_id="network.view", response_model=NetworkView,
             responses=error_responses(401, 403))
    def network_view(p: Principal = Depends(gw.principal)) -> NetworkView:
        """This box's interfaces, addresses, gateway, DNS, Wi-Fi signal and listening ports (read only).

        `available` is false, with a reason, when the host service cannot be reached: the screen then
        says so instead of showing nothing. Firewall rules are in `/v1/network/firewall`.
        """
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read network", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may see the box's network")
        return read_view(client)

    @app.get("/v1/network/firewall", tags=["net"], operation_id="network.firewall", response_model=FirewallView,
             responses=error_responses(401, 403))
    def network_firewall(p: Principal = Depends(gw.principal)) -> FirewallView:
        """The box's live firewall (nftables), checked and explained in plain words: what is open, and to whom
        (this box, the mesh, the apps on it, the home network, or any address). Read only.

        `exposure` answers the headline question; `open_to_anywhere` is empty on a normal box. `available`
        is false, with a reason, when the host service cannot be reached. Allow rules with automatic revert
        are a later step (P-09 part 2): `editable` is false until then.
        """
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read firewall", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may see the box's firewall")
        return read_firewall(client)
