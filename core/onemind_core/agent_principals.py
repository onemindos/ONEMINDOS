# SPDX-License-Identifier: Apache-2.0
"""AIG-03 (#167): an AI agent such as Hermes is a gateway principal with its own limits.

What already held: an agent (kind "agent") may file a request and never approve or deny one
(actions.py), and its token carries only the scopes it was minted with, never more than the person
who owns it (identity). What this adds, in plain words:

- a daily budget: the most requests the agent may file in a rolling 24 hours, so a looping model
  cannot flood the owner's Approvals screen;
- a cancel path: the owner stops an agent in one call. New requests are refused, every request it
  has waiting for approval is cancelled, and its identity tokens are revoked;
- an owner-visible record of both (audit lines agent.budget_set, agent.cancelled, agent.resumed).

Nothing here lets an agent do more. Every limit only refuses; the approval rule is unchanged.
An agent without a row gets DEFAULT_BUDGET_PER_DAY.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Integer, String, inspect, select, text, update
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from .actions import ActionService
from .audit import AuditLog
from .auth import Principal
from .errors import ApiError
from .ledger import Base, iso, utc
from .store import Database, FeatureSchema

SCHEMA = FeatureSchema("agents")


@SCHEMA.step(2, "bind Inputs declarations to permanent identities")
def _bind_inputs(conn: Connection) -> None:
    if "identity_uid" not in {c["name"] for c in inspect(conn).get_columns("agents_inputs")}:
        conn.execute(text("ALTER TABLE agents_inputs ADD COLUMN identity_uid VARCHAR(40)"))
        if conn.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE agents_inputs ALTER COLUMN principal_id TYPE VARCHAR(100)"))

DEFAULT_BUDGET_PER_DAY = 200
MAX_BUDGET_PER_DAY = 10_000
# The principal id exactly as the gateway shows it: agent:<name> for identity tokens and apps, or a
# static-file id such as hermes.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,79}$")
WINDOW = timedelta(hours=24)


class AgentRow(Base):
    __tablename__ = "agents_principals"
    principal_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    budget_per_day: Mapped[int] = mapped_column(Integer, default=DEFAULT_BUDGET_PER_DAY)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentPrincipals:
    def __init__(self, db: Database, actions: ActionService, audit: AuditLog, clock):
        self.db, self.actions, self.audit, self.clock = db, actions, audit, clock
        actions.requester_checks.append(self.check_request)

    @staticmethod
    def principal_id(name: str) -> str:
        if not NAME_RE.fullmatch(name):
            raise ApiError(422, "conflict", "agent id: a-z, 0-9, '.', '_', ':', '-'")
        return name

    def _row(self, pid: str) -> AgentRow | None:
        with self.db.session() as s:
            return s.get(AgentRow, pid)

    def _save(self, pid: str, **fields) -> None:
        now = self.clock()
        with self.db.session.begin() as s:
            row = s.get(AgentRow, pid)
            if row is None:
                s.add(AgentRow(principal_id=pid, **{"budget_per_day": DEFAULT_BUDGET_PER_DAY, **fields}, updated_at=now))
            else:
                s.execute(update(AgentRow).where(AgentRow.principal_id == pid).values(updated_at=now, **fields))

    def _mine(self, pid: str, states: set[str] | None = None):
        return [a for a in self.actions.repo.list(states) if a.requested_by.get("id") == pid]

    def used_24h(self, pid: str) -> int:
        since = self.clock() - WINDOW
        return sum(1 for a in self._mine(pid) if utc(a.created_at) > since)

    def check_request(self, p: Principal) -> None:
        """Refuse a fresh request from a cancelled agent or one over its daily budget."""
        if p.kind != "agent":
            return
        row = self._row(p.id)
        if row is not None and row.cancelled_at is not None:
            self.audit.append("authz.denied", p.as_dict(), None, {"attempted": "request action", "reason": "agent_cancelled"})
            raise ApiError(403, "permission_denied", "this agent was cancelled by the owner", reason="agent_cancelled")
        budget = row.budget_per_day if row is not None else DEFAULT_BUDGET_PER_DAY
        if self.used_24h(p.id) >= budget:
            raise ApiError(429, "rate_limited", f"daily budget of {budget} requests used up",
                           reason="agent_budget", retry_after_s=3600)

    # ---- owner operations -------------------------------------------------------------------
    @staticmethod
    def _owner(p: Principal, what: str, svc: ActionService) -> None:
        if not p.is_owner:
            raise svc._deny(p, what)

    def view(self, pid: str) -> dict:
        row = self._row(pid)
        pending = self._mine(pid, {"awaiting_approval"})
        return {
            "id": pid,
            "budget_per_day": row.budget_per_day if row else DEFAULT_BUDGET_PER_DAY,
            "used_24h": self.used_24h(pid),
            "pending_approvals": len(pending),
            "cancelled": bool(row and row.cancelled_at),
            "cancelled_at": iso(row.cancelled_at) if row else None,
            "principal_uid": self._uid(pid),
        }

    def _uid(self, pid: str) -> str | None:
        reg = self.actions.principals
        live = reg.live(pid if ":" in pid else f"agent:{pid}") if reg is not None else None
        return live["uid"] if live else None

    def known_ids(self) -> list[str]:
        ids = {a.requested_by["id"] for a in self.actions.repo.list() if a.requested_by.get("kind") == "agent"}
        with self.db.session() as s:
            ids |= set(s.scalars(select(AgentRow.principal_id)))
        return sorted(ids)

    def list(self, p: Principal) -> list[dict]:
        self._owner(p, "list agents", self.actions)
        return [self.view(i) for i in self.known_ids()]

    def get(self, p: Principal, name: str) -> dict:
        self._owner(p, "read an agent", self.actions)
        return self.view(self.principal_id(name))

    def set_budget(self, p: Principal, name: str, budget: int) -> dict:
        self._owner(p, "set an agent budget", self.actions)
        pid = self.principal_id(name)
        self._save(pid, budget_per_day=budget)
        self.audit.append("agent.budget_set", p.as_dict(), None, {"agent": pid, "budget_per_day": budget})
        return self.view(pid)

    def cancel(self, p: Principal, name: str) -> dict:
        self._owner(p, "cancel an agent", self.actions)
        pid = self.principal_id(name)
        now = self.clock()
        self._save(pid, cancelled_at=now, cancelled_by=p.id)
        withdrawn = 0
        for a in self._mine(pid, {"awaiting_approval"}):
            moved = self.actions.repo.transition(a.id, {"awaiting_approval"}, "cancelled", now,
                                                 decided_by=p.as_dict(), decided_at=now)
            if moved is not None:
                withdrawn += 1
                self.actions._release_feature(a)
                self.audit.append("action.denied", p.as_dict(), a.id, {"params": a.params, "reason": "agent_cancelled"})
        revoked = self.revoke_tokens(pid, now)
        if self.actions.principals is not None:  # PR 7: its standing approvals stop with it
            self.actions.principals.retire(pid if ":" in pid else f"agent:{pid}", "agent_cancelled")
        self.audit.append("agent.cancelled", p.as_dict(), None,
                          {"agent": pid, "requests_cancelled": withdrawn, "tokens_revoked": revoked})
        return {**self.view(pid), "requests_cancelled": withdrawn, "tokens_revoked": revoked}

    def revoke_tokens(self, pid: str, now: datetime) -> int:
        from .identity.models import TokenRow  # identity is optional wiring; its tokens die with the agent

        with self.db.session.begin() as s:
            res = s.execute(update(TokenRow).where(TokenRow.principal_id == pid, TokenRow.kind == "agent",
                                                   TokenRow.revoked_at.is_(None))
                            .values(revoked_at=now, prev_hash=None))
            return res.rowcount or 0

    def resume(self, p: Principal, name: str) -> dict:
        self._owner(p, "resume an agent", self.actions)
        pid = self.principal_id(name)
        self._save(pid, cancelled_at=None, cancelled_by=None)
        self.audit.append("agent.resumed", p.as_dict(), None, {"agent": pid})
        return self.view(pid)
