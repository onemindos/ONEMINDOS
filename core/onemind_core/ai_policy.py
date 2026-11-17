# SPDX-License-Identifier: Apache-2.0
"""Policy for the catalog MCP surface, not a provider-data/model-routing permission.

Legacy non-health catalog metadata stays visible. Sensitive catalog entries default
 to display-only. Consent, local routing and official-provider MCP are not implemented,
so none of those policy values authorizes this MCP server to expose the entry.
"""

from __future__ import annotations


SENSITIVE_CATEGORIES = frozenset({"health", "wellness"})


def catalog_policy(manifest: dict) -> object:
    spec = manifest.get("spec") or {}
    if "aiPolicy" in spec:
        return spec["aiPolicy"]
    category = (manifest.get("metadata") or {}).get("category")
    return "display-only" if category in SENSITIVE_CATEGORIES else None


def catalog_visible_to_ai(summary: dict) -> bool:
    # Absence retains legacy catalog metadata only; it must never authorize
    # future access to an app's provider data. Explicit unknown values fail closed.
    return "aiPolicy" not in summary or summary["aiPolicy"] == "allowed"
