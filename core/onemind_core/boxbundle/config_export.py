# SPDX-License-Identifier: Apache-2.0
"""Cleartext projection of the box bundle schema for private Git."""
from typing import Any

import yaml

from ..store import Database
from .box_config import collect
from .manifest import BundleRefused, schema

SETTINGS_SCHEMA = "onemind.io/config-as-code/settings/v1"

def render(doc: dict) -> str:
    return yaml.safe_dump(doc, sort_keys=True, allow_unicode=True)

def _exportable(rules: dict) -> bool:
    # This projector reads direct properties and items. A composed or referenced schema
    # could carry annotations we cannot see here, so leave it out.
    indirect = {"$ref", "$dynamicRef", "allOf", "anyOf", "oneOf", "if", "then", "else", "dependentSchemas"}
    return (rules.get("x-config-export") is True and not (rules.get("x-secret") or rules.get("writeOnly"))
            and indirect.isdisjoint(rules))


def _project(value: Any, rules: dict) -> Any:
    # Only explicitly classified fields and array items can cross into cleartext.
    if isinstance(value, dict):
        return {
            key: _project(value[key], field)
            for key, field in rules.get("properties", {}).items()
            if key in value and _exportable(field)
        }
    if isinstance(value, list):
        item = rules.get("items", {})
        return [_project(entry, item) for entry in value] if _exportable(item) else []
    return value


def settings_document(db: Database) -> dict:
    layer, _ = collect(db)
    rules = schema()["$defs"]["boxConfig"]
    if not _exportable(rules):
        raise BundleRefused(["box config is unavailable for cleartext export"])
    return {"schema": SETTINGS_SCHEMA, **_project(layer, rules)}


def export_settings(db: Database) -> str:
    return render(settings_document(db))


def settings_rules() -> dict:
    """The same allowlist also defines the accepted cleartext input shape."""
    def restrict(rules: dict) -> dict:
        out = {key: rules[key] for key in (
            "type", "enum", "pattern", "minLength", "maxLength", "minimum", "maximum", "maxItems",
        ) if key in rules}
        if "properties" in rules or "object" in rules.get("type", ()):
            properties = {key: restrict(field) for key, field in rules.get("properties", {}).items()
                          if _exportable(field)}
            out.update(properties=properties, additionalProperties=False,
                       required=[key for key in rules.get("required", ()) if key in properties])
        if isinstance(items := rules.get("items"), dict) and _exportable(items):
            out["items"] = restrict(items)
        return out

    rules = schema()["$defs"]["boxConfig"]
    if not _exportable(rules):
        raise BundleRefused(["box config is unavailable for cleartext export"])
    out = restrict(rules)
    out["properties"]["schema"] = {"const": SETTINGS_SCHEMA}
    out["required"].append("schema")
    return out
