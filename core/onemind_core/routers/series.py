# SPDX-License-Identifier: Apache-2.0
"""Read node heartbeat history after a gateway or node restart."""

from datetime import datetime

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel

from ..auth import Principal
from ..context import Gateway
from ..errors import error_responses
from ..identity.scopes import register_route_scope
from ..series.store import RETENTION_S, Metric

ORDER = 251  # the monitoring service is registered at 250
register_route_scope("GET,HEAD", r"/v1/series", ("monitoring:read",))


class SeriesPoint(BaseModel):
    at: datetime
    value: float


def register(app: FastAPI, gw: Gateway) -> None:
    store = app.state.monitoring.series

    @app.get("/v1/series", operation_id="series.query", tags=["monitoring"], responses=error_responses(401, 403))
    def query(node_id: str = Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"),
              metric: Metric = Query(), window_s: int = Query(86400, ge=1, le=RETENTION_S),
              points: int = Query(60, ge=1, le=500), _: Principal = Depends(gw.principal)) -> list[SeriesPoint]:
        """Query a trailing window of up to 30 days. Each node contributes one sample per
        minute. Return at most `points` averages, timestamped at the first observation in
        each bin. Empty bins and unavailable metrics are omitted."""
        return store.query("node", node_id, metric, gw.clock(), window_s, points)
