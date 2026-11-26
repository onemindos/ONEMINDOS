# SPDX-License-Identifier: Apache-2.0
"""P-16: going back to the previous OS version is approved only with the owner's passkey (D-028/D-029).

Real gateway with identity on, one owner with a passkey, and a stand-in for the host service that answers
like internal/host (test_hostlink.FakeHost). The approval is signed over the action, so a stolen token or a
signed-in session cannot reboot the box into an older system."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.identity import IdentitySettings
from test_hostlink import NODE, ROLLBACK_RAUC, FakeHost, link_settings
from test_identity import ORIGIN, RP_ID, SoftAuthenticator, at_box, register_passkey, setup_owner
from test_os_updates import HB


@pytest.fixture
def host():
    h = FakeHost()
    h.available["os-rollback"] = True
    yield h
    h.close()


@pytest.fixture
def passkey_box(settings, clock, executor, host):
    s = link_settings(settings, host.path)
    s = replace(s, sections={**s.sections, "identity": IdentitySettings(rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False,
                                                                         box_code_file=settings.audit_path.parent / "box-code.json")})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        setup_owner(c)
        c.key = SoftAuthenticator()
        register_passkey(c, c.key)
        hb = {**HB, "node_id": NODE, "rauc": ROLLBACK_RAUC}
        assert c.app.state.registry.ingest(f"onemind.node.{NODE}.status", json.dumps(hb).encode())
        c.clock = clock
        yield c


def file(c, headers=OWNER):
    return c.post("/v1/actions", headers=headers, json={
        "type": "os.rollback", "params": {"node_id": NODE, "version": "0.1.0"}, "idempotency_key": "rb-pk",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})


def sign(c, action_id, headers=OWNER):
    opts = c.post(f"/v1/actions/{action_id}/approve-options", headers=headers).json()
    return {"webauthn": c.key.assert_(opts["challenge"], flat=True), **at_box(c, opts)}


def test_a_bare_owner_token_or_session_never_approves_a_rollback(passkey_box, host):
    c = passkey_box
    aid = file(c).json()["id"]
    for headers in (OWNER, {"OneMind-CSRF": c.cookies.get("onemind_csrf")}):
        refused = c.post(f"/v1/actions/{aid}/approve", headers=headers)
        assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required", refused.text
    assert c.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert host.posts == []


def test_the_owners_passkey_sends_the_rollback_to_the_host(passkey_box, host):
    c = passkey_box
    aid = file(c).json()["id"]
    done = c.post(f"/v1/actions/{aid}/approve", headers=OWNER, json=sign(c, aid))
    assert done.status_code == 200, done.text
    assert done.json()["state"] == "dispatched"
    assert host.posts == [{"action_id": aid, "kind": "os-rollback", "version": "0.1.0"}]
    host.set_state(aid, "succeeded", message="rebooted into the previous version 0.1.0")
    c.app.state.hostlink.poll()
    final = c.get(f"/v1/actions/{aid}", headers=OWNER).json()
    assert final["state"] == "succeeded" and final["result"]["steps"][0]["kind"] == "os-rollback"


def test_an_agent_can_only_ask_and_cannot_ride_a_passkey(passkey_box, host):
    c = passkey_box
    assert file(c, headers=AGENT).status_code == 403
    aid = file(c).json()["id"]
    assert c.post(f"/v1/actions/{aid}/approve", headers=AGENT, json=sign(c, aid)).status_code == 403
    assert host.posts == []


def test_ordinary_installs_keep_their_own_approval(passkey_box):
    """The passkey rule is for os.rollback only: an install is still the owner's ordinary approval."""
    c = passkey_box
    r = c.post("/v1/actions", headers=OWNER, json={
        "type": "os.update.install", "params": {"node_id": NODE, "version": "0.1.2"}, "idempotency_key": "ins",
        "expires_at": (c.clock.now + timedelta(hours=1)).isoformat()})
    assert r.status_code == 201, r.text
    ok = c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER, json=sign(c, r.json()["id"]))
    assert ok.status_code == 200


def test_approval_rechecks_that_the_previous_version_is_still_the_same(passkey_box, host):
    c = passkey_box
    aid = file(c).json()["id"]
    changed = [{**s, "bundle_version": "0.0.9"} if s["bootname"] == "B" else s for s in ROLLBACK_RAUC["slots"]]
    hb = {**HB, "node_id": NODE, "rauc": {**ROLLBACK_RAUC, "slots": changed}}  # the other slot was overwritten since the request
    assert c.app.state.registry.ingest(f"onemind.node.{NODE}.status", json.dumps(hb).encode())
    stale = c.post(f"/v1/actions/{aid}/approve", headers=OWNER, json=sign(c, aid))
    assert stale.status_code == 409, stale.text
    assert c.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert host.posts == []
