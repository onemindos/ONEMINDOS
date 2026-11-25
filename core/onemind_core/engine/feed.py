# SPDX-License-Identifier: Apache-2.0
"""GET /v1/engine: the bus as the hub's NATS sees it, cut to the caller's scope (issue #619).

Who sees what:

- the owner: every account's connections, every node's leaf link and outbox lag, JetStream used
  against its cap, slow consumers and the server facts (scope `all`);
- a node (principal node:<node_id>): its own account, its own link and outbox, JetStream totals
  (scope `node`);
- every other caller allowed on the route (adults, guests, agents): the health, JetStream totals
  and how many links are up or down, nothing per account or per node (scope `summary`).

Terms. An *account* is a NATS name space: ONEMIND for the hub's own clients, NODE_<node_id> for one
joined machine (natsconf.py). A *leaf link* is the connection a machine's own nats-server keeps to
the hub. A machine writes its events to a local *outbox* first; the hub copies them into
NODE_node_<node_id>_OUTBOX (internal/leaf HubSourceStream), and the *lag* is how many messages the
hub still has to copy, which is how far behind a machine is after its link comes back.

JetStream is never shown as healthy without a cap: a server whose JetStream has no memory limit of 0
or no file-store limit is running on nats-server's dynamic defaults (75 % of RAM, all free disk), and
the feed reports state `refused` (jetstream.py rule 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from ..natsconf import HUB_ACCOUNT, NODE_ID_RE
from ..ledger import iso
from .monitor import Snapshot

OUTBOX_RE = re.compile(r"^NODE_node_([a-z0-9]{1,32})_OUTBOX$")
LEAF_NAME_RE = re.compile(r"^node-([a-z0-9]{1,32})$")
ACCOUNT_NODE_RE = re.compile(r"^NODE_([a-z0-9]{1,32})$")


# ---- the answer ----------------------------------------------------------------------------------
class EngineMonitor(BaseModel):
    state: str = Field(description="up: the loopback monitor answered; down: it did not")
    checked_at: str
    errors: dict[str, str] = Field(default_factory=dict, description="Endpoint -> what failed (owner only)")


class EngineHealth(BaseModel):
    status: str = Field(description="ok, unavailable (NATS says it is not healthy) or unknown (no answer)")
    error: str | None = None


class EngineServer(BaseModel):
    version: str | None = None
    uptime: str | None = None
    connections: int | None = None
    total_connections: int | None = None
    leafnodes: int | None = None
    in_msgs: int | None = None
    out_msgs: int | None = None


class EngineAccount(BaseModel):
    account: str
    node_id: str | None = Field(None, description="The machine this account belongs to; null for the hub's own")
    connections: int
    leafnodes: int
    jetstream_bytes: int | None = None


class EngineOutbox(BaseModel):
    stream: str
    messages: int | None = None
    bytes: int | None = None
    lag: int | None = Field(None, description="Messages the hub has still to copy from the machine's outbox")
    last_active_s: float | None = Field(None, description="Seconds since the hub last heard from the outbox")
    error: str | None = None


class EngineNode(BaseModel):
    node_id: str
    link: str = Field(description="up: the machine's leaf link is connected; down: it is not; unknown: no leaf data")
    rtt: str | None = None
    heartbeat: str | None = Field(None, description="online, stale or offline from the heartbeat registry")
    outbox: EngineOutbox | None = None


class EngineLinks(BaseModel):
    up: int
    down: int


class EngineJetStream(BaseModel):
    state: str = Field(description="off, refused, pending, ready or error (the gateway's core streams, #601), "
                                   "or refused when NATS runs JetStream without a cap")
    reason: str = ""
    enabled: bool | None = Field(None, description="What NATS says; null when the monitor did not answer")
    used_bytes: int | None = None
    cap_bytes: int | None = Field(None, description="The file-store cap NATS enforces")
    planned_cap_bytes: int | None = Field(None, description="The cap the gateway planned from the data disk")
    used_pct: float | None = None
    reserved_bytes: int | None = None
    streams: int | None = None
    consumers: int | None = None


class EngineSlowConsumers(BaseModel):
    total: int | None = None
    clients: int | None = None
    routes: int | None = None
    gateways: int | None = None
    leafs: int | None = None


class EngineView(BaseModel):
    """GET /v1/engine. Never carries a credential, a client address, a user name, a path or a subject."""

    at: str
    scope: str = Field(description="all (owner), node (a machine: its own account and link) or summary")
    monitor: EngineMonitor
    health: EngineHealth
    links: EngineLinks
    jetstream: EngineJetStream
    server: EngineServer | None = None
    accounts: list[EngineAccount] = Field(default_factory=list)
    nodes: list[EngineNode] = Field(default_factory=list)
    slow_consumers: EngineSlowConsumers | None = None
    connections_truncated: bool = False


# ---- scope ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Scope:
    kind: str                  # all | node | summary
    node_id: str | None = None


def scope_for(principal) -> Scope | None:
    """The caller's scope, or None when it may not read the feed at all (plugins, automations, children)."""
    if principal.is_owner:
        return Scope("all")
    if principal.kind == "node":
        nid = principal.id.removeprefix("node:")
        return Scope("node", nid) if NODE_ID_RE.match(nid) else None
    if principal.kind in ("plugin", "automation"):
        return None
    if principal.kind == "person" and principal.role in ("child", "teen"):
        return None
    return Scope("summary")


