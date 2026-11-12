# SPDX-License-Identifier: Apache-2.0
"""Contract §3: the action ledger routes (request, list, get, approve, deny)."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from ..actions import ActionRequest
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses


def register(app: FastAPI, gw: Gateway) -> None:
    actions = gw.actions
    principal = gw.principal

    @app.post(
        "/v1/actions",
        tags=["actions"],
        status_code=201,
        responses={
            200: {"description": "Idempotent replay: the action created earlier with this idempotency_key"},
            **error_responses(401, 403, 404, 409, 422, 429),
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
    def approve_action(action_id: str, p: Principal = Depends(principal)):
        return actions.approve(p, action_id)

    @app.post("/v1/actions/{action_id}/deny", tags=["actions"], responses=error_responses(401, 403, 404, 409, 422))
    def deny_action(action_id: str, p: Principal = Depends(principal)):
        return actions.deny(p, action_id)
