# SPDX-License-Identifier: Apache-2.0
"""Contract §12.22 through the REST API: logs, settings + app.configure, dependencies, host ports,
exposure tiers, Compose conversion and community sources (umbrel-parity PD-08…PD-13, PD-17)."""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from conftest import ADULT, AGENT, GUEST, OWNER, ScriptedExecutor, action_body, make_client, write_scan
from onemind_core.executors import NoopExecutor
from onemind_core.appstore.sources import FetchError, GitFetcher

DIGEST = "sha256:" + "a" * 64
COMMIT_A = "1" * 40
COMMIT_B = "2" * 40
_keys = itertools.count()


# ---- helpers -----------------------------------------------------------------------------------------

def add_app(cfg, clock, app_id: str, scan: bool = True, **spec_extra) -> Path:
    """Write a valid app folder into the test's apps dir (with a fresh passing scan)."""
    d = cfg.apps_dir / app_id
    (d / "manifests").mkdir(parents=True, exist_ok=True)
    (d / "manifests" / "kustomization.yaml").write_text("resources: []\n")
    doc = {
        "apiVersion": "onemind.app/v1alpha1", "kind": "App",
        "metadata": {"id": app_id, "name": app_id.title(), "version": "1.0.0", "description": "test app",
                     "category": "developer", "license": "MIT"},
        "spec": {"archs": ["amd64", "arm64"], "requires": {"gpu": False, "minMemoryMb": 64}, **spec_extra},
    }
    (d / "onemind.app.yaml").write_text(yaml.safe_dump(doc))
    if scan:
        write_scan(d, clock.now - timedelta(hours=1))
    return d


def request(client, clock, type_, params, headers=OWNER, key=None):
    body = action_body(clock, key=key or f"{type_}-{next(_keys)}")
    body["type"], body["params"] = type_, params
    return client.post("/v1/actions", json=body, headers=headers)


def run(client, clock, type_, params, headers=OWNER):
    """Request (as headers) and approve (as owner); returns the approve response."""
    r = request(client, clock, type_, params, headers=headers)
    assert r.status_code == 201, r.text
    return client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)


def install(client, clock, app_id):
    r = run(client, clock, "app.install", {"app_id": app_id})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text


def audit_events(settings) -> list[dict]:
    return [json.loads(line) for line in settings.audit_path.read_text().splitlines()]


def store_of(client):
    return client.app.state.appstore


# ---- settings and app.configure (PD-09) --------------------------------------------------------------

SETTINGS = [
    {"name": "retention_days", "env": "RETENTION_DAYS", "type": "integer", "default": 7, "minimum": 1, "maximum": 365},
    {"name": "theme", "env": "THEME", "type": "enum", "enum": ["light", "dark"], "default": "light", "restart": False},
    {"name": "debug", "env": "DEBUG", "type": "bool", "default": False},
    {"name": "site_name", "env": "SITE_NAME", "type": "string", "maxLength": 20, "pattern": "[A-Za-z ]+"},
]


@pytest.fixture
def cfg_client(settings, clock, executor):
    add_app(settings, clock, "notes", settings=SETTINGS)
    c = make_client(settings, clock, executor)
    with c:
        yield c


@pytest.fixture
def noop_cfg_client(settings, clock):
    add_app(settings, clock, "notes", settings=SETTINGS)
    with make_client(settings, clock, NoopExecutor()) as c:
        yield c


def test_settings_view_hides_values_from_guests_and_agents(cfg_client):
    r = cfg_client.get("/v1/apps/notes/settings", headers=OWNER)
    assert r.status_code == 200
    body = r.json()
    assert [f["name"] for f in body["fields"]] == ["retention_days", "theme", "debug", "site_name"]
    assert body["fields"][1]["type"] == "string" and body["fields"][2]["type"] == "boolean"  # aliases
    assert body["values"] == {"retention_days": 7, "theme": "light", "debug": False}
    for headers in (GUEST, AGENT):
        assert cfg_client.get("/v1/apps/notes/settings", headers=headers).json()["values"] is None


