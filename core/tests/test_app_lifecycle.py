# SPDX-License-Identifier: Apache-2.0
"""App lifecycle (PD-03..PD-07): start/stop/restart/update/configure/delete_data, plan binding,
health-gated updates with revert, remove-keeps-data and sealed app credentials.

The tests run on SQLite by default and on PostgreSQL when ONEMIND_TEST_DB_URL is set (CI does).
"""

from __future__ import annotations

import json
import subprocess

import pytest
import yaml
from sqlalchemy import create_engine, inspect, select

from conftest import ADULT, AGENT, OWNER, FakeKubectl, ScriptedExecutor, action_body, make_client
from onemind_core.catalog import Catalog
from onemind_core.executors import ExecResult, KubernetesExecutor
from onemind_core.lifecycle import CredentialRow
from onemind_core.store import _core_v2

APP = "uptime-kuma"


def file(client, clock, type_, key, app_id=APP, who=OWNER, **extra):
    body = action_body(clock, app_id=app_id, type_=type_, key=key)
    body["params"].update(extra.pop("params", {}))
    body.update(extra)
    return client.post("/v1/actions", json=body, headers=who)


def run(client, clock, type_, key, app_id=APP, **extra):
    r = file(client, clock, type_, key, app_id, **extra)
    assert r.status_code == 201, r.text
    ok = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert ok.status_code == 200, ok.text
    return ok.json()


def status(client, app_id=APP):
    row = next(a for a in client.get("/v1/apps", headers=OWNER).json() if a["id"] == app_id)
    return row["status"], row["data_kept"]


def audit_events(settings):
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines()]


def bump_manifest(settings, version="2.1.0"):
    path = settings.apps_dir / APP / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"]["version"] = version
    path.write_text(yaml.safe_dump(doc))


# ---- happy paths and progress -----------------------------------------------------------------


def test_stop_start_restart_cycle_with_progress(settings, clock):
    with make_client(settings, clock) as c:  # the noop executor reports progress
        assert run(c, clock, "app.install", "i")["state"] == "succeeded"
        stopped = run(c, clock, "app.stop", "s")
        assert stopped["state"] == "succeeded" and status(c) == ("stopped", False)
        assert stopped["progress"] == {"step": "app.stop done", "pct": 100}
        assert stopped["risk"] == "write" and stopped["plan_sha256"].startswith("sha256:")
        assert run(c, clock, "app.start", "st")["state"] == "succeeded" and status(c)[0] == "installed"
        assert run(c, clock, "app.restart", "r")["state"] == "succeeded" and status(c)[0] == "installed"
    kinds = [e["event"] for e in audit_events(settings)]
    assert kinds.count("action.progress") >= 4  # events carry step and pct, never secrets
    first = next(e for e in audit_events(settings) if e["event"] == "action.progress")
    assert set(first["data"]["payload"]) == {"type", "app_id", "step", "pct"}


def test_lifecycle_actions_refused_from_wrong_state(client, clock):
    assert file(client, clock, "app.stop", "a").status_code == 409  # not installed
    assert file(client, clock, "app.update", "b").status_code == 409
    run(client, clock, "app.install", "i")
    assert file(client, clock, "app.start", "c").status_code == 409  # already running


# ---- plan binding -----------------------------------------------------------------------------


def test_plan_endpoint_is_pure_and_stable(client, clock):
    a = client.get(f"/v1/apps/{APP}/plan?type=app.install", headers=OWNER)
    b = client.get(f"/v1/apps/{APP}/plan?type=app.install", headers=OWNER)
    assert a.status_code == 200 and a.json() == b.json()
    body = a.json()
    assert body["policy_verdict"] == "needs_approval" and body["risk"] == "sensitive"
    assert body["plan"]["objects"][0]["bundle_sha256"].startswith("sha256:")
    assert client.get("/v1/actions", headers=OWNER).json() == []  # nothing was filed
    other = client.get(f"/v1/apps/{APP}/plan?type=app.stop", headers=OWNER).json()
    assert other["policy_verdict"] == "refused" and other["plan_sha256"] != body["plan_sha256"]
    assert client.get("/v1/apps/nope/plan?type=app.install", headers=OWNER).status_code == 404
    assert client.get(f"/v1/apps/{APP}/plan?type=app.bogus", headers=OWNER).status_code == 422
    posted = client.post("/v1/plans", json={"type": "app.install", "params": {"app_id": APP}}, headers=OWNER)
    assert posted.json()["plan_sha256"] == body["plan_sha256"]


