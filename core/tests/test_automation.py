# SPDX-License-Identifier: Apache-2.0
"""Automation rules, standing approvals, windows, dry run and kill switch (contract §12.17).

Maps to docs/architecture/AUTOMATION.md §9 (AT-2..AT-6, AT-8..AT-11) and BACKLOG CORE-AUTO-2..4.
Runs on SQLite, and on PostgreSQL with ONEMIND_TEST_DB_URL.
"""

from __future__ import annotations

import itertools
import json
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from onemind_core.actions import StandingGrant
from onemind_core.app import create_app
from onemind_core.audit import verify
from onemind_core.auth import Principal
from onemind_core.automation import AutomationSettings

from conftest import AGENT, GUEST, OWNER, action_body


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@pytest.fixture
def auto_settings(settings):
    # The background thread stays off: tests drive tick() and process_events() themselves.
    return replace(settings, sections={"automation": AutomationSettings(enabled=False)})


@pytest.fixture
def client(auto_settings, clock, executor):
    with TestClient(create_app(auto_settings, clock=clock, executor=executor)) as c:
        yield c


def svc(client):
    return client.app.state.automation


_installs = itertools.count()


def install(client, clock, app_id="whoami"):
    key = f"inst-{app_id}-{next(_installs)}"
    r = client.post("/v1/actions", json=action_body(clock, app_id, key=key), headers=OWNER)
    assert r.status_code == 201, r.text
    r = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert r.json()["state"] == "succeeded", r.text


def remove_rule(trigger, app_id="whoami", **options):
    return {"name": "remove on trouble", "trigger": trigger,
            "actions": [{"type": "app.remove", "params": {"app_id": app_id}}],
            "options": {"debounce_s": 0, **options}}


def create_rule(client, body):
    r = client.post("/v1/automation/rules", json=body, headers=OWNER)
    assert r.status_code == 201, r.text
    return r.json()


