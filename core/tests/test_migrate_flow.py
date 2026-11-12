# SPDX-License-Identifier: Apache-2.0
"""Migration kit through the API: plan -> import -> copy -> cutover -> revert, plus the refusals.

The old cluster is migrate_fakes.FakeCluster and this box's kubectl is FakeBox; nothing real is
contacted. Every step after the plan is an action only a person with role owner approves.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import timedelta

import pytest

from conftest import ADULT, AGENT, OWNER, write_scan
from migrate_fakes import NS, TOKEN, FakeBox, FakeCluster, kubeconfig


@pytest.fixture
def world(client):
    svc = client.app.state.migrate
    cluster, box = FakeCluster(), FakeBox()
    svc.transport = lambda target: cluster.send
    svc.box = box
    svc.sleep = lambda s: None
    client.app.state.actions.spawn = lambda fn: fn()  # run approved steps synchronously
    return svc, cluster, box


def _plan(client, **body):
    r = client.post("/v1/migrate/plans", headers=OWNER, json={"kubeconfig": kubeconfig(), "namespace": NS,
                                                               "app_id": "notes", "name": "Notes", **body})
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client, action_id):
    r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    return client.get(f"/v1/actions/{action_id}", headers=OWNER).json()


def _audit_text(settings) -> str:
    return settings.audit_path.read_text()


def _imported(client, svc, clock):
    plan = _plan(client)
    write_scan(svc.bundle_dir(plan["id"]), clock.now - timedelta(hours=1))
    r = client.post(f"/v1/migrate/plans/{plan['id']}/import", headers=OWNER, json={})
    assert r.status_code == 202, r.text
    assert _approve(client, r.json()["id"])["state"] == "succeeded"
    return plan


def _copied(client, svc, clock):
    plan = _imported(client, svc, clock)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER, json={"kubeconfig": kubeconfig()})
    assert r.status_code == 202, r.text
    got = _approve(client, r.json()["id"])
    assert got["state"] == "succeeded", got
    return plan


def test_plan_is_read_only_and_reports(client, world, settings):
    svc, cluster, _ = world
    plan = _plan(client)
    assert plan["state"] == "planned" and plan["next"] == "import"
    assert plan["report"]["blocking"] == 0 and plan["report"]["counts"]["move"] >= 2
    assert plan["source"]["server_host"] == "old.example.test" and plan["source"]["version"] == "v1.30.0"
    assert {m for m, _ in cluster.requests} == {"GET"}
    assert (svc.bundle_dir(plan["id"]) / "staging" / "kustomization.yaml").is_file()
    text = _audit_text(settings)
    assert "migrate.plan.created" in text and TOKEN not in text
    assert client.get("/v1/migrate/plans", headers=AGENT).json()[0]["id"] == plan["id"]


def test_only_owner_plans(client, world, settings):
    for who in (ADULT, AGENT):
        r = client.post("/v1/migrate/plans", headers=who, json={"kubeconfig": kubeconfig(), "namespace": NS})
        assert r.status_code == 403
    assert not world[1].requests  # the old cluster was never contacted
    assert "authz.denied" in _audit_text(settings)


def test_plan_refusals(client, world):
    bad = client.post("/v1/migrate/plans", headers=OWNER, json={
        "kubeconfig": kubeconfig(user={"exec": {"command": "x"}}), "namespace": NS})
    assert bad.status_code == 422 and "exec" in bad.json()["message"]
    taken = client.post("/v1/migrate/plans", headers=OWNER,
                        json={"kubeconfig": kubeconfig(), "namespace": NS, "app_id": "uptime-kuma"})
    assert taken.status_code == 409 and "Market" in taken.json()["message"]
    world[1].forbidden = {"deployments"}
    denied = client.post("/v1/migrate/plans", headers=OWNER, json={"kubeconfig": kubeconfig(), "namespace": NS})
    assert denied.status_code == 409 and "onemind migrate role" in denied.json()["message"]


def test_import_needs_scan_and_owner_approval(client, world, clock, executor):
    svc, _, _ = world
    plan = _plan(client)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/import", headers=OWNER, json={})
    assert r.status_code == 202 and r.headers["location"] == f"/v1/actions/{r.json()['id']}"
    action = r.json()
    assert action["type"] == "migrate.import" and action["params"]["bundle_sha256"] == plan["bundle_sha256"]
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
    stale = client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
    assert stale.status_code == 409 and "scan" in stale.json()["message"]  # F-7: nothing unscanned runs
    write_scan(svc.bundle_dir(plan["id"]), clock.now - timedelta(hours=1))
    assert _approve(client, action["id"])["state"] == "succeeded"
    assert executor.calls == [("app.install", "notes")]
    got = client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()
    assert got["state"] == "staged" and got["next"] == "copy"
    assert client.app.state.repo.get_app_state("notes").status == "stopped"


def test_import_fails_without_the_platform_storage_class(client, world, clock, executor):
    svc, _, box = world
    box.storage_class = False
    plan = _plan(client)
    write_scan(svc.bundle_dir(plan["id"]), clock.now)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/import", headers=OWNER, json={})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "failed" and "onemind-local" in got["result"]["message"]
    assert executor.calls == []  # nothing applied


def test_unschedulable_helper_fails_instead_of_waiting(client, world, clock):
    svc, cluster, _ = world
    plan = _imported(client, svc, clock)
    cluster.helper_phase = "Pending"
    svc.settings = type(svc.settings)(rollout_timeout_s=0, poll_s=0.01)
    real_send = cluster.send

    def send(method, url, headers, body):
        status, raw = real_send(method, url, headers, body)
        for pod in cluster.helpers.values():
            pod["status"]["conditions"] = [{"type": "PodScheduled", "status": "False", "message": "0/1 nodes are available"}]
        return status, raw

    svc.transport = lambda target: send
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER,
                    json={"kubeconfig": kubeconfig(), "pvcs": ["notes-data"]})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "failed" and "could not be scheduled" in got["result"]["message"]
    assert not cluster.helpers  # deleted even so


def test_import_refused_when_bundle_changed(client, world, clock):
    svc, _, _ = world
    plan = _plan(client)
    write_scan(svc.bundle_dir(plan["id"]), clock.now)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/import", headers=OWNER, json={})
    (svc.bundle_dir(plan["id"]) / "onemind.app.yaml").write_text("tampered: true\n")
    stale = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert stale.status_code == 409 and "changed" in stale.json()["message"]


def test_agent_cannot_request_steps(client, world):
    plan = _plan(client)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=AGENT, json={"kubeconfig": kubeconfig()})
    assert r.status_code == 403


def test_copy_side_by_side_and_secrets_stay_out_of_records(client, world, clock, settings, executor):
    svc, cluster, box = world
    plan = _copied(client, svc, clock)
    got = client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()
    assert got["state"] == "running" and got["next"] == "cutover"
    assert sorted(c["pvc"] for c in got["copies"]) == ["data-db-0", "notes-data"]
    assert {c["state"] for c in got["copies"]} == {"verified"} and {c["phase"] for c in got["copies"]} == {"warm"}
    # The old cluster saw: reads, then for each volume one helper pod created, read and deleted.
    writes = [(m, p) for m, p in cluster.requests if m != "GET"]
    assert [m for m, _ in writes] == ["POST", "DELETE", "POST", "DELETE"]
    assert not cluster.helpers  # every helper pod deleted
    pod = cluster.created[0]
    env = {e["name"]: e["value"] for e in pod["spec"]["containers"][0]["env"]}
    repo_url, repo_pw = env["RESTIC_REPOSITORY"], env["RESTIC_PASSWORD"]
    assert repo_url.startswith("rest:http://") and "/v1/migrate/repo/" + plan["id"] + "/" in repo_url
    upload_secret = repo_url.split("://", 1)[1].split("@", 1)[0].split(":", 1)[1]
    # Box side: secret + job applied and deleted, new app started and rolled out.
    kinds = [c[2] for c in box.calls if c[0] == "apply"]
    assert kinds == ["Secret", "Job", "Secret", "Job"]
    assert sum(1 for c in box.calls if c[0] == "delete" and c[2] == "secret") == 2
    assert ("rollout", "app-notes", "Deployment", "notes") in box.calls
    assert executor.calls[-1] == ("app.install", "notes")
    assert client.app.state.repo.get_app_state("notes").status == "installed"
    # Credentials never land in params, results, events or the audit log.
    text = _audit_text(settings)
    actions = json.dumps(client.get("/v1/actions", headers=OWNER).json())
    for secret in (TOKEN, repo_pw, upload_secret):
        assert secret not in text and secret not in actions
    assert hashlib.sha256(TOKEN.encode()).hexdigest() not in text  # only the fingerprint, not a bare token hash
    assert '"credentials": "provided"' in text or '"credentials":"provided"' in text
    # The upload user is revoked once the action ended.
    auth = base64.b64encode(repo_url.split("://", 1)[1].split("@", 1)[0].encode()).decode()
    r = client.get(f"/v1/migrate/repo/{plan['id']}/config", headers={"Authorization": f"Basic {auth}"})
    assert r.status_code == 401


def test_copy_reports_changed_files_while_old_app_runs(client, world, clock):
    svc, _, box = world
    plan = _imported(client, svc, clock)
    box.restore_failed = 1
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER, json={"kubeconfig": kubeconfig(), "pvcs": ["notes-data"]})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "succeeded" and "changed while copying" in got["result"]["message"]
    copies = client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()["copies"]
    assert [(c["pvc"], c["state"]) for c in copies] == [("notes-data", "mismatch")]


def test_copy_failure_is_reported_and_scrubbed(client, world, clock):
    svc, cluster, _ = world
    plan = _imported(client, svc, clock)
    cluster.helper_phase = "Failed"
    cluster.helper_log = "Fatal: unable to open repository\n"
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER, json={"kubeconfig": kubeconfig()})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "failed" and "unable to open repository" in got["result"]["message"]
    assert client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()["state"] == "staged"


def test_copy_refused_after_kubeconfig_is_dropped(client, world, clock):
    svc, _, _ = world
    plan = _imported(client, svc, clock)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER, json={"kubeconfig": kubeconfig()})
    svc._held.clear()  # what a gateway restart does
    stale = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert stale.status_code == 409 and "no longer held" in stale.json()["message"]


def test_copy_refuses_kubeconfig_for_another_cluster(client, world, clock):
    svc, _, _ = world
    plan = _imported(client, svc, clock)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER,
                    json={"kubeconfig": kubeconfig(server="https://other.example.test:6443")})
    assert r.status_code == 409 and "different cluster" in r.json()["message"]


def test_cutover_stops_old_copies_final_and_revert(client, world, clock, settings):
    svc, cluster, box = world
    plan = _copied(client, svc, clock)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/cutover", headers=OWNER,
                    json={"kubeconfig": kubeconfig(), "stop_old": True})
    assert r.status_code == 202
    got = _approve(client, r.json()["id"])
    assert got["state"] == "succeeded", got
    assert "notes.example.test" in got["result"]["message"]
    view = client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()
    assert view["state"] == "switched" and view["old_replicas"] == {"Deployment/notes": 1, "StatefulSet/db": 1}
    assert {c["state"] for c in view["copies"] if c["phase"] == "final"} == {"verified"}
    assert cluster.objects["deployments"][0]["spec"]["replicas"] == 0
    assert "migrate.cutover.done" in _audit_text(settings)
    # Revert: the new app stops and the old one gets its replicas back.
    r = client.post(f"/v1/migrate/plans/{plan['id']}/revert", headers=OWNER, json={"kubeconfig": kubeconfig()})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "succeeded", got
    assert cluster.objects["deployments"][0]["spec"]["replicas"] == 1
    assert cluster.objects["statefulsets"][0]["spec"]["replicas"] == 1
    view = client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()
    assert view["state"] == "staged" and view["old_replicas"] is None
    assert ("scale", "app-notes", "Deployment", "notes", 0) in box.calls


def test_cutover_without_stop_old_needs_old_app_stopped(client, world, clock):
    svc, cluster, _ = world
    plan = _copied(client, svc, clock)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/cutover", headers=OWNER, json={"kubeconfig": kubeconfig()})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "failed" and f"kubectl -n {NS} scale deployment/notes --replicas=0" in got["result"]["message"]
    assert not any(m == "PATCH" for m, _ in cluster.requests)  # without stop_old OneMind never scales


def test_cutover_mismatch_puts_old_and_new_back(client, world, clock):
    svc, cluster, box = world
    plan = _copied(client, svc, clock)
    box.restore_failed = 2
    r = client.post(f"/v1/migrate/plans/{plan['id']}/cutover", headers=OWNER,
                    json={"kubeconfig": kubeconfig(), "stop_old": True})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "failed" and "did not verify" in got["result"]["message"]
    assert cluster.objects["deployments"][0]["spec"]["replicas"] == 1  # old app scaled back
    view = client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()
    assert view["state"] == "running" and view["old_replicas"] is None and view["busy_action_id"] is None


def test_cutover_refused_before_copy(client, world, clock):
    svc, _, _ = world
    plan = _imported(client, svc, clock)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/cutover", headers=OWNER, json={"kubeconfig": kubeconfig()})
    assert r.status_code == 409 and "staged" in r.json()["message"]


def test_copy_without_box_kubernetes_fails_cleanly(client, world, clock):
    svc, _, _ = world
    plan = _imported(client, svc, clock)
    svc.box = None
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER, json={"kubeconfig": kubeconfig()})
    got = _approve(client, r.json()["id"])
    assert got["state"] == "failed" and "ONEMIND_EXECUTOR=kubernetes" in got["result"]["message"]


def test_helper_preview_has_no_credentials(client, world):
    plan = _plan(client)
    pod = client.get(f"/v1/migrate/plans/{plan['id']}/helper", params={"pvc": "notes-data"}, headers=OWNER).json()
    env = {e["name"]: e["value"] for e in pod["spec"]["containers"][0]["env"]}
    assert "<password issued at copy>@" in env["RESTIC_REPOSITORY"]
    assert client.get(f"/v1/migrate/plans/{plan['id']}/helper", params={"pvc": "nope"}, headers=OWNER).status_code == 404


def test_restart_releases_plan_and_fails_running_copies(client, world, clock, settings):
    from fastapi.testclient import TestClient

    from onemind_core.app import create_app

    svc, _, _ = world
    plan = _imported(client, svc, clock)
    r = client.post(f"/v1/migrate/plans/{plan['id']}/copy", headers=OWNER, json={"kubeconfig": kubeconfig()})
    client.app.state.actions.spawn = lambda fn: None  # the gateway dies after dispatch
    client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert client.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()["busy_action_id"] == r.json()["id"]
    with TestClient(create_app(settings, clock=clock)) as c2:
        assert c2.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()["state"] == "outcome_unknown"
        assert c2.get(f"/v1/migrate/plans/{plan['id']}", headers=OWNER).json()["busy_action_id"] is None
