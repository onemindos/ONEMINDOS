# SPDX-License-Identifier: Apache-2.0
"""Storage routes (STORAGE-ACT-1, UMB-STOR-5; shapes proposed for contract §12 by UMB-STOR-0).

Reads are direct; every disk change is an action the owner approves at /v1/actions/{id}/approve.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from ..actions import FeatureAction
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..storage import TYPES, StorageActionRequest, StoragePlanRequest, StorageService, StorageSettings


def destructive_step_up(gw: Gateway):
    """Approval guard: a destructive storage action is approved only with a passkey assertion.

    The identity guard (registered earlier, so it runs first) verifies the assertion: signed over this
    action and plan, by an active owner. This guard adds what identity's does not: for these types the
    owner's bare token or password session is never enough, whatever `require_passkey_approval` says,
    because the action erases a disk. With no passkey registered the answer is the same 401, so the
    owner registers one first. Non-owners are not decided here: actions.approve refuses and audits them.
    """

    def guard(p: Principal, action_id: str, body: dict, request: Request) -> None:
        if not p.is_owner:
            return
        try:
            action = gw.actions.get(action_id)
        except ApiError:
            return  # unknown id: the approve route answers 404
        spec = TYPES.get(action.get("type"))
        if spec is None or spec[1] != "destructive":
            return
        if body.get("webauthn") is None or not _identity_guard_present(gw):
            gw.events.publish_event(
                "auth", "step_up.required",
                {"attempted": "approve", "action_id": action_id, "type": action.get("type"), "reason": "destructive_storage_needs_passkey"},
                principal=p.as_dict(), severity="warning", action_id=action_id)
            raise ApiError(401, "unauthenticated", "erasing a disk needs your passkey: register one, then approve with it",
                           reason="step_up_required")

    return guard


def _identity_guard_present(gw: Gateway) -> bool:
    """The assertion is only worth anything if the identity guard (which verifies it) is installed
    and ran before this one: it is the first entry in approval_guards."""
    return any(getattr(g, "__name__", "") == "approval_guard" for g in gw.approval_guards)


def register(app: FastAPI, gw: Gateway) -> None:
    svc = StorageService(gw)
    for action_type, (_, risk, requesters) in TYPES.items():
        gw.actions.register_type(action_type, FeatureAction(risk, svc.run, requesters, check=svc.recheck))
    gw.approval_guards.append(destructive_step_up(gw))
    gw.on_startup(svc.start)
    gw.on_shutdown(svc.stop)
    app.state.storage = svc
    principal = gw.principal

    def owner(p: Principal) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "storage owner read", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may do this")

    @app.get("/v1/storage", tags=["storage"], operation_id="storage.summary", responses=error_responses(401))
    def storage_summary(_: Principal = Depends(principal)):
        """The data set of this box: state, members, running operation. No disk identities."""
        return svc.summary()

    @app.get("/v1/storage/devices", tags=["storage"], operation_id="storage.devices.list", responses=error_responses(401, 403, 409))
    def storage_devices(p: Principal = Depends(principal)):
        """Every disk with its role and health (full serials: owners only)."""
        owner(p)
        return svc.devices()

    @app.post("/v1/storage/plans", tags=["storage"], operation_id="storage.plans.create", responses=error_responses(401, 403, 409, 422))
    def storage_plan(req: StoragePlanRequest, p: Principal = Depends(principal)):
        """Dry run: the plan a storage action would get. Nothing is filed or changed."""
        return svc.plan(p, req)

    @app.post(
        "/v1/storage/actions", tags=["storage"], operation_id="storage.actions.create", status_code=202,
        responses={200: {"description": "Idempotent replay"}, **error_responses(401, 403, 409, 422)},
    )
    def storage_request(
        req: StorageActionRequest, p: Principal = Depends(principal),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    ):
        """Request a storage action; it waits for the owner's approval with its plan."""
        body, created = svc.request(p, req, idempotency_key)
        return JSONResponse(status_code=202 if created else 200, content=body,
                            headers={"Location": f"/v1/actions/{body['action']['id']}"})

    @app.get("/v1/storage/operations/{action_id}", tags=["storage"], operation_id="storage.operations.get", responses=error_responses(401, 403, 404))
    def storage_operation(action_id: str, p: Principal = Depends(principal)):
        """The stored plan and, while it runs, the node's journal (step by step)."""
        if not p.can_request_actions:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "read storage operation", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only requesters and owners read storage operations")
        return svc.operation(action_id, p)

    @app.post("/v1/storage/recovery-key", tags=["storage"], operation_id="storage.recovery_key.take", responses=error_responses(401, 403, 404, 409))
    def storage_recovery_key(p: Principal = Depends(principal)):
        """The data set's recovery key, once (H-11). Never stored by the gateway, never shown again."""
        owner(p)
        if not gw.settings.section(StorageSettings).recovery_key_api:  # pending F-61/F-62/F-63: off by default
            raise ApiError(404, "not_found", "the recovery key is not available through the API on this box")
        return JSONResponse(content=svc.take_recovery_key(p), headers={"Cache-Control": "no-store"})
