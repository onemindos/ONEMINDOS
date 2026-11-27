# SPDX-License-Identifier: Apache-2.0
"""#186 E2 broker: a host grant is pending until an owner approves it, and revocation removes it."""

from __future__ import annotations

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER, action_body
from onemind_core.automation import registry
from onemind_core.hostgrants.kinds import NO_HOST, HostAllowance

PATH = "/v1/host-grants"


def body(clock, key="g1", **over):
    out = {"app_id": "uptime-kuma", "kind": "device", "device_class": "usb-serial", "path": "/dev/ttyACM0",
           "reason": "Z-Wave stick", "idempotency_key": key, "expires_at": action_body(clock)["expires_at"]}
    out.update(over)
    return {k: v for k, v in out.items() if v is not None}


def approve(client, action_id, headers=OWNER):
    return client.post(f"/v1/actions/{action_id}/approve", headers=headers)


def test_a_grant_waits_for_the_owner_and_then_allows_exactly_that_node(client, clock):
    broker = client.app.state.host_grants
    r = client.post(PATH + "/requests", json=body(clock), headers=OWNER)
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["type"] == "host.grant" and action["state"] == "awaiting_approval"
    assert action["params"] == {"app_id": "uptime-kuma", "kind": "device", "device_class": "usb-serial",
                                "path": "/dev/ttyACM0", "reason": "Z-Wave stick"}
    assert broker.allowance("uptime-kuma") == NO_HOST
    assert approve(client, action["id"]).json()["state"] == "succeeded"
    assert broker.allowance("uptime-kuma") == HostAllowance(frozenset({"/dev/ttyACM0"}))
    assert broker.allowance("whoami") == NO_HOST  # another app gets nothing from it
    [grant] = client.get(PATH, headers=OWNER).json()["grants"]
    assert grant["approved_by"] and grant["action_id"] == action["id"]
    assert client.get(PATH, params={"app_id": "whoami"}, headers=OWNER).json() == {"grants": []}


@pytest.mark.parametrize("headers", [AGENT, ADULT, GUEST])
def test_only_an_owner_approves_reads_or_revokes(client, clock, headers):
    filed = client.post(PATH + "/requests", json=body(clock), headers=OWNER).json()
    assert approve(client, filed["id"], headers).status_code == 403
    assert client.get(PATH, headers=headers).status_code == 403
    approve(client, filed["id"])
    gid = client.get(PATH, headers=OWNER).json()["grants"][0]["id"]
    assert client.post(f"{PATH}/{gid}/revoke", headers=headers).status_code == 403
    assert client.app.state.host_grants.allowance("uptime-kuma").device_paths == {"/dev/ttyACM0"}


def test_people_who_are_not_owners_cannot_file_and_nobody_unauthenticated_can(client, clock):
    assert client.post(PATH + "/requests", json=body(clock), headers=GUEST).status_code == 403
    assert client.post(PATH + "/requests", json=body(clock), headers={}).status_code == 401
    assert client.post(PATH + "/requests", json=body(clock, key="a"), headers=AGENT).status_code == 202


@pytest.mark.parametrize("over", [
    {"path": "/dev/sda"}, {"device_class": None}, {"kind": "privileged"}, {"kind": "host-network"},
    {"kind": "gpu", "device_class": None, "path": "/dev/dri"}, {"reason": "  "}, {"extra": True},
    {"path": "/dev/serial/by-id/../../sda"},
])
def test_a_request_names_exactly_one_allowed_thing(client, clock, over):
    r = client.post(PATH + "/requests", json=body(clock, **over), headers=OWNER)
    assert r.status_code == 422, r.text


def test_unknown_app_community_tier_and_duplicates_are_refused(client, clock):
    assert client.post(PATH + "/requests", json=body(clock, app_id="no-such-app"), headers=OWNER).status_code == 404
    community = client.post(PATH + "/requests", json=body(clock, app_id="vault-like"), headers=OWNER)
    assert community.status_code == 409 and "Z-21" in community.json()["message"]
    first = client.post(PATH + "/requests", json=body(clock), headers=OWNER)
    replay = client.post(PATH + "/requests", json=body(clock), headers=OWNER)
    assert first.json()["id"] == replay.json()["id"]
    approve(client, first.json()["id"])
    assert client.post(PATH + "/requests", json=body(clock, key="g2"), headers=OWNER).status_code == 409


def test_revocation_is_final_for_requests_filed_before_it(client, clock):
    early = client.post(PATH + "/requests", json=body(clock, key="early"), headers=AGENT).json()
    first = client.post(PATH + "/requests", json=body(clock, key="first"), headers=OWNER).json()
    approve(client, first["id"])
    gid = client.get(PATH, headers=OWNER).json()["grants"][0]["id"]
    clock.advance(1)
    assert client.post(f"{PATH}/{gid}/revoke", headers=OWNER).json()["active"] is False
    assert client.app.state.host_grants.allowance("uptime-kuma") == NO_HOST
    stale = approve(client, early["id"])
    assert stale.status_code == 409 and stale.json()["error"] == "stale_precondition"
    clock.advance(1)
    again = client.post(PATH + "/requests", json=body(clock, key="again"), headers=OWNER).json()
    assert approve(client, again["id"]).json()["state"] == "succeeded"


def test_no_standing_approval_or_unapproved_run_activates_a_grant(client, clock):
    assert registry.policy_may_cover("host.grant", {}) is not None
    broker = client.app.state.host_grants
    filed = client.post(PATH + "/requests", json=body(clock), headers=AGENT).json()
    results = []
    broker.activate(broker.gw.repo.get(filed["id"]), results.append)  # still awaiting approval
    assert results[0].outcome == "failed" and broker.allowance("uptime-kuma") == NO_HOST


def test_revoking_an_unknown_grant_is_404(client):
    assert client.post(f"{PATH}/hg_unknown/revoke", headers=OWNER).status_code == 404
