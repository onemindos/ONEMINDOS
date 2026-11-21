# SPDX-License-Identifier: Apache-2.0
"""Network screen route (NET-UI-01, #239): a real gateway reads a real host service over a real Unix
socket (the same JSON internal/netview emits). Addresses are RFC 5737 / RFC 3849 documentation ranges."""

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
from onemind_core.hostnet import parse_view
from onemind_core.netconf import NetSettings

GOOD = {
    "schema": "onemind.netview/v1", "at": "2026-11-20T12:00:00Z",
    "interfaces": [
        {"name": "eth0", "kind": "ethernet", "state": "up", "mac": "00:00:5e:00:53:01", "mtu": 1500,
         "addresses": ["192.0.2.10/24", "2001:db8::10/64"]},
        {"name": "wlan0", "kind": "wifi", "state": "down", "mac": "00:00:5e:00:53:02", "mtu": 1500, "addresses": [],
         "wifi": {"signal_dbm": -50}},
        {"name": "lo", "kind": "loopback", "state": "unknown", "mtu": 65536, "addresses": ["127.0.0.1/8"]},
    ],
    "gateways": [{"interface": "eth0", "via": "192.0.2.1", "family": "ipv4"}],
    "dns": ["192.0.2.53", "2001:db8::53"],
    "ports": [{"proto": "tcp", "addr": "0.0.0.0", "port": 22, "scope": "any"},
              {"proto": "tcp", "addr": "127.0.0.1", "port": 8080, "scope": "loopback"}],
}


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline().decode()
        while self.rfile.readline().strip():
            pass
        status, body = self.server.answer if line.startswith("GET /v1/network ") else (404, {})
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.wfile.write(f"HTTP/1.1 {status} X\r\nContent-Type: application/json\r\nContent-Length: {len(raw)}\r\nConnection: close\r\n\r\n".encode() + raw)


class _Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    answer: tuple[int, object] = (200, GOOD)


@pytest.fixture
def host():
    d = tempfile.mkdtemp(prefix="nv")  # short: AF_UNIX paths are limited to about 100 bytes
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


def test_owner_reads_interfaces_gateway_dns_and_ports(settings, clock, executor, host):
    with box(settings, clock, executor, host.path) as c:
        r = c.get("/v1/network", headers=OWNER)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["available"] is True and b["dropped"] == 0 and b["reason"] is None
        assert [i["name"] for i in b["interfaces"]] == ["eth0", "wlan0", "lo"]
        assert b["interfaces"][0]["addresses"] == ["192.0.2.10/24", "2001:db8::10/64"]
        assert b["interfaces"][1]["wifi"] == {"signal_dbm": -50}
        assert b["gateways"] == [{"interface": "eth0", "via": "192.0.2.1", "family": "ipv4"}]
        assert b["dns"] == ["192.0.2.53", "2001:db8::53"]
        assert {"proto": "tcp", "addr": "127.0.0.1", "port": 8080, "scope": "loopback"} in b["ports"]


@pytest.mark.parametrize("who", [ADULT, AGENT])
def test_only_the_owner_sees_the_network(settings, clock, executor, host, who):
    with box(settings, clock, executor, host.path) as c:
        assert c.get("/v1/network", headers=who).status_code == 403
        assert c.get("/v1/network").status_code == 401


def test_unreachable_host_service_is_said_not_hidden(settings, clock, executor):
    with box(settings, clock, executor, "/nonexistent/host.sock") as c:
        r = c.get("/v1/network", headers=OWNER)
        assert r.status_code == 200
        b = r.json()
        assert b["available"] is False and b["reason"] == "host_service_unreachable" and b["interfaces"] == []


def test_host_service_error_and_garbage(settings, clock, executor, host):
    with box(settings, clock, executor, host.path) as c:
        host.answer = (500, {"error": "internal"})
        assert c.get("/v1/network", headers=OWNER).json()["reason"] == "host_service_error"
        host.answer = (200, b"<html>not json</html>")
        assert c.get("/v1/network", headers=OWNER).json()["reason"] == "bad_response"
        host.answer = (200, {"schema": "something-else/v9"})
        assert c.get("/v1/network", headers=OWNER).json()["reason"] == "bad_response"


def test_every_field_is_rechecked_and_bad_entries_dropped():
    """H-06: nothing the host service sends reaches a screen unchecked, and one bad entry hides no other."""
    bad = {**GOOD,
           "interfaces": [GOOD["interfaces"][0],
                          {**GOOD["interfaces"][0], "name": "<script>alert(1)</script>"},
                          {**GOOD["interfaces"][0], "name": "e1", "mac": "not-a-mac"},
                          {**GOOD["interfaces"][0], "name": "e2", "kind": "wormhole"},
                          {**GOOD["interfaces"][0], "name": "e3", "addresses": ["999.1.1.1/8"]},
                          {**GOOD["interfaces"][0], "name": "e4", "mtu": -5},
                          "not an object"],
           "gateways": [{"interface": "eth0", "via": "192.0.2.1", "family": "ipv6"}, GOOD["gateways"][0]],
           "dns": ["192.0.2.53", "javascript:alert(1)", 7],
           "ports": [{"proto": "tcp", "addr": "0.0.0.0", "port": 70000, "scope": "any"},
                     {"proto": "sctp", "addr": "0.0.0.0", "port": 22, "scope": "any"},
                     GOOD["ports"][0]]}
    v = parse_view(bad)
    assert v.available
    assert [i.name for i in v.interfaces] == ["eth0"]
    assert [g.via for g in v.gateways] == ["192.0.2.1"] and v.gateways[0].family == "ipv4"
    assert v.dns == ["192.0.2.53"]
    assert [p.port for p in v.ports] == [22]
    assert v.dropped == 6 + 1 + 2 + 2


def test_scope_ids_non_text_addresses_and_too_many_interfaces_are_refused():
    eth = GOOD["interfaces"][0]
    v = parse_view({**GOOD, "interfaces": [{**eth, "addresses": ["fe80::1%eth0/64"]}, {**eth, "name": "e1", "addresses": [5]}, eth],
                    "gateways": [{"interface": "eth0", "via": "fe80::1%eth0", "family": "ipv6"}],
                    "dns": ["fe80::53%eth0"]})
    assert [i.name for i in v.interfaces] == ["eth0"] and v.gateways == [] and v.dns == [] and v.dropped == 4
    many = [{**eth, "name": f"v{i}"} for i in range(70)]
    v = parse_view({**GOOD, "interfaces": many})
    assert len(v.interfaces) == 64 and v.dropped == 6


def test_wifi_signal_out_of_range_is_not_believed():
    wl = {**GOOD["interfaces"][1], "wifi": {"signal_dbm": 9999}}
    assert parse_view({**GOOD, "interfaces": [wl]}).interfaces[0].wifi.signal_dbm is None


def test_openapi_describes_the_route(client):
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/v1/network"]["get"]["operationId"] == "network.view"
