# SPDX-License-Identifier: Apache-2.0
"""Tables of the app secret store (feature `secrets`, docs/leap/core/PLUMBING.md §3).

- `secrets_values`: the current value of each (app, Secret, key), AES-256-GCM ciphertext only.
- `secrets_staged`: values an owner entered for an `app.configure` action that is not decided
  yet. They become current only when that action is approved; a denied or expired action's rows
  are purged.

No column ever holds a plaintext value. `fingerprint` is a keyed HMAC tag (crypto.StoreKey).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema, SqlRepository

SCHEMA = FeatureSchema("secrets")


class SecretValueRow(Base):
    __tablename__ = "secrets_values"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    name: Mapped[str] = mapped_column(String(253), primary_key=True)
    key: Mapped[str] = mapped_column(String(253), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(16))  # owner | generated
    fingerprint: Mapped[str] = mapped_column(String(40))
    action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StagedSecretRow(Base):
    __tablename__ = "secrets_staged"
    action_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(253), primary_key=True)
    key: Mapped[str] = mapped_column(String(253), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(59), index=True)
    op: Mapped[str] = mapped_column(String(16))  # set | generate | clear
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class StoredValue:
    """One encrypted value as read from the database (still ciphertext)."""

    name: str
    key: str
    ciphertext: bytes
    nonce: bytes
    key_id: str
    version: int
    source: str
    fingerprint: str
    updated_at: datetime
    updated_by: str | None


@dataclass(frozen=True)
class StagedValue:
    name: str
    key: str
    op: str
    ciphertext: bytes | None
    nonce: bytes | None
    key_id: str | None
    fingerprint: str | None


@dataclass(frozen=True)
class NewValue:
    """A value to write: ciphertext made for `version` by the service."""

    name: str
    key: str
    ciphertext: bytes
    nonce: bytes
    key_id: str
    version: int
    source: str
    fingerprint: str


class SecretsRepository(SqlRepository):
    def current(self, app_id: str) -> dict[tuple[str, str], StoredValue]:
        with self.db.session() as s:
            rows = s.scalars(select(SecretValueRow).where(SecretValueRow.app_id == app_id)).all()
        return {
            (r.name, r.key): StoredValue(r.name, r.key, r.ciphertext, r.nonce, r.key_id, r.version, r.source,
                                         r.fingerprint, r.updated_at, r.updated_by)
            for r in rows
        }

    def stage(self, action_id: str, app_id: str, rows: list[StagedValue], by: str, now: datetime) -> None:
        with self.db.session.begin() as s:
            for v in rows:
                s.add(StagedSecretRow(
                    action_id=action_id, name=v.name, key=v.key, app_id=app_id, op=v.op,
                    ciphertext=v.ciphertext, nonce=v.nonce, key_id=v.key_id, fingerprint=v.fingerprint,
                    created_by=by, created_at=now,
                ))

    def staged(self, action_id: str) -> list[StagedValue]:
        with self.db.session() as s:
            rows = s.scalars(select(StagedSecretRow).where(StagedSecretRow.action_id == action_id)).all()
        return [StagedValue(r.name, r.key, r.op, r.ciphertext, r.nonce, r.key_id, r.fingerprint) for r in rows]

    def staged_action_ids(self) -> set[str]:
        with self.db.session() as s:
            return set(s.scalars(select(StagedSecretRow.action_id).distinct()).all())

    def drop_staged(self, action_ids: set[str]) -> int:
        if not action_ids:
            return 0
        with self.db.session.begin() as s:
            res = s.execute(delete(StagedSecretRow).where(StagedSecretRow.action_id.in_(action_ids)))
            return res.rowcount or 0

    def commit(
        self, app_id: str, writes: list[NewValue], clears: list[tuple[str, str]], action_id: str,
        by: str | None, now: datetime,
    ) -> None:
        """Write new current values, remove cleared ones and drop the action's staged rows, in one transaction."""
        with self.db.session.begin() as s:
            for name, key in clears:
                s.execute(delete(SecretValueRow).where(
                    SecretValueRow.app_id == app_id, SecretValueRow.name == name, SecretValueRow.key == key))
            for v in writes:
                row = s.get(SecretValueRow, (app_id, v.name, v.key))
                if row is None:
                    row = SecretValueRow(app_id=app_id, name=v.name, key=v.key)
                    s.add(row)
                row.ciphertext, row.nonce, row.key_id = v.ciphertext, v.nonce, v.key_id
                row.version, row.source, row.fingerprint = v.version, v.source, v.fingerprint
                row.action_id, row.updated_by, row.updated_at = action_id, by, now
            s.execute(delete(StagedSecretRow).where(StagedSecretRow.action_id == action_id))
