# SPDX-License-Identifier: Apache-2.0
"""The list of system apps ("Built in" apps): the only authority for which app ids are system apps.

Why a file in the image and not a flag in an app's own manifest: anyone can write a manifest, so a
manifest that says "I am a system app" proves nothing. The list lives at
/usr/lib/onemind/system-apps.json, inside the read-only, signed OS image (RAUC-signed bundle,
verity-protected root), so only an OS update can change it. The gateway loads it once at start.

Rules enforced here, on top of the file being part of the signed image:
- a file that group or others can write is refused (a tampered or misplaced copy is not trusted);
- Files, Approvals, Settings, Market, Updates, Backups and Notifications can never be switched off,
  whatever the file says (NEVER_DISABLE is a floor in code: they are how the owner repairs a box,
  gets it back after a failure and hears that something is wrong).
A bad file never stops the gateway: the list is then empty, so no manifest can claim to be a system
app and nothing extra can be disabled, and the error is logged.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("onemind.systemlist")

SCHEMA = "onemind.io/system-apps/v1"
IMAGE_FILE = Path("/usr/lib/onemind/system-apps.json")
REPO_FILE = Path(__file__).resolve().parents[2] / "os/rootfs/layers/onemind/usr/lib/onemind/system-apps.json"
SYSTEM_DIR = "_system"  # apps/_system/<id>/ is the only folder a container system app may live in
NEVER_DISABLE = frozenset({"files", "approvals", "settings", "market", "updates", "backups", "notifications"})
_ID = re.compile(r"^[a-z]([a-z0-9-]{0,57}[a-z0-9])?$")
CLASSES = ("container", "native")
UPDATES = ("os", "own")
DISABLES = ("allowed", "never")


class SystemListError(ValueError):
    pass


@dataclass(frozen=True)
class SystemApp:
    id: str
    name: str
    klass: str      # container (a catalog app run as a workload) | native (part of the OS or dashboard)
    update: str     # os (updated with the OS image) | own (updated like any app, but not removable)
    disable: str    # allowed | never

    @property
    def can_disable(self) -> bool:
        return self.disable == "allowed" and self.id not in NEVER_DISABLE


@dataclass(frozen=True)
class SystemList:
    apps: dict[str, SystemApp]

    def ids(self) -> frozenset[str]:
        return frozenset(self.apps)

    def get(self, app_id: str) -> SystemApp | None:
        return self.apps.get(app_id)


EMPTY = SystemList({})


def parse(doc: object) -> SystemList:
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or set(doc) != {"schema", "apps"}:
        raise SystemListError(f"must be an object with exactly schema ({SCHEMA}) and apps")
    rows = doc["apps"]
    if not isinstance(rows, list):
        raise SystemListError("apps must be a list")
    out: dict[str, SystemApp] = {}
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or set(r) != {"id", "name", "class", "update", "disable"}:
            raise SystemListError(f"apps[{i}] must have exactly id, name, class, update, disable")
        app_id, name = r["id"], r["name"]
        if not isinstance(app_id, str) or not _ID.match(app_id):
            raise SystemListError(f"apps[{i}].id is not a valid app id")
        if not isinstance(name, str) or not 1 <= len(name) <= 80:
            raise SystemListError(f"apps[{i}].name must be 1-80 characters")
        for key, allowed in (("class", CLASSES), ("update", UPDATES), ("disable", DISABLES)):
            if r[key] not in allowed:
                raise SystemListError(f"apps[{i}].{key} must be one of {', '.join(allowed)}")
        if app_id in out:
            raise SystemListError(f"duplicate id {app_id}")
        out[app_id] = SystemApp(app_id, name, r["class"], r["update"], r["disable"])
    return SystemList(out)


def load(path: Path | None = None) -> SystemList:
    """The list at path, else the image's file, else the repo's copy (development). Never raises."""
    candidates = [path] if path is not None else [IMAGE_FILE, REPO_FILE]
    for p in candidates:
        try:
            st = p.stat()
        except OSError:
            continue
        try:
            if st.st_mode & 0o022:
                raise SystemListError("the file is writable by group or others")
            return parse(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log.error("system apps list %s refused: %s; no app is a system app until it is fixed", p, exc)
            return EMPTY
    log.warning("no system apps list found; no app is a system app")
    return EMPTY
