# SPDX-License-Identifier: Apache-2.0
"""Security properties of storage actions (STORAGE-ACT-1, A7 review).

* Every destructive storage action needs the owner AND the owner's passkey; agents only request.
* No LUKS key or passphrase reaches a log, the audit chain, an event or an API answer; the recovery
  key route is off until founder decisions F-61/F-62 are made.
* A disk is named by /dev/<name>, a WWN or a serial, never by a path that climbs out of /dev.

All key-looking values here are obviously fake."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from conftest import AGENT, GUEST, OWNER
from test_storage import (  # noqa: F401  (fixtures and helpers of the storage tests)
    FakeNode, approve, booted, events, no_poller, node, request_create,
)

DESTRUCTIVE = [
    ("storage.mirror.create", {"device": "/dev/vdc"}),
    ("storage.mirror.add", {"device": "/dev/vdc"}),
    ("storage.mirror.replace", {"member": "2", "device": "/dev/vdc"}),
    ("storage.mirror.remove", {"member": "2", "wipe": True}),
]


def file_request(c, kind, params, headers=OWNER):
    return c.post("/v1/storage/actions", headers=headers, json={"type": kind, "params": params, "idempotency_key": f"k-{kind}"})


@pytest.mark.parametrize("kind,params", DESTRUCTIVE, ids=[k for k, _ in DESTRUCTIVE])
def test_destructive_actions_need_a_passkey_even_from_the_owner_token(settings, clock, node, no_poller, kind, params):
    with booted(settings, clock, node) as c:
        r = file_request(c, kind, params)
        assert r.status_code == 202, r.text
        aid = r.json()["action"]["id"]
        for headers in (OWNER, {"OneMind-CSRF": c.cookies.get("onemind_csrf")}):  # token, or the signed-in session
            refused = c.post(f"/v1/actions/{aid}/approve", headers=headers)
            assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required", refused.text
        assert c.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
        assert node.started == []  # nothing was sent to the disks
        assert approve(c, aid).status_code == 200  # with the owner's passkey it runs
        assert len(node.started) == 1


def test_passkey_off_switch_does_not_open_destructive_storage(settings, clock, node, no_poller):
    """identity's require_passkey_approval=False lets owners approve other actions by token; erasing a
    disk still needs the passkey."""
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from onemind_core.app import create_app
    from onemind_core.identity import IdentitySettings
    from test_identity import ORIGIN, RP_ID
    from test_storage import _settings

    s = _settings(settings, node)
    s = replace(s, sections={**s.sections, "identity": IdentitySettings(
        rp_id=RP_ID, origins=(ORIGIN,), cookie_secure=False, require_passkey_approval=False)})
    with TestClient(create_app(s, clock=clock)) as c:
        aid = request_create(c).json()["action"]["id"]
        seen: list[dict] = []
        c.app.state.gateway.events.subscribe("auth.>", seen.append)
        r = c.post(f"/v1/actions/{aid}/approve", headers=OWNER)
        assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
        assert node.started == []
        assert any(e["type"] == "auth.step_up.required" and e["data"]["reason"] == "destructive_storage_needs_passkey" for e in seen)


def test_no_passkey_registered_means_no_destructive_approval(settings, clock, node, no_poller):
    from fastapi.testclient import TestClient

    from onemind_core.app import create_app
    from test_storage import _settings

    with TestClient(create_app(_settings(settings, node), clock=clock)) as c:  # no owner account, no passkey
        aid = request_create(c).json()["action"]["id"]
        assert c.post(f"/v1/actions/{aid}/approve", headers=OWNER).status_code == 401
        assert c.post(f"/v1/actions/{aid}/approve", headers=OWNER, json={"webauthn": {"id": "x"}}).status_code == 401
        assert node.started == []


def test_repair_is_not_destructive_and_keeps_the_ordinary_owner_approval(settings, clock, node, no_poller):
    """Only data-losing types get the extra step-up; repair re-syncs a set and erases nothing."""
    with booted(settings, clock, node) as c:
        r = c.post("/v1/storage/actions", headers=OWNER, json={"type": "storage.mirror.repair", "params": {}})
        assert r.status_code == 202 and r.json()["risk"] == "write"
        aid = r.json()["action"]["id"]
        assert approve(c, aid).status_code == 200


def test_agents_and_guests_can_only_request(settings, clock, node, no_poller):
    with booted(settings, clock, node) as c:
        for kind, params in DESTRUCTIVE[:3]:
            aid = file_request(c, kind, params, headers=AGENT).json()["action"]["id"]
            assert c.post(f"/v1/actions/{aid}/approve", headers=AGENT).status_code == 403
            # an agent cannot ride a passkey assertion either: approvals are owner principals only
            opts = c.post(f"/v1/actions/{aid}/approve-options", headers=OWNER).json()
            body = {"webauthn": c.key.assert_(opts["challenge"], flat=True)}
            assert c.post(f"/v1/actions/{aid}/approve", headers=AGENT, json=body).status_code == 403
            assert c.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
        assert file_request(c, "storage.mirror.remove", {"member": "2"}, headers=AGENT).status_code == 403
        assert file_request(c, "storage.mirror.create", {"device": "/dev/vdc"}, headers=GUEST).status_code == 403
        assert node.started == []


def test_the_generic_actions_route_cannot_file_a_storage_action(settings, clock, node, no_poller):
    """POST /v1/actions is for app actions: a storage type there is refused, so nothing skips the plan."""
    with booted(settings, clock, node) as c:
        for who in (OWNER, AGENT):
            r = c.post("/v1/actions", headers=who, json={
                "type": "storage.mirror.create", "params": {"device": "/dev/vdc"}, "idempotency_key": "g1",
                "expires_at": "2099-01-01T00:00:00Z"})
            assert r.status_code in (400, 422), r.text
        assert node.started == []


@pytest.mark.parametrize("device", [
    "/dev/../etc/shadow", "/dev/sda/../sdb", "/dev//sda", "/dev/./sda", "/dev/sda/..", "/dev/",
    "../../etc/passwd", "/etc/passwd", "/dev/vdc;reboot", "/dev/vdc\nrm", "/dev/vdc && x", "-rf",
])
def test_device_paths_are_validated_before_anything_runs(settings, clock, node, no_poller, device):
    with booted(settings, clock, node) as c:
        for kind, key in (("storage.mirror.create", "device"), ("storage.mirror.add", "device"),
                          ("storage.mirror.remove", "member")):
            params = {key: device}
            assert c.post("/v1/storage/plans", headers=OWNER, json={"type": kind, "params": params}).status_code == 422
            assert file_request(c, kind, params).status_code == 422
        r = c.post("/v1/storage/actions", headers=OWNER, json={
            "type": "storage.mirror.replace", "params": {"member": "1", "device": device}})
        assert r.status_code == 422
        assert node.started == [] and node.plans == 0  # not even a plan was asked of the node


@pytest.mark.parametrize("device", ["/dev/vdc", "/dev/disk/by-id/ata-FAKE_DISK_0001", "vdc", "wwn-0x5000000000000000", "FAKESERIAL1234"])
def test_plain_disk_names_are_accepted(settings, clock, node, no_poller, device):
    with booted(settings, clock, node) as c:
        assert c.post("/v1/storage/plans", headers=OWNER, json={"type": "storage.mirror.create", "params": {"device": device}}).status_code == 200


# ---- keys never leave the node through the gateway ---------------------------------------------------
def audit_text(settings) -> str:
    return Path(settings.audit_path).read_text()


def test_recovery_key_route_is_off_by_default(settings, clock, node, no_poller):
    with booted(settings, clock, node) as c:  # recovery_key_api not set
        r = c.post("/v1/storage/recovery-key", headers=OWNER)
        assert r.status_code == 404 and "FAKE-RECOVERY-KEY" not in r.text
        assert node.recovery_key is not None  # the gateway did not even ask the node for it
        assert c.get("/v1/storage", headers=OWNER).json()["recovery_key_pending"] is True  # a flag, never the key


def test_no_key_in_logs_audit_events_or_answers(settings, clock, node, no_poller, caplog):
    caplog.set_level(logging.DEBUG)
    with booted(settings, clock, node, recovery_key_api=True) as c:
        seen = events(c)
        aid = request_create(c).json()["action"]["id"]
        answers = [
            c.get("/v1/storage", headers=OWNER).text,
            c.get("/v1/storage/devices", headers=OWNER).text,
            c.get(f"/v1/storage/operations/{aid}", headers=OWNER).text,
            c.get(f"/v1/actions/{aid}", headers=OWNER).text,
            approve(c, aid).text,
            c.get("/v1/actions", headers=OWNER).text,
            c.get("/v1/audit", headers=OWNER).text,
        ]
        c.app.state.storage.poll()
        key = c.post("/v1/storage/recovery-key", headers=OWNER).json()["one_time"]["recovery_key"]
        assert key == "FAKE-RECOVERY-KEY-FOR-TESTS-ONLY"
        answers.append(c.get(f"/v1/actions/{aid}", headers=OWNER).text)
        blob = "\n".join(answers) + audit_text(settings) + json.dumps(seen) + caplog.text
        assert key not in blob
        assert any(e["type"] == "storage.recovery_key.shown" for e in seen)  # the fact is told, not the key


def test_plans_and_requests_carry_no_secret_fields(settings, clock, node, no_poller):
    """params are stored and audited: the request model has no field a key could travel in."""
    with booted(settings, clock, node) as c:
        for field in ("passphrase", "key", "recovery_key", "keyfile", "password"):
            r = c.post("/v1/storage/actions", headers=OWNER, json={
                "type": "storage.mirror.create", "params": {"device": "/dev/vdc", field: "FAKE-NOT-A-REAL-SECRET"}})
            assert r.status_code == 422, field