def test_request_and_approval_are_bound_to_plan_sha256(client, clock, executor):
    h = client.get(f"/v1/apps/{APP}/plan?type=app.install", headers=OWNER).json()["plan_sha256"]
    r = file(client, clock, "app.install", "x", plan_sha256="sha256:" + "0" * 64)
    assert r.status_code == 409 and r.json()["reason"] == "plan_changed"
    r = file(client, clock, "app.install", "y", plan_sha256=h)
    assert r.status_code == 201 and r.json()["plan_sha256"] == h
    aid = r.json()["id"]
    bad = client.post(f"/v1/actions/{aid}/approve", json={"plan_sha256": "sha256:" + "1" * 64}, headers=OWNER)
    assert bad.status_code == 409 and bad.json()["reason"] == "plan_changed"
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == []
    ok = client.post(f"/v1/actions/{aid}/approve", json={"plan_sha256": h}, headers=OWNER)
    assert ok.status_code == 200 and ok.json()["state"] == "succeeded"


def test_approval_refused_when_the_app_changed_after_the_request(client, clock, executor, settings):
    run(client, clock, "app.install", "i")
    r = file(client, clock, "app.update", "u")
    assert r.status_code == 201
    bump_manifest(settings)  # the app's files change between the request and the approval
    res = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert res.status_code == 409 and res.json()["reason"] == "plan_changed"
    assert client.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == [("app.install", APP)]  # the update never ran
    assert status(client)[0] == "installed"


def test_execution_refuses_a_plan_that_changed_after_approval(client, clock, executor, monkeypatch):
    r = file(client, clock, "app.install", "i")
    svc = client.app.state.actions
    real, seen = svc.render, []

    def drifting(action_type, params):
        app, rendered, problem = real(action_type, params)
        seen.append(1)
        if len(seen) > 1:  # the second look, right before the executor, sees something different
            rendered = {**rendered, "plan_sha256": "sha256:" + "2" * 64}
        return app, rendered, problem

    monkeypatch.setattr(svc, "render", drifting)
    res = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert res.status_code == 200 and res.json()["state"] == "failed"
    assert res.json()["result"]["reason"] == "plan_changed"
    assert executor.calls == []  # nothing ran
    assert status(client) == ("not_installed", False)


def test_strict_clients_must_send_plan_sha256(client, clock):
    aid = file(client, clock, "app.install", "i").json()["id"]
    strict = client.post(f"/v1/actions/{aid}/approve", headers={**OWNER, "OneMind-API-Version": "1"})
    assert strict.status_code == 409 and strict.json()["reason"] == "plan_unchecked"
    lax = client.post(f"/v1/actions/{aid}/approve", headers=OWNER)  # old clients still work, but it is recorded
    assert lax.status_code == 200


def test_unchecked_approval_is_recorded_in_the_audit_log(client, clock, settings):
    run(client, clock, "app.install", "i")
    approved = next(e for e in audit_events(settings) if e["event"] == "action.approved")
    assert approved["data"]["plan_unchecked"] is True


# ---- health-gated update ----------------------------------------------------------------------


class UpdateExecutor(ScriptedExecutor):
    def __init__(self, update: ExecResult):
        super().__init__()
        self.update = update

    def run(self, action_type, app, agent=None, ctx=None):
        self.calls.append((action_type, app.id))
        return self.update if action_type == "app.update" else ExecResult("succeeded", "ok")


def test_healthy_update_records_the_new_version(settings, clock):
    with make_client(settings, clock, UpdateExecutor(ExecResult("succeeded", "ok", reverted=False))) as c:
        run(c, clock, "app.install", "i")
        before = c.get(f"/v1/apps/{APP}/plan?type=app.update", headers=OWNER).json()
        bump_manifest(settings)
        after = c.get(f"/v1/apps/{APP}/plan?type=app.update", headers=OWNER).json()
        assert before["plan_sha256"] != after["plan_sha256"]
        assert after["plan"]["objects"][0]["from_version"] == "2.0.2" and after["plan"]["objects"][0]["to_version"] == "2.1.0"
        done = run(c, clock, "app.update", "u")
        assert done["state"] == "succeeded" and status(c)[0] == "installed"
        rt = c.app.state.repo.get_runtime(APP)
        assert (rt.version, rt.previous_version) == ("2.1.0", "2.0.2")


