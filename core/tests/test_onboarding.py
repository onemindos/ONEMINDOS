# SPDX-License-Identifier: Apache-2.0
"""Step 5 saves software preferences, never host settings or backup jobs."""
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
import json
import pytest
from onemind_core.auth import Principal
from onemind_core.backups.store import DestinationRow

PATH = "/v1/onboarding/settings"
BODY = {"box_name": "home-hub", "time_zone": "Europe/London", "backup_choice": "later"}


def test_owner_save_is_durable_and_audited(client, settings, clock):
    before = client.get(PATH, headers=OWNER)
    assert before.status_code == 200
    assert before.json()["saved"] is False
    saved = client.put(PATH, headers=OWNER, json=BODY)
    assert saved.status_code == 200
    expected = {**BODY, "backup_destination_id": None, "saved": True}
    assert saved.json() == expected
    assert saved.headers["cache-control"] == "no-store"
    with TestClient(create_app(settings, clock=clock)) as restarted:
        read = restarted.get(PATH, headers=OWNER)
        assert read.json() == expected
        assert read.headers["cache-control"] == "no-store"
        assert restarted.get("/v1/instance", headers=OWNER).json()["name"] == "home-hub"
    import json
    records = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    event = next(e for e in records if e["event"] == "onboarding.settings.saved")
    assert event["principal"]["role"] == "owner"
    assert event["data"] == BODY | {"backup_destination_id": None}


@pytest.mark.parametrize("patch", [
    {"box_name": "-bad"}, {"box_name": "UPPER"}, {"box_name": "a" * 64},
    {"box_name": ""}, {"time_zone": "../../etc/passwd"}, {"time_zone": "+03:00"},
    {"time_zone": "Mars/Olympus"}, {"backup_choice": "unknown"},
    {"backup_destination_id": "dst_0123456789abcdef"},
    {"backup_choice": "usb", "backup_destination_id": "dst_0123456789abcdef"},
    {"credentials": {"password": "must-not-be-audited"}},
])
def test_invalid_save_is_atomic(client, settings, patch):
    assert client.put(PATH, headers=OWNER, json=BODY).status_code == 200
    before = client.get(PATH, headers=OWNER).json()
    audit = settings.audit_path.read_text()
    assert client.put(PATH, headers=OWNER, json=BODY | patch).status_code == 422
    assert client.get(PATH, headers=OWNER).json() == before
    assert settings.audit_path.read_text() == audit


@pytest.mark.parametrize("kind,choice", [("usb", "usb"), ("box", "peer"), ("s3", "s3")])
def test_binds_actual_backup_service_destination_without_jobs(client, clock, kind, choice):
    svc = client.app.state.backups
    dest = "dst_0123456789abcdef"
    svc.repo.add_destination(DestinationRow(id=dest, kind=kind, label="Existing test destination",
        is_primary=True, append_only=True, config={}, created_at=clock.now))
    listed = client.get("/v1/backups/destinations", headers=OWNER).json()
    assert listed[0]["id"] == dest
    body = BODY | {"backup_choice": choice, "backup_destination_id": listed[0]["id"]}
    assert client.put(PATH, headers=OWNER, json=body).json() == body | {"saved": True}
    before = client.get(PATH, headers=OWNER).json()
    assert client.put(PATH, headers=OWNER, json=body | {"backup_choice": "later"}).status_code == 422
    wrong = "s3" if choice != "s3" else "usb"
    assert client.put(PATH, headers=OWNER, json=body | {"backup_choice": wrong}).status_code == 422
    assert client.get(PATH, headers=OWNER).json() == before
    assert svc.repo.runs() == []
    assert svc.repo.kit() is None
    assert svc.destinations() == listed


@pytest.mark.parametrize("kind,role", [("person", "adult"), ("person", "guest"),
    ("person", "child"), ("agent", "agent"), ("agent", "owner"), ("plugin", "owner")])
def test_nonowners_cannot_read_or_save_even_with_other_person_id(client, settings, kind, role):
    assert client.put(PATH, headers=OWNER, json=BODY).status_code == 200
    before = client.get(PATH, headers=OWNER).json()
    dependency = client.app.state.gateway.principal
    client.app.dependency_overrides[dependency] = lambda: Principal("other-person", kind, role)
    for method in ("GET", "PUT"):
        assert client.request(method, PATH, json=BODY).status_code == 403
    client.app.dependency_overrides.pop(dependency)
    assert client.get(PATH, headers=OWNER).json() == before
    events = [json.loads(x) for x in settings.audit_path.read_text().splitlines()]
    assert sum(e["event"] == "authz.denied" for e in events) == 2


def test_unauthenticated_is_refused(client):
    for method in ("GET", "PUT"):
        assert client.request(method, PATH, json=BODY).status_code == 401


def test_real_scoped_owner_token_cannot_read_or_save(settings, clock):
    from test_identity import id_settings, setup_owner, csrf
    with TestClient(create_app(id_settings(settings), clock=clock)) as c:
        setup_owner(c)
        token = c.post("/v1/tokens", headers=csrf(c), json={"name": "reader",
            "scopes": ["instance:read"]}).json()["one_time"]["token"]
        h = {"Authorization": "Bearer " + token}
        assert c.get("/v1/instance", headers=h).status_code == 200
        for method in ("GET", "PUT"):
            assert c.request(method, PATH, headers=h, json=BODY).status_code == 403
        assert c.get(PATH, headers=OWNER).json()["saved"] is False
