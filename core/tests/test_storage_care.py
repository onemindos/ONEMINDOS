# SPDX-License-Identifier: Apache-2.0
"""Storage housekeeping (P-10): a real gateway talks over a real Unix socket to a stand-in for
`onemindd host serve` that answers like internal/host (same routes, status codes and JSON).
TRIM status and the drive list are read; an agent may ask to remove a drive, never run it; only the owner
approves; a drive the box is using is refused; smartd's warnings become one alert each, never twice.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.hostlink import HostLinkSettings
from onemind_core.identity.scopes import required_scopes
from onemind_core.netconf import NetSettings

STICK = {"device": "/dev/sdb", "model": "Cruzer", "serial": "4C530001230", "size_bytes": 16000000000, "label": "HOLIDAY",
         "mountpoints": ["/run/media/holiday"], "ejectable": True, "partitions": 1}
BUSY = {"device": "/dev/sdc", "model": "Boot stick", "size_bytes": 500, "mountpoints": ["/data/odd"], "ejectable": False,
        "why_not": "the box is using this drive (/data/odd)", "partitions": 1}
SMART = {"id": "t1-sda-Health", "at": "2026-11-25T01:00:00Z", "device": "/dev/sda", "kind": "FailedHealthCheck",
         "message": "SMART health check failed"}
VIEW = {"trim": {"enabled": True, "timer_state": "active", "last_run_at": "2026-11-23T00:07:14Z", "last_result": "success",
                 "last_trimmed_bytes": 13314398208, "next_run_at": "2026-11-30T00:00:00Z"},
        "smart": {"daemon_state": "active", "alerts": [SMART]}, "removable": [STICK, BUSY], "at": "2026-11-25T12:00:00Z"}


class FakeHost:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="sc")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = os.path.join(self.dir, "host.sock")
        self.view = json.loads(json.dumps(VIEW))
        self.posts: list[dict] = []
        self.ops: dict[str, dict] = {}
        host = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *a):
                pass

            def send(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/v1/status":
                    ops = [{"kind": k, "available": True, "unavailable_reason": None}
                           for k in ("restart", "shutdown", "factory-reset", "os-install", "service-restart", "eject")]
                    return self.send(200, {"schema": "onemind.host/v1", "journal": True, "operations": ops})
                if self.path == "/v1/storage/housekeeping":
                    return self.send(200, host.view)
                if self.path.startswith("/v1/operations/"):
                    op = host.ops.get(self.path.rsplit("/", 1)[1])
                    return self.send(200, op) if op else self.send(404, {"error": "not_found"})
                self.send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                host.posts.append(body)
                host.ops[body["action_id"]] = {**body, "state": "accepted", "message": "accepted"}
                self.send(202, host.ops[body["action_id"]])

        class S(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True

        self.server = S(self.path, H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)


@pytest.fixture
def host():
    h = FakeHost()
    yield h
    h.close()


@contextmanager
def box(settings, clock, sock: str):
    s = replace(settings, sections={"net": NetSettings(host_socket=Path(sock)), "hostlink": HostLinkSettings(socket=Path(sock))})
    with TestClient(create_app(s, clock=clock)) as c:
        yield c


def eject(c, name="sdb", who=OWNER, **body):
    return c.post(f"/v1/storage/removable/{name}/eject", headers=who, json=body or None)


def test_housekeeping_shows_trim_warnings_and_drives_to_the_owner_only(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = c.get("/v1/storage/housekeeping", headers=OWNER)
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["available"] is True and v["trim"]["last_run_at"] == "2026-11-23T00:07:14Z" and v["trim"]["last_trimmed_bytes"] == 13314398208
        assert v["trim"]["enabled"] is True and v["smart"]["alerts"][0]["device"] == "/dev/sda"
        assert [(d["name"], d["ejectable"]) for d in v["removable"]] == [("sdb", True), ("sdc", False)]
        assert v["removable"][1]["why_not"].startswith("the box is using")
        for who in (ADULT, GUEST, AGENT):
            assert c.get("/v1/storage/housekeeping", headers=who).status_code == 403
        assert required_scopes("GET", "/v1/storage/housekeeping") == ("system:admin",)
        assert required_scopes("POST", "/v1/storage/removable/sdb/eject") == ("actions:request",)


def test_a_trim_that_never_ran_is_null_not_a_made_up_date(settings, clock, host):
    host.view["trim"].update(last_run_at=None, last_result=None, last_trimmed_bytes=None)
    with box(settings, clock, host.path) as c:
        t = c.get("/v1/storage/housekeeping", headers=OWNER).json()["trim"]
        assert t["last_run_at"] is None and t["last_trimmed_bytes"] is None and t["next_run_at"] == "2026-11-30T00:00:00Z"


def test_an_agent_can_ask_to_remove_a_drive_but_only_the_owner_runs_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = eject(c, who=AGENT, reason="the backup to this stick is done")
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == "storage.eject" and a["state"] == "awaiting_approval" and a["params"] == {"device": "/dev/sdb", "serial": "4C530001230"}
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403
        assert host.posts == []
        ok = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        assert ok.status_code == 200 and ok.json()["state"] == "dispatched", ok.text
        assert host.posts == [{"action_id": a["id"], "kind": "eject", "device": "/dev/sdb", "serial": "4C530001230"}]
        host.ops[a["id"]].update(state="succeeded", message="/dev/sdb is safe to remove")
        c.app.state.hostlink.poll()
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and done["requested_by"]["kind"] == "agent", done


@pytest.mark.parametrize("name,status,reason", [
    ("sdc", 409, "in_use"),            # the box is using it
    ("vda", 404, None),                # not a removable drive
    ("sdz", 404, None),                # not plugged in
    ("Sdb", 404, None),             # not a drive name
])
def test_a_drive_that_cannot_be_removed_is_refused_and_nothing_is_filed(settings, clock, host, name, status, reason):
    with box(settings, clock, host.path) as c:
        r = eject(c, name=name)
        assert r.status_code == status, r.text
        if reason:
            assert r.json()["reason"] == reason
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.posts == []


def test_a_drive_the_box_starts_using_before_approval_is_not_ejected(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = eject(c).json()
        host.view["removable"][0].update(ejectable=False, why_not="the box is using this drive (/data/x)")
        r = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        assert r.status_code == 409 and host.posts == []
        assert c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_only_owners_and_agents_may_ask_and_the_generic_route_cannot_file_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        for who in (ADULT, GUEST):
            assert eject(c, who=who).status_code == 403
        r = c.post("/v1/actions", headers=OWNER, json={"type": "storage.eject", "params": {"device": "/dev/vda"},
                                                        "idempotency_key": "k1", "expires_at": "2099-01-01T00:00:00Z"})
        assert r.status_code == 422  # only the route that checks the drive list files it
        first, again = eject(c, idempotency_key="same"), eject(c, idempotency_key="same")
        assert first.status_code == 202 and again.status_code == 200 and again.json()["id"] == first.json()["id"]


def test_an_unreachable_host_says_so_and_files_nothing(settings, clock):
    with box(settings, clock, "/nonexistent/host.sock") as c:
        v = c.get("/v1/storage/housekeeping", headers=OWNER).json()
        assert v["available"] is False and "host service" in v["message"] and v["trim"] is None
        r = eject(c)
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_a_garbled_host_answer_is_unavailable_not_trusted(settings, clock, host):
    host.view["removable"][0]["mountpoints"] = ["/run/media/x\u001b[31m"]
    host.view["trim"].pop("enabled")
    with box(settings, clock, host.path) as c:
        assert c.get("/v1/storage/housekeeping", headers=OWNER).json()["available"] is False


def open_alerts(c):
    return [a for a in c.get("/v1/alerts", headers=OWNER, params={"state": "open"}).json() if a["type"].startswith("storage.smart")]


def test_each_smartd_warning_becomes_one_alert_and_is_never_told_twice(settings, clock, host):
    with box(settings, clock, host.path) as c:
        poll = c.app.state.storage_care_poll
        assert poll() == 1
        (a,) = open_alerts(c)
        assert a["type"] == "storage.smart.failing" and a["severity"] == "critical" and "/dev/sda" in a["title"]
        assert poll() == 0 and len(open_alerts(c)) == 1  # the same warning is not raised again
        host.view["smart"]["alerts"].insert(0, {**SMART, "id": "t2-nvme-Temperature", "device": "/dev/nvme0n1", "kind": "Temperature",
                                                "message": "Temperature 71 Celsius"})
        assert poll() == 1
        assert sorted(x["type"] for x in open_alerts(c)) == ["storage.smart.failing", "storage.smart.warning"]
        # An owner clears one; it stays cleared (told once, even across a restart of the poll).
        assert poll() == 0


def test_the_eject_is_bound_to_the_drive_that_was_asked_about(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = eject(c).json()
        assert a["params"]["serial"] == "4C530001230"
        host.view["removable"][0]["serial"] = "OTHERSTICK"  # another stick came up as sdb before approval
        r = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        assert r.status_code == 409 and host.posts == []
        host.view["removable"][0]["serial"] = "4C530001230"
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).status_code in (200, 202)
        assert host.posts and host.posts[0]["serial"] == "4C530001230" and host.posts[0]["device"] == "/dev/sdb"
