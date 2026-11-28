# SPDX-License-Identifier: Apache-2.0
"""Contract §3: the action ledger routes (request, list, get, approve, deny)."""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..actions import ActionRequest, ActionRequestBody, ApprovalInput, FeatureActionRequest
from ..agent_stop import is_agent
from ..ai_policy import actions_for_agent
from ..apimodels import Action
from ..appsecrets.api import SealedInput
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.approver_keys import DeviceSignature
from ..jsonbody import JsonBody
from .identity import PasswordTotpProof
from ..plugins.actions import own_actions, own_action
from ..taint import agent_answer, answer_source, rest_source
from .apps import app_rows


class OverrideInput(BaseModel):
    """F-7 owner override (override.py): why, and the app id typed as confirmation."""

    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=2000)
    confirm: str = Field(max_length=200)


class ApproveBody(JsonBody):
    """§12.4: optional approve body. `webauthn` is the passkey assertion over approve-options' challenge.

    sealed: the app's secrets form for app.install (appsecrets/); override: the F-7 owner override.
    """

    plan_sha256: str | None = Field(default=None, max_length=200)
    sealed: SealedInput | None = None
    override: OverrideInput | None = None
    accept_licence: str | None = Field(
        default=None, max_length=200,
        description="#173: the app id typed by the owner to accept a licence class that is not green "
        "(blocked or unknown). Required to approve app.install for such an app; ignored otherwise.",
    )
    webauthn: dict | None = None
    password_totp: PasswordTotpProof | None = None
    box_code: str | None = Field(default=None, max_length=12, description="D-028 / N-1 b: the code the box's own "
                                 "screen shows, when approve-options said box_code_required")
    # #702: or a phone approver key's signature over approve-options' device_payload (identity guard).
    device_signature: DeviceSignature | None = None
    # #723 hold-to-approve: how long the approve control was held, in ms (a physical action needs
    # at least actions.HOLD_MIN_MS, with a passkey assertion and plan_sha256).
    hold_ms: int | None = Field(default=None, ge=0, le=600000)


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 150


def register(app: FastAPI, gw: Gateway) -> None:
    actions = gw.actions
    principal = gw.principal

    def taint_rest_reads(request: Request, p: Principal) -> None:
        """AIG-04: an agent that reads over REST is tainted like one that reads over MCP (taint.py).

        Marked when the caller is known, before the route runs: a read that then fails still counts,
        which can only make the agent wait for a person, never the other way round.
        """
        if is_agent(p):
            source = rest_source(request.scope)
            if source is not None:
                actions.taint.mark(p.id, source)

    gw.principal_guards.append(taint_rest_reads)

    def seen_by(p: Principal, rows: list[dict]) -> list[dict]:
        # aiPolicy (#165): an app's tool output reaches an agent only when the app allows app data
        # to go to an AI, the same rule as the MCP tools. People and plugins see the action as stored.
        if is_agent(p):
            return actions_for_agent(rows, lambda: app_rows(gw))
        for view in gw.action_views:  # identity: required_level on a request waiting for approval (D-028)
            rows = [view(r) for r in rows]
        return rows

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
    def create_action(req: ActionRequestBody, request: Request, p: Principal = Depends(principal)):
        if isinstance(req, FeatureActionRequest) and req.type not in postable_feature_types():
            # Same 422 a lifecycle body with a bad type gets: only registered types are requests.
            raise RequestValidationError([{"type": "literal_error", "loc": ("body", "type"),
                                           "msg": f"unknown action type {req.type!r}", "input": req.type}])
        body, created = actions.create(p, ActionRequest.model_validate(req.model_dump()))
        if is_agent(p):  # AIG-04: the agent's answer carries no third-party text (taint.agent_answer)
            body = agent_answer(body)
            if source := answer_source(request.scope, body):
                actions.taint.mark(p.id, source)
        # An idempotent replay returns the stored action, result included.
        return JSONResponse(status_code=201 if created else 200, content=seen_by(p, [body])[0])

    @app.get(
        "/v1/actions", tags=["actions"], operation_id="actions.list",
        responses={200: {"model": list[Action]}, **error_responses(401)},
    )
    def list_actions(p: Principal = Depends(principal)):
        if p.kind == "plugin":
            return own_actions(gw, p)
        return seen_by(p, actions.list())

    @app.get(
        "/v1/actions/{action_id}", tags=["actions"], operation_id="actions.get",
        responses={200: {"model": Action}, **error_responses(401, 404, 422)},
    )
    def get_action(action_id: str, p: Principal = Depends(principal)):
        if p.kind == "plugin":
            return own_action(gw, p, action_id)
        return seen_by(p, [actions.get(action_id)])[0]

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
            accept_licence=body.accept_licence if body else None,
            webauthn=bool(body and body.webauthn),
            verified_presence=bool(getattr(request.state, "action_bound_proof", False)),
            hold_ms=body.hold_ms if body else None,
        )
        action = actions.approve(p, action_id, body.plan_sha256 if body else None, strict, extra)
        for observe in gw.approval_observers:
            observe(request, p, action)
        return action

    @app.post(
        "/v1/actions/{action_id}/deny", tags=["actions"], operation_id="actions.deny",
        responses={200: {"model": Action}, **error_responses(401, 403, 404, 409, 422)},
    )
    def deny_action(action_id: str, p: Principal = Depends(principal)):
        return actions.deny(p, action_id)