# ---- building the answer -------------------------------------------------------------------------
def _node_of_leaf(leaf: dict) -> str | None:
    m = ACCOUNT_NODE_RE.match(leaf.get("account") or "") or LEAF_NAME_RE.match(leaf.get("name") or "")
    return m.group(1) if m else None


def _jetstream(snap: Snapshot, core: dict | None) -> EngineJetStream:
    core = core or {"state": "off", "reason": "the gateway has no JetStream state", "plan": None}
    planned = (core.get("plan") or {}).get("cap_bytes")
    out = EngineJetStream(state=core.get("state") or "off", reason=core.get("reason") or "", planned_cap_bytes=planned)
    js = snap.jsz
    if js is None:
        return out
    out.enabled = bool(js.get("enabled"))
    if not out.enabled:
        return out
    out.used_bytes, out.cap_bytes = js.get("storage"), js.get("max_storage")
    out.reserved_bytes, out.streams, out.consumers = js.get("reserved_storage"), js.get("streams"), js.get("consumers")
    if out.used_bytes is not None and out.cap_bytes:
        out.used_pct = round(100.0 * out.used_bytes / out.cap_bytes, 1)
    if not out.cap_bytes or out.cap_bytes <= 0 or js.get("max_memory") != 0:
        out.state = "refused"
        out.reason = ("NATS runs JetStream without a cap (it needs max_file_store and max_memory_store: 0); "
                      "the hub refuses that")
    elif planned and out.cap_bytes > planned:
        out.reason = (out.reason + "; " if out.reason else "") + "NATS allows more than the cap the gateway planned"
    return out


def _outbox(name: str, src: dict) -> EngineOutbox:
    active = src.get("active_ns")
    return EngineOutbox(stream=name, messages=src.get("messages"), bytes=src.get("bytes"), lag=src.get("lag"),
                        last_active_s=round(active / 1e9, 1) if isinstance(active, int) and active >= 0 else None,
                        error=src.get("error"))


def view(snap: Snapshot, scope: Scope, *, jetstream: dict | None, nodes: list[dict], hub_node_id: str) -> dict:
    """The Engine feed for one caller. `nodes` is the heartbeat registry; the hub itself has no link."""
    leafz = snap.leafz
    up_by_node: dict[str, dict] = {}
    for lf in leafz or []:
        nid = _node_of_leaf(lf)
        if nid is not None:
            up_by_node.setdefault(nid, lf)
    sourced = (snap.jsz or {}).get("sourced") or {}
    outbox_by_node = {m.group(1): (name, src) for name, src in sourced.items() if (m := OUTBOX_RE.match(name))}
    beats = {n["node_id"]: n.get("status") for n in nodes if isinstance(n.get("node_id"), str)}
    ids = sorted((set(beats) | set(up_by_node) | set(outbox_by_node)) - {hub_node_id})
    rows = []
    for nid in ids:
        lf = up_by_node.get(nid)
        link = "up" if lf is not None else ("unknown" if leafz is None else "down")
        ob = outbox_by_node.get(nid)
        rows.append(EngineNode(node_id=nid, link=link, rtt=(lf or {}).get("rtt"), heartbeat=beats.get(nid),
                               outbox=_outbox(*ob) if ob else None))

    connz = snap.connz or {}
    per_conn: dict[str, int] = dict(connz.get("accounts") or {})
    per_leaf: dict[str, int] = {}
    for lf in leafz or []:
        if lf.get("account"):
            per_leaf[lf["account"]] = per_leaf.get(lf["account"], 0) + 1
    js_bytes = {a["account"]: a.get("storage") for a in (snap.jsz or {}).get("accounts") or [] if a.get("account")}
    names = set(per_conn) | set(per_leaf)
    if snap.connz is not None:
        names.add(HUB_ACCOUNT)   # the hub's own account is listed even with no client in it
    accounts = []
    for acc in sorted(names):
        m = ACCOUNT_NODE_RE.match(acc)
        accounts.append(EngineAccount(account=acc, node_id=m.group(1) if m else None, connections=per_conn.get(acc, 0),
                                      leafnodes=per_leaf.get(acc, 0), jetstream_bytes=js_bytes.get(acc)))

    health = EngineHealth(**snap.healthz) if snap.healthz else EngineHealth(status="unknown")
    varz = snap.varz or {}
    out = EngineView(
        at=iso(snap.at), scope=scope.kind,
        monitor=EngineMonitor(state="up" if snap.reachable else "down", checked_at=iso(snap.at)),
        health=health, links=EngineLinks(up=0, down=0), jetstream=_jetstream(snap, jetstream),
    )
    if scope.kind == "node":
        rows = [r for r in rows if r.node_id == scope.node_id]
        accounts = [a for a in accounts if a.node_id == scope.node_id]
    out.links = EngineLinks(up=sum(r.link == "up" for r in rows), down=sum(r.link == "down" for r in rows))
    if scope.kind == "summary":
        return out.model_dump()
    out.nodes, out.accounts = rows, accounts
    if scope.kind == "all":
        out.monitor.errors = dict(snap.errors)
        out.connections_truncated = bool(connz.get("truncated"))
        if snap.varz is not None:
            out.server = EngineServer(**{k: varz.get(k) for k in EngineServer.model_fields})
            out.slow_consumers = EngineSlowConsumers(total=varz.get("slow_consumers"),
                                                     **(varz.get("slow_consumer_stats") or {}))
    return out.model_dump()
