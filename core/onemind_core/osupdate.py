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
- `os.update.settings` (REL-02, #154): the owner's update policy (`auto`, the security channel's
  default, `notify` or `off`) and maintenance window. The host stores them under /data, where the
  engine reads them on its next cycle; the image's read-only update.conf stays the default. Turning
  automatic updates off or moving the window loosens a security setting, so approving it takes the
  owner's passkey (routers/osupdates.py); turning them back on with the same window does not (D-028:
  every tightening stays L0).
- `os.rollback` (P-16): go back to the previous OS version. The other A/B slot already holds it and
  already passed the health gate once, so nothing is downloaded: the host marks that slot active and
  reboots, and the gate commits it. Destructive (it discards the running version and its slot), so
  approving it takes the owner's passkey (routers/osupdates.py). Refused when the other slot is not
  known good.

The path to the engine is the host executor (hostlink.py, docs/leap/core/HOST-ACTIONS.md): an approved
install is sent to `onemindd host serve` on /run/onemind/host.sock, which runs `internal/update` (restic
snapshot, RAUC install into the other slot, reboot, health gate, automatic rollback). Without that
socket (a dev box, the compose stack) an approved install finishes `failed` with reason
`engine_unreachable` and tells the owner to run `onemind update apply` at the box. It never pretends
to have installed anything, and the host runs only the version the owner approved.
Heartbeats come from any LAN device (no NATS users yet, H-06), so every field is re-checked here.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import OrderedDict
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, Integer, String, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from .actions import FeatureAction
from .auth import Principal
from .errors import ApiError
from .executors import ExecResult
from .hostlink import UNREACHABLE, HostLink
from .ledger import Base, iso
from .nodes import MAX_NODES
from .store import FeatureSchema, SqlRepository

log = logging.getLogger("onemind.osupdate")

SCHEMA = FeatureSchema("osupdate")  # version 1 = the shape below
ACTION = "os.update.install"
ROLLBACK = "os.rollback"
SETTINGS = "os.update.settings"
POLICIES = ("auto", "notify", "off")  # internal/update Policy
# internal/update ParseWindow: "any", or HH:MM-HH:MM local time that may wrap midnight, start != end.
WINDOW = re.compile(r"^(?:any|(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d)$")
SOURCES = ("image", "owner")
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
               "Install at the box with `sudo onemind update apply --local`; it keeps the A/B rollback and the health gate.",
}


def _text(v: object, n: int = 128) -> str | None:
    return v[:n] if isinstance(v, str) and v else None


class InstallParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    version: str = Field(pattern=r"^[0-9A-Za-z.+-]{1,64}$")


class RollbackParams(BaseModel):
    """`version` is the version the owner read on the Updates screen: the host goes back to that one or to nothing."""

    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    version: str = Field(pattern=r"^[0-9A-Za-z.+-]{1,64}$")


def valid_window(v: object) -> bool:
    return isinstance(v, str) and WINDOW.fullmatch(v) is not None and (v == "any" or v[:5] != v[6:])


class SettingsParams(BaseModel):
    """The policy and window the owner will read on the approval card; the host stores exactly these."""

    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    policy: str = Field(pattern=r"^(auto|notify|off)$")
    window: str = Field(max_length=11)

    @field_validator("window")
    @classmethod
    def _window(cls, v: str) -> str:
        if not valid_window(v):
            raise ValueError("window must be HH:MM-HH:MM (local time, may wrap past midnight, start and end differ) or any")
        return v


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


def _no_rollback(reason: str, message: str) -> dict:
    return {"available": False, "version": None, "slot": None, "reason": reason, "message": message}


