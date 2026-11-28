# SPDX-License-Identifier: Apache-2.0
"""The box's network facts for the Network screen (NET-UI-01, #239), read from the host service.

The gateway runs in a container and cannot see the host's interfaces, so `onemindd host serve`
(root, on the host) answers `GET /v1/network` on its local socket (internal/netview). Node heartbeats
are not the source: their contract forbids IP and MAC addresses (sdk/contracts/poc-v0.md section 2).

The host service is trusted but not blindly: every field is checked again here (H-06), item by item.
An interface, gateway or port that fails a check is dropped and counted in `dropped`, so one odd
entry cannot hide the rest or put unchecked text on a screen. This is read-only; changing the
network is a later, owner-approved action.
"""

from __future__ import annotations

import ipaddress
import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .storage import StorageTimeout, StorageUnavailable, _UnixConnection

MAX_BODY = 1 << 20
NAME_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,32}$")
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
STATE_RE = re.compile(r"^[a-z-]{1,16}$")
KINDS = ("ethernet", "wifi", "loopback", "bridge", "virtual")
PROTOS = ("tcp", "udp")
SCOPES = ("any", "loopback", "address")
MAX_ITEMS = 400
MAX_INTERFACES = 64  # the Go side stops at 64 too (internal/netview)

Reason = Literal["host_service_unreachable", "host_service_error", "bad_response"]


