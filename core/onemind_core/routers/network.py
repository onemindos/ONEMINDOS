# SPDX-License-Identifier: Apache-2.0
"""The Network screen's routes: the read (NET-UI-01, #239: interfaces, addresses, gateway, DNS, Wi-Fi signal
and listening ports of this box, from the host service, hostnet.py) and the wired change (P-08, netchange.py):
`PUT /v1/network/{iface}` files an owner action (static IP, DNS, or back to DHCP) and
`POST /v1/network/{iface}/confirm` keeps an identified change after the owner verifies reachability.

Owner only: the answer names every address, MAC and open port of the box. Wi-Fi changes (with the same
automatic revert) come later.
`GET /v1/network/firewall` (P-09 part 1) shows the live firewall in plain words, read only.

P-09 part 2, allow rules with automatic revert (fwallow.py):
- `POST /v1/network/firewall/allow` files a `firewall.allow` action for one port from the home network (`lan`)
  or the mesh. An owner or an agent may ask; only an owner approves, with a passkey. The rule then starts
  pending and the box removes it again after `ttl_seconds` unless it is confirmed.
- `POST /v1/network/firewall/allow/{id}/confirm` keeps a pending rule (owner only, audited).
- `DELETE /v1/network/firewall/allow/{id}` takes a rule away (owner only, audited; removing exposure needs no approval).
"""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..fwallow import (ACTION as ALLOW_ACTION, RULE_ID_RE, AllowParams, AllowRequest, HostAllowClient, HostAllowError, host_problem,
                       phrase, run_allow)
from ..hostfw import FirewallView
from ..hostfw import read_view as read_firewall
from ..hostnet import HostNetClient, NetworkView, read_view
from ..identity.scopes import register_route_scope
from ..netchange import (ACTION as NET_ACTION, IFACE_RE, HostNetChangeClient, NetChangeService, NetworkConfigBody,
                         NetworkConfirm, NetworkConfirmBody)
from ..netconf import NetSettings

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 275

# Owner only (the handler checks too): the row asks for every scope, so no scoped token reads it (#323).
register_route_scope("GET,HEAD", r"/v1/network", ("*",))
register_route_scope("GET,HEAD", r"/v1/network/firewall", ("*",))
register_route_scope("POST", r"/v1/network/firewall/allow", ("actions:request",))
register_route_scope("POST", r"/v1/network/firewall/allow/[^/]+/confirm", ("*",))
register_route_scope("DELETE", r"/v1/network/firewall/allow/[^/]+", ("*",))
register_route_scope("PUT", r"/v1/network/[^/]+", ("*",))
register_route_scope("POST", r"/v1/network/[^/]+/confirm", ("*",))

REQUESTERS = frozenset({"agent"})  # besides the owner; an agent asks, only an owner approves
REQUEST_TTL = timedelta(hours=24)