def rollback_view(reported: bool, state: str | None, current: str | None, rauc: dict, previous: str | None = None) -> dict:
    """What going back would boot, from the node's heartbeat: the one other rootfs slot, when it is marked
    good and holds a known, different version. The version is the slot's own record, else the one the update
    engine noted when it committed the update that replaced it (`previous_version`: a slot the image builder
    wrote has no record of its own). The host checks again from RAUC itself before it acts."""
    if not reported:
        return _no_rollback("no_update_service", "This machine runs no update service, so it cannot go back.")
    if state in BUSY:
        return _no_rollback("update_in_progress", f"An OS update is {state}; wait for the health gate's verdict.")
    booted = rauc.get("booted_slot")
    others = [s for s in rauc["slots"] if (s.get("class") == "rootfs" or (not s.get("class") and (s.get("name") or "").startswith("rootfs.")))
              and booted not in (s.get("bootname"), s.get("name"))]
    if not booted or len(others) != 1:
        return _no_rollback("no_previous_slot", "This machine has no other system slot to go back to.")
    o = others[0]
    name = o.get("bootname") or "the other slot"
    if o.get("boot_status") != "good":
        return _no_rollback("previous_not_good", f"Slot {name} is not marked good ({o.get('boot_status') or 'no status'}): "
                                                 "it did not pass the health gate, so the box will not boot it.")
    version = o.get("bundle_version") or previous
    if not version:
        return _no_rollback("previous_unknown", f"Slot {name} holds no known OneMind version.")
    if version == current:
        return _no_rollback("same_version", f"The other slot holds {current}, the version already running.")
    return {"available": True, "version": version, "slot": o.get("bootname"), "reason": None, "message": None}


def node_view(n: dict) -> dict:
    """One node's OS facts, from its heartbeat, with every field re-checked."""
    up = n.get("update") if isinstance(n.get("update"), dict) else None
    rauc = n.get("rauc") if isinstance(n.get("rauc"), dict) else {}
    slots = rauc.get("slots") if isinstance(rauc.get("slots"), list) else []
    state = _text(up.get("state")) if up else None
    view_rauc = {
        "present": rauc.get("present") is True,
        "booted_slot": _text(rauc.get("booted_slot")),
        "slots": [{k: _text(s.get(k)) for k in ("name", "class", "bootname", "state", "boot_status", "bundle_version")}
                  for s in slots[:8] if isinstance(s, dict)],
    }
    current = _text(up.get("current_version")) if up else None
    state = state if state in STATES else ("unknown" if up else None)
    policy = up.get("policy") if up and up.get("policy") in POLICIES else None
    window = up.get("window") if up and valid_window(up.get("window")) else None
    source = up.get("settings_source") if up and up.get("settings_source") in SOURCES else None
    return {
        "node_id": n["node_id"],
        "hostname": _text(n.get("hostname")),
        "status": n.get("status"),
        "last_seen": n.get("last_seen"),
        "reported": up is not None,  # false: this node runs no update service
        "channel": _text(up.get("channel")) if up else None,
        "current_version": current,
        "available_version": _text(up.get("available_version")) if up else None,
        "state": state,
        "last_check": _text(up.get("last_check")) if up else None,
        "last_result": _text(up.get("last_result"), 500) if up else None,
        # REL-02: the update policy and window in force, and whose they are (null from an older onemindd).
        "policy": policy,
        "window": window,
        "settings_source": source,
        "rauc": view_rauc,
        "rollback": rollback_view(up is not None, state, current, view_rauc, _text(up.get("previous_version")) if up else None),
    }


INSTALL_READY = {
    "available": True,
    "reason": None,
    "message": "An approved install runs on this box through the host service: restic snapshot, install into the "
               "other A/B slot, reboot, health gate, automatic rollback.",
}


ROLLBACK_ENGINE = {
    "available": False,
    "reason": "engine_unreachable",
    "message": "The gateway cannot reach the box's host service yet, so an approved rollback does not run. "
               "At the box, the rescue console shows both system slots.",
}
ROLLBACK_READY = {
    "available": True,
    "reason": None,
    "message": "An approved rollback runs on this box through the host service: it marks the previous system slot "
               "active and reboots into it, and the health gate commits it.",
}


SETTINGS_ENGINE = {
    "available": False,
    "reason": "engine_unreachable",
    "message": "The gateway cannot reach the box's host service yet, so an approved settings change does not run. "
               "The image's settings stay in force: security updates install by themselves inside the window.",
}
SETTINGS_READY = {
    "available": True,
    "reason": None,
    "message": "An approved change is stored on this box by the host service and counts from the next update check.",
}


def settings_need_passkey(params: dict, current: dict | None) -> bool:
    """True when the change loosens a security setting (D-028: L2 for every security-related setting, every
    tightening L0): anything but automatic updates with the window the node reports now.

    Deliberately coarse, erring on the strict side: off -> notify and a fixed window -> "any" also ask for
    the passkey although neither loosens (stricter than needed, never weaker). On the stable channel,
    notify -> auto with the same window asks for none: automatic installs inside the window are the
    security default, and the health-gated rollback makes them safe."""
    if params.get("policy") != "auto":
        return True
    return current is None or current.get("window") is None or params.get("window") != current.get("window")


