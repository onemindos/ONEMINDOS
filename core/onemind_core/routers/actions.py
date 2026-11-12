# SPDX-License-Identifier: Apache-2.0
"""Contract §3: the action ledger routes (request, list, get, approve, deny)."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionRequest, ApprovalInput
from ..appsecrets.api import SealedInput
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses


class OverrideInput(BaseModel):
    """F-7 owner override (override.py): why, and the app id typed as confirmation."""

    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=2000)
    confirm: str = Field(max_length=200)


class ApproveBody(BaseModel):
    """Optional approve body. Clients that send none keep the §3 behaviour.

    sealed: the app's secrets form for app.install (appsecrets/); override: the F-7 owner override;
    webauthn: the passkey assertion over approve-options' challenge (identity feature, §12.4).
    """

    sealed: SealedInput | None = None
    override: OverrideInput | None = None
    webauthn: dict | None = None


def register(app: FastAPI, gw: Gateway) -> None:
    actions = gw.actions
    principal = gw.principal

    @app.post(
        "/v1/actions",
        tags=["actions"],
        status_code=201,
        responses={
            200: {"description": "Idempotent replay: the action created earlier with this idempotency_key"},
            **error_responses(401, 403, 404, 409, 422),
        },
    )
    def create_action(req: ActionRequest, p: Principal = Depends(principal)):
        body, created = actions.create(p, req)
        return JSONResponse(status_code=201 if created else 200, content=body)

    @app.get("/v1/actions", tags=["actions"], responses=error_responses(401))
    def list_actions(_: Principal = Depends(principal)):
        return actions.list()

    @app.get("/v1/actions/{action_id}", tags=["actions"], responses=error_responses(401, 404, 422))
    def get_action(action_id: str, _: Principal = Depends(principal)):
        return actions.get(action_id)

    @app.post("/v1/actions/{action_id}/approve", tags=["actions"], responses=error_responses(401, 403, 404, 409, 422))
    def approve_action(action_id: str, body: ApproveBody | None = None, p: Principal = Depends(principal)):
        extra = ApprovalInput(
            sealed=body.sealed.model_dump(exclude_none=True) if body and body.sealed else None,
            override=body.override.model_dump() if body and body.override else None,
            webauthn=bool(body and body.webauthn),
        )
        return actions.approve(p, action_id, extra)

    @app.post("/v1/actions/{action_id}/deny", tags=["actions"], responses=error_responses(401, 403, 404, 409, 422))
    def deny_action(action_id: str, p: Principal = Depends(principal)):
        return actions.deny(p, action_id)
