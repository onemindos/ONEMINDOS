# SPDX-License-Identifier: Apache-2.0
"""Recovery contacts: invite, accept, verify (gateway permissions design PR 25d, §3.13 tests 3 and 5, D-028).

Each test fails without the change: the routes, the signed invite, the cooling-off, the 5-contact
limit, the household role check, the step-up to add, and the contact principal that reaches nothing
but its own routes."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.recovery.crypto import b64, unb64
from recovery_support import ContactPhone, add_contact, invite_and_accept, owner_with_passkey
from test_identity import audit_events, csrf, enrol, id_settings, setup_owner


@pytest.fixture
def rc(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor)) as c:
        yield c


def svc(c: TestClient):
    return c.app.state.recovery_contacts


def test_an_owner_invites_a_contact_who_accepts_and_counts_after_the_cooling_off(rc, clock, settings):
    owner_with_passkey(rc)
    r = add_contact(rc, "Ana", cooling_off_days=3)
    assert r.status_code == 201, r.text
    added = r.json()
    assert added["state"] == "invited" and added["cooling_off_days"] == 3
    assert added["box_key_fingerprint"].startswith("sha256:") and added["invite"].startswith("omri1.")
    # The invite carries the box key (to pin), the id, a nonce and the owner's name; never a secret of the box.
    payload = json.loads(unb64(added["invite"].split(".")[1]))
    assert set(payload) == {"typ", "box_key", "box_key_fingerprint", "invite_id", "nonce", "owner", "role", "expires_at"}

    phone = ContactPhone()
    r = phone.accept(rc, added["invite"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert phone.token.startswith("omc_") and len(phone.secret) == 32
    assert body["box_key_fingerprint"] == added["box_key_fingerprint"]

    contacts = rc.get("/v1/auth/recovery/contacts").json()
    assert contacts[0]["state"] == "cooling_off" and contacts[0]["key_fingerprint"] == phone.fingerprint
    assert svc(rc).usable(contacts[0]["id"].replace("rc_", "")) == []  # nobody's id, nothing usable
    owner_id = rc.get("/v1/me").json()["principal"]["id"]
    assert svc(rc).usable(owner_id) == []  # still cooling off
    me = TestClient(rc.app).get("/v1/recovery/contact", headers=phone.auth)
    assert me.status_code == 200 and me.json()["state"] == "cooling_off" and me.json()["owner_display_name"] == "Zeus"

    clock.advance(timedelta(days=3).total_seconds() + 1)
    assert [r.id for r in svc(rc).usable(owner_id)] == [phone.contact_id]
    assert TestClient(rc.app).get("/v1/recovery/contact", headers=phone.auth).json()["state"] == "active"
    # The secret and the token never reach the audit log.
    text = "\n".join(json.dumps(e) for e in audit_events(settings))
    assert phone.token not in text and b64(phone.secret) not in text and payload["nonce"] not in text
    events = [e["event"] for e in audit_events(settings)]
    assert "recovery.contact.invited" in events and "recovery.contact.accepted" in events


def test_a_bad_signature_another_contacts_invite_an_expired_or_a_reused_invite_is_refused(rc, clock):
    owner_with_passkey(rc)
    invite = add_contact(rc, "Ana").json()["invite"]
    head, body, sig = invite.split(".")
    phone = ContactPhone()

    # Tampered payload (another owner name): the signature no longer verifies.
    p = json.loads(unb64(body))
    p["owner"] = "Mallory"
    forged = ".".join((head, b64(json.dumps(p, sort_keys=True, separators=(",", ":")).encode()), sig))
    r = phone.accept(rc, forged)
    assert r.status_code == 422 and r.json()["reason"] == "invite_invalid"
    # A signature from another key (another box) is refused too.
    r = phone.accept(rc, ".".join((head, body, b64(bytes(64)))))
    assert r.status_code == 422 and r.json()["reason"] == "invite_invalid"
    # A proof signed by a key other than the one offered is refused.
    good = phone.accept_body(invite)
    good["public_key"] = ContactPhone().spki
    r = TestClient(rc.app).post(f"/v1/recovery/invites/{p['invite_id']}/accept", json=good)
    assert r.status_code == 422 and r.json()["reason"] == "proof_invalid"
    # The real invite works once; the second use is refused.
    assert phone.accept(rc, invite).status_code == 201
    r = ContactPhone().accept(rc, invite)
    assert r.status_code == 409 and r.json()["reason"] == "invite_used"
    # An invite nobody accepted for 7 days has expired.
    late = add_contact(rc, "Ben").json()["invite"]
    clock.advance(timedelta(days=7).total_seconds() + 1)
    r = ContactPhone().accept(rc, late)
    assert r.status_code == 409 and r.json()["reason"] == "invite_expired"


def test_at_most_five_contacts_and_a_withdrawn_invite_frees_a_place(rc):
    owner_with_passkey(rc)
    ids = [add_contact(rc, f"Person {i}").json()["id"] for i in range(5)]
    r = add_contact(rc, "Sixth")
    assert r.status_code == 422 and r.json()["reason"] == "too_many"
    assert rc.delete(f"/v1/auth/recovery/contacts/{ids[0]}", headers=csrf(rc)).json()["state"] == "removed"
    assert add_contact(rc, "Sixth").status_code == 201


def test_only_an_adult_of_the_household_may_be_a_household_contact(rc, clock):
    owner_with_passkey(rc)
    people = {}
    for role in ("adult", "teen", "child", "guest"):
        enrol(rc, role, f"{role}x")
    for u in rc.get("/v1/users").json():
        people[u["role"]] = u["id"]
    for role in ("teen", "child", "guest"):
        r = add_contact(rc, kind="household", household_user_id=people[role])
        assert r.status_code == 422 and r.json()["reason"] == "role_not_allowed", role
    r = add_contact(rc, kind="household", household_user_id=people["owner"])
    assert r.status_code == 422 and r.json()["reason"] == "self"
    r = add_contact(rc, kind="household", household_user_id=people["adult"])
    assert r.status_code == 201, r.text
    assert add_contact(rc, kind="household", household_user_id=people["adult"]).status_code == 409


def test_a_household_invite_is_accepted_only_from_that_adults_own_session(rc):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ana")
    other = enrol(rc, "adult", "ben")
    ana_id = adult.get("/v1/me").json()["principal"]["id"]
    added = add_contact(rc, kind="household", household_user_id=ana_id).json()
    assert added["display_name"] == "Ana"
    # Ana sees the invitation in her own session; Ben does not.
    assert [i["id"] for i in adult.get("/v1/auth/recovery/invitations").json()] == [added["id"]]
    assert other.get("/v1/auth/recovery/invitations").json() == []
    # Without a session, or from Ben's, the household invite is refused; from Ana's it works.
    assert ContactPhone().accept(rc, added["invite"]).status_code == 401
    assert ContactPhone().accept(rc, added["invite"], client=other).status_code == 403
    assert ContactPhone().accept(rc, added["invite"], client=adult).status_code == 201


def test_adding_needs_an_owner_session_and_the_passkey_step_up_removing_does_not(rc, clock):
    owner_with_passkey(rc)
    adult = enrol(rc, "adult", "ana")
    clock.advance(301)  # the passkey proof is older than step_up_s
    r = add_contact(rc, "Ana")
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    # A static owner token holds no session, an adult is not the owner.
    r = rc.post("/v1/auth/recovery/contacts", json={"kind": "outside", "display_name": "Ana"}, headers=OWNER)
    assert r.status_code == 403
    assert add_contact(adult, "Ben").status_code == 403
    assert adult.get("/v1/auth/recovery/contacts").status_code == 403


def test_removing_a_contact_is_l0_and_its_token_stops_at_once(rc, clock):
    owner_with_passkey(rc)
    phone = invite_and_accept(rc)
    clock.advance(600)  # no fresh passkey any more: removing still works
    r = rc.delete(f"/v1/auth/recovery/contacts/{phone.contact_id}", headers=csrf(rc))
    assert r.status_code == 200 and r.json()["state"] == "removed"
    assert TestClient(rc.app).get("/v1/recovery/contact", headers=phone.auth).status_code == 401
    assert rc.delete(f"/v1/auth/recovery/contacts/{phone.contact_id}", headers=csrf(rc)).status_code == 200
    assert rc.delete("/v1/auth/recovery/contacts/rc_none", headers=csrf(rc)).status_code == 404


def test_a_contact_may_resign_and_every_contact_hears_of_changes(rc, clock):
    owner_with_passkey(rc)
    first = invite_and_accept(rc, "Ana")
    second = invite_and_accept(rc, "Ben")
    seen = TestClient(rc.app).get("/v1/recovery/contact/notices", headers=first.auth).json()
    assert {"recovery.contact.accepted", "recovery.contact.invited"} <= {n["event"] for n in seen}
    assert all("household_user_id" not in n["data"] and "via" not in n["data"] for n in seen)
    clock.advance(1)
    r = TestClient(rc.app).post("/v1/recovery/contact/resign", headers=second.auth)
    assert r.status_code == 200 and r.json()["state"] == "resigned"
    assert TestClient(rc.app).get("/v1/recovery/contact", headers=second.auth).status_code == 401
    seen = TestClient(rc.app).get("/v1/recovery/contact/notices", headers=first.auth).json()
    assert seen[0]["event"] == "recovery.contact.resigned" and seen[0]["data"]["contact_id"] == second.contact_id
    assert [c["state"] for c in rc.get("/v1/auth/recovery/contacts").json()] == ["cooling_off", "resigned"]


def test_a_contact_principal_reaches_its_own_routes_and_nothing_else(rc, settings):
    """§3.13 test 5: the contact gets 403 on every data, settings, approval and export route."""
    owner_with_passkey(rc)
    phone = invite_and_accept(rc)
    bare = TestClient(rc.app)
    own = {"/v1/recovery/contact", "/v1/recovery/contact/notices", "/v1/recovery/contact/resign"}
    checked = 0
    for route in rc.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/v1/") or path in own or "/v1/recovery/invites/" in path:
            continue
        concrete = path.replace("{", "x").replace("}", "")
        for method in sorted((getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}):
            anon = bare.request(method, concrete, json={})
            if anon.status_code != 401 or "missing bearer token" not in anon.text:
                continue  # a public route (sign-in, the box name): no principal is asked for at all
            r = bare.request(method, concrete, headers=phone.auth, json={})
            assert r.status_code == 403, (method, path, r.status_code, r.text[:200])
            checked += 1
    assert checked > 100
    assert any(e["event"] == "authz.denied" and e["data"].get("reason") == "contact_policy"
               for e in audit_events(settings))
    # A person cannot use the contact routes either.
    assert rc.get("/v1/recovery/contact").status_code == 403


def test_waits_come_from_set_options_and_shortening_needs_the_step_up(rc, clock):
    owner_with_passkey(rc)
    got = rc.get("/v1/auth/recovery/settings").json()
    assert got["values"]["cooling_off_days"] == 7 and got["options"]["cooling_off_days"] == [3, 7, 14]
    assert rc.put("/v1/auth/recovery/settings", json={"cooling_off_days": 5}, headers=csrf(rc)).status_code == 422
    assert rc.put("/v1/auth/recovery/settings", json={"cooling_off_days": 14}, headers=csrf(rc)).status_code == 200
    clock.advance(301)
    # Longer is a tightening (L0); shorter loosens and needs a fresh passkey.
    r = rc.put("/v1/auth/recovery/settings", json={"cooling_off_days": 3}, headers=csrf(rc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    # A new contact takes the owner's default.
    clock.advance(-301)
    assert add_contact(rc, "Ana").json()["cooling_off_days"] == 14


def test_without_any_passkey_yet_the_owner_session_can_still_add_a_contact(rc):
    """The gateway's step-up applies once passkeys are active (F-2), as elsewhere; D-028's L2 comes with PR 11."""
    setup_owner(rc)
    assert add_contact(rc, "Ana").status_code == 201
