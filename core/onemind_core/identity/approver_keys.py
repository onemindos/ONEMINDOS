# SPDX-License-Identifier: Apache-2.0
"""Device-bound approver keys (#702): a P-256 key held by the owner's phone signs an approval.

The phone keeps the private key in its keystore (Android Keystore / StrongBox, iOS Secure Enclave)
behind a biometric prompt; the gateway keeps only the public key. Signing reuses the §12.4
approve-options challenge, so expiry and single use are the same rows a passkey uses. Pure
functions here; state and audit live in service.py.

Why a domain-separated payload rather than the bare challenge: the key may only ever produce a
signature that says "approve action X with plan Y", so a signature can never be lifted into
another protocol, and the phone can show exactly what it is signing.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from pydantic import BaseModel, Field

# hardware-attested: a verified attestation chain says the key never leaves secure hardware (needs
#   attestation verification, not built yet, so registration refuses it for now);
# hardware-reported: the phone app says the key is in secure hardware, unverified;
# software: the key lives in app storage.
KEY_KINDS = ("hardware-attested", "hardware-reported", "software")
KeyKind = Literal["hardware-attested", "hardware-reported", "software"]
PAYLOAD_TAG = "onemind-approve-v1"
MAX_ACTIVE_PER_USER = 10


class ApproverKeyError(ValueError):
    """The public key or signature is malformed or does not verify."""


class DeviceSignature(BaseModel):
    """An approver key's ECDSA P-256 / SHA-256 signature over approve-options' `device_payload`."""

    key_id: str = Field(max_length=40)
    challenge: str = Field(max_length=128, description="The approve-options challenge (base64url) that was signed.")
    signature: str = Field(max_length=200, description="base64url; ASN.1 DER (Android, iOS) or raw r||s (64 bytes).")


def _unb64(value: str) -> bytes:
    s = value.strip().replace("+", "-").replace("/", "_").rstrip("=")
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ApproverKeyError("not base64") from exc


def parse_public_key(value: str) -> tuple[bytes, str]:
    """(SubjectPublicKeyInfo DER, "sha256:<hex>" fingerprint) of a base64 P-256 public key."""
    der = _unb64(value)
    try:
        key = serialization.load_der_public_key(der)
    except (ValueError, TypeError) as exc:
        raise ApproverKeyError("public_key must be a SubjectPublicKeyInfo (DER, base64url)") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ApproverKeyError("public_key must be an EC P-256 key")
    canon = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return canon, "sha256:" + hashlib.sha256(canon).hexdigest()


def signing_payload(challenge: str, action_id: str, action_sha256: str, plan_sha256: str | None) -> bytes:
    """What the phone signs (UTF-8): tag, action id, action hash, plan hash ("-" when none), challenge."""
    return "\n".join((PAYLOAD_TAG, action_id, action_sha256, plan_sha256 or "-", challenge)).encode()


def verify(public_key_der: bytes, payload: bytes, signature: str) -> None:
    """Raises ApproverKeyError unless `signature` is a valid ECDSA SHA-256 signature of payload."""
    sig = _unb64(signature)
    key = serialization.load_der_public_key(public_key_der)
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ApproverKeyError("stored approver key is not an EC key")
    candidates = [sig]
    if len(sig) == 64:  # WebCrypto / raw r||s
        candidates.append(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")))
    for der in candidates:
        try:
            key.verify(der, payload, ec.ECDSA(hashes.SHA256()))
            return
        except (InvalidSignature, ValueError):
            continue
    raise ApproverKeyError("device signature does not verify")
