# SPDX-License-Identifier: Apache-2.0
"""Public signing trust changes only after an owner approves the exact key."""
from datetime import timedelta
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import pytest
from sqlalchemy import select

from conftest import AGENT, GUEST, OWNER, action_body
from onemind_core.plugins.key_models import KeyCandidateRow, SigningKeyRow
from onemind_core.plugins.owner_keys import parse_public_key
from test_plugin_credentials import approve

PATH = "/v1/plugin-trust/keys"


@pytest.fixture
def public():
    return ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def body(public, clock, key="key-enroll"):
    return {"public_key": public, "name": "Development signing key", "idempotency_key": key,
            "expires_at": (clock() + timedelta(minutes=10)).isoformat()}


def test_enrollment_and_revocation_wait_for_owner_approval(client, clock, public):
    r = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock))
    assert r.status_code == 202, r.text
    action = r.json()
    assert action["state"] == "awaiting_approval"
    assert client.get(PATH, headers=OWNER).json() == {"keys": []}
    fingerprint, canonical = parse_public_key(public)
    assert action["params"]["key_id"] == fingerprint and action["params"]["name"] == "Development signing key"
    assert "public_key" not in action["params"]
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=AGENT).status_code == 403
    assert approve(client, action["id"])["state"] == "succeeded"
    row = client.get(PATH, headers=OWNER).json()["keys"][0]
    assert row["public_key"] == canonical and row["id"] == fingerprint and row["active"]
    revoked = client.post(PATH + "/" + fingerprint + "/revoke", headers=OWNER,
                         json={k: v for k, v in body(public, clock, "key-revoke").items()
                               if k in {"idempotency_key", "expires_at"}})
    assert revoked.status_code == 202
    assert client.get(PATH, headers=OWNER).json()["keys"][0]["active"]
    assert approve(client, revoked.json()["id"])["state"] == "succeeded"
    assert client.get(PATH, headers=OWNER).json()["keys"][0]["active"] is False


@pytest.mark.parametrize("headers", [AGENT, GUEST, {}])
def test_nonowners_cannot_read_or_propose_trust(client, clock, public, headers):
    expected = 401 if not headers else 403
    assert client.get(PATH, headers=headers).status_code == expected
    assert client.post(PATH + "/requests", headers=headers, json=body(public, clock)).status_code == expected
    assert client.app.state.identity.repo.all(select(KeyCandidateRow)) == []


def test_private_key_never_enters_candidate_ledger_or_audit(client, clock, settings):
    private = ed25519.Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    before = client.get("/v1/actions", headers=OWNER).json()
    r = client.post(PATH + "/requests", headers=OWNER, json=body(private, clock))
    assert r.status_code == 422
    assert client.get("/v1/actions", headers=OWNER).json() == before
    assert client.app.state.identity.repo.all(select(KeyCandidateRow)) == []
    assert private.splitlines()[1] not in settings.audit_path.read_text()
    assert private.splitlines()[1] not in r.text


def test_idempotent_proposal_and_changed_payload_conflict(client, clock, public):
    payload = body(public, clock)
    first = client.post(PATH + "/requests", headers=OWNER, json=payload)
    second = client.post(PATH + "/requests", headers=OWNER, json=payload)
    assert first.status_code == second.status_code == 202 and first.json()["id"] == second.json()["id"]
    payload["name"] = "Different key label"
    assert client.post(PATH + "/requests", headers=OWNER, json=payload).status_code == 409


def test_expired_or_mutated_proposal_cannot_activate_trust(client, clock, public):
    r = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock))
    clock.advance(11 * 60)
    assert client.post(f"/v1/actions/{r.json()['id']}/approve", headers=OWNER).status_code == 409
    assert client.get(PATH, headers=OWNER).json() == {"keys": []}


def test_public_key_fingerprint_matches_canonical_spki(public):
    fingerprint, canonical = parse_public_key(public)
    key = serialization.load_pem_public_key(public.encode())
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    assert fingerprint == "sha256:" + hashlib.sha256(der).hexdigest()
    assert parse_public_key(canonical.replace("\n", "\r\n"))[0] == fingerprint


