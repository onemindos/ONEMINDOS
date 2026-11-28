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
from .principals import display_key
from .store import Database, FeatureSchema

SCHEMA = FeatureSchema("agents")


@SCHEMA.step(2, "bind Inputs declarations to permanent identities")
def _bind_inputs(conn: Connection) -> None:
    if "identity_uid" not in {c["name"] for c in inspect(conn).get_columns("agents_inputs")}:
        conn.execute(text("ALTER TABLE agents_inputs ADD COLUMN identity_uid VARCHAR(40)"))
        if conn.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE agents_inputs ALTER COLUMN principal_id TYPE VARCHAR(100)"))


@SCHEMA.step(3, "bind per-agent grants to permanent identities")
def _bind_controls(conn: Connection) -> None:
    additions = {
        "agents_principals": {"budget_uid": "VARCHAR(40)", "resumed_uid": "VARCHAR(40)", "budget_ceiling": "INTEGER"},
        "agents_nats_keys": {"principal_uid": "VARCHAR(40)"},
    }
    for table, columns in additions.items():
        existing = {c["name"] for c in inspect(conn).get_columns(table)}
        for column, kind in columns.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {kind}"))

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
    budget_uid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    budget_ceiling: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resumed_uid: Mapped[str | None] = mapped_column(String(40), nullable=True)
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
                now = max(utc(now), utc(row.updated_at) + timedelta(microseconds=1))
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
        uid = self.uid(p.id) if row and (row.budget_uid or row.resumed_uid) else None
        budget, cancelled_at = self._limits(row, uid)
        if cancelled_at is not None:
            self.audit.append("authz.denied", p.as_dict(), None, {"attempted": "request action", "reason": "agent_cancelled"})
            raise ApiError(403, "permission_denied", "this agent was cancelled by the owner", reason="agent_cancelled")
        if self.used_24h(p.id) >= budget:
            raise ApiError(429, "rate_limited", f"daily budget of {budget} requests used up",
                           reason="agent_budget", retry_after_s=3600)

    # ---- owner operations -------------------------------------------------------------------
    def owner_only(self, p: Principal, what: str) -> None:
        if not p.is_owner:
            raise self.actions._deny(p, what)

    @staticmethod
    def _limits(row: AgentRow | None, uid: str | None) -> tuple[int, datetime | None]:
        budget = DEFAULT_BUDGET_PER_DAY
        cancelled_at = None
        if row is not None:
            if uid is not None and row.budget_uid == uid:
                budget = row.budget_per_day
            else:
                # A name can carry a restriction forward. Only the reviewed identity gets a raise.
                budget = row.budget_ceiling if row.budget_ceiling is not None else min(row.budget_per_day, budget)
            if uid is None or row.resumed_uid != uid:
                cancelled_at = row.cancelled_at
        return budget, cancelled_at

    def control_state(self, pid: str) -> dict:
        """Snapshot the agent and its limits for a queued permission change."""
        row = self._row(pid)
        uid = self.uid(pid)
        budget, cancelled_at = self._limits(row, uid)
        return {
            "budget_per_day": budget,
            "cancelled_at": iso(cancelled_at),
            "updated_at": iso(row.updated_at) if row else None,
            "principal_uid": uid,
        }

    def view(self, pid: str) -> dict:
        state = self.control_state(pid)
        pending = self._mine(pid, {"awaiting_approval"})
        return {
            "id": pid,
            "budget_per_day": state["budget_per_day"],
            "used_24h": self.used_24h(pid),
            "pending_approvals": len(pending),
            "cancelled": state["cancelled_at"] is not None,
            "cancelled_at": state["cancelled_at"],
            "principal_uid": state["principal_uid"],
        }

    def uid(self, pid: str) -> str | None:
        reg = self.actions.principals
        live = reg.resolve(display_key({"id": pid, "kind": "agent"})) if reg is not None else None
        return live["uid"] if live else None

    def known_ids(self) -> list[str]:
        ids = {a.requested_by["id"] for a in self.actions.repo.list() if a.requested_by.get("kind") == "agent"}
        with self.db.session() as s:
            ids |= set(s.scalars(select(AgentRow.principal_id)))
        return sorted(ids)

    def list(self, p: Principal) -> list[dict]:
        self.owner_only(p, "list agents")
        return [self.view(i) for i in self.known_ids()]

    def get(self, p: Principal, name: str) -> dict:
        self.owner_only(p, "read an agent")
        return self.view(self.principal_id(name))

    def set_budget(self, p: Principal, name: str, budget: int, *, uid: str | None, tighten: bool = False) -> dict:
        self.owner_only(p, "set an agent budget")
        pid = self.principal_id(name)
        ceiling, _ = self._limits(self._row(pid), None)
        self._save(pid, budget_per_day=budget, budget_uid=uid,
                   budget_ceiling=min(ceiling, budget) if tighten else ceiling)
        self.audit.append("agent.budget_set", p.as_dict(), None,
                          {"agent": pid, "principal_uid": uid, "budget_per_day": budget})
        return self.view(pid)

    def cancel(self, p: Principal, name: str) -> dict:
        self.owner_only(p, "cancel an agent")
        pid = self.principal_id(name)
        now = self.clock()
        self._save(pid, cancelled_at=now, cancelled_by=p.id, resumed_uid=None)
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
            self.actions.principals.retire(display_key({"id": pid, "kind": "agent"}), "agent_cancelled")
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

    def resume(self, p: Principal, name: str, *, uid: str) -> dict:
        self.owner_only(p, "resume an agent")
        pid = self.principal_id(name)
        self._save(pid, resumed_uid=uid)
        self.audit.append("agent.resumed", p.as_dict(), None, {"agent": pid, "principal_uid": uid})
        return self.view(pid)
