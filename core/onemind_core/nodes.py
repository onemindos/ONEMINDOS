"""Node registry: the hub's view of every machine, fed by heartbeats on NATS (contract section 2).

Each `onemindd` publishes its status to onemind.node.<node_id>.status every 10 s. We keep the
latest heartbeat per node, plus `last_seen` = when *the gateway* received it (the gateway's clock,
not the node's, so a node with a wrong clock cannot look fresher than it is).

status:  online  if last_seen <= 30 s ago
         stale   if 30 s < age <= 120 s
         offline if age > 120 s
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import datetime

from .ledger import iso

log = logging.getLogger("onemind.nodes")

HEARTBEAT_SCHEMA = "onemind.node.status/v1"
SUBJECT_RE = re.compile(r"^onemind\.node\.([A-Za-z0-9_-]{1,64})\.status$")
MAX_HEARTBEAT_BYTES = 64 * 1024
STALE_AFTER_S = 30
OFFLINE_AFTER_S = 120
# Fields the contract forbids in heartbeats; dropped defensively if a node sends them.
FORBIDDEN_KEYS = {"serial", "serial_number", "mac", "mac_address", "macs", "ip", "ips", "ip_address", "user", "users", "username"}


def node_status(age_s: float) -> str:
    if age_s <= STALE_AFTER_S:
        return "online"
    if age_s <= OFFLINE_AFTER_S:
        return "stale"
    return "offline"


class NodeRegistry:
    def __init__(self, clock: Callable[[], datetime]):
        self.clock = clock
        self._lock = threading.Lock()
        self._nodes: dict[str, tuple[dict, datetime]] = {}

    def ingest(self, subject: str, data: bytes) -> bool:
        """Accept one heartbeat. Returns False (and drops it) if it is malformed."""
        m = SUBJECT_RE.match(subject)
        if not m:
            return False
        if len(data) > MAX_HEARTBEAT_BYTES:
            log.warning("dropping oversized heartbeat on %s", subject)
            return False
        try:
            hb = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("dropping non-JSON heartbeat on %s", subject)
            return False
        if not isinstance(hb, dict) or hb.get("schema") != HEARTBEAT_SCHEMA:
            log.warning("dropping heartbeat with wrong schema on %s", subject)
            return False
        if hb.get("node_id") != m.group(1):
            log.warning("dropping heartbeat: node_id does not match subject %s", subject)
            return False
        for k in FORBIDDEN_KEYS & hb.keys():
            hb.pop(k)
        hb.pop("status", None)
        hb.pop("last_seen", None)
        with self._lock:
            self._nodes[hb["node_id"]] = (hb, self.clock())
        return True

    def _view(self, hb: dict, seen: datetime, now: datetime) -> dict:
        age = (now - seen).total_seconds()
        return {**hb, "status": node_status(age), "last_seen": iso(seen)}

    def list(self) -> list[dict]:
        now = self.clock()
        with self._lock:
            items = list(self._nodes.values())
        return sorted((self._view(hb, seen, now) for hb, seen in items), key=lambda n: n["node_id"])

    def get(self, node_id: str) -> dict | None:
        with self._lock:
            item = self._nodes.get(node_id)
        return None if item is None else self._view(item[0], item[1], self.clock())
