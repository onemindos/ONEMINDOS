# SPDX-License-Identifier: Apache-2.0
"""files-webdav (#722), part 1: per-person app passwords for WebDAV clients.

Real gateway, real routes, real ledger. The WebDAV tree that takes these passwords is the next PR
on #722 (core/onemind_core/files/webdav.py); here: who may make, see and revoke one, that the secret
is shown once and stored only as a hash, and that the check every WebDAV request makes is live
(a revoked password fails on the next lookup, a gateway token is never a password).
"""

from __future__ import annotations

import pytest

from conftest import ADULT, AGENT, GUEST, OWNER
from files_support import audit_events
from onemind_core.files.apppasswords import PASSWORD_RE, digest

PW = "/v1/files/app-passwords"


def new_password(client, headers=ADULT, scopes=("home:rw", "shared:r"), label="MacBook Finder") -> dict:
    r = client.post(PW, headers=headers, json={"label": label, "scopes": list(scopes)})
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == "no-store"
    return r.json()


def test_a_person_makes_lists_and_revokes_their_own(client):
    cred = new_password(client)
    assert cred["username"] == "adult" and cred["shown_once"] is True and PASSWORD_RE.match(cred["password"])
    assert cred["scopes"] == ["home:rw", "shared:r"] and cred["id"].startswith("apw_")
    listed = client.get(PW, headers=ADULT).json()["app_passwords"]
    assert [p["id"] for p in listed] == [cred["id"]]
    assert "password" not in listed[0] and cred["password"] not in str(listed)
    assert client.post(f"{PW}/{cred['id']}/revoke", headers=ADULT).json() == {"revoked": True, "id": cred["id"]}
    assert client.get(PW, headers=ADULT).json()["app_passwords"] == []
    assert client.post(f"{PW}/{cred['id']}/revoke", headers=ADULT).status_code == 404


def test_the_secret_is_kept_only_as_a_hash_and_never_audited(client, settings):
    cred = new_password(client)
    (row,) = client.app.state.app_passwords.repo.all()
    assert row.secret_sha256 == digest(cred["password"])
    events = [e for e in audit_events(settings) if e["event"].startswith("webdav.app_password.")]
    assert [e["event"] for e in events] == ["webdav.app_password.created"]
    assert cred["password"] not in settings.audit_path.read_text()


def test_the_owner_sees_and_revokes_everyones_and_an_adult_only_their_own(client):
    mine = new_password(client, OWNER, label="owner laptop")
    theirs = new_password(client, ADULT)
    assert {p["id"] for p in client.get(PW, headers=OWNER).json()["app_passwords"]} == {mine["id"], theirs["id"]}
    assert [p["id"] for p in client.get(PW, headers=ADULT).json()["app_passwords"]] == [theirs["id"]]
    assert client.post(f"{PW}/{mine['id']}/revoke", headers=ADULT).status_code == 404  # not even told it exists
    assert client.post(f"{PW}/{theirs['id']}/revoke", headers=OWNER).status_code == 200


@pytest.mark.parametrize("headers", [GUEST, AGENT])
def test_guests_and_agents_get_none(client, headers):
    assert client.post(PW, headers=headers, json={"label": "x", "scopes": ["shared:r"]}).status_code == 403
    assert client.get(PW, headers=headers).status_code == 403


@pytest.mark.parametrize("scopes", [[], ["home:rw", "home:r"], ["photos:r"], ["home:x"], ["home:r", "shared:r", "home:rw"]])
def test_scopes_must_name_each_space_once(client, scopes):
    r = client.post(PW, headers=ADULT, json={"label": "x", "scopes": scopes})
    assert r.status_code == 422, r.text


def test_the_live_check_refuses_revoked_passwords_other_users_and_gateway_tokens(client):
    passwords = client.app.state.app_passwords
    cred = new_password(client)
    assert passwords.check("adult", cred["password"]).id == cred["id"]
    assert passwords.check("owner", cred["password"]) is None  # a password works only with its own user name
    assert passwords.check("owner", OWNER["Authorization"].split(" ", 1)[1]) is None
    client.post(f"{PW}/{cred['id']}/revoke", headers=ADULT)
    assert passwords.check("adult", cred["password"]) is None  # no cache: the next lookup fails


def test_a_person_holds_at_most_twenty(client):
    for i in range(20):
        new_password(client, label=f"device {i}")
    r = client.post(PW, headers=ADULT, json={"label": "one more", "scopes": ["home:r"]})
    assert r.status_code == 409 and r.json()["reason"] == "too_many_app_passwords"
