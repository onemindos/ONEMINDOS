# SPDX-License-Identifier: Apache-2.0
"""Node metric history: one sample per node per minute, kept in memory for 24 h (contract §12.15).

Samples come from heartbeats (memory, disk, and the optional `metrics` object: CPU, load,
temperature) and, for CPU on k3s nodes whose agent does not report it, from metrics-server.
Nothing is written to disk: a restart starts an empty history (history beyond 24 h, or across
restarts, is a Market app's job).
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timedelta

from ..ledger import iso

KEEP = 24 * 60          # samples per node (one per minute)
SAMPLE_EVERY_S = 60


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def sample_from(hb: dict, at: datetime, metrics_server_cpu_m: float | None = None) -> tuple[dict, str]:
    """(sample, source) from one heartbeat view."""
    m = hb.get("metrics") if isinstance(hb.get("metrics"), dict) else {}
    mem_total, mem_avail = _num(hb.get("mem_total_mb")), _num(hb.get("mem_available_mb"))
    disk_total, disk_free = _num(hb.get("disk_total_gb")), _num(hb.get("disk_free_gb"))
    st = hb.get("storage") if isinstance(hb.get("storage"), dict) else None
    if st and _num(st.get("free_bytes")) is not None and _num(st.get("used_bytes")) is not None:
        free, used = float(st["free_bytes"]), float(st["used_bytes"])
        if free + used > 0:  # §12.10: the /data volume, which is what fills up
            disk_free, disk_total = round(free / 1e9, 1), round((free + used) / 1e9, 1)
    cpu = _num(m.get("cpu_pct"))
    source = "heartbeat"
    cpus = _num(hb.get("cpus"))
    if cpu is None and metrics_server_cpu_m is not None and cpus:
        cpu, source = round(min(100.0, metrics_server_cpu_m / (cpus * 1000) * 100), 1), "metrics-server"
    sample = {
        "at": iso(at), "cpu_pct": cpu,
        "mem_used_mb": None if mem_total is None or mem_avail is None else mem_total - mem_avail,
        "mem_total_mb": mem_total, "disk_free_gb": disk_free, "disk_total_gb": disk_total,
        "temp_c": _num(m.get("temp_c")), "load1": _num(m.get("load1")),
    }
    return sample, source


class NodeHistory:
    def __init__(self):
        self._lock = threading.Lock()
        self._samples: dict[str, deque] = {}
        self._last: dict[str, datetime] = {}
        self._source: dict[str, str] = {}

    def add(self, node_id: str, sample: dict, source: str, at: datetime) -> bool:
        with self._lock:
            last = self._last.get(node_id)
            if last is not None and (at - last).total_seconds() < SAMPLE_EVERY_S:
                return False
            self._samples.setdefault(node_id, deque(maxlen=KEEP)).append((at, sample))
            self._last[node_id] = at
            self._source[node_id] = source
            return True

    def window(self, node_id: str, now: datetime, seconds: int) -> tuple[list[dict], str]:
        cutoff = now - timedelta(seconds=seconds)
        with self._lock:
            items = list(self._samples.get(node_id, ()))
            source = self._source.get(node_id, "heartbeat")
        return [s for at, s in items if at >= cutoff], source

    def recent(self, node_id: str, n: int) -> list[dict]:
        with self._lock:
            items = list(self._samples.get(node_id, ()))
        return [s for _, s in items[-n:]]
