"""Node registry: the hub's view of every machine, fed by heartbeats on NATS (contract section 2).

Each `onemindd` publishes its status to onemind.node.<node_id>.status every 10 s. We keep the
latest heartbeat per node, plus `last_seen` = when *the gateway* received it (the gateway's clock,
not the node's, so a node with a wrong clock cannot look fresher than it is).

status:  online  if last_seen <= 30 s ago
         stale   if 30 s < age <= 120 s
         offline if age > 120 s, or at once after a departure

presence (#608) is the fast projection live screens show: online while heartbeats keep coming,
offline once one is clearly missed (age > PRESENCE_LOST_S) or at once after a departure. It
exists beside `status` because placement and alerts must not flap on one late heartbeat.

A departure (onemind.node.departure/v1) is what onemindd publishes once, on its own status
subject, when it stops cleanly (internal/agent). It is trusted as far as a heartbeat is: on a
strict hub only that node's NATS account can publish on that subject (natsconf.py, H-06). It is
honoured only for a node the registry already knows, and the next heartbeat undoes it.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import datetime

from pydantic import ValidationError

from .apimodels import NodeCapabilities
from .ledger import iso

log = logging.getLogger("onemind.nodes")

HEARTBEAT_SCHEMA = "onemind.node.status/v1"
SUBJECT_RE = re.compile(r"^onemind\.node\.([A-Za-z0-9_-]{1,64})\.status$")
MAX_HEARTBEAT_BYTES = 64 * 1024
STALE_AFTER_S = 30
OFFLINE_AFTER_S = 120
# Heartbeats come every 10 s. An unplugged node must read offline within 15 s of the plug coming
# out (#608): the last heartbeat is at most 10 s older than that, the event stream wakes at the
# 14 s mark itself (next_change_in), so 14 s after the last heartbeat is the latest that still holds, and it still allows a
# heartbeat to run 4 s late without a healthy node blinking offline.
PRESENCE_LOST_S = 14
DEPARTURE_SCHEMA = "onemind.node.departure/v1"
DEPARTURE_KEYS = {"schema", "node_id", "reason"}
DEPARTURE_REASONS = {"shutdown"}
MAX_NODES = 256  # a household fabric is a handful of machines; more ids than this are noise or an attack
# Fields the contract forbids in heartbeats; dropped defensively if a node sends them.
FORBIDDEN_KEYS = {"serial", "serial_number", "mac", "mac_address", "macs", "ip", "ips", "ip_address", "user", "users", "username"}


def valid_capabilities(caps: object, subject: str) -> bool:
    """The hardware profile (#618) is served only if it is exactly a NodeCapabilities document.

    NATS has no users yet (H-06), so any LAN publisher can send a heartbeat; VM device grants and
    app verdicts read accelerators and device paths from this profile, so a profile with an extra
    field, a wrong type or a device outside /dev/(hailo|accel/accel|video)N is not trusted at all.
    """
    try:
        NodeCapabilities.model_validate(caps)
    except ValidationError as e:
        log.warning("dropping invalid hardware profile on %s: %d error(s)", subject, e.error_count())
        return False
    return True


def presence(age_s: float) -> str:
    return "online" if age_s <= PRESENCE_LOST_S else "offline"


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
        self._departed: dict[str, datetime] = {}  # node id -> when its departure arrived
        # Called with each accepted heartbeat, outside the lock (osupdate.py records commits and
        # rollbacks). A failing listener is logged and never drops the heartbeat.
        self.listeners: list[Callable[[dict], None]] = []
        # Called, with no arguments, after every accepted heartbeat and departure: the event stream
        # wakes on it (#608), so it never has to poll the registry on a timer.
        self.change_listeners: list[Callable[[], None]] = []

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
        if isinstance(hb, dict) and hb.get("schema") == DEPARTURE_SCHEMA:
            return self._depart(subject, m.group(1), hb)
        if not isinstance(hb, dict) or hb.get("schema") != HEARTBEAT_SCHEMA:
            log.warning("dropping heartbeat with wrong schema on %s", subject)
            return False
        if hb.get("node_id") != m.group(1):
            log.warning("dropping heartbeat: node_id does not match subject %s", subject)
            return False
        for k in FORBIDDEN_KEYS & hb.keys():
            hb.pop(k)
        if "capabilities" in hb and not valid_capabilities(hb["capabilities"], subject):
            hb.pop("capabilities")  # the profile is dropped, never the heartbeat
        for k in ("status", "last_seen", "presence", "departed_at"):
            hb.pop(k, None)  # the gateway's to say, never the node's
        now = self.clock()
        with self._lock:
            if hb["node_id"] not in self._nodes and len(self._nodes) >= MAX_NODES:
                # NATS has no users yet (H-06), so any LAN device can invent node ids. Never let that
                # grow the registry (64 KiB each) without bound: make room by dropping the node
                # unheard of for longest, but only if it is already offline; else refuse the newcomer.
                oldest = min(self._nodes, key=lambda n: self._nodes[n][1])
                if (now - self._nodes[oldest][1]).total_seconds() <= OFFLINE_AFTER_S:
                    log.warning("node registry full (%d); dropping heartbeat from a new node id", MAX_NODES)
                    return False
                del self._nodes[oldest]
                self._departed.pop(oldest, None)
            self._nodes[hb["node_id"]] = (hb, now)
            self._departed.pop(hb["node_id"], None)  # it is back
        for listen in list(self.listeners):
            try:
                listen(hb)
            except Exception:  # noqa: BLE001 - a feature's bookkeeping never costs a heartbeat
                log.exception("heartbeat listener failed")
        self._changed()
        return True

    def _changed(self) -> None:
        for listen in list(self.change_listeners):
            try:
                listen()
            except Exception:  # noqa: BLE001 - a waking stream never costs a heartbeat
                log.exception("node change listener failed")

    def next_change_in(self) -> float | None:
        """Seconds until the soonest time a node's status or presence changes by itself (age alone),
        or None when none will. A departed node is already offline in both. The event stream sleeps
        for this long, so a missed heartbeat shows at once without polling."""
        now = self.clock()
        soonest: float | None = None
        with self._lock:
            seen = [s for n, (_, s) in self._nodes.items() if n not in self._departed]
        for s in seen:
            age = (now - s).total_seconds()
            left = [t - age for t in (PRESENCE_LOST_S, STALE_AFTER_S, OFFLINE_AFTER_S) if t >= age]
            if left and (soonest is None or min(left) < soonest):
                soonest = min(left)
        return soonest

    def _depart(self, subject: str, node_id: str, msg: dict) -> bool:
        """Accept one departure: exactly the three fields, for a node already known, else dropped."""
        if (msg.keys() != DEPARTURE_KEYS or msg.get("node_id") != node_id
                or msg.get("reason") not in DEPARTURE_REASONS):
            log.warning("dropping malformed departure on %s", subject)
            return False
        now = self.clock()
        with self._lock:
            if node_id not in self._nodes:
                return False  # never heard of it: nothing to take offline, and no new entry
            self._departed.setdefault(node_id, now)
        log.info("node %s departed (clean shutdown)", node_id)
        self._changed()
        return True

    def _view(self, hb: dict, seen: datetime, departed: datetime | None, now: datetime) -> dict:
        age = (now - seen).total_seconds()
        if departed is not None:
            return {**hb, "status": "offline", "presence": "offline", "departed_at": iso(departed), "last_seen": iso(seen)}
        return {**hb, "status": node_status(age), "presence": presence(age), "departed_at": None, "last_seen": iso(seen)}

    def list(self) -> list[dict]:
        now = self.clock()
        with self._lock:
            items = [(hb, seen, self._departed.get(n)) for n, (hb, seen) in self._nodes.items()]
        return sorted((self._view(hb, seen, dep, now) for hb, seen, dep in items), key=lambda n: n["node_id"])

    def get(self, node_id: str) -> dict | None:
        with self._lock:
            item = self._nodes.get(node_id)
            dep = self._departed.get(node_id)
        return None if item is None else self._view(item[0], item[1], dep, self.clock())
