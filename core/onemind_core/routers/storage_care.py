# SPDX-License-Identifier: Apache-2.0
"""Storage housekeeping (P-10): TRIM status, smartd warnings and safely removing a USB drive.

- GET /v1/storage/housekeeping: when the weekly TRIM last ran and runs next, what smartd has warned about,
  and the removable drives. Owner only. The facts come from the host service (`onemindd host serve`, root),
  checked field by field again here (H-06).
- POST /v1/storage/removable/{name}/eject: files a storage.eject action for one removable drive. An owner or
  an agent may ask; only an owner approves (no passkey: it changes no access, only unmounts a drive the owner
  names). The host checks again that the drive is removable and that the box is not using it.
- smartd's warnings reach Notifications: a background pass reads the host's list and raises one
  `storage.smart.*` event per new warning (notify/catalogue.py), never twice.
"""

from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..executors import ExecResult
from ..hostservices import CONTROL_RE, HostServicesClient
from ..identity.scopes import register_route_scope
from ..netconf import NetSettings
from ..storage import StorageTimeout, StorageUnavailable

# Right after routers/storage.py (310): it owns app.state.storage, whose observation table this reads.
ORDER = 311
ACTION = "storage.eject"
PATH = "/v1/storage/housekeeping"
REQUESTERS = frozenset({"agent"})  # besides the owner; an agent asks, only an owner approves
REQUEST_TTL = timedelta(hours=24)
POLL_S = 60
FIRST_S = 5  # the first pass waits a moment: the host service may still be starting
MAX_ALERTS = 50
MAX_DRIVES = 32
SERIAL_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
DEVICE_RE = re.compile(r"^/dev/[a-z][a-z0-9]{1,15}$")
NAME_RE = re.compile(r"^[a-z][a-z0-9]{1,15}$")
ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
CRITICAL_KINDS = frozenset({"Health", "FailedHealthCheck"})
log = logging.getLogger("onemind.storage_care")

register_route_scope("GET,HEAD", r"/v1/storage/housekeeping", ("system:admin",))
register_route_scope("POST", r"/v1/storage/removable/[^/]+/eject", ("actions:request",))


class Trim(BaseModel):
    enabled: bool = Field(description="fstrim.timer is enabled (the image enables it)")
    timer_state: str = Field(description="systemd state of the timer: active, inactive or unknown")
    last_run_at: datetime | None = Field(description="When the last TRIM finished; null: it has not run on this box yet")
    last_result: str | None = Field(default=None, description="systemd's result of that run, e.g. success")
    last_trimmed_bytes: int | None = Field(description="How much the last run told the SSD it may reuse; null when not reported")
    next_run_at: datetime | None = Field(description="When the timer runs next; null when it has none")


class SmartAlert(BaseModel):
    id: str
    at: datetime
    device: str
    kind: str = Field(description="smartd's warning type, e.g. Health, Temperature, FailedHealthCheck")
    message: str


class Smart(BaseModel):
    daemon_state: str = Field(description="state of smartd: active, inactive (a virtual machine has no disk to watch) or unknown")
    alerts: list[SmartAlert] = Field(description="Warnings smartd raised, newest first")


class Removable(BaseModel):
    device: str = Field(description="Device path, e.g. /dev/sdb")
    name: str = Field(description="The path segment for the eject route, e.g. sdb")
    model: str | None = None
    serial: str | None = Field(default=None, description="The drive's own serial number when it reports one; the eject is bound to it")
    size_bytes: int
    label: str | None = None
    mountpoints: list[str]
    partitions: int
    ejectable: bool = Field(description="false while the box is using the drive; why_not says why")
    why_not: str | None = None


class Housekeeping(BaseModel):
    """GET /v1/storage/housekeeping."""

    available: bool
    message: str | None = Field(default=None, description="Why nothing is shown when the host service cannot be read")
    trim: Trim | None = None
    smart: Smart | None = None
    removable: list[Removable] = []
    at: datetime | None = None


class EjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def _text(v, hi: int) -> str:
    if not isinstance(v, str) or len(v) > hi or CONTROL_RE.search(v):
        raise ValueError("bad text")
    return v


