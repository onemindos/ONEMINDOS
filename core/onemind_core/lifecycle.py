# SPDX-License-Identifier: Apache-2.0
"""App lifecycle (umbrel-parity PD-03..PD-07; contract §12.4 and §12.5).

What lives here, in plain words:

- the table of app action types: which app states each may start from, what state the app is in
  while it runs, what it becomes afterwards, how risky it is and who may even ask for it;
- the **plan**: a description of what an action would do (versions, bundle fingerprint, data at
  risk), rendered with no side effects. `plan_sha256` is a fingerprint of that plan. The owner
  approves *that fingerprint*; if the app's files changed in between, the approval is refused
  instead of running something the owner never saw (the "approve what you read" rule);
- sealed app credentials (PD-07): a generated password per app, encrypted at rest, shown only to
  the owner on demand, never to an agent, never written to a plan, event or audit line.

Nothing in this module changes the outside world; executors.py does, after approval.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from collections.abc import Callable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import DateTime, String, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from .catalog import AppEntry
from .ledger import AppRuntime, Base
from .store import Database, FeatureSchema, SqlRepository

# ---- the action types ---------------------------------------------------------------------


@dataclass(frozen=True)
class LifecycleType:
    claim: str  # app status while the action runs
    allowed: frozenset[str]  # statuses it may start from
    allow_absent: bool  # may the app have no state row at all (a fresh install)
    final: str | None  # status after success (None = the state row is deleted)
    risk: str  # contract §12.3 risk class
    agent_may_request: bool = True


_S = frozenset
TYPES: dict[str, LifecycleType] = {
    "app.install": LifecycleType("installing", _S({"failed", "unknown", "removed"}), True, "installed", "sensitive"),
    "app.start": LifecycleType("starting", _S({"stopped", "failed", "unknown"}), False, "installed", "write"),
    "app.stop": LifecycleType("stopping", _S({"installed", "failed", "unknown"}), False, "stopped", "write"),
    "app.restart": LifecycleType("restarting", _S({"installed", "failed", "unknown"}), False, "installed", "write"),
    "app.update": LifecycleType("updating", _S({"installed", "failed"}), False, "installed", "write"),
    "app.configure": LifecycleType("configuring", _S({"installed"}), False, "installed", "write"),
    # Remove keeps the data (contract §12.5): the app is gone, its volumes stay. `removed` is shown
    # to clients as status not_installed with data_kept true.
    "app.remove": LifecycleType(
        "removing", _S({"installed", "stopped", "failed", "unknown"}), False, "removed", "write"
    ),
    # Deleting the data is its own request: owner only, typed confirmation, never an agent.
    "app.delete_data": LifecycleType("deleting_data", _S({"removed"}), False, None, "destructive", False),
}
ACTION_TYPES = tuple(TYPES)
TRANSIENT = frozenset(t.claim for t in TYPES.values())  # statuses that mean "an action is running"

SETTING_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
# Settings are plain configuration. Anything that looks like a secret must go through the sealed
# path instead (contract §12.1 "Secrets"), so it never lands in params, plans or the audit log.
SECRETISH_RE = re.compile(r"pass|secret|token|credential|private|api[_-]?key|auth", re.IGNORECASE)
MAX_SETTINGS = 50
MAX_SETTING_VALUE = 1024


def settings_problem(settings: dict) -> str | None:
    if len(settings) > MAX_SETTINGS:
        return f"at most {MAX_SETTINGS} settings"
    for k, v in settings.items():
        if not isinstance(k, str) or not SETTING_NAME_RE.match(k):
            return f"setting name {k!r} is not valid"
        if SECRETISH_RE.search(k):
            return f"setting {k!r} looks like a secret; secrets are never sent as settings"
        if isinstance(v, bool) or (isinstance(v, (int, float)) and math.isfinite(v)):
            continue  # typed by the app's spec.settings (§12.22); checked against the field there
        if not isinstance(v, str) or len(v) > MAX_SETTING_VALUE:
            return f"setting {k!r} must be a string of at most {MAX_SETTING_VALUE} characters"
    return None


# ---- the plan -----------------------------------------------------------------------------


def canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def plan_hash(action_type: str, params: dict, target: dict, objects: list) -> str:
    """sha256 of the canonical JSON of {type, params, target, objects} (contract §12.4)."""
    body = canonical({"type": action_type, "params": params, "target": target, "objects": objects})
    return "sha256:" + hashlib.sha256(body.encode()).hexdigest()


def bundle_sha256(app: AppEntry) -> str | None:
    """Fingerprint of the app's manifest and every regular file under its manifests folder."""
    h = hashlib.sha256()
    try:
        root = app.manifests_dir
    except ValueError:
        return None
    files = [app.dir / "onemind.app.yaml"]
    if root.is_dir():
        files += sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    base = app.dir.resolve()
    for p in files:
        try:
            rel = p.resolve().relative_to(base).as_posix()
            data = p.read_bytes()
        except (OSError, ValueError):
            continue
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
    return "sha256:" + h.hexdigest()


