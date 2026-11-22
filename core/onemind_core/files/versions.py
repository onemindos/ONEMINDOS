# SPDX-License-Identifier: Apache-2.0
"""FILES previous versions (BAK-04, #241): read a file's older copies from the local btrfs snapshots and
restore one as a new file.

`onemindd snapshots-tick` (internal/backup/localsnapshot, run by onemind-snapshots.timer as root) takes
read-only snapshots of the whole Files root into ONEMIND_FILES_SNAPSHOTS_DIR, named `hourly-<UTC>` and
`daily-<UTC>`. That directory is mode 0750 root:onemind, so the gateway (user onemind) can read it and
never write it. A snapshot mirrors the Files root, so a file at (home:<person>, /Docs/a.txt) was at
`<snapshot>/home/<space dir>/Docs/a.txt`.

Rules:
- People only. Reading an older copy and restoring it is a person's own data-plane write inside a space
  they can already change (D-F1, the same rule as restoring from the trash). An app or agent is refused:
  AI never restores a version on its own.
- A restore never overwrites. The copy goes to the original path when that is free, otherwise beside it as
  `name (version <date> UTC).ext`, or to the `to_path` the person chose; an existing name is a 409.
- The copy is written in .system first and linked into place, so the folder never shows a half-written file.
- Snapshots live on the same disk as the files: they are not backups. The dashboard says so and links to
  Backups (restic, off the box).
"""

from __future__ import annotations

import os
import re
import stat as stat_mod
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Iterator

from ..auth import Principal
from ..ledger import iso
from . import paths
from .access import is_person
from .errors import FilesError, conflict, not_found
from .store import new_id

if TYPE_CHECKING:
    from .service import FilesService

SNAPSHOT_RE = re.compile(r"^(hourly|daily)-(\d{8}T\d{6}Z)$")
VERSION_PATTERN = r"^(?:hourly|daily)-\d{8}T\d{6}Z$"
COPY_CHUNK = 1024 * 1024
RESTORE_DIR = "restore"


