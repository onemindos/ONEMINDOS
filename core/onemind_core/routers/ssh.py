# SPDX-License-Identifier: Apache-2.0
"""The owner's SSH keys and switch (P-06): `/v1/ssh`, `/v1/ssh/keys`.

Reads are owner-only. Every change is a request filed in the action ledger (`ssh.key.add`, `ssh.key.remove`,
`ssh.toggle`): the owner approves it at /v1/actions/{id}/approve, and adding a key or switching SSH on needs a
passkey once passkeys are active (step-up). Nothing changes on the box before that. See core/onemind_core/sshaccess.py.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..jsonbody import JsonBody
from ..sshaccess import KEY_ADD, KEY_REMOVE, TOGGLE, SshService, parse_public_key

# Route order in the app and in /openapi.json (routers/__init__.py): after file sharing (337), before system (340).
ORDER = 338
REQUEST_TTL = timedelta(hours=24)
READ = {"security": [{"bearer": ["system:admin"]}]}          # the scopes register_route_scope names below
ASK = {"security": [{"bearer": ["actions:request"]}]}
IdemHeader = Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=200)]

# Same scope as /v1/system/controls: minted to no one, so only the owner role (every scope) reads it.
register_route_scope("GET,HEAD", r"/v1/ssh(/keys)?", ("system:admin",))
register_route_scope("POST", r"/v1/ssh/keys", ("actions:request",))
register_route_scope("DELETE", r"/v1/ssh/keys/[^/]+", ("actions:request",))
register_route_scope("PUT", r"/v1/ssh", ("actions:request",))


class KeyAddRequest(JsonBody):
    model_config = ConfigDict(extra="forbid")
    public_key: str = Field(min_length=1, max_length=8192, description="The one line of a .pub file.")
    label: str | None = Field(default=None, max_length=60, description="A name for the key; defaults to the key's own comment.")
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class SwitchRequest(JsonBody):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    reason: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class SshKey(BaseModel):
    id: str
    fingerprint: str
    type: str
    bits: int | None
    comment: str


class SshServiceInfo(BaseModel):
    available: bool
    reason: str | None
    message: str | None
    state: str = Field(description="on | off | waiting_for_key | starting | unavailable")
    enabled: bool
    running: bool
    port: int
    user: str
    reach: list[str] = Field(description="Where port 22 answers from: lan and mesh, plus internet on a cloud board")
    password_login: bool
    rate_limit: str
    max_keys: int


class SshView(BaseModel):
    service: SshServiceInfo
    keys: list[SshKey]


class SshKeys(BaseModel):
    keys: list[SshKey]


OFF_WARNING = ("Switching SSH off stops new logins and keeps it off after a reboot. Sessions already open keep running "
               "until they end. On a cloud box this closes its only shell apart from the provider's console.")


def register(app: FastAPI, gw: Gateway) -> None:
    svc = SshService(gw)
    svc.register()
    app.state.ssh = svc

    def passkey_step_up(p: Principal, action_id: str, body: dict, request: Request) -> None:
        """Approval guard: adding a key or switching SSH on needs a passkey (or a phone approver key's signature)
        once passkeys are active. The identity guard verifies what is sent; this makes it mandatory for these two."""
        if not p.is_owner:
            return  # actions.approve refuses and audits non-owners itself
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        params = action.get("params") or {}
        if not (action.get("type") == KEY_ADD or (action.get("type") == TOGGLE and params.get("enabled") is True)):
            return
        identity = getattr(request.app.state, "identity", None)
        if identity is None or not identity.passkeys_active():
            return
        if body.get("webauthn") is None and body.get("device_signature") is None:
            gw.events.publish_event(
                "auth", "step_up.required", {"attempted": "approve", "action_id": action_id, "type": action.get("type")},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "letting a key in, or switching SSH on, needs your passkey",
                           reason="step_up_required")

    gw.approval_guards.insert(0, passkey_step_up)  # the existing identity guard verifies any supplied assertion

    def owner(p: Principal, what: str) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may do this")

    def file(p: Principal, action_type: str, params: dict, idem: str | None, reason: str | None, key: str | None):
        svc.check_request(action_type, params)
        body, created = gw.actions.request_feature(
            p, action_type, params, idempotency_key=idem or key or f"ssh:{uuid.uuid4()}",
            expires_at=gw.clock() + REQUEST_TTL, reason=reason, pending_cap=True)
        return JSONResponse(status_code=202 if created else 200, content=body, headers={"Location": f"/v1/actions/{body['id']}"})

    @app.get("/v1/ssh", tags=["system"], operation_id="ssh.get", response_model=SshView, responses=error_responses(401, 403),
             openapi_extra=READ)
    def ssh_get(p: Principal = Depends(gw.principal)):
        """Whether SSH is on, whether it listens, the rules it runs under, and the keys that may log in (owner only)."""
        owner(p, "read SSH access")
        return svc.view()

    @app.get("/v1/ssh/keys", tags=["system"], operation_id="ssh.keys.list", response_model=SshKeys, responses=error_responses(401, 403),
             openapi_extra=READ)
    def ssh_keys(p: Principal = Depends(gw.principal)):
        """The SSH keys that may log in as admin, with fingerprints (owner only). Keys added on the box's console show too."""
        owner(p, "read SSH keys")
        return {"keys": svc.view()["keys"]}

    @app.post("/v1/ssh/keys", tags=["system"], operation_id="ssh.keys.add", status_code=202, response_model=Action,
              responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 409, 422, 429)},
              openapi_extra=ASK)
    def ssh_key_add(req: KeyAddRequest, p: Principal = Depends(gw.principal), idem: IdemHeader = None):
        """Ask to let an SSH key log in as admin. It waits for the owner, who approves it with a passkey once passkeys
        are active. 422 for a key that is not a plain, supported, strong enough public key; 409 for a key already
        authorised or a box that cannot manage SSH (nothing is filed)."""
        owner(p, "request an SSH key")
        key = parse_public_key(req.public_key, req.label)
        params = {"public_key": key.line, "fingerprint": key.fingerprint, "type": key.type, "comment": key.comment}
        return file(p, KEY_ADD, params, idem, req.reason, req.idempotency_key)

    @app.delete("/v1/ssh/keys/{key_id}", tags=["system"], operation_id="ssh.keys.remove", status_code=202, response_model=Action,
                responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 404, 409, 429)},
                openapi_extra=ASK)
    def ssh_key_remove(key_id: str, p: Principal = Depends(gw.principal), idem: IdemHeader = None, reason: str | None = None):
        """Ask to remove a key (its id or SHA256 fingerprint). It waits for the owner. Logins with it are refused once
        approved; a session already open stays until it ends."""
        owner(p, "request removing an SSH key")
        found = svc.find(key_id)
        if found is None:
            raise ApiError(404, "not_found", "There is no such SSH key on this box.")
        params = {"fingerprint": found["fingerprint"], "comment": found["comment"]}
        return file(p, KEY_REMOVE, params, idem, reason[:500] if reason else None, None)

    @app.put("/v1/ssh", tags=["system"], operation_id="ssh.switch", status_code=202, response_model=Action,
             responses={200: {"model": Action, "description": "Idempotent replay"}, **error_responses(401, 403, 409, 422, 429)},
             openapi_extra=ASK)
    def ssh_switch(req: SwitchRequest, p: Principal = Depends(gw.principal), idem: IdemHeader = None):
        """Ask to switch SSH on or off. Off stops sshd and keeps it off after a reboot; on lets it listen again (once a
        key exists). It waits for the owner; switching on needs a passkey once passkeys are active."""
        owner(p, "request switching SSH")
        # The approval card shows the params. Off is the one change that can lock an owner out, so it says what stays.
        params = {"enabled": req.enabled, **({} if req.enabled else {"note": OFF_WARNING})}
        return file(p, TOGGLE, params, idem, req.reason, req.idempotency_key)
