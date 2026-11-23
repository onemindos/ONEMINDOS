# SPDX-License-Identifier: Apache-2.0
"""The tips pack: its format, its signature check and the loader that picks the first good pack (#669).

A pack is a folder holding two files:
- `pack.json`, the whole pack as one JSON document (format `Pack` below; tip text only, clips are
  separate release assets, tips/README.md);
- `pack.json.sig`, the Ed25519 signature over the exact bytes of pack.json, base64 encoded.

The trusted public key is a PEM file inside the read-only image (/usr/lib/onemind/keys/tips.pub by
default), so only an OS update changes which key the box trusts.

A pack is refused, and the loader goes on to the next candidate, when:
- the signature is missing or does not verify (checked before the JSON is even parsed);
- the document does not match the format (unknown fields, unknown collection, a duplicate id...);
- the running OS version is outside the pack's `os` range: a pack made for a newer OS ("too_new")
  may name screens this OS does not have.
v1 has one candidate, the image pack at /usr/share/onemind/tips. When none is good the box serves no
tips (and logs why); it never serves an unchecked pack. #790 adds a newer signed pack in /data/tips
ahead of the image pack, which is why the loader takes a list.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .. import __version__

log = logging.getLogger("onemind.tips")

SCHEMA = "onemind.io/tips-pack/v1"
PACK_FILE = "pack.json"
SIG_FILE = "pack.json.sig"
MAX_PACK_BYTES = 4 * 1024 * 1024
MAX_SIG_BYTES = 1024
MAX_KEY_BYTES = 16384
SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"
VERSION = r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
# Paths under /v1/tips that are routes, so a tip may not take them as its id.
RESERVED_IDS = frozenset({"collections", "whats-new"})
Role = Literal["owner", "adult", "guest", "child", "teen"]
Version = tuple[int, int, int]


def parse_version(text: str) -> Version | None:
    """The leading MAJOR.MINOR.PATCH of a version string (0.1.20261112025704 and 0.1.0-dev both count)."""
    m = re.match(r"^(\d{1,20})\.(\d{1,20})\.(\d{1,20})", text.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def running_version(os_release: Path) -> Version:
    """ONEMIND_VERSION from the image's os-release (os/assemble/assemble.py writes it), else the gateway's own."""
    try:
        text = os_release.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    for line in text.splitlines():
        if line.startswith("ONEMIND_VERSION="):
            found = parse_version(line.split("=", 1)[1].strip().strip("\"'"))
            if found is not None:
                return found
    fallback = parse_version(__version__)
    assert fallback is not None
    return fallback


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Opens(_Strict):
    dashboard: str = Field(pattern=r"^/", max_length=200)
    phone: str = Field(pattern=r"^onemind://", max_length=200)


class Clip(_Strict):
    release: str = Field(pattern=SLUG, max_length=64)
    caption: str = Field(min_length=1, max_length=300)


class Tip(_Strict):
    id: str = Field(pattern=SLUG, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    collection: str = Field(pattern=SLUG, max_length=64)
    body: str = Field(min_length=1, max_length=4000)
    opens: Opens
    from_: str = Field(alias="from", pattern=VERSION)
    until: str | None = Field(default=None, pattern=VERSION)
    skip_if_done: list[str] = Field(default_factory=list, max_length=20)
    # Who sees the tip. Absent: every person.
    roles: list[Role] | None = Field(default=None, min_length=1)
    clip: Clip | None = None

    @model_validator(mode="after")
    def _check(self):
        for ev in self.skip_if_done:
            if not re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", ev):
                raise ValueError(f"skip_if_done event {ev!r} is not an event name")
        if self.roles is not None and len(set(self.roles)) != len(self.roles):
            raise ValueError("roles must be unique")
        return self

    def shows_on(self, version: Version) -> bool:
        lo = parse_version(self.from_)
        hi = parse_version(self.until) if self.until else None
        return lo <= version and (hi is None or version <= hi)

    def shows_to(self, role: str) -> bool:
        return self.roles is None or role in self.roles


class Collection(_Strict):
    id: str = Field(pattern=SLUG, max_length=64)
    title: str = Field(min_length=1, max_length=80)


class WhatsNew(_Strict):
    version: str = Field(pattern=VERSION)
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=4000)


class OsRange(_Strict):
    from_: str = Field(alias="from", pattern=VERSION)
    until: str | None = Field(default=None, pattern=VERSION)


class Pack(_Strict):
    schema_: Literal["onemind.io/tips-pack/v1"] = Field(alias="schema")
    version: str = Field(pattern=r"^[0-9A-Za-z.+-]{1,64}$")
    os: OsRange
    collections: list[Collection] = Field(max_length=50)
    checklist: list[str] = Field(default_factory=list, max_length=50)
    tips: list[Tip] = Field(max_length=1000)
    whats_new: list[WhatsNew] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _check(self):
        cols = [c.id for c in self.collections]
        if len(set(cols)) != len(cols):
            raise ValueError("collection ids must be unique")
        tip_ids = [t.id for t in self.tips]
        if len(set(tip_ids)) != len(tip_ids):
            raise ValueError("tip ids must be unique")
        if RESERVED_IDS & set(tip_ids):
            raise ValueError(f"tip ids {sorted(RESERVED_IDS)} are routes, not tips")
        missing = sorted({t.collection for t in self.tips} - set(cols))
        if missing:
            raise ValueError(f"tips name unknown collections: {missing}")
        if set(self.checklist) - set(tip_ids) or len(set(self.checklist)) != len(self.checklist):
            raise ValueError("checklist must name each of its tips once")
        return self


class PackRefused(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def load_key(path: Path) -> Ed25519PublicKey | None:
    """The trusted Ed25519 public key (PEM), or None when it is missing or not an Ed25519 key."""
    try:
        with path.open("rb") as f:
            pem = f.read(MAX_KEY_BYTES + 1)
        key = serialization.load_pem_public_key(pem) if len(pem) <= MAX_KEY_BYTES else None
    except (OSError, ValueError, TypeError, UnsupportedAlgorithm):
        return None
    return key if isinstance(key, Ed25519PublicKey) else None


def _read(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as f:
            data = f.read(limit + 1)
    except FileNotFoundError:
        raise PackRefused("missing") from None
    except OSError:
        raise PackRefused("unreadable") from None
    if len(data) > limit:
        raise PackRefused("too_large")
    return data


def read_pack(folder: Path, key: Ed25519PublicKey | None, version: Version) -> Pack:
    """The pack in `folder`, or PackRefused(reason). The signature is checked before anything is parsed."""
    if key is None:
        raise PackRefused("no_key")
    data = _read(folder / PACK_FILE, MAX_PACK_BYTES)
    try:
        sig = base64.b64decode(_read(folder / SIG_FILE, MAX_SIG_BYTES).strip(), validate=True)
    except PackRefused as exc:
        raise PackRefused("unsigned" if exc.reason == "missing" else exc.reason) from None
    except (binascii.Error, ValueError):
        raise PackRefused("bad_signature") from None
    try:
        key.verify(sig, data)
    except InvalidSignature:
        raise PackRefused("bad_signature") from None
    try:
        pack = Pack.model_validate(json.loads(data))
    except (ValueError, ValidationError):  # json.JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise PackRefused("invalid") from None
    if version < parse_version(pack.os.from_):
        raise PackRefused("too_new")
    if pack.os.until and version > parse_version(pack.os.until):
        raise PackRefused("too_old")
    return pack


@dataclass(frozen=True)
class Loaded:
    pack: Pack | None
    source: str | None
    refused: list[tuple[str, str]] = field(default_factory=list)


def load_first(candidates: list[tuple[str, Path]], key: Ed25519PublicKey | None, version: Version) -> Loaded:
    """The first candidate (name, folder) whose pack is good; the refused ones and why. Never raises."""
    refused: list[tuple[str, str]] = []
    for name, folder in candidates:
        try:
            pack = read_pack(folder, key, version)
        except PackRefused as exc:
            log.warning("tips pack %s refused: %s", name, exc.reason)
            refused.append((name, exc.reason))
            continue
        return Loaded(pack, name, refused)
    return Loaded(None, None, refused)
