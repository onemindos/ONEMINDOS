# SPDX-License-Identifier: Apache-2.0
"""Prometheus text exposition (format 0.0.4) of what the gateway already knows.

Nothing new is measured here. The node numbers are the newest sample of each node's heartbeat
history (`metrics.NodeHistory`), the app numbers are the watcher's health states, and the alert
numbers are the open alerts. Prometheus then keeps the history (30 days in the default
monitoring bundle), which the in-memory 24 h history cannot.
"""

from __future__ import annotations

from collections.abc import Iterable

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
APP_STATES = ("healthy", "unhealthy", "starting", "stopped", "unknown")
NODE_STATUSES = ("online", "stale", "offline")
SEVERITIES = ("info", "warning", "critical")
_MB, _GB = 1024 * 1024, 1e9


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _fmt(v: float) -> str:
    return repr(float(v)) if v != int(v) else str(int(v))


class _Out:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def family(self, name: str, help_: str, kind: str, samples: Iterable[tuple[dict[str, str], float | None]]) -> None:
        rows = [(lb, v) for lb, v in samples if v is not None]
        if not rows:
            return
        self.lines += [f"# HELP {name} {help_}", f"# TYPE {name} {kind}"]
        for lb, v in rows:
            tag = "{" + ",".join(f'{k}="{_esc(x)}"' for k, x in sorted(lb.items())) + "}" if lb else ""
            self.lines.append(f"{name}{tag} {_fmt(v)}")


def render(nodes: list[dict], latest: dict[str, dict | None], app_states: dict[str, str],
           alert_counts: dict[str, int], version: str = "") -> str:
    """`nodes` are registry views, `latest` maps node id to its newest history sample (or None)."""
    o = _Out()
    if version:
        o.family("onemind_build_info", "Gateway version.", "gauge", [({"version": version}, 1)])
    by_status = {s: 0 for s in NODE_STATUSES}
    for n in nodes:
        by_status[n["status"]] = by_status.get(n["status"], 0) + 1
    o.family("onemind_nodes", "Nodes by liveness status.", "gauge", [({"status": s}, c) for s, c in by_status.items()])
    per_node = (
        ("onemind_node_cpu_percent", "CPU use, percent, newest sample.", "cpu_pct", 1),
        ("onemind_node_memory_used_bytes", "Memory in use.", "mem_used_mb", _MB),
        ("onemind_node_memory_total_bytes", "Memory installed.", "mem_total_mb", _MB),
        ("onemind_node_disk_free_bytes", "Free space on the data volume.", "disk_free_gb", _GB),
        ("onemind_node_disk_total_bytes", "Size of the data volume.", "disk_total_gb", _GB),
        ("onemind_node_temperature_celsius", "Hottest sensor.", "temp_c", 1),
        ("onemind_node_load1", "One-minute load average.", "load1", 1),
    )
    for name, help_, key, scale in per_node:
        o.family(name, help_, "gauge", [
            ({"node": n["node_id"]}, None if (s := latest.get(n["node_id"])) is None or s.get(key) is None
             else s[key] * scale) for n in nodes])
    o.family("onemind_app_health", "1 for the state each installed app is in now.", "gauge", [
        ({"app": a, "state": s}, 1 if app_states.get(a, "unknown") == s else 0)
        for a in sorted(app_states) for s in APP_STATES])
    o.family("onemind_alerts_open", "Open alerts by severity.", "gauge",
             [({"severity": s}, alert_counts.get(s, 0)) for s in SEVERITIES])
    return "\n".join(o.lines) + "\n"
