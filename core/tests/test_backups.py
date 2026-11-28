# SPDX-License-Identifier: Apache-2.0
"""Backups switched on (contract §12.12): actions, hooks, restore with undo, kit, shared PostgreSQL.

The agent (onemindd backup) and kubectl are fakes here; the Lima run in test/backup-wire/ drives the
real ones. Runs on SQLite and, with ONEMIND_TEST_DB_URL, on PostgreSQL.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from onemind_core.errors import ApiError
from onemind_core.backups.jobs import AgentError, canonical, sign_job
from onemind_core.backups.kit import check_group_ok
from onemind_core.backups.kube import Kube, KubeError, Workload
from onemind_core.backups.manifest import parse_backup, parse_database
from onemind_core.databases import DatabasesSettings, SharedPostgres

from conftest import ADULT, AGENT, OWNER
from test_identity_levels import root  # noqa: F401 - pytest fixture

NOTES = """apiVersion: onemind.app/v1alpha1
kind: App
metadata: {id: notes, name: Notes, version: "1.0.0", description: test, category: productivity, license: MIT, licenceClass: L1,
           source: "https://example.org/notes"}
spec:
  archs: [amd64, arm64]
  requires: {gpu: false, minMemoryMb: 64}
  manifests: manifests/
  updates: {channel: stable, automerge: none}
  backup:
    mode: hot
    pre: [{exec: {container: app, command: [sh, -c, "sync"]}}]
    post: {exec: {command: ["true"]}}
    exclude: [cache/]
    restore: {post: [{exec: {command: ["true"]}}]}
  database: {engine: postgres, secret: notes-db}
"""


class FakeAgent:
    """In-memory onemindd backup: records jobs, keeps snapshots per unit."""

    def __init__(self, clock):
        self.clock = clock
        self.jobs: list[tuple[str, dict, str | None]] = []
        self.snaps: list[dict] = []
        self.targets: list[dict] = []
        self.verified: dict[str, dict] = {}
        self.fail: dict[str, str] = {}
        self.run_state = "succeeded"
        self.content_bytes: dict[str, int] = {}

    def job(self, kind, params, *, action_id=None, timeout=None):
        canonical(params)  # what is sent must be signable
        self.jobs.append((kind, params, action_id))
        if kind in self.fail:
            raise AgentError(kind, self.fail[kind], reason="failed")
        if kind == "backup.run":
            units = params.get("units") or [f"app:{a['id']}" for a in params["apps"]] + ["system"]
            units = [u for u in units if u not in params.get("skip_units", [])]
            out = []
            content = {a["id"]: a["content"] for a in params["apps"] if a.get("content")}
            for u in units:
                sid = hashlib.sha256(f"{u}{len(self.snaps)}".encode()).hexdigest()
                tags = [f"content={content[u[4:]]}"] if u[4:] in content else []  # as units.go tags it
                self.snaps.append({"id": sid, "short_id": sid[:8], "unit": u, "app_id": u[4:] if u.startswith("app:") else "",
                                   "node_id": "n1", "taken_at": self.clock().isoformat(), "reason": params["reason"],
                                   "run_id": params["run_id"], "tags": tags, "paths": [f"/var/lib/rancher/k3s/storage/pvc-1_app-notes_data"]})
                out.append({"unit": u, "state": "succeeded", "snapshot_id": sid})
            return {"id": params["run_id"], "state": self.run_state, "units": out, "bytes_added": 42, "target_id": "dst_x"}
        if kind == "backup.snapshots":
            if params.get("box_id") and params.get("recovery_key") != getattr(self, "recovery_key", None):
                # the repository is sealed with the old box's device key: only the recovery key opens it
                raise AgentError(kind, "restic snapshots: exit 12: wrong password or no key found", reason="failed")
            return [s for s in reversed(self.snaps) if not params.get("unit") or s["unit"] == params["unit"]]
        if kind == "backup.status":
            units = {s["unit"]: {"state": "unverified", "last_success_at": s["taken_at"], "verified_at": None} for s in self.snaps}
            for u, v in self.verified.items():
                units[u] = {"state": "verified", "last_success_at": v["finished_at"], "verified_at": v["finished_at"]}
            box = {"state": "verified" if units and all(b["state"] == "verified" for b in units.values()) else
                   ("unverified" if units else "none")}
            return {"status": {"box": box, "units": units, "last_verified": self.verified, "fenced": False,
                               "copies": len(self.targets)},
                    "runs": [], "verifications": list(self.verified.values())}
        if kind == "backup.verify":
            out = []
            for u in params.get("units") or sorted({s["unit"] for s in self.snaps}):
                v = {"id": f"ver_{u}", "unit": u, "kind": "restore", "verdict": "passed", "snapshot_id": self.snaps[-1]["id"],
                     "started_at": self.clock().isoformat(), "finished_at": self.clock().isoformat(), "details": {"files": 3}}
                self.verified[u] = v
                out.append(v)
            return out
        if kind == "backup.restore":
            return {"app_id": params.get("app_id"), "stamp": params.get("stamp"), "items": [], "pre_restore_snapshot_id": "pre1"}
        if kind == "backup.content.size":
            return [{"id": a["id"], "bytes": self.content_bytes.get(a["id"], 0), "files": 1} for a in params["apps"]]
        if kind == "backup.tree":
            return [{"name": "notes.txt", "path": params["path"].rstrip("/") + "/notes.txt", "type": "file", "size": 2}]
        if kind == "backup.configure":
            self.targets = params["targets"]
            return {"targets": [target["id"] for target in self.targets]}
        if kind in ("backup.restore.finish", "backup.key.add"):
            return {"ok": True}
        raise AssertionError(kind)

    def file(self, params, chunk=65536):
        self.jobs.append(("backup.file", params, None))
        return iter([b"v", b"1"]), {"Content-Length": "2", "name": "notes.txt"}

    def kinds(self):
        return [k for k, _, _ in self.jobs]


class FakeKube(Kube):
    """kubectl stand-in: one running pod per app namespace, one bound claim."""

    def __init__(self, ready: bool = True):
        super().__init__("kubectl")
        self.calls: list[tuple] = []
        self.ready = ready
        self.fail_exec: set[str] = set()

    def run(self, args, stdin=None, timeout=None):
        self.calls.append(("run", tuple(args), stdin))
        return ""

    def exists(self, *args):
        return True

    def pvcs(self, namespace):
        if namespace == "onemind-db":
            return [{"claim": "data-postgres-0", "volume": "pvc-pg", "storage_class": "onemind-local"}]
        return [{"claim": "data", "volume": "pvc-1", "storage_class": "onemind-local"}]

    def running_pod(self, namespace, container=None):
        return f"{namespace}-pod"

    def exec(self, namespace, pod, command, *, container=None, stdin=None, timeout=None):
        self.calls.append(("exec", namespace, tuple(command), container, stdin))
        if command[0] in self.fail_exec:
            raise KubeError(f"{command[0]} exited 1")
        return ""

    def workloads(self, namespace):
        return [Workload("deployment", "notes", 1)]

    def scale(self, namespace, w, replicas):
        self.calls.append(("scale", namespace, w.name, replicas))

    def wait_no_pods(self, namespace, deadline_s):
        self.calls.append(("wait_no_pods", namespace))

    def fresh_ready(self, namespace, since, expected):
        return self.ready, {"fresh_pods": 1 if self.ready else 0, "ready": 1 if self.ready else 0, "expected": expected}

    def execs(self):
        return [c for c in self.calls if c[0] == "exec"]


@pytest.fixture
def notes_app(settings):
    d = settings.apps_dir / "notes"
    (d / "manifests").mkdir(parents=True)
    (d / "onemind.app.yaml").write_text(NOTES)
    (d / "manifests" / "kustomization.yaml").write_text("resources: []\n")
    return d


@pytest.fixture
def bk(client, clock, notes_app):
    """The backups service with fakes, switched on, notes installed."""
    app = client.app
    svc = app.state.backups
    svc.agent = FakeAgent(clock)
    svc.kube = FakeKube()
    pg = SharedPostgres(svc.kube, DatabasesSettings(), dry_run=False)
    svc.pg = pg
    svc.worker.inline = True
    svc.s = replace(svc.s, health_deadline_s=1)
    app.state.gateway.repo.set_app_state("notes", "installed", clock.now)
    return svc


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def approve(client, action_id):
    r = client.post(f"/v1/actions/{action_id}/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


def add_usb(client, bk):
    r = client.post("/v1/backups/destinations", headers=OWNER,
                    json={"kind": "usb", "label": "USB disk", "config": {"usb_uuid": "1234-ABCD"}})
    assert r.status_code == 202, r.text
    return approve(client, r.json()["id"])


# ---- switched off ----------------------------------------------------------------------------
def test_disabled_status_and_unavailable(client):
    st = client.get("/v1/backups/status", headers=OWNER).json()
    assert st["health"] == "not_configured" and st["agent"] == "off"
    assert st["setup"]["blocking"] == ["emergency_kit"]
    r = client.post("/v1/backups/runs", headers=OWNER, json={})
    assert r.status_code == 503 and r.json()["error"] == "unavailable" and r.json()["reason"] == "backups_disabled"
    assert client.get("/v1/backups/status", headers=GUEST_HEADERS).status_code == 403


GUEST_HEADERS = {"Authorization": "Bearer dev-guest-token-change-me"}


# ---- destinations ----------------------------------------------------------------------------
def test_destination_credentials_are_write_only(client, bk, settings):
    r = client.post("/v1/backups/destinations", headers=OWNER, json={
        "kind": "box", "label": "Garage box", "config": {"url": "https://garage.example:8000/b/", "user": "box1"},
        "credentials": {"password": "pw-should-never-be-stored"}})
    assert r.status_code == 202 and r.json()["state"] == "awaiting_approval"
    assert "credentials" not in json.dumps(r.json()["params"])
    assert "backup.configure" not in bk.agent.kinds(), "nothing changes before the owner approves"
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded", done
    kind, params, _ = bk.agent.jobs[-1]
    assert kind == "backup.configure"
    assert params["targets"][0]["kind"] == "node" and params["targets"][0]["append_only"] is True
    assert params["secrets"] == {params["targets"][0]["id"]: {"password": "pw-should-never-be-stored"}}
    listed = client.get("/v1/backups/destinations", headers=OWNER).json()
    assert listed[0]["primary"] is True and listed[0]["label"] == "Garage box"
    for blob in (json.dumps(listed), settings.audit_path.read_text(), json.dumps(client.get("/v1/actions", headers=OWNER).json())):
        assert "pw-should-never-be-stored" not in blob
    assert '"credentials": "provided"' in settings.audit_path.read_text() or '"credentials":"provided"' in settings.audit_path.read_text()


def test_destination_rules(client, bk):
    r = client.post("/v1/backups/destinations", headers=OWNER, json={"kind": "s3", "label": "B2", "config": {"endpoint": "http://x", "bucket": "b"}})
    assert r.status_code == 422
    assert client.post("/v1/backups/destinations", headers=AGENT, json={"kind": "usb", "label": "x", "config": {"usb_uuid": "1"}}).status_code == 403
    add_usb(client, bk)
    dest = client.get("/v1/backups/destinations", headers=OWNER).json()[0]["id"]
    r = client.delete(f"/v1/backups/destinations/{dest}", headers=OWNER)
    assert r.status_code == 202
    approve(client, r.json()["id"])
    assert client.get("/v1/backups/destinations", headers=OWNER).json() == []
    assert bk.agent.jobs[-1][1]["targets"] == []


# ---- runs and hooks ----------------------------------------------------------------------------
def test_cancelled_or_unbudgeted_agent_is_refused_on_the_backup_routes(client, bk):
    """AIG-03 (#167): cancel and budget hold on feature routes too, not only POST /v1/actions."""
    add_usb(client, bk)
    client.post("/v1/agents/hermes/cancel", headers=OWNER)
    for path in ("/v1/backups/runs", "/v1/backups/verify"):
        r = client.post(path, headers=AGENT, json={})
        assert r.status_code == 403 and r.json()["reason"] == "agent_cancelled", path
    client.post("/v1/agents/hermes/resume", headers=OWNER)
    client.put("/v1/agents/hermes/budget", json={"budget_per_day": 0}, headers=OWNER)
    assert client.post("/v1/backups/runs", headers=AGENT, json={}).status_code == 429
    assert client.post("/v1/backups/runs", headers=OWNER, json={}).status_code in (200, 202)


def test_agent_requests_a_run_but_only_the_owner_approves(client, bk):
    add_usb(client, bk)
    r = client.post("/v1/backups/runs", headers=AGENT, json={"scope": {"app_id": "notes"}})
    assert r.status_code == 202 and r.json()["state"] == "awaiting_approval"
    assert r.json()["approved_by"] is None
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    before = len(client.get("/v1/actions", headers=OWNER).json())
    for path in ("/v1/backups/runs", "/v1/backups/verify"):
        assert client.post(path, headers=AGENT, json={"approve": True}).status_code == 403
    assert len(client.get("/v1/actions", headers=OWNER).json()) == before, "a refused owner shortcut files nothing (§12.1)"
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded", done
    assert done["approved_by"] == done["decided_by"]["id"] == "owner"
    assert client.get(f"/v1/actions/{r.json()['id']}", headers=OWNER).json()["approved_by"] == "owner"


def test_run_runs_hooks_inside_the_app_and_dumps_its_database(client, bk):
    add_usb(client, bk)
    r = client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    assert r.status_code == 202 and r.json()["state"] == "succeeded", r.text
    execs = bk.kube.execs()
    pre = [c for c in execs if c[1] == "app-notes" and c[2][0] == "sh"]
    assert pre and pre[0][3] == "app", "the pre hook runs in the named container of the app's own pod"
    assert any(c[1] == "onemind-db" and c[2][0] == "pg_dump" for c in execs)
    assert execs.index(pre[0]) < max(i for i, c in enumerate(execs) if c[2][0] == "true"), "post runs after pre"
    kind, params, action_id = next(j for j in bk.agent.jobs if j[0] == "backup.run")
    notes = params["apps"][0]
    assert notes["volumes"] == [{"namespace": "app-notes", "claim": "data", "volume": "pvc-1"}]
    assert notes["files"][0]["path"] == "onemind-dumps/app_notes.pgdump" and notes["excludes"] == ["cache/"]
    assert action_id == r.json()["id"]
    run = client.get("/v1/backups/runs", headers=OWNER).json()[0]
    assert run["state"] == "succeeded" and run["action_id"] == r.json()["id"] and run["hooks"]


def test_failed_pre_hook_leaves_the_app_out_instead_of_copying_it_inconsistently(client, bk):
    add_usb(client, bk)
    bk.kube.fail_exec.add("sh")
    r = client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    assert r.json()["state"] == "failed"
    params = next(p for k, p, _ in bk.agent.jobs if k == "backup.run")
    assert params["skip_units"] == ["app:notes"]
    run = client.get("/v1/backups/runs", headers=OWNER).json()[0]
    assert run["state"] == "partial"
    assert {"unit": "app:notes", "state": "failed", "error": "pre hook sh failed: sh exited 1"} in run["units"]


def test_schedule_fires_once_per_slot(client, bk, clock):
    assert bk.schedule_tick() is False, "no destination yet"
    add_usb(client, bk)
    bk._last_slot = None
    assert bk.schedule_tick() is True
    assert bk.schedule_tick() is False
    clock.advance(3600)
    assert bk.schedule_tick() is True
    assert [r["reason"] for r in client.get("/v1/backups/runs", headers=OWNER).json()] == ["scheduled", "scheduled"]


# ---- status, verify, browse --------------------------------------------------------------------
def test_badge_turns_green_after_a_scratch_restore(client, bk):
    add_usb(client, bk)
    client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    st = client.get("/v1/backups/status", headers=AGENT).json()
    assert st["health"] == "ok" and st["badges"]["apps"]["notes"]["state"] == "unverified"
    r = client.post("/v1/backups/verify", headers=AGENT, json={})
    assert r.status_code == 202 and r.json()["state"] == "awaiting_approval"
    # The agent read the status over REST first, so its request is tainted (AIG-04, #168): the card
    # carries the note and the owner approves the exact plan fingerprint.
    assert r.json()["plan"]["taint"]["sources"] == ["rest:GET /v1/backups/status"]
    ok = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER,
                     json={"plan_sha256": r.json()["plan_sha256"]})
    assert ok.status_code == 200, ok.text
    st = client.get("/v1/backups/status", headers=OWNER).json()
    assert st["badges"]["apps"]["notes"]["state"] == "verified" and st["badges"]["box"]["state"] == "verified"
    assert st["last_verified_restore_at"] is not None
    v = client.get("/v1/backups/verifications", headers=OWNER).json()
    assert v and v[0]["mode"] == "scratch_restore" and v[0]["result"] == "pass"


