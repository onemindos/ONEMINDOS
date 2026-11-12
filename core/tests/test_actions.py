"""Contract §3 actions: request, idempotency, approve/deny, expiry, executor outcomes, denials."""

import threading

import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, GUEST, OWNER, ScriptedExecutor, action_body
from onemind_core.app import create_app


def create(client, clock, headers=OWNER, **kw):
    return client.post("/v1/actions", json=action_body(clock, **kw), headers=headers)


# ---- POST /v1/actions -----------------------------------------------------------------

@pytest.mark.parametrize("headers,kind", [(OWNER, "person"), (AGENT, "agent")])
def test_owner_and_agent_can_request(client, clock, headers, kind):
    r = create(client, clock, headers=headers)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["state"] == "awaiting_approval"
    assert a["type"] == "app.install"
    assert a["params"] == {"app_id": "uptime-kuma"}
    assert a["requested_by"]["kind"] == kind
    assert a["expires_at"].endswith("Z")


@pytest.mark.parametrize("headers", [ADULT, GUEST])
def test_adult_and_guest_cannot_request(client, clock, headers):
    r = create(client, clock, headers=headers)
    assert r.status_code == 403
    assert r.json()["error"] == "permission_denied"


def test_same_idempotency_key_returns_same_action_200(client, clock):
    first = create(client, clock)
    again = create(client, clock)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    assert len(client.get("/v1/actions", headers=OWNER).json()) == 1


def test_idempotency_key_reuse_with_other_body_is_conflict(client, clock):
    assert create(client, clock).status_code == 201
    r = create(client, clock, app_id="whoami")
    assert r.status_code == 409 and r.json()["error"] == "conflict"


def test_idempotency_key_reuse_by_other_principal_is_conflict(client, clock):
    assert create(client, clock).status_code == 201
    r = create(client, clock, headers=AGENT)
    assert r.status_code == 409 and r.json()["error"] == "conflict"


def test_unknown_app_is_404(client, clock):
    r = create(client, clock, app_id="no-such-app")
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_expires_at_in_past_is_409_expired(client, clock):
    r = create(client, clock, ttl=-1)
    assert r.status_code == 409 and r.json()["error"] == "expired"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(type="app.delete_everything"),
        lambda b: b.update(params={"app_id": "../etc"}),
        lambda b: b.update(params={"app_id": "uptime-kuma", "extra": 1}),
        lambda b: b.pop("idempotency_key"),
        lambda b: b.pop("expires_at"),
        lambda b: b.update(expires_at="2026-11-11T22:10:00"),  # no timezone
    ],
)
def test_malformed_request_is_422(client, clock, mutate):
    body = action_body(clock)
    mutate(body)
    r = client.post("/v1/actions", json=body, headers=OWNER)
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_request"


def test_remove_of_not_installed_app_is_stale_precondition(client, clock):
    r = create(client, clock, type_="app.remove")
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"


# ---- GET ------------------------------------------------------------------------------

@pytest.mark.parametrize("headers", [OWNER, ADULT, GUEST, AGENT])
def test_any_principal_can_read_actions(client, clock, headers):
    aid = create(client, clock).json()["id"]
    assert client.get("/v1/actions", headers=headers).status_code == 200
    r = client.get(f"/v1/actions/{aid}", headers=headers)
    assert r.status_code == 200 and r.json()["id"] == aid


def test_get_unknown_action_404(client):
    r = client.get("/v1/actions/does-not-exist", headers=OWNER)
    assert r.status_code == 404 and r.json()["error"] == "not_found"


# ---- approve --------------------------------------------------------------------------

def test_owner_approve_runs_executor_and_succeeds(client, clock, executor):
    aid = create(client, clock, headers=AGENT).json()["id"]
    assert executor.calls == []  # nothing actuates before approval
    r = client.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["state"] == "succeeded"
    assert a["decided_by"]["id"] == "owner"
    assert executor.calls == [("app.install", "uptime-kuma")]
    apps = {x["id"]: x for x in client.get("/v1/apps", headers=OWNER).json()}
    assert apps["uptime-kuma"]["installed"] is True
    assert apps["uptime-kuma"]["status"] == "installed"


def test_agent_approve_is_403_permission_denied_and_nothing_runs(client, clock, executor):
    aid = create(client, clock, headers=AGENT).json()["id"]
    r = client.post(f"/v1/actions/{aid}/approve", headers=AGENT)
    assert r.status_code == 403
    assert r.json()["error"] == "permission_denied"
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "awaiting_approval"
    assert executor.calls == []


