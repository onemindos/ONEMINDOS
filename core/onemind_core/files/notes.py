# SPDX-License-Identifier: Apache-2.0
"""A person's plain Markdown vault in Files. The Markdown is the source of truth."""

from __future__ import annotations

import fcntl
import hashlib
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ..auth import Principal
from . import paths
from .access import has_home
from .errors import FilesError, conflict, denied
from .service import FilesService, Target

VAULT = "Notes"
MAX_NOTE_BYTES = 1024 * 1024


def _note_parts(path: str) -> tuple[str, ...]:
    parts = paths.split_path(path)
    if not parts or any(part.startswith(".") for part in parts) or not parts[-1].lower().endswith(".md"):
        raise paths.PathRefused("notes must be visible Markdown files in the vault")
    return parts


def _revision(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise conflict("the note must contain UTF-8 Markdown", "invalid_markdown") from None


def _encode(markdown: str) -> bytes:
    try:
        data = markdown.encode("utf-8")
    except UnicodeEncodeError:
        raise conflict("the note must contain UTF-8 Markdown", "invalid_markdown") from None
    _check_size(len(data))
    return data


def _check_size(size: int) -> None:
    if size > MAX_NOTE_BYTES:
        raise FilesError(413, "payload_too_large", "the note is larger than 1 MiB", reason="note_too_large")


def _read_data(fd: int) -> bytes:
    with os.fdopen(os.dup(fd), "rb") as stream:
        data = stream.read(MAX_NOTE_BYTES + 1)
    _check_size(len(data))
    return data


def _current(dir_fd: int, name: str) -> tuple[bytes | None, tuple[int, ...] | None]:
    try:
        fd, st = paths.open_file_at(dir_fd, name)
    except FilesError as exc:
        if exc.status == 404:
            return None, None
        raise
    try:
        return _read_data(fd), _identity(st)
    finally:
        os.close(fd)


def _identity(st: os.stat_result) -> tuple[int, ...]:
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def _conflict_name(name: str, revision: str | None, data: bytes) -> str:
    digest = hashlib.sha256((revision or "").encode() + b"\0" + data).hexdigest()[:20]
    suffix = f" (conflict {digest}).md"
    stem = name[:-3].encode()[: paths.MAX_COMPONENT_BYTES - len(suffix)]
    return stem.decode(errors="ignore") + suffix


def _write_temp(dir_fd: int, data: bytes) -> str:
    name = f"notes-{secrets.token_hex(16)}.part"
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        os.unlink(name, dir_fd=dir_fd)
        raise
    return name


@dataclass(frozen=True)
class Note:
    path: str
    markdown: str
    revision: str


@dataclass(frozen=True)
class SaveResult:
    note: Note
    conflict: bool = False


WRITE_GUARANTEE = (
    "Gateway saves are serialised and never overwrite an edit the gateway has seen. An SMB or "
    "Syncthing write that lands between the final identity re-check and os.replace can still be "
    "overwritten; closing that gap needs a shared write contract across protocols."
)


class NotesVault:
    """A person's Notes vault. Routes must surface WRITE_GUARANTEE; it is the weaker guarantee."""

    write_guarantee = WRITE_GUARANTEE

    def __init__(self, files: FilesService):
        self.files = files

    def _target(self, person: Principal, parts: tuple[str, ...] = (), need: str = "read") -> Target:
        if not has_home(person):
            raise denied("Notes requires a person's own Home", "role")
        return self.files.target(person, f"home:{person.id}", paths.join((VAULT,) + parts), need)

    def _ensure_vault(self, person: Principal) -> None:
        t = self._target(person, need="entry")
        try:
            self.files.mkdir(person, t.root.id, t.path)
        except FilesError as exc:
            if exc.reason != "exists":
                raise

    @contextmanager
    def _work(self, target: Target) -> Iterator[int]:
        """Serialise Notes saves in different gateway processes as well as other local Files writes."""
        with self.files._lock, self.files._system("notes", self.files.space_dir_name(target.root.person_id)) as work:
            lock = os.open("write.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=work)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX)
                yield work
            finally:
                os.close(lock)

    def get(self, person: Principal, path: str) -> Note:
        parts = _note_parts(path)
        t = self._target(person, parts)
        with self.files.open_file(person, t.root.id, t.path, "notes.read") as (fd, _, _):
            data = _read_data(fd)
        return Note(paths.join(parts), _decode(data), _revision(data))

    def save(self, person: Principal, path: str, markdown: str, *, revision: str | None) -> SaveResult:
        """Save against an observed revision, or create when revision is None.

        A retry with the same content reuses the saved note or its conflict copy. Storage
        exposed to SMB can also change outside the gateway's lock. Recheck its identity
        immediately before replacement so changes visible by that point go to a copy.
        """
        parts = _note_parts(path)
        t = self._target(person, parts, "entry")
        data = _encode(markdown)
        self._ensure_vault(person)
        name = parts[-1]
        saved_revision = _revision(data)
        try:
            with self._work(t) as work, self.files._space(t.root) as space:
                with paths.dir_at(space, t.parts[:-1]) as folder:
                    previous, identity = _current(folder, name)
                    if previous == data:
                        return SaveResult(Note(paths.join(parts), markdown, saved_revision))
                    expected = _revision(previous) if previous is not None else None
                    if revision == expected and self._replace(work, folder, t, name, data, identity):
                        saved_name = name
                    else:
                        saved_name = _conflict_name(name, revision, data)
                        if not self._create_copy(work, folder, t, saved_name, data):
                            copy_parts = parts[:-1] + (saved_name,)
                            return SaveResult(Note(paths.join(copy_parts), markdown, saved_revision), True)
                    os.fsync(folder)
        except OSError as exc:
            raise paths.os_error(exc) from None
        saved_parts = t.parts[:-1] + (saved_name,)
        is_conflict = saved_name != name
        self._record(person, t, saved_parts, data, is_conflict)
        return SaveResult(Note(paths.join(saved_parts[1:]), markdown, saved_revision), is_conflict)

    def _replace(self, work: int, folder: int, target: Target, name: str, data: bytes,
                 identity: tuple[int, ...] | None) -> bool:
        self.files.check_space(target.root, len(data) - (identity[2] if identity else 0))
        staged = _write_temp(work, data)
        try:
            if identity is None:
                try:
                    os.link(staged, name, src_dir_fd=work, dst_dir_fd=folder, follow_symlinks=False)
                except FileExistsError:
                    return False
            else:
                try:
                    actual = os.stat(name, dir_fd=folder, follow_symlinks=False)
                except FileNotFoundError:
                    return False
                if _identity(actual) != identity:
                    return False
                os.replace(staged, name, src_dir_fd=work, dst_dir_fd=folder)
            return True
        finally:
            try:
                os.unlink(staged, dir_fd=work)
            except FileNotFoundError:
                pass

    def _create_copy(self, work: int, folder: int, target: Target, name: str, data: bytes) -> bool:
        previous, _ = _current(folder, name)
        if previous == data:
            return False
        if previous is not None or not self._replace(work, folder, target, name, data, None):
            raise conflict("a file already occupies the conflict copy path", "exists")
        return True

    def _record(self, person: Principal, target: Target, parts: tuple[str, ...], data: bytes,
                is_conflict: bool = False) -> None:
        revision = _revision(data)
        self.files.reindex(target.root, parts, depth=0, known_hash=revision)
        self.files.event("notes.conflict" if is_conflict else "notes.saved", person, {
            "root": target.root.id, "path": paths.join(parts), "size": len(data), "sha256": revision,
        })

    def _create(self, person: Principal, name: str, markdown: str) -> Note:
        t = self._target(person, (name,), "entry")
        self._ensure_vault(person)
        data = _encode(markdown)
        try:
            with self._work(t) as work, self.files._space(t.root) as space, paths.dir_at(space, (VAULT,)) as folder:
                created = not paths.exists_at(folder, name) and self._replace(work, folder, t, name, data, None)
                if created:
                    os.fsync(folder)
        except OSError as exc:
            raise paths.os_error(exc) from None
        if created:
            self._record(person, t, t.parts, data)
        return self.get(person, name)

    def daily(self, person: Principal, day: date) -> Note:
        stamp = day.isoformat()
        return self._create(person, f"{stamp}.md", f"# {stamp}\n")

    def capture(self, person: Principal, capture_id: UUID, markdown: str) -> Note:
        """Store a capture once. Use the same client ID when retrying the request."""
        note = self._create(person, f"Capture-{capture_id.hex}.md", markdown)
        if note.markdown != markdown:
            raise conflict("the capture already exists; use its current revision to edit it", "exists")
        return note
