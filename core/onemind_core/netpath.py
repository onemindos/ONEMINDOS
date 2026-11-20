# SPDX-License-Identifier: Apache-2.0
"""Which network path a request really came from, and which exposure tiers let it in (#285, UMB-P02b).

The app proxy already honours the exposure tier by host name (a private app is 404 on its mesh
name). A Host header is only what the client says, so on its own it cannot keep a LAN-only app off
the internet: anyone who can reach the port can send `Host: <app>.onemind.local`. This module
judges the connection instead.

Paths, from the peer address the socket reports (never from a header the client controls):

- mesh: the peer is inside the mesh ranges (100.64.0.0/10, fd7a:115c:a1e0::/48), the address the
  box CA also pins. Checked before LAN because 100.64.0.0/10 is not RFC 1918 but is "private" to
  Python's ipaddress module.
- lan: an address in an explicit LAN list that is not mesh (RFC 1918, fc00::/7, fe80::/10, 169.254/16).
  Python's "private" is deliberately not used: it admits Teredo, 6to4 and reserved ranges.
- public: any other global address.
- tor: only ever asserted by a trusted edge (the onion service daemon connects from loopback, so
  the socket cannot tell Tor from the LAN).
- unknown: everything else (non-global addresses outside the LAN list, such as 2001:db8::/32 or
  240/4, included), loopback with no trusted edge, an unparsable or missing peer,
  and a trusted edge that said nothing or something unrecognised. Unknown fails closed: no tier
  admits it, not even private.

A trusted edge (a reverse proxy, a tunnel or Tor on this box, CORE-NET-5) hides the real peer, so
it states the path in `X-OneMind-Path: lan|mesh|tor|public`. That header is believed only when the
socket peer is inside the configured trusted proxy networks (ONEMIND_NET_TRUSTED_PROXIES, default
none); from anyone else it is ignored, so a client cannot upgrade itself by sending it. The edge
must set the header on every request, replacing any value the client sent.

Tiers (contract §12.22): private -> lan; mesh -> lan, mesh; public -> lan, mesh, tor, public.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Literal

from .ca import MESH_NETS

NetPath = Literal["lan", "mesh", "tor", "public", "unknown"]
PATH_HEADER = "x-onemind-path"
EDGE_PATHS: frozenset[str] = frozenset({"lan", "mesh", "tor", "public"})

TIER_PATHS: dict[str, frozenset[str]] = {
    "private": frozenset({"lan"}),
    "mesh": frozenset({"lan", "mesh"}),
    "public": frozenset({"lan", "mesh", "tor", "public"}),
}

_IP = ipaddress.IPv4Address | ipaddress.IPv6Address

# The home LAN, spelled out. Python's `is_private` is not this: it also covers ranges the internet can
# reach (Teredo 2001::/32, 6to4 2002::/16) and reserved ones (documentation, 198.18/15, 240/4).
LAN_NETS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fc00::/7", "fe80::/10"))


def parse_networks(spec: str | tuple[str, ...] | list[str]) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Comma-separated CIDRs or addresses; raises ValueError on anything else."""
    items = spec.split(",") if isinstance(spec, str) else spec
    return tuple(ipaddress.ip_network(i.strip(), strict=False) for i in items if i.strip())


def _peer_ip(peer: str | None) -> _IP | None:
    if not peer:
        return None
    try:
        ip = ipaddress.ip_address(peer.split("%", 1)[0])  # drop an IPv6 zone id
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def path_of_peer(peer: str | None) -> NetPath:
    """The path an address on the socket implies; unknown when it implies nothing safe."""
    ip = _peer_ip(peer)
    if ip is None or ip.is_loopback or ip.is_unspecified or ip.is_multicast:
        return "unknown"
    if any(ip in n for n in MESH_NETS if n.version == ip.version):
        return "mesh"
    if any(ip in n for n in LAN_NETS if n.version == ip.version):
        return "lan"
    return "public" if ip.is_global else "unknown"


class PathClassifier:
    """Classifies a request by its socket peer, believing a trusted edge's X-OneMind-Path."""

    def __init__(self, trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()):
        self.trusted_proxies = trusted_proxies

    def trusts(self, peer: str | None) -> bool:
        ip = _peer_ip(peer)
        return ip is not None and any(ip in n for n in self.trusted_proxies if n.version == ip.version)

    def __call__(self, peer: str | None, headers: Mapping[str, str]) -> NetPath:
        if self.trusts(peer):
            claimed = headers.get(PATH_HEADER, "").strip().lower()
            return claimed if claimed in EDGE_PATHS else "unknown"  # type: ignore[return-value]
        return path_of_peer(peer)

    def from_edge(self, headers: Mapping[str, str]) -> NetPath:
        """For an endpoint only the edge can call (forward-auth is loopback only): the edge's word."""
        claimed = headers.get(PATH_HEADER, "").strip().lower()
        return claimed if claimed in EDGE_PATHS else "unknown"  # type: ignore[return-value]


def tier_admits(tier: str, path: str) -> bool:
    """True when an app with this exposure tier may answer a request that came by this path."""
    return path in TIER_PATHS.get(tier, TIER_PATHS["private"])  # an unknown tier is the strictest
