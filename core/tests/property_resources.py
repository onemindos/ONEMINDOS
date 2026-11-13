# SPDX-License-Identifier: Apache-2.0
"""Fresh, retained real SQL resources per generated example, never a shared reset.

ONEMIND_TEST_DB_URL selects PostgreSQL; ONEMIND_PROPERTY_BACKEND can require the
backend explicitly. ONEMIND_PROPERTY_ARTIFACTS selects a retained evidence root.
Closing an example releases handles only. No DROP, reset, or cleanup is used.
The application can still delete rows when a test exercises removal; this helper
is not authorization to run destructive application paths.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema

from conftest import Clock, EXAMPLES, FIXTURES, write_scan
from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core.guard import LimitSettings
from onemind_core.ledger import Base, SqlActionRepository, make_engine
from onemind_core.notify.service import NotifySettings


class PropertyResources:
    def __init__(self, *, root=None, db_url=None, expected=None, limit=25000):
        self.db_url = db_url
        actual = make_url(db_url).get_backend_name() if db_url else "sqlite"
        self.expected = expected or actual
        if self.expected not in {"sqlite", "postgresql"} or self.expected != actual:
            raise ValueError("property backend does not match the required backend")
        if db_url and actual != "postgresql":
            raise ValueError("property database URL must select the PostgreSQL backend")
        if db_url and make_url(db_url).query.get("options"):
            raise ValueError("property database URL must not supply connection options")
        if limit < 1:
            raise ValueError("property allocation limit must be positive")
        self.root = Path(root) if root else Path(tempfile.mkdtemp(prefix="onemind-properties-"))
        self.root.mkdir(parents=True, exist_ok=True)
        # A separate manifest per factory keeps worker processes from sharing append handles.
        self.manifest = self.root / ("allocations-" + uuid.uuid4().hex + ".jsonl")
        self.limit, self.allocated = limit, 0

    @classmethod
    def from_env(cls):
        return cls(root=os.environ.get("ONEMIND_PROPERTY_ARTIFACTS"),
                   db_url=os.environ.get("ONEMIND_TEST_DB_URL"),
                   expected=os.environ.get("ONEMIND_PROPERTY_BACKEND"),
                   limit=int(os.environ.get("ONEMIND_PROPERTY_MAX_ALLOCATIONS", "25000")))

    def record(self, **fields):
        # No URLs, bearer tokens, exception messages or application payloads in allocation logs.
        with self.manifest.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(fields, sort_keys=True) + "\n")

    @contextmanager
    def example(self):
        if self.allocated >= self.limit:
            raise RuntimeError("property allocation limit reached; retained resources were not reset")
        self.allocated += 1
        ident = "prop_" + uuid.uuid4().hex
        root = self.root / ident
        root.mkdir()  # never reuse an old example, including during shrinking
        schema = ident if self.expected == "postgresql" else None
        self.record(example=ident, backend=self.expected, state="allocating", schema=schema)
        engine = None
        try:
            if schema:
                assert re.fullmatch(r"prop_[0-9a-f]{32}", schema)
                assert self.db_url is not None
                admin = make_engine(self.db_url)
                try:
                    with admin.begin() as connection:
                        database = connection.scalar(text("SELECT current_database()"))
                        connection.execute(CreateSchema(schema))
                finally:
                    admin.dispose()
                url = make_url(self.db_url).update_query_dict({"options": "-csearch_path=" + schema})
                engine = make_engine(url.render_as_string(hide_password=False))
            else:
                database = None
                engine = make_engine(f"sqlite:///{root / 'ledger.sqlite'}")
            sample = PropertyExample(root, engine, self.expected, schema, database)
            sample.assert_namespace()
            sample.repo = SqlActionRepository(engine)
            assert sample.repo.list() == [] and sample.repo.list_app_states() == {}
            sample.assert_namespace()
            self.record(example=ident, backend=self.expected, state="allocated", schema=schema)
            yield sample
        except BaseException as exc:
            self.record(example=ident, backend=self.expected, state="failed", error=type(exc).__name__)
            raise
        else:
            self.record(example=ident, backend=self.expected, state="finished", schema=schema)
        finally:
            if engine is not None:
                engine.dispose()


class PropertyExample:
    def __init__(self, root, engine, expected, schema, database):
        self.root, self.engine, self.expected = root, engine, expected
        self.schema, self.database = schema, database
        self.repo: SqlActionRepository | None = None
        self.clock = Clock()
        self.scan_time = self.clock.now - timedelta(days=1)
        self.apps = root / "apps"
        shutil.copytree(FIXTURES / "apps", self.apps)
        for app in ("uptime-kuma", "hermes-like"):
            write_scan(self.apps / app, self.scan_time)
        self.audit_path = root / "audit.jsonl"

    def assert_namespace(self):
        assert self.engine.dialect.name == self.expected, "actual property backend mismatch"
        # Hold both open: search_path must apply on every physical connection, not one SET.
        with self.engine.connect() as first, self.engine.connect() as second:
            for connection in (first, second):
                if self.schema:
                    assert self.engine.dialect.driver == "psycopg"
                    observed = connection.execute(text(
                        "SELECT current_database(), current_schema(), current_setting('search_path')"
                    )).one()
                    assert tuple(observed) == (self.database, self.schema, self.schema), "property namespace mismatch"
                    if self.repo is not None:
                        # All registered tables resolve in this schema, never public/$user.
                        for table in Base.metadata.sorted_tables:
                            resolved = connection.scalar(text(
                                "SELECT n.nspname FROM pg_catalog.pg_class c "
                                "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                                "WHERE c.oid=to_regclass(:name)"
                            ), {"name": table.name})
                            assert resolved == self.schema, "property table escaped its allocated schema"
                else:
                    observed = connection.exec_driver_sql("PRAGMA database_list").all()
                    # Compare real paths: macOS reports /private/var for a /var temp dir.
                    actual = next(r[2] for r in observed if r[1] == "main")
                    assert os.path.realpath(actual) == os.path.realpath(self.root / "ledger.sqlite")

    def audit_records(self):
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text(encoding="utf-8").split("\n") if line]

    @contextmanager
    def http(self, executor=None):
        settings = Settings(
            tokens_file=EXAMPLES / "tokens.example.yaml",
            db_url=self.engine.url.render_as_string(hide_password=False),
            apps_dir=self.apps, dashboard_dist=None, executor="noop", nats_url=None,
            audit_path=self.audit_path, node_id="abc123def456", instance_name="Property test",
            app_schema_path=None, kubectl="kubectl", executor_timeout_s=5, host="127.0.0.1", port=8080,
            sections={"limits": LimitSettings(read_burst=100_000, request_burst=100_000,
                                            auth_failures_per_min=100_000),
                      # Protocol/action properties do not test delivery or retention pruning.
                      # This supported setting avoids background network/retention side effects.
                      "notify": NotifySettings(worker=False)},
        )
        app = create_app(settings, clock=self.clock, repo=self.repo, executor=executor)
        assert app.state.repo.engine is app.state.gateway.db.engine is self.engine
        self.assert_namespace()
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
        self.assert_namespace()
