"""Gateway permissions design PR 3 (gaps 3 and 9, review item 15).

The standing-approval rules list is the owner's: an agent that could read it could shape requests to fit a rule.
A request nobody decides must not wait for ever: 72 hours for software that asks, 7 days for a person.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from conftest import AGENT, GUEST, OWNER, action_body


def audit_events(client) -> list[dict]:
    return [json.loads(line) for line in client.app.state.settings.audit_path.read_text().splitlines()]


def test_only_the_owner_reads_the_rules_list(client):
    assert client.get("/v1/approval-policies", headers=OWNER).status_code == 200
    for headers in (AGENT, GUEST):
        r = client.get("/v1/approval-policies", headers=headers)
        assert r.status_code == 403, r.text
    denied = [e for e in audit_events(client) if e["event"] == "authz.denied"
              and e["data"].get("attempted") == "list standing approvals"]
    assert len(denied) == 2


def test_an_agent_request_may_wait_72_hours_and_not_longer(client, clock):
    ok = client.post("/v1/actions", json=action_body(clock, "whoami", key="a72", ttl=72 * 3600), headers=AGENT)
    assert ok.status_code == 201, ok.text
    r = client.post("/v1/actions", json=action_body(clock, "whoami", key="a73", ttl=72 * 3600 + 1), headers=AGENT)
    assert r.status_code == 422 and "72 hours" in r.json()["message"], r.text
    two_years = client.post("/v1/actions", json=action_body(clock, "whoami", key="a2y", ttl=2 * 365 * 86400), headers=AGENT)
    assert two_years.status_code == 422


def test_a_person_request_may_wait_7_days_and_not_longer(client, clock):
    ok = client.post("/v1/actions", json=action_body(clock, "whoami", key="p7", ttl=7 * 86400), headers=OWNER)
    assert ok.status_code == 201, ok.text
    r = client.post("/v1/actions", json=action_body(clock, "whoami", type_="app.install", key="p8", ttl=7 * 86400 + 1),
                    headers=OWNER)
    assert r.status_code == 422 and "7 days" in r.json()["message"], r.text


def test_the_limit_is_measured_from_now_not_from_filing(client, clock):
    r = client.post("/v1/actions", json=action_body(clock, "whoami", key="late", ttl=3600), headers=AGENT)
    assert r.status_code == 201
    clock.now += timedelta(hours=100)
    r = client.post("/v1/actions", json=action_body(clock, "whoami", key="late2", ttl=72 * 3600), headers=AGENT)
    assert r.status_code == 201, r.text
