# SPDX-License-Identifier: Apache-2.0
"""Firewall allow rules with automatic revert (P-09 part 2): a real gateway, ledger, approval rule and audit
chain talk over a real Unix socket to a stand-in for `onemindd host serve` that answers like
internal/host/firewall_allow.go and internal/firewall (same routes, status codes and JSON).

An owner or an agent may ask to open a port; only an owner approves, with a passkey; the scope is the home
network or the mesh and never the internet; a rule starts pending and the host takes it away unless it is
confirmed; removing and confirming are owner only and audited.
"""

from __future__ import annotations

import copy
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
from onemind_core.hostfw import parse_view
from onemind_core.identity import IdentitySettings
from onemind_core.identity.scopes import required_scopes
from onemind_core.netconf import NetSettings
from test_firewall_view import GOOD
from test_identity import LOCAL_PEER, ORIGIN, RP_ID, SoftAuthenticator, register_passkey, setup_owner

ALLOW = "/v1/network/firewall/allow"


class FakeHost:
    """GET /v1/firewall (with the allow part) and the three allow calls, with the rules held like the host does."""

    def __init__(self, supported=True):
        self.dir = tempfile.mkdtemp(prefix="fa")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = os.path.join(self.dir, "host.sock")
        self.rules: dict[str, dict] = {}
        self.supported = supported
        self.calls: list[tuple[str, str, dict | None]] = []
        self.refuse: tuple[int, dict] | None = None
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

            def body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n)) if n else None

            def do_GET(self):
                if self.path != "/v1/firewall":
                    return self.send(404, {})
                v = copy.deepcopy(GOOD)
                v["allow"] = {"supported": host.supported, "ttl_seconds": 300, "rules": list(host.rules.values())}
                if not host.supported:
                    v["allow"]["reason"] = "this OS image's firewall has no owner rules lists yet; update the OS"
                self.send(200, v)

            def do_POST(self):
                body = self.body()
                host.calls.append(("POST", self.path, body))
                if host.refuse:
                    return self.send(*host.refuse)
                if self.path == "/v1/firewall/allow":
                    rule = {**body, "state": "pending", "created": "2026-11-25T12:00:00Z", "expires": "2026-11-25T12:05:00Z"}
                    host.rules.setdefault(body["id"], rule)
                    return self.send(200, host.rules[body["id"]])
                rid = self.path.split("/")[-2]
                if rid not in host.rules:
                    return self.send(404, {"error": "not_found", "reason": "unknown_rule", "message": "no such rule"})
                host.rules[rid].update(state="confirmed")
                host.rules[rid].pop("expires", None)
                self.send(200, host.rules[rid])

            def do_DELETE(self):
                host.calls.append(("DELETE", self.path, None))
                rid = self.path.rsplit("/", 1)[1]
                if host.rules.pop(rid, None) is None:
                    return self.send(404, {"error": "not_found", "reason": "unknown_rule", "message": "no such rule"})
                self.send(200, {"removed": True})

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
def box(settings, clock, sock: str, *, passkey=True):
    s = replace(settings, sections={
        "identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False),
        "net": NetSettings(host_socket=Path(sock))})
    with TestClient(create_app(s, clock=clock), client=LOCAL_PEER) as c:
        if passkey:
            setup_owner(c)
            c.key = SoftAuthenticator()
            register_passkey(c, c.key)
        yield c


def ask(c, who=OWNER, **over):
    return c.post(ALLOW, headers=who, json={"proto": "tcp", "port": 8123, "scope": "lan", **over})


def approve(c, action_id):
    opts = c.post(f"/v1/actions/{action_id}/approve-options", headers=OWNER).json()
    return c.post(f"/v1/actions/{action_id}/approve", headers=OWNER, json={"webauthn": c.key.assert_(opts["challenge"], flat=True)})


def audit(settings) -> list[dict]:
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines() if x.strip()]


