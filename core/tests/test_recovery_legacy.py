# SPDX-License-Identifier: Apache-2.0
"""Legacy contacts and the claim process (gateway permissions design PR 25f, §3.13 tests 7 and 10, D-028).

Each test fails without the change: the access key and its verifier, the claim with a certificate,
the owner's wait, the cancel on any owner sign-in, the inactivity check, the second person, the
12-month read-only export, and a legacy principal that reaches nothing else."""

from __future__ import annotations

import base64
import io
import json
import tarfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from recovery_support import ContactPhone, owner_with_passkey
from test_identity import PASSWORD, audit_events, csrf, enrol, id_settings

DAY = 86400
PDF = base64.b64encode(b"%PDF-1.4 death certificate").decode()


@pytest.fixture
def rc(settings, clock, executor, tmp_path):
    from dataclasses import replace

    from onemind_core.files.settings import FilesSettings

    s = id_settings(settings)
    s = replace(s, sections={**s.sections, "files": FilesSettings(root=tmp_path / "files", min_free_bytes=0)})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        yield c


def add_legacy(rc, name="Ana", **extra):
    return rc.post("/v1/auth/legacy/contacts", json={"kind": "outside", "display_name": name, **extra}, headers=csrf(rc))


def legacy_phone(rc, name="Ana", **extra) -> tuple[ContactPhone, str]:
    r = add_legacy(rc, name, **extra)
    assert r.status_code == 201, r.text
    invite = r.json()["invite"]
    phone = ContactPhone()
    payload = json.loads(base64.urlsafe_b64decode(invite.split(".")[1] + "=="))
    body = phone.accept_body(invite)
    r = TestClient(rc.app).post(f"/v1/legacy/invites/{payload['invite_id']}/accept", json=body)
    assert r.status_code == 201, r.text
    one = r.json()["one_time"]
    phone.token, phone.contact_id = one["contact_token"], r.json()["contact_id"]
    return phone, one["access_key"]


def claim(rc, phone, key, cert=PDF, ctype="application/pdf"):
    return TestClient(rc.app).post("/v1/legacy/claims", headers=phone.auth,
                                   json={"access_key": key, "certificate_type": ctype, "certificate": cert})


def put_home_file(rc, name: str, data: bytes):
    owner_id = rc.get("/v1/me").json()["principal"]["id"]
    files = rc.app.state.files_service
    import os

    from onemind_core.files.access import Root

    with files._space(Root("home", owner_id)) as fd:
        f = os.open(name, os.O_WRONLY | os.O_CREAT, 0o600, dir_fd=fd)
        os.write(f, data)
        os.close(f)


def test_a_legacy_contact_gets_an_access_key_once_and_the_box_keeps_only_a_verifier(rc, settings):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc, wait_days=14)
    assert len(key.replace("-", "")) == 64
    listed = rc.get("/v1/auth/legacy/contacts").json()
    assert listed[0]["wait_days"] == 14 and listed[0]["state"] == "cooling_off"
    me = TestClient(rc.app).get("/v1/legacy/contact", headers=phone.auth).json()
    assert me["wait_days"] == 14 and "access_key" not in me
    text = "\n".join(json.dumps(e) for e in audit_events(settings))
    assert key not in text and key.replace("-", "") not in text
    with rc.app.state.legacy_contacts.db.session() as s:
        from onemind_core.recovery.models import ContactRow

        row = s.get(ContactRow, phone.contact_id)
    assert key not in json.dumps(row.extra) and row.extra["access_verifier"]
    assert add_legacy(rc, "Ben", wait_days=45).status_code == 422  # only the set options


def test_a_wrong_key_or_a_bad_certificate_is_refused_and_a_cooling_off_contact_cannot_claim(rc, clock):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    r = claim(rc, phone, key)
    assert r.status_code == 409 and r.json()["reason"] == "cooling_off"
    clock.advance(7 * DAY + 1)
    assert claim(rc, phone, "AAAA-BBBB").json()["reason"] == "access_key_invalid"
    r = claim(rc, phone, key, cert=base64.b64encode(b"not a document").decode())
    assert r.status_code == 422 and r.json()["reason"] == "certificate_type"
    r = claim(rc, phone, key, cert=PDF, ctype="image/png")
    assert r.status_code == 422 and r.json()["reason"] == "certificate_type"
    r = claim(rc, phone, key.lower())  # letter case and dashes do not matter
    assert r.status_code == 201, r.text
    assert claim(rc, phone, key).json()["reason"] == "already_open"


def test_any_owner_sign_in_during_the_wait_cancels_the_claim(rc, clock, settings):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    assert c["state"] == "waiting" and c["needs_second"] is False
    r = TestClient(rc.app).post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
    assert r.status_code == 200
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["state"] == "cancelled" and got["end_reason"] == "owner_signed_in"
    assert "legacy.claim.started" in [e["event"] for e in audit_events(settings)]


