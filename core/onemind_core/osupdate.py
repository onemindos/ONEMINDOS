# SPDX-License-Identifier: Apache-2.0
"""OS updates seen from the gateway (UMB-P05, #142; PD-19; brief 30 B4.2, REC-DEC-13).

The box side is `internal/update` (#15): it checks the signed channel, installs a RAUC bundle into
the other A/B slot and lets the health gate commit or roll back. Every `onemindd` already reports
that engine's state in its heartbeat (`update`: channel, current and available version, state,
last result) and its A/B slots (`rauc`). This module turns those heartbeats into:

- the status: per node, the running version, the booted slot, the slots, and a pending update;
- the history: every commit and rollback the gateway saw a node report, kept in its own table so it
  survives a gateway restart;
- `os.update.install`: an owner-approved action. Nothing installs at request time.

The gap, said plainly: the gateway has no path to the update engine yet. `internal/update` says
"the `/v1/os/*` gateway API and the local Unix socket API come later", and `onemindd` serves no
update socket. So an approved install finishes `failed` with reason `engine_unreachable` and tells
the owner to run `onemind update apply` at the box. It never pretends to have installed anything.
Heartbeats come from any LAN device (no NATS users yet, H-06), so every field is re-checked here.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Integer, String, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from .actions import FeatureAction
from .auth import Principal
from .errors import ApiError
from .executors import ExecResult
from .ledger import Base, iso
from .nodes import MAX_NODES
from .store import FeatureSchema, SqlRepository

log = logging.getLogger("onemind.osupdate")

SCHEMA = FeatureSchema("osupdate")  # version 1 = the shape below
ACTION = "os.update.install"
STATES = ("idle", "downloading", "installing", "pending_reboot", "trial", "committed", "rolled_back", "error")
BUSY = ("downloading", "installing", "pending_reboot", "trial")  # a new install would race the engine or the gate
VERDICTS = ("committed", "rolled_back")  # what the history keeps
KEEP_PER_NODE = 100  # a LAN device can flip states at will (H-06); the table stays bounded
# A LAN device can also invent node ids (H-06), so the table is capped overall too: never more rows
# than the registry's node limit times the per-node limit (read at call time so tests can shrink it).
ENGINE = {
    "available": False,
    "reason": "engine_unreachable",
    "message": "The gateway cannot reach the box's update engine yet, so an approved install does not run. "
               "Install at the box with `onemind update apply`; it keeps the A/B rollback and the health gate.",
}


def _text(v: object, n: int = 128) -> str | None:
    return v[:n] if isinstance(v, str) and v else None


class InstallParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    version: str = Field(pattern=r"^[0-9A-Za-z.+-]{1,64}$")


class OsUpdateEventRow(Base):
    __tablename__ = "osupdate_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16))  # committed | rolled_back
    version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_result: Mapped[str | None] = mapped_column(String(128), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def to_json(self) -> dict:
        return {"node_id": self.node_id, "state": self.state, "version": self.version,
                "last_result": self.last_result, "observed_at": iso(self.observed_at)}


class OsUpdateRepository(SqlRepository):
    def last(self, node_id: str) -> dict | None:
        with self.db.session() as s:
            r = s.scalars(select(OsUpdateEventRow).where(OsUpdateEventRow.node_id == node_id)
                          .order_by(OsUpdateEventRow.id.desc()).limit(1)).first()
            return r.to_json() if r else None

    def add(self, row: OsUpdateEventRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)
            s.flush()
            old = select(OsUpdateEventRow.id).where(OsUpdateEventRow.node_id == row.node_id) \
                .order_by(OsUpdateEventRow.id.desc()).offset(KEEP_PER_NODE)
            s.execute(delete(OsUpdateEventRow).where(OsUpdateEventRow.id.in_(old.scalar_subquery())))
            cap = select(OsUpdateEventRow.id).order_by(OsUpdateEventRow.id.desc()).offset(KEEP_PER_NODE * MAX_NODES)
            s.execute(delete(OsUpdateEventRow).where(OsUpdateEventRow.id.in_(cap.scalar_subquery())))

    def count(self) -> int:
        with self.db.session() as s:
            return s.scalar(select(func.count()).select_from(OsUpdateEventRow)) or 0

    def list(self, limit: int = 100) -> list[dict]:
        with self.db.session() as s:
            rows = s.scalars(select(OsUpdateEventRow).order_by(OsUpdateEventRow.id.desc()).limit(limit))
            return [r.to_json() for r in rows]


def node_view(n: dict) -> dict:
    """One node's OS facts, from its heartbeat, with every field re-checked."""
    up = n.get("update") if isinstance(n.get("update"), dict) else None
    rauc = n.get("rauc") if isinstance(n.get("rauc"), dict) else {}
    slots = rauc.get("slots") if isinstance(rauc.get("slots"), list) else []
    state = _text(up.get("state")) if up else None
    return {
        "node_id": n["node_id"],
        "hostname": _text(n.get("hostname")),
        "status": n.get("status"),
        "last_seen": n.get("last_seen"),
        "reported": up is not None,  # false: this node runs no update service
        "channel": _text(up.get("channel")) if up else None,
        "current_version": _text(up.get("current_version")) if up else None,
        "available_version": _text(up.get("available_version")) if up else None,
        "state": state if state in STATES else ("unknown" if up else None),
        "last_check": _text(up.get("last_check")) if up else None,
        "last_result": _text(up.get("last_result"), 500) if up else None,
        "rauc": {
            "present": rauc.get("present") is True,
            "booted_slot": _text(rauc.get("booted_slot")),
            "slots": [{k: _text(s.get(k)) for k in ("name", "bootname", "state", "boot_status", "bundle_version")}
                      for s in slots[:8] if isinstance(s, dict)],
        },
    }


