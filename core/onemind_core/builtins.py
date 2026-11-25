# SPDX-License-Identifier: Apache-2.0
"""Built-in app descriptors: what each built-in plugs into, and the one switch-off gate (#603).

A descriptor is `core/onemind_core/<id>/onemind.app.yaml` (schema: sdk/schema/onemind.builtin.schema.json).
It is read only for ids on the signed system apps list (systemlist.py): a descriptor folder for any
other id is ignored, so a file dropped into the package cannot make itself a built-in.

From the descriptors of the built-ins that are switched on, the gateway builds:
- the request-only MCP tools (`spec.actions` with `mcp: true`, mcp/tools.py);
- the Settings pages (`spec.settingsPages`) and the backup set (`spec.backup.units`);
- GET /v1/builtins (routers/builtins.py), which lists all of that for every client. The route is
  provisional: it folds into the surface registry (GET /v1/surfaces) when that lands.

Each built-in also has an app principal (`AppPrincipal`, id `app:<id>`): the in-process identity its
engine uses to post to the one inbox under the topics its descriptor declares (notify/topics.py). It
is never a token and never requests or approves anything.

`BuiltinGate` is the one place that answers 409 `app_disabled`: every request (HTTP or websocket)
under a prefix a switched-off built-in owns (`spec.routes.owns`) is refused there, so no module reads
its own switch and no route under the prefix, public or not, is reachable while it is off.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from .auth import Principal
from .errors import ApiError, error_response
from .systemlist import SystemList

log = logging.getLogger("onemind.builtins")

DESCRIPTOR = "onemind.app.yaml"
PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_NAME = "onemind.builtin.schema.json"
REPO_SCHEMA = PACKAGE_DIR.parents[1] / "sdk" / "schema" / SCHEMA_NAME
MCP_PREFIX = "request_"
APP_PRINCIPAL_PREFIX = "app:"


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
        out += [p["source"] for p in self.spec.get("settingsPages", [])]
        return out


@dataclass(frozen=True)
class AppPrincipal(Principal):
    """A built-in app's own principal (#613): kind and role `app`, id `app:<id>`.

    Made only in-process by `Builtins.principal` for a loaded descriptor; no token, tokens file or
    identity credential can carry kind `app`. It is not an owner and cannot request actions."""

    def __post_init__(self) -> None:
        if self.kind != "app" or self.role != "app" or not self.id.startswith(APP_PRINCIPAL_PREFIX):
            raise ValueError("an app principal has kind and role app and id app:<id>")

    @property
    def app_id(self) -> str:
        return self.id[len(APP_PRINCIPAL_PREFIX):]


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

    def principal(self, app_id: str) -> AppPrincipal | None:
        """The app principal of a built-in with a loaded descriptor (switched on or not), else None."""
        if app_id not in self.descriptors:
            return None
        return AppPrincipal(id=APP_PRINCIPAL_PREFIX + app_id, kind="app", role="app")

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
        return [{"app_id": d.id, **p} for d in self.enabled() for p in d.spec.get("settingsPages", [])]

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


class BuiltinGate:
    """ASGI middleware: every HTTP or websocket request under a prefix a switched-off built-in owns
    is refused here, before any route runs, so a public or websocket route stays shut too.

    Whether an app is off is told only to a caller the gateway signs in: the gate runs the same
    principal check the routes use (bearer token, session cookie, route scopes, kill switch). A
    caller it signs in gets 409 app_disabled; anyone else gets that check's own refusal (401, or
    403 without the route's scope), so a made-up credential learns nothing. A websocket gets the
    same answer as an HTTP denial response, or a close (4409 / 4401) where the server lacks that.
    """

    def __init__(self, app, *, builtins: Builtins, principal: Callable[[Request], object]):
        self.app = app
        self.builtins = builtins
        self.principal = principal

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            d = self.builtins.owner_of(scope.get("path", ""))
            if d is not None and d.id in self.builtins.disabled():
                return await self._refuse(d, scope, receive, send)
        return await self.app(scope, receive, send)

    async def _refuse(self, d: Descriptor, scope, receive, send):
        ws = scope["type"] == "websocket"
        # The principal check reads method, path, headers and cookies only, never the body.
        request = Request({**scope, "type": "http", "method": "GET"} if ws else scope)
        try:
            await run_in_threadpool(self.principal, request)
        except ApiError as exc:
            resp = error_response(exc.status, exc.error, exc.message, reason=exc.reason,
                                  details=exc.details, retry_after_s=exc.retry_after_s)
            code = 4401 if exc.status == 401 else 4403
        else:
            resp = error_response(409, "stale_precondition",
                                  f"{d.name} is switched off; switch it on first (app.enable)",
                                  reason="app_disabled")
            code = 4409
        if not ws:
            return await resp(scope, receive, send)
        message = await receive()  # websocket.connect
        if message.get("type") != "websocket.connect":
            return None
        if "websocket.http.response" in (scope.get("extensions") or {}):
            return await resp(scope, receive, send)
        return await send({"type": "websocket.close", "code": code, "reason": "app_disabled" if code == 4409 else ""})
