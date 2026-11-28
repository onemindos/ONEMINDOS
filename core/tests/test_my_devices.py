# SPDX-License-Identifier: Apache-2.0
"""My devices (#715): GET /v1/me/devices joins a person's sessions, passkeys, approver keys and push
registrations per device; DELETE /v1/me/devices/{id} (Lost this device) revokes all of them in one
person-approved, idempotent step."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from conftest import AGENT, OWNER
from onemind_core.app import create_app
from onemind_core.identity import models as idm
from onemind_core.monitoring import MonitoringSettings
from onemind_core.notify import NotifySettings
from sec_world import ip
from test_identity import (
    LOCAL_PEER, PASSWORD, SoftAuthenticator, audit_events, csrf, enrol, id_settings, new_session_client, setup_owner,
)
from test_identity_levels import AttestedAuthenticator, add_key, grant, lvc, root  # noqa: F401 - pytest fixtures


@pytest.fixture
def hc(settings, clock, executor, tmp_path):
    s = id_settings(settings)
    s = replace(s, sections={**s.sections, "notify": NotifySettings(worker=False, dir=tmp_path / "keys"),
                             "monitoring": MonitoringSettings(enabled=False)})
    with TestClient(create_app(s, clock=clock, executor=executor), client=LOCAL_PEER) as c:
        yield c


OLD_PHONE, NEW_PHONE = "inst_old_phone_0001", "inst_new_phone_0002"  # what each app install makes for itself


def phone_login(hc: TestClient, name: str = "Pixel 9", username: str = "zeus",
                install_id: str | None = None) -> tuple[TestClient, dict]:
    """The phone app's sign-in: a bearer session with a refresh token, named after the phone."""
    phone = new_session_client(hc)
    extra = {"install_id": install_id} if install_id else {}
    r = phone.post("/v1/auth/login", json={"username": username, "password": PASSWORD, "client": "app",
                                           "client_name": name, **extra})
    assert r.status_code == 200, r.text
    return phone, r.json()


def bearer(body: dict) -> dict:
    return {"Authorization": "Bearer " + body["access_token"]}


def prove_this_device(c, *, headers=None, label="testclient", install_id=None):
    headers = headers if headers is not None else csrf(c)
    options = c.post("/v1/auth/passkeys/register/options", headers=headers)
    assert options.status_code == 200, options.text
    body = {"credential": SoftAuthenticator().register(options.json()), "label": label, "install_id": install_id}
    registered = c.post("/v1/auth/passkeys/register", headers=headers, json=body)
    assert registered.status_code == 201, registered.text


