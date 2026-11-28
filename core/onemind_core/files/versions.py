# SPDX-License-Identifier: Apache-2.0
"""Read the storage Snapper timeline and restore a file as a new entry (BAK-04, #241)."""

from __future__ import annotations

import hashlib
import os
import re
import stat as stat_mod
import xml.etree.ElementTree as ET
from contextlib import closing, contextmanager
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

NUMBER_PATTERN = r"[1-9][0-9]{0,9}"
VERSION_PATTERN = rf"^snapper-({NUMBER_PATTERN})-([0-9]{{8}}T[0-9]{{6}}Z)$"
VERSION_RE = re.compile(VERSION_PATTERN)
ID_TIME = "%Y%m%dT%H%M%SZ"
COPY_CHUNK = 1024 * 1024
COMPARE_LIMIT = COPY_CHUNK  # keep larger copies visible without reading gigabytes to list history
RESTORE_DIR = "restore"
RESTORE_STAGE_RE = re.compile(r"rst_[0-9A-HJKMNP-TV-Z]{26}")


class Versions:
    def __init__(self, svc: FilesService):
        self.svc = svc

    @contextmanager
    def _history(self) -> Iterator[int]:
        history = self.svc.settings.snapshots_dir
        if history is None:
            raise not_found("local versions are unavailable on this box")
        try:
            fd = os.open(history, paths.O_DIR)
        except OSError:
            raise not_found("local versions are unavailable on this box") from None
        try:
            yield fd
        finally:
            os.close(fd)

    @staticmethod
    def _timeline_info(entry: int, number: str) -> tuple[datetime, int] | None:
        try:
            fd, st = paths.open_file_at(entry, "info.xml")
            with os.fdopen(fd, "rb") as info:
                xml = ET.fromstring(info.read(65536))
            if (xml.tag == "snapshot" and xml.findtext("num") == number
                    and xml.findtext("type") == "single" and xml.findtext("cleanup") == "timeline"):
                taken = datetime.strptime(xml.findtext("date", ""), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                return taken, st.st_ino
        except (FilesError, OSError, ET.ParseError, ValueError):
            pass
        return None

    @staticmethod
    def _capture_parts(number: str, inode: int) -> tuple[str, str]:
        return (".files", f"{number}-{inode}")

    def _snapshots(self, base: int) -> Iterator[tuple[str, datetime]]:
        with os.scandir(base) as entries:
            for entry in entries:
                if not re.fullmatch(NUMBER_PATTERN, entry.name):
                    continue
                try:
                    with paths.dir_at(base, (entry.name,)) as info:
                        timeline = self._timeline_info(info, entry.name)
                        if timeline is not None:
                            taken, inode = timeline
                            with paths.dir_at(base, self._capture_parts(entry.name, inode)):
                                yield entry.name, taken
                except FilesError:
                    continue  # cleanup, or a storage snapshot taken without the Files plugin

    def available(self) -> bool:
        try:
            with self._history() as base, closing(self._snapshots(base)) as snapshots:
                return next(snapshots, None) is not None
        except (FilesError, OSError):
            return False

    def _space_parts(self, root) -> tuple[str, ...]:
        return ("home", self.svc.space_dir_name(root.person_id)) if root.kind == "home" else ("shared",)

    @contextmanager
    def _snapshot_space(self, base: int, number: str, taken: datetime, root) -> Iterator[int]:
        with paths.dir_at(base, (number,)) as info:
            timeline = self._timeline_info(info, number)
            if timeline is None or timeline[0] != taken:
                raise not_found("that version is no longer available")
            with paths.dir_at(base, (*self._capture_parts(number, timeline[1]), *self._space_parts(root))) as fd:
                yield fd

    @staticmethod
    def _fingerprint(directory: int, name: str, st: os.stat_result) -> bytes | None:
        if not stat_mod.S_ISREG(st.st_mode) or st.st_size > COMPARE_LIMIT:
            return None
        try:
            fd, before = paths.open_file_at(directory, name)
            try:
                data = os.pread(fd, before.st_size, 0) if before.st_size <= COMPARE_LIMIT else b""
                after = os.fstat(fd)
            finally:
                os.close(fd)
        except (FilesError, OSError):
            return None
        if (len(data) == before.st_size and before.st_ino == st.st_ino
                and before.st_ctime_ns == st.st_ctime_ns == after.st_ctime_ns):
            return hashlib.sha256(data).digest()
        return None

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
        seen = set()
        try:
            with self.svc._space(t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
                current = paths.lstat_at(d, t.parts[-1])
                fingerprint = self._fingerprint(d, t.parts[-1], current)
                if fingerprint is not None:
                    seen.add(fingerprint)
        except FilesError as exc:
            if exc.status != 404:
                raise
        versions = []
        snaps = []
        try:
            with self._history() as base:
                snaps = sorted(self._snapshots(base), key=lambda v: (v[1], int(v[0])), reverse=True)
                for number, taken in snaps:
                    try:
                        with self._snapshot_space(base, number, taken, t.root) as space, paths.dir_at(space, t.parts[:-1]) as d:
                            st = paths.lstat_at(d, t.parts[-1])
                            fingerprint = self._fingerprint(d, t.parts[-1], st)
                    except FilesError:
                        continue
                    if not stat_mod.S_ISREG(st.st_mode) or fingerprint in seen:
                        continue
                    if fingerprint is not None:
                        seen.add(fingerprint)
                    versions.append({"version": f"snapper-{number}-{taken:{ID_TIME}}", "cadence": "timeline",
                                     "taken_at": iso(taken), "size": st.st_size,
                                     "mtime": iso(datetime.fromtimestamp(st.st_mtime, tz=UTC))})
        except (FilesError, OSError):
            pass  # no Snapper history on this box
        return {"root": t.root.id, "path": t.path, "enabled": bool(snaps), "exists": current is not None,
                "versions": versions}

    # ---- restore ------------------------------------------------------------------------
    def recover_stages(self) -> None:
        # Startup runs before the single gateway process begins serving. A stage linked
        # into a space before interruption keeps its live name when this link is removed.
        try:
            with self.svc._system(RESTORE_DIR) as work, os.scandir(work) as entries:
                for entry in entries:
                    if RESTORE_STAGE_RE.fullmatch(entry.name) and entry.is_file(follow_symlinks=False):
                        os.unlink(entry.name, dir_fd=work)
        except OSError as exc:
            raise paths.os_error(exc) from None

    @staticmethod
    def default_name(name: str, taken: datetime) -> str:
        stem, ext = os.path.splitext(name)
        suffix = f" (version {taken:%Y-%m-%d %H.%M} UTC)"
        raw = name.encode()
        if len(raw) + len(suffix) <= paths.MAX_COMPONENT_BYTES:
            return f"{stem}{suffix}{ext}"
        # Keep distinct long names from collapsing to the same truncated prefix.
        suffix = f" [{hashlib.sha256(raw).hexdigest()[:8]}]{suffix}"
        budget = paths.MAX_COMPONENT_BYTES - len(suffix)
        if len(ext.encode()) >= budget:
            stem, ext = name, ""
        # The original is valid UTF-8. Only a trailing, sliced code point can be incomplete.
        shortened = stem.encode()[:budget - len(ext.encode())].decode("utf-8", errors="ignore")
        return f"{shortened}{suffix}{ext}"

    def restore(self, p: Principal, root: str | None, path: str | None, version: str, to_path: str | None = None) -> dict:
        self._person(p, "files versions restore")
        match = VERSION_RE.fullmatch(version or "")
        try:
            if match is None:
                raise ValueError
            number, stamp = match.groups()
            taken = datetime.strptime(stamp, ID_TIME).replace(tzinfo=UTC)
            if taken.strftime(ID_TIME) != stamp:
                raise ValueError
        except ValueError:
            raise FilesError(422, "conflict", "invalid version", reason="invalid_version") from None
        src = self.svc.target(p, root, path, "read")
        if not src.parts:
            raise conflict("a space is a folder, not a file", "not_a_file")
        if to_path is None:
            try:
                with self.svc._space(src.root) as space, paths.dir_at(space, src.parts[:-1]) as d:
                    free = not paths.exists_at(d, src.parts[-1])
            except FilesError as exc:
                if exc.status != 404:
                    raise
                raise not_found("the original folder is gone; choose a destination path in an existing folder") from None
            name = src.parts[-1] if free else self.default_name(src.parts[-1], taken)
            paths.validate_name(name)
            to_path = paths.join(src.parts[:-1] + (name,))
        dst = self.svc.target(p, src.root.id, to_path, "entry")
        if not dst.parts:
            raise conflict("cannot restore over a space", "space_root")
        tmp = new_id("rst")
        with self._history() as base, self._snapshot_space(base, number, taken, src.root) as snap:
            with paths.dir_at(snap, src.parts[:-1]) as sd:
                fd, st = paths.open_file_at(sd, src.parts[-1])
        try:
            with self.svc._system(RESTORE_DIR) as work:
                try:
                    with self.svc._reserve_restore_space(dst.root, st.st_size):
                        self._copy(fd, work, tmp)
                except OSError as exc:
                    raise paths.os_error(exc) from None
                try:
                    with self.svc._lock, self.svc._space(dst.root) as space, paths.dir_at(space, dst.parts[:-1]) as d:
                        if paths.exists_at(d, dst.parts[-1]):
                            raise conflict("something with that name is already there; restore it under another name", "exists")
                        self.svc.check_space(dst.root, st.st_size, staged=True)
                        try:
                            os.link(tmp, dst.parts[-1], src_dir_fd=work, dst_dir_fd=d, follow_symlinks=False)
                        except FileExistsError:
                            raise conflict("something with that name is already there; restore it under another name", "exists") from None
                        except OSError as exc:
                            raise paths.os_error(exc) from None
                        entry = self.svc._entry(dst.parts[-1], dst.parts[:-1], paths.lstat_at(d, dst.parts[-1]))
                finally:
                    os.unlink(tmp, dir_fd=work)
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
