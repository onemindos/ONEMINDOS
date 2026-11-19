# SPDX-License-Identifier: Apache-2.0
"""When a file's stat() is safe to use as a cache key ("did this file change?").

The catalog and scan caches keep a parsed file until its (mtime, ctime, size, inode) changes. That
is only sound if every later write changes at least one of them. A write in place keeps the inode,
an edit that keeps the length keeps the size ("pass" -> "fail" in scan.json), and the kernel stamps
mtime and ctime from a coarse clock: on Linux they only move once per timer tick (4 ms at the
CONFIG_HZ=250 of Debian's arm64 kernel, up to 10 ms at HZ=100; whole seconds on some filesystems).
So a file written, read and rewritten within one tick can look unchanged, and the cache would keep
serving the old content, for scan.json an old "pass" after the scanner wrote "fail".

Git has the same problem with its index ("racy git") and solves it the same way: a signature is
only trusted once the file's timestamps are clearly older than now. A later write then lands in a
later tick and moves mtime and ctime. Until then the file is simply read again, which costs one
small read for files changed in the last couple of seconds.
"""

from __future__ import annotations

import os
import time

# Longer than any timestamp granularity we expect (Linux ticks are <= 10 ms; FAT and some network
# filesystems use 1-2 s), and short enough that a just-edited file is cached again almost at once.
RACY_WINDOW_NS = 2_000_000_000


def cache_signature(st: os.stat_result, now_ns: int | None = None) -> tuple | None:
    """The cache key for a file with this stat, or None if it changed too recently to trust.

    A later write sets both mtime and ctime to the current tick, so the key can only collide if
    BOTH are still within the current tick; once either is older than the window, any write moves
    it. That is why the older of the two decides (a copy2/utime'd file has an old mtime and is safe).
    """
    now = time.time_ns() if now_ns is None else now_ns
    if now - min(st.st_mtime_ns, st.st_ctime_ns) < RACY_WINDOW_NS:
        return None
    return (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino)
