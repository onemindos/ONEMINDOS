# SPDX-License-Identifier: Apache-2.0
"""Area read tools on /mcp (#632): backups, OS updates, file metadata, machines, storage, alerts,
settings and troubleshooting logs.

The tools are declared once in surfaces/core.py (AREA_TOOLS), so the catalogue, the per-tool scopes and
route parity pick them up like every other tool. This module serves them. Each one calls the same service
as its REST route, with that route's own rule for who may read, and then, before anything reaches the model:

1. redacts: a value under a key that names a secret (password, token, api_key, private_key, ...) becomes
   "[redacted]", and every string goes through the log redactor (monitoring/redact.py: bearer and basic
   credentials, URL passwords, JWTs, OneMind and cloud keys, PEM private keys, e-mail and IP addresses);
2. caps: a list tool returns at most `limit` rows (AREA_PAGE_MAX) with `next_cursor` for the next page; any
   other list in a result is cut at AREA_PAGE_MAX and the result says `truncated: true`; app logs return at
   most LOG_LINES_MAX lines, and asking for more says `truncated: true`;
3. marks third-party text untrusted (mcp/untrusted.py): log lines, alert text, machine names, file names.

App logs and file metadata need a scope granted by name (logs:read, files:read; auth.MCP_BY_NAME_ONLY).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..auth import Principal
from ..errors import ApiError
from ..monitoring.redact import Redactor
from ..surfaces.core import AREA_PAGE_MAX, AREA_TOOLS, LOG_LINES_MAX, LOG_TAIL_ASK_MAX
from .tools import INVALID_PARAMS, RpcError, _source, refusal, result

AREA_TOOL_NAMES = frozenset(t.name for t in AREA_TOOLS)
REDACTED = "[redacted]"
SECRET_KEY = re.compile(r"(?i)passw|passphrase|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|"
                        r"(?:secret|encryption|signing|ssh|master|account|repo)[_-]?key|credential|cookie|"
                        r"authorization|session[_-]?id|^key$")
MAX_DEPTH = 32
TOO_DEEP = "[nested too deep: omitted]"
_APP_ID = re.compile(r"^[a-z0-9]([a-z0-9-]{0,57}[a-z0-9])?$")
_COMPONENT = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")
_ROOT = re.compile(r"^(?:shared|home:[ -~]{1,200})$")
_CURSOR = re.compile(r"^[0-9]{1,9}$")


# ---- redaction and caps --------------------------------------------------------------------------

def redact_text(text: str) -> str:
    r = Redactor()  # line by line, so a PEM block spread over lines is redacted whole
    return "\n".join(r.line(x) for x in text.split("\n"))


def redact(value: Any, key: str = "", depth: int = 0) -> Any:
    """value with every secret-looking field and string redacted; the shape is kept."""
    if depth > MAX_DEPTH:
        return TOO_DEEP
    if key and SECRET_KEY.search(key) and value is not None and not isinstance(value, bool) \
            and value not in ("", [], {}):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {str(k): redact(v, str(k), depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, "", depth + 1) for v in value]
    return value


def cap(value: Any, depth: int = 0) -> tuple[Any, bool]:
    """value with every list cut at AREA_PAGE_MAX; True when anything was cut."""
    if depth > MAX_DEPTH:
        return TOO_DEEP, True
    cut = False
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            out[k], c = cap(v, depth + 1)
            cut |= c
        return out, cut
    if isinstance(value, (list, tuple)):
        cut = len(value) > AREA_PAGE_MAX
        items = []
        for v in list(value)[:AREA_PAGE_MAX]:
            x, c = cap(v, depth + 1)
            items.append(x)
            cut |= c
        return items, cut
    return value, False


# ---- the readers: the REST routes' own services, read when called ---------------------------------

def _error(exc: Exception) -> dict | None:
    """A refusal the model can read for a service's own error; None when it is not one."""
    error, message = getattr(exc, "error", None), getattr(exc, "message", None)
    if isinstance(exc, ApiError) or (isinstance(error, str) and isinstance(message, str)):
        return refusal(error, message)
    if type(exc).__name__ in ("Unavailable", "AgentError"):  # backups: switched off or agent unreachable
        return refusal("unavailable", str(exc))
    return None


