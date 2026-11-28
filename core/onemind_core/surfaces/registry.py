# SPDX-License-Identifier: Apache-2.0
"""The surface registry (#605): one list of what every enabled app plugs into, for every client.

Read live on every call from the gateway's own tools (surfaces/core.py) and the descriptors of the
switched-on built-ins (builtins.py), so switching an app off removes its tools, cards, search
provider, share target, topics, layers, Settings pages and backup units at once; switching it on
brings them back, and its data stays.

What a declaration cannot prove is refused, listed under `refused` with the reason, and served on no
surface (the MCP catalogue reads `mcp_actions` from here):
- a tool whose action type the gateway has not registered (an undeclared tool);
- a notification topic naming an event the notify catalogue does not route to it (an undeclared topic);
- a card whose source is not a public read operation whose response declares `observed_at`, so no
  card ever shows a value without saying when it was read.

Installed Market apps join from their installation receipt (the manifest a person approved, never the
mutable catalog file), and only while installed and running that receipt (`MarketApp`). A Market tool is
served over REST (POST /v1/plugins/{id}/tools/{tool}); its write or destructive call files a
plugin.invoke request a person approves. A Market card is a template widget whose source tool is one of
the app's own served read tools with `observed_at` in its output schema; anything else is refused. A
Market map layer is served only with source `emits` (the layer emits of the app's own bridge, served by the
gateway); a call source would have the host fetch a core route of the app's choosing with the viewer's
token, so it is refused (`kind: layer`).

GET /v1/surfaces (routers/surfaces.py) serves `view`.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..builtins import Builtins, Descriptor, tool_name
from .core import CORE_TOOLS

OBSERVED_AT = "observed_at"
PLUGIN_INVOKE = "plugin.invoke"
PLUGIN_SCOPE = "actions:request:plugin.invoke"


TOOL_NAME_MAX = 64
TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # the strictest LLM tool-name rule (UNVERIFIED)
MARKET_SEP = "__"  # app ids never hold "_" and no core or built-in tool name holds "__"
LAYER_EMITS = "emits"


def market_tool_name(app_id: str, tool: str) -> str:
    """A Market tool's one name on every surface (REST listing, cards, and /mcp once Market tools join it).

    `<app_id>__<tool>`: only letters, digits, `_` and `-`, at most 64 characters, so it passes the
    tool-name rules LLM tool APIs apply (no dots). An app id is a DNS label (up to 59 characters, no
    `_`) and a tool name up to 40, so a pair that would pass 64 keeps the start of the app id and adds 8
    hex characters of sha256("<app_id>/<tool>"), which keeps names distinct and stable."""
    name = f"{app_id}{MARKET_SEP}{tool}"
    if len(name) <= TOOL_NAME_MAX:
        return name
    digest = hashlib.sha256(f"{app_id}/{tool}".encode()).hexdigest()[:8]
    keep = max(1, TOOL_NAME_MAX - len(MARKET_SEP) - len(tool) - len(digest) - 1)
    return f"{app_id[:keep]}-{digest}{MARKET_SEP}{tool}"[:TOOL_NAME_MAX]


def market_tool_route(app_id: str, tool: str) -> str:
    return f"POST /v1/plugins/{app_id}/tools/{tool}"


@dataclass(frozen=True)
class MarketApp:
    """An installed Market app as its approved receipt declares it.

    spec: the receipt manifest's spec; served: tool name -> the declaration the gateway serves for it
    (plugins/tools.py `Tools.lookup` accepted it). A declared tool missing from `served` is refused."""

    id: str
    name: str
    description: str | None
    spec: dict
    served: dict[str, dict] = field(default_factory=dict)


def _schema_props(spec: dict, schema: dict, depth: int = 0) -> set[str]:
    """Property names of a response schema, following $ref and allOf (bounded)."""
    if depth > 8 or not isinstance(schema, dict):
        return set()
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        return _schema_props(spec, spec.get("components", {}).get("schemas", {}).get(ref.rsplit("/", 1)[1], {}),
                             depth + 1)
    props = set(schema.get("properties") or {})
    for part in schema.get("allOf") or []:
        props |= _schema_props(spec, part, depth + 1)
    return props


def card_problem(openapi: dict, source: str) -> str | None:
    """Why a card may not read `source` ("GET /v1/..."), or None when it may."""
    method, _, path = source.partition(" ")
    op = openapi.get("paths", {}).get(path, {}).get(method.lower())
    if method != "GET" or op is None:
        return f"source {source} is not a public read operation"
    ok = next((r for code, r in sorted(op.get("responses", {}).items()) if code.startswith("2")), None)
    schema = ((ok or {}).get("content") or {}).get("application/json", {}).get("schema", {})
    if OBSERVED_AT not in _schema_props(openapi, schema):
        return f"source {source} declares no {OBSERVED_AT}, so the card could not say when its value was read"
    return None


class SurfaceRegistry:
    """Joins the core tools with the switched-on built-ins. Every input is read when asked.

    known_action(type): is the action type registered with the gateway;
    event_topic(event): the notify catalogue topic an event routes to, or None;
    openapi(): the gateway's public OpenAPI document (FastAPI caches it)."""

    def __init__(self, builtins: Builtins, *, known_action: Callable[[str], bool],
                 event_topic: Callable[[str], str | None], openapi: Callable[[], dict],
                 market: Callable[[], list[MarketApp]] = list):
        self.builtins = builtins
        self.market = market
        self.known_action = known_action
        self.event_topic = event_topic
        self.openapi = openapi

    # ---- tools -----------------------------------------------------------------------------
    def route_enabled(self, route: str) -> bool:
        """Internal tool calls observe the same route ownership as the HTTP gate."""
        owner = self.builtins.owner_of(route.split(" ", 1)[1])
        return owner is None or owner.id not in self.builtins.disabled()

    def core_tools(self) -> list[dict]:
        return [{"name": t.name, "app_id": None, "title": t.title, "effect": t.effect, "exposure": list(t.exposure),
                 "route": t.route, "action_type": None, "scope": t.scope} for t in CORE_TOOLS if self.route_enabled(t.route)]

    def _app_tools(self, d: Descriptor, refused: list[dict]) -> list[dict]:
        out = []
        for a in d.spec.get("actions", []):
            if not a["mcp"]:
                continue
            if not self.known_action(a["type"]):
                refused.append({"app_id": d.id, "kind": "tool", "id": tool_name(a["type"]),
                                "reason": f"action type {a['type']} is not registered with the gateway"})
                continue
            out.append({"name": tool_name(a["type"]), "app_id": d.id, "title": a["title"], "effect": "write",
                        "exposure": ["mcp"], "route": None, "action_type": a["type"],
                        "scope": f"actions:request:{a['type']}"})
        return out

    @staticmethod
    def _market_tools(m: MarketApp, refused: list[dict]) -> list[dict]:
        out = []
        declared = ((m.spec.get("extensions") or {}).get("tools")) or []
        for item in declared:
            name = item.get("name") if isinstance(item, dict) else None
            tool = m.served.get(name) if isinstance(name, str) else None
            if tool is None:
                refused.append({"app_id": m.id, "kind": "tool", "id": market_tool_name(m.id, str(name)),
                                "reason": f"tool {name} is not served: a Market tool needs a valid declaration "
                                          "with exposure.rest"})
                continue
            exposure = [k for k in ("rest", "cli") if (tool.get("exposure") or {}).get(k) is True]
            out.append({"name": market_tool_name(m.id, name), "app_id": m.id,
                        "title": str(tool.get("title", name))[:128], "effect": tool["effect"],
                        "exposure": exposure, "route": market_tool_route(m.id, name),
                        "action_type": None if tool["effect"] == "read" else PLUGIN_INVOKE,
                        "scope": PLUGIN_SCOPE})
        return out

    @staticmethod
    def _market_cards(m: MarketApp, refused: list[dict]) -> list[dict]:
        out = []
        for w in ((m.spec.get("extensions") or {}).get("widgets")) or []:
            if not isinstance(w, dict) or w.get("render") != "template":
                continue  # an iframe widget is the app's own page, not a card the host draws
            tool_ref = (w.get("source") or {}).get("tool")
            tool = m.served.get(tool_ref)
            if tool is None or tool["effect"] != "read":
                problem = f"source tool {tool_ref} is not one of this app's served read tools"
            elif OBSERVED_AT not in _schema_props({}, tool.get("output") or {}):
                problem = (f"source tool {tool_ref} declares no {OBSERVED_AT} in its output, so the card could "
                           "not say when its value was read")
            else:
                out.append({"app_id": m.id, "id": w["id"], "title": w["title"], "template": w["template"],
                            "source": market_tool_route(m.id, tool_ref), "tool": market_tool_name(m.id, tool_ref),
                            "args": dict((w.get("source") or {}).get("args") or {})})
                continue
            refused.append({"app_id": m.id, "kind": "card", "id": str(w.get("id")), "reason": problem})
        return out

    @staticmethod
    def _market_layers(m: MarketApp, refused: list[dict]) -> list[dict]:
        out = []
        for x in m.spec.get("mapLayers") or []:
            if not isinstance(x, dict):
                continue
            if x.get("source") != LAYER_EMITS:
                refused.append({"app_id": m.id, "kind": "layer", "id": str(x.get("id")),
                                "reason": f"source {x.get('source')} is not {LAYER_EMITS}: a Market layer draws "
                                          "only its own bridge's emits, never a gateway route"})
                continue
            out.append({"app_id": m.id, "id": x["id"], "title": x["title"], "source": LAYER_EMITS})
        return out

    def mcp_actions(self) -> dict[str, tuple[str, str, str]]:
        """MCP tool name -> (action type, title, app name): the request-only tools of switched-on
        built-ins whose action type is registered. Nothing refused is ever an MCP tool."""
        names = {d.id: d.name for d in self.builtins.enabled()}
        return {t["name"]: (t["action_type"], t["title"], names[t["app_id"]])
                for d in self.builtins.enabled() for t in self._app_tools(d, [])}

    # ---- cards and topics ------------------------------------------------------------------
    def _cards(self, d: Descriptor, refused: list[dict]) -> list[dict]:
        out = []
        for c in d.spec.get("cards", []):
            problem = card_problem(self.openapi(), c["source"])
            if problem:
                refused.append({"app_id": d.id, "kind": "card", "id": c["id"], "reason": problem})
            else:
                out.append({"app_id": d.id, **c})
        return out

    def _topics(self, d: Descriptor | MarketApp, refused: list[dict]) -> list[dict]:
        out = []
        for t in (d.spec.get("notifications") or {}).get("topics", []):
            stray = [e for e in t.get("events", []) if self.event_topic(e) != t["id"]]
            if stray:
                refused.append({"app_id": d.id, "kind": "topic", "id": t["id"],
                                "reason": f"the notify catalogue does not route {', '.join(stray)} to topic {t['id']}"})
            else:
                out.append({"app_id": d.id, "id": t["id"], "title": t.get("title"), "events": list(t.get("events", []))})
        return out

    # ---- the one list ----------------------------------------------------------------------
    def view(self, visible: Callable[[str], bool]) -> dict:
        """Everything the caller may see. `visible(app_id)` is the gateway's app filters."""
        apps = [d for d in self.builtins.enabled() if visible(d.id)]
        refused: list[dict] = []
        tools = self.core_tools()
        out: dict[str, list] = {"apps": [], "cards": [], "search": [], "share": [], "notifications": [],
                                "map_layers": [], "settings_pages": [], "backup_units": []}
        for d in apps:
            spec = d.spec
            out["apps"].append({"id": d.id, "name": d.name, "description": d.description, "origin": "builtin",
                                "phone": spec["phone"]})
            tools += self._app_tools(d, refused)
            out["cards"] += self._cards(d, refused)
            out["notifications"] += self._topics(d, refused)
            if "search" in spec:
                out["search"].append({"app_id": d.id, **spec["search"]})
            if "share" in spec:
                out["share"].append({"app_id": d.id, **spec["share"]})
            out["map_layers"] += [{"app_id": d.id, **m} for m in spec.get("mapLayers", [])]
            out["settings_pages"] += [{"app_id": d.id, **p} for p in spec.get("settingsPages", [])]
            out["backup_units"] += [{"app_id": d.id, **u} for u in spec["backup"]["units"]]
        for m in self.market():
            if not visible(m.id):
                continue
            spec = m.spec
            out["apps"].append({"id": m.id, "name": m.name, "description": m.description, "origin": "market",
                                "phone": {"entry": "web" if "web" in spec else "none"}})
            tools += self._market_tools(m, refused)
            out["cards"] += self._market_cards(m, refused)
            out["notifications"] += self._topics(m, refused)
            if "search" in spec:
                out["search"].append({"app_id": m.id, **spec["search"]})
            if "share" in spec:
                out["share"].append({"app_id": m.id, **spec["share"]})
            out["map_layers"] += self._market_layers(m, refused)
            if ((spec.get("extensions") or {}).get("settings")):
                out["settings_pages"].append({"app_id": m.id, "id": "settings", "title": f"{m.name} settings",
                                              "source": f"GET /v1/plugins/{m.id}/settings"})
            out["backup_units"].append({"app_id": m.id, "kind": "app", "name": m.id})
        return {**out, "tools": tools, "refused": refused}
