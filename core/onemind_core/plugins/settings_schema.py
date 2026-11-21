# SPDX-License-Identifier: Apache-2.0
"""Bounded, offline JSON settings schemas snapshotted at approved installation."""
import json
from pathlib import PurePosixPath

from jsonschema import Draft202012Validator, SchemaError

from ..appstore.appsettings import pattern_risk


def compile_schema(schema):
    count = 0

    def expand(value, depth=0, refs=()):
        nonlocal count
        count += 1
        if depth > 16 or count > 2048:
            raise ValueError("plugin settings schema exceeds complexity limits")
        if isinstance(value, list):
            return [expand(v, depth + 1, refs) for v in value]
        if not isinstance(value, dict):
            return value
        if "$dynamicRef" in value or "$id" in value:
            raise ValueError("plugin settings dynamic references and schema IDs are unsupported")
        if "pattern" in value:
            pattern = value["pattern"]
            if not isinstance(pattern, str) or len(pattern) > 128 or pattern_risk(pattern):
                raise ValueError("plugin settings pattern is not bounded")
        if "patternProperties" in value:
            raise ValueError("plugin settings patternProperties are unsupported")
        other = {k: expand(v, depth + 1, refs) for k, v in value.items() if k != "$ref"}
        if "$ref" not in value:
            return other
        ref = value["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/") or ref in refs:
            raise ValueError("plugin settings references must be nonrecursive local JSON pointers")
        target = schema
        try:
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise ValueError("plugin settings reference does not resolve") from None
        return {"allOf": [expand(target, depth + 1, (*refs, ref)), other]}

    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("plugin settings schema must describe an object")
    dialect = schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
    if dialect != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("plugin settings schema must use draft 2020-12")
    expanded = expand(schema)
    try:
        Draft202012Validator.check_schema(expanded)
    except SchemaError as exc:
        raise ValueError("invalid plugin settings JSON schema") from exc
    return Draft202012Validator(expanded)


def load_settings_schema(app):
    settings = (app.manifest.get("spec", {}).get("extensions") or {}).get("settings")
    if settings is None:
        return None
    name = settings.get("schema") if isinstance(settings, dict) else None
    if not isinstance(name, str) or not name or PurePosixPath(name).is_absolute():
        raise ValueError("invalid plugin settings schema path")
    root = app.dir.resolve()
    path = app.dir
    for part in name.split("/"):
        if part in {"", ".", ".."}:
            raise ValueError("plugin settings schema path escapes its bundle")
        path = path / part
        if path.is_symlink():
            raise ValueError("plugin settings schema must not traverse symlinks")
    try:
        if not path.resolve().is_relative_to(root) or not path.is_file() or path.stat().st_size > 131072:
            raise ValueError("plugin settings schema is missing, outside its bundle or too large")
        schema = json.loads(path.read_text())
    except OSError as exc:
        raise ValueError("plugin settings schema cannot be read") from exc
    compile_schema(schema)
    return schema
