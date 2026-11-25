# SPDX-License-Identifier: Apache-2.0
"""Gateway catalogue of installed basemap packs. The Offline Maps app serves the bytes."""
from fastapi import Depends, FastAPI

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..geo.map_packs import MapPacks, MapSettings, Packs
from ..identity.scopes import register_route_scope

ORDER = 253

# Same read scope as Map sites (routers/geo.py).
register_route_scope("GET,HEAD", r"/v1/map/packs", ("nodes:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    service = MapPacks(gw, gw.settings.section(MapSettings))
    app.state.map_packs = service

    @app.get("/v1/map/packs", tags=["map"], operation_id="map.packs_list",
             responses=error_responses(401, 403, 503))
    def list_packs(_: Principal = Depends(gw.principal)) -> Packs:
        return service.list()