def parse(d) -> Housekeeping:
    """The host's answer, checked. Raises ValueError (or pydantic's) on anything odd; the caller then says unavailable."""
    if not isinstance(d, dict):
        raise ValueError("not an object")
    t, sm = d.get("trim"), d.get("smart")
    if not isinstance(t, dict) or not isinstance(sm, dict) or not isinstance(sm.get("alerts"), list) or not isinstance(d.get("removable"), list):
        raise ValueError("missing part")
    alerts = []
    for a in sm["alerts"][:MAX_ALERTS]:
        if not isinstance(a, dict) or not ID_RE.fullmatch(str(a.get("id"))) or not DEVICE_RE.fullmatch(str(a.get("device"))):
            continue  # one odd warning never hides the rest
        alerts.append(SmartAlert(id=a["id"], at=a["at"], device=a["device"], kind=_text(a.get("kind"), 64), message=_text(a.get("message"), 400)))
    drives = []
    for r in d["removable"][:MAX_DRIVES]:
        dev = r.get("device") if isinstance(r, dict) else None
        if not isinstance(dev, str) or not DEVICE_RE.fullmatch(dev) or not isinstance(r.get("mountpoints"), list):
            continue
        mounts = [_text(m, 200) for m in r["mountpoints"][:16]]
        ok = r.get("ejectable") is True
        drives.append(Removable(
            device=dev, name=dev.removeprefix("/dev/"), serial=r["serial"] if isinstance(r.get("serial"), str) and SERIAL_RE.fullmatch(r["serial"]) else None, model=_text(r["model"], 80) if r.get("model") else None, size_bytes=r["size_bytes"],
            label=_text(r["label"], 64) if r.get("label") else None, mountpoints=mounts, partitions=int(r.get("partitions") or 0),
            ejectable=ok, why_not=None if ok else _text(r.get("why_not") or "the box is using this drive", 200)))
    return Housekeeping(
        available=True, at=d.get("at"),
        trim=Trim(enabled=t["enabled"], timer_state=_text(t.get("timer_state", "unknown"), 32), last_run_at=t.get("last_run_at"),
                  last_result=_text(t["last_result"], 32) if t.get("last_result") else None,
                  last_trimmed_bytes=t.get("last_trimmed_bytes"), next_run_at=t.get("next_run_at")),
        smart=Smart(daemon_state=_text(sm.get("daemon_state", "unknown"), 32), alerts=alerts), removable=drives)


def read(client: HostServicesClient) -> Housekeeping:
    try:
        status, body = client.fetch(PATH)
    except (StorageUnavailable, StorageTimeout):
        return Housekeeping(available=False, message="The host service cannot be reached, so TRIM, disk warnings and drives cannot be read.")
    if status != 200:
        return Housekeeping(available=False, message=f"The host service answered {status}.")
    try:
        return parse(body)
    except (ValueError, TypeError, KeyError) as exc:
        log.warning("host housekeeping answer rejected: %s", exc)
        return Housekeeping(available=False, message="The host service sent something this version cannot read.")


def alert_event(a: SmartAlert, node_id: str) -> tuple[str, str]:
    return ("smart.failing", "critical") if a.kind in CRITICAL_KINDS else ("smart.warning", "warning")


