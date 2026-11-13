# SPDX-License-Identifier: Apache-2.0
"""Backups tables on the shared ledger database (docs/leap/core/PLUMBING.md §3).

Destinations, runs, restores and the emergency kit's state. Snapshots and verifications live in
the restic repositories and the agent's state; the gateway asks the agent for them. No table holds
a credential or a key: destination secrets go straight to the agent's 0600 files, the owner key
exists only in the one response that shows it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, delete, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base, iso, utc
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("backups")  # version 1 = the shape below


class DestinationRow(Base):
    __tablename__ = "backups_destinations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(8))  # usb | box | rest | s3
    label: Mapped[str] = mapped_column(String(80))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    append_only: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(JSON)  # never credentials
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunRow(Base):
    __tablename__ = "backups_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(String(16))
    destination_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    state: Mapped[str] = mapped_column(String(16))  # running | succeeded | partial | failed | refused
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    units: Mapped[list] = mapped_column(JSON)
    hooks: Mapped[list] = mapped_column(JSON)
    bytes_added: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RestoreRow(Base):
    __tablename__ = "backups_restores"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(36))
    snapshot_id: Mapped[str] = mapped_column(String(64))
    scope: Mapped[dict] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(10))
    target: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(20))
    plan: Mapped[dict] = mapped_column(JSON)
    pre_restore_snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    health_gate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    steps: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class KitRow(Base):
    __tablename__ = "backups_kit"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)  # always "kit"
    state: Mapped[str] = mapped_column(String(12))  # issued | confirmed
    fingerprint: Mapped[str] = mapped_column(String(32))
    challenge: Mapped[dict] = mapped_column(JSON)  # group indices and salted hashes, never the key
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)


def destination_json(r: DestinationRow) -> dict:
    return {"id": r.id, "kind": r.kind, "label": r.label, "primary": r.is_primary, "append_only": r.append_only,
            "config": r.config, "action_id": r.action_id, "created_at": iso(r.created_at)}


def run_json(r: RunRow) -> dict:
    return {"id": r.id, "action_id": r.action_id, "reason": r.reason, "destination_id": r.destination_id,
            "state": r.state, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
            "bytes_done": r.bytes_added, "bytes_total": None, "units": r.units, "hooks": r.hooks, "error": r.error}


def restore_json(r: RestoreRow) -> dict:
    return {"id": r.id, "action_id": r.action_id, "snapshot_id": r.snapshot_id, "scope": r.scope, "mode": r.mode,
            "target": r.target, "state": r.state, "plan": r.plan, "pre_restore_snapshot_id": r.pre_restore_snapshot_id,
            "health_gate": r.health_gate, "steps": r.steps, "created_at": iso(r.created_at),
            "started_at": iso(r.started_at), "finished_at": iso(r.finished_at), "error": r.error}


class BackupsRepository(SqlRepository):
    # destinations
    def destinations(self) -> list[DestinationRow]:
        with self.db.session() as s:
            return list(s.scalars(select(DestinationRow).order_by(DestinationRow.created_at)))

    def add_destination(self, row: DestinationRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def clear_primary(self) -> None:
        with self.db.session.begin() as s:
            s.execute(update(DestinationRow).values(is_primary=False))

    def remove_destination(self, dest_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(DestinationRow).where(DestinationRow.id == dest_id))
            first = s.scalars(select(DestinationRow).order_by(DestinationRow.created_at)).first()
            if first is not None and not s.scalars(select(DestinationRow).where(DestinationRow.is_primary.is_(True))).first():
                first.is_primary = True

    # runs
    def add_run(self, row: RunRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def update_run(self, run_id: str, **fields) -> None:
        with self.db.session.begin() as s:
            s.execute(update(RunRow).where(RunRow.id == run_id).values(**fields))

    def runs(self, limit: int = 100) -> list[RunRow]:
        with self.db.session() as s:
            return list(s.scalars(select(RunRow).order_by(RunRow.started_at.desc()).limit(limit)))

    def run(self, run_id: str) -> RunRow | None:
        with self.db.session() as s:
            return s.get(RunRow, run_id)

    def fail_unfinished_runs(self, now: datetime) -> int:
        with self.db.session.begin() as s:
            res = s.execute(update(RunRow).where(RunRow.state == "running").values(
                state="failed", finished_at=utc(now), error="the gateway restarted during the run"))
            return res.rowcount or 0

    # restores
    def add_restore(self, row: RestoreRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def update_restore(self, restore_id: str, **fields) -> None:
        with self.db.session.begin() as s:
            s.execute(update(RestoreRow).where(RestoreRow.id == restore_id).values(**fields))

    def restores(self, limit: int = 100) -> list[RestoreRow]:
        with self.db.session() as s:
            return list(s.scalars(select(RestoreRow).order_by(RestoreRow.created_at.desc()).limit(limit)))

    def restore(self, restore_id: str) -> RestoreRow | None:
        with self.db.session() as s:
            return s.get(RestoreRow, restore_id)

    def restore_for_action(self, action_id: str) -> RestoreRow | None:
        with self.db.session() as s:
            return s.scalars(select(RestoreRow).where(RestoreRow.action_id == action_id)).first()

    # kit
    def kit(self) -> KitRow | None:
        with self.db.session() as s:
            return s.get(KitRow, "kit")

    def put_kit(self, row: KitRow) -> None:
        with self.db.session.begin() as s:
            s.merge(row)

    def update_kit(self, **fields) -> None:
        with self.db.session.begin() as s:
            s.execute(update(KitRow).where(KitRow.id == "kit").values(**fields))