def test_browse_is_owner_only_and_audited(client, bk, settings):
    add_usb(client, bk)
    client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    snap = client.get("/v1/backups/snapshots?app_id=notes", headers=ADULT).json()[0]
    assert snap["unit"] == "app:notes"
    path = snap["paths"][0]
    assert client.get(f"/v1/backups/snapshots/{snap['id']}/tree", params={"path": path}, headers=ADULT).status_code == 403
    assert client.get(f"/v1/backups/snapshots/{snap['id']}/tree", params={"path": path}, headers=AGENT).status_code == 403
    tree = client.get(f"/v1/backups/snapshots/{snap['id']}/tree", params={"path": path}, headers=OWNER).json()
    assert tree[0]["name"] == "notes.txt"
    f = client.get(f"/v1/backups/snapshots/{snap['id']}/file", params={"path": tree[0]["path"]}, headers=OWNER)
    assert f.status_code == 200 and f.content == b"v1" and "notes.txt" in f.headers["content-disposition"]
    audit = settings.audit_path.read_text()
    assert '"event":"backup.browse"' in audit.replace(" ", "") and '"event":"backup.download"' in audit.replace(" ", "")


# ---- restore -------------------------------------------------------------------------------------
def restorable(client, bk):
    add_usb(client, bk)
    client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    return client.get("/v1/backups/snapshots?app_id=notes", headers=OWNER).json()[0]


def test_restore_is_owner_requested_planned_and_approved(client, bk):
    snap = restorable(client, bk)
    assert client.post("/v1/restores", headers=AGENT, json={"snapshot_id": snap["id"], "scope": {"app_id": "notes"}}).status_code == 403
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": {"app_id": "notes"}})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["state"] == "awaiting_approval" and body["type"] == "backup.restore"
    plan = body["restore"]["plan"]
    assert plan["database"] is True and "pre-restore snapshot" in plan["steps"][0]
    assert "backup.restore" not in bk.agent.kinds(), "nothing is restored before approval"
    jobs_before = len(bk.agent.jobs)

    done = approve(client, body["id"])
    assert done["state"] == "succeeded", done
    seq = [(k, p.get("reason") or p.get("scope") or p.get("commit")) for k, p, _ in bk.agent.jobs[jobs_before:]]
    assert seq[0] == ("backup.run", "pre-restore"), "the undo point comes first"
    assert seq[1][0] == "backup.restore" and seq[2] == ("backup.restore.finish", True)
    calls = [c for c in bk.kube.calls if c[0] in ("scale", "exec")]
    stop = calls.index(("scale", "app-notes", "notes", 0))
    restore_db = next(i for i, c in enumerate(calls) if c[0] == "exec" and c[2][0] == "pg_restore")
    start = calls.index(("scale", "app-notes", "notes", 1))
    assert stop < restore_db < start, "stop, recreate the database, start"
    assert any(c[0] == "exec" and c[2][0] == "pg_dump" for c in calls[stop:restore_db]), \
        "the database is dumped again once the app is stopped, so a rollback loses no writes"
    rst = client.get("/v1/restores", headers=OWNER).json()[0]
    assert rst["state"] == "succeeded" and rst["pre_restore_snapshot_id"] and rst["health_gate"]["verdict"] == "pass"


