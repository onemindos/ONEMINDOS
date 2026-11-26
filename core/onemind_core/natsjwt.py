# SPDX-License-Identifier: Apache-2.0
"""NATS JWTs and nkeys with `cryptography` only (D-029; for the auth callout, callout.py).

A NATS JWT is three base64url parts without padding: a header `{"typ":"JWT","alg":"ed25519-nkey"}`,
the claims, and an Ed25519 signature over `header.claims` by the issuer's nkey. The issuer's public
nkey is the claims' `iss`; `jti` is base32 (no padding) of SHA-512/256 over the claims with an empty
`jti` (github.com/nats-io/jwt/v2 claims.go doEncode, hash). This module writes and reads exactly that,
without the `nkeys` package, which ships no wheel for the image's --only-binary install (#269).
internal/leaf/callout_test.go decodes what this writes with jwt/v2 and runs it in nats-server 2.15.3.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from .natsconf import _crc16, _encode

# nkeys prefix bytes (github.com/nats-io/nkeys strkey.go).
PREFIX_SEED = 18 << 3
PREFIX_ACCOUNT = 0
PREFIX_SERVER = 13 << 3
PREFIX_USER = 20 << 3
HEADER = {"typ": "JWT", "alg": "ed25519-nkey"}


class JwtError(ValueError):
    """A token or key that does not decode or verify."""


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except ValueError as exc:
        raise JwtError("not base64url") from exc


def decode_public(key: str, prefix: int) -> bytes:
    """The raw 32-byte Ed25519 key of a public nkey with this prefix byte; refuses anything else."""
    try:
        raw = base64.b32decode(key + "=" * (-len(key) % 8))
    except (ValueError, TypeError) as exc:
        raise JwtError("not a public nkey") from exc
    if len(raw) != 35 or raw[0] != prefix or _crc16(raw[:-2]) != int.from_bytes(raw[-2:], "little"):
        raise JwtError("not a public nkey of the expected kind")
    return raw[1:33]


def public_key(key: Ed25519PrivateKey, prefix: int) -> str:
    return _encode(bytes([prefix]), key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def encode_seed(key: Ed25519PrivateKey, prefix: int) -> str:
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    return _encode(bytes([PREFIX_SEED | (prefix >> 5), (prefix & 31) << 3]), raw)


def decode_seed(text: str, prefix: int) -> Ed25519PrivateKey:
    text = text.strip()
    try:
        raw = base64.b32decode(text + "=" * (-len(text) % 8))
    except (ValueError, TypeError) as exc:
        raise JwtError("not an nkey seed") from exc
    if (len(raw) != 36 or _crc16(raw[:-2]) != int.from_bytes(raw[-2:], "little")
            or raw[0] != PREFIX_SEED | (prefix >> 5) or raw[1] != (prefix & 31) << 3):
        raise JwtError("not an nkey seed of the expected kind")
    return Ed25519PrivateKey.from_private_bytes(raw[2:34])


def load_or_create_seed(path: Path, prefix: int) -> Ed25519PrivateKey:
    """The nkey seed in `path` (0600), made on first use. A file that is not a seed raises."""
    if path.exists():
        return decode_seed(path.read_text(encoding="ascii"), prefix)
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (encode_seed(key, prefix) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)
    return key


def _jti(claims: dict) -> str:
    # jwt/v2 hashes json.Marshal(ClaimsData) with jti "": the standard fields in struct order, empty
    # ones left out. Servers do not check jti; it only has to be unique, so the same rule is enough.
    std = {k: claims[k] for k in ("aud", "exp", "jti", "iat", "iss", "name", "nbf", "sub") if claims.get(k)}
    std["jti"] = ""
    h = hashlib.new("sha512_256", json.dumps(std, separators=(",", ":")).encode())
    return base64.b32encode(h.digest()).decode().rstrip("=")


def encode(claims: dict, key: Ed25519PrivateKey, prefix: int, now: float | None = None) -> str:
    """Sign `claims` as a NATS JWT by `key` (an nkey of kind `prefix`); sets iss, iat and jti."""
    c = dict(claims)
    c["iss"] = public_key(key, prefix)
    c["iat"] = int(now if now is not None else time.time())
    c["jti"] = _jti(c)
    head = _b64(json.dumps(HEADER, separators=(",", ":")).encode())
    body = _b64(json.dumps(c, separators=(",", ":")).encode())
    sig = key.sign(f"{head}.{body}".encode())
    return f"{head}.{body}.{_b64(sig)}"


def decode(token: str, issuer_prefix: int) -> dict:
    """The claims of a NATS JWT whose signature verifies with its own `iss` of kind `issuer_prefix`."""
    parts = token.split(".") if isinstance(token, str) else []
    if len(parts) != 3:
        raise JwtError("a JWT has three parts")
    try:
        header = json.loads(_unb64(parts[0]))
        claims = json.loads(_unb64(parts[1]))
    except (ValueError, TypeError) as exc:
        raise JwtError("JWT parts are not JSON") from exc
    if not isinstance(header, dict) or str(header.get("alg", "")).lower() != "ed25519-nkey" or not isinstance(claims, dict):
        raise JwtError("not an ed25519-nkey JWT")
    pub = Ed25519PublicKey.from_public_bytes(decode_public(str(claims.get("iss", "")), issuer_prefix))
    try:
        pub.verify(_unb64(parts[2]), f"{parts[0]}.{parts[1]}".encode())
    except InvalidSignature as exc:
        raise JwtError("JWT signature does not verify") from exc
    return claims


def verify_nonce(user_nkey: str, nonce: str, sig: str) -> bool:
    """Did the holder of `user_nkey` sign `nonce`? NATS clients send the signature base64url (nats.go)
    or standard base64 (nats-py); the server accepts both, so this does too."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(decode_public(user_nkey, PREFIX_USER))
    except JwtError:
        return False
    for dec in (lambda s: _unb64(s), lambda s: base64.b64decode(s + "=" * (-len(s) % 4))):
        try:
            pub.verify(dec(sig), nonce.encode())
            return True
        except (InvalidSignature, ValueError, TypeError):
            continue
    return False
