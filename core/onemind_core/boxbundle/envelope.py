# SPDX-License-Identifier: Apache-2.0
"""The offline .omb envelope (BOX-EXPORT-IMPORT.md §4).

The caller supplies the payload (a deterministic tar of the manifest and layers).
Version 1 encodes bytes in the canonical JSON header as lowercase hex. The
signature covers the entire header except itself, including the ciphertext hash.
Each payload chunk authenticates the header before the hash and signature are
added. The 96-bit nonce is a big-endian uint64 chunk index and uint32 final flag.

Only an export key and the kit's public recipient are needed to seal a bundle.
The owner uses the fabric root separately to certify that export key. Reading
always requires the root fingerprint obtained independently from the owner kit.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import secrets
import struct
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature, InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed25519, mlkem, x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.hpke import (
    AEAD,
    KDF,
    KEM,
    MLKEM768X25519PrivateKey,
    MLKEM768X25519PublicKey,
    Suite,
)
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..backups.kit import GROUPS, OwnerKey, check_group_ok
from .manifest import BundleRefused, canonical, sha256

MAGIC = b"ONEMIND-BOX-BUNDLE\n"
CHUNK_SIZE = 64 * 1024
_HEADER_LIMIT = 8 * 1024
_TAG_SIZE = 16
_KEY_SIZE = 32
_MLKEM_PUBLIC_SIZE = 1184
_SUITE = "chacha20-poly1305"
_KIT_KIND = "hpke-mlkem768-x25519-hkdf-sha256-chacha20-poly1305"
_PASSPHRASE_KIND = "argon2id-v1-chacha20-poly1305"
_DOMAIN = b"onemind.io/box-bundle/v1/"
_HPKE = Suite(KEM.MLKEM768_X25519, KDF.HKDF_SHA256, AEAD.CHACHA20_POLY1305)


@dataclass(frozen=True)
class OpenedBundle:
    source_instance_id: str
    box_name: str
    created_at: datetime
    payload: bytes


def _kit_keys(owner_key: OwnerKey) -> tuple[mlkem.MLKEM768PrivateKey, x25519.X25519PrivateKey]:
    groups = [group.strip().upper() for group in owner_key.groups]
    if len(groups) != GROUPS or any(len(group) != 4 for group in groups) or not check_group_ok(groups, owner_key.check):
        raise ValueError("invalid owner recovery key")
    text = "".join(groups)
    try:
        raw = base64.b32decode(text + "====")
    except binascii.Error:
        raise ValueError("invalid owner recovery key") from None
    if base64.b32encode(raw).decode() != text + "====":
        raise ValueError("invalid owner recovery key")

    # RFC 5869, SHA-256, default zero salt. The input is the kit's 32 random
    # bytes and each component has a distinct, versioned info label.
    mlkem_seed = HKDF(hashes.SHA256(), 64, None, _DOMAIN + b"kit/mlkem768").derive(raw)
    x25519_seed = HKDF(hashes.SHA256(), 32, None, _DOMAIN + b"kit/x25519").derive(raw)
    return mlkem.MLKEM768PrivateKey.from_seed_bytes(mlkem_seed), x25519.X25519PrivateKey.from_private_bytes(x25519_seed)


def _kit_public(keys: tuple[mlkem.MLKEM768PrivateKey, x25519.X25519PrivateKey]) -> bytes:
    mlkem_key, x25519_key = keys
    return mlkem_key.public_key().public_bytes_raw() + x25519_key.public_key().public_bytes_raw()


def kit_recipient_public_key(owner_key: OwnerKey) -> bytes:
    """Return the only kit recipient material that may be retained on the box."""
    return _kit_public(_kit_keys(owner_key))


def _passphrase_key(passphrase: str, salt: bytes) -> bytes:
    if not passphrase:
        raise ValueError("empty recovery passphrase")
    # RFC 9106 §4, second recommended option. The recipient kind fixes all
    # parameters, so an imported header cannot choose the work factor.
    return Argon2id(salt=salt, length=_KEY_SIZE, iterations=3, lanes=4, memory_cost=65536).derive(
        passphrase.encode("utf-8")
    )


def _hex(value: str, size: int) -> bytes:
    if not isinstance(value, str) or len(value) != 2 * size:
        raise ValueError("invalid hex field length")
    decoded = bytes.fromhex(value)
    if decoded.hex() != value:
        raise ValueError("invalid hex field encoding")
    return decoded


def certify_export_key(
    fabric_root: ed25519.Ed25519PrivateKey,
    export_public_key: ed25519.Ed25519PublicKey,
    *,
    source_instance_id: str,
) -> dict:
    """Authorize a distinct purpose key under the owner's offline fabric root."""
    root = fabric_root.public_key().public_bytes_raw()
    export = export_public_key.public_bytes_raw()
    if not source_instance_id or root == export:
        raise ValueError("export requires a source instance and a distinct purpose key")
    certificate = {
        "root": root.hex(),
        "public_key": export.hex(),
        "kid": sha256(export),
        "purpose": "export",
        "source_instance_id": source_instance_id,
    }
    return {**certificate, "signature": fabric_root.sign(_DOMAIN + b"certificate\0" + canonical(certificate)).hex()}


