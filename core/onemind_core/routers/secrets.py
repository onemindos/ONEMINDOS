# SPDX-License-Identifier: Apache-2.0
"""App secrets (DEPLOYMENTS.md §7, contract §12.1 sealed input, §12.18 spec.secrets).

GET  /v1/secrets/public-key      any principal: the key browsers seal forms to
GET  /v1/apps/{id}/secrets       any principal: declarations and set flags, never a value
POST /v1/apps/{id}/secrets       owner: files app.configure with the changes staged (202)

Install-time values travel in the approve body (routers/actions.py). Logic: appsecrets/service.py.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse

from ..appsecrets.api import SecretsChange
from ..appsecrets.service import AppSecretsService, SecretsSettings, load_store_key
from ..appsecrets.store import SecretsRepository
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses


def register(app: FastAPI, gw: Gateway) -> None:
    key = load_store_key(gw.settings.section(SecretsSettings), gw.settings.audit_path)
    svc = AppSecretsService(SecretsRepository(gw.db), key, gw.catalog, gw.repo, gw.audit, gw.events, gw.clock)
    gw.actions.app_secrets = svc
    gw.on_startup(svc.purge)
    app.state.app_secrets = svc
    principal = gw.principal

    @app.get("/v1/secrets/public-key", tags=["secrets"], responses=error_responses(401))
    def public_key(_: Principal = Depends(principal)):
        return svc.public_key()

    @app.get("/v1/apps/{app_id}/secrets", tags=["secrets"], responses=error_responses(401, 404))
    def describe(app_id: str, _: Principal = Depends(principal)):
        return svc.describe(svc.app(app_id))

    @app.post(
        "/v1/apps/{app_id}/secrets", tags=["secrets"], status_code=202,
        responses={200: {"description": "Idempotent replay"}, **error_responses(401, 403, 404, 409, 422)},
    )
    def change(
        app_id: str, body: SecretsChange, p: Principal = Depends(principal),
        idempotency_key: str | None = Header(default=None, max_length=200),
    ):
        action, created = svc.request_change(
            gw.actions, p, app_id,
            sealed=body.sealed.model_dump(exclude_none=True) if body.sealed else None,
            generate=body.generate, clear=body.clear, reason=body.reason,
            idempotency_key=idempotency_key, expires_at=body.expires_at,
        )
        return JSONResponse(
            status_code=202 if created else 200, content=action, headers={"Location": f"/v1/actions/{action['id']}"}
        )
