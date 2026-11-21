# SPDX-License-Identifier: Apache-2.0
"""Approved installation snapshot, separate from mutable Market declarations."""
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..ledger import Base
from ..store import FeatureSchema

SCHEMA = FeatureSchema("plugins")


class PluginInstallRow(Base):
    __tablename__ = "plugins_installs"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    secret_name: Mapped[str] = mapped_column(String(253))
    bundle_sha256: Mapped[str] = mapped_column(String(71))
    manifest: Mapped[dict] = mapped_column(JSON)