def enable(client, rule_id):
    assert client.post(f"/v1/automation/rules/{rule_id}/dry-run", json={}, headers=OWNER).status_code == 200
    r = client.post(f"/v1/automation/rules/{rule_id}/enable", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


def policy(client, clock, *, types=("app.remove",), requested_by=("automation:*",), params=None,
           per_day=3, window_id=None, headers=OWNER):
    body = {"allow": {"types": list(types), "requested_by": list(requested_by), "params": params or {}},
            "limits": {"per_day": per_day}, "expires_at": iso(clock.now + timedelta(days=30))}
    if window_id:
        body["window_id"] = window_id
    return client.post("/v1/approval-policies", json=body, headers=headers)


def unhealthy(client, app_id="whoami", **kw):
    return client.app.state.gateway.events.publish_event(
        "app", "unhealthy", {"app_id": app_id}, resource={"kind": "app", "id": app_id}, **kw)


def audit_events(client) -> list[dict]:
    return [json.loads(line) for line in client.app.state.settings.audit_path.read_text().splitlines()]


# ---- rule validation -----------------------------------------------------------------------------
@pytest.mark.parametrize("body, needle", [
    (remove_rule({"schedule": {"cron": "* * * *"}}), "5 fields"),
    (remove_rule({"webhook": {}}), "not built yet"),
    (remove_rule({"event": {"type": "automation.fired"}}), "loop guard"),
    (remove_rule({"event": {"type": "app.unhealthy", "for_s": 60}}), "for_s"),
    (remove_rule({"schedule": {"cron": "0 3 * * *", "tz": "Mars/Base"}}), "time zone"),
    ({**remove_rule({"schedule": {"cron": "0 3 * * *"}}),
      "actions": [{"type": "node.remove", "params": {"node_id": "n1", "wipe": True}}]}, "may not request"),
    ({**remove_rule({"schedule": {"cron": "0 3 * * *"}}),
      "actions": [{"type": "app.remove", "params": {"app_id": "whoami", "delete_data": True}}]}, "destructive"),
    ({**remove_rule({"schedule": {"cron": "0 3 * * *"}}),
      "actions": [{"type": "app.rollback", "params": {"app_id": "whoami"}}]}, "cannot file"),
    ({**remove_rule({"schedule": {"cron": "0 3 * * *"}}),
      "actions": [{"type": "app.remove", "params": {"app_id": "${event.resource.id}"}}]}, "no event"),
    ({**remove_rule({"event": {"type": "app.unhealthy"}}),
      "actions": [{"type": "app.remove", "params": {"app_id": "app-${event.resource.id}"}}]}, "whole value"),
    ({**remove_rule({"schedule": {"cron": "0 3 * * *"}}),
      "actions": [{"type": "app.remove", "params": {"app_id": "whoami", "extra": 1}}]}, "params do not fit"),
    ({**remove_rule({"schedule": {"cron": "0 3 * * *"}}), "conditions": [{"x": 1}]}, "conditions"),
])
def test_bad_rules_are_refused(client, body, needle):
    r = client.post("/v1/automation/rules", json=body, headers=OWNER)
    assert r.status_code == 422, r.text
    assert needle in r.json()["message"]
    assert client.get("/v1/automation/rules", headers=OWNER).json() == []


def test_only_the_owner_writes_rules_and_anyone_reads(client):
    body = remove_rule({"schedule": {"cron": "0 3 * * *"}})
    assert client.post("/v1/automation/rules", json=body, headers=AGENT).status_code == 403
    rule = create_rule(client, body)
    assert rule["enabled"] is False and rule["revision"] == 1 and rule["created_by"]["id"] == "owner"
    assert client.get(f"/v1/automation/rules/{rule['id']}", headers=GUEST).json()["id"] == rule["id"]
    assert client.post(f"/v1/automation/rules/{rule['id']}/enable", headers=AGENT).status_code == 403
    assert client.delete(f"/v1/automation/rules/{rule['id']}", headers=AGENT).status_code == 403
    assert client.get("/v1/automation/rules/rule_nope", headers=OWNER).status_code == 404


def test_enable_needs_a_fresh_dry_run_of_the_current_revision(client, clock):
    rule = create_rule(client, remove_rule({"schedule": {"cron": "0 3 * * *"}}))
    r = client.post(f"/v1/automation/rules/{rule['id']}/enable", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"
    assert "dry_run_required" in r.json()["message"]
    assert enable(client, rule["id"])["enabled"] is True
    # An edit is a new revision: it disables the rule and needs its own dry run.
    r = client.patch(f"/v1/automation/rules/{rule['id']}", json={"name": "renamed"}, headers=OWNER)
    assert r.status_code == 200 and r.json()["revision"] == 2 and r.json()["enabled"] is False
    assert client.post(f"/v1/automation/rules/{rule['id']}/enable", headers=OWNER).status_code == 409
    client.post(f"/v1/automation/rules/{rule['id']}/dry-run", json={}, headers=OWNER)
    clock.advance(25 * 3600)  # a dry run older than 24 h no longer counts
    assert client.post(f"/v1/automation/rules/{rule['id']}/enable", headers=OWNER).status_code == 409
    # Turning a rule off only removes power: an agent may do it.
    enable(client, rule["id"])
    assert client.post(f"/v1/automation/rules/{rule['id']}/disable", headers=AGENT).json()["enabled"] is False
    assert client.post(f"/v1/automation/rules/{rule['id']}/disable", headers=GUEST).status_code == 403
    # A dry run unlocks enabling and costs an event scan: guests may not run one.
    assert client.post(f"/v1/automation/rules/{rule['id']}/dry-run", json={}, headers=GUEST).status_code == 403
    assert client.delete(f"/v1/automation/rules/{rule['id']}", headers=OWNER).status_code == 204


# ---- schedules -----------------------------------------------------------------------------------
def test_schedule_requests_as_the_rule_and_dry_run_matches_the_first_fire(client, clock):
    install(client, clock)
    rule = create_rule(client, remove_rule({"schedule": {"cron": "0 3 * * *", "tz": "Europe/London"}}))
    dry = client.post(f"/v1/automation/rules/{rule['id']}/dry-run", json={}, headers=OWNER).json()
    assert dry["policy_outcome"] == "needs_approval" and len(dry["would_request"]) == 7
    first = dry["would_request"][0]
    assert first["at"] == "2026-11-12T03:00:00Z" and first["verdict"] == "needs_approval"
    client.post(f"/v1/automation/rules/{rule['id']}/enable", headers=OWNER)
    sched = client.get("/v1/automation/schedules", headers=OWNER).json()
    assert sched[0]["next_fire_at"] == "2026-11-12T03:00:00Z"

    clock.now = datetime(2026, 11, 12, 2, 59, 50, tzinfo=UTC)
    assert svc(client).tick() == []
    clock.advance(20)
    fired = svc(client).tick()
    assert [f["outcome"] for f in fired] == ["requested"]
    assert svc(client).tick() == []  # the same minute never fires twice
    action = client.get(f"/v1/actions/{fired[0]['action_ids'][0]}", headers=OWNER).json()
    assert action["state"] == "awaiting_approval"  # an automation only asks
    assert action["requested_by"] == {"id": f"automation:{rule['id']}", "kind": "automation"}
    assert (action["type"], action["params"]) == (first["type"], first["params"])
    runs = client.get("/v1/automation/runs", headers=OWNER).json()
    assert runs[0]["rule_id"] == rule["id"] and runs[0]["action_ids"] == fired[0]["action_ids"]


@pytest.mark.parametrize("catch_up, expected", [("none", 0), ("last", 1)])
def test_missed_fires_after_downtime(client, clock, catch_up, expected):
    install(client, clock)
    rule = create_rule(client, remove_rule({"schedule": {"cron": "0 3 * * *"}}, catch_up=catch_up))
    enable(client, rule["id"])
    clock.advance(3 * 86400)  # the gateway was down for three nights
    fired = svc(client).tick()
    assert len(fired) == expected


def test_a_late_tick_fires_a_rule_once(client, clock):
    install(client, clock)
    rule = create_rule(client, remove_rule({"schedule": {"cron": "* * * * *"}}))
    enable(client, rule["id"])
    clock.now = datetime(2026, 11, 11, 22, 0, 30, tzinfo=UTC)
    svc(client).tick()
    clock.advance(100)  # 22:01 and 22:02 are both due, both inside the grace period
    fired = svc(client).tick()
    assert [f["outcome"] for f in fired] == ["requested"]
    action = client.get(f"/v1/actions/{fired[0]['action_ids'][0]}", headers=OWNER).json()
    assert action["requested_by"]["id"] == f"automation:{rule['id']}"


def test_concurrency_one(client, clock):
    install(client, clock)
    rule = create_rule(client, remove_rule({"schedule": {"cron": "*/5 * * * *"}}))
    enable(client, rule["id"])
    clock.now = datetime(2026, 11, 11, 22, 5, 1, tzinfo=UTC)
    assert svc(client).tick()[0]["outcome"] == "requested"
    clock.now = datetime(2026, 11, 11, 22, 10, 1, tzinfo=UTC)
    assert svc(client).tick()[0]["outcome"] == "skipped_concurrency"


# ---- standing approvals --------------------------------------------------------------------------
@pytest.mark.parametrize("kw, status, needle", [
    ({"types": ("app.install",)}, 422, "sensitive"),
    ({"types": ("backup.restore",)}, 422, "destructive"),
    ({"requested_by": ("agent:*",)}, 422, "names it exactly"),
    ({"types": ("nope.nope",)}, 422, "unknown action type"),
    ({"params": {"app_id": {"regex": "x"}}}, 422, "takes const"),
    ({"types": ("app.update",)}, 422, "window_id"),
    ({"types": ("automation.rule.enable",), "requested_by": ("agent:hermes",)}, 422, "always waits"),
    ({"window_id": "win_missing"}, 404, "no window"),
    ({"headers": AGENT}, 403, "may not"),
])
def test_bad_standing_approvals_are_refused(client, clock, kw, status, needle):
    r = policy(client, clock, **kw)
    assert r.status_code == status, r.text
    assert needle in r.json()["message"]


def test_standing_approval_expiry_is_bounded(client, clock):
    body = {"allow": {"types": ["app.remove"], "requested_by": ["automation:*"]}, "limits": {"per_day": 1},
            "expires_at": iso(clock.now + timedelta(days=91))}
    r = client.post("/v1/approval-policies", json=body, headers=OWNER)
    assert r.status_code == 422 and "90 days" in r.json()["message"]


def test_policy_limit_is_counted_in_the_database(client, clock, auto_settings, executor):
    pol = policy(client, clock, requested_by=("agent:hermes",), params={"app_id": {"enum": ["whoami"]}}).json()
    approver = f"policy:{pol['id']}@1"
    for i in range(3):
        install(client, clock)
        r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key=f"rm{i}"), headers=AGENT)
        assert r.status_code == 201
        a = r.json()
        assert a["state"] == "succeeded", a
        assert a["decided_by"] == {"id": approver, "kind": "policy", "role": "policy"}
    install(client, clock)
    # A restarted gateway keeps the count (from here on only the new process writes).
    with TestClient(create_app(auto_settings, clock=clock, executor=executor)) as again:
        r = again.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="rm3"), headers=AGENT)
        assert r.json()["state"] == "awaiting_approval"
        assert again.get("/v1/approval-policies", headers=GUEST).json()[0]["uses_24h"] == 3
        assert any(e["event"] == "automation.policy.limit_reached" and e["data"]["uses"] == "3/3"
                   for e in audit_events(again))
        approved = [e for e in audit_events(again) if e["event"] == "action.approved" and e["data"].get("approved_via")]
        assert approved[0]["data"]["approved_by"] == approver
        assert approved[0]["data"]["policy_created_by"] == "owner"
        # 24 hours later there is room again.
        again.post(f"/v1/actions/{r.json()['id']}/deny", headers=OWNER)
        clock.advance(86401)
        r = again.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="rm4"), headers=AGENT)
        assert r.json()["state"] == "succeeded"
        ok, _, msg = verify(again.app.state.settings.audit_path)
        assert ok, msg