def test_restore_that_does_not_come_back_healthy_is_rolled_back(client, bk):
    snap = restorable(client, bk)
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": {"app_id": "notes"}})
    bk.kube.ready = False
    done = approve(client, r.json()["id"])
    assert done["state"] == "failed" and "previous data is back" in done["result"]["message"]
    finish = [p for k, p, _ in bk.agent.jobs if k == "backup.restore.finish"]
    assert finish == [{"app_id": "notes", "stamp": finish[0]["stamp"], "commit": False}]
    assert sum(1 for c in bk.kube.execs() if c[2][0] == "pg_restore") == 2, "restored dump, then the previous one"
    rst = client.get("/v1/restores", headers=OWNER).json()[0]
    assert rst["state"] == "failed" and rst["health_gate"]["verdict"] == "fail"


def test_failed_pre_restore_snapshot_changes_nothing(client, bk):
    snap = restorable(client, bk)
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": {"app_id": "notes"}})
    bk.agent.run_state = "failed"
    done = approve(client, r.json()["id"])
    assert done["state"] == "failed" and "nothing was changed" in done["result"]["message"]
    assert "backup.restore" not in bk.agent.kinds()
    assert not any(c[0] == "scale" and c[3] == 0 for c in bk.kube.calls if c[0] == "scale")


def test_restore_refusals(client, bk):
    snap = restorable(client, bk)
    system = next(s for s in client.get("/v1/backups/snapshots", headers=OWNER).json() if s["unit"] == "system")
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": system["id"], "scope": {"app_id": "notes"}})
    assert r.status_code == 409 and "not app:notes" in r.json()["message"]
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": "box"})
    assert r.status_code == 409 and "onboarding" in r.json()["message"]
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": {"app_id": "notes", "path": "/etc/passwd"}})
    assert r.status_code == 409
    # Inside the snapshot by prefix, somewhere else once cleaned: the card would not show what runs.
    for bad in ("/../etc/passwd", "/./x", "//x"):
        r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"],
                        "scope": {"app_id": "notes", "path": snap["paths"][0] + bad}})
        assert r.status_code == 422, (bad, r.text)


def test_agent_refusal_is_unavailable_not_a_crash(client, bk):
    add_usb(client, bk)
    bk.agent.fail["backup.snapshots"] = "no destination is set up yet"
    r = client.get("/v1/backups/snapshots", headers=OWNER)
    assert r.status_code == 503 and r.json()["error"] == "unavailable" and r.json()["reason"] == "agent_failed"


def test_snapshots_before_any_destination_is_an_empty_list_with_a_reason_not_a_wait(client, bk):
    r = client.get("/v1/backups/snapshots", headers=OWNER)
    assert r.status_code == 200 and r.json() == []
    assert r.headers["OneMind-Reason"] == "no backup destination yet"
    assert not any(j[0] == "backup.snapshots" for j in bk.agent.jobs)  # no repository lookup
    add_usb(client, bk)
    r = client.get("/v1/backups/snapshots", headers=OWNER)
    assert r.status_code == 200 and r.json() == [] and "OneMind-Reason" not in r.headers
    assert any(j[0] == "backup.snapshots" for j in bk.agent.jobs)  # with a destination the agent is asked


def test_agent_only_destination_keeps_snapshots_discoverable_and_restorable(client, bk):
    snap = restorable(client, bk)
    destination, = bk.repo.destinations()
    bk.repo.remove_destination(destination.id)  # simulate losing the row after the agent saved its config
    assert not bk.repo.destinations()
    assert [target["id"] for target in bk.agent.targets] == [destination.id]

    listed = client.get("/v1/backups/snapshots", params={"app_id": "notes"}, headers=OWNER)
    assert listed.status_code == 200 and listed.json() == [snap]
    assert "OneMind-Reason" not in listed.headers
    detail = client.get(f"/v1/backups/snapshots/{snap['id']}", headers=OWNER)
    assert detail.status_code == 200 and detail.json() == snap
    restore = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": {"app_id": "notes"}})
    assert restore.status_code == 202, restore.text
    assert restore.json()["state"] == "awaiting_approval"
    assert restore.json()["restore"]["plan"]["snapshot"]["id"] == snap["id"]
    assert "backup.restore" not in bk.agent.kinds()


def test_snapshot_list_without_destinations_preserves_agent_refusal(client, bk):
    bk.agent.fail["backup.status"] = "could not read backup status"
    r = client.get("/v1/backups/snapshots", headers=OWNER)
    assert r.status_code == 503 and r.json()["reason"] == "agent_failed"
    assert "OneMind-Reason" not in r.headers


def test_snapshot_list_reason_matches_the_listing_when_a_destination_is_removed(client, bk, monkeypatch):
    add_usb(client, bk)
    destination, = bk.repo.destinations()
    job = bk.agent.job

    def remove_after_listing(kind, params, **kwargs):
        out = job(kind, params, **kwargs)
        if kind == "backup.snapshots":
            job("backup.configure", {"targets": []})
            bk.repo.remove_destination(destination.id)
        return out

    monkeypatch.setattr(bk.agent, "job", remove_after_listing)
    r = client.get("/v1/backups/snapshots", headers=OWNER)
    assert r.status_code == 200 and r.json() == []
    assert "OneMind-Reason" not in r.headers
    assert not bk.repo.destinations()


def test_snapshots_with_backups_switched_off_stay_503_even_without_a_destination(client):
    r = client.get("/v1/backups/snapshots", headers=OWNER)
    assert r.status_code == 503 and r.json()["reason"] == "backups_disabled" and r.headers["retry-after"] == "30"


def test_destination_request_replays_with_the_same_idempotency_key(client, bk):
    body = {"kind": "usb", "label": "USB disk", "config": {"usb_uuid": "1234-ABCD"}}
    first = client.post("/v1/backups/destinations", headers={**OWNER, "Idempotency-Key": "k-1"}, json=body)
    again = client.post("/v1/backups/destinations", headers={**OWNER, "Idempotency-Key": "k-1"}, json=body)
    assert first.status_code == again.status_code == 202, again.text
    assert again.json()["id"] == first.json()["id"] and again.headers["OneMind-Idempotent-Replay"] == "true"
    other = client.post("/v1/backups/destinations", headers={**OWNER, "Idempotency-Key": "k-1"}, json={**body, "label": "Other"})
    assert other.status_code == 409


def test_restore_one_path(client, bk):
    snap = restorable(client, bk)
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"],
                    "scope": {"app_id": "notes", "path": snap["paths"][0] + "/notes.txt"}})
    assert r.status_code == 202 and "stopped" in r.json()["restore"]["plan"]["downtime"]
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded"
    assert bk.agent.jobs[-1][1]["scope"] == "path"
    # The app is stopped while root writes into its folder (a running app could swap a symlink in).
    seq = [c[:4] for c in bk.kube.calls if c[0] == "scale"]
    assert seq == [("scale", "app-notes", "notes", 0), ("scale", "app-notes", "notes", 1)]


def test_path_restore_that_cannot_stop_the_app_changes_nothing(client, bk):
    snap = restorable(client, bk)
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"],
                    "scope": {"app_id": "notes", "path": snap["paths"][0] + "/notes.txt"}})
    before = len(bk.agent.jobs)

    def no_stop(ns, w, n):
        raise KubeError("scale refused")
    bk.kube.scale = no_stop
    done = approve(client, r.json()["id"])
    assert done["state"] == "failed", done
    assert "backup.restore" not in [k for k, _, _ in bk.agent.jobs[before:]]


def test_app_restore_asks_the_agent_to_refuse_a_snapshot_without_the_dump(client, bk):
    snap = restorable(client, bk)
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": {"app_id": "notes"}})
    approve(client, r.json()["id"])
    job = next(p for k, p, _ in bk.agent.jobs if k == "backup.restore" and p.get("scope") == "app")
    assert job["strict_files"] is True, "an app with a database is never restored files-only"


def test_cold_backup_scales_every_stopped_app_back_up_when_stopping_fails_midway(client, bk, monkeypatch):
    from onemind_core.backups import service as svc_mod
    real = svc_mod.backup_spec
    monkeypatch.setattr(svc_mod, "backup_spec", lambda app: replace(real(app), mode="cold"))
    add_usb(client, bk)
    two = [Workload("deployment", "web", 2), Workload("statefulset", "worker", 3)]
    bk.kube.workloads = lambda ns: two
    real_scale = bk.kube.scale

    def flaky(ns, w, n):
        if n == 0 and w.name == "worker":
            raise KubeError("scale refused")
        real_scale(ns, w, n)
    bk.kube.scale = flaky
    bk.kube.calls.clear()
    r = client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    assert r.status_code == 202, r.text
    ups = {c[2]: c[3] for c in bk.kube.calls if c[0] == "scale" and c[3] > 0}
    assert ups == {"web": 2, "worker": 3}, "every workload that may have been stopped is scaled back to its replicas"


