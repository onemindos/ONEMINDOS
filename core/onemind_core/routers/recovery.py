# SPDX-License-Identifier: Apache-2.0
"""Recovery contacts (gateway permissions design PR 25d, §3.13, D-028): invite, accept, verify.

Three audiences, three route groups:
- the owner, in a signed-in session: /v1/auth/recovery/contacts and /v1/auth/recovery/settings
  (adding a contact or shortening a wait needs the passkey step-up; removing is L0);
- the contact's phone: POST /v1/recovery/invites/{id}/accept takes the box-signed invite, a P-256
  public key and a proof that the phone holds the private half (no account needed; a household
  invite is accepted from that adult's own session);
- the contact principal (`omc_` token): /v1/recovery/contact... and nothing else.

No MCP tool touches any of it (surfaces/parity.py: CREDENTIAL). Logic in recovery/contacts.py.
"""

from __future__ import annotations

from typing import Literal

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, ConfigDict, Field

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity import ctx_of
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..recovery.contacts import RecoveryContacts

ORDER = 265  # after identity (260): it needs app.state.identity

TAGS = ["recovery"]
OWNER_SECURITY = {"security": [{"bearer": ["*"]}]}  # an owner session; the handler checks the session
PERSON_SECURITY = {"security": [{"bearer": ["instance:read"]}]}  # a household person's own list
CONTACT_SECURITY = {"security": [{"bearer": ["recovery:contact"]}]}  # the contact token (omc_) only
# /v1/auth/... is already self-service (identity/scopes.py); the handlers check for an owner session.
register_route_scope("POST", r"/v1/recovery/invites/[^/]+/accept", None)  # no principal: the invite is the credential
register_route_scope("GET,HEAD,POST", r"/v1/recovery/contact(/[a-z-]+)?", None)  # the contact principal only


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


def register(app: FastAPI, gw: Gateway) -> None:
    ident = getattr(app.state, "identity", None)
    if ident is None:  # identity is a core router; without it there are no owners to protect
        return
    svc = RecoveryContacts(gw, ident)
    app.state.recovery_contacts = svc
    gw.authenticators.append(svc.authenticate)
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
        changes = {k: v for k, v in body.model_dump().items() if v is not None}
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

