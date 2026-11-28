# SPDX-License-Identifier: Apache-2.0
"""Backup units of the native built-ins (#616): the set, a portable export, and the replay on a fresh box.

Each built-in's descriptor (`spec.backup.units`, builtins.py) names its gateway tables and the folders its
settings point at (`ONEMIND_<SECTION>_<FIELD>`). The backup set is every switched-on built-in's units plus
the gateway database itself, which the agent copies whole in its `system` unit (an online SQLite copy, or
the PostgreSQL dump hook).

> **In plain words.** The whole database copy is right for putting the same box back. On a *new* box the
> gateway may already have started and written its own first rows, so dropping an old database file over it
> is not safe. The export below writes each built-in's rows as plain JSON lines, with a checksum per table,
> plus a copy of its folders; the restore checks everything first and then writes the rows back in one
> database transaction, so it either brings all of them back or none.

Restore rules (it is the owner's own data coming back, so it is strict rather than clever):
- every table and folder in the export must be declared by a built-in this gateway knows;
- every table file must match the checksum in the manifest;
- each feature's schema version must equal this box's (restore on the same OneMind version, then update);
- a table that already holds rows is refused unless `replace` is asked for; a folder with files is refused;
- folders are copied in first (to a temporary sibling, then renamed into place) and removed again if the
  database transaction fails.

CLI on the box, with the gateway's environment, as the gateway's user, gateway stopped for a restore:
    python -m onemind_core.backups.units list
    python -m onemind_core.backups.units export DIR [--no-dirs]      # or: export --tar - (for the agent hook)
    python -m onemind_core.backups.units restore DIR|FILE.tar [--replace]
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tarfile
import tempfile
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import IO
from uuid import UUID

from sqlalchemy import Date, DateTime, LargeBinary, Numeric, Time, Uuid, func, inspect, select
from sqlalchemy.types import Float

from ..ledger import Base
from ..sections import _SECTIONS, env_name
from ..store import SchemaVersionRow, registered_schemas

FORMAT = "onemind.builtin-units/v1"
GATEWAY_UNIT = "gateway"
TABLE_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
BATCH = 500


class RestoreRefused(Exception):
    """The export cannot be replayed here; nothing was written. `problems` says why, one line each."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# ---- the set -----------------------------------------------------------------------------------------------

def setting_path(settings, name: str) -> tuple[bool, Path | None]:
    """(is a known setting, its folder or None when unset) for an ONEMIND_<SECTION>_<FIELD> name."""
    for section, cls in _SECTIONS.items():
        for f in dataclasses.fields(cls):
            if env_name(section, f.name) == name:
                value = getattr(settings.section(cls), f.name)
                return True, Path(value) if value else None
    return False, None


def dir_fingerprint(path: str) -> str:
    """A run records which folder each carried setting pointed at by this, so no host path is stored."""
    return hashlib.sha256(os.path.normpath(path).encode()).hexdigest()[:16]


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    p = Path(os.path.normpath(path))
    return any(p == r or r in p.parents for r in (Path(os.path.normpath(x)) for x in roots))


def unit_set(gw, registry, *, export: bool = False, agent_dirs: frozenset[str] = frozenset(),
             agent_paths: tuple[Path, ...] = (), include_off_photos: bool = False) -> list[dict]:
    """The gateway database, then one `builtin:<id>` unit per switched-on built-in.

    `export`: the gateway writes the built-ins' table export into a folder the agent's `system` unit
    copies (BackupsSettings.export_dir); `agent_dirs`: the folder settings that unit also copies;
    `agent_paths`: when set, the folders it really copies (a setting pointing elsewhere is not carried).
    Include switched-off Photos in a recovery export so switching it off cannot strand existing data."""
    have = set(inspect(gw.db.engine).get_table_names())
    out = [{"unit": GATEWAY_UNIT, "kind": "database", "engine": gw.db.engine.dialect.name, "snapshot_unit": "system"}]
    descriptors = registry.enabled() if registry is not None else []
    if include_off_photos and registry is not None and "photos" in registry.descriptors:
        photos = registry.descriptors["photos"]
        if photos not in descriptors:
            descriptors.append(photos)
    for d in descriptors:
        tables, dirs, problems = [], [], []
        for u in d.spec["backup"]["units"]:
            if u["kind"] == "table":
                tables.append(u["name"])
                if u["name"] not in have:
                    problems.append(f"table {u['name']} is not in the gateway database")
            else:
                known, path = setting_path(gw.settings, u["name"])
                if not known:
                    problems.append(f"{u['name']} is not a gateway setting")
                carried = (u["name"] in agent_dirs and path is not None
                           and (not agent_paths or _inside(path, agent_paths)))
                dirs.append({"name": u["name"], "path": str(path) if path else None, "carried": carried})
        # snapshot_unit None: no agent unit carries this built-in's export (no export folder is set), so its
        # rows live only in the whole-database copy. The status must not read as "backed up".
        out.append({"unit": f"builtin:{d.id}", "kind": "builtin", "app_id": d.id, "tables": tables, "dirs": dirs,
                    "problems": problems, "snapshot_unit": "system" if export else None})
    return out