def test_wildcards_never_cover_agents_and_params_must_match(client, clock):
    install(client, clock)
    policy(client, clock, requested_by=("automation:*", "person:*"))
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="a1"), headers=AGENT)
    assert r.json()["state"] == "awaiting_approval"
    client.post(f"/v1/actions/{r.json()['id']}/deny", headers=OWNER)
    policy(client, clock, requested_by=("agent:hermes",), params={"app_id": {"enum": ["uptime-kuma"]}})
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="a2"), headers=AGENT)
    assert r.json()["state"] == "awaiting_approval"


def test_sensitive_requests_are_never_auto_approved(client, clock):
    # Even an owner-set policy cannot be made to cover app.install; an automation's install waits.
    body = {**remove_rule({"event": {"type": "app.unhealthy"}}),
            "actions": [{"type": "app.install", "params": {"app_id": "${event.resource.id}"}}]}
    rule = create_rule(client, body)
    enable(client, rule["id"])
    policy(client, clock)  # covers app.remove only
    unhealthy(client, "whoami")
    fired = svc(client).process_events()
    a = client.get(f"/v1/actions/{fired[0]['action_ids'][0]}", headers=OWNER).json()
    assert a["type"] == "app.install" and a["state"] == "awaiting_approval"


def test_action_path_never_lets_a_policy_accept_above_write(client, clock):
    # docs/leap/core/AUTOMATION.md §4: enforced in the action path, not only where policies are made.
    install(client, clock)
    s, gw = svc(client), client.app.state.gateway
    s.repo.add_policy(  # written past validation, as a bug or a hand-edited database would
        id="pol_forged", name=None, per_day=10, window_id=None, expires_at=clock.now + timedelta(days=1),
        allow={"types": ["app.install"], "requested_by": ["agent:hermes"], "params": {}},
        created_by={"id": "owner"}, created_at=clock.now)
    rogue = StandingGrant(Principal("policy:pol_rogue@1", "policy", "policy"), {"approved_via": "policy"}, lambda: None)
    gw.actions.standing_approvals.insert(0, lambda a: rogue)
    r = client.post("/v1/actions", json=action_body(clock, "uptime-kuma", key="x1"), headers=AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert s.repo.count_uses("pol_forged", clock.now - timedelta(days=1)) == 0
    # The same hook does accept a write request, so the refusal above is the risk ceiling.
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="x2"), headers=AGENT)
    assert r.json()["state"] == "succeeded"


