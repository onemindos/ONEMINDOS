# SPDX-License-Identifier: Apache-2.0
"""The box's secret-store key and what is derived from it (DEPLOYMENTS.md §7, BACKUPS.md §6.4).

One 256-bit **store key** lives in a file in the box key store (default
`$ONEMIND_DATA_DIR/custodian/secrets.key`, mode 0600 in a 0700 directory; or a systemd credential,
which systemd can seal to the TPM). Everything else is derived from it with HKDF-SHA256, so
backing up that one file (it travels in the restic `system` unit, BACKUPS.md §6.4) is enough:

| Purpose | HKDF info | Used for |
|---|---|---|
| storage | `onemind/app-secrets/aead/v1` | AES-256-GCM of each stored value; AAD binds app, Secret, key and version |
| sealed input | `onemind/app-secrets/x25519/v1` | the X25519 key pair browsers encrypt the form to (`GET /v1/secrets/public-key`) |
| fingerprint | `onemind/app-secrets/fingerprint/v1` | HMAC-SHA256 tag that shows a value changed without letting anyone guess it |

Why this is independent of LUKS: the values are ciphertext in the gateway database, its dumps,
its PostgreSQL server and its backups. A copy of the database alone reveals nothing; a stolen
disk without LUKS still needs the key file, which is a separate file with its own permissions
(and a TPM-sealed credential on the image).

**Sealed input** (contract §12.1, `"sealed": {"alg": "X25519-AES256GCM", "epk", "ct"}`):
the client makes an ephemeral X25519 key, `shared = X25519(eph, box)`,
`k = HKDF-SHA256(shared, salt = epk ‖ box_pub, info = "onemind sealed-input v1")`, and sends
`ct = nonce(12) ‖ AES-256-GCM(k, nonce, json, aad = context)`; `epk` and `ct` are base64url
without padding. `context` is `onemind/app-secrets/<app-id>`, so a sealed form for one app
cannot be replayed into another. WebCrypto implements every step (ui/src/secrets/seal.ts).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import stat
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SEALED_ALG = "X25519-AES256GCM"
SEALED_INFO = b"onemind sealed-input v1"
KEY_BYTES = 32
NONCE_BYTES = 12
MAX_SEALED_CT = 64 * 1024


class SealedInputError(ValueError):
    """The sealed input cannot be opened. The message never contains any part of the plaintext."""


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64u(text: str) -> bytes:
    if not isinstance(text, str) or len(text) > 2 * MAX_SEALED_CT:
        raise SealedInputError("not base64url text")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError):
        raise SealedInputError("not base64url text") from None


def _hkdf(ikm: bytes, info: bytes, salt: bytes | None = None, length: int = 32) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _raw_public(pub: X25519PublicKey) -> bytes:
    return pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


class StoreKey:
    """The secret-store key. There is no method that returns the key bytes."""

    def __init__(self, master: bytes):
        if len(master) != KEY_BYTES:
            raise ValueError("the secret-store key must be 32 bytes")
        self._aead = AESGCM(_hkdf(master, b"onemind/app-secrets/aead/v1"))
        self._fp_key = _hkdf(master, b"onemind/app-secrets/fingerprint/v1")
        self._x25519 = X25519PrivateKey.from_private_bytes(_hkdf(master, b"onemind/app-secrets/x25519/v1"))
        self.public_key = _raw_public(self._x25519.public_key())
        self.key_id = "sk_" + hashlib.sha256(self.public_key).hexdigest()[:16]

    def __repr__(self) -> str:  # never the key
        return f"StoreKey({self.key_id})"

    # ---- loading -----------------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path, *, create: bool = True) -> "StoreKey":
        """Read the key file; create it (0600 in a 0700 directory) on first start when allowed.

        An existing key is never overwritten. A key file that group or others can read is
        refused, so a wrong umask or a careless copy stops the gateway instead of leaking.
        """
        if not path.exists():
            if not create:
                raise FileNotFoundError(f"secret-store key {path} does not exist")
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # O_EXCL: never overwrite
            with os.fdopen(fd, "w") as fh:
                fh.write(os.urandom(KEY_BYTES).hex() + "\n")
        mode = path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise PermissionError(
                f"secret-store key {path} must not be readable by group or others (mode {oct(mode & 0o777)})"
            )
        raw = path.read_bytes()
        text = raw.strip()
        try:
            master = bytes.fromhex(text.decode("ascii")) if len(text) == 2 * KEY_BYTES else raw
        except (UnicodeDecodeError, ValueError):
            master = raw
        if len(master) != KEY_BYTES:
            raise ValueError(f"secret-store key {path} must hold 32 bytes (or 64 hex characters)")
        return cls(master)

    # ---- storage -----------------------------------------------------------------------------
    def encrypt(self, plaintext: bytes, aad: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(NONCE_BYTES)
        return nonce, self._aead.encrypt(nonce, plaintext, aad)

    def decrypt(self, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
        return self._aead.decrypt(nonce, ciphertext, aad)

    def fingerprint(self, *parts: str) -> str:
        """Keyed tag of a value: equal values give equal tags; without the key nothing can be guessed."""
        msg = "\x00".join(parts).encode("utf-8")
        return "fp_" + hmac.new(self._fp_key, msg, hashlib.sha256).hexdigest()[:24]

    # ---- sealed input ------------------------------------------------------------------------
    def public_key_json(self) -> dict:
        return {"alg": "X25519", "key": b64u(self.public_key), "key_id": self.key_id, "sealed_alg": SEALED_ALG}

    def open_sealed(self, sealed: object, context: str) -> bytes:
        if not isinstance(sealed, dict):
            raise SealedInputError("sealed must be an object {alg, epk, ct}")
        if sealed.get("alg") != SEALED_ALG:
            raise SealedInputError(f"sealed.alg must be {SEALED_ALG}")
        kid = sealed.get("kid")
        if kid is not None and kid != self.key_id:
            raise SealedInputError("sealed for another key; fetch GET /v1/secrets/public-key again")
        epk, blob = unb64u(sealed.get("epk", "")), unb64u(sealed.get("ct", ""))
        if len(epk) != KEY_BYTES or not NONCE_BYTES + 16 <= len(blob) <= MAX_SEALED_CT:
            raise SealedInputError("sealed.epk or sealed.ct has the wrong size")
        try:
            shared = self._x25519.exchange(X25519PublicKey.from_public_bytes(epk))
        except ValueError:  # all-zero shared secret (a low-order point)
            raise SealedInputError("sealed.epk is not a usable X25519 key") from None
        key = _hkdf(shared, SEALED_INFO, salt=epk + self.public_key)
        try:
            return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], context.encode("utf-8"))
        except InvalidTag:
            raise SealedInputError("sealed input does not open with this box's key for this app") from None


def seal(public_key: bytes, plaintext: bytes, context: str, key_id: str | None = None) -> dict:
    """Client side of sealed input (tests, and the reference for ui/src/secrets/seal.ts)."""
    eph = X25519PrivateKey.generate()
    epk = _raw_public(eph.public_key())
    shared = eph.exchange(X25519PublicKey.from_public_bytes(public_key))
    key = _hkdf(shared, SEALED_INFO, salt=epk + public_key)
    nonce = os.urandom(NONCE_BYTES)
    out = {"alg": SEALED_ALG, "epk": b64u(epk), "ct": b64u(nonce + AESGCM(key).encrypt(nonce, plaintext, context.encode("utf-8")))}
    if key_id:
        out["kid"] = key_id
    return out


def seal_values(public_key_json: dict, app_id: str, values: dict[str, dict[str, str]]) -> dict:
    """Seal `{secret name: {key: value}}` for app_id, given GET /v1/secrets/public-key's answer."""
    body = json.dumps({"values": values}, separators=(",", ":")).encode("utf-8")
    return seal(unb64u(public_key_json["key"]), body, sealed_context(app_id), public_key_json.get("key_id"))


def sealed_context(app_id: str) -> str:
    return f"onemind/app-secrets/{app_id}"