class OsUpdateService:
    def __init__(self, gw, link: HostLink | None = None):
        self.gw = gw
        self.link = link
        self.repo = OsUpdateRepository(gw.db)
        self._lock = threading.Lock()
        # node -> last verdict written, so a heartbeat every 10 s writes once. An LRU of at most
        # MAX_NODES entries: rotating fake node ids (H-06) evicts the oldest, which costs one DB read
        # if that node reports again, never a duplicate row.
        self._seen: OrderedDict[str, tuple | None] = OrderedDict()

    # ---- reads -----------------------------------------------------------------------------
    def install_problem(self) -> tuple[str, str] | None:
        """(reason, message) why an approved install cannot run on this box now, or None when it can."""
        return self.link.problem(ACTION) if self.link is not None else (UNREACHABLE, ENGINE["message"])

    def rollback_problem(self) -> tuple[str, str] | None:
        """(reason, message) why an approved rollback cannot run on this box now, or None when it can."""
        return self.link.problem(ROLLBACK) if self.link is not None else (UNREACHABLE, ROLLBACK_ENGINE["message"])

    def status(self) -> dict:
        p = self.install_problem()
        install = INSTALL_READY if p is None else ENGINE if p[0] == UNREACHABLE else \
            {"available": False, "reason": p[0], "message": p[1]}
        q = self.rollback_problem()
        rollback = ROLLBACK_READY if q is None else ROLLBACK_ENGINE if q[0] == UNREACHABLE else \
            {"available": False, "reason": q[0], "message": q[1]}
        r = self.settings_problem()
        settings = SETTINGS_READY if r is None else SETTINGS_ENGINE if r[0] == UNREACHABLE else \
            {"available": False, "reason": r[0], "message": r[1]}
        return {"nodes": [node_view(n) for n in self.gw.registry.list()], "install": install, "rollback": rollback,
                "settings": settings}

    def settings_problem(self) -> tuple[str, str] | None:
        """(reason, message) why an approved settings change cannot run on this box now, or None when it can."""
        return self.link.problem(SETTINGS) if self.link is not None else (UNREACHABLE, SETTINGS_ENGINE["message"])

    def history(self) -> dict:
        reqs = [{"action_id": a["id"], "type": a["type"], "state": a["state"], "node_id": a["params"].get("node_id"),
                 "version": a["params"].get("version"), "policy": a["params"].get("policy"),
                 "window": a["params"].get("window"), "created_at": a["created_at"],
                 "updated_at": a["updated_at"], "message": (a.get("result") or {}).get("message")}
                for a in self.gw.actions.list() if a["type"] in (ACTION, ROLLBACK, SETTINGS)][:100]
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
        if self.link is not None and self.link.present() and v["node_id"] != self.gw.settings.node_id:
            # The host service acts on the box it runs on. Other machines need signed jobs (contract 12.11).
            return "other_node", "The host service installs updates on this hub only; other machines update at the box."
        return None

    def problem(self, params: dict) -> str | None:
        r = self.refusal(params)
        return r[1] if r else None

    # ---- os.rollback ------------------------------------------------------------------------
    def rollback_refusal(self, params: dict) -> tuple[str, str] | None:
        """Why this rollback cannot be filed (or approved) now, as (reason, message), or None."""
        n = self.gw.registry.get(params["node_id"])
        if n is None:
            return "unknown_node", f"No node {params['node_id']} has reported to this hub."
        v = node_view(n)
        rb = v["rollback"]
        if not rb["available"]:
            return rb["reason"], rb["message"]
        if rb["version"] != params["version"]:
            return "no_such_version", (f"Version {params['version']} is not the previous version of node {v['node_id']} "
                                       f"({rb['version']}).")
        if self.link is not None and self.link.present() and v["node_id"] != self.gw.settings.node_id:
            return "other_node", "The host service goes back on this hub only; other machines go back at the box."
        # The heartbeat cannot see the host's own refusals (a version just rolled back sits in the gate's
        # bad-releases list, which the gateway never reads), so ask the host: a request it would refuse
        # is not filed or approved. A host that cannot be reached is reported when the action runs.
        if self.link is not None and self.link.present() and v["node_id"] == self.gw.settings.node_id:
            p = self.rollback_problem()
            if p is not None and p[0] != UNREACHABLE:
                return p
        return None

    def rollback_check(self, a) -> str | None:
        """Approval-time re-check: the node may have updated or fallen back since the request."""
        r = self.rollback_refusal(a.params)
        return r[1] if r else None

    def _check_rollback_request(self, params: dict, _: Principal) -> None:
        if (r := self.rollback_refusal(params)) is not None:
            raise ApiError(409, "policy_refused", r[1], reason=r[0])

    def _run_rollback(self, a, finish) -> None:
        p = self.rollback_problem()
        if p is None:
            self.link.run(a, finish)  # type: ignore[union-attr]
            return
        message = ROLLBACK_ENGINE["message"] if p[0] == UNREACHABLE else p[1]
        finish(ExecResult("failed", message, steps=[
            {"step": "reach host service", "node_id": a.params["node_id"], "result": p[0]}]))

    def _check_request(self, params: dict, _: Principal) -> None:
        if (r := self.refusal(params)) is not None:
            raise ApiError(409, "policy_refused", r[1], reason=r[0])

    def _run(self, a, finish) -> None:
        """After the owner's approval: hand the approved version to the host service, or say why not."""
        p = self.install_problem()
        if p is None:
            self.link.run(a, finish)  # type: ignore[union-attr]  # install_problem is None only with a link
            return
        message = ENGINE["message"] if p[0] == UNREACHABLE else p[1]
        finish(ExecResult("failed", message, steps=[
            {"step": "reach update engine", "node_id": a.params["node_id"], "result": p[0]}]))

    # ---- os.update.settings -------------------------------------------------------------------
    def current_settings(self, node_id: str) -> dict | None:
        n = self.gw.registry.get(node_id)
        return node_view(n) if n is not None else None

    def settings_refusal(self, params: dict) -> tuple[str, str] | None:
        """Why this settings change cannot be filed (or approved) now, as (reason, message), or None."""
        v = self.current_settings(params["node_id"])
        if v is None:
            return "unknown_node", f"No node {params['node_id']} has reported to this hub."
        if not v["reported"]:
            return "no_update_service", f"Node {v['node_id']} runs no update service, so it has no update settings."
        if v["policy"] == params["policy"] and v["window"] == params["window"]:
            return "no_change", f"Node {v['node_id']} already uses policy {v['policy']} with window {v['window']}."
        if self.link is not None and self.link.present() and v["node_id"] != self.gw.settings.node_id:
            return "other_node", "The host service changes update settings on this hub only; other machines are set at the box."
        return None

    def settings_check(self, a) -> str | None:
        r = self.settings_refusal(a.params)
        return r[1] if r else None

    def check_settings_request(self, params: dict, _: Principal | None = None) -> None:
        if (r := self.settings_refusal(params)) is not None:
            raise ApiError(409, "policy_refused", r[1], reason=r[0])

    def _run_settings(self, a, finish) -> None:
        p = self.settings_problem()
        if p is None:
            self.link.run(a, finish)  # type: ignore[union-attr]
            return
        message = SETTINGS_ENGINE["message"] if p[0] == UNREACHABLE else p[1]
        finish(ExecResult("failed", message, steps=[
            {"step": "reach host service", "node_id": a.params["node_id"], "result": p[0]}]))

    def register(self) -> None:
        # "actuate": an install reboots the box into the other A/B slot (§12.3).
        self.gw.actions.register_type(ACTION, FeatureAction(
            "actuate", self._run, frozenset({"person"}), check=lambda a: self.problem(a.params),
            params_model=InstallParams, check_request=self._check_request))
        # "destructive": it discards the running version for the other slot. The passkey step-up is the
        # approval guard in routers/osupdates.py. A person files it; an agent or the CLI only requests.
        self.gw.actions.register_type(ROLLBACK, FeatureAction(
            "destructive", self._run_rollback, frozenset({"person"}), check=self.rollback_check,
            params_model=RollbackParams, check_request=self._check_rollback_request))
        # "sensitive": it changes whether security updates install by themselves (REL-02). Only an owner
        # files it (contract §12.5: O); loosening it takes the owner's passkey (routers/osupdates.py).
        self.gw.actions.register_type(SETTINGS, FeatureAction(
            "sensitive", self._run_settings, frozenset(), check=self.settings_check,
            params_model=SettingsParams, check_request=self.check_settings_request))
        self.gw.registry.listeners.append(self.observe)
