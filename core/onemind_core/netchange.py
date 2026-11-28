# SPDX-License-Identifier: Apache-2.0
"""Changing a wired interface's IPv4 setup: static address and DNS, or back to DHCP (P-08).

`PUT /v1/network/{iface}` does not change anything: it files a `network.configure` action that an owner
approves with a passkey (D-027, D-028: an OS-changing write is an owner action; the CLI and agents only
ask). On approval the gateway sends the change to the host service (internal/host/netset.go), which asks
NetworkManager to make it inside a *checkpoint with a rollback timer*. The owner then has `rollback_seconds`
(default 120) to open the box at its NEW address and press Confirm (`POST /v1/network/{iface}/confirm`).
No confirmation, no problem: NetworkManager puts the old settings back by itself, so a wrong address
never strands anyone. A confirmed change lives in the NetworkManager profile on /data and survives
reboots and A/B updates.

Why this module checks the request again although the host does: a request that can only fail should not
reach an owner's approval queue, and the host is the authority only for what the box can do.
"""

from __future__ import annotations

import ipaddress
import logging
import uuid
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .actions import FeatureAction
from .auth import Principal
from .ca import MESH_NETS
from .context import Gateway
from .errors import ApiError
from .executors import ExecResult
from .hostnet import NETWORK_ACTION_ID, HostNetClient, NetChanges, parse_changes, read_view
from .jsonbody import JsonBody
from .storage import StorageClient, StorageTimeout, StorageUnavailable

log = logging.getLogger("onemind.netchange")
ACTION = "network.configure"
REQUEST_TTL = timedelta(hours=1)  # an approval left for a day would apply a network picked a day ago
IFACE_RE = r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,14}$"
MIN_ROLLBACK, MAX_ROLLBACK, DEFAULT_ROLLBACK = 10, 600, 120


class NetworkConfigBody(JsonBody):
    """The wanted IPv4 setup of one wired interface. `dhcp` takes no address, gateway or DNS."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["static", "dhcp"]
    address: str | None = Field(default=None, max_length=18, description="static: IPv4 address with prefix, like 192.0.2.20/24")
    gateway: str | None = Field(default=None, max_length=15, description="static: the router, inside the address's subnet")
    dns: list[str] = Field(default_factory=list, max_length=3, description="static: up to three DNS servers")
    rollback_seconds: int = Field(default=DEFAULT_ROLLBACK, ge=MIN_ROLLBACK, le=MAX_ROLLBACK,
                                  description="how long the owner has to confirm from the new address before the old settings return")
    reason: str | None = Field(default=None, max_length=200, description="shown to the owner on the approval card")
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class NetworkConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool
    interface: str


class NetworkConfirmBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(pattern=NETWORK_ACTION_ID, description="The approved action ID from the pending network change.")
    verified_reachable: Literal[True] = Field(description="The owner opened the dashboard directly at this interface's new IPv4 address from another device and verified it loaded.")

    @field_validator("verified_reachable", mode="before")
    @classmethod
    def require_attestation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("verify the box is reachable at its new IPv4 address before confirming")
        return value


class NetHostError(Exception):
    """The host refused or could not do it: a stable `reason` and a sentence for the owner."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