def test_unhealthy_update_reverts_and_the_app_stays_installed(settings, clock):
    bad = ExecResult("failed", "the new version was not healthy; the previous revision was restored", reverted=True)
    with make_client(settings, clock, UpdateExecutor(bad)) as c:
        run(c, clock, "app.install", "i")
        bump_manifest(settings)
        done = run(c, clock, "app.update", "u")
        assert done["state"] == "failed" and done["result"]["reverted"] is True
        assert status(c)[0] == "installed"  # the old revision is running again
        assert c.app.state.repo.get_runtime(APP).version == "2.0.2"  # not recorded as updated
    assert "app.update_reverted" in [e["event"] for e in audit_events(settings)]


def test_failed_update_that_was_not_reverted_marks_the_app_failed(settings, clock):
    with make_client(settings, clock, UpdateExecutor(ExecResult("failed", "kubectl exited 1"))) as c:
        run(c, clock, "app.install", "i")
        assert run(c, clock, "app.update", "u")["state"] == "failed"
        assert status(c)[0] == "failed"


class Cluster:
    """A fake kubectl: renders kustomize, lists two workloads, and fails `rollout status` on demand."""

    def __init__(self, unhealthy_first=0, undo_fails=False):
        self.calls, self.unhealthy_first, self.undo_fails, self.status_calls = [], unhealthy_first, undo_fails, 0

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        out, rc = "", 0
        if argv[1:2] == ["kustomize"]:
            out = ""
        elif argv[1:2] == ["get"]:
            out = json.dumps({"items": [
                {"kind": "Deployment", "metadata": {"name": "web"}, "spec": {"replicas": 2}},
                {"kind": "StatefulSet", "metadata": {"name": "db", "annotations": {}}, "spec": {"replicas": 1}},
            ]})
        elif argv[1:3] == ["rollout", "status"]:
            self.status_calls += 1
            rc = 1 if self.status_calls <= self.unhealthy_first else 0
        elif argv[1:3] == ["rollout", "undo"] and self.undo_fails:
            rc = 1
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="err" if rc else "")

    def verbs(self):
        return [" ".join(a[1:3]) for a in self.calls if a[1:2] != ["kustomize"]]


@pytest.fixture
def kuma(settings):
    return Catalog(settings.apps_dir).get(APP)


def test_k8s_update_waits_for_every_workload_then_keeps_the_new_revision(kuma):
    cluster = Cluster()
    res = KubernetesExecutor(runner=cluster).run("app.update", kuma)
    assert res.outcome == "succeeded" and res.reverted is False
    assert [v for v in cluster.verbs() if v.startswith("rollout")] == ["rollout status", "rollout status"]


def test_k8s_update_that_never_becomes_healthy_is_reverted(kuma):
    cluster = Cluster(unhealthy_first=1)
    res = KubernetesExecutor(runner=cluster).run("app.update", kuma)
    assert res.outcome == "failed" and res.reverted is True
    verbs = cluster.verbs()
    assert verbs.count("rollout undo") == 2  # every workload is rolled back
    assert verbs.index("rollout undo") > verbs.index("rollout status")
    assert verbs[-2:] == ["rollout status", "rollout status"]  # and checked healthy again


def test_k8s_failed_revert_is_outcome_unknown_not_a_claim(kuma):
    res = KubernetesExecutor(runner=Cluster(unhealthy_first=1, undo_fails=True)).run("app.update", kuma)
    assert res.outcome == "outcome_unknown" and res.reverted is None


def test_k8s_stop_remembers_replicas_and_start_restores_them(kuma):
    cluster = Cluster()
    ex = KubernetesExecutor(runner=cluster)
    assert ex.run("app.stop", kuma).outcome == "succeeded"
    scaled = [a for a in cluster.calls if a[1:2] == ["scale"]]
    assert [a[2] for a in scaled] == ["deployment/web", "statefulset/db"] and all("--replicas=0" in a for a in scaled)
    assert any(a[1:2] == ["annotate"] and "onemind.io/replicas-before-stop=2" in a for a in cluster.calls)


