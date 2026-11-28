# SPDX-License-Identifier: Apache-2.0
"""Contract §12.6: sign-in, sessions, passkeys, users, API tokens, per-app sharing, /v1/me, and
§12.4 approve-options. Logic is in identity/service.py; docs/leap/core/IDENTITY.md explains it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Request, Security
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity import IdentityService, ctx_of
from ..identity.approver_keys import KeyKind
from ..jsonbody import JsonBody

SIGNIN_HTML = Path(__file__).resolve().parent.parent / "identity" / "signin.html"


class ApprovalChallenge(BaseModel):
    challenge: str
    action_sha256: str
    plan_sha256: str | None
    expires_at: str
    # #702: what a phone's approver key signs (UTF-8, ECDSA P-256 SHA-256) instead of a passkey assertion.
    device_payload: str
    publicKey: dict[str, Any]
    # D-028 / design 3.11: the level this approval needs, and whether the no-proven-key grace eased it
    # from L2 to L1. allowCredentials lists only the keys that meet it.
    required_level: Literal["L0", "L1", "L2", "L3"]
    grace: bool
    box_code_required: bool = Field(default=False, description="N-1 b: during the grace an L2 approval also needs "
                                    "the code the box's own screen now shows; send it as box_code")
    decided_by: str = Field(description="the verification-table row that set the level")


Level = Literal["L0", "L1", "L2", "L3"]


class Passkey(BaseModel):
    credential_id: str
    label: str
    created_at: str
    last_used_at: str | None
    level: Level = Field(description="L1 Device check, L2 Proven key, L3 Biometric-only key")
    level_reason: str = Field(description="no_attestation | synced | model_not_trusted | chain_untrusted | "
                                          "not_biometric_capable | proven | legacy")
    explanation: str
    model: str | None = Field(description="the trusted model name, for a proven key")
    aaguid: str | None = Field(description="the authenticator model id (never identifies a person)")
    attestation: str | None
    device_bound: bool | None = Field(description="false for a passkey that syncs between devices")
    synced: bool | None


class PasskeyRegistered(BaseModel):
    credential_id: str
    label: str
    created_at: str
    level: Level
    level_reason: str
    explanation: str


class StepUpOptionsBody(JsonBody):
    op: str = Field(max_length=64, description="the owner route's operation id, e.g. users.update")
    target: str = Field(default="", max_length=200, description="its path id (user id, app id, ...), or empty")
    body: dict[str, Any] = Field(default_factory=dict,
                                 description="the request body with every field (defaults filled in)")
    at_box: bool = Field(default=False, description="when the step-up allows it (details box: alt, e.g. revoking a "
                         "lost last proven key): confirm with any passkey plus the code on the box's own screen")


class StepUpOptions(BaseModel):
    challenge_id: str
    expires_at: str
    required_level: Level = Field(description="the level the key that answers must meet")
    grace: bool
    box_code_required: bool = Field(description="D-028 / N-1 b: the box's own screen now shows a code; send it "
                                    "as box_code with the assertion")
    publicKey: dict[str, Any]


class StepUpBody(BaseModel):
    credential: dict[str, Any]
    box_code: str | None = Field(default=None, max_length=12, description="the code on the box's own screen")


class StepUpGrant(BaseModel):
    step_up: str = Field(description="send as the OneMind-Step-Up header on the change, once, within 2 minutes")
    expires_at: str
    level: Level


class VerificationRow(BaseModel):
    key: str
    label: str
    default: Level
    current: Level
    minimum: Level
    maximum: Level
    strict: bool = Field(description="never eased while the household has no proven key")


class VerificationType(BaseModel):
    key: str
    current: Level
    minimum: Level
    maximum: Level


class VerificationTable(BaseModel):
    rows: list[VerificationRow]
    types: list[VerificationType] = Field(description="per-action-type opt-ins above their tier (type:<action>)")
    household_level: Level | None = Field(description="the strongest key any owner holds")
    grace: bool = Field(description="no owner has had a proven key yet, so L2 rows accept L1 plus the code on the box's "
                        "own screen (not strict rows)")
    recovery_needed: bool = Field(description="a proven key existed and none is left: L2 rows wait for a recovery "
                                  "path (an owner at the box can enrol a new key); the grace never returns")
    box_confirm: bool = Field(description="this install has a box screen that can show confirmation codes")


class TrustedModel(BaseModel):
    aaguid: str
    name: str
    user_verification: list[str]
    biometric: bool
    roots: int
    source: Literal["shipped", "owner"]
    added_at: str | None


# The random id an app install keeps for itself (#715): My devices groups a phone's sign-ins, passkeys
# and push registrations by it, so a renamed phone stays one device and two phones with the same
# default name stay two.
INSTALL_ID = r"^[A-Za-z0-9_-]{16,64}$"


class LoginBody(BaseModel):
    username: str | None = Field(default=None, max_length=64)
    password: str | None = Field(default=None, max_length=1024)
    totp: str | None = Field(default=None, max_length=12)
    passkey: dict[str, Any] | None = None
    # browser → HttpOnly cookie + CSRF token; cli/app → bearer access + refresh token
    client: Literal["browser", "cli", "app"] = "browser"
    client_name: str | None = Field(default=None, max_length=200)
    install_id: str | None = Field(default=None, pattern=INSTALL_ID)


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
    install_id: str | None = Field(default=None, pattern=INSTALL_ID)
    box_code: str | None = Field(default=None, max_length=12, description="N-1 b: the code on the box's own screen "
                                 "(register/options box_code_if_proven); the first proven key is added at the box")


class ApproverKeyBody(BaseModel):
    public_key: str = Field(max_length=400, description="P-256 SubjectPublicKeyInfo, DER, base64url.")
    label: str = Field(max_length=100, description="The phone this key lives on, e.g. 'Pixel 9'.")
    key_kind: KeyKind


class ApproverKey(BaseModel):
    key_id: str
    label: str
    key_kind: str
    fingerprint: str
    created_at: str
    last_used_at: str | None
    revoked_at: str | None


class RescueVerifyBody(BaseModel):
    credential: dict[str, Any]


class PasswordBody(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)


class CodeBody(BaseModel):
    code: str = Field(max_length=12)


class PasswordOnlyBody(BaseModel):
    password: str = Field(max_length=1024)


class SignInMethods(BaseModel):
    """How the signed-in person can sign in (Settings > Account and security). Facts only, no secret."""

    password: bool = Field(description="This person has a password (password sign-in works).")
    totp: bool = Field(description="An authenticator code is asked after the password. A fallback: passkeys come first (D-030).")
    passkeys: int = Field(description="Passkeys this person has registered.")
    passkeys_active: bool = Field(description="An owner on this box has a passkey, so owner actions need a fresh passkey sign-in.")


class TotpSecret(BaseModel):
    secret: str = Field(description="Base32 secret for an authenticator app; shown once.")
    otpauth_uri: str = Field(description="The same secret as an otpauth:// link (what a QR code holds).")


class TotpSetup(BaseModel):
    one_time: TotpSecret


class MePatchBody(BaseModel):
    # Not length-limited tightly here: the service answers 422 with a reason, like the other identity routes.
    display_name: str | None = Field(default=None, max_length=1000)


class UserCreateBody(BaseModel):
    display_name: str = Field(max_length=100)
    role: str = Field(max_length=16)
    username: str | None = Field(default=None, max_length=64)


class UserPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=100)
    role: str | None = Field(default=None, max_length=16)


class TokenCreateBody(JsonBody):
    name: str = Field(max_length=100)
    # "self" or {kind: "agent", id: "agent:<name>"}. Go gets `any`: oapi-codegen would need its
    # runtime package for a union, and the Go SDK stays standard-library only (SDK.md §1).
    principal: Literal["self"] | dict[str, Any] = Field(
        default="self", json_schema_extra={"x-go-type": "any", "x-go-type-skip-optional-pointer": True})
    scopes: list[str] | None = Field(default=None, max_length=64)
    expires_in_days: int | None = None


class RotateBody(JsonBody):
    grace_s: int = 0


class AccessBody(BaseModel):
    roles: list[str] = Field(default_factory=list, max_length=8)
    people: list[str] = Field(default_factory=list, max_length=500)
    auth: Literal["onemind", "app"] | None = None


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 260
# Names the bearer scheme in /openapi.json for routes added after the contract lint (#874). It never refuses by
# itself: gw.principal and the handler decide, and a session cookie works as on every other route.
_BEARER = HTTPBearer(scheme_name="bearer", auto_error=False, description="A gateway token or a signed-in session (contract §3)")
SIGNED_IN = [Security(_BEARER, scopes=["*"])]


def register(app: FastAPI, gw: Gateway) -> None:
    svc = IdentityService(gw)
    gw.authenticators.append(svc.authenticate)
    gw.approval_guards.append(svc.approval_guard)
    gw.action_views.append(svc.action_view)
    gw.app_filters.append(svc.app_filter)
    gw.people_sources.append(svc.people)
    app.state.identity = svc
    svc.levels.register()
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

    def start(request: Request, user, method: str, client: str, name: str | None, passkey: bool, status=200,
              install_id: str | None = None):
        body = svc.start_session(request, user, method, name, bearer=client != "browser", passkey=passkey,
                                 install_id=install_id)
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
            return start(request, user, "passkey", body.client, body.client_name, passkey=True,
                         install_id=body.install_id)
        user = svc.login_password(request, body.username or "", body.password or "", body.totp)
        method = "password+totp" if user.totp_secret else "password"
        return start(request, user, method, body.client, body.client_name, passkey=False,
                     install_id=body.install_id)

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

    @app.post("/v1/auth/passkeys/register", operation_id="auth.passkeys.register", tags=["auth"], status_code=201, response_model=PasskeyRegistered, responses=R(401, 403, 409, 422))
    def passkey_register(body: PasskeyRegisterBody, request: Request, _: Principal = Depends(principal)):
        return svc.passkey_register(request, ctx_of(request), body.credential, body.label, body.install_id,
                                    body.box_code)

    @app.get("/v1/auth/passkeys", operation_id="auth.passkeys.list", tags=["auth"], response_model=list[Passkey], responses=R(401, 403))
    def passkeys(request: Request, _: Principal = Depends(principal)):
        return svc.list_passkeys(ctx_of(request))

    @app.delete("/v1/auth/passkeys/{credential_id}", operation_id="auth.passkeys.delete", tags=["auth"], status_code=204, responses=R(401, 403, 404, 409))
    def passkey_delete(credential_id: str, request: Request, _: Principal = Depends(principal)):
        svc.delete_passkey(ctx_of(request), credential_id)
        return Response(status_code=204)

    # ---- verification levels (D-028, design 3.11) -----------------------------------------------------
    @app.post("/v1/auth/step-up/options", operation_id="auth.step_up.options", tags=["auth"], response_model=StepUpOptions, responses=R(401, 403, 409, 422), openapi_extra={"security": [{"bearer": ["*"]}]})
    def step_up_options(body: StepUpOptionsBody, request: Request, _: Principal = Depends(principal)):
        """A passkey challenge for one owner change that needs L2 or more; only keys at that level answer."""
        return svc.step_up_options(request, ctx_of(request), body.op, body.target, body.body, body.at_box)

    @app.post("/v1/auth/step-up", operation_id="auth.step_up.verify", tags=["auth"], response_model=StepUpGrant, responses=R(401, 403, 422), openapi_extra={"security": [{"bearer": ["*"]}]})
    def step_up_verify(body: StepUpBody, request: Request, _: Principal = Depends(principal)):
        return svc.step_up_verify(request, ctx_of(request), body.credential, body.box_code)

    @app.get("/v1/verification-requirements", operation_id="verification.requirements.get", tags=["auth"], response_model=VerificationTable, responses=R(401, 403), openapi_extra={"security": [{"bearer": ["actions:approve"]}]})
    def verification_requirements(p: Principal = Depends(principal)):
        """The level each kind of approval and change needs. Change a row by requesting
        verification.requirement.set (POST /v1/actions); an owner approves it at the table's own level."""
        if not p.is_owner:
            raise svc.deny(p, "read the verification table")
        return svc.levels.table()

    @app.get("/v1/auth/authenticator-allowlist", operation_id="auth.trusted_models.list", tags=["auth"], response_model=list[TrustedModel], responses=R(401, 403), openapi_extra={"security": [{"bearer": ["actions:approve"]}]})
    def trusted_models(p: Principal = Depends(principal)):
        """Key models that can be proven keys (L2). Add one by requesting authenticator.allowlist.add."""
        return svc.levels.list_models(p)

    @app.delete("/v1/auth/authenticator-allowlist/{aaguid}", operation_id="auth.trusted_models.remove", tags=["auth"], status_code=204, responses=R(401, 403, 404, 409), openapi_extra={"security": [{"bearer": ["actions:approve"]}]})
    def trusted_model_remove(aaguid: str, request: Request, p: Principal = Depends(principal)):
        """Stop trusting a model you added. Its keys drop to L1 at once; taking trust away needs no step-up,
        except for the model behind the household's last proven key (that key, or an owner at the box)."""
        svc.levels.remove_model(p, aaguid, ctx_of(request))
        return Response(status_code=204)

    # ---- device-bound approver keys (#702): the phone's biometric-gated signing key -------------------
    @app.post("/v1/auth/approver-keys", operation_id="auth.approver_keys.register", tags=["auth"], status_code=201, response_model=ApproverKey, responses=R(401, 403, 409, 422))
    def approver_key_register(body: ApproverKeyBody, request: Request, _: Principal = Depends(principal)):
        """An owner adds a phone's P-256 approver key; needs a passkey sign-in on this session in the last minutes."""
        return svc.register_approver_key(ctx_of(request), body.public_key, body.label, body.key_kind)

    @app.get("/v1/auth/approver-keys", operation_id="auth.approver_keys.list", tags=["auth"], response_model=list[ApproverKey], responses=R(401, 403))
    def approver_keys(request: Request, _: Principal = Depends(principal)):
        return svc.list_approver_keys(ctx_of(request))

    @app.delete("/v1/auth/approver-keys/{key_id}", operation_id="auth.approver_keys.revoke", tags=["auth"], status_code=204, responses=R(401, 403, 404))
    def approver_key_revoke(key_id: str, request: Request, _: Principal = Depends(principal)):
        svc.revoke_approver_key(ctx_of(request), key_id)
        return Response(status_code=204)

    @app.post("/v1/auth/password", operation_id="auth.password.change", tags=["auth"], status_code=204, responses=R(401, 403, 422, 429))
    def password(body: PasswordBody, request: Request, _: Principal = Depends(principal)):
        svc.change_password(request, ctx_of(request), body.current_password, body.new_password)
        return Response(status_code=204)

    @app.get("/v1/auth/methods", operation_id="auth.methods.get", tags=["auth"], response_model=SignInMethods,
             dependencies=SIGNED_IN, responses=R(401, 403))
    def sign_in_methods(request: Request, _: Principal = Depends(principal)):
        """Your own sign-in methods: password, authenticator code, passkeys. A household person only."""
        return svc.sign_in_methods(ctx_of(request))

    @app.post("/v1/auth/totp/setup", operation_id="auth.totp.setup", tags=["auth"], response_model=TotpSetup,
              responses=R(401, 403, 409))
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

    @app.patch("/v1/me", operation_id="me.update", tags=["auth"], responses=R(401, 403, 422))
    def update_me(body: MePatchBody, request: Request, p: Principal = Depends(principal)):
        """Set (or clear, with null) your own display name. Display text only; it grants nothing."""
        return svc.set_profile_name(request, p, body.display_name)

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
    @app.post("/v1/actions/{action_id}/approve-options", operation_id="actions.approve_options", tags=["actions"], response_model=ApprovalChallenge, responses=R(401, 403, 404, 409))
    def approve_options(action_id: str, request: Request, p: Principal = Depends(principal)):
        return svc.approve_options(request, p, action_id)

    # ---- rescue console step-up (D-014): called by the console on this box, never listed in the API ----
    @app.post("/v1/auth/rescue/options", include_in_schema=False)
    def rescue_options(request: Request, p: Principal = Depends(principal)):
        return svc.rescue_options(request, p)

    @app.post("/v1/auth/rescue/verify", include_in_schema=False)
    def rescue_verify(body: RescueVerifyBody, request: Request, p: Principal = Depends(principal)):
        return svc.rescue_verify(request, p, body.credential)

    # ---- the minimal sign-in page (until the new UI wires its own screens) ---------------------------
    @app.get("/signin", include_in_schema=False)
    def signin_page():
        return HTMLResponse(SIGNIN_HTML.read_text(), headers={
            "Cache-Control": "no-cache",
            "Content-Security-Policy": "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                                       "style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; "
                                       "frame-ancestors 'none'; base-uri 'none'",
            "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})
