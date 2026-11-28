# SPDX-License-Identifier: Apache-2.0
"""Private-tier signing trust is activated only by an approved owner action."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema

SCHEMA = FeatureSchema("plugin_trust")


class SigningKeyRow(Base):
    __tablename__ = "plugin_trust_keys"
    id: Mapped[str] = mapped_column(String(71), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    public_key: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_id: Mapped[str] = mapped_column(String(36))


class KeyCandidateRow(Base):
    __tablename__ = "plugin_trust_candidates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    key_id: Mapped[str] = mapped_column(String(71))
    name: Mapped[str] = mapped_column(String(80))
    public_key: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
