# SPDX-License-Identifier: Apache-2.0
"""Storage routes (STORAGE-ACT-1, UMB-STOR-5; shapes proposed for contract §12 by UMB-STOR-0).

Reads are direct; every disk change is an action the owner approves at /v1/actions/{id}/approve.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..storage import TYPES, StorageActionRequest, StoragePlanRequest, StorageService


def register(app: FastAPI, gw: Gateway) -> None:
    svc = StorageService(gw)
    for action_type in TYPES:
        gw.actions.register_type(action_type, svc)
    gw.on_startup(svc.start)
    gw.on_shutdown(svc.stop)
    app.state.storage = svc
    principal = gw.principal

    def owner(p: Principal) -> None:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "storage owner read", "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may do this")

    @app.get("/v1/storage", tags=["storage"], responses=error_responses(401))
    def storage_summary(_: Principal = Depends(principal)):
        """The data set of this box: state, members, running operation. No disk identities."""
        return svc.summary()

    @app.get("/v1/storage/devices", tags=["storage"], responses=error_responses(401, 403, 409))
    def storage_devices(p: Principal = Depends(principal)):
        """Every disk with its role and health (full serials: owners only)."""
        owner(p)
        return svc.devices()

    @app.post("/v1/storage/plans", tags=["storage"], responses=error_responses(401, 403, 409, 422))
    def storage_plan(req: StoragePlanRequest, p: Principal = Depends(principal)):
        """Dry run: the plan a storage action would get. Nothing is filed or changed."""
        return svc.plan(p, req)

    @app.post(
        "/v1/storage/actions", tags=["storage"], status_code=202,
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

    @app.get("/v1/storage/operations/{action_id}", tags=["storage"], responses=error_responses(401, 403, 404))
    def storage_operation(action_id: str, p: Principal = Depends(principal)):
        """The stored plan and, while it runs, the node's journal (step by step)."""
        if not p.can_request_actions:
            raise ApiError(403, "permission_denied", "only requesters and owners read storage operations")
        return svc.operation(action_id, p)

    @app.post("/v1/storage/recovery-key", tags=["storage"], responses=error_responses(401, 403, 404, 409))
    def storage_recovery_key(p: Principal = Depends(principal)):
        """The data set's recovery key, once (H-11). Never stored by the gateway, never shown again."""
        owner(p)
        return JSONResponse(content=svc.take_recovery_key(p), headers={"Cache-Control": "no-store"})
