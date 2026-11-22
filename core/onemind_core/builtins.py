# SPDX-License-Identifier: Apache-2.0
"""Built-in app descriptors: what each built-in plugs into, and the one switch-off gate (#603).

A descriptor is `core/onemind_core/<id>/onemind.app.yaml` (schema: sdk/schema/onemind.builtin.schema.json).
It is read only for ids on the signed system apps list (systemlist.py): a descriptor folder for any
other id is ignored, so a file dropped into the package cannot make itself a built-in.

From the descriptors of the built-ins that are switched on, the gateway builds:
- the request-only MCP tools (`spec.actions` with `mcp: true`, mcp/tools.py);
- the Settings pages (`spec.settings.pages`) and the backup set (`spec.backup.units`);
- GET /v1/builtins (routers/builtins.py), which lists all of that for every client.

`BuiltinGate` is the one place that answers 409 `app_disabled`: every request under a prefix a
switched-off built-in owns (`spec.routes.owns`) is refused there, so no module reads its own switch.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .errors import error_response
from .systemlist import SystemList

log = logging.getLogger("onemind.builtins")

DESCRIPTOR = "onemind.app.yaml"
PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_NAME = "onemind.builtin.schema.json"
REPO_SCHEMA = PACKAGE_DIR.parents[1] / "sdk" / "schema" / SCHEMA_NAME
MCP_PREFIX = "request_"


@dataclass(frozen=True)
class Descriptor:
    id: str
    name: str
    description: str | None
    spec: dict

    def owns(self) -> list[str]:
        return list(self.spec["routes"]["owns"])

    def calls(self) -> list[str]:
        """Every public operation the descriptor names: routes.calls plus each card, layer and page source."""
        out = list(self.spec["routes"]["calls"])
        out += [c["source"] for c in self.spec.get("cards", [])]
        out += [m["source"] for m in self.spec.get("mapLayers", [])]
        out += [p["source"] for p in (self.spec.get("settings") or {}).get("pages", [])]
        return out


def schema_path(app_schema_path: Path | None) -> Path | None:
    """Next to the app manifest schema on the box (/usr/lib/onemind/sdk/schema), else the repo's copy."""
    for p in ([app_schema_path.parent / SCHEMA_NAME] if app_schema_path else []) + [REPO_SCHEMA]:
        if p.is_file():
            return p
    return None


def load(system: SystemList, root: Path = PACKAGE_DIR, schema: Path | None = REPO_SCHEMA
         ) -> tuple[dict[str, Descriptor], dict[str, list[str]]]:
    """(descriptors by id, errors by id) for the ids on the signed list. Never raises.

    Without the schema nothing is loaded (fail closed): an unchecked descriptor could own any route.
    """
    if schema is None or not schema.is_file():
        log.error("built-in descriptor schema not found; no built-in descriptor is loaded")
        return {}, {}
    validator = Draft202012Validator(json.loads(schema.read_text(encoding="utf-8")))
    found: dict[str, Descriptor] = {}
    errors: dict[str, list[str]] = {}
    for app_id in sorted(system.ids()):
        path = root / app_id / DESCRIPTOR
        if not path.is_file():
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            errors[app_id] = [f"cannot parse: {exc.__class__.__name__}"]
            continue
        errs = [f"{'/'.join(str(x) for x in e.absolute_path) or '<root>'}: {e.message}"
                for e in validator.iter_errors(doc)]
        if not errs and doc["metadata"]["id"] != app_id:
            errs.append(f"metadata.id {doc['metadata']['id']!r} must match folder name {app_id!r}")
        if errs:
            log.warning("skipping built-in descriptor %s: %s", app_id, "; ".join(errs))
            errors[app_id] = errs
            continue
        md = doc["metadata"]
        found[app_id] = Descriptor(app_id, md["name"], md.get("description"), doc["spec"])
    return found, errors


def tool_name(action_type: str) -> str:
    return MCP_PREFIX + action_type.replace(".", "_")


def under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


class Builtins:
    """The loaded descriptors joined with the owner's on/off switch (gw.disabled_apps)."""

    def __init__(self, descriptors: dict[str, Descriptor], disabled: Callable[[], frozenset[str]],
                 errors: dict[str, list[str]] | None = None):
        self.descriptors = descriptors
        self.disabled = disabled
        self.errors = errors or {}

    def enabled(self) -> list[Descriptor]:
        off = self.disabled()
        return [d for app_id, d in sorted(self.descriptors.items()) if app_id not in off]

    def owner_of(self, path: str) -> Descriptor | None:
        for d in self.descriptors.values():
            if any(under(path, p) for p in d.owns()):
                return d
        return None

    def mcp_actions(self) -> dict[str, tuple[str, str, Descriptor]]:
        """tool name -> (action type, title, descriptor), for switched-on built-ins only."""
        return {tool_name(a["type"]): (a["type"], a["title"], d)
                for d in self.enabled() for a in d.spec.get("actions", []) if a["mcp"]}

    def settings_pages(self) -> list[dict]:
        return [{"app_id": d.id, **p} for d in self.enabled() for p in (d.spec.get("settings") or {}).get("pages", [])]

    def backup_units(self) -> list[dict]:
        return [{"app_id": d.id, **u} for d in self.enabled() for u in d.spec["backup"]["units"]]

    def view(self, visible: Callable[[str], bool]) -> dict:
        apps = [d for d in self.enabled() if visible(d.id)]
        ids = {d.id for d in apps}
        return {
            "apps": [{"id": d.id, "name": d.name, "description": d.description, "spec": d.spec} for d in apps],
            "settings_pages": [p for p in self.settings_pages() if p["app_id"] in ids],
            "backup_units": [u for u in self.backup_units() if u["app_id"] in ids],
            "tools": [{"name": n, "app_id": d.id, "action_type": t, "title": title}
                      for n, (t, title, d) in sorted(self.mcp_actions().items()) if d.id in ids],
        }


def _has_credential(scope) -> bool:
    return any(k in (b"authorization", b"cookie") for k, _ in scope.get("headers") or [])


class BuiltinGate:
    """ASGI middleware: 409 app_disabled for every route a switched-off built-in owns.

    A request without credentials passes through to the route, which answers 401: whether an app
    is switched off is not told to someone who has not signed in.
    """

    def __init__(self, app, *, builtins: Builtins):
        self.app = app
        self.builtins = builtins

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and _has_credential(scope):
            d = self.builtins.owner_of(scope.get("path", ""))
            if d is not None and d.id in self.builtins.disabled():
                resp = error_response(409, "stale_precondition",
                                      f"{d.name} is switched off; switch it on first (app.enable)",
                                      reason="app_disabled")
                return await resp(scope, receive, send)
        return await self.app(scope, receive, send)
