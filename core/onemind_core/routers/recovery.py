# SPDX-License-Identifier: Apache-2.0
"""Recovery contacts (gateway permissions design PR 25d) and contact-assisted recovery (25e), §3.13, D-028.

Three audiences, three route groups:
- the owner, in a signed-in session: /v1/auth/recovery/contacts and /v1/auth/recovery/settings
  (adding a contact or shortening a wait needs the passkey step-up; removing is L0);
- the contact's phone: POST /v1/recovery/invites/{id}/accept takes the box-signed invite, a P-256
  public key and a proof that the phone holds the private half (no account needed; a household
  invite is accepted from that adult's own session);
- the contact principal (`omc_` token): /v1/recovery/contact... and /v1/recovery/requests... (25e:
  see a recovery of their owner, confirm it by picking the matching number, or cancel it), nothing else;
- the locked-out owner (25e): POST /v1/auth/recovery starts a recovery and answers
  once with a request token (`omr_`); that token, as the bearer, reaches only that request's routes
  under /v1/auth/recovery/requests/{id} (status, the contact's 8-digit code, cancel, finish).

No MCP tool touches any of it (surfaces/parity.py: CREDENTIAL). Logic in recovery/contacts.py.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..recovery.contacts import RecoveryContacts
from ..recovery.requests import REQUEST_TOKEN_PREFIX, Recoveries
from ..recovery.ticker import Ticker

ORDER = 265  # after identity (260): it needs app.state.identity

TAGS = ["recovery"]
OWNER_SECURITY = {"security": [{"bearer": ["*"]}]}  # an owner session; the handler checks the session
PERSON_SECURITY = {"security": [{"bearer": ["instance:read"]}]}  # a household person's own list
CONTACT_SECURITY = {"security": [{"bearer": ["recovery:contact"]}]}  # the contact token (omc_) only
# /v1/auth/... is already self-service (identity/scopes.py); the handlers check for an owner session.
register_route_scope("POST", r"/v1/recovery/invites/[^/]+/accept", None)  # no principal: the invite is the credential
register_route_scope("GET,HEAD,POST", r"/v1/recovery/contact(/[a-z-]+)?", None)  # the contact principal only
register_route_scope("GET,HEAD,POST", r"/v1/recovery/requests(/[^/]+/(vouch|cancel))?", None)  # 25e, contact only
STARTER_SECURITY = {"security": [{"bearer": ["recovery:request"]}]}  # the request token (omr_) from POST /v1/auth/recovery


class ContactView(BaseModel):
    id: str
    role: str
    kind: str = Field(description="household (an adult with an account here) or outside (through the OneMind phone app)")
    display_name: str
    household_user_id: str | None
    state: str = Field(description="invited, expired, cooling_off (accepted, not usable yet), active, removed or resigned")
    invited_at: str
    invite_expires_at: str
    cooling_off_days: int
    accepted_at: str | None
    usable_at: str | None = Field(description="when this contact can first confirm a recovery")
    ended_at: str | None
    device_label: str | None
    key_kind: str | None
    key_fingerprint: str | None
    last_seen_at: str | None


class ContactAdded(ContactView):
    invite: str = Field(description="the box-signed invite (single use, 7 days); show it as a link or QR code once")
    box_key_fingerprint: str


class ContactAddBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["household", "outside"]
    display_name: str = Field(default="", max_length=200, description="the contact's name (outside contacts)")
    household_user_id: str | None = Field(default=None, max_length=40)
    cooling_off_days: Literal[3, 7, 14] | None = Field(default=None, description="days before the contact counts; default from settings (7)")


class RecoverySettings(BaseModel):
    values: dict[str, int]
    defaults: dict[str, int]
    options: dict[str, list[int]]
    updated_at: str | None


class RecoverySettingsBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    cooling_off_days: Literal[3, 7, 14] | None = None
    contact_wait_hours: Literal[24, 48, 72] | None = Field(
        default=None, description="the wait after a contact confirms (rises to 72 by itself if a strong key was used in the last 7 days)")
    remote_wait_hours: Literal[72, 168] | None = Field(default=None, description="the wait of a recovery with no contact")


class Invitation(BaseModel):
    id: str
    role: str
    owner_display_name: str | None
    invite_expires_at: str
    cooling_off_days: int


class AcceptBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    invite: str = Field(max_length=2000, description="the invite text from the link or QR code")
    public_key: str = Field(max_length=400, description="the contact key: P-256 SubjectPublicKeyInfo, DER, base64url")
    key_kind: Literal["hardware-reported", "software"]
    device_label: str = Field(default="", max_length=100)
    proof: str = Field(max_length=200, description="ECDSA P-256 SHA-256 signature by the new key over the accept payload "
                                                   "(onemind-recovery-accept-v1, invite id, sha256 of the nonce, key fingerprint)")


class AcceptOneTime(BaseModel):
    contact_token: str = Field(description="the contact's bearer token (omc_...), shown once; reaches only the contact routes")
    contact_secret: str = Field(description="32 bytes, base64url, shown once: keep it in the phone's secure hardware")


class Accepted(BaseModel):
    contact_id: str
    role: str
    owner_display_name: str | None
    usable_at: str
    box_key_fingerprint: str
    one_time: AcceptOneTime


class ContactSelf(BaseModel):
    contact_id: str
    role: str
    state: str
    owner_display_name: str | None
    accepted_at: str | None
    usable_at: str | None
    box_key_fingerprint: str


class Notice(BaseModel):
    id: str
    at: str
    event: str
    data: dict


class RecoveryStartBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    path: Literal["contact", "remote"]
    username: str = Field(default="", max_length=64)
    password: str | None = Field(default=None, max_length=1024, description="remote path: with the authenticator code")
    totp: str | None = Field(default=None, max_length=12)
    passkey: dict[str, Any] | None = Field(default=None, description="remote path: an assertion from a passkey you still have")


class ContactRecoveryView(BaseModel):
    id: str
    path: str = Field(description="contact (a recovery contact confirms) or remote (no contact, a longer wait)")
    state: str = Field(description="awaiting_contact, waiting, completed, cancelled, expired or failed")
    created_at: str
    vouch_expires_at: str | None
    vouched_at: str | None
    vouch_method: str | None = Field(description="online (picked the matching number) or code (the 8-digit code)")
    wait_hours: int | None
    liveness_raised: bool = Field(description="the wait rose to 72 hours because a strong key was used in the last 7 days")
    not_before: str | None = Field(description="when the person who started it may finish")
    ended_at: str | None
    end_reason: str | None


class RecoveryView(ContactRecoveryView):
    source: str


class StarterView(RecoveryView):
    matching_number: str | None = Field(description="the 2 digits the contact must pick; shown only to the starter")
    request_code: str | None = Field(description="read this to your contact if their app cannot reach the box")


class StartOneTime(BaseModel):
    request_token: str = Field(description="the bearer for this request's own routes (omr_...), shown once")


class Started(StarterView):
    one_time: StartOneTime


class CodeBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(max_length=16, description="the 8 ASCII digits your contact's app shows")


class VouchBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    picked: str = Field(pattern=r"^[0-9]{2}$", description="the number the contact picked from the three")
    signature: str = Field(max_length=200, description="ECDSA P-256 SHA-256 by the contact key over "
                                                       "onemind-recovery-vouch-v1, request id, picked, challenge")


class ContactRequest(BaseModel):
    id: str
    state: str
    owner_display_name: str | None
    created_at: str
    expires_at: str | None = None
    not_before: str | None = None
    choices: list[str] | None = Field(default=None, description="three numbers; pick the one on the owner's screen")
    challenge: str | None = None


class CompleteBody(JsonBody):
    model_config = ConfigDict(extra="forbid")
    credential: dict[str, Any] | None = Field(default=None, description="a new passkey from complete/options")
    label: str | None = Field(default=None, max_length=100)
    new_password: str | None = Field(default=None, max_length=1024, description="contact path only")
    current_password: str | None = Field(default=None, max_length=1024, description="required on the contact path")
    client: Literal["browser", "cli", "app"] = "browser"


def register(app: FastAPI, gw: Gateway) -> None:
    ident = getattr(app.state, "identity", None)
    if ident is None:  # identity is a core router; without it there are no owners to protect
        return
    svc = RecoveryContacts(gw, ident)
    app.state.recovery_contacts = svc
    gw.authenticators.append(svc.authenticate)
    rec = Recoveries(svc)
    app.state.recoveries = rec
    ticker = Ticker([rec.tick])
    gw.on_startup(ticker.start)
    gw.on_shutdown(ticker.stop)
    principal = gw.principal
    R = error_responses

    # ---- the owner -----------------------------------------------------------------------------------
    @app.get("/v1/auth/recovery/contacts", operation_id="recovery.contacts.list", tags=TAGS,
             response_model=list[ContactView], responses=R(401, 403), openapi_extra=OWNER_SECURITY)
    def list_contacts(request: Request, _: Principal = Depends(principal)):
        """Your recovery contacts and their state (owner, signed-in session)."""
        return svc.list(ctx_of(request))

    @app.post("/v1/auth/recovery/contacts", operation_id="recovery.contacts.add", tags=TAGS, status_code=201,
              response_model=ContactAdded, responses=R(401, 403, 409, 422), openapi_extra=OWNER_SECURITY)
    def add_contact(body: ContactAddBody, request: Request, _: Principal = Depends(principal)):
        """Invite a recovery contact (up to 5). A security setting: owner session plus the passkey step-up."""
        return svc.add(ctx_of(request), body.kind, body.display_name, body.household_user_id, body.cooling_off_days)

    @app.delete("/v1/auth/recovery/contacts/{contact_id}", operation_id="recovery.contacts.remove", tags=TAGS,
                response_model=ContactView, responses=R(401, 403, 404), openapi_extra=OWNER_SECURITY)
    def remove_contact(contact_id: str, request: Request, _: Principal = Depends(principal)):
        """Remove a contact or withdraw an invite. Takes power away, so no step-up (L0)."""
        return svc.remove(ctx_of(request), contact_id)

    @app.get("/v1/auth/recovery/settings", operation_id="recovery.settings.get", tags=TAGS,
             response_model=RecoverySettings, responses=R(401, 403), openapi_extra=OWNER_SECURITY)
    def get_settings(request: Request, _: Principal = Depends(principal)):
        ctx = ctx_of(request)
        return svc.settings(svc._session_owner(ctx, "read recovery waits").id)

    @app.put("/v1/auth/recovery/settings", operation_id="recovery.settings.set", tags=TAGS,
             response_model=RecoverySettings, responses=R(401, 403, 422), openapi_extra=OWNER_SECURITY)
    def put_settings(body: RecoverySettingsBody, request: Request, _: Principal = Depends(principal)):
        """Each wait from its set options (D-028). A shorter wait needs the passkey step-up."""
        changes = {k: v for k, v in body.model_dump().items() if v is not None}  # every wait is an int
        if not changes:
            raise ApiError(422, "conflict", "name at least one wait to change", reason="nothing_to_change")
        return svc.set_settings(ctx_of(request), changes)

    @app.get("/v1/auth/recovery/invitations", operation_id="recovery.invitations.list", tags=TAGS,
             response_model=list[Invitation], responses=R(401, 403), openapi_extra=PERSON_SECURITY)
    def invitations(request: Request, _: Principal = Depends(principal)):
        """Invites addressed to you as a household adult; accept one from your phone app."""
        return svc.invitations(ctx_of(request))

    # ---- the contact's phone -------------------------------------------------------------------------
    @app.post("/v1/recovery/invites/{invite_id}/accept", operation_id="recovery.invites.accept", tags=TAGS,
              status_code=201, response_model=Accepted, responses=R(401, 403, 409, 422, 429),
              openapi_extra={"security": []})
    def accept(invite_id: str, body: AcceptBody, request: Request):
        """Accept a box-signed invite with the phone's new contact key. The answer holds the contact
        token and contact secret once; the contact counts only after the owner's cooling-off."""
        return svc.accept(request, invite_id, body.invite, body.public_key, body.key_kind, body.device_label,
                          body.proof)

    # ---- the contact principal -----------------------------------------------------------------------
    @app.get("/v1/recovery/contact", operation_id="recovery.contact.get", tags=TAGS,
             response_model=ContactSelf, responses=R(401, 403), openapi_extra=CONTACT_SECURITY)
    def contact_self(request: Request, p: Principal = Depends(principal)):
        """Who you are a contact for, and from when you count (contact principal only)."""
        return svc.contact_view(svc.contact_row(request, p))

    @app.get("/v1/recovery/contact/notices", operation_id="recovery.contact.notices", tags=TAGS,
             response_model=list[Notice], responses=R(401, 403), openapi_extra=CONTACT_SECURITY)
    def contact_notices(request: Request, p: Principal = Depends(principal)):
        """What you are told about the owner's recovery setup: contacts added or removed, recoveries."""
        return svc.notices(svc.contact_row(request, p))

    @app.post("/v1/recovery/contact/resign", operation_id="recovery.contact.resign", tags=TAGS,
              response_model=ContactSelf, responses=R(401, 403), openapi_extra=CONTACT_SECURITY)
    def contact_resign(request: Request, p: Principal = Depends(principal)):
        """Stop being a contact. The owner is told; the token and secret stop working at once."""
        return svc.resign(svc.contact_row(request, p), p)

    # ---- 25e: the locked-out owner -------------------------------------------------------------------
    def starter(request_id: str, request: Request) -> None:
        """The request token first: a caller without it gets 401 before its body is even read."""
        rec.status(request, request_id)

    @app.post("/v1/auth/recovery", operation_id="recovery.start", tags=TAGS, status_code=201,
              response_model=Started, responses=R(401, 409, 422, 429), openapi_extra={"security": []})
    def start(body: RecoveryStartBody, request: Request):
        """Start a recovery. contact: your username; one of your recovery contacts confirms. remote: your
        password and authenticator code (or a passkey you still have), then a 72-hour wait."""
        return rec.start(request, body.path, body.username, body.password, body.totp, body.passkey)

    @app.get("/v1/auth/recovery", operation_id="recovery.list", tags=TAGS, response_model=list[RecoveryView],
             responses=R(401, 403), openapi_extra=OWNER_SECURITY)
    def list_recoveries(request: Request, p: Principal = Depends(principal)):
        """Every running recovery on the box, for a full owner credential. Codes are never shown here."""
        return rec.for_owner(p, ctx_of(request))

    @app.get("/v1/auth/recovery/requests/{request_id}", operation_id="recovery.status", tags=TAGS,
             response_model=StarterView, responses=R(401), openapi_extra=STARTER_SECURITY)
    def recovery_status(request_id: str, request: Request):
        return rec.status(request, request_id)

    @app.post("/v1/auth/recovery/requests/{request_id}/code", operation_id="recovery.code", tags=TAGS,
              response_model=RecoveryView, responses=R(401, 409, 422), openapi_extra=STARTER_SECURITY)
    def recovery_code(request_id: str, body: CodeBody, request: Request, _: None = Depends(starter)):
        """Type the 8-digit code your contact read to you (3 tries)."""
        return rec.vouch_code(request, request_id, body.code)

    @app.post("/v1/auth/recovery/requests/{request_id}/cancel", operation_id="recovery.cancel", tags=TAGS,
              response_model=RecoveryView, responses=R(401, 403, 404), openapi_extra=STARTER_SECURITY)
    def recovery_cancel(request_id: str, request: Request):
        """Stop a recovery with its request token or a full owner credential (L0)."""
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer" and token.strip().startswith(REQUEST_TOKEN_PREFIX):
            return rec.cancel_by_starter(request, request_id)
        p = gw.principal(request)
        return rec.cancel_by_owner(p, ctx_of(request), request_id)

    @app.post("/v1/auth/recovery/requests/{request_id}/complete/options", operation_id="recovery.complete_options",
              tags=TAGS, responses=R(401, 409), openapi_extra=STARTER_SECURITY)
    def recovery_complete_options(request_id: str, request: Request):
        """After the wait: the WebAuthn options to enrol your new passkey."""
        return rec.complete_options(request, request_id)

    @app.post("/v1/auth/recovery/requests/{request_id}/complete", operation_id="recovery.complete", tags=TAGS,
              responses=R(401, 409, 422, 429), openapi_extra=STARTER_SECURITY)
    def recovery_complete(request_id: str, body: CompleteBody, request: Request, _: None = Depends(starter)):
        """After the wait, enrol a new passkey. With a recovery contact, prove the current password
        and enrol a passkey or set a new password. Completion returns a normal session."""
        _, user = rec.complete(request, request_id, body.credential, body.label, body.new_password,
                               body.current_password)
        out = ident.start_session(request, user, "recovery", None, bearer=body.client != "browser", passkey=False)
        cookies = out.pop("_cookies", None)
        resp = JSONResponse(status_code=200, content=out)
        if cookies:
            common = dict(max_age=cookies["max_age"], secure=ident.cfg.cookie_secure, samesite="strict", path="/")
            resp.set_cookie(ident.cookie, cookies["session"], httponly=True, **common)
            resp.set_cookie(ident.csrf_cookie, cookies["csrf"], httponly=False, **common)
        return resp

    # ---- 25e: the contact principal ------------------------------------------------------------------
    @app.get("/v1/recovery/requests", operation_id="recovery.requests.list", tags=TAGS,
             response_model=list[ContactRequest], responses=R(401, 403, 409), openapi_extra=CONTACT_SECURITY)
    def contact_requests(request: Request, p: Principal = Depends(principal)):
        """Recoveries of your owner: confirm one by picking the number on their screen."""
        return rec.pending_for(svc.contact_row(request, p))

    @app.post("/v1/recovery/requests/{request_id}/vouch", operation_id="recovery.requests.vouch", tags=TAGS,
              response_model=ContactRecoveryView, responses=R(401, 403, 404, 409, 422), openapi_extra=CONTACT_SECURITY)
    def contact_vouch(request_id: str, body: VouchBody, request: Request, p: Principal = Depends(principal)):
        """Confirm it is really your owner: the number you picked, signed with your contact key."""
        return rec.vouch_online(svc.contact_row(request, p), p, request_id, body.picked, body.signature)

    @app.post("/v1/recovery/requests/{request_id}/cancel", operation_id="recovery.requests.cancel", tags=TAGS,
              response_model=ContactRecoveryView, responses=R(401, 403, 404), openapi_extra=CONTACT_SECURITY)
    def contact_cancel(request_id: str, request: Request, p: Principal = Depends(principal)):
        """Stop a recovery of your owner that you do not trust (any contact, L0)."""
        return rec.cancel_by_contact(svc.contact_row(request, p), p, request_id)