def _verify_certificate(certificate: dict, root_fingerprint: str, source_instance_id: str) -> ed25519.Ed25519PublicKey:
    unsigned = dict(certificate)
    signature = _hex(unsigned.pop("signature"), 64)
    root = _hex(unsigned["root"], _KEY_SIZE)
    export = _hex(unsigned["public_key"], _KEY_SIZE)
    if not hmac.compare_digest(sha256(root), root_fingerprint):
        raise BundleRefused(["export signer does not match the owner kit's fabric root"])
    if (unsigned["purpose"] != "export" or unsigned["source_instance_id"] != source_instance_id
            or root == export or unsigned["kid"] != sha256(export)):
        raise ValueError("invalid export certificate")
    ed25519.Ed25519PublicKey.from_public_bytes(root).verify(signature, _DOMAIN + b"certificate\0" + canonical(unsigned))
    return ed25519.Ed25519PublicKey.from_public_bytes(export)


def _crypt_payload(payload: bytes, key: bytes, aad: bytes, *, decrypt: bool) -> bytes:
    cipher = ChaCha20Poly1305(key)
    size = CHUNK_SIZE + _TAG_SIZE if decrypt else CHUNK_SIZE
    crypt = cipher.decrypt if decrypt else cipher.encrypt
    # Include one authenticated final chunk even when the plaintext is empty.
    return b"".join(
        crypt(struct.pack(">QI", index, offset + size >= len(payload)), payload[offset:offset + size], aad)
        for index, offset in enumerate(range(0, max(1, len(payload)), size))
    )


def seal_bundle(
    payload: bytes,
    *,
    kit_public_key: bytes,
    export_key: ed25519.Ed25519PrivateKey,
    certificate: dict,
    box_name: str,
    created_at: datetime,
    passphrase: str | None = None,
) -> bytes:
    """Encrypt a payload using the public kit recipient and sign with the export key."""
    source_instance_id = certificate["source_instance_id"]
    if not source_instance_id or not box_name or created_at.utcoffset() is None:
        raise ValueError("bundle requires a source, box name and timezone-aware timestamp")
    signer = _verify_certificate(certificate, sha256(_hex(certificate["root"], _KEY_SIZE)), source_instance_id)
    if signer.public_bytes_raw() != export_key.public_key().public_bytes_raw():
        raise ValueError("export signing key does not match its certificate")
    recipient = MLKEM768X25519PublicKey(
        mlkem.MLKEM768PublicKey.from_public_bytes(kit_public_key[:_MLKEM_PUBLIC_SIZE]),
        x25519.X25519PublicKey.from_public_bytes(kit_public_key[_MLKEM_PUBLIC_SIZE:]),
    )
    data_key = secrets.token_bytes(_KEY_SIZE)
    recipients = [{
        "kind": _KIT_KIND,
        "kid": sha256(kit_public_key),
        "wrapped_key": _HPKE.encrypt(data_key, recipient, info=_DOMAIN + b"kit-wrap").hex(),
    }]
    if passphrase is not None:
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        wrapped = ChaCha20Poly1305(_passphrase_key(passphrase, salt)).encrypt(
            nonce, data_key, _DOMAIN + b"passphrase-wrap"
        )
        recipients.append({
            "kind": _PASSPHRASE_KIND,
            "kid": sha256(salt),
            "salt": salt.hex(),
            "nonce": nonce.hex(),
            "wrapped_key": wrapped.hex(),
        })
    header = {
        "format": {"major": 1, "minor": 0},
        "created_at": created_at.astimezone(UTC).isoformat(),
        "source_instance_id": source_instance_id,
        "box_name": box_name,
        "suite": _SUITE,
        "chunk_size": CHUNK_SIZE,
        "recipients": recipients,
        "signer": certificate,
    }
    ciphertext = _crypt_payload(payload, data_key, canonical(header), decrypt=False)
    header["payload_sha256"] = sha256(ciphertext)
    header["signature"] = export_key.sign(_DOMAIN + b"header\0" + canonical(header)).hex()
    line = canonical(header)
    if len(line) > _HEADER_LIMIT:
        raise ValueError("bundle header too large")
    return MAGIC + line + b"\n" + ciphertext


