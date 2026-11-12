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
from pathlib import Path, PurePosixPath

STORE = ".shared-store"
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


class PhotoFiles:
    def __init__(self, root: Path):
        self.root = root
        self.staging_dir = root / "staging"
        self.library_dir = root / "library"
        self.store_dir = self.library_dir / STORE

    # ---- staging -------------------------------------------------------------------------------
    def staging(self, upload_id: str) -> Path:
        return self.staging_dir / upload_id

    def create_staging(self, upload_id: str) -> None:
        self.staging_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.staging(upload_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        fsync_dir(self.staging_dir)

    def staged_size(self, upload_id: str) -> int | None:
        try:
            return os.stat(self.staging(upload_id)).st_size
        except FileNotFoundError:
            return None

    def discard(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    # ---- the shared store ---------------------------------------------------------------------
    def store_path(self, h: str) -> Path:
        return self.store_dir / h[:2] / h

    def blob_present(self, h: str, size: int) -> bool:
        """The stored copy exists as a regular file of the right size (a receipt alone is no proof)."""
        try:
            st = os.stat(self.store_path(h))
        except FileNotFoundError:
            return False
        return stat.S_ISREG(st.st_mode) and st.st_size == size

    def library_file_present(self, library_path: str, size: int) -> bool:
        """The person's own file (a path under <dir> from link_into_library) is a regular file of size."""
        try:
            st = os.lstat(self.root / library_path)
        except FileNotFoundError:
            return False
        return stat.S_ISREG(st.st_mode) and st.st_size == size

    def asset_present(self, h: str, size: int, library_path: str) -> bool:
        """Both the stored copy and the person's own file hold size bytes: what `check` calls "have"."""
        return self.blob_present(h, size) and self.library_file_present(library_path, size)

    def place_blob(self, staged: Path, h: str, size: int) -> None:
        """Make the verified, fsynced staged file the stored copy of h, unless a good one exists."""
        dest = self.store_path(h)
        dest.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        try:
            try:
                os.link(staged, dest)
            except OSError as exc:
                if isinstance(exc, FileExistsError) or exc.errno not in _NO_LINK:
                    raise
                self._copy_into(staged, dest)
        except FileExistsError:
            if not self.blob_present(h, size):
                os.replace(staged, dest)  # heal a damaged copy with bytes we just verified
        fsync_dir(dest.parent)

    # ---- a person's library -------------------------------------------------------------------
    def link_into_library(self, h: str, rel_dir: PurePosixPath, name: str) -> str:
        """Give the person a file for h under library/<rel_dir>/ and return its path under <dir>.

        A hard link to the stored copy; a copy when the filesystem cannot link. An existing name
        is never overwritten: "name (2).ext" and so on.
        """
        folder = self.library_dir.joinpath(*rel_dir.parts)
        folder.mkdir(mode=0o750, parents=True, exist_ok=True)
        src = self.store_path(h)
        for candidate in _candidates(name):
            target = folder / candidate
            try:
                try:
                    os.link(src, target)
                except OSError as exc:
                    if isinstance(exc, FileExistsError) or exc.errno not in _NO_LINK:
                        raise
                    self._copy_into(src, target)
            except FileExistsError:
                continue
            fsync_dir(folder)
            return target.relative_to(self.root).as_posix()
        raise FileExistsError(f"no free file name for {name!r}")

    def restore_library_file(self, h: str, library_path: str) -> None:
        """Put the stored copy of h back at the person's own path, replacing a missing or damaged file.

        A damaged stored copy is healed by a new inode (place_blob), so the person's old hard link
        still holds the damaged bytes until it is replaced here. The new file is made under a
        temporary name (library names never start with ".") and renamed over the old one.
        """
        target = self.root / library_path
        target.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        tmp = target.parent / f".heal-{secrets.token_hex(8)}"
        try:
            try:
                os.link(self.store_path(h), tmp)
            except OSError as exc:
                if exc.errno not in _NO_LINK:
                    raise
                self._copy_into(self.store_path(h), tmp)
            os.replace(tmp, target)
        except BaseException:
            self.discard(tmp)
            raise
        fsync_dir(target.parent)

    def _copy_into(self, src: Path, dest: Path) -> None:
        """Copy for filesystems without hard links: create dest exclusively, copy, fsync.

        FileExistsError when dest exists. A crash mid-copy leaves a short file, which
        blob_present() rejects by size and place_blob() then replaces.
        """
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            with open(src, "rb") as fin, os.fdopen(fd, "wb", closefd=False) as fout:
                shutil.copyfileobj(fin, fout, READ_CHUNK)
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            self.discard(dest)
            raise
        os.close(fd)

    def free_bytes(self) -> int:
        path = self.root
        while not path.exists() and path != path.parent:
            path = path.parent
        return shutil.disk_usage(path).free
