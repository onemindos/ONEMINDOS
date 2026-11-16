# SPDX-License-Identifier: Apache-2.0
"""UMB-P07 (#144): /v1/me/home is one document per person, kept on the hub."""
import json

from fastapi.testclient import TestClient

from conftest import ADULT, AGENT, OWNER
from onemind_core.app import create_app

PATH = "/v1/me/home"


def put(client, headers, body, etag):
    return client.put(PATH, headers={**headers, "If-Match": etag}, json=body)


def test_defaults_then_save_survives_restart(client, settings, clock):
    first = client.get(PATH, headers=ADULT)
    assert first.status_code == 200
    doc = first.json()
    assert doc["layout"] == "desktop" and doc["appearance"]["theme"] == "system" and doc["updated_at"] is None
    assert first.headers["etag"].startswith('"') and first.headers["cache-control"] == "no-store"

    doc["appearance"].update(theme="dark", wallpaper="om-dusk-02", density="compact")
    saved = put(client, ADULT, doc, first.headers["etag"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["appearance"]["theme"] == "dark" and saved.json()["updated_at"]
    assert saved.headers["etag"] != first.headers["etag"]

    # A "new browser" (new client) and a restarted gateway both see it: nothing lives in a browser.
    with TestClient(create_app(settings, clock=clock)) as restarted:
        again = restarted.get(PATH, headers=ADULT).json()
        assert again["appearance"] == saved.json()["appearance"]


def test_if_match_is_required_and_checked(client):
    etag = client.get(PATH, headers=ADULT).headers["etag"]
    body = client.get(PATH, headers=ADULT).json()
    missing = client.put(PATH, headers=ADULT, json=body)
    assert missing.status_code == 428 and missing.json()["reason"] == "precondition_required"
    stale = put(client, ADULT, body, '"0000"')
    assert stale.status_code == 412 and stale.json()["error"] == "stale_precondition"
    body["appearance"]["theme"] = "dark"
    assert put(client, ADULT, body, etag).status_code == 200
    # The same ETag again is now stale: the second writer must read first.
    body["appearance"]["theme"] = "light"
    assert put(client, ADULT, body, etag).status_code == 412


def test_each_person_has_their_own(client):
    adult = client.get(PATH, headers=ADULT)
    body = adult.json()
    body["appearance"]["theme"] = "dark"
    assert put(client, ADULT, body, adult.headers["etag"]).status_code == 200
    assert client.get(PATH, headers=OWNER).json()["appearance"]["theme"] == "system"


def test_agents_have_no_home(client):
    assert client.get(PATH, headers=AGENT).status_code == 403
    assert client.get(PATH).status_code == 401


def test_owner_dock_always_starts_with_approvals(client):
    got = client.get(PATH, headers=OWNER)
    body = got.json()
    assert body["dock"][0] == "sys:approvals"
    body["dock"] = ["sys:apps", "sys:settings"]
    saved = put(client, OWNER, body, got.headers["etag"])
    assert saved.json()["dock"] == ["sys:approvals", "sys:apps", "sys:settings"]
    adult = client.get(PATH, headers=ADULT).json()
    assert adult["dock"] == []  # only owners get Approvals forced


def test_unknown_app_is_refused_and_limits_hold(client):
    got = client.get(PATH, headers=ADULT)
    etag = got.headers["etag"]
    base = got.json()
    bad = put(client, ADULT, {**base, "dock": ["app:no-such-app"]}, etag)
    assert bad.status_code == 422 and bad.json()["reason"] == "unknown_item"
    assert put(client, ADULT, {**base, "dock": [f"sys:s{i}" for i in range(9)]}, etag).status_code == 422
    assert put(client, ADULT, {**base, "widgets": [{"id": f"sys:w{i}"} for i in range(7)]}, etag).status_code == 422
    assert put(client, ADULT, {**base, "dock": ["javascript:alert(1)"]}, etag).status_code == 422
    assert put(client, ADULT, {**base, "shortcuts": []}, etag).status_code == 422  # not supported yet
    assert put(client, ADULT, {**base, "appearance": {**base["appearance"], "wallpaper": "../x"}}, etag).status_code == 422


def test_a_real_app_can_be_pinned(client):
    got = client.get(PATH, headers=ADULT)
    ids = [a["id"] for a in client.get("/v1/apps", headers=ADULT).json()]
    assert ids
    body = {**got.json(), "dock": [f"app:{ids[0]}"]}
    saved = put(client, ADULT, body, got.headers["etag"])
    assert saved.status_code == 200 and saved.json()["dock"] == [f"app:{ids[0]}"]


def test_write_is_audited_with_field_names_only(client, settings):
    got = client.get(PATH, headers=ADULT)
    body = got.json()
    body["appearance"]["wallpaper"] = "om-secret-name"
    assert put(client, ADULT, body, got.headers["etag"]).status_code == 200
    records = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    event = next(e for e in records if e["event"] == "home.updated")
    assert event["principal"]["id"] == "adult" and event["data"] == {"changed": ["appearance"]}
    assert "om-secret-name" not in settings.audit_path.read_text()
