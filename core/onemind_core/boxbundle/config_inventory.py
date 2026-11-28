# SPDX-License-Identifier: Apache-2.0
"""Cleartext v1 inventories for installed apps, household users and schedules."""

from typing import get_args

from jsonschema import Draft202012Validator
from sqlalchemy import select

from ..automation.cron import Cron, resolve_tz
from ..automation.store import RuleRow
from ..backups.service import BackupService
from ..backups.store import CopyCadence, DestinationRow
from ..catalog import APP_ID_RE
from ..context import Gateway
from ..identity.models import UserRow
from ..identity.service import PERSON_ROLES
from ..ledger import AppRuntimeRow, AppStateRow
from .manifest import BundleRefused


def _object(properties: dict, *, required: bool = True) -> dict:
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": list(properties) if required else []}


def _integer(minimum: int, maximum: int) -> dict:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


# Independently reviewed fields of the apps' spec.settings. Manifest text, custom apps, URLs,
# usernames, and arbitrary strings do not grant permission to write runtime values to cleartext.
# An app without a review has a closed, empty settings schema and still appears in the inventory.
_PORT = _integer(1, 65535)
_POLL = _integer(1, 3600)
_SAFE_APP_FIELDS = {
    "bacnet-adapter": {"bacnet_port": _PORT, "poll_seconds": _POLL},
    "can-adapter": {"can_port": _PORT, "poll_seconds": _POLL},
    "kiwix": {"reserve_mb": _integer(0, 1048576)},
    "library-chat": {"sources": _integer(1, 8)},
    "modbus-adapter": {"modbus_port": _PORT, "modbus_unit": _integer(0, 255), "poll_seconds": _POLL},
    "mosquitto": {"nats_mqtt_port": _PORT},
    "offline-maps": {"flavor": {"enum": ["light", "dark", "white", "grayscale", "black"]}},
    "opcua-adapter": {"poll_seconds": _POLL},
}
_APP_SETTING_RULES = {app_id: Draft202012Validator(_object(fields, required=False))
                      for app_id, fields in _SAFE_APP_FIELDS.items()}
_NO_APP_SETTINGS = Draft202012Validator(_object({}))

_APP = _object({
    "id": {"type": "string", "pattern": APP_ID_RE.pattern},
    "version": {"type": ["string", "null"], "maxLength": 64, "pattern": "^[A-Za-z0-9][A-Za-z0-9._+-]*$"},
    "settings": {"type": "object"},
})
_USER = _object({
    "id": {"type": "string", "minLength": 1, "maxLength": 40},
    "username": {"type": ["string", "null"], "maxLength": 64},
    "display_name": {"type": "string", "maxLength": 100},
    "role": {"enum": list(PERSON_ROLES)},
    "disabled": {"type": "boolean"},
})
_AUTOMATION = _object({
    "id": {"type": "string", "minLength": 1, "maxLength": 40},
    "name": {"type": "string", "maxLength": 120},
    "enabled": {"type": "boolean"},
    "cron": {"type": "string", "maxLength": 200},
    "tz": {"type": "string", "maxLength": 128},
})
_DESTINATION = _object({
    "destination_id": {"type": "string", "pattern": "^dst_[0-9a-f]{16}$"},
    "cadence": {"enum": list(get_args(CopyCadence))},
})
_BACKUP = _object({
    "cadence": {"enum": ["hourly", "manual"]},
    "minute_utc": {"type": ["integer", "null"], "minimum": 0, "maximum": 59},
})


def _schema_id(file: str) -> str:
    return f"onemind.io/config-as-code/{file.removesuffix('.yaml')}/v1"


def _inventory_schema(file: str, **properties: dict) -> Draft202012Validator:
    return Draft202012Validator(_object({"schema": {"const": _schema_id(file)}, **properties}))


