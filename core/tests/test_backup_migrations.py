# SPDX-License-Identifier: Apache-2.0
"""Upgrade backup history on SQLite and on PostgreSQL with ONEMIND_TEST_DB_URL."""

import pytest
from sqlalchemy import select, text

from onemind_core.backups.store import BackupsRepository, ContentTierRow
from onemind_core.ledger import make_engine
from onemind_core.store import Database, SchemaVersionRow, migrate


@pytest.mark.parametrize("has_content_tier", [False, True], ids=["main", "early-release-next"])
def test_upgrade_backup_byte_counters_from_v1(settings, clock, has_content_tier):
    engine = make_engine(settings.db_url)
    try:
        with engine.begin() as conn:
            SchemaVersionRow.__table__.create(conn)
            conn.execute(SchemaVersionRow.__table__.insert().values(
                feature="backups", version=1, updated_at=clock.now,
            ))
            # Keep the shipped v1 DDL here so this test exercises an INTEGER column on PostgreSQL.
            conn.execute(text("""
                CREATE TABLE backups_runs (
                    id VARCHAR(64) PRIMARY KEY,
                    action_id VARCHAR(36),
                    reason VARCHAR(16) NOT NULL,
                    destination_id VARCHAR(40),
                    state VARCHAR(16) NOT NULL,
                    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    finished_at TIMESTAMP WITH TIME ZONE,
                    units JSON NOT NULL,
                    hooks JSON NOT NULL,
                    bytes_added INTEGER,
                    error TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO backups_runs (id, reason, state, started_at, units, hooks, bytes_added)
                VALUES ('old', 'scheduled', 'succeeded', CURRENT_TIMESTAMP, '[]', '[]', 1024),
                       ('pending', 'scheduled', 'running', CURRENT_TIMESTAMP, '[]', '[]', NULL)
            """))
            if has_content_tier:
                conn.execute(text("""
                    CREATE TABLE backups_content_tier (
                        app_id VARCHAR(64) PRIMARY KEY,
                        size_bytes INTEGER NOT NULL,
                        action_id VARCHAR(36) NOT NULL,
                        enabled_at TIMESTAMP WITH TIME ZONE NOT NULL
                    )
                """))
                conn.execute(text("""
                    INSERT INTO backups_content_tier (app_id, size_bytes, action_id, enabled_at)
                    VALUES ('old-app', 2048, 'old-action', CURRENT_TIMESTAMP)
                """))

        versions = migrate(engine, now=clock.now)
        repo = BackupsRepository(Database(engine))
        assert repo.run("old").bytes_added == 1024
        assert repo.run("pending").bytes_added is None
        large_count = 5 * 1024**3 + 1
        repo.update_run("pending", bytes_added=large_count, state="succeeded")
        repo.set_content_tier(ContentTierRow(
            app_id="large-app", size_bytes=large_count, action_id="new-action", enabled_at=clock.now,
        ), "large-app")

        assert versions["backups"] == 2
        assert migrate(engine)["backups"] == 2
        assert repo.run("old").bytes_added == 1024
        assert repo.run("pending").bytes_added == large_count
        sizes = {app: row.size_bytes for app, row in repo.content_tier().items()}
        assert sizes.pop("large-app") == large_count
        assert sizes == ({"old-app": 2048} if has_content_tier else {})
        with engine.connect() as conn:
            assert conn.scalar(select(SchemaVersionRow.version).where(SchemaVersionRow.feature == "backups")) == 2
    finally:
        engine.dispose()
