# SPDX-License-Identifier: Apache-2.0
"""The manifest's `spec.backup` (contract §12.18) and `spec.database` (shared PostgreSQL) blocks.

    spec:
      backup:
        mode: hot                  # hot (default) | cold: the app is stopped while it is copied
        pre:  [{exec: {container: app, command: [sqlite3, /data/app.db, ".backup /data/app.db.bak"]}}]
        post: [{exec: {command: [rm, -f, /data/app.db.bak]}}]
        sqlite: [{claim: data, path: app.db}]     # SQLite files inside a volume: online copy
        exclude: [cache/, "*.tmp"]
        restore: {post: [{exec: {command: [...]}}]}
      database: {engine: postgres, secret: notes-db}   # a database, role and Secret at install

A hook is `{exec: {container?, command: [argv...]}, timeout_s?}`; one hook may be given without
the list. Commands run inside the app's container through the Kubernetes API, never on the host.
An app without `backup:` is copied hot ("crash-consistent only") and its badge says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..catalog import SECRET_NAME_RE, AppEntry

CONTAINER_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
CLAIM_RE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")


@dataclass(frozen=True)
class ExecHook:
    command: tuple[str, ...]
    container: str | None = None
    timeout_s: int = 300


@dataclass(frozen=True)
class BackupSpec:
    declared: bool = False
    mode: str = "hot"
    pre: tuple[ExecHook, ...] = ()
    post: tuple[ExecHook, ...] = ()
    restore_post: tuple[ExecHook, ...] = ()
    sqlite: tuple[tuple[str, str], ...] = ()  # (claim, path inside the volume)
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class DatabaseSpec:
    secret: str
    engine: str = "postgres"
    extra: dict = field(default_factory=dict)


def _hooks(value: object, where: str, errs: list[str]) -> tuple[ExecHook, ...]:
    if value is None:
        return ()
    items = value if isinstance(value, list) else [value]
    out = []
    for i, h in enumerate(items):
        ex = h.get("exec") if isinstance(h, dict) else None
        cmd = ex.get("command") if isinstance(ex, dict) else None
        if not isinstance(cmd, list) or not cmd or len(cmd) > 64 or not all(isinstance(c, str) and c for c in cmd):
            errs.append(f"{where}[{i}].exec.command must be a non-empty argv list of strings")
            continue
        container = ex.get("container")
        if container is not None and (not isinstance(container, str) or not CONTAINER_RE.match(container)):
            errs.append(f"{where}[{i}].exec.container must be a container name")
            continue
        t = h.get("timeout_s", 300)
        if not isinstance(t, int) or isinstance(t, bool) or not 1 <= t <= 3600:
            errs.append(f"{where}[{i}].timeout_s must be 1-3600")
            continue
        out.append(ExecHook(tuple(cmd), container, t))
    return tuple(out)


def parse_backup(spec: object) -> tuple[BackupSpec, list[str]]:
    errs: list[str] = []
    b = spec.get("backup") if isinstance(spec, dict) else None
    if b is None:
        return BackupSpec(), errs
    if not isinstance(b, dict):
        return BackupSpec(), ["spec.backup must be a mapping"]
    mode = b.get("mode", "hot")
    if mode not in ("hot", "cold"):
        errs.append("spec.backup.mode must be hot or cold")
    sqlite = []
    for i, s in enumerate(b.get("sqlite") or []):
        claim, path = (s.get("claim"), s.get("path")) if isinstance(s, dict) else (None, None)
        if not (isinstance(claim, str) and CLAIM_RE.match(claim) and isinstance(path, str) and path
                and not path.startswith("/") and ".." not in path.split("/")):
            errs.append(f"spec.backup.sqlite[{i}] must be {{claim, path}} with a relative path")
            continue
        sqlite.append((claim, path))
    exclude = b.get("exclude") or []
    if not isinstance(exclude, list) or not all(
        isinstance(e, str) and e and not e.startswith("/") and ".." not in e for e in exclude
    ):
        errs.append("spec.backup.exclude must be a list of relative patterns")
        exclude = []
    restore = b.get("restore") or {}
    out = BackupSpec(
        declared=True,
        mode=mode if mode in ("hot", "cold") else "hot",
        pre=_hooks(b.get("pre"), "spec.backup.pre", errs),
        post=_hooks(b.get("post"), "spec.backup.post", errs),
        restore_post=_hooks(restore.get("post") if isinstance(restore, dict) else None, "spec.backup.restore.post", errs),
        sqlite=tuple(sqlite),
        exclude=tuple(exclude),
    )
    return out, errs


def parse_database(spec: object) -> tuple[DatabaseSpec | None, list[str]]:
    d = spec.get("database") if isinstance(spec, dict) else None
    if d is None:
        return None, []
    if not isinstance(d, dict):
        return None, ["spec.database must be a mapping"]
    errs = []
    if d.get("engine", "postgres") != "postgres":
        errs.append("spec.database.engine must be postgres (the shared PostgreSQL on the hub)")
    secret = d.get("secret")
    if not isinstance(secret, str) or len(secret) > 253 or not SECRET_NAME_RE.match(secret):
        errs.append("spec.database.secret must be a Kubernetes Secret name")
    if errs:
        return None, errs
    return DatabaseSpec(secret=secret), []


def backup_spec(app: AppEntry) -> BackupSpec:
    spec, _ = parse_backup(app.manifest.get("spec"))
    return spec


def database_spec(app: AppEntry) -> DatabaseSpec | None:
    spec, _ = parse_database(app.manifest.get("spec"))
    return spec


def db_name(app_id: str) -> str:
    """Database and role name for an app: app_<id> with dashes as underscores (≤ 63 bytes)."""
    return "app_" + app_id.replace("-", "_")
