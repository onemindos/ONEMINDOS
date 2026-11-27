# SPDX-License-Identifier: Apache-2.0
"""Layer a of a box bundle: the box's own settings (docs/architecture/BOX-EXPORT-IMPORT.md §3.a).

What it holds today, read from the gateway database (the only place these settings live on release/next):
- `box`      box name and time zone (`onboarding_settings`, onboarding.py);
- `updates`  the owner's app update policy (`update_policy`, automation/updatepolicy.py), or null for defaults;
- `backups`  the backup choice, each destination's *location* and the content-tier apps (`backups_*`).

What it never holds: credentials. The gateway does not store destination passwords or S3 keys
(backups/store.py), and `collect` drops any credential-looking key that reaches a destination's config
anyway, and says so in the bundle's `excluded` list.

Import is in three steps, and this module does the first two as plain functions:
1. `check`  validate the layer against `$defs/boxConfig`; fields a newer OneMind added are set aside and named;
2. `plan`   compare it with this box and list every change, field by field, for the preview;
3. `apply`  write only what is safe to write without a person: the box name, the time zone and the update
            policy. Destinations need their credentials typed again and the content tier needs its own
            approval (`backup.content.set`), so `plan` marks them `needs_owner` and `apply` never writes them.
No route calls `apply` yet. When one does (phase 3), it runs as an approved owner action, never directly.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from zoneinfo import available_timezones

from pydantic import ValidationError

from ..automation.cron import parse_ranges
from ..automation.updatepolicy import (
    UpdatePolicyBody,
    UpdatePolicyRepository,
    UpdatePolicyRow,
)
from ..backups.store import BackupsRepository
from ..onboarding import OnboardingService, SettingsRow
from ..store import Database
from .manifest import BundleRefused, Layer, make_layer, problems_of, schema, validator

LAYER_ID = "box_config"
LAYER_SCHEMA = "onemind.io/box-bundle/box-config/v1"
# Location keys the backup agent reads per destination kind (BackupService._targets). Anything else in a
# destination's config is left out and named: an allow-list, so a credential under a new name cannot slip through.
LOCATION_KEYS = {"usb": frozenset({"usb_uuid"}), "box": frozenset({"url", "user", "append_only"}),
                 "rest": frozenset({"url", "user", "append_only"}), "s3": frozenset({"endpoint", "bucket", "prefix", "region"})}
SAFE_SECTIONS = frozenset({"box", "updates"})


def collect(db: Database) -> tuple[dict, list[dict]]:
    """The box-config layer as data, plus the extra `excluded` lines it produced. Read-only."""
    onboarding = OnboardingService(db).read()
    policy = UpdatePolicyRepository(db).get()
    backups = BackupsRepository(db)
    excluded: list[dict] = []
    destinations = []
    for row in sorted(backups.destinations(), key=lambda r: r.id):
        config = {}
        allowed = LOCATION_KEYS.get(row.kind, frozenset())
        for key, value in sorted((row.config or {}).items()):
            if key not in allowed or not isinstance(value, (str, bool)) or (isinstance(value, str) and _has_userinfo(value)):
                excluded.append({"what": f"backup destination {row.id}: {key}",
                                 "reason": "not a plain location setting (it may be a credential); it is typed again on the new box"})
                continue
            config[key] = value
        destinations.append({"id": row.id, "kind": row.kind, "label": row.label, "is_primary": bool(row.is_primary),
                             "append_only": bool(row.append_only), "config": config})
    doc = {
        "schema": LAYER_SCHEMA,
        "box": {"box_name": onboarding["box_name"], "time_zone": onboarding["time_zone"]},
        "updates": UpdatePolicyBody.model_validate(policy["doc"]).model_dump() if policy else None,
        "backups": {
            "choice": onboarding["backup_choice"],
            "primary_destination_id": next((d["id"] for d in destinations if d["is_primary"]), None),
            "destinations": destinations,
            "content_tier_apps": sorted(backups.content_tier()),
        },
    }
    problems = problems_of(validator("boxConfig"), doc)
    if problems:  # the box holds something the schema does not allow: never write a bundle that cannot be read back
        raise BundleRefused(problems)
    return doc, excluded


def _has_userinfo(value: str) -> bool:
    """True for a URL that carries a user name and password (scheme://user:pw@host)."""
    head = value.split("/", 3)
    return "://" in value and len(head) > 2 and "@" in head[2]


@lru_cache(maxsize=1)
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def layer(db: Database) -> tuple[Layer, list[dict]]:
    """The layer ready for `manifest.build_manifest`, plus its extra `excluded` lines."""
    doc, excluded = collect(db)
    items = 2 + len(doc["backups"]["destinations"]) + len(doc["backups"]["content_tier_apps"])
    return make_layer(LAYER_ID, LAYER_SCHEMA, doc, items=items, sensitive=False), excluded


def _branch_properties(node: dict, rules: dict) -> dict:
    """Property rules from the `allOf` if/then branches that match this object (the `kind` -> config allow-list)."""
    out: dict = {}
    for branch in rules.get("allOf", []):
        cond = branch.get("if", {}).get("properties", {})
        if cond and all(k in node and ("const" in c and node[k] == c["const"] or "enum" in c and node[k] in c["enum"])
                        for k, c in cond.items()):
            out.update(branch.get("then", {}).get("properties", {}))
    return out


def _set_aside(node: object, rules: dict, defs: dict, path: str, skipped: list[str]) -> object:
    """Drop object keys the schema does not define (where it forbids extra keys), recording each path."""
    # Walks `properties`, `items`, `$ref` and the `allOf` if/then branches whose `if` is a const/enum on a sibling
    # property (the per-kind destination config). A future layer schema that adds other branch shapes with objects
    # inside (oneOf, anyOf) must extend this walk (the test for unknown fields would show it).
    if "$ref" in rules:
        rules = defs[rules["$ref"].rsplit("/", 1)[-1]]
    if isinstance(node, dict) and "properties" in rules:
        props = {**rules["properties"], **_branch_properties(node, rules)}
        out = {}
        for key, value in node.items():
            here = f"{path}/{key}" if path else key
            if key not in props:
                if rules.get("additionalProperties") is False:
                    skipped.append(here)
                    continue
                out[key] = value
            else:
                out[key] = _set_aside(value, props[key], defs, here, skipped)
        return out
    if isinstance(node, list) and isinstance(rules.get("items"), dict):
        return [_set_aside(v, rules["items"], defs, f"{path}/{i}", skipped) for i, v in enumerate(node)]
    return node


@dataclass(frozen=True)
class Checked:
    doc: dict
    skipped: list[str]  # fields a newer OneMind wrote that this box does not understand; never applied


def check(doc: object, *, newer_minor: bool = False) -> Checked:
    """Accept or refuse a box-config layer read from a bundle.

    `newer_minor` is `ManifestCheck.newer_minor`. Only a bundle from a newer OneMind may carry fields this box
    does not know: those are set aside and named. At this version or older an unknown field is refused."""
    if not isinstance(doc, dict) or doc.get("schema") != LAYER_SCHEMA:
        raise BundleRefused([f"not a {LAYER_SCHEMA} layer"])
    defs = schema()["$defs"]
    skipped: list[str] = []
    clean = _set_aside(copy.deepcopy(doc), defs["boxConfig"], defs, "", skipped)
    if skipped and not newer_minor:
        raise BundleRefused([f"{path}: not a field of this layer version" for path in skipped])
    problems = problems_of(validator("boxConfig"), clean)
    if problems:
        raise BundleRefused(problems)
    zone = clean["box"]["time_zone"]
    if zone is not None and _zones() and zone not in _zones():  # no tzdata at all: nothing to compare against
        clean["box"]["time_zone"] = None  # this box keeps its own zone; the preview names the one it could not use
        skipped.append(f"box/time_zone ({zone} is not installed on this box)")
    return Checked(clean, skipped)


def plan(current: dict, incoming: Checked) -> list[dict]:
    """Every difference between this box (`collect`) and the bundle, for the import preview. Writes nothing.

    Each line: section, field, current, incoming and what an import does:
    `same`, `change` (written by `apply`), `keep` (the bundle has nothing to say: this box keeps its value),
    `needs_owner` (only the owner can finish it: credentials or a separate approval), `skipped` (unknown field)."""
    out: list[dict] = []
    new = incoming.doc
    for field in ("box_name", "time_zone"):
        cur, inc = current["box"][field], new["box"][field]
        action = "keep" if inc is None else ("same" if cur == inc else "change")
        out.append({"section": "box", "field": field, "current": cur, "incoming": inc, "action": action})
    cur_up, inc_up = current["updates"], new["updates"]
    out.append({"section": "updates", "field": "policy", "current": cur_up, "incoming": inc_up,
                "action": "keep" if inc_up is None else ("same" if cur_up == inc_up else "change")})
    have = {d["id"]: d for d in current["backups"]["destinations"]}
    for dest in new["backups"]["destinations"]:
        mine = have.get(dest["id"])
        same = mine == dest
        out.append({"section": "backups", "field": f"destination {dest['id']}", "current": mine, "incoming": dest,
                    "action": "same" if same else "needs_owner"})
    cur_tier, inc_tier = sorted(current["backups"]["content_tier_apps"]), sorted(new["backups"]["content_tier_apps"])
    out.append({"section": "backups", "field": "content_tier_apps", "current": cur_tier, "incoming": inc_tier,
                "action": "same" if cur_tier == inc_tier else "needs_owner"})
    out += [{"section": "unknown", "field": path, "current": None, "incoming": None, "action": "skipped"}
            for path in incoming.skipped]
    return out


def apply(db: Database, incoming: Checked, *, now: datetime, by: dict, window_exists: Callable[[str], bool],
          sections: frozenset[str] = SAFE_SECTIONS) -> list[str]:
    """Write the safe sections of the layer to this box; returns the fields written.

    Only `box` and `updates` can be written here. Everything is checked before the first write, with the same checks
    `UpdatePolicyService.put` makes (the update window exists on this box, the AI schedule parses), and the writes
    share one transaction, so a refusal or a database error leaves the box as it was. The caller is an approved owner action (phase 4), never a route directly."""
    if not sections <= SAFE_SECTIONS:
        raise ValueError(f"only {sorted(SAFE_SECTIONS)} can be written without the owner: {sorted(sections - SAFE_SECTIONS)}")
    new = incoming.doc
    svc = OnboardingService(db)
    cur = svc.read()
    values = {"box_name": cur["box_name"], "time_zone": cur["time_zone"],
              "backup_choice": cur["backup_choice"], "backup_destination_id": cur["backup_destination_id"]}
    written: list[str] = []
    if "box" in sections:
        for field in ("box_name", "time_zone"):
            if new["box"][field] is not None and new["box"][field] != cur[field]:
                values[field] = new["box"][field]
                written.append(f"box.{field}")
        if written and (values["box_name"] is None or values["time_zone"] is None):
            raise BundleRefused(["box: a box name and a time zone are both needed before either is saved"])
    policy = None
    if "updates" in sections and new["updates"] is not None:
        try:
            body = UpdatePolicyBody.model_validate(new["updates"])
            parse_ranges(body.ai_schedule.off)
        except (ValidationError, ValueError) as exc:
            raise BundleRefused([f"updates: {exc}"]) from None
        if not window_exists(body.window_id):
            raise BundleRefused([f"updates: this box has no update window {body.window_id!r}; create it first"])
        repo = UpdatePolicyRepository(db)
        current = repo.get()
        if current is None or current["doc"] != body.model_dump():
            policy = body.model_dump()
    # Every check passed: write, both in one transaction, so a database error cannot leave half of it.
    if written or policy is not None:
        with db.session.begin() as session:
            if written:
                session.execute(db.insert()(SettingsRow).values(id="box", **values).on_conflict_do_update(
                    index_elements=[SettingsRow.id], set_=values))
            if policy is not None:
                session.execute(db.insert()(UpdatePolicyRow).values(id="global", resumed={}, updated_at=now, doc=policy, updated_by=by)
                                .on_conflict_do_update(index_elements=[UpdatePolicyRow.id],
                                                       set_={"updated_at": now, "doc": policy, "updated_by": by}))
    if policy is not None:
        written.append("updates.policy")
    return written