def test_an_agent_asks_the_owner_approves_with_a_passkey_and_the_rule_starts_pending(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = ask(c, AGENT, reason="the printer app needs it")
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == "firewall.allow" and a["state"] == "awaiting_approval"
        assert a["params"] == {"proto": "tcp", "port": 8123, "scope": "lan"}
        # the reason on record says what would be opened first, then the asker's words
        asked = next(x for x in audit(settings) if x["event"] == "action.requested" and x.get("action_id") == a["id"])
        assert asked["data"]["reason"] == "Open TCP port 8123 for devices on your home network (LAN): the printer app needs it", asked
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403  # an agent never approves
        refused = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)  # the owner's token alone is not enough
        assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
        assert host.calls == [] and host.rules == {}  # nothing reached the host before the passkey
        ok = approve(c, a["id"])
        assert ok.status_code == 200, ok.text
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and "unless you confirm" in done["result"]["message"], done
        assert host.calls == [("POST", "/v1/firewall/allow", {"id": a["id"], "proto": "tcp", "port": 8123, "scope": "lan"})]
        view = c.get("/v1/network/firewall", headers=OWNER).json()
        assert view["editable"] is True and view["allow"]["ttl_seconds"] == 300
        (rule,) = view["allow"]["rules"]
        assert rule["id"] == a["id"] and rule["state"] == "pending" and rule["expires_at"].startswith("2026-11-25T12:05")
        assert "TCP port 8123" in rule["summary"] and "home network" in rule["summary"] and "unless you confirm" in rule["summary"]
        events = [x["event"] for x in audit(settings) if x.get("action_id") == a["id"]]
        assert "action.requested" in events and any(e.startswith("action.approved") for e in events), events