@pytest.mark.parametrize("headers", [ADULT, GUEST, AGENT])
def test_non_owner_cannot_approve_or_deny(client, clock, executor, headers):
    aid = create(client, clock).json()["id"]
    for verb in ("approve", "deny"):
        r = client.post(f"/v1/actions/{aid}/{verb}", headers=headers)
        assert r.status_code == 403 and r.json()["error"] == "permission_denied"
    assert executor.calls == []


def test_approve_after_expiry_is_409_expired(client, clock, executor):
    aid = create(client, clock, ttl=60).json()["id"]
    clock.advance(61)
    r = client.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "expired"
    assert client.get(f"/v1/actions/{aid}", headers=OWNER).json()["state"] == "expired"
    assert executor.calls == []


def test_listing_marks_overdue_actions_expired(client, clock):
    create(client, clock, ttl=60)
    clock.advance(120)
    states = [a["state"] for a in client.get("/v1/actions", headers=OWNER).json()]
    assert states == ["expired"]


def test_approve_twice_is_conflict(client, clock, executor):
    aid = create(client, clock).json()["id"]
    assert client.post(f"/v1/actions/{aid}/approve", headers=OWNER).status_code == 200
    r = client.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "conflict"
    assert len(executor.calls) == 1


def test_approve_unknown_action_404(client):
    r = client.post("/v1/actions/nope/approve", headers=OWNER)
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_executor_failure_marks_failed(settings, clock):
    ex = ScriptedExecutor("failed")
    with TestClient(create_app(settings, clock=clock, executor=ex)) as c:
        aid = create(c, clock).json()["id"]
        a = c.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()
        assert a["state"] == "failed"
        assert a["result"]["outcome"] == "failed"
        app = {x["id"]: x for x in c.get("/v1/apps", headers=OWNER).json()}["uptime-kuma"]
        assert app["status"] == "failed" and app["installed"] is False


@pytest.mark.parametrize("ex", [ScriptedExecutor("outcome_unknown"), ScriptedExecutor(raise_exc=True)])
def test_executor_timeout_or_crash_is_outcome_unknown(settings, clock, ex):
    with TestClient(create_app(settings, clock=clock, executor=ex)) as c:
        aid = create(c, clock).json()["id"]
        a = c.post(f"/v1/actions/{aid}/approve", headers=OWNER).json()
        assert a["state"] == "outcome_unknown"
        # no automatic re-dispatch
        r = c.post(f"/v1/actions/{aid}/approve", headers=OWNER)
        assert r.status_code == 409
        assert len(ex.calls) == 1


def test_stale_precondition_at_approval(client, clock, executor):
    first = create(client, clock, key="a").json()["id"]
    second = create(client, clock, key="b").json()["id"]
    assert client.post(f"/v1/actions/{first}/approve", headers=OWNER).json()["state"] == "succeeded"
    r = client.post(f"/v1/actions/{second}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "stale_precondition"
    a = client.get(f"/v1/actions/{second}", headers=OWNER).json()
    assert a["state"] == "failed" and a["result"]["error"] == "stale_precondition"
    assert len(executor.calls) == 1


def test_install_then_remove_round_trip(client, clock, executor):
    aid = create(client, clock, key="i").json()["id"]
    client.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    rid = create(client, clock, key="r", type_="app.remove").json()["id"]
    a = client.post(f"/v1/actions/{rid}/approve", headers=OWNER).json()
    assert a["state"] == "succeeded"
    app = {x["id"]: x for x in client.get("/v1/apps", headers=OWNER).json()}["uptime-kuma"]
    assert app["installed"] is False and app["status"] == "not_installed"
    assert executor.calls == [("app.install", "uptime-kuma"), ("app.remove", "uptime-kuma")]


def test_concurrent_approvals_dispatch_once(client, clock, executor):
    aid = create(client, clock).json()["id"]
    codes = []

    def go():
        codes.append(client.post(f"/v1/actions/{aid}/approve", headers=OWNER).status_code)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes).count(200) == 1
    assert set(codes) <= {200, 409}
    assert len(executor.calls) == 1


# ---- deny -----------------------------------------------------------------------------

def test_owner_deny_cancels(client, clock, executor):
    aid = create(client, clock, headers=AGENT).json()["id"]
    r = client.post(f"/v1/actions/{aid}/deny", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    r = client.post(f"/v1/actions/{aid}/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "conflict"
    assert executor.calls == []


def test_deny_after_expiry_is_expired(client, clock):
    aid = create(client, clock, ttl=10).json()["id"]
    clock.advance(11)
    r = client.post(f"/v1/actions/{aid}/deny", headers=OWNER)
    assert r.status_code == 409 and r.json()["error"] == "expired"


def test_deny_unknown_action_404(client):
    r = client.post("/v1/actions/nope/deny", headers=OWNER)
    assert r.status_code == 404
