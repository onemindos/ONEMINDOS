# SPDX-License-Identifier: Apache-2.0
"""Owner recovery with the printed kit at the box's console (gateway permissions design 25c, D-028).

The console routes are not in the OpenAPI, the SDK or the MCP tools: only `onemindd recover-owner` and
`onemind recovery kit` on the box call them, with the console key (identity/kit_recovery.py). The one network
route, POST /v1/auth/recovery/kit/redeem, turns a one-time code made at the console into a short session that may
add a passkey, so a phone can be enrolled after every key was lost.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ..context import Gateway
from ..errors import error_responses
from ..identity.kit_recovery import KitRecovery

ORDER = 265  # after identity (260) and backups (200): it needs both

GROUP = Annotated[str, Field(min_length=4, max_length=4, pattern=r"^[A-Za-z2-7]{4}$")]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KitKeyBody(_Body):
    groups: list[GROUP] = Field(min_length=13, max_length=13)
    check: GROUP


class OwnerBody(_Body):
    user_id: str = Field(min_length=1, max_length=40)


class PasswordBody(OwnerBody):
    password: str = Field(min_length=1, max_length=1024)


class PasskeyBody(OwnerBody):
    credential_id: str = Field(min_length=1, max_length=1024)


class RedeemBody(_Body):
    code: str = Field(min_length=12, max_length=32)
    client: str = Field(default="browser", pattern=r"^(browser|app|cli)$")


def register(app: FastAPI, gw: Gateway) -> None:
    identity = getattr(app.state, "identity", None)
    if identity is None:
        return
    key_file = gw.settings.audit_path.parent / "console-recovery.key"
    kit = KitRecovery(identity, getattr(app.state, "backups", None), key_file)
    app.state.kit_recovery = kit
    gw.on_startup(kit.key)  # the console key exists before anyone stands at the box
    hidden = dict(include_in_schema=False, responses=error_responses(401, 403, 404, 409, 422, 429))

    @app.post("/v1/auth/recovery/kit", **hidden)
    def kit_unlock(body: KitKeyBody, request: Request):
        """The kit key typed at the console: a 15-minute kit session, or a counted wrong try."""
        kit.require_console(request)
        return JSONResponse(content=kit.unlock(body.groups, body.check), headers={"Cache-Control": "no-store"})

    @app.get("/v1/auth/recovery/kit/owners", **hidden)
    def kit_owners(request: Request):
        kit.require_session(request)
        return kit.owners()

    @app.post("/v1/auth/recovery/kit/password", status_code=204, **hidden)
    def kit_password(body: PasswordBody, request: Request):
        kit.require_session(request)
        kit.set_password(body.user_id, body.password)
        return Response(status_code=204)

    @app.post("/v1/auth/recovery/kit/authenticator/clear", status_code=204, **hidden)
    def kit_totp(body: OwnerBody, request: Request):
        kit.require_session(request)
        kit.clear_authenticator(body.user_id)
        return Response(status_code=204)

    @app.post("/v1/auth/recovery/kit/passkeys/remove", status_code=204, **hidden)
    def kit_passkey(body: PasskeyBody, request: Request):
        kit.require_session(request)
        kit.remove_passkey(body.user_id, body.credential_id)
        return Response(status_code=204)

    @app.post("/v1/auth/recovery/kit/sign-in-code", **hidden)
    def kit_code(body: OwnerBody, request: Request):
        kit.require_session(request)
        return JSONResponse(content=kit.sign_in_code(body.user_id), headers={"Cache-Control": "no-store"})

    @app.post("/v1/auth/recovery/kit/redeem", include_in_schema=False, responses=error_responses(401, 422, 429))
    def kit_redeem(body: RedeemBody, request: Request):
        """From any device: a code from the box's console signs its owner in to add a passkey (no other power)."""
        now, src = identity.now(), request.client.host if request.client else "unknown"
        identity.limiter.check(src, now)
        try:
            user = kit.redeem(body.code)
        except Exception:
            identity.limiter.fail(src, now)
            raise
        body_out = identity.start_session(request, user, "kit", None, bearer=body.client != "browser", passkey=False)
        cookies = body_out.pop("_cookies", None)
        resp = JSONResponse(content=body_out, headers={"Cache-Control": "no-store"})
        if cookies:
            common = dict(max_age=cookies["max_age"], secure=identity.cfg.cookie_secure, samesite="strict", path="/")
            resp.set_cookie(identity.cookie, cookies["session"], httponly=True, **common)
            resp.set_cookie(identity.csrf_cookie, cookies["csrf"], httponly=False, **common)
        return resp
