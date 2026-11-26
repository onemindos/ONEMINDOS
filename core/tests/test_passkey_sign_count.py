# SPDX-License-Identifier: Apache-2.0
"""The WebAuthn signature counter is an unsigned 32-bit number: the passkey column must be BIGINT.

PostgreSQL's INTEGER is signed 32-bit, so a counter above 2147483647 (a passkey that signs often, or an
authenticator that uses a timestamp as its counter) would fail the update and lock that passkey out. SQLite
ignores the width, so the type itself is what the test pins, plus the upgrade for databases made before."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from onemind_core.identity import models
from onemind_core.identity.models import PasskeyRow

MAX_U32 = 2**32 - 1


def test_the_sign_count_column_is_a_big_integer():
    col = PasskeyRow.__table__.c.sign_count
    assert isinstance(col.type, BigInteger)
    assert "sign_count BIGINT" in str(CreateTable(PasskeyRow.__table__).compile(dialect=postgresql.dialect()))
    assert "sign_count BIGINT" in str(CreateTable(PasskeyRow.__table__).compile(dialect=sqlite.dialect()))


def test_an_unsigned_32_bit_counter_round_trips(client):
    repo = client.app.state.identity.repo
    row = PasskeyRow(id="cred-high-counter", user_id="usr_x", label="phone", public_key=b"k", sign_count=MAX_U32,
                     transports=[], created_at=datetime(2026, 11, 25, tzinfo=UTC))
    repo.add(row)
    assert repo.get(PasskeyRow, "cred-high-counter").sign_count == MAX_U32
    repo.update(PasskeyRow, [PasskeyRow.id == "cred-high-counter"], {"sign_count": MAX_U32 - 1})
    assert repo.get(PasskeyRow, "cred-high-counter").sign_count == MAX_U32 - 1


class _Conn:
    def __init__(self, dialect: str):
        self.dialect = type("D", (), {"name": dialect})()
        self.sql: list[str] = []

    def execute(self, stmt):
        self.sql.append(str(stmt))


def test_the_upgrade_widens_the_column_on_postgresql_and_does_nothing_on_sqlite():
    assert models.SCHEMA.head >= 4 and 4 in models.SCHEMA.steps
    pg, lite = _Conn("postgresql"), _Conn("sqlite")
    models.SCHEMA.steps[4][1](pg)
    models.SCHEMA.steps[4][1](lite)
    assert pg.sql == ["ALTER TABLE identity_passkeys ALTER COLUMN sign_count TYPE BIGINT"]
    assert lite.sql == []