def test_a_failing_policy_approval_leaves_the_request_filed(client, clock, monkeypatch):
    install(client, clock)
    policy(client, clock, requested_by=("agent:hermes",))
    gw = client.app.state.gateway

    def boom(*_a, **_k):
        raise RuntimeError("database went away")

    monkeypatch.setattr(gw.actions.repo, "accept_and_claim", boom)
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="f1"), headers=AGENT)
    assert r.status_code == 201 and r.json()["state"] == "awaiting_approval"
    assert client.get("/v1/approval-policies", headers=OWNER).json()[0]["uses_24h"] == 0  # the use came back


def test_window_bound_policy_and_revision_bump(client, clock):
    install(client, clock)
    pol = policy(client, clock, requested_by=("agent:hermes",), window_id="win_nightly").json()
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="w1"), headers=AGENT)
    assert r.json()["state"] == "awaiting_approval"  # 22:00 UTC: nightly is 02:00-05:00
    client.post(f"/v1/actions/{r.json()['id']}/deny", headers=OWNER)
    w = client.put("/v1/windows/win_nightly", headers=OWNER,
                   json={"name": "nightly", "tz": "UTC", "ranges": [{"start": "21:00", "end": "23:00"}]})
    assert w.status_code == 200 and w.json()["open_now"] is True
    assert client.put("/v1/windows/win_nightly", headers=AGENT, json={"name": "x", "ranges": []}).status_code == 403
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="w2"), headers=AGENT)
    assert r.json()["decided_by"]["id"] == f"policy:{pol['id']}@2"


