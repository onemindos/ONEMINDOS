# SPDX-License-Identifier: Apache-2.0
"""Time zone and clock (P-04): a real gateway, ledger, approval rule and audit chain talk over a real Unix
socket to a stand-in for `onemindd host serve` that answers like internal/host (same routes and JSON). An agent
may ask for a zone change, never approve it; the owner approves; the host journal closes the action; the clock
state is read from the host and every field is checked again here.
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
from onemind_core.identity import IdentitySettings
from onemind_core.identity.scopes import required_scopes
from onemind_core.netconf import NetSettings
from onemind_core.routers.clock import parse_time
from test_identity import ORIGIN, RP_ID

GOOD_TIME = {"schema": "onemind.host.time/v1", "zone": "Europe/Berlin", "ntp_enabled": True, "ntp_synchronized": True,
             "server": "0.debian.pool.ntp.org", "stratum": 2, "last_sync_at": "2026-11-25T12:00:00Z",
             "at": "2026-11-25T12:30:00Z", "problem": None}
KINDS = ("restart", "shutdown", "factory-reset", "os-install", "service-restart", "set-timezone")


class FakeHost:
    """GET /v1/status, GET /v1/time, POST /v1/operations, GET /v1/operations/{id}."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="tz")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = os.path.join(self.dir, "host.sock")
        self.posts: list[dict] = []
        self.ops: dict[str, dict] = {}
        self.time: dict | None = GOOD_TIME
        self.time_status = 200
        self.kinds = KINDS
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
                    ops = [{"kind": k, "available": True, "unavailable_reason": None} for k in host.kinds]
                    return self.send(200, {"schema": "onemind.host/v1", "journal": True, "operations": ops})
                if self.path == "/v1/time":
                    return self.send(host.time_status, host.time)
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


@pytest.fixture(autouse=True)
def zones(monkeypatch):
    """The same zone database everywhere: CI's container may have none, a laptop has all of them."""
    monkeypatch.setattr("zoneinfo.available_timezones", lambda: {"UTC", "Europe/Berlin", "Pacific/Auckland"})


@pytest.fixture
def host():
    h = FakeHost()
    yield h
    h.close()


@contextmanager
def box(settings, clock, sock: str):
    s = replace(settings, sections={
        "identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False),
        "net": NetSettings(host_socket=Path(sock)), "hostlink": HostLinkSettings(socket=Path(sock))})
    with TestClient(create_app(s, clock=clock)) as c:
        yield c


def set_zone(c, zone="Europe/Berlin", who=OWNER, **body):
    return c.post("/v1/system/time/zone", headers=who, json={"zone": zone, **body})


def audit(settings) -> list[dict]:
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines() if x.strip()]


