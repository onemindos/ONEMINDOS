# SPDX-License-Identifier: Apache-2.0
"""Identity tables (feature "identity", docs/leap/core/PLUMBING.md §3) and their repository."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import JSON, Boolean, DateTime, Integer, LargeBinary, String, func, select, text, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from ..ledger import Base
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("identity")  # v1 = the shape below
OWNER_PASSKEY_SEEN = "owner_passkey_seen"
PROVEN_SEEN = "proven_key_seen"


@SCHEMA.step(2, "profile_name: the optional name a person chose, shown on Home")
def _identity_v2(conn) -> None:
    from sqlalchemy import inspect, text

    if "profile_name" not in {c["name"] for c in inspect(conn).get_columns("identity_users")}:
        conn.execute(text("ALTER TABLE identity_users ADD COLUMN profile_name VARCHAR(60)"))


@SCHEMA.step(3, "install_id: the random id one app install sends, so My devices groups its sign-ins and passkeys (#715)")
def _identity_v3(conn) -> None:
    from sqlalchemy import inspect, text

    for table in ("identity_sessions", "identity_passkeys"):
        if "install_id" not in {c["name"] for c in inspect(conn).get_columns(table)}:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN install_id VARCHAR(64)"))


# Design 3.11 / D-028: what a passkey proved at enrolment, and which credential stepped a session up.
_V4_PASSKEY = {"aaguid": "VARCHAR(36)", "att_fmt": "VARCHAR(24)", "att_chain_sha256": "VARCHAR(71)",
               "backup_eligible": "BOOLEAN", "backed_up": "BOOLEAN", "level": "VARCHAR(2)",
               "level_reason": "VARCHAR(32)", "model": "VARCHAR(100)"}


@SCHEMA.step(4, "verification levels: passkey attestation facts and level; the session's step-up credential")
def _identity_v4(conn) -> None:
    from sqlalchemy import inspect, text

    have = {c["name"] for c in inspect(conn).get_columns("identity_passkeys")}
    for col, typ in _V4_PASSKEY.items():
        if col not in have:
            conn.execute(text(f"ALTER TABLE identity_passkeys ADD COLUMN {col} {typ}"))
    if "step_up_credential_id" not in {c["name"] for c in inspect(conn).get_columns("identity_sessions")}:
        conn.execute(text("ALTER TABLE identity_sessions ADD COLUMN step_up_credential_id VARCHAR(512)"))


@SCHEMA.step(5, "D-034 setup, password recovery and second-factor sessions")
def _identity_v5(conn) -> None:
    from sqlalchemy import inspect, text

    for table, columns in {
        "identity_users": {"setup_pending": "BOOLEAN", "recovery_hash": "VARCHAR(64)",
                           "email": "VARCHAR(254)", "email_verified_at": "TIMESTAMP WITH TIME ZONE",
                           "credential_revision": "INTEGER"},
        "identity_sessions": {"totp_at": "TIMESTAMP WITH TIME ZONE", "credential_revision": "INTEGER"},
    }.items():
        have = {c["name"] for c in inspect(conn).get_columns(table)}
        for column, kind in columns.items():
            if column not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {kind}"))


@SCHEMA.step(6, "remember completed owner passkey setup")
def _identity_v6(conn) -> None:
    # Disabled owners retain their keys. An existing grace latch also proves setup ended,
    # even if all owners' credentials have been removed.
    conn.execute(text("""
        INSERT INTO identity_household_flags (key, set_at, detail)
        SELECT :flag, CURRENT_TIMESTAMP, 'existing owner passkey history'
        WHERE EXISTS (
            SELECT 1 FROM identity_passkeys AS p JOIN identity_users AS u ON u.id = p.user_id
            WHERE u.role = 'owner'
        ) OR EXISTS (SELECT 1 FROM identity_household_flags WHERE key = :proven)
        ON CONFLICT (key) DO NOTHING
    """), {"flag": OWNER_PASSKEY_SEEN, "proven": PROVEN_SEEN})


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
    # What the person chose to be called ("Good afternoon, Ana"). Display text only: null until set, never
    # used for authorisation or audit (those use `id` and `role`). Added in identity schema v2.
    profile_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # TOTP secrets must be readable to check a code; protected by the data-disk encryption (H-11).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_pending: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_last_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setup_pending: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    recovery_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    credential_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    install_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # #715, see devices/service.py
    # Verification levels (schema v4, levels.py). Rows from before v4 have nulls and count as L1.
    aaguid: Mapped[str | None] = mapped_column(String(36), nullable=True)  # the model, never the person
    att_fmt: Mapped[str | None] = mapped_column(String(24), nullable=True)
    att_chain_sha256: Mapped[str | None] = mapped_column(String(71), nullable=True)
    backup_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # BE: may sync
    backed_up: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # BS: is synced
    level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    level_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)


class VerificationLevelRow(Base):
    """An owner edit of the verification table (levels.ROWS or type:<action type>); absent = default."""

    __tablename__ = "identity_verification_levels"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[str] = mapped_column(String(2))
    updated_at: Mapped[datetime] = mapped_column(TS)
    updated_by: Mapped[str] = mapped_column(String(100))
    action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TrustedModelRow(Base):
    """An authenticator model an owner added to the allow-list (beside the shipped file)."""

    __tablename__ = "identity_trusted_models"
    aaguid: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    roots: Mapped[list] = mapped_column(JSON, default=list)  # PEM strings
    user_verification: Mapped[list] = mapped_column(JSON, default=list)
    added_at: Mapped[datetime] = mapped_column(TS)
    added_by: Mapped[str] = mapped_column(String(100))
    action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class HouseholdFlagRow(Base):
    """One-way household facts (design 3.11): owner passkey setup ended, or an owner held a proven key."""

    __tablename__ = "identity_household_flags"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    set_at: Mapped[datetime] = mapped_column(TS)
    detail: Mapped[str] = mapped_column(String(200), default="")


class ApproverKeyRow(Base):
    """#702: a phone's device-bound P-256 approver key. Revoked rows stay, so the audit can name them."""

    __tablename__ = "identity_approver_keys"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # apk_<ulid>
    user_id: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(100))  # the phone, as the owner named it
    key_kind: Mapped[str] = mapped_column(String(24))  # approver_keys.KEY_KINDS
    public_key: Mapped[bytes] = mapped_column(LargeBinary)  # SubjectPublicKeyInfo DER
    fingerprint: Mapped[str] = mapped_column(String(80), unique=True)  # sha256:<hex> of the DER
    created_at: Mapped[datetime] = mapped_column(TS)
    last_used_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


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
    totp_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    credential_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_up_credential_id: Mapped[str | None] = mapped_column(String(512), nullable=True)  # who set passkey_at
    created_at: Mapped[datetime] = mapped_column(TS)
    last_seen_at: Mapped[datetime] = mapped_column(TS)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    install_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # #715, see devices/service.py


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