# ---- emergency kit ---------------------------------------------------------------------------------
def test_separate_kit_request_on_a_box_without_passkeys_stays_pending(client, bk):
    """Option A (founder, 2026-11-28): a separately approved kit goes only to the approving owner session.
    A static owner token can file and approve, but it has no session, so nothing it sends releases the page."""
    assert not client.app.state.identity.passkeys_active()
    headers = {**OWNER, "Idempotency-Key": "separate-kit-request"}
    body = {"approve": False}
    request = client.post("/v1/backups/kit", headers=headers, json=body)
    assert request.status_code == 202, request.text
    action = request.json()
    assert action["state"] == "awaiting_approval" and "one_time" not in action
    assert client.get("/v1/backups/kit", headers=OWNER).json()["state"] == "missing"
    assert client.post("/v1/backups/kit", headers=headers, json=body).status_code == 202
    assert approve(client, action["id"])["state"] == "succeeded"
    # The old private delivery token is gone: the field is refused, and repeating the request never delivers.
    old = client.post("/v1/backups/kit", headers=headers, json={"approve": False, "delivery_token": secrets.token_hex(32)})
    assert old.status_code == 422 and "owner_key" not in old.text
    again = client.post("/v1/backups/kit", headers=headers, json=body)
    assert again.status_code == 409 and "owner_key" not in again.text
    claim = client.post(f"/v1/backups/kit/{action['id']}/claim", headers=OWNER)
    assert claim.status_code == 403 and "owner_key" not in claim.text


def test_emergency_kit_is_shown_once_and_must_be_typed_back(client, bk, settings):
    assert client.post("/v1/backups/kit", headers=ADULT).status_code == 403
    add_usb(client, bk)
    r = client.post("/v1/backups/kit", headers=OWNER, json=None)
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    one = r.json()["one_time"]
    assert len(one["groups"]) == 13 and all(len(g) == 4 for g in one["groups"])
    assert check_group_ok(one["groups"], one["check"])
    assert one["owner_key"] == "-".join(one["groups"]) and one["owner_key"] in one["text"]
    assert bk.agent.jobs[-1][:2] == ("backup.key.add", {"which": "owner", "key": one["owner_key"]})
    kit = client.get("/v1/backups/kit", headers=OWNER).json()
    assert kit["state"] == "issued" and len(kit["positions"]) == 2 and "owner_key" not in kit
    assert client.get("/v1/backups/status", headers=OWNER).json()["setup"]["blocking"] == ["emergency_kit"]

    wrong = {str(p): "AAAA" for p in kit["positions"]}
    assert client.post("/v1/backups/kit/confirm", headers=OWNER, json={"answers": wrong}).status_code == 409
    right = {str(p): one["groups"][p - 1].lower() for p in kit["positions"]}
    assert client.post("/v1/backups/kit/confirm", headers=OWNER, json={"answers": right}).json()["state"] == "confirmed"
    assert client.get("/v1/backups/status", headers=OWNER).json()["setup"]["blocking"] == []

    # The key is nowhere on the box: not in the ledger, not in the audit log.
    for blob in (json.dumps(client.get("/v1/actions", headers=OWNER).json()), settings.audit_path.read_text()):
        assert one["owner_key"] not in blob and one["groups"][0] + "-" + one["groups"][1] not in blob
    if settings.db_url.startswith("sqlite:///"):
        assert one["owner_key"].encode() not in open(settings.db_url[len("sqlite:///"):], "rb").read()


# ---- shared PostgreSQL --------------------------------------------------------------------------------
def test_install_creates_the_database_role_and_secret_before_the_app(client, bk, settings, clock):
    from conftest import action_body, write_scan

    write_scan(notes_dir := settings.apps_dir / "notes", clock.now - timedelta(days=1))
    assert notes_dir.exists()
    gw = client.app.state.gateway
    gw.repo.set_app_state("notes", None, clock.now)
    client.app.state.databases.kube = bk.kube
    client.app.state.databases.dry_run = False
    r = client.post("/v1/actions", headers=OWNER, json=action_body(clock, app_id="notes"))
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded", done
    steps = done["result"]["steps"]
    assert [s["hook"] for s in steps if "hook" in s][-1] == "database"
    psql = next(c for c in bk.kube.execs() if c[2][0] == "psql")
    assert "CREATE ROLE app_notes LOGIN" in psql[4] and "REVOKE ALL ON DATABASE app_notes FROM PUBLIC" in psql[4]
    assert "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC" in psql[4]
    password = psql[4].split("PASSWORD '")[1].split("'")[0]
    assert len(password) == 48
    secret = next(c for c in bk.kube.calls if c[0] == "run" and "--server-side" in c[1] and '"notes-db"' in (c[2] or ""))
    data = json.loads(secret[2])["data"]
    assert base64.b64decode(data["PGPASSWORD"]).decode() == password
    assert base64.b64decode(data["PGHOST"]).decode() == "postgres.onemind-db.svc.cluster.local"
    for blob in (json.dumps(done), settings.audit_path.read_text()):
        assert password not in blob
    dbs = client.get("/v1/databases", headers=OWNER).json()
    assert dbs == [{"app_id": "notes", "engine": "postgres", "database": "app_notes", "role": "app_notes", "secret": "notes-db",
                    "namespace": "app-notes", "host": "postgres.onemind-db.svc.cluster.local", "port": 5432, "installed": True}]
    assert client.get("/v1/databases", headers=AGENT).status_code == 403


def test_install_fails_cleanly_when_the_database_cannot_be_prepared(client, bk, settings, clock):
    from conftest import action_body, write_scan

    write_scan(settings.apps_dir / "notes", clock.now - timedelta(days=1))
    client.app.state.gateway.repo.set_app_state("notes", None, clock.now)
    client.app.state.databases.kube = bk.kube
    client.app.state.databases.dry_run = False
    bk.kube.fail_exec.add("psql")
    r = client.post("/v1/actions", headers=OWNER, json=action_body(clock, app_id="notes"))
    done = approve(client, r.json()["id"])
    assert done["state"] == "failed" and "install preparation failed" in done["result"]["message"]
    assert client.app.state.gateway.executor.calls == [], "the app's manifests are never applied"


def test_noop_executor_only_records_what_it_would_do(client, notes_app, clock, settings):
    from conftest import action_body, write_scan

    write_scan(notes_app, clock.now - timedelta(days=1))
    r = client.post("/v1/actions", headers=OWNER, json=action_body(clock, app_id="notes"))
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded"
    assert any("would" in s and "app_notes" in s["would"] for s in done["result"]["steps"])


# ---- pieces ------------------------------------------------------------------------------------------
def test_canonical_matches_go_vector():
    obj = {"z": 1, "a": [True, None, -7, "x"],
           "m": {"b": "Café ☃ \U0001F600", "a": "tab\tnl\nq\"bs\\ctl\x01del\x7f/slash<>&"}, "é": 0}
    want = ('{"a":[true,null,-7,"x"],"m":{"a":"tab\\tnl\\nq\\"bs\\\\ctl\\u0001del\\u007f/slash<>&",'
            '"b":"Caf\\u00e9 \\u2603 \\ud83d\\ude00"},"z":1,"\\u00e9":0}')
    assert canonical(obj).decode() == want  # internal/backup/job_test.go canonicalVectorOut
    with pytest.raises(TypeError):
        canonical({"x": 1.5})


def test_signed_job_verifies():
    key = Ed25519PrivateKey.generate()
    now = datetime(2026, 11, 12, 10, 0, tzinfo=datetime.now().astimezone().tzinfo).astimezone()
    env = sign_job(key, "backup.run", {"reason": "manual", "apps": []}, now, action_id="a1")
    sig = base64.b64decode(env.pop("sig"))
    key.public_key().verify(sig, canonical(env))
    assert env["params_sha256"] == "sha256:" + hashlib.sha256(canonical(env["params"])).hexdigest()
    assert env["job_id"].startswith("job_") and env["expires_at"] > env["issued_at"]


def test_manifest_blocks():
    spec, errs = parse_backup({"backup": {"mode": "warm", "pre": [{"exec": {"command": "rm -rf /"}}],
                                          "sqlite": [{"claim": "data", "path": "../x"}], "exclude": ["/etc"]}})
    assert len(errs) == 4
    spec, errs = parse_backup({"backup": {"pre": {"exec": {"container": "db", "command": ["pg_dump", "x"]}, "timeout_s": 60}}})
    assert errs == [] and spec.pre[0].container == "db" and spec.pre[0].timeout_s == 60
    assert parse_database({"database": {"engine": "mysql", "secret": "Bad_Name"}})[1]
    assert parse_database({"database": {"secret": "x-db"}})[0].secret == "x-db"


def test_schema_accepts_backup_and_database_blocks():
    """sdk/schema: spec.backup (contract §12.18) and spec.database on a real seed manifest."""
    from pathlib import Path

    import yaml
    from jsonschema.validators import validator_for

    root = Path(__file__).resolve().parents[2]
    schema = json.loads((root / "sdk/schema/onemind.app.schema.json").read_text())
    v = validator_for(schema)(schema)
    doc = yaml.safe_load((root / "apps/uptime-kuma/onemind.app.yaml").read_text())
    assert list(v.iter_errors(doc)) == []
    doc["spec"]["backup"] = yaml.safe_load(NOTES)["spec"]["backup"]
    doc["spec"]["database"] = {"engine": "postgres", "secret": "kuma-db"}
    assert list(v.iter_errors(doc)) == []
    doc["spec"]["backup"]["pre"] = {"exec": {"command": "sh -c 'rm -rf /'"}}
    doc["spec"]["backup"]["exclude"] = ["../../etc"]
    doc["spec"]["database"] = {"engine": "mysql", "secret": "x"}
    assert len(list(v.iter_errors(doc))) == 3