_SUMMARY = {
    "app.install": "Install {name} {to}.",
    "app.start": "Start {name}: bring its workloads back up from the stopped state.",
    "app.stop": "Stop {name}: scale its workloads to zero. Its data is untouched.",
    "app.restart": "Restart {name}: roll its workloads one by one.",
    "app.update": "Update {name} from {frm} to {to}. If it is not healthy afterwards, the previous revision is restored.",
    "app.configure": "Change the settings of {name}, then restart it.",
    "app.remove": "Remove {name}. Its workloads are deleted; its data stays on the box.",
    "app.delete_data": "Permanently delete all stored data of {name}. This cannot be undone.",
}


def render_plan(action_type: str, params: dict, app: AppEntry, runtime: AppRuntime | None, status: str | None) -> dict:
    """The plan for one action, with `plan_sha256`. Pure: no cluster call, no write."""
    md = app.manifest.get("metadata") or {}
    to_version = str(md.get("version")) if md.get("version") is not None else None
    frm = runtime.version if runtime else None
    name = md.get("name") or app.id
    ns = f"app-{app.id}"
    bundle = bundle_sha256(app)
    obj: dict = {"kind": "App", "id": app.id, "action": action_type, "bundle_sha256": bundle}
    warnings: list[str] = []
    volumes: list[dict] = []
    if action_type in ("app.install", "app.update"):
        obj["to_version"] = to_version
    if action_type == "app.update":
        obj["from_version"] = frm
        if frm is not None and frm == to_version and runtime and runtime.bundle_sha256 == bundle:
            warnings.append("The catalog offers the version that is already installed; nothing would change.")
        warnings.append(
            "Health-gated: the update is kept only if every workload becomes ready; otherwise the previous "
            "revision is restored. Volume snapshots before the update arrive with box backups."
        )
    if action_type == "app.configure":
        obj["settings"] = dict(params.get("settings") or {})
    if action_type in ("app.remove", "app.stop"):
        volumes.append({"kind": "PersistentVolumeClaim", "namespace": ns, "selector": "all", "effect": "kept"})
    if action_type == "app.delete_data":
        volumes.append({"kind": "PersistentVolumeClaim", "namespace": ns, "selector": "all", "effect": "deleted"})
        obj["namespace"] = ns
        warnings.append("All files and databases of this app are deleted. There is no undo.")
    if bundle is None:
        warnings.append("The app's manifest folder could not be read.")
    objects = [obj]
    target = {"kind": "app", "id": app.id}
    plan = {
        "summary": _SUMMARY[action_type].format(name=name, to=to_version or "", frm=frm or "the current version"),
        "objects": objects, "images": [], "volumes": volumes, "nodes": [], "warnings": warnings,
        "app_status": status or "not_installed",
    }
    return {"plan": plan, "plan_sha256": plan_hash(action_type, params, target, objects), "target": target}


# ---- what an executor receives and may report --------------------------------------------

_PROGRESS: ContextVar[Callable[[str, int], None] | None] = ContextVar("onemind_progress", default=None)


def report_progress(step: str, pct: int) -> None:
    """Called by an executor: tell the owner what step it is on. A no-op outside an action."""
    cb = _PROGRESS.get()
    if cb is not None:
        cb(step, max(0, min(100, int(pct))))


def set_progress_callback(cb: Callable[[str, int], None] | None):
    return _PROGRESS.set(cb)


def reset_progress_callback(token) -> None:
    _PROGRESS.reset(token)


