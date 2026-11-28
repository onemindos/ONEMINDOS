# SPDX-License-Identifier: Apache-2.0
"""Map site configuration and asset locations (#651)."""
from fastapi import Depends, FastAPI
from sqlalchemy import select

from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..geo.sites import GeoSite, SiteRow
from ..identity.scopes import register_route_scope

ORDER = 252
register_route_scope("GET,HEAD", r"/v1/sites", ("nodes:read",))
register_route_scope("POST", r"/v1/sites", ("geo:admin",))


def register(app: FastAPI, gw: Gateway) -> None:
    def owner(p: Principal = Depends(gw.principal)) -> Principal:
        if not p.is_owner:
            gw.audit.append("authz.denied", p.as_dict(), None, {"attempted": "write geo records"})
            raise ApiError(403, "permission_denied", "Only an owner can write map records")
        return p

    @app.post("/v1/sites", tags=["geo"], operation_id="geo.create_site", status_code=201,
              responses=error_responses(401, 403, 409))
    def create_site(body: GeoSite, p: Principal = Depends(owner)) -> GeoSite:
        with gw.db.session.begin() as s:
            stmt = gw.db.insert()(SiteRow).values(id=body.id, record=body.model_dump())
            created = s.scalar(stmt.on_conflict_do_nothing(index_elements=["id"]).returning(SiteRow.id))
            if created is None:
                raise ApiError(409, "conflict", "Site ID already exists")
        gw.audit.append("geo.site_created", p.as_dict(), None, {"site_id": body.id})
        return body

    @app.get("/v1/sites", tags=["geo"], operation_id="geo.list_sites", responses=error_responses(401, 403))
    def list_sites(p: Principal = Depends(gw.principal)) -> list[GeoSite]:
        with gw.db.session() as s:
            sites = [GeoSite.model_validate(row) for row in s.scalars(select(SiteRow.record).order_by(SiteRow.id))]
        # The owner's address text is the owner's own data: other readers (family, guests, agents with
        # nodes:read) get the site without it. Its anchors still carry the position (flagged for the Map work).
        return sites if p.is_owner else [site.model_copy(update={"address": None}) for site in sites]
