from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core.guard import LimitSettings
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
        self.agents: list = []  # the AgentSecret grant of each call (None for apps without spec.agent)
        self.secrets: list = []  # the AppSecret list of each call (() for apps without spec.secrets)

    def run(self, action_type, app, agent=None, ctx=None):
        self.calls.append((action_type, app.id))
        self.agents.append(agent)
        self.secrets.append(list(ctx.secrets) if ctx is not None else [])
        if self.raise_exc:
            raise RuntimeError("boom")
        return ExecResult(self.outcome, f"scripted {self.outcome}")


@pytest.fixture(autouse=True)
def _dispose_engines(monkeypatch):
    """Close every engine a test created, so the PostgreSQL leg never runs out of connections."""
    import onemind_core.ledger as ledger

    made = []
    real = ledger.make_engine

    def tracking(db_url):
        engine = real(db_url)
        made.append(engine)
        return engine

    monkeypatch.setattr(ledger, "make_engine", tracking)
    yield
    for engine in made:
        engine.dispose()


@pytest.fixture(scope="module")
def property_resources():
    """Stateless allocator: each draw owns a fresh retained backend and directory."""
    from property_resources import PropertyResources

    return PropertyResources.from_env()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def write_scan(app_dir: Path, scanned_at: datetime | None, result: str = "pass") -> None:
    """Write a §11.1 scan record (scanned_at=None removes it)."""
    path = app_dir / "scan.json"
    if scanned_at is None:
        path.unlink(missing_ok=True)
        return
    path.write_text(json.dumps({
        "scanned_at": scanned_at.isoformat().replace("+00:00", "Z"), "result": result, "images": [],
        "licence": {"spdx": "MIT", "class": "L1"}, "smoke": "pass",
    }))


@pytest.fixture
def settings(tmp_path: Path, clock) -> Settings:
    apps = tmp_path / "apps"
    shutil.copytree(FIXTURES / "apps", apps)
    # §10.3: installs need a passing scan newer than 7 days. Every valid fixture app gets one.
    for app_id in ("uptime-kuma", "whoami", "hermes-like", "vault-like"):
        write_scan(apps / app_id, clock.now - timedelta(days=1))
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
        # Tests fire requests faster than a person: rate buckets wide open, everything else at
        # its defaults. test_guard.py exercises the real limits.
        sections={"limits": LimitSettings(read_burst=100_000, request_burst=100_000, auth_failures_per_min=100_000)},
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


def fake_kustomize(manifests_dir) -> str:
    """A stand-in for `kubectl kustomize` that concatenates the listed local resources."""
    import yaml

    kdir = Path(manifests_dir)
    doc = yaml.safe_load((kdir / "kustomization.yaml").read_text()) or {}
    parts = [(kdir / r).read_text() for r in doc.get("resources") or []]
    return "\n---\n".join(parts)


class FakeKubectl:
    """Fake subprocess runner: renders with fake_kustomize, answers everything else with `rc`.

    results: optional list of return codes or exceptions for the non-render calls, in order.
    """

    def __init__(self, results=None, rc=0, echo=False):
        self.results = list(results) if results is not None else None
        self.rc = rc
        self.echo = echo
        self.calls = []

    def __call__(self, argv, **kw):
        import subprocess

        self.calls.append((argv, kw.get("input")))
        if argv[1:2] == ["kustomize"]:
            return subprocess.CompletedProcess(argv, 0, stdout=fake_kustomize(argv[-1]), stderr="")
        r = self.results.pop(0) if self.results is not None else self.rc
        if isinstance(r, Exception):
            raise r
        stdin = kw.get("input") or ""
        return subprocess.CompletedProcess(argv, r, stdout=stdin if self.echo else "ok", stderr="err" if r else "")

    @property
    def cluster_calls(self):
        return [(a, i) for a, i in self.calls if a[1:2] != ["kustomize"]]


def conform_to_schema(app_dir: Path) -> None:
    """Fill the contract §9.3 fields that sdk/schema now requires, for fixtures written before it.

    Tests that validate against the real schema call this on their tmp copy of a fixture; the
    fixture files themselves keep their deliberate oddities for the tests that need them.
    """
    import yaml

    path = app_dir / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    meta, spec = doc["metadata"], doc["spec"]
    meta["links"] = {
        "docs": "https://example.com/docs",
        "github": "https://github.com/example/" + meta["id"],
        "website": "https://example.com",
        "support": "https://github.com/example/" + meta["id"] + "/issues",
    }
    meta.setdefault("upstream", {"release": "v" + str(meta["version"]), "released_at": "2026-01-01T00:00:00Z", "archived": False})
    meta.setdefault("tier", "community")
    spec.setdefault("updates", {"channel": "stable", "automerge": "none"})
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
