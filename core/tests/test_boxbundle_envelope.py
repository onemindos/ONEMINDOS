# SPDX-License-Identifier: Apache-2.0
"""Recovery bundle v1 wire format and offline trust checks."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import ed25519, mlkem

from onemind_core.backups.kit import OwnerKey, new_owner_key
from onemind_core.boxbundle import (
    OpenedBundle,
    certify_export_key,
    envelope,
    kit_recipient_public_key,
    open_bundle,
    seal_bundle,
)
from onemind_core.boxbundle.envelope import CHUNK_SIZE, MAGIC
from onemind_core.boxbundle.manifest import BundleRefused, canonical, sha256

CREATED = datetime(2026, 11, 27, tzinfo=UTC)
PHRASE = "one mind passphrase"
SOURCE = "box-vector"


def test_kit_derivation_known_answer():
    # Owner key encodes bytes 00 through 1f. The seeds and public-key digest
    # were generated independently using Go 1.26 crypto/hkdf, mlkem and ecdh.
    text = base64.b32encode(bytes(range(32))).rstrip(b"=")
    check = base64.b32encode(hashlib.sha256(text).digest())[:4].decode()
    kit = OwnerKey(tuple(text[i:i + 4].decode() for i in range(0, len(text), 4)), check)
    mlkem_key, x25519_key = envelope._kit_keys(kit)
    assert mlkem_key.private_bytes_raw().hex() == (
        "29b95c7ec06e5fdb6df814bab15fed1ee4942eaab7c5d6469d902035c89e6eb635"
        "c8cbbdbeb75ce4b62ef4d31bbaa713d2ed849b450cd98e5068850316ae2bf9"
    )
    assert x25519_key.private_bytes_raw().hex() == "5096fd64ef9a64ef545ff11c8a28ba58fbf922ec531503c46135be2fabdff8de"
    assert sha256(kit_recipient_public_key(kit)) == "0fd05a4843a5a4c7efb753e96ad81d2374d3cff7db4b4e633d888f8320b35d2d"


def test_passphrase_derivation_known_answer():
    # Independently generated with libargon2 argon2id_hash_raw(3, 65536, 4, …).
    assert envelope._passphrase_key(PHRASE, bytes(range(16))).hex() == (
        "1ffe103c21694fea7591b070d9b1760e86d892df2c9422f488c3973dba1b4aa5"
    )


@pytest.fixture
def keys():
    root = ed25519.Ed25519PrivateKey.generate()
    export = ed25519.Ed25519PrivateKey.generate()
    kit = new_owner_key()
    return root, export, kit


def _pin(root):
    return hashlib.sha256(root.public_key().public_bytes_raw()).hexdigest()


def _seal(keys, payload, passphrase=None):
    root, export, kit = keys
    return seal_bundle(
        payload,
        kit_public_key=kit_recipient_public_key(kit),
        export_key=export,
        certificate=certify_export_key(root, export.public_key(), source_instance_id=SOURCE),
        box_name="Owner's box",
        created_at=CREATED,
        passphrase=passphrase,
    )


@pytest.mark.parametrize("size", [0, 1, CHUNK_SIZE, CHUNK_SIZE + 1, 2 * CHUNK_SIZE])
def test_kit_opens_chunk_boundaries(keys, size):
    root, _, kit = keys
    payload = b"x" * size
    bundle = _seal(keys, payload)
    assert open_bundle(bundle, root_fingerprint=_pin(root), owner_key=kit) == OpenedBundle(
        SOURCE, "Owner's box", CREATED, payload
    )
    with pytest.raises(BundleRefused, match="no passphrase recipient"):
        open_bundle(bundle, root_fingerprint=_pin(root), passphrase=PHRASE)


def test_both_recipients_and_wrong_credentials(keys):
    root, _, kit = keys
    payload = b"test bundle payload" * 5000
    bundle = _seal(keys, payload, passphrase=PHRASE)
    assert open_bundle(bundle, root_fingerprint=_pin(root), passphrase=PHRASE).payload == payload
    assert open_bundle(bundle, root_fingerprint=_pin(root), owner_key=kit).payload == payload
    with pytest.raises(BundleRefused, match="owner key does not match"):
        open_bundle(bundle, root_fingerprint=_pin(root), owner_key=new_owner_key())
    with pytest.raises(BundleRefused, match="authentication failed"):
        open_bundle(bundle, root_fingerprint=_pin(root), passphrase=PHRASE + " ")


def _parts(bundle):
    line, ciphertext = bundle[len(MAGIC):].split(b"\n", 1)
    return json.loads(line), ciphertext


def _resign(header, ciphertext, export):
    header.pop("signature")
    header["payload_sha256"] = sha256(ciphertext)
    header["signature"] = export.sign(envelope._DOMAIN + b"header\0" + canonical(header)).hex()
    return MAGIC + canonical(header) + b"\n" + ciphertext


def test_tampering_and_header_replay(keys):
    root, export, kit = keys
    bundle = _seal(keys, b"a" * CHUNK_SIZE + b"b")
    header, ciphertext = _parts(bundle)
    header["box_name"] = "tampered"
    changed_header = MAGIC + canonical(header) + b"\n" + ciphertext
    pin = _pin(root)
    with pytest.raises(BundleRefused, match="signature"):
        open_bundle(changed_header, root_fingerprint=pin, owner_key=kit)
    changed = ciphertext[:-1] + bytes([ciphertext[-1] ^ 1])
    _, foreign_payload = _parts(_seal(keys, b"c" * CHUNK_SIZE + b"d"))
    prefix = bundle[:-len(ciphertext)]
    for damaged in changed, ciphertext[:-1], ciphertext + b"x", foreign_payload:
        with pytest.raises(BundleRefused, match="checksum mismatch"):
            open_bundle(prefix + damaged, root_fingerprint=pin, owner_key=kit)

    # A valid outer signature and digest alone cannot authorize reordered or
    # truncated AEAD frames, or reuse the payload with different metadata.
    full_frame = CHUNK_SIZE + 16
    original, _ = _parts(bundle)
    for metadata, damaged in (
        (dict(original), ciphertext[full_frame:] + ciphertext[:full_frame]),
        (dict(original), ciphertext[:full_frame]),
        (header, ciphertext),
    ):
        with pytest.raises(BundleRefused, match="authentication failed"):
            open_bundle(_resign(metadata, damaged, export), root_fingerprint=pin, owner_key=kit)


def test_public_recipient_does_not_make_foreign_signer_trusted(keys):
    root, _, kit = keys
    foreign = ed25519.Ed25519PrivateKey.generate()
    export = ed25519.Ed25519PrivateKey.generate()
    forged = _seal((foreign, export, kit), b"forged payload")
    with pytest.raises(BundleRefused, match="owner kit's fabric root"):
        open_bundle(forged, root_fingerprint=_pin(root), owner_key=kit)


def test_wrong_purpose_and_source_are_refused(keys):
    root, export, kit = keys
    bundle = _seal(keys, b"test payload")
    header, ciphertext = _parts(bundle)
    signer = header["signer"]
    signer.pop("signature")
    signer["purpose"] = "job"
    signer["signature"] = root.sign(envelope._DOMAIN + b"certificate\0" + canonical(signer)).hex()
    for change in (header, {**_parts(bundle)[0], "source_instance_id": "other-box"}):
        with pytest.raises(BundleRefused):
            open_bundle(_resign(change, ciphertext, export), root_fingerprint=_pin(root), owner_key=kit)
    with pytest.raises(ValueError, match="distinct purpose key"):
        certify_export_key(root, root.public_key(), source_instance_id=SOURCE)


def test_version_compatibility(keys):
    root, export, kit = keys
    payload = b"test payload"
    header, _ = _parts(_seal(keys, payload))
    key = envelope._unwrap_key(header["recipients"], kit, None)
    header["format"]["minor"] = 2
    header["future_optional"] = True
    aad = canonical({k: v for k, v in header.items() if k not in ("payload_sha256", "signature")})
    ciphertext = envelope._crypt_payload(payload, key, aad, decrypt=False)
    newer = _resign(header, ciphertext, export)
    assert open_bundle(newer, root_fingerprint=_pin(root), owner_key=kit).payload == payload

    header["format"]["major"] = 2
    with pytest.raises(BundleRefused, match="unsupported recovery bundle version"):
        open_bundle(_resign(header, ciphertext, export), root_fingerprint=_pin(root), owner_key=kit)


def test_hybrid_backend_failure_stops_sealing(keys, monkeypatch):
    root, export, kit = keys
    public_key = kit_recipient_public_key(kit)

    def unavailable(data):
        raise UnsupportedAlgorithm("ML-KEM is unavailable")

    monkeypatch.setattr(mlkem, "MLKEM768PublicKey", SimpleNamespace(from_public_bytes=unavailable))
    with pytest.raises(UnsupportedAlgorithm):
        seal_bundle(
            b"test payload",
            kit_public_key=public_key,
            export_key=export,
            certificate=certify_export_key(root, export.public_key(), source_instance_id=SOURCE),
            box_name="Owner's box",
            created_at=CREATED,
            passphrase=PHRASE,
        )
