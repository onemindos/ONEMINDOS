# SPDX-License-Identifier: Apache-2.0
"""Exposure tiers (contract §12.22, PD-17): who can reach an app's web UI, and from where.

- private: the LAN names only (`<app>.onemind.local`), behind OneMind sign-in. Every install
  starts here and a removal comes back here.
- mesh:    also the mesh name `<app>.apps.onemind.internal`, for the owner's phones and laptops
  on the OneMind mesh (NETWORKING §9.1). Still behind sign-in.
- public:  reachable from the internet through the relay. Parked until the relay and the
  exposure review exist (CORE-NET-15); a request for it is refused with reason `parked`.

Each tier is its own request (`exposure.private|mesh|public`), owner-requested only and never by
an agent. The proxy and forward-auth consult `tier()` and answer 404 for a mesh name of an app
that is not exposed on the mesh.
"""

from __future__ import annotations

TIERS = ("private", "mesh", "public")
LAN_DOMAIN = "onemind.local"
MESH_DOMAIN = "apps.onemind.internal"


def names(app_id: str, tier: str) -> list[str]:
    out = [f"{app_id}.{LAN_DOMAIN}"]
    if tier in ("mesh", "public"):
        out.append(f"{app_id}.{MESH_DOMAIN}")
    return out


def allows_host(tier: str, host: str, mesh_domains: tuple[str, ...] = (MESH_DOMAIN,)) -> bool:
    """False when host is a mesh name and the tier does not include the mesh."""
    host = host.lower().split(":", 1)[0].rstrip(".")
    on_mesh = any(host.endswith("." + d) for d in mesh_domains)
    return not on_mesh or tier in ("mesh", "public")