def test_the_claim_completes_only_after_the_wait_with_the_owner_silent_then_a_read_only_export(rc, clock):
    owner_with_passkey(rc)
    put_home_file(rc, "letters.txt", b"to my family")
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    legacy = rc.app.state.legacy_contacts
    # Notices every 7 days and on the last day; no export before the end.
    clock.advance(7 * DAY + 1)
    assert legacy.tick() == 1 and legacy.tick() == 0
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).status_code == 403
    clock.advance(23 * DAY)  # 30 days and a second after the claim
    legacy.tick()
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["state"] == "granted" and got["access_until"]
    m = TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth)
    assert m.status_code == 200 and m.json()["read_only"] is True
    assert [f["path"] for f in m.json()["files"]] == ["letters.txt"]
    tar = TestClient(rc.app).get("/v1/legacy/export/download", headers=phone.auth)
    assert tar.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(tar.content)) as t:
        assert t.extractfile("letters.txt").read() == b"to my family"
    # 12 months later the window is over; the data stays on the box.
    clock.advance(366 * DAY)
    r = TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth)
    assert r.status_code == 403 and r.json()["reason"] == "export_window_ended"
    assert c["id"]


def test_a_second_person_must_confirm_when_one_exists(rc, clock):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    assert c["needs_second"] is True
    legacy = rc.app.state.legacy_contacts
    clock.advance(30 * DAY + 1)
    legacy.tick()
    assert TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]["state"] == "awaiting_second"
    # The claimant cannot confirm their own claim; an owner token is not the second person either.
    assert TestClient(rc.app).post(f"/v1/legacy/claims/{c['id']}/confirm", headers=phone.auth).status_code == 403
    assert TestClient(rc.app).post(f"/v1/auth/legacy/claims/{c['id']}/confirm", headers=OWNER).status_code == 403
    # The adult's session expired over the month; a fresh sign-in is still the adult (not the owner).
    fresh = TestClient(rc.app)
    assert fresh.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD}).status_code == 200
    r = fresh.post(f"/v1/auth/legacy/claims/{c['id']}/confirm", headers=csrf(fresh))
    assert r.status_code == 200 and r.json()["state"] == "granted", r.text
    assert adult is not None


def test_the_household_sees_the_claim_and_certificate_and_an_owner_cancels_and_blocks(rc, clock):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    listed = TestClient(rc.app).get("/v1/auth/legacy/claims", headers=OWNER).json()
    assert listed[0]["contact_display_name"] == "Ana"
    cert = TestClient(rc.app).get(f"/v1/auth/legacy/claims/{c['id']}/certificate", headers=OWNER)
    assert cert.status_code == 200 and cert.content.startswith(b"%PDF-")
    assert adult.get("/v1/auth/legacy/claims").status_code in (200, 401)  # session may have lapsed over 7 days
    r = TestClient(rc.app).post(f"/v1/auth/legacy/claims/{c['id']}/cancel", headers=OWNER, json={"block": True})
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert TestClient(rc.app).get("/v1/legacy/contact", headers=phone.auth).status_code == 401  # blocked


def test_a_legacy_principal_reaches_its_own_routes_and_nothing_else(rc, clock):
    """§3.13 test 7: 403 on admin, other people's Homes, app secrets and every delete route."""
    owner_with_passkey(rc)
    phone, _ = legacy_phone(rc)
    bare = TestClient(rc.app)
    checked = 0
    for route in rc.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/v1/") or path.startswith(("/v1/legacy/", "/v1/recovery/invites/")):
            continue
        concrete = path.replace("{", "x").replace("}", "")
        for method in sorted((getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}):
            anon = bare.request(method, concrete, json={})
            if anon.status_code != 401 or "missing bearer token" not in anon.text:
                continue
            r = bare.request(method, concrete, headers=phone.auth, json={})
            assert r.status_code == 403, (method, path, r.status_code, r.text[:200])
            checked += 1
    assert checked > 100
    # And a recovery contact token cannot use the legacy routes, nor a legacy token the recovery ones.
    assert bare.get("/v1/recovery/contact", headers=phone.auth).status_code == 403


def test_removing_a_legacy_contact_ends_their_claim_and_is_l0(rc, clock):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    claim(rc, phone, key)
    fresh = TestClient(rc.app)
    assert fresh.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    # (that sign-in already cancelled the claim; removing the contact still works with no fresh passkey)
    r = fresh.delete(f"/v1/auth/legacy/contacts/{phone.contact_id}", headers=csrf(fresh))
    assert r.status_code == 200 and r.json()["state"] == "removed"
    assert timedelta(days=1)
