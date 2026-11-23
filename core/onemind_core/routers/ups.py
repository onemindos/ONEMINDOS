# SPDX-License-Identifier: Apache-2.0
"""IMG-06 (#244): GET /v1/system/ups, the UPS battery for Settings > About and the dashboard.

The image runs NUT for a UPS plugged into the box by USB (onemind-ups.service: the driver and upsd, on loopback
only; onemind-ups-monitor.service shuts the box down in order on a low battery). This route only reads: it asks
upsd for the variables of the UPS named `onemind` with NUT's plain-text protocol (LIST VAR, no login needed for
reads) and turns them into a few plain fields. No upsd on the box (no UPS was found at boot) is not an error:
the answer says present=false. It never sends a command to the UPS.
"""

from __future__ import annotations

import os
import socket
from typing import Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope

ORDER = 342  # after services (341): the system read routes sit together

ADDR_ENV = "ONEMIND_UPS_ADDR"
DEFAULT_ADDR = "127.0.0.1:3493"  # upsd.conf in /data/onemind/ups (onemind_ups.py render)
UPS = "onemind"
TIMEOUT = 2.0
MAX_BYTES = 64 * 1024

# Device health, like the facts /v1/os/about shows: the same scope reads it (a child has no nodes:read).
register_route_scope("GET,HEAD", r"/v1/system/ups", ("nodes:read",))

State = Literal["none", "online", "on_battery", "low_battery", "unknown"]


class UpsStatus(BaseModel):
    present: bool
    # none: no UPS on this box; online: on mains; on_battery: the power is out; low_battery: the box is about to
    # shut down cleanly; unknown: a UPS is set up but its driver gives no fresh data.
    state: State
    # NUT's raw status flags (OL, OB, LB, CHRG, ...), for the technical details.
    flags: list[str] = []
    battery_percent: int | None = None
    runtime_seconds: int | None = None
    load_percent: int | None = None
    model: str | None = None


def _num(v: str | None) -> int | None:
    try:
        return round(float(v)) if v is not None else None
    except ValueError:
        return None


def read_vars(addr: str) -> dict[str, str] | None:
    """The UPS's variables from upsd, {} when upsd answers with an error, None when nothing listens."""
    host, _, port = addr.rpartition(":")
    try:
        with socket.create_connection((host.strip("[]"), int(port)), timeout=TIMEOUT) as s:
            s.settimeout(TIMEOUT)
            s.sendall(f"LIST VAR {UPS}\n".encode())
            buf = b""
            while not (buf.startswith(b"ERR") and b"\n" in buf) and f"END LIST VAR {UPS}\n".encode() not in buf:
                chunk = s.recv(4096)
                if not chunk or len(buf) > MAX_BYTES:
                    break
                buf += chunk
    except (OSError, ValueError):
        return None
    out: dict[str, str] = {}
    for line in buf.decode("utf-8", "replace").splitlines():
        parts = line.split(" ", 3)
        if len(parts) == 4 and parts[0] == "VAR" and parts[1] == UPS:
            out[parts[2]] = parts[3].strip().strip('"').replace('\\"', '"')
    return out


def status(addr: str) -> UpsStatus:
    found = read_vars(addr)
    if found is None:
        return UpsStatus(present=False, state="none")
    flags = found.get("ups.status", "").split()
    if "LB" in flags or "FSD" in flags:
        state: State = "low_battery"
    elif "OB" in flags:
        state = "on_battery"
    elif "OL" in flags:
        state = "online"
    else:
        state = "unknown"
    model = " ".join(x for x in (found.get("device.mfr") or found.get("ups.mfr"),
                                 found.get("device.model") or found.get("ups.model")) if x) or None
    return UpsStatus(present=True, state=state, flags=flags, battery_percent=_num(found.get("battery.charge")),
                     runtime_seconds=_num(found.get("battery.runtime")), load_percent=_num(found.get("ups.load")),
                     model=model)


def register(app: FastAPI, gw: Gateway) -> None:
    @app.get("/v1/system/ups", tags=["system"], operation_id="system.ups", response_model=UpsStatus,
             responses=error_responses(401, 403))
    def system_ups(_: Principal = Depends(gw.principal)):
        """The UPS plugged into this box: on mains or battery, charge, minutes left, load. present=false when
        the box has no UPS. Read only; the box shuts itself down in order on a low battery."""
        return status(os.environ.get(ADDR_ENV, DEFAULT_ADDR))