class OsUpdateService:
    def __init__(self, gw):
        self.gw = gw
        self.repo = OsUpdateRepository(gw.db)
        self._lock = threading.Lock()
        # node -> last verdict written, so a heartbeat every 10 s writes once. An LRU of at most
        # MAX_NODES entries: rotating fake node ids (H-06) evicts the oldest, which costs one DB read
        # if that node reports again, never a duplicate row.
        self._seen: OrderedDict[str, tuple | None] = OrderedDict()

    # ---- reads -----------------------------------------------------------------------------
    def status(self) -> dict:
        return {"nodes": [node_view(n) for n in self.gw.registry.list()], "install": ENGINE}

    def history(self) -> dict:
        reqs = [{"action_id": a["id"], "state": a["state"], "node_id": a["params"].get("node_id"),
                 "version": a["params"].get("version"), "created_at": a["created_at"],
                 "updated_at": a["updated_at"], "message": (a.get("result") or {}).get("message")}
                for a in self.gw.actions.list() if a["type"] == ACTION][:100]
        return {"events": self.repo.list(), "requests": reqs}

    def observe(self, hb: dict) -> None:
        """Heartbeat listener: record a commit or a rollback the first time a node reports it."""
        v = node_view(hb)
        if v["state"] not in VERDICTS:
            return
        # One verdict is (state, version). last_result is free text the engine may reword between
        # heartbeats; it is kept from the first report and never makes a new row on its own.
        key = (v["state"], v["current_version"])
        node = v["node_id"]
        with self._lock:
            if node in self._seen:
                self._seen.move_to_end(node)
            else:
                last = self.repo.last(node)
                self._seen[node] = (last["state"], last["version"]) if last else None
                while len(self._seen) > MAX_NODES:
                    self._seen.popitem(last=False)
            if self._seen[node] == key:
                return
            self.repo.add(OsUpdateEventRow(node_id=node, state=key[0], version=key[1], last_result=v["last_result"],
                                           observed_at=self.gw.clock()))
            self._seen[node] = key

    # ---- os.update.install ----------------------------------------------------------------
    def refusal(self, params: dict) -> tuple[str, str] | None:
        """Why this install cannot be filed now, as (reason, message), or None."""
        n = self.gw.registry.get(params["node_id"])
        if n is None:
            return "unknown_node", f"No node {params['node_id']} has reported to this hub."
        v = node_view(n)
        if not v["reported"]:
            return "no_such_update", f"Node {v['node_id']} runs no update service, so it has no update to install."
        if v["state"] in BUSY:
            return "already_installing", f"Node {v['node_id']} is already {v['state']}; wait for the health gate's verdict."
        if v["available_version"] != params["version"]:
            return "no_such_update", (f"Version {params['version']} is not the update node {v['node_id']} offers "
                                      f"({v['available_version'] or 'none'}).")
        return None

    def problem(self, params: dict) -> str | None:
        r = self.refusal(params)
        return r[1] if r else None

    def _check_request(self, params: dict, _: Principal) -> None:
        if (r := self.refusal(params)) is not None:
            raise ApiError(409, "policy_refused", r[1], reason=r[0])

    def _run(self, a, finish) -> None:
        # No gateway path to internal/update yet (see the module docstring): say so, change nothing.
        finish(ExecResult("failed", ENGINE["message"], steps=[
            {"step": "reach update engine", "node_id": a.params["node_id"], "result": ENGINE["reason"]}]))

    def register(self) -> None:
        # "actuate": an install reboots the box into the other A/B slot (§12.3).
        self.gw.actions.register_type(ACTION, FeatureAction(
            "actuate", self._run, frozenset({"person"}), check=lambda a: self.problem(a.params),
            params_model=InstallParams, check_request=self._check_request))
        self.gw.registry.listeners.append(self.observe)
