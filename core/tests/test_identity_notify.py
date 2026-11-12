# SPDX-License-Identifier: Apache-2.0
"""Household identity (§12.6) together with notifications (§12.14) and monitoring (§12.15).

The two streams were built apart; these pin down how they meet: household accounts are notified,
their role scopes reach the notification and monitoring routes the contract gives them, and an
app hidden by per-app sharing stays hidden on the per-app monitoring routes."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, GUEST, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.monitoring import MonitoringSettings
from onemind_core.notify import NotifySettings
from test_identity import SoftAuthenticator, csrf, enrol, id_settings, register_passkey, setup_owner


@pytest.fixture
def hc(settings, clock, executor, tmp_path):
    s = id_settings(settings)
    s = replace(s, sections={**s.sections, "notify": NotifySettings(worker=False, dir=tmp_path / "keys"),
                             "monitoring": MonitoringSettings(enabled=False)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def me(c: TestClient) -> str:
    return c.get("/v1/me").json()["principal"]["id"]


def test_household_owner_gets_approval_notifications(hc, clock):
    setup_owner(hc)  # hc is now the owner's browser session
    aid = hc.post("/v1/actions", headers=AGENT, json=action_body(clock)).json()["id"]
    items = hc.get("/v1/notifications").json()
    assert [(n["topic"], n["action_id"]) for n in items] == [("approvals", aid)]
    assert hc.get("/v1/notifications", headers=OWNER).json()[0]["action_id"] == aid  # the file owner too


def test_people_source_lists_active_accounts_only(hc):
    setup_owner(hc)
    adult = enrol(hc, "adult", "ana")
    uid, owner_id = me(adult), me(hc)
    people = hc.app.state.notify.people()
    assert people[uid] == "adult" and people[owner_id] == "owner" and people["owner"] == "owner"
    assert hc.post(f"/v1/users/{uid}/disable", headers=csrf(hc)).status_code == 200
    assert uid not in hc.app.state.notify.people()


def test_role_scopes_reach_the_notification_routes(hc):
    setup_owner(hc)
    adult, guest, child = enrol(hc, "adult", "ana"), enrol(hc, "guest", "gus"), enrol(hc, "child", "kid")
    for c in (adult, guest, child):  # every person reads their own inbox and the alerts for them
        assert c.get("/v1/notifications").status_code == 200
        assert c.get("/v1/alerts").status_code == 200
        assert c.get("/v1/notifications/preferences").status_code == 200
        assert c.post("/v1/notifications/read-all", headers=csrf(c)).status_code == 200
        assert c.get("/v1/push/vapid-public-key").status_code == 200
    # A loopback webhook: the handler refuses it for a non-owner (422, no DNS lookup), so a 422 shows
    # the guest's notifications:write passed the scope check; a scope refusal is 403.
    body = {"kind": "webhook", "label": "x", "config": {"url": "http://127.0.0.1:9/x"}}
    r = guest.post("/v1/notifications/channels", json=body, headers=csrf(guest))
    assert r.status_code == 422 and r.json()["error"] == "conflict"
    # A child has notifications:read but not :write (§12.6 role table).
    assert child.post("/v1/notifications/channels", json=body, headers=csrf(child)).status_code == 403
    assert child.put("/v1/notifications/preferences", json={"routes": []}, headers=csrf(child)).status_code == 403
    # Only agents, plugins and automations send; owners keep `*`, the handler refuses people.
    send = {"severity": "info", "topic": "plugin.x", "title": "t", "body": "b", "dedupe_key": "k"}
    assert adult.post("/v1/notifications/send", json=send, headers=csrf(adult)).status_code == 403


def test_role_scopes_reach_the_monitoring_routes(hc):
    setup_owner(hc)
    adult, guest = enrol(hc, "adult", "ana"), enrol(hc, "guest", "gus")
    assert adult.get("/v1/monitoring/summary").status_code == 200
    assert adult.get("/v1/apps/whoami/metrics").status_code == 200
    assert adult.get("/v1/nodes/n1/metrics").status_code == 404  # allowed, no such node
    # monitoring:read is not a guest scope (§12.6), though nodes:read and apps:read are.
    assert guest.get("/v1/monitoring/summary").status_code == 403
    assert guest.get("/v1/nodes/n1/metrics").status_code == 403
    assert guest.get("/v1/apps/whoami/logs").status_code == 403
    assert hc.get("/v1/monitoring/summary").status_code == 200  # owner: `*`


def test_sharing_gates_the_per_app_routes(hc):
    setup_owner(hc)
    guest = enrol(hc, "guest", "gus")
    assert guest.get("/v1/apps/whoami").status_code == 404  # not shared: as absent as in GET /v1/apps
    owner_view = hc.get("/v1/apps/whoami").json()["access"]
    assert owner_view == {"roles": ["owner", "adult"], "shared_with_me": True}
    hc.put("/v1/apps/whoami/access", json={"roles": ["guest"]}, headers=csrf(hc))
    r = guest.get("/v1/apps/whoami")
    assert r.status_code == 200 and r.json()["access"] == {"roles": ["owner", "guest"], "shared_with_me": True}
    # A static-file guest keeps the v0 catalog view (F-14) but is not counted as shared with.
    hc.put("/v1/apps/whoami/access", json={"roles": []}, headers=csrf(hc))
    r = hc.get("/v1/apps/whoami", headers=GUEST)
    assert r.status_code == 200 and r.json()["access"]["shared_with_me"] is False
    assert guest.get("/v1/apps/whoami").status_code == 404  # unsharing is instant


def _fixable_alert(hc, clock):
    """An installed app whose scan went stale: the alert carries an app.remove fix."""
    hc.post("/v1/actions", headers=OWNER, json=action_body(clock))
    aid = hc.get("/v1/actions", headers=OWNER).json()[0]["id"]
    assert hc.post(f"/v1/actions/{aid}/approve", headers=csrf(hc)).status_code == 200  # no passkey yet
    hc.app.state.events.publish_event("app", "scan_blocked", {"app_id": "uptime-kuma"}, severity="critical")
    return next(a for a in hc.get("/v1/alerts", headers=OWNER).json() if a["type"] == "app.scan_blocked")


def test_fix_with_approve_cannot_skip_the_approval_gates(hc, clock):
    """/v1/alerts/{id}/fix {"approve": true} is an approval path: it needs the approve scope and,
    once an owner has a passkey, a passkey assertion, exactly like POST /v1/actions/{id}/approve."""
    setup_owner(hc)
    alert = _fixable_alert(hc, clock)
    fix = f"/v1/alerts/{alert['id']}/fix"

    # 1. A narrowed owner token (actions:request only) may file the fix but not approve it.
    pat = hc.post("/v1/tokens", headers=csrf(hc),
                  json={"name": "narrow", "scopes": ["actions:request", "alerts:read"]}).json()["one_time"]["token"]
    bearer = {"Authorization": f"Bearer {pat}"}
    r = hc.post(fix, headers=bearer, json={"approve": True})
    assert r.status_code == 403, r.text
    filed = hc.post(fix, headers=bearer)  # without approve it is an ordinary request
    assert filed.status_code == 202 and filed.json()["state"] == "awaiting_approval"

    # 2. Once the owner has a passkey, no credential can approve through this route.
    register_passkey(hc, SoftAuthenticator())
    r = hc.post(fix, headers=OWNER, json={"approve": True})
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required", r.text
    # The signed-in owner already has this fix pending (filed above), which a repeat call returns as is.
    again = hc.post(fix, headers=csrf(hc), json={"approve": True})
    assert again.status_code == 202 and again.json()["state"] == "awaiting_approval"
    assert hc.get(f"/v1/actions/{filed.json()['id']}", headers=OWNER).json()["state"] == "awaiting_approval"


def test_fix_with_approve_still_works_without_passkeys(hc, clock):
    setup_owner(hc)
    alert = _fixable_alert(hc, clock)
    r = hc.post(f"/v1/alerts/{alert['id']}/fix", headers=csrf(hc), json={"approve": True})
    assert r.status_code == 202 and r.json()["type"] == "app.remove" and r.json()["state"] == "succeeded", r.text
