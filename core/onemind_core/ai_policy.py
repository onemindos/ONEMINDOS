# SPDX-License-Identifier: Apache-2.0
"""Policy for the catalog MCP surface, not a provider-data/model-routing permission.

Legacy non-health catalog metadata stays visible. Sensitive catalog entries default
 to display-only. Consent, local routing and official-provider MCP are not implemented,
so none of those policy values authorizes this MCP server to expose the entry.
"""

from __future__ import annotations

from dataclasses import dataclass


SENSITIVE_CATEGORIES = frozenset({"health", "wellness"})


def catalog_policy(manifest: dict) -> object:
    spec = manifest.get("spec") or {}
    if "aiPolicy" in spec:
        return spec["aiPolicy"]
    category = (manifest.get("metadata") or {}).get("category")
    return "display-only" if category in SENSITIVE_CATEGORIES else None


# ---- The stable decision interface (#165) -------------------------------------------------------
# Other gateway code (the model router #166, tainted-input approval #168, MCP tools) asks ONE
# question before any app data leaves for an AI: decide(policy, destination). Deny by default:
# an absent, unknown or malformed policy allows nothing except legacy catalog metadata.

ALLOWED = "allowed"
CONSENT_REQUIRED = "consent-required"
OFFICIAL_MCP_ONLY = "official-mcp-only"
DISPLAY_ONLY = "display-only"
PROHIBITED = "prohibited"
POLICIES = frozenset({ALLOWED, CONSENT_REQUIRED, OFFICIAL_MCP_ONLY, DISPLAY_ONLY, PROHIBITED})

# Where the data would go.
CATALOG = "catalog"              # app metadata shown to an agent through REST or MCP
MCP_TOOL = "mcp-tool"            # app data returned by a gateway MCP tool
LOCAL_MODEL = "local-model"      # a model running on this box
REMOTE_MODEL = "remote-model"    # a model run by someone else
OFFICIAL_MCP = "official-mcp"    # the provider's own MCP server, connected by the owner
DESTINATIONS = frozenset({CATALOG, MCP_TOOL, LOCAL_MODEL, REMOTE_MODEL, OFFICIAL_MCP})

ABSENT = object()  # no aiPolicy declared at all (not the same as an explicit null)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    needs_consent: bool = False  # true when only the owner's recorded consent is missing


class AIPolicyDenied(Exception):
    def __init__(self, decision: Decision):
        super().__init__(decision.reason)
        self.decision = decision


def decide(policy: object, destination: str, *, consented: bool = False) -> Decision:
    """May data under `policy` go to `destination`? `consented` must come from a stored
    owner consent, never from a request field or an agent's own claim."""
    if destination not in DESTINATIONS:
        return Decision(False, "unknown destination")
    if policy is ABSENT:
        # Legacy apps keep their catalog metadata visible; their data goes nowhere.
        return Decision(True, "legacy catalog metadata") if destination == CATALOG else Decision(
            False, "no aiPolicy declared; deny by default")
    if not isinstance(policy, str) or policy not in POLICIES:
        return Decision(False, "unknown aiPolicy; deny by default")
    if policy == ALLOWED:
        return Decision(True, "aiPolicy allowed")
    if policy == CONSENT_REQUIRED:
        if consented is True:
            return Decision(True, "owner consent recorded")
        return Decision(False, "owner consent required", needs_consent=True)
    if policy == OFFICIAL_MCP_ONLY:
        if destination == OFFICIAL_MCP:
            return Decision(True, "provider's official MCP only")
        return Decision(False, "provider data may reach AI only through its official MCP")
    return Decision(False, f"aiPolicy {policy}")


def decide_for_manifest(manifest: dict, destination: str, *, consented: bool = False) -> Decision:
    spec = manifest.get("spec") or {}
    policy = catalog_policy(manifest) if ("aiPolicy" in spec or catalog_policy(manifest) is not None) else ABSENT
    return decide(policy, destination, consented=consented)


def require(manifest: dict, destination: str, *, consented: bool = False) -> None:
    """Raise AIPolicyDenied unless the app's data may go to `destination`."""
    decision = decide_for_manifest(manifest, destination, consented=consented)
    if not decision.allowed:
        raise AIPolicyDenied(decision)


def catalog_visible_to_ai(summary: dict) -> bool:
    # Absence retains legacy catalog metadata only; it must never authorize
    # future access to an app's provider data. Explicit unknown values fail closed.
    return decide(summary.get("aiPolicy", ABSENT), CATALOG).allowed
