# SPDX-License-Identifier: Apache-2.0
"""Path handling that cannot leave a space (docs/umbrel2/files-backups.md §4.6).

Two layers, both required:

1. `split_path` validates the client's relative path as text: no `..` or `.` components, no NUL,
   backslash or control characters, no component over 255 bytes, no path over 4096 bytes, valid
   UTF-8. It returns the components; nothing ever joins client text onto a host path.
2. `open_dir` walks those components one at a time with `openat(dir_fd, name, O_DIRECTORY |
   O_NOFOLLOW)`, starting from a descriptor of the space's own directory. No symlink is ever
   followed, so a symlink planted inside a space (or swapped in during a request) cannot lead
   out of it; every later operation (`stat`, `rename`, `mkdir`, `open`) is relative to the
   final descriptor and also refuses to follow a symlink.

There is no string-prefix check anywhere: confinement comes from the descriptors.
"""

from __future__ import annotations

import errno
import os
import stat as stat_mod
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager

from .errors import FilesError, denied, not_found

MAX_COMPONENT_BYTES = 255
MAX_PATH_BYTES = 4096

O_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
O_FILE_READ = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)


class PathRefused(FilesError):
    def __init__(self, message: str):
        super().__init__(422, "conflict", f"invalid path: {message}", reason="invalid_path")


def validate_name(name: str) -> str:
    """One path component (a file or folder name). Returns it unchanged or raises PathRefused."""
    if not isinstance(name, str) or name == "":
        raise PathRefused("empty name")
    if name in (".", ".."):
        raise PathRefused("'.' and '..' are not allowed")
    try:
        raw = name.encode("utf-8")
    except UnicodeEncodeError:
        raise PathRefused("name is not valid UTF-8") from None
    if len(raw) > MAX_COMPONENT_BYTES:
        raise PathRefused(f"a name is longer than {MAX_COMPONENT_BYTES} bytes")
    for ch in name:
        if ch in "/\\\x00" or ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise PathRefused("names may not contain '/', '\\' or control characters")
        if unicodedata.category(ch) in ("Cs", "Co", "Cn") and ord(ch) > 0x7F:
            raise PathRefused("names may not contain unassigned or private-use characters")
    if name.strip() == "":
        raise PathRefused("a name cannot be only spaces")
    return name


def split_path(path: str | None) -> tuple[str, ...]:
    """A client path ('' or '/' is the space itself; '/a/b' and 'a/b' are the same) -> components."""
    if path is None:
        return ()
    if not isinstance(path, str):
        raise PathRefused("path must be a string")
    try:
        if len(path.encode("utf-8")) > MAX_PATH_BYTES:
            raise PathRefused(f"path is longer than {MAX_PATH_BYTES} bytes")
    except UnicodeEncodeError:
        raise PathRefused("path is not valid UTF-8") from None
    if "\x00" in path or "\\" in path:
        raise PathRefused("path may not contain NUL or '\\'")
    parts = tuple(p for p in path.split("/") if p != "")
    for p in parts:
        validate_name(p)
    return parts


def join(parts: tuple[str, ...]) -> str:
    """The canonical client form of a path: '/' for the space itself, else '/a/b'."""
    return "/" + "/".join(parts)


def is_within(parts: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return parts[: len(prefix)] == prefix


def _refuse_os_error(exc: OSError) -> FilesError:
    if exc.errno == errno.ENOENT:
        return not_found()
    if exc.errno in (errno.ELOOP, errno.EMLINK):  # O_NOFOLLOW hit a symlink
        return denied("the path goes through a symbolic link, which FILES never follows", "symlink")
    if exc.errno == errno.ENOTDIR:
        return FilesError(409, "conflict", "a component of the path is not a folder", reason="not_a_folder")
    if exc.errno == errno.EACCES:
        return denied("the box cannot read this path", "host_permission")
    return FilesError(503, "unavailable", f"file system error ({errno.errorcode.get(exc.errno, exc.errno)})")


def os_error(exc: OSError) -> FilesError:
    """Map an OSError from a confined operation onto the API's error envelope."""
    return _refuse_os_error(exc)


def open_dir(base_fd: int, parts: tuple[str, ...]) -> int:
    """Descriptor of the folder `parts` under base_fd, following no symlink. Caller closes it."""
    fd = os.dup(base_fd)
    try:
        for name in parts:
            nfd = os.open(name, O_DIR, dir_fd=fd)
            os.close(fd)
            fd = nfd
    except OSError as exc:
        err = _refuse_os_error(exc)
        if exc.errno == errno.ENOTDIR:  # macOS (and some Linux paths) say ENOTDIR for a symlink here
            try:
                if stat_mod.S_ISLNK(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode):
                    err = _refuse_os_error(OSError(errno.ELOOP, "symlink"))
            except OSError:
                pass
        os.close(fd)
        raise err from None
    return fd


@contextmanager
def dir_at(base_fd: int, parts: tuple[str, ...]) -> Iterator[int]:
    fd = open_dir(base_fd, parts)
    try:
        yield fd
    finally:
        os.close(fd)


def lstat_at(dir_fd: int, name: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError as exc:
        raise _refuse_os_error(exc) from None


def exists_at(dir_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def open_file_at(dir_fd: int, name: str) -> tuple[int, os.stat_result]:
    """Open a regular file for reading without following a symlink. Caller closes the fd."""
    try:
        fd = os.open(name, O_FILE_READ, dir_fd=dir_fd)
    except OSError as exc:
        raise _refuse_os_error(exc) from None
    st = os.fstat(fd)
    if not stat_mod.S_ISREG(st.st_mode):
        os.close(fd)
        raise FilesError(409, "conflict", "not a regular file", reason="not_a_file")
    # Clear O_NONBLOCK (only set so that opening a FIFO cannot hang the request).
    try:
        os.set_blocking(fd, True)
    except OSError:
        pass
    return fd, st


def kind_of(st: os.stat_result) -> str:
    if stat_mod.S_ISDIR(st.st_mode):
        return "dir"
    if stat_mod.S_ISREG(st.st_mode):
        return "file"
    if stat_mod.S_ISLNK(st.st_mode):
        return "symlink"
    return "other"


def tree_size(dir_fd: int, name: str | None = None) -> int:
    """Bytes used by a file, or a folder and everything in it, never following a symlink."""
    st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False) if name is not None else os.fstat(dir_fd)
    if not stat_mod.S_ISDIR(st.st_mode):
        return st.st_size if stat_mod.S_ISREG(st.st_mode) else 0
    fd = os.open(name, O_DIR, dir_fd=dir_fd) if name is not None else os.dup(dir_fd)
    total = 0
    try:
        for _root, _dirs, files, rootfd in os.fwalk(".", dir_fd=fd, follow_symlinks=False):
            for f in files:
                try:
                    s = os.stat(f, dir_fd=rootfd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat_mod.S_ISREG(s.st_mode):
                    total += s.st_size
    finally:
        os.close(fd)
    return total