def public_view(units: list[dict], snapshotted: set[str] = frozenset(),
                builtin_snapshotted: set[str] = frozenset(), snapshot_dirs: dict | None = None) -> list[dict]:
    """The set as GET /v1/backups/status shows it: whether each folder is set, never its host path.

    `in_snapshot` is true only for a unit whose `snapshot_unit` is in `snapshotted` (the agent units with
    a successful snapshot; `builtin_snapshotted` for built-ins: a successful snapshot that holds their
    export) and, for a built-in, whose every set folder that snapshot carried, at the folder it points at
    now. `snapshot_dirs` is what the run recorded ({setting: dir_fingerprint}), not today's settings: a
    folder added to the backup or moved after the snapshot is not in it."""
    snapshot_dirs = snapshot_dirs or {}
    out = []
    for u in units:
        if "dirs" not in u:
            v = dict(u)
            v["in_snapshot"] = u.get("snapshot_unit") is not None and u["snapshot_unit"] in snapshotted
        else:
            v = {**u, "dirs": [{"name": x["name"], "configured": x["path"] is not None, "carried": x["carried"]}
                               for x in u["dirs"]]}
            v["in_snapshot"] = (u.get("snapshot_unit") is not None and u["snapshot_unit"] in builtin_snapshotted
                                and all(snapshot_dirs.get(x["name"]) == dir_fingerprint(x["path"])
                        for x in u["dirs"] if x["path"] is not None))
        out.append(v)
    return out


def feature_of(table: str) -> str:
    """The feature schema a table belongs to: the longest `<feature>_` prefix, else core (store.py §1)."""
    hits = [s.feature for s in registered_schemas() if table.startswith(s.feature + "_")]
    return max(hits, key=len, default="core")


def schema_versions(engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {r.feature: r.version for r in conn.execute(select(SchemaVersionRow.feature, SchemaVersionRow.version))}


# ---- values ------------------------------------------------------------------------------------------------

def _encode(v):
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (bytes, memoryview)):
        return base64.b64encode(bytes(v)).decode()
    if isinstance(v, (Decimal, UUID)):
        return str(v)
    return v


def _decoder(col):
    t = col.type
    if isinstance(t, DateTime):
        return datetime.fromisoformat
    if isinstance(t, Date):
        return date.fromisoformat
    if isinstance(t, Time):
        return time.fromisoformat
    if isinstance(t, LargeBinary):
        return base64.b64decode
    if isinstance(t, Uuid):
        return UUID
    if isinstance(t, Numeric) and not isinstance(t, Float):
        return Decimal
    return None


# ---- folders -----------------------------------------------------------------------------------------------

