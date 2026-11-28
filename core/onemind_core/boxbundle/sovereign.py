# SPDX-License-Identifier: Apache-2.0
"""Owner-signed completion records and kit-encrypted bundles (BOX-EXPORT-IMPORT §4, §5.2)."""
from __future__ import annotations

import base64
import io
import json
import re
import secrets
import tarfile
from datetime import datetime
from typing import Annotated

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hpke
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.mlkem import MLKEM768PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from . import box_config
from .manifest import BundleRefused, Layer, Source, build_manifest, canonical, check_layer, check_manifest, make_layer, sha256

BOX_ID = r"^[A-Za-z0-9._:-]{1,80}$"
KEY = r"^(?:[A-Z2-7]{4}-){12}[A-Z2-7]{4}$"
HEX = r"^[a-f0-9]{64}$"
COPY_ID = r"^[a-f0-9]{32}$"
RUN_ID = r"^[A-Za-z0-9._:-]{1,128}$"
MAX_BUNDLE = 640 << 10
CHUNK = 64 << 10
MAGIC = b"ONEMIND-BOX-BUNDLE\n"
DOMAIN = b"onemind.io/sovereign-copy/v1/"
REFS_SCHEMA = "onemind.io/box-bundle/app-data-refs/v1"
SUITE = "MLKEM768-X25519/HKDF-SHA256/ChaCha20Poly1305"
HexID = Annotated[str, StringConstraints(pattern=HEX)]


class CopyRefused(ValueError):
    """A candidate failed an integrity check."""


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    repository: HexID
    run_id: str = Field(pattern=RUN_ID)
    snapshots: list[HexID] = Field(min_length=1, max_length=256)

    @field_validator("snapshots")
    @classmethod
    def unique(cls, ids: list[str]) -> list[str]:
        if ids != sorted(set(ids)):
            raise ValueError("snapshot IDs must be sorted and unique")
        return ids


class Completion(Point):
    format: int = Field(ge=1, le=1)
    box_id: str = Field(pattern=BOX_ID)
    copy_id: str = Field(pattern=COPY_ID)
    generation: int = Field(ge=0)
    created_at: AwareDatetime
    backed_up_at: AwareDatetime
    size: int = Field(gt=0, le=MAX_BUNDLE)
    sha256: HexID


class UnitReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: HexID
    unit: str = Field(min_length=1, max_length=140)
    app_id: str | None
    app_revision: str | None


class References(Point):
    units: list[UnitReference] = Field(min_length=1, max_length=256)


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def unb64(data: str) -> bytes:
    return base64.b64decode(data, validate=True)


def decode(raw: bytes) -> dict:
    doc = json.loads(raw)
    if not isinstance(doc, dict) or canonical(doc) != raw:
        raise CopyRefused("expected canonical JSON")
    return doc


def signed(domain: bytes, key: Ed25519PrivateKey, doc: dict) -> dict:
    return {"body": doc, "signature": b64(key.sign(DOMAIN + domain + canonical(doc)))}


def verified(domain: bytes, key: Ed25519PublicKey, obj: dict) -> dict:
    if set(obj) != {"body", "signature"} or not isinstance(obj["body"], dict):
        raise CopyRefused("malformed signature")
    key.verify(unb64(obj["signature"]), DOMAIN + domain + canonical(obj["body"]))
    return obj["body"]


def certificate(root: Ed25519PrivateKey, export: Ed25519PublicKey, box_id: str) -> dict:
    return signed(b"delegate/", root, {"purpose": "export", "box_id": box_id, "public_key": b64(export.public_bytes_raw())})


def export_key(trust: dict, box_id: str, fingerprint: str) -> Ed25519PublicKey:
    raw = unb64(trust["root"])
    if sha256(raw) != fingerprint:
        raise CopyRefused("the fabric root does not match the owner's kit")
    cert = verified(b"delegate/", Ed25519PublicKey.from_public_bytes(raw), trust["certificate"])
    if cert.get("purpose") != "export" or cert.get("box_id") != box_id:
        raise CopyRefused("the signer is not this box's export key")
    export = unb64(cert["public_key"])
    if export == raw:
        raise CopyRefused("the export key must be separate from the fabric root")
    return Ed25519PublicKey.from_public_bytes(export)


def open_record(raw: bytes, box_id: str, copy_id: str, fingerprint: str) -> tuple[Completion, Ed25519PublicKey]:
    doc = decode(raw)
    key = export_key(doc["trust"], box_id, fingerprint)
    body = verified(b"complete/", key, doc["completion"])
    record = Completion.model_validate_json(canonical(body))
    if record.box_id != box_id or record.copy_id != copy_id or record.backed_up_at > record.created_at:
        raise CopyRefused("completion record belongs to another copy or has inconsistent times")
    return record, key


def recipient(password: str) -> hpke.MLKEM768X25519PrivateKey:
    if not re.fullmatch(KEY, password):
        raise CopyRefused("expected the printed recovery key")
    text = password.replace("-", "")
    raw = base64.b32decode(text + "====")
    if base64.b32encode(raw).decode().rstrip("=") != text:
        raise CopyRefused("expected a canonical recovery key")

    def derive(label: bytes, length: int) -> bytes:
        return HKDF(algorithm=SHA256(), length=length, salt=None, info=DOMAIN + b"recipient/" + label).derive(raw)

    return hpke.MLKEM768X25519PrivateKey(MLKEM768PrivateKey.from_seed_bytes(derive(b"mlkem768", 64)),
                                       X25519PrivateKey.from_private_bytes(derive(b"x25519", 32)))


