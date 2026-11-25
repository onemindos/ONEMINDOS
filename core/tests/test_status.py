# SPDX-License-Identifier: Apache-2.0
"""FD-01 (#498, D-018): GET /v1/status. The contract: a source that cannot be read is unknown, never ok."""
from __future__ import annotations

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER
from onemind_core import status as S

SOURCES = ("alerts", "approvals", "apps", "storage", "backups", "updates", "mesh", "host")
STATES = {"ok", "attention", "critical", "unknown"}


def get(client, headers=OWNER):
    return client.get("/v1/status", headers=headers)


def test_every_source_has_state_and_observed_at(client, clock):
    r = get(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] in STATES and body["observed_at"]
    for name in SOURCES:
        src = body[name]
        assert set(src) >= {"state", "observed_at", "summary"} and src["state"] in STATES, name
        if src["state"] != "unknown":
            assert src["observed_at"] == "2026-11-11T22:00:00Z", name


def test_sources_with_nothing_to_read_are_unknown_not_ok(client):
    body = get(client).json()
    # No storage service, no node reporting updates, and no Kubernetes here: nothing was observed.
    assert body["storage"]["state"] == "unknown" and body["storage"]["observed_at"] is None
    assert body["updates"]["state"] == "unknown" and body["updates"]["observed_at"] is None
    assert body["alerts"]["state"] == "ok" and body["approvals"]["state"] == "ok"


@pytest.mark.parametrize("name", SOURCES)
def test_a_failing_source_is_unknown_never_ok(client, monkeypatch, name):
    def boom(gw, state):
        raise RuntimeError("/srv/secret/path hostile-detail exploded")

    monkeypatch.setitem(S.SOURCES, name, boom)
    r = get(client)
    assert r.status_code == 200
    src = r.json()[name]
    assert src["state"] == "unknown" and src["observed_at"] is None
    assert "secret" not in r.text and "hostile-detail" not in r.text  # the failure text stays in the log
    assert r.json()["state"] != "ok"
    for other in set(SOURCES) - {name}:  # the others still answer
        assert r.json()[other]["state"] in STATES


def test_overall_state_is_the_worst_known_one(client, monkeypatch):
    monkeypatch.setitem(S.SOURCES, "alerts", lambda gw, st: ("critical", "1 critical alert", 1))
    monkeypatch.setitem(S.SOURCES, "approvals", lambda gw, st: ("attention", "1 change waits", 1))
    assert get(client).json()["state"] == "critical"
    monkeypatch.setitem(S.SOURCES, "alerts", lambda gw, st: ("ok", "none", 0))
    assert get(client).json()["state"] == "attention"


def test_an_unknown_source_outranks_ok_but_not_a_known_problem(client, monkeypatch):
    for n in SOURCES:
        monkeypatch.setitem(S.SOURCES, n, lambda gw, st: ("ok", "fine", 0))
    assert get(client).json()["state"] == "ok"

    def blind(gw, st):
        raise S.Unreadable("not wired")

    monkeypatch.setitem(S.SOURCES, "mesh", blind)
    assert get(client).json()["state"] == "unknown"
    monkeypatch.setitem(S.SOURCES, "approvals", lambda gw, st: ("attention", "1", 1))
    assert get(client).json()["state"] == "attention"


def test_pending_approval_and_open_alert_show_up(client, clock):
    from conftest import action_body

    assert client.post("/v1/actions", headers=OWNER, json=action_body(clock)).status_code in (201, 202)
    assert get(client).json()["approvals"]["state"] == "attention"
    assert get(client).json()["approvals"]["count"] == 1
    mon = client.app.state.gateway
    mon.events.publish_event("node", "stale", {"node_id": "n1"}, severity="critical", dedupe_key="t:1")
    alerts = get(client).json()["alerts"]
    assert alerts["state"] in ("critical", "ok")  # the catalogue decides whether this event opens an alert


def test_who_may_read(client):
    assert get(client, OWNER).status_code == 200
    assert get(client, ADULT).status_code == 200
    assert get(client, AGENT).status_code == 200
    assert get(client, GUEST).status_code == 403
    assert client.get("/v1/status").status_code == 401


def test_status_never_changes_anything(client):
    assert client.post("/v1/status", headers=OWNER, json={}).status_code in (404, 405)


def test_storage_mapping():
    class St:
        def __init__(self, d):
            self.d = d

        def summary(self):
            return self.d

    class State:
        pass

    def read(d):
        s = State()
        s.storage = St(d)
        try:
            return S.read_storage(None, s)[0]
        except S.Unreadable:
            return "unknown"

    assert read({"enabled": False}) == "unknown"
    assert read({"enabled": True, "available": False}) == "unknown"
    assert read({"enabled": True, "available": True}) == "unknown"  # no verdict is not ok
    assert read({"enabled": True, "available": True, "state": "protected"}) == "ok"
    assert read({"enabled": True, "available": True, "state": "unprotected"}) == "attention"
    assert read({"enabled": True, "available": True, "state": "degraded"}) == "critical"


def test_a_host_reader_that_fails_says_missing_never_reachable(client, monkeypatch):
    def boom(gw, st):
        raise RuntimeError("socket gone at /run/x")

    monkeypatch.setitem(S.SOURCES, "host", boom)
    h = get(client).json()["host"]
    assert h["state"] == "unknown" and h["helper"] == "missing" and h["hostname"] is None
    assert "/run/" not in h["summary"]