def test_f6_patch_updates_of_verified_apps_inside_the_window(client, clock, auto_settings):
    path = auto_settings.apps_dir / "whoami" / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"]["tier"] = "verified"
    path.write_text(yaml.safe_dump(doc))
    s = svc(client)
    s.policies.installed_version = lambda app_id: "1.10.1"
    assert policy(client, clock, types=("app.update",), requested_by=("automation:*",),
                  window_id="win_nightly").status_code == 201
    who = {"id": "automation:rule_x", "kind": "automation"}
    night = datetime(2026, 11, 12, 3, 0, tzinfo=UTC)
    ev = s.policies.evaluate
    assert ev("app.update", {"app_id": "whoami", "to_version": "1.10.2"}, who, night, paused=False).outcome == "auto_approved"
    assert ev("app.update", {"app_id": "whoami", "to_version": "1.11.0"}, who, night, paused=False).reason == "not_a_patch_update"
    assert ev("app.update", {"app_id": "whoami", "to_version": "1.10.2"}, who, clock.now, paused=False).reason == "outside_window"
    assert ev("app.update", {"app_id": "uptime-kuma", "to_version": "2.0.3"}, who, night, paused=False).reason == "app_not_verified"
    assert ev("app.update", {"app_id": "whoami", "to_version": "1.10.2"}, who, night, paused=True).reason == "automation_paused"


# ---- event rules ---------------------------------------------------------------------------------
def event_rule(client, **options):
    body = {**remove_rule({"event": {"type": "app.unhealthy", "where": {"resource.kind": "app"}}}, **options),
            "actions": [{"type": "app.remove", "params": {"app_id": "${event.resource.id}"}}]}
    rule = create_rule(client, body)
    enable(client, rule["id"])
    return rule


