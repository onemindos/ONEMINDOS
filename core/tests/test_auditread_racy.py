# SPDX-License-Identifier: Apache-2.0
"""`verify()` must never return a cached "ok" after a same-size change in the same tick (#364).

AuditReader caches a full verify result until the audit file changes. The kernel stamps mtime and
ctime from a coarse clock (one 4 ms tick on Debian's arm64 kernel), so a same-size edit in place
within one tick leaves mtime, ctime, size and inode unchanged. A cache keyed on (size, mtime) then
keeps reporting the old "ok" for a tampered log.

These tests freeze what stat() reports, so they do not depend on the host's clock granularity:

* fresh: mtime = ctime = now, a plain write in place;
* copied: mtime an hour old, ctime = now, a write that also sets mtime back (utime, cp -p).

They do not import onemind_core.filesig, so they also run against the code before the fix.
"""

import os
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

from onemind_core import auditread
from onemind_core.audit import AuditLog
from onemind_core.auditread import AuditReader

HOUR_NS = 3600 * 10**9


def write_chain(p: Path, n: int = 5) -> None:
    log = AuditLog(p, lambda: datetime(2026, 11, 19, 9, 0, tzinfo=UTC))
    for i in range(n):
        log.append("test.event", {"id": "x", "kind": "person", "role": "owner"}, None, {"i": i})


def tamper_same_size(p: Path) -> None:
    """Change one record in place without changing the file's length (a forged value)."""
    data = p.read_bytes()
    forged = data.replace(b'"i":2', b'"i":7', 1)
    assert forged != data and len(forged) == len(data)
    with p.open("r+b") as fh:  # in place: same inode
        fh.write(forged)


def reader(p: Path) -> AuditReader:
    return AuditReader(p, lambda: datetime(2026, 11, 19, 9, 0, tzinfo=UTC), lambda _id: set())


@contextmanager
def frozen_stat(name: str, *, tick: int, mtime: int):
    """Make stat() of every file called `name` report ctime=tick and this mtime."""
    real_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        st = real_stat(self, *args, **kwargs)
        if self.name != name:
            return st
        return os.stat_result(
            (st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid, st.st_gid, st.st_size,
             int(st.st_atime), mtime // 10**9, tick // 10**9),
            {"st_atime_ns": st.st_atime_ns, "st_mtime_ns": mtime, "st_ctime_ns": tick},
        )

    with mock.patch.object(Path, "stat", fake_stat):
        yield


@pytest.mark.parametrize("copied", [False, True], ids=["fresh", "copied"])
def test_same_tick_tamper_is_not_served_from_cache(tmp_path, copied):
    p = tmp_path / "audit.jsonl"
    tick = time.time_ns()
    mtime = tick - HOUR_NS if copied else tick
    with frozen_stat(p.name, tick=tick, mtime=mtime), mock.patch.object(time, "time_ns", return_value=tick):
        write_chain(p)
        r = reader(p)
        assert r.verify()["ok"] is True
        tamper_same_size(p)  # same size, same inode, same tick
        result = r.verify()
        assert result["ok"] is False, "verify() returned a cached ok for a tampered log"
        assert result["first_bad_seq"] == 3


def test_settled_file_is_verified_once(tmp_path):
    """Once ctime is clearly in the past, a full verify is cached: no re-hash on every call."""
    p = tmp_path / "audit.jsonl"
    write_chain(p)
    now = time.time_ns()
    old = now - 10 * 10**9
    with frozen_stat(p.name, tick=old, mtime=old), mock.patch.object(time, "time_ns", return_value=now):
        r = reader(p)
        assert r.verify()["ok"] is True
        with mock.patch.object(auditread, "verify_file", side_effect=AssertionError("re-verified")):
            assert r.verify()["ok"] is True


def test_settled_tamper_with_mtime_set_back_is_seen(tmp_path):
    """A later write moves ctime even when the writer sets mtime back, so the cache is dropped."""
    p = tmp_path / "audit.jsonl"
    write_chain(p)
    now = time.time_ns()
    t1 = now - 10 * 10**9
    with mock.patch.object(time, "time_ns", return_value=now):
        with frozen_stat(p.name, tick=t1, mtime=t1):
            r = reader(p)
            assert r.verify()["ok"] is True
        tamper_same_size(p)
        with frozen_stat(p.name, tick=t1 + 4_000_000, mtime=t1):  # one 4 ms tick later
            assert r.verify()["ok"] is False


def test_partial_verify_is_never_cached(tmp_path):
    """A from_seq check must not fill or read the full-verify cache."""
    p = tmp_path / "audit.jsonl"
    write_chain(p)
    now = time.time_ns()
    old = now - 10 * 10**9
    with frozen_stat(p.name, tick=old, mtime=old), mock.patch.object(time, "time_ns", return_value=now):
        r = reader(p)
        assert r.verify(from_seq=3)["ok"] is True
        assert r._verify_cache is None
