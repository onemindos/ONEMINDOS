# SPDX-License-Identifier: Apache-2.0
"""Contract §3: GET /v1/nodes and /v1/nodes/{node_id} from the heartbeat registry."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..apimodels import Node, RadioCard
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses
from ..identity.scopes import register_route_scope
from ..radios import cards as radio_cards
from ..wake import WakeCapability, WakeService


# Route order in the app and in /openapi.json (routers/__init__.py).
ORDER = 110

# The radio-found cards come from the hardware profile, so they need what the profile needs (#732).
register_route_scope("GET,HEAD", r"/v1/radios", ("nodes:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    registry = gw.registry
    principal = gw.principal
    wake = WakeService(gw)

    @app.get(
        "/v1/nodes/{node_id}/wake", tags=["nodes"], operation_id="nodes.wake_capability",
        response_model=WakeCapability, responses=error_responses(401, 404),
    )
    def wake_capability(node_id: str, _: Principal = Depends(principal)):
        if registry.get(node_id) is None:
            raise ApiError(404, "not_found", "no such node")
        return wake.capability(node_id)

    @app.get("/v1/nodes", tags=["nodes"], operation_id="nodes.list", responses={200: {"model": list[Node]}, **error_responses(401)})
    def list_nodes(_: Principal = Depends(principal)):
        return registry.list()

    @app.get(
        "/v1/radios", tags=["nodes"], operation_id="radios.list",
        response_model=list[RadioCard], responses=error_responses(401),
    )
    def list_radios(_: Principal = Depends(principal)):
        """Radio-found cards: every USB serial line on every machine; known radios carry kind and device (#732)."""
        return radio_cards(registry.list())

    @app.get(
        "/v1/nodes/{node_id}", tags=["nodes"], operation_id="nodes.get",
        responses={200: {"model": Node}, **error_responses(401, 404, 422)},
    )
    def get_node(node_id: str, _: Principal = Depends(principal)):
        node = registry.get(node_id)
        if node is None:
            raise ApiError(404, "not_found", "no such node")
        return node
