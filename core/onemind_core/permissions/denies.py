# SPDX-License-Identifier: Apache-2.0
"""Deny rules (gateway permissions design §3.6, fix 8): a per-principal "never".

A deny names one principal (its display id, so it holds across a new token or a reinstall: a "no"
should never lapse by accident) and either one action type or one risk tier. `decide()` checks it
before anything that could say yes, so a standing approval can never open it.

- Adding one only tightens: the owner, or the person who owns that agent's token, may add it, with
  no step-up (D-028: every tightening stays at L0).
- Removing one loosens: the owner only, with the passkey step-up the gateway has today (L1). D-028
  sets L2 as the target for permission rules; the verification levels arrive with design PR 11.
- An agent never adds or removes a deny, its own included.

Table `permissions_denies` (feature "permissions"; new table, so create_all adds it at this shape).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import DateTime, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..audit import AuditLog
from ..auth import Principal
from ..errors import ApiError
from ..ledger import Base, iso, utc
from ..store import Database, FeatureSchema

SCHEMA = FeatureSchema("permissions")

TIERS = {"T0": ("read",), "T1": ("write",), "T2": ("sensitive",), "T3": ("destructive",), "T4": ("actuate",)}
PRINCIPAL_RE = re.compile(r"^(agent|plugin|automation|person):[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}$")
TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
MAX_DENIES = 500


class DenyRow(Base):
    __tablename__ = "permissions_denies"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    principal: Mapped[str] = mapped_column(String(100), index=True)
    action_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tier: Mapped[str | None] = mapped_column(String(4), nullable=True)  # T0..T4 or P (physical)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _json(r: DenyRow) -> dict:
    return {"id": r.id, "principal": r.principal, "action_type": r.action_type, "tier": r.tier, "reason": r.reason,
            "created_by": r.created_by, "created_at": iso(utc(r.created_at))}


class DenyStore:
    def __init__(self, db: Database, audit: AuditLog, clock: Callable[[], datetime]):
        self.db, self.audit, self.clock = db, audit, clock
        # person id -> the agents and plugins whose tokens that person owns (identity); set by the router.
        self.owned_by: Callable[[str], set[str]] = lambda _uid: set()

    def list(self) -> list[dict]:
        with self.db.session() as s:
            return [_json(r) for r in s.scalars(select(DenyRow).order_by(DenyRow.created_at, DenyRow.id))]

    def match(self, principal: str, action_type: str, risk: str | None, physical: bool) -> str | None:
        """The id of the first deny rule covering this request, or None."""
        with self.db.session() as s:
            rows = list(s.scalars(select(DenyRow).where(DenyRow.principal == principal)
                                  .order_by(DenyRow.created_at, DenyRow.id)))
        for r in rows:
            if r.action_type == action_type:
                return r.id
            if r.tier == "P" and physical:
                return r.id
            if r.tier in TIERS and risk in TIERS[r.tier]:
                return r.id
        return None

    @staticmethod
    def may_hold_agents(p: Principal) -> bool:
        """People who can own an agent token (tokens:self): the owner and adults. Guests and children cannot."""
        return p.kind == "person" and p.role in ("owner", "adult")

    def may_manage(self, p: Principal, principal: str, user_id: str | None) -> bool:
        """Who has a say over a principal: the owner, or the person who owns that agent's token."""
        if p.is_owner:
            return True
        return self.may_hold_agents(p) and user_id is not None and principal in self.owned_by(user_id)

    def visible_to(self, p: Principal, user_id: str | None) -> list[dict]:
        rows = self.list()
        if p.is_owner:
            return rows
        mine = self.owned_by(user_id) if user_id else set()
        return [r for r in rows if r["principal"] in mine]

    def add(self, p: Principal, user_id: str | None, principal: str, action_type: str | None, tier: str | None,
            reason: str | None) -> dict:
        from ..automation.store import new_id

        if not self.may_hold_agents(p):
            self._denied(p, "add a deny rule")
        if not PRINCIPAL_RE.fullmatch(principal):
            raise ApiError(422, "conflict", "principal must be <kind>:<id> for an agent, plugin, automation or person")
        if (action_type is None) == (tier is None):
            raise ApiError(422, "conflict", "name exactly one of action_type or tier")
        if action_type is not None and not TYPE_RE.fullmatch(action_type):
            raise ApiError(422, "conflict", "action_type must look like app.install")
        if tier is not None and tier not in (*TIERS, "P"):
            raise ApiError(422, "conflict", "tier is one of T0, T1, T2, T3, T4 or P (physical)")
        from ..principals import display_key

        if principal == display_key(p.as_dict()):
            raise ApiError(422, "conflict", "a deny rule is for someone else's requests, not your own")
        if principal.startswith("person:") and not p.is_owner:
            self._denied(p, "add a deny rule for a person")
        if not self.may_manage(p, principal, user_id):
            self._denied(p, f"add a deny rule for {principal}")
        for r in self.list():  # the same "never" twice is the rule already there (a retry adds nothing)
            if (r["principal"], r["action_type"], r["tier"]) == (principal, action_type, tier):
                return r
        if len(self.list()) >= MAX_DENIES:
            raise ApiError(409, "conflict", f"at most {MAX_DENIES} deny rules")
        row = DenyRow(id=new_id("den_"), principal=principal, action_type=action_type, tier=tier,
                      reason=(reason or None) and reason[:200], created_by=p.as_dict(), created_at=self.clock())
        with self.db.session.begin() as s:
            s.add(row)
        out = _json(row)
        self.audit.append("approval.deny.added", p.as_dict(), None, {k: out[k] for k in ("id", "principal", "action_type", "tier", "reason")})
        return out

    def remove(self, p: Principal, deny_id: str, approval: str) -> None:
        if not p.is_owner:
            self._denied(p, "remove a deny rule")
        with self.db.session.begin() as s:
            row = s.get(DenyRow, deny_id)
            if row is None:
                raise ApiError(404, "not_found", "no such deny rule")
            gone = _json(row)
            s.execute(delete(DenyRow).where(DenyRow.id == deny_id))
        self.audit.append("approval.deny.removed", p.as_dict(), None,
                          {"id": deny_id, "principal": gone["principal"], "action_type": gone["action_type"],
                           "tier": gone["tier"], "approval": approval})

    def _denied(self, p: Principal, what: str) -> None:
        self.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
        raise ApiError(403, "permission_denied", f"{p.kind}/{p.role} may not {what}")
