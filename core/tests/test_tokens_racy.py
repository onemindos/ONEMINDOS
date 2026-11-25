# SPDX-License-Identifier: Apache-2.0
"""A revoke written to the tokens file inside one clock tick must take effect at once (#363).

The kernel stamps mtime and ctime from a coarse clock: on Linux they only move once per timer tick
(4 ms on Debian's arm64 kernel). Revoking a token by rewriting the file with a same-length token
keeps the inode and the size, so two writes in one tick look identical to stat(). A store that
reloads only when mtime changes keeps accepting the revoked token until the file changes again.

These tests freeze what stat() reports, so they do not depend on the host's clock granularity:

* fresh: mtime = ctime = now, a plain write in place;
* copied: mtime an hour old, ctime = now, a cp -p / install -p style write that sets mtime back.

They do not import onemind_core.filesig, so they also run against the code before the fix.
"""

import os
import time
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pytest
import yaml

from onemind_core.auth import TokenStore

HOUR_NS = 3600 * 10**9
OLD = "revoked-token-aaaaaaaaaaaa"
NEW = "replaced-token-bbbbbbbbbbb"
assert len(OLD) == len(NEW)  # a same-size rewrite: inode and size stay the same


def write_tokens(p: Path, token: str) -> None:
    p.write_text(yaml.safe_dump({"tokens": {token: {"id": "z", "kind": "person", "role": "owner"}}}))


@contextmanager
def frozen_stat(name: str, *, tick: int, mtime: int):
    """Make stat() of every file called `name` report ctime=tick and this mtime; clock at `now`."""
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


@contextmanager
def one_tick(name: str, *, copied: bool):
    """stat() of `name` reports one frozen tick, and the clock stands still on that tick."""
    tick = time.time_ns()
    mtime = tick - HOUR_NS if copied else tick
    with frozen_stat(name, tick=tick, mtime=mtime), mock.patch.object(time, "time_ns", return_value=tick):
        yield


@pytest.mark.parametrize("copied", [False, True], ids=["fresh", "copied"])
def test_same_tick_revoke_is_seen_at_once(tmp_path, copied):
    p = tmp_path / "tokens.yaml"
    with one_tick(p.name, copied=copied):
        write_tokens(p, OLD)
        store = TokenStore(p)
        assert store.lookup(OLD) is not None
        write_tokens(p, NEW)  # the revoke: same size, same inode, same tick
        assert p.stat().st_size == len(p.read_bytes())
        assert store.lookup(OLD) is None, "a revoked token kept working after a same-tick rewrite"
        assert store.lookup(NEW) is not None


def test_same_tick_fix_of_a_broken_file_is_seen(tmp_path):
    """A bad edit followed by its fix in the same tick must not leave the bad file 'remembered'."""
    p = tmp_path / "tokens.yaml"
    with one_tick(p.name, copied=False):
        write_tokens(p, OLD)
        store = TokenStore(p)
        p.write_text("tokens: [unclosed" + " " * (len(p.read_text()) - 17))
        assert store.lookup(OLD) is not None  # last good set kept
        write_tokens(p, NEW)
        assert store.lookup(OLD) is None
        assert store.lookup(NEW) is not None


def test_settled_file_is_parsed_once(tmp_path):
    """Once ctime is clearly in the past, the file is cached: no re-parse on every request."""
    p = tmp_path / "tokens.yaml"
    write_tokens(p, OLD)
    now = time.time_ns()
    old_tick = now - 10 * 10**9
    with frozen_stat(p.name, tick=old_tick, mtime=old_tick), \
            mock.patch.object(time, "time_ns", return_value=now):
        store = TokenStore(p)
        with mock.patch("onemind_core.auth.parse_tokens", side_effect=AssertionError("re-parsed")):
            for _ in range(3):
                assert store.lookup(OLD) is not None


def test_settled_rewrite_is_seen(tmp_path):
    """A rewrite in a later tick moves ctime, so a settled cache is dropped."""
    p = tmp_path / "tokens.yaml"
    write_tokens(p, OLD)
    now = time.time_ns()
    t1 = now - 10 * 10**9
    with mock.patch.object(time, "time_ns", return_value=now):
        with frozen_stat(p.name, tick=t1, mtime=t1):
            store = TokenStore(p)
            assert store.lookup(OLD) is not None
        write_tokens(p, NEW)
        with frozen_stat(p.name, tick=t1 + 4_000_000, mtime=t1):  # one 4 ms tick later, mtime set back
            assert store.lookup(OLD) is None
            assert store.lookup(NEW) is not None
