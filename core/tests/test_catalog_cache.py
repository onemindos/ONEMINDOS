# SPDX-License-Identifier: Apache-2.0
"""The catalog is parsed once, not on every request (perf-smoke p95 grew with the app count).

Behaviour must stay identical to a fresh read each time: edits, new apps, removed apps, broken
manifests and changed scan.json files all show up on the very next load().
"""

import shutil
import time
from datetime import UTC, datetime, timedelta

from conftest import FIXTURES, write_scan
from onemind_core.catalog import Catalog
from onemind_core.scan import read_scan


def make_apps(tmp_path, n=40):
    apps = tmp_path / "apps"
    apps.mkdir()
    for i in range(n):
        d = apps / f"app-{i}"
        shutil.copytree(FIXTURES / "apps" / "whoami", d)
        text = (d / "onemind.app.yaml").read_text().replace("id: whoami", f"id: app-{i}")
        (d / "onemind.app.yaml").write_text(text)
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
    cat = Catalog(apps)
    for _ in range(3):
        assert cat.load() == {}
        assert "must match folder name" in cat.errors["wrong-folder"][0]
    assert cat.parse_count == 1


def test_scan_record_is_cached_but_changes_are_seen(tmp_path):
    d = tmp_path / "app"
    d.mkdir()
    now = datetime.now(UTC)
    write_scan(d, now - timedelta(hours=1))
    first = read_scan(d)
    assert first is not None and first.result == "pass"
    assert read_scan(d) is first  # same parsed record, file not re-read

    write_scan(d, now - timedelta(hours=1), result="fail")
    assert read_scan(d).result == "fail"
    (d / "scan.json").write_text("{not json")
    assert read_scan(d) is None  # an unreadable scan is never served from the cache
    (d / "scan.json").unlink()
    assert read_scan(d) is None
