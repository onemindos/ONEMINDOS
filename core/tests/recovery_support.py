# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for the recovery tests: a contact's phone and the owner's invite step."""

from __future__ import annotations

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from onemind_core.identity.approver_keys import parse_public_key
from onemind_core.identity.crypto import b64url
from onemind_core.recovery.crypto import accept_payload, unb64
from test_identity import SoftAuthenticator, csrf, register_passkey, setup_owner, stepped


class ContactPhone:
    """The contact's side: a P-256 key in the phone's keystore, then the token and secret it got."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.token: str | None = None
        self.secret: bytes | None = None
        self.contact_id: str | None = None

    @property
    def spki(self) -> str:
        return b64url(self.key.public_key().public_bytes(serialization.Encoding.DER,
                                                         serialization.PublicFormat.SubjectPublicKeyInfo))

    @property
    def fingerprint(self) -> str:
        return parse_public_key(self.spki)[1]

    def sign(self, payload: bytes) -> str:
        return b64url(self.key.sign(payload, ec.ECDSA(hashes.SHA256())))

    def accept_body(self, invite: str, label: str = "Ana's phone") -> dict:
        import json

        payload = json.loads(unb64(invite.split(".")[1]))
        proof = self.sign(accept_payload(payload["invite_id"], payload["nonce"], self.fingerprint))
        return {"invite": invite, "public_key": self.spki, "key_kind": "hardware-reported",
                "device_label": label, "proof": proof}

    def accept(self, c: TestClient, invite: str, client: TestClient | None = None):
        import json

        invite_id = json.loads(unb64(invite.split(".")[1]))["invite_id"]
        # The phone is not signed in to the box: a fresh client with no cookies, unless the test passes a
        # household adult's own session.
        r = (client or TestClient(c.app)).post(f"/v1/recovery/invites/{invite_id}/accept",
                                               json=self.accept_body(invite),
                                               headers=csrf(client) if client is not None else None)
        if r.status_code == 201:
            body = r.json()
            self.token = body["one_time"]["contact_token"]
            self.secret = unb64(body["one_time"]["contact_secret"])
            self.contact_id = body["contact_id"]
        return r

    @property
    def auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


def owner_with_passkey(c: TestClient) -> SoftAuthenticator:
    setup_owner(c)
    key = SoftAuthenticator()
    register_passkey(c, key)  # a fresh passkey proof on this session (the step-up)
    return key


def add_contact(c: TestClient, name: str = "Ana", **extra):
    """Add a contact as the owner at the box: adding one is L2 (D-028), so stepped() answers the named step-up
    with this session's passkey and, during the grace, the box's code."""
    body = {"kind": "outside", "display_name": name, **extra}
    return stepped(c, "POST", "/v1/auth/recovery/contacts", json=body)


def invite_and_accept(c: TestClient, name: str = "Ana", **extra) -> ContactPhone:
    r = add_contact(c, name, **extra)
    assert r.status_code == 201, r.text
    phone = ContactPhone()
    r = phone.accept(c, r.json()["invite"])
    assert r.status_code == 201, r.text
    return phone
