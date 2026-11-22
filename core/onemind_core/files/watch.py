# SPDX-License-Identifier: Apache-2.0
"""The index scanner and the inotify watcher (#698): writes that bypass the FILES API reach the index.

SMB (Samba) and WebDAV write straight into the space folders, so the FILES service never sees
them. Two things catch them:

- a scanner: a full reconcile of every space at start and every `index_scan_interval_s`;
- on Linux, an inotify watch on every folder of every space. An event marks its space dirty, and
  the space is reconciled once it has been quiet for DEBOUNCE_S (at most MAX_DELAY_S after the
  first event), so a copy of a thousand files is one rescan, not a thousand.

inotify (man7.org/linux/man-pages/man7/inotify.7.html) is called through ctypes, so there is no
new dependency. When it is missing (not Linux) or out of watches (fs.inotify.max_user_watches),
the periodic scan is the fallback. The scanner never creates folders: a space that does not exist
yet has nothing to index.
"""

from __future__ import annotations

import ctypes
import logging
import os
import select
import struct
import sys
import threading
import time
from datetime import timedelta

from . import paths

log = logging.getLogger("onemind.files.index")

DEBOUNCE_S = 1.0
MAX_DELAY_S = 5.0
IN_MASK = (0x2 | 0x4 | 0x8 | 0x40 | 0x80 | 0x100 | 0x200 | 0x400 | 0x800)  # modify, attrib, close_write, moves, create, delete, self
IN_Q_OVERFLOW = 0x4000
IN_IGNORED = 0x8000
_EVENT = struct.Struct("iIII")


class Inotify:
    """The few inotify calls the watcher needs. `open()` returns None where inotify is unavailable."""

    def __init__(self, fd: int, libc):
        self.fd = fd
        self.libc = libc
        self.roots: dict[int, str] = {}   # watch descriptor -> root id
        self.full = False                 # out of watches: the periodic scan covers the rest

    @classmethod
    def open(cls) -> Inotify | None:
        if not sys.platform.startswith("linux"):
            return None
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        except (OSError, AttributeError):
            return None
        return cls(fd, libc) if fd >= 0 else None

    def watch(self, dir_fd: int, root: str) -> None:
        if self.full:
            return
        wd = self.libc.inotify_add_watch(self.fd, f"/proc/self/fd/{dir_fd}".encode(), IN_MASK)
        if wd >= 0:
            self.roots[wd] = root
        elif ctypes.get_errno() == 28:  # ENOSPC: the per-user watch limit
            self.full = True
            log.warning("files index: out of inotify watches; changes made outside OneMind wait for the next scan")

    def read(self, timeout: float) -> set[str | None]:
        """Roots with events within `timeout` seconds; None in the set means "all of them" (overflow)."""
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return set()
        try:
            data = os.read(self.fd, 64 * 1024)
        except BlockingIOError:
            return set()
        out: set[str | None] = set()
        pos = 0
        while pos + _EVENT.size <= len(data):
            wd, mask, _cookie, length = _EVENT.unpack_from(data, pos)
            pos += _EVENT.size + length
            if mask & IN_Q_OVERFLOW:
                out.add(None)
            elif mask & IN_IGNORED:
                self.roots.pop(wd, None)
            elif wd in self.roots:
                out.add(self.roots[wd])
        return out

    def close(self) -> None:
        os.close(self.fd)


class IndexWatcher:
    """Background thread: scan every space, then reconcile the ones inotify reports as changed."""

    def __init__(self, files):
        self.files = files
        self.settings = files.settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.inotify: Inotify | None = None

    # ---- the spaces on disk ---------------------------------------------------------------
    def spaces(self) -> list[tuple[str, tuple[str, ...]]]:
        """(root id, folder names under the Files root) of every space that exists on disk."""
        out = [("shared", ("shared",))]
        out += [(f"home:{pid}", ("home", name)) for pid, name in sorted(self.files.repo.spaces().items())]
        return out

    def scan(self, only: set[str] | None = None) -> int:
        """Reconcile the spaces (all, or the root ids in `only`). Returns the rows changed."""
        base = self.settings.root
        try:
            base_fd = os.open(base, paths.O_DIR)
        except OSError:
            return 0  # the storage is not there (yet): nothing to index
        changed = 0
        try:
            for root, folder in self.spaces():
                if only is not None and root not in only:
                    continue
                try:
                    space = paths.open_dir(base_fd, folder)
                except Exception:
                    continue
                try:
                    on_dir = (lambda fd, r=root: self.inotify.watch(fd, r)) if self.inotify else None
                    changed += self.files.index.reconcile(space, root, (), hash_max=None, on_dir=on_dir)
                    self.files.index.prune(root, timedelta(days=self.settings.index_tombstone_days))
                except Exception:
                    log.exception("files index: scan of %s failed", root)
                finally:
                    os.close(space)
        finally:
            os.close(base_fd)
        return changed

    # ---- the thread -----------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        if self.settings.index_watch:
            self.inotify = Inotify.open()
        self._thread = threading.Thread(target=self._run, name="files-index", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if self.inotify is not None:
            self.inotify.close()
            self.inotify = None

    def _run(self) -> None:
        interval = self.settings.index_scan_interval_s
        next_full = 0.0
        dirty: set[str] = set()
        first = last = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now >= next_full:
                self.scan()
                dirty.clear()
                next_full = now + interval if interval else float("inf")
            if self.inotify is None:
                self._stop.wait(min(60.0, max(0.5, next_full - now)))
                continue
            got = self.inotify.read(0.5)
            now = time.monotonic()
            if got:
                if not dirty:
                    first = now
                last = now
                if None in got:
                    next_full = now  # events were lost: rescan everything
                dirty |= {r for r in got if r is not None}
            if dirty and (now - last >= DEBOUNCE_S or now - first >= MAX_DELAY_S):
                todo, dirty = dirty, set()
                self.scan(todo)


__all__ = ["IndexWatcher", "Inotify"]