def test_event_rule_with_standing_approval_runs_and_is_audited(client, clock, executor):
    install(client, clock)
    rule = event_rule(client)
    pol = policy(client, clock, params={"app_id": {"enum": ["whoami"]}}).json()
    unhealthy(client, "whoami")
    fired = svc(client).process_events()
    assert fired[0]["outcome"] == "requested"
    a = client.get(f"/v1/actions/{fired[0]['action_ids'][0]}", headers=OWNER).json()
    assert a["state"] == "succeeded" and a["decided_by"]["id"] == f"policy:{pol['id']}@1"
    assert ("app.remove", "whoami") in executor.calls
    events = [e["event"] for e in audit_events(client)]
    assert "automation.fired" in events and "action.approved" in events
    ok, _, msg = verify(client.app.state.settings.audit_path)
    assert ok, msg
    # Loop guard: an event that belongs to the rule's own action does not fire it again.
    unhealthy(client, "whoami", action_id=a["id"])
    assert svc(client).process_events()[0]["outcome"] == "skipped_loop"
    assert client.get("/v1/automation/runs", params={"rule_id": rule["id"]}, headers=OWNER).json()[0]["outcome"] == "skipped_loop"


def test_event_debounce(client, clock):
    install(client, clock)
    event_rule(client, debounce_s=300)
    for _ in range(5):
        unhealthy(client, "whoami")
    outcomes = [f["outcome"] for f in svc(client).process_events()]
    # 5 events, 1 request: the rest wait on the open request or the 300 s debounce.
    assert outcomes[0] == "requested" and set(outcomes[1:]) <= {"skipped_concurrency", "skipped_debounce"}


def test_template_error_files_nothing(client, clock):
    event_rule(client)
    before = len(client.get("/v1/actions", headers=OWNER).json())
    client.app.state.gateway.events.publish_event("app", "unhealthy", {}, resource={"kind": "app", "id": "a/b"})
    fired = svc(client).process_events()
    assert fired[0]["outcome"] == "template_error" and fired[0]["action_ids"] == []
    assert len(client.get("/v1/actions", headers=OWNER).json()) == before


def test_breaker_opens_after_three_failures(client, clock, executor):
    install(client, clock)
    executor.outcome = "failed"  # every remove fails; the app ends up "failed", which may be removed again
    rule = event_rule(client)
    policy(client, clock, per_day=10)
    for _ in range(3):
        unhealthy(client, "whoami")
        svc(client).process_events()
    svc(client).tick()
    r = client.get(f"/v1/automation/rules/{rule['id']}", headers=OWNER).json()
    assert r["breaker"] == "open" and r["enabled"] is False and r["failures"] == 3
    assert any(e["event"] == "automation.breaker.opened" for e in audit_events(client))
    unhealthy(client, "whoami")
    assert svc(client).process_events() == []  # no 4th fire


# ---- kill switch and dry run ---------------------------------------------------------------------
def test_kill_switch_stops_rules_and_standing_approvals(client, clock):
    install(client, clock)
    event_rule(client)
    policy(client, clock, requested_by=("agent:hermes",))
    assert client.post("/v1/automation/pause", json={}, headers=AGENT).status_code == 403
    r = client.post("/v1/automation/pause", json={"reason": "investigating"}, headers=OWNER)
    assert r.json()["paused"] is True and r.json()["reason"] == "investigating"
    unhealthy(client, "whoami")
    assert svc(client).process_events() == []
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="k1"), headers=AGENT)
    assert r.json()["state"] == "awaiting_approval"
    client.post(f"/v1/actions/{r.json()['id']}/deny", headers=OWNER)
    assert client.post("/v1/automation/resume", headers=OWNER).json()["paused"] is False
    assert client.get("/v1/automation/state", headers=GUEST).json()["paused"] is False
    r = client.post("/v1/actions", json=action_body(clock, "whoami", "app.remove", key="k2"), headers=AGENT)
    assert r.json()["state"] == "succeeded"


