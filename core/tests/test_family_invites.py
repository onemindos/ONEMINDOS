# SPDX-License-Identifier: Apache-2.0
"""D-034 invitation authorization and verification through the gateway."""

from conftest import AGENT, OWNER
from test_identity import SoftAuthenticator, csrf, idc, register_passkey, setup_owner, stepped  # noqa: F401


def test_install_token_cannot_issue_invites_before_first_owner_setup(idc):
    response = idc.post("/v1/users", headers=OWNER, json={"display_name": "Family", "role": "adult"})
    assert response.status_code == 403, response.text
    assert idc.get("/v1/auth/setup/status").json()["state"] == "unclaimed"
    setup_owner(idc)
    assert [user["role"] for user in idc.get("/v1/users").json()] == ["owner"]


def test_direct_and_queued_invites_require_the_same_verification(idc):
    setup_owner(idc)
    register_passkey(idc, SoftAuthenticator())
    body = {"display_name": "Family", "role": "adult"}
    direct = idc.post("/v1/users", headers=csrf(idc), json=body)
    assert direct.status_code == 401, direct.text
    step = direct.json()["details"][0]["step_up"]
    assert step["required_level"] == "L1" and step["box"] == "required"
    queued = idc.post("/v1/users/invites", headers=csrf(idc), json=body)
    assert queued.status_code == 202, queued.text
    action = f"/v1/actions/{queued.json()['id']}"
    assert idc.get(action).json()["required_level"] == "L2"
    options = idc.post(f"{action}/approve-options", headers=csrf(idc))
    assert options.status_code == 200, options.text
    assert options.json()["required_level"] == "L1" and options.json()["box_code_required"]

    agent = idc.post("/v1/users", headers=AGENT, json=body)
    assert agent.status_code == 403, agent.text
    approve = idc.post(f"{action}/approve", headers=AGENT)
    assert approve.status_code == 403, approve.text
    assert idc.get(action).json()["state"] == "awaiting_approval"
    assert len(idc.get("/v1/users").json()) == 1

    invitation = stepped(idc, "POST", "/v1/users", json=body)
    assert invitation.status_code == 201, invitation.text
    assert invitation.headers["cache-control"] == "no-store"
    assert "#enrol=" in invitation.json()["one_time"]["enrolment_url"]
    assert [row["id"] for row in idc.get("/v1/actions").json()] == [queued.json()["id"]]
