# SPDX-License-Identifier: Apache-2.0
"""Same-size rewrites inside one clock tick must never be served from the scan or manifest cache.

These tests freeze what stat() reports, so they do not depend on the host's clock granularity: on
macOS APFS (nanosecond timestamps) a real rewrite always moves ctime, so only a frozen stat shows
what Debian arm64 (one 4 ms tick) does. Each write keeps the inode and the size, and stat() keeps
reporting the same ctime and mtime, as two writes in one tick do on Linux:

* fresh: mtime = ctime = now, a plain write in place;
* copied: mtime an hour old, ctime = now, a cp -p / shutil.copy2 / tar -x / rsync -t style write
  that sets mtime back. Only the kernel-stamped ctime may decide (onemind_core.filesig).

They do not import onemind_core.filesig, so they also run against the code before it existed.
"""

import os
import shutil
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest
from conftest import FIXTURES, write_scan
from onemind_core.catalog import Catalog
from onemind_core.scan import read_scan

HOUR_NS = 3600 * 10**9


@contextmanager
def one_tick(name: str, *, copied: bool):
    """Make stat() of every file called `name` report one frozen tick, and freeze the clock there."""
    tick = time.time_ns()
    mtime = tick - HOUR_NS if copied else tick
    real_stat = Path.stat

    def frozen_stat(self, *args, **kwargs):
        st = real_stat(self, *args, **kwargs)
        if self.name != name:
            return st
        return os.stat_result(
            (st.st_mode, st.st_ino, st.st_dev, st.st_nlink, st.st_uid, st.st_gid, st.st_size,
             int(st.st_atime), mtime // 10**9, tick // 10**9),
            {"st_atime_ns": st.st_atime_ns, "st_mtime_ns": mtime, "st_ctime_ns": tick},
        )

    with mock.patch.object(Path, "stat", frozen_stat), mock.patch.object(time, "time_ns", return_value=tick):
        yield


@pytest.mark.parametrize("copied", [False, True], ids=["fresh", "copied"])
def test_scan_rewrite_in_one_tick_is_seen(tmp_path, copied):
    d = tmp_path / "app"
    d.mkdir()
    scanned_at = datetime.now(UTC) - timedelta(hours=1)
    with one_tick("scan.json", copied=copied):
        write_scan(d, scanned_at, result="pass")
        assert read_scan(d).result == "pass"
        ino = (d / "scan.json").stat().st_ino
        write_scan(d, scanned_at, result="fail")  # same size, same inode, same tick
        assert (d / "scan.json").stat().st_ino == ino
        assert read_scan(d).result == "fail"


@pytest.mark.parametrize("copied", [False, True], ids=["fresh", "copied"])
def test_manifest_rewrite_in_one_tick_is_seen(tmp_path, copied):
    apps = tmp_path / "apps"
    shutil.copytree(FIXTURES / "apps" / "whoami", apps / "whoami")
    path = apps / "whoami" / "onemind.app.yaml"
    cat = Catalog(apps)
    with one_tick("onemind.app.yaml", copied=copied):
        assert cat.get("whoami").manifest["metadata"]["name"] == "Whoami"
        size = path.stat().st_size
        path.write_text(path.read_text().replace("name: Whoami", "name: Whoamj", 1))
        assert path.stat().st_size == size
        assert cat.get("whoami").manifest["metadata"]["name"] == "Whoamj"
