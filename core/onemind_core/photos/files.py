# SPDX-License-Identifier: Apache-2.0
"""The Photos folder tree and the durable steps on it (docs/leap/core/PHOTOS.md §4).

    <dir>/staging/<upload id>                                       bytes of an unfinished upload
    <dir>/library/.shared-store/<aa>/<sha256>                       each set of bytes, stored once
    <dir>/library/<person>/<phone folder>/<YYYY>/<MM>/<file name>   a hard link to the stored bytes

Originals are plain files with their own names, so the photos survive without OneMind. A person's
file is a hard link to the shared copy, so two people (or two phones) holding the same photo cost
the disk once. Every step that a receipt depends on is fsynced: the bytes, then each directory
entry, before the database records the receipt.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import secrets
import shutil
import stat
import unicodedata
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from ..files.errors import FilesError
from ..files.paths import lstat_at, open_dir, os_error, split_path, validate_name

STORE = ".shared-store"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_NO_LINK = {errno.EXDEV, errno.EPERM, errno.EMLINK, errno.ENOTSUP, errno.EOPNOTSUPP}
_MAX_NAME_BYTES = 180
READ_CHUNK = 1024 * 1024


def fsync_dir(path: Path) -> None:
    """Make the directory's entries (a new name, a removed name) durable."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(READ_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def slug(text: str, limit: int = 32) -> str:
    """Lower-case ASCII words joined by '-', for folder names. Empty when nothing is left."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:limit].strip("-")


def person_folder(owner: str) -> str:
    """The library folder of a principal id: the id itself when it is a safe name, else a hash.

    Never lossy for safe ids, so two people can never share a folder by their names folding
    together ("Ana" and "ana" are hashed apart).
    """
    if _SEGMENT_RE.match(owner) and owner not in (".", ".."):
        return owner
    return "p-" + hashlib.sha256(owner.encode()).hexdigest()[:16]


def source_folder(name: str, source_id: str) -> str:
    return f"{slug(name) or 'phone'}-{source_id[-6:].lower()}"


def safe_file_name(raw: str) -> str:
    """The phone's file name made safe for one path segment: no separators, no control characters,
    no leading dots, NFC (the same bytes on macOS and Linux), at most 180 bytes with its extension kept."""
    name = unicodedata.normalize("NFC", raw).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if unicodedata.category(c)[0] != "C").strip().lstrip(".").strip()
    if not name:
        return "photo"
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem or len(ext.encode()) > 16:
        stem, ext = name, ""
    ext_part = f".{ext}" if ext else ""
    budget = _MAX_NAME_BYTES - len(ext_part.encode())
    while len(stem.encode()) > budget:
        stem = stem[:-1]
    return (stem.rstrip() or "photo") + ext_part


def _candidates(name: str):
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        stem, ext = name, ""
    ext_part = f".{ext}" if ext else ""
    yield name
    for n in range(2, 1000):
        yield f"{stem} ({n}){ext_part}"
    yield f"{secrets.token_hex(4)} {name}"


class LibraryEscape(Exception):
    """A step on the library tree was refused by the FILES confinement (a symlink on the way, an
    invalid name). Nothing was written outside the library."""


@contextmanager
def _guard():
    """Run FILES path helpers, turning their API errors into FileNotFoundError / LibraryEscape."""
    try:
        yield
    except FilesError as exc:
        if exc.status == 404:
            raise FileNotFoundError(exc.message) from None
        raise LibraryEscape(exc.message) from None


def _check_hash(h: str) -> str:
    if not _HEX64.match(h):
        raise LibraryEscape("not a SHA-256 hex digest")
    return h


class PhotoFiles:
    """Every step under the library goes through the FILES confinement (core/onemind_core/files/paths.py):
    names are validated as single path components and every folder is walked from a descriptor of the
    photos folder with openat(O_NOFOLLOW), so a symlink planted in the library (or swapped in during a
    request) is refused instead of followed, and hard links are made with linkat relative to those
    descriptors. Client text (the phone's file name) never reaches a host path unvalidated."""

    def __init__(self, root: Path):
        self.root = root
        self.staging_dir = root / "staging"
        self.library_dir = root / "library"
        self.store_dir = self.library_dir / STORE

    # ---- confined directory access --------------------------------------------------------------
    def _root_fd(self) -> int:
        self.root.mkdir(mode=0o750, parents=True, exist_ok=True)
        return os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0))  # configured path

    @contextmanager
    def _dir(self, parts: tuple[str, ...], create: bool = False):
        base = self._root_fd()
        fd = os.dup(base)
        try:
            with _guard():
                for name in parts:
                    validate_name(name)
                    if create:
                        try:
                            os.mkdir(name, 0o750, dir_fd=fd)
                        except FileExistsError:
                            pass
                        except OSError as exc:
                            raise os_error(exc) from None
                    nfd = open_dir(fd, (name,))
                    os.close(fd)
                    fd = nfd
            yield fd
        finally:
            os.close(fd)
            os.close(base)

    # ---- staging -------------------------------------------------------------------------------
    def staging(self, upload_id: str) -> Path:
        return self.staging_dir / upload_id

    def create_staging(self, upload_id: str) -> None:
        with self._dir(("staging",), create=True) as fd:
            with _guard():
                validate_name(upload_id)
            nfd = os.open(upload_id, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=fd)
            try:
                os.fsync(nfd)
            finally:
                os.close(nfd)
            os.fsync(fd)

    def staged_size(self, upload_id: str) -> int | None:
        try:
            with self._dir(("staging",)) as fd:
                return lstat_at(fd, upload_id).st_size
        except (FileNotFoundError, LibraryEscape, FilesError):
            return None

    def discard(self, path: Path) -> None:
        """Remove a staged file (a path from staging())."""
        try:
            with self._dir(("staging",)) as fd:
                os.unlink(path.name, dir_fd=fd)
        except (FileNotFoundError, LibraryEscape):
            pass

    def discard_library(self, library_path: str) -> None:
        try:
            *folder, name = split_path(library_path)
            with self._dir(tuple(folder)) as fd:
                os.unlink(name, dir_fd=fd)
        except (FileNotFoundError, LibraryEscape, FilesError, ValueError):
            pass

    # ---- the shared store ---------------------------------------------------------------------
    def store_path(self, h: str) -> Path:
        return self.store_dir / h[:2] / _check_hash(h)

    def _regular_size(self, parts: tuple[str, ...], name: str, size: int) -> bool:
        try:
            with self._dir(parts) as fd:
                st = lstat_at(fd, name)  # lstat: a symlink is not a regular file
        except (FileNotFoundError, LibraryEscape, FilesError):
            return False
        return stat.S_ISREG(st.st_mode) and st.st_size == size

    def blob_present(self, h: str, size: int) -> bool:
        """The stored copy exists as a regular file of the right size (a receipt alone is no proof)."""
        _check_hash(h)
        return self._regular_size(("library", STORE, h[:2]), h, size)

    def library_file_present(self, library_path: str, size: int) -> bool:
        """The person's own file (a path under <dir> from link_into_library) is a regular file of size."""
        try:
            parts = split_path(library_path)
        except FilesError:
            return False
        if len(parts) < 2 or parts[0] != "library":
            return False
        return self._regular_size(parts[:-1], parts[-1], size)

    def asset_present(self, h: str, size: int, library_path: str) -> bool:
        """Both the stored copy and the person's own file hold size bytes: what `check` calls "have"."""
        return self.blob_present(h, size) and self.library_file_present(library_path, size)

    @staticmethod
    def _regular_size_in(fd: int, name: str, size: int) -> bool:
        try:
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return stat.S_ISREG(st.st_mode) and st.st_size == size

    def place_blob(self, staged: Path, h: str, size: int) -> None:
        """Make the verified, fsynced staged file the stored copy of h, unless a good one exists."""
        _check_hash(h)
        with self._dir(("library", STORE, h[:2]), create=True) as fd, self._dir(("staging",)) as stg:
            name = staged.name
            try:
                try:
                    os.link(name, h, src_dir_fd=stg, dst_dir_fd=fd, follow_symlinks=False)
                except OSError as exc:
                    if isinstance(exc, FileExistsError) or exc.errno not in _NO_LINK:
                        raise
                    sfd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=stg)
                    try:
                        self._copy_into(sfd, fd, h)
                    finally:
                        os.close(sfd)
            except FileExistsError:
                if not self._regular_size_in(fd, h, size):
                    os.replace(name, h, src_dir_fd=stg, dst_dir_fd=fd)  # heal a damaged copy with bytes we just verified
            os.fsync(fd)

    # ---- a person's library -------------------------------------------------------------------
    def link_into_library(self, h: str, rel_dir: PurePosixPath, name: str) -> str:
        """Give the person a file for h under library/<rel_dir>/ and return its path under <dir>.

        A hard link to the stored copy; a copy when the filesystem cannot link. An existing name
        is never overwritten: "name (2).ext" and so on.
        """
        _check_hash(h)
        folder_parts = ("library", *rel_dir.parts)
        with self._dir(("library", STORE, h[:2])) as sfd, self._dir(folder_parts, create=True) as fd:
            for candidate in _candidates(name):
                with _guard():
                    validate_name(candidate)
                try:
                    try:
                        os.link(h, candidate, src_dir_fd=sfd, dst_dir_fd=fd, follow_symlinks=False)
                    except OSError as exc:
                        if isinstance(exc, FileExistsError) or exc.errno not in _NO_LINK:
                            raise
                        src = os.open(h, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=sfd)
                        try:
                            self._copy_into(src, fd, candidate)
                        finally:
                            os.close(src)
                except FileExistsError:
                    continue
                os.fsync(fd)
                return PurePosixPath(*folder_parts, candidate).as_posix()
        raise FileExistsError(f"no free file name for {name!r}")

    def restore_library_file(self, h: str, library_path: str) -> None:
        """Put the stored copy of h back at the person's own path, replacing a missing or damaged file.

        A damaged stored copy is healed by a new inode (place_blob), so the person's old hard link
        still holds the damaged bytes until it is replaced here. The new file is made under a
        temporary name (library names never start with ".") and renamed over the old one.
        """
        _check_hash(h)
        with _guard():
            *folder, name = split_path(library_path)
        if not folder or folder[0] != "library":
            raise LibraryEscape("not a library path")
        tmp = f".heal-{secrets.token_hex(8)}"
        with self._dir(("library", STORE, h[:2])) as sfd, self._dir(tuple(folder), create=True) as fd:
            try:
                try:
                    os.link(h, tmp, src_dir_fd=sfd, dst_dir_fd=fd, follow_symlinks=False)
                except OSError as exc:
                    if exc.errno not in _NO_LINK:
                        raise
                    src = os.open(h, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=sfd)
                    try:
                        self._copy_into(src, fd, tmp)
                    finally:
                        os.close(src)
                os.replace(tmp, name, src_dir_fd=fd, dst_dir_fd=fd)
            except BaseException:
                try:
                    os.unlink(tmp, dir_fd=fd)
                except FileNotFoundError:
                    pass
                raise
            os.fsync(fd)

    @staticmethod
    def _copy_into(src_fd: int, dir_fd: int, name: str) -> None:
        """Copy for filesystems without hard links: create name exclusively under dir_fd, copy, fsync.

        FileExistsError when it exists. A crash mid-copy leaves a short file, which
        blob_present() rejects by size and place_blob() then replaces.
        """
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=dir_fd)
        try:
            with os.fdopen(os.dup(src_fd), "rb") as fin, os.fdopen(fd, "wb", closefd=False) as fout:
                shutil.copyfileobj(fin, fout, READ_CHUNK)
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            try:
                os.unlink(name, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            raise
        os.close(fd)

    def free_bytes(self) -> int:
        path = self.root
        while not path.exists() and path != path.parent:
            path = path.parent
        return shutil.disk_usage(path).free
