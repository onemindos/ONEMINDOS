# SPDX-License-Identifier: Apache-2.0
"""System controls (UMB-P09, #146): restart, shutdown and factory reset are owner approvals, a reset
needs the owner's passkey, and the diagnostic bundle passes the public-repo hygiene checks.

Real gateway, real routes, real ledger and approval rule. The host executor is the gateway's real
one (no host path yet: approved controls end `failed`, never `succeeded`) or a recording fake.
"""

from __future__ import annotations

import importlib.util
import json
import re
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core.app import create_app
from onemind_core.executors import ExecResult
from onemind_core.identity import IdentitySettings
from onemind_core.identity.scopes import required_scopes
from onemind_core.system import NoHostPath, node_pseudonym, redact
from test_identity import ORIGIN, RP_ID, SoftAuthenticator, at_box, register_passkey, setup_owner

ROOT = Path(__file__).resolve().parents[2]


def hygiene_patterns() -> dict[str, str]:
    spec = importlib.util.spec_from_file_location("hygiene", ROOT / "scripts" / "hygiene.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PATTERNS


class Host:
    """A host executor that records what it was asked to do."""

    def __init__(self):
        self.ran: list[str] = []

    def unavailable(self, action_type):
        return None

    def run(self, action_type):
        self.ran.append(action_type)
        return ExecResult("succeeded", f"{action_type} started")


@contextmanager
def box(settings, clock, *, passkey=False, host=None):
    s = replace(settings, sections={"identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False,
                                                                  box_code_file=settings.audit_path.parent / "box-code.json")})
    with TestClient(create_app(s, clock=clock)) as c:
        if host is not None:
            c.app.state.system.executor = host
        if passkey:
            setup_owner(c)
            c.key = SoftAuthenticator()
            register_passkey(c, c.key)
        yield c


def ask(c, typ, headers=OWNER, **extra):
    return c.post("/v1/system/actions", headers=headers, json={"type": typ, **extra})


def approve_with_passkey(c, action_id):
    opts = c.post(f"/v1/actions/{action_id}/approve-options", headers=OWNER).json()
    return c.post(f"/v1/actions/{action_id}/approve", headers=OWNER,
                  json={"webauthn": c.key.assert_(opts["challenge"], flat=True), **at_box(c, opts)})


@pytest.mark.parametrize("typ", ["system.restart", "system.shutdown"])
def test_power_controls_wait_for_the_owner_then_run_once(settings, clock, typ):
    host = Host()
    with box(settings, clock, host=host) as c:
        r = ask(c, typ, reason="kernel update")
        assert r.status_code == 202, r.text
        a = r.json()
        assert a["state"] == "awaiting_approval" and a["type"] == typ and r.headers["Location"] == f"/v1/actions/{a['id']}"
        assert host.ran == []  # nothing touches the host before approval
        assert c.get("/v1/system/controls", headers=OWNER).json()["pending"][0]["id"] == a["id"]
        done = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
        assert done.status_code == 200 and done.json()["state"] == "succeeded", done.text
        assert host.ran == [typ]


def test_agent_may_ask_for_a_restart_but_never_approve_it(settings, clock):
    host = Host()
    with box(settings, clock, host=host) as c:
        a = ask(c, "system.restart", headers=AGENT).json()
        assert c.post(f"/v1/actions/{a['id']}/approve", headers=AGENT).status_code == 403
        assert c.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "awaiting_approval"
        assert host.ran == []
        for who in (ADULT, GUEST):
            assert ask(c, "system.shutdown", headers=who).status_code == 403


def test_no_host_path_refuses_to_file_controls_it_cannot_perform(settings, clock):
    with box(settings, clock) as c:
        ctl = c.get("/v1/system/controls", headers=OWNER).json()["controls"]
        assert {x["type"] for x in ctl} == {"system.restart", "system.shutdown", "system.factory_reset"}
        assert all(x["available"] is False and x["unavailable_reason"] == NoHostPath.MESSAGE for x in ctl)
        for typ, who, extra in (("system.restart", OWNER, {}), ("system.shutdown", AGENT, {}),
                                ("system.factory_reset", OWNER, {"confirm": "factory reset"})):
            r = ask(c, typ, headers=who, **extra)
            assert r.status_code == 409 and r.json()["reason"] == "host_unavailable", r.text
            assert "rescue console" in r.json()["message"]
        assert ask(c, "system.restart", headers=GUEST).status_code == 403  # no availability hint to the unauthorised
        assert c.get("/v1/actions", headers=OWNER).json() == [] and c.get("/v1/system/controls", headers=OWNER).json()["pending"] == []


