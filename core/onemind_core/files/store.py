# SPDX-License-Identifier: Apache-2.0
"""FILES tables (feature `files`, docs/leap/core/PLUMBING.md §3) and their repository.

files_spaces    one row per person whose Home exists (person id -> directory name)
files_quotas    owner-set per-person limits (absent = the default from settings)
files_trash     items moved to a person's trash, until restored or purged
files_uploads   resumable uploads (tus) in progress or finished
files_requests  action-shaped records for changes that need an owner approval
                (folder grants, emptying a trash): awaiting_approval -> succeeded | failed |
                cancelled | expired
files_grants    approved folder grants to an app or an agent; revoked_at set when removed
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Index, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base, utc
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("files")

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str) -> str:
    """A prefixed ULID (contract §12.1): 48-bit milliseconds + 80 random bits, Crockford base32."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(secrets.token_bytes(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"


class SpaceRow(Base):
    __tablename__ = "files_spaces"
    person_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    dir_name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class QuotaRow(Base):
    __tablename__ = "files_quotas"
    person_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # None = no limit
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str] = mapped_column(String(200))


class TrashRow(Base):
    __tablename__ = "files_trash"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    person_id: Mapped[str] = mapped_column(String(200), index=True)  # whose trash
    root: Mapped[str] = mapped_column(String(220))                    # where it came from
    path: Mapped[str] = mapped_column(String(4200))
    kind: Mapped[str] = mapped_column(String(8))                     # file | dir
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    trashed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trashed_by: Mapped[str] = mapped_column(String(200))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UploadRow(Base):
    __tablename__ = "files_uploads"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(200), index=True)
    root: Mapped[str] = mapped_column(String(220))
    dir_path: Mapped[str] = mapped_column(String(4200))
    name: Mapped[str] = mapped_column(String(1024))
    length: Mapped[int] = mapped_column(BigInteger)
    received: Mapped[int] = mapped_column(BigInteger)  # bytes stored so far (the tus offset)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overwrite: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(16))  # open | done | failed | terminated | expired
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RequestRow(Base):
    __tablename__ = "files_requests"
    __table_args__ = (Index("ix_files_requests_idem", "requested_by_id", "idempotency_key", unique=True),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON)
    plan: Mapped[dict] = mapped_column(JSON)
    risk: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(24), index=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_by: Mapped[dict] = mapped_column(JSON)
    requested_by_id: Mapped[str] = mapped_column(String(200))
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body_sha256: Mapped[str] = mapped_column(String(64))
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_via: Mapped[str | None] = mapped_column(String(16), nullable=True)
    approval: Mapped[str | None] = mapped_column(String(16), nullable=True)
    deny_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GrantRow(Base):
    __tablename__ = "files_grants"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(40))
    subject_kind: Mapped[str] = mapped_column(String(8))   # app | agent
    subject_id: Mapped[str] = mapped_column(String(200), index=True)
    slot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    root: Mapped[str] = mapped_column(String(220))
    path: Mapped[str] = mapped_column(String(4200))
    access: Mapped[str] = mapped_column(String(2))        # r | rw
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str] = mapped_column(String(200))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


def _safe_dir_name(person_id: str) -> str:
    import hashlib
    import re

    if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", person_id):
        return person_id
    return "p_" + hashlib.sha256(person_id.encode("utf-8")).hexdigest()[:32]


