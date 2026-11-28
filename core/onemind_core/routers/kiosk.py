# SPDX-License-Identifier: Apache-2.0
"""UX-07 (#242 part 2): the owner turns the box's own screen into the full-screen dashboard (kiosk).

GET /v1/instance/kiosk   owner: {enabled, apply}
PUT /v1/instance/kiosk   owner: {enabled} creates or removes the flag file the screen units test

The flag file (ConditionPathExists in onemind-kiosk.service and onemind-screen.service) is the whole
switch, so this is the way an owner reaches it on a box with a locked root account and no SSH. First boot
creates it once on the boards made for a monitor (kiosk on by default, founder decision 2026-11-28). The
gateway user owns /data/onemind/kiosk only; onemind-kiosk.path notices the change and restarts the
screen units, so the gateway holds no privilege to do it. The kiosk browser never holds a token and
the keyboard and mouse on the box stay live: whoever sits at it can sign in through the browser.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody

# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 175

FLAG_ENV = "ONEMIND_KIOSK_FLAG"
DEFAULT_FLAG = "/data/onemind/kiosk/enabled"

# Module level so the scope table knows these routes (#323 rule); the handlers also demand the owner.
register_route_scope("GET,HEAD", r"/v1/instance/kiosk", ("instance:read",))
register_route_scope("PUT", r"/v1/instance/kiosk", ("users:admin",))


class KioskState(BaseModel):
    enabled: bool
    # What happens after a change: the screen switches by itself within seconds.
    apply: str = "The box's own screen switches within a few seconds."


class KioskChange(JsonBody):
    enabled: bool


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    flag = Path(os.environ.get(FLAG_ENV, DEFAULT_FLAG))

    def owner_only(p: Principal, what: str) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not change the box's own screen")

    @app.get("/v1/instance/kiosk", tags=["instance"], operation_id="instance.kiosk.get",
             response_model=KioskState, responses=error_responses(401, 403))
    def get_kiosk(p: Principal = Depends(principal)):
        owner_only(p, "read kiosk mode")
        return KioskState(enabled=flag.exists())

    @app.put("/v1/instance/kiosk", tags=["instance"], operation_id="instance.kiosk.set",
             response_model=KioskState, responses=error_responses(401, 403, 503))
    def set_kiosk(body: KioskChange, p: Principal = Depends(principal)):
        owner_only(p, "change kiosk mode")
        try:
            if body.enabled:
                flag.parent.mkdir(parents=True, exist_ok=True)
                flag.write_text("on\n")
            else:
                flag.unlink(missing_ok=True)
        except OSError as e:
            raise ApiError(503, "unavailable", f"kiosk mode cannot be changed on this box: {e.strerror}") from e
        gw.audit.append("kiosk.set", p.as_dict(), None, {"enabled": body.enabled})
        return KioskState(enabled=flag.exists())