def test_a_control_that_became_unavailable_after_the_request_fails_and_never_claims_success(settings, clock):
    with box(settings, clock, host=Host()) as c:
        a = ask(c, "system.restart").json()
        c.app.state.system.executor = NoHostPath()
        done = c.post(f"/v1/actions/{a['id']}/approve", headers=OWNER).json()
        assert done["state"] == "failed" and done["decided_by"]["id"] and "rescue console" in done["result"]["message"]


def test_an_agent_cannot_flood_the_approval_queue(settings, clock):
    with box(settings, clock, host=Host()) as c:
        c.app.state.actions.max_pending_per_requester = 2
        assert [ask(c, "system.restart", headers=AGENT).status_code for _ in range(2)] == [202, 202]
        r = ask(c, "system.shutdown", headers=AGENT)
        assert r.status_code == 429 and r.json()["reason"] == "too_many_pending", r.text
        assert sum(a["requested_by"]["kind"] == "agent" for a in c.get("/v1/actions", headers=OWNER).json()) == 2
        assert ask(c, "system.restart", headers=OWNER).status_code == 202  # the owner is never capped


def test_factory_reset_needs_the_typed_phrase_the_owner_and_a_passkey(settings, clock):
    host = Host()
    with box(settings, clock, passkey=True, host=host) as c:
        assert ask(c, "system.factory_reset").status_code == 422
        assert ask(c, "system.factory_reset", confirm="yes").status_code == 422
        assert ask(c, "system.restart", confirm="factory reset").status_code == 422
        assert ask(c, "system.factory_reset", headers=AGENT, confirm="factory reset").status_code == 403  # AI never asks for this
        r = ask(c, "system.factory_reset", confirm="factory reset")
        assert r.status_code == 202, r.text
        aid = r.json()["id"]
        refused = c.post(f"/v1/actions/{aid}/approve", headers=OWNER)  # the owner's token alone is not enough
        assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
        assert host.ran == [] and c.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
        ok = approve_with_passkey(c, aid)
        assert ok.status_code == 200 and ok.json()["state"] == "succeeded", ok.text
        assert host.ran == ["system.factory_reset"]


def test_factory_reset_without_a_registered_passkey_cannot_be_approved(settings, clock):
    host = Host()
    with box(settings, clock, host=host) as c:
        aid = ask(c, "system.factory_reset", confirm="factory reset").json()["id"]
        assert c.post(f"/v1/actions/{aid}/approve", headers=OWNER).status_code == 401
        assert c.post(f"/v1/actions/{aid}/approve", headers=OWNER, json={"webauthn": {"id": "x"}}).status_code == 401
        assert host.ran == []


def test_the_generic_actions_route_cannot_file_a_system_control(settings, clock):
    with box(settings, clock) as c:
        r = c.post("/v1/actions", headers=OWNER, json={"type": "system.restart", "params": {}, "idempotency_key": "k1",
                                                        "expires_at": "2099-01-01T00:00:00Z"})
        assert r.status_code == 422


def test_requests_are_idempotent(settings, clock):
    with box(settings, clock, host=Host()) as c:
        first = ask(c, "system.shutdown", idempotency_key="same")
        again = ask(c, "system.shutdown", idempotency_key="same")
        assert first.status_code == 202 and again.status_code == 200 and again.json()["id"] == first.json()["id"]


def test_reads_are_owner_only_and_scoped():
    assert required_scopes("GET", "/v1/system/diagnostics") == ("system:admin",)
    assert required_scopes("POST", "/v1/system/actions") == ("actions:request",)


def test_owner_only_reads(settings, clock):
    with box(settings, clock) as c:
        for path in ("/v1/system/controls", "/v1/system/diagnostics"):
            for who in (ADULT, GUEST, AGENT):
                assert c.get(path, headers=who).status_code == 403
            assert c.get(path).status_code == 401


# Planted personal values, built at run time so this file passes the hygiene greps itself.
HOME = "/" + "Users" + "/alice/.ssh/id_ed25519"
LAN = ".".join(["192", "168", "1", "20"])
CGNAT = ".".join(["100", "101", "7", "9"])
MAIL = "alice" + "@" + "example.org"
TAILNET = "box.tail1234" + ".ts" + ".net"
SECRET = "sk_live_" + "Q" * 44


