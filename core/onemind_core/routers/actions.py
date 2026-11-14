# SPDX-License-Identifier: Apache-2.0
"""Contract §3: the action ledger routes (request, list, get, approve, deny)."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionRequest, ActionRequestBody, ApprovalInput, FeatureActionRequest
from ..apimodels import Action
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
    """§12.4: optional approve body. `webauthn` is the passkey assertion over approve-options' challenge.

    sealed: the app's secrets form for app.install (appsecrets/); override: the F-7 owner override.
    """

    plan_sha256: str | None = Field(default=None, max_length=200)
    sealed: SealedInput | None = None
    override: OverrideInput | None = None
    webauthn: dict | None = None


def register(app: FastAPI, gw: Gateway) -> None:
    actions = gw.actions
    principal = gw.principal

    def postable_feature_types() -> list[str]:
        # Only a type registered with a params model is filed through POST /v1/actions; the rest
        # (backup.*, migrate.*, storage.*) have their own routes.
        return sorted(t for t, spec in actions.feature_types.items() if spec.params_model is not None)

    build = app.openapi

    def openapi() -> dict:
        # Feature action types (source.*, exposure.*, ...) are registered at startup, after the models
        # are defined, so the published variant lists them here: /openapi.json never offers a type the
        # server refuses (an unregistered one is a 422 at the body, like a bad lifecycle type).
        doc = build()
        feature = doc.get("components", {}).get("schemas", {}).get("FeatureActionRequest")
        if feature and (posted := postable_feature_types()):
            feature["properties"]["type"] = {"type": "string", "enum": posted, "title": "Type"}
        return doc

    app.openapi = openapi  # type: ignore[method-assign]

    @app.post(
        "/v1/actions",
        tags=["actions"],
        status_code=201,
        operation_id="actions.create",
        responses={
            201: {"model": Action, "description": "Created, in awaiting_approval"},
            200: {"model": Action, "description": "Idempotent replay: the action created earlier with this idempotency_key"},
            **error_responses(401, 403, 404, 409, 422, 429),
        },
    )
    def create_action(req: ActionRequestBody, p: Principal = Depends(principal)):
        if isinstance(req, FeatureActionRequest) and req.type not in postable_feature_types():
            # Same 422 a lifecycle body with a bad type gets: only registered types are requests.
            raise RequestValidationError([{"type": "literal_error", "loc": ("body", "type"),
                                           "msg": f"unknown action type {req.type!r}", "input": req.type}])
        body, created = actions.create(p, ActionRequest.model_validate(req.model_dump()))
        return JSONResponse(status_code=201 if created else 200, content=body)

    @app.get(
        "/v1/actions", tags=["actions"], operation_id="actions.list",
        responses={200: {"model": list[Action]}, **error_responses(401)},
    )
    def list_actions(_: Principal = Depends(principal)):
        return actions.list()

    @app.get(
        "/v1/actions/{action_id}", tags=["actions"], operation_id="actions.get",
        responses={200: {"model": Action}, **error_responses(401, 404, 422)},
    )
    def get_action(action_id: str, _: Principal = Depends(principal)):
        return actions.get(action_id)

    @app.post(
        "/v1/actions/{action_id}/approve", tags=["actions"], operation_id="actions.approve",
        responses={200: {"model": Action}, **error_responses(401, 403, 404, 409, 422)},
    )
    def approve_action(
        action_id: str, request: Request, body: ApproveBody | None = None, p: Principal = Depends(principal)
    ):
        for guard in gw.approval_guards:  # identity: passkey step-up (F-2); raises to refuse
            guard(p, action_id, body.model_dump() if body else {}, request)
        # Clients that send OneMind-API-Version: 1 must name the plan they read (contract §12.4).
        strict = request.headers.get("OneMind-API-Version") == "1"
        extra = ApprovalInput(
            sealed=body.sealed.model_dump(exclude_none=True) if body and body.sealed else None,
            override=body.override.model_dump() if body and body.override else None,
            webauthn=bool(body and body.webauthn),
        )
        return actions.approve(p, action_id, body.plan_sha256 if body else None, strict, extra)

    @app.post(
        "/v1/actions/{action_id}/deny", tags=["actions"], operation_id="actions.deny",
        responses={200: {"model": Action}, **error_responses(401, 403, 404, 409, 422)},
    )
    def deny_action(action_id: str, p: Principal = Depends(principal)):
        return actions.deny(p, action_id)
