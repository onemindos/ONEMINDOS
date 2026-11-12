# SPDX-License-Identifier: Apache-2.0
"""Contract §12.15: app status and health, app logs, app and node metrics, the Home summary.

- `GET /v1/apps/{id}`, metrics and the summary: any principal, but an app hidden from it by
  §12.6 sharing (`gw.app_filters`, as in `GET /v1/apps`) is `404`. Household accounts and
  identity tokens also need `apps:read` / `monitoring:read` (registered below).
- `GET /v1/apps/{id}/logs`: owners and adults only (agents need a `logs:read:<app-id>` grant,
  which arrives with CORE-SEC scopes). At most 2000 lines, each line redacted; `follow=1` is
  an SSE stream of at most 15 minutes and 5 streams per principal. Every request is audited.
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from datetime import datetime

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from ..auth import Principal
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..ledger import iso, utc
from ..monitoring import MonitoringService
from ..monitoring import health as H
from ..monitoring.redact import Redactor, redact_lines
from ..identity.scopes import register_route_scope
from ..notify.store import NotifyRepository
from .apps import app_rows

MAX_TAIL = 2000
FOLLOW_MAX_S = 15 * 60
STREAMS_PER_PRINCIPAL = 5

# Scopes for household accounts and identity-issued tokens (§12.15 "Who" column). They override
# identity's broad /v1/apps(/.*)? -> apps:read and /v1/nodes(/.*)? -> nodes:read rows; GET
# /v1/apps/{id} keeps apps:read. A narrowed logs:read:<app-id> is refused (fail closed) until
# agents may read logs at all.
register_route_scope("GET,HEAD", r"/v1/apps/[^/]+/logs", ("logs:read",))
register_route_scope("GET,HEAD", r"/v1/apps/[^/]+/metrics", ("monitoring:read",))
register_route_scope("GET,HEAD", r"/v1/nodes/[^/]+/metrics", ("monitoring:read",))
register_route_scope("GET,HEAD", r"/v1/monitoring/summary", ("monitoring:read",))
_DURATION = re.compile(r"^(\d{1,6})([smh]?)$")
_COMPONENT = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


def parse_window(value: str | None, now: datetime, default_s: int, max_s: int) -> int:
    """`300`, `300s`, `30m`, `24h` or an RFC 3339 time (meaning "since then") -> seconds."""
    if value is None or value == "":
        return default_s
    m = _DURATION.match(value)
    if m:
        secs = int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600}[m.group(2)]
    else:
        try:
            secs = int((now - utc(datetime.fromisoformat(value.replace("Z", "+00:00")))).total_seconds())
        except ValueError:
            raise ApiError(422, "conflict", "window/since must be seconds, Nm, Nh or an RFC 3339 time") from None
    if secs <= 0 or secs > max_s:
        raise ApiError(422, "conflict", f"window/since must be between 1 s and {max_s} s")
    return secs


def register(app: FastAPI, gw: Gateway) -> None:
    mon = MonitoringService(gw)
    app.state.monitoring = mon
    gw.on_startup(mon.start)
    gw.on_shutdown(mon.stop)
    principal = gw.principal
    alerts = NotifyRepository(gw.db)
    streams: dict[str, int] = defaultdict(int)
    streams_lock = threading.Lock()

    def app_entry(app_id: str, request: Request, p: Principal) -> dict:
        if not APP_ID_RE.match(app_id):
            raise ApiError(404, "not_found", "no such app")
        row = next((r for r in app_rows(gw) if r["id"] == app_id), None)
        # §12.6 sharing: an app hidden from this principal in GET /v1/apps does not exist here either.
        if row is None or not all(f(request, p, app_id) for f in gw.app_filters):
            raise ApiError(404, "not_found", "no such app")
        return row

    def kube_or_404():
        if mon.kube is None:
            raise ApiError(404, "not_found", "this box has no Kubernetes API to read from")
        return mon.kube

    # ---- apps ---------------------------------------------------------------------------
    @app.get("/v1/apps/{app_id}", operation_id="apps.get", tags=["apps"], responses=error_responses(401, 404))
    def get_app(app_id: str, request: Request, p: Principal = Depends(principal)):
        row = app_entry(app_id, request, p)
        health, components = mon.app_view(app_id, row["installed"])
        identity = getattr(request.app.state, "identity", None)
        if identity is None:  # no household accounts: owners and adults see every app
            roles, shared = ["owner", "adult"], p.kind == "person" and p.role in ("owner", "adult")
        else:
            roles, shared = identity.shared_roles(app_id), p.kind == "person" and identity.can_open(p, app_id)
        return {
            **row, "node_id": None, "current_revision": None, "health": health, "components": components,
            "backup": None, "access": {"roles": roles, "shared_with_me": shared},
        }

    @app.get("/v1/apps/{app_id}/logs", operation_id="apps.logs", tags=["apps"], response_class=PlainTextResponse,
             responses={200: {"content": {"text/plain": {}, "text/event-stream": {}}},
                        429: {"description": "rate_limited: too many open log streams"},
                        **error_responses(401, 403, 404, 422)})
    def app_logs(
        app_id: str,
        request: Request,
        component: str | None = None,
        since: str | None = None,
        tail: int = Query(default=200, ge=1, le=MAX_TAIL),
        follow: bool = False,
        p: Principal = Depends(principal),
    ):
        if not (p.kind == "person" and p.role in ("owner", "adult")):
            raise ApiError(403, "permission_denied", "only owners and adults read app logs")
        row = app_entry(app_id, request, p)
        if not row["installed"]:
            raise ApiError(404, "not_found", "the app is not installed")
        if component is not None and not _COMPONENT.match(component):
            raise ApiError(422, "conflict", "bad component name")
        since_s = parse_window(since, gw.clock(), 0, 7 * 24 * 3600) if since else None
        kube = kube_or_404()
        ns = f"app-{app_id}"
        pods = kube.pods(ns)
        if pods is None:
            raise ApiError(404, "not_found", "the Kubernetes API is not reachable")
        pods = sorted((x for x in pods if component is None or H.component_of(x) == component),
                      key=lambda x: (x.get("metadata") or {}).get("name", ""))
        if not pods:
            raise ApiError(404, "not_found", "no pods for that component")
        pod = pods[0]["metadata"]["name"]
        gw.events.publish_event("logs", "opened", {"app_id": app_id, "component": component, "tail": tail,
                                                   "follow": follow}, principal=p.as_dict())
        if not follow:
            lines = kube.logs(ns, pod, None, tail, since_s)
            if lines is None:
                raise ApiError(404, "not_found", "could not read the logs")
            return PlainTextResponse("\n".join(redact_lines(lines)) + ("\n" if lines else ""))
        with streams_lock:
            if streams[p.id] >= STREAMS_PER_PRINCIPAL:
                return JSONResponse(status_code=429, headers={"Retry-After": "60"},
                                    content={"error": "rate_limited", "message": "too many open log streams",
                                             "reason": "limit_reached", "retry_after_s": 60})
            streams[p.id] += 1

        def gen():
            r = Redactor()
            try:
                with kube.follow(ns, pod, None, tail, FOLLOW_MAX_S) as lines:
                    for line in lines:
                        yield f"data: {r.line(line)}\n\n"
                yield "event: end\ndata: stream closed\n\n"
            finally:
                with streams_lock:
                    streams[p.id] -= 1

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/v1/apps/{app_id}/metrics", operation_id="apps.metrics", tags=["apps"], responses=error_responses(401, 404))
    def app_metrics(app_id: str, request: Request, p: Principal = Depends(principal)):
        app_entry(app_id, request, p)
        out = {"app_id": app_id, "at": iso(gw.clock()), "components": []}
        if mon.kube is None:
            return out
        ns = f"app-{app_id}"
        pods = mon.kube.pods(ns) or []
        usage = mon.kube.pod_metrics(ns)
        comps: dict[str, dict] = {}
        for pod in pods:
            name = H.component_of(pod)
            c = comps.setdefault(name, {"name": name, "cpu_millicores": None if usage is None else 0.0,
                                        "mem_mb": None if usage is None else 0.0, "restarts": 0})
            c["restarts"] += sum(x["restarts"] for x in H.containers(pod))
            if usage is not None:
                for cpu, mem in usage.get(pod["metadata"]["name"], {}).values():
                    c["cpu_millicores"] = round(c["cpu_millicores"] + (cpu or 0), 1)
                    c["mem_mb"] = round(c["mem_mb"] + (mem or 0), 1)
        out["components"] = sorted(comps.values(), key=lambda c: c["name"])
        return out

    # ---- nodes --------------------------------------------------------------------------
    @app.get("/v1/nodes/{node_id}/metrics", operation_id="nodes.metrics", tags=["nodes"], responses=error_responses(401, 404, 422))
    def node_metrics(node_id: str, window: str | None = None, _: Principal = Depends(principal)):
        now = gw.clock()
        secs = parse_window(window, now, 3600, 24 * 3600)
        samples, source = mon.history.window(node_id, now, secs)
        if not samples and gw.registry.get(node_id) is None:
            raise ApiError(404, "not_found", "no such node")
        return {"node_id": node_id, "source": source, "samples": samples}

    # ---- summary ------------------------------------------------------------------------
    @app.get("/v1/monitoring/summary", operation_id="monitoring.summary", tags=["monitoring"], responses=error_responses(401))
    def summary(_: Principal = Depends(principal)):
        nodes = gw.registry.list()
        counts = {"online": 0, "stale": 0, "offline": 0}
        for n in nodes:
            counts[n["status"]] = counts.get(n["status"], 0) + 1
        apps = {"healthy": 0, "unhealthy": 0, "starting": 0, "stopped": 0, "unknown": 0}
        states = mon.app_states()
        for app_id in mon.installed_apps():
            apps[states.get(app_id, "unknown")] = apps.get(states.get(app_id, "unknown"), 0) + 1
        sev = alerts.open_alert_counts()
        return {
            "nodes": counts, "apps": apps,
            "open_alerts": {"info": sev.get("info", 0), "warning": sev.get("warning", 0), "critical": sev.get("critical", 0)},
            "storage": [{"node_id": n["node_id"], "state": n["storage"].get("state")}
                        for n in nodes if isinstance(n.get("storage"), dict)],
            "at": iso(gw.clock()),
        }
