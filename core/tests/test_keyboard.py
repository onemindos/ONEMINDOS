# SPDX-License-Identifier: Apache-2.0
"""Keyboard layout (P-11): a real gateway, ledger, approval rule and audit chain talk over a real Unix socket to a
stand-in for `onemindd host serve` that answers like internal/host (GET /v1/keyboard, POST /v1/operations with a layout
and variant). An agent may ask, never run it; only the owner approves; no passkey is needed (not a security change); a
layout the image does not offer is refused before anything is filed.
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
from onemind_core.hostkeyboard import parse_view
from onemind_core.hostlink import HostLinkSettings
from onemind_core.identity.scopes import required_scopes
from onemind_core.netconf import NetSettings

VIEW = {
    "schema": "onemind.keyboard/v1", "at": "2026-11-25T12:00:00Z", "seeded": True,
    "current": {"model": "pc105", "layout": "us", "variant": "", "options": ""},
    "layouts": [
        {"id": "us", "name": "English (US)", "variants": [{"id": "dvorak", "name": "English (Dvorak)"}]},
        {"id": "de", "name": "German", "variants": [{"id": "nodeadkeys", "name": "German (no dead keys)"}]},
        {"id": "fr", "name": "French", "variants": []},
    ],
}


class FakeHost:
    """GET /v1/status, GET /v1/keyboard, POST /v1/operations, GET /v1/operations/{id}."""

    def __init__(self, view=VIEW, kinds=("restart", "shutdown", "factory-reset", "os-install", "service-restart", "set-keymap")):
        self.dir = tempfile.mkdtemp(prefix="kb")  # short: AF_UNIX paths are limited to about 100 bytes
        self.path = os.path.join(self.dir, "host.sock")
        self.posts: list[dict] = []
        self.ops: dict[str, dict] = {}
        self.view = view
        host = self

        class H(http.server.BaseHTTPRequestHandler):
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
                    ops = [{"kind": k, "available": True, "unavailable_reason": None} for k in kinds]
                    return self.send(200, {"schema": "onemind.host/v1", "journal": True, "operations": ops})
                if self.path == "/v1/keyboard":
                    return self.send(200, host.view) if host.view is not None else self.send(404, {})
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


def ask(c, who=OWNER, **body):
    return c.post("/v1/system/keyboard", headers=who, json=body)


def audit(settings) -> list[dict]:
    return [json.loads(x) for x in settings.audit_path.read_text().splitlines() if x.strip()]


def test_the_owner_sees_the_layout_and_every_layout_the_image_offers(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = c.get("/v1/system/keyboard", headers=OWNER)
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["available"] is True and v["seeded"] is True and v["current"]["layout"] == "us"
        assert [x["id"] for x in v["layouts"]] == ["us", "de", "fr"] and v["layouts"][1]["variants"][0]["id"] == "nodeadkeys"
        assert v["dropped"] == 0
        for who in (ADULT, GUEST, AGENT):
            assert c.get("/v1/system/keyboard", headers=who).status_code == 403


def test_an_agent_can_request_a_layout_change_but_not_run_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        r = ask(c, who=AGENT, layout="de", variant="nodeadkeys", reason="the owner types German")
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["type"] == "system.set_keymap" and a["state"] == "awaiting_approval"
        assert a["params"] == {"layout": "de", "variant": "nodeadkeys"}
        assert r.headers["Location"] == f"/v1/actions/{a['id']}"
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403  # an agent never approves
        assert host.posts == []
        ok = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)  # the owner's approval alone: not a security change
        assert ok.status_code == 200 and ok.json()["state"] == "dispatched", ok.text
        assert host.posts == [{"action_id": a["id"], "kind": "set-keymap", "layout": "de", "variant": "nodeadkeys"}]
        host.ops[a["id"]].update(state="succeeded", message="the keyboard layout is now de (nodeadkeys)")
        c.app.state.hostlink.poll()
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "succeeded" and done["requested_by"]["kind"] == "agent", done
        events = [x["event"] for x in audit(settings) if x.get("action_id") == a["id"]]
        assert "action.requested" in events and any(e.startswith("action.approved") for e in events), events


def test_a_variant_is_optional_and_a_host_refusal_ends_the_action_failed(settings, clock, host):
    with box(settings, clock, host.path) as c:
        a = ask(c, layout="fr").json()
        assert a["params"] == {"layout": "fr"}
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).status_code == 200
        assert host.posts == [{"action_id": a["id"], "kind": "set-keymap", "layout": "fr"}]
        host.ops[a["id"]].update(state="failed", reason="host_error", message="the keyboard layout was not changed: exit status 1")
        c.app.state.hostlink.poll()
        done = c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()
        assert done["state"] == "failed" and "was not changed" in json.dumps(done)


@pytest.mark.parametrize("body", [
    {"layout": "zz"},                           # not offered
    {"layout": "de", "variant": "dvorak"},      # a variant of another layout
    {"layout": "fr", "variant": "nodeadkeys"},  # offered for de only
])
def test_a_layout_the_image_does_not_offer_is_refused_and_nothing_is_filed(settings, clock, host, body):
    with box(settings, clock, host.path) as c:
        r = ask(c, **body)
        assert r.status_code == 404, r.text
        assert c.get("/v1/actions", headers=OWNER).json() == [] and host.posts == []


@pytest.mark.parametrize("body", [{"layout": "de; reboot"}, {"layout": "de", "variant": "no/dead"}, {"layout": ""}, {}, {"layout": "de", "extra": 1}])
def test_a_malformed_request_is_422(settings, clock, host, body):
    with box(settings, clock, host.path) as c:
        assert ask(c, **body).status_code == 422
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_only_owners_and_agents_may_ask_and_the_generic_route_cannot_file_it(settings, clock, host):
    with box(settings, clock, host.path) as c:
        for who in (ADULT, GUEST):
            assert ask(c, who=who, layout="de").status_code == 403
        r = c.post("/v1/actions", headers=OWNER, json={"type": "system.set_keymap", "params": {"layout": "zz"},
                                                        "idempotency_key": "k1", "expires_at": "2099-01-01T00:00:00Z"})
        assert r.status_code == 422  # only the route that checks the image's list files it
        first, again = ask(c, layout="de", idempotency_key="same"), ask(c, layout="de", idempotency_key="same")
        assert first.status_code == 202 and again.status_code == 200 and again.json()["id"] == first.json()["id"]
        hdr = {**OWNER, "Idempotency-Key": "hdr-1"}
        h1, h2 = (c.post("/v1/system/keyboard", headers=hdr, json={"layout": "fr"}) for _ in range(2))
        assert h1.status_code == 202 and h2.status_code == 200 and h2.json()["id"] == h1.json()["id"] != first.json()["id"]


def test_an_unreachable_host_files_nothing_and_says_so(settings, clock):
    with box(settings, clock, "/nonexistent/host.sock") as c:
        r = ask(c, layout="de")
        assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
        v = c.get("/v1/system/keyboard", headers=OWNER).json()
        assert v["available"] is False and v["reason"] == "host_service_unreachable" and v["layouts"] == []
        assert c.get("/v1/actions", headers=OWNER).json() == []


def test_a_host_without_the_kind_files_nothing(settings, clock):
    h = FakeHost(kinds=("restart", "shutdown"))
    try:
        with box(settings, clock, h.path) as c:
            r = ask(c, layout="de")
            assert r.status_code == 409 and r.json()["reason"] == "host_unavailable"
            assert c.get("/v1/actions", headers=OWNER).json() == []
    finally:
        h.close()


def test_an_old_host_service_without_the_route_reads_as_unavailable(settings, clock):
    h = FakeHost(view=None)
    try:
        with box(settings, clock, h.path) as c:
            v = c.get("/v1/system/keyboard", headers=OWNER).json()
            assert v["available"] is False and v["reason"] == "host_service_error" and "cannot change the keyboard" in v["message"]
    finally:
        h.close()


def test_the_gateway_checks_the_host_s_answer_again():
    bad = {**VIEW, "layouts": [
        {"id": "us", "name": "English (US)", "variants": [{"id": "dvorak", "name": "ok"}, {"id": "../x", "name": "bad id"},
                                                          {"id": "dvorak", "name": "twice"}]},
        {"id": "de; reboot", "name": "bad id", "variants": []},
        {"id": "fr", "name": "Fr\x1b[31mench", "variants": []},
        {"id": "us", "name": "listed twice", "variants": []},
        "not an object",
        {"id": "de", "name": "German", "variants": "nope"},
    ]}
    v = parse_view(bad)
    assert v.available and [x.id for x in v.layouts] == ["us", "de"] and [x.id for x in v.layouts[0].variants] == ["dvorak"]
    assert v.dropped == 7, v.dropped
    for body in (None, [], {**VIEW, "schema": "other"}, {**VIEW, "current": {"model": "pc105", "layout": "de$(x)", "variant": "", "options": ""}},
                 {**VIEW, "current": {"model": "pc105", "layout": "", "variant": "", "options": ""}}):
        assert parse_view(body).available is False and parse_view(body).reason == "bad_response"


def test_routes_are_scoped_and_the_action_has_no_passkey_step_up():
    assert required_scopes("GET", "/v1/system/keyboard") == ("system:admin",)
    assert required_scopes("POST", "/v1/system/keyboard") == ("actions:request",)
