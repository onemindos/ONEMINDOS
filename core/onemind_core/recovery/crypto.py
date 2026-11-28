# SPDX-License-Identifier: Apache-2.0
"""The box's invite key, signed invites, the contact secret's seal and the contact key's proofs.

**Signed invite.** The box signs every contact invite with its own Ed25519 key, made on first use
next to the audit log (`recovery/invite.key`, 0600; the backups job key pattern). The invite text is
`omri1.<payload>.<signature>` (base64url). The payload carries the box's public key, so the contact's
app checks the signature and **pins** that key: a later request that claims to come from this box
must be signed by it. The payload also carries the invite id, a single-use nonce (the box keeps
only its hash), the owner's display name, the role and the expiry. It carries no data and no secret
that opens anything: the nonce can only accept this one invite, once, before it expires.

**Contact secret.** 32 random bytes made at accept time, given to the contact's phone once, and kept
on the box sealed with AES-256-GCM under `recovery/secret.key` (the contact id is the associated
data, so a row copied to another contact does not open). It powers the offline 8-digit code (25e).

**Proof of the contact key.** Every signature by a contact key is ECDSA P-256 / SHA-256 over a
domain-separated text (`onemind-recovery-...-v1`), so a signature can never be lifted into another
protocol (the approver-key rule, identity/approver_keys.py).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..backups.jobs import load_or_create_job_key

INVITE_PREFIX = "omri1"
INVITE_TAG = "onemind-recovery-invite-v1"
ACCEPT_TAG = "onemind-recovery-accept-v1"
MAX_INVITE_CHARS = 2000


class InviteError(ValueError):
    """An invite that is malformed or whose signature does not verify."""


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def unb64(s: str) -> bytes:
    s = (s or "").strip()
    try:
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    except (binascii.Error, ValueError) as exc:
        raise InviteError("not base64url") from exc


def nonce_hash(nonce: str) -> str:
    return hashlib.sha256(("recovery-invite\n" + nonce).encode()).hexdigest()


class BoxKey:
    """The box's Ed25519 invite key; `fingerprint` is sha256:<hex> of the raw public key."""

    def __init__(self, path: Path):
        self.path = path
        self._signer: Ed25519PrivateKey | None = None  # loaded (or made) on first use

    @property
    def key(self) -> Ed25519PrivateKey:
        if self._signer is None:
            self._signer = load_or_create_job_key(self.path)
        return self._signer

    @property
    def public_raw(self) -> bytes:
        return self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    @property
    def fingerprint(self) -> str:
        return "sha256:" + hashlib.sha256(self.public_raw).hexdigest()

    def sign_invite(self, *, invite_id: str, nonce: str, owner: str, role: str, expires_at: datetime) -> str:
        payload = {
            "typ": INVITE_TAG, "box_key": b64(self.public_raw), "box_key_fingerprint": self.fingerprint,
            "invite_id": invite_id, "nonce": nonce, "owner": owner, "role": role,
            "expires_at": expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        sig = self.key.sign(INVITE_TAG.encode() + b"\n" + body)
        return f"{INVITE_PREFIX}.{b64(body)}.{b64(sig)}"

    def open_invite(self, text: str) -> dict:
        """The payload of an invite this box signed. Raises InviteError otherwise."""
        if not isinstance(text, str) or len(text) > MAX_INVITE_CHARS:
            raise InviteError("not an invite")
        parts = text.strip().split(".")
        if len(parts) != 3 or parts[0] != INVITE_PREFIX:
            raise InviteError("not a OneMind recovery invite")
        body, sig = unb64(parts[1]), unb64(parts[2])
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise InviteError("invite payload is not JSON") from exc
        if not isinstance(payload, dict) or payload.get("typ") != INVITE_TAG:
            raise InviteError("not a OneMind recovery invite")
        if payload.get("box_key") != b64(self.public_raw):
            raise InviteError("this invite was signed by another box")
        try:
            Ed25519PublicKey.from_public_bytes(self.public_raw).verify(sig, INVITE_TAG.encode() + b"\n" + body)
        except (InvalidSignature, ValueError) as exc:
            raise InviteError("the invite signature does not verify") from exc
        return payload


def accept_payload(invite_id: str, nonce: str, key_fingerprint: str) -> bytes:
    """What the contact's new key signs to prove it holds the private half (proof of possession)."""
    return "\n".join((ACCEPT_TAG, invite_id, nonce_hash(nonce), key_fingerprint)).encode()


class Sealer:
    """AES-256-GCM under a 0600 key file made on first use (the CredentialStore pattern)."""

    def __init__(self, path: Path):
        self.path = path

    def _key(self) -> bytes:
        try:
            return bytes.fromhex(self.path.read_text().strip())
        except FileNotFoundError:
            pass
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        tmp = self.path.with_name(f".{self.path.name}.{secrets.token_hex(4)}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key.hex())
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp, self.path)  # atomic, and never replaces a key that already sealed secrets
        except FileExistsError:
            return bytes.fromhex(self.path.read_text().strip())
        finally:
            tmp.unlink(missing_ok=True)
        return key

    def derive(self, label: str) -> bytes:
        """A box-only subkey for `label` (HMAC of the key file's key): nobody holding a contact secret can compute it."""
        return hmac.new(self._key(), b"onemind-derive-v1:" + label.encode(), hashlib.sha256).digest()

    def seal(self, secret: bytes, aad: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._key()).encrypt(nonce, secret, aad.encode())

    def open(self, sealed: bytes, aad: str) -> bytes:
        try:
            return AESGCM(self._key()).decrypt(sealed[:12], sealed[12:], aad.encode())
        except (InvalidTag, ValueError) as exc:
            raise ValueError("sealed secret does not open") from exc
