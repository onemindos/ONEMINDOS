# SPDX-License-Identifier: Apache-2.0
"""Legacy contacts and the claim process (gateway permissions design PR 25f, §3.13 tests 7 and 10, D-028).

Each test fails without the change: the access key and its verifier, the claim with a certificate,
the owner's wait, the cancel on any owner sign-in, the inactivity check, the second person, the
12-month read-only export, and a legacy principal that reaches nothing else."""

from __future__ import annotations

import base64
import fcntl
import io
import json
import os
import tarfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from threading import Barrier, Event, get_ident

import anyio
import pytest
from fastapi.testclient import TestClient

from conftest import ADULT, OWNER
from onemind_core.app import create_app
from onemind_core.errors import ApiError
from onemind_core.recovery.legacy import LegacyContacts
from recovery_support import ContactPhone, owner_with_passkey as setup_passkey_owner
from test_identity import LOCAL_PEER, PASSWORD, SoftAuthenticator, audit_events, box_code, csrf, enrol, id_settings, register_passkey, setup_owner

DAY = 86400
PDF = base64.b64encode(b"%PDF-1.4 death certificate").decode()


def recovery_client(settings, clock, executor, tmp_path, **identity_options):
    from dataclasses import replace

    from onemind_core.files.settings import FilesSettings

    s = id_settings(settings, **identity_options)
    s = replace(s, sections={**s.sections, "files": FilesSettings(root=tmp_path / "files", min_free_bytes=0)})
    return TestClient(create_app(s, clock=clock, executor=executor), client=LOCAL_PEER)


@pytest.fixture
def enrollment_available(monkeypatch):
    # Exercise the downstream enrollment and claim paths while the release hold is in place.
    monkeypatch.setattr(LegacyContacts, "_require_enrollment", lambda self: None)


@pytest.fixture
def rc(settings, clock, executor, tmp_path, enrollment_available):
    with recovery_client(settings, clock, executor, tmp_path) as c:
        yield c


@pytest.fixture(name="long_session_rc")
def long_session_client(settings, clock, executor, tmp_path, enrollment_available):
    # A live password session can cancel a grant without signing in again first.
    with recovery_client(settings, clock, executor, tmp_path, session_idle_hours=24 * 90, session_max_days=90) as c:
        yield c


def owner_with_passkey(rc):
    rc.legacy_passkey = setup_passkey_owner(rc)


def request_invite(rc, name="Ana", headers=None, **extra):
    return rc.post("/v1/auth/legacy/contacts", json={"kind": "outside", "display_name": name, **extra},
                   headers=csrf(rc) if headers is None else headers)


def invite_approval(rc, action_id):
    options = rc.post(f"/v1/actions/{action_id}/approve-options", headers=csrf(rc))
    assert options.status_code == 200, options.text
    proof = {"webauthn": rc.legacy_passkey.assert_(options.json()["challenge"])}
    if options.json().get("box_code_required"):  # D-028: L2; during the grace an L1 key plus the box's code
        proof["box_code"] = box_code(rc)
    return proof


def add_legacy(rc, name="Ana", **extra):
    queued = request_invite(rc, name, **extra)
    assert queued.status_code == 202, queued.text
    action = queued.json()
    url = f"/v1/actions/{action['action_id']}/approve"
    result = rc.post(url, headers=csrf(rc), json=invite_approval(rc, action["action_id"]))
    assert result.status_code == 200 and result.json()["state"] == "succeeded", result.text
    return rc.get(f"/v1/auth/legacy/contacts/{action['contact_id']}/invite")


def legacy_phone(rc, name="Ana", **extra) -> tuple[ContactPhone, str]:
    r = add_legacy(rc, name, **extra)
    assert r.status_code == 200, r.text
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


def put_home_file(rc, name: str, data: bytes, *, owner_id: str | None = None):
    owner_id = owner_id or _owner_id(rc)
    files = rc.app.state.files_service
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
    assert request_invite(rc, "Ben", wait_days=45).status_code == 422  # only the set options


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
    r = TestClient(rc.app, client=LOCAL_PEER).post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
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
    assert c["state"] == "waiting" and c["ends_at"]


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
    fresh = TestClient(rc.app, client=LOCAL_PEER)
    assert fresh.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD}).status_code == 200
    r = fresh.post(f"/v1/auth/legacy/claims/{c['id']}/confirm", headers=csrf(fresh))
    assert r.status_code == 200 and r.json()["state"] == "granted", r.text
    assert adult is not None


@pytest.mark.parametrize("credential", ["static", "personal_token"])
def test_only_a_live_adult_session_can_confirm_a_household_claim(rc, clock, credential):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    adult_id = adult.get("/v1/me").json()["principal"]["id"]
    headers = ADULT if credential == "static" else owner_pat(adult, "instance:read")
    phone, key = legacy_phone(rc, wait_days=14)
    clock.advance(7 * DAY + 1)
    cid = claim(rc, phone, key).json()["id"]
    clock.advance(14 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    legacy.tick()
    assert legacy._claim(cid).state == "awaiting_second"

    client = TestClient(rc.app, client=LOCAL_PEER)
    url = f"/v1/auth/legacy/claims/{cid}/confirm"
    assert client.post(url, headers=headers).status_code == 403
    assert legacy._claim(cid).second_by is None
    assert client.get("/v1/legacy/export", headers=phone.auth).status_code == 403

    session = client.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD, "client": "cli"})
    assert session.status_code == 200, session.text
    result = client.post(url, headers={"Authorization": f"Bearer {session.json()['access_token']}"})
    assert result.status_code == 200 and result.json()["state"] == "granted", result.text
    assert legacy._claim(cid).second_by == adult_id


def test_the_household_sees_the_claim_and_certificate_and_an_owner_cancels_and_blocks(long_session_rc, clock):
    rc = long_session_rc
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    listed = TestClient(rc.app).get("/v1/auth/legacy/claims", headers=OWNER).json()
    assert listed[0]["contact_display_name"] == "Ana"
    cert = TestClient(rc.app).get(f"/v1/auth/legacy/claims/{c['id']}/certificate", headers=OWNER)
    assert cert.status_code == 200 and cert.content.startswith(b"%PDF-")
    adult_view = adult.get("/v1/auth/legacy/claims")
    if adult_view.status_code == 200:  # the adult's session may have lapsed over 7 days
        assert adult_view.json()[0]["id"] == c["id"]
    else:
        assert adult_view.status_code == 401
    r = rc.post(f"/v1/auth/legacy/claims/{c['id']}/cancel", headers=csrf(rc), json={"block": True})
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
    fresh = TestClient(rc.app, client=LOCAL_PEER)
    assert fresh.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    # (that sign-in already cancelled the claim; removing the contact still works with no fresh passkey)
    r = fresh.delete(f"/v1/auth/legacy/contacts/{phone.contact_id}", headers=csrf(fresh))
    assert r.status_code == 200 and r.json()["state"] == "removed"
    with rc.app.state.legacy_contacts.db.session() as s:
        from onemind_core.recovery.legacy import ClaimRow

        assert s.query(ClaimRow).one().end_reason in ("owner_signed_in", "contact_ended")


def granted(rc, clock, phone, key) -> dict:
    """A claim that ran its 30-day wait with the owner silent and nobody else to confirm: granted."""
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    clock.advance(30 * DAY + 1)
    rc.app.state.legacy_contacts.tick()
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["id"] == c["id"] and got["state"] == "granted", got
    return got


