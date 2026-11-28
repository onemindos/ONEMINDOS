# SPDX-License-Identifier: Apache-2.0
"""The hub's time zone and clock (P-04), from the host service.

- GET /v1/system/time: the zone and whether the clock is set from a time server (`timedatectl show` and
  `show-timesync`, read by `onemindd host serve`). Owner only, read only. `available` is false, with a
  reason, when the host service cannot be reached.
- POST /v1/system/time/zone: files a system.set_timezone action. An owner or an agent may ask; only an owner
  approves. The root is read-only, so the host keeps the zone on /data (a symlink the image points
  /etc/localtime at): it applies at once, survives a reboot and survives an A/B update (internal/host/timezone.go).
  A zone name this box has no zone file for is refused before anything is filed.

Every host field is checked again here (H-06): a value that fails its check is null, never shown.
"""

from __future__ import annotations

import functools
import re
import uuid
import zoneinfo
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..executors import ExecResult
from ..identity.scopes import register_route_scope
from ..storage import StorageTimeout, StorageUnavailable

ORDER = 341
ACTION = "system.set_timezone"
REQUESTERS = frozenset({"agent"})  # besides the owner; an agent asks, only an owner approves
REQUEST_TTL = timedelta(hours=24)
HOST_SCHEMA = "onemind.host.time/v1"
# Same shape the host enforces (internal/host/timezone.go ZoneName): Europe/Berlin, UTC, Etc/GMT+5.
ZONE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){0,2}$")
# tzdata helper entries that are not zones (localtime links back to /etc/localtime); same list as the host.
NOT_ZONES = frozenset({"localtime", "posixrules", "Factory"})
SERVER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,252}$")

register_route_scope("GET,HEAD", r"/v1/system/time", ("system:admin",))
register_route_scope("POST", r"/v1/system/time/zone", ("actions:request",))


def zone_name(v: Any) -> bool:
    return (isinstance(v, str) and len(v) <= 64 and bool(ZONE_RE.fullmatch(v))
            and not v.startswith(("posix/", "right/")) and v not in NOT_ZONES)


class TimeView(BaseModel):
    """GET /v1/system/time."""

    model_config = ConfigDict(extra="forbid")
    available: bool
    reason: Literal["host_service_unreachable", "host_service_error", "bad_response"] | None = None
    message: str | None = None
    zone: str | None = Field(default=None, description="IANA zone name, e.g. Europe/Berlin; null when the box names none")
    ntp_enabled: bool | None = Field(default=None, description="The box is asked to keep its clock from the network (timedatectl NTP)")
    ntp_synchronized: bool | None = Field(default=None, description="The clock is currently set from a time server (timedatectl NTPSynchronized)")
    server: str | None = Field(default=None, description="The time server systemd-timesyncd talked to last; null before it reached one")
    stratum: int | None = Field(default=None, ge=0, le=16)
    last_sync_at: datetime | None = Field(default=None, description="When systemd-timesyncd last set the clock")
    at: datetime | None = Field(default=None, description="The hub's own clock now")
    problem: str | None = Field(default=None, description="Why the clock state could not be read (the zone is still given)")


class SetZoneRequest(BaseModel):
    """POST /v1/system/time/zone."""

    model_config = ConfigDict(extra="forbid")
    zone: str = Field(min_length=1, max_length=64, description="IANA time zone name, e.g. Europe/Berlin")
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


def parse_time(body: Any, now: datetime) -> TimeView:
    if not isinstance(body, dict) or body.get("schema") != HOST_SCHEMA:
        return TimeView(available=False, reason="bad_response", at=now,
                        message="the host service sent something the gateway does not understand")
    flag = lambda k: body[k] if isinstance(body.get(k), bool) else None  # noqa: E731
    server = body.get("server")
    stratum = body.get("stratum")
    last = None
    try:
        last = datetime.fromisoformat(str(body.get("last_sync_at")).replace("Z", "+00:00")) if body.get("last_sync_at") else None
    except ValueError:
        pass
    problem = body.get("problem")
    return TimeView(
        available=True, at=now, zone=body["zone"] if zone_name(body.get("zone")) else None,
        ntp_enabled=flag("ntp_enabled"), ntp_synchronized=flag("ntp_synchronized"),
        server=server if isinstance(server, str) and SERVER_RE.fullmatch(server) else None,
        stratum=stratum if isinstance(stratum, int) and not isinstance(stratum, bool) and 0 <= stratum <= 16 else None,
        last_sync_at=last, problem=problem[:200] if isinstance(problem, str) and problem else None)