class AreaReads:
    """Built by routers/mcp.py. The services live on app.state and are looked up per call, because their
    routers register after /mcp (routers/__init__.py order)."""

    def __init__(self, state: Any, gw: Any, app_rows: Callable[[], list[dict]],
                 can_see_alert: Callable[[Principal, dict], bool]):
        # can_see_alert is GET /v1/alerts' own audience rule (routers/notifications.py), handed in by the router.
        self.state, self.gw, self.app_rows, self.can_see_alert = state, gw, app_rows, can_see_alert

    def svc(self, attr: str) -> Any:
        found = getattr(self.state, attr, None)
        if found is None:
            raise ApiError(503, "unavailable", f"{attr} is not running on this box")
        return found

    def map_packs_list(self, p: Principal, a: dict):
        return self.svc("map_packs").list().model_dump(mode="json")

    def get_backup_status(self, p: Principal, a: dict):
        self._backup_reader(p)
        return self.svc("backups").status()

    def list_backup_runs(self, p: Principal, a: dict):
        self._backup_reader(p)
        return self.svc("backups").runs()

    def list_backup_snapshots(self, p: Principal, a: dict):
        self._backup_reader(p)
        app_id = _opt(a, "app_id", 59, _APP_ID)
        return self.svc("backups").snapshots(app_id=app_id, unit=_opt(a, "unit", 128))

    def _backup_reader(self, p: Principal) -> None:  # routers/backups.py reader()
        if not (p.is_owner or p.role in ("adult", "agent")):
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not read backups")

    def get_os_updates(self, p: Principal, a: dict):
        return self.svc("osupdate").status()

    def get_os_update_history(self, p: Principal, a: dict):
        return self.svc("osupdate").history()

    def stat_file(self, p: Principal, a: dict):
        root = _opt(a, "root", 205, _ROOT, required=True)
        return self.svc("files_service").stat(p, root, _opt(a, "path", 4096) or "/")

    def list_machines(self, p: Principal, a: dict):
        return self.svc("machines").repo.all()

    def get_machine(self, p: Principal, a: dict):
        name = _opt(a, "name", 200, required=True)
        row = self.svc("machines").repo.get(name)
        if row is None:
            raise ApiError(404, "not_found", f"There is no machine named {name}.")
        return row

    def get_storage(self, p: Principal, a: dict):
        from ..storage import StorageSummary  # the REST route's response model: no disk identities

        return StorageSummary.model_validate(self.svc("storage").summary()).model_dump(mode="json",
                                                                                       exclude_unset=True)

    def list_alerts(self, p: Principal, a: dict):
        import json

        from ..notify.store import alert_json

        state = _opt(a, "state", 40)
        states = None
        if state:
            wanted = set(state.split(","))
            states = ({"open", "acknowledged"} if "open" in wanted else set()) | (wanted & {"acknowledged", "resolved"})
        rows = self.svc("notify").repo.list_alerts(states)
        return [alert_json(r) for r in rows if self.can_see_alert(p, json.loads(r.audience_json or "{}"))]

    def get_alert(self, p: Principal, a: dict):
        import json

        from ..notify.store import alert_json

        row = self.svc("notify").repo.get_alert(_opt(a, "alert_id", 200, required=True))
        if row is None or not self.can_see_alert(p, json.loads(row.audience_json or "{}")):
            raise ApiError(404, "not_found", "no such alert")
        return alert_json(row)

    def get_update_settings(self, p: Principal, a: dict):
        return self.svc("update_policy").to_json()

    def read_app_logs(self, p: Principal, a: dict):
        from ..monitoring import health as H

        app_id = _opt(a, "app_id", 59, _APP_ID, required=True)
        component = _opt(a, "component", 253, _COMPONENT)
        tail = a.get("tail", 200)
        if not isinstance(tail, int) or isinstance(tail, bool) or not 1 <= tail <= LOG_TAIL_ASK_MAX:
            raise RpcError(INVALID_PARAMS, f"tail must be an integer in [1, {LOG_TAIL_ASK_MAX}]")
        row = next((r for r in self.app_rows() if r["id"] == app_id), None)
        if row is None:
            raise ApiError(404, "not_found", "no such app")
        if not row["installed"]:
            raise ApiError(404, "not_found", "the app is not installed")
        kube = getattr(self.svc("monitoring"), "kube", None)
        if kube is None:
            raise ApiError(404, "not_found", "this box has no Kubernetes API to read from")
        pods = kube.pods(f"app-{app_id}")
        if pods is None:
            raise ApiError(404, "not_found", "the Kubernetes API is not reachable")
        pods = sorted((x for x in pods if component is None or H.component_of(x) == component),
                      key=lambda x: (x.get("metadata") or {}).get("name", ""))
        if not pods:
            raise ApiError(404, "not_found", "no pods for that component")
        # One line more than we return tells whether lines were left out.
        lines = kube.logs(f"app-{app_id}", pods[0]["metadata"]["name"], None, min(tail, LOG_LINES_MAX + 1), None)
        if lines is None:
            raise ApiError(404, "not_found", "could not read the logs")
        self.gw.events.publish_event("logs", "opened", {"app_id": app_id, "component": component, "tail": tail,
                                                        "follow": False, "via": "mcp"}, principal=p.as_dict())
        r = Redactor()
        return {"app_id": app_id, "component": component,
                "lines": [r.line(x) for x in lines[-LOG_LINES_MAX:]], "truncated": len(lines) > LOG_LINES_MAX}


