# SPDX-License-Identifier: Apache-2.0
"""REL-02 (#154): security updates install by themselves by default; the owner may opt out or move the window.

Real gateway with identity on, one owner with a passkey, and a stand-in for the host service that answers like
internal/host (test_hostlink.FakeHost). The node reports the image default (policy auto, window 02:00-05:00).
Turning automatic updates off or moving the window loosens a security setting: approved only with the owner's
passkey (D-028). Turning them back on with the same window is a tightening and needs none.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.identity import IdentitySettings
from test_hostlink import NODE, FakeHost, link_settings
from test_identity import ORIGIN, RP_ID, SoftAuthenticator, register_passkey, setup_owner
from test_os_updates import HB

DEFAULT = {"policy": "auto", "window": "02:00-05:00", "settings_source": "image"}


@pytest.fixture
def host():
    h = FakeHost()
    h.available["os-update-settings"] = True
    yield h
    h.close()


@pytest.fixture
def box(settings, clock, executor, host):
    s = link_settings(settings, host.path)
    s = replace(s, sections={**s.sections, "identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        setup_owner(c)
        c.key = SoftAuthenticator()
        register_passkey(c, c.key)

        def report(**update):
            hb = {**HB, "node_id": NODE, "update": {**HB["update"], **DEFAULT, **update}}
            assert c.app.state.registry.ingest(f"onemind.node.{NODE}.status", json.dumps(hb).encode())
        c.report, c.clock, c.n = report, clock, 0
        report()
        yield c


def put(c, body, headers=OWNER):
    return c.put("/v1/os/settings", headers=headers, json={"node_id": NODE, **body})


def sign(c, action_id):
    opts = c.post(f"/v1/actions/{action_id}/approve-options", headers=OWNER).json()
    return {"webauthn": c.key.assert_(opts["challenge"], flat=True)}


def test_status_shows_the_default_policy_window_and_source(box):
    st = box.get("/v1/os/updates", headers=OWNER).json()
    [n] = st["nodes"]
    assert (n["policy"], n["window"], n["settings_source"]) == ("auto", "02:00-05:00", "image")
    assert st["settings"]["available"] is True
    box.report(policy="sometimes", window="25:00-01:00", settings_source="hacker")  # H-06: re-checked, never passed on
    [n] = box.get("/v1/os/updates", headers=OWNER).json()["nodes"]
    assert (n["policy"], n["window"], n["settings_source"]) == (None, None, None)


def test_opting_out_needs_the_owners_passkey_then_reaches_the_host(box, host):
    r = put(box, {"policy": "off"})
    assert r.status_code == 202, r.text
    a = r.json()
    assert a["type"] == "os.update.settings" and a["state"] == "awaiting_approval" and a["risk"] == "sensitive"
    assert a["params"] == {"node_id": NODE, "policy": "off", "window": "02:00-05:00"}  # window kept
    refused = box.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required", refused.text
    assert host.posts == []
    done = box.post(f"/v1/actions/{a['id']}/approve", headers=OWNER, json=sign(box, a["id"]))
    assert done.status_code == 200, done.text
    assert host.posts == [{"action_id": a["id"], "kind": "os-update-settings", "policy": "off", "window": "02:00-05:00"}]
    host.set_state(a["id"], "succeeded", message="update policy off, window 02:00-05:00")
    box.app.state.hostlink.poll()
    assert box.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "succeeded"
    [req] = box.get("/v1/os/updates/history", headers=OWNER).json()["requests"]
    assert req["type"] == "os.update.settings" and req["policy"] == "off"


def test_moving_the_window_needs_the_passkey_too(box):
    a = put(box, {"window": "01:00-03:00"}).json()
    assert a["params"]["policy"] == "auto"
    refused = box.post(f"/v1/actions/{a['id']}/approve", headers=OWNER)
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"


@pytest.fixture
def plain(settings, clock, executor, host):
    """No passkeys on this box: only the settings guard itself decides whether a passkey is needed."""
    with TestClient(create_app(link_settings(settings, host.path), clock=clock, executor=executor)) as c:
        def report(**update):
            hb = {**HB, "node_id": NODE, "update": {**HB["update"], **DEFAULT, **update}}
            assert c.app.state.registry.ingest(f"onemind.node.{NODE}.status", json.dumps(hb).encode())
        c.report = report
        report()
        yield c


def test_turning_automatic_updates_back_on_is_a_tightening(plain, host):
    off = put(plain, {"policy": "off"}).json()
    refused = plain.post(f"/v1/actions/{off['id']}/approve", headers=OWNER)
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"  # loosening: always the passkey
    plain.report(policy="off", settings_source="owner")
    on = put(plain, {"policy": "auto"}).json()
    done = plain.post(f"/v1/actions/{on['id']}/approve", headers=OWNER)
    assert done.status_code == 200, done.text
    assert host.posts == [{"action_id": on["id"], "kind": "os-update-settings", "policy": "auto", "window": "02:00-05:00"}]


def test_only_an_owner_requests_and_approves(box):
    assert put(box, {"policy": "off"}, headers=AGENT).status_code == 403
    assert put(box, {"policy": "off"}, headers=ADULT).status_code == 403
    via_actions = box.post("/v1/actions", headers=AGENT, json={
        "type": "os.update.settings", "params": {"node_id": NODE, "policy": "off", "window": "any"},
        "idempotency_key": "agent-off", "expires_at": (box.clock.now + timedelta(hours=1)).isoformat()})
    assert via_actions.status_code == 403  # AI never turns security updates off (D-027)
    a = put(box, {"policy": "notify"}).json()
    assert box.post(f"/v1/actions/{a['id']}/approve", headers=ADULT).status_code == 403


def test_request_rules(box):
    assert put(box, {}).status_code == 422
    assert put(box, {"policy": "sometimes"}).status_code == 422
    for bad in ("25:00-01:00", "03:00-03:00", "3:00-4:00", "always"):
        assert put(box, {"window": bad}).status_code == 422, bad
    same = put(box, {"policy": "auto", "window": "02:00-05:00"})
    assert same.status_code == 409 and same.json()["reason"] == "no_change"
    ghost = box.put("/v1/os/settings", headers=OWNER, json={"node_id": "ghost", "policy": "off", "window": "any"})
    assert ghost.status_code == 409 and ghost.json()["reason"] == "unknown_node"
    assert put(box, {"policy": "off", "channel": "stable"}).status_code == 422  # channel is not changed here
    box.report(policy=None, window=None, settings_source=None)  # an older onemindd
    old = put(box, {"policy": "off"})
    assert old.status_code == 409 and old.json()["reason"] == "settings_unknown"
    assert put(box, {"policy": "off", "window": "any"}).status_code == 202


def test_approval_rechecks_that_the_change_is_still_a_change(box):
    a = put(box, {"policy": "notify"}).json()
    box.report(policy="notify", settings_source="owner")  # set at the box meanwhile
    stale = box.post(f"/v1/actions/{a['id']}/approve", headers=OWNER, json=sign(box, a["id"]))
    assert stale.status_code == 409
    assert box.get(f"/v1/actions/{a['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_a_standing_approval_never_accepts_a_settings_change(plain, host):
    """Review (#1342): even a hook that grants everything cannot turn security updates off unattended:
    os.update.settings is `sensitive`, above the standing-approval ceiling (§12.3: read and write only)."""
    from onemind_core.actions import StandingGrant
    from onemind_core.auth import Principal

    rogue = StandingGrant(Principal("policy:pol_rogue@1", "policy", "policy"), {"approved_via": "policy"}, lambda: None)
    plain.app.state.gateway.actions.standing_approvals.insert(0, lambda a: rogue)
    for body in ({"policy": "off"}, {"window": "any"}):
        r = put(plain, body)
        assert r.status_code == 202 and r.json()["state"] == "awaiting_approval", r.text
    assert host.posts == []
