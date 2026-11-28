# SPDX-License-Identifier: Apache-2.0
"""Software WebAuthn authenticator shared by gateway and image tests."""

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from onemind_core.identity.crypto import b64url

ORIGIN, RP_ID = "http://localhost", "localhost"


class SoftAuthenticator:
    """A software passkey (ES256, attestation "none") so tests run the real WebAuthn verification."""

    def __init__(self, rp_id: str = RP_ID, origin: str = ORIGIN):
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = os.urandom(16)
        self.counter = 0

    def _client_data(self, typ: str, challenge: str) -> bytes:
        return json.dumps({"type": typ, "challenge": challenge, "origin": self.origin, "crossOrigin": False}).encode()

    def register(self, options: dict) -> dict:
        nums = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})
        auth_data = (hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x45]) + struct.pack(">I", 0)
                     + bytes(16) + struct.pack(">H", len(self.cred_id)) + self.cred_id + cose)
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        cd = self._client_data("webauthn.create", options["publicKey"]["challenge"])
        return {"id": b64url(self.cred_id), "rawId": b64url(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64url(cd), "attestationObject": b64url(att), "transports": ["internal"]}}

    def assert_(self, challenge: str, flat: bool = False) -> dict:
        self.counter += 1
        auth_data = hashlib.sha256(self.rp_id.encode()).digest() + bytes([0x05]) + struct.pack(">I", self.counter)
        cd = self._client_data("webauthn.get", challenge)
        sig = self.key.sign(auth_data + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        body = {"clientDataJSON": b64url(cd), "authenticatorData": b64url(auth_data), "signature": b64url(sig)}
        if flat:  # the §12.4 flat shape
            return {"id": b64url(self.cred_id), **body}
        return {"id": b64url(self.cred_id), "rawId": b64url(self.cred_id), "type": "public-key", "response": body}
