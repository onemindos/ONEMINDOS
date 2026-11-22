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

    settings_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PluginSettingsRow(Base):
    __tablename__ = "plugins_settings"
    app_id: Mapped[str] = mapped_column(String(59), primary_key=True)
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    claim_action: Mapped[str | None] = mapped_column(String(36), nullable=True)
    prior_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


@SCHEMA.step(2, "snapshot installed settings schemas")
def _plugins_v2(conn):
    from sqlalchemy import inspect, text

    columns = {column["name"] for column in inspect(conn).get_columns("plugins_installs")}
    if "settings_schema" not in columns:
        conn.execute(text("ALTER TABLE plugins_installs ADD COLUMN settings_schema JSON"))
