# SPDX-License-Identifier: Apache-2.0
"""Recovery tables on the shared ledger database (feature "recovery"; new tables, so create_all adds
them at this shape, store.py).

- `recovery_contacts`: the people an owner trusts to confirm a recovery (up to 5, D-028). Each row
  is one invite and, once accepted, one contact credential: a P-256 public key held in the contact's
  phone (the #702 approver-key machinery), the sealed contact secret behind the offline 8-digit code
  (25e), and the hash of the contact's bearer token (`omc_`), which reaches only the contact routes.
- `recovery_settings`: the owner's chosen waits, one JSON object per owner so later PRs add keys
  without a schema step (D-028: "the owner picks each wait from set options").
- `recovery_notices`: what a contact is told (a contact was added, a recovery started, ...). Owners
  and adults get the same facts as notifications (notify catalogue); a contact outside the household
  has no inbox on the box, so their app reads these.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from ..ledger import Base
from ..store import FeatureSchema

SCHEMA = FeatureSchema("recovery")
TS = DateTime(timezone=True)


class ContactRow(Base):
    __tablename__ = "recovery_contacts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # rc_<ulid>
    owner_user_id: Mapped[str] = mapped_column(String(40), index=True)
    # recovery (25d) | legacy (25f): the same invite and credential machinery, separate roles.
    role: Mapped[str] = mapped_column(String(16), default="recovery")
    kind: Mapped[str] = mapped_column(String(16))  # household | outside
    household_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    display_name: Mapped[str] = mapped_column(String(60))
    # invited -> active -> removed | resigned; an invite nobody accepted in time reads as expired.
    state: Mapped[str] = mapped_column(String(16))
    invite_nonce_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_at: Mapped[datetime] = mapped_column(TS)
    invite_expires_at: Mapped[datetime] = mapped_column(TS)
    cooling_off_days: Mapped[int] = mapped_column(Integer)
    accepted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    usable_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    device_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    key_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    public_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # P-256 SPKI DER
    key_fingerprint: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    sealed_secret: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # AES-GCM, see seal.py
    token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    # Role-specific values a later PR adds without a schema step (25f: the legacy wait and verifier).
    extra: Mapped[dict] = mapped_column(JSON, default=dict)


class SettingsRow(Base):
    __tablename__ = "recovery_settings"
    owner_user_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    values: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(TS)
    updated_by: Mapped[str] = mapped_column(String(80))


class NoticeRow(Base):
    __tablename__ = "recovery_notices"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)  # rn_<ulid>
    owner_user_id: Mapped[str] = mapped_column(String(40), index=True)
    at: Mapped[datetime] = mapped_column(TS, index=True)
    event: Mapped[str] = mapped_column(String(60))  # the notify event type, e.g. recovery.contact.added
    # Ids, names the owner typed and times only: never a secret, never any of the owner's data.
    data: Mapped[dict] = mapped_column(JSON)