def test_an_owner_who_signs_in_after_the_grant_ends_it_and_the_export_refuses(rc, clock):
    """The owner was away (a trip), a claim was granted; the owner signs in again: the export ends at once."""
    owner_with_passkey(rc)
    put_home_file(rc, "letters.txt", b"to my family")
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).status_code == 200
    assert TestClient(rc.app, client=LOCAL_PEER).post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    for path in ("/v1/legacy/export", "/v1/legacy/export/download"):
        assert TestClient(rc.app).get(path, headers=phone.auth).status_code == 403
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["state"] == "cancelled" and got["end_reason"] == "owner_signed_in"


def test_owner_activity_after_the_grant_without_a_sign_in_event_also_ends_it(rc, clock):
    """Defence in depth: a key used after the grant (no auth.login event) ends the claim before any export."""
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    from onemind_core.identity.models import PasskeyRow
    from onemind_core.ledger import utc

    legacy = rc.app.state.legacy_contacts
    clock.advance(60)
    with legacy.db.session.begin() as s:
        for row in s.query(PasskeyRow).all():
            row.last_used_at = utc(clock.now)
    r = TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth)
    assert r.status_code == 403
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["state"] == "cancelled" and got["end_reason"] == "owner_active"


def test_an_adult_who_accepted_an_outside_invite_cannot_confirm_their_own_claim(rc, clock):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    # The adult accepts an *outside* legacy invite while signed in on that device.
    r = add_legacy(rc, "Ben (outside)")
    invite = r.json()["invite"]
    payload = json.loads(base64.urlsafe_b64decode(invite.split(".")[1] + "=="))
    phone = ContactPhone()
    r = adult.post(f"/v1/legacy/invites/{payload['invite_id']}/accept", json=phone.accept_body(invite),
                   headers=csrf(adult))
    assert r.status_code == 201, r.text
    phone.token, key = r.json()["one_time"]["contact_token"], r.json()["one_time"]["access_key"]
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    clock.advance(30 * DAY + 1)
    rc.app.state.legacy_contacts.tick()
    fresh = TestClient(rc.app, client=LOCAL_PEER)
    assert fresh.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD}).status_code == 200
    r = fresh.post(f"/v1/auth/legacy/claims/{c['id']}/confirm", headers=csrf(fresh))
    assert r.status_code == 403 and "your own legacy claim" in r.text, r.text
    # Ben is not a second person for his own claim, so nobody is waited for: the claim still finishes.
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["needs_second"] is False and got["state"] == "granted", got


def test_the_access_key_never_reaches_the_audit_the_events_or_the_notices(rc, clock, settings):
    owner_with_passkey(rc)
    legacy = rc.app.state.legacy_contacts
    published: list[str] = []
    real_publish = legacy.gw.events.publish_event

    def capture(*a, **kw):
        published.append(json.dumps([a, kw], default=str))
        return real_publish(*a, **kw)

    legacy.gw.events.publish_event = capture
    try:
        phone, key = legacy_phone(rc)
        assert claim(rc, phone, "AAAA-BBBB").status_code in (401, 409)  # a refused key is audited too
        # After the cooling-off, a near miss (the real key with its last letter changed) takes the
        # key_refused path, which writes an audit line: the attempted key must not be in it.
        clock.advance(7 * DAY + 1)
        near = key[:-1] + ("A" if key[-1] != "A" else "B")
        assert claim(rc, phone, near).status_code == 401
        granted(rc, clock, phone, key)
        TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth)
        own = TestClient(rc.app).get("/v1/legacy/contact", headers=phone.auth)
        listed = TestClient(rc.app).get("/v1/auth/legacy/claims", headers=OWNER)
        assert own.status_code == 200 and listed.status_code == 200
        feed, household = own.text, listed.text  # the contact's own view, and the household's claims list
    finally:
        legacy.gw.events.publish_event = real_publish
    from onemind_core.recovery.models import NoticeRow

    with legacy.db.session() as s:
        notices = json.dumps([[n.event, n.data] for n in s.query(NoticeRow).all()], default=str)
    audit = "\n".join(json.dumps(e) for e in audit_events(settings))
    events = "\n".join(published)
    assert published and "claim.granted" in events and "legacy.claim.key_refused" in audit
    for secret in (key, key.replace("-", ""), key.lower(), near, near.replace("-", ""), phone.token):
        for where in (audit, events, notices, feed, household):
            assert secret not in where


# ---- compare-and-set on every claim write (Opus review round 2, #1208) -----------------------------------

def _record_claim_notices(legacy) -> list[tuple[str, str]]:
    import threading

    log: list[tuple[str, str]] = []
    lock = threading.Lock()
    real = legacy.tell

    def tell(owner_id, event, data, *a, **kw):
        with lock:
            log.append((event, data.get("claim_id")))
        return real(owner_id, event, data, *a, **kw)

    legacy.tell = tell
    return log


def _endings(log, claim_id) -> list[str]:
    return [e.removeprefix("legacy.claim.") for e, cid in log
            if cid == claim_id and e in ("legacy.claim.granted", "legacy.claim.cancelled")]


def _owner_id(rc) -> str:
    return rc.get("/v1/me").json()["principal"]["id"]


def _due_claim(rc, contact_id: str, owner_id: str) -> str:
    """A claim whose wait is over, nobody else to confirm, the owner silent since it started: tick grants it."""
    from onemind_core.identity.crypto import new_id
    from onemind_core.recovery.legacy import ClaimRow

    legacy = rc.app.state.legacy_contacts
    now = legacy.now()
    row = ClaimRow(id=new_id("lcl"), owner_user_id=owner_id, contact_id=contact_id, state="waiting",
                   created_at=now - timedelta(seconds=10), ends_at=now - timedelta(seconds=1), needs_second=False,
                   certificate_type="application/pdf", certificate_sha256="0" * 64, notices_sent=["start"])
    with legacy.db.session.begin() as s:
        s.add(row)
    return row.id


def test_a_sign_in_that_lands_while_tick_is_granting_is_never_overwritten_back_to_granted(rc, clock):
    """The owner signs in between tick()'s activity check and its grant write. Before the fix the grant
    wrote `granted` over the cancel; now the grant finds the claim cancelled and writes nothing."""
    owner_with_passkey(rc)
    owner_id = _owner_id(rc)  # the owner's last activity, before the claim
    phone, _key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    log = _record_claim_notices(legacy)
    cid = _due_claim(rc, phone.contact_id, owner_id)
    real = legacy._owner_active_since

    def silent_then_sign_in(owner, since):
        answer = real(owner, since)  # "silent" for the whole wait...
        legacy._owner_signed_in({"data": {"user_id": owner_id}})  # ...then the sign-in lands, before the grant
        return answer

    legacy._owner_active_since = silent_then_sign_in
    try:
        legacy.tick()
    finally:
        legacy._owner_active_since = real
    c = legacy._claim(cid)
    assert c.state == "cancelled" and c.end_reason == "owner_signed_in" and c.granted_at is None
    assert _endings(log, cid) == ["cancelled"]
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).status_code == 403


def test_stale_claim_writes_change_nothing_once_the_claim_ended(rc, clock):
    owner_with_passkey(rc)
    owner_id = _owner_id(rc)
    phone, _key = legacy_phone(rc)
    clock.advance(60)
    legacy = rc.app.state.legacy_contacts
    log = _record_claim_notices(legacy)
    cid = _due_claim(rc, phone.contact_id, owner_id)
    stale = legacy._claim(cid)
    legacy._owner_signed_in({"data": {"user_id": owner_id}})
    from onemind_core.recovery.legacy import OPEN_STATES, ClaimRow

    assert legacy._set(stale, OPEN_STATES, state="granted") is False
    assert legacy._set(stale, OPEN_STATES, ClaimRow.second_at.is_(None), second_by="usr_x") is False
    assert legacy._end_claim(stale, "cancelled", "owner_active", None).end_reason == "owner_signed_in"
    assert legacy._claim(cid).state == "cancelled" and legacy._claim(cid).second_by is None
    assert _endings(log, cid) == ["cancelled"]