def test_k8s_configure_applies_a_configmap_then_rolls(kuma):
    from onemind_core.lifecycle import ExecContext

    cluster = Cluster()
    calls = []
    inner = cluster.__call__

    def spy(argv, **kw):
        calls.append((argv, kw.get("input")))
        return inner(argv, **kw)

    res = KubernetesExecutor(runner=spy).run("app.configure", kuma, ctx=ExecContext(settings={"LANG": "en", "DEBUG": "true"}))
    assert res.outcome == "succeeded"
    cm = json.loads(calls[0][1])
    assert cm["kind"] == "ConfigMap" and cm["data"] == {"DEBUG": "true", "LANG": "en"}
    assert [" ".join(a[1:3]) for a, _ in calls if a[1:3] == ["rollout", "restart"]] == ["rollout restart"] * 2


def test_k8s_delete_data_removes_the_namespace_but_remove_never_does(kuma):
    d, r = FakeKubectl(), FakeKubectl()
    KubernetesExecutor(runner=d).run("app.delete_data", kuma)
    KubernetesExecutor(runner=r).run("app.remove", kuma)
    assert d.calls[0][0][:3] == ["kubectl", "delete", "namespace"]
    assert "namespace" not in r.calls[0][0][2].split(",") and "persistentvolumeclaims" not in r.calls[0][0][2]


# ---- authority: AI proposes, a person approves -------------------------------------------------


