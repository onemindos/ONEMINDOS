# SPDX-License-Identifier: Apache-2.0
"""The box bundle manifest: what is inside, in which version, and the checksum of every layer.

Rules (docs/architecture/BOX-EXPORT-IMPORT.md §4):
- every layer is canonical JSON (sorted keys, no spaces, UTF-8), so the same data gives the same bytes and
  the same sha256 on any machine;
- the manifest lists each layer's path, schema, size and sha256; a reader checks both before using a layer;
- `format.major` must equal this reader's major; a higher `format.minor` is accepted (newer bundles only add
  optional fields and layers) and reported, so the import preview can say "made by a newer OneMind";
- `excluded` always lists what the bundle deliberately leaves out, so the owner reads it before importing.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_ID = "onemind.io/box-bundle/v1"
FORMAT_MAJOR = 1
FORMAT_MINOR = 0
SCHEMA_NAME = "onemind.box-bundle.schema.json"
_REPO_SCHEMA = Path(__file__).resolve().parents[3] / "sdk" / "schema" / SCHEMA_NAME
_IMAGE_SCHEMA = Path("/opt/onemind/sdk/schema") / SCHEMA_NAME

LAYER_IDS = ("box_config", "people", "policies", "apps", "app_data_refs", "fabric", "box_keys")

# What every bundle leaves out, whatever layers it holds (design §3.h). Shown on the import preview.
ALWAYS_EXCLUDED: tuple[dict, ...] = (
    {"what": "passkeys and other sign-in keys",
     "reason": "a passkey's private key never leaves the person's device and is bound to the box's web name; "
               "people sign in once with their password or a recovery path and enrol their passkey again"},
    {"what": "OneMind's release signing keys",
     "reason": "the update root is OneMind's, held on YubiKeys (D-031); it is never on a box, so never in a bundle"},
    {"what": "the disk encryption key and the TPM binding",
     "reason": "they belong to this machine's disk; the new box makes its own and prints a new kit (D-020)"},
    {"what": "the emergency kit's owner key",
     "reason": "only the printed kit holds it; the bundle is encrypted to it, so it cannot also be inside"},
    {"what": "sessions, sign-in challenges and one-time codes",
     "reason": "short-lived; a restored box starts with everyone signed out"},
    {"what": "app data volumes and container images",
     "reason": "large; they come back from the restic backup the bundle points at, and images by digest"},
    {"what": "logs and the audit log",
     "reason": "the audit log stays on the old box and in its backups; the new box starts its own chain and "
               "records the import as its first entries"},
)


class BundleRefused(Exception):
    """The bundle cannot be used here; nothing was read further. `problems` says why, one line each."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def canonical(doc: object) -> bytes:
    """The one byte form of a JSON document that every checksum in a bundle is taken over."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def schema() -> dict:
    """The bundle schema: the repo copy in development and tests, the image copy on a box."""
    for path in (_REPO_SCHEMA, _IMAGE_SCHEMA):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"{SCHEMA_NAME} not found in sdk/schema or /opt/onemind/sdk/schema")


def validator(ref: str | None = None) -> Draft202012Validator:
    """A validator for the whole manifest, or for one `$defs` entry (for example `boxConfig`)."""
    doc = schema()
    target = doc if ref is None else {"$ref": f"#/$defs/{ref}", "$defs": doc["$defs"]}
    return Draft202012Validator(target, format_checker=FormatChecker())


def problems_of(v: Draft202012Validator, doc: object) -> list[str]:
    out = []
    for err in sorted(v.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        where = "/".join(map(str, err.absolute_path)) or "(top)"
        out.append(f"{where}: {err.message}")
    return out


@dataclass(frozen=True)
class Layer:
    """One layer, ready to go into a bundle: its manifest entry and its exact bytes."""
    entry: dict
    data: bytes


def make_layer(layer_id: str, layer_schema: str, doc: dict, *, items: int, sensitive: bool) -> Layer:
    if layer_id not in LAYER_IDS:
        raise ValueError(f"unknown layer {layer_id!r}")
    data = canonical(doc)
    return Layer({"id": layer_id, "schema": layer_schema, "path": f"layers/{layer_id}.json", "sha256": sha256(data),
                  "size": len(data), "items": items, "sensitive": sensitive}, data)


@dataclass(frozen=True)
class Source:
    instance_id: str
    box_name: str | None
    onemind_version: str
    arch: str = "unknown"
    generation: int = 0


def build_manifest(source: Source, layers: list[Layer], *, now: datetime, excluded: list[dict] | None = None,
                   bundle_id: str | None = None) -> dict:
    """The manifest for these layers. It is checked against the schema before it is returned."""
    if now.tzinfo is None:
        raise ValueError("now must carry a time zone")
    ids = [layer.entry["id"] for layer in layers]
    if len(set(ids)) != len(ids):
        raise ValueError(f"a layer appears twice: {ids}")
    doc = {
        "schema": SCHEMA_ID,
        "format": {"major": FORMAT_MAJOR, "minor": FORMAT_MINOR},
        "bundle_id": bundle_id or "bnd_" + secrets.token_hex(16),
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "source": {"instance_id": source.instance_id, "box_name": source.box_name,
                   "onemind_version": source.onemind_version, "arch": source.arch, "generation": source.generation},
        "layers": [layer.entry for layer in layers],
        "excluded": [*ALWAYS_EXCLUDED, *(excluded or [])],
    }
    problems = problems_of(validator(), doc)
    if problems:
        raise BundleRefused(problems)
    return doc


@dataclass
class ManifestCheck:
    """What a reader learned from a manifest it accepted."""
    manifest: dict
    newer_minor: bool
    unknown_layers: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)  # manifest fields a newer OneMind added; shown, never used


def check_manifest(doc: object) -> ManifestCheck:
    """Accept or refuse a manifest read from a bundle (version first, then the schema)."""
    if not isinstance(doc, dict):
        raise BundleRefused(["the manifest is not a JSON object"])
    if doc.get("schema") != SCHEMA_ID:
        raise BundleRefused([f"not a OneMind box bundle (schema {doc.get('schema')!r})"])
    fmt = doc.get("format") if isinstance(doc.get("format"), dict) else {}
    major, minor = fmt.get("major"), fmt.get("minor")
    if major != FORMAT_MAJOR:
        raise BundleRefused([f"bundle format {major}.x needs a OneMind that reads it; this box reads {FORMAT_MAJOR}.x"])
    newer = isinstance(minor, int) and minor > FORMAT_MINOR
    unknown: list[str] = []
    if newer and isinstance(doc.get("layers"), list):
        # A newer minor may add layers this box does not know: set them aside (named on the preview), check the rest.
        known = [entry for entry in doc["layers"] if not isinstance(entry, dict) or entry.get("id") in LAYER_IDS]
        unknown = [str(entry.get("id")) for entry in doc["layers"] if isinstance(entry, dict) and entry.get("id") not in LAYER_IDS]
        doc = {**doc, "layers": known}
        if not known:
            raise BundleRefused([f"every layer in this bundle is newer than this box understands ({', '.join(unknown)}); update this box first"])
    problems = problems_of(validator(), doc)
    if not newer:  # this version wrote nothing else: an unknown field here is a typo or a hand edit, not a newer OneMind
        problems += _unknown_fields(doc)
    ids = [entry["id"] for entry in doc.get("layers", []) if isinstance(entry, dict) and "id" in entry]
    if len(set(ids)) != len(ids):
        problems.append(f"layers: a layer appears twice ({ids})")
    problems += [f"layers: {entry['id']} must be at layers/{entry['id']}.json, not {entry.get('path')!r}"
                 for entry in doc.get("layers", []) if isinstance(entry, dict) and entry.get("id") in LAYER_IDS
                 and entry.get("path") != f"layers/{entry['id']}.json"]
    if problems:
        raise BundleRefused(problems)
    known_fields = set(schema()["properties"])
    return ManifestCheck(doc, newer_minor=newer, unknown_layers=unknown,
                         unknown_fields=sorted(k for k in doc if k not in known_fields))


def _unknown_fields(doc: dict) -> list[str]:
    """Fields the manifest schema does not name, in the manifest, `source` and each layer entry."""
    defs = schema()
    top = defs["properties"]
    out = [f"{key}: not a field of bundle format {FORMAT_MAJOR}.{FORMAT_MINOR}" for key in sorted(doc) if key not in top]
    source = doc.get("source")
    if isinstance(source, dict):
        out += [f"source/{key}: not a field of bundle format {FORMAT_MAJOR}.{FORMAT_MINOR}"
                for key in sorted(source) if key not in top["source"].get("properties", {})]
    layer_props = _layer_entry_props()
    for i, entry in enumerate(doc.get("layers", [])):
        if isinstance(entry, dict):
            out += [f"layers/{i}/{key}: not a field of bundle format {FORMAT_MAJOR}.{FORMAT_MINOR}"
                    for key in sorted(entry) if key not in layer_props]
    return out


def _layer_entry_props() -> set[str]:
    items = schema()["properties"]["layers"]["items"]
    if "$ref" in items:
        items = schema()["$defs"][items["$ref"].rsplit("/", 1)[-1]]
    return set(items.get("properties", {}))


def check_layer(entry: dict, data: bytes) -> None:
    """Refuse a layer whose bytes are not the ones the manifest lists."""
    problems = []
    if len(data) != entry["size"]:
        problems.append(f"{entry['path']}: size {len(data)} does not match the manifest ({entry['size']})")
    if sha256(data) != entry["sha256"]:
        problems.append(f"{entry['path']}: checksum does not match the manifest")
    if problems:
        raise BundleRefused(problems)