def test_fresh_ready_counts_a_pod_started_in_the_same_second():
    """Kubernetes timestamps have whole seconds; a restart at .38 s must still see its pod."""
    from datetime import UTC

    class Pods(Kube):
        def pods(self, namespace):
            return [
                {"metadata": {"creationTimestamp": "2026-11-12T10:35:48Z"},
                 "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
                {"metadata": {"creationTimestamp": "2026-11-12T10:35:47Z"},
                 "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
            ]

    since = datetime(2026, 11, 12, 10, 35, 48, 382955, tzinfo=UTC)
    ok, info = Pods().fresh_ready("app-x", since, 1)
    assert ok and info == {"fresh_pods": 1, "ready": 1, "expected": 1}
    assert Pods().fresh_ready("app-x", since, 2)[0] is False, "the pod from the second before is not fresh"


# ---- review fixes: dump file permissions ---------------------------------------------------------
def test_dump_file_is_created_private_and_a_failed_dump_leaves_no_tmp(client, bk):
    bk.pg.dump("notes")
    cmds = [c[2] for c in bk.kube.calls if c[0] == "exec" and c[1] == "onemind-db"]
    assert any(c[0] == "sh" and "umask 077" in c[2] and "chmod 700" in c[2] for c in cmds), "dump folder is 0700"
    create = next(i for i, c in enumerate(cmds) if c[0] == "sh" and ": >" in c[2])
    dump = next(i for i, c in enumerate(cmds) if c[0] == "pg_dump")
    assert create < dump, "the file exists at 0600 before pg_dump writes into it"
    assert cmds[dump][-1].endswith(".pgdump.tmp")
    bk.kube.calls.clear()
    bk.kube.fail_exec.add("pg_dump")
    with pytest.raises(KubeError):
        bk.pg.dump("notes")
    last = [c[2] for c in bk.kube.calls if c[0] == "exec"][-1]
    assert last[:2] == ("rm", "-f") and last[2].endswith(".pgdump.tmp"), "the half-written dump is deleted"


# ---- first-run restore candidates (UMB-P08) -------------------------------------------------
def _fresh(client, bk):
    """A fresh box: a destination is configured but no app is installed."""
    dst = add_usb(client, bk)
    did = client.get("/v1/backups/destinations", headers=OWNER).json()[0]["id"]
    bk.gw.repo.set_app_state("notes", "uninstalled", bk.gw.clock())
    return did


def test_restore_candidates_group_by_run_and_refuse_a_box_with_apps(client, bk):
    add_usb(client, bk)
    did = client.get("/v1/backups/destinations", headers=OWNER).json()[0]["id"]
    body = {"destination_id": did}
    # notes is installed (the fixture): a populated box restores per app, not at first run.
    r = client.post("/v1/onboarding/restore/candidates", headers=OWNER, json=body)
    assert r.status_code == 409, r.text
    assert "already has apps" in r.json()["message"]

    bk.gw.repo.set_app_state("notes", "uninstalled", bk.gw.clock())
    r = client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    assert r.status_code == 202, r.text
    bk.agent.snaps.extend([
        {"id": "a" * 64, "short_id": "aaaaaaaa", "unit": "system", "app_id": "", "node_id": "old", "taken_at": "2026-11-10T10:00:00Z",
         "reason": "scheduled", "run_id": "run_old", "tags": [], "paths": ["/etc"]},
        {"id": "b" * 64, "short_id": "bbbbbbbb", "unit": "app:notes", "app_id": "notes", "node_id": "old", "taken_at": "2026-11-10T10:01:00Z",
         "reason": "scheduled", "run_id": "run_old", "tags": [], "paths": ["/x"]},
    ])
    r = client.post("/v1/onboarding/restore/candidates", headers=OWNER, json=body)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    pts = r.json()["points"]
    old = next(p for p in pts if p["run_id"] == "run_old")
    assert old["system"] is True and old["apps"] == ["notes"] and len(old["snapshot_ids"]) == 2
    assert [p["taken_at"] for p in pts] == sorted((p["taken_at"] for p in pts), reverse=True)
    sent = [j for j in bk.agent.jobs if j[0] == "backup.snapshots" and j[1].get("target_id") == did]
    assert sent, "the destination id must reach the agent"


def test_restore_candidates_passes_box_id_and_is_owner_only(client, bk):
    did = _fresh(client, bk)
    bk.agent.recovery_key = "K" * 40
    r = client.post("/v1/onboarding/restore/candidates", headers=OWNER, json={"destination_id": did, "box_id": "old-box", "recovery_key": "K" * 40})
    assert r.status_code == 200, r.text
    assert any(j[0] == "backup.snapshots" and j[1].get("box_id") == "old-box" for j in bk.agent.jobs)
    for who in (ADULT, AGENT):
        assert client.post("/v1/onboarding/restore/candidates", headers=who, json={"destination_id": did}).status_code == 403
    assert client.post("/v1/onboarding/restore/candidates", headers=OWNER, json={"destination_id": "dst_0000000000000000"}).status_code == 404
    assert client.post("/v1/onboarding/restore/candidates", headers=OWNER, json={"destination_id": did, "box_id": "a b;"}).status_code == 422


def test_restore_candidates_unavailable_when_backups_off(client):
    r = client.post("/v1/onboarding/restore/candidates", headers=OWNER, json={"destination_id": "dst_0000000000000000"})
    assert r.status_code == 503 and r.json()["reason"] == "backups_disabled"


def test_restore_candidates_other_box_needs_the_recovery_key(client, bk, settings):
    did = _fresh(client, bk)
    bk.agent.recovery_key = "RK" * 20
    # a box id without the key cannot open the repository: refused before the agent is asked
    r = client.post("/v1/onboarding/restore/candidates", headers=OWNER, json={"destination_id": did, "box_id": "old-box"})
    assert r.status_code == 422, r.text
    assert not any(j[0] == "backup.snapshots" for j in bk.agent.jobs)
    # the wrong key: the agent's failure is a 409, and the key is never echoed or audited
    bad = "XX" * 20
    r = client.post("/v1/onboarding/restore/candidates", headers=OWNER,
                    json={"destination_id": did, "box_id": "old-box", "recovery_key": bad})
    assert r.status_code == 409 and bad not in r.text, r.text
    # the right key reaches the agent with the box id and lists the points
    r = client.post("/v1/onboarding/restore/candidates", headers=OWNER,
                    json={"destination_id": did, "box_id": "old-box", "recovery_key": bk.agent.recovery_key})
    assert r.status_code == 200, r.text
    assert "RK" * 20 not in r.text and r.headers["cache-control"] == "no-store"
    audit = settings.audit_path.read_text()
    assert "onboarding.restore.candidates" in audit and "RK" * 20 not in audit and bad not in audit
    # short or multi-line keys are refused
    for k in ("short", "A" * 40 + "\nB"):
        r = client.post("/v1/onboarding/restore/candidates", headers=OWNER,
                        json={"destination_id": did, "box_id": "old-box", "recovery_key": k})
        assert r.status_code == 422
        assert k.strip() not in r.text  # a refused key is not echoed back either


# ---- first-run restore of an app from another box's backup (UMB-P08, #145) --------------------------
def _other_box(client, bk, key="RK" * 20):
    """The old box's points sit on the destination; `notes` is installed on this fresh box."""
    add_usb(client, bk)
    did = client.get("/v1/backups/destinations", headers=OWNER).json()[0]["id"]
    bk.agent.recovery_key = key
    bk.agent.snaps.append({"id": "c" * 64, "short_id": "cccccccc", "unit": "app:notes", "app_id": "notes", "node_id": "old",
                           "taken_at": "2026-11-10T10:01:00Z", "reason": "scheduled", "run_id": "run_old", "tags": [],
                           "paths": ["/x"]})
    return did, {"destination_id": did, "box_id": "old-box", "recovery_key": key, "run_id": "run_old", "app_id": "notes"}


def test_restore_app_from_another_box_uses_the_key_once_and_never_stores_it(client, bk, settings):
    did, body = _other_box(client, bk)
    r = client.post("/v1/onboarding/restore/apps", headers=OWNER, json=body)
    assert r.status_code == 202, r.text
    act = r.json()
    assert act["state"] == "awaiting_approval" and act["restore"]["plan"]["source"]["box_id"] == "old-box"
    assert r.headers["cache-control"] == "no-store"
    key = body["recovery_key"]
    assert key not in r.text and key not in str(act["params"]), "the key is not part of the action"
    assert "backup.restore" not in bk.agent.kinds(), "nothing is restored before approval"

    done = approve(client, act["id"])
    assert done["state"] == "succeeded", done
    job = next(p for k, p, _ in bk.agent.jobs if k == "backup.restore" and p.get("scope") == "app")
    assert job["box_id"] == "old-box" and job["recovery_key"] == key and job["target_id"] == did
    assert job["snapshot_id"] == "c" * 64
    assert not any(p.get("recovery_key") for k, p, _ in bk.agent.jobs if k == "backup.run"), "the undo snapshot is of this box"
    assert key not in settings.audit_path.read_text()
    assert key not in client.get(f"/v1/actions/{act['id']}", headers=OWNER).text
    assert key not in client.get("/v1/restores", headers=OWNER).text


def test_restore_app_from_another_box_is_refused_cleanly(client, bk):
    did, body = _other_box(client, bk)
    for who in (ADULT, AGENT):
        assert client.post("/v1/onboarding/restore/apps", headers=who, json=body).status_code == 403
    bad = client.post("/v1/onboarding/restore/apps", headers=OWNER, json={**body, "recovery_key": "XX" * 20})
    assert bad.status_code == 409 and "XX" * 20 not in bad.text
    assert client.post("/v1/onboarding/restore/apps", headers=OWNER, json={**body, "run_id": "nope"}).status_code == 404
    assert client.post("/v1/onboarding/restore/apps", headers=OWNER,
                       json={**body, "destination_id": "dst_0000000000000000"}).status_code == 404
    short = client.post("/v1/onboarding/restore/apps", headers=OWNER, json={**body, "recovery_key": "short"})
    assert short.status_code == 422 and "short" not in short.json().get("message", "")
    assert "backup.restore" not in bk.agent.kinds()


def test_restore_app_key_is_gone_after_a_restart_and_nothing_changes(client, bk):
    did, body = _other_box(client, bk)
    act = client.post("/v1/onboarding/restore/apps", headers=OWNER, json=body).json()
    client.app.state.backups._pending_keys.clear()
    done = approve(client, act["id"])
    assert done["state"] == "failed" and "gone" in done["result"]["message"]
    assert "backup.restore" not in bk.agent.kinds() and not any(
        c[0] == "scale" and c[3] == 0 for c in bk.kube.calls if c[0] == "scale")


# ---- owner shortcut passes the same approval guards as the approve route (F-2) -----------------------
def test_owner_shortcuts_require_verification_after_setup(client, bk):
    from fastapi.testclient import TestClient

    from test_identity import LOCAL_PEER, setup_bearer_owner

    add_usb(client, bk)
    assert client.post("/v1/backups/runs", headers=OWNER, json={"approve": True}).json()["state"] == "succeeded"
    snap = client.get("/v1/backups/snapshots", headers=OWNER, params={"app_id": "notes"}).json()[0]
    home = TestClient(client.app, client=LOCAL_PEER)
    setup_bearer_owner(home)
    jobs = len(bk.agent.jobs)
    # the control: the normal approve route is refused
    ctl = client.post("/v1/backups/runs", headers=OWNER, json={})
    assert client.post(f"/v1/actions/{ctl.json()['id']}/approve", headers=OWNER).status_code == 401
    attempts = [
        ("post", "/v1/backups/destinations", {"kind": "usb", "label": "Off box", "config": {"usb_uuid": "9999-ZZZZ"}, "approve": True}),
        ("post", "/v1/backups/runs", {"approve": True}),
        ("post", "/v1/backups/verify", {"approve": True}),
        ("post", "/v1/restores", {"approve": True, "snapshot_id": snap["id"], "scope": {"app_id": "notes"}}),
    ]
    for verb, path, body in attempts:
        r = getattr(client, verb)(path, headers=OWNER, json=body)
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required", (path, r.text)
    # the owner key is not minted, and the shortcut approval did not run anything
    r = client.post("/v1/backups/kit", headers=OWNER)
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    assert not any(j[0] in ("backup.key.add", "backup.restore", "backup.configure", "backup.run") for j in bk.agent.jobs[jobs:])
    acts = client.get("/v1/actions", headers=OWNER).json()
    assert [a["state"] for a in acts if a["type"] == "backup.kit.issue"] == ["awaiting_approval"]
    assert [a["state"] for a in acts if a["type"] == "backup.restore"] == ["awaiting_approval"]
    assert len([a for a in acts if a["type"] == "backup.destination.add"]) == 2 and \
        [a["state"] for a in acts if a["type"] == "backup.destination.add"].count("awaiting_approval") == 1


def test_kit_needs_no_backup_destination(client, bk):
    """D-028: a box with no backup target still gets a kit; a destination added later is listed as not covered
    until a new kit is issued, and issuing again adds a key beside the old one (restic key add), never replaces."""
    r = client.post("/v1/backups/kit", headers=OWNER)
    assert r.status_code == 201, r.text
    one = r.json()["one_time"]
    assert check_group_ok(one["groups"], one["check"]) and one["owner_key"] in one["text"]
    assert "none yet" in one["text"] and "disk_recovery_key" not in one
    assert "backup.key.add" not in bk.agent.kinds(), "no destination: nothing to add the key to"
    kit = client.get("/v1/backups/kit", headers=OWNER).json()
    assert kit["state"] == "issued" and kit["uncovered_destinations"] == [] and kit["disk_key_included"] is False
    right = {str(p): one["groups"][p - 1] for p in kit["positions"]}
    assert client.post("/v1/backups/kit/confirm", headers=OWNER, json={"answers": right}).json()["state"] == "confirmed"
    add_usb(client, bk)
    dest = bk.repo.destinations()[0].id
    kit = client.get("/v1/backups/kit", headers=OWNER).json()
    assert kit["uncovered_destinations"] == [dest], kit
    assert client.get("/v1/backups/status", headers=OWNER).json()["kit"]["uncovered_destinations"] == [dest]


def test_kit_reissue_adds_a_key_and_covers_destinations(client, bk):
    add_usb(client, bk)
    first = client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]["owner_key"]
    assert client.get("/v1/backups/kit", headers=OWNER).json()["uncovered_destinations"] == []
    r = client.post("/v1/backups/destinations", headers=OWNER,
                    json={"kind": "usb", "label": "Second disk", "config": {"usb_uuid": "5678-EFGH"}})
    approve(client, r.json()["id"])
    assert len(client.get("/v1/backups/kit", headers=OWNER).json()["uncovered_destinations"]) == 1
    # a new kit (new idempotency key) adds its key on every destination and never removes the first key
    r = client.post("/v1/backups/kit", headers=OWNER, json=None)
    assert r.status_code in (201, 409)
    keys = [j for j in bk.agent.jobs if j[0] == "backup.key.add"]
    assert keys[0][1]["key"] == first and all(j[1]["which"] == "owner" for j in keys)
    assert "backup.key.remove" not in bk.agent.kinds()


def test_disk_key_goes_into_the_kit_and_a_later_kit_names_the_page_that_holds_it(client, bk, settings):
    """D-028: the LUKS recovery key is read for the kit step only, printed, never stored. Confirming the kit
    destroys the node's copy; a later kit then points at the page that holds the key (no new dead end)."""
    waiting = ["MODHEX-DISK-KEY-FOR-TESTS-ONLY"]
    forgotten = []
    svc = client.app.state.backups
    svc.disk_key_source = lambda: waiting[0] if waiting else None
    svc.disk_key_forget = lambda: (forgotten.append(1), waiting.clear())
    disk = waiting[0]
    add_usb(client, bk)
    r = client.post("/v1/backups/kit", headers=OWNER)
    assert r.status_code == 201, r.text
    one = r.json()["one_time"]
    assert one["disk_recovery_key"] == disk and disk in one["text"]
    kit = client.get("/v1/backups/kit", headers=OWNER).json()
    assert kit["disk_key_included"] is True and kit["disk_key_kit"]["fingerprint"] == kit["fingerprint"]
    assert forgotten == [], "an unconfirmed page may be lost: the node keeps the key"
    for blob in (json.dumps(client.get("/v1/actions", headers=OWNER).json()), settings.audit_path.read_text(),
                 json.dumps(client.get("/v1/backups/kit", headers=OWNER).json()),
                 json.dumps(client.get("/v1/backups/status", headers=OWNER).json())):
        assert disk not in blob
    if settings.db_url.startswith("sqlite:///"):
        assert disk.encode() not in Path(settings.db_url[len("sqlite:///"):]).read_bytes()
    right = {str(p): one["groups"][p - 1] for p in kit["positions"]}
    assert client.post("/v1/backups/kit/confirm", headers=OWNER, json={"answers": right}).json()["state"] == "confirmed"
    assert forgotten == [1]
    first = kit
    # a re-issue has no disk key to print, but says which kit holds it, in its text and in the kit status
    again = client.post("/v1/backups/kit", headers=OWNER).json()
    assert "disk_recovery_key" not in again["one_time"] and disk not in again["one_time"]["text"]
    assert "NOT on this page" in again["one_time"]["text"]
    assert first["fingerprint"] in again["one_time"]["text"] and first["issued_at"] in again["one_time"]["text"]
    now = client.get("/v1/backups/kit", headers=OWNER).json()
    assert now["disk_key_included"] is False
    assert now["disk_key_kit"] == {"fingerprint": first["fingerprint"], "issued_at": first["issued_at"]}
    assert disk not in json.dumps(now)


def test_kit_reissue_is_announced_and_kit_without_disk_key_has_no_marker(client, bk):
    one = client.post("/v1/backups/kit", headers=OWNER).json()
    assert "NOT on this page" not in one["one_time"]["text"] and one["kit"]["disk_key_kit"] is None
    seen: list[dict] = []
    client.app.state.gateway.events.subscribe("backup.>", seen.append)
    client.post("/v1/backups/kit", headers=OWNER)
    ev = [e for e in seen if e["type"] == "backup.kit.reissued"]
    assert len(ev) == 1 and ev[0]["severity"] == "warning", seen  # the first issue is not a re-issue; the second is
    assert ev[0]["data"]["old_fingerprint"] == one["kit"]["fingerprint"], ev[0]


def test_failed_kit_issue_does_not_use_up_the_disk_key(client, bk):
    taken = []
    client.app.state.backups.disk_key_source = lambda: taken.append(1) or "KEY"
    add_usb(client, bk)
    bk.agent.fail["backup.key.add"] = "boom"
    assert client.post("/v1/backups/kit", headers=OWNER).status_code == 409
    assert taken == [], "the disk key is read after everything that can fail"


def test_console_kit_check_locks_after_five_wrong_tries_and_never_wipes(client, bk, clock):
    from onemind_core.backups.kit import new_owner_key
    one = client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]
    svc = client.app.state.backups
    principal = type("P", (), {"as_dict": lambda self: {"id": "console", "kind": "static"}})()
    wrong = new_owner_key().password
    for _ in range(5):
        with pytest.raises(ApiError) as e:
            svc.verify_console_kit(principal, wrong)
        assert e.value.status == 401
    with pytest.raises(ApiError) as e:  # now locked, even for the right key
        svc.verify_console_kit(principal, one["owner_key"])
    assert e.value.status == 429 and e.value.retry_after_s >= 15 * 60 - 1
    clock.advance(16 * 60)
    with pytest.raises(ApiError) as e:  # a wrong try after the first lock doubles it
        svc.verify_console_kit(principal, wrong)
    assert e.value.status == 401
    with pytest.raises(ApiError) as e:
        svc.verify_console_kit(principal, one["owner_key"])
    assert e.value.status == 429 and e.value.retry_after_s > 29 * 60
    clock.advance(31 * 60)
    assert svc.verify_console_kit(principal, one["owner_key"].lower().replace("-", " "))["fingerprint"]
    assert svc.verify_console_kit(principal, one["owner_key"] + " " + one["check"])["fingerprint"]
    assert svc.repo.kit_lock().fails == 0
    with pytest.raises(ApiError) as e:  # a mistyped key is not a try
        svc.verify_console_kit(principal, "AAAA-BBBB")
    assert e.value.status == 422 and svc.repo.kit_lock().fails == 0
    assert svc.repo.kit() is not None and "backup.restore" not in bk.agent.kinds()


