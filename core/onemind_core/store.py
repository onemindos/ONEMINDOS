# SPDX-License-Identifier: Apache-2.0
"""Feature tables on the shared ledger database, and their versioned upgrade steps.

How a feature stores data (docs/leap/core/PLUMBING.md §3):

1. Declare its tables on the shared `ledger.Base` in its own module, named `<feature>_<thing>`.
2. Create `SCHEMA = FeatureSchema("<feature>")` there. Version 1 is the shape `create_all` builds.
3. Write a repository class that subclasses `SqlRepository` and takes the `Database`.
4. To change a table that has shipped: change the model AND add `@SCHEMA.step(n)` (n = 2, 3, ...)
   that brings an existing database from n-1 to n. Steps never edit another feature's tables.

`migrate(engine)` runs at gateway start: `create_all` (new tables appear at their current shape),
then, per feature, either stamps a feature seen for the first time at its head version (its
tables were just created at that shape) or runs its pending steps in order, one transaction each.

Why not Alembic: one global revision chain means five parallel streams each adding "the next
revision" collide on every merge. Per-feature chains never collide, and need no new dependency.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from .ledger import Base

log = logging.getLogger("onemind.store")

FEATURE_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

Step = Callable[[Connection], None]


class SchemaVersionRow(Base):
    """One row per feature: the version its tables are at in this database."""

    __tablename__ = "schema_versions"
    feature: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeatureSchema:
    """A feature's schema version chain. Version 1 is the baseline create_all builds."""

    def __init__(self, feature: str, *, register: bool = True):
        if not FEATURE_RE.match(feature):
            raise ValueError(f"feature name {feature!r} must match {FEATURE_RE.pattern}")
        self.feature = feature
        self.steps: dict[int, tuple[str, Step]] = {}
        if register:
            _register(self)

    @property
    def head(self) -> int:
        return max(self.steps, default=1)

    def step(self, version: int, description: str = "") -> Callable[[Step], Step]:
        """Register the upgrade from version-1 to version. Versions start at 2 and have no gaps."""

        def deco(fn: Step) -> Step:
            if version < 2:
                raise ValueError("version 1 is the create_all baseline; steps start at 2")
            if version in self.steps:
                raise ValueError(f"{self.feature}: step {version} registered twice")
            self.steps[version] = (description or fn.__name__, fn)
            return fn

        return deco

    def check(self) -> None:
        missing = [v for v in range(2, self.head + 1) if v not in self.steps]
        if missing:
            raise ValueError(f"{self.feature}: missing upgrade steps {missing}")


_SCHEMAS: dict[str, FeatureSchema] = {}


def _register(schema: FeatureSchema) -> None:
    if schema.feature in _SCHEMAS and _SCHEMAS[schema.feature] is not schema:
        raise ValueError(f"feature schema {schema.feature!r} registered twice")
    _SCHEMAS[schema.feature] = schema


def registered_schemas() -> list[FeatureSchema]:
    return [_SCHEMAS[k] for k in sorted(_SCHEMAS)]


# The tables ledger.py has always had (actions, app_states, agent_tokens) are feature "core", v1.
CORE_SCHEMA = FeatureSchema("core")


@CORE_SCHEMA.step(2, "app lifecycle: plan, plan_sha256, progress and risk on actions (app_runtime is a new table)")
def _core_v2(conn: Connection) -> None:
    from sqlalchemy import inspect, text

    have = {c["name"] for c in inspect(conn).get_columns("actions")}
    for name, ddl in (("plan", "JSON"), ("plan_sha256", "VARCHAR(80)"), ("progress", "JSON"), ("risk", "VARCHAR(16)")):
        if name not in have:
            conn.execute(text(f"ALTER TABLE actions ADD COLUMN {name} {ddl}"))


@CORE_SCHEMA.step(3, "durable approval attribution; historical approvals remain unknown")
def _core_v3(conn: Connection) -> None:
    from sqlalchemy import inspect, text

    if "approved_by" not in {c["name"] for c in inspect(conn).get_columns("actions")}:
        conn.execute(text("ALTER TABLE actions ADD COLUMN approved_by VARCHAR(200)"))


def migrate(engine: Engine, schemas: Iterable[FeatureSchema] | None = None, now: datetime | None = None) -> dict[str, int]:
    """Create missing tables, then bring each feature to its head version. Returns feature -> version."""
    schemas = registered_schemas() if schemas is None else list(schemas)
    now = now or datetime.now(UTC)
    Base.metadata.create_all(engine)
    result: dict[str, int] = {}
    for schema in schemas:
        schema.check()
        with engine.begin() as conn:
            current = conn.execute(
                select(SchemaVersionRow.version).where(SchemaVersionRow.feature == schema.feature)
            ).scalar()
            if current is None:  # first time: create_all just built its tables at the head shape
                conn.execute(_insert(engine)(SchemaVersionRow).values(
                    feature=schema.feature, version=schema.head, updated_at=now
                ).on_conflict_do_nothing(index_elements=[SchemaVersionRow.feature]))
                result[schema.feature] = schema.head
                continue
        if current > schema.head:
            raise RuntimeError(
                f"database has {schema.feature} schema v{current}, this gateway knows only v{schema.head}"
                " (downgrade is not supported; restore the database from before the upgrade)"
            )
        for version in range(current + 1, schema.head + 1):
            description, fn = schema.steps[version]
            log.info("upgrading %s schema to v%d: %s", schema.feature, version, description)
            with engine.begin() as conn:  # the step and its version bump commit together, or neither
                fn(conn)
                conn.execute(
                    SchemaVersionRow.__table__.update()
                    .where(SchemaVersionRow.feature == schema.feature)
                    .values(version=version, updated_at=now)
                )
        result[schema.feature] = schema.head
    return result


def _insert(engine: Engine):
    return (postgresql if engine.dialect.name == "postgresql" else sqlite).insert


class Database:
    """The ledger engine plus a session factory, shared by every feature repository."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.session = sessionmaker(engine, expire_on_commit=False)

    def insert(self):
        """Dialect insert with on_conflict_do_*; read the outcome with RETURNING (psycopg 3 rowcount is -1)."""
        return _insert(self.engine)


class SqlRepository:
    """Base class for a feature repository: `self.db.session.begin()` for writes, `self.db.session()` for reads."""

    def __init__(self, db: Database):
        self.db = db
