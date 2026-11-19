# SPDX-License-Identifier: Apache-2.0
"""The catalog is parsed once, not on every request (perf-smoke p95 grew with the app count).

Behaviour must stay identical to a fresh read each time: edits, new apps, removed apps, broken
manifests and changed scan.json files all show up on the very next load().

A file changed in the last two seconds is never cached (onemind_core.filesig): on Linux its mtime
and ctime only move once per clock tick, so a same-size rewrite in that tick looks unchanged. Tests
that check caching therefore settle their files first, as files on a real box are.
"""

import os
import shutil
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from conftest import FIXTURES, write_scan
from onemind_core.catalog import Catalog
from onemind_core.filesig import RACY_WINDOW_NS, cache_signature
from onemind_core.scan import read_scan


def settle(root):
    """Date every file under root an hour back, like a file written long before it is read."""
    old = time.time() - 3600
    for path in [root, *root.rglob("*")] if root.is_dir() else [root]:
        os.utime(path, (old, old))


def make_apps(tmp_path, n=40):
    apps = tmp_path / "apps"
    apps.mkdir()
    for i in range(n):
        d = apps / f"app-{i}"
        shutil.copytree(FIXTURES / "apps" / "whoami", d)
        text = (d / "onemind.app.yaml").read_text().replace("id: whoami", f"id: app-{i}")
        (d / "onemind.app.yaml").write_text(text)
    settle(apps)
    return apps


def test_load_does_not_reparse_unchanged_manifests(tmp_path):
    cat = Catalog(make_apps(tmp_path))
    assert len(cat.load()) == 40
    assert cat.parse_count == 40
    for _ in range(25):
        assert len(cat.load()) == 40
        assert cat.get("app-7") is not None
    assert cat.parse_count == 40  # nothing parsed after warm-up


def test_warm_load_cost_does_not_include_parsing(tmp_path):
    cat = Catalog(make_apps(tmp_path, 60))
    t = time.perf_counter()
    cat.load()
    cold = time.perf_counter() - t
    t = time.perf_counter()
    for _ in range(20):
        cat.load()
    warm = (time.perf_counter() - t) / 20
    assert cat.parse_count == 60
    assert warm < cold / 4  # generous: a warm load only lists and stats the files


def test_edit_add_remove_and_break_show_up_on_next_load(tmp_path):
    apps = make_apps(tmp_path, 3)
    cat = Catalog(apps)
    assert set(cat.load()) == {"app-0", "app-1", "app-2"}

    path = apps / "app-1" / "onemind.app.yaml"
    path.write_text(path.read_text().replace("name: Whoami", "name: Renamed", 1) + "\n# edited\n")
    assert cat.get("app-1").manifest["metadata"]["name"] == "Renamed"

    shutil.rmtree(apps / "app-2")
    shutil.copytree(apps / "app-0", apps / "app-9")
    (apps / "app-9" / "onemind.app.yaml").write_text(
        (apps / "app-0" / "onemind.app.yaml").read_text().replace("id: app-0", "id: app-9")
    )
    assert set(cat.load()) == {"app-0", "app-1", "app-9"}

    path.write_text("not: [valid")  # broken YAML: skipped and reported, others stay
    assert set(cat.load()) == {"app-0", "app-9"}
    assert cat.errors["app-1"] == ["cannot parse: ParserError"]
    assert cat.errors["app-1"] == ["cannot parse: ParserError"]  # still reported while cached

    shutil.rmtree(apps / "app-1")
    cat.load()
    assert "app-1" not in cat.errors


def test_wrong_folder_name_stays_an_error_while_cached(tmp_path):
    apps = tmp_path / "apps"
    shutil.copytree(FIXTURES / "apps" / "wrong-folder", apps / "wrong-folder")
    settle(apps)
    cat = Catalog(apps)
    for _ in range(3):
        assert cat.load() == {}
        assert "must match folder name" in cat.errors["wrong-folder"][0]
    assert cat.parse_count == 1


def test_scan_record_is_cached_but_changes_are_seen(tmp_path):
    d = tmp_path / "app"
    d.mkdir()
    now = datetime.now(UTC)
    # Back-to-back rewrites in place, same length ("pass" <-> "fail"), same inode, on Linux often
    # within one clock tick: each one must be seen on the very next read.
    for result in ("pass", "fail", "pass", "fail", "pass"):
        write_scan(d, now - timedelta(hours=1), result=result)
        assert read_scan(d).result == result

    settle(d / "scan.json")
    first = read_scan(d)
    assert first is not None and first.result == "pass"
    assert read_scan(d) is first  # same parsed record, file not re-read

    write_scan(d, now - timedelta(hours=1), result="fail")
    assert read_scan(d).result == "fail"
    settle(d / "scan.json")
    failed = read_scan(d)
    assert failed.result == "fail" and read_scan(d) is failed  # cached again once settled
    (d / "scan.json").write_text("{not json")
    assert read_scan(d) is None  # an unreadable scan is never served from the cache
    (d / "scan.json").unlink()
    assert read_scan(d) is None


def test_same_size_manifest_edit_is_seen_at_once(tmp_path):
    apps = make_apps(tmp_path, 1)
    cat = Catalog(apps)
    assert cat.get("app-0").manifest["metadata"]["name"] == "Whoami"
    path = apps / "app-0" / "onemind.app.yaml"
    for name in ("Whoamj", "Whoamk", "Whoami"):  # same length, same inode, back to back
        path.write_text(path.read_text().replace(cat.get("app-0").manifest["metadata"]["name"], name, 1))
        assert cat.get("app-0").manifest["metadata"]["name"] == name


def test_signature_is_withheld_while_a_rewrite_could_share_the_clock_tick():
    now = 1_800_000_000_000_000_000
    st = SimpleNamespace(st_mtime_ns=now, st_ctime_ns=now, st_size=10, st_ino=7)
    assert cache_signature(st, now) is None  # written this tick: a same-size rewrite looks equal
    st.st_mtime_ns = st.st_ctime_ns = now - RACY_WINDOW_NS + 1
    assert cache_signature(st, now) is None
    st.st_mtime_ns = st.st_ctime_ns = now - RACY_WINDOW_NS
    assert cache_signature(st, now) == (st.st_mtime_ns, st.st_ctime_ns, 10, 7)
    # A copied or utime'd file: old mtime, fresh ctime. Any later write moves mtime, so it is safe.
    st.st_mtime_ns, st.st_ctime_ns = now - 3600 * 10**9, now
    assert cache_signature(st, now) is not None