def suite() -> hpke.Suite:
    return hpke.Suite(hpke.KEM.MLKEM768_X25519, hpke.KDF.HKDF_SHA256, hpke.AEAD.CHACHA20_POLY1305)


def nonce(index: int, last: bool) -> bytes:
    return index.to_bytes(11, "big") + bytes([last])


def archive(manifest: dict, layers: list[Layer]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in [("manifest.json", canonical(manifest)), *((layer.entry["path"], layer.data) for layer in layers)]:
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
    return buffer.getvalue()


def seal(config: Layer, point: References, source: Source, now: datetime, copy_id: str, key: Ed25519PrivateKey,
         recipient_key: hpke.MLKEM768X25519PublicKey, excluded: list[dict]) -> bytes:
    refs = make_layer("app_data_refs", REFS_SCHEMA, point.model_dump(), items=len(point.snapshots), sensitive=False)
    layers = [config, refs]
    manifest = build_manifest(source, layers, now=now, bundle_id="bnd_" + copy_id, excluded=excluded)
    payload = archive(manifest, layers)
    data_key = secrets.token_bytes(32)
    aead = ChaCha20Poly1305(data_key)
    ciphertext = b"".join(aead.encrypt(nonce(i // CHUNK, i + CHUNK >= len(payload)),
                                       payload[i:i + CHUNK], DOMAIN + b"payload/")
                          for i in range(0, len(payload), CHUNK))
    header = {"format": 1, "bundle_id": manifest["bundle_id"], "source": manifest["source"], "created_at": manifest["created_at"],
              "suite": SUITE, "chunk_size": CHUNK, "recipients": [{"kind": "kit", "wrapped_key":
                  b64(suite().encrypt(data_key, recipient_key, info=DOMAIN + b"wrap/"))}], "payload_sha256": sha256(ciphertext)}
    bundle = MAGIC + canonical(signed(b"envelope/", key, header)) + b"\n" + ciphertext
    if len(bundle) > MAX_BUNDLE:
        raise CopyRefused("bundle exceeds the copy size limit")
    return bundle


def open_bundle(bundle: bytes, record: Completion, signer: Ed25519PublicKey,
                private: hpke.MLKEM768X25519PrivateKey) -> tuple[dict, References]:
    if len(bundle) != record.size or sha256(bundle) != record.sha256 or not bundle.startswith(MAGIC):
        raise CopyRefused("bundle length, digest or format does not match")
    header_line, newline, ciphertext = bundle[len(MAGIC):].partition(b"\n")
    header = verified(b"envelope/", signer, decode(header_line))
    if (not newline or header["format"] != 1 or header["suite"] != SUITE or header["chunk_size"] != CHUNK
            or sha256(ciphertext) != header["payload_sha256"] or len(header["recipients"]) != 1
            or header["recipients"][0]["kind"] != "kit"):
        raise CopyRefused("bundle envelope does not match")
    data_key = suite().decrypt(unb64(header["recipients"][0]["wrapped_key"]), private, info=DOMAIN + b"wrap/")
    aead = ChaCha20Poly1305(data_key)
    stride = CHUNK + 16
    payload = b"".join(aead.decrypt(nonce(i // stride, i + stride >= len(ciphertext)),
                                    ciphertext[i:i + stride], DOMAIN + b"payload/")
                       for i in range(0, len(ciphertext), stride))
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as tar:
        for member in tar:
            if (len(files) >= 33 or member.type != tarfile.REGTYPE or member.name in files
                    or not re.fullmatch(r"(?:manifest|layers/[a-z_]+)\.json", member.name)
                    or not 0 < member.size <= len(payload)):
                raise CopyRefused("unexpected bundle member")
            files[member.name] = tar.extractfile(member).read()
    manifest = decode(files.pop("manifest.json"))
    checked = check_manifest(manifest)
    if (manifest["bundle_id"] != "bnd_" + record.copy_id or manifest["bundle_id"] != header["bundle_id"]
            or manifest["source"] != header["source"] or manifest["source"]["instance_id"] != record.box_id
            or manifest["source"]["generation"] != record.generation
            or manifest["created_at"] != header["created_at"]
            or datetime.fromisoformat(manifest["created_at"]) != record.created_at):
        raise CopyRefused("bundle source does not match the completion record")
    contents = {}
    for entry in manifest["layers"]:
        if entry["path"] != f"layers/{entry['id']}.json":
            raise CopyRefused("layer path does not match its ID")
        data = files.pop(entry["path"])
        check_layer(entry, data)
        contents[entry["id"]] = decode(data)
    if files:
        raise CopyRefused("bundle contains unlisted layers")
    layers = {entry["id"]: entry for entry in checked.manifest["layers"]}
    if layers["app_data_refs"]["schema"] != REFS_SCHEMA or layers["box_config"]["schema"] != box_config.LAYER_SCHEMA:
        raise CopyRefused("unsupported required layer schema")
    box_config.check(contents["box_config"])
    refs = References.model_validate(contents["app_data_refs"])
    if (refs.repository != record.repository or refs.run_id != record.run_id or refs.snapshots != record.snapshots
            or sorted(unit.id for unit in refs.units) != record.snapshots):
        raise CopyRefused("bundle references do not match the completion record")
    return manifest, refs


INVALID_COPY = (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError, InvalidSignature, InvalidTag,
                BundleRefused, tarfile.TarError)
