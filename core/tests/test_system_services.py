# SPDX-License-Identifier: Apache-2.0
"""Service cards (#623): a real gateway reads a real host service over a real Unix socket, answering
the JSON internal/svcregistry emits, and checks every card again before a screen sees it."""

from __future__ import annotations

import json
import os
import socketserver
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.hostservices import parse_view
from onemind_core.netconf import NetSettings

GW = {"unit": "onemind-gateway.service", "name": "Gateway", "docs": "docs/leap/core/PLUMBING.md", "restartable": True,
      "risk": "medium", "depends_on": ["onemind-nats.service"], "known": True, "installed": True,
      "description": "The front door: dashboard, phone app, CLI and agents all talk to it.",
      "load_state": "loaded", "active_state": "active", "sub_state": "running", "memory_bytes": 104857600, "version": "0.2.0"}
NATS = {**GW, "unit": "onemind-nats.service", "name": "Message bus", "depends_on": [], "active_state": "failed",
        "sub_state": "failed", "memory_bytes": None, "description": "Carries events between the gateway and apps."}
MYSTERY = {"unit": "onemind-mystery.service", "name": "onemind-mystery.service", "description": "", "docs": "",
           "restartable": False, "risk": "unknown", "depends_on": [], "known": False, "installed": True,
           "load_state": "loaded", "active_state": "active", "sub_state": "running", "memory_bytes": 4096, "version": None}
GOOD = {"schema": "onemind.host.services/v1", "registry": "ok", "registry_error": None, "at": "2026-11-21T12:00:00Z",
        "services": [GW, NATS, MYSTERY]}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode()
        while self.rfile.readline().strip():
            pass
        status, body = self.server.answer if line.startswith("GET /v1/services ") else (404, {})
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.wfile.write(f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {len(raw)}\r\nConnection: close\r\n\r\n".encode() + raw)


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    answer: tuple[int, object] = (200, GOOD)


@pytest.fixture
def host():
    d = tempfile.mkdtemp(prefix="sv")  # short: AF_UNIX paths are limited to about 100 bytes
    sock = os.path.join(d, "h.sock")
    srv = _Server(sock, _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.path = sock
    yield srv
    srv.shutdown()
    srv.server_close()


def box(settings, clock, executor, sock: str):
    s = replace(settings, sections={"net": NetSettings(host_socket=Path(sock))})
    return TestClient(create_app(s, clock=clock, executor=executor))


def test_owner_reads_the_service_cards(settings, clock, executor, host):
    with box(settings, clock, executor, host.path) as c:
        r = c.get("/v1/system/services", headers=OWNER)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["available"] is True and b["registry"] == "ok" and b["dropped"] == 0 and b["unknown"] == 1
        assert [s["unit"] for s in b["services"]] == ["onemind-gateway.service", "onemind-nats.service", "onemind-mystery.service"]
        gw = b["services"][0]
        assert gw["name"] == "Gateway" and gw["risk"] == "medium" and gw["restartable"] is True
        assert gw["active_state"] == "active" and gw["memory_bytes"] == 104857600 and gw["version"] == "0.2.0"
        assert gw["docs"] == "docs/leap/core/PLUMBING.md" and gw["depends_on"] == ["onemind-nats.service"]
        assert b["services"][1]["memory_bytes"] is None and b["services"][1]["active_state"] == "failed"
        m = b["services"][2]
        assert m["known"] is False and m["risk"] == "unknown" and m["description"] == "" and m["restartable"] is False


@pytest.mark.parametrize("who", [ADULT, AGENT])
def test_only_the_owner_sees_the_services(settings, clock, executor, host, who):
    with box(settings, clock, executor, host.path) as c:
        assert c.get("/v1/system/services", headers=who).status_code == 403
        assert c.get("/v1/system/services").status_code == 401


def test_unreachable_host_service_is_said_not_hidden(settings, clock, executor):
    with box(settings, clock, executor, "/nonexistent/host.sock") as c:
        b = c.get("/v1/system/services", headers=OWNER).json()
        assert b["available"] is False and b["reason"] == "host_service_unreachable" and b["services"] == []


def test_host_service_error_garbage_and_a_missing_registry(settings, clock, executor, host):
    with box(settings, clock, executor, host.path) as c:
        host.answer = (500, {"error": "internal"})
        assert c.get("/v1/system/services", headers=OWNER).json()["reason"] == "host_service_error"
        host.answer = (200, b"<html>not json</html>")
        assert c.get("/v1/system/services", headers=OWNER).json()["reason"] == "bad_response"
        host.answer = (200, {"schema": "onemind.netview/v1"})
        assert c.get("/v1/system/services", headers=OWNER).json()["reason"] == "bad_response"
        host.answer = (200, {**GOOD, "registry": "missing", "services": [MYSTERY]})
        b = c.get("/v1/system/services", headers=OWNER).json()
        assert b["registry"] == "missing" and b["unknown"] == 1 and "unknown" in b["message"]


def test_every_card_is_rechecked_and_bad_ones_dropped():
    """H-06: nothing the host service sends reaches a screen unchecked, and one bad card hides no other."""
    bad = [
        {**GW, "unit": "../../etc/passwd"},
        {**GW, "unit": "onemind-a.service", "name": "<b>\x1b[31m</b>"},
        {**GW, "unit": "onemind-b.service", "risk": "none"},
        {**GW, "unit": "onemind-c.service", "docs": "https://evil.invalid/x.md"},
        {**GW, "unit": "onemind-d.service", "memory_bytes": -1},
        {**GW, "unit": "onemind-e.service", "active_state": "ACTIVE; rm -rf"},
        {**GW, "unit": "onemind-f.service", "restartable": "yes"},
        {**GW, "unit": "onemind-g.service", "depends_on": ["not a unit"]},
        GW,  # listed twice: the second is dropped
        "not an object",
    ]
    v = parse_view({**GOOD, "services": [GW, *bad]})
    assert v.available and [c.unit for c in v.services] == ["onemind-gateway.service"] and v.dropped == len(bad)


def test_an_unknown_card_carries_nothing_the_registry_did_not_vouch_for():
    v = parse_view({**GOOD, "services": [{**MYSTERY, "name": "Totally safe", "description": "Trust me, I am the gateway.",
                                          "restartable": True, "risk": "low", "docs": "docs/x.md", "version": "9.9.9"}]})
    c = v.services[0]
    assert (c.name, c.description, c.restartable, c.risk, c.docs, c.version) == (
        "onemind-mystery.service", "", False, "unknown", None, None)


def test_openapi_describes_the_route(client):
    spec = client.get("/openapi.json").json()
    op = spec["paths"]["/v1/system/services"]["get"]
    assert op["operationId"] == "system.services.list"
    assert "ServiceCard" in spec["components"]["schemas"] and "ServicesView" in spec["components"]["schemas"]