def test_configure_round_trip(noop_cfg_client, clock, settings):
    cfg_client = noop_cfg_client
    install(cfg_client, clock, "notes")
    r = run(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": {"retention_days": 30, "theme": "dark"}})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    steps = r.json()["result"]["steps"]
    assert steps[0]["keys"] == ["DEBUG", "RETENTION_DAYS", "THEME"] and "roll the workloads" in steps[0]["would"]
    view = cfg_client.get("/v1/apps/notes/settings", headers=ADULT).json()
    assert view["values"] == {"retention_days": 30, "theme": "dark", "debug": False}
    assert view["action_id"] == r.json()["id"]
    apps = {a["id"]: a for a in cfg_client.get("/v1/apps", headers=OWNER).json()}
    assert apps["notes"]["status"] == "installed"


@pytest.mark.parametrize("values,status", [
    ({"retention_days": 0}, 422), ({"retention_days": "30"}, 422), ({"theme": "blue"}, 422),
    ({"nope": 1}, 422), ({}, 422), ({"debug": 1}, 422), ({"site_name": "x" * 21}, 422),
    ({"site_name": "bad1"}, 422), ({"site_name": "a\x00b"}, 422),
])
def test_configure_refuses_bad_values(cfg_client, clock, values, status):
    install(cfg_client, clock, "notes")
    r = request(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": values})
    assert r.status_code == status, r.text


def test_configure_needs_an_installed_app_and_no_sealed(cfg_client, clock):
    r = request(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": {"debug": True}})
    assert r.status_code == 409 and "not installed" in r.json()["message"]
    install(cfg_client, clock, "notes")
    r = request(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": {"debug": True}, "sealed": {"ct": "x"}})
    assert r.status_code == 422
    r = request(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": {"debug": True}, "extra": 1})
    assert r.status_code == 422


def test_agent_may_request_configure_but_never_approve(cfg_client, clock):
    install(cfg_client, clock, "notes")
    r = request(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": {"debug": True}}, headers=AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert cfg_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    assert cfg_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"


def test_configure_rechecked_at_approval(cfg_client, clock, settings):
    install(cfg_client, clock, "notes")
    r = request(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": {"retention_days": 300}})
    assert r.status_code == 201
    tighter = [dict(SETTINGS[0], maximum=100), *SETTINGS[1:]]
    add_app(settings, clock, "notes", settings=tighter)  # the manifest moved under the request
    a = cfg_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert a.status_code == 409 and a.json()["error"] == "stale_precondition" and a.json()["reason"] == "settings_invalid"
    assert cfg_client.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_credential_looking_settings_are_refused(client, settings, clock):
    add_app(settings, clock, "leaky", settings=[{"name": "admin_password", "env": "ADMIN_PASSWORD", "type": "string"}])
    r = client.get("/v1/apps/leaky/settings", headers=OWNER)
    assert r.status_code == 409 and "credential" in r.json()["message"]


class KubeNamedExecutor(ScriptedExecutor):
    name = "kubernetes"


class CtxSpyExecutor(ScriptedExecutor):
    """Records the ExecContext of each call: what the lifecycle executor (§12.40) would write."""

    def __init__(self):
        super().__init__()
        self.ctxs = []

    def run(self, action_type, app, agent=None, ctx=None):
        self.ctxs.append((action_type, ctx))
        return super().run(action_type, app, agent=agent, ctx=ctx)


def test_configure_hands_the_executor_the_configmap_data_and_a_restart(settings, clock):
    """The §12.40 executor writes ConfigMap onemind-settings and rolls the workloads; the app store
    gives it the data keyed by env name, defaults included, booleans as true/false (§12.22)."""
    add_app(settings, clock, "notes", settings=SETTINGS)
    spy = CtxSpyExecutor()
    with make_client(settings, clock, spy) as c:
        install(c, clock, "notes")
        r = run(c, clock, "app.configure", {"app_id": "notes", "settings": {"retention_days": 30}})
        assert r.json()["state"] == "succeeded", r.text
    ctx = [x for t, x in spy.ctxs if t == "app.configure"][0]
    assert ctx.settings == {"RETENTION_DAYS": "30", "THEME": "light", "DEBUG": "false"} and ctx.restart is True


def test_configure_restart_skipped_when_fields_say_so(noop_cfg_client, clock):
    cfg_client = noop_cfg_client
    install(cfg_client, clock, "notes")
    r = run(cfg_client, clock, "app.configure", {"app_id": "notes", "settings": {"theme": "dark"}})
    steps = r.json()["result"]["steps"]
    assert len(steps) == 1 and "not restarted" in steps[0]["would"]


def test_configure_restart_flag_reaches_the_executor(settings, clock):
    add_app(settings, clock, "notes", settings=SETTINGS)
    spy = CtxSpyExecutor()
    with make_client(settings, clock, spy) as c:
        install(c, clock, "notes")
        assert run(c, clock, "app.configure", {"app_id": "notes", "settings": {"theme": "dark"}}).json()["state"] == "succeeded"
    assert [x.restart for t, x in spy.ctxs if t == "app.configure"] == [False]


# ---- dependencies (PD-10) ----------------------------------------------------------------------------

@pytest.fixture
def dep_client(settings, clock, executor):
    add_app(settings, clock, "postgres")
    add_app(settings, clock, "mariadb")
    add_app(settings, clock, "wiki", dependencies=[{"id": "postgres", "alternatives": ["mariadb"], "reason": "database"}])
    with make_client(settings, clock, executor) as c:
        yield c


def test_install_refused_until_a_dependency_is_installed(dep_client, clock):
    r = request(dep_client, clock, "app.install", {"app_id": "wiki"})
    assert r.status_code == 409 and r.json()["reason"] == "dependency_missing"
    assert "one of postgres, mariadb (database)" in r.json()["message"]
    view = dep_client.get("/v1/apps/wiki/dependencies", headers=GUEST).json()
    assert view["requires"][0]["satisfied_by"] is None
    assert [c["id"] for c in view["requires"][0]["choices"]] == ["postgres", "mariadb"]
    install(dep_client, clock, "mariadb")  # an alternative is enough
    install(dep_client, clock, "wiki")
    assert dep_client.get("/v1/apps/wiki/dependencies", headers=OWNER).json()["requires"][0]["satisfied_by"] == "mariadb"


def test_remove_these_first(dep_client, clock):
    install(dep_client, clock, "mariadb")
    install(dep_client, clock, "wiki")
    assert dep_client.get("/v1/apps/mariadb/dependencies", headers=OWNER).json()["dependents"] == [
        {"id": "wiki", "name": "Wiki"}]
    r = request(dep_client, clock, "app.remove", {"app_id": "mariadb"})
    assert r.status_code == 409 and r.json()["reason"] == "has_dependents"
    assert r.json()["message"] == "remove these first: wiki"
    install(dep_client, clock, "postgres")  # another provider: removal is fine now
    assert run(dep_client, clock, "app.remove", {"app_id": "mariadb"}).json()["state"] == "succeeded"


def test_dependency_rechecked_at_approval(dep_client, clock):
    install(dep_client, clock, "mariadb")
    r = request(dep_client, clock, "app.install", {"app_id": "wiki"})
    assert r.status_code == 201
    assert run(dep_client, clock, "app.remove", {"app_id": "mariadb"}).json()["state"] == "succeeded"
    a = dep_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert a.status_code == 409 and a.json()["reason"] == "dependency_missing"


# ---- host ports (PD-11) ------------------------------------------------------------------------------

def test_host_port_conflicts(settings, clock, executor):
    add_app(settings, clock, "dns-a", hostPorts=[{"port": 53, "protocol": "udp", "description": "DNS"}])
    add_app(settings, clock, "dns-b", hostPorts=[{"port": 53, "protocol": "udp", "description": "DNS"},
                                                 {"port": 53, "protocol": "tcp", "description": "DNS over TCP"}])
    add_app(settings, clock, "sshy", hostPorts=[{"port": 22, "protocol": "tcp", "description": "ssh"}])
    with make_client(settings, clock, executor) as c:
        install(c, clock, "dns-a")
        r = request(c, clock, "app.install", {"app_id": "dns-b"})
        assert r.status_code == 409 and r.json()["reason"] == "host_port_conflict"
        assert "53/udp (held by dns-a)" in r.json()["message"]
        view = c.get("/v1/apps/dns-b/host-ports", headers=OWNER).json()
        assert view["conflicts"] == [{"port": 53, "protocol": "udp", "with": "dns-a"}] and len(view["declared"]) == 2
        r = request(c, clock, "app.install", {"app_id": "sshy"})
        assert r.status_code == 409 and "onemind:ssh" in r.json()["message"]
        assert run(c, clock, "app.remove", {"app_id": "dns-a"}).json()["state"] == "succeeded"
        install(c, clock, "dns-b")


# ---- exposure (PD-17) --------------------------------------------------------------------------------

def test_exposure_tiers_are_separate_owner_requests(client, clock, settings):
    install(client, clock, "uptime-kuma")
    view = client.get("/v1/apps/uptime-kuma/exposure", headers=GUEST).json()
    assert view["tier"] == "private" and view["names"] == ["uptime-kuma.onemind.local"]
    r = request(client, clock, "exposure.mesh", {"app_id": "uptime-kuma"}, headers=AGENT)
    assert r.status_code == 403
    r = run(client, clock, "exposure.mesh", {"app_id": "uptime-kuma"})
    assert r.json()["state"] == "succeeded"
    view = client.get("/v1/apps/uptime-kuma/exposure", headers=OWNER).json()
    assert view["tier"] == "mesh" and "uptime-kuma.apps.onemind.internal" in view["names"]
    assert any(e["event"] == "app.exposure.changed" for e in audit_events(settings))
    r = request(client, clock, "exposure.public", {"app_id": "uptime-kuma"})
    assert r.status_code == 409 and r.json()["reason"] == "parked"
    assert run(client, clock, "exposure.private", {"app_id": "uptime-kuma"}).json()["state"] == "succeeded"
    assert client.get("/v1/apps/uptime-kuma/exposure", headers=OWNER).json()["tier"] == "private"


def test_exposure_resets_on_remove(client, clock):
    assert request(client, clock, "exposure.mesh", {"app_id": "uptime-kuma"}).status_code == 409  # not installed
    install(client, clock, "uptime-kuma")
    run(client, clock, "exposure.mesh", {"app_id": "uptime-kuma"})
    assert run(client, clock, "app.remove", {"app_id": "uptime-kuma"}).json()["state"] == "succeeded"
    install(client, clock, "uptime-kuma")
    assert client.get("/v1/apps/uptime-kuma/exposure", headers=OWNER).json()["tier"] == "private"
    assert store_of(client).tier("uptime-kuma") == "private"


def test_proxy_refuses_mesh_names_unless_exposed(client, clock):
    from onemind_core.proxy import AppProxy, Decision, token_session_resolver

    install(client, clock, "uptime-kuma")
    gw = client.app.state.gateway
    store = store_of(client)
    proxy = AppProxy(gw.catalog, lambda i: (st := gw.repo.get_app_state(i)) and st.status,
                     token_session_resolver(gw.tokens), lambda ns, port: "198.51.100.7",
                     box_domains=("onemind.local", "apps.onemind.internal"), exposure=store.tier)
    auth = {"authorization": OWNER["Authorization"]}
    lan = proxy.decide({**auth, "host": "uptime-kuma.onemind.local"}, "uptime-kuma")[0]
    mesh = proxy.decide({**auth, "host": "uptime-kuma.apps.onemind.internal:443"}, "uptime-kuma")[0]
    assert lan == Decision.ALLOW and mesh == Decision.NOT_FOUND
    run(client, clock, "exposure.mesh", {"app_id": "uptime-kuma"})
    assert proxy.decide({**auth, "host": "uptime-kuma.apps.onemind.internal"}, "uptime-kuma")[0] == Decision.ALLOW


# ---- Compose conversion (PD-13) ----------------------------------------------------------------------

GOOD_COMPOSE = f"""
services:
  web:
    image: ghcr.io/example/notes:1.2.3@{DIGEST}
    user: "1000:1000"
    ports: ["8080:3000"]
    environment:
      DB_HOST: db
      LOG_LEVEL: ${{LOG_LEVEL:-info}}
    volumes: ["notes-data:/data"]
  db:
    image: docker.io/library/postgres:17@{DIGEST}
    user: "999"
    expose: ["5432"]
    volumes: ["db-data:/var/lib/postgresql/data"]
volumes:
  notes-data: {{}}
  db-data: {{}}
"""


def test_compose_converts_to_a_private_app(client, settings):
    r = client.post("/v1/deploy/compose", json={"app_id": "notes", "name": "Notes", "compose": GOOD_COMPOSE},
                    headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["refusals"] == []
    files = body["files"]
    manifest = yaml.safe_load(files["onemind.app.yaml"])
    assert manifest["metadata"]["origin"] == "private" and manifest["spec"]["web"] == {"port": 3000}
    dep = yaml.safe_load(files["manifests/web-deployment.yaml"])
    c = dep["spec"]["template"]["spec"]["containers"][0]
    assert c["securityContext"]["capabilities"] == {"drop": ["ALL"]} and c["securityContext"]["runAsUser"] == 1000
    assert {"name": "LOG_LEVEL", "value": "info"} in c["env"]
    assert dep["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
    assert yaml.safe_load(files["manifests/db-service.yaml"])["spec"]["ports"][0]["port"] == 5432
    assert "manifests/notes-data-pvc.yaml" in files
    assert any("host port 8080 is not published" in w for w in body["warnings"])
    assert not (settings.apps_dir / "notes").exists()  # no side effects
    events = [e for e in audit_events(settings) if e["event"] == "deploy.compose.converted"]
    assert events and events[0]["data"]["ok"] is True and "compose" not in events[0]["data"]


@pytest.mark.parametrize("service,rule", [
    ({"privileged": True}, "F-06"),
    ({"network_mode": "host"}, "F-01"),
    ({"pid": "host"}, "F-02"),
    ({"ipc": "host"}, "F-03"),
    ({"volumes": ["/etc:/host-etc"]}, "F-04"),
    ({"volumes": ["./data:/data"]}, "F-04"),
    ({"volumes": [{"type": "bind", "source": "/var/run/docker.sock", "target": "/var/run/docker.sock"}]}, "F-04"),
    ({"cap_add": ["SYS_ADMIN"]}, "F-07"),
    ({"user": "root"}, "S-01"),
    ({"user": "0:0"}, "S-01"),
    ({"image": "nginx:latest"}, "I-01"),
    ({"build": "."}, "C-02"),
    ({"env_file": [".env"]}, "C-04"),
    ({"environment": ["FROM_HOST"]}, "C-04"),
    ({"environment": {"X": "${FROM_HOST}"}}, "C-04"),
    ({"devices": ["/dev/ttyUSB0:/dev/ttyUSB0"]}, "C-06"),
    ({"security_opt": ["seccomp:unconfined"]}, "C-07"),
    ({"sysctls": {"net.ipv4.ip_forward": 1}}, "C-08"),
    ({"network_mode": "service:other"}, "C-09"),
    ({"userns_mode": "host"}, "C-10"),
    ({"mystery_key": 1}, "C-01"),
])
def test_compose_refuses_what_the_sandbox_refuses(client, service, rule):
    svc = {"image": f"ghcr.io/example/app:1@{DIGEST}", "user": "1000", **service}
    text = yaml.safe_dump({"services": {"app": svc}})
    r = client.post("/v1/deploy/compose", json={"app_id": "imported", "compose": text}, headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False and body["files"] == {}
    assert rule in {x["rule"] for x in body["refusals"]}, body["refusals"]


def test_compose_driver_opts_bind_is_refused(client):
    text = yaml.safe_dump({"services": {"app": {"image": f"x/y:1@{DIGEST}", "user": "1000", "volumes": ["v:/d"]}},
                           "volumes": {"v": {"driver": "local", "driver_opts": {"type": "none", "o": "bind", "device": "/"}}}})
    body = client.post("/v1/deploy/compose", json={"app_id": "imported", "compose": text}, headers=OWNER).json()
    assert body["ok"] is False and "F-04" in {x["rule"] for x in body["refusals"]}


@pytest.mark.parametrize("headers", [ADULT, GUEST, AGENT])
def test_compose_is_owner_only(client, headers):
    r = client.post("/v1/deploy/compose", json={"app_id": "imported", "compose": GOOD_COMPOSE}, headers=headers)
    assert r.status_code == 403


def test_compose_rejects_bad_input(client):
    bomb = "a: &a [x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"{c}: &{c} [*{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}]\n" for p, c in zip("abcdefgh", "bcdefghi")
    ) + f"services: {{app: {{image: 'x/y:1@{DIGEST}', x-bomb: *i}}}}\n"
    for text in ("services: [", "just a string", "services: {}", bomb):
        r = client.post("/v1/deploy/compose", json={"app_id": "imported", "compose": text}, headers=OWNER)
        assert r.status_code == 422, text[:40]
    r = client.post("/v1/deploy/compose", json={"app_id": "uptime-kuma", "compose": GOOD_COMPOSE}, headers=OWNER)
    assert r.status_code == 409  # the id is taken


# ---- community sources (PD-12) -----------------------------------------------------------------------

def source_app(root: Path, app_id: str, *, version="1.0.0", host_network=False, scan_pass=False):
    d = root / app_id
    (d / "manifests").mkdir(parents=True, exist_ok=True)
    (d / "onemind.app.yaml").write_text(yaml.safe_dump({
        "apiVersion": "onemind.app/v1alpha1", "kind": "App",
        "metadata": {"id": app_id, "name": app_id, "version": version, "description": "community app",
                     "category": "developer", "license": "MIT", "tier": "verified"},
        "spec": {"archs": ["amd64"], "requires": {"gpu": False, "minMemoryMb": 32}},
    }))
    (d / "manifests" / "kustomization.yaml").write_text("resources: [deployment.yaml]\n")
    pod = {"containers": [{"name": "app", "image": f"ghcr.io/example/{app_id}:1@{DIGEST}"}]}
    if host_network:
        pod["hostNetwork"] = True
    (d / "manifests" / "deployment.yaml").write_text(yaml.safe_dump({
        "apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": app_id},
        "spec": {"selector": {"matchLabels": {"a": "b"}}, "template": {"metadata": {"labels": {"a": "b"}}, "spec": pod}},
    }))
    if scan_pass:  # a community repo's own scan.json is never trusted
        (d / "scan.json").write_text(json.dumps({"scanned_at": "2026-11-11T21:00:00Z", "result": "pass"}))


class FakeFetcher(GitFetcher):
    def __init__(self, root: Path, trees: dict[str, Path]):
        super().__init__(root)
        self.trees = trees

    def check_url(self, url):  # no DNS in tests; the host guard has its own tests (test_appstore_units)
        return None

    def fetch(self, source_id, url, commit):
        if commit not in self.trees:
            raise FetchError("no such commit")
        dst = self.path(source_id, commit)
        if not dst.exists():
            shutil.copytree(self.trees[commit], dst)
        return dst


class PassScanner:
    name = "test-scanner"

    def __init__(self):
        self.seen = []

    def scan(self, images):
        self.seen.append(images)
        return "pass", "ok"


@pytest.fixture
def src_client(settings, clock, executor, tmp_path):
    a, b = tmp_path / "tree-a", tmp_path / "tree-b"
    source_app(a, "comm-hello", scan_pass=True)
    source_app(a, "comm-net", host_network=True)
    source_app(a, "other-prefix")
    source_app(a, "uptime-kuma")
    source_app(b, "comm-hello", version="1.1.0")
    source_app(b, "comm-new")
    with make_client(settings, clock, executor) as c:
        store = store_of(c)
        store.fetcher = store.sources.fetcher = FakeFetcher(tmp_path / "cache", {COMMIT_A: a, COMMIT_B: b})
        yield c


def add_source(c, clock):
    r = run(c, clock, "source.add", {"name": "comm", "url": "https://git.example.org/comm/apps", "commit": COMMIT_A})
    assert r.status_code == 200 and r.json()["state"] == "succeeded", r.text
    return c.get("/v1/sources", headers=OWNER).json()[0]


def test_sources_are_owner_requests_with_valid_params(src_client, clock):
    for headers in (AGENT,):
        r = request(src_client, clock, "source.add", {"name": "comm", "url": "https://x.org/r", "commit": COMMIT_A},
                    headers=headers)
        assert r.status_code == 403
    for params in (
        {"name": "comm", "url": "http://x.org/r", "commit": COMMIT_A},
        {"name": "comm", "url": "https://user:pw@gitserver/r", "commit": COMMIT_A},
        {"name": "comm", "url": "https://x.org/r?ref=main", "commit": COMMIT_A},
        {"name": "comm", "url": "https://x.org/r", "commit": "main"},
        {"name": "Comm!", "url": "https://x.org/r", "commit": COMMIT_A},
        {"name": "comm", "url": "ext::sh -c id", "commit": COMMIT_A},
    ):
        assert request(src_client, clock, "source.add", params).status_code == 422, params


def test_source_apps_appear_capped_and_need_an_on_box_scan(src_client, clock):
    src = add_source(src_client, clock)
    assert src["state"] == "ready" and src["commit"] == COMMIT_A and src["id"].startswith("src_")
    scans = {a["id"]: a["scan"] for a in src["apps"]}
    assert set(scans) == {"comm-hello", "comm-net"}
    assert scans["comm-hello"]["result"] == "fail"  # no image scanner on the box
    assert scans["comm-hello"]["checks"]["images"]["result"] == "unavailable"
    assert "F-01" in json.dumps(scans["comm-net"]["checks"]["static"])
    assert any("other-prefix" in e for e in src["errors"]) and any("uptime-kuma" in e for e in src["errors"])
    apps = {a["id"]: a for a in src_client.get("/v1/apps", headers=GUEST).json()}
    hello = apps["comm-hello"]
    assert hello["tier"] == "community" and hello["catalog_source"] == {"id": src["id"], "name": "comm", "commit": COMMIT_A}
    assert hello["scan"]["result"] == "fail"  # the repository's own "pass" is ignored
    assert apps["uptime-kuma"]["catalog_source"] is None  # official ids always win
    r = request(src_client, clock, "app.install", {"app_id": "comm-hello"})
    assert r.status_code == 201
    a = src_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert a.status_code == 409 and a.json()["error"] == "stale_precondition"


def test_source_app_installs_after_a_passing_on_box_scan(src_client, clock, settings):
    scanner = PassScanner()
    store_of(src_client).image_scanner = scanner
    add_source(src_client, clock)
    install(src_client, clock, "comm-hello")
    assert ["ghcr.io/example/comm-hello:1@" + DIGEST] in scanner.seen
    # comm-net fails its static checks whatever the image scanner says
    r = request(src_client, clock, "app.install", {"app_id": "comm-net"})
    assert src_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).status_code == 409


def test_stale_on_box_scan_is_redone_before_first_install(src_client, clock, settings):
    store_of(src_client).image_scanner = PassScanner()
    add_source(src_client, clock)
    clock.advance(8 * 24 * 3600)
    r = request(src_client, clock, "app.install", {"app_id": "comm-hello"}, key="late")
    assert r.status_code == 201
    assert any(e["event"] == "source.app.scanned" for e in audit_events(settings))
    assert src_client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"


def test_move_source_reports_diff_and_protects_installed_apps(src_client, clock):
    store_of(src_client).image_scanner = PassScanner()
    src = add_source(src_client, clock)
    r = run(src_client, clock, "source.move", {"source_id": src["id"], "to_commit": COMMIT_B})
    assert r.json()["state"] == "succeeded", r.text
    diff = r.json()["result"]["steps"][0]["diff"]
    assert diff == {"added": ["comm-new"], "removed": ["comm-net"], "changed": ["comm-hello"]}
    assert src_client.get(f"/v1/sources/{src['id']}", headers=OWNER).json()["commit"] == COMMIT_B
    install(src_client, clock, "comm-new")
    r = run(src_client, clock, "source.move", {"source_id": src["id"], "to_commit": COMMIT_A})
    assert r.json()["state"] == "failed" and "remove these first: comm-new" in r.json()["result"]["message"]
    assert src_client.get(f"/v1/sources/{src['id']}", headers=OWNER).json()["commit"] == COMMIT_B
    bad = run(src_client, clock, "source.move", {"source_id": src["id"], "to_commit": "3" * 40})
    assert bad.json()["state"] == "failed"


def test_remove_source(src_client, clock):
    store_of(src_client).image_scanner = PassScanner()
    src = add_source(src_client, clock)
    install(src_client, clock, "comm-hello")
    r = request(src_client, clock, "source.remove", {"source_id": src["id"]})
    assert r.status_code == 409 and r.json()["reason"] == "has_installed_apps"
    assert run(src_client, clock, "app.remove", {"app_id": "comm-hello"}).json()["state"] == "succeeded"
    assert run(src_client, clock, "source.remove", {"source_id": src["id"]}).json()["state"] == "succeeded"
    assert src_client.get("/v1/sources", headers=OWNER).json() == []
    assert "comm-hello" not in {a["id"] for a in src_client.get("/v1/apps", headers=OWNER).json()}
    assert src_client.get(f"/v1/sources/{src['id']}", headers=OWNER).status_code == 404


def test_duplicate_source_name_is_conflict(src_client, clock):
    add_source(src_client, clock)
    r = request(src_client, clock, "source.add", {"name": "comm", "url": "https://other.example.org/r", "commit": COMMIT_B})
    assert r.status_code == 409


def test_unknown_action_type_is_422(client, clock):
    assert request(client, clock, "app.delete_everything", {"app_id": "uptime-kuma"}).status_code == 422
    assert request(client, clock, "source.add", {"app_id": "x"}).status_code == 422


def test_source_yaml_alias_bombs_are_refused(src_client, clock, tmp_path):
    tree = store_of(src_client).fetcher.trees[COMMIT_A]
    bomb = "a: &a [x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"{c}: &{c} [*{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}, *{p}]\n" for p, c in zip("abcdefgh", "bcdefghi"))
    (tree / "comm-bomb").mkdir()
    (tree / "comm-bomb" / "onemind.app.yaml").write_text(bomb)
    src = add_source(src_client, clock)
    assert any("comm-bomb" in e and "cannot parse" in e for e in src["errors"])
    assert "comm-bomb" not in {a["id"] for a in src_client.get("/v1/apps", headers=OWNER).json()}