def register(app: FastAPI, gw: Gateway) -> None:
    cfg = gw.settings.section(NetSettings)
    client = HostServicesClient(str(cfg.host_socket), cfg.host_timeout_s)
    stop = threading.Event()

    def deny(p: Principal, what: str, msg: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", msg)

    def recheck(a) -> str | None:
        view = read(client)
        if not view.available:
            return view.message
        d = next((r for r in view.removable if r.device == (a.params or {}).get("device")), None)
        if d is None:
            return "that drive is no longer plugged in"
        want = (a.params or {}).get("serial")
        if want and d.serial != want:
            return "that is not the drive you were asked about (it was swapped or replugged)"
        return None if d.ejectable else (d.why_not or "the box is using that drive")

    def run(a, finish) -> None:
        link = app.state.hostlink
        why = link.problem(ACTION)
        if why is not None:
            finish(ExecResult("failed", why[1], steps=[{"step": "host", "result": why[0]}]))
            return
        link.run(a, finish)

    gw.actions.register_type(ACTION, FeatureAction("actuate", run, REQUESTERS, check=recheck))

    @app.get("/v1/storage/housekeeping", tags=["storage"], operation_id="storage.housekeeping", response_model=Housekeeping,
             responses=error_responses(401, 403), openapi_extra={"security": [{"bearer": ["system:admin"]}]})
    def storage_housekeeping(p: Principal = Depends(gw.principal)) -> Housekeeping:
        """When the weekly TRIM last ran and runs next, smartd's warnings, and the USB drives that can be safely
        removed. `available` is false, with a plain reason, when the host service cannot be read. Owner only."""
        if not p.is_owner:
            raise deny(p, "read storage housekeeping", "only an owner may see the drives and disk warnings on this box")
        return read(client)

    @app.post("/v1/storage/removable/{name}/eject", tags=["storage"], operation_id="storage.removable.eject", status_code=202,
              response_model=Action, responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 404, 409, 422, 429)},
              openapi_extra={"security": [{"bearer": ["actions:request"]}]})
    def storage_eject(name: str, req: EjectRequest | None = None, p: Principal = Depends(gw.principal),
                      idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Ask to safely remove one USB drive (name from the housekeeping list, e.g. `sdb`). It waits for the owner
        to approve it; the response is the action. 404 for a drive that is not plugged in or not removable; 409
        `in_use` while the box is using it, `host_unavailable` while the host service cannot be reached."""
        req = req or EjectRequest()
        if not p.can_request_actions or not (p.is_owner or p.kind in REQUESTERS):
            raise deny(p, f"request {ACTION}", "only an owner or an agent may ask to remove a drive")
        if not NAME_RE.fullmatch(name):
            raise ApiError(404, "not_found", "no removable drive with that name")
        view = read(client)
        if not view.available:
            raise ApiError(409, "conflict", view.message or "the host service is not reachable", reason="host_unavailable")
        drive = next((r for r in view.removable if r.name == name), None)
        if drive is None:
            raise ApiError(404, "not_found", "no removable drive with that name is plugged in")
        if not drive.ejectable:
            raise ApiError(409, "conflict", drive.why_not or "the box is using that drive", reason="in_use")
        why = app.state.hostlink.problem(ACTION)
        if why is not None:
            raise ApiError(409, "conflict", why[1], reason="host_unavailable")
        body, created = gw.actions.request_feature(
            p, ACTION, {"device": drive.device, **({"serial": drive.serial} if drive.serial else {})}, idempotency_key=idem or req.idempotency_key or f"eject:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=req.reason, pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body, headers={"Location": f"/v1/actions/{body['id']}"})

    # ---- smartd warnings -> Notifications --------------------------------------------------------------
    def poll() -> int:
        """One pass: raise an event for each warning not told before. Returns how many."""
        view = read(client)
        if not view.available or view.smart is None:
            return 0
        repo = app.state.storage.repo
        seen = repo.observations()
        told = 0
        node_id = app.state.storage.node_id
        for a in reversed(view.smart.alerts):  # oldest first, so the inbox reads in order
            key = f"smartd:{a.id}"
            if key in seen:
                continue
            kind, sev = alert_event(a, node_id)
            gw.events.publish_event(
                "storage", kind, {"node_id": node_id, "alert_id": a.id, "device": a.device, "smart_kind": a.kind, "message": a.message},
                severity=sev, resource={"kind": "storage_set", "id": node_id}, dedupe_key=f"storage:{node_id}:smartd:{a.id}")
            repo.observe(key, "told", gw.clock())
            told += 1
        return told

    def loop() -> None:
        stop.wait(FIRST_S)
        while not stop.is_set():
            try:
                poll()
            except Exception:
                log.exception("smartd warning pass failed")
            stop.wait(POLL_S)

    app.state.storage_care_poll = poll
    def start() -> None:  # the app may start more than once (tests enter it twice): a fresh thread each time
        stop.clear()
        threading.Thread(target=loop, name="storage-care", daemon=True).start()

    gw.on_startup(start)
    gw.on_shutdown(stop.set)
