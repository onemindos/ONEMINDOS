# SPDX-License-Identifier: Apache-2.0
"""The feature plumbing of docs/leap/core/PLUMBING.md: router registry, feature tables and
upgrade steps, settings sections, and the publish_event hook. Runs on SQLite and PostgreSQL."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Integer, String, inspect, select, text
from sqlalchemy.orm import Mapped, mapped_column

import onemind_core.app as app_module
from onemind_core import ledger, sections
from onemind_core.app import ROUTERS, create_app
from onemind_core.audit import AuditLog, verify
from onemind_core.auth import Principal
from onemind_core.config import Settings
from onemind_core.context import Gateway
from onemind_core.events import EVENT_SCHEMA, MAX_PAYLOAD_BYTES, EventHub, matches
from onemind_core.routers import static
from onemind_core.sections import config_section, env_name, load_section
from onemind_core.store import Database, FeatureSchema, SchemaVersionRow, SqlRepository, migrate

from conftest import OWNER


# ---- a throwaway feature, declared the way PLUMBING.md tells a stream to -------------------
class PlumbtestItemRow(ledger.Base):
    __tablename__ = "plumbtest_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(String(80), nullable=True)  # added in v2


class PlumbtestRepository(SqlRepository):
    def add(self, name: str) -> int:
        with self.db.session.begin() as s:
            res = s.execute(
                self.db.insert()(PlumbtestItemRow).values(name=name).returning(PlumbtestItemRow.id)
            )
            return res.scalar_one()

    def names(self) -> list[str]:
        with self.db.session() as s:
            return list(s.scalars(select(PlumbtestItemRow.name).order_by(PlumbtestItemRow.id)))


def plumbtest_schema() -> FeatureSchema:
    schema = FeatureSchema("plumbtest", register=False)

    @schema.step(2, "add plumbtest_items.note")
    def _add_note(conn):
        conn.execute(text("ALTER TABLE plumbtest_items ADD COLUMN note VARCHAR(80)"))

    return schema


@pytest.fixture
def engine(settings):
    eng = ledger.make_engine(settings.db_url)  # tracked and disposed by conftest
    yield eng


def versions(engine) -> dict[str, int]:
    with engine.connect() as c:
        return dict(c.execute(select(SchemaVersionRow.feature, SchemaVersionRow.version)).all())


# ---- routers ---------------------------------------------------------------------------------
def test_router_registry_keeps_static_last():
    assert ROUTERS[-1] is static.register
    assert len(set(ROUTERS)) == len(ROUTERS)


def test_feature_router_plugs_in_with_one_entry(settings, clock, executor, monkeypatch):
    seen = {}

    def register(app: FastAPI, gw: Gateway) -> None:
        gw.on_startup(lambda: seen.setdefault("started", True))

        async def stop():
            seen["stopped"] = True

        gw.on_shutdown(stop)

        @app.get("/v1/plumbtest", tags=["plumbtest"])
        def hello(p: Principal = Depends(gw.principal)):
            return {"principal": p.id, "instance": gw.settings.instance_name}

    monkeypatch.setattr(app_module, "ROUTERS", [*ROUTERS[:-1], register, ROUTERS[-1]])
    with TestClient(create_app(settings, clock=clock, executor=executor)) as c:
        assert seen == {"started": True}
        assert c.get("/v1/plumbtest").status_code == 401
        r = c.get("/v1/plumbtest", headers=OWNER)
        assert r.status_code == 200 and r.json()["instance"] == "Test OneMind"
        assert "/v1/plumbtest" in c.get("/openapi.json").json()["paths"]
    assert seen["stopped"] is True


def test_gateway_records_core_schema_version(client):
    gw = client.app.state.gateway
    assert versions(gw.db.engine)["core"] == 3
    assert "approved_by" in {c["name"] for c in inspect(gw.db.engine).get_columns("actions")}


# ---- feature tables and upgrade steps -------------------------------------------------------
def test_fresh_feature_is_stamped_at_head_without_running_steps(engine, clock):
    schema = plumbtest_schema()
    assert migrate(engine, [schema], now=clock.now) == {"plumbtest": 2}
    assert versions(engine)["plumbtest"] == 2
    cols = {c["name"] for c in inspect(engine).get_columns("plumbtest_items")}
    assert cols == {"id", "name", "note"}
    repo = PlumbtestRepository(Database(engine))
    repo.add("a")
    repo.add("b")
    assert repo.names() == ["a", "b"]
    # Running again changes nothing.
    assert migrate(engine, [schema], now=clock.now) == {"plumbtest": 2}


def test_existing_feature_runs_pending_steps_in_order(engine, clock):
    migrate(engine, [], now=clock.now)  # schema_versions exists
    with engine.begin() as c:
        c.execute(text("DROP TABLE IF EXISTS plumbtest_items"))
        c.execute(text("CREATE TABLE plumbtest_items (id INTEGER PRIMARY KEY, name VARCHAR(40))"))
        c.execute(text("INSERT INTO plumbtest_items (id, name) VALUES (1, 'old')"))
        c.execute(SchemaVersionRow.__table__.insert().values(feature="plumbtest", version=1, updated_at=clock.now))
    assert migrate(engine, [plumbtest_schema()], now=clock.now) == {"plumbtest": 2}
    assert versions(engine)["plumbtest"] == 2
    cols = {c["name"] for c in inspect(engine).get_columns("plumbtest_items")}
    assert "note" in cols
    assert PlumbtestRepository(Database(engine)).names() == ["old"]


def test_failing_step_rolls_back_and_keeps_version(engine, clock):
    schema = FeatureSchema("plumbfail", register=False)
    migrate(engine, [schema], now=clock.now)  # stamped at 1

    @schema.step(2, "breaks")
    def _boom(conn):
        conn.execute(SchemaVersionRow.__table__.update().where(SchemaVersionRow.feature == "core").values(version=99))
        raise RuntimeError("step failed")

    with pytest.raises(RuntimeError, match="step failed"):
        migrate(engine, [schema], now=clock.now)
    v = versions(engine)
    assert v["plumbfail"] == 1 and v.get("core") != 99


def test_newer_database_is_refused(engine, clock):
    schema = FeatureSchema("plumbnew", register=False)
    migrate(engine, [schema], now=clock.now)
    with engine.begin() as c:
        c.execute(SchemaVersionRow.__table__.update().where(SchemaVersionRow.feature == "plumbnew").values(version=3))
    with pytest.raises(RuntimeError, match="downgrade is not supported"):
        migrate(engine, [schema], now=clock.now)


def test_schema_declaration_rules():
    with pytest.raises(ValueError):
        FeatureSchema("Bad-Name", register=False)
    schema = FeatureSchema("plumbrules", register=False)
    with pytest.raises(ValueError):
        schema.step(1)(lambda c: None)
    schema.step(3)(lambda c: None)
    with pytest.raises(ValueError, match="missing upgrade steps"):
        schema.check()
    with pytest.raises(ValueError, match="registered twice"):
        schema.step(3)(lambda c: None)


# ---- settings sections ----------------------------------------------------------------------
@config_section("plumbtest")
@dataclass(frozen=True)
class PlumbtestSettings:
    enabled: bool = False
    url: str | None = None
    retry_s: float = 30.0
    limit: int = 5
    spool: Path = Path("spool")
    channels: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.limit < 1:
            raise ValueError("ONEMIND_PLUMBTEST_LIMIT must be at least 1")


def test_section_loads_typed_values_from_env():
    env = {
        "ONEMIND_PLUMBTEST_ENABLED": "yes", "ONEMIND_PLUMBTEST_URL": "https://ntfy.example.org",
        "ONEMIND_PLUMBTEST_RETRY_S": "2.5", "ONEMIND_PLUMBTEST_LIMIT": "9",
        "ONEMIND_PLUMBTEST_SPOOL": "/data/spool", "ONEMIND_PLUMBTEST_CHANNELS": "push, ntfy,,email",
    }
    s = load_section(PlumbtestSettings, env)
    assert s == PlumbtestSettings(True, "https://ntfy.example.org", 2.5, 9, Path("/data/spool"), ("push", "ntfy", "email"))
    assert load_section(PlumbtestSettings, {"ONEMIND_PLUMBTEST_URL": ""}).url is None
    assert env_name("plumbtest", "retry_s") == "ONEMIND_PLUMBTEST_RETRY_S"


@pytest.mark.parametrize("var,value,msg", [
    ("ONEMIND_PLUMBTEST_ENABLED", "maybe", "must be a bool"),
    ("ONEMIND_PLUMBTEST_LIMIT", "ten", "must be a int"),
    ("ONEMIND_PLUMBTEST_LIMIT", "0", "at least 1"),
])
def test_section_refuses_bad_values(var, value, msg):
    with pytest.raises(ValueError, match=msg):
        load_section(PlumbtestSettings, {var: value})


def test_required_section_field(monkeypatch):
    monkeypatch.setattr(sections, "_SECTIONS", dict(sections._SECTIONS))  # keep it out of other tests

    @config_section("plumbreq")
    @dataclass(frozen=True)
    class Required:
        token_file: Path

    with pytest.raises(ValueError, match="ONEMIND_PLUMBREQ_TOKEN_FILE is required"):
        load_section(Required, {})
    assert load_section(Required, {"ONEMIND_PLUMBREQ_TOKEN_FILE": "t"}).token_file == Path("t")


def test_settings_from_env_carries_sections(settings, monkeypatch):
    s = Settings.from_env({"ONEMIND_NODE_ID": "abc123def456", "ONEMIND_PLUMBTEST_LIMIT": "7"})
    assert s.section(PlumbtestSettings).limit == 7
    # Built directly (as the tests do): the section's defaults.
    assert settings.section(PlumbtestSettings) == PlumbtestSettings()
    assert replace(settings, sections={"plumbtest": PlumbtestSettings(limit=3)}).section(PlumbtestSettings).limit == 3
    with pytest.raises(ValueError, match="ONEMIND_PLUMBTEST_ENABLED"):
        Settings.from_env({"ONEMIND_NODE_ID": "x", "ONEMIND_PLUMBTEST_ENABLED": "2"})


def test_section_registration_rules():
    with pytest.raises(ValueError):
        config_section("Bad")
    with pytest.raises(TypeError):
        config_section("plumbnotdc")(type("NotDataclass", (), {}))


# ---- publish_event ---------------------------------------------------------------------------
@pytest.fixture
def hub(tmp_path, clock):
    published: list[tuple[str, bytes]] = []
    audit = AuditLog(tmp_path / "audit.jsonl", clock)
    return EventHub(audit, clock, publish=lambda s, d: published.append((s, d)), instance_id="abc123def456"), published


def test_publish_event_audits_publishes_and_fans_out(hub, tmp_path):
    events, published = hub
    got, other = [], []
    events.subscribe("backup.>", got.append)
    events.subscribe("node.*", other.append)
    env = events.publish_event(
        "backup", "run.failed", {"run_id": "r1", "reason": "target unreachable"},
        principal={"id": "owner", "kind": "person", "role": "owner"}, severity="critical",
        resource={"kind": "backup_target", "id": "t1"}, dedupe_key="backup:t1:failing",
    )
    assert env["schema"] == EVENT_SCHEMA and env["type"] == "backup.run.failed" and env["actor_id"] == "owner"
    assert env["id"].startswith("evt_") and env["instance_id"] == "abc123def456"
    # contract 12.8: schema with a slash, ts and subject
    assert env["schema"] == "onemind.event/v1" and env["ts"] and env["subject"] == {"backup_target_id": "t1"}
    # 1. hash chain
    lines = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert lines[-1]["event"] == "backup.run.failed"
    assert lines[-1]["data"] == {
        "event_id": env["id"], "severity": "critical", "payload": {"run_id": "r1", "reason": "target unreachable"},
        "resource": {"kind": "backup_target", "id": "t1"}, "dedupe_key": "backup:t1:failing",
    }
    assert verify(tmp_path / "audit.jsonl")[0]
    # 2. NATS (the audit line itself has no publisher in this fixture)
    assert [s for s, _ in published] == ["onemind.event.backup.run.failed"]
    assert json.loads(published[0][1]) == env
    # 3. in-process
    assert got == [env] and other == []


def test_publish_event_survives_broken_bus_and_subscriber(tmp_path, clock):
    def bad_publish(subject, data):
        raise ConnectionError("nats down")

    events = EventHub(AuditLog(tmp_path / "a.jsonl", clock), clock, publish=bad_publish)
    calls = []
    events.subscribe("app.*", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    unsubscribe = events.subscribe("app.*", calls.append)
    events.publish_event("app", "unhealthy", {"app_id": "whoami"}, severity="warning")
    assert len(calls) == 1
    unsubscribe()
    events.publish_event("app", "healthy", {"app_id": "whoami"})
    assert len(calls) == 1
    assert verify(tmp_path / "a.jsonl") == (True, 2, "ok")


@pytest.mark.parametrize("domain,name,payload,kw", [
    ("Backup", "failed", {}, {}),
    ("backup", "run..failed", {}, {}),
    ("backup", "failed", {"x": object()}, {}),
    ("backup", "failed", {"x": "y" * MAX_PAYLOAD_BYTES}, {}),
    ("backup", "failed", {}, {"severity": "fatal"}),
])
def test_publish_event_rejects_bad_input(hub, domain, name, payload, kw):
    events, published = hub
    with pytest.raises(ValueError):
        events.publish_event(domain, name, payload, **kw)
    assert published == []


def test_subject_pattern_matching():
    assert matches("node.offline", "node.offline")
    assert matches("node.*", "node.offline") and not matches("node.*", "node.a.b")
    assert matches("backup.>", "backup.run.failed") and not matches("backup.>", "backup")
    assert matches(">", "anything.at.all") and not matches("app.*", "node.offline")
    with pytest.raises(ValueError):
        EventHub.subscribe(EventHub.__new__(EventHub), "a.>.b", print)


def test_gateway_exposes_events_on_the_live_bus_path(client):
    gw = client.app.state.gateway
    assert client.app.state.events is gw.events
    env = gw.events.publish_event("plumbtest", "ping", {"n": 1})
    assert env["type"] == "plumbtest.ping"
    ok, n, _ = verify(gw.settings.audit_path)
    assert ok and n >= 2


@pytest.mark.nats
def test_publish_event_reaches_real_nats(settings, clock, executor):
    """onemind.event.<type> on a real NATS server. Skipped unless ONEMIND_TEST_NATS_URL is set."""
    import asyncio
    import os
    import threading
    import time

    import nats

    url = os.environ.get("ONEMIND_TEST_NATS_URL")
    if not url:
        pytest.skip("ONEMIND_TEST_NATS_URL not set")
    received: list[bytes] = []
    ready, stop = threading.Event(), threading.Event()

    async def side_channel():
        nc = await nats.connect(url)

        async def on_event(msg):
            received.append(msg.data)

        await nc.subscribe("onemind.event.>", cb=on_event)
        await nc.flush()
        ready.set()
        while not stop.is_set():
            await asyncio.sleep(0.05)
        await nc.drain()

    t = threading.Thread(target=lambda: asyncio.run(side_channel()), daemon=True)
    t.start()
    assert ready.wait(10)
    try:
        with TestClient(create_app(replace(settings, nats_url=url), clock=clock, executor=executor)) as c:
            gw = c.app.state.gateway
            end = time.time() + 10
            while not gw.bus.connected and time.time() < end:
                time.sleep(0.05)
            env = gw.events.publish_event("plumbtest", "nats", {"n": 2})
            end = time.time() + 10
            while not received and time.time() < end:
                time.sleep(0.05)
    finally:
        stop.set()
        t.join(10)
    assert received and json.loads(received[0]) == env


def test_event_severity_follows_contract_12_8(hub):
    """Only info|warning|critical leave the gateway; draft-era names are mapped, junk is refused."""
    events, _ = hub
    assert events.publish_event("backup", "x", {}, severity="error")["severity"] == "warning"
    assert events.publish_event("backup", "x", {}, severity="debug")["severity"] == "info"
    with pytest.raises(ValueError):
        events.publish_event("backup", "x", {}, severity="bogus")