class HostNetChangeClient:
    """JSON over the host service's Unix socket (internal/host/netset.go)."""

    def __init__(self, socket_path, timeout_s: float, read_timeout_s: float | None = None):
        # Two clients: applying waits up to `timeout_s` (NetworkManager re-activates the link); reading the
        # pending change for the Network screen and the approval check waits only `read_timeout_s`, so a slow
        # Apply never holds a page load for a minute (review of #1156). The host answers reads at once anyway.
        self.api = StorageClient(socket_path, timeout_s)
        self.read_api = StorageClient(socket_path, read_timeout_s if read_timeout_s is not None else timeout_s)

    def _call(self, method: str, path: str, body: dict | None = None, *, read: bool = False) -> tuple[int, dict]:
        try:
            status, doc = (self.read_api if read else self.api).call(method, path, body)
        except StorageUnavailable:
            raise NetHostError("host_unavailable", "The host service is not reachable, so the network cannot be changed.") from None
        except StorageTimeout:
            raise NetHostError("host_timeout", "The host service did not answer in time. Check the network screen before trying again.") from None
        return status, doc if isinstance(doc, dict) else {}

    def changes(self) -> NetChanges:
        try:
            status, doc = self._call("GET", "/v1/network/changes", read=True)
        except NetHostError as e:
            return NetChanges(can_change=False, reason=e.message)
        return parse_changes(doc) if status == 200 else NetChanges(can_change=False, reason=f"The host service answered {status}.")

    def _ok(self, status: int, doc: dict) -> dict:
        if status == 200:
            return doc
        if status == 409 and isinstance(doc.get("reason"), str):
            raise NetHostError(doc["reason"], str(doc.get("message") or "The host refused."))
        raise NetHostError("host_error", "The host service could not do it; see the box's journal.")

    def apply(self, iface: str, body: dict) -> NetChanges:
        return parse_changes(self._ok(*self._call("PUT", f"/v1/network/{iface}", body)))

    def confirm(self, iface: str, action_id: str) -> NetChanges:
        return parse_changes(self._ok(*self._call("POST", f"/v1/network/{iface}/confirm", {"action_id": action_id})))


def _bad(msg: str, reason: str = "invalid_config") -> ApiError:
    return ApiError(422, "conflict", msg, reason=reason)


def check_config(body: NetworkConfigBody) -> None:
    """Refuse what no home network can use. The host checks again; this keeps junk out of the approval queue."""
    if body.mode == "dhcp":
        if body.address or body.gateway or body.dns:
            raise _bad("Automatic (DHCP) takes no address, gateway or DNS: the router hands them out.")
        return
    try:
        iface = ipaddress.ip_interface(body.address or "")
    except ValueError:
        raise _bad("address must be an IPv4 address with its prefix, like 192.0.2.20/24.", "invalid_address") from None
    net = iface.network
    if iface.version != 4 or "/" not in (body.address or "") or not 8 <= net.prefixlen <= 30:
        raise _bad("address must be an IPv4 address with a prefix between /8 and /30, like 192.0.2.20/24.", "invalid_address")
    ip = iface.ip
    if (not ip.is_global and not ip.is_private) or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified \
            or ip == net.network_address or ip == net.broadcast_address:
        raise _bad(f"{ip} cannot be this box's address (network, broadcast, loopback, link-local or multicast).", "invalid_address")
    if any(ip in n for n in MESH_NETS):
        raise _bad(f"{ip} is in the range the mesh keeps for itself; pick a home-network address.", "invalid_address")
    try:
        gw = ipaddress.ip_address(body.gateway or "")
    except ValueError:
        raise _bad("A fixed address needs a gateway: the router's IPv4 address.", "invalid_gateway") from None
    if gw.version != 4 or gw not in net or gw in (ip, net.network_address, net.broadcast_address):
        raise _bad(f"The gateway must be another host inside {net}.", "invalid_gateway")
    seen: set = set()
    for s in body.dns:
        try:
            d = ipaddress.ip_address(s)
        except ValueError:
            raise _bad(f"{s!r} is not a DNS server address.", "invalid_dns") from None
        if d.version != 4 or d in seen or d.is_loopback or d.is_unspecified or d.is_multicast or d.is_link_local:
            raise _bad(f"{s} is not a usable, distinct DNS server address.", "invalid_dns")
        seen.add(d)