def test_generic_action_path_cannot_skip_owner_or_candidate_binding(client, clock, public):
    requested = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock)).json()
    req = action_body(clock, key="generic-enroll")
    req.update(type="plugin.key.enroll", params=requested["params"])
    assert client.post("/v1/actions", headers=AGENT, json=req).status_code == 403
    req["params"]["key_id"] = "sha256:" + "0" * 64
    assert client.post("/v1/actions", headers=OWNER, json=req).status_code == 409
    assert client.get(PATH, headers=OWNER).json() == {"keys": []}


def test_key_changes_require_real_action_bound_passkey_when_active(settings, clock, public):
    from conftest import make_client
    from test_identity import LOCAL_PEER, SoftAuthenticator, at_box, id_settings, register_passkey, setup_owner
    with make_client(id_settings(settings, require_passkey_approval=False), clock, peer=LOCAL_PEER) as client:
        setup_owner(client)
        authenticator = SoftAuthenticator()
        register_passkey(client, authenticator)
        action = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock)).json()
        route = f"/v1/actions/{action['id']}/approve"
        assert action["risk"] == "sensitive"
        assert client.post(route, headers=OWNER).status_code == 401
        assert client.post(route, headers=OWNER, json={"webauthn": {"fake": True}}).status_code == 401
        assert client.get(PATH, headers=OWNER).json() == {"keys": []}
        options = client.post(route + "-options", headers=OWNER).json()
        response = client.post(route, headers=OWNER,
                               json={"webauthn": authenticator.assert_(options["challenge"]), **at_box(client, options)})
        assert response.status_code == 200 and response.json()["state"] == "succeeded", response.text


def test_mutated_candidate_cannot_enroll_a_different_key(client, clock, public):
    action = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock)).json()
    candidate_id = action["params"]["candidate_id"]
    client.app.state.identity.repo.update(KeyCandidateRow, [KeyCandidateRow.id == candidate_id],
                                          {"name": "Changed after request"})
    assert client.post(f"/v1/actions/{action['id']}/approve", headers=OWNER).status_code == 409
    assert client.get(PATH, headers=OWNER).json() == {"keys": []}


def test_narrow_owner_token_cannot_use_enrollment_route(client, clock, public):
    from onemind_core.identity.crypto import new_secret, sha256_hex
    from onemind_core.identity.models import TokenRow, UserRow
    user = UserRow(id="narrow-owner-person", display_name="Fixture owner", role="owner", created_at=clock(), updated_at=clock())
    client.app.state.identity.repo.add(user)
    token = new_secret("pat")
    client.app.state.identity.repo.add(TokenRow(id="owner-narrow", prefix=token[:11], name="Narrow owner",
        hash=sha256_hex(token), kind="person", principal_id=user.id, owner_user_id=user.id, scopes=["actions:request:app.install"],
        source="api", created_by="owner", created_at=clock()))
    response = client.post(PATH + "/requests", headers={"Authorization": "Bearer " + token}, json=body(public, clock))
    assert response.status_code == 403
    assert client.app.state.identity.repo.all(select(KeyCandidateRow)) == []


def test_revocation_cannot_be_rolled_back_by_a_stale_enrollment(client, clock, public):
    """A2 filed while K is active must not re-activate K after K is revoked as compromised."""
    first = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock, "enroll-a1")).json()
    assert approve(client, first["id"])["state"] == "succeeded"
    stale = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock, "enroll-a2")).json()
    clock.advance(1)
    revoke = client.post(PATH + f"/{first['params']['key_id']}/revoke", headers=OWNER,
                         json={k: v for k, v in body(public, clock, "revoke-k").items()
                               if k in {"idempotency_key", "expires_at"}}).json()
    assert approve(client, revoke["id"])["state"] == "succeeded"
    clock.advance(1)
    refused = client.post(f"/v1/actions/{stale['id']}/approve", headers=OWNER)
    assert refused.status_code == 409, refused.text
    assert client.get(PATH, headers=OWNER).json()["keys"][0]["active"] is False
    clock.advance(1)  # a fresh proposal after the revocation is a deliberate new decision
    fresh = client.post(PATH + "/requests", headers=OWNER, json=body(public, clock, "enroll-a3")).json()
    assert approve(client, fresh["id"])["state"] == "succeeded"
    assert client.get(PATH, headers=OWNER).json()["keys"][0]["active"] is True


def test_proposal_lifetime_is_capped(client, clock, public):
    payload = body(public, clock)
    payload["expires_at"] = (clock() + timedelta(days=30)).isoformat()
    assert client.post(PATH + "/requests", headers=OWNER, json=payload).status_code == 422
