# SPDX-License-Identifier: Apache-2.0
"""Migration tables (feature "migrate", docs/leap/core/PLUMBING.md §3).

- migrate_plans: one per namespace read, with its report, mapping and bundle hash.
- migrate_copies: one per volume copied (warm while the old app runs, final at switch-over).
- migrate_repo_users: short-lived restic REST users of a plan's repository. Only the sha256
  of each password is stored; they are revoked when the action that issued them ends.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base, iso, utc
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("migrate")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    """A prefixed ULID (contract §12.1): 48-bit milliseconds + 80 random bits, Crockford base32."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"


class MigratePlanRow(Base):
    __tablename__ = "migrate_plans"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(80))
    namespace: Mapped[str] = mapped_column(String(63))
    state: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[dict] = mapped_column(JSON)
    report: Mapped[dict] = mapped_column(JSON)
    bundle_sha256: Mapped[str] = mapped_column(String(80))
    busy_action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    old_replicas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MigrateCopyRow(Base):
    __tablename__ = "migrate_copies"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(40), index=True)
    action_id: Mapped[str] = mapped_column(String(36))
    pvc: Mapped[str] = mapped_column(String(253))
    phase: Mapped[str] = mapped_column(String(8))  # warm | final
    state: Mapped[str] = mapped_column(String(16))  # running | verified | mismatch | failed
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    files: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_files: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    manifest_sha256: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MigrateRepoUserRow(Base):
    __tablename__ = "migrate_repo_users"
    username: Mapped[str] = mapped_column(String(40), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(40), index=True)
    action_id: Mapped[str] = mapped_column(String(36), index=True)
    secret_sha256: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(1))  # w: read + append; r: read only
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


PLAN_STATES = ("planned", "staged", "running", "switched", "superseded")


def plan_json(r: MigratePlanRow, copies: list[dict] | None = None) -> dict:
    return {
        "id": r.id, "app_id": r.app_id, "name": r.name, "namespace": r.namespace, "state": r.state,
        "source": r.source, "bundle_sha256": r.bundle_sha256, "report": r.report,
        "busy_action_id": r.busy_action_id, "old_replicas": r.old_replicas, "last_error": r.last_error,
        "created_by": r.created_by, "created_at": iso(r.created_at), "updated_at": iso(r.updated_at),
        **({"copies": copies} if copies is not None else {}),
    }


def copy_json(r: MigrateCopyRow) -> dict:
    return {
        "id": r.id, "action_id": r.action_id, "pvc": r.pvc, "phase": r.phase, "state": r.state,
        "snapshot_id": r.snapshot_id, "files": r.files, "failed_files": r.failed_files, "bytes": r.bytes,
        "manifest_sha256": r.manifest_sha256, "error": r.error,
        "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
    }


class MigrateStore(SqlRepository):
    # ---- plans ---------------------------------------------------------------------------
    def add_plan(self, row: MigratePlanRow) -> None:
        with self.db.session.begin() as s:
            # A newer plan for the same app replaces older ones that were never imported.
            s.execute(
                update(MigratePlanRow)
                .where(MigratePlanRow.app_id == row.app_id, MigratePlanRow.state == "planned")
                .values(state="superseded", updated_at=row.created_at)
            )
            s.add(row)

    def get_plan(self, plan_id: str) -> MigratePlanRow | None:
        with self.db.session() as s:
            return s.get(MigratePlanRow, plan_id)

    def list_plans(self) -> list[MigratePlanRow]:
        with self.db.session() as s:
            return list(s.scalars(select(MigratePlanRow).order_by(MigratePlanRow.created_at.desc())))

    def active_for_app(self, app_id: str) -> MigratePlanRow | None:
        """The plan that owns app_id on the box (imported and not superseded), if any."""
        with self.db.session() as s:
            return s.scalars(
                select(MigratePlanRow).where(
                    MigratePlanRow.app_id == app_id, MigratePlanRow.state.in_(("staged", "running", "switched"))
                )
            ).first()

    def update_plan(self, plan_id: str, now: datetime, **fields) -> None:
        with self.db.session.begin() as s:
            s.execute(update(MigratePlanRow).where(MigratePlanRow.id == plan_id).values(updated_at=now, **fields))

    def claim(self, plan_id: str, action_id: str, now: datetime) -> bool:
        """Compare-and-swap: one running action per plan."""
        with self.db.session.begin() as s:
            res = s.execute(
                update(MigratePlanRow)
                .where(MigratePlanRow.id == plan_id, MigratePlanRow.busy_action_id.is_(None))
                .values(busy_action_id=action_id, updated_at=now)
            )
            return res.rowcount == 1

    def release(self, plan_id: str, action_id: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(
                update(MigratePlanRow)
                .where(MigratePlanRow.id == plan_id, MigratePlanRow.busy_action_id == action_id)
                .values(busy_action_id=None, updated_at=now)
            )

    def busy_plans(self) -> list[MigratePlanRow]:
        with self.db.session() as s:
            return list(s.scalars(select(MigratePlanRow).where(MigratePlanRow.busy_action_id.is_not(None))))

    # ---- copies ------------------------------------------------------------------------------
    def add_copy(self, row: MigrateCopyRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def finish_copy(self, copy_id: str, now: datetime, **fields) -> None:
        with self.db.session.begin() as s:
            s.execute(update(MigrateCopyRow).where(MigrateCopyRow.id == copy_id).values(finished_at=now, **fields))

    def copies(self, plan_id: str) -> list[MigrateCopyRow]:
        with self.db.session() as s:
            return list(s.scalars(
                select(MigrateCopyRow).where(MigrateCopyRow.plan_id == plan_id).order_by(MigrateCopyRow.started_at)
            ))

    def fail_running_copies(self, now: datetime, reason: str) -> int:
        with self.db.session.begin() as s:
            res = s.execute(
                update(MigrateCopyRow).where(MigrateCopyRow.state == "running")
                .values(state="failed", error=reason, finished_at=now)
            )
            return res.rowcount

    # ---- restic REST users ----------------------------------------------------------------------
    def add_user(self, username: str, plan_id: str, action_id: str, secret: str, mode: str, expires_at: datetime) -> None:
        with self.db.session.begin() as s:
            s.add(MigrateRepoUserRow(
                username=username, plan_id=plan_id, action_id=action_id, mode=mode, expires_at=expires_at,
                secret_sha256=hashlib.sha256(secret.encode()).hexdigest(), revoked=False,
            ))

    def check_user(self, username: str, secret: str, plan_id: str, now: datetime) -> str | None:
        """The user's mode ("w" or "r") if the credentials are valid for this plan right now."""
        with self.db.session() as s:
            row = s.get(MigrateRepoUserRow, username)
        given = hashlib.sha256(secret.encode()).hexdigest()
        if row is None or not hmac.compare_digest(row.secret_sha256, given):
            return None
        if row.revoked or row.plan_id != plan_id or utc(row.expires_at) <= now:
            return None
        return row.mode

    def revoke_users(self, action_id: str) -> None:
        with self.db.session.begin() as s:
            s.execute(update(MigrateRepoUserRow).where(MigrateRepoUserRow.action_id == action_id).values(revoked=True))