_RULES = {
    "apps.yaml": _inventory_schema("apps.yaml", apps={"type": "array", "items": _APP}),
    "users.yaml": _inventory_schema("users.yaml", users={"type": "array", "items": _USER}),
    "schedules.yaml": _inventory_schema("schedules.yaml", backup=_BACKUP,
        automation={"type": "array", "items": _AUTOMATION},
        destination_copies={"type": "array", "items": _DESTINATION}),
}
_SORT_KEYS = {"apps": "id", "users": "id", "automation": "id", "destination_copies": "destination_id"}


def _app_settings(app_id: str, settings: dict) -> dict:
    fields = _SAFE_APP_FIELDS.get(app_id, {})
    return {key: settings[key] for key, rule in fields.items()
            if key in settings and Draft202012Validator(rule).is_valid(settings[key])}


def collect_inventory(gw: Gateway, backups: BackupService) -> dict[str, dict]:
    with gw.db.session() as session:
        apps = [{"id": app_id, "version": version, "settings": _app_settings(app_id, settings or {})}
                for app_id, version, settings in session.execute(
                    select(AppStateRow.app_id, AppRuntimeRow.version, AppRuntimeRow.settings)
                    .outerjoin(AppRuntimeRow, AppRuntimeRow.app_id == AppStateRow.app_id)
                    .where(AppStateRow.status.in_(("installed", "stopped"))))]
        users = [dict(row) for row in session.execute(select(
            UserRow.id, UserRow.username, UserRow.display_name, UserRow.role, UserRow.disabled)).mappings()]
        automation = []
        for row in session.execute(select(RuleRow.id, RuleRow.name, RuleRow.enabled, RuleRow.trigger)).mappings():
            if schedule := row["trigger"].get("schedule"):
                automation.append({"id": row["id"], "name": row["name"], "enabled": row["enabled"],
                                   "cron": schedule["cron"], "tz": schedule["tz"]})
        copies = [{"destination_id": dest_id, "cadence": cadence}
                  for dest_id, cadence in session.execute(select(DestinationRow.id, DestinationRow.copy_cadence))]

    hourly = backups.enabled and backups.s.schedule
    backup = {"cadence": "hourly" if hourly else "manual", "minute_utc": backups.run_minute() if hourly else None}
    inventories = {"apps.yaml": {"apps": apps}, "users.yaml": {"users": users}, "schedules.yaml": {
        "backup": backup, "automation": automation, "destination_copies": copies}}
    return {file: validate_inventory(file, {"schema": _schema_id(file), **doc}) for file, doc in inventories.items()}


def validate_inventory(file: str, doc: object) -> dict:
    rules = _RULES.get(file)
    if rules is None:
        raise BundleRefused(["unknown inventory file"])
    if not isinstance(doc, dict) or doc.get("schema") != _schema_id(file):
        raise BundleRefused([f"{file}: expected schema {_schema_id(file)}"])
    if not rules.is_valid(doc):
        raise BundleRefused([f"{file}: fields do not match the v1 schema"])
    normalized = dict(doc)
    for key, identity in _SORT_KEYS.items():
        if key not in doc:
            continue
        rows = sorted(doc[key], key=lambda row: row[identity])
        if len({row[identity] for row in rows}) != len(rows):
            raise BundleRefused([f"{file}: {key} contains a duplicate {identity}"])
        normalized[key] = rows
    for app in normalized.get("apps", ()):
        if not _APP_SETTING_RULES.get(app["id"], _NO_APP_SETTINGS).is_valid(app["settings"]):
            raise BundleRefused([f"{file}: app settings do not match their approved export schema"])
    if file == "schedules.yaml":
        backup = normalized["backup"]
        if (backup["cadence"] == "hourly") != (backup["minute_utc"] is not None):
            raise BundleRefused([f"{file}: hourly backups need a UTC minute and manual backups use null"])
        try:
            automation = []
            for row in normalized["automation"]:
                cron = Cron.parse(row["cron"])
                resolve_tz(row["tz"])
                automation.append({**row, "cron": cron.expr})
        except ValueError:
            raise BundleRefused([f"{file}: invalid automation cron or time zone"]) from None
        normalized["automation"] = automation
    return normalized