def test_sign_in_after_grant_commit_publishes_cancel_after_grant(rc, clock, monkeypatch):
    """Pause the grant before delivery and let another worker try to cancel the committed grant."""
    from onemind_core.recovery.legacy import LegacyContacts

    owner_with_passkey(rc)
    owner_id = _owner_id(rc)
    phone, _key = legacy_phone(rc)
    legacy = rc.app.state.legacy_contacts
    cancel_worker = LegacyContacts(legacy.gw, legacy.ident, legacy.notify)
    clock.advance(7 * DAY + 1)
    cid = _due_claim(rc, phone.contact_id, owner_id)
    log = []
    unsubscribe = legacy.gw.events.subscribe(
        "legacy.claim.*", lambda event: log.append((event["type"], event["data"]["claim_id"]))
    )
    cancel_reached_lock_or_finished = Event()
    cancel_thread = None
    flock = fcntl.flock
    tell = legacy.tell

    def observe_lock(fd, operation):
        if get_ident() == cancel_thread and operation == fcntl.LOCK_EX:
            try:
                return flock(fd, operation | fcntl.LOCK_NB)
            except BlockingIOError:
                cancel_reached_lock_or_finished.set()
        return flock(fd, operation)

    def sign_in():
        nonlocal cancel_thread
        cancel_thread = get_ident()
        try:
            cancel_worker._owner_signed_in({"data": {"user_id": owner_id}})
        finally:
            # If the cancellation didn't contend for the lock, its notice has already gone out.
            cancel_reached_lock_or_finished.set()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool, monkeypatch.context() as mp:
            cancels = []

            def pause_grant_notice(owner, event, data, *args, **kwargs):
                if event == "legacy.claim.granted":
                    assert legacy._claim(cid).state == "granted"
                    cancels.append(pool.submit(sign_in))
                    assert cancel_reached_lock_or_finished.wait(timeout=10)
                return tell(owner, event, data, *args, **kwargs)

            mp.setattr(legacy, "tell", pause_grant_notice)
            mp.setattr(fcntl, "flock", observe_lock)
            assert legacy.tick() == 1
            assert len(cancels) == 1
            cancels[0].result(timeout=10)
    finally:
        unsubscribe()
    c = legacy._claim(cid)
    assert c.state == "cancelled" and c.end_reason == "owner_signed_in"
    assert _endings(log, cid) == ["granted", "cancelled"]
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).status_code == 403


# ---- who accepted, and the second person (Opus review, #1208 non-blocking items) ------------------------

def _accept_outside(rc, name, client: TestClient, headers=None, **extra):
    r = add_legacy(rc, name, **extra)
    invite = r.json()["invite"]
    payload = json.loads(base64.urlsafe_b64decode(invite.split(".")[1] + "=="))
    phone = ContactPhone()
    r = client.post(f"/v1/legacy/invites/{payload['invite_id']}/accept", json=phone.accept_body(invite),
                    headers=headers or {})
    assert r.status_code == 201, r.text
    phone.token, phone.contact_id = r.json()["one_time"]["contact_token"], r.json()["contact_id"]
    return phone, r.json()["one_time"]["access_key"]


def _extra(rc, contact_id):
    from onemind_core.recovery.models import ContactRow

    with rc.app.state.legacy_contacts.db.session() as s:
        return dict(s.get(ContactRow, contact_id).extra or {})


def test_who_accepted_is_recorded_with_the_access_key_for_every_session_kind(rc, clock):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    ben_id = adult.get("/v1/me").json()["principal"]["id"]
    # A bearer session (the phone app or the CLI signed in).
    bearer = TestClient(rc.app, client=LOCAL_PEER)
    tok = bearer.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD, "client": "cli"}).json()
    phone, _ = _accept_outside(rc, "B1", TestClient(rc.app, client=LOCAL_PEER), {"Authorization": f"Bearer {tok['access_token']}"})
    e = _extra(rc, phone.contact_id)
    assert e["accepted_signed_in"] is True and e["accepted_by_user_id"] == ben_id and e["access_verifier"]
    # A browser cookie session with its CSRF header.
    phone, _ = _accept_outside(rc, "B2", adult, csrf(adult))
    assert _extra(rc, phone.contact_id)["accepted_by_user_id"] == ben_id
    # A cookie WITHOUT the CSRF header: identity refuses it (H-16), so it counts as signed out; the accept works.
    phone, _ = _accept_outside(rc, "B3", adult)
    e = _extra(rc, phone.contact_id)
    assert e["accepted_signed_in"] is False and e["accepted_by_user_id"] is None and e["access_verifier"]
    # A bare, signed-out phone.
    phone, _ = _accept_outside(rc, "B4", TestClient(rc.app))
    e = _extra(rc, phone.contact_id)
    assert e["accepted_signed_in"] is False and e["accepted_by_user_id"] is None


def test_the_household_sees_the_confirmer_next_to_the_claimant_and_a_signed_out_accept(rc, clock):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    phone, key = _accept_outside(rc, "Ana", TestClient(rc.app))  # signed out
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    view = next(x for x in TestClient(rc.app).get("/v1/auth/legacy/claims", headers=OWNER).json() if x["id"] == c["id"])
    assert view["contact_display_name"] == "Ana" and view["claimant_accepted_signed_in"] is False
    assert view["confirmed_by_display_name"] is None
    fresh = TestClient(rc.app, client=LOCAL_PEER)
    assert fresh.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD}).status_code == 200
    r = fresh.post(f"/v1/auth/legacy/claims/{c['id']}/confirm", headers=csrf(fresh))
    assert r.status_code == 200, r.text
    view = next(x for x in fresh.get("/v1/auth/legacy/claims").json() if x["id"] == c["id"])
    assert view["confirmed_by_display_name"] == "Ben" and view["second_confirmed"] is True
    # A second confirmation changes nothing and sends no second notice.
    log = _record_claim_notices(rc.app.state.legacy_contacts)
    assert fresh.post(f"/v1/auth/legacy/claims/{c['id']}/confirm", headers=csrf(fresh)).status_code == 200
    assert [e for e, cid in log if e == "legacy.claim.confirmed"] == []
    assert adult is not None


# ---- round 1 review fixes (#1208) -------------------------------------------------------------------------

def test_a_second_person_who_disappears_during_the_wait_does_not_lock_the_claim(rc, clock):
    owner_with_passkey(rc)
    enrol(rc, "adult", "ben")
    ben_id = next(u["id"] for u in rc.get("/v1/users").json() if u.get("username") == "ben")
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    assert c["needs_second"] is True
    from onemind_core.identity.models import UserRow

    with rc.app.state.legacy_contacts.db.session.begin() as db:  # the owner's session lapsed over the cooling-off
        db.get(UserRow, ben_id).disabled = True
    clock.advance(30 * DAY + 1)
    rc.app.state.legacy_contacts.tick()
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["needs_second"] is False and got["state"] == "granted", got


def test_the_owners_own_personal_token_use_counts_as_alive_during_the_wait_and_after_the_grant(rc, clock):
    owner_with_passkey(rc)
    r = rc.post("/v1/tokens", json={"name": "phone app", "scopes": ["instance:read"], "expires_in_days": 365},
                headers=csrf(rc))
    assert r.status_code == 201, r.text
    pat = {"Authorization": "Bearer " + r.json()["one_time"]["token"]}
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    clock.advance(29 * DAY)
    assert TestClient(rc.app).get("/v1/me", headers=pat).status_code == 200  # the owner's script, no sign-in
    clock.advance(2 * DAY)
    rc.app.state.legacy_contacts.tick()
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["id"] == c["id"] and got["state"] == "cancelled" and got["end_reason"] == "owner_active", got