class FilesRepository(SqlRepository):
    # ---- spaces and quotas ------------------------------------------------------------------
    def space_dir(self, person_id: str, now: datetime) -> str:
        """The Home directory name for a person, recorded on first use."""
        with self.db.session() as s:
            row = s.get(SpaceRow, person_id)
            if row is not None:
                return row.dir_name
        name = _safe_dir_name(person_id)
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(SpaceRow).values(person_id=person_id, dir_name=name, created_at=now)
                      .on_conflict_do_nothing())
        with self.db.session() as s:
            return s.get(SpaceRow, person_id).dir_name

    def spaces(self) -> dict[str, str]:
        with self.db.session() as s:
            return {r.person_id: r.dir_name for r in s.scalars(select(SpaceRow))}

    def quota(self, person_id: str) -> QuotaRow | None:
        with self.db.session() as s:
            return s.get(QuotaRow, person_id)

    def quotas(self) -> dict[str, QuotaRow]:
        with self.db.session() as s:
            return {r.person_id: r for r in s.scalars(select(QuotaRow))}

    def set_quota(self, person_id: str, limit_bytes: int | None, by: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            s.execute(self.db.insert()(QuotaRow).values(
                person_id=person_id, limit_bytes=limit_bytes, updated_at=now, updated_by=by,
            ).on_conflict_do_update(
                index_elements=[QuotaRow.person_id],
                set_={"limit_bytes": limit_bytes, "updated_at": now, "updated_by": by},
            ))

    # ---- trash ------------------------------------------------------------------------------
    def add_trash(self, row: TrashRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def trash_items(self, person_id: str | None = None, *, live: bool = True) -> list[TrashRow]:
        with self.db.session() as s:
            q = select(TrashRow)
            if person_id is not None:
                q = q.where(TrashRow.person_id == person_id)
            if live:
                q = q.where(TrashRow.purged_at.is_(None))
            return list(s.scalars(q.order_by(TrashRow.trashed_at.desc(), TrashRow.id)))

    def trash_item(self, trash_id: str) -> TrashRow | None:
        with self.db.session() as s:
            return s.get(TrashRow, trash_id)

    def trash_bytes(self, root: str) -> int:
        with self.db.session() as s:
            rows = s.scalars(select(TrashRow.size_bytes).where(TrashRow.root == root, TrashRow.purged_at.is_(None)))
            return int(sum(rows))

    def mark_trash(self, trash_id: str, now: datetime, *, purged: bool) -> bool:
        """purged=True: gone for good. purged=False: restored (the row is deleted). True if it changed."""
        with self.db.session.begin() as s:
            row = s.get(TrashRow, trash_id, with_for_update=True)
            if row is None or row.purged_at is not None:
                return False
            if purged:
                row.purged_at = now
            else:
                s.delete(row)
            return True

    # ---- uploads ----------------------------------------------------------------------------
    def add_upload(self, row: UploadRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def upload(self, upload_id: str) -> UploadRow | None:
        with self.db.session() as s:
            return s.get(UploadRow, upload_id)

    def open_uploads(self, root: str | None = None) -> list[UploadRow]:
        with self.db.session() as s:
            q = select(UploadRow).where(UploadRow.state == "open")
            if root is not None:
                q = q.where(UploadRow.root == root)
            return list(s.scalars(q))

    def update_upload(self, upload_id: str, now: datetime, *, from_states: set[str] | None = None, **fields) -> bool:
        with self.db.session.begin() as s:
            q = update(UploadRow).where(UploadRow.id == upload_id)
            if from_states:
                q = q.where(UploadRow.state.in_(from_states))
            res = s.execute(q.values(updated_at=now, **fields).returning(UploadRow.id))
            return res.first() is not None

    # ---- requests and grants ----------------------------------------------------------------
    def add_request(self, row: RequestRow) -> tuple[RequestRow, bool]:
        """Insert; on an idempotency-key clash return the existing row and False."""
        with self.db.session.begin() as s:
            res = s.execute(
                self.db.insert()(RequestRow).values(**{c.name: getattr(row, c.key) for c in RequestRow.__table__.columns})
                .on_conflict_do_nothing().returning(RequestRow.id)
            )
            inserted = res.first() is not None
        if inserted:
            return self.request(row.id), True
        return self.request_by_key(row.requested_by_id, row.idempotency_key), False

    def request(self, request_id: str) -> RequestRow | None:
        with self.db.session() as s:
            return s.get(RequestRow, request_id)

    def request_by_key(self, principal_id: str, key: str | None) -> RequestRow | None:
        if key is None:
            return None
        with self.db.session() as s:
            return s.scalars(select(RequestRow).where(
                RequestRow.requested_by_id == principal_id, RequestRow.idempotency_key == key
            )).first()

    def requests(self, requested_by_id: str | None = None) -> list[RequestRow]:
        with self.db.session() as s:
            q = select(RequestRow)
            if requested_by_id is not None:
                q = q.where(RequestRow.requested_by_id == requested_by_id)
            return list(s.scalars(q.order_by(RequestRow.created_at.desc(), RequestRow.id)))

    def pending_count(self, requested_by_id: str) -> int:
        with self.db.session() as s:
            return len(list(s.scalars(select(RequestRow.id).where(
                RequestRow.requested_by_id == requested_by_id, RequestRow.state == "awaiting_approval"
            ))))

    def transition_request(self, request_id: str, from_states: set[str], to_state: str, now: datetime, **fields) -> RequestRow | None:
        """Compare-and-swap on state, so two owners deciding at once cannot both win."""
        with self.db.session.begin() as s:
            res = s.execute(
                update(RequestRow).where(RequestRow.id == request_id, RequestRow.state.in_(from_states))
                .values(state=to_state, updated_at=now, **fields).returning(RequestRow.id)
            )
            moved = res.first() is not None
        return self.request(request_id) if moved else None

    def add_grant(self, row: GrantRow) -> None:
        with self.db.session.begin() as s:
            s.add(row)

    def grant(self, grant_id: str) -> GrantRow | None:
        with self.db.session() as s:
            return s.get(GrantRow, grant_id)

    def grants(self, *, subject_kind: str | None = None, subject_id: str | None = None, active: bool = True) -> list[GrantRow]:
        with self.db.session() as s:
            q = select(GrantRow)
            if subject_kind is not None:
                q = q.where(GrantRow.subject_kind == subject_kind)
            if subject_id is not None:
                q = q.where(GrantRow.subject_id == subject_id)
            if active:
                q = q.where(GrantRow.revoked_at.is_(None))
            return list(s.scalars(q.order_by(GrantRow.created_at, GrantRow.id)))

    def revoke_grant(self, grant_id: str, by: str, now: datetime) -> bool:
        with self.db.session.begin() as s:
            res = s.execute(
                update(GrantRow).where(GrantRow.id == grant_id, GrantRow.revoked_at.is_(None))
                .values(revoked_at=now, revoked_by=by).returning(GrantRow.id)
            )
            return res.first() is not None


def aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    return None if dt is None else utc(dt)


__all__ = [
    "SCHEMA", "FilesRepository", "GrantRow", "QuotaRow", "RequestRow", "SpaceRow", "TrashRow", "UploadRow",
    "aware", "new_id",
]
