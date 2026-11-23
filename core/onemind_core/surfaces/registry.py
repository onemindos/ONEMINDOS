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

GET /v1/surfaces (routers/surfaces.py) serves `view`. Market manifests join in a later slice.
"""

from __future__ import annotations

from collections.abc import Callable

from ..builtins import Builtins, Descriptor, tool_name
from .core import CORE_TOOLS

OBSERVED_AT = "observed_at"


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
                 event_topic: Callable[[str], str | None], openapi: Callable[[], dict]):
        self.builtins = builtins
        self.known_action = known_action
        self.event_topic = event_topic
        self.openapi = openapi

    # ---- tools -----------------------------------------------------------------------------
    @staticmethod
    def core_tools() -> list[dict]:
        return [{"name": t.name, "app_id": None, "title": t.title, "effect": t.effect, "exposure": list(t.exposure),
                 "route": t.route, "action_type": None, "scope": t.scope} for t in CORE_TOOLS]

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

    def _topics(self, d: Descriptor, refused: list[dict]) -> list[dict]:
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
        return {**out, "tools": tools, "refused": refused}