def test_agent_can_propose_lifecycle_actions_but_never_approve_them(client, clock, executor):
    run(client, clock, "app.install", "i")
    r = file(client, clock, "app.stop", "ag", who=AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    aid = r.json()["id"]
    assert client.post(f"/v1/actions/{aid}/approve", headers=AGENT).status_code == 403
    assert client.post(f"/v1/actions/{aid}/approve", json={"plan_sha256": r.json()["plan_sha256"]}, headers=AGENT).status_code == 403
    assert client.post(f"/v1/actions/{aid}/approve", headers=ADULT).status_code == 403
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == [("app.install", APP)]  # nothing ran without the owner
    assert client.post(f"/v1/actions/{aid}/approve", headers=OWNER).status_code == 200


def test_agent_cannot_request_or_plan_delete_data(client, clock):
    run(client, clock, "app.install", "i")
    run(client, clock, "app.remove", "r")
    body = {"confirm": APP}
    assert file(client, clock, "app.delete_data", "d", who=AGENT, params=body).status_code == 403
    assert file(client, clock, "app.delete_data", "d2", who=ADULT, params=body).status_code == 403
    plan = client.post("/v1/plans", json={"type": "app.delete_data", "params": {"app_id": APP, "confirm": APP}}, headers=AGENT)
    assert plan.status_code == 403
    assert "app.delete_data" not in {a["type"] for a in client.get("/v1/actions", headers=OWNER).json()}  # nothing filed


def test_settings_that_look_like_secrets_are_refused(client, clock):
    run(client, clock, "app.install", "i")
    for name in ("DB_PASSWORD", "api_key", "authToken"):
        r = file(client, clock, "app.configure", "c" + name, params={"settings": {name: "x"}})
        assert r.status_code == 422, name
    assert file(client, clock, "app.configure", "empty", params={"settings": {}}).status_code == 422
    assert file(client, clock, "app.stop", "s", params={"settings": {"A": "1"}}).status_code == 422


def test_configure_stores_settings_and_hands_them_to_a_reinstall(client, clock, executor):
    run(client, clock, "app.install", "i")
    done = run(client, clock, "app.configure", "c", params={"settings": {"LANG": "de"}})
    assert done["state"] == "succeeded" and client.app.state.repo.get_runtime(APP).settings == {"LANG": "de"}
    assert done["plan"]["objects"][0]["settings"] == {"LANG": "de"}


# ---- remove keeps data; delete_data is its own explicit act -----------------------------------


def test_remove_keeps_data_and_delete_data_needs_typed_confirmation(client, clock, executor):
    run(client, clock, "app.install", "i")
    plan = client.get(f"/v1/apps/{APP}/plan?type=app.remove", headers=OWNER).json()
    assert plan["plan"]["volumes"][0]["effect"] == "kept" and "data stays" in plan["plan"]["summary"]
    run(client, clock, "app.remove", "r")
    assert status(client) == ("not_installed", True)  # gone, data kept
    assert file(client, clock, "app.delete_data", "d0").status_code == 422  # no confirmation
    assert file(client, clock, "app.delete_data", "d1", params={"confirm": "other"}).status_code == 422
    # a running app's data can't be deleted (remove first)
    run(client, clock, "app.install", "i2")
    assert file(client, clock, "app.delete_data", "d2", params={"confirm": APP}).status_code == 409
    run(client, clock, "app.remove", "r2")
    dplan = client.post("/v1/plans", json={"type": "app.delete_data", "params": {"app_id": APP, "confirm": APP}}, headers=OWNER).json()
    assert dplan["risk"] == "destructive" and dplan["plan"]["volumes"][0]["effect"] == "deleted"
    done = run(client, clock, "app.delete_data", "d3", params={"confirm": APP})
    assert done["state"] == "succeeded" and done["risk"] == "destructive"
    assert status(client) == ("not_installed", False)
    assert [c[0] for c in executor.calls].count("app.delete_data") == 1


# ---- sealed credentials (PD-07) ---------------------------------------------------------------


@pytest.fixture
def with_credentials(settings):
    path = settings.apps_dir / APP / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["spec"]["credentials"] = {"username": "admin", "password": "generated", "showBeforeOpen": True}
    path.write_text(yaml.safe_dump(doc))


def test_generated_credentials_are_sealed_owner_only_and_audited(with_credentials, client, clock, executor, settings):
    run(client, clock, "app.install", "i")
    r = client.get(f"/v1/apps/{APP}/credentials", headers=OWNER)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    login = r.json()
    assert login["username"] == "admin" and len(login["password"]) >= 24
    # never an agent, never an adult
    assert client.get(f"/v1/apps/{APP}/credentials", headers=AGENT).status_code == 403
    assert client.get(f"/v1/apps/{APP}/credentials", headers=ADULT).status_code == 403
    # the password is nowhere but the sealed row: not in the database as text, the actions, or the audit log
    repo = client.app.state.repo
    with repo._session() as s:
        sealed = s.scalars(select(CredentialRow.sealed)).one()
    assert login["password"] not in sealed
    assert login["password"] not in json.dumps(client.get("/v1/actions", headers=OWNER).json())
    assert login["password"] not in settings.audit_path.read_text()
    events = [e["event"] for e in audit_events(settings)]
    assert "app.credentials.generated" in events and events.count("app.credentials.revealed") == 1
    assert "authz.denied" in events
    # the executor was handed it to create the Secret, and the repr hides it
    assert executor.calls[0] == ("app.install", APP)


def test_credentials_survive_remove_and_go_with_delete_data(with_credentials, client, clock):
    run(client, clock, "app.install", "i")
    first = client.get(f"/v1/apps/{APP}/credentials", headers=OWNER).json()
    run(client, clock, "app.remove", "r")
    run(client, clock, "app.install", "i2")  # the kept data still has its old password, so it is reused
    assert client.get(f"/v1/apps/{APP}/credentials", headers=OWNER).json() == first
    run(client, clock, "app.remove", "r2")
    run(client, clock, "app.delete_data", "d", params={"confirm": APP})
    assert client.get(f"/v1/apps/{APP}/credentials", headers=OWNER).status_code == 404


def test_k8s_install_creates_the_credentials_secret_server_side(with_credentials, settings):
    from onemind_core.lifecycle import AppCredentialGrant, ExecContext

    app = Catalog(settings.apps_dir).get(APP)
    run_ = FakeKubectl()
    grant = AppCredentialGrant(f"{APP}-credentials", "admin", "s3cret-value")
    assert "s3cret-value" not in repr(grant)
    res = KubernetesExecutor(runner=run_).run("app.install", app, ctx=ExecContext(credentials=grant))
    assert res.outcome == "succeeded"
    secret_calls = [(a, i) for a, i in run_.cluster_calls if i and '"kind": "Secret"' in i]
    assert len(secret_calls) == 1 and "--server-side" in secret_calls[0][0]
    assert "s3cret-value" not in json.dumps(res.to_json())  # not in the recorded steps


# ---- storage -----------------------------------------------------------------------------------


def test_core_schema_v2_upgrades_an_existing_actions_table():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE actions (id VARCHAR(36) PRIMARY KEY, type VARCHAR(64))")
        _core_v2(conn)
        _core_v2(conn)  # idempotent
        assert {"plan", "plan_sha256", "progress", "risk"} <= {c["name"] for c in inspect(conn).get_columns("actions")}
