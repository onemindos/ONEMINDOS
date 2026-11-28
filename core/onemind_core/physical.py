# SPDX-License-Identifier: Apache-2.0
"""The owner's motion lockout (#723): one switch that refuses every physical action.

An action type registered with FeatureAction(physical=True) moves or switches something in the world.
While the lockout is on, the action service files none of them and approves none of them (409
conflict, reason motion_lockout). Only an owner reads or changes the switch: agents, automations,
plugins and machines get 403, and the route scope `physical:admin` is minted to no one. Turning it
on is one call; turning it off again needs a fresh passkey sign-in once passkeys are active. Every
change is an audit line. A lockout that cannot be read counts as on (actions.ActionService._locked).
Every change confirms fabric enforcement before acknowledging it. A failed confirmation leaves the
local switch in effect and sends an error to the caller.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .audit import AuditLog
from .auth import Principal
from .errors import ApiError
from .jsonbody import JsonBody
from .ledger import Base, iso, utc
from .store import Database, FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("physical")


class MotionLockoutRow(Base):
    """One row, id "global": the owner's motion lockout."""

    __tablename__ = "physical_lockout"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_by: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class MotionLockoutState(BaseModel):
    """GET/PUT /v1/physical/lockout: whether physical actions are refused, and who set it."""

    locked: bool
    changed_by: dict | None = None
    changed_at: str | None = None
    reason: str | None = None


class MotionLockoutChange(JsonBody):
    model_config = ConfigDict(extra="forbid")
    locked: bool
    reason: str | None = Field(default=None, max_length=500)


class MotionLockoutRepository(SqlRepository):
    def get(self) -> MotionLockoutRow | None:
        with self.db.session() as s:
            row = s.get(MotionLockoutRow, "global")
            if row is not None:
                s.expunge(row)
            return row

    def set(self, locked: bool, by: dict, now: datetime, reason: str | None) -> None:
        values = {"locked": locked, "changed_by": by, "changed_at": now, "reason": reason}
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(MotionLockoutRow).values(id="global", **values)
                      .on_conflict_do_update(index_elements=[MotionLockoutRow.id], set_=values))


class MotionLockout:
    def __init__(self, db: Database, audit: AuditLog, clock: Callable[[], datetime]):
        self.repo = MotionLockoutRepository(db)
        self.audit = audit
        self.clock = clock
        self._changes = threading.Lock()
        self.confirm_fabric: Callable[[bool], None] | None = None

    def locked(self) -> bool:
        """For ActionService.motion_lockout. Raises when the store cannot be read (the service fails closed)."""
        row = self.repo.get()
        return bool(row and row.locked)

    def state(self) -> dict:
        row = self.repo.get()
        if row is None:
            return {"locked": False, "changed_by": None, "changed_at": None, "reason": None}
        return {"locked": bool(row.locked), "changed_by": row.changed_by,
                "changed_at": iso(utc(row.changed_at)) if row.changed_at else None, "reason": row.reason}

    def owner_only(self, p: Principal, what: str) -> None:
        if not p.is_owner:
            self.audit.append("authz.denied", p.as_dict(), None, {"attempted": what, "reason": "permission_denied"})
            raise ApiError(403, "permission_denied", "only an owner may read or change the motion lockout")

    def set(self, p: Principal, locked: bool, reason: str | None, via: str = "token") -> dict:
        self.owner_only(p, "set the motion lockout")
        with self._changes:
            self.repo.set(locked, p.as_dict(), self.clock(), reason)
            self.audit.append("physical.lockout.on" if locked else "physical.lockout.off", p.as_dict(), None,
                              {"reason": reason, "step_up": via})
            if self.confirm_fabric is not None:
                self.confirm_fabric(locked)
            return self.state()
