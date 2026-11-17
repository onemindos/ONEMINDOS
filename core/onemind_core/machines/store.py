# SPDX-License-Identifier: Apache-2.0
"""Machines table on the shared ledger database (docs/leap/core/PLUMBING.md §3)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base, iso
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("machines")  # version 1 = the shape below


class MachineRow(Base):
    __tablename__ = "machines_machines"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    node_id: Mapped[str] = mapped_column(String(64))
    ram_mb: Mapped[int] = mapped_column(Integer)
    cpus: Mapped[int] = mapped_column(Integer)
    disk_gb: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(12))  # creating | stopped | running | unknown
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def to_json(self) -> dict:
        return {"name": self.name, "node_id": self.node_id, "ram_mb": self.ram_mb, "cpus": self.cpus,
                "disk_gb": self.disk_gb, "state": self.state, "created_at": iso(self.created_at),
                "updated_at": iso(self.updated_at)}


class MachinesRepository(SqlRepository):
    def all(self) -> list[dict]:
        with self.db.session() as s:
            return [r.to_json() for r in s.scalars(select(MachineRow).order_by(MachineRow.created_at, MachineRow.name))]

    def get(self, name: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(MachineRow, name)
            return row.to_json() if row else None

    def add(self, row: MachineRow) -> bool:
        """False when the name is taken (primary key)."""
        with self.db.session.begin() as s:
            if s.get(MachineRow, row.name) is not None:
                return False
            s.add(row)
            return True

    def set_state(self, name: str, state: str, now: datetime, *, only_from: tuple[str, ...] | None = None) -> bool:
        with self.db.session.begin() as s:
            q = update(MachineRow).where(MachineRow.name == name)
            if only_from:
                q = q.where(MachineRow.state.in_(only_from))
            return s.execute(q.values(state=state, updated_at=now)).rowcount == 1

    def remove(self, name: str, *, only_state: str | None = None) -> None:
        with self.db.session.begin() as s:
            q = delete(MachineRow).where(MachineRow.name == name)
            if only_state:
                q = q.where(MachineRow.state == only_state)
            s.execute(q)
