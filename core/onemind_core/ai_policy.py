# SPDX-License-Identifier: Apache-2.0
"""Policy for the catalog MCP surface, not a provider-data/model-routing permission.

Legacy non-health catalog metadata stays visible. Sensitive catalog entries default
 to display-only. Consent, local routing and official-provider MCP are not implemented,
so none of those policy values authorizes this MCP server to expose the entry.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
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
    # A row as GET /v1/apps and MCP list_apps show it carries null for "none declared"
    # (shown_policy), so null reads as absent here. Catalog summary rows never carry null:
    # catalog.py records an explicit manifest null as "unknown", which stays hidden.
    policy = summary.get("aiPolicy", ABSENT)
    return decide(ABSENT if policy is None else policy, CATALOG).allowed


# ---- App data handed to an agent (#165) ---------------------------------------------------------
# One rule for both agent surfaces: what a gateway MCP tool returns and what an agent reads over
# REST are the same destination, app data given to an AI (MCP_TOOL). Absent, unknown and every
# restrictive policy deny it; only "allowed" passes until owner consent records exist. Both
# surfaces call the functions below: the MCP tools (mcp/tools.py) and the agent REST readers of
# action results and plugin read tools (routers/actions.py, routers/plugin_tools.py).

def is_agent(principal: object) -> bool:
    """aiPolicy limits what reaches an AI: agent principals. People, automations and plugins are
    not AI, and the owner always sees the app's own data."""
    return getattr(principal, "kind", None) == "agent"


def action_app_id(action: dict) -> object:
    params = action.get("params")
    return params.get("app_id") if isinstance(params, dict) else None


def app_policy(apps: Iterable[dict], app_id: object) -> object:
    """The policy of one app read from catalog summary rows (routers/apps.app_rows); ABSENT when
    the app is not in the catalog, so an unknown app's data is denied like any undeclared one."""
    return summary_policy(next((a for a in apps if a.get("id") == app_id), None))


def _carries_output(action: dict) -> bool:
    result = action.get("result")
    steps = result.get("steps") if isinstance(result, dict) else None
    return isinstance(steps, list) and any(isinstance(s, dict) and "output" in s for s in steps)


def actions_for_agent(rows: list[dict], apps: Callable[[], Iterable[dict]]) -> list[dict]:
    """Every action as an agent may see it. `apps` returns the catalog summary rows and is read only
    when some action carries an app's tool output."""
    if not any(_carries_output(a) for a in rows):
        return rows
    by_id = {a.get("id"): a for a in apps()}
    return [withhold_app_data(a, summary_policy(by_id.get(action_app_id(a)))) for a in rows]


def app_data_to_agent(policy: object) -> Decision:
    return decide(policy, MCP_TOOL)


def withhold_app_data(action: dict, policy: object) -> dict:
    """The action as an agent may see it. A tool's output (`result.steps[].output`, written by the
    app's own backend: plugins/tools.py) is the app's data, so it is removed unless the app's
    aiPolicy lets app data reach an AI. The outcome, message and the gateway's own steps stay, so
    the agent still learns whether its request ran."""
    if not _carries_output(action):
        return action
    decision = app_data_to_agent(policy)
    if decision.allowed:
        return action
    result = action["result"]
    steps = result["steps"]
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
