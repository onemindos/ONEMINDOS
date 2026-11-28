# SPDX-License-Identifier: Apache-2.0
"""GET /v1/fabric/events: who connected to the hub's message bus, who was refused (#620, NATS plan N3).

Read-only. The observer (fabricwatch.py) listens to the hub NATS server's own system-account events and
writes `fabric.connect`, `fabric.disconnect` and `fabric.auth_failed` audit lines; this route reads the
newest of them back, for Settings > About ("Security events") and `onemind fabric events`. It needs
`audit:read` (owner and adult), the same as the audit log it reads. Alerts for an unknown key, a removed
key that keeps retrying, a refused sign-in that claims a live key and a flapping machine go to the notification inbox under the `security` topic,
which every person already switches on or off in their notification preferences.

`observer` says whether the box is watching: `watching`, `connecting` (NATS not reachable yet) or `off`
(this box has no observer key, for example an install from before #620: nothing is listed then).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel

from ..agents_nats import agent_users
from ..auditread import can_read_all, glob_any, iter_all_records
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..fabric import FabricRepository
from ..fabricwatch import EVENTS, FabricWatch, SeenKeys
from ..identity.scopes import register_route_scope
from ..natsconf import OBSERVER_SERVICE, load_service_keys
from ..netconf import FabricSettings

ORDER = 343   # after the net router (the fabric routes), whose tables this reads

register_route_scope("GET,HEAD", r"/v1/fabric/events", ("audit:read",))
DEFAULT_COUNT, MAX_COUNT = 50, 200   # `count`, not `limit`: one newest-first window, not a paged list


class FabricEvent(BaseModel):
    seq: int
    ts: str
    event: str
    account: str | None = None
    key: str | None = None
    identity: str | None = None
    client: str | None = None
    name: str | None = None
    cause: str | None = None
    reason: str | None = None
    repeats: int | None = None


class FabricEvents(BaseModel):
    observer: str
    events: list[FabricEvent]


def identities(gw: Gateway, keys_dir: Path | None) -> dict[str, str]:
    """{public nkey: label} for every key the hub accepts right now."""
    out = {s.nkey: f"service:{s.name}" for s in load_service_keys(keys_dir)}
    out.update({n["nats_pubkey"]: f"node:{n['node_id']}" for n in FabricRepository(gw.db).nodes()})
    out.update({a.nkey: a.principal_id for a in agent_users(gw.db)})
    return out


def register(app: FastAPI, gw: Gateway) -> None:
    fab = gw.settings.section(FabricSettings)
    keys_dir = fab.nats_service_keys
    seed = keys_dir / f"{OBSERVER_SERVICE}.nk" if keys_dir is not None else None
    watch = FabricWatch(
        url=gw.settings.nats_url, seed=seed if seed is not None and seed.is_file() else None, audit=gw.audit,
        publish_event=gw.events.publish_event, identities=lambda: identities(gw, keys_dir),
        seen=SeenKeys(gw.db), clock=gw.clock,
    )
    app.state.fabric_watch = watch
    gw.on_startup(watch.start)
    gw.on_shutdown(watch.stop)

    @app.get("/v1/fabric/events", operation_id="fabric.events", tags=["fabric"], response_model=FabricEvents,
             responses=error_responses(401, 403),
             openapi_extra={"security": [{"bearer": ["audit:read"]}]})
    def events(count: int = Query(DEFAULT_COUNT, ge=1, le=MAX_COUNT), p: Principal = Depends(gw.principal)):
        """The newest bus connections, disconnections and refused sign-ins, newest first."""
        if not can_read_all(p):
            raise gw.actions._deny(p, "read the bus security events")
        pattern = ",".join(EVENTS)
        # Read from memory: the audit log is scanned once, the first time, not on every poll.
        newest = watch.recent(count, lambda: (r for r in iter_all_records(gw.settings.audit_path)
                                              if glob_any(pattern, r.get("event"))))
        rows = []
        for rec in newest:
            d = rec.get("data") or {}
            rows.append(FabricEvent(seq=rec["seq"], ts=rec["ts"], event=rec["event"], **{
                k: d.get(k) for k in ("account", "key", "identity", "client", "name", "cause", "reason", "repeats")}))
        return FabricEvents(observer=watch.state, events=rows)
