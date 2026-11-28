from __future__ import annotations

import json
import os
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onemind_core import systemlist
from onemind_core.app import create_app
from onemind_core.config import Settings
from onemind_core.guard import LimitSettings
from onemind_core.executors import ExecResult, Executor, NoopExecutor

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


def _signed_list_for_tests() -> None:
    """systemlist.load() refuses a group- or world-writable list, as it must on the box. A checkout made
    under umask 0002 leaves the repo copy 0664, which would empty the system apps list in every test.
    Then the tests read a 0644 copy of the same bytes; test_system_apps.py still checks the refusal."""
    src = systemlist.REPO_FILE
    if not src.is_file() or not src.stat().st_mode & 0o022:
        return
    import atexit
    import tempfile

    folder = Path(tempfile.mkdtemp(prefix="onemind-system-apps-"))
    atexit.register(shutil.rmtree, folder, ignore_errors=True)
    copy = folder / src.name
    copy.write_bytes(src.read_bytes())
    copy.chmod(0o644)
    systemlist.REPO_FILE = copy


_signed_list_for_tests()

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


def pytest_configure(config):
    """Give each pytest-xdist worker its own PostgreSQL database (CI-03, #228).

    The `settings` fixture drops every table before each test, so workers sharing one database
    would wipe each other's rows mid-test. Worker gw3 gets `<db>_gw3`, created on first use and
    emptied the same way by `settings`. Serial runs (no xdist) keep the database they were given.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    db_url = os.environ.get("ONEMIND_TEST_DB_URL")
    if not (worker and db_url):
        return
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from onemind_core.ledger import make_engine

    base = make_url(db_url)
    if base.get_backend_name() != "postgresql":
        return
    name = f"{base.database}_{worker}"
    admin = make_engine(db_url).execution_options(isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}):
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.engine.dispose()
    os.environ["ONEMIND_TEST_DB_URL"] = base.set(database=name).render_as_string(hide_password=False)


def _shard_key(item) -> str:
    group = item.get_closest_marker("xdist_group")
    if group is not None:
        return "group:" + str(group.args[0] if group.args else group.kwargs.get("name"))
    return item.nodeid


def pytest_collection_modifyitems(config, items):
    """ONEMIND_TEST_SHARD=k/n keeps a stable 1/n of the tests (CI-03, #228).

    ci-core splits the slow PostgreSQL leg over several runners. A test goes to shard
    crc32(node id) mod n, so every test runs in exactly one shard and the split does not move
    when tests are added elsewhere. Tests in one xdist_group stay in the same shard.
    """
    spec = os.environ.get("ONEMIND_TEST_SHARD", "").strip()
    if not spec:
        return
    import zlib

    k, n = (int(x) for x in spec.split("/"))
    if not 1 <= k <= n:
        raise pytest.UsageError("ONEMIND_TEST_SHARD must be k/n with 1 <= k <= n")
    keep, drop = [], []
    for item in items:
        (keep if zlib.crc32(_shard_key(item).encode()) % n == k - 1 else drop).append(item)
    if drop:
        config.hook.pytest_deselected(items=drop)
    items[:] = keep


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


def fresh_scans(settings) -> None:
    """Re-date every fixture app's scan record to one day before the real wall clock.

    Tests that run a gateway on the real clock need this: the `settings` fixture dates scans on the
    frozen test clock, which ages past the 7-day scan rule (§10.3) as the real date moves on.
    """
    for app_dir in Path(settings.apps_dir).iterdir():
        if (app_dir / "scan.json").exists():
            write_scan(app_dir, datetime.now(UTC) - timedelta(days=1))


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


@pytest.fixture(autouse=True)
def test_agent_reads_nothing(request):
    """The scripted test agent ("hermes") is one whose owner declared it reads no outside text.

    D-028: every agent is exposed (tainted all the time) until the owner declares otherwise, so a
    standing approval never accepts its requests. Tests of standing approvals, rate limits and the
    like need the declared-none case; tests of the default itself carry
    `@pytest.mark.default_exposure` and see the real lookup.
    """
    if request.node.get_closest_marker("default_exposure"):
        yield
        return
    from onemind_core.taint_store import AgentInputs

    real = AgentInputs._default
    # Its own MonkeyPatch: a test's `monkeypatch.undo()` must not undo this too.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(AgentInputs, "_default",
                   lambda self, pid, kind: () if pid == "hermes" else real(self, pid, kind))
        yield


@pytest.fixture
def executor() -> ScriptedExecutor:
    return ScriptedExecutor()


@pytest.fixture
def client(settings, clock, executor):
    app = create_app(settings, clock=clock, executor=executor)
    with TestClient(app) as c:
        yield c


def make_client(settings: Settings, clock, executor=None, *, peer=("testclient", 50000), **changes):
    s = replace(settings, **changes)
    return TestClient(create_app(s, clock=clock, executor=executor or NoopExecutor()), client=peer)


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
    meta.setdefault("age_rating", 18)  # FAM-01: required by the schema; the safest value for a fixture
    meta.setdefault("licenceClass", "L1")  # #173: required by the schema
    spec.setdefault("updates", {"channel": "stable", "automerge": "none"})
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