def test_diagnostic_bundle_passes_the_hygiene_checks(settings, clock):
    with box(settings, clock, host=Host()) as c:
        hb = {"schema": "onemind.node.status/v1", "node_id": "pc0123456789", "hostname": "alices-laptop", "role": "hub",
              "arch": "amd64", "note": f"mounted {HOME} from {LAN} via {TAILNET}, {CGNAT}; owner {MAIL}",
              "api_token": SECRET, "last_error": f"Bearer {SECRET}", "v6": "fd00:1:2:3:4:5:6:7"}
        assert c.app.state.registry.ingest("onemind.node.pc0123456789.status", json.dumps(hb).encode())
        ask(c, "system.restart", reason=f"asked by {MAIL} from {LAN}")
        r = c.get("/v1/system/diagnostics", headers=OWNER)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store" and "attachment" in r.headers["content-disposition"]
        text = r.text
        for kind, rx in hygiene_patterns().items():
            assert not re.search(rx, text), f"{kind} leaked: {re.search(rx, text).group(0)}"
        for planted in (SECRET, "alices-laptop", "fd00:1:2", LAN, CGNAT, "alice"):
            assert planted not in text
        b = r.json()
        assert b["schema"] == "onemind.diagnostics/v1" and b["nodes"][0]["node_id"] == node_pseudonym("pc0123456789")
        assert b["nodes"][0]["status"] == "online"  # real health survives redaction
        assert b["actions"]["by_state"] == {"awaiting_approval": 1}
        assert any(e["event"] == "action.requested" for e in b["audit"])
        assert {"email", "home-path", "ipv4", "tailnet", "secret-field"} <= b["redaction"]["found"].keys()
        assert any(e["event"] == "system.diagnostics.exported" for e in _audit(c))


def _audit(c) -> list[dict]:
    return [json.loads(line) for line in c.app.state.gateway.audit.path.read_text().splitlines()]


def test_redact_keeps_times_versions_and_ids():
    out, found = redact({"at": "2026-11-18T12:00:00Z", "version": "0.1.0", "id": "act_123", "n": 3})
    assert out == {"at": "2026-11-18T12:00:00Z", "version": "0.1.0", "id": "act_123", "n": 3} and found == {}


def test_bundle_hashes_node_ids_and_drops_node_names(settings, clock):
    with box(settings, clock) as c:
        hb = {"schema": "onemind.node.status/v1", "node_id": "zeus-mbp", "name": "zeus-mbp", "display_name": "Zeus's MacBook",
              "role": "hub", "labels": {"owner": "zeus"}, "peer": {"node_id": "zeus-mbp", "nickname": "laptop"}}
        assert c.app.state.registry.ingest("onemind.node.zeus-mbp.status", json.dumps(hb).encode())
        r = c.get("/v1/system/diagnostics", headers=OWNER)
        assert "zeus" not in r.text.lower() and "laptop" not in r.text
        b = r.json()
        node = b["nodes"][0]
        assert node["node_id"] == node_pseudonym("zeus-mbp") == "node-" + node["node_id"][5:] and len(node["node_id"]) == 17
        assert node["peer"] == {"node_id": node_pseudonym("zeus-mbp")} and node["role"] == "hub" and node["status"] == "online"
        assert not {"name", "display_name", "labels"} & node.keys()
        hub = c.app.state.gateway.settings.node_id
        assert b["gateway"]["hub_node_id"] == (node_pseudonym(hub) if hub else None)
        assert b["redaction"]["found"]["name-field"] == 4 and b["redaction"]["found"]["node-id"] >= 2
        assert node_pseudonym("zeus-mbp") == c.get("/v1/system/diagnostics", headers=OWNER).json()["nodes"][0]["node_id"]  # stable


@pytest.mark.parametrize("text", ["std::vector<int>", "deadbeef::cafe", "Foo::Bar", "a :: b", "at 12:30:45", "fe80"])
def test_ipv6_rule_leaves_code_and_words_alone(text):
    assert redact(text) == (text, {})


@pytest.mark.parametrize("addr", ["fd7a:115c:a1e0::1", "2001:db8::1", "::1", "fd00:1:2:3:4:5:6:7", "fe80::1"])
def test_ipv6_rule_still_removes_addresses(addr):
    out, found = redact(f"peer {addr}, up")
    assert out == "peer [ip], up" and found == {"ipv6": 1}


def test_controls_and_bundle_match_their_published_models(settings, clock):
    from onemind_core.system import DiagnosticsBundle, SystemControls
    with box(settings, clock, host=Host()) as c:
        ask(c, "system.restart")
        SystemControls.model_validate(c.get("/v1/system/controls", headers=OWNER).json())
        DiagnosticsBundle.model_validate(c.get("/v1/system/diagnostics", headers=OWNER).json())
        spec = c.get("/openapi.json").json()
        ok = spec["paths"]["/v1/system/actions"]["post"]["responses"]["202"]["content"]["application/json"]["schema"]
        assert ok["$ref"].endswith("/Action")
