# SPDX-License-Identifier: Apache-2.0
"""P-08: a wired address change as an owner action with an automatic way back.

A real gateway, ledger, approval rule, passkey step-up and audit chain talk over a real Unix socket to a
stand-in for `onemindd host serve` that answers like internal/host/netset.go (same routes, status codes and
JSON). The stand-in keeps the pending change the way the box does. What is judged here: nothing changes
before an owner approves with a passkey, the host gets exactly what was approved, refusals file nothing,
and only an owner may ask or confirm. That NetworkManager really rolls back is judged by the QEMU battery
(test/qemu/CRITERIA-NETWORK-SET.md). Addresses are RFC 5737 documentation ranges.
"""

from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.identity import IdentitySettings
from onemind_core.netconf import NetSettings
from test_identity import ORIGIN, RP_ID, SoftAuthenticator, register_passkey, setup_owner
from test_network_view import GOOD

STATIC = {"mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.1", "dns": ["192.0.2.53"], "rollback_seconds": 45}
NOW = "2026-11-25T12:00:00Z"
LATER = "2026-11-25T12:00:45Z"


class FakeHost:
    """GET /v1/network, GET /v1/network/changes, PUT /v1/network/{iface}, POST /v1/network/{iface}/confirm."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="nc")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = os.path.join(self.dir, "host.sock")
        self.puts: list[tuple[str, dict]] = []
        self.confirms: list[tuple[str, str]] = []
        self.pending: dict | None = None
        self.last: dict | None = None
        self.available = True
        self.fail: tuple[int, dict] | None = None
        self.put_delay = 0.0  # answers after this long, but has already applied the change
        self.changes_delay = 0.0  # GET /v1/network/changes answers after this long
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

            def status(self):
                why = None if host.available else "NetworkManager is not running on this box"
                return {"available": host.available, "unavailable_reason": why, "pending": host.pending, "last": host.last}

            def do_GET(self):
                if self.path == "/v1/network":
                    return self.send(200, GOOD)
                if self.path == "/v1/network/changes":
                    if host.changes_delay:
                        time.sleep(host.changes_delay)
                    try:
                        return self.send(200, self.status())
                    except OSError:
                        return None  # the gateway gave up waiting
                self.send(404, {})

            def do_PUT(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                host.puts.append((self.path.rsplit("/", 1)[1], body))
                if host.fail:
                    return self.send(*host.fail)
                host.pending = {"action_id": body.get("action_id"), "interface": self.path.rsplit("/", 1)[1], "mode": body["mode"], "address": body.get("address"),
                                "gateway": body.get("gateway"), "dns": body.get("dns", []), "result": "pending",
                                "started_at": NOW, "deadline": LATER}
                if host.put_delay:
                    time.sleep(host.put_delay)
                try:
                    self.send(200, self.status())
                except OSError:
                    pass  # the gateway gave up waiting

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                action_id = json.loads(raw).get("action_id") if raw else None
                iface = self.path.split("/")[3]
                host.confirms.append((iface, action_id))
                if host.pending is None or host.pending["interface"] != iface:
                    return self.send(409, {"error": "refused", "reason": "no_pending_change", "message": "nothing waiting"})
                if not action_id or host.pending.get("action_id") != action_id:
                    return self.send(409, {"error": "refused", "reason": "change_mismatch", "message": "a different change is pending"})
                host.last, host.pending = {**host.pending, "result": "confirmed", "ended_at": LATER}, None
                self.send(200, self.status())

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
def box(settings, clock, sock: str, *, passkey=True, timeout_s: float | None = None):
    net = NetSettings(host_socket=Path(sock)) if timeout_s is None else NetSettings(host_socket=Path(sock), host_timeout_s=timeout_s)
    s = replace(settings, sections={
        "identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False),
        "net": net})
    with TestClient(create_app(s, clock=clock)) as c:
        if passkey:
            setup_owner(c)
            c.key = SoftAuthenticator()
            register_passkey(c, c.key)
        yield c


def put(c, iface="eth0", who=OWNER, **body):
    return c.put(f"/v1/network/{iface}", headers=who, json=body)


def approve(c, action_id):
    opts = c.post(f"/v1/actions/{action_id}/approve-options", headers=OWNER).json()
    return c.post(f"/v1/actions/{action_id}/approve", headers=OWNER, json={"webauthn": c.key.assert_(opts["challenge"], flat=True)})


def confirm(c, action_id, who=OWNER, verified=True):
    return c.post("/v1/network/eth0/confirm", headers=who, json={"action_id": action_id, "verified_reachable": verified})


def audit(settings) -> list[dict]:
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines() if x.strip()]


def test_nothing_changes_until_the_owner_approves_with_a_passkey(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = put(c, **STATIC)
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == "network.configure" and a["state"] == "awaiting_approval"
        assert a["params"] == {"interface": "eth0", "mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.1",
                               "dns": ["192.0.2.53"], "rollback_seconds": 45}
        assert r.headers["Location"] == f"/v1/actions/{a['id']}"
        assert host.puts == []  # filed, not applied
        refused = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)  # the owner's token alone is not enough
        assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
        assert host.puts == [] and c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
        ok = approve(c, a["id"])
        assert ok.status_code == 200, ok.text
        assert host.puts == [("eth0", {**STATIC, "action_id": a["id"]})]
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and "Confirm within 45 seconds" in done["result"]["message"], done
        assert "192.0.2.50" in done["result"]["message"]
        events = [x["event"] for x in audit(settings) if x.get("action_id") == a["id"]]
        assert "action.requested" in events and any(e.startswith("action.approved") for e in events), events


def test_the_screen_sees_the_pending_change_and_confirm_keeps_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        view = c.get("/v1/network", headers=OWNER).json()
        assert view["changes"] == {"can_change": True, "reason": None, "pending": None, "last": None}
        a = put(c, **STATIC).json()
        assert approve(c, a["id"]).status_code == 200
        pend = c.get("/v1/network", headers=OWNER).json()["changes"]["pending"]
        assert pend["interface"] == "eth0" and pend["result"] == "pending" and pend["address"] == "192.0.2.50/24"
        assert pend["deadline"].startswith("2026-11-25T12:00:45")
        assert pend["action_id"] == a["id"]
        r = confirm(c, a["id"])
        assert r.status_code == 200 and r.json() == {"confirmed": True, "interface": "eth0"}
        after = c.get("/v1/network", headers=OWNER).json()["changes"]
        assert after["pending"] is None and after["last"]["result"] == "confirmed"
        assert any(x["event"] == "network.confirmed" and x["action_id"] == a["id"]
                   and x["data"] == {"interface": "eth0", "verified_reachable": True} for x in audit(settings))
        again = confirm(c, a["id"])
        assert again.status_code == 409 and again.json()["reason"] == "no_pending_change"


def test_a_delayed_confirmation_cannot_keep_the_next_change(settings, clock, host):
    with box(settings, clock, host.path) as c:
        first = put(c, **STATIC).json()["id"]
        assert approve(c, first).status_code == 200
        host.last, host.pending = {**host.pending, "result": "rolled_back", "ended_at": LATER}, None
        second = put(c, mode="dhcp").json()["id"]
        assert approve(c, second).status_code == 200

        stale = confirm(c, first)
        assert stale.status_code == 409 and stale.json()["reason"] == "change_mismatch"
        assert host.confirms == [("eth0", first)]
        assert c.get("/v1/network", headers=OWNER).json()["changes"]["pending"]["action_id"] == second
        assert not any(x["event"] == "network.confirmed" for x in audit(settings))
        assert confirm(c, second).status_code == 200


def test_confirmation_requires_an_explicit_reachability_attestation(settings, clock, host):
    with box(settings, clock, host.path) as c:
        action_id = put(c, **STATIC).json()["id"]
        assert approve(c, action_id).status_code == 200
        assert c.post("/v1/network/eth0/confirm", headers=OWNER, json={"action_id": action_id}).status_code == 422
        for unverified in (False, 1, "true"):
            assert confirm(c, action_id, verified=unverified).status_code == 422
        assert host.confirms == [] and host.pending["action_id"] == action_id
        assert confirm(c, action_id).status_code == 200


def test_going_back_to_dhcp_sends_no_address(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = put(c, mode="dhcp").json()
        assert approve(c, a["id"]).status_code == 200
        assert host.puts == [("eth0", {"mode": "dhcp", "rollback_seconds": 120, "action_id": a["id"]})]
        msg = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["result"]["message"]
        assert "address the router gives it" in msg


@pytest.mark.parametrize("body,reason", [
    ({"mode": "static", "gateway": "192.0.2.1"}, "invalid_address"),
    ({"mode": "static", "address": "192.0.2.50", "gateway": "192.0.2.1"}, "invalid_address"),
    ({"mode": "static", "address": "2001:db8::5/64", "gateway": "2001:db8::1"}, "invalid_address"),
    ({"mode": "static", "address": "192.0.2.0/24", "gateway": "192.0.2.1"}, "invalid_address"),
    ({"mode": "static", "address": "192.0.2.255/24", "gateway": "192.0.2.1"}, "invalid_address"),
    ({"mode": "static", "address": "127.0.0.2/8", "gateway": "127.0.0.1"}, "invalid_address"),
    ({"mode": "static", "address": "169.254.1.5/16", "gateway": "169.254.0.1"}, "invalid_address"),
    ({"mode": "static", "address": "100.64.0.5/24", "gateway": "100.64.0.1"}, "invalid_address"),
    ({"mode": "static", "address": "192.0.2.50/31", "gateway": "192.0.2.51"}, "invalid_address"),
    ({"mode": "static", "address": "192.0.2.50/24"}, "invalid_gateway"),
    ({"mode": "static", "address": "192.0.2.50/24", "gateway": "198.51.100.1"}, "invalid_gateway"),
    ({"mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.50"}, "invalid_gateway"),
    ({"mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.1", "dns": ["127.0.0.1"]}, "invalid_dns"),
    ({"mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.1", "dns": ["192.0.2.9", "192.0.2.9"]}, "invalid_dns"),
    ({"mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.1", "dns": ["not an address"]}, "invalid_dns"),
    ({"mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.1", "dns": ["2001:db8::53"]}, "invalid_dns"),
    ({"mode": "dhcp", "address": "192.0.2.50/24"}, "invalid_config"),
])
def test_an_address_no_network_can_use_is_refused_and_nothing_is_filed(settings, clock, host, body, reason):
    with box(settings, clock, host.path) as c:
        r = put(c, **body)
        assert r.status_code == 422 and r.json()["reason"] == reason, r.text
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.puts == []


def test_shape_errors_are_422_too(settings, clock, host):
    with box(settings, clock, host.path) as c:
        assert put(c, mode="static", address="192.0.2.5/24", gateway="192.0.2.1", rollback_seconds=5).status_code == 422
        assert put(c, mode="static", address="192.0.2.5/24", gateway="192.0.2.1", dns=["192.0.2.2"] * 4).status_code == 422
        assert put(c, mode="bridge").status_code == 422
        assert put(c, mode="dhcp", surprise=1).status_code == 422
        assert c.put("/v1/network/eth0", headers=OWNER).status_code == 422
        assert c.get("/v1/actions", headers=OWNER).json() == []


@pytest.mark.parametrize("iface,status,reason", [
    ("lo", 409, "not_wired"), ("wlan0", 409, "not_wired"), ("eth9", 409, "unknown_interface"),
    ("-h", 404, None), ("a" * 16, 404, None)])
def test_only_a_real_cable_interface_is_accepted(settings, clock, host, iface, status, reason):
    with box(settings, clock, host.path) as c:
        r = put(c, iface, mode="dhcp")
        assert r.status_code == status, r.text
        assert reason is None or r.json()["reason"] == reason
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_a_second_change_waits_for_the_first(settings, clock, host):
    with box(settings, clock, host.path) as c:
        host.pending = {"interface": "eth0", "mode": "static", "address": "192.0.2.50/24", "gateway": "192.0.2.1", "dns": [],
                        "result": "pending", "started_at": NOW, "deadline": LATER}
        r = put(c, mode="dhcp")
        assert r.status_code == 409 and r.json()["reason"] == "change_pending"
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_a_request_filed_earlier_is_checked_again_at_approval(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = put(c, mode="dhcp").json()
        host.pending = {"interface": "eth0", "mode": "dhcp", "result": "pending", "started_at": NOW, "deadline": LATER, "dns": []}
        r = approve(c, a["id"])
        assert r.status_code == 409 and r.json()["error"] == "stale_precondition", r.text
        assert host.puts == []


def test_no_host_means_nothing_is_filed_and_the_view_says_so(settings, clock):
    with box(settings, clock, "/nonexistent/host.sock") as c:
        r = put(c, mode="dhcp")
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
        assert c.get("/v1/actions", headers=OWNER).json() == []
        assert confirm(c, "act-1").status_code == 409


def test_networkmanager_not_running_is_host_unavailable(settings, clock, host):
    with box(settings, clock, host.path) as c:
        host.available = False
        r = put(c, mode="dhcp")
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable" and "NetworkManager" in r.json()["message"]
        ch = c.get("/v1/network", headers=OWNER).json()["changes"]
        assert ch["can_change"] is False and "NetworkManager" in ch["reason"]


def test_a_host_that_cannot_apply_ends_the_action_as_failed_with_its_reason(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = put(c, **STATIC).json()
        host.fail = (409, {"error": "refused", "reason": "apply_failed", "message": "NetworkManager could not apply that; the old settings are back"})
        assert approve(c, a["id"]).status_code == 200
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "failed" and "old settings are back" in done["result"]["message"], done
        assert done["result"]["steps"][0]["result"] == "apply_failed"


def test_a_host_that_is_slow_but_does_apply_is_not_reported_as_failed(settings, clock, host):
    with box(settings, clock, host.path, timeout_s=0.3) as c:
        a = put(c, **STATIC).json()
        host.put_delay = 1.0
        assert approve(c, a["id"]).status_code == 200
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and done["result"]["steps"][0]["result"] == "pending_confirmation", done


def test_only_owners_may_ask_or_confirm(settings, clock, host):
    with box(settings, clock, host.path) as c:
        for who in (ADULT, AGENT):
            assert put(c, who=who, mode="dhcp").status_code == 403
            assert confirm(c, "act-1", who).status_code == 403
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.puts == [] and host.confirms == []
        denied = [x for x in audit(settings) if x["event"] == "authz.denied"]
        assert {d["data"]["attempted"] for d in denied} >= {"change network", "confirm network change"}
    with box(settings, clock, host.path, passkey=False) as anon:  # no session, no token
        assert anon.put("/v1/network/eth0", json={"mode": "dhcp"}).status_code == 401
        assert confirm(anon, "act-1", who={}).status_code == 401
        assert host.puts == [] and host.confirms == []


def test_a_static_change_without_dns_is_accepted_and_null_is_not(settings, clock, host):
    """Review of #1156: `onemind network set` without --dns sends no dns key (cmd/onemind/cli/network.go); that
    body must be accepted. A null is refused, which is why the CLI leaves the key out."""
    with box(settings, clock, host.path) as c:
        r = put(c, mode="static", address="192.0.2.50/24", gateway="192.0.2.1")
        assert r.status_code == 202, r.text
        assert r.json()["params"]["dns"] == []
        c.post(f"/v1/actions/{r.json()['id']}/deny", headers=OWNER, json={})
        assert put(c, mode="static", address="192.0.2.50/24", gateway="192.0.2.1", dns=None).status_code == 422


def test_the_network_screen_never_waits_the_long_change_timeout(settings, clock, host):
    """Review of #1156: GET /v1/network reads the pending change with the short read timeout, not the 60 s one
    an Apply gets, so a busy host never holds the page."""
    net = NetSettings(host_socket=Path(host.path), host_timeout_s=0.3, change_timeout_s=30)
    s = replace(settings, sections={"identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False), "net": net})
    host.changes_delay = 3.0
    with TestClient(create_app(s, clock=clock)) as c:
        t0 = time.monotonic()
        v = c.get("/v1/network", headers=OWNER).json()
        took = time.monotonic() - t0
    assert took < 2.5, took
    assert v["available"] is True and v["changes"]["can_change"] is False, v