def test_the_owner_reads_the_zone_and_the_sync_state(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = c.get("/v1/system/time", headers=OWNER)
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["available"] is True and v["zone"] == "Europe/Berlin" and v["ntp_synchronized"] is True and v["ntp_enabled"] is True
        assert v["server"] == "0.debian.pool.ntp.org" and v["stratum"] == 2 and v["last_sync_at"].startswith("2026-11-25T12:00:00")
        assert v["at"]  # the hub's own clock
        for who in (ADULT, GUEST, AGENT):
            assert c.get("/v1/system/time", headers=who).status_code == 403


def test_an_unsynchronised_clock_is_reported_as_it_is(settings, clock, host):
    host.time = {**GOOD_TIME, "ntp_synchronized": False, "server": None, "stratum": None, "last_sync_at": None}
    with box(settings, clock, host.path) as c:
        v = c.get("/v1/system/time", headers=OWNER).json()
        assert v["ntp_synchronized"] is False and v["server"] is None and v["last_sync_at"] is None


def test_host_fields_that_fail_their_checks_are_dropped():
    v = parse_time({**GOOD_TIME, "zone": "../../etc/passwd", "server": "bad host\nname", "stratum": 99,
                    "ntp_synchronized": "yes", "last_sync_at": "never", "problem": 5}, None)
    assert v.available and v.zone is None and v.server is None and v.stratum is None
    assert v.ntp_synchronized is None and v.last_sync_at is None and v.problem is None
    assert parse_time({"schema": "something else"}, None).reason == "bad_response"


def test_an_unreachable_or_failing_host_says_so(settings, clock, host):
    with box(settings, clock, "/nonexistent/host.sock") as c:
        v = c.get("/v1/system/time", headers=OWNER).json()
        assert v["available"] is False and v["reason"] == "host_service_unreachable" and v["zone"] is None
        r = set_zone(c)
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
        assert c.get("/v1/actions", headers=OWNER).json() == []
    host.time_status, host.time = 500, {"error": "internal"}
    with box(settings, clock, host.path) as c:
        assert c.get("/v1/system/time", headers=OWNER).json()["reason"] == "host_service_error"


def test_an_agent_can_ask_for_a_zone_but_only_the_owner_approves_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = set_zone(c, "Pacific/Auckland", who=AGENT, reason="the owner moved")
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == "system.set_timezone" and a["state"] == "awaiting_approval" and a["params"] == {"zone": "Pacific/Auckland"}
        assert r.headers["Location"] == f"/v1/actions/{a['id']}"
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403  # an agent never approves
        assert host.posts == []  # nothing reached the host before the owner approved
        ok = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        assert ok.status_code == 200 and ok.json()["state"] == "dispatched", ok.text
        assert host.posts == [{"action_id": a["id"], "kind": "set-timezone", "zone": "Pacific/Auckland"}]
        host.ops[a["id"]].update(state="succeeded", message="time zone set to Pacific/Auckland")
        c.app.state.hostlink.poll()
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and done["requested_by"]["kind"] == "agent", done
        events = [x["event"] for x in audit(settings) if x.get("action_id") == a["id"]]
        assert "action.requested" in events and any(e.startswith("action.approved") for e in events), events


def test_a_host_that_fails_the_change_ends_the_action_failed(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = set_zone(c).json()
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).status_code == 200
        host.ops[a["id"]].update(state="failed", reason="host_error", message="setting the time zone failed")
        c.app.state.hostlink.poll()
        assert c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "failed"


@pytest.mark.parametrize("zone,status", [("../../etc/passwd", 422), ("Europe//Berlin", 422), ("posix/UTC", 422), ("localtime", 422), ("posixrules", 422), ("Factory", 422), ("Mars/Olympus_Mons", 409)])
def test_a_bad_zone_is_refused_and_nothing_is_filed(settings, clock, host, zone, status):
    with box(settings, clock, host.path) as c:
        r = set_zone(c, zone)
        assert r.status_code == status, r.text
        if status == 409:
            assert r.json()["reason"] == "unknown_zone"
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.posts == []


def test_a_host_without_the_kind_files_nothing(settings, clock, host):
    host.kinds = KINDS[:-1]  # an older host service
    with box(settings, clock, host.path) as c:
        r = set_zone(c)
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_only_owners_and_agents_may_ask_the_generic_route_cannot_file_it_and_a_retry_replays(settings, clock, host):
    with box(settings, clock, host.path) as c:
        for who in (ADULT, GUEST):
            assert set_zone(c, who=who).status_code == 403
        r = c.post("/v1/actions", headers=OWNER, json={"type": "system.set_timezone", "params": {"zone": "UTC"},
                                                        "idempotency_key": "k1", "expires_at": "2099-01-01T00:00:00Z"})
        assert r.status_code == 422  # only the route that checks the zone files it
        first, again = set_zone(c, idempotency_key="same"), set_zone(c, idempotency_key="same")
        assert first.status_code == 202 and again.status_code == 200 and again.json()["id"] == first.json()["id"]


def test_routes_are_scoped():
    assert required_scopes("GET", "/v1/system/time") == ("system:admin",)
    assert required_scopes("POST", "/v1/system/time/zone") == ("actions:request",)
