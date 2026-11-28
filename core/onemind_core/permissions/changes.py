# SPDX-License-Identifier: Apache-2.0
"""File and run permission-increasing settings changes through the action ledger (D-028)."""

from collections.abc import Callable
from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from ..actions import FeatureAction
from ..apimodels import Action
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError
from ..executors import ExecResult

QUEUED = {202: {"model": Action, "description": "Change awaiting the owner's action-bound approval"}}


def owner_has_passkey(app: FastAPI) -> bool:
    identity = getattr(app.state, "identity", None)
    return bool(identity is not None and identity.passkeys_active())


def require_owner_passkey(app: FastAPI) -> None:
    if not owner_has_passkey(app):
        raise ApiError(409, "conflict", "add a passkey first: nothing is loosened before the owner has one",
                       reason="no_owner_passkey")


def request_change(app: FastAPI, gw: Gateway, p: Principal, kind: str, params: dict,
                   *, idempotency_key: str | None = None) -> JSONResponse:
    require_owner_passkey(app)
    action, _ = gw.actions.request_feature(p, kind, params, idempotency_key=idempotency_key or str(uuid4()),
                                           expires_at=gw.clock() + timedelta(minutes=15), pending_cap=True)
    return JSONResponse(status_code=202, content=action)


def register_change(app: FastAPI, gw: Gateway, kind: str, apply: Callable[[Principal, dict], object]) -> None:
    def run(action, finish):
        try:
            require_owner_passkey(app)
            owner = Principal(action.decided_by["id"], "person", "owner")
            result = apply(owner, action.params)
        except ApiError as exc:
            finish(ExecResult("failed", exc.message))
            return
        if isinstance(result, ExecResult):
            finish(result)
            return
        steps = [{"policy_id": result["id"]}] if kind == "policy.rule.create" else []
        finish(ExecResult("succeeded", "Permission change applied", steps=steps))

    gw.actions.register_type(kind, FeatureAction("sensitive", run, approval_level=2))