class NetChangeService:
    def __init__(self, gw: Gateway, client: HostNetClient, host: HostNetChangeClient):
        self.gw, self.view_client, self.host = gw, client, host

    def register(self) -> None:
        # "actuate": the box's own network changes. Only an owner asks (requesters is empty: no agent), and the
        # approval needs the owner's passkey (routers/network.py).
        self.gw.actions.register_type(ACTION, FeatureAction("actuate", self._run, frozenset(), check=self._recheck))

    # ---- what is possible now --------------------------------------------------------------------
    def refusal(self, iface: str, mode: str) -> tuple[str, str] | None:
        """Why this change cannot be filed or approved now, as (reason, message), or None."""
        changes = self.host.changes()
        if not changes.can_change:
            return "host_unavailable", changes.reason or "The host service cannot change the network."
        if changes.pending is not None:
            return "change_pending", (f"The change to {changes.pending.interface} is still waiting for confirmation. "
                                       "Confirm it, or wait for it to roll back, before changing again.")
        view = read_view(self.view_client)
        if not view.available:
            return "host_unavailable", view.message or "The network cannot be read right now."
        found = next((i for i in view.interfaces if i.name == iface), None)
        if found is None:
            return "unknown_interface", f"This box has no network interface called {iface}."
        if found.kind != "ethernet":
            return "not_wired", f"{iface} is not a cable connection; this changes wired interfaces only."
        return None

    def check_request(self, iface: str, body: NetworkConfigBody) -> None:
        check_config(body)
        if (r := self.refusal(iface, body.mode)) is not None:
            raise ApiError(409, "conflict", r[1], reason=r[0])

    def _recheck(self, a) -> str | None:
        r = self.refusal(a.params["interface"], a.params["mode"])
        return r[1] if r else None

    # ---- the action -------------------------------------------------------------------------------
    def request(self, p: Principal, iface: str, body: NetworkConfigBody, idem: str | None = None) -> tuple[dict, bool]:
        self.check_request(iface, body)
        params = {"interface": iface, "mode": body.mode, "rollback_seconds": body.rollback_seconds}
        if body.mode == "static":
            params |= {"address": body.address, "gateway": body.gateway, "dns": body.dns}
        return self.gw.actions.request_feature(
            p, ACTION, params, idempotency_key=idem or body.idempotency_key or f"network:{uuid.uuid4()}",
            expires_at=self.gw.clock() + REQUEST_TTL, reason=body.reason, pending_cap=True)

    def _run(self, a, finish) -> None:
        p = a.params
        host_body = {k: p[k] for k in ("mode", "address", "gateway", "dns", "rollback_seconds") if p.get(k) is not None}
        host_body["action_id"] = a.id
        try:
            changes = self.host.apply(p["interface"], host_body)
        except NetHostError as e:
            if e.reason == "host_timeout":
                # The host may still be applying: it can answer after this call gave up. Read it again before
                # calling the action failed, because a change that is now pending is waiting for Confirm.
                after = self.host.changes()
                if after.pending is not None and after.pending.interface == p["interface"] and after.pending.action_id == a.id:
                    changes = after
                    e = None
            if e is not None:
                finish(ExecResult("failed", e.message, steps=[{"step": "apply network", "interface": p["interface"], "result": e.reason}]))
                return
        except Exception as e:  # noqa: BLE001 - an approved action must always end
            log.exception("applying the network change failed")
            finish(ExecResult("failed", f"The gateway could not apply the change ({type(e).__name__}). Check the network screen.",
                              steps=[{"step": "apply network", "interface": p["interface"], "result": "internal_error"}]))
            return
        where = f"at {p['address'].split('/')[0]}" if p["mode"] == "static" else "at the address the router gives it"
        finish(ExecResult(
            "succeeded",
            f"{p['interface']} is changed. Open this box {where} and press Confirm within {p['rollback_seconds']} seconds, "
            "or it goes back to its old settings by itself.",
            steps=[{"step": "apply network", "interface": p["interface"], "result": "pending_confirmation",
                    "deadline": changes.pending.deadline.isoformat() if changes.pending else None}]))

    # ---- confirm ------------------------------------------------------------------------------------
    def confirm(self, p: Principal, iface: str, action_id: str) -> NetworkConfirm:
        try:
            self.host.confirm(iface, action_id)
        except NetHostError as e:
            status = 409
            raise ApiError(status, "conflict", e.message, reason=e.reason) from None
        self.gw.audit.append("network.confirmed", p.as_dict(), action_id, {"interface": iface, "verified_reachable": True})
        return NetworkConfirm(confirmed=True, interface=iface)

    def changes(self) -> NetChanges:
        return self.host.changes()

    def now(self) -> datetime:
        return self.gw.clock()
