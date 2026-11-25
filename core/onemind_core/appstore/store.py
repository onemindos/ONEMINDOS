# SPDX-License-Identifier: Apache-2.0
"""Tables of the appstore feature (docs/leap/core/PLUMBING.md §3): settings values, exposure
tiers, community sources and their on-box scan records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, and_, delete, func, select
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


class SystemDisabledRow(Base):
    """A system app the owner switched off. The row is the switch: no row, the app is on. Volumes,
    secrets and settings are other tables and objects and are never touched by a disable."""
    __tablename__ = "appstore_system_disabled"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    prior_status: Mapped[str] = mapped_column(String(16))  # installed | stopped | not_installed
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    disabled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class CustomAppRow(Base):
    """A custom app: one Git repository an owner linked (PLG-GIT-01). The row is the app; its history is
    appstore_custom_revisions. current_revision is what the catalog serves (null: nothing passed yet);
    deployed_revision is what an approved install or update last put on the box."""
    __tablename__ = "appstore_custom_apps"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    ref: Mapped[str] = mapped_column(String(100))
    added_by: Mapped[str] = mapped_column(String(200))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deployed_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CustomRevisionRow(Base):
    __tablename__ = "appstore_custom_revisions"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    commit: Mapped[str] = mapped_column(String(40))
    ref: Mapped[str] = mapped_column(String(100))
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_sha: Mapped[str] = mapped_column(String(64))
    scan_result: Mapped[str] = mapped_column(String(8))
    scan_checks: Mapped[dict] = mapped_column(JSON)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


@dataclass(frozen=True)
class CustomApp:
    app_id: str
    url: str
    ref: str
    added_by: str
    added_at: datetime
    current_revision: int | None
    deployed_revision: int | None


@dataclass(frozen=True)
class CustomRevision:
    app_id: str
    revision: int
    commit: str
    ref: str
    version: str | None
    manifest_sha: str
    scan_result: str
    scan_checks: dict
    scanned_at: datetime
    created_by: str
    created_at: datetime
    deployed_at: datetime | None
    action_id: str | None


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


def _custom(r: CustomAppRow) -> CustomApp:
    return CustomApp(r.app_id, r.url, r.ref, r.added_by, utc(r.added_at), r.current_revision, r.deployed_revision)


def _revision(r: CustomRevisionRow) -> CustomRevision:
    return CustomRevision(r.app_id, r.revision, r.commit, r.ref, r.version, r.manifest_sha, r.scan_result,
                          dict(r.scan_checks), utc(r.scanned_at), r.created_by, utc(r.created_at),
                          utc(r.deployed_at) if r.deployed_at else None, r.action_id)


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

    # ---- system apps switched off ------------------------------------------------------------------
    def disabled(self) -> dict[str, tuple[str, str | None, datetime]]:
        """app id -> (prior status, action id, when) for every switched-off system app."""
        with self.db.session() as s:
            return {r.app_id: (r.prior_status, r.action_id, utc(r.disabled_at))
                    for r in s.scalars(select(SystemDisabledRow))}

    def set_disabled(self, app_id: str, prior_status: str, action_id: str | None, now: datetime) -> None:
        row = {"prior_status": prior_status, "action_id": action_id, "disabled_at": now}
        with self.db.session.begin() as s:
            s.execute(
                self.db.insert()(SystemDisabledRow).values(app_id=app_id, **row)
                .on_conflict_do_update(index_elements=[SystemDisabledRow.app_id], set_=row)
            )

    def clear_disabled(self, app_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(SystemDisabledRow).where(SystemDisabledRow.app_id == app_id))

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

    # ---- custom apps (PLG-GIT-01) -----------------------------------------------------------------
    def list_custom(self) -> list[CustomApp]:
        with self.db.session() as s:
            return [_custom(r) for r in s.scalars(select(CustomAppRow).order_by(CustomAppRow.app_id))]

    def get_custom(self, app_id: str) -> CustomApp | None:
        with self.db.session() as s:
            r = s.get(CustomAppRow, app_id)
            return _custom(r) if r else None

    def custom_current(self) -> list[tuple[CustomApp, CustomRevision]]:
        """Every custom app with the revision the catalog serves (one query: the catalog loads often)."""
        with self.db.session() as s:
            rows = s.execute(
                select(CustomAppRow, CustomRevisionRow).join(
                    CustomRevisionRow, and_(CustomRevisionRow.app_id == CustomAppRow.app_id,
                                            CustomRevisionRow.revision == CustomAppRow.current_revision))
                .order_by(CustomAppRow.app_id))
            return [(_custom(a), _revision(r)) for a, r in rows]

    def custom_revisions(self, app_id: str) -> list[CustomRevision]:
        with self.db.session() as s:
            rows = s.scalars(select(CustomRevisionRow).where(CustomRevisionRow.app_id == app_id)
                             .order_by(CustomRevisionRow.revision))
            return [_revision(r) for r in rows]

    def add_custom_revision(self, app_id: str, url: str, ref: str, rev: CustomRevision, serve: bool) -> CustomRevision:
        """Record a revision under the next number; the app row is created by the first one. `serve`
        points the catalog at it (only a revision that passed its scan is served)."""
        with self.db.session.begin() as s:
            row = s.get(CustomAppRow, app_id)
            if row is None:
                row = CustomAppRow(app_id=app_id, url=url, ref=ref, added_by=rev.created_by, added_at=rev.created_at,
                                   current_revision=None, deployed_revision=None)
                s.add(row)
            top = s.scalar(select(func.max(CustomRevisionRow.revision)).where(CustomRevisionRow.app_id == app_id)) or 0
            n = top + 1
            s.add(CustomRevisionRow(
                app_id=app_id, revision=n, commit=rev.commit, ref=rev.ref, version=rev.version, manifest_sha=rev.manifest_sha,
                scan_result=rev.scan_result, scan_checks=rev.scan_checks, scanned_at=rev.scanned_at,
                created_by=rev.created_by, created_at=rev.created_at, deployed_at=None, action_id=None))
            row.ref = ref
            if serve:
                row.current_revision = n
            return CustomRevision(**{**rev.__dict__, "revision": n})

    def rescan_custom_revision(self, app_id: str, revision: int, result: str, checks: dict, now: datetime) -> None:
        with self.db.session.begin() as s:
            r = s.get(CustomRevisionRow, (app_id, revision))
            if r is not None:
                r.scan_result, r.scan_checks, r.scanned_at = result, checks, now

    def set_custom_current(self, app_id: str, revision: int) -> None:
        with self.db.session.begin() as s:
            r = s.get(CustomAppRow, app_id)
            if r is not None:
                r.current_revision = revision

    def mark_custom_deployed(self, app_id: str, revision: int, action_id: str | None, now: datetime) -> None:
        with self.db.session.begin() as s:
            r = s.get(CustomAppRow, app_id)
            rev = s.get(CustomRevisionRow, (app_id, revision))
            if r is not None and rev is not None:
                r.deployed_revision = revision
                rev.deployed_at, rev.action_id = now, action_id

    def remove_custom(self, app_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(delete(CustomRevisionRow).where(CustomRevisionRow.app_id == app_id))
            s.execute(delete(CustomAppRow).where(CustomAppRow.app_id == app_id))
