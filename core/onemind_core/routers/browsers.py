# SPDX-License-Identifier: Apache-2.0
"""Browser windows with a per-person profile (#692; browsers.py has the model).

- POST   /v1/browsers/{app_id}/session        create (first time) and start the caller's own browser pod;
                                               answers the URL of their browser host
- POST   /v1/browsers/{app_id}/session/close  stop the caller's pod; the profile stays
- POST   /v1/browsers/{app_id}/profile/reset  file browser.profile.reset for the caller's profile; it runs
                                               only after an owner approves it

Only a signed-in person, through a session (a static v0 person token counts), may call these: an
agent, plugin or automation principal and any API token get 403, so no token can open a person's
browser. The person never names whose browser: the key is always derived from the caller.
Sets app.state.browsers before routers/net.py builds the app proxy, which serves the browser host.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..apimodels import Action
from ..auth import Principal
from ..browsers import (
    RESET_ACTION, BrowserError, BrowserProfiles, BrowserSpec, ResetHandler, browser_spec, host_label, person_key,
    profile_claim,
)
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..netconf import NetSettings
from ..proxy import ACCESS_LEVELS, DEFAULT_ACCESS, allowed

ORDER = 266  # after identity (scopes, sessions); before net (270), whose app proxy reads app.state.browsers
register_route_scope("POST", r"/v1/browsers/[^/]+/session(/close)?", ("apps:read",))
register_route_scope("POST", r"/v1/browsers/[^/]+/profile/reset", ("apps:read",))
RESET_TTL = timedelta(days=1)


class BrowserSession(BaseModel):
    app_id: str
    person_key: str = Field(description="One-way key of the signed-in person's profile; names their pod and host")
    url: str = Field(description="The person's browser host, served by the gateway proxy to this person only")
    profile: str = Field(description="Name of the person's profile volume claim")
    state: Literal["starting", "stopped"] = Field(description="starting: the pod is being started; stopped: closed, the profile kept")


def register(app: FastAPI, gw: Gateway) -> None:
    net = gw.settings.section(NetSettings)
    profiles = BrowserProfiles(gw.settings.kubectl)
    app.state.browsers = profiles

    def spec_of(app_id: str) -> BrowserSpec | None:
        entry = gw.catalog.get(app_id)
        return browser_spec(entry.manifest) if entry is not None else None

    gw.actions.register_handler(RESET_ACTION, ResetHandler(profiles, lambda a: spec_of(a) is not None))
    principal = gw.principal

    def deny(p: Principal, what: str) -> ApiError:
        gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        return ApiError(403, "permission_denied", "only a signed-in person opens their own browser")

    def caller(request: Request, p: Principal, app_id: str, what: str) -> tuple[BrowserSpec, str]:
        """(the app's browser spec, the caller's profile key), or the refusal."""
        ctx = ctx_of(request)
        if p.kind != "person" or (ctx is not None and ctx.session is None):
            raise deny(p, what)
        spec = spec_of(app_id)
        state = gw.repo.get_app_state(app_id)
        if spec is None or not all(f(request, p, app_id) for f in list(gw.app_filters)):
            raise ApiError(404, "not_found", "no such browser app")
        if state is None or state.status != "installed":
            raise ApiError(409, "conflict", f"{app_id} is not installed and running")
        web = (gw.catalog.get(app_id).manifest.get("spec") or {}).get("web") or {}
        access = web.get("access") if web.get("access") in ACCESS_LEVELS else DEFAULT_ACCESS
        if not allowed(p, access):
            raise deny(p, what)
        return spec, person_key(p.id)

    def url_for(request: Request, app_id: str, key: str) -> str:
        label = host_label(app_id, key)
        if label is None:
            raise ApiError(409, "conflict", "the app id is too long for a browser host name")
        host = (request.headers.get("host") or "").split(":", 1)[0].lower()
        domains = net.box_domains()
        domain = next((d for d in domains if host == d or host.endswith("." + d)), domains[0])
        return f"{'https' if net.tls else 'http'}://{label}.{domain}/"

    @app.post("/v1/browsers/{app_id}/session", operation_id="browsers.session_open", tags=["browsers"],
              response_model=BrowserSession, responses=error_responses(401, 403, 404, 409, 503))
    def open_session(app_id: str, request: Request, p: Principal = Depends(principal)):
        """Open the caller's own browser: their profile is created the first time and kept after."""
        spec, key = caller(request, p, app_id, "open a browser")
        url = url_for(request, app_id, key)
        try:
            profiles.open(app_id, key, spec)
        except BrowserError as exc:
            raise ApiError(503, "unavailable", f"the browser could not be started: {exc}") from exc
        gw.audit.append("browser.session.opened", p.as_dict(), None, {"app_id": app_id, "person_key": key})
        return JSONResponse(BrowserSession(app_id=app_id, person_key=key, url=url, profile=profile_claim(key),
                                           state="starting").model_dump(), headers={"Cache-Control": "no-store"})

    @app.post("/v1/browsers/{app_id}/session/close", operation_id="browsers.session_close", tags=["browsers"],
              response_model=BrowserSession, responses=error_responses(401, 403, 404, 409, 503))
    def close_session(app_id: str, request: Request, p: Principal = Depends(principal)):
        """Stop the caller's browser pod. The profile stays for the next open."""
        _, key = caller(request, p, app_id, "close a browser")
        url = url_for(request, app_id, key)
        try:
            profiles.close(app_id, key)
        except BrowserError as exc:
            raise ApiError(503, "unavailable", f"the browser could not be stopped: {exc}") from exc
        gw.audit.append("browser.session.closed", p.as_dict(), None, {"app_id": app_id, "person_key": key})
        return JSONResponse(BrowserSession(app_id=app_id, person_key=key, url=url, profile=profile_claim(key),
                                           state="stopped").model_dump(), headers={"Cache-Control": "no-store"})

    @app.post("/v1/browsers/{app_id}/profile/reset", operation_id="browsers.profile_reset", tags=["browsers"],
              status_code=202, response_model=Action, responses=error_responses(401, 403, 404, 409))
    def reset_profile(app_id: str, request: Request, p: Principal = Depends(principal)):
        """Ask to erase the caller's profile. Nothing is erased until an owner approves it in Approvals."""
        _, key = caller(request, p, app_id, "reset a browser profile")
        action = gw.actions.file(RESET_ACTION, {"app_id": app_id, "person_key": key}, p.as_dict(),
                                 expires_at=gw.clock() + RESET_TTL, idempotency_key=f"browser-reset-{uuid.uuid4().hex}",
                                 audit_principal=p.as_dict())
        return JSONResponse(status_code=202, content=action.to_json())