def test_personal_token_use_after_the_grant_ends_the_export(rc, clock):
    owner_with_passkey(rc)
    r = rc.post("/v1/tokens", json={"name": "cli", "scopes": ["instance:read"], "expires_in_days": 365},
                headers=csrf(rc))
    pat = {"Authorization": "Bearer " + r.json()["one_time"]["token"]}
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    clock.advance(120)
    assert TestClient(rc.app).get("/v1/me", headers=pat).status_code == 200
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).status_code == 403
    got = TestClient(rc.app).get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["state"] == "cancelled" and got["end_reason"] == "owner_active"


def test_the_database_rejects_a_second_open_claim(rc, clock):
    from sqlalchemy.exc import IntegrityError

    from onemind_core.identity.crypto import new_id
    from onemind_core.recovery.legacy import ClaimRow

    owner_with_passkey(rc)
    phone, _key = legacy_phone(rc)
    legacy = rc.app.state.legacy_contacts
    owner_id = _owner_id(rc)
    _due_claim(rc, phone.contact_id, owner_id)
    with pytest.raises(IntegrityError), legacy.db.session.begin() as s:  # what the second simultaneous claim hits
        s.add(ClaimRow(id=new_id("lcl"), owner_user_id=owner_id, contact_id=phone.contact_id, state="waiting",
                       created_at=legacy.now(), ends_at=legacy.now(), certificate_type="application/pdf",
                       certificate_sha256="0" * 64, notices_sent=[]))


def test_the_export_streams_a_valid_tar_and_allows_one_download_at_a_time(rc, clock):
    owner_with_passkey(rc)
    big = bytes(range(256)) * 9000  # 2.3 MB, spans several blocks and is not a multiple of 512
    put_home_file(rc, "big.bin", big)
    put_home_file(rc, "small.txt", b"hi")
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    contact = legacy._get(phone.contact_id)
    first = legacy.archive(contact, _Who())
    next(first)  # a download is running: the slot is taken
    second = TestClient(rc.app).get("/v1/legacy/export/download", headers=phone.auth)
    assert second.status_code == 409 and second.json()["reason"] == "download_running"
    first.close()  # released when the stream ends or is closed
    ok = TestClient(rc.app).get("/v1/legacy/export/download", headers=phone.auth)
    assert ok.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(ok.content)) as t:
        assert t.extractfile("big.bin").read() == big and t.extractfile("small.txt").read() == b"hi"


class _Who:
    def as_dict(self):
        return {"id": "legacy:test", "kind": "legacy", "role": "legacy"}


# ---- round 2 review fixes (#1208) -------------------------------------------------------------------------

@pytest.mark.parametrize("revocation", ["sign_in", "cancel", "personal_token"])
def test_revoking_a_grant_stops_the_current_file_and_later_files(long_session_rc, clock, settings, revocation):
    rc = long_session_rc
    owner_with_passkey(rc)
    if revocation == "personal_token":
        r = rc.post("/v1/tokens", json={"name": "cli", "scopes": ["instance:read"], "expires_in_days": 365},
                    headers=csrf(rc))
        assert r.status_code == 201, r.text
        pat = {"Authorization": "Bearer " + r.json()["one_time"]["token"]}
    block = b"a" * (1 << 20)
    put_home_file(rc, "a-current.bin", block if revocation == "cancel" else block + b"last bytes of current file")
    put_home_file(rc, "b-later.txt", b"later file")
    phone, key = legacy_phone(rc)
    c = granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    client = TestClient(rc.app, client=LOCAL_PEER)
    with closing(legacy.archive(legacy._get(phone.contact_id), _Who())) as stream:
        assert next(stream).startswith(b"a-current.bin")
        assert next(stream) == block
        clock.advance(120)
        if revocation == "sign_in":
            r = client.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
        elif revocation == "cancel":
            r = rc.post(f"/v1/auth/legacy/claims/{c['id']}/cancel", headers=csrf(rc))
        else:
            r = client.get("/v1/me", headers=pat)
        assert r.status_code == 200, r.text
        assert list(stream) == []
    assert legacy._claim(c["id"]).state == "cancelled"
    assert any(e["event"] == "legacy.export.stopped" for e in audit_events(settings))


@pytest.mark.parametrize("preflight", ["ok", "too_large", "walk_error"])
def test_a_download_holds_the_slot_during_preflight_across_workers(rc, clock, monkeypatch, preflight):
    from onemind_core.recovery.legacy import MAX_EXPORT_BYTES, LegacyContacts

    owner_with_passkey(rc)
    put_home_file(rc, "letter.txt", b"private")
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    other_worker = LegacyContacts(legacy.gw, legacy.ident, legacy.notify)
    other_worker.files = legacy.files
    walk = legacy._walk
    walking, proceed = Event(), Event()

    def slow_walk(owner_id):
        walking.set()
        assert proceed.wait(timeout=10)
        if preflight == "too_large":
            yield "big", MAX_EXPORT_BYTES + 1, -1, "big"
        elif preflight == "walk_error":
            raise OSError("failed to walk the home")
        else:
            yield from walk(owner_id)

    contact = legacy._get(phone.contact_id)
    with monkeypatch.context() as mp, ThreadPoolExecutor(max_workers=1) as pool:
        mp.setattr(legacy, "_walk", slow_walk)
        first = pool.submit(legacy.archive, contact, _Who())
        try:
            assert walking.wait(timeout=10)
            clock.advance(7 * 3600)
            with pytest.raises(ApiError) as busy:
                with closing(other_worker.archive(contact, _Who())):
                    pass
            assert (busy.value.status, busy.value.reason) == (409, "download_running")
        finally:
            proceed.set()
        if preflight == "ok":
            with closing(first.result(timeout=10)) as stream:
                assert next(stream).startswith(b"letter.txt")
                with pytest.raises(ApiError) as busy:
                    with closing(legacy.archive(contact, _Who())):
                        pass
                assert (busy.value.status, busy.value.reason) == (409, "download_running")
        elif preflight == "too_large":
            with pytest.raises(ApiError) as large:
                first.result(timeout=10)
            assert (large.value.status, large.value.reason) == (413, "export_too_large")
        else:
            with pytest.raises(OSError, match="failed to walk"):
                first.result(timeout=10)
    r = TestClient(rc.app).get("/v1/legacy/export/download", headers=phone.auth)
    assert r.status_code == 200, r.text


def test_closing_a_download_before_its_first_chunk_releases_the_slot(rc, clock):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    legacy.archive(legacy._get(phone.contact_id), _Who()).close()
    r = TestClient(rc.app).get("/v1/legacy/export/download", headers=phone.auth)
    assert r.status_code == 200, r.text


def test_disconnect_before_the_first_chunk_releases_the_http_download(rc, clock, monkeypatch):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    archive = legacy.archive
    streams = []  # Keep the iterator alive so garbage collection cannot hide a missing response cleanup.

    def track_archive(*args):
        stream = archive(*args)
        streams.append(stream)
        return stream

    path = "/v1/legacy/export/download"

    async def disconnect():
        async def send(message):
            assert message["type"] == "http.response.start" and message["status"] == 200
            raise BrokenPipeError("client disconnected")

        async def receive():
            await anyio.sleep_forever()

        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1",
                 "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
                 "headers": [(k.lower().encode(), v.encode()) for k, v in phone.auth.items()],
                 "root_path": "", "client": ("testclient", 50000), "server": ("testserver", 80), "state": {}}
        with anyio.fail_after(10), pytest.raises(BrokenPipeError, match="client disconnected"):
            await rc.app(scope, receive, send)

    try:
        with monkeypatch.context() as mp:
            mp.setattr(legacy, "archive", track_archive)
            rc.portal.call(disconnect)
        assert len(streams) == 1
        r = TestClient(rc.app).get(path, headers=phone.auth)
        assert r.status_code == 200, r.text
    finally:
        for stream in streams:
            stream.close()


