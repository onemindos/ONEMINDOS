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
    adult_view = adult.get("/v1/auth/legacy/claims")
    if adult_view.status_code == 200:  # the adult's session may have lapsed over 7 days
        assert adult_view.json()[0]["id"] == c["id"]
    else:
        assert adult_view.status_code == 401
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
    assert got["state"] == "granted", got
    return c


def test_an_owner_who_signs_in_after_the_grant_ends_it_and_the_export_refuses(rc, clock):
    """The owner was away (a trip), a claim was granted; the owner signs in again: the export ends at once."""
    owner_with_passkey(rc)
    put_home_file(rc, "letters.txt", b"to my family")
    phone, key = legacy_phone(rc)
    granted(rc, clock, phone, key)
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).status_code == 200
    assert TestClient(rc.app).post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200
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
    fresh = TestClient(rc.app)
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


def test_sign_in_and_tick_truly_at_once_always_end_cancelled_with_agreeing_notices(rc, clock):
    """Two threads (two database sessions; two PostgreSQL connections with ONEMIND_TEST_DB_URL), released
    together, many rounds with jitter. Whatever the order the claim ends `cancelled`; a grant notice is only
    ever followed by a cancel notice, and the last notice always matches the final state."""
    import random
    import threading
    import time

    owner_with_passkey(rc)
    owner_id = _owner_id(rc)
    phone, _key = legacy_phone(rc)
    legacy = rc.app.state.legacy_contacts
    log = _record_claim_notices(legacy)
    clock.advance(60)
    rng = random.Random(1208)
    orders = []
    for _ in range(12):
        cid = _due_claim(rc, phone.contact_id, owner_id)
        barrier = threading.Barrier(2)
        delays = (rng.uniform(0, 0.03), rng.uniform(0, 0.03))

        def grant(barrier=barrier, delays=delays):
            barrier.wait()
            time.sleep(delays[0])
            legacy.tick()

        def sign_in(barrier=barrier, delays=delays, owner_id=owner_id):
            barrier.wait()
            time.sleep(delays[1])
            legacy._owner_signed_in({"data": {"user_id": owner_id}})

        threads = [threading.Thread(target=grant), threading.Thread(target=sign_in)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert not any(t.is_alive() for t in threads)
        c = legacy._claim(cid)
        endings = _endings(log, cid)
        assert c.state == "cancelled", (c.state, endings)
        assert endings in (["cancelled"], ["granted", "cancelled"]), endings
        assert endings[-1] == c.state
        orders.append(tuple(endings))
    assert TestClient(rc.app).get("/v1/legacy/export", headers=phone.auth).status_code == 403


# ---- who accepted, and the second person (Opus review, #1208 non-blocking items) ------------------------

def _accept_outside(rc, name, client: TestClient, headers=None):
    r = add_legacy(rc, name)
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
    bearer = TestClient(rc.app)
    tok = bearer.post("/v1/auth/login", json={"username": "ben", "password": PASSWORD, "client": "cli"}).json()
    phone, _ = _accept_outside(rc, "B1", TestClient(rc.app), {"Authorization": f"Bearer {tok['access_token']}"})
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
    fresh = TestClient(rc.app)
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


def test_two_claims_at_once_leave_one_open_claim(rc, clock):
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
