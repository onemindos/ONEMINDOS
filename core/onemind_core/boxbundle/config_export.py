# SPDX-License-Identifier: Apache-2.0
"""Cleartext projection of the box bundle schema for private Git."""
from typing import Any

import yaml

from ..store import Database
from .box_config import collect
from .manifest import BundleRefused, schema

SETTINGS_SCHEMA = "onemind.io/config-as-code/settings/v1"


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


def export_settings(db: Database) -> str:
    layer, _ = collect(db)
    rules = schema()["$defs"]["boxConfig"]
    if not _exportable(rules):
        raise BundleRefused(["box config is unavailable for cleartext export"])
    settings = _project(layer, rules)
    return yaml.safe_dump({"schema": SETTINGS_SCHEMA, **settings}, sort_keys=True, allow_unicode=True)
