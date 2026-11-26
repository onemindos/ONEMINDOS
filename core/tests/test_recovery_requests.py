# SPDX-License-Identifier: Apache-2.0
"""Contact-assisted recovery and the remote wait (gateway permissions design PR 25e, §3.13 tests 3, 4, 6, 10).

Each test fails without the change: starting a recovery, the matching number, the 8-digit code, the
tries and expiry, the 24/72-hour wait, cancelling from every side, the remote path's second factor and
wait, finishing with a new passkey, and the notices."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.identity.crypto import new_id, totp_code
from onemind_core.recovery.requests import MAX_TRIES, code_for, vouch_payload
from recovery_support import ContactPhone, invite_and_accept, owner_with_passkey
from test_identity import PASSWORD, SoftAuthenticator, audit_events, csrf, id_settings

DAY = 86400


@pytest.fixture
def rc(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as c:
        yield c


def ready_contact(rc, clock, name="Ana", days=7) -> ContactPhone:
    phone = invite_and_accept(rc, name)
    clock.advance(days * DAY + 1)
    return phone


def start(rc, path="contact", **body):
    return TestClient(rc.app).post("/v1/auth/recovery", json={"path": path, "username": "zeus", **body})


def as_starter(rc, started: dict) -> TestClient:
    c = TestClient(rc.app)
    c.headers["Authorization"] = f"Bearer {started['one_time']['request_token']}"
    return c


def vouch(rc, phone: ContactPhone, request_id: str, picked: str | None = None):
    c = TestClient(rc.app)
    pending = c.get("/v1/recovery/requests", headers=phone.auth)
    assert pending.status_code == 200, pending.text
    item = next(i for i in pending.json() if i["id"] == request_id)
    pick = picked if picked is not None else item["choices"][0]
    return c.post(f"/v1/recovery/requests/{request_id}/vouch", headers=phone.auth,
                  json={"picked": pick, "signature": phone.sign(vouch_payload(request_id, pick, item["challenge"]))}), item


def test_a_contact_confirms_online_by_the_matching_number_then_the_24_hour_wait(rc, clock, settings):
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    clock.advance(8 * DAY)  # the owner's passkey was last used more than 7 days ago: no liveness raise
    r = start(rc)
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["state"] == "awaiting_contact" and len(s["matching_number"]) == 2 and s["request_code"].count("-") == 2
    # The contact sees three numbers, one of them the owner's, the same on every poll; never the request code.
    pending = TestClient(rc.app).get("/v1/recovery/requests", headers=phone.auth).json()[0]
    assert s["matching_number"] in pending["choices"] and len(set(pending["choices"])) == 3
    assert "request_code" not in pending and "matching_number" not in pending
    r, _ = vouch(rc, phone, s["id"], picked=s["matching_number"])
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["state"] == "waiting" and v["vouch_method"] == "online" and v["wait_hours"] == 24 and not v["liveness_raised"]
    # Finishing before the wait is over is refused; nobody can shorten it.
    starter = as_starter(rc, s)
    assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete/options").status_code == 409
    events = [e["event"] for e in audit_events(settings)]
    assert "recovery.request.started" in events and "recovery.request.vouched" in events


def test_the_wait_rises_to_72_hours_when_a_strong_key_was_used_in_the_last_7_days(rc, clock):
    key = owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    # The owner signs in with the passkey (a strong key in use): the account looks alive.
    opts = rc.post("/v1/auth/login/options").json()
    assert rc.post("/v1/auth/login", json={"passkey": key.assert_(opts["publicKey"]["challenge"])}).status_code == 200
    s = start(rc).json()
    v, _ = vouch(rc, phone, s["id"], picked=s["matching_number"])
    assert v.json()["wait_hours"] == 72 and v.json()["liveness_raised"] is True


def test_wrong_numbers_and_wrong_codes_close_the_request_after_three_tries(rc, clock):
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    s = start(rc).json()
    wrong = next(n for n in TestClient(rc.app).get("/v1/recovery/requests", headers=phone.auth).json()[0]["choices"]
                 if n != s["matching_number"])
    r, _ = vouch(rc, phone, s["id"], picked=wrong)
    assert r.status_code == 422 and r.json()["reason"] == "wrong_answer"
    starter = as_starter(rc, s)
    assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/code", json={"code": "00000000"}).status_code == 422
    r = starter.post(f"/v1/auth/recovery/requests/{s['id']}/code", json={"code": "11111111"})
    assert r.status_code == 409 and r.json()["reason"] == "request_closed"
    assert starter.get(f"/v1/auth/recovery/requests/{s['id']}").json()["state"] == "failed"
    # Even the right number does nothing now.
    r = TestClient(rc.app).post(f"/v1/recovery/requests/{s['id']}/vouch", headers=phone.auth,
                                json={"picked": s["matching_number"], "signature": phone.sign(b"x")})
    assert r.status_code in (401, 409)


def test_the_8_digit_code_works_offline_and_only_for_its_own_request(rc, clock):
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    s = start(rc).json()
    starter = as_starter(rc, s)
    # A code computed for another request id (or another request code) is refused.
    another_request = new_id("rr")
    other = code_for(phone.secret, another_request, s["request_code"])
    assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/code", json={"code": other}).status_code == 422
    good = code_for(phone.secret, s["id"], s["request_code"])
    r = starter.post(f"/v1/auth/recovery/requests/{s['id']}/code", json={"code": good[:4] + " " + good[4:]})
    assert r.status_code == 200 and r.json()["vouch_method"] == "code" and r.json()["state"] == "waiting"


def test_an_expired_request_a_cooling_off_contact_and_a_second_start_the_same_day_are_refused(rc, clock):
    owner_with_passkey(rc)
    early = invite_and_accept(rc, "Ben")  # accepted now: still cooling off
    assert start(rc).status_code == 409  # no usable contact yet (one answer for every reason)
    assert TestClient(rc.app).get("/v1/recovery/requests", headers=early.auth).status_code == 409
    clock.advance(7 * DAY + 1)
    s = start(rc).json()
    clock.advance(15 * 60 + 1)
    starter = as_starter(rc, s)
    assert starter.get(f"/v1/auth/recovery/requests/{s['id']}").json()["state"] == "expired"
    assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/code", json={"code": "12345678"}).status_code == 409
    r = start(rc)
    assert r.status_code == 429 and r.json()["reason"] == "one_a_day"
    clock.advance(DAY)
    assert start(rc).status_code == 201


def test_any_owner_session_any_contact_or_the_starter_can_cancel(rc, clock):
    owner_with_passkey(rc)
    ana = ready_contact(rc, clock, "Ana", days=0)
    ben = invite_and_accept(rc, "Ben")
    clock.advance(7 * DAY + 1)
    # Another contact (Ben) stops the recovery Ana confirmed.
    s = start(rc).json()
    vouch(rc, ana, s["id"], picked=s["matching_number"])
    r = TestClient(rc.app).post(f"/v1/recovery/requests/{s['id']}/cancel", headers=ben.auth)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    # An owner token (no fresh passkey needed: L0) cancels; so does the starter's own token.
    clock.advance(DAY)
    s = start(rc).json()
    listed = TestClient(rc.app).get("/v1/auth/recovery", headers=OWNER).json()
    assert [x["id"] for x in listed] == [s["id"]] and "request_code" not in listed[0]
    r = TestClient(rc.app).post(f"/v1/auth/recovery/requests/{s['id']}/cancel", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    clock.advance(DAY)
    s = start(rc).json()
    assert as_starter(rc, s).post(f"/v1/auth/recovery/requests/{s['id']}/cancel").json()["state"] == "cancelled"


def test_removing_the_contact_who_confirmed_stops_the_wait(rc, clock):
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    s = start(rc).json()
    vouch(rc, phone, s["id"], picked=s["matching_number"])
    TestClient(rc.app).post("/v1/recovery/contact/resign", headers=phone.auth)
    r = as_starter(rc, s).get(f"/v1/auth/recovery/requests/{s['id']}").json()
    assert r["state"] == "cancelled" and r["end_reason"] == "contact_ended"


def test_after_the_wait_the_starter_enrols_a_passkey_sets_a_password_and_gets_a_session(rc, clock, settings):
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    s = start(rc).json()
    vouch(rc, phone, s["id"], picked=s["matching_number"])
    clock.advance(24 * 3600 + 1)
    starter = as_starter(rc, s)
    opts = starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete/options")
    assert opts.status_code == 200, opts.text
    new_key = SoftAuthenticator()
    r = starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete",
                     json={"credential": new_key.register(opts.json()), "label": "new phone",
                           "new_password": "a brand new passphrase", "client": "cli"})
    assert r.status_code == 200, r.text
    assert r.json()["access_token"].startswith("om_ses_")
    # The old browser session is signed out by the password reset; the new password and passkey work.
    assert rc.get("/v1/me").status_code == 401
    fresh = TestClient(rc.app)
    assert fresh.post("/v1/auth/login", json={"username": "zeus", "password": "a brand new passphrase"}).status_code == 200
    labels = [k["label"] for k in fresh.get("/v1/auth/passkeys").json()]
    assert "new phone" in labels
    # It cannot be finished twice.
    assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete", json={"new_password": "x" * 20}).status_code == 409
    events = [e["event"] for e in audit_events(settings)]
    assert "recovery.request.completed" in events


def test_remote_recovery_needs_more_than_a_password_waits_72_hours_and_only_adds_a_key(rc, clock):
    owner_with_passkey(rc)
    # A password alone is refused, even with the wait.
    r = start(rc, "remote", password=PASSWORD)
    assert r.status_code == 401 and r.json()["reason"] == "second_factor_required"
    secret = rc.post("/v1/auth/totp/setup", headers=csrf(rc)).json()["one_time"]["secret"]
    step = int(clock.now.timestamp() // 30)
    assert rc.post("/v1/auth/totp/confirm", headers=csrf(rc), json={"code": totp_code(secret, step)}).status_code == 204
    clock.advance(30)
    r = start(rc, "remote", password=PASSWORD, totp=totp_code(secret, step + 1))
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["state"] == "waiting" and s["wait_hours"] == 72 and s["matching_number"] is None
    starter = as_starter(rc, s)
    clock.advance(71 * 3600)
    assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete/options").status_code == 409
    clock.advance(3600 + 1)
    assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete",
                        json={"new_password": "another passphrase"}).json()["reason"] == "password_not_allowed"
    opts = starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete/options").json()
    r = starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete",
                     json={"credential": SoftAuthenticator().register(opts), "client": "cli"})
    assert r.status_code == 200, r.text


def test_the_owner_chooses_the_waits_and_shortening_needs_the_step_up(rc, clock):
    owner_with_passkey(rc)
    r = rc.put("/v1/auth/recovery/settings", json={"contact_wait_hours": 72, "remote_wait_hours": 168}, headers=csrf(rc))
    assert r.status_code == 200 and r.json()["values"]["remote_wait_hours"] == 168
    assert rc.put("/v1/auth/recovery/settings", json={"remote_wait_hours": 100}, headers=csrf(rc)).status_code == 422
    clock.advance(301)
    r = rc.put("/v1/auth/recovery/settings", json={"contact_wait_hours": 24}, headers=csrf(rc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"


def test_every_contact_and_owner_hears_of_the_recovery_and_reminders_during_the_wait(rc, clock):
    owner_with_passkey(rc)
    assert rc.put("/v1/auth/recovery/settings", json={"contact_wait_hours": 72}, headers=csrf(rc)).status_code == 200
    ana = ready_contact(rc, clock, "Ana", days=0)
    ben = invite_and_accept(rc, "Ben")
    clock.advance(7 * DAY + 1)
    s = start(rc).json()
    vouch(rc, ana, s["id"], picked=s["matching_number"])
    rec = rc.app.state.recoveries
    assert rec.tick() == 0
    clock.advance(DAY + 1)
    assert rec.tick() == 1 and rec.tick() == 0  # day 1, once
    clock.advance(DAY)
    assert rec.tick() == 1  # day 2
    clock.advance(DAY - 3600 + 5)
    assert rec.tick() == 1  # the last hour
    seen = [n["event"] for n in TestClient(rc.app).get("/v1/recovery/contact/notices", headers=ben.auth).json()]
    assert {"recovery.request.started", "recovery.request.vouched", "recovery.request.reminder"} <= set(seen)


def test_a_contact_cannot_start_a_recovery_or_see_another_owners(rc, clock):
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    r = TestClient(rc.app).post("/v1/recovery/requests", headers=phone.auth, json={"path": "contact"})
    assert r.status_code in (403, 405)
    s = start(rc).json()
    r = TestClient(rc.app).post(f"/v1/recovery/requests/{s['id']}/vouch", headers=phone.auth,
                                json={"picked": s["matching_number"], "signature": ContactPhone().sign(b"x")})
    assert r.status_code == 401 and r.json()["reason"] == "signature_invalid"


def test_a_cancel_that_lands_while_finishing_leaves_the_credentials_unchanged(rc, clock):
    """The claim (waiting -> completed) runs first, in the same transaction as the writes: a cancel just
    before it means nothing is written, not "cancelled but the password changed"."""
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    s = start(rc).json()
    vouch(rc, phone, s["id"], picked=s["matching_number"])
    clock.advance(24 * 3600 + 1)
    rec = rc.app.state.recoveries
    real_ready = rec._ready

    def ready_then_cancel(row):
        real_ready(row)  # the checks pass, then an owner's cancel lands before the claim
        rec._cancel(row, "usr_owner")

    rec._ready = ready_then_cancel
    try:
        r = as_starter(rc, s).post(f"/v1/auth/recovery/requests/{s['id']}/complete",
                                   json={"new_password": "a brand new passphrase"})
    finally:
        rec._ready = real_ready
    assert r.status_code == 409 and r.json()["reason"] == "not_waiting"
    assert as_starter(rc, s).get(f"/v1/auth/recovery/requests/{s['id']}").json()["state"] == "cancelled"
    # No session was revoked, the new password does not work and the old one still does.
    from onemind_core.identity.models import SessionRow
    with rec.db.session() as db:
        assert db.query(SessionRow).filter(SessionRow.revoked_at.is_not(None)).count() == 0
    fresh = TestClient(rc.app)
    assert fresh.post("/v1/auth/login", json={"username": "zeus", "password": "a brand new passphrase"}).status_code == 401
    assert TestClient(rc.app).post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD}).status_code == 200


def test_tries_are_counted_atomically_even_from_a_stale_read(rc, clock):
    """Two wrong answers that both read tries=0 (parallel requests) still count as two tries."""
    owner_with_passkey(rc)
    ready_contact(rc, clock)
    s = start(rc).json()
    rec = rc.app.state.recoveries
    stale = rec._get(s["id"])
    for _ in range(MAX_TRIES - 1):
        assert rec._one_try(stale, "wrong").reason == "wrong_answer"  # same stale row object each time
    err = rec._one_try(stale, "wrong")
    assert err.reason == "request_closed"
    assert rec._get(s["id"]).state == "failed" and rec._get(s["id"]).tries == MAX_TRIES
    assert rec._one_try(stale, "wrong").reason == "not_awaiting"  # a closed request takes no more tries


def test_the_request_token_and_the_8_digit_code_never_reach_the_audit_events_or_notices(rc, clock, settings):
    owner_with_passkey(rc)
    phone = ready_contact(rc, clock)
    rec = rc.app.state.recoveries
    published: list[str] = []
    real_publish = rec.gw.events.publish_event

    def capture(*a, **kw):
        published.append(json.dumps([a, kw], default=str))
        return real_publish(*a, **kw)

    rec.gw.events.publish_event = capture
    try:
        s = start(rc).json()
        token = s["one_time"]["request_token"]
        starter = as_starter(rc, s)
        assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/code", json={"code": "00000000"}).status_code == 422
        good = code_for(phone.secret, s["id"], s["request_code"])
        assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/code", json={"code": good}).status_code == 200
        clock.advance(24 * 3600 + 1)
        assert starter.post(f"/v1/auth/recovery/requests/{s['id']}/complete",
                            json={"new_password": "a brand new passphrase"}).status_code == 200
    finally:
        rec.gw.events.publish_event = real_publish
    assert token.startswith("omr_") and len(good) == 8
    audit = Path(settings.audit_path).read_text()
    notices = json.dumps(TestClient(rc.app).get("/v1/recovery/contact/notices", headers=phone.auth).json())
    events = "\n".join(published)
    assert published, "the flow publishes events"
    for secret in (token, token[len("omr_"):], good, s["request_code"], "a brand new passphrase"):
        assert secret not in audit and secret not in events and secret not in notices


# ---- cancel against complete: the state and the notice always agree (Opus review round 2, #1197) --------

def _waiting_request(rc, clock) -> tuple[str, str]:
    """A contact-path request whose wait is already over, written straight into the table (so a test can
    make many of them without the one-a-day rule). Returns (request id, the starter's token)."""
    import secrets as _secrets

    from sqlalchemy import select as _select

    from onemind_core.identity.models import UserRow
    from onemind_core.recovery.contacts import token_hash
    from onemind_core.recovery.requests import REQUEST_TOKEN_PREFIX, RequestRow

    rec = rc.app.state.recoveries
    owner = rec.ident.repo.one(_select(UserRow).where(UserRow.username == "zeus"))
    token = REQUEST_TOKEN_PREFIX + _secrets.token_urlsafe(32)
    now = rec.now()
    row = RequestRow(id=new_id("rr"), owner_user_id=owner.id, path="contact", state="waiting", created_at=now,
                     vouched_at=now, vouch_method="code", wait_hours=24, liveness_raised=False,
                     not_before=now - timedelta(seconds=1), starter_token_hash=token_hash(token),
                     source="testclient", tries=0, notices_sent=["start", "vouched"])
    with rec.db.session.begin() as s:
        s.add(row)
    return row.id, token


def _record_endings(rec) -> list[tuple[str, str]]:
    """Wrap contacts.tell to record every (event, request id) the module sends."""
    import threading

    log: list[tuple[str, str]] = []
    lock = threading.Lock()
    real = rec.contacts.tell

    def tell(owner_id, event, data, *a, **kw):
        with lock:
            log.append((event, data.get("request_id")))
        return real(owner_id, event, data, *a, **kw)

    rec.contacts.tell = tell
    return log


def _endings_for(log, request_id) -> list[str]:
    return [e for e, rid in log if rid == request_id and e in ("recovery.request.completed", "recovery.request.cancelled")]


def _complete(rc, request_id, token, password):
    c = TestClient(rc.app)
    c.headers["Authorization"] = f"Bearer {token}"
    return c.post(f"/v1/auth/recovery/requests/{request_id}/complete", json={"new_password": password})


def _signs_in(rc, password) -> bool:
    return TestClient(rc.app).post("/v1/auth/login", json={"username": "zeus", "password": password}).status_code == 200


def test_a_cancel_read_before_a_completion_cannot_overwrite_it(rc, clock):
    """The reviewer's interleaving: the cancel reads `waiting`, complete() claims and commits, then the
    cancel writes. The request stays `completed`, the cancel answers `completed`, no "cancelled" notice."""
    owner_with_passkey(rc)
    rec = rc.app.state.recoveries
    log = _record_endings(rec)
    rid, token = _waiting_request(rc, clock)
    stale = rec._get(rid)
    assert stale.state == "waiting"
    assert _complete(rc, rid, token, "a brand new passphrase").status_code == 200
    answer = rec._cancel(stale, "usr_owner")  # the late cancel, on its stale row
    assert answer["state"] == "completed"
    assert rec._get(rid).state == "completed" and rec._get(rid).end_reason == "completed"
    assert _endings_for(log, rid) == ["recovery.request.completed"]
    assert _signs_in(rc, "a brand new passphrase")


def test_a_cancel_that_commits_first_wins_and_the_completion_writes_nothing(rc, clock):
    owner_with_passkey(rc)
    rec = rc.app.state.recoveries
    log = _record_endings(rec)
    rid, token = _waiting_request(rc, clock)
    assert rec._cancel(rec._get(rid), "usr_owner")["state"] == "cancelled"
    r = _complete(rc, rid, token, "a brand new passphrase")
    assert r.status_code == 409
    assert rec._get(rid).state == "cancelled"
    assert _endings_for(log, rid) == ["recovery.request.cancelled"]
    assert not _signs_in(rc, "a brand new passphrase") and _signs_in(rc, PASSWORD)
    # A second cancel of the ended request sends nothing more.
    rec._cancel(rec._get(rid), "usr_owner")
    rec._cancel(rec._fresh(rec._get(rid)), "usr_other")
    assert _endings_for(log, rid) == ["recovery.request.cancelled"]


def test_an_expiry_or_a_contact_ending_never_overwrites_a_completion(rc, clock):
    """The other enders are conditional too: _end on a stale row of a completed request changes nothing."""
    owner_with_passkey(rc)
    rec = rc.app.state.recoveries
    log = _record_endings(rec)
    rid, token = _waiting_request(rc, clock)
    stale = rec._get(rid)
    assert _complete(rc, rid, token, "a brand new passphrase").status_code == 200
    for state, reason in (("cancelled", "contact_ended"), ("expired", "no_contact_in_time"), ("failed", "too_many_tries")):
        assert rec._end(stale, state, reason, None).state == "completed"
    assert rec._set(stale, ("waiting",), notices_sent=["tampered"]) is False
    assert rec._get(rid).state == "completed" and rec._get(rid).notices_sent == ["start", "vouched"]
    assert _endings_for(log, rid) == ["recovery.request.completed"]


def test_cancel_and_complete_run_truly_at_once_and_the_state_and_notice_always_agree(rc, clock):
    """Two threads, two database sessions (two PostgreSQL connections when ONEMIND_TEST_DB_URL is set),
    released together by a barrier, many rounds with jitter on both sides. Whatever the order: exactly one
    ending notice, and it matches the final state, the HTTP answers and whether the new password works."""
    import random as _random
    import threading
    import time

    owner_with_passkey(rc)
    rec = rc.app.state.recoveries
    log = _record_endings(rec)
    rng = _random.Random(1197)
    outcomes = []
    for n in range(12):
        rid, token = _waiting_request(rc, clock)
        stale = rec._get(rid)  # the cancel's earlier read, as in a real request
        password = f"round {n} brand new passphrase"
        barrier = threading.Barrier(2)
        got: dict = {}
        delays = (rng.uniform(0, 0.05), rng.uniform(0, 0.4))

        def finish():
            barrier.wait()
            time.sleep(delays[0])
            got["complete"] = _complete(rc, rid, token, password).status_code

        def cancel():
            barrier.wait()
            time.sleep(delays[1])
            got["cancel"] = rec._cancel(stale, "usr_owner")["state"]

        threads = [threading.Thread(target=finish), threading.Thread(target=cancel)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert not any(t.is_alive() for t in threads)
        final = rec._get(rid).state
        endings = _endings_for(log, rid)
        assert final in ("completed", "cancelled"), final
        assert endings == [f"recovery.request.{final}"], (final, endings)
        assert got["cancel"] == final, got
        assert got["complete"] == (200 if final == "completed" else 409), got
        assert _signs_in(rc, password) is (final == "completed")
        outcomes.append(final)
    assert len(outcomes) == 12