def add_push(c: TestClient, headers: dict, label: str = "Pixel 9", install_id: str | None = None) -> str:
    extra = {"install_id": install_id} if install_id else {}
    r = c.post("/v1/push/registrations", headers=headers,
               json={"platform": "unifiedpush", "endpoint": f"https://{ip(1, 1, 1, 1)}/push/phone", "label": label,
                     **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def devices(c: TestClient, headers: dict | None = None) -> list[dict]:
    r = c.get("/v1/me/devices", headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()["devices"]


def by_label(items: list[dict], label: str) -> dict:
    return next(d for d in items if d["label"] == label)


def test_list_joins_each_devices_credentials_by_its_name(hc):
    setup_owner(hc)  # hc is the owner's browser
    phone, body = phone_login(hc)
    push_id = add_push(phone, bearer(body))
    r = hc.get("/v1/me/devices")
    assert r.status_code == 200
    out = r.json()
    assert out["sources"] == {"sessions": True, "passkeys": True, "approver_keys": hasattr(idm, "ApproverKeyRow"),
                              "push": True, "mesh": False, "nats": False}
    pixel = by_label(out["devices"], "Pixel 9")
    assert pixel["kind"] == "phone" and pixel["current"] is False and pixel["last_seen_at"]
    assert {(c["source"], c["id"]) for c in pixel["credentials"]} == {("sessions", body["session"]["id"]), ("push", push_id)}
    browser = next(d for d in out["devices"] if d["current"])
    assert browser["kind"] == "browser" and browser["id"] != pixel["id"]
    assert devices(phone, bearer(body)) == [{**d, "current": d["id"] == pixel["id"]} for d in out["devices"]]  # same ids


def test_lost_device_revokes_refresh_token_and_push_and_is_idempotent(hc, settings):
    setup_owner(hc)
    phone, body = phone_login(hc)
    push_id = add_push(phone, bearer(body))
    pixel = by_label(devices(hc), "Pixel 9")
    r = hc.delete(f"/v1/me/devices/{pixel['id']}", headers=csrf(hc))
    assert r.status_code == 200, r.text
    assert r.json() == {"id": pixel["id"], "removed": True,
                        "revoked": {"sessions": 1, "passkeys": 0, "approver_keys": 0, "push": 1}}
    # Acceptance (#715): the old refresh token, the access token and the push registration all fail.
    assert phone.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
    assert phone.get("/v1/me", headers=bearer(body)).status_code == 401
    assert hc.app.state.notify.repo.get_device(push_id) is None
    assert hc.delete(f"/v1/push/registrations/{push_id}", headers=csrf(hc)).status_code == 404
    assert all(d["label"] != "Pixel 9" for d in devices(hc))
    # Again: nothing left to revoke, the same answer shape, still 200.
    again = hc.delete(f"/v1/me/devices/{pixel['id']}", headers=csrf(hc))
    assert again.status_code == 200 and again.json()["removed"] is False
    assert sum(again.json()["revoked"].values()) == 0
    removed = [e for e in audit_events(settings) if e.get("event") == "auth.device.removed"]
    assert len(removed) == 1 and removed[0]["data"]["payload"]["device_id"] == pixel["id"]


def test_lost_device_can_remove_a_sole_l1_passkey_from_a_password_session(hc):
    setup_owner(hc)
    phone, body = phone_login(hc)
    key = SoftAuthenticator()
    opts = phone.post("/v1/auth/passkeys/register/options", headers=bearer(body)).json()
    r = phone.post("/v1/auth/passkeys/register", headers=bearer(body),
                   json={"credential": key.register(opts), "label": "Pixel 9"})
    assert r.status_code == 201, r.text
    pixel = by_label(devices(hc), "Pixel 9")
    assert {c["source"] for c in pixel["credentials"]} == {"sessions", "passkeys"}
    assert hc.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    r = hc.delete(f"/v1/me/devices/{pixel['id']}", headers=csrf(hc))
    assert r.status_code == 200 and r.json()["revoked"]["passkeys"] == 1 and r.json()["revoked"]["sessions"] == 1
    assert phone.get("/v1/me", headers=bearer(body)).status_code == 401
    assert hc.get("/v1/me").status_code == 200
    login = new_session_client(hc).post("/v1/auth/login/options").json()
    assert new_session_client(hc).post(
        "/v1/auth/login", json={"passkey": key.assert_(login["publicKey"]["challenge"])}).status_code == 401


def test_lost_device_requires_l2_to_remove_all_proven_keys(lvc, root):
    setup_owner(lvc)
    first = AttestedAuthenticator(root)
    ids = [add_key(lvc, first, "Security keys")["credential_id"]]
    second = AttestedAuthenticator(root)
    ids.append(add_key(lvc, second, "Security keys",
                       grant(lvc, first, "auth.passkeys.register"))["credential_id"])
    device = by_label(devices(lvc), "Security keys")
    path = f"/v1/me/devices/{device['id']}"
    assert lvc.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    refused = lvc.delete(path, headers=csrf(lvc))
    assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required", refused.text
    (details,) = refused.json()["details"]
    assert details["step_up"]["required_level"] == "L2"
    assert len(lvc.get("/v1/auth/passkeys").json()) == 2
    proof = grant(lvc, first, "me.devices.remove", device["id"], {"passkeys": sorted(ids)})
    removed = lvc.delete(path, headers={**csrf(lvc), "OneMind-Step-Up": proof})
    assert removed.status_code == 200 and removed.json()["revoked"]["passkeys"] == 2, removed.text
    assert lvc.get("/v1/auth/passkeys").json() == []


def test_lost_device_cannot_remove_a_passwordless_accounts_last_sign_in_method(hc):
    setup_owner(hc)
    member = enrol(hc, "adult", "alex")
    key = SoftAuthenticator()
    opts = member.post("/v1/auth/passkeys/register/options", headers=csrf(member)).json()
    assert member.post("/v1/auth/passkeys/register", headers=csrf(member),
                       json={"credential": key.register(opts), "label": "Security key"}).status_code == 201
    svc = hc.app.state.identity
    uid = member.get("/v1/me").json()["principal"]["id"]
    svc.repo.update(idm.UserRow, [idm.UserRow.id == uid], {"password_hash": None})
    device = by_label(devices(member), "Security key")
    r = member.delete(f"/v1/me/devices/{device['id']}", headers=csrf(member))
    assert r.status_code == 409 and r.json()["reason"] == "last_sign_in_method", r.text
    assert len(member.get("/v1/auth/passkeys").json()) == 1


def test_an_old_and_a_new_phone_with_the_default_name_stay_two_devices(hc):
    """Upgrade day: both phones carry the default name. Each install's id keeps them apart, so the new
    phone can remove the old one, and removing the old one never signs the new one out."""
    setup_owner(hc)
    old, old_body = phone_login(hc, "Android phone", install_id=OLD_PHONE)
    old_push = add_push(old, bearer(old_body), "Android phone", OLD_PHONE)
    new, new_body = phone_login(hc, "Android phone", install_id=NEW_PHONE)
    new_push = add_push(new, bearer(new_body), "Android phone", NEW_PHONE)
    prove_this_device(new, headers=bearer(new_body), label="Android phone", install_id=NEW_PHONE)
    seen = [d for d in devices(new, bearer(new_body)) if d["label"] == "Android phone"]
    assert len(seen) == 2 and seen[0]["id"] != seen[1]["id"]
    lost = next(d for d in seen if not d["current"])  # the new phone sees the old one as not in use: Lost is offered
    assert {(c["source"], c["id"]) for c in lost["credentials"]} == {("sessions", old_body["session"]["id"]), ("push", old_push)}
    r = new.delete(f"/v1/me/devices/{lost['id']}", headers=bearer(new_body))
    assert r.status_code == 200, r.text
    assert r.json()["revoked"] == {"sessions": 1, "passkeys": 0, "approver_keys": 0, "push": 1}
    assert old.post("/v1/auth/refresh", json={"refresh_token": old_body["refresh_token"]}).status_code == 401
    assert new.get("/v1/me", headers=bearer(new_body)).status_code == 200  # the new phone is untouched
    assert hc.app.state.notify.repo.get_device(new_push) is not None


def test_a_renamed_phone_stays_one_device_and_lost_revokes_everything_it_holds(hc, clock):
    """Sign-in used the default name, push the name typed later in Settings: one install, one device."""
    setup_owner(hc)
    prove_this_device(hc)
    phone, body = phone_login(hc, "Android phone", install_id=NEW_PHONE)
    clock.advance(60)
    push_id = add_push(phone, bearer(body), "Zeus's Pixel", NEW_PHONE)
    mine = [d for d in devices(hc) if not d["current"]]
    assert len(mine) == 1 and mine[0]["label"] == "Zeus's Pixel"  # the newest name shows
    assert {c["source"] for c in mine[0]["credentials"]} == {"sessions", "push"}
    r = hc.delete(f"/v1/me/devices/{mine[0]['id']}", headers=csrf(hc))
    assert r.status_code == 200 and r.json()["revoked"] == {"sessions": 1, "passkeys": 0, "approver_keys": 0, "push": 1}
    assert phone.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
    assert hc.app.state.notify.repo.get_device(push_id) is None
    assert [d for d in devices(hc) if not d["current"]] == []


def test_a_passkey_joins_its_install_whatever_its_label(hc):
    setup_owner(hc)
    phone, body = phone_login(hc, "Android phone", install_id=NEW_PHONE)
    opts = phone.post("/v1/auth/passkeys/register/options", headers=bearer(body)).json()
    r = phone.post("/v1/auth/passkeys/register", headers=bearer(body),
                   json={"credential": SoftAuthenticator().register(opts), "label": "Zeus's Pixel", "install_id": NEW_PHONE})
    assert r.status_code == 201, r.text
    mine = [d for d in devices(hc) if not d["current"]]
    assert len(mine) == 1 and {c["source"] for c in mine[0]["credentials"]} == {"sessions", "passkeys"}


def test_install_id_must_look_like_one(hc):
    setup_owner(hc)
    for bad in ("short", "has spaces in it, sixteen+", "x" * 65):
        r = new_session_client(hc).post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD,
                                                                "client": "app", "install_id": bad})
        assert r.status_code == 422, bad


def test_refuses_the_current_device_tokens_and_agents(hc):
    setup_owner(hc)
    prove_this_device(hc)
    current = next(d for d in devices(hc) if d["current"])
    r = hc.delete(f"/v1/me/devices/{current['id']}", headers=csrf(hc))
    assert r.status_code == 409 and r.json()["reason"] == "current_device"
    _, body = phone_login(hc)
    pixel = by_label(devices(hc), "Pixel 9")
    pat = hc.post("/v1/tokens", json={"name": "script"}, headers=csrf(hc)).json()["one_time"]["token"]
    for headers in (AGENT, OWNER, {"Authorization": f"Bearer {pat}"}):  # an agent, a static token, an API token
        for r in (hc.get("/v1/me/devices", headers=headers), hc.delete(f"/v1/me/devices/{pixel['id']}", headers=headers)):
            # The reason reaches the caller, so the CLI and the dashboard can say "sign in, a token cannot do this".
            assert r.status_code == 403 and r.json()["reason"] == "session_required", r.text
    assert hc.get("/v1/me", headers=bearer(body)).status_code == 200  # nothing was revoked


def test_people_see_and_remove_only_their_own_devices(hc):
    setup_owner(hc)
    adult = enrol(hc, "adult", "ana")
    prove_this_device(adult)
    ana_phone, body = phone_login(hc, "Ana's phone", username="ana")
    owner_view = devices(hc)
    assert all(d["label"] != "Ana's phone" for d in owner_view)
    ana = by_label(devices(adult), "Ana's phone")
    r = hc.delete(f"/v1/me/devices/{ana['id']}", headers=csrf(hc))  # another person's device: not found, no-op
    assert r.status_code == 200 and r.json()["removed"] is False
    assert ana_phone.get("/v1/me", headers=bearer(body)).status_code == 200
    r = adult.delete(f"/v1/me/devices/{ana['id']}", headers=csrf(adult))
    assert r.status_code == 200 and r.json()["removed"] is True
    assert ana_phone.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


@pytest.mark.skipif(not hasattr(idm, "ApproverKeyRow"), reason="the approver key table arrives with #702 (PR #838)")
def test_lost_device_revokes_its_approver_key(hc, clock):
    setup_owner(hc)
    prove_this_device(hc)
    phone, body = phone_login(hc)
    owner_id = hc.get("/v1/me").json()["principal"]["id"]
    identity = hc.app.state.identity
    identity.repo.add(idm.ApproverKeyRow(id="apk_lost_phone", user_id=owner_id, label="Pixel 9", key_kind="software",
                                         public_key=b"\x30", fingerprint="sha256:lost-phone", created_at=clock.now))
    pixel = by_label(devices(hc), "Pixel 9")
    assert pixel["kind"] == "phone" and ("approver_keys", "apk_lost_phone") in {(c["source"], c["id"]) for c in pixel["credentials"]}
    r = hc.delete(f"/v1/me/devices/{pixel['id']}", headers=csrf(hc))
    assert r.status_code == 200 and r.json()["revoked"]["approver_keys"] == 1 and r.json()["revoked"]["sessions"] == 1
    assert identity.repo.get(idm.ApproverKeyRow, "apk_lost_phone").revoked_at is not None  # it can no longer approve
    assert phone.post("/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
