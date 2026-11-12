# SPDX-License-Identifier: Apache-2.0
"""Contract §12.6: sign-in, sessions, passkeys, users, API tokens, per-app sharing, /v1/me, and
§12.4 approve-options. Logic is in identity/service.py; docs/leap/core/IDENTITY.md explains it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity import IdentityService, ctx_of

SIGNIN_HTML = Path(__file__).resolve().parent.parent / "identity" / "signin.html"


class LoginBody(BaseModel):
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=1024)
    totp: str | None = Field(default=None, max_length=12)
    passkey: dict[str, Any] | None = None
    # browser → HttpOnly cookie + CSRF token; cli/app → bearer access + refresh token
    client: Literal["browser", "cli", "app"] = "browser"
    client_name: str | None = Field(default=None, max_length=200)


class SetupBody(BaseModel):
    username: str = Field(max_length=64)
    display_name: str | None = Field(default=None, max_length=100)
    password: str = Field(max_length=1024)
    client: Literal["browser", "cli", "app"] = "browser"


class EnrolBody(BaseModel):
    code: str = Field(max_length=200)
    username: str | None = Field(default=None, max_length=64)
    password: str = Field(max_length=1024)
    client: Literal["browser", "cli", "app"] = "browser"


class RefreshBody(BaseModel):
    refresh_token: str = Field(max_length=200)


class PasskeyRegisterBody(BaseModel):
    credential: dict[str, Any]
    label: str | None = Field(default=None, max_length=100)


class PasswordBody(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class CodeBody(BaseModel):
    code: str = Field(max_length=12)


class PasswordOnlyBody(BaseModel):
    password: str = Field(max_length=1024)


class UserCreateBody(BaseModel):
    display_name: str = Field(max_length=100)
    role: str = Field(max_length=16)
    username: str | None = Field(default=None, max_length=64)


class UserPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, max_length=16)


class TokenCreateBody(BaseModel):
    name: str = Field(max_length=100)
    principal: Literal["self"] | dict[str, Any] = "self"
    scopes: list[str] | None = Field(default=None, max_length=64)
    expires_in_days: int | None = None


class RotateBody(BaseModel):
    grace_s: int = 0


class AccessBody(BaseModel):
    roles: list[str] = Field(default_factory=list, max_length=8)
    people: list[str] = Field(default_factory=list, max_length=500)
    auth: Literal["onemind", "app"] | None = None


def register(app: FastAPI, gw: Gateway) -> None:
    svc = IdentityService(gw)
    gw.authenticators.append(svc.authenticate)
    gw.approval_guards.append(svc.approval_guard)
    gw.app_filters.append(svc.app_filter)
    gw.people_sources.append(svc.people)
    app.state.identity = svc
    principal = gw.principal
    cfg = svc.cfg

    def session_response(body: dict, status: int = 200) -> JSONResponse:
        cookies = body.pop("_cookies", None)
        resp = JSONResponse(status_code=status, content=body)
        if cookies:
            common = dict(max_age=cookies["max_age"], secure=cfg.cookie_secure, samesite="strict", path="/")
            resp.set_cookie(svc.cookie, cookies["session"], httponly=True, **common)
            # Readable by the page's own script so it can echo it in OneMind-CSRF; useless cross-site.
            resp.set_cookie(svc.csrf_cookie, cookies["csrf"], httponly=False, **common)
        return resp

    def start(request: Request, user, method: str, client: str, name: str | None, passkey: bool, status=200):
        body = svc.start_session(request, user, method, name, bearer=client != "browser", passkey=passkey)
        return session_response(body, status)

    R = error_responses
    # ---- sign-in (no principal) ----------------------------------------------------------------------
    @app.post("/v1/auth/setup", operation_id="auth.setup", tags=["auth"], status_code=201, responses=R(401, 409, 422, 429))
    def setup(body: SetupBody, request: Request):
        """First owner: needs the install owner token (or the first-boot token) as the bearer."""
        token = request.headers.get("authorization", "").partition(" ")[2].strip()
        user = svc.setup(request, token, body.username, body.display_name or body.username, body.password)
        return start(request, user, "setup", body.client, None, passkey=False, status=201)

    @app.post("/v1/auth/login/options", operation_id="auth.login_options", tags=["auth"], responses=R(429))
    def login_options(request: Request):
        return svc.login_options(request)

    @app.post("/v1/auth/login", operation_id="auth.login", tags=["auth"], responses=R(401, 422, 429))
    def login(body: LoginBody, request: Request):
        if body.passkey is not None:
            user = svc.login_passkey(request, body.passkey)
            return start(request, user, "passkey", body.client, body.client_name, passkey=True)
        user = svc.login_password(request, body.username or "", body.password or "", body.totp)
        method = "password+totp" if user.totp_secret else "password"
        return start(request, user, method, body.client, body.client_name, passkey=False)

    @app.post("/v1/auth/enrol", operation_id="auth.enrol", tags=["auth"], status_code=201, responses=R(401, 409, 422, 429))
    def enrol(body: EnrolBody, request: Request):
        user = svc.enrol(request, body.code, body.username or "", body.password)
        return start(request, user, "enrolment", body.client, None, passkey=False, status=201)

    @app.post("/v1/auth/refresh", operation_id="auth.refresh", tags=["auth"], responses=R(401, 429))
    def refresh(body: RefreshBody, request: Request):
        return svc.refresh(request, body.refresh_token)

    # ---- the signed-in person ----------------------------------------------------------------------
    @app.post("/v1/auth/logout", operation_id="auth.logout", tags=["auth"], status_code=204, responses=R(401, 403, 409))
    def logout(request: Request, _: Principal = Depends(principal)):
        svc.logout(ctx_of(request))
        resp = Response(status_code=204)
        for name in (svc.cookie, svc.csrf_cookie):
            resp.delete_cookie(name, path="/", secure=cfg.cookie_secure, samesite="strict")
        return resp

    @app.get("/v1/auth/sessions", operation_id="auth.sessions.list", tags=["auth"], responses=R(401, 403))
    def sessions(request: Request, p: Principal = Depends(principal)):
        return svc.list_sessions(ctx_of(request), p)

    @app.delete("/v1/auth/sessions/{session_id}", operation_id="auth.sessions.revoke", tags=["auth"], status_code=204, responses=R(401, 403, 404))
    def revoke_session(session_id: str, request: Request, p: Principal = Depends(principal)):
        svc.revoke_session(ctx_of(request), p, session_id)
        return Response(status_code=204)

    @app.post("/v1/auth/passkeys/register/options", operation_id="auth.passkeys.register_options", tags=["auth"], responses=R(401, 403))
    def passkey_options(request: Request, _: Principal = Depends(principal)):
        return svc.passkey_register_options(request, ctx_of(request))

    @app.post("/v1/auth/passkeys/register", operation_id="auth.passkeys.register", tags=["auth"], status_code=201, responses=R(401, 403, 409, 422))
    def passkey_register(body: PasskeyRegisterBody, request: Request, _: Principal = Depends(principal)):
        return svc.passkey_register(request, ctx_of(request), body.credential, body.label)

    @app.get("/v1/auth/passkeys", operation_id="auth.passkeys.list", tags=["auth"], responses=R(401, 403))
    def passkeys(request: Request, _: Principal = Depends(principal)):
        return svc.list_passkeys(ctx_of(request))

    @app.delete("/v1/auth/passkeys/{credential_id}", operation_id="auth.passkeys.delete", tags=["auth"], status_code=204, responses=R(401, 403, 404, 409))
    def passkey_delete(credential_id: str, request: Request, _: Principal = Depends(principal)):
        svc.delete_passkey(ctx_of(request), credential_id)
        return Response(status_code=204)

    @app.post("/v1/auth/password", operation_id="auth.password.change", tags=["auth"], status_code=204, responses=R(401, 403, 422, 429))
    def password(body: PasswordBody, request: Request, _: Principal = Depends(principal)):
        svc.change_password(request, ctx_of(request), body.current_password, body.new_password)
        return Response(status_code=204)

    @app.post("/v1/auth/totp/setup", operation_id="auth.totp.setup", tags=["auth"], responses=R(401, 403, 409))
    def totp_setup(request: Request, _: Principal = Depends(principal)):
        return svc.totp_setup(ctx_of(request))

    @app.post("/v1/auth/totp/confirm", operation_id="auth.totp.confirm", tags=["auth"], status_code=204, responses=R(401, 403, 409, 422))
    def totp_confirm(body: CodeBody, request: Request, _: Principal = Depends(principal)):
        svc.totp_confirm(ctx_of(request), body.code)
        return Response(status_code=204)

    @app.post("/v1/auth/totp/disable", operation_id="auth.totp.disable", tags=["auth"], status_code=204, responses=R(401, 403, 429))
    def totp_disable(body: PasswordOnlyBody, request: Request, _: Principal = Depends(principal)):
        svc.totp_disable(request, ctx_of(request), body.password)
        return Response(status_code=204)

    @app.get("/v1/me", operation_id="me.get", tags=["auth"], responses=R(401, 403))
    def me(request: Request, p: Principal = Depends(principal)):
        return svc.me(request, p)

    # ---- users (owner) -------------------------------------------------------------------------------
    @app.get("/v1/users", operation_id="users.list", tags=["users"], responses=R(401, 403))
    def users(p: Principal = Depends(principal)):
        return svc.list_users(p)

    @app.post("/v1/users", operation_id="users.create", tags=["users"], status_code=201, responses=R(401, 403, 409, 422))
    def create_user(body: UserCreateBody, request: Request, p: Principal = Depends(principal)):
        return svc.create_user(request, ctx_of(request), p, body.display_name, body.role, body.username)

    @app.patch("/v1/users/{user_id}", operation_id="users.update", tags=["users"], responses=R(401, 403, 404, 409, 422))
    def update_user(user_id: str, body: UserPatchBody, request: Request, p: Principal = Depends(principal)):
        return svc.update_user(ctx_of(request), p, user_id, body.display_name, body.role)

    @app.post("/v1/users/{user_id}/disable", operation_id="users.disable", tags=["users"], responses=R(401, 403, 404, 409))
    def disable_user(user_id: str, p: Principal = Depends(principal)):
        return svc.disable_user(p, user_id)

    # ---- API tokens (H-09) ---------------------------------------------------------------------------
    @app.get("/v1/tokens", operation_id="tokens.list", tags=["tokens"], responses=R(401, 403))
    def tokens(request: Request, p: Principal = Depends(principal)):
        return svc.list_tokens(ctx_of(request), p)

    @app.post("/v1/tokens", operation_id="tokens.create", tags=["tokens"], status_code=201, responses=R(401, 403, 422))
    def create_token(body: TokenCreateBody, request: Request, p: Principal = Depends(principal)):
        return svc.create_token(ctx_of(request), p, body.name, body.principal, body.scopes, body.expires_in_days)

    @app.post("/v1/tokens/{token_id}/rotate", operation_id="tokens.rotate", tags=["tokens"], status_code=201, responses=R(401, 403, 404, 409, 422))
    def rotate_token(token_id: str, request: Request, body: RotateBody | None = None, p: Principal = Depends(principal)):
        return svc.rotate_token(ctx_of(request), p, token_id, body.grace_s if body else 0)

    @app.delete("/v1/tokens/{token_id}", operation_id="tokens.revoke", tags=["tokens"], status_code=204, responses=R(401, 403, 404))
    def revoke_token(token_id: str, request: Request, p: Principal = Depends(principal)):
        svc.revoke_token(ctx_of(request), p, token_id)
        return Response(status_code=204)

    # ---- per-app sharing -----------------------------------------------------------------------------
    @app.get("/v1/apps/{app_id}/access", operation_id="apps.access.get", tags=["apps"], responses=R(401, 403, 404))
    def get_access(app_id: str, p: Principal = Depends(principal)):
        return svc.get_access(p, app_id)

    @app.put("/v1/apps/{app_id}/access", operation_id="apps.access.set", tags=["apps"], responses=R(401, 403, 404, 422))
    def put_access(app_id: str, body: AccessBody, request: Request, p: Principal = Depends(principal)):
        return svc.put_access(ctx_of(request), p, app_id, body.roles, body.people, body.auth)

    # ---- approval step-up challenge (§12.4) ----------------------------------------------------------
    @app.post("/v1/actions/{action_id}/approve-options", operation_id="actions.approve_options", tags=["actions"], responses=R(401, 403, 404, 409))
    def approve_options(action_id: str, request: Request, p: Principal = Depends(principal)):
        return svc.approve_options(request, p, action_id)

    # ---- the minimal sign-in page (until the new UI wires its own screens) ---------------------------
    @app.get("/signin", include_in_schema=False)
    def signin_page():
        return HTMLResponse(SIGNIN_HTML.read_text(), headers={
            "Cache-Control": "no-cache",
            "Content-Security-Policy": "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                                       "style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; "
                                       "frame-ancestors 'none'; base-uri 'none'",
            "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
