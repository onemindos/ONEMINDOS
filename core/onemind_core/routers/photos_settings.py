# SPDX-License-Identifier: Apache-2.0
"""The Photos switch: GET/PUT /v1/settings/photos (refs #1232, #234).

Photos is built in and on by default. This is the owner's one place to read and change it. It sits
outside /v1/photos because that prefix is closed by the built-in gate while Photos is off.

PUT never changes anything itself: it files the existing `app.disable` / `app.enable` action for the
`photos` built-in app, which waits in Approvals until an owner approves it. Only an owner may ask here.
ONEMIND_PHOTOS_ENABLED=0 is the operator's hard off and cannot be undone from the API.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from threading import Lock
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Response, Security
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict

from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope, within
from ..identity.service import ctx_of
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
PENDING = {"requested", "awaiting_approval"}


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
    # The hub runs one gateway process. Serialize the pending lookup and request
    # insert across its concurrent HTTP handlers.
    request_lock = Lock()

    def pending_request():
        now = gw.clock()
        for action in gw.repo.list(PENDING):
            if (action.type in ("app.enable", "app.disable") and action.params.get("app_id") == APP_ID
                    and action.expires_at > now):
                return action
        return None

    @app.get("/v1/settings/photos", tags=["photos"], operation_id="photos.switch.get",
             dependencies=READ,
             response_model=PhotosSwitch, responses=error_responses(401, 404))
    def get_switch(request: Request, p: Principal = Depends(principal)):
        """Is Photos on? Pending approval details require an owner credential with approval permission."""
        if not all(f(request, p, APP_ID) for f in gw.app_filters):
            raise ApiError(404, "not_found", "no such app")
        ctx = ctx_of(request)
        may_request = p.is_owner and (ctx is None or within("actions:approve", ctx.scopes))
        owner_on = APP_ID not in gw.disabled_apps()
        pending = pending_request() if may_request else None
        return PhotosSwitch(enabled=settings.active and owner_on, owner_switch_on=owner_on,
                            operator_off=not settings.active, can_change=settings.active and may_request,
                            pending_action_id=pending.id if pending else None)

    @app.put("/v1/settings/photos", tags=["photos"], operation_id="photos.switch.set", status_code=202,
             dependencies=WRITE, response_model=Action,
             responses={**error_responses(401, 403, 409, 422),
                        200: {"model": Action, "description": "A matching request is already open, or replaying the "
                              "Idempotency-Key that filed an action returned it in its current state. "
                              "No new request was filed."}})
    def put_switch(body: PhotosSwitchBody, response: Response, idempotency_key: IdemKey = None,
                   p: Principal = Depends(principal)):
        """Ask to switch Photos on or off (owner only). Files app.enable or app.disable; it waits in
        Approvals and nothing changes until an owner approves it. Photos data is kept either way."""
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None,
                            {"attempted": "change the Photos switch", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not change the Photos switch")
        kind = "app.enable" if body.enabled else "app.disable"
        direction = "on" if body.enabled else "off"
        key = f"photos-switch-{idempotency_key or uuid.uuid4().hex}"
        with request_lock:
            # A replay takes precedence over current state, including a newer pending request.
            # Let the action service validate that the key belongs to this caller and request.
            if not (idempotency_key and gw.repo.get_by_idempotency_key(key)):
                if not settings.active:
                    raise ApiError(409, "policy_refused", "Photos is switched off in the box's configuration "
                                   "(ONEMIND_PHOTOS_ENABLED=0); an operator has to change that", reason="operator_off")
                if pending := pending_request():
                    if pending.type == kind:
                        response.status_code = 200
                        return pending.to_json()
                    raise ApiError(409, "stale_precondition",
                                   f"a request to switch Photos {'off' if body.enabled else 'on'} is already "
                                   f"waiting in Approvals ({pending.id}); decide it first",
                                   reason="request_pending")
                if body.enabled == (APP_ID not in gw.disabled_apps()):
                    raise ApiError(409, "stale_precondition", f"Photos is already {direction}",
                                   reason=f"already_{'enabled' if body.enabled else 'disabled'}")
            action, created = gw.actions.request_feature(
                p, kind, {"app_id": APP_ID}, idempotency_key=key,
                expires_at=gw.clock() + timedelta(minutes=10),
                reason=f"owner asked to switch Photos {direction}")
            response.status_code = 202 if created else 200
            return action
