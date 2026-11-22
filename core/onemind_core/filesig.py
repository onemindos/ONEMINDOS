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
only trusted once the file's ctime is clearly older than now. A later write then lands in a later
tick and moves ctime. Until then the file is simply read again, which costs one small read for
files changed in the last couple of seconds.

Only ctime counts, never mtime: user space can set mtime to any value (utime, cp -p,
shutil.copy2, tar -x, rsync -t), but the kernel alone stamps ctime, with the current tick, on
every write, chmod or utime. A copied file carries its source's old mtime, so an mtime-based rule
would trust it at once, and a same-size rewrite carrying the same old mtime in the same tick
would then look unchanged.
"""

from __future__ import annotations

import os
import time

# Longer than any timestamp granularity we expect (Linux ticks are <= 10 ms; FAT and some network
# filesystems use 1-2 s), and short enough that a just-edited file is cached again almost at once.
RACY_WINDOW_NS = 2_000_000_000


def cache_signature(st: os.stat_result, now_ns: int | None = None) -> tuple | None:
    """The cache key for a file with this stat, or None if it changed too recently to trust.

    The key is trusted only when ctime is at least RACY_WINDOW_NS old: any later write stamps
    ctime with a later tick, so the key must change. mtime is ignored for this decision because
    it can be set back by the writer (a cp -p copy has an old mtime and a fresh ctime). A ctime
    in the future (clock stepped back) is never counted as old.
    """
    now = time.time_ns() if now_ns is None else now_ns
    age = now - st.st_ctime_ns
    if age < RACY_WINDOW_NS:  # also true for a future ctime (negative age)
        return None
    return (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_ino)