def test_dry_run_shows_verdicts_and_limits_without_side_effects(client, clock):
    install(client, clock)
    rule = create_rule(client, remove_rule({"schedule": {"cron": "0 * * * *"}}))
    pol = policy(client, clock, per_day=2).json()
    before = client.get("/v1/actions", headers=OWNER).json()
    r = client.post(f"/v1/automation/rules/{rule['id']}/dry-run", headers=OWNER,
                    json={"from": iso(clock.now), "to": iso(clock.now + timedelta(hours=3))})
    d = r.json()
    assert [w["verdict"] for w in d["would_request"]] == ["auto_approved", "auto_approved", "needs_approval"]
    assert d["would_request"][0]["policy"] == f"policy:{pol['id']}@1"
    assert d["would_request"][2]["reason"] == "limit_reached" and d["would_request"][2]["uses"] == "2/2"
    assert d["policy_outcome"] == "needs_approval"
    assert client.get("/v1/actions", headers=OWNER).json() == before
    assert client.get("/v1/approval-policies", headers=OWNER).json()[0]["uses_24h"] == 0
    bad = client.post(f"/v1/automation/rules/{rule['id']}/dry-run", headers=OWNER,
                      json={"from": iso(clock.now), "to": iso(clock.now + timedelta(days=40))})
    assert bad.status_code == 422


def test_event_dry_run_replays_seen_events_and_samples(client, clock):
    rule = create_rule(client, {**remove_rule({"event": {"type": "app.*"}}, debounce_s=300),
                                "actions": [{"type": "app.remove", "params": {"app_id": "${event.resource.id}"}}]})
    for _ in range(4):
        unhealthy(client, "whoami")
    unhealthy(client, "bad/x")
    d = client.post(f"/v1/automation/rules/{rule['id']}/dry-run", json={}, headers=OWNER).json()
    assert d["source"] == "events_seen_since_start"
    assert [w["verdict"] for w in d["would_request"]] == ["needs_approval", "template_error"]
    assert [s["reason"] for s in d["skipped"]] == ["skipped_debounce"] * 3
    sample = {"id": "evt_s", "type": "app.unhealthy", "resource": {"kind": "app", "id": "uptime-kuma"}}
    d = client.post(f"/v1/automation/rules/{rule['id']}/dry-run", json={"sample_event": sample}, headers=OWNER).json()
    assert d["would_request"][0]["params"] == {"app_id": "uptime-kuma"}
    assert any(e["event"] == "automation.dry_run" for e in audit_events(client))


def test_routes_are_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/v1/automation/rules", "/v1/automation/rules/{rule_id}/dry-run", "/v1/automation/runs",
              "/v1/automation/schedules", "/v1/automation/pause", "/v1/approval-policies", "/v1/windows"):
        assert p in paths
    assert client.get("/v1/windows", headers=GUEST).json()[0]["id"] == "win_nightly"


def test_limit_counter_holds_under_concurrent_requests(client, clock):
    pol = policy(client, clock, per_day=3).json()
    repo = svc(client).repo
    results: list[str] = []

    def take(i: int) -> None:
        results.append(repo.reserve_use(pol["id"], 1, 3, f"act-{i}", clock.now)[0])

    threads = [threading.Thread(target=take, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 3 and results.count("limit") == 9


def test_background_worker_handles_events(auto_settings, clock, executor):
    s = replace(auto_settings, sections={"automation": AutomationSettings(enabled=True, tick_s=300)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        install(c, clock)
        event_rule(c)
        unhealthy(c, "whoami")
        deadline = time.monotonic() + 5
        runs: list = []
        while time.monotonic() < deadline and (not runs or runs[0]["outcome"] == "requesting"):
            time.sleep(0.05)
            runs = c.get("/v1/automation/runs", headers=OWNER).json()
        assert runs[0]["outcome"] == "requested"