@functools.lru_cache(maxsize=1)
def _zones() -> frozenset[str]:
    """The zone database's names, read once (each call to available_timezones walks the whole tree)."""
    return frozenset(zoneinfo.available_timezones())


def known_zone(zone: str) -> bool:
    """Does this machine's zone database know the name? With no database at all (a bare container) the host
    decides, so this says yes."""
    zones = _zones()
    return not zones or zone in zones


def register(app: FastAPI, gw: Gateway) -> None:
    def deny(p: Principal, what: str, msg: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", msg)

    def run(a, finish) -> None:
        link = app.state.hostlink
        why = link.problem(ACTION)
        if why is not None:
            finish(ExecResult("failed", why[1], steps=[{"step": "host", "result": why[0]}]))
            return
        link.run(a, finish)

    def recheck(a) -> str | None:
        why = app.state.hostlink.problem(ACTION)
        return why[1] if why else None

    gw.actions.register_type(ACTION, FeatureAction("actuate", run, REQUESTERS, check=recheck))

    @app.get("/v1/system/time", tags=["system"], operation_id="system.time.get", response_model=TimeView,
             responses=error_responses(401, 403),
             openapi_extra={"security": [{"bearer": ["system:admin"]}]})
    def system_time(p: Principal = Depends(gw.principal)) -> TimeView:
        """The hub's time zone and whether its clock is set from a time server (read only, owner only).

        `available` is false, with a reason, when the host service cannot be reached; a field the clock
        did not report is null, never guessed."""
        if not p.is_owner:
            raise deny(p, "read the clock", "only an owner may see the clock settings of this box")
        now = gw.clock()
        try:
            status, body = app.state.hostlink.client.call("GET", "/v1/time")
        except (StorageUnavailable, StorageTimeout):
            return TimeView(available=False, reason="host_service_unreachable", at=now,
                            message="the host service is not reachable from the gateway, so the clock cannot be read yet")
        if status != 200:
            return TimeView(available=False, reason="host_service_error", at=now, message=f"the host service answered {status}")
        return parse_time(body, now)

    @app.post("/v1/system/time/zone", tags=["system"], operation_id="system.time.set_zone", status_code=202, response_model=Action,
              responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 409, 422, 429)},
              openapi_extra={"security": [{"bearer": ["actions:request"]}]})
    def system_set_zone(req: SetZoneRequest, p: Principal = Depends(gw.principal),
                        idem: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)] = None):
        """Ask for a new time zone. It waits for the owner, who approves it; the response is the action, whose id
        is the approval to look for. An agent may ask, never approve.

        422 for a name that is not a time zone; 409 unknown_zone for a name this box has no zone file for;
        409 host_unavailable while the host service cannot set it (nothing is filed). The `Idempotency-Key`
        header (or the body's `idempotency_key`) makes a retry replay the same action."""
        if not p.can_request_actions or not (p.is_owner or p.kind in REQUESTERS):
            raise deny(p, f"request {ACTION}", "only an owner or an agent may ask for a time zone change")
        if not zone_name(req.zone):
            raise ApiError(422, "conflict", "zone must be an IANA time zone name such as Europe/Berlin")
        if not known_zone(req.zone):
            raise ApiError(409, "conflict", f"this box does not know the time zone {req.zone}", reason="unknown_zone")
        why = app.state.hostlink.problem(ACTION)
        if why is not None:
            raise ApiError(409, "conflict", why[1], reason="host_unavailable")
        body, created = gw.actions.request_feature(
            p, ACTION, {"zone": req.zone}, idempotency_key=idem or req.idempotency_key or f"time:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=req.reason, pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body, headers={"Location": f"/v1/actions/{body['id']}"})