def _opt(a: dict, key: str, max_len: int, rx: re.Pattern | None = None, required: bool = False) -> str | None:
    v = a.get(key)
    if v is None and not required:
        return None
    if not isinstance(v, str) or not v or len(v) > max_len or (rx is not None and not rx.match(v)):
        raise RpcError(INVALID_PARAMS, f"{key} must be a valid string of at most {max_len} characters")
    return v


# ---- how each tool's result is shaped -------------------------------------------------------------

@dataclass(frozen=True)
class Shape:
    untrusted: tuple[str, ...] = ()  # mark() patterns, relative to one row for list tools
    id_field: str = "id"
    kind: str = "item"  # the wrapper source names a value after its row: <kind>:<id>:<field>


SHAPES: dict[str, Shape] = {
    "map_packs_list": Shape(("packs.*.region",)),
    "get_backup_status": Shape(("last_run.error", "last_run.message")),
    "list_backup_runs": Shape(("error", "message"), kind="run"),
    "list_backup_snapshots": Shape(("paths.*", "tags.*"), kind="snapshot"),
    "get_os_updates": Shape(("install.message",)),
    "get_os_update_history": Shape(("requests.*.message", "events.*.message")),
    "stat_file": Shape(("name", "path")),
    "list_machines": Shape(("name", "description"), id_field="name", kind="machine"),
    "get_machine": Shape(("name", "description")),
    "get_storage": Shape(("error",)),
    "list_alerts": Shape(("title", "body"), kind="alert"),
    "get_alert": Shape(("title", "body")),
    "get_update_settings": Shape(),
    "read_app_logs": Shape(("lines.*",)),
}
_PAGED = {t.name: t.body_key for t in AREA_TOOLS if t.body_key}
_ARGS = {t.name: set(t.input.get("properties", {})) for t in AREA_TOOLS}


def call(reads: AreaReads | None, p: Principal, name: str, args: dict) -> dict:
    """tools/call for an area tool: validated, read, redacted, capped, paged and marked."""
    extra = set(args) - _ARGS[name]
    if extra:
        raise RpcError(INVALID_PARAMS, f"unknown arguments: {sorted(extra)}")
    if reads is None:
        return refusal("unavailable", "area reads are not wired on this gateway")
    key = _PAGED.get(name)
    if key:
        cursor = _opt(args, "cursor", 20, _CURSOR)
        limit = args.get("limit", AREA_PAGE_MAX)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= AREA_PAGE_MAX:
            raise RpcError(INVALID_PARAMS, f"limit must be an integer in [1, {AREA_PAGE_MAX}]")
    try:
        body = getattr(reads, name)(p, args)
    except RpcError:
        raise
    except Exception as exc:  # a service refusal is a tool result, not a protocol error
        out = _error(exc)
        if out is None:
            raise
        return out
    shape = SHAPES[name]
    if key:
        rows = list(body or [])
        start = int(cursor) if cursor else 0
        page, _ = cap([redact(r) for r in rows[start:start + limit]])
        s: dict[str, Any] = {key: page}
        if start + limit < len(rows):
            s["next_cursor"] = str(start + limit)
        patterns = [f"{key}.*.{f}" for f in shape.untrusted]
        return result(s, patterns, _source(s, key, shape.id_field, shape.kind))
    if name == "read_app_logs":  # its own cap (LOG_LINES_MAX lines) and its own truncated flag
        s = redact(body)
        return result(s, list(shape.untrusted), lambda path: f"app:{s['app_id']}:{path}")
    s, cut = cap(redact(body if isinstance(body, dict) else {"items": body}))
    if cut:
        s["truncated"] = True
    return result(s, list(shape.untrusted))
