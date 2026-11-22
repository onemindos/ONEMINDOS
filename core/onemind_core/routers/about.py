# SPDX-License-Identifier: Apache-2.0
"""GET /v1/os/about: the device facts of "About this box" (UMB-P14, #432), from the node heartbeats."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from ..about import about
from ..apimodels import About
from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope

ORDER = 336

# The same facts /v1/nodes shows, so the same scope reads them (#323).
register_route_scope("GET,HEAD", r"/v1/os/about", ("nodes:read",))


def register(app: FastAPI, gw: Gateway) -> None:
    @app.get("/v1/os/about", tags=["os"], operation_id="os.about",
             responses={200: {"model": About}, **error_responses(401)})
    def os_about(_: Principal = Depends(gw.principal)):
        """Hostname, OneMind version and A/B slot, Debian base, kernel, CPU, memory, disk, uptime and board
        per node, and how many nodes the hub knows. No serial numbers and no addresses, ever."""
        return about(gw)