def test_an_adult_enabled_during_the_wait_must_confirm_the_claim(rc, clock):
    from onemind_core.identity.models import UserRow

    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    adult_id = adult.get("/v1/me").json()["principal"]["id"]
    legacy = rc.app.state.legacy_contacts
    with legacy.db.session.begin() as s:
        s.get(UserRow, adult_id).disabled = True
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    r = claim(rc, phone, key)
    assert r.status_code == 201 and r.json()["needs_second"] is False, r.text
    cid = r.json()["id"]
    with legacy.db.session.begin() as s:
        s.get(UserRow, adult_id).disabled = False
    clock.advance(30 * DAY + 1)
    client = TestClient(rc.app, client=LOCAL_PEER)
    got = client.get("/v1/legacy/claims", headers=phone.auth).json()[0]
    assert got["state"] == "awaiting_second" and got["needs_second"] is True, got
    assert client.get("/v1/legacy/export/download", headers=phone.auth).status_code == 403
    assert client.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD}).status_code == 200
    r = client.post(f"/v1/auth/legacy/claims/{cid}/confirm", headers=csrf(client))
    assert r.status_code == 200 and r.json()["state"] == "granted", r.text


def test_losing_the_open_claim_race_returns_conflict_and_removes_its_certificate(rc, clock, monkeypatch):
    owner_with_passkey(rc)
    loser, loser_key = legacy_phone(rc, "Ana")
    winner, winner_key = legacy_phone(rc, "Bea")
    clock.advance(7 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    real = legacy._second_people
    winning_id = None

    def competing_claim(owner_id, contact):
        nonlocal winning_id
        if contact.id == loser.contact_id:
            # The loser passed the pre-check and wrote its certificate, but hasn't inserted its claim.
            assert len(list(legacy.dir.glob("*/certificate.pdf"))) == 1
            r = claim(rc, winner, winner_key)
            assert r.status_code == 201, r.text
            winning_id = r.json()["id"]
        return real(owner_id, contact)

    with monkeypatch.context() as mp:
        mp.setattr(legacy, "_second_people", competing_claim)
        r = claim(rc, loser, loser_key)
    assert r.status_code == 409 and r.json()["reason"] == "already_open", r.text
    assert winning_id is not None
    assert list(legacy.dir.glob("*/certificate.*")) == [legacy._cert_path(winning_id, "pdf")]


@pytest.mark.parametrize("damage", ["missing_file", "unknown_type"])
def test_an_unavailable_certificate_returns_404(rc, clock, damage):
    from onemind_core.recovery.legacy import ClaimRow

    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    r = claim(rc, phone, key)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    legacy = rc.app.state.legacy_contacts
    if damage == "missing_file":
        legacy._cert_path(cid, "pdf").unlink()
    else:
        with legacy.db.session.begin() as s:
            s.get(ClaimRow, cid).certificate_type = "application/octet-stream"
    r = TestClient(rc.app).get(f"/v1/auth/legacy/claims/{cid}/certificate", headers=OWNER)
    assert r.status_code == 404, r.text


def owner_pat(rc, *scopes):
    r = rc.post("/v1/tokens", json={"name": "CLI test", "scopes": list(scopes), "expires_in_days": 365},
                headers=csrf(rc))
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["one_time"]["token"]}


def test_invite_requires_a_separate_owner_approval_with_a_bound_passkey(rc):
    setup_owner(rc)
    pat = owner_pat(rc, "actions:approve", "instance:read")
    client = TestClient(rc.app)
    for credential in (OWNER, pat):
        assert request_invite(client, headers=credential).status_code == 403
    r = request_invite(rc)
    assert r.status_code == 202 and "invite" not in r.json(), r.text
    action_id, contact_id = r.json()["action_id"], r.json()["contact_id"]
    approve = f"/v1/actions/{action_id}/approve"
    invite = f"/v1/auth/legacy/contacts/{contact_id}/invite"
    assert rc.get("/v1/auth/legacy/contacts").json() == []
    assert rc.get(invite).status_code == 404
    assert rc.post(approve, headers=csrf(rc)).json()["reason"] == "step_up_required"
    assert rc.get(f"/v1/actions/{action_id}").json()["state"] == "awaiting_approval"

    rc.legacy_passkey = SoftAuthenticator()
    register_passkey(rc, rc.legacy_passkey)
    assert rc.post(approve, headers=csrf(rc)).json()["reason"] == "step_up_required"
    other = request_invite(rc, "Other contact").json()["action_id"]
    wrong_proof = invite_approval(rc, other)
    assert rc.post(approve, headers=csrf(rc), json=wrong_proof).status_code == 401
    proof = invite_approval(rc, action_id)
    for credential in (OWNER, pat):
        assert client.post(approve, headers=credential, json=proof).status_code == 403
    result = rc.post(approve, headers=csrf(rc), json=proof)
    assert result.status_code == 200 and result.json()["state"] == "succeeded", result.text
    issued = rc.get(invite)
    assert issued.status_code == 200 and issued.json()["invite"].startswith("omri1.")
    assert issued.json()["invite"] not in result.text
    for credential in (OWNER, pat):
        assert client.get(invite, headers=credential).status_code == 403


def test_shipping_gateway_refuses_new_legacy_enrollment_with_an_l1_key(settings, clock, executor, tmp_path):
    with recovery_client(settings, clock, executor, tmp_path) as rc:
        owner_with_passkey(rc)
        response = request_invite(rc)
        assert response.status_code == 503 and response.json()["reason"] == "legacy_enrollment_unavailable"
        assert all(action.type != "legacy.contact.add" for action in rc.app.state.repo.list())


@pytest.mark.parametrize("stage", ["approval", "pickup", "accept"])
def test_shipping_gateway_blocks_preexisting_legacy_enrollment(settings, clock, executor, tmp_path, monkeypatch, stage):
    with recovery_client(settings, clock, executor, tmp_path) as rc:
        owner_with_passkey(rc)
        with monkeypatch.context() as setup:
            setup.setattr(LegacyContacts, "_require_enrollment", lambda self: None)
            if stage == "approval":
                queued = request_invite(rc)
                assert queued.status_code == 202, queued.text
                action_id = queued.json()["action_id"]
                proof = invite_approval(rc, action_id)
            else:
                issued = add_legacy(rc)
                assert issued.status_code == 200, issued.text
                invite = issued.json()["invite"]
                contact_id = issued.json()["id"]

        if stage == "approval":
            result = rc.post(f"/v1/actions/{action_id}/approve", json=proof, headers=csrf(rc))
            assert result.status_code == 200 and result.json()["state"] == "failed", result.text
            assert "Legacy enrollment requires" in result.json()["result"]["message"]
            assert rc.get("/v1/auth/legacy/contacts").json() == []
        else:
            if stage == "pickup":
                result = rc.get(f"/v1/auth/legacy/contacts/{contact_id}/invite")
            else:
                result = TestClient(rc.app).post(f"/v1/legacy/invites/{contact_id}/accept",
                                                 json=ContactPhone().accept_body(invite))
            assert result.status_code == 503 and result.json()["reason"] == "legacy_enrollment_unavailable"
            assert rc.get("/v1/auth/legacy/contacts").json()[0]["state"] == "invited"