class RemoteRecoveryRow(Base):
    __tablename__ = "identity_remote_recovery"
    user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(40))
    credential_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_at: Mapped[datetime] = mapped_column(TS)
    expires_at: Mapped[datetime] = mapped_column(TS)


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

    @contextmanager
    def lock_household(self) -> Iterator[Session]:
        """Serialise writes that establish an owner passkey or change model trust."""
        with self.db.session.begin() as s:
            if self.db.engine.dialect.name == "sqlite":
                s.execute(text("BEGIN IMMEDIATE"))  # SQLite has no SELECT FOR UPDATE
            else:
                # One identity household per database. Acquire its transaction lock before the user row.
                s.execute(text("SELECT pg_advisory_xact_lock(:namespace, 1)"), {"namespace": 0x4F4D4944})  # OMID
            yield s

    @contextmanager
    def lock_user(self, user_id: str) -> Iterator[tuple[Session, UserRow | None]]:
        with self.lock_household() as s:
            yield s, s.get(UserRow, user_id, with_for_update=True)

    def set_household_flag(self, session: Session, key: str, now: datetime, detail: str) -> bool:
        stmt = self.db.insert()(HouseholdFlagRow).values(key=key, set_at=now, detail=detail[:200])
        return session.scalar(stmt.on_conflict_do_nothing().returning(HouseholdFlagRow.key)) is not None

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
