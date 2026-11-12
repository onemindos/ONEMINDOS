from __future__ import annotations

import os
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core.executors import ExecResult, Executor, NoopExecutor

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"

OWNER = {"Authorization": "Bearer dev-owner-token-change-me"}
ADULT = {"Authorization": "Bearer dev-adult-token-change-me"}
GUEST = {"Authorization": "Bearer dev-guest-token-change-me"}
AGENT = {"Authorization": "Bearer dev-agent-token-change-me"}


class Clock:
    """Controllable clock so expiry and node staleness are tested without sleeping."""

    def __init__(self):
        self.now = datetime(2026, 11, 11, 22, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class ScriptedExecutor(Executor):
    """Executor whose outcome the test chooses."""

    name = "scripted"

    def __init__(self, outcome: str = "succeeded", raise_exc: bool = False):
        self.outcome = outcome
        self.raise_exc = raise_exc
        self.calls: list[tuple[str, str]] = []

    def run(self, action_type, app):
        self.calls.append((action_type, app.id))
        if self.raise_exc:
            raise RuntimeError("boom")
        return ExecResult(self.outcome, f"scripted {self.outcome}")


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    apps = tmp_path / "apps"
    shutil.copytree(FIXTURES / "apps", apps)
    db_url = os.environ.get("ONEMIND_TEST_DB_URL")
    if db_url:
        # Run the whole suite against PostgreSQL (BD-04): start every test from empty tables.
        from onemind_core.ledger import Base, make_engine

        engine = make_engine(db_url)
        Base.metadata.drop_all(engine)
        engine.dispose()
    return Settings(
        tokens_file=EXAMPLES / "tokens.example.yaml",
        db_url=db_url or f"sqlite:///{tmp_path / 'onemind.db'}",
        apps_dir=apps,
        dashboard_dist=FIXTURES / "dist",
        executor="noop",
        nats_url=None,
        audit_path=tmp_path / "audit.jsonl",
        node_id="abc123def456",
        instance_name="Test OneMind",
        app_schema_path=None,
        kubectl="kubectl",
        executor_timeout_s=5,
        host="127.0.0.1",
        port=8080,
    )


@pytest.fixture
def executor() -> ScriptedExecutor:
    return ScriptedExecutor()


@pytest.fixture
def client(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        yield c


def make_client(settings: Settings, clock, executor=None, **changes):
    s = replace(settings, **changes)
    return TestClient(create_app(s, clock=clock, executor=executor or NoopExecutor()))


def action_body(clock: Clock, app_id="uptime-kuma", type_="app.install", key="k1", ttl=600):
    return {
        "type": type_,
        "params": {"app_id": app_id},
        "idempotency_key": key,
        "expires_at": (clock.now + timedelta(seconds=ttl)).isoformat().replace("+00:00", "Z"),
    }