@pytest.mark.parametrize("conflict", ["final_slot", "same_household_adult"])
def test_parallel_approved_invites_preserve_contact_limits(rc, monkeypatch, conflict):
    owner_with_passkey(rc)
    if conflict == "final_slot":
        for n in range(4):
            assert add_legacy(rc, f"Contact {n}").status_code == 200
        params, expected_count, message = {}, 5, "at most 5 legacy contacts"
    else:
        adult = enrol(rc, "adult", "ben")
        params = {"kind": "household", "household_user_id": adult.get("/v1/me").json()["principal"]["id"]}
        expected_count, message = 1, "already a legacy contact"

    legacy = rc.app.state.legacy_contacts
    other = LegacyContacts(legacy.gw, legacy.ident, legacy.notify)
    actions = []
    for name in ("First", "Second"):
        response = request_invite(rc, name, **params)
        assert response.status_code == 202, response.text
        actions.append(legacy.gw.repo.get(response.json()["action_id"]))
    both_validated = Barrier(2)
    details = legacy._invite_details

    def validate(*args):
        values = details(*args)
        both_validated.wait(timeout=10)
        return values

    def run(service, action):
        results = []
        service._approve_invite(action, results.append)
        return results[0]

    monkeypatch.setattr(legacy, "_invite_details", validate)
    monkeypatch.setattr(other, "_invite_details", validate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, legacy, actions[0])
        second = pool.submit(run, other, actions[1])
        results = [first.result(timeout=10), second.result(timeout=10)]
    failed, succeeded = sorted(results, key=lambda result: result.outcome)
    assert failed.outcome == "failed" and message in failed.message
    assert succeeded.outcome == "succeeded"
    assert len(rc.get("/v1/auth/legacy/contacts").json()) == expected_count


def test_legacy_revocation_refuses_owner_credentials_and_accepts_a_password_session(long_session_rc, clock):
    rc = long_session_rc
    owner_with_passkey(rc)
    pat = owner_pat(rc, "instance:read")
    phone, key = legacy_phone(rc)
    assert rc.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    c = granted(rc, clock, phone, key)
    client = TestClient(rc.app)
    cancel = f"/v1/auth/legacy/claims/{c['id']}/cancel"
    remove = f"/v1/auth/legacy/contacts/{phone.contact_id}"
    for credential in (OWNER, pat):
        assert client.delete(remove, headers=credential).status_code == 403
        assert client.post(cancel, headers=credential, json={"block": True}).status_code == 403
    assert rc.app.state.legacy_contacts._claim(c["id"]).state == "granted"
    stopped = rc.post(cancel, headers=csrf(rc), json={"block": True})
    assert stopped.status_code == 200 and stopped.json()["end_reason"] == "owner_cancelled", stopped.text
    assert client.get("/v1/legacy/contact", headers=phone.auth).status_code == 401


@pytest.mark.parametrize("claimant_kind", ["household", "outside"])
def test_same_adult_on_two_legacy_records_cannot_be_the_second_person(rc, clock, claimant_kind):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ben")
    adult_id = adult.get("/v1/me").json()["principal"]["id"]
    household = _accept_outside(rc, "Ben household", adult, csrf(adult), kind="household",
                               household_user_id=adult_id, cooling_off_days=3)
    outside = _accept_outside(rc, "Ben outside", adult, csrf(adult), cooling_off_days=3)
    distinct, _ = legacy_phone(rc, "Distinct contact", cooling_off_days=14)
    (claimant, key), (duplicate, _) = (household, outside) if claimant_kind == "household" else (outside, household)
    clock.advance(3 * DAY + 1)
    opened = claim(rc, claimant, key)
    assert opened.status_code == 201 and opened.json()["needs_second"] is False, opened.text
    confirm = f"/v1/legacy/claims/{opened.json()['id']}/confirm"
    client = TestClient(rc.app)
    refused = client.post(confirm, headers=duplicate.auth)
    assert refused.status_code == 403 and refused.json()["message"] == "not allowed to confirm this legacy claim", refused.text
    clock.advance(11 * DAY)
    accepted = client.post(confirm, headers=distinct.auth)
    assert accepted.status_code == 200 and accepted.json()["second_confirmed"] is True, accepted.text


@pytest.mark.parametrize("credential", ["session", "pat"])
def test_repeat_owner_activity_within_the_touch_interval_ends_the_claim(long_session_rc, clock, credential):
    from onemind_core.identity.service import TOUCH_EVERY

    rc = long_session_rc
    owner_with_passkey(rc)
    pat = owner_pat(rc, "instance:read")
    phone, key = legacy_phone(rc)
    owner_client, headers = (rc, {}) if credential == "session" else (TestClient(rc.app), pat)
    clock.advance(7 * DAY + 1)
    assert owner_client.get("/v1/me", headers=headers).status_code == 200
    clock.advance(1)
    opened = claim(rc, phone, key)
    assert opened.status_code == 201, opened.text
    clock.advance(TOUCH_EVERY.total_seconds() / 2)
    assert owner_client.get("/v1/me", headers=headers).status_code == 200
    clock.advance(30 * DAY)
    legacy = rc.app.state.legacy_contacts
    legacy.tick()
    row = legacy._claim(opened.json()["id"])
    assert (row.state, row.end_reason, row.granted_at) == ("cancelled", "owner_active", None)


def test_owner_activity_between_liveness_read_and_write_never_grants(rc, clock, monkeypatch):
    owner_with_passkey(rc)
    pat = owner_pat(rc, "instance:read")
    owner_id = _owner_id(rc)
    phone, _ = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    cid = _due_claim(rc, phone.contact_id, owner_id)
    notices = _record_claim_notices(legacy)
    real = legacy._owner_active_since

    def activity_after_read(owner, since):
        answer = real(owner, since)
        if not answer:
            assert TestClient(rc.app).get("/v1/me", headers=pat).status_code == 200
        return answer

    monkeypatch.setattr(legacy, "_owner_active_since", activity_after_read)
    legacy.tick()
    row = legacy._claim(cid)
    assert (row.state, row.end_reason, row.granted_at) == ("cancelled", "owner_active", None)
    assert _endings(notices, cid) == ["cancelled"]


@pytest.mark.parametrize("last_file", [False, True])
def test_cancel_during_manifest_stops_the_walk_and_withholds_file_list(long_session_rc, clock, monkeypatch, last_file):
    rc = long_session_rc
    owner_with_passkey(rc)
    put_home_file(rc, "private-a.txt", b"private")
    if not last_file:
        put_home_file(rc, "private-b.txt", b"also private")
    phone, key = legacy_phone(rc)
    c = granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    walk, visited = legacy._walk, []

    def cancel_during_walk(owner_id, **kwargs):
        for item in walk(owner_id, **kwargs):
            visited.append(item[0])
            if len(visited) == 1:
                stopped = rc.post(f"/v1/auth/legacy/claims/{c['id']}/cancel", headers=csrf(rc))
                assert stopped.status_code == 200 and stopped.json()["state"] == "cancelled", stopped.text
            yield item

    monkeypatch.setattr(legacy, "_walk", cancel_during_walk)
    r = TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth)
    assert r.status_code == 403 and r.json()["reason"] == "no_granted_claim", r.text
    assert visited == ["private-a.txt"] and "private-" not in r.text


def test_export_window_cannot_be_renewed_with_the_same_contact_key(rc, clock):
    from onemind_core.identity.models import iso

    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    first = granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    for days in (1, 365):
        clock.advance(days * DAY)
        replay = claim(rc, phone, key)
        assert replay.status_code == 409 and replay.json()["reason"] == "export_already_granted", replay.text
        assert iso(legacy._claim(first["id"]).access_until) == first["access_until"]
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).json()["reason"] == "export_window_ended"

    owner = TestClient(rc.app, client=LOCAL_PEER)
    assert owner.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
    old_key = claim(rc, phone, key)
    assert old_key.status_code == 409 and old_key.json()["reason"] == "export_already_granted"
    assert owner.delete(f"/v1/auth/legacy/contacts/{phone.contact_id}", headers=csrf(owner)).status_code == 200
    owner.legacy_passkey = rc.legacy_passkey
    replacement, new_key = legacy_phone(owner)
    assert new_key != key
    assert granted(rc, clock, replacement, new_key)["access_until"] > first["access_until"]