def _read_header(bundle: bytes) -> tuple[dict, int]:
    end = bundle.find(b"\n", len(MAGIC), len(MAGIC) + _HEADER_LIMIT + 1)
    if not bundle.startswith(MAGIC) or end < 0:
        raise ValueError("invalid bundle framing")
    line = bundle[len(MAGIC):end]
    header = json.loads(line)
    if not isinstance(header, dict) or canonical(header) != line:
        raise ValueError("noncanonical bundle header")
    version = header["format"]
    if (type(version["major"]) is not int or version["major"] != 1
            or type(version["minor"]) is not int or version["minor"] < 0
            or header["suite"] != _SUITE or type(header["chunk_size"]) is not int
            or header["chunk_size"] != CHUNK_SIZE):
        raise BundleRefused(["unsupported recovery bundle version or suite"])
    return header, end + 1


def _unwrap_key(recipients: list, owner_key: OwnerKey | None, passphrase: str | None) -> bytes:
    by_kind = {}
    for recipient in recipients:
        kind = recipient["kind"]
        if kind in by_kind:
            raise ValueError("duplicate recovery recipient kind")
        by_kind[kind] = recipient
    kit = by_kind[_KIT_KIND]
    _hex(kit["kid"], _KEY_SIZE)
    wrapped = _hex(kit["wrapped_key"], KEM.MLKEM768_X25519.enc_length() + _KEY_SIZE + _TAG_SIZE)
    if owner_key is not None:
        keys = _kit_keys(owner_key)
        if not hmac.compare_digest(sha256(_kit_public(keys)), kit["kid"]):
            raise BundleRefused(["owner key does not match the bundle's kit recipient"])
        return _HPKE.decrypt(wrapped, MLKEM768X25519PrivateKey(*keys), info=_DOMAIN + b"kit-wrap")
    if passphrase is None or _PASSPHRASE_KIND not in by_kind:
        raise BundleRefused(["bundle has no passphrase recipient"])
    recipient = by_kind[_PASSPHRASE_KIND]
    salt = _hex(recipient["salt"], 16)
    if recipient["kid"] != sha256(salt):
        raise ValueError("invalid passphrase recipient id")
    return ChaCha20Poly1305(_passphrase_key(passphrase, salt)).decrypt(
        _hex(recipient["nonce"], 12), _hex(recipient["wrapped_key"], _KEY_SIZE + _TAG_SIZE),
        _DOMAIN + b"passphrase-wrap",
    )


def open_bundle(
    bundle: bytes,
    *,
    root_fingerprint: str,
    owner_key: OwnerKey | None = None,
    passphrase: str | None = None,
) -> OpenedBundle:
    """Verify before unlocking. The root pin is SHA-256 hex of the kit's raw Ed25519 root public key."""
    if (owner_key is None) == (passphrase is None):
        raise ValueError("supply exactly one recovery credential")
    try:
        header, start = _read_header(bundle)
        source = header["source_instance_id"]
        box_name = header["box_name"]
        created_at = datetime.fromisoformat(header["created_at"])
        if not isinstance(source, str) or not isinstance(box_name, str) or not source or not box_name:
            raise ValueError("missing bundle source")
        if created_at.utcoffset() is None:
            raise ValueError("missing timezone")
        _hex(root_fingerprint, _KEY_SIZE)
        signer = _verify_certificate(header["signer"], root_fingerprint, source)
        signature = _hex(header.pop("signature"), 64)
        signer.verify(signature, _DOMAIN + b"header\0" + canonical(header))
        ciphertext = bundle[start:]
        if len(ciphertext) < _TAG_SIZE or not hmac.compare_digest(sha256(ciphertext), header.pop("payload_sha256")):
            raise BundleRefused(["recovery bundle ciphertext checksum mismatch"])
        data_key = _unwrap_key(header["recipients"], owner_key, passphrase)
        payload = _crypt_payload(ciphertext, data_key, canonical(header), decrypt=True)
        return OpenedBundle(source, box_name, created_at, payload)
    except InvalidSignature:
        raise BundleRefused(["invalid recovery bundle signature"]) from None
    except InvalidTag:
        raise BundleRefused(["recovery bundle authentication failed"]) from None
    except UnsupportedAlgorithm:
        raise BundleRefused(["required recovery bundle crypto suite is unavailable"]) from None
    except (AttributeError, KeyError, RecursionError, TypeError, ValueError):
        raise BundleRefused(["invalid recovery bundle or recovery credential"]) from None
