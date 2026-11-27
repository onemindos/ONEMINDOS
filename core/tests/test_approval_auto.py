# SPDX-License-Identifier: Apache-2.0
"""Gateway permissions PR 13: approval.auto notices (design §3.8, fix 10).

Each test fails without the change: before it a request a standing approval accepted told nobody,
had no Revoke action, and an `each` rule kept firing while its notices could not be delivered.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER, action_body
from onemind_core.app import create_app
from onemind_core.notify import NotifySettings
from onemind_core.notify import topics
from test_notify import FakeHttp, add_channel, inbox  # noqa: F401


@pytest.fixture
def nc(settings, clock, executor, tmp_path):
    s = replace(settings, sections={"notify": NotifySettings(worker=False, dir=tmp_path / "keys")})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        r = c.post("/v1/actions", json=action_body(clock, "whoami", key="inst"), headers=OWNER)
        assert c.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).json()["state"] == "succeeded"
        yield c


@pytest.fixture
def http():
    srv = FakeHttp()
    yield srv
    srv.close()


def rule(c, clock, notify_after, types=("app.restart",)):
    r = c.post("/v1/approval-policies", headers=OWNER, json={
        "allow": {"types": list(types), "requested_by": ["agent:hermes"], "params": {}}, "limits": {"per_day": 50},
        "expires_at": (clock.now + timedelta(days=30)).isoformat().replace("+00:00", "Z"), "notify_after": notify_after})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def restart(c, clock, key):
    return c.post("/v1/actions", json=action_body(clock, "whoami", "app.restart", key=key), headers=AGENT).json()


def autos(c):
    return [n for n in inbox(c, OWNER) if n["title"].startswith("Approved by your rule")]


def test_each_use_is_pushed_with_a_revoke_action_and_never_an_approve_one(nc, clock, http):
    add_channel(nc, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    pid = rule(nc, clock, "each")
    a = restart(nc, clock, "e0")
    assert a["state"] == "succeeded"
    [n] = autos(nc)
    assert n["action_id"] == a["id"] and pid in n["body"] and n["link"] == f"/settings/permissions/rules/{pid}"
    kinds = {x["kind"] for x in n["actions"]}
    assert kinds == {"revoke", "open"} and "approve" not in {x["id"] for x in n["actions"]}
    assert next(x for x in n["actions"] if x["kind"] == "revoke")["policy_id"] == pid
    assert nc.app.state.notify.repo.deliveries_for(n["id"])  # pushed, not only in the inbox
    nc.app.state.notify.pump()
    assert any(n["id"].encode() in r["body"] for r in http.requests)  # the notice itself went out


def test_an_app_can_never_post_an_approve_button():
    for kind in ("approve", "revoke"):
        with pytest.raises(ValueError):
            topics.check_actions([{"id": "x", "label": "x", "kind": kind}], lambda _t: True)


def test_digest_rules_go_to_the_inbox_and_the_daily_list_and_silent_rules_say_nothing(nc, clock, http):
    add_channel(nc, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    rule(nc, clock, "digest")
    restart(nc, clock, "d0")
    restart(nc, clock, "d1")
    items = autos(nc)
    assert len(items) == 2 and all(nc.app.state.notify.repo.deliveries_for(n["id"]) == [] for n in items)
    assert nc.app.state.notify.digest_tick(clock.now) == []  # never for a day that is still running
    clock.advance(86400)  # the next day: yesterday's list goes out once
    made = nc.app.state.notify.digest_tick(clock.now)
    assert len(made) == 1 and nc.app.state.notify.digest_tick(clock.now) == []
    daily = next(n for n in inbox(nc, OWNER) if n["id"] == made[0])
    assert daily["title"] == "Approved by your rules today: 2" and "Rules in force: 1" in daily["body"]


def test_silent_read_only_rules_are_not_notified(nc, clock):
    nc.app.state.notify._approval_auto({"event": "action.approved", "action_id": "x",
                                        "data": {"approved_via": "policy", "policy_id": "pol_1", "notify_after": "silent"}})
    assert autos(nc) == []


def test_an_each_rule_pauses_when_the_push_transport_fails(nc, clock, http):
    http.status = 503
    add_channel(nc, {"kind": "webhook", "label": "hook", "config": {"url": http.url}})
    pid = rule(nc, clock, "each")
    assert restart(nc, clock, "f0")["state"] == "succeeded"
    nc.app.state.notify.pump()
    row = next(p for p in nc.get("/v1/approval-policies", headers=OWNER).json() if p["id"] == pid)
    assert (row["state"], row["suspended_reason"]) == ("suspended", "push_failed")
    assert restart(nc, clock, "f1")["state"] == "awaiting_approval"
    # one tap re-confirms it once the owner has fixed the channel
    http.status = 200
    assert nc.post(f"/v1/approval-policies/{pid}/reconfirm", headers=OWNER).status_code == 200
    assert restart(nc, clock, "f2")["state"] == "succeeded"


def test_an_each_rule_with_nowhere_to_push_pauses(nc, clock):
    pid = rule(nc, clock, "each")  # no channel, no phone
    assert restart(nc, clock, "n0")["state"] == "succeeded"
    row = next(p for p in nc.get("/v1/approval-policies", headers=OWNER).json() if p["id"] == pid)
    assert row["suspended_reason"] == "no_push_target"
    assert restart(nc, clock, "n1")["state"] == "awaiting_approval"
