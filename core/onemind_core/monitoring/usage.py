# SPDX-License-Identifier: Apache-2.0
"""Live usage (UMB-P11, #429): CPU, memory, disk and temperature per machine, and per app.

Nothing here is measured by this module; it only joins what the gateway already has:

- per machine: the latest heartbeat (memory, disk, the optional `metrics` object) through the same
  `sample_from` the history uses, and metrics-server CPU for k3s nodes whose agent reports none.
  A machine whose last heartbeat is old is returned with `stale: true` (and its age), never as live.
- per app: CPU and memory from metrics-server (`kubectl get --raw /apis/metrics.k8s.io`), and the bytes
  used on the app's volume claims from the kubelet's stats summary. A number the runtime does not report is
  `null`, not 0. The per-app block is cached for a few seconds so that several open panels do not make the
  gateway run kubectl on every poll; when a refresh fails, the last good reading is served with its own
  `sampled_at` and `stale: true` once it is older than `APPS_STALE_AFTER_S`.
"""

from __future__ import annotations

import threading
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..apimodels import OPEN_ENUM
from ..ledger import iso
from .health import parse_time
from .kube import pvc_usage
from .metrics import sample_from

APPS_CACHE_S = 5
APPS_STALE_AFTER_S = 30


class UsageNode(BaseModel):
    """One machine's latest heartbeat reading."""

    model_config = ConfigDict(extra="allow")
    node_id: str
    hostname: str | None = None
    status: str = Field(description="online | stale | offline (from the heartbeat age)", json_schema_extra=OPEN_ENUM)
    stale: bool = Field(description="True when the last heartbeat is older than 30 s: the numbers are not current")
    last_seen: str
    age_s: int = Field(description="Seconds since the gateway last heard from the machine")
    cpus: float | None = None
    cpu_pct: float | None = Field(default=None, description="null when the machine reports no CPU figure")
    load1: float | None = None
    mem_used_mb: float | None = None
    mem_total_mb: float | None = None
    disk_used_gb: float | None = None
    disk_total_gb: float | None = None
    temp_c: float | None = Field(default=None, description="null when the hardware reports no temperature")
    cpu_source: str = Field(description="heartbeat | metrics-server", json_schema_extra=OPEN_ENUM)


class UsageApp(BaseModel):
    app_id: str
    name: str | None = None
    cpu_millicores: float | None = Field(default=None, description="null when the runtime reports no figure")
    mem_mb: float | None = None
    disk_mb: float | None = Field(default=None, description="Bytes used on the app's volume claims, in MB; null when unknown")


class UsageApps(BaseModel):
    source: str = Field(description="kubernetes | unavailable", json_schema_extra=OPEN_ENUM)
    sampled_at: str | None = Field(description="When these numbers were read from the runtime; null if never")
    stale: bool = Field(description="True when sampled_at is older than 30 s, or nothing was ever read")
    items: list[UsageApp]


class Usage(BaseModel):
    """GET /v1/usage."""

    at: str
    nodes: list[UsageNode]
    apps: UsageApps


def _mb(v: float | None) -> float | None:
    return None if v is None else round(v / 1e6, 1)


class UsageReader:
    def __init__(self, mon):
        self.mon = mon
        self._lock = threading.Lock()
        self._rows: list[dict] | None = None
        self._at: datetime | None = None

    # ---- machines -----------------------------------------------------------------------
    def nodes(self, now: datetime) -> list[dict]:
        kube = self.mon.kube
        ms = kube.node_metrics() if kube is not None else None
        out = []
        for n in self.mon.gw.registry.list():
            host = n.get("hostname") or n["node_id"]
            sample, source = sample_from(n, now, (ms or {}).get(host))
            seen = parse_time(n.get("last_seen"))
            age = max(0, int((now - seen).total_seconds())) if seen else 0
            dt, df = sample["disk_total_gb"], sample["disk_free_gb"]
            out.append({
                "node_id": n["node_id"], "hostname": n.get("hostname"), "status": n["status"],
                "stale": n["status"] != "online", "last_seen": n["last_seen"], "age_s": age,
                "cpus": n.get("cpus") if isinstance(n.get("cpus"), (int, float)) else None,
                "cpu_pct": sample["cpu_pct"], "load1": sample["load1"],
                "mem_used_mb": sample["mem_used_mb"], "mem_total_mb": sample["mem_total_mb"],
                "disk_used_gb": None if dt is None or df is None else round(dt - df, 1), "disk_total_gb": dt,
                "temp_c": sample["temp_c"], "cpu_source": source,
            })
        return out

    # ---- apps ---------------------------------------------------------------------------
    def _read_apps(self) -> list[dict] | None:
        """One reading of every installed app, or None when the runtime could not be read at all."""
        kube = self.mon.kube
        if kube is None:
            return None
        rows, reached = [], False
        node_stats: dict[str, dict | None] = {}
        for app_id in self.mon.installed_apps():
            ns = f"app-{app_id}"
            pods = kube.pods(ns)
            cpu = mem = disk = None
            if pods is not None:
                reached = True
                usage = kube.pod_metrics(ns)
                if usage is not None:
                    cpu = round(sum(c or 0 for u in usage.values() for c, _ in u.values()), 1)
                    mem = round(sum(m or 0 for u in usage.values() for _, m in u.values()), 1)
                names = {(p.get("spec") or {}).get("nodeName") for p in pods} - {None, ""}
                vols: dict[str, float] = {}
                for node in names:
                    if node not in node_stats:
                        node_stats[node] = kube.node_stats(node)
                    vols.update(pvc_usage(node_stats[node], ns))
                if names and all(node_stats[n] is not None for n in names):
                    disk = _mb(sum(vols.values()))
            entry = self.mon.gw.catalog.get(app_id)
            rows.append({"app_id": app_id, "name": (entry.manifest.get("metadata") or {}).get("name") if entry else None,
                         "cpu_millicores": cpu, "mem_mb": mem, "disk_mb": disk})
        return rows if reached or not rows else None

    def apps(self, now: datetime) -> dict:
        with self._lock:
            fresh = self._at is not None and (now - self._at).total_seconds() < APPS_CACHE_S
            if not fresh:
                rows = self._read_apps()
                if rows is not None:
                    self._rows, self._at = rows, now
            if self._rows is None or self._at is None:
                return {"source": "unavailable", "sampled_at": None, "stale": True, "rows": []}
            age = (now - self._at).total_seconds()
            return {"source": "kubernetes", "sampled_at": iso(self._at), "stale": age > APPS_STALE_AFTER_S,
                    "rows": list(self._rows)}
