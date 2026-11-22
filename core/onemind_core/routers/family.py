# SPDX-License-Identifier: Apache-2.0
"""FAM-01: private owner-managed family profiles and app classifications."""
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..family import AppClassification, FamilyProfile, FamilyService
from ..identity import ctx_of
from ..identity.scopes import register_route_scope

ORDER = 265  # identity must be registered first
register_route_scope("GET,HEAD", r"/v1/family/profiles/[^/]+", ("users:read",))
register_route_scope("PUT", r"/v1/family/profiles/[^/]+", ("users:admin",))
register_route_scope("GET,HEAD", r"/v1/family/apps/[^/]+", ("users:read",))
register_route_scope("PUT", r"/v1/family/apps/[^/]+", ("users:admin",))


def register(app: FastAPI, gw: Gateway) -> None:
    svc = FamilyService(gw, app.state.identity)
    gw.app_filters.append(svc.app_filter)
    app.state.family = svc
    principal = gw.principal

    def private(policy):
        return JSONResponse(policy.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    @app.get("/v1/family/profiles/{user_id}", operation_id="family.profiles.get", tags=["family"],
             response_model=FamilyProfile, responses=error_responses(401, 403, 404))
    def get_profile(user_id: str, p: Principal = Depends(principal)):
        return private(svc.profile(p, user_id))

    @app.put("/v1/family/profiles/{user_id}", operation_id="family.profiles.set", tags=["family"],
             response_model=FamilyProfile, responses=error_responses(401, 403, 404, 422))
    def put_profile(user_id: str, body: FamilyProfile, request: Request, p: Principal = Depends(principal)):
        """Replace a person's controls. Owner only, with the existing passkey step-up rules."""
        return private(svc.put_profile(ctx_of(request), p, user_id, body))

    @app.get("/v1/family/apps/{app_id}", operation_id="family.apps.get", tags=["family"],
             response_model=AppClassification, responses=error_responses(401, 403, 404))
    def get_classification(app_id: str, p: Principal = Depends(principal)):
        return private(svc.classification(p, app_id))

    @app.put("/v1/family/apps/{app_id}", operation_id="family.apps.set", tags=["family"],
             response_model=AppClassification, responses=error_responses(401, 403, 404, 422))
    def put_classification(app_id: str, body: AppClassification, request: Request, p: Principal = Depends(principal)):
        return private(svc.put_classification(ctx_of(request), p, app_id, body))
