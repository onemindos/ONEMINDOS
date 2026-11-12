# SPDX-License-Identifier: Apache-2.0
"""Identity tables (feature "identity", docs/leap/core/PLUMBING.md §3) and their repository."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import JSON, Boolean, DateTime, Integer, LargeBinary, String, func, select, update
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("identity")  # v1 = the shape below

T = TypeVar("T", bound=Base)


def utc(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; everything here is UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def iso(dt: datetime | None) -> str | None:
    dt = utc(dt)
    return dt.isoformat().replace("+00:00", "Z") if dt else None


TS = DateTime(timezone=True)


class UserRow(Base):
    __tablename__ = "identity_users"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # TOTP secrets must be readable to check a code; protected by the data-disk encryption (H-11).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_pending: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_last_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrol_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    enrol_expires_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)
    last_seen_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)


class PasskeyRow(Base):
    __tablename__ = "identity_passkeys"
    id: Mapped[str] = mapped_column(String(512), primary_key=True)  # credential id, base64url
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(100))
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(TS)
    last_used_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class SessionRow(Base):
    __tablename__ = "identity_sessions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    transport: Mapped[str] = mapped_column(String(8))  # cookie | bearer
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    refresh_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    access_expires_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    client: Mapped[str] = mapped_column(String(200))
    auth_method: Mapped[str] = mapped_column(String(32))
    passkey_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS)
    last_seen_at: Mapped[datetime] = mapped_column(TS)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class TokenRow(Base):
    __tablename__ = "identity_tokens"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(100))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    prev_valid_until: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    kind: Mapped[str] = mapped_column(String(16))  # person | agent | plugin | node | automation
    principal_id: Mapped[str] = mapped_column(String(100), index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16))  # api | app-install
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TS)
    expires_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class ChallengeRow(Base):
    __tablename__ = "identity_challenges"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(16))  # register | login | approve
    challenge: Mapped[str] = mapped_column(String(128), unique=True)  # base64url
    user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(TS)
    used_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class AppAccessRow(Base):
    __tablename__ = "identity_app_access"
    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    roles: Mapped[list] = mapped_column(JSON, default=list)
    people: Mapped[list] = mapped_column(JSON, default=list)
    auth: Mapped[str] = mapped_column(String(16), default="onemind")
    updated_at: Mapped[datetime] = mapped_column(TS)
    updated_by: Mapped[str] = mapped_column(String(100))


class IdentityRepository(SqlRepository):
    """Small generic helpers; the rules live in service.py."""

    def get(self, cls: type[T], key: Any) -> T | None:
        with self.db.session() as s:
            return s.get(cls, key)

    def one(self, stmt) -> Any:
        with self.db.session() as s:
            return s.execute(stmt).scalars().first()

    def all(self, stmt) -> list[Any]:
        with self.db.session() as s:
            return list(s.execute(stmt).scalars())

    def count(self, cls: type[Base], *where) -> int:
        with self.db.session() as s:
            return s.execute(select(func.count()).select_from(cls).where(*where)).scalar_one()

    def add(self, *rows: Base) -> None:
        with self.db.session.begin() as s:
            s.add_all(rows)

    def update(self, cls: type[T], where: Iterable, values: dict, returning=None) -> list[Any]:
        """UPDATE ... WHERE ... RETURNING <pk> (rowcount is not trusted across drivers)."""
        pk = returning if returning is not None else list(cls.__table__.primary_key.columns)[0]
        with self.db.session.begin() as s:
            return list(s.execute(update(cls).where(*where).values(**values).returning(pk)).scalars())

    def delete(self, cls: type[Base], *where) -> None:
        from sqlalchemy import delete as sa_delete

        with self.db.session.begin() as s:
            s.execute(sa_delete(cls).where(*where))