class Wifi(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal_dbm: int | None = Field(description="Signal level in dBm; null when the driver does not report it.")


class NetInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kind: Literal["ethernet", "wifi", "loopback", "bridge", "virtual"]
    state: str = Field(description="The kernel's operstate: up, down, unknown, ...")
    mac: str | None = None
    mtu: int
    addresses: list[str] = Field(description="CIDR form, e.g. 192.0.2.10/24")
    wifi: Wifi | None = None


class NetGateway(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interface: str
    via: str
    family: Literal["ipv4", "ipv6"]


class NetPort(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proto: Literal["tcp", "udp"]
    addr: str
    port: int
    scope: Literal["any", "loopback", "address"] = Field(description="any = every interface; loopback = this machine only; address = one address")


NETWORK_ACTION_ID = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$"


class NetChange(BaseModel):
    """One wired-address change (netconf of an interface, P-08) and what became of it."""

    model_config = ConfigDict(extra="forbid")
    action_id: str | None = Field(default=None, pattern=NETWORK_ACTION_ID, description="The approved action for this change. Older records may have no action ID.")
    interface: str
    mode: Literal["static", "dhcp"]
    address: str | None = None
    gateway: str | None = None
    dns: list[str] = []
    result: Literal["pending", "confirmed", "rolled_back"] = Field(description="pending: applied, waiting for the owner to confirm before `deadline`; confirmed: kept; rolled_back: not confirmed in time (or it failed), the old settings are back")
    started_at: datetime
    deadline: datetime = Field(description="When NetworkManager puts the old settings back unless the owner confirms.")
    ended_at: datetime | None = None


class NetChanges(BaseModel):
    """Whether this box can change its wired network, and the change waiting for confirmation."""

    model_config = ConfigDict(extra="forbid")
    can_change: bool
    reason: str | None = None
    pending: NetChange | None = None
    last: NetChange | None = Field(default=None, description="The most recent change that finished.")


class NetworkView(BaseModel):
    """What the box listens on and how it is connected. It does not include firewall rules."""

    model_config = ConfigDict(extra="forbid")
    available: bool
    reason: Reason | None = None
    message: str | None = None
    at: datetime | None = None
    interfaces: list[NetInterface] = []
    gateways: list[NetGateway] = []
    dns: list[str] = []
    ports: list[NetPort] = []
    dropped: int = Field(default=0, description="Entries the gateway refused because a field failed its checks.")
    changes: NetChanges | None = Field(default=None, description="Wired address changes: whether they are possible, and the one waiting for confirmation.")


def unavailable(reason: Reason, message: str) -> NetworkView:
    return NetworkView(available=False, reason=reason, message=message)


class HostNetClient:
    def __init__(self, path: str, timeout_s: float):
        self.path, self.timeout_s = path, timeout_s

    def fetch(self, path: str = "/v1/network") -> tuple[int, Any]:
        conn = _UnixConnection(self.path, self.timeout_s)
        try:
            try:
                conn.connect()
            except OSError as exc:
                raise StorageUnavailable(exc.__class__.__name__) from None
            try:
                conn.request("GET", path)
                resp = conn.getresponse()
                raw = resp.read(MAX_BODY + 1)
            except Exception as exc:  # timeout, reset, protocol error
                raise StorageTimeout(exc.__class__.__name__) from None
            if len(raw) > MAX_BODY:
                return resp.status, None
            try:
                return resp.status, json.loads(raw or b"null")
            except ValueError:
                return resp.status, None
        finally:
            conn.close()


def _ip(v: Any) -> str:
    if not isinstance(v, str):
        raise ValueError("not text")
    if "%" in v:  # an IPv6 scope id ("fe80::1%eth0") names a local interface; never shown
        raise ValueError("scope id")
    return str(ipaddress.ip_address(v))


def _name(v: Any) -> str:
    if not isinstance(v, str) or not NAME_RE.match(v):
        raise ValueError("bad name")
    return v


def _cidr(a: Any) -> str:
    if not isinstance(a, str) or "%" in a:
        raise ValueError("bad address")
    return str(ipaddress.ip_interface(a))


def _interface(d: dict) -> NetInterface:
    if d.get("kind") not in KINDS:
        raise ValueError("bad kind")
    state = d.get("state")
    if not isinstance(state, str) or not STATE_RE.match(state):
        raise ValueError("bad state")
    mac = d.get("mac") or None
    if mac is not None and (not isinstance(mac, str) or not MAC_RE.match(mac)):
        raise ValueError("bad mac")
    mtu = d.get("mtu")
    if not isinstance(mtu, int) or isinstance(mtu, bool) or not 0 <= mtu <= 1_000_000:
        raise ValueError("bad mtu")
    addrs = d.get("addresses") or []
    if not isinstance(addrs, list) or len(addrs) > 64:
        raise ValueError("bad addresses")
    wifi = None
    if d.get("kind") == "wifi" and isinstance(d.get("wifi"), dict):
        sig = d["wifi"].get("signal_dbm")
        ok = sig is None or (isinstance(sig, int) and not isinstance(sig, bool) and -200 < sig < 0)
        wifi = Wifi(signal_dbm=sig if ok else None)
    return NetInterface(name=_name(d.get("name")), kind=d["kind"], state=state, mac=mac, mtu=mtu,
                        addresses=[_cidr(a) for a in addrs], wifi=wifi)


def _gateway(d: dict) -> NetGateway:
    via = _ip(d.get("via"))
    family = "ipv6" if ":" in via else "ipv4"
    if d.get("family") != family:
        raise ValueError("family does not match address")
    return NetGateway(interface=_name(d.get("interface")), via=via, family=family)


def _port(d: dict) -> NetPort:
    port = d.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("bad port")
    if d.get("proto") not in PROTOS or d.get("scope") not in SCOPES:
        raise ValueError("bad proto or scope")
    return NetPort(proto=d["proto"], addr=_ip(d.get("addr")), port=port, scope=d["scope"])


def _items(raw: Any, build, limit: int = MAX_ITEMS) -> tuple[list, int]:
    """Each entry checked on its own; a bad one is dropped and counted."""
    out, dropped = [], 0
    if not isinstance(raw, list):
        return out, 1 if raw not in (None, []) else 0
    for entry in raw[:limit]:
        try:
            if not isinstance(entry, dict):
                raise ValueError("not an object")
            out.append(build(entry))
        except (ValueError, TypeError):
            dropped += 1
    return out, dropped + max(0, len(raw) - limit)


def parse_view(body: Any) -> NetworkView:
    if not isinstance(body, dict) or body.get("schema") != "onemind.netview/v1":
        return unavailable("bad_response", "the host service sent something the gateway does not understand")
    interfaces, d1 = _items(body.get("interfaces"), _interface, MAX_INTERFACES)
    gateways, d2 = _items(body.get("gateways"), _gateway)
    ports, d3 = _items(body.get("ports"), _port)
    dns, d4 = _items([{"a": a} for a in body["dns"]] if isinstance(body.get("dns"), list) else body.get("dns"),
                     lambda e: _ip(e.get("a")))
    at = None
    try:
        at = datetime.fromisoformat(str(body.get("at")).replace("Z", "+00:00"))
    except ValueError:
        pass
    return NetworkView(available=True, at=at, interfaces=interfaces, gateways=gateways, dns=dns[:8], ports=ports,
                       dropped=d1 + d2 + d3 + d4)


def read_view(client: HostNetClient) -> NetworkView:
    try:
        status, body = client.fetch()
    except (StorageUnavailable, StorageTimeout):
        return unavailable("host_service_unreachable",
                           "the host service is not reachable from the gateway, so this box's network cannot be read yet")
    if status != 200:
        return unavailable("host_service_error", f"the host service answered {status}")
    return parse_view(body)


def _change(d: Any) -> NetChange | None:
    if not isinstance(d, dict):
        return None
    try:
        return NetChange(action_id=d.get("action_id"), interface=_name(d.get("interface")), mode=d.get("mode"),
                         address=_cidr(d["address"]) if d.get("address") else None,
                         gateway=_ip(d["gateway"]) if d.get("gateway") else None,
                         dns=[_ip(x) for x in (d.get("dns") or [])][:3], result=d.get("result"),
                         started_at=d.get("started_at"), deadline=d.get("deadline"), ended_at=d.get("ended_at"))
    except (ValueError, TypeError):  # includes pydantic's ValidationError
        return None


def parse_changes(body: Any) -> NetChanges:
    """The host service's GET /v1/network/changes, checked field by field. A bad answer means no change possible."""
    if not isinstance(body, dict) or not isinstance(body.get("available"), bool):
        return NetChanges(can_change=False, reason="the host service sent something the gateway does not understand")
    why = body.get("unavailable_reason")
    return NetChanges(can_change=body["available"], reason=None if body["available"] else str(why or "the host cannot change the network")[:300],
                      pending=_change(body.get("pending")), last=_change(body.get("last")))