def test_another_legacy_contact_can_read_their_owners_claim_notices(rc, clock):
    from recovery_support import invite_and_accept

    owner_with_passkey(rc)
    claimant, key = legacy_phone(rc)
    confirmer, _ = legacy_phone(rc, "Second contact")
    recovery = invite_and_accept(rc)
    clock.advance(7 * DAY + 1)
    opened = claim(rc, claimant, key)
    assert opened.status_code == 201 and opened.json()["needs_second"] is True, opened.text
    client = TestClient(rc.app)
    path = "/v1/legacy/contact/notices"
    feed = client.get(path, headers=confirmer.auth)
    assert feed.status_code == 200, feed.text
    notice = next(item for item in feed.json() if item["event"] == "legacy.claim.started")
    assert notice["data"]["claim_id"] == opened.json()["id"]
    assert notice["data"]["contact_id"] == claimant.contact_id
    assert key not in feed.text and PDF not in feed.text
    for credential in (OWNER, recovery.auth):
        assert client.get(path, headers=credential).status_code == 403


@pytest.mark.parametrize("change", ["growth", "addition"])
def test_download_budget_uses_the_current_tar_entries(rc, clock, settings, monkeypatch, change):
    from onemind_core.recovery import legacy as module

    owner_with_passkey(rc)
    owner_id = _owner_id(rc)
    put_home_file(rc, "a.txt", b"short", owner_id=owner_id)
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    service = rc.app.state.legacy_contacts
    budget = 2048  # one 512-byte header, one 512-byte data block, 1024-byte trailer
    monkeypatch.setattr(module, "MAX_EXPORT_BYTES", budget)
    with closing(service.archive(service._get(phone.contact_id), _Who())) as stream:
        put_home_file(rc, "a.txt" if change == "growth" else "b.txt", b"x" * 1024, owner_id=owner_id)
        chunks = list(stream)
    assert sum(map(len, chunks)) <= budget
    assert any(e["event"] == "legacy.export.stopped" and e["data"]["reason"] == "export_too_large"
               for e in audit_events(settings))


def test_download_skips_a_file_replaced_by_a_fifo_after_stat(rc, clock, monkeypatch):
    owner_with_passkey(rc)
    put_home_file(rc, "a.txt", b"swap")
    put_home_file(rc, "b.txt", b"read")
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    walk, open_fd = legacy._walk, os.open

    def swap_after_stat(owner_id):
        for item in walk(owner_id):
            if item[3] == "a.txt":
                os.unlink(item[3], dir_fd=item[2])
                os.mkfifo(item[3], dir_fd=item[2])
            yield item

    def refuse_blocking_open(path, flags, *args, **kwargs):
        if path == "a.txt":
            assert flags & os.O_NONBLOCK, "opening the FIFO here would block the download"
        return open_fd(path, flags, *args, **kwargs)

    with closing(legacy.archive(legacy._get(phone.contact_id), _Who())) as stream:
        monkeypatch.setattr(legacy, "_walk", swap_after_stat)
        monkeypatch.setattr(os, "open", refuse_blocking_open)
        payload = b"".join(stream)
    with tarfile.open(fileobj=io.BytesIO(payload)) as tar:
        assert tar.getnames() == ["b.txt"] and tar.extractfile("b.txt").read() == b"read"