class Versions:
    def __init__(self, svc: FilesService):
        self.svc = svc

    # ---- the snapshot directory ---------------------------------------------------------
    def snapshots(self) -> list[tuple[str, str, datetime]]:
        """(id, cadence, taken_at) of every managed snapshot, newest first; [] when versions are off."""
        try:
            fd = os.open(self.svc.settings.snapshots_dir, paths.O_DIR)
        except OSError:
            return []
        out = []
        try:
            for name in os.listdir(fd):
                m = SNAPSHOT_RE.match(name)
                if not m:
                    continue
                try:
                    if not stat_mod.S_ISDIR(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                        continue
                    taken = datetime.strptime(m.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                except (OSError, ValueError):
                    continue
                out.append((name, m.group(1), taken))
        finally:
            os.close(fd)
        out.sort(key=lambda v: v[2], reverse=True)
        return out

    def available(self) -> bool:
        return bool(self.snapshots())

    def _space_parts(self, root) -> tuple[str, ...]:
        return ("home", self.svc.space_dir_name(root.person_id)) if root.kind == "home" else ("shared",)

    @contextmanager
    def _snapshot_space(self, snapshot_id: str, root) -> Iterator[int]:
        """Descriptor of a space's folder inside one snapshot (read-only; never created)."""
        try:
            base = os.open(self.svc.settings.snapshots_dir, paths.O_DIR)
        except OSError:
            raise not_found("versions are not turned on for this box") from None
        try:
            with paths.dir_at(base, (snapshot_id, *self._space_parts(root))) as fd:
                yield fd
        finally:
            os.close(base)

    def _person(self, p: Principal, attempted: str) -> None:
        if not is_person(p):
            raise self.svc._deny(p, attempted, "only a person restores earlier versions", "people_only")

    # ---- list ---------------------------------------------------------------------------
    def list(self, p: Principal, root: str | None, path: str | None) -> dict:
        self._person(p, "files versions list")
        t = self.svc.target(p, root, path, "read")
        if not t.parts:
            raise conflict("a space is a folder, not a file", "not_a_file")
        current = None
        try:
            with self.svc._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
                current = paths.lstat_at(d, t.parts[-1])
        except FilesError as exc:
            if exc.status != 404:
                raise
        snaps = self.snapshots()
        seen = set() if current is None else {(current.st_size, current.st_mtime_ns)}
        versions = []
        for sid, cadence, taken in snaps:
            try:
                with self._snapshot_space(sid, t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
                    st = paths.lstat_at(d, t.parts[-1])
            except FilesError:
                continue  # the file did not exist yet, or a folder on its path was not there then
            # Only distinct copies: a file unchanged for a day appears once, and a copy equal to today's is left out.
            if not stat_mod.S_ISREG(st.st_mode) or (st.st_size, st.st_mtime_ns) in seen:
                continue
            seen.add((st.st_size, st.st_mtime_ns))
            versions.append({"version": sid, "cadence": cadence, "taken_at": iso(taken), "size": st.st_size,
                             "mtime": iso(datetime.fromtimestamp(st.st_mtime, tz=UTC))})
        return {"root": t.root.id, "path": t.path, "enabled": bool(snaps), "exists": current is not None,
                "versions": versions}

    # ---- restore ------------------------------------------------------------------------
    @staticmethod
    def default_name(name: str, taken: datetime) -> str:
        stem, ext = os.path.splitext(name)
        return f"{stem} (version {taken:%Y-%m-%d %H.%M} UTC){ext}"

    def restore(self, p: Principal, root: str | None, path: str | None, version: str, to_path: str | None = None) -> dict:
        self._person(p, "files versions restore")
        m = SNAPSHOT_RE.match(version or "")
        if not m:
            raise FilesError(422, "conflict", "unknown version", reason="invalid_version")
        src = self.svc.target(p, root, path, "read")
        if not src.parts:
            raise conflict("a space is a folder, not a file", "not_a_file")
        taken = datetime.strptime(m.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        if to_path is None:
            with self.svc._space(src.root) as space, paths.dir_at(space, src.parts[:-1]) as d:
                free = not paths.exists_at(d, src.parts[-1])
            name = src.parts[-1] if free else self.default_name(src.parts[-1], taken)
            paths.validate_name(name)
            to_path = paths.join(src.parts[:-1] + (name,))
        dst = self.svc.target(p, src.root.id, to_path, "entry")
        if not dst.parts:
            raise conflict("cannot restore over a space", "space_root")
        tmp = new_id("rst")
        with self._snapshot_space(version, src.root) as snap, paths.dir_at(snap, src.parts[:-1]) as sd:
            fd, st = paths.open_file_at(sd, src.parts[-1])
        try:
            with self.svc._lock, self.svc._system(RESTORE_DIR) as work, self.svc._space(dst.root) as space:
                with paths.dir_at(space, dst.parts[:-1]) as d:
                    if paths.exists_at(d, dst.parts[-1]):
                        raise conflict("something with that name is already there; restore it under another name", "exists")
                    self.svc.check_space(dst.root, st.st_size)
                    self._copy(fd, work, tmp)
                    try:
                        os.link(tmp, dst.parts[-1], src_dir_fd=work, dst_dir_fd=d, follow_symlinks=False)
                    except FileExistsError:
                        raise conflict("something with that name is already there; restore it under another name", "exists") from None
                    except OSError as exc:
                        raise paths.os_error(exc) from None
                    finally:
                        try:
                            os.unlink(tmp, dir_fd=work)
                        except FileNotFoundError:
                            pass
                    entry = self.svc._entry(dst.parts[-1], dst.parts[:-1], paths.lstat_at(d, dst.parts[-1]))
        finally:
            os.close(fd)
        self.svc.reindex(dst.root, dst.parts)
        self.svc.event("version.restored", p, {"root": dst.root.id, "path": src.path, "to_path": dst.path,
                                               "version": version, "size": st.st_size})
        return entry | {"root": dst.root.id, "restored_from": version}

    @staticmethod
    def _copy(src_fd: int, dir_fd: int, name: str) -> None:
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                      0o640, dir_fd=dir_fd)
        try:
            pos = 0
            while chunk := os.pread(src_fd, COPY_CHUNK, pos):
                view = memoryview(chunk)
                while view:
                    view = view[os.write(out, view):]
                pos += len(chunk)
            os.fsync(out)
        except BaseException:
            os.close(out)
            os.unlink(name, dir_fd=dir_fd)
            raise
        os.close(out)
