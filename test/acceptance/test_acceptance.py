# SPDX-License-Identifier: Apache-2.0
"""API acceptance checks against a live hub. Each test names the docs/leap/ALPHA-CHECKLIST.md row it serves.

Nothing here approves an install: requests are filed, inspected and denied, so a hub under test is
left as it was found. Run: ONEMIND_HUB_URL=... ONEMIND_OWNER_TOKEN=... pytest test/acceptance
"""

from __future__ import annotations

import pytest
from conftest import cites, install_request

INSTALL = "Install and first steps"
SECURITY = "Security basics"
BACKUPS = "Backups and restore"
APPS = "App updates: health-gated, with rollback"

# The gateway locks an address out for 15 minutes after 10 failed sign-ins a minute (guard.py), so
# the suite sends only a handful of bad credentials in total: two without a token, two with a wrong one.
UNAUTH_PATHS = ["/v1/actions", "/v1/audit/events"]


# ---- health and sign-in ---------------------------------------------------------------------------

@cites(INSTALL)
def test_health_is_open_and_ok(hub):
    r = hub.call("GET", "/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}


@cites(SECURITY)
def test_swagger_uis_are_not_exposed(hub):
    for path in ("/docs", "/redoc"):
        assert hub.call("GET", path).status_code in (401, 404), path


@cites(INSTALL)
def test_owner_token_signs_in(hub, owner):
    inst = hub.json("GET", "/v1/instance", owner, 200)
    assert inst["name"] and inst["version"]
    me = hub.call("GET", "/v1/me", owner)
    assert me.status_code == 200, me.text[:200]
    assert me.json()["principal"]["role"] == "owner"


# ---- denial tests ---------------------------------------------------------------------------------

@cites(SECURITY)
def test_no_token_is_401(hub):
    for path in UNAUTH_PATHS:
        r = hub.call("GET", path)
        assert r.status_code == 401, f"{path} -> {r.status_code}"
        assert r.json()["error"]


@cites(SECURITY)
def test_wrong_token_is_401(hub):
    for path in UNAUTH_PATHS:
        assert hub.call("GET", path, "not-a-real-token-0123456789").status_code == 401, path


@cites(SECURITY)
def test_wrong_scope_cannot_request_or_approve(hub, owner, reader_token, filed, app_id):
    r = hub.call("POST", "/v1/actions", reader_token, json=install_request(app_id, "reader"))
    assert r.status_code == 403, r.text[:200]
    waiting = filed(owner, "reader-approve")
    r = hub.call("POST", f"/v1/actions/{waiting['id']}/approve", reader_token)
    assert r.status_code == 403, r.text[:200]
    assert hub.json("GET", f"/v1/actions/{waiting['id']}", owner, 200)["state"] == "awaiting_approval"


@cites(SECURITY)
def test_child_cannot_install_or_see_backups(hub, owner, child_token, app_id):
    r = hub.call("POST", "/v1/actions", child_token, json=install_request(app_id, "child"))
    assert r.status_code == 403, r.text[:200]
    assert hub.call("GET", "/v1/backups/status", child_token).status_code == 403
    apps = hub.json("GET", "/v1/apps", owner, 200)
    assert not next(a for a in apps if a["id"] == app_id)["installed"]


# ---- approval gate --------------------------------------------------------------------------------

@cites(APPS)
def test_install_files_an_approval_and_installs_nothing(hub, owner, filed, app_id):
    a = filed(owner, "owner")
    assert a["state"] == "awaiting_approval", a["state"]
    assert a["type"] == "app.install" and a["params"]["app_id"] == app_id
    assert a.get("plan_sha256"), "an approval must be bound to a plan"
    again = hub.json("GET", f"/v1/actions/{a['id']}", owner, 200)
    assert again["state"] == "awaiting_approval"
    row = next(x for x in hub.json("GET", "/v1/apps", owner, 200) if x["id"] == app_id)
    assert row["installed"] is False and row["status"] == "not_installed"


@cites(SECURITY)
def test_ai_proposed_action_waits_for_a_human(hub, owner, agent_token, filed, app_id):
    a = filed(agent_token, "agent")
    assert a["state"] == "awaiting_approval"
    assert a["requested_by"]["kind"] == "agent"
    r = hub.call("POST", f"/v1/actions/{a['id']}/approve", agent_token)
    assert r.status_code == 403, f"an agent approved its own request: {r.status_code} {r.text[:200]}"
    still = hub.json("GET", f"/v1/actions/{a['id']}", owner, 200)
    assert still["state"] == "awaiting_approval"
    row = next(x for x in hub.json("GET", "/v1/apps", owner, 200) if x["id"] == app_id)
    assert row["installed"] is False


@cites(SECURITY)
def test_denied_request_stays_not_installed(hub, owner, filed, app_id):
    a = filed(owner, "deny")
    d = hub.json("POST", f"/v1/actions/{a['id']}/deny", owner, 200)
    assert d["state"] == "cancelled" and d["state"] != "succeeded"
    row = next(x for x in hub.json("GET", "/v1/apps", owner, 200) if x["id"] == app_id)
    assert row["installed"] is False


# ---- audit ----------------------------------------------------------------------------------------

@cites(SECURITY)
def test_audit_records_the_request_and_the_chain_verifies(hub, owner, filed):
    a = filed(owner, "audit")
    events = hub.json("GET", f"/v1/audit/events?action_id={a['id']}", owner, 200)
    names = {e["event"] for e in events}
    assert {"action.requested", "action.awaiting_approval"} <= names, names
    assert not names & {"action.approved", "action.dispatched"}, "nothing may run before approval"
    v = hub.json("GET", "/v1/audit/verify", owner, 200)
    assert v["ok"] is True and v["first_bad_seq"] is None


# ---- backups --------------------------------------------------------------------------------------

@cites(BACKUPS)
def test_backup_listing(hub, owner):
    assert hub.json("GET", "/v1/backups/status", owner, 200).get("setup") is not None
    for path in ("/v1/backups/destinations", "/v1/backups/runs", "/v1/backups/snapshots"):
        r = hub.call("GET", path, owner)
        if r.status_code == 503 and r.json().get("reason") == "backups_disabled":
            pytest.skip("backups are not switched on for this hub (ONEMIND_BACKUPS_ENABLED=1)")
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        assert isinstance(r.json(), (list, dict)), path
