# SPDX-License-Identifier: Apache-2.0
"""REST catalog visibility for agents; never permission to read provider data.

Use the gateway's existing app-filter hook so list, detail, plan and appstore
reads share the boundary. Only trusted catalog manifests decide visibility;
request headers, query parameters and an agent's own policy claims do not.
"""

from __future__ import annotations

from .ai_policy import catalog_policy, catalog_visible_to_ai
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
        policy = catalog_policy(entry.manifest)
        # Match the catalog summary consumed by MCP, including explicit null:
        # absence is legacy metadata access, but an explicit unknown fails closed.
        summary = {"aiPolicy": policy} if "aiPolicy" in spec or policy is not None else {}
        return catalog_visible_to_ai(summary)

    return visible
