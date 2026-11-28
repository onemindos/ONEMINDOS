# SPDX-License-Identifier: Apache-2.0
"""#702: device-bound approver keys. A phone's P-256 key signs approve-options' device_payload; the
gateway checks action, plan, expiry, single use and revocation, and audits the device and key kind.
Destructive and actuate stay passkey-only until the founder agrees (F-2)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi.testclient import TestClient

from conftest import OWNER, action_body
from onemind_core.actions import FeatureAction
from onemind_core.app import create_app
from onemind_core.auth import Principal
from onemind_core.executors import ExecResult
from onemind_core.identity.crypto import b64url
from test_identity import (
    LOCAL_PEER,
    PASSWORD,
    SoftAuthenticator,
    audit_events,
    csrf,
    enrol,
    id_settings,
    new_session_client,
    register_passkey,
    setup_owner,
    stepped,
)


class PhoneKey:
    """The phone side: a P-256 key in the keystore that signs the device_payload (SHA256withECDSA)."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())

    @property
    def spki(self) -> str:
        return b64url(self.key.public_key().public_bytes(serialization.Encoding.DER,
                                                         serialization.PublicFormat.SubjectPublicKeyInfo))

    def sign(self, payload: str, raw: bool = False) -> str:
        der = self.key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
        if not raw:
            return b64url(der)
        r, s = decode_dss_signature(der)
        return b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


@pytest.fixture
def idc(settings, clock, executor):
    with TestClient(create_app(id_settings(settings), clock=clock, executor=executor),
                    client=LOCAL_PEER) as c:
        yield c


def ready(c: TestClient) -> SoftAuthenticator:
    """An owner with a passkey; registering it is a fresh passkey proof on this session."""
    setup_owner(c)
    key = SoftAuthenticator()
    register_passkey(c, key)
    return key


def add_key(c: TestClient, phone: PhoneKey, label="Pixel 9", kind="hardware-reported"):
    """Adding an approver key is an L2 row (an authenticator): during the grace the owner confirms with
    the session's passkey plus the box's code (N-1 b), made in place by stepped()."""
    return stepped(c, "POST", "/v1/auth/approver-keys", json={"public_key": phone.spki, "label": label, "key_kind": kind})


def signed(c: TestClient, aid: str, key_id: str, phone: PhoneKey, raw: bool = False) -> dict:
    opts = c.post(f"/v1/actions/{aid}/approve-options", headers=csrf(c)).json()
    return {"device_signature": {"key_id": key_id, "challenge": opts["challenge"],
                                 "signature": phone.sign(opts["device_payload"], raw)}}


def new_action(c: TestClient, clock, key: str, app_id="uptime-kuma") -> str:
    r = c.post("/v1/actions", json=action_body(clock, app_id=app_id, key=key), headers=OWNER)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_a_valid_device_signature_approves_and_the_audit_names_device_and_kind(idc, clock, settings):
    ready(idc)
    phone = PhoneKey()
    r = add_key(idc, phone)
    assert r.status_code == 201, r.text
    key = r.json()
    assert key["key_kind"] == "hardware-reported" and key["label"] == "Pixel 9" and key["revoked_at"] is None
    aid = new_action(idc, clock, "k1")
    # Without anything signed, a passkey box still refuses (no bare "success" flag).
    assert idc.post(f"/v1/actions/{aid}/approve", headers=csrf(idc)).status_code == 401
    r = idc.post(f"/v1/actions/{aid}/approve", json=signed(idc, aid, key["key_id"], phone), headers=csrf(idc))
    assert r.status_code == 200 and r.json()["state"] in ("succeeded", "dispatched", "accepted"), r.text
    ok = [e for e in audit_events(settings) if e["event"] == "auth.step_up.succeeded"
          and e["data"]["payload"].get("action_id") == aid]
    want = {"approval": "device_key", "key_id": key["key_id"], "key_kind": "hardware-reported", "device": "Pixel 9"}
    assert ok and want.items() <= ok[-1]["data"]["payload"].items()
    assert idc.get("/v1/auth/approver-keys").json()[0]["last_used_at"] is not None
    # WebCrypto's raw r||s signature shape is accepted too.
    aid2 = new_action(idc, clock, "k2", app_id="whoami")
    r = idc.post(f"/v1/actions/{aid2}/approve", json=signed(idc, aid2, key["key_id"], phone, raw=True),
                 headers=csrf(idc))
    assert r.status_code == 200, r.text


