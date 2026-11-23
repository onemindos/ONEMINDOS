# SPDX-License-Identifier: Apache-2.0
"""REST catalog visibility for agents; never permission to read provider data.

Use the gateway's existing app-filter hook so list, detail, plan and appstore
reads share the boundary. Only trusted catalog manifests decide visibility;
request headers, query parameters and an agent's own policy claims do not.
"""

from __future__ import annotations

from .ai_policy import CATALOG, decide, manifest_policy
from .auth import Principal
from .context import Gateway


def agent_catalog_filter(gw: Gateway):
    def visible(_request, principal: Principal, app_id: str) -> bool:
        if principal.kind != "agent":
            return True  # AI policy must not remove the person's existing display access.
        entry = gw.catalog.load().get(app_id)
        if entry is None:
            return False
        # The same policy the MCP catalogue reads from the summary row, including explicit null:
        # absence is legacy metadata access, but an explicit unknown fails closed.
        return decide(manifest_policy(entry.manifest), CATALOG).allowed

    return visible