@dataclass(frozen=True)
class AppCredentialGrant:
    """The generated login handed to the executor so it can create the app's Secret. Never logged."""

    secret_name: str
    username: str | None
    password: str = field(repr=False, default="")


@dataclass(frozen=True)
class ExecContext:
    params: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)  # settings to apply (configure: new; others: stored)
    credentials: AppCredentialGrant | None = None
    restart: bool = True  # app.configure: roll the workloads after the settings are written (§12.22 restart: false)
    # The app's declared secrets with their current values (executors.AppSecret; appsecrets/).
    # Never shown in a repr, step, result or log line.
    secrets: tuple = field(default=(), repr=False)


# ---- sealed credentials (PD-07) ----------------------------------------------------------


class CredentialRow(Base):
    __tablename__ = "app_credentials"
    app_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sealed: Mapped[str] = mapped_column(Text)  # hex(nonce || AES-256-GCM ciphertext)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


CREDENTIALS_SCHEMA = FeatureSchema("credentials")


def credentials_spec(app: AppEntry) -> dict | None:
    c = (app.manifest.get("spec") or {}).get("credentials")
    return c if isinstance(c, dict) else None


class CredentialStore(SqlRepository):
    """Generated app passwords, encrypted with AES-256-GCM under a key file next to the audit log.

    The key file is created 0600 on first use. The app id is bound in as associated data, so a
    row copied to another app does not decrypt. Backups must include the key file with the
    database (docs/leap/core/APP-LIFECYCLE.md).
    """

    def __init__(self, db: Database, key_path: Path):
        super().__init__(db)
        self.key_path = key_path

    def _key(self) -> bytes:
        try:
            return bytes.fromhex(self.key_path.read_text().strip())
        except FileNotFoundError:
            pass
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        # Write the whole key to a private temp file, then hard-link it into place: the link is
        # atomic and fails if the key exists, so a concurrent reader never sees a half-written key
        # and nobody overwrites a key that already sealed passwords.
        tmp = self.key_path.with_name(f".{self.key_path.name}.{secrets.token_hex(4)}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key.hex())
        try:
            os.link(tmp, self.key_path)
        except FileExistsError:  # another request created it first: use theirs
            return bytes.fromhex(self.key_path.read_text().strip())
        finally:
            tmp.unlink(missing_ok=True)
        return key

    def has(self, app_id: str) -> bool:
        with self.db.session() as s:
            return s.get(CredentialRow, app_id) is not None

    def ensure(self, app: AppEntry, now: datetime) -> tuple[AppCredentialGrant | None, bool]:
        """The app's login: the stored one, or a freshly generated one. (grant, generated_now)."""
        spec = credentials_spec(app)
        if spec is None:
            return None, False
        username = spec.get("username") if isinstance(spec.get("username"), str) else None
        with self.db.session() as s:
            row = s.get(CredentialRow, app.id)
        generated = row is None
        if row is None:
            password = secrets.token_urlsafe(24)
            nonce = secrets.token_bytes(12)
            ct = AESGCM(self._key()).encrypt(nonce, password.encode(), app.id.encode())
            with self.db.session.begin() as s:
                s.execute(
                    self.db.insert()(CredentialRow)
                    .values(app_id=app.id, username=username, sealed=(nonce + ct).hex(), created_at=now)
                    .on_conflict_do_nothing(index_elements=[CredentialRow.app_id])
                )
            with self.db.session() as s:  # re-read: a concurrent writer may have won
                row = s.get(CredentialRow, app.id)
        return AppCredentialGrant(f"{app.id}-credentials", row.username, self._open(row)), generated

    def _open(self, row: CredentialRow) -> str:
        raw = bytes.fromhex(row.sealed)
        return AESGCM(self._key()).decrypt(raw[:12], raw[12:], row.app_id.encode()).decode()

    def reveal(self, app_id: str) -> dict | None:
        with self.db.session() as s:
            row = s.get(CredentialRow, app_id)
        if row is None:
            return None
        return {"username": row.username, "password": self._open(row)}

    def delete(self, app_id: str) -> bool:
        with self.db.session.begin() as s:
            return s.execute(delete(CredentialRow).where(CredentialRow.app_id == app_id)).rowcount > 0

    def stored_ids(self) -> set[str]:
        with self.db.session() as s:
            return set(s.scalars(select(CredentialRow.app_id)))
