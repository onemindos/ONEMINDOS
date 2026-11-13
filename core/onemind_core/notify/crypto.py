# SPDX-License-Identifier: Apache-2.0
"""Box-local keys for notifications: the secret box, VAPID (RFC 8292) and Web Push encryption (RFC 8291).

Both keys are generated on the box at first start and written with mode 0600 into the notify
directory (default: next to the audit log). Nothing here is ever logged or returned by the API,
except the VAPID *public* key.

- `SecretBox` seals channel secrets and push endpoints at rest (AES-256-GCM, a random nonce per
  value, the row id as associated data so a sealed value cannot be moved to another row).
- `Vapid` signs the `Authorization: vapid t=<JWT>, k=<public key>` header of every Web Push.
- `encrypt_aes128gcm` encrypts one Web Push message to a browser's or UnifiedPush distributor's
  subscription keys (`p256dh`, `auth`), so the push service sees only size and timing.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


class SecretBox:
    """AES-256-GCM with one random key per box (`secret.key`, 0600)."""

    PREFIX = "v1:"

    def __init__(self, path: Path):
        if not path.exists():
            _write_private(path, os.urandom(32))
        key = path.read_bytes()
        if len(key) != 32:
            raise ValueError(f"{path.name} must hold exactly 32 bytes")
        self._aead = AESGCM(key)

    def seal(self, plaintext: str, aad: str) -> str:
        nonce = os.urandom(12)
        return self.PREFIX + b64u(nonce + self._aead.encrypt(nonce, plaintext.encode(), aad.encode()))

    def open(self, token: str, aad: str) -> str:
        if not token.startswith(self.PREFIX):
            raise ValueError("not a sealed value")
        raw = b64u_decode(token[len(self.PREFIX):])
        return self._aead.decrypt(raw[:12], raw[12:], aad.encode()).decode()


def _uncompressed(public_key: ec.EllipticCurvePublicKey) -> bytes:
    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


class Vapid:
    """The box's VAPID key pair (ECDSA P-256, `vapid.pem`, 0600)."""

    def __init__(self, path: Path):
        if not path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            _write_private(path, key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
            ))
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256r1":
            raise ValueError(f"{path.name} must be an ECDSA P-256 private key")
        self._key = key
        self.public_key = b64u(_uncompressed(key.public_key()))

    def authorization(self, endpoint: str, subject: str, now_s: int, ttl_s: int = 12 * 3600) -> str:
        """RFC 8292 header value for a push to `endpoint` (audience = its origin)."""
        parts = urlsplit(endpoint)
        header = {"typ": "JWT", "alg": "ES256"}
        claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": now_s + ttl_s, "sub": subject}
        signing_input = (
            b64u(json.dumps(header, separators=(",", ":")).encode()) + "."
            + b64u(json.dumps(claims, separators=(",", ":")).encode())
        )
        der = self._key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        jwt = signing_input + "." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"vapid t={jwt}, k={self.public_key}"


RECORD_SIZE = 4096


def _hkdf(salt: bytes, info: bytes, length: int, ikm: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt_aes128gcm(plaintext: bytes, ua_public: str, auth_secret: str) -> bytes:
    """RFC 8291 message encryption, one record, content coding aes128gcm (RFC 8188)."""
    ua_pub_bytes = b64u_decode(ua_public)
    auth = b64u_decode(auth_secret)
    if len(ua_pub_bytes) != 65 or len(auth) != 16:
        raise ValueError("push subscription keys must be a 65-byte P-256 point and a 16-byte auth secret")
    if len(plaintext) > RECORD_SIZE - 17 - 86:
        raise ValueError("push payload too large for one record")
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_bytes)
    as_key = ec.generate_private_key(ec.SECP256R1())
    as_pub = _uncompressed(as_key.public_key())
    shared = as_key.exchange(ec.ECDH(), ua_pub)
    ikm = _hkdf(auth, b"WebPush: info\x00" + ua_pub_bytes + as_pub, 32, shared)
    salt = os.urandom(16)
    cek = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    body = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + body
