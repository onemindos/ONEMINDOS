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


def manifest_policy(manifest: dict) -> object:
    """The app's policy as decide() takes it: ABSENT when the manifest declares none and no
    sensitive-category default applies. Explicit values (null too) are passed on unchanged."""
    spec = manifest.get("spec") or {}
    policy = catalog_policy(manifest)
    return policy if ("aiPolicy" in spec or policy is not None) else ABSENT


def summary_policy(summary: dict | None) -> object:
    """The same policy read back from a catalog summary row (catalog.CatalogEntry.summary)."""
    return ABSENT if summary is None else summary.get("aiPolicy", ABSENT)


def decide_for_manifest(manifest: dict, destination: str, *, consented: bool = False) -> Decision:
    return decide(manifest_policy(manifest), destination, consented=consented)


def require(manifest: dict, destination: str, *, consented: bool = False) -> None:
    """Raise AIPolicyDenied unless the app's data may go to `destination`."""
    decision = decide_for_manifest(manifest, destination, consented=consented)
    if not decision.allowed:
        raise AIPolicyDenied(decision)


def catalog_visible_to_ai(summary: dict) -> bool:
    # Absence retains legacy catalog metadata only; it must never authorize
    # future access to an app's provider data. Explicit unknown values fail closed.
    return decide(summary.get("aiPolicy", ABSENT), CATALOG).allowed


# ---- App data handed to an agent (#165) ---------------------------------------------------------
# One rule for both agent surfaces: what a gateway MCP tool returns and what an agent reads over
# REST are the same destination, app data given to an AI (MCP_TOOL). Absent, unknown and every
# restrictive policy deny it; only "allowed" passes until owner consent records exist. The MCP
# tools call it now; the agent REST readers of action results and plugin read tools
# (routers/actions.py, routers/plugin_tools.py) are to call the same functions (#165 follow-up).

def app_data_to_agent(policy: object) -> Decision:
    return decide(policy, MCP_TOOL)


def withhold_app_data(action: dict, policy: object) -> dict:
    """The action as an agent may see it. A tool's output (`result.steps[].output`, written by the
    app's own backend: plugins/tools.py) is the app's data, so it is removed unless the app's
    aiPolicy lets app data reach an AI. The outcome, message and the gateway's own steps stay, so
    the agent still learns whether its request ran."""
    result = action.get("result")
    steps = result.get("steps") if isinstance(result, dict) else None
    if not isinstance(steps, list) or not any(isinstance(s, dict) and "output" in s for s in steps):
        return action
    decision = app_data_to_agent(policy)
    if decision.allowed:
        return action
    clean = [{**{k: v for k, v in s.items() if k != "output"}, "output_withheld": decision.reason}
             if isinstance(s, dict) and "output" in s else s for s in steps]
    return {**action, "result": {**result, "steps": clean}}


UNKNOWN = "unknown"  # shown for a declared value the gateway does not know (treated as deny)


def policy_label(value: object) -> str:
    """The aiPolicy as GET /v1/apps shows it: a known policy name, else "unknown"."""
    return value if isinstance(value, str) and value in POLICIES else UNKNOWN


def shown_policy(summary: dict) -> str | None:
    """The same value for a summary row that MCP returns: null when nothing is declared."""
    policy = summary_policy(summary)
    return None if policy is ABSENT else policy_label(policy)
