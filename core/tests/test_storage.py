# SPDX-License-Identifier: Apache-2.0
"""Storage actions through the gateway (STORAGE-ACT-1, UMB-STOR-5).

A fake node storage service speaks the socket API of internal/storage/ops/server.go over a real
Unix socket, so the client, the action flow and the poller are tested end to end. Runs on SQLite
and PostgreSQL (ONEMIND_TEST_DB_URL)."""

from __future__ import annotations

import json
import shutil
import socketserver
import tempfile
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.storage import StorageService, StorageSettings

from conftest import AGENT, GUEST, OWNER

SHA_A = "a" * 64
SHA_B = "b" * 64
SERIAL = "S3EVNX0K123456"


class FakeNode:
    """What onemindd storage serve would answer."""

    def __init__(self):
        self.sha = SHA_A
        self.blocked = False
        self.ops: dict[str, dict] = {}
        self.started: list[dict] = []
        self.busy = False
        self.recovery_key: str | None = "cbdefghi-jklnrtuv-cbdefghi-jklnrtuv-cbdefghi-jklnrtuv-cbdefghi-jklnrtuv"
        self.state = "unprotected"
        self.verdict = "ok"

    def plan(self, req: dict) -> dict:
        return {
            "kind": "protect", "mount": "/data", "blocked": self.blocked, "plan_sha256": self.sha,
            "checks": [{"id": "unused:/dev/vdc", "ok": not self.blocked, "detail": "holds: ext4"}],
            "targets": [{"path": "/dev/vdc", "id": SERIAL, "serial_tail": SERIAL[-4:], "size_bytes": 4 << 30}],
            "steps": [] if self.blocked else [
                {"id": "wipe", "phase": "prepare", "cmd": ["sgdisk", "--zap-all", "/dev/vdc"], "why": "", "destructive": True},
                {"id": "device-add", "phase": "join", "cmd": ["btrfs", "device", "add", "/dev/vdc1", "/data"], "why": ""},
                {"id": "balance", "phase": "commit", "cmd": ["btrfs", "balance", "start", "/data"], "why": ""},
            ],
            "request": req,
        }

    def status(self) -> dict:
        return {
            "mount": "/data", "operations_available": True, "recovery_key_pending": self.recovery_key is not None,
            "tpm2": False, "at": "2026-11-12T10:00:00Z", "active_operation": None,
            "mirror": {"state": self.state, "encrypted": True, "generation": 3, "needs_scrub": False,
                       "reasons": [] if self.state != "degraded" else ["1 of 2 disks missing"],
                       "members": [{"devid": 1, "path": "/dev/mapper/x", "missing": False, "size_bytes": 1, "allocated_bytes": 1, "errors": {}}],
                       "profiles": [{"kind": "Data", "profile": "single"}]},
            "disks": [{"path": "/dev/vdc", "id": SERIAL, "serial": SERIAL, "serial_tail": SERIAL[-4:], "model": "Disk", "role": "unused"}],
            "health": {"/dev/vdc": {"verdict": self.verdict, "reasons": ["SMART failed"] if self.verdict == "critical" else []}},
        }


