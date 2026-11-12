# SPDX-License-Identifier: Apache-2.0
"""GET /v1/events: the live stream of contract §12.8 (Server-Sent Events), DEV-API-8.

Where events come from:
- the audit log. Every state change the gateway makes is an audit record, so the stream follows
  the file and turns records into `onemind.event/v1` envelopes. The event id is the audit `seq`:
  monotonic, durable, and the resume point (`Last-Event-ID` or `?since_id=`);
- the node registry, polled every few seconds: a `node.status` event when a node's status
  changes. These are not durable and carry no SSE `id:`, so they never move the resume point.

Events carry ids and states only; a client reads the full object over REST (SDK.md §3.9).
Replay reaches back REPLAY_MAX records; an older resume point gets `stream.reset` first.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from pathlib import Path

from .auditread import can_read_all, glob_any, iter_records
from .auth import Principal

SCHEMA = "onemind.event/v1"
REPLAY_MAX = 10_000
KEEPALIVE_S = 15.0
POLL_S = 0.5
NODE_POLL_S = 2.0
MAX_STREAMS_PER_PRINCIPAL = 5

# audit event -> the action state it moves to (§3 states).
ACTION_STATES = {
    "action.awaiting_approval": "awaiting_approval",
    "action.approved": "accepted",
    "action.denied": "cancelled",
    "action.dispatched": "dispatched",
    "action.succeeded": "succeeded",
    "action.failed": "failed",
    "action.expired": "expired",
    "action.outcome_unknown": "outcome_unknown",
}


def _envelope(id_: str, type_: str, ts: str, subject: dict, data: dict, actor: str | None = None) -> dict:
    env = {"schema": SCHEMA, "id": id_, "type": type_, "ts": ts, "subject": subject, "severity": "info", "data": data}
    if actor:
        env["actor_id"] = actor
    return env


def events_for_record(rec: dict) -> list[dict]:
    """The §12.8 events one audit record produces (always `audit.appended`, plus action events)."""
    seq, event, ts = str(rec["seq"]), rec.get("event", ""), rec.get("ts", "")
    actor = (rec.get("principal") or {}).get("id")
    action_id = rec.get("action_id")
    out = []
    if event == "action.requested" and action_id:
        out.append(_envelope(seq, "action.requested", ts, {"action_id": action_id},
                             {"state": "requested"}, actor))
    elif event in ACTION_STATES and action_id:
        out.append(_envelope(seq, "action.state_changed", ts, {"action_id": action_id},
                             {"to": ACTION_STATES[event], "audit_event": event}, actor))
    out.append(_envelope(seq, "audit.appended", ts, {"seq": rec["seq"]}, {"event": event}, actor))
    return out


def sse(event: dict, with_id: bool = True) -> bytes:
    head = f"id: {event['id']}\n" if with_id else ""
    data = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    return f"{head}event: {event['type']}\ndata: {data}\n\n".encode()


class StreamSlots:
    """At most MAX_STREAMS_PER_PRINCIPAL open streams per principal (§12.1 limits)."""

    def __init__(self, limit: int = MAX_STREAMS_PER_PRINCIPAL):
        self.limit = limit
        self._open: dict[str, int] = {}
        self._lock = threading.Lock()

    def take(self, key: str) -> bool:
        with self._lock:
            if self._open.get(key, 0) >= self.limit:
                return False
            self._open[key] = self._open.get(key, 0) + 1
            return True

    def give(self, key: str) -> None:
        with self._lock:
            self._open[key] = max(0, self._open.get(key, 0) - 1)


class EventStream:
    def __init__(
        self,
        audit_path: Path,
        list_nodes: Callable[[], list[dict]],
        owned_action_ids: Callable[[str], set[str]],
        clock: Callable[[], datetime],
    ):
        self.audit_path = audit_path
        self.list_nodes = list_nodes
        self.owned_action_ids = owned_action_ids
        self.clock = clock

    def _allowed(self, p: Principal) -> Callable[[dict], bool]:
        """Per-principal filter (§12.8): audit.* needs audit:read; agents see their own actions."""
        full = can_read_all(p)

        def ok(ev: dict) -> bool:
            t = ev["type"]
            if t.startswith("audit."):
                return full
            if t.startswith("action."):
                if full or (p.kind == "person" and p.role == "owner"):
                    return True
                if p.kind == "agent":
                    return ev["subject"].get("action_id") in self.owned_action_ids(p.id)
                return False
            return True  # node.status, stream.reset

        return ok

    async def stream(
        self,
        p: Principal,
        types: str | None,
        since_id: int | None,
        is_disconnected: Callable[[], object],
        *,
        poll_s: float = POLL_S,
        keepalive_s: float = KEEPALIVE_S,
    ) -> AsyncIterator[bytes]:
        allowed = self._allowed(p)

        def wanted(ev: dict) -> bool:
            return glob_any(types, ev["type"]) and allowed(ev)

        yield b"retry: 3000\n\n"
        # Replay or start at the head.
        offset, head = 0, 0
        records = list(iter_records(self.audit_path))
        if records:
            offset, head = records[-1][0], records[-1][1]["seq"]
        if since_id is not None:
            oldest_kept = max(1, head - REPLAY_MAX + 1)
            if since_id + 1 < oldest_kept or since_id > head:
                reset = _envelope(str(head), "stream.reset", self._now(), {}, {"reason": "replay_unavailable"})
                yield sse(reset, with_id=False)
            else:
                for _, rec in records:
                    if rec["seq"] > since_id:
                        for ev in events_for_record(rec):
                            if wanted(ev):
                                yield sse(ev)
        del records
        nodes = {n["node_id"]: n.get("status") for n in self.list_nodes()}
        loop = asyncio.get_running_loop()
        last_out = last_nodes = loop.time()
        while True:
            if await is_disconnected():
                return
            sent = False
            for pos, rec in iter_records(self.audit_path, offset):
                offset = pos
                for ev in events_for_record(rec):
                    if wanted(ev):
                        yield sse(ev)
                        sent = True
            now = loop.time()
            if now - last_nodes >= NODE_POLL_S:
                last_nodes = now
                current = {n["node_id"]: n.get("status") for n in self.list_nodes()}
                for node_id, status in sorted(current.items()):
                    if nodes.get(node_id) != status:
                        ev = _envelope(f"node:{node_id}:{status}", "node.status", self._now(),
                                       {"node_id": node_id}, {"status": status, "previous": nodes.get(node_id)})
                        if wanted(ev):
                            yield sse(ev, with_id=False)
                            sent = True
                nodes = current
            if sent:
                last_out = now
            elif now - last_out >= keepalive_s:
                yield b": keepalive\n\n"
                last_out = now
            await asyncio.sleep(poll_s)

    def _now(self) -> str:
        return self.clock().isoformat().replace("+00:00", "Z")
