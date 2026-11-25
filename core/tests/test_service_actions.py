# SPDX-License-Identifier: Apache-2.0
"""Service logs and restart (#636): a real gateway, ledger, approval rule and audit chain talk over a real
Unix socket to a stand-in for `onemindd host serve` that answers like internal/host and internal/svcregistry
(same routes, status codes and JSON). An agent may ask for a restart, never run it; only the owner approves,
with a passkey; a unit that is not restartable answers 403; every log line is redacted before it leaves.
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
from onemind_core.hostservices import parse_view
from onemind_core.identity import IdentitySettings
from onemind_core.identity.scopes import required_scopes
from onemind_core.netconf import NetSettings
from test_identity import ORIGIN, RP_ID, SoftAuthenticator, register_passkey, setup_owner
from test_system_services import GOOD, GW, NATS

# What a wrong host (or registry) might claim: the rescue console as restartable. The gateway never believes it.
RESCUE = {**GW, "unit": "onemind-rescue.service", "name": "Rescue console", "depends_on": [], "risk": "high",
          "description": "The rescue console on the box's own screen and the LAN page."}
CARDS = {**GOOD, "services": [GW, {**NATS, "restartable": False}, RESCUE]}
TOKEN = "om_pat_" + "s3cr3tT0kenValue1234"  # test values, split for scanners
EMAIL = "owner" + "@" + "example.org"
LOG = [f"2026-11-22T10:00:00+0000 box onemind-gateway[7]: request Authorization: Bearer {TOKEN}",
       f"2026-11-22T10:00:01+0000 box onemind-gateway[7]: db password=hunter2 user={EMAIL}",
       "2026-11-22T10:00:02+0000 box onemind-gateway[7]: listening"]


class FakeHost:
    """GET /v1/status, /v1/services, /v1/services/{unit}/logs, POST /v1/operations, GET /v1/operations/{id}."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="sa")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = os.path.join(self.dir, "host.sock")
        self.posts: list[dict] = []
        self.ops: dict[str, dict] = {}
        self.log_requests: list[str] = []
        host = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"  # one request per connection; a logs body ends when the host closes

            def log_message(self, *a):
                pass

            def send(self, code, body, ctype="application/json"):
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/v1/status":
                    ops = [{"kind": k, "available": True, "unavailable_reason": None}
                           for k in ("restart", "shutdown", "factory-reset", "os-install", "service-restart", "set-hostname")]
                    return self.send(200, {"schema": "onemind.host/v1", "journal": True, "operations": ops})
                if self.path == "/v1/services":
                    return self.send(200, CARDS)
                if self.path.startswith("/v1/services/"):
                    host.log_requests.append(self.path)
                    if not self.path.startswith("/v1/services/onemind-gateway.service/logs?"):
                        return self.send(404, {"error": "not_found", "reason": "unknown_unit", "message": "not listed"})
                    return self.send(200, "".join(x + "\n" for x in LOG).encode(), "text/plain; charset=utf-8")
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
def box(settings, clock, sock: str, *, passkey=False):
    s = replace(settings, sections={
        "identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False),
        "net": NetSettings(host_socket=Path(sock)), "hostlink": HostLinkSettings(socket=Path(sock))})
    with TestClient(create_app(s, clock=clock)) as c:
        if passkey:
            setup_owner(c)
            c.key = SoftAuthenticator()
            register_passkey(c, c.key)
        yield c


def restart(c, unit="onemind-gateway.service", who=OWNER, **body):
    return c.post(f"/v1/system/services/{unit}/restart", headers=who, json=body or None)


def audit(settings) -> list[dict]:
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines() if x.strip()]


def test_an_agent_can_request_a_restart_but_not_run_it(settings, clock, host):
    with box(settings, clock, host.path, passkey=True) as c:
        r = restart(c, who=AGENT, reason="the gateway looks stuck")
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == "service.restart" and a["state"] == "awaiting_approval" and a["params"] == {"unit": "onemind-gateway.service"}
        assert r.headers["Location"] == f"/v1/actions/{a['id']}"
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403  # an agent never approves
        refused = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)  # the owner's token alone is not enough
        assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
        assert host.posts == [] and c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
        opts = c.post(f"/v1/actions/{a['id']}/approve-options", headers=OWNER).json()
        ok = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER, json={"webauthn": c.key.assert_(opts["challenge"], flat=True)})
        assert ok.status_code == 200 and ok.json()["state"] == "dispatched", ok.text
        assert host.posts == [{"action_id": a["id"], "kind": "service-restart", "unit": "onemind-gateway.service"}]
        host.ops[a["id"]].update(state="succeeded", message="onemind-gateway.service restarted")
        c.app.state.hostlink.poll()
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and done["requested_by"]["kind"] == "agent", done
        events = [x["event"] for x in audit(settings) if x.get("action_id") == a["id"]]
        assert "action.requested" in events and any(e.startswith("action.approved") for e in events), events