def test_console_checks_a_full_salted_hash_not_the_public_fingerprint(client, bk):
    """The fingerprint is shown (status, event, page) and is only 64 bits, so it must never be the proof."""
    import hashlib
    one = client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]
    svc = client.app.state.backups
    k = svc.repo.kit()
    v = k.challenge["console_verify"]
    assert len(v["hash"]) == 64 and v["salt"] and v["hash"] != hashlib.sha256(one["owner_key"].encode()).hexdigest()
    assert k.fingerprint not in v["hash"] and one["owner_key"] not in json.dumps(k.challenge)
    principal = type("P", (), {"as_dict": lambda self: {"id": "console", "kind": "static"}})()
    assert svc.verify_console_kit(principal, one["owner_key"])["fingerprint"] == k.fingerprint
    # a key that matches only the 16-hex fingerprint of the real one would not pass: the check is the hash
    tampered = dict(k.challenge, console_verify={"salt": v["salt"], "hash": "0" * 64})
    svc.repo.update_kit(challenge=tampered)
    with pytest.raises(ApiError) as e:
        svc.verify_console_kit(principal, one["owner_key"])
    assert e.value.status == 401
    # a kit issued before the hash was stored still opens with its key (no dead end), until a new kit replaces it
    legacy = {kk: vv for kk, vv in k.challenge.items() if kk != "console_verify"}
    svc.repo.update_kit(challenge=legacy)
    svc.repo.put_kit_lock(0, None)
    assert svc.verify_console_kit(principal, one["owner_key"])["fingerprint"] == k.fingerprint


