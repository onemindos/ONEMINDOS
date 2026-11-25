# SPDX-License-Identifier: Apache-2.0
"""The Network screen's routes: the read (NET-UI-01, #239: interfaces, addresses, gateway, DNS, Wi-Fi signal
and listening ports of this box, from the host service, hostnet.py) and the wired change (P-08, netchange.py):
`PUT /v1/network/{iface}` files an owner action (static IP, DNS, or back to DHCP) and
`POST /v1/network/{iface}/confirm` keeps it after the owner reached the new address.

Owner only: the answer names every address, MAC and open port of the box. Wi-Fi and firewall changes (with the
same automatic revert) come later.
"""

from __future__ import annotations

import re

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..hostnet import HostNetClient, NetworkView, read_view
from ..identity.scopes import register_route_scope
from ..netchange import ACTION, IFACE_RE, HostNetChangeClient, NetChangeService, NetworkConfigBody, NetworkConfirm
from ..netconf import NetSettings

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 275

# Owner only (the handler checks too): the row asks for every scope, so no scoped token reads it (#323).
register_route_scope("GET,HEAD", r"/v1/network", ("*",))
register_route_scope("PUT", r"/v1/network/[^/]+", ("*",))
register_route_scope("POST", r"/v1/network/[^/]+/confirm", ("*",))


def passkey_step_up(gw: Gateway):
    """Approval guard: a network change is approved only with the owner's passkey, whatever
    `require_passkey_approval` says (D-027: a change of the box's address and DNS is security related). The
    identity guard (registered earlier, so it runs first) verifies the assertion: signed over this action, by an
    active owner. Same rule as a service restart (routers/services.py) and a factory reset."""

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        if action.get("type") != ACTION:
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if body.get("webauthn") is None or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": ACTION, "reason": "network_change_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "a network change needs your passkey: register one, then approve with it",
                           reason="step_up_required")

    return guard


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostNetClient(str(cfg.host_socket), cfg.host_timeout_s)
    svc = NetChangeService(gw, client, HostNetChangeClient(cfg.host_socket, cfg.change_timeout_s))
    svc.register()
    gw.approval_guards.append(passkey_step_up(gw))
    app.state.netchange = svc

    def owner(p: Principal, what: str) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may see or change the box's network")

    @app.get("/v1/network", tags=["net"], operation_id="network.view", response_model=NetworkView,
             responses=error_responses(401, 403))
    def network_view(p: Principal = Depends(gw.principal)) -> NetworkView:
        """This box's interfaces, addresses, gateway, DNS, Wi-Fi signal and listening ports (read only).

        `available` is false, with a reason, when the host service cannot be reached: the screen then
        says so instead of showing nothing. Firewall rules are not part of this view yet.
        """
        owner(p, "read network")
        view = read_view(client)
        if view.available:
            view.changes = svc.changes()
        return view

    def iface_name(iface: str) -> str:
        if not re.fullmatch(IFACE_RE, iface):
            raise ApiError(404, "not_found", "this box has no network interface with that name")
        return iface

    @app.put("/v1/network/{iface}", tags=["net"], operation_id="network.configure", status_code=202, response_model=Action,
             responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 404, 409, 422, 429)})
    def network_configure(iface: str, body: NetworkConfigBody, p: Principal = Depends(gw.principal)):
        """Ask to give a wired interface a fixed IPv4 address and DNS, or to go back to DHCP. Nothing changes yet.

        The request waits for an owner, who approves it with a passkey. After approval the box applies it
        and the owner has `rollback_seconds` (default 120) to open the box at the new address and confirm
        (`POST /v1/network/{iface}/confirm`); without that the old settings come back by themselves.

        409 `host_unavailable` while the box cannot change its network, `unknown_interface` / `not_wired` for an
        interface that is not a cable, `change_pending` while an earlier change waits for confirmation (nothing
        is filed in these cases); 422 for an address, gateway or DNS no network can use."""
        owner(p, "change network")
        if not p.can_request_actions:
            raise ApiError(403, "permission_denied", "this token cannot request actions")
        body_out, created = svc.request(p, iface_name(iface), body)
        return JSONResponse(status_code=202 if created else 200, content=body_out,
                            headers={"Location": f"/v1/actions/{body_out['id']}"})

    @app.post("/v1/network/{iface}/confirm", tags=["net"], operation_id="network.confirm", response_model=NetworkConfirm,
              responses=error_responses(401, 403, 404, 409))
    def network_confirm(iface: str, p: Principal = Depends(gw.principal)) -> NetworkConfirm:
        """Keep the pending change on this interface: you reached the box at its new address.

        409 `no_pending_change` when nothing waits for confirmation (it may have rolled back already)."""
        owner(p, "confirm network change")
        return svc.confirm(p, iface_name(iface))
