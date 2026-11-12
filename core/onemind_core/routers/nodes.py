# SPDX-License-Identifier: Apache-2.0
"""Contract §3: GET /v1/nodes and /v1/nodes/{node_id} from the heartbeat registry."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..apimodels import Node
from ..auth import Principal
from ..context import Gateway
from ..errors import ApiError, error_responses


def register(app: FastAPI, gw: Gateway) -> None:
    registry = gw.registry
    principal = gw.principal

    @app.get("/v1/nodes", tags=["nodes"], operation_id="nodes.list", responses={200: {"model": list[Node]}, **error_responses(401)})
    def list_nodes(_: Principal = Depends(principal)):
        return registry.list()

    @app.get(
        "/v1/nodes/{node_id}", tags=["nodes"], operation_id="nodes.get",
        responses={200: {"model": Node}, **error_responses(401, 404, 422)},
    )
    def get_node(node_id: str, _: Principal = Depends(principal)):
        node = registry.get(node_id)
        if node is None:
            raise ApiError(404, "not_found", "no such node")
        return node
