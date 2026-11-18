# SPDX-License-Identifier: Apache-2.0
"""The agent kill switch (CORE-SEC-6, #159): one owner switch that stops every AI agent at once.

While it is on, the gateway refuses every request from an agent principal (a static agent token,
an app's agent principal issued at install, or an identity-issued agent token) before any route
runs, with 403 `permission_denied` and `reason: "agents_stopped"`. It also refuses an owner's
approval of an action an agent requested, so nothing an agent asked for before the stop can
actuate while it is on. People keep working; the automation kill switch (§12.17) is separate.

Why block instead of revoking every grant: the switch is meant for "stop now, look, then decide".
Revoking would force every app to be reinstalled to get its token back; blocking is instant and
undone by the same switch. Revoking one agent stays what `DELETE /v1/tokens/{id}` and app removal do.

Rules:
- only a person with role owner turns it on or off (an agent can never turn it off: it is refused
  at the door while the switch is on, and refused by the owner check when it is off);
- every change writes an `agents.stopped` / `agents.resumed` event (audit line plus NATS), and a
  refused change writes `authz.denied`;
- the state lives in the database (table `agent_stop_state`), so it survives a gateway restart;
- a refused agent request writes at most one `agents.refused` audit line a minute, with the count
  of refusals suppressed since the previous line, so a looping agent cannot flood the log.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .auth import Principal
from .errors import ApiError
from .ledger import Base, iso, utc
from .store import Database, FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("agent_stop")
REASON = "agents_stopped"
REFUSED_AUDIT_INTERVAL_S = 60
AGENT_KINDS = frozenset({"agent"})


class AgentStopRow(Base):
    """One row, id "global": the agent kill switch."""

    __tablename__ = "agent_stop_state"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    on: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AgentStopRepository(SqlRepository):
    def state(self) -> dict:
        with self.db.session() as s:
            r = s.get(AgentStopRow, "global")
            if r is None:
                return {"on": False, "changed_by": None, "changed_at": None, "reason": None}
            return {"on": bool(r.on), "changed_by": r.changed_by,
                    "changed_at": utc(r.changed_at) if r.changed_at else None, "reason": r.reason}

    def set(self, on: bool, by: dict, now: datetime, reason: str | None) -> None:
        values = {"on": on, "changed_by": by, "changed_at": now, "reason": reason}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(AgentStopRow).values(id="global", **values)
                      .on_conflict_do_update(index_elements=[AgentStopRow.id], set_=values))


def is_agent(principal: Principal | dict | None) -> bool:
    kind = principal.get("kind") if isinstance(principal, dict) else getattr(principal, "kind", None)
    return kind in AGENT_KINDS


class AgentStop:
    """The switch, its enforcement and its audit trail. One per gateway."""

    def __init__(self, gw: Any, db: Database | None = None):
        self.gw = gw
        self.repo = AgentStopRepository(db or gw.db)
        self._lock = threading.Lock()
        self._on = bool(self.repo.state()["on"])  # read once at start: the switch survives a restart
        self._refused: dict[str, Any] = {"last": None, "suppressed": 0}

    # ---- state -----------------------------------------------------------------------------
    @property
    def on(self) -> bool:
        return self._on

    def state(self) -> dict:
        s = self.repo.state()
        return {"on": s["on"], "changed_by": s["changed_by"],
                "changed_at": iso(s["changed_at"]) if s["changed_at"] else None, "reason": s["reason"]}

    def set(self, principal: Principal, on: bool, reason: str | None) -> dict:
        if not principal.is_owner:  # an agent can never be the one that turns agents back on
            self.gw.audit.append("authz.denied", principal.as_dict(), None,
                                 {"attempted": "turn the agent kill switch " + ("on" if on else "off"),
                                  "reason": "permission_denied"})
            raise ApiError(403, "permission_denied",
                           f"{principal.kind}/{principal.role} may not change the agent kill switch; only the owner can")
        with self._lock:
            self.repo.set(on, principal.as_dict(), self.gw.clock(), reason)
            self._on = on
        self.gw.events.publish_event(
            "agents", "stopped" if on else "resumed", {"reason": reason},
            principal=principal.as_dict(), severity="warning" if on else "info",
            resource={"kind": "agents", "id": "all"}, dedupe_key="agents:kill_switch",
        )
        return self.state()

    # ---- enforcement -----------------------------------------------------------------------
    def _refuse(self, principal: Principal, what: dict, *, throttle: bool = True) -> ApiError:
        now = self.gw.clock()
        with self._lock:
            last = self._refused["last"]
            if not throttle:
                suppressed, write = 0, True
            elif last is None or (now - last).total_seconds() >= REFUSED_AUDIT_INTERVAL_S:
                suppressed, self._refused["last"], self._refused["suppressed"] = self._refused["suppressed"], now, 0
                write = True
            else:
                self._refused["suppressed"] += 1
                write = False
        if write:
            self.gw.audit.append("agents.refused", principal.as_dict(), what.get("action_id"),
                                 {**what, "reason": REASON, "suppressed_since_last": suppressed})
        return ApiError(403, "permission_denied",
                        "the owner has stopped all AI agents (agent kill switch is on); nothing an agent asks is accepted",
                        reason=REASON)

    def refuse_agent_request(self, request: Any, principal: Principal) -> None:
        """context.PrincipalGuard: refuse every request from an agent while the switch is on."""
        if self._on and is_agent(principal):
            raise self._refuse(principal, {"method": request.method, "path": request.url.path})

    def refuse_agent_approval(self, principal: Principal, action_id: str, _body: dict, _request: Any) -> None:
        """context.ApprovalGuard: an action an agent requested cannot be approved while agents are stopped."""
        if not self._on:
            return
        action = self.gw.repo.get(action_id) if isinstance(action_id, str) else None
        if action is not None and is_agent(action.requested_by):
            raise self._refuse(principal, {"action_id": action_id, "attempted": "approve an agent's request"},
                               throttle=False)