def network_step_up(gw: Gateway):
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
        if action.get("type") != NET_ACTION:
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if body.get("webauthn") is None or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": NET_ACTION, "reason": "network_change_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "a network change needs your passkey: register one, then approve with it",
                           reason="step_up_required")

    return guard


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostNetClient(str(cfg.host_socket), cfg.host_timeout_s)
    allow_client = HostAllowClient(cfg.host_socket, cfg.host_timeout_s)

    def deny(p: Principal, what: str, msg: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", msg)

    def allow_problem(proto: str, port: int, scope: str) -> str | None:
        """Why this rule cannot be opened now, read from the box each time; None when it can."""
        view = read_firewall(client)
        if not view.available:
            return view.message or "the box's firewall cannot be read"
        if view.exposure == "no_firewall" or view.allow is None or not view.allow.supported:
            return (view.allow.reason if view.allow and view.allow.reason else None) or "this box cannot take allow rules: its firewall is not loaded or the OS is too old"
        if any(r.proto == proto and r.port == port and r.scope == scope for r in view.allow.rules):
            return f"{phrase(proto, port, scope)} is already allowed"
        return None

    def card_reason(req: AllowRequest) -> str:
        """The approval card shows the reason first, so it always says what would be opened, then the asker's words."""
        what = f"Open {phrase(req.proto, req.port, req.scope)}"
        return f"{what}: {req.reason}"[:500] if req.reason else what

    def recheck(a) -> str | None:
        prm = a.params or {}
        return allow_problem(prm.get("proto", ""), prm.get("port", 0), prm.get("scope", ""))

    def run(a, finish) -> None:
        finish(run_allow(allow_client, a.id, a.params or {}))

    gw.actions.register_type(ALLOW_ACTION, FeatureAction("actuate", run, REQUESTERS, check=recheck))
    gw.approval_guards.append(firewall_step_up(gw))

    svc = NetChangeService(gw, client, HostNetChangeClient(cfg.host_socket, cfg.change_timeout_s, cfg.host_timeout_s))
    svc.register()
    gw.approval_guards.append(network_step_up(gw))
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
        says so instead of showing nothing. Firewall rules are in `/v1/network/firewall`.
        """
        owner(p, "read network")
        view = read_view(client)
        if view.available:
            view.changes = svc.changes()
        return view

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

    @app.post("/v1/network/firewall/allow", tags=["net"], operation_id="network.firewall.allow", status_code=202, response_model=Action,
              responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 409, 422, 429)})
    def network_firewall_allow(req: AllowRequest, p: Principal = Depends(gw.principal),
                               idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Ask to open one port to the home network (`lan`) or your mesh (`mesh`). The internet is not an option.

        It waits for the owner, who approves it with a passkey; the response is the action, whose id is the
        approval to look for. After approval the rule is *pending*: the box removes it again after
        `ttl_seconds` (see the firewall view) unless the owner confirms it. An agent may ask, never approve.

        409 when the box cannot take the rule now (host unreachable, firewall not loaded, image too old, or the
        same rule already exists); nothing is filed then."""
        if not p.can_request_actions or not (p.is_owner or p.kind in REQUESTERS):
            raise deny(p, f"request {ALLOW_ACTION}", "only an owner or an agent may ask to open a port")
        problem = allow_problem(req.proto, req.port, req.scope)
        if problem is not None:
            raise ApiError(409, "conflict", problem, reason="firewall_unavailable")
        body, created = gw.actions.request_feature(
            p, ALLOW_ACTION, AllowParams(proto=req.proto, port=req.port, scope=req.scope).model_dump(),
            idempotency_key=idem or req.idempotency_key or f"firewall-allow:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=card_reason(req), pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body, headers={"Location": f"/v1/actions/{body['id']}"})

    def owner_call(p: Principal, rule_id: str, method: str, suffix: str, what: str):
        if not p.is_owner:
            raise deny(p, what, f"only an owner may {what}")
        if not RULE_ID_RE.fullmatch(rule_id):
            raise ApiError(404, "not_found", "no such allow rule")
        try:
            status, doc = allow_client.call(method, f"/v1/firewall/allow/{rule_id}{suffix}")
        except HostAllowError as exc:
            raise ApiError(409, "conflict", exc.message, reason=exc.reason) from None
        if status == 404:
            raise ApiError(404, "not_found", "there is no such allow rule (a rule that was not confirmed in time is already gone)")
        if status != 200:
            reason, msg = host_problem(status, doc)
            raise ApiError(409, "conflict", msg, reason=reason)
        return doc

    @app.post("/v1/network/firewall/allow/{rule_id}/confirm", tags=["net"], operation_id="network.firewall.allow.confirm",
              responses=error_responses(401, 403, 404, 409))
    def network_firewall_allow_confirm(rule_id: str, p: Principal = Depends(gw.principal)):
        """Keep a pending allow rule for good. Owner only and audited. A rule nobody confirmed in time is already gone: 404.

        Deliberately no step-up here: the passkey approval of the request came first, this only keeps what the owner
        already approved open (it widens nothing), and the caller must be an owner."""
        doc = owner_call(p, rule_id, "POST", "/confirm", "confirm a firewall rule")
        gw.audit.append("firewall.allow.confirmed", p.as_dict(), None, {"rule_id": rule_id, "proto": doc.get("proto"), "port": doc.get("port"), "scope": doc.get("scope")})
        return {"id": rule_id, "state": "confirmed"}

    @app.delete("/v1/network/firewall/allow/{rule_id}", tags=["net"], operation_id="network.firewall.allow.remove",
                responses=error_responses(401, 403, 404, 409))
    def network_firewall_allow_remove(rule_id: str, p: Principal = Depends(gw.principal)):
        """Take an allow rule away, pending or confirmed. Owner only and audited; removing exposure needs no approval."""
        owner_call(p, rule_id, "DELETE", "", "remove a firewall rule")
        gw.audit.append("firewall.allow.removed", p.as_dict(), None, {"rule_id": rule_id})
        return {"id": rule_id, "removed": True}

    def iface_name(iface: str) -> str:
        if not re.fullmatch(IFACE_RE, iface):
            raise ApiError(404, "not_found", "this box has no network interface with that name")
        return iface

    @app.put("/v1/network/{iface}", tags=["net"], operation_id="network.configure", status_code=202, response_model=Action,
             responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 404, 409, 422, 429)})
    def network_configure(iface: str, body: NetworkConfigBody, p: Principal = Depends(gw.principal),
                          idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Ask to give a wired interface a fixed IPv4 address and DNS, or to go back to DHCP. Nothing changes yet.

        The request waits for an owner, who approves it with a passkey. After approval the box applies it
        and the owner has `rollback_seconds` (default 120) to open the box at the new address and confirm
        (`POST /v1/network/{iface}/confirm`); without that the old settings come back by themselves.

        409 `host_unavailable` while the box cannot change its network, `unknown_interface` / `not_wired` for an
        interface that is not a cable, `change_pending` while an earlier change waits for confirmation (nothing
        is filed in these cases); 422 for an address, gateway or DNS no network can use. The `Idempotency-Key` header
        (or the body's `idempotency_key`) makes a retry replay the same request."""
        owner(p, "change network")
        if not p.can_request_actions:
            raise ApiError(403, "permission_denied", "this token cannot request actions")
        body_out, created = svc.request(p, iface_name(iface), body, idem)
        return JSONResponse(status_code=202 if created else 200, content=body_out,
                            headers={"Location": f"/v1/actions/{body_out['id']}"})

    @app.post("/v1/network/{iface}/confirm", tags=["net"], operation_id="network.confirm", response_model=NetworkConfirm,
              responses=error_responses(401, 403, 404, 409, 422))
    def network_confirm(iface: str, body: NetworkConfirmBody, p: Principal = Depends(gw.principal)) -> NetworkConfirm:
        """Keep the pending change identified by the approved action ID.

        Before sending this request, use another device on the wired network to open the dashboard directly at
        the changed interface's IPv4 address, sign in, and verify that this box's Network page loads. For DHCP,
        find the address assigned to this interface in the router. The request records the owner's attestation;
        the gateway cannot infer that the check succeeded from the request's network path.

        409 `no_pending_change` if nothing waits for confirmation or `change_mismatch` if a different action is pending."""
        owner(p, "confirm network change")
        return svc.confirm(p, iface_name(iface), body.action_id)


def firewall_step_up(gw: Gateway):
    """Approval guard: opening a port is approved only with the owner's passkey (D-027/D-028), whatever
    `require_passkey_approval` says. The identity guard (registered earlier, so it runs first) verifies the
    assertion: signed over this action, by an active owner. Same rule as a service restart (routers/services.py)."""

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        if action.get("type") != ALLOW_ACTION:
            return
        identity_present = any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)
        if body.get("webauthn") is None or not identity_present:
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": ALLOW_ACTION, "reason": "firewall_allow_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "opening a port needs your passkey: register one, then approve with it",
                           reason="step_up_required")

    return guard