@pytest.mark.parametrize("unit,status", [
    ("onemind-rescue.service", 403),   # the host claims restartable: the never list wins
    ("onemind-nats.service", 403),     # the registry says restartable: false
    ("onemind-mystery.service", 404),  # not in the registry
    ("not a unit", 404),
])
def test_a_unit_that_is_not_restartable_is_refused_and_nothing_is_filed(settings, clock, host, unit, status):
    with box(settings, clock, host.path) as c:
        r = restart(c, unit=unit)
        assert r.status_code == status, r.text
        if status == 403:
            assert r.json()["reason"] == "not_restartable"
            assert any(x["event"] == "authz.denied" for x in audit(settings))
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.posts == []


def test_only_owners_and_agents_may_ask_and_the_generic_route_cannot_file_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        for who in (ADULT, GUEST):
            assert restart(c, who=who).status_code == 403
        r = c.post("/v1/actions", headers=OWNER, json={"type": "service.restart", "params": {"unit": "onemind-rescue.service"},
                                                        "idempotency_key": "k1", "expires_at": "2099-01-01T00:00:00Z"})
        assert r.status_code == 422  # only the route that checks the registry files it
        first, again = restart(c, idempotency_key="same"), restart(c, idempotency_key="same")
        assert first.status_code == 202 and again.status_code == 200 and again.json()["id"] == first.json()["id"]
        hdr = {**OWNER, "Idempotency-Key": "hdr-1"}  # the contract's header (openapi-lint) replays the same way
        h1 = c.post("/v1/system/services/onemind-gateway.service/restart", headers=hdr)
        h2 = c.post("/v1/system/services/onemind-gateway.service/restart", headers=hdr)
        assert h1.status_code == 202 and h2.status_code == 200 and h2.json()["id"] == h1.json()["id"] != first.json()["id"]


def test_a_seeded_token_in_a_log_line_is_masked(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = c.get("/v1/system/services/onemind-gateway.service/logs?tail=50", headers=OWNER)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain"), r.text
        assert TOKEN not in r.text and "hunter2" not in r.text and EMAIL not in r.text
        assert r.text.count("\n") == 3 and "[redacted]" in r.text and "listening" in r.text
        assert host.log_requests[-1] == "/v1/services/onemind-gateway.service/logs?lines=50&follow=0"
        s = c.get("/v1/system/services/onemind-gateway.service/logs?follow=true", headers=OWNER)
        assert s.status_code == 200 and s.headers["content-type"].startswith("text/event-stream")
        assert TOKEN not in s.text and s.text.count("data: ") == 4 and "event: end" in s.text
        assert c.get("/v1/system/services/onemind-mystery.service/logs", headers=OWNER).status_code == 404
        for who in (ADULT, AGENT):
            assert c.get("/v1/system/services/onemind-gateway.service/logs", headers=who).status_code == 403


def test_an_unreachable_host_files_nothing_and_says_so(settings, clock):
    with box(settings, clock, "/nonexistent/host.sock") as c:
        r = restart(c)
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
        assert c.get("/v1/system/services/onemind-gateway.service/logs", headers=OWNER).status_code == 409
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_never_restart_units_show_no_button_and_routes_are_scoped():
    v = parse_view({**GOOD, "services": [RESCUE, {**GW, "unit": "onemind-data-layout.service"},
                                         {**GW, "unit": "onemind-host.service"}, {**GW, "unit": "onemind-firstboot.service"}, GW]})
    assert [c.restartable for c in v.services] == [False, False, False, False, True]
    assert required_scopes("GET", "/v1/system/services/onemind-gateway.service/logs") == ("system:admin",)
    assert required_scopes("POST", "/v1/system/services/onemind-gateway.service/restart") == ("actions:request",)
