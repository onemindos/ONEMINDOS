# SPDX-License-Identifier: Apache-2.0
"""The Photos switch: GET/PUT /v1/settings/photos (refs #1232, #234).

Photos is built in and on by default. This is the owner's one place to read and change it. It sits
outside /v1/photos because that prefix is closed by the built-in gate while Photos is off.

PUT never changes anything itself: it files the existing `app.disable` / `app.enable` action for the
`photos` built-in app, which waits in Approvals until an owner approves it. Only an owner may ask here.
ONEMIND_PHOTOS_ENABLED=0 is the operator's hard off and cannot be undone from the API.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Response, Security
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..photos import PhotosSettings

APP_ID = "photos"
ORDER = 185  # after the app store (130), which owns the switch and the signed list

register_route_scope("GET,HEAD", r"/v1/settings/photos", ("apps:read",))
register_route_scope("PUT", r"/v1/settings/photos", ("actions:approve",))


_BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description="A gateway token or a signed-in session (contract §3)")
READ = [Security(_BEARER, scopes=["apps:read"])]
WRITE = [Security(_BEARER, scopes=["actions:approve"])]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=120)]


class PhotosSwitch(BaseModel):
    enabled: bool                  # Photos answers requests right now
    owner_switch_on: bool          # the owner's switch (app.enable / app.disable)
    operator_off: bool             # ONEMIND_PHOTOS_ENABLED=0: off for good, not changeable here
    can_change: bool               # an owner may ask to change it
    pending_action_id: str | None = None   # an app.enable / app.disable request waiting in Approvals


class PhotosSwitchBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


def register(app: FastAPI, gw: Gateway) -> None:
    principal = gw.principal
    settings = gw.settings.section(PhotosSettings)

    def state() -> dict:
        owner_on = APP_ID not in gw.disabled_apps()
        pending = None
        for a in gw.repo.list({"requested", "awaiting_approval"}):
            if a.type in ("app.enable", "app.disable") and a.params.get("app_id") == APP_ID \
                    and a.state in ("requested", "awaiting_approval"):
                pending = a.id
                break
        return {"enabled": settings.enabled and owner_on, "owner_switch_on": owner_on,
                "operator_off": not settings.enabled, "can_change": settings.enabled, "pending_action_id": pending}

    @app.get("/v1/settings/photos", tags=["photos"], operation_id="photos.switch.get",
             dependencies=READ,
             response_model=PhotosSwitch, responses=error_responses(401))
    def get_switch(_: Principal = Depends(principal)):
        """Is Photos on? It is on unless the owner switched it off or the operator set ONEMIND_PHOTOS_ENABLED=0."""
        return state()

    @app.put("/v1/settings/photos", tags=["photos"], operation_id="photos.switch.set", status_code=202,
             dependencies=WRITE,
             responses=error_responses(401, 403, 409, 422))
    def put_switch(body: PhotosSwitchBody, response: Response, idempotency_key: IdemKey = None,
                   p: Principal = Depends(principal)):
        """Ask to switch Photos on or off (owner only). Files app.enable or app.disable; it waits in
        Approvals and nothing changes until an owner approves it. Photos data is kept either way."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "change the Photos switch", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not change the Photos switch")
        cur = state()
        if cur["operator_off"]:
            raise ApiError(409, "policy_refused", "Photos is switched off in the box's configuration "
                           "(ONEMIND_PHOTOS_ENABLED=0); an operator has to change that", reason="operator_off")
        if body.enabled == cur["owner_switch_on"]:
            raise ApiError(409, "stale_precondition",
                           f"Photos is already {'on' if body.enabled else 'off'}",
                           reason="already_enabled" if body.enabled else "already_disabled")
        kind = "app.enable" if body.enabled else "app.disable"
        window = 600  # one open request per ten minutes: a double click files it once
        now = gw.clock()
        action, created = gw.actions.request_feature(
            p, kind, {"app_id": APP_ID}, idempotency_key=(f"photos-switch-{idempotency_key}" if idempotency_key
                             else f"photos-switch-{kind}-{int(now.timestamp()) // window}"),
            expires_at=now + timedelta(seconds=window),
            reason=f"owner asked to switch Photos {'on' if body.enabled else 'off'}")
        response.status_code = 202 if created else 200
        return action
