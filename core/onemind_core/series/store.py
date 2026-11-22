# SPDX-License-Identifier: Apache-2.0
"""Minute-resolution history. Store each series key once per hour instead of once per point."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import BigInteger, Column, Float, String, Table, and_, delete, or_, select, update

from ..ledger import Base
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("series")
RETENTION_S = 30 * 86400
Metric = Literal["cpu_pct", "mem_used_mb", "mem_total_mb", "disk_free_gb", "disk_total_gb", "temp_c", "load1"]
MINUTES = tuple(f"m{i:02d}" for i in range(60))
HOURS = Table(
    "series_hours", Base.metadata,
    Column("namespace", String(64), primary_key=True),
    Column("source_id", String(64), primary_key=True),
    Column("metric", String(64), primary_key=True),
    Column("hour", BigInteger, primary_key=True, index=True),
    *(Column(name, Float) for name in MINUTES),
)
# (observed time, source id, metric name, numeric value). Producers own validation and visibility.
Reading = tuple[datetime, str, str, float]


class SeriesStore(SqlRepository):
    def record(self, namespace: str, now: datetime, readings: Iterable[Reading]) -> None:
        """Upsert observed minutes only. Replays and concurrent writers preserve adjacent points."""
        oldest = math.ceil((now.timestamp() - RETENTION_S) / 60)
        latest = int(now.timestamp() // 60)
        blocks: dict[tuple[str, str, int], dict[str, float]] = defaultdict(dict)
        for at, source, metric, value in readings:
            minute = int(at.timestamp() // 60)
            if oldest <= minute <= latest and math.isfinite(value):
                hour, offset = divmod(minute, 60)
                blocks[source, metric, hour][MINUTES[offset]] = value

        # Group rows with the same set of measured minutes for one executemany call.
        # A live monitoring tick has one such group. A replay can contain partial hours.
        batches = defaultdict(list)
        for (source, metric, hour), values in blocks.items():
            batches[tuple(sorted(values))].append(
                {"namespace": namespace, "source_id": source, "metric": metric, "hour": hour, **values})

        with self.db.engine.begin() as conn:
            hour, first = divmod(oldest, 60)
            conn.execute(delete(HOURS).where(HOURS.c.hour < hour))
            if first:  # At the retention boundary, keep only minutes still in the window.
                remaining_empty = and_(*(HOURS.c[k].is_(None) for k in MINUTES[first:]))
                conn.execute(delete(HOURS).where(HOURS.c.hour == hour, remaining_empty))
                expired = MINUTES[:first]
                has_expired = or_(*(HOURS.c[k].is_not(None) for k in expired))
                conn.execute(update(HOURS).where(HOURS.c.hour == hour, has_expired).values({k: None for k in expired}))
            for columns, rows in batches.items():
                insert = self.db.insert()(HOURS)
                conn.execute(insert.on_conflict_do_update(
                    index_elements=list(HOURS.primary_key), set_={k: insert.excluded[k] for k in columns},
                ), rows)

    def query(self, namespace: str, source: str, metric: str, now: datetime, window_s: int, points: int) -> list[dict]:
        end = int(now.timestamp())
        start = end - window_s
        width = window_s // points + 1  # both endpoints are inclusive
        stmt = select(HOURS.c.hour, *(HOURS.c[k] for k in MINUTES)).where(
            HOURS.c.namespace == namespace, HOURS.c.source_id == source, HOURS.c.metric == metric,
            HOURS.c.hour.between(start // 3600, end // 3600),
        ).order_by(HOURS.c.hour)

        bins: dict[int, tuple[int, list[float]]] = {}
        with self.db.engine.connect() as conn:
            for hour, *values in conn.execute(stmt):
                for offset, value in enumerate(values):
                    at = hour * 3600 + offset * 60
                    if value is not None and start <= at <= end:
                        index = (at - start) // width
                        if index not in bins:
                            bins[index] = (at, [])
                        bins[index][1].append(value)
        return [{"at": datetime.fromtimestamp(at, UTC), "value": math.fsum(values) / len(values)}
                for at, values in bins.values()]