def test_two_workers_send_the_same_reminder_only_once(rc, clock, monkeypatch):
    from onemind_core.recovery.legacy import LegacyContacts

    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    c = claim(rc, phone, key).json()
    clock.advance(7 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    other = LegacyContacts(legacy.gw, legacy.ident, legacy.notify)
    both_read_waiting = Barrier(2)
    real = legacy._owner_active_since

    def activity(owner_id, since):
        both_read_waiting.wait(timeout=10)
        return real(owner_id, since)

    monkeypatch.setattr(legacy, "_owner_active_since", activity)
    monkeypatch.setattr(other, "_owner_active_since", activity)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(legacy.tick), pool.submit(other.tick)
        assert sorted((first.result(timeout=10), second.result(timeout=10))) == [0, 1]
    feed = TestClient(rc.app).get("/v1/legacy/contact/notices", headers=phone.auth).json()
    assert [n["data"]["notice"] for n in feed if n["event"] == "legacy.claim.reminder"
            and n["data"]["claim_id"] == c["id"]] == ["week1"]


def test_missed_last_day_notice_is_sent_before_grant(rc, clock):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    legacy = rc.app.state.legacy_contacts
    log = _record_claim_notices(legacy)
    c = granted(rc, clock, phone, key)
    assert [e for e, cid in log if cid == c["id"]] == [
        "legacy.claim.started", "legacy.claim.reminder", "legacy.claim.granted",
    ]
    feed = TestClient(rc.app).get("/v1/legacy/contact/notices", headers=phone.auth).json()
    assert [n["data"]["notice"] for n in feed if n["event"] == "legacy.claim.reminder"] == ["last_day"]


def test_deadline_worker_rechecks_after_a_weekly_reminder_wins(rc, clock, monkeypatch):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    cid = claim(rc, phone, key).json()["id"]
    deadline = rc.app.state.legacy_contacts
    weekly = LegacyContacts(deadline.gw, deadline.ident, deadline.notify)
    week_one = weekly.now() + timedelta(days=7, seconds=1)
    monkeypatch.setattr(weekly, "now", lambda: week_one)
    clock.advance(30 * DAY + 1)

    deadline_read, weekly_done = Event(), Event()
    check_active = deadline._owner_active_since

    def after_claim_read(owner_id, since):
        active = check_active(owner_id, since)
        deadline_read.set()
        assert weekly_done.wait(timeout=10)
        return active

    monkeypatch.setattr(deadline, "_owner_active_since", after_claim_read)
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(deadline.tick)
        try:
            assert deadline_read.wait(timeout=10)
            assert weekly.tick() == 1
        finally:
            weekly_done.set()
        assert waiting.result(timeout=10) == 1

    client = TestClient(rc.app)
    feed = client.get("/v1/legacy/contact/notices", headers=phone.auth).json()
    assert [n["data"]["notice"] for n in feed if n["event"] == "legacy.claim.reminder"
            and n["data"]["claim_id"] == cid] == ["last_day", "week1"]
    assert deadline._claim(cid).state == "granted"


@pytest.mark.parametrize("interrupted_before_upgrade", [False, True])
def test_interrupted_final_day_notice_is_retried_before_grant(rc, clock, monkeypatch, interrupted_before_upgrade):
    from onemind_core.recovery.legacy import OPEN_STATES

    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    cid = claim(rc, phone, key).json()["id"]
    clock.advance(30 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    if interrupted_before_upgrade:
        # The old gateway committed a marker, then stopped before creating the notice.
        assert legacy._set(legacy._claim(cid), OPEN_STATES,
                           notices_sent=["start", "week1", "week2", "week3", "week4", "last_day"])
    else:
        def interrupted(*args, **kwargs):
            raise RuntimeError("stopped before recording the notice")

        with monkeypatch.context() as crash:
            crash.setattr(legacy, "tell", interrupted)
            with pytest.raises(RuntimeError, match="stopped before recording the notice"):
                legacy.tick()
    assert legacy._claim(cid).state == "waiting"

    restarted = LegacyContacts(legacy.gw, legacy.ident, legacy.notify)
    log = _record_claim_notices(restarted)
    assert restarted.tick() == 1 and restarted.tick() == 0
    assert [event for event, claim_id in log if claim_id == cid] == ["legacy.claim.reminder", "legacy.claim.granted"]
    feed = TestClient(rc.app).get("/v1/legacy/contact/notices", headers=phone.auth).json()
    assert [n["data"]["notice"] for n in feed if n["event"] == "legacy.claim.reminder"
            and n["data"]["claim_id"] == cid] == ["last_day"]
    assert restarted._claim(cid).state == "granted"


@pytest.mark.parametrize("feed_only_marker", [False, True])
def test_failed_owner_inbox_insert_blocks_grant_and_is_retried(rc, clock, feed_only_marker):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    owner_with_passkey(rc)
    owner_id = _owner_id(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    cid = claim(rc, phone, key).json()["id"]
    legacy = rc.app.state.legacy_contacts
    if feed_only_marker:
        # A prior gateway may have marked the feed complete after losing the owner's inbox insert.
        assert legacy._set(legacy._claim(cid), ("waiting",), notices_sent=["start", "last_day_recorded"])
    clock.advance(30 * DAY + 1)
    inbox_title = "A legacy access request is still open"
    attempts = []

    def fail_owner_insert(_conn, _cursor, statement, params, _context, _executemany):
        if statement.startswith("INSERT INTO notify_notifications ") and owner_id in str(params) and inbox_title in str(params):
            attempts.append(owner_id)
            raise OperationalError(statement, None, RuntimeError("owner inbox insert interrupted"))

    engine = legacy.db.engine
    event.listen(engine, "before_cursor_execute", fail_owner_insert)
    try:
        legacy.tick()
    finally:
        event.remove(engine, "before_cursor_execute", fail_owner_insert)

    def reminders():
        repo = rc.app.state.notify.repo
        return [n for n in repo.list_notifications(owner_id, unread=None, severities=None, topics=None,
                                                    since=None, limit=100, cursor=None) if n.title == inbox_title]

    row = legacy._claim(cid)
    assert row.state == "waiting" and row.granted_at is None
    assert attempts == [owner_id]
    assert reminders() == []
    contact = legacy._get(phone.contact_id)
    assert all(n["event"] != "legacy.claim.reminder" for n in legacy.notices(contact))

    restarted = LegacyContacts(legacy.gw, legacy.ident, legacy.notify)
    owner_notices_at_grant = []
    unsubscribe = legacy.gw.events.subscribe(
        "legacy.claim.granted", lambda _: owner_notices_at_grant.extend(reminders()),
    )
    try:
        assert restarted.tick() == 1
        assert restarted.tick() == 0
    finally:
        unsubscribe()
    assert restarted._claim(cid).state == "granted"
    assert len(owner_notices_at_grant) == len(reminders()) == 1
    assert [n["data"]["notice"] for n in legacy.notices(contact) if n["event"] == "legacy.claim.reminder"] == ["last_day"]


def test_resignation_without_hook_rejects_an_already_authenticated_claim(rc, clock):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    contact = legacy._get(phone.contact_id)
    legacy.ended_hooks.clear()
    assert legacy.resign(contact, _Who())["state"] == "resigned"

    with pytest.raises(ApiError) as error:
        legacy.start_claim(contact, _Who(), key, "application/pdf", PDF)
    assert error.value.reason == "contact_ended"
    assert legacy.claims_of(contact) == []
    assert not list(legacy.dir.rglob("*.pdf"))


def test_resignation_between_tick_read_and_grant_prevents_grant(rc, clock, monkeypatch):
    owner_with_passkey(rc)
    phone, key = legacy_phone(rc)
    clock.advance(7 * DAY + 1)
    cid = claim(rc, phone, key).json()["id"]
    clock.advance(30 * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    legacy.ended_hooks.clear()
    contact = legacy._get(phone.contact_id)
    write = legacy._set

    def resign_before_grant(row, expect, *where, **values):
        if values.get("state") == "granted":
            assert legacy.resign(contact, _Who())["state"] == "resigned"
        return write(row, expect, *where, **values)

    monkeypatch.setattr(legacy, "_set", resign_before_grant)
    legacy.tick()
    assert legacy._claim(cid).granted_at is None
    legacy.tick()
    row = legacy._claim(cid)
    assert (row.state, row.end_reason, row.granted_at) == ("cancelled", "contact_ended", None)


def test_resignation_without_hook_stops_an_open_export_stream(rc, clock):
    owner_with_passkey(rc)
    block = b"a" * (1 << 20)
    put_home_file(rc, "letters.bin", block + b"last bytes")
    phone, key = legacy_phone(rc)
    c = granted(rc, clock, phone, key)
    legacy = rc.app.state.legacy_contacts
    contact = legacy._get(phone.contact_id)
    legacy.ended_hooks.clear()
    with closing(legacy.archive(contact, _Who())) as stream:
        assert next(stream).startswith(b"letters.bin")
        assert next(stream) == block
        assert legacy.resign(contact, _Who())["state"] == "resigned"
        assert legacy._claim(c["id"]).state == "granted"
        assert list(stream) == []
    assert legacy._claim(c["id"]).end_reason == "contact_ended"


@pytest.mark.parametrize("notice", ["confirmed", "reminder", "awaiting_second"])
def test_cancellation_is_never_followed_by_an_obsolete_claim_notice(rc, clock, monkeypatch, notice):
    from onemind_core.recovery.legacy import LegacyContacts

    owner_with_passkey(rc)
    owner_id = _owner_id(rc)
    phone, key = legacy_phone(rc)
    other, _ = legacy_phone(rc, "Second contact")
    clock.advance(7 * DAY + 1)
    cid = claim(rc, phone, key).json()["id"]
    if notice != "confirmed":
        clock.advance((7 if notice == "reminder" else 30) * DAY + 1)
    legacy = rc.app.state.legacy_contacts
    cancel_worker = LegacyContacts(legacy.gw, legacy.ident, legacy.notify)
    log = []
    cancel_contended_or_done = Event()
    cancels = []
    flock, tell = fcntl.flock, legacy.tell
    cancel_thread = None

    def observe_lock(fd, op):
        if get_ident() == cancel_thread and op == fcntl.LOCK_EX:
            try:
                return flock(fd, op | fcntl.LOCK_NB)
            except BlockingIOError:
                cancel_contended_or_done.set()
        return flock(fd, op)

    def cancel():
        nonlocal cancel_thread
        cancel_thread = get_ident()
        try:
            cancel_worker._owner_signed_in({"data": {"user_id": owner_id}})
        finally:
            cancel_contended_or_done.set()

    unsubscribe = legacy.gw.events.subscribe("legacy.claim.*", lambda event: log.append(event["type"]))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            def deliver(owner, event, data, *args, **kwargs):
                if event == f"legacy.claim.{notice}":
                    cancels.append(pool.submit(cancel))
                    assert cancel_contended_or_done.wait(timeout=10)
                return tell(owner, event, data, *args, **kwargs)

            monkeypatch.setattr(fcntl, "flock", observe_lock)
            monkeypatch.setattr(legacy, "tell", deliver)
            if notice == "confirmed":
                client = TestClient(rc.app)
                assert client.post(f"/v1/legacy/claims/{cid}/confirm", headers=other.auth).status_code == 200
            else:
                legacy.tick()
            assert len(cancels) == 1
            cancels[0].result(timeout=10)
    finally:
        unsubscribe()
    assert legacy._claim(cid).state == "cancelled"
    assert log[-2:] == [f"legacy.claim.{notice}", "legacy.claim.cancelled"]
