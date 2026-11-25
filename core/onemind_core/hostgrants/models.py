# SPDX-License-Identifier: Apache-2.0
"""Host grants an owner approved: one row per (app, kind, class, path), active until revoked."""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("hostgrants")


class HostGrantRow(Base):
    __tablename__ = "hostgrants_grants"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(63), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    device_class: Mapped[str | None] = mapped_column(String(16), nullable=True)
    path: Mapped[str | None] = mapped_column(String(220), nullable=True)
    reason: Mapped[str] = mapped_column(String(300))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str] = mapped_column(String(100))
    action_id: Mapped[str] = mapped_column(String(36))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


def grant_id(app_id: str, kind: str, device_class: str | None, path: str | None) -> str:
    """The same grant always has the same id, so a re-grant after a revocation reuses its row."""
    key = "\0".join((app_id, kind, device_class or "", path or ""))
    return "hg_" + hashlib.sha256(key.encode()).hexdigest()[:32]


class HostGrantRepository(SqlRepository):
    def get(self, gid: str) -> HostGrantRow | None:
        with self.db.session() as s:
            return s.get(HostGrantRow, gid)

    def list(self, app_id: str | None = None, active_only: bool = False) -> list[HostGrantRow]:
        q = select(HostGrantRow)
        if app_id is not None:
            q = q.where(HostGrantRow.app_id == app_id)
        if active_only:
            q = q.where(HostGrantRow.active.is_(True))
        with self.db.session() as s:
            return list(s.scalars(q.order_by(HostGrantRow.app_id, HostGrantRow.granted_at, HostGrantRow.id)))

    def activate(self, values: dict) -> bool:
        """Insert the grant, or turn a revoked row back on. False when it is already active."""
        with self.db.session.begin() as s:
            changed = s.execute(self.db.insert()(HostGrantRow).values(**values).on_conflict_do_update(
                index_elements=[HostGrantRow.id], set_=values, where=HostGrantRow.active.is_(False),
            ).returning(HostGrantRow.id)).first()
        return changed is not None

    def revoke(self, gid: str, by: str, now: datetime) -> bool:
        with self.db.session.begin() as s:
            changed = s.execute(update(HostGrantRow).where(HostGrantRow.id == gid, HostGrantRow.active.is_(True))
                                .values(active=False, revoked_at=now, revoked_by=by)
                                .returning(HostGrantRow.id)).first()
        return changed is not None
