# SPDX-License-Identifier: Apache-2.0
"""REST catalog visibility for agents; never permission to read provider data.

Use the gateway's existing app-filter hook so list, detail, plan and appstore
reads share the boundary. Only trusted catalog manifests decide visibility;
request headers, query parameters and an agent's own policy claims do not.
"""

from __future__ import annotations

from .auth import Principal
from .context import Gateway


def agent_catalog_filter(gw: Gateway):
    def visible(_request, principal: Principal, app_id: str) -> bool:
        if principal.kind != "agent":
            return True  # AI policy must not remove the person's existing display access.
        entry = gw.catalog.load().get(app_id)
        if entry is None:
            return False
        spec = entry.manifest.get("spec") or {}
        if "aiPolicy" in spec:
            # Consent, official MCP and local routing are not yet implemented.
            return spec["aiPolicy"] == "allowed"
        category = (entry.manifest.get("metadata") or {}).get("category")
        # Legacy non-health catalog metadata only, NOT a provider-data grant.
        return category not in {"health", "wellness"}

    return visible
