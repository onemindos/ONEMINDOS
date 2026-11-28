# SPDX-License-Identifier: Apache-2.0
"""Validate a private Git snapshot and apply an owner-approved, revision-bound change."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from zoneinfo import available_timezones

import yaml
from jsonschema import Draft202012Validator
from sqlalchemy import update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, ScalarNode

from ..automation.cron import parse_ranges, resolve_tz
from ..automation.store import AutomationRepository
from ..automation.updatepolicy import UpdatePolicyRepository
from ..backups.store import BackupsRepository, DestinationRow
from ..context import Gateway
from ..executors import ExecResult
from ..onboarding import OnboardingService
from ..store import Database
from .box_config import normalize_off_hours_days
from .config_export import SETTINGS_SCHEMA, render, settings_document, settings_rules
from .config_inventory import collect_inventory, validate_inventory
from .manifest import BundleRefused, canonical, sha256

FILES = ("settings.yaml", "apps.yaml", "users.yaml", "schedules.yaml")
SCHEMAS = {name: f"onemind.io/config-as-code/{name.removesuffix('.yaml')}/v1" for name in FILES}


class ConfigLoader(yaml.SafeLoader):
    """Reject ambiguous maps and unbounded YAML structures before construction."""

    depth = 0

    def compose_node(self, parent, index):
        event = self.peek_event()
        if isinstance(event, AliasEvent) or event.anchor is not None or event.tag is not None or self.depth >= 20:
            raise yaml.YAMLError("anchors, aliases, explicit tags and deeply nested YAML are unavailable")
        self.depth += 1
        try:
            return super().compose_node(parent, index)
        finally:
            self.depth -= 1

    def construct_mapping(self, node, deep=False):
        if isinstance(node, MappingNode):
            seen = set()
            for key, _ in node.value:
                if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str" or key.value in seen:
                    raise yaml.YAMLError("mapping keys must be unique strings")
                seen.add(key.value)
        return super().construct_mapping(node, deep=deep)


def read_documents(files: dict[str, str]) -> dict[str, dict]:
    out = {}
    for name in FILES:
        if name not in files:
            continue
        try:
            doc = yaml.load(files[name], Loader=ConfigLoader)
        except (yaml.YAMLError, ValueError, OverflowError, RecursionError):
            raise BundleRefused([f"{name}: invalid YAML"]) from None
        schema_id = SCHEMAS[name]
        if not isinstance(doc, dict) or doc.get("schema") != schema_id:
            raise BundleRefused([f"{name}: expected schema {schema_id}"])
        if schema_id == SETTINGS_SCHEMA:
            normalize_off_hours_days(doc.get("updates"))
            if not Draft202012Validator(settings_rules()).is_valid(doc):
                raise BundleRefused([f"{name}: invalid or unrecognized settings fields"])
            apps = doc["backups"]["content_tier_apps"]
            if len(set(apps)) != len(apps):
                raise BundleRefused([f"{name}: repeated content-tier app"])
            doc["backups"]["content_tier_apps"] = sorted(apps)
            if doc["updates"] is not None:
                try:
                    parse_ranges(doc["updates"]["ai_schedule"]["off"])
                    resolve_tz(doc["updates"]["ai_schedule"]["tz"], doc["box"]["time_zone"] or "UTC")
                except ValueError:
                    raise BundleRefused([f"{name}: invalid AI update schedule"]) from None
            out[name] = doc
        else:
            out[name] = validate_inventory(name, doc)
    return out


@contextmanager
def snapshot(gw: Gateway, *, writing: bool = False) -> Iterator[Gateway]:
    """Use one database snapshot for all repositories and commit approved writes together."""
    with gw.db.engine.connect() as conn:
        sqlite = conn.dialect.name == "sqlite"
        if not sqlite:
            conn = conn.execution_options(isolation_level="SERIALIZABLE" if writing else "REPEATABLE READ")
        with conn.begin():
            if sqlite:
                conn.exec_driver_sql("BEGIN IMMEDIATE" if writing else "BEGIN")
            db = Database(gw.db.engine)
            db.session = sessionmaker(conn, expire_on_commit=False)
            yield replace(gw, db=db)


def collect_all(gw: Gateway, backups) -> dict[str, dict]:
    return {"settings.yaml": settings_document(gw.db), **collect_inventory(gw, backups)}


@dataclass(frozen=True)
class Preview:
    revision: str
    base_revision: str
    changes: list[dict]
    blockers: list[str]
    patch: dict


class ConfigApply:
    def __init__(self, gw: Gateway, backups):
        self.gw = gw
        self.backups = backups

    def preview(self, proposed: dict[str, dict]) -> Preview:
        with snapshot(self.gw) as gw:
            live = collect_all(gw, self.backups)
            onboarding = OnboardingService(gw.db).read()
            base = self.base_revision(live, onboarding)
            revision = sha256(canonical({"base": base, "proposed": proposed}))
            changes = []
            blockers = []
            patch = {}
            for name, after in proposed.items():
                before = live[name]
                if before == after:
                    continue
                changes.append({"file": name, "before": render(before), "after": render(after)})
                if name == "settings.yaml":
                    self._settings(gw.db, before, after, onboarding, patch, blockers)
                elif name == "schedules.yaml":
                    self._schedules(before, after, patch, blockers)
                else:
                    blockers.append(f"{name} is inventory. Make those changes in Apps or People before applying.")
            return Preview(revision, base, changes, blockers, patch)

    @staticmethod
    def base_revision(live: dict, onboarding: dict) -> str:
        # The selected destination influences backup-choice changes but is never in the cleartext export.
        return sha256(canonical({"files": live, "onboarding": onboarding}))

    @staticmethod
    def _settings(db, before, after, onboarding, patch, blockers):
        fields = {**after["box"], "backup_choice": after["backups"]["choice"],
                  "backup_destination_id": onboarding["backup_destination_id"]}
        if after["backups"]["content_tier_apps"] != before["backups"]["content_tier_apps"]:
            blockers.append("Change the content tier through Backups. It requires its own approval.")
        if after["box"] != before["box"] or fields["backup_choice"] != onboarding["backup_choice"]:
            if not fields["box_name"] or fields["time_zone"] not in available_timezones():
                blockers.append("Set a box name and an installed IANA time zone.")
            elif fields["backup_choice"] != onboarding["backup_choice"]:
                choice = fields["backup_choice"]
                fields["backup_destination_id"] = None
                if choice != "later":
                    kind = {"usb": "usb", "peer": "box", "s3": "s3"}[choice]
                    candidates = [d for d in BackupsRepository(db).destinations() if d.kind == kind]
                    if len(candidates) != 1:
                        blockers.append("Select an existing destination in Backups before changing the backup choice.")
                    else:
                        fields["backup_destination_id"] = candidates[0].id
            patch["box"] = {
                "before": {key: onboarding[key] for key in fields},
                "after": fields,
            }
        if after["updates"] != before["updates"]:
            policy = after["updates"]
            if policy is not None and AutomationRepository(db).get_window(policy["window_id"]) is None:
                blockers.append("Create the selected update window on this box first.")
            patch["updates"] = {"before": before["updates"], "after": policy}

    @staticmethod
    def _schedules(before, after, patch, blockers):
        if before["backup"] != after["backup"] or before["automation"] != after["automation"]:
            blockers.append("Change the backup job or automation schedule through its own settings.")
        old = {row["destination_id"]: row["cadence"] for row in before["destination_copies"]}
        new = {row["destination_id"]: row["cadence"] for row in after["destination_copies"]}
        if old.keys() != new.keys():
            blockers.append("Set up the same destinations on this box before changing copy cadence.")
            return
        changed = {key: {"before": old[key], "after": value} for key, value in new.items() if old[key] != value}
        if changed:
            patch["copy_cadence"] = changed

    def recheck(self, action) -> str | None:
        with snapshot(self.gw) as gw:
            return self._stale(gw, action.params)

    def _stale(self, gw, params) -> str | None:
        onboarding = OnboardingService(gw.db).read()
        if self.base_revision(collect_all(gw, self.backups), onboarding) != params["base_revision"]:
            return "Box configuration changed. Review a new diff before requesting approval again."
        policy = params["patch"].get("updates", {}).get("after")
        if policy is not None and AutomationRepository(gw.db).get_window(policy["window_id"]) is None:
            return "The update window was removed. Review a new diff."
        return None

    def run(self, action, finish) -> None:
        params = action.params
        patch = params["patch"]
        try:
            with snapshot(self.gw, writing=True) as gw:
                problem = self._stale(gw, params)
                if not problem and "box" in patch:
                    OnboardingService(gw.db).save(patch["box"]["after"])
                if not problem and "updates" in patch:
                    policy = patch["updates"]["after"]
                    # An unset policy uses defaults, while preserving unrelated per-app back-off overrides.
                    UpdatePolicyRepository(gw.db).put(
                        now=gw.clock(), doc=policy, updated_by=action.decided_by,
                    )
                if not problem and "copy_cadence" in patch:
                    with gw.db.session.begin() as session:
                        for destination_id, change in patch["copy_cadence"].items():
                            session.execute(update(DestinationRow).where(DestinationRow.id == destination_id)
                                            .values(copy_cadence=change["after"]))
        except DBAPIError as exc:
            # Serialization failures roll back the whole change. A lost connection at commit is ambiguous.
            if getattr(exc.orig, "sqlstate", None) != "40001":
                raise
            finish(ExecResult("failed", "Box configuration changed concurrently. Review a new diff."))
            return
        if problem:
            finish(ExecResult("failed", problem))
        else:
            finish(ExecResult("succeeded", "Approved box configuration applied."))
