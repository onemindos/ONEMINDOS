# SPDX-License-Identifier: Apache-2.0
"""Password hashing (scrypt, stdlib), TOTP (RFC 6238), opaque ids and secrets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

# scrypt N=2^15, r=8, p=1: about 32 MiB and tens of milliseconds per hash (OWASP minimum is 2^17
# with r=8 for interactive use only when memory allows; a small board runs several gateways' worth
# of apps, so we take 2^15 and rate-limit logins instead). Parameters are stored with each hash.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**15, 8, 1
_MAXMEM = 128 * 1024 * 1024
PASSWORD_MIN, PASSWORD_MAX = 10, 1024


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=_MAXMEM, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(dk)}"


_DUMMY = None


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check. With stored=None it still spends one hash, so unknown users take as long."""
    global _DUMMY
    if stored is None:
        _DUMMY = _DUMMY or hash_password("not-a-real-password")
        stored, password, result = _DUMMY, password + "x", False
    else:
        result = True
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p),
                             maxmem=_MAXMEM, dklen=len(_unb64(dk)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, _unb64(dk)) and result


# ---- TOTP (RFC 6238: HMAC-SHA1, 6 digits, 30 s) -----------------------------------------------
TOTP_STEP, TOTP_DIGITS = 30, 6


def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[off:off + 4])[0] & 0x7FFFFFFF
    return str(value % 10**TOTP_DIGITS).zfill(TOTP_DIGITS)


def totp_match(secret: str, code: str, now: float | None = None, last_step: int | None = None) -> int | None:
    """The time step `code` matches (window ±1), or None. A step at or before last_step is a replay."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != TOTP_DIGITS or not code.isdigit():
        return None
    current = int((time.time() if now is None else now) // TOTP_STEP)
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp_code(secret, step), code):
            if last_step is not None and step <= last_step:
                return None
            return step
    return None


def otpauth_uri(secret: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


# ---- ids and secrets ----------------------------------------------------------------------------
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id(prefix: str, now_ms: int | None = None) -> str:
    """A prefixed ULID (§12.1): 48-bit millisecond time + 80 random bits, Crockford base32."""
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    n = (ms << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 31])
        n >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"


# §12.6 token format om_<kind>_<random>; ses/ref are session access and refresh tokens.
TOKEN_KINDS = {"person": "pat", "agent": "agt", "plugin": "plg", "node": "nod", "automation": "aut"}


def new_secret(tag: str) -> str:
    return f"om_{tag}_{secrets.token_urlsafe(32)}"


def b64url(b: bytes) -> str:
    return _b64(b)


def unb64url(s: str) -> bytes:
    return _unb64(s)
