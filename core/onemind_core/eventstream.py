# SPDX-License-Identifier: Apache-2.0
"""GET /v1/events: the live stream of contract §12.8 (Server-Sent Events), DEV-API-8 and #606.

Where events come from (fanout.py has the one reader per source; each stream has its own queue):
- the audit log. Every state change the gateway makes is an audit record; the stream turns records
  into `onemind.event/v1` envelopes. The event id is the audit `seq`: monotonic, durable, and the
  resume point (`Last-Event-ID` or `?since_id=`). A replay reads the file; live records come from the
  one AuditPump, woken by each append, so an idle stream reads nothing;
- asset values (#606): `asset.value` and `asset.removed` from the hub's asset-state bucket, opt-in
  with `types=asset.*`. On connect the stream first sends the current value of every asset the caller
  may see (`data.snapshot: true`), then `stream.snapshot` {count, state}, then changes, latest-wins per
  key. `?kind=` (asset classes) and `?bbox=` (min_lon,min_lat,max_lon,max_lat) narrow them for a map.
  They carry no SSE id: a reconnect gets a fresh snapshot instead of a replay;
- the node registry (in memory), looked at when it can have changed: the registry wakes the stream on
  every heartbeat and departure, and the stream sleeps until the next time a node ages into a new
  status (never on a fixed timer). A `node.status` event when a
  node's `status` or `presence` changes (#608: a clean shutdown reaches the stream within one
  poll, an unplugged node within 15 s). These are not durable and carry no SSE `id:`, so they
  never move the resume point;
- the sync index (#698), polled the same way: `sync.root_changed` {root, revision} when a root
  the caller may read has a new revision. It is a wake-up, not the log: at most one per root per
  poll, no id, and the caller reads what changed from GET /v1/sync/changes.

Facts always go before values. A stream that falls FACT_QUEUE_MAX facts (or VALUE_KEYS_MAX asset keys)
behind gets `stream.reset` {reason: slow_client} and ends; it reconnects with Last-Event-ID.
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
from .fanout import AssetState, AssetValue, AssetView, AuditPump, Subscriber
from .identity.scopes import has_any, role_scopes


SCHEMA = "onemind.event/v1"
REPLAY_MAX = 10_000
KEEPALIVE_S = 15.0
POLL_S = 2.0          # longest an idle stream sleeps (new facts and values wake it at once)
NODE_SLACK_S = 0.05   # past a node's next age boundary, so the check sees it crossed
ROOT_POLL_S = 2.0     # the sync index is a database read
DRAIN_MAX = 256       # items sent between two checks of the connection and the nodes
MAX_STREAMS_PER_PRINCIPAL = 5
# Person roles whose §12.6 defaults include nodes:read (agents have it in every grant bundle).
NODE_READERS = {"owner", "adult", "guest"}
ASSET_SCOPE = "assets:read"

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


def node_states(nodes: list[dict]) -> dict[str, tuple[str | None, str | None]]:
    """node id -> (status, presence), what a `node.status` event reports a change of."""
    return {n["node_id"]: (n.get("status"), n.get("presence")) for n in nodes}


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
    # Only explicit producer facts are mapped: never forward arbitrary audit payloads.
    data = rec.get("data") or {}
    payload = data.get("payload", data)
    mapped = None
    if event == "action.progress" and action_id and payload.get("app_id"):
        mapped = (event, {"action_id": action_id, "app_id": payload["app_id"]},
                  {k: payload[k] for k in ("step", "pct") if k in payload})
    if event in {"alert.opened", "alert.updated", "alert.acknowledged", "alert.resolved"}:
        if payload.get("alert_id"):
            mapped = ("alert.updated" if event == "alert.acknowledged" else event,
                      {"alert_id": payload["alert_id"]}, {"state": payload.get("state")})
    elif event == "notification.created" and payload.get("notification_id"):
        mapped = (event, {"notification_id": payload["notification_id"]}, {})
    elif event in {"app.status", "app.restarted", "app.healthy", "app.unhealthy"} and payload.get("app_id"):
        subject = {"app_id": payload["app_id"]}
        if action_id:
            subject["action_id"] = action_id
        if event in {"app.healthy", "app.unhealthy"}:
            mapped = ("app.health", subject, {"state": event.split(".")[1]})
        elif event == "app.status":
            mapped = (event, subject, {k: payload[k] for k in ("status", "data_kept") if k in payload})
        else:
            mapped = (event, subject, {})
    if mapped:
        ev = _envelope(seq, mapped[0], ts, mapped[1], mapped[2], actor)
        ev["severity"] = data.get("severity", "info")
        out.append(ev)
    out.append(_envelope(seq, "audit.appended", ts, {"seq": rec["seq"]}, {"event": event}, actor))
    return out


def sse(event: dict, with_id: bool = True) -> bytes:
    head = f"id: {event['id']}\n" if with_id else ""
    data = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
    return f"{head}event: {event['type']}\ndata: {data}\n\n".encode()


def asset_event(v: AssetValue, ts: str, *, snapshot: bool = False, removed: bool = False) -> dict:
    """`asset.value` {revision, snapshot, datapoint} or `asset.removed` {revision} for one asset key.

    The envelope id is `asset:<revision>`: the KV revision is the bucket's stream sequence, unique
    across every key, so the id never outgrows onemind.event/v1's 128 characters (a key alone can be
    64 + 128 + 64 characters long). The asset is named by `subject`, not by the id."""
    subject = {"asset_id": v.asset_id, "asset_class": v.asset_class, "field": v.field}
    if removed:
        return _envelope(f"asset:{v.revision}", "asset.removed", ts, subject, {"revision": v.revision})
    return _envelope(f"asset:{v.revision}", "asset.value", ts, subject,
                     {"revision": v.revision, "snapshot": snapshot, "datapoint": v.datapoint})


def may_read_assets(p: Principal, scopes: frozenset[str] | set[str] | None) -> bool:
    """assets:read: an identity credential's own scopes; otherwise the person's role defaults, or an
    agent token that lists it. Plugins, nodes, automations, guests and children have no grant."""
    if scopes is not None:
        return has_any(scopes, (ASSET_SCOPE,))
    if p.kind == "person":
        return has_any(role_scopes(p.role), (ASSET_SCOPE,))
    return p.kind == "agent" and p.scopes is not None and ASSET_SCOPE in p.scopes


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
        root_revisions: Callable[[Principal], dict[str, int]] | None = None,
        assets: AssetState | None = None,
        next_node_change: Callable[[], float | None] | None = None,
    ):
        self.audit_path = audit_path
        self.list_nodes = list_nodes
        self.owned_action_ids = owned_action_ids
        self.clock = clock
        # The roots this principal may read as a whole -> their revision (files sync index).
        self.root_revisions = root_revisions
        self.pump = AuditPump(audit_path)
        self.assets = assets
        # Seconds until a node next changes by age alone (NodeRegistry.next_change_in), or None.
        self.next_node_change = next_node_change
        if assets is not None:
            assets.listeners.append(self._on_asset)

    def _on_asset(self, op: str, v: AssetValue) -> None:
        for sub in self.pump.subscribers():
            if sub.wants(v):
                sub.push_value(op, v)

    def wake_nodes(self) -> None:
        """A heartbeat or departure was accepted: every open stream looks at the nodes now. Any thread."""
        for sub in self.pump.subscribers():
            sub._wake()

    def _allowed(self, p: Principal, resource_allowed: Callable[[dict], bool] | None = None) -> Callable[[dict], bool]:
        """Per-principal filter (§12.8): audit.* needs audit:read; agents see their own actions;
        node.status needs nodes:read (§12.6 role defaults: not a child, nor an unknown role)."""
        full = can_read_all(p)
        nodes = p.kind == "agent" or (p.kind == "person" and p.role in NODE_READERS)
        # An agent's own action ids, looked up once and again only when an unknown id shows up
        # (its own new request). A lookup reads the whole ledger, so never once per event.
        own: set[str] | None = None
        foreign: set[str] = set()

        def owns(action_id: str | None) -> bool:
            nonlocal own
            if not action_id or action_id in foreign:
                return False
            if own is None or action_id not in own:
                own = self.owned_action_ids(p.id)
            if action_id in own:
                return True
            foreign.add(action_id)  # ownership is fixed at creation, before the audit line
            return False

        def ok(ev: dict) -> bool:
            t = ev["type"]
            action_id = ev.get("subject", {}).get("action_id")
            # App visibility does not grant visibility of the action that caused its state.
            # Apply the same owner/requester boundary to every envelope carrying action ids,
            # before domain dispatch or generic audit fallback selection.
            if action_id and not (full or p.is_owner or (p.kind == "agent" and owns(action_id))):
                return False
            if resource_allowed is not None and not resource_allowed(ev):
                return False
            if t.startswith(("alert.", "notification.", "app.", "asset.")):
                return resource_allowed is not None
            if t.startswith("audit."):
                return full
            if t.startswith("action."):
                if full or (p.kind == "person" and p.role == "owner"):
                    return True
                if p.kind == "agent":
                    return owns(ev["subject"].get("action_id"))
                return False
            if t == "node.status":
                return nodes
            if t == "sync.root_changed":  # root_revisions already lists only roots this caller may read
                return True
            return t in ("stream.reset", "stream.snapshot")

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
        resource_allowed: Callable[[dict], bool] | None = None,
        kinds: frozenset[str] | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        asset_allowed: Callable[[AssetValue], bool] | None = None,
    ) -> AsyncIterator[bytes]:
        """resource_allowed judges each envelope (scopes, audiences); asset_allowed also judges each
        asset value itself (class, id, field and datapoint: the gateway asset filters), before the
        snapshot and every change. Without resource_allowed no asset event is sent at all."""
        allowed = self._allowed(p, resource_allowed)

        def wanted(ev: dict) -> bool:
            return glob_any(types, ev["type"]) and allowed(ev)

        def selected(rec: dict) -> dict | None:
            candidates = events_for_record(rec)
            domain = candidates[:-1]
            # Generic audit envelopes must not reveal even the existence of a hidden resource.
            if domain and not all(allowed(ev) for ev in domain):
                return None
            return next((ev for ev in candidates if wanted(ev)), None)

        # Asset values are many and carry values: only a stream that names them gets them.
        assets_on = self.assets is not None and bool(types) and glob_any(types, "asset.value")
        view = AssetView(kinds, bbox, self.assets.position if self.assets is not None else lambda c, i: None)

        def asset_out(v: AssetValue, *, snapshot: bool = False, removed: bool = False) -> bytes | None:
            if not view.passes(v, removed):
                return None
            if asset_allowed is not None and not asset_allowed(v):
                return None
            ev = asset_event(v, self._now(), snapshot=snapshot, removed=removed)
            return sse(ev, with_id=False) if wanted(ev) else None

        loop = asyncio.get_running_loop()
        sub = Subscriber(loop, assets=assets_on, kinds=kinds)
        # Attach before reading the head, so nothing written in between is missed (seq dedupes).
        self.pump.attach(sub)
        try:
            # Replay or start at the head, read right after attaching.
            head = 0
            records = list(iter_records(self.audit_path))
            if records:
                head = records[-1][1]["seq"]
            yield b"retry: 3000\n\n"
            if since_id is not None:
                oldest_kept = max(1, head - REPLAY_MAX + 1)
                if since_id + 1 < oldest_kept or since_id > head:
                    reset = _envelope(str(head), "stream.reset", self._now(), {}, {"reason": "replay_unavailable"})
                    yield sse(reset, with_id=False)
                else:
                    for _, rec in records:
                        if rec["seq"] > since_id:
                            ev = selected(rec)
                            if ev is not None:
                                yield sse(ev)
            del records
            last_seq = head
            if assets_on:
                count = 0
                for v in self.assets.snapshot():
                    chunk = asset_out(v, snapshot=True)
                    if chunk is not None:
                        count += 1
                        yield chunk
                # A control event, like stream.reset: sent whatever `types` says.
                done = _envelope(str(head), "stream.snapshot", self._now(), {},
                                 {"count": count, "state": self.assets.state})
                yield sse(done, with_id=False)
            nodes = node_states(self.list_nodes())
            roots = self._roots(p)
            last_out = last_roots = loop.time()
            while True:
                if await is_disconnected():
                    return
                sent = False
                for _ in range(DRAIN_MAX):
                    if sub.reset:
                        reset = _envelope(str(last_seq), "stream.reset", self._now(), {}, {"reason": sub.reset})
                        yield sse(reset, with_id=False)
                        return
                    item = sub.next()
                    if item is None:
                        break
                    op, obj = item
                    if op == "fact":
                        if obj["seq"] <= last_seq:
                            continue  # already replayed, or written before this stream started
                        last_seq = obj["seq"]
                        ev = selected(obj)
                        chunk = sse(ev) if ev is not None else None
                    else:
                        chunk = asset_out(obj, removed=op == "removed")
                    if chunk is not None:
                        yield chunk
                        sent = True
                self.pump.poll()
                now = loop.time()
                # nodes are in memory and cheap: looked at on every wake-up (a heartbeat, a departure,
                # a node ageing into a new status, or a fact)
                current = node_states(self.list_nodes())
                for node_id, (status, presence) in sorted(current.items()):
                    previous = nodes.get(node_id)
                    if previous != (status, presence):
                        ev = _envelope(f"node:{node_id}:{status}:{presence}", "node.status", self._now(),
                                       {"node_id": node_id},
                                       {"status": status, "presence": presence,
                                        "previous": previous and previous[0]})
                        if wanted(ev):
                            yield sse(ev, with_id=False)
                            sent = True
                nodes = current
                if now - last_roots >= ROOT_POLL_S - NODE_SLACK_S:
                    last_roots = now
                    current_roots = self._roots(p)
                    for root, revision in sorted(current_roots.items()):
                        if root in roots and revision > roots[root]:
                            ev = _envelope(f"sync:{root}:{revision}", "sync.root_changed", self._now(),
                                           {"root": root}, {"revision": revision})
                            if wanted(ev):
                                yield sse(ev, with_id=False)
                                sent = True
                    roots = current_roots
                if sent:
                    last_out = now
                elif now - last_out >= keepalive_s:
                    yield b": keepalive\n\n"
                    last_out = now
                if sub.waiting():
                    continue  # more than DRAIN_MAX was waiting: go on without sleeping
                wait = min(poll_s, max(0.01, keepalive_s - (loop.time() - last_out)))
                if self.next_node_change is not None:
                    ahead = self.next_node_change()
                    if ahead is not None:
                        wait = min(wait, max(0.01, ahead + NODE_SLACK_S))
                await sub.wait(wait)
        finally:
            self.pump.detach(sub)

    def _roots(self, p: Principal) -> dict[str, int]:
        if self.root_revisions is None:
            return {}
        try:
            return self.root_revisions(p)
        except Exception:  # the files storage or index is not ready: no wake-ups, the stream goes on
            return {}

    def _now(self) -> str:
        return self.clock().isoformat().replace("+00:00", "Z")
