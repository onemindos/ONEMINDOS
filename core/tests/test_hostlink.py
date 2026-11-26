# SPDX-License-Identifier: Apache-2.0
"""The gateway's link to the host executor (#146, #142; docs/leap/core/HOST-ACTIONS.md section 2).

A real gateway and ledger talk over a real Unix socket to a stand-in for `onemindd host serve` that
answers like internal/host/server.go (same routes, status codes and JSON). Nothing reaches the host
before an owner approves; the host gets the action id and kind (and the approved version), never a command.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import tempfile
import threading
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.hostlink import HostLinkSettings
from test_os_updates import HB

NODE = "abc123def456"  # settings.node_id: the hub itself


class FakeHost:
    """onemindd host serve: GET /v1/status, POST /v1/operations, GET /v1/operations/{id}."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="hl")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = os.path.join(self.dir, "host.sock")
        self.posts: list[dict] = []
        self.ops: dict[str, dict] = {}
        self.journal = True
        self.available = {"restart": True, "shutdown": True, "factory-reset": False, "os-install": True}
        self.refuse: tuple[int, dict] | None = None
        self.hostname: object = "testbox"  # GET /v1/status names the box (#875); None leaves the field out
        self.status_code = 200
        self.plan_sha = "ab" * 32  # GET /v1/plans/factory-reset
        host = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def send(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/v1/status":
                    ops = [{"kind": k, "available": v, "unavailable_reason": None if v else f"{k} is off here"}
                           for k, v in host.available.items()]
                    st = {"schema": "onemind.host/v1", "journal": host.journal, "operations": ops, "active_operation": None}
                    if host.hostname is not None:
                        st["hostname"] = host.hostname
                    return self.send(host.status_code, st)
                if self.path == "/v1/plans/factory-reset":
                    return self.send(200, {"schema": "onemind.host.factory-reset-plan/v1", "available": True, "plan_sha256": host.plan_sha})
                if self.path.startswith("/v1/operations/"):
                    op = host.ops.get(self.path.rsplit("/", 1)[1])
                    return self.send(200, op) if op else self.send(404, {"error": "not_found", "reason": "unknown_action", "message": "no host action with that id"})
                self.send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                host.posts.append(body)
                if host.refuse:
                    return self.send(*host.refuse)
                op = host.ops.setdefault(body["action_id"], {**body, "state": "accepted", "message": "accepted"})
                self.send(202, op)

        class S(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        self.server = S(self.path, H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def set_state(self, action_id: str, state: str, **more) -> None:
        self.ops[action_id] = {**self.ops[action_id], "state": state, **more}

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)


@pytest.fixture
def host():
    h = FakeHost()
    yield h
    h.close()


def link_settings(settings, path, **kw):
    return replace(settings, sections={**settings.sections, "hostlink": HostLinkSettings(socket=path, **kw)})


@pytest.fixture
def box(settings, clock, executor, host):
    app = create_app(link_settings(settings, host.path), clock=clock, executor=executor)
    with TestClient(app) as c:
        c.app_, c.clock, c.n, c.host = app, clock, 0, host
        c.link = app.state.hostlink

        def report(update=None, **changes):
            hb = {**HB, "node_id": NODE, **changes, "update": {**HB["update"], **(update or {})}}
            assert app.state.registry.ingest(f"onemind.node.{hb['node_id']}.status", json.dumps(hb).encode())
        c.report = report
        report()
        yield c


def ask(c, params=None, who=OWNER):
    c.n += 1
    return c.post("/v1/actions", headers=who, json={
        "type": "os.update.install", "params": params or {"node_id": NODE, "version": "0.1.2"}, "idempotency_key": f"hl{c.n}",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})


def approved(c) -> dict:
    r = ask(c)
    assert r.status_code == 201, r.text
    done = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert done.status_code == 200, done.text
    return done.json()


def state(c, action_id) -> dict:
    return c.get(f"/v1/actions/{action_id}", headers=OWNER).json()


# ---- can it run? -----------------------------------------------------------------------------------------
def test_status_says_install_is_ready_when_the_host_offers_it(box):
    inst = box.get("/v1/os/updates", headers=OWNER).json()["install"]
    assert inst["available"] is True and inst["reason"] is None


def test_status_reports_the_hosts_own_reason(box, host):
    host.available["os-install"] = False
    inst = box.get("/v1/os/updates", headers=OWNER).json()["install"]
    assert inst == {"available": False, "reason": "unavailable", "message": "os-install is off here"}
    host.available["os-install"], host.journal = True, False
    assert box.get("/v1/os/updates", headers=OWNER).json()["install"]["reason"] == "no_journal"


def test_a_missing_socket_denies_by_default(settings, clock, executor, tmp_path):
    app = create_app(link_settings(settings, tmp_path / "none.sock"), clock=clock, executor=executor)
    with TestClient(app) as c:
        assert c.get("/v1/os/updates", headers=OWNER).json()["install"]["reason"] == "engine_unreachable"
        assert app.state.hostlink.problem("system.restart")[0] == "engine_unreachable"
        assert app.state.hostlink.problem("app.install")[0] == "unavailable"  # not a host action


# ---- the approval gate ---------------------------------------------------------------------------------
def test_nothing_reaches_the_host_before_an_owner_approves(box, host):
    r = ask(box)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert box.post(f"/v1/actions/{r.json()['id']}/approve", headers=ADULT).status_code == 403
    assert ask(box, who=AGENT).status_code == 403
    box.link.poll()
    assert host.posts == [] and host.ops == {}


def test_approval_sends_the_action_id_kind_and_version_only(box, host):
    a = approved(box)
    assert host.posts == [{"action_id": a["id"], "kind": "os-install", "version": "0.1.2"}]
    assert a["state"] == "dispatched"  # the host is working; the poller closes it


# ---- the journal closes the ledger action -----------------------------------------------------------------
def test_succeeded_in_the_journal_closes_the_action(box, host):
    a = approved(box)
    host.set_state(a["id"], "running")
    box.link.poll()
    assert state(box, a["id"])["state"] == "dispatched"
    host.set_state(a["id"], "succeeded", message="installed 0.1.2; rebooting into it")
    box.link.poll()
    done = state(box, a["id"])
    assert done["state"] == "succeeded" and done["result"]["message"] == "installed 0.1.2; rebooting into it"
    assert done["result"]["steps"][0]["kind"] == "os-install"


def test_going_down_keeps_the_action_open(box, host):
    a = approved(box)
    host.set_state(a["id"], "going_down")
    box.link.poll()
    assert state(box, a["id"])["state"] == "dispatched"


@pytest.mark.parametrize("op_reason, outcome", [("engine_declined", "failed"), ("host_error", "failed"), ("interrupted", "outcome_unknown")])
def test_failed_in_the_journal(box, host, op_reason, outcome):
    a = approved(box)
    host.set_state(a["id"], "failed", reason=op_reason, message="the host says no")
    box.link.poll()
    done = state(box, a["id"])
    assert done["state"] == outcome and done["result"]["message"] == "the host says no"


def test_the_host_refusing_ends_the_action_failed_with_its_reason(box, host):
    host.refuse = (409, {"error": "refused", "reason": "update_in_progress", "message": "an update is installing"})
    a = approved(box)
    assert a["state"] == "failed" and "an update is installing" in a["result"]["message"]
    assert a["result"]["steps"][0]["result"] == "update_in_progress"


def test_a_host_that_vanished_between_status_and_approval_fails_not_succeeds(box, host):
    r = ask(box)
    host.close()
    done = box.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()
    assert done["state"] == "failed" and "onemind update apply" in done["result"]["message"]


def test_install_for_another_machine_is_refused_when_the_host_is_there(box):
    box.report(node_id="otherbox00001")
    r = ask(box, {"node_id": "otherbox00001", "version": "0.1.2"})
    assert r.status_code == 409 and r.json()["reason"] == "other_node"


# ---- a reboot restarts the gateway while the host finishes ----------------------------------------------
def test_a_restarted_gateway_reads_the_verdict_from_the_journal(settings, clock, executor, host):
    s = link_settings(settings, host.path)
    with TestClient(create_app(s, clock=clock, executor=executor)) as first:
        first.n, first.clock = 0, clock
        first.app.state.registry.ingest(f"onemind.node.{NODE}.status", json.dumps({**HB, "node_id": NODE}).encode())
        a = approved(first)
        host.set_state(a["id"], "going_down")  # the box powers off; the gateway goes with it
    with TestClient(create_app(s, clock=clock, executor=executor)) as second:
        # Not outcome_unknown: the host's journal owns the answer (actions.SELF_RECONCILED_TYPES).
        assert state(second, a["id"])["state"] == "dispatched"
        host.set_state(a["id"], "succeeded", message="the box is back on 0.1.2")  # next boot
        second.app.state.hostlink.poll()
        done = state(second, a["id"])
        assert done["state"] == "succeeded" and done["result"]["message"] == "the box is back on 0.1.2"


def test_a_restart_before_the_request_was_sent_is_outcome_unknown(settings, clock, executor, host):
    s = link_settings(settings, host.path)
    with TestClient(create_app(s, clock=clock, executor=executor)) as first:
        first.n, first.clock = 0, clock
        first.app.state.registry.ingest(f"onemind.node.{NODE}.status", json.dumps({**HB, "node_id": NODE}).encode())
        r = ask(first).json()
        # Approved (accepted) but the process died before it was dispatched.
        assert first.app.state.actions.repo.transition(r["id"], {"awaiting_approval"}, "accepted", clock())
    with TestClient(create_app(s, clock=clock, executor=executor)) as second:
        assert state(second, r["id"])["state"] == "outcome_unknown"
        assert host.posts == []  # never retried: the owner asks again


def test_an_action_the_host_never_heard_of_gives_up_after_a_while(box, host):
    a = approved(box)
    host.ops.clear()  # the journal lost it (or the request never arrived)
    box.link.poll()
    assert state(box, a["id"])["state"] == "dispatched"  # still inside the grace period
    box.clock.advance(HostLinkSettings().give_up_s + 1)
    box.link.poll()
    done = state(box, a["id"])
    assert done["state"] == "outcome_unknown" and "no record" in done["result"]["message"]


def test_a_silent_host_gives_up_after_a_while(box, host):
    a = approved(box)
    host.close()
    box.link.poll()
    assert state(box, a["id"])["state"] == "dispatched"
    box.clock.advance(HostLinkSettings().give_up_s + 1)
    box.link.poll()
    assert state(box, a["id"])["state"] == "outcome_unknown"


# ---- the image wires the gateway to the socket -----------------------------------------------------------
def test_settings_validate():
    with pytest.raises(ValueError):
        HostLinkSettings(poll_s=0).validate()
    with pytest.raises(ValueError):
        HostLinkSettings(give_up_s=5).validate()
    HostLinkSettings().validate()


# ---- os.rollback (P-16) --------------------------------------------------------------------------------
ROLLBACK_RAUC = {"present": True, "booted_slot": "A", "slots": [
    {"name": "rootfs.0", "class": "rootfs", "bootname": "A", "state": "booted", "boot_status": "good", "bundle_version": "0.1.1"},
    {"name": "rootfs.1", "class": "rootfs", "bootname": "B", "state": "inactive", "boot_status": "good", "bundle_version": "0.1.0"}]}


def ask_rollback(c, version="0.1.0"):
    c.n += 1
    return c.post("/v1/actions", headers=OWNER, json={
        "type": "os.rollback", "params": {"node_id": NODE, "version": version}, "idempotency_key": f"rb{c.n}",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})


def test_a_rollback_is_offered_only_when_the_host_offers_it(box, host):
    box.report(rauc=ROLLBACK_RAUC)
    assert box.get("/v1/os/updates", headers=OWNER).json()["rollback"]["reason"] == "unavailable"  # fake host: not listed
    host.available["os-rollback"] = True
    assert box.get("/v1/os/updates", headers=OWNER).json()["rollback"]["available"] is True
    host.available["os-rollback"] = False  # e.g. the host sees the other slot is bad
    st = box.get("/v1/os/updates", headers=OWNER).json()["rollback"]
    assert st == {"available": False, "reason": "unavailable", "message": "os-rollback is off here"}


def test_an_approved_rollback_sends_the_kind_and_the_version_only(box, host):
    host.available["os-rollback"] = True
    box.report(rauc=ROLLBACK_RAUC)
    r = ask_rollback(box)
    assert r.status_code == 201, r.text
    box.link.poll()
    assert host.posts == []  # nothing reaches the host before the owner approves
    # A bare owner token is not enough: it takes the passkey (test_os_rollback_passkey.py signs one).
    assert box.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).status_code == 401
    assert host.posts == []


def test_the_link_maps_the_action_to_os_rollback():
    from onemind_core.hostlink import KINDS
    assert KINDS["os.rollback"] == "os-rollback"


def test_a_rollback_the_host_would_refuse_is_not_filed(box, host):
    """After a go-back the heartbeat still shows the version just left as a good slot; only the host knows
    (it keeps that version in the gate's bad-releases list), so the request is refused when it is filed."""
    box.report(rauc=ROLLBACK_RAUC)
    host.available["os-rollback"] = False
    r = ask_rollback(box)
    assert r.status_code == 409 and r.json()["reason"] == "unavailable" and "os-rollback is off here" in r.json()["message"]
    host.available["os-rollback"] = True
    assert ask_rollback(box).status_code == 201