# ---- first-run wizard state (driven by the server, not a browser flag) --------------------------------
def test_onboarding_state_follows_settings_and_kit(client, bk):
    st = client.get("/v1/onboarding/state", headers=OWNER)
    assert st.status_code == 200 and st.headers["cache-control"] == "no-store"
    assert st.json()["complete"] is False and st.json()["kit"]["state"] == "missing" and st.json()["destinations"] == 0
    settings = {"box_name": "home-hub", "time_zone": "UTC", "backup_choice": "later"}
    assert client.put("/v1/onboarding/settings", headers=OWNER, json=settings).status_code == 200
    assert client.get("/v1/onboarding/state", headers=OWNER).json()["complete"] is True, "no destination: no kit needed"
    add_usb(client, bk)
    st = client.get("/v1/onboarding/state", headers=OWNER).json()
    assert st["complete"] is False and st["destinations"] == 1, "a destination makes the kit required"
    one = client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]
    st = client.get("/v1/onboarding/state", headers=OWNER).json()
    assert st["complete"] is False and st["kit"]["state"] == "issued" and len(st["kit"]["positions"]) == 2
    assert one["owner_key"] not in json.dumps(st), "the recovery key is shown once, never in state"
    right = {str(p): one["groups"][p - 1] for p in st["kit"]["positions"]}
    assert client.post("/v1/backups/kit/confirm", headers=OWNER, json={"answers": right}).status_code == 200
    assert client.get("/v1/onboarding/state", headers=OWNER).json()["complete"] is True
    assert client.get("/v1/onboarding/state", headers=ADULT).status_code == 403


def test_signed_in_owner_can_claim_approved_backup_kit_and_finish_onboarding(settings, clock, executor):
    from fastapi.testclient import TestClient

    from onemind_core.app import create_app
    from onemind_core.identity.crypto import totp_code

    from test_identity import LOCAL_PEER, PASSWORD, audit_events, box_code, id_settings, setup_bearer_owner

    app = create_app(id_settings(settings), clock=clock, executor=executor)
    with TestClient(app, client=LOCAL_PEER) as home:
        backups = app.state.backups
        backups.agent = FakeAgent(clock)
        add_usb(home, backups)
        headers = setup_bearer_owner(home)
        pending = home.post("/v1/auth/totp/setup", headers=headers)
        assert pending.status_code == 200, pending.text
        secret = pending.json()["one_time"]["secret"]

        def next_code():
            clock.advance(30)
            return totp_code(secret, int(clock.now.timestamp()) // 30)

        assert home.post("/v1/auth/totp/confirm", headers=headers, json={"code": next_code()}).status_code == 204
        config = {"box_name": "home-hub", "time_zone": "UTC", "backup_choice": "usb",
                  "backup_destination_id": backups.destinations()[0]["id"]}
        assert home.put("/v1/onboarding/settings", headers=headers, json=config).status_code == 200
        assert home.get("/v1/onboarding/state", headers=headers).json()["complete"] is False

        requested = home.post("/v1/backups/kit/request", headers=headers)
        assert requested.status_code == 202, requested.text
        action = requested.json()
        assert action["type"] == "backup.kit.issue" and action["state"] == "awaiting_approval"
        path = f"/v1/actions/{action['id']}"
        claim = f"/v1/backups/kit/{action['id']}/claim"
        assert home.post(claim, headers=headers).status_code == 409
        assert home.post(f"{path}/approve", headers=headers).json()["reason"] == "step_up_required"
        assert "backup.key.add" not in backups.agent.kinds()

        options = home.post(f"{path}/approve-options", headers=headers, json={"method": "password+totp", "at_box": True})
        assert options.status_code == 200 and options.json()["box_code_required"], options.text
        proof = {"challenge": options.json()["challenge"], "password": PASSWORD, "totp": next_code()}
        approved = home.post(f"{path}/approve", headers=headers, json={"password_totp": proof, "box_code": box_code(home)})
        assert approved.status_code == 200 and approved.json()["state"] == "succeeded", approved.text
        assert home.get("/v1/onboarding/state", headers=headers).json()["complete"] is False

        other_login = home.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD,
                                "client": "cli", "totp": next_code()})
        assert other_login.status_code == 200, other_login.text
        another_session = {"Authorization": f"Bearer {other_login.json()['access_token']}"}
        assert home.post(claim, headers=another_session).status_code == 409
        assert home.post(claim, headers=ADULT).status_code == 403
        resumed = home.post("/v1/backups/kit/request", headers=headers).json()
        assert resumed["id"] == action["id"] and resumed["state"] == "succeeded"

        delivered = home.post(claim, headers=headers)
        assert delivered.status_code == 200 and delivered.headers["cache-control"] == "no-store", delivered.text
        one = delivered.json()["one_time"]
        assert home.post(claim, headers=headers).status_code == 409
        assert backups.agent.kinds().count("backup.key.add") == 1
        assert one["owner_key"] not in approved.text + home.get(path, headers=headers).text + str(audit_events(settings))

        positions = delivered.json()["kit"]["positions"]
        answers = {str(pos): one["groups"][pos - 1] for pos in positions}
        assert home.post("/v1/backups/kit/confirm", headers=headers, json={"answers": answers}).status_code == 200
        state = home.get("/v1/onboarding/state", headers=headers).json()
        assert state["complete"] is True and state["kit"]["state"] == "confirmed"


