# SPDX-License-Identifier: Apache-2.0
"""Backups switched on (contract §12.12): actions, hooks, restore with undo, kit, shared PostgreSQL.

The agent (onemindd backup) and kubectl are fakes here; the Lima run in test/backup-wire/ drives the
real ones. Runs on SQLite and, with ONEMIND_TEST_DB_URL, on PostgreSQL.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from onemind_core.backups.jobs import AgentError, canonical, sign_job
from onemind_core.backups.kit import check_group_ok
from onemind_core.backups.kube import Kube, KubeError, Workload
from onemind_core.backups.manifest import parse_backup, parse_database
from onemind_core.databases import DatabasesSettings, SharedPostgres

from conftest import ADULT, AGENT, OWNER

NOTES = """apiVersion: onemind.app/v1alpha1
kind: App
metadata: {id: notes, name: Notes, version: "1.0.0", description: test, category: productivity, license: MIT,
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
        self.verified: dict[str, dict] = {}
        self.fail: dict[str, str] = {}
        self.run_state = "succeeded"

    def job(self, kind, params, *, action_id=None, timeout=None):
        canonical(params)  # what is sent must be signable
        self.jobs.append((kind, params, action_id))
        if kind in self.fail:
            raise AgentError(kind, self.fail[kind], reason="failed")
        if kind == "backup.run":
            units = params.get("units") or [f"app:{a['id']}" for a in params["apps"]] + ["system"]
            units = [u for u in units if u not in params.get("skip_units", [])]
            out = []
            for u in units:
                sid = hashlib.sha256(f"{u}{len(self.snaps)}".encode()).hexdigest()
                self.snaps.append({"id": sid, "short_id": sid[:8], "unit": u, "app_id": u[4:] if u.startswith("app:") else "",
                                   "node_id": "n1", "taken_at": self.clock().isoformat(), "reason": params["reason"],
                                   "run_id": params["run_id"], "tags": [], "paths": [f"/var/lib/rancher/k3s/storage/pvc-1_app-notes_data"]})
                out.append({"unit": u, "state": "succeeded", "snapshot_id": sid})
            return {"id": params["run_id"], "state": self.run_state, "units": out, "bytes_added": 42, "target_id": "dst_x"}
        if kind == "backup.snapshots":
            return [s for s in reversed(self.snaps) if not params.get("unit") or s["unit"] == params["unit"]]
        if kind == "backup.status":
            units = {s["unit"]: {"state": "unverified", "last_success_at": s["taken_at"], "verified_at": None} for s in self.snaps}
            for u, v in self.verified.items():
                units[u] = {"state": "verified", "last_success_at": v["finished_at"], "verified_at": v["finished_at"]}
            box = {"state": "verified" if units and all(b["state"] == "verified" for b in units.values()) else
                   ("unverified" if units else "none")}
            return {"status": {"box": box, "units": units, "last_verified": self.verified, "fenced": False},
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
        if kind == "backup.tree":
            return [{"name": "notes.txt", "path": params["path"].rstrip("/") + "/notes.txt", "type": "file", "size": 2}]
        if kind in ("backup.configure", "backup.restore.finish", "backup.key.add"):
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
def test_agent_requests_a_run_but_only_the_owner_approves(client, bk):
    add_usb(client, bk)
    r = client.post("/v1/backups/runs", headers=AGENT, json={"scope": {"app_id": "notes"}})
    assert r.status_code == 202 and r.json()["state"] == "awaiting_approval"
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=AGENT).status_code == 403
    assert client.post("/v1/backups/runs", headers=AGENT, json={"approve": True}).status_code == 403
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded", done


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
    approve(client, r.json()["id"])
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


def test_restore_one_path(client, bk):
    snap = restorable(client, bk)
    r = client.post("/v1/restores", headers=OWNER, json={"snapshot_id": snap["id"],
                    "scope": {"app_id": "notes", "path": snap["paths"][0] + "/notes.txt"}})
    assert r.status_code == 202 and r.json()["restore"]["plan"]["downtime"] == "none"
    done = approve(client, r.json()["id"])
    assert done["state"] == "succeeded"
    assert bk.agent.jobs[-1][1]["scope"] == "path"
    assert not any(c[0] == "scale" for c in bk.kube.calls), "a one-file restore does not stop the app"


# ---- emergency kit ---------------------------------------------------------------------------------
def test_emergency_kit_is_shown_once_and_must_be_typed_back(client, bk, settings):
    assert client.post("/v1/backups/kit", headers=OWNER).status_code == 409, "a destination comes first"
    add_usb(client, bk)
    assert client.post("/v1/backups/kit", headers=ADULT).status_code == 403
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
