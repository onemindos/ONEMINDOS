# SPDX-License-Identifier: Apache-2.0
"""Tables of the appstore feature (docs/leap/core/PLUMBING.md §3): settings values, exposure
tiers, community sources and their on-box scan records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base, utc
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("appstore")  # version 1 = the shapes below


class SettingsRow(Base):
    __tablename__ = "appstore_settings"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExposureRow(Base):
    __tablename__ = "appstore_exposure"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    tier: Mapped[str] = mapped_column(String(16))
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceRow(Base):
    __tablename__ = "appstore_sources"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)
    url: Mapped[str] = mapped_column(String(500))
    commit: Mapped[str] = mapped_column(String(40))
    added_by: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class SourceScanRow(Base):
    __tablename__ = "appstore_source_scans"
    source_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    commit: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    result: Mapped[str] = mapped_column(String(8))
    checks: Mapped[dict] = mapped_column(JSON)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    commit: str
    added_by: str
    added_at: datetime
    updated_at: datetime
    action_id: str | None


@dataclass(frozen=True)
class SourceScan:
    source_id: str
    commit: str
    app_id: str
    result: str
    checks: dict
    scanned_at: datetime


def _source(r: SourceRow) -> Source:
    return Source(r.id, r.name, r.url, r.commit, r.added_by, utc(r.added_at), utc(r.updated_at), r.action_id)


class AppStoreRepository(SqlRepository):
    # ---- settings -------------------------------------------------------------------------------
    def get_settings(self, app_id: str) -> tuple[dict, str | None, datetime | None]:
        with self.db.session() as s:
            r = s.get(SettingsRow, app_id)
            return (dict(r.data), r.action_id, utc(r.updated_at)) if r else ({}, None, None)

    def set_settings(self, app_id: str, values: dict, action_id: str | None, now: datetime) -> None:
        row = {"data": values, "action_id": action_id, "updated_at": now}
        with self.db.session.begin() as s:
            s.execute(
                self.db.insert()(SettingsRow).values(app_id=app_id, **row)
                .on_conflict_do_update(index_elements=[SettingsRow.app_id], set_=row)
            )

    # ---- exposure -------------------------------------------------------------------------------
    def get_exposure(self, app_id: str) -> tuple[str, str | None, datetime | None]:
        with self.db.session() as s:
            r = s.get(ExposureRow, app_id)
            return (r.tier, r.action_id, utc(r.updated_at)) if r else ("private", None, None)

    def set_exposure(self, app_id: str, tier: str, action_id: str | None, now: datetime) -> None:
        with self.db.session.begin() as s:
            if tier == "private" and action_id is None:
                s.execute(delete(ExposureRow).where(ExposureRow.app_id == app_id))
                return
            row = {"tier": tier, "action_id": action_id, "updated_at": now}
            s.execute(
                self.db.insert()(ExposureRow).values(app_id=app_id, **row)
                .on_conflict_do_update(index_elements=[ExposureRow.app_id], set_=row)
            )

    # ---- sources --------------------------------------------------------------------------------
    def list_sources(self) -> list[Source]:
        with self.db.session() as s:
            return [_source(r) for r in s.scalars(select(SourceRow).order_by(SourceRow.name))]

    def get_source(self, source_id: str) -> Source | None:
        with self.db.session() as s:
            r = s.get(SourceRow, source_id)
            return _source(r) if r else None

    def source_by_name(self, name: str) -> Source | None:
        with self.db.session() as s:
            r = s.scalars(select(SourceRow).where(SourceRow.name == name)).first()
            return _source(r) if r else None

    def add_source(self, src: Source) -> bool:
        """Insert; False when the name is already taken (a concurrent source.add won)."""
        with self.db.session.begin() as s:
            res = s.execute(
                self.db.insert()(SourceRow).values(
                    id=src.id, name=src.name, url=src.url, commit=src.commit, added_by=src.added_by,
                    added_at=src.added_at, updated_at=src.updated_at, action_id=src.action_id,
                ).on_conflict_do_nothing().returning(SourceRow.id)
            )
            return res.first() is not None

    def move_source(self, source_id: str, commit: str, action_id: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            r = s.get(SourceRow, source_id)
            if r is not None:
                r.commit, r.action_id, r.updated_at = commit, action_id, now

    def remove_source(self, source_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(SourceScanRow).where(SourceScanRow.source_id == source_id))
            s.execute(delete(SourceRow).where(SourceRow.id == source_id))

    # ---- on-box scan records --------------------------------------------------------------------
    def put_scan(self, scan: SourceScan) -> None:
        row = {"result": scan.result, "checks": scan.checks, "scanned_at": scan.scanned_at}
        with self.db.session.begin() as s:
            s.execute(
                self.db.insert()(SourceScanRow)
                .values(source_id=scan.source_id, commit=scan.commit, app_id=scan.app_id, **row)
                .on_conflict_do_update(
                    index_elements=[SourceScanRow.source_id, SourceScanRow.commit, SourceScanRow.app_id], set_=row,
                )
            )

    def scans_for(self, source_id: str, commit: str) -> dict[str, SourceScan]:
        with self.db.session() as s:
            rows = s.scalars(
                select(SourceScanRow).where(SourceScanRow.source_id == source_id, SourceScanRow.commit == commit)
            )
            return {
                r.app_id: SourceScan(r.source_id, r.commit, r.app_id, r.result, dict(r.checks), utc(r.scanned_at))
                for r in rows
            }
