# SPDX-License-Identifier: Apache-2.0
"""Config-as-code inventories use live records and closed per-file schemas."""
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text

from onemind_core.backups.store import SCHEMA, DestinationRow
from onemind_core.boxbundle.config_inventory import (
    _SAFE_APP_FIELDS,
    collect_inventory,
    validate_inventory,
)
from onemind_core.boxbundle.manifest import BundleRefused
from onemind_core.identity.models import PasskeyRow, UserRow
from onemind_core.store import SchemaVersionRow, migrate

MARKER = "should-never-cross-the-export-boundary"


def test_reviewed_app_fields_match_declared_app_types():
    apps_dir = Path(__file__).resolve().parents[2] / "apps"
    for app_id, fields in _SAFE_APP_FIELDS.items():
        manifest = yaml.safe_load((apps_dir / app_id / "onemind.app.yaml").read_text())
        settings = {setting["name"]: setting for setting in manifest["spec"]["settings"]}
        for name, rule in fields.items():
            declared = settings[name]
            if "enum" in rule:
                assert declared["type"] == "enum"
                assert rule["enum"] == declared["enum"]
            else:
                assert {key: declared[key] for key in rule} == rule


def test_exports_installed_runtime_versions_and_only_schema_approved_app_settings(client, clock):
    gw = client.app.state.gateway
    for app_id, state in [("uptime-kuma", "installed"), ("offline-maps", "stopped"),
                          ("kiwix", "installed"), ("mosquitto", "removed"), ("whoami", "installed")]:
        gw.repo.set_app_state(app_id, state, clock.now)
    gw.repo.set_runtime("kiwix", clock.now, version="3.8.1", settings={"reserve_mb": MARKER, "mirror": MARKER})
    gw.repo.set_runtime("offline-maps", clock.now, version="1.2.3", settings={
        "flavor": "dark", "language": MARKER, "unreviewed": MARKER,
    })
    gw.repo.set_runtime("uptime-kuma", clock.now, version="1.0.0", settings={"arbitrary": MARKER})
    doc = collect_inventory(gw, client.app.state.backups)["apps.yaml"]
    assert doc["apps"] == [
        {"id": "kiwix", "version": "3.8.1", "settings": {}},
        {"id": "offline-maps", "version": "1.2.3", "settings": {"flavor": "dark"}},
        {"id": "uptime-kuma", "version": "1.0.0", "settings": {}},
        {"id": "whoami", "version": None, "settings": {}},
    ]
    assert MARKER not in yaml.safe_dump(doc)


def test_exports_users_and_roles_without_identity_credentials(client, clock):
    gw = client.app.state.gateway
    with gw.db.session.begin() as session:
        for user_id, username, role, disabled in [("usr_b", None, "guest", True), ("usr_a", "al", "owner", False)]:
            session.add(UserRow(id=user_id, username=username, display_name="Example", role=role, disabled=disabled,
                                password_hash=MARKER, totp_secret=MARKER, totp_pending=MARKER, enrol_hash=MARKER,
                                created_at=clock.now, updated_at=clock.now))
        session.add(PasskeyRow(id=MARKER, user_id="usr_a", label=MARKER, public_key=MARKER.encode(),
                               created_at=clock.now))
    doc = collect_inventory(gw, client.app.state.backups)["users.yaml"]
    assert doc["users"] == [
        {"id": "usr_a", "username": "al", "display_name": "Example", "role": "owner", "disabled": False},
        {"id": "usr_b", "username": None, "display_name": "Example", "role": "guest", "disabled": True},
    ]
    assert MARKER not in yaml.safe_dump(doc)


def test_exports_backup_and_automation_schedules_without_runtime_history_or_payloads(client, clock, monkeypatch):
    gw = client.app.state.gateway
    backups = client.app.state.backups
    for suffix, choice in [("f", "weekly"), ("0", None)]:
        dest = DestinationRow(id="dst_" + suffix * 16, kind="usb", label=MARKER, config={"location": MARKER},
                              created_at=clock.now)
        if choice:
            dest.copy_cadence = choice
        backups.repo.add_destination(dest)
    rules = client.app.state.automation.repo
    for rule_id, trigger in [("rule_scheduled", {"schedule": {"cron": "10 2 * * *", "tz": "box"}}),
                             ("rule_event", {"event": {"subject": MARKER}})]:
        rules.add_rule(id=rule_id, name="Daily", enabled=False, trigger=trigger, conditions=[{"example": MARKER}],
                       actions=[{"example": MARKER}], options={}, created_by={"id": MARKER},
                       created_at=clock.now, updated_at=clock.now, last_fired_at=clock.now)
    doc = collect_inventory(gw, backups)["schedules.yaml"]
    assert doc["backup"] == {"cadence": "manual", "minute_utc": None}
    assert doc["automation"] == [
        {"id": "rule_scheduled", "name": "Daily", "enabled": False, "cron": "10 2 * * *", "tz": "box"},
    ]
    assert doc["destination_copies"] == [
        {"destination_id": "dst_" + "0" * 16, "cadence": "manual"},
        {"destination_id": "dst_" + "f" * 16, "cadence": "weekly"},
    ]
    assert MARKER not in yaml.safe_dump(doc)
    # Agent presence enables the hourly schedule. Collection makes no calls to the agent.
    monkeypatch.setattr(backups, "agent", object())
    hourly = collect_inventory(gw, backups)["schedules.yaml"]
    assert hourly["backup"] == {"cadence": "hourly", "minute_utc": backups.run_minute()}


