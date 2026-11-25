# SPDX-License-Identifier: Apache-2.0
"""A box can upgrade the first registry slice without losing installed receipts."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from onemind_core.ledger import make_engine
from onemind_core.plugins.models import SCHEMA, PluginInstallRow
from onemind_core.store import migrate


def test_upgrade_registry_v1_preserves_receipts_and_adds_nullable_settings(tmp_path):
    engine = make_engine("sqlite:///" + str(tmp_path / "old.db"))
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE schema_versions (feature VARCHAR(40) PRIMARY KEY, "
                              "version INTEGER NOT NULL, updated_at DATETIME NOT NULL)"))
            conn.execute(text("INSERT INTO schema_versions VALUES ('plugins', 1, CURRENT_TIMESTAMP)"))
            conn.execute(text("CREATE TABLE plugins_installs (app_id VARCHAR(59) PRIMARY KEY, "
                              "secret_name VARCHAR(253) NOT NULL, bundle_sha256 VARCHAR(71) NOT NULL, "
                              "manifest JSON NOT NULL)"))
            conn.execute(text("INSERT INTO plugins_installs VALUES ('example', 'example-identity', :digest, '{}')"),
                         {"digest": "sha256:" + "1" * 64})
        assert migrate(engine, schemas=[SCHEMA])["plugins"] == 2
        with Session(engine) as session:
            row = session.get(PluginInstallRow, "example")
            assert row.secret_name == "example-identity" and row.manifest == {}
            assert row.settings_schema is None
        assert migrate(engine, schemas=[SCHEMA])["plugins"] == 2
    finally:
        engine.dispose()


def test_fresh_plugin_database_starts_at_latest_schema(tmp_path):
    engine = make_engine("sqlite:///" + str(tmp_path / "new.db"))
    try:
        assert migrate(engine, schemas=[SCHEMA])["plugins"] == 2
    finally:
        engine.dispose()