def _serve(node: FakeNode, path: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if self.path == "/v1/status":
                return self._send(200, node.status())
            if self.path.startswith("/v1/operations/"):
                op = node.ops.get(self.path.rsplit("/", 1)[1])
                return self._send(200, op) if op else self._send(404, {"error": "not_found", "message": "no such operation"})
            self._send(404, {"error": "not_found"})

        def do_POST(self):
            body = self._body()
            if self.path == "/v1/plans":
                return self._send(200, node.plan(body))
            if self.path == "/v1/operations":
                if node.busy:
                    return self._send(409, {"error": "busy", "message": "another storage operation is running"})
                if body.get("plan_sha256") != node.sha:
                    return self._send(409, {"error": "stale_precondition", "reason": "plan_changed", "message": "the plan changed"})
                node.started.append(body)
                plan = node.plan(body)
                op = {"id": body["action_id"], "request": body, "plan": plan, "state": "running", "next": 1,
                      "steps": [{"state": "done"}, {"state": "running"}, {"state": "pending"}]}
                node.ops[body["action_id"]] = op
                return self._send(202, op)
            if self.path == "/v1/recovery-key/take":
                if node.recovery_key is None:
                    return self._send(404, {"error": "not_found", "message": "shown once"})
                key, node.recovery_key = node.recovery_key, None
                return self._send(200, {"recovery_key": key})
            self._send(404, {"error": "not_found"})

    class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
        daemon_threads = True

    srv = Server(path, Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture
def node():
    d = tempfile.mkdtemp(prefix="om-st-", dir="/tmp")  # Unix socket paths are limited to ~104 bytes
    n = FakeNode()
    n.sock = Path(d) / "s.sock"
    srv = _serve(n, str(n.sock))
    yield n
    srv.shutdown()
    srv.server_close()
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def no_poller(monkeypatch):
    """Tests drive the poller by hand (svc.poll()), so the background thread is not started."""
    monkeypatch.setattr(StorageService, "start", lambda self: None)


def storage_client(settings, clock, node, enabled=True):
    s = replace(settings, sections={"storage": StorageSettings(enabled=enabled, socket=node.sock, poll_s=60, timeout_s=5)})
    return TestClient(create_app(s, clock=clock))


def request_create(c, headers=OWNER, **extra):
    return c.post("/v1/storage/actions", headers=headers,
                  json={"type": "storage.mirror.create", "params": {"device": "/dev/vdc"}, **extra})


def events(c) -> list[dict]:
    seen: list[dict] = []
    c.app.state.gateway.events.subscribe("storage.>", seen.append)
    return seen


def test_request_approve_run_and_finish(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        seen = events(c)
        r = request_create(c, reason="second disk arrived")
        assert r.status_code == 202, r.text
        body = r.json()
        action = body["action"]
        assert action["state"] == "awaiting_approval" and action["type"] == "storage.mirror.create"
        assert r.headers["location"] == f"/v1/actions/{action['id']}"
        assert body["plan_sha256"] == SHA_A and body["risk"] == "destructive"
        assert body["plan"]["targets"][0]["serial_tail"] == SERIAL[-4:]  # the approval card names the disk
        assert node.started == []  # nothing runs before approval

        a = c.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
        assert a.status_code == 200 and a.json()["state"] == "dispatched", a.text
        assert node.started == [{"kind": "create", "device": "/dev/vdc", "plan_sha256": SHA_A, "action_id": action["id"]}]
        op = c.get(f"/v1/storage/operations/{action['id']}", headers=OWNER).json()
        assert op["state"] == "running" and [s["id"] for s in op["journal"]] == ["wipe", "device-add", "balance"]

        svc = c.app.state.storage
        svc.poll()  # still running: stays dispatched
        assert c.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "dispatched"
        node.ops[action["id"]]["state"] = "succeeded"
        node.ops[action["id"]]["next"] = 3
        svc.poll()
        done = c.get(f"/v1/actions/{action['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and done["result"]["operation"]["state"] == "succeeded"
        assert any(e["type"] == "storage.operation.finished" and e["data"]["state"] == "succeeded" for e in seen)
        svc.poll()  # closed once
        assert sum(e["type"] == "storage.operation.finished" for e in seen) == 1
        audit = [json.loads(x) for x in Path(settings.audit_path).read_text().splitlines()]
        assert [x["event"] for x in audit if x.get("action_id") == action["id"] and x["event"].startswith("action.")] == [
            "action.requested", "action.awaiting_approval", "action.approved", "action.dispatched", "action.succeeded"]


def test_plan_changed_before_approval_is_stale(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        action = request_create(c).json()["action"]
        node.sha = SHA_B  # someone swapped the cable: the disk on that path is a different one
        a = c.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
        assert a.status_code == 409 and a.json()["error"] == "stale_precondition", a.text
        assert c.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
        assert node.started == []


def test_node_refuses_changed_plan_at_dispatch(settings, clock, node, no_poller, monkeypatch):
    with storage_client(settings, clock, node) as c:
        action = request_create(c).json()["action"]
        svc = c.app.state.storage
        monkeypatch.setattr(svc, "recheck", lambda a: None)  # the change lands between approval and dispatch
        node.sha = SHA_B
        a = c.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).json()
        assert a["state"] == "failed" and "not started" in a["result"]["message"]
        assert node.started == []


def test_agents_request_but_never_approve(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        r = request_create(c, headers=AGENT)
        assert r.status_code == 202
        action = r.json()["action"]
        assert action["requested_by"]["kind"] == "agent"
        assert c.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
        assert node.started == []
        rm = c.post("/v1/storage/actions", headers=AGENT, json={"type": "storage.mirror.remove", "params": {"member": "2"}})
        assert rm.status_code == 403  # remove is owner-only
        assert c.post("/v1/storage/actions", headers=GUEST, json={"type": "storage.mirror.repair"}).status_code == 403
        assert c.get("/v1/storage/devices", headers=AGENT).status_code == 403


def test_refusals(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        node.blocked = True
        r = request_create(c)
        assert r.status_code == 409 and "unused:/dev/vdc" in r.json()["message"]
        node.blocked = False
        r = c.post("/v1/storage/actions", headers=OWNER, json={"type": "storage.mirror.replace", "params": {"device": "/dev/vdc"}})
        assert r.status_code == 422 and "member" in r.json()["message"]
        r = c.post("/v1/storage/actions", headers=OWNER, json={"type": "storage.mirror.create", "params": {"device": "/dev/vdc; rm -rf /"}})
        assert r.status_code == 422
        r = c.post("/v1/storage/actions", headers=OWNER, json={"type": "storage.mirror.create", "params": {"device": "/dev/vdc", "node_id": "elsewhere1"}})
        assert r.status_code == 409 and "other nodes" in r.json()["message"]
        r = c.post("/v1/storage/actions", headers=OWNER, json={"type": "storage.mirror.create", "params": {"device": "/dev/vdc"}, "approve": True})
        assert r.status_code == 422  # no owner shortcut for disk changes in v0
        node.busy = True
        action = request_create(c).json()["action"]
        a = c.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).json()
        assert a["state"] == "failed" and "another storage operation" in a["result"]["message"]


def test_idempotent_replay(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        h = {**OWNER, "Idempotency-Key": "disk-2"}
        first = c.post("/v1/storage/actions", headers=h, json={"type": "storage.mirror.create", "params": {"device": "/dev/vdc"}})
        node.sha = SHA_B  # a replay does not re-render
        again = c.post("/v1/storage/actions", headers=h, json={"type": "storage.mirror.create", "params": {"device": "/dev/vdc"}})
        assert first.status_code == 202 and again.status_code == 200
        assert again.json()["action"]["id"] == first.json()["action"]["id"] and again.json()["plan_sha256"] == SHA_A
        other = c.post("/v1/storage/actions", headers=h, json={"type": "storage.mirror.create", "params": {"device": "/dev/vdd"}})
        assert other.status_code == 409


def test_disabled_and_unreachable(settings, clock, node, no_poller):
    with storage_client(settings, clock, node, enabled=False) as c:
        assert c.get("/v1/storage", headers=GUEST).json() == {"node_id": "abc123def456", "enabled": False, "available": False}
        assert request_create(c).status_code == 409
    node.sock = Path("/tmp/om-st-missing/s.sock")
    with storage_client(settings, clock, node) as c:
        assert c.get("/v1/storage", headers=OWNER).json()["available"] is False
        r = request_create(c)
        assert r.status_code == 409 and "not reachable" in r.json()["message"]


def test_summary_has_no_disk_identities(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        s = c.get("/v1/storage", headers=GUEST)
        assert s.status_code == 200 and s.json()["state"] == "unprotected" and s.json()["recovery_key_pending"] is True
        assert SERIAL not in s.text and SERIAL[-4:] not in s.text
        d = c.get("/v1/storage/devices", headers=OWNER).json()
        assert d[0]["serial"] == SERIAL and d[0]["health"]["verdict"] == "ok"


def test_recovery_key_shown_once_to_owners(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        assert c.post("/v1/storage/recovery-key", headers=AGENT).status_code == 403
        r = c.post("/v1/storage/recovery-key", headers=OWNER)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        key = r.json()["one_time"]["recovery_key"]
        assert c.post("/v1/storage/recovery-key", headers=OWNER).status_code == 404
        assert key not in Path(settings.audit_path).read_text()


def test_health_and_state_events_once(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        seen = events(c)
        svc = c.app.state.storage
        svc.poll()
        node.state, node.verdict = "degraded", "critical"
        svc.poll()
        svc.poll()  # no change: nothing new
        types = [e["type"] for e in seen]
        assert types.count("storage.degraded") == 1 and types.count("storage.disk.failing") == 1
        failing = next(e for e in seen if e["type"] == "storage.disk.failing")
        assert failing["severity"] == "critical" and failing["dedupe_key"].startswith("storage:abc123def456:disk:")
        assert SERIAL not in json.dumps(failing) and failing["data"]["serial_tail"] == SERIAL[-4:]
        node.state, node.verdict = "protected", "ok"
        svc.poll()
        types = [e["type"] for e in seen]
        assert "storage.ok" in types and "storage.disk.ok" in types


def test_gateway_restart_keeps_a_running_operation(settings, clock, node, no_poller):
    s = replace(settings, sections={"storage": StorageSettings(enabled=True, socket=node.sock)})
    with TestClient(create_app(s, clock=clock)) as c:
        action = request_create(c).json()["action"]
        assert c.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).json()["state"] == "dispatched"
    with TestClient(create_app(s, clock=clock)) as c:  # the gateway restarts mid-operation
        assert c.get(f"/v1/actions/{action['id']}", headers=OWNER).json()["state"] == "dispatched"
        node.ops[action["id"]].update(state="rolled_back", error="step 13 device-add exited 1")
        c.app.state.storage.poll()
        a = c.get(f"/v1/actions/{action['id']}", headers=OWNER).json()
        assert a["state"] == "failed" and "rolled back" in a["result"]["message"]


def test_dispatched_but_never_started(settings, clock, node, no_poller):
    with storage_client(settings, clock, node) as c:
        action = request_create(c).json()["action"]
        c.post(f"/v1/actions/{action['id']}/approve", headers=OWNER)
        node.ops.clear()  # the node never got it
        c.app.state.storage.poll()
        a = c.get(f"/v1/actions/{action['id']}", headers=OWNER).json()
        assert a["state"] == "failed" and "never started" in a["result"]["message"]


def test_background_poller_runs(settings, clock, node):
    s = replace(settings, sections={"storage": StorageSettings(enabled=True, socket=node.sock, poll_s=5)})
    seen: list[dict] = []
    app = create_app(s, clock=clock)
    app.state.gateway.events.subscribe("storage.state", seen.append)
    with TestClient(app):
        for _ in range(50):
            if seen:
                break
            threading.Event().wait(0.05)
    assert seen and seen[0]["data"]["state"] == "unprotected"


def test_storage_settings_validate():
    with pytest.raises(ValueError):
        StorageSettings(poll_s=1).validate()
