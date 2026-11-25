# SPDX-License-Identifier: Apache-2.0
"""NMD-07 (#132): update policy knobs for apps, one test per rule, and the dry run.

Cool-off after a release, same major only, back-off after repeated failures, "what would update
tonight", and the AI schedule. Runs on SQLite, and on PostgreSQL with ONEMIND_TEST_DB_URL.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.automation import AutomationSettings
from onemind_core.ledger import Action

from conftest import ADULT, AGENT, OWNER, action_body

NIGHT = datetime(2026, 11, 12, 2, 0, tzinfo=UTC)  # the next opening of win_nightly (02:00-05:00 UTC)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@pytest.fixture
def auto_settings(settings):
    return replace(settings, sections={"automation": AutomationSettings(enabled=False)})


@pytest.fixture
def client(auto_settings, clock, executor):
    with TestClient(create_app(auto_settings, clock=clock, executor=executor)) as c:
        yield c


def svc(client):
    return client.app.state.update_policy


def gw(client):
    return client.app.state.gateway


_keys = itertools.count()


def install(client, clock, app_id="whoami"):
    r = client.post("/v1/actions", json=action_body(clock, app_id, key=f"inst-{next(_keys)}"), headers=OWNER)
    r = client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER)
    assert r.json()["state"] == "succeeded", r.text


def offer(auto_settings, app_id="whoami", version="1.10.2", released: datetime | None = None, tier="verified"):
    """Make the catalog offer `version` of the app, released at `released`."""
    path = auto_settings.apps_dir / app_id / "onemind.app.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["metadata"]["version"] = version
    doc["metadata"]["tier"] = tier
    if released is not None:
        doc["metadata"]["upstream"] = {"release": f"v{version}", "released_at": iso(released)}
    path.write_text(yaml.safe_dump(doc))


def update_attempt(client, clock, state: str, app_id="whoami") -> None:
    """An app.update in the ledger that ended in `state` (the executor path is tested elsewhere)."""
    clock.now += timedelta(minutes=1)
    gw(client).repo.create(Action(
        id=str(uuid.uuid4()), type="app.update", params={"app_id": app_id}, state=state,
        requested_by={"id": "automation:update-policy", "kind": "automation"}, idempotency_key=f"upd-{next(_keys)}",
        created_at=clock.now, updated_at=clock.now, expires_at=clock.now + timedelta(hours=1)))


def put(client, headers=OWNER, **knobs):
    return client.put("/v1/update-policy", json=knobs, headers=headers)


# ---- the knobs -----------------------------------------------------------------------------------
def test_defaults_until_the_owner_changes_them(client):
    r = client.get("/v1/update-policy", headers=ADULT)
    assert r.status_code == 200
    body = r.json()
    assert body["customized"] is False
    assert (body["cool_off_hours"], body["same_major_only"], body["backoff_after_failures"]) == (48, True, 3)
    assert body["window_id"] == "win_nightly" and body["ai_schedule"]["enabled"] is False
    assert body["paused_apps"] == []


def test_only_the_owner_edits_and_bad_values_are_refused(client):
    assert put(client, ADULT, cool_off_hours=0).status_code == 403
    assert put(client, AGENT, cool_off_hours=0).status_code == 403
    assert put(client, cool_off_hours=-1).status_code == 422
    assert put(client, backoff_after_failures=0).status_code == 422
    assert put(client, window_id="win_nope").status_code == 422
    assert put(client, ai_schedule={"enabled": True, "off": [{"start": "25:00", "end": "07:00"}]}).status_code == 422
    assert put(client, ai_schedule={"enabled": True, "tz": "Mars/Base"}).status_code == 422
    r = put(client, cool_off_hours=12, same_major_only=False)
    assert r.status_code == 200, r.text
    assert r.json()["customized"] is True and r.json()["cool_off_hours"] == 12
    assert client.get("/v1/update-policy", headers=OWNER).json()["same_major_only"] is False


# ---- rule 1: cool-off after a release -------------------------------------------------------------
def test_cool_off_holds_a_fresh_release(client, auto_settings):
    released = NIGHT - timedelta(hours=10)
    offer(auto_settings, released=released)
    s = svc(client)
    assert s.hold("whoami", "1.10.1", "1.10.2", NIGHT) == ("cool_off", released + timedelta(hours=48))
    assert s.hold("whoami", "1.10.1", "1.10.2", released + timedelta(hours=48)) is None
    put(client, cool_off_hours=6)
    assert s.hold("whoami", "1.10.1", "1.10.2", NIGHT) is None


def test_cool_off_waits_for_a_person_when_the_release_date_is_unknown(client, auto_settings):
    offer(auto_settings)  # no upstream.released_at
    s = svc(client)
    assert s.hold("whoami", "1.10.1", "1.10.2", NIGHT) == ("release_time_unknown", None)
    # the date belongs to the catalog's version only, never to another one
    offer(auto_settings, released=NIGHT - timedelta(days=9))
    assert s.hold("whoami", "1.10.1", "1.10.3", NIGHT) == ("release_time_unknown", None)
    put(client, cool_off_hours=0)
    assert s.hold("whoami", "1.10.1", "1.10.3", NIGHT) is None


# ---- rule 2: same major only ----------------------------------------------------------------------
def test_same_major_only_holds_a_new_major(client, auto_settings):
    offer(auto_settings, version="2.0.0", released=NIGHT - timedelta(days=9))
    s = svc(client)
    assert s.hold("whoami", "1.10.1", "2.0.0", NIGHT) == ("major_update", None)
    assert s.hold("whoami", "1.10.1", "1.11.0", NIGHT) == ("release_time_unknown", None)  # minor: not this rule
    put(client, same_major_only=False)
    assert s.hold("whoami", "1.10.1", "2.0.0", NIGHT) is None


# ---- rule 3: back-off after repeated failures -----------------------------------------------------
def test_backoff_pauses_after_failures_in_a_row_until_the_owner_resumes(client, clock, auto_settings):
    offer(auto_settings, released=NIGHT - timedelta(days=9))
    install(client, clock)
    s = svc(client)
    update_attempt(client, clock, "failed")
    update_attempt(client, clock, "succeeded")  # a success resets the count
    update_attempt(client, clock, "failed")
    update_attempt(client, clock, "outcome_unknown")
    update_attempt(client, clock, "cancelled")  # never ran: does not count either way
    update_attempt(client, clock, "failed", app_id="uptime-kuma")  # another app
    assert s.failures("whoami") == 2
    assert s.hold("whoami", "1.10.1", "1.10.2", NIGHT) is None
    update_attempt(client, clock, "failed")
    assert s.hold("whoami", "1.10.1", "1.10.2", NIGHT) == ("paused_after_failures", None)
    assert client.get("/v1/update-policy", headers=OWNER).json()["paused_apps"] == [{"app_id": "whoami", "failures": 3}]
    assert client.post("/v1/update-policy/resume", json={"app_id": "whoami"}, headers=ADULT).status_code == 403
    r = client.post("/v1/update-policy/resume", json={"app_id": "whoami"}, headers=OWNER)
    assert r.status_code == 200 and r.json()["paused_apps"] == []
    assert s.hold("whoami", "1.10.1", "1.10.2", NIGHT) is None
    put(client, backoff_after_failures=1)
    update_attempt(client, clock, "failed")
    assert s.hold("whoami", "1.10.1", "1.10.2", NIGHT) == ("paused_after_failures", None)


# ---- the knobs hold standing approvals back, never the reverse ----------------------------------
def test_a_held_update_waits_for_a_person_even_with_a_standing_approval(client, clock, auto_settings):
    install(client, clock)
    offer(auto_settings, released=NIGHT - timedelta(hours=1))
    body = {"allow": {"types": ["app.update"], "requested_by": ["automation:update-policy"]}, "limits": {"per_day": 3},
            "window_id": "win_nightly", "expires_at": iso(clock.now + timedelta(days=30))}
    assert client.post("/v1/approval-policies", json=body, headers=OWNER).status_code == 201
    pol = client.app.state.automation.policies
    who = {"id": "automation:update-policy", "kind": "automation"}
    params = {"app_id": "whoami", "to_version": "1.10.2"}
    assert pol.evaluate("app.update", params, who, NIGHT, paused=False).reason == "cool_off"
    put(client, cool_off_hours=0)
    assert pol.evaluate("app.update", params, who, NIGHT, paused=False).outcome == "auto_approved"


# ---- rule 4: the dry run ----------------------------------------------------------------------------
def test_dry_run_says_what_would_update_tonight(client, clock, auto_settings):
    install(client, clock)
    offer(auto_settings, released=NIGHT - timedelta(days=9))
    r = client.get("/v1/update-policy/dry-run", headers=ADULT)
    assert r.status_code == 200
    d = r.json()
    assert d["window"] == {"id": "win_nightly", "name": "nightly", "open_now": False, "next_open_at": "2026-11-12T02:00:00Z"}
    assert d["at"] == "2026-11-12T02:00:00Z"
    [item] = d["apps"]
    assert item["app_id"] == "whoami" and (item["from_version"], item["to_version"], item["kind"]) == ("1.10.1", "1.10.2", "patch")
    assert (item["outcome"], item["reason"]) == ("needs_approval", "no_policy")  # nobody said yes in advance
    body = {"allow": {"types": ["app.update"], "requested_by": ["automation:update-policy"]}, "limits": {"per_day": 3},
            "window_id": "win_nightly", "expires_at": iso(clock.now + timedelta(days=30))}
    assert client.post("/v1/approval-policies", json=body, headers=OWNER).status_code == 201
    [item] = client.get("/v1/update-policy/dry-run", headers=OWNER).json()["apps"]
    assert item["outcome"] == "would_update"
    offer(auto_settings, released=NIGHT - timedelta(hours=1))
    [item] = client.get("/v1/update-policy/dry-run", headers=OWNER).json()["apps"]
    assert (item["outcome"], item["reason"], item["until"]) == ("held", "cool_off", "2026-11-14T01:00:00Z")
    offer(auto_settings, version="2.0.0", released=NIGHT - timedelta(days=9))
    [item] = client.get("/v1/update-policy/dry-run", headers=OWNER).json()["apps"]
    assert (item["outcome"], item["reason"], item["kind"]) == ("held", "major_update", "major")
    # the dry run files nothing
    assert all(a["type"] != "app.update" for a in client.get("/v1/actions", headers=OWNER).json())


def test_dry_run_lists_nothing_when_everything_is_current(client, clock):
    install(client, clock)
    assert client.get("/v1/update-policy/dry-run", headers=OWNER).json()["apps"] == []


# ---- rule 5: the AI schedule --------------------------------------------------------------------
def test_ai_schedule_says_when_the_ai_apps_are_off(client, clock):
    now = clock.now  # 22:00 UTC
    gw(client).repo.set_app_state("hermes-like", "installed", now)  # category ai
    gw(client).repo.set_app_state("whoami", "installed", now)  # not an AI app
    ai = client.get("/v1/update-policy/dry-run", headers=OWNER).json()["ai"]
    assert ai == {"enabled": False, "off_now": False, "next_change_at": None, "apps": ["hermes-like"]}
    r = put(client, ai_schedule={"enabled": True, "tz": "UTC", "off": [{"start": "21:00", "end": "23:00"}]})
    assert r.status_code == 200, r.text
    ai = client.get("/v1/update-policy/dry-run", headers=OWNER).json()["ai"]
    assert ai == {"enabled": True, "off_now": True, "next_change_at": "2026-11-11T23:00:00Z", "apps": ["hermes-like"]}
    put(client, ai_schedule={"enabled": True, "tz": "UTC", "off": [{"days": ["sat"], "start": "01:00", "end": "06:00"}]})
    ai = client.get("/v1/update-policy/dry-run", headers=OWNER).json()["ai"]
    assert ai["off_now"] is False and ai["next_change_at"] == "2026-11-14T01:00:00Z"  # 2026-11-14 is a Saturday
