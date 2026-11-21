# SPDX-License-Identifier: Apache-2.0
"""About this box (UMB-P14, #432): the facts an owner reads out when asking for help.

Read from the node heartbeats the registry already holds (internal/heartbeat, contract section 2):
hostname, board, kernel, Debian base, CPU, memory, disk, uptime, plus the OneMind version and the
booted A/B slot that the OS updates view (osupdate.node_view, #142) already derives. Nothing here
is a new data path.

Heartbeats come from any LAN device (no NATS users yet, H-06), so every field is rebuilt from an
allow-list and re-checked: a wrong type becomes null, text is cut, numbers are range-checked. A
serial number or an address can never appear, because no such field is ever copied across (and the
box never sends one, contract section 2). The node id is the one stable identifier left; the dashboard
and the CLI leave it out of "copy details" unless the owner asks for it.
"""

from __future__ import annotations

from .osupdate import node_view

MAX_ABOUT_NODES = 64  # a household fabric is a handful of machines (the registry caps at 256)


def _text(v: object, n: int = 128) -> str | None:
    return v[:n] if isinstance(v, str) and v else None


def _count(v: object, hi: int) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= hi else None


def _gb(v: object) -> float | None:
    ok = isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1e7 and v == v
    return round(float(v), 1) if ok else None


def about_node(n: dict) -> dict:
    """One node's device facts, rebuilt from its heartbeat."""
    os_ = n.get("os") if isinstance(n.get("os"), dict) else {}
    v = node_view(n)
    return {
        "node_id": v["node_id"],
        "hostname": v["hostname"],
        "role": _text(n.get("role"), 16),
        "board": _text(n.get("board"), 32),
        "arch": _text(n.get("arch"), 32),
        "status": v["status"],
        "last_seen": v["last_seen"],
        "os_pretty": _text(os_.get("pretty")),
        "os_id": _text(os_.get("id"), 32),
        "os_version_id": _text(os_.get("version_id"), 32),
        "onemind_version": v["current_version"],
        "agent_version": _text(n.get("agent_version"), 64),
        "booted_slot": v["rauc"]["booted_slot"],
        "kernel": _text(n.get("kernel")),
        "cpu_model": _text(n.get("cpu_model")),
        "cpus": _count(n.get("cpus"), 4096),
        "mem_total_mb": _count(n.get("mem_total_mb"), 1 << 31),
        "mem_available_mb": _count(n.get("mem_available_mb"), 1 << 31),
        "disk_total_gb": _gb(n.get("disk_total_gb")),
        "disk_free_gb": _gb(n.get("disk_free_gb")),
        "uptime_s": _count(n.get("uptime_s"), 10 * 365 * 86400),
    }


def about(gw) -> dict:
    """GET /v1/os/about: this hub's own box first, then the other nodes, and the node count."""
    hub_id = gw.settings.node_id
    # Any LAN device can invent node ids (H-06), so when there are more than we show, the hub comes first,
    # then online nodes, then the most recently heard from: spoofed ids cannot push real nodes out.
    nodes = [about_node(n) for n in gw.registry.list()]
    nodes.sort(key=lambda x: x["last_seen"] or "", reverse=True)  # newest first (RFC 3339 sorts as text)
    nodes.sort(key=lambda x: (x["node_id"] != hub_id, x["status"] != "online"))  # stable: keeps newest first
    return {"hub_node_id": hub_id, "node_count": len(nodes), "nodes": nodes[:MAX_ABOUT_NODES]}