def copy_tree(src: Path, dst: Path) -> tuple[int, int]:
    """Copy regular files and folders, keeping hard links as links (Photos stores each blob once).

    Symlinks, sockets and devices are left out: a restored link could point anywhere."""
    seen: dict[tuple[int, int], Path] = {}
    files = size = 0
    dst.mkdir(mode=0o700, parents=True, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        here = Path(dirpath)
        rel = here.relative_to(src)
        for dn in list(dirnames):
            if (here / dn).is_symlink():
                dirnames.remove(dn)
                continue
            (dst / rel / dn).mkdir(mode=0o700, exist_ok=True)
            shutil.copystat(here / dn, dst / rel / dn, follow_symlinks=False)
        for fn in filenames:
            st = (here / fn).lstat()
            if not stat.S_ISREG(st.st_mode):
                continue
            key = (st.st_dev, st.st_ino)
            if st.st_nlink > 1 and key in seen:
                os.link(seen[key], dst / rel / fn)
                continue
            shutil.copy2(here / fn, dst / rel / fn, follow_symlinks=False)
            seen[key] = dst / rel / fn
            files, size = files + 1, size + st.st_size
    return files, size


def holds_files(path: Path) -> bool:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        return True
    return path.exists() and any(not p.is_dir() or p.is_symlink() for p in path.rglob("*"))


# ---- export ------------------------------------------------------------------------------------------------

def _write(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def export(gw, registry, dest: Path, *, include_dirs: bool = True) -> dict:
    """Export switched-on built-ins and Photos data into `dest` (missing or empty); return the manifest."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    (dest / "tables").mkdir(mode=0o700)
    engine = gw.db.engine
    units = [u for u in unit_set(gw, registry, include_off_photos=True) if u["kind"] == "builtin"]
    if bad := [f"{u['unit']}: {p}" for u in units for p in u["problems"]]:
        raise ValueError("cannot export: " + "; ".join(bad))
    manifest = {"format": FORMAT, "engine": engine.dialect.name, "schema_versions": schema_versions(engine),
                "units": []}
    with engine.connect() as conn:
        for u in units:
            entry = {"unit": u["unit"], "app_id": u["app_id"], "tables": [], "dirs": []}
            for name in u["tables"]:
                t = Base.metadata.tables[name]
                buf = io.BytesIO()
                n = 0
                for r in conn.execute(select(t).order_by(*t.primary_key.columns)):
                    row = {k: _encode(v) for k, v in r._mapping.items()}
                    buf.write(json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n")
                    n += 1
                data = buf.getvalue()
                _write(dest / "tables" / f"{name}.jsonl", data)
                entry["tables"].append({"name": name, "rows": n, "sha256": hashlib.sha256(data).hexdigest()})
            for d in u["dirs"]:
                path = Path(d["path"]) if d["path"] else None
                if not include_dirs:
                    entry["dirs"].append({"name": d["name"], "state": "skipped"})
                elif path is None or not path.is_dir():
                    entry["dirs"].append({"name": d["name"], "state": "not_configured" if path is None else "absent"})
                else:
                    files, size = copy_tree(path, dest / "dirs" / u["app_id"] / d["name"])
                    entry["dirs"].append({"name": d["name"], "state": "copied", "files": files, "bytes": size})
            manifest["units"].append(entry)
    _write(dest / "manifest.json", json.dumps(manifest, indent=1, sort_keys=True).encode())
    return manifest


EXPORT_FILE = "builtin-units.tar"


def write_export(gw, registry, folder: Path) -> dict:
    """The tables-only export as `folder`/builtin-units.tar, replaced atomically (the agent copies the
    folders itself). Called by the gateway before each box run."""
    folder = Path(folder)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = folder / f".{EXPORT_FILE}.{secrets.token_hex(4)}"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            manifest = export_tar(gw, registry, f, include_dirs=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, folder / EXPORT_FILE)
    finally:
        tmp.unlink(missing_ok=True)
    return manifest


def export_tar(gw, registry, out: IO[bytes], *, include_dirs: bool = False) -> dict:
    """The export as one tar stream (the agent's command hook keeps a command's output as one file)."""
    with tempfile.TemporaryDirectory(prefix="onemind-units-") as tmp:
        manifest = export(gw, registry, Path(tmp) / "export", include_dirs=include_dirs)
        with tarfile.open(fileobj=out, mode="w|") as tar:
            tar.add(Path(tmp) / "export", arcname=".")
    return manifest


# ---- restore -----------------------------------------------------------------------------------------------

def _check(gw, registry, src: Path, replace: bool) -> tuple[dict, list[tuple], list[tuple]]:
    try:
        m = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RestoreRefused(["manifest.json is missing or not JSON"]) from None
    if not isinstance(m, dict) or m.get("format") != FORMAT or not isinstance(m.get("units"), list):
        raise RestoreRefused([f"manifest.json is not a {FORMAT} export"])
    declared = {(d.id, u["kind"], u["name"]) for d in (registry.descriptors if registry else {}).values()
                for u in d.spec["backup"]["units"]}
    engine = gw.db.engine
    have, mine = set(inspect(engine).get_table_names()), schema_versions(engine)
    theirs = m.get("schema_versions") or {}
    problems: list[str] = []
    tables: list[tuple] = []  # (table, file)
    dirs: list[tuple] = []    # (app id, name, source folder, target folder)
    for u in m["units"]:
        app = u.get("app_id")
        for t in u.get("tables") or []:
            name = t.get("name") or ""
            if not TABLE_RE.match(name) or (app, "table", name) not in declared:
                problems.append(f"{app} does not declare table {name}")
                continue
            if name not in have or name not in Base.metadata.tables:
                problems.append(f"table {name} is not in this gateway's database")
                continue
            f = src / "tables" / f"{name}.jsonl"
            if not f.is_file() or f.is_symlink() or hashlib.sha256(f.read_bytes()).hexdigest() != t.get("sha256"):
                problems.append(f"tables/{name}.jsonl does not match its checksum")
                continue
            feat = feature_of(name)
            if theirs.get(feat) != mine.get(feat):
                problems.append(f"{feat} schema is v{theirs.get(feat)} in the export and v{mine.get(feat)} here;"
                                " restore on the same OneMind version, then update")
                continue
            tables.append((Base.metadata.tables[name], f))
        for d in u.get("dirs") or []:
            if d.get("state") != "copied":
                continue
            name = d.get("name") or ""
            if (app, "dir", name) not in declared:
                problems.append(f"{app} does not declare folder {name}")
                continue
            _, target = setting_path(gw.settings, name)
            source = src / "dirs" / str(app) / name
            if target is None:
                problems.append(f"{name} is not set on this box; set it, then restore")
            elif not source.is_dir() or source.is_symlink():
                problems.append(f"dirs/{app}/{name} is missing from the export")
            elif holds_files(target):
                problems.append(f"{name} ({target}) is not empty; empty it or point {name} at an empty folder")
            else:
                dirs.append((app, name, source, target))
    with engine.connect() as conn:
        for t, _ in tables:
            if not replace and conn.execute(select(func.count()).select_from(t)).scalar():
                problems.append(f"{t.name} already holds rows; restore onto a fresh box, or ask for replace")
    if problems:
        raise RestoreRefused(problems)
    return m, tables, dirs


def _place(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.restore-{secrets.token_hex(4)}"
    try:
        copy_tree(source, tmp)
        if target.exists():
            for p in sorted(target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                p.rmdir()  # only empty folders are here (checked); a file appearing now stops the restore
            target.rmdir()
        tmp.rename(target)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)


def restore(gw, registry, src: Path, *, replace: bool = False) -> dict:
    """Replay an export (a folder, or the tar `export_tar` wrote) on this box. Raises RestoreRefused."""
    src = Path(src)
    if src.is_file():
        with tempfile.TemporaryDirectory(prefix="onemind-units-") as tmp, tarfile.open(src, mode="r:") as tar:
            tar.extractall(tmp, filter="data")
            return restore(gw, registry, Path(tmp), replace=replace)
    _, tables, dirs = _check(gw, registry, src, replace)
    placed: list[Path] = []
    order = [t for t in Base.metadata.sorted_tables if any(t is x for x, _ in tables)]
    files = {t.name: f for t, f in tables}
    count = 0
    try:
        for _, _, source, target in dirs:
            _place(source, target)
            placed.append(target)
        with gw.db.engine.begin() as conn:
            if replace:
                for t in reversed(order):
                    conn.execute(t.delete())
            for t in order:
                cols = {c.name: _decoder(c) for c in t.columns}
                batch: list[dict] = []
                for line in files[t.name].read_bytes().splitlines():
                    row = json.loads(line)
                    if unknown := set(row) - set(cols):
                        raise RestoreRefused([f"{t.name} rows have columns this gateway lacks: {sorted(unknown)}"])
                    batch.append({k: (cols[k](v) if cols[k] and v is not None else v) for k, v in row.items()})
                    if len(batch) >= BATCH:
                        conn.execute(t.insert(), batch)
                        count, batch = count + len(batch), []
                if batch:
                    conn.execute(t.insert(), batch)
                    count += len(batch)
    except BaseException:
        for p in placed:
            shutil.rmtree(p, ignore_errors=True)
        raise
    return {"rows": count, "tables": [t.name for t in order], "dirs": [f"{a}:{n}" for a, n, _, _ in dirs]}


# ---- CLI ---------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m onemind_core.backups.units", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the backup set of this box")
    e = sub.add_parser("export", help="write the built-ins' units to an empty folder")
    e.add_argument("dest", nargs="?")
    e.add_argument("--tar", metavar="FILE", help="write one tar instead ('-' for stdout)")
    e.add_argument("--no-dirs", action="store_true", help="tables only (the agent copies the folders itself)")
    r = sub.add_parser("restore", help="replay an export on this box")
    r.add_argument("src")
    r.add_argument("--replace", action="store_true", help="clear the exported tables first")
    a = p.parse_args(argv)

    from ..app import create_app  # every feature module registers its tables on import
    app = create_app()
    gw, registry = app.state.gateway, getattr(app.state, "builtins", None)
    if a.cmd == "list":
        print(json.dumps(unit_set(gw, registry), indent=1))
        return 0
    if a.cmd == "export":
        if a.tar:
            if a.tar == "-":
                export_tar(gw, registry, sys.stdout.buffer, include_dirs=not a.no_dirs)
            else:
                with open(a.tar, "xb") as f:
                    export_tar(gw, registry, f, include_dirs=not a.no_dirs)
            return 0
        if not a.dest:
            p.error("export needs DIR or --tar")
        print(json.dumps(export(gw, registry, Path(a.dest), include_dirs=not a.no_dirs), indent=1))
        return 0
    try:
        print(json.dumps(restore(gw, registry, Path(a.src), replace=a.replace), indent=1))
    except RestoreRefused as exc:
        print("restore refused, nothing was written:", *exc.problems, sep="\n  ", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