def test_another_plan_a_replay_an_expired_challenge_or_a_revoked_key_is_refused(idc, clock):
    ready(idc)
    phone = PhoneKey()
    key_id = add_key(idc, phone).json()["key_id"]
    a1, a2 = new_action(idc, clock, "k1"), new_action(idc, clock, "k2", app_id="whoami")

    # A signature over another action's challenge and payload does not approve this one.
    other = signed(idc, a2, key_id, phone)
    r = idc.post(f"/v1/actions/{a1}/approve", json=other, headers=csrf(idc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    # This challenge with a signature over a different payload (another plan hash) fails.
    opts = idc.post(f"/v1/actions/{a1}/approve-options", headers=csrf(idc)).json()
    forged = opts["device_payload"].replace(opts["action_sha256"], "sha256:" + "0" * 64)
    body = {"device_signature": {"key_id": key_id, "challenge": opts["challenge"], "signature": phone.sign(forged)}}
    assert idc.post(f"/v1/actions/{a1}/approve", json=body, headers=csrf(idc)).status_code == 401
    # The client naming a plan other than the one signed is refused as a changed plan.
    good = signed(idc, a1, key_id, phone)
    r = idc.post(f"/v1/actions/{a1}/approve", headers=csrf(idc),
                 json={**good, "plan_sha256": "sha256:" + "1" * 64})
    assert r.status_code == 409 and r.json()["reason"] == "plan_changed"
    assert idc.get(f"/v1/actions/{a1}").json()["state"] == "awaiting_approval"

    # Replay: a used challenge never approves again, on the same action or another.
    good = signed(idc, a1, key_id, phone)
    assert idc.post(f"/v1/actions/{a1}/approve", json=good, headers=csrf(idc)).status_code == 200
    assert idc.post(f"/v1/actions/{a2}/approve", json=good, headers=csrf(idc)).status_code == 401

    # Expired: the challenge lives 120 s.
    late = signed(idc, a2, key_id, phone)
    clock.advance(121)
    assert idc.post(f"/v1/actions/{a2}/approve", json=late, headers=csrf(idc)).status_code == 401

    # Revoked: the phone was lost; its key no longer approves anything.
    fresh = signed(idc, a2, key_id, phone)
    assert idc.delete(f"/v1/auth/approver-keys/{key_id}", headers=csrf(idc)).status_code == 204
    r = idc.post(f"/v1/actions/{a2}/approve", json=fresh, headers=csrf(idc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    assert idc.get(f"/v1/actions/{a2}").json()["state"] == "awaiting_approval"
    assert idc.get("/v1/auth/approver-keys").json()[0]["revoked_at"] is not None
    # A wrong key's signature (another phone) fails too.
    stranger = PhoneKey()
    key2 = add_key(idc, stranger, label="Tablet").json()["key_id"]
    body = signed(idc, a2, key2, phone)  # signed by the revoked phone, sent under the tablet's key id
    assert idc.post(f"/v1/actions/{a2}/approve", json=body, headers=csrf(idc)).status_code == 401


def test_destructive_stays_passkey_only_until_f2(idc, clock, settings):
    ready(idc)
    phone = PhoneKey()
    key_id = add_key(idc, phone).json()["key_id"]
    svc = idc.app.state.actions
    done = lambda a, finish: finish(ExecResult("succeeded", "ok"))  # noqa: E731
    svc.register_type("test.disk.wipe", FeatureAction(risk="destructive", run=done, requesters=frozenset({"person"})))
    owner_p = Principal(id="person:owner", kind="person", role="owner")
    wipe, _ = svc.request_feature(owner_p, "test.disk.wipe", {"disk": "sdb"}, idempotency_key="w1",
                                  expires_at=clock.now + timedelta(minutes=10))
    body = signed(idc, wipe["id"], key_id, phone)
    r = idc.post(f"/v1/actions/{wipe['id']}/approve", json=body, headers=csrf(idc))
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    assert idc.get(f"/v1/actions/{wipe['id']}").json()["state"] == "awaiting_approval"
    assert any(e["event"] == "auth.step_up.required"
               and e["data"]["payload"].get("reason") == "device_key_not_allowed" for e in audit_events(settings))


def test_f2_setting_on_lets_a_device_key_approve_destructive(settings, clock, executor):
    s = id_settings(settings, approver_key_high_risk=True)
    with TestClient(create_app(s, clock=clock, executor=executor), client=LOCAL_PEER) as c:
        ready(c)
        # T3 is an L2 row; during the grace that is a passkey plus the box's code, which a phone key can't
        # send. The owner lowered T3 to L1 (N-3 a, an audited L2 change), so the F2 setting decides.
        from onemind_core.identity.models import VerificationLevelRow

        c.app.state.identity.repo.add(VerificationLevelRow(key="tier.T3", level="L1", updated_at=clock.now,
                                                           updated_by="person:owner"))
        phone = PhoneKey()
        key_id = add_key(c, phone).json()["key_id"]
        svc = c.app.state.actions
        svc.register_type("test.disk.wipe", FeatureAction(
            risk="destructive", run=lambda a, finish: finish(ExecResult("succeeded", "ok")),
            requesters=frozenset({"person"})))
        owner_p = Principal(id="person:owner", kind="person", role="owner")
        wipe, _ = svc.request_feature(owner_p, "test.disk.wipe", {"disk": "sdb"}, idempotency_key="w1",
                                      expires_at=clock.now + timedelta(minutes=10))
        r = c.post(f"/v1/actions/{wipe['id']}/approve", json=signed(c, wipe["id"], key_id, phone), headers=csrf(c))
        assert r.status_code == 200, r.text


def test_registering_needs_an_owner_session_with_a_fresh_passkey(idc, clock):
    setup_owner(idc)
    phone = PhoneKey()
    # A password session with no passkey proof cannot add an approver key.
    r = add_key(idc, phone)
    assert r.status_code == 401 and r.json()["reason"] == "step_up_required"
    register_passkey(idc, SoftAuthenticator())
    # A static owner token (no session) cannot either.
    assert idc.post("/v1/auth/approver-keys", headers=OWNER,
                    json={"public_key": phone.spki, "label": "Pixel", "key_kind": "software"}).status_code == 403
    # A non-owner cannot register one, even signed in.
    adult = enrol(idc, "adult", "ana")
    assert add_key(adult, PhoneKey()).status_code in (401, 403)
    # A fresh passkey sign-in alone is not enough (an authenticator is an L2 row: during the grace the box
    # confirms it too), and the passkey proof goes stale after step_up_s anyway.
    raw = {"public_key": phone.spki, "label": "Pixel", "key_kind": "software"}
    assert idc.post("/v1/auth/approver-keys", headers=csrf(idc), json=raw).status_code == 401
    clock.advance(301)
    assert idc.post("/v1/auth/approver-keys", headers=csrf(idc), json=raw).status_code == 401
    assert add_key(idc, phone).status_code == 201  # confirmed in place, at the box


def test_registration_refuses_bad_keys_duplicates_and_unverified_attestation(idc):
    ready(idc)
    phone = PhoneKey()
    assert add_key(idc, phone, kind="hardware-attested").json()["reason"] == "attestation_unverified"
    assert add_key(idc, phone, kind="tpm").status_code == 422
    ed = b64url(ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
    assert stepped(idc, "POST", "/v1/auth/approver-keys",
                   json={"public_key": ed, "label": "x", "key_kind": "software"}).status_code == 422
    p384 = b64url(ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
    assert stepped(idc, "POST", "/v1/auth/approver-keys",
                   json={"public_key": p384, "label": "x", "key_kind": "software"}).status_code == 422
    assert stepped(idc, "POST", "/v1/auth/approver-keys",
                   json={"public_key": "not a key", "label": "x", "key_kind": "software"}).status_code == 422
    assert add_key(idc, phone, label="   ").status_code == 422
    assert add_key(idc, phone, kind="software").status_code == 201
    assert add_key(idc, phone, label="Other").status_code == 409  # same key twice
    assert add_key(idc, PhoneKey()).json()["reason"] == "label_taken"  # one key per phone


def test_keys_are_per_person_and_only_the_owner_of_a_key_revokes_it(idc, clock):
    ready(idc)
    phone = PhoneKey()
    key_id = add_key(idc, phone).json()["key_id"]
    adult = enrol(idc, "adult", "ana")
    assert adult.get("/v1/auth/approver-keys").json() == []
    assert adult.delete(f"/v1/auth/approver-keys/{key_id}", headers=csrf(adult)).status_code == 404
    pw = new_session_client(idc)
    pw.post("/v1/auth/login", json={"username": "zeus", "password": PASSWORD})
    # Revoking takes power away, so a plain password session may do it (lost phone).
    assert pw.delete(f"/v1/auth/approver-keys/{key_id}", headers=csrf(pw)).status_code == 204
    assert pw.delete(f"/v1/auth/approver-keys/{key_id}", headers=csrf(pw)).status_code == 204


def test_both_a_passkey_and_a_device_signature_is_refused(idc, clock):
    key = ready(idc)
    phone = PhoneKey()
    key_id = add_key(idc, phone).json()["key_id"]
    aid = new_action(idc, clock, "k1")
    body = signed(idc, aid, key_id, phone)
    body["webauthn"] = key.assert_(body["device_signature"]["challenge"], flat=True)
    assert idc.post(f"/v1/actions/{aid}/approve", json=body, headers=csrf(idc)).status_code == 422


def test_openapi_lists_the_approver_key_routes(idc):
    spec = idc.get("/openapi.json").json()
    assert {"post", "get"} <= set(spec["paths"]["/v1/auth/approver-keys"])
    assert "delete" in spec["paths"]["/v1/auth/approver-keys/{key_id}"]
    assert "device_payload" in spec["components"]["schemas"]["ApprovalChallenge"]["properties"]
    assert "device_signature" in spec["components"]["schemas"]["onemind_core__routers__actions__ApproveBody"]["properties"]
