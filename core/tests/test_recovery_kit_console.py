# SPDX-License-Identifier: Apache-2.0
"""Design 25c (gateway permissions design 3.13, path 2; D-028): recover owner access at the box with the kit.

The owner lost every passkey. At the box's own console they type the printed kit key; the console (onemindd
recover-owner) presents the console key on loopback. Tests 3.13 #2 and #9: the right key opens a 15-minute kit
session; wrong keys start a doubling lockout that deletes nothing; a network source is refused; the key is in no
log; a box without a kit answers 409; and nothing here removes a disk or backup key or approves anything.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from test_backups import bk, notes_app  # noqa: F401  (fixtures)
from test_identity import PASSWORD, SoftAuthenticator, id_settings, register_passkey, setup_owner

NEW_PASSWORD = "a brand new passphrase"


@pytest.fixture
def settings(settings):  # identity on, plain-HTTP cookies (as test_identity runs it)
    return id_settings(settings)


@pytest.fixture
def box(client, bk):
    """A box with a kit and an owner who has a passkey (then loses it). Returns (kit one_time, console client)."""
    one = client.post("/v1/backups/kit", headers=OWNER).json()["one_time"]  # before the install token retires
    setup_owner(client)
    register_passkey(client, SoftAuthenticator())
    console = TestClient(client.app, client=("127.0.0.1", 40000))
    console.headers["OneMind-Console"] = client.app.state.kit_recovery.key()
    return one, console


def unlock(console, one, **over):
    return console.post("/v1/auth/recovery/kit", json={"groups": one["groups"], "check": one["check"], **over})


def test_only_the_box_console_reaches_the_kit_routes(client, box):
    one, console = box
    body = {"groups": one["groups"], "check": one["check"]}
    key = console.headers["OneMind-Console"]
    net = client.post("/v1/auth/recovery/kit", json=body, headers={"OneMind-Console": key})
    assert net.status_code == 403 and net.json()["reason"] == "console_only", "a network source never gets in"
    local = TestClient(client.app, client=("127.0.0.1", 40001))
    assert local.post("/v1/auth/recovery/kit", json=body).status_code == 403, "loopback without the console key"
    proxied = console.post("/v1/auth/recovery/kit", json=body, headers={"X-Forwarded-For": "203.0.113.9"})
    assert proxied.status_code == 403, "a request a proxy forwarded is a network request"
    assert "/v1/auth/recovery/kit" not in json.dumps(client.get("/openapi.json").json()), "not in the API schema"


def test_the_right_kit_key_gives_owner_access_back(client, box, settings):
    one, console = box
    r = unlock(console, one)
    assert r.status_code == 200, r.text
    s = {"OneMind-Kit-Session": r.json()["session"]}
    owner = r.json()["owners"][0]
    assert owner["username"] == "zeus" and len(owner["passkeys"]) == 1
    # a new password signs out every session the old one opened
    assert console.post("/v1/auth/recovery/kit/password", headers=s,
                        json={"user_id": owner["user_id"], "password": NEW_PASSWORD}).status_code == 204
    assert client.get("/v1/me").status_code == 401, "the old session is gone"
    other = TestClient(client.app)
    assert other.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 401
    assert other.post("/v1/auth/login", json={"username": "zeus", "password": NEW_PASSWORD}).status_code == 200
    # the lost passkey is cut off, the authenticator code turned off
    cred = owner["passkeys"][0]["credential_id"]
    assert console.post("/v1/auth/recovery/kit/passkeys/remove", headers=s,
                        json={"user_id": owner["user_id"], "credential_id": cred}).status_code == 204
    assert console.post("/v1/auth/recovery/kit/authenticator/clear", headers=s,
                        json={"user_id": owner["user_id"]}).status_code == 204
    # a one-time code from the console signs a phone in to add a new passkey
    code = console.post("/v1/auth/recovery/kit/sign-in-code", headers=s, json={"user_id": owner["user_id"]}).json()["code"]
    phone = TestClient(client.app)
    got = phone.post("/v1/auth/recovery/kit/redeem", json={"code": code.lower()})
    assert got.status_code == 200, got.text
    assert phone.get("/v1/me").json()["session"]["auth_method"] == "kit"
    assert phone.post("/v1/auth/recovery/kit/redeem", json={"code": code}).status_code == 401, "single use"
    register_passkey(phone, SoftAuthenticator())
    register_passkey(phone, SoftAuthenticator())  # a second key too: no step-up with keys the owner no longer has
    # told, and the kit key is in no log
    audit = settings.audit_path.read_text()
    assert "auth.recovery.kit.unlocked" in audit and "auth.recovery.kit.password_set" in audit
    assert "-".join(one["groups"][:3]) not in audit and NEW_PASSWORD not in audit


def test_a_kit_session_can_do_nothing_else(client, box):
    one, console = box
    s = {"OneMind-Kit-Session": unlock(console, one).json()["session"]}
    for path in ("/v1/actions", "/v1/backups/kit", "/v1/users", "/v1/files/roots"):
        assert console.get(path, headers=s).status_code == 401, f"{path}: a kit session is not a sign-in"
    assert console.post("/v1/storage/recovery-key", headers=s).status_code == 401, "it never shows the disk key"
    assert console.post("/v1/actions/act_x/approve", headers=s, json={}).status_code == 401, "it never approves"
    assert console.post("/v1/auth/recovery/kit/password", json={"user_id": "x", "password": NEW_PASSWORD}).status_code == 401


def test_wrong_keys_wait_longer_each_time_and_delete_nothing(client, box, clock, bk):
    one, console = box
    wrong = list(reversed(one["groups"]))
    from onemind_core.backups.kit import new_owner_key

    other = new_owner_key()
    bad = {"groups": list(other.groups), "check": other.check}
    assert unlock(console, one, groups=wrong).status_code == 422, "a typo the check group catches is not a try"
    for _ in range(5):
        assert console.post("/v1/auth/recovery/kit", json=bad).status_code == 401
    locked = unlock(console, one)
    assert locked.status_code == 429 and 890 <= locked.json()["retry_after_s"] <= 901, "15 minutes, even for the right key"
    clock.advance(15 * 60 + 1)
    for _ in range(5):
        console.post("/v1/auth/recovery/kit", json=bad)
    assert 1790 <= unlock(console, one).json()["retry_after_s"] <= 1801, "then 30 minutes"
    for _ in range(10):  # many more lockouts: capped at 24 hours
        clock.advance(25 * 3600)
        for _ in range(5):
            console.post("/v1/auth/recovery/kit", json=bad)
    assert unlock(console, one).json()["retry_after_s"] <= 24 * 3600 + 1
    clock.advance(24 * 3600 + 1)
    assert unlock(console, one).status_code == 200, "the right key still works afterwards"
    # nothing was wiped: the owner, the passkey, the kit and its keys are all still there
    assert client.app.state.identity.active_owner_ids()
    assert client.app.state.backups.kit_state()["state"] == "issued"
    assert not [k for k, _, _ in bk.agent.jobs if k not in ("backup.key.add", "backup.configure")], \
        "no backup key was removed and nothing else ran"


def test_a_box_without_a_kit_says_so(client, bk):
    setup_owner(client)
    console = TestClient(client.app, client=("127.0.0.1", 40000))
    console.headers["OneMind-Console"] = client.app.state.kit_recovery.key()
    r = console.post("/v1/auth/recovery/kit", json={"groups": ["AAAA"] * 13, "check": "AAAA"})
    assert r.status_code == 409 and r.json()["reason"] == "no_kit"


def test_the_console_key_is_private_and_survives_a_restart(client, settings):
    path = settings.audit_path.parent / "console-recovery.key"
    key = client.app.state.kit_recovery.key()
    assert path.read_text().strip() == key and (path.stat().st_mode & 0o777) == 0o600
    from onemind_core.identity.kit_recovery import load_or_create_console_key

    assert load_or_create_console_key(path) == key
