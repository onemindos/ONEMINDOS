# SPDX-License-Identifier: Apache-2.0
"""Private plugin signing-key enrollment, always through the owner action ledger."""
from datetime import datetime

from fastapi import Depends, FastAPI, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ..actions import ActionRequest
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.models import iso
from ..identity.scopes import register_route_scope
from ..plugins.owner_keys import OwnerKeys

ORDER = 280
register_route_scope("GET,HEAD", r"/v1/plugin-trust/keys", ("apps:read",))
register_route_scope("POST", r"/v1/plugin-trust/keys/requests", ("actions:request:plugin.key.enroll",))
register_route_scope("POST", r"/v1/plugin-trust/keys/[^/]+/revoke", ("actions:request:plugin.key.revoke",))


class SigningKey(BaseModel):
    id: str
    name: str
    public_key: str
    active: bool
    enrolled_at: datetime
    revoked_at: datetime | None


class SigningKeys(BaseModel):
    keys: list[SigningKey]


class KeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    public_key: str = Field(min_length=1, max_length=16384)
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime


class RevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: str = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime


def register(app: FastAPI, gw: Gateway):
    service = OwnerKeys(gw, app.state.identity)

    def step_up(principal, action_id, body, request):
        action = gw.repo.get(action_id)
        if (principal.is_owner and action and action.type in {"plugin.key.enroll", "plugin.key.revoke"}
                and app.state.identity.account_setup_exists()
                and not (body.get("webauthn") or body.get("password_totp"))):
            raise ApiError(401, "unauthenticated", "signing trust changes require an action-bound sign-in check",
                           reason="step_up_required")
    gw.approval_guards.insert(0, step_up)  # the existing identity guard verifies any supplied assertion

    @app.get("/v1/plugin-trust/keys", operation_id="plugins.keys.list", tags=["plugins"],
             response_model=SigningKeys, responses=error_responses(401, 403))
    def keys(p: Principal = Depends(gw.principal)):
        return {"keys": [{"id": row.id, "name": row.name, "public_key": row.public_key, "active": row.active,
                          "enrolled_at": iso(row.enrolled_at), "revoked_at": iso(row.revoked_at)}
                         for row in service.keys(p)]}

    @app.post("/v1/plugin-trust/keys/requests", operation_id="plugins.keys.enroll", tags=["plugins"],
              response_model=Action, status_code=202, responses=error_responses(401, 403, 409, 422))
    def enroll(body: KeyRequest, request: Request, p: Principal = Depends(gw.principal)):
        return service.request_enrollment(p, body)

    @app.post("/v1/plugin-trust/keys/{key_id}/revoke", operation_id="plugins.keys.revoke", tags=["plugins"],
              response_model=Action, status_code=202, responses=error_responses(401, 403, 404, 409, 422))
    def revoke(key_id: str, body: RevokeRequest, p: Principal = Depends(gw.principal)):
        return gw.actions.create(p, ActionRequest(type="plugin.key.revoke", params={"key_id": key_id},
            idempotency_key=body.idempotency_key, expires_at=body.expires_at))[0]