def test_existing_headless_owner_recovers_l2_to_finish_backup_kit(settings, clock, executor, tmp_path, root):
    from fastapi.testclient import TestClient

    from onemind_core.app import create_app
    from onemind_core.identity.crypto import hash_password
    from onemind_core.identity.models import UserRow

    from test_identity import LOCAL_PEER, PASSWORD, audit_events, csrf, id_settings
    from test_identity_levels import BIO_AAGUID, AttestedAuthenticator
    from test_identity_signin import enable_totp

    allow = tmp_path / "allowlist.json"
    allow.write_text(json.dumps({"version": 1, "entries": [{
        "kind": "fido_aaguid", "aaguid": BIO_AAGUID, "name": "Test Bio Key", "roots": [root.pem],
        "user_verification": ["fingerprint_internal"],
    }]}))
    cfg = id_settings(settings, box_code_file=None, allowlist_file=allow)
    with TestClient(create_app(cfg, clock=clock, executor=executor), client=LOCAL_PEER) as home:
        backups = home.app.state.backups
        backups.agent = FakeAgent(clock)
        add_usb(home, backups)
        home.app.state.identity.repo.add(UserRow(id="usr_existing", username="zeus", display_name="Existing owner",
                                                role="owner", password_hash=hash_password(PASSWORD),
                                                created_at=clock.now, updated_at=clock.now, created_by="legacy"))
        login = {"username": "zeus", "password": PASSWORD}
        assert home.post("/v1/auth/login", json=login).status_code == 200
        kit_path = "/v1/auth/setup/kit?legacy_upgrade=true"
        assert home.post(kit_path, headers=csrf(home)).json()["reason"] == "step_up_required"
        secret = enable_totp(home, clock)

        def sign_in():
            from onemind_core.identity.crypto import totp_code

            proof = {**login, "totp": totp_code(secret, int(clock.now.timestamp()) // 30)}
            r = home.post("/v1/auth/login", json=proof)
            assert r.status_code == 200, r.text

        sign_in()
        config = {"box_name": "home-hub", "time_zone": "UTC", "backup_choice": "usb",
                  "backup_destination_id": backups.destinations()[0]["id"]}
        assert home.put("/v1/onboarding/settings", headers=csrf(home), json=config).status_code == 200
        assert home.get("/v1/onboarding/state").json()["complete"] is False
        requested = home.post("/v1/backups/kit/request", headers=csrf(home))
        assert requested.status_code == 202, requested.text
        action = f"/v1/actions/{requested.json()['id']}"
        assert home.post(f"{action}/approve", headers=csrf(home)).json()["reason"] == "step_up_required"
        assert "backup.key.add" not in backups.agent.kinds()

        remote = "/v1/auth/recovery/remote"
        assert home.get(remote).json()["upgrade_kit_available"] is True
        kit = home.post(kit_path, headers=csrf(home))
        assert kit.status_code == 200 and kit.headers["cache-control"] == "no-store", kit.text
        code = kit.json()["recovery_code"]
        assert kit.json()["disk_recovery_key"] is None
        assert home.post(kit_path, headers=csrf(home)).status_code == 409
        assert home.post(remote, headers=csrf(home), json={"recovery_code": code}).json()["state"] == "waiting"
        opts = "/v1/auth/passkeys/register/options?remote_recovery=true"
        clock.advance(72 * 3600 - 1)
        sign_in()
        assert home.post(opts, headers=csrf(home)).json()["reason"] == "remote_recovery_wait"
        assert home.get("/v1/onboarding/state").json()["complete"] is False
        clock.advance(1)
        options = home.post(opts, headers=csrf(home))
        assert options.status_code == 200, options.text
        key = AttestedAuthenticator(root)
        registered = home.post("/v1/auth/passkeys/register", headers=csrf(home),
                               json={"credential": key.register(options.json())})
        assert registered.status_code == 201 and registered.json()["level"] == "L2", registered.text

        requested = home.post("/v1/backups/kit/request", headers=csrf(home))
        assert requested.status_code == 202, requested.text
        aid = requested.json()["id"]
        action = f"/v1/actions/{aid}"
        options = home.post(f"{action}/approve-options", headers=csrf(home))
        assert options.status_code == 200 and options.json()["required_level"] == "L2", options.text
        proof = {"webauthn": key.assert_(options.json()["publicKey"]["challenge"])}
        done = home.post(f"{action}/approve", headers=csrf(home), json=proof)
        assert done.status_code == 200 and done.json()["state"] == "succeeded", done.text
        issued = home.post(f"/v1/backups/kit/{aid}/claim", headers=csrf(home))
        assert issued.status_code == 200, issued.text
        groups = issued.json()["one_time"]["groups"]
        answers = {str(pos): groups[pos - 1] for pos in issued.json()["kit"]["positions"]}
        assert home.post("/v1/backups/kit/confirm", headers=csrf(home), json={"answers": answers}).status_code == 200
        assert home.get("/v1/onboarding/state").json()["complete"] is True
        assert code not in str(audit_events(settings))


# ---- content tier (BAK-03, REC-NOMAD-07) -------------------------------------------------------
LIBRARY = NOTES.replace("id: notes, name: Notes", "id: library, name: Library").split("  backup:")[0] + """  backup:
    mode: hot
    exclude: ["*.zim.part"]
    content: ["*.zim"]
"""
GIB = 1 << 30


@pytest.fixture
def library(bk, settings, clock):
    d = settings.apps_dir / "library"
    (d / "manifests").mkdir(parents=True)
    (d / "onemind.app.yaml").write_text(LIBRARY)
    (d / "manifests" / "kustomization.yaml").write_text("resources: []\n")
    bk.gw.repo.set_app_state("library", "installed", clock.now)
    bk.agent.content_bytes["library"] = 5 * GIB
    return d


def run_apps(bk) -> dict[str, dict]:
    """The app entries of the last backup.run job, by app id."""
    params = [p for k, p, _ in bk.agent.jobs if k == "backup.run"][-1]
    return {a["id"]: a for a in params["apps"]}


def test_content_tier_is_off_by_default_and_its_size_is_shown(client, bk, library):
    r = client.get("/v1/backups/content", headers=ADULT)
    assert r.status_code == 200, r.text
    [entry] = r.json()  # notes marks no content, so only the library is listed
    assert entry["app_id"] == "library" and entry["patterns"] == ["*.zim"]
    assert entry["enabled"] is False and entry["size_bytes"] == 5 * GIB and entry["measured_at"]
    size_job = [p for k, p, _ in bk.agent.jobs if k == "backup.content.size"][-1]
    assert size_job["apps"] == [{"id": "library", "volumes": [{"namespace": "app-library", "claim": "data", "volume": "pvc-1"}],
                                 "patterns": ["*.zim"]}]
    assert client.get("/v1/backups/content", headers=GUEST_HEADERS).status_code == 403

    add_usb(client, bk)
    client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    apps = run_apps(bk)
    assert apps["library"]["content"] == "excluded"
    assert apps["library"]["excludes"] == ["*.zim.part", "*.zim"], "content stays out until switched on"
    assert "content" not in apps["notes"]


def test_switching_the_content_tier_on_needs_the_size_seen_and_the_owner(client, bk, library):
    on = {"app_id": "library", "enabled": True}
    assert client.post("/v1/backups/content", headers=ADULT, json={**on, "seen_size_bytes": 5 * GIB}).status_code == 403
    assert client.post("/v1/backups/content", headers=AGENT, json={**on, "seen_size_bytes": 5 * GIB}).status_code == 403
    r = client.post("/v1/backups/content", headers=OWNER, json=on)
    assert r.status_code == 422 and r.json()["reason"] == "size_not_seen"
    r = client.post("/v1/backups/content", headers=OWNER, json={**on, "seen_size_bytes": 1024})
    assert r.status_code == 409 and r.json()["reason"] == "size_changed", "a size far below today's is not consent"
    r = client.post("/v1/backups/content", headers=OWNER, json={"app_id": "notes", "enabled": True, "seen_size_bytes": 0})
    assert r.status_code == 404, "notes marks no downloadable content"

    r = client.post("/v1/backups/content", headers=OWNER, json={**on, "seen_size_bytes": 5 * GIB})
    assert r.status_code == 202 and r.json()["state"] == "awaiting_approval", "nothing changes before approval"
    assert r.json()["params"]["size_bytes"] == 5 * GIB
    assert client.get("/v1/backups/content", headers=OWNER).json()[0]["enabled"] is False
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded", done
    entry = client.get("/v1/backups/content", headers=OWNER).json()[0]
    assert entry["enabled"] is True and entry["enabled_size_bytes"] == 5 * GIB

    r = client.post("/v1/backups/content", headers=OWNER, json={"app_id": "library", "enabled": False, "approve": True})
    assert r.status_code == 202 and r.json()["state"] == "succeeded"
    assert client.get("/v1/backups/content", headers=OWNER).json()[0]["enabled"] is False


def test_restore_with_and_without_the_content_tier(client, bk, library):
    """BAK-03 done-when, gateway side (the agent side, with real files, is internal/backup/content_test.go)."""
    add_usb(client, bk)
    client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    assert run_apps(bk)["library"]["content"] == "excluded"
    without = client.get("/v1/backups/snapshots?app_id=library", headers=OWNER).json()[0]
    assert "content=excluded" in without["tags"]

    r = client.post("/v1/backups/content", headers=OWNER,
                    json={"app_id": "library", "enabled": True, "seen_size_bytes": 5 * GIB, "approve": True})
    assert r.json()["state"] == "succeeded", r.text
    client.post("/v1/backups/runs", headers=OWNER, json={"approve": True})
    lib = run_apps(bk)["library"]
    assert lib["content"] == "included" and lib["excludes"] == ["*.zim.part"]
    with_ = client.get("/v1/backups/snapshots?app_id=library", headers=OWNER).json()[0]
    assert "content=included" in with_["tags"]

    for snap, content in ((without, "excluded"), (with_, "included")):
        r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"], "scope": {"app_id": "library"}})
        assert r.status_code == 202, r.text
        plan = r.json()["restore"]["plan"]
        assert plan["content"] == content
        warned = any("downloadable content" in w for w in plan["warnings"])
        assert warned is (content == "excluded"), plan["warnings"]
        done = approve(client, r.json()["id"])
        assert done["state"] == "succeeded", done
        restore_job = [p for k, p, _ in bk.agent.jobs if k == "backup.restore"][-1]
        assert restore_job["snapshot_id"] == snap["id"] and restore_job["app_id"] == "library"


def test_manifest_content_block():
    spec, errs = parse_backup({"backup": {"content": ["*.zim", "maps/*.pmtiles"]}})
    assert errs == [] and spec.content == ("*.zim", "maps/*.pmtiles")
    for bad in (["/data"], ["../x"], ["a/**/b"], "x"):
        assert parse_backup({"backup": {"content": bad}})[1]


def test_market_apps_mark_their_downloadable_content():
    """Kiwix ZIMs, offline map archives and Ollama models are the content tier, not always-excluded."""
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[2]
    for app, pattern in (("kiwix", "*.zim"), ("offline-maps", "maps/*.pmtiles"), ("ollama", "models/")):
        spec, errs = parse_backup(yaml.safe_load((root / "apps" / app / "onemind.app.yaml").read_text())["spec"])
        assert errs == [] and pattern in spec.content and pattern not in spec.exclude, app


def test_byte_counts_use_64_bit_columns():
    """Sizes and byte counts pass 2 GiB, so PostgreSQL needs BIGINT (an INTEGER column overflowed at 5 GiB)."""
    from sqlalchemy import BigInteger

    from onemind_core.backups.store import ContentTierRow, RunRow

    assert isinstance(ContentTierRow.__table__.c.size_bytes.type, BigInteger)
    assert isinstance(RunRow.__table__.c.bytes_added.type, BigInteger)