def test_inventory_validates_versions_unknown_fields_duplicates_and_nested_shapes(client):
    docs = collect_inventory(client.app.state.gateway, client.app.state.backups)
    with pytest.raises(BundleRefused, match="unknown inventory file"):
        validate_inventory("other.yaml", {})
    for file, doc in docs.items():
        assert validate_inventory(file, doc) == doc
        with pytest.raises(BundleRefused, match="expected schema"):
            validate_inventory(file, {**doc, "schema": doc["schema"].replace("/v1", "/v2")})
        with pytest.raises(BundleRefused, match="fields do not match"):
            validate_inventory(file, {**doc, "unexpected": MARKER})

    app_doc = docs["apps.yaml"]
    approved = {"id": "offline-maps", "version": "1.0", "settings": {"flavor": "dark"}}
    unknown_app = {"id": "unknown-app", "version": "1.0", "settings": {}}
    assert validate_inventory("apps.yaml", {**app_doc, "apps": [unknown_app, approved]})["apps"] == [
        approved, unknown_app,
    ]
    with pytest.raises(BundleRefused, match="duplicate id"):
        validate_inventory("apps.yaml", {**app_doc, "apps": [approved, approved]})
    for unsafe in [approved | {"settings": {"flavor": MARKER}}, approved | {"settings": {"token": MARKER}},
                   unknown_app | {"settings": {"flavor": "dark"}}]:
        with pytest.raises(BundleRefused, match="approved export schema"):
            validate_inventory("apps.yaml", {**app_doc, "apps": [unsafe]})

    user = {"id": "usr_a", "username": None, "display_name": "Owner", "role": "owner", "disabled": False}
    for unsafe in [user | {"password_hash": MARKER}, user | {"passkeys": []}, user | {"role": "agent"}]:
        with pytest.raises(BundleRefused, match="fields do not match"):
            validate_inventory("users.yaml", {**docs["users.yaml"], "users": [unsafe]})

    schedule_doc = docs["schedules.yaml"]
    schedule = {"id": "rule_a", "name": "Example", "cron": "10  2 * * *", "tz": "box", "enabled": True}
    assert validate_inventory("schedules.yaml", {**schedule_doc, "automation": [schedule]})["automation"] == [
        schedule | {"cron": "10 2 * * *"},
    ]
    for invalid in [schedule | {"cron": MARKER}, schedule | {"tz": "Mars/Olympus"}]:
        with pytest.raises(BundleRefused, match="invalid automation"):
            validate_inventory("schedules.yaml", {**schedule_doc, "automation": [invalid]})
    invalid_backup = deepcopy(schedule_doc)
    invalid_backup["backup"]["minute_utc"] = 12
    with pytest.raises(BundleRefused, match="manual backups use null"):
        validate_inventory("schedules.yaml", invalid_backup)
    invalid_copies = {"destination_id": "dst_" + "0" * 16, "cadence": "quarterly"}
    with pytest.raises(BundleRefused, match="fields do not match"):
        validate_inventory("schedules.yaml", {**schedule_doc, "destination_copies": [invalid_copies]})


def test_destination_copy_cadence_migrates_existing_backups_database(client, clock):
    db = client.app.state.gateway.db
    backups = client.app.state.backups.repo
    dest_id = "dst_" + "0" * 16
    backups.add_destination(DestinationRow(id=dest_id, kind="usb", label="Disk", config={}, created_at=clock.now))
    with db.engine.begin() as conn:
        conn.execute(text("ALTER TABLE backups_destinations DROP COLUMN copy_cadence"))
        conn.execute(SchemaVersionRow.__table__.update().where(SchemaVersionRow.feature == "backups").values(version=1))
    assert migrate(db.engine, schemas=[SCHEMA]) == {"backups": 2}
    assert [(row.id, row.copy_cadence) for row in backups.destinations()] == [(dest_id, "manual")]