def test_confirm_keeps_it_and_remove_takes_it_away_both_owner_only_and_audited(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = ask(c).json()
        assert approve(c, a["id"]).status_code == 200
        for who in (ADULT, GUEST, AGENT):
            assert c.post(f"{ALLOW}/{a['id']}/confirm", headers=who).status_code == 403
            assert c.delete(f"{ALLOW}/{a['id']}", headers=who).status_code == 403
        assert [x for x in host.calls if x[0] != "POST" or "confirm" in x[1]] == []  # none of those reached the host
        r = c.post(f"{ALLOW}/{a['id']}/confirm", headers=OWNER)
        assert r.status_code == 200 and r.json() == {"id": a["id"], "state": "confirmed"}
        assert host.rules[a["id"]]["state"] == "confirmed"
        (rule,) = c.get("/v1/network/firewall", headers=OWNER).json()["allow"]["rules"]
        assert rule["state"] == "confirmed" and rule["expires_at"] is None and "stays open" in rule["summary"]
        d = c.delete(f"{ALLOW}/{a['id']}", headers=OWNER)
        assert d.status_code == 200 and d.json() == {"id": a["id"], "removed": True} and host.rules == {}
        assert c.delete(f"{ALLOW}/{a['id']}", headers=OWNER).status_code == 404
        ev = [x["event"] for x in audit(settings)]
        assert "firewall.allow.confirmed" in ev and "firewall.allow.removed" in ev and ev.count("authz.denied") >= 6


def test_a_rule_that_reverted_cannot_be_confirmed(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = ask(c).json()
        assert approve(c, a["id"]).status_code == 200
        host.rules.clear()  # the host's timer ran out
        r = c.post(f"{ALLOW}/{a['id']}/confirm", headers=OWNER)
        assert r.status_code == 404 and "already gone" in r.json()["message"]
        assert c.get("/v1/network/firewall", headers=OWNER).json()["allow"]["rules"] == []


@pytest.mark.parametrize("over", [
    {"scope": "wan"}, {"scope": "any"}, {"scope": "internet"}, {"scope": "0.0.0.0/0"}, {"scope": ""},  # the internet is not a scope
    {"proto": "icmp"}, {"port": 0}, {"port": 65536}, {"port": "80; flush ruleset"}, {"extra": 1},
])
def test_the_internet_and_odd_values_are_refused_and_nothing_is_filed(settings, clock, host, over):
    with box(settings, clock, host.path) as c:
        assert ask(c, **over).status_code == 422
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.calls == []


def test_mesh_scope_and_udp_are_fine(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = ask(c, proto="udp", port=9000, scope="mesh").json()
        assert approve(c, a["id"]).status_code == 200
        assert host.calls[0][2] == {"id": a["id"], "proto": "udp", "port": 9000, "scope": "mesh"}
        assert "your OneMind mesh" in c.get("/v1/network/firewall", headers=OWNER).json()["allow"]["rules"][0]["summary"]


def test_only_owners_and_agents_may_ask_and_the_generic_route_cannot_file_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        for who in (ADULT, GUEST):
            assert ask(c, who).status_code == 403
        r = c.post("/v1/actions", headers=OWNER, json={"type": "firewall.allow", "params": {"proto": "tcp", "port": 80, "scope": "lan"},
                                                        "idempotency_key": "k1", "expires_at": "2099-01-01T00:00:00Z"})
        assert r.status_code == 422  # only the route that checks the firewall files it
        first, again = ask(c, idempotency_key="same"), ask(c, idempotency_key="same")
        assert first.status_code == 202 and again.status_code == 200 and again.json()["id"] == first.json()["id"]


def test_a_box_that_cannot_take_rules_files_nothing_and_says_why(settings, clock):
    h = FakeHost(supported=False)
    try:
        with box(settings, clock, h.path) as c:
            r = ask(c)
            assert r.status_code == 409 and r.json()["reason"] == "firewall_unavailable" and "update the OS" in r.json()["message"]
            v = c.get("/v1/network/firewall", headers=OWNER).json()
            assert v["editable"] is False and v["allow"]["supported"] is False
            assert c.get("/v1/actions", headers=OWNER).json() == []
    finally:
        h.close()
    with box(settings, clock, "/nonexistent/host.sock", passkey=False) as c:
        r = ask(c)
        assert r.status_code == 409 and c.get("/v1/actions", headers=OWNER).json() == []
        assert c.post(f"{ALLOW}/x/confirm", headers=OWNER).status_code == 409


def test_an_already_open_port_is_not_filed_again(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = ask(c).json()
        assert approve(c, a["id"]).status_code == 200
        r = ask(c, idempotency_key="second")
        assert r.status_code == 409 and "already allowed" in r.json()["message"]


def test_a_host_refusal_ends_the_action_failed_never_succeeded(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = ask(c).json()
        host.refuse = (409, {"error": "refused", "reason": "too_many", "message": "at most 16 allow rules; remove one first"})
        assert approve(c, a["id"]).status_code == 200
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "failed" and "at most 16" in done["result"]["message"], done
        assert host.rules == {}


def test_a_host_that_lies_in_its_rule_list_is_dropped_and_counted():
    ok = {"id": "a1", "proto": "tcp", "port": 80, "scope": "lan", "state": "pending", "created": "2026-11-25T12:00:00Z", "expires": "2026-11-25T12:05:00Z"}
    bad = [{**ok, "id": "a2", "scope": "wan"}, {**ok, "id": "a3", "port": 0}, {**ok, "id": "a 4"}, {**ok, "id": "a5", "state": "maybe"},
           {k: v for k, v in ok.items() if k != "expires"} | {"id": "a6"}, {**ok, "id": "a1"}, "text", {**ok, "id": "a8", "proto": "icmp"}]
    v = parse_view({**copy.deepcopy(GOOD), "allow": {"supported": True, "ttl_seconds": 300, "rules": [ok, *bad]}})
    assert [r.id for r in v.allow.rules] == ["a1"] and v.dropped == len(bad) and v.editable is True
    for broken in ({"supported": "yes", "ttl_seconds": 300, "rules": []}, {"supported": True, "ttl_seconds": 0, "rules": []}, "x"):
        w = parse_view({**copy.deepcopy(GOOD), "allow": broken})
        assert w.allow is None and w.editable is False and w.dropped == 1
    assert parse_view(copy.deepcopy(GOOD)).allow is None  # an older host service says nothing: no rules, not editable


def test_a_rule_whose_revert_failed_is_shown_without_a_deadline_and_can_be_removed():
    stuck = {"id": "a1", "proto": "tcp", "port": 80, "scope": "lan", "state": "revert_failed", "created": "2026-11-25T12:00:00Z"}
    v = parse_view({**copy.deepcopy(GOOD), "allow": {"supported": True, "ttl_seconds": 300, "rules": [stuck]}})
    (r,) = v.allow.rules
    assert r.state == "revert_failed" and r.expires_at is None and v.dropped == 0
    assert "could not close it yet" in r.summary and "remove it" in r.summary


def test_routes_are_scoped():
    assert required_scopes("POST", ALLOW) == ("actions:request",)
    assert required_scopes("POST", f"{ALLOW}/abc/confirm") == ("*",)
    assert required_scopes("DELETE", f"{ALLOW}/abc") == ("*",)
