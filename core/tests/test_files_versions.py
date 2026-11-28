# SPDX-License-Identifier: Apache-2.0
"""FILES previous versions (BAK-04, #241): a member restores yesterday's version of a file.

Fixtures mirror Snapper's numeric directories, metadata and storage subtree.
The privileged Linux check also runs the shipped timeline command against btrfs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Event
from xml.etree import ElementTree

import pytest

from onemind_core.files.settings import FilesSettings
from onemind_core.files.store import new_id

from files_support import ADULT, AGENT, GUEST, OWNER, audit_events, fc, mkdir, ok, upload  # noqa: F401

from test_identity import csrf, enrol, id_settings, setup_owner

YESTERDAY = "snapper-2-20261121T030000Z"
EARLIER = "snapper-1-20261121T020000Z"


@pytest.fixture
def files_root(tmp_path):
    if os.environ.get("ONEMIND_TEST_SNAPPER_TIMELINE"):
        return Path("/data/onemind/files")
    return tmp_path / "files"


@pytest.fixture
def snapshots(tmp_path):
    if os.environ.get("ONEMIND_TEST_SNAPPER_TIMELINE"):
        return Path("/data/storage/.snapshots")
    return tmp_path / "snapshots"


@pytest.fixture
def files_settings(files_root, snapshots):
    return FilesSettings(root=files_root, min_free_bytes=0, snapshots_dir=snapshots)


@pytest.fixture
def settings(settings):
    return id_settings(settings)


def snapshot(files_root, snapshots, name, cleanup="timeline"):
    _, number, stamp = name.split("-")
    entry = snapshots / number
    entry.mkdir(parents=True)
    taken = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    info = entry / "info.xml"
    info.write_text(
        f"<snapshot><type>single</type><num>{number}</num><date>{taken}</date><cleanup>{cleanup}</cleanup></snapshot>"
    )
    capture = snapshots / ".files" / f"{number}-{info.stat().st_ino}"
    shutil.copytree(files_root, capture, symlinks=True)
    capture.with_suffix(".info").hardlink_to(info)
    return capture


def versions(c, headers, root, path):
    return ok(c.get("/v1/files/versions", params={"root": root, "path": path}, headers=headers))


def restore(c, headers, root, path, version, **kw):
    return c.post("/v1/files/ops", headers=headers, json={"op": "restore_version", "root": root, "path": path,
                                                         "version": version, **kw})


def read(c, headers, root, path):
    r = c.get("/v1/files/download", params={"root": root, "path": path}, headers=headers)
    assert r.status_code == 200, r.text
    return r.content


def test_member_restores_yesterdays_version_as_a_new_file(fc, files_root, snapshots, settings):
    ok(upload(fc, ADULT, "home:adult", "/", "notes.txt", b"yesterday's words\n"), 204)
    snapshot(files_root, snapshots, EARLIER)
    snapshot(files_root, snapshots, YESTERDAY)  # unchanged since EARLIER: listed once
    ok(upload(fc, ADULT, "home:adult", "/", "notes.txt", b"today\n", overwrite=True), 204)

    st = ok(fc.get("/v1/files/stat", params={"root": "home:adult", "path": "/notes.txt"}, headers=ADULT))
    assert st["versions_available"] is True
    out = versions(fc, ADULT, "home:adult", "/notes.txt")
    assert out["enabled"] is True and out["exists"] is True
    assert [(v["version"], v["cadence"], v["size"]) for v in out["versions"]] == [(YESTERDAY, "timeline", 18)]
    assert out["versions"][0]["taken_at"].startswith("2026-11-21T03:00:00")

    # the file is still there, so the old copy lands beside it: nothing is overwritten
    entry = ok(restore(fc, ADULT, "home:adult", "/notes.txt", YESTERDAY))
    assert entry["path"] == "/notes (version 2026-11-21 03.00 UTC).txt" and entry["restored_from"] == YESTERDAY
    assert read(fc, ADULT, "home:adult", entry["path"]) == b"yesterday's words\n"
    assert read(fc, ADULT, "home:adult", "/notes.txt") == b"today\n"
    names = [e["name"] for e in ok(fc.get("/v1/files/list", params={"root": "home:adult"}, headers=ADULT))]
    assert names == ["notes (version 2026-11-21 03.00 UTC).txt", "notes.txt"]  # no half-written temp file

    r = restore(fc, ADULT, "home:adult", "/notes.txt", YESTERDAY)
    assert r.status_code == 409 and r.json()["reason"] == "exists"
    r = restore(fc, ADULT, "home:adult", "/notes.txt", YESTERDAY, to_path="/notes.txt")
    assert r.status_code == 409 and r.json()["reason"] == "exists"
    assert read(fc, ADULT, "home:adult", "/notes.txt") == b"today\n"

    # gone today: it comes back at its own path
    ok(fc.post("/v1/files/ops", headers=ADULT, json={"op": "trash", "root": "home:adult", "path": "/notes.txt"}))
    assert versions(fc, ADULT, "home:adult", "/notes.txt")["exists"] is False
    assert ok(restore(fc, ADULT, "home:adult", "/notes.txt", YESTERDAY))["path"] == "/notes.txt"
    assert read(fc, ADULT, "home:adult", "/notes.txt") == b"yesterday's words\n"

    events = [e for e in audit_events(settings) if e["event"] == "files.version.restored"]
    assert len(events) == 2 and events[0]["principal"]["id"] == "adult"


@pytest.mark.parametrize("name", ["界" * 83 + "é.txt", "a." + "é" * 126 + "x"])
def test_restore_generates_a_valid_copy_name_for_long_utf8_files(fc, files_root, snapshots, name):
    assert len(name.encode()) == 255
    ok(upload(fc, ADULT, "shared", "/", name, b"yesterday"), 204)
    snapshot(files_root, snapshots, YESTERDAY)
    ok(upload(fc, ADULT, "shared", "/", name, b"today", overwrite=True), 204)

    # The dashboard sends the source and version without a destination.
    entry = ok(restore(fc, ADULT, "shared", f"/{name}", YESTERDAY))
    assert len(entry["name"].encode()) <= 255
    assert entry["name"].startswith(name[0]) and " (version 2026-11-21 03.00 UTC)" in entry["name"]
    if name.endswith(".txt"):
        assert entry["name"].endswith(".txt")
    assert read(fc, ADULT, "shared", entry["path"]) == b"yesterday"
    assert read(fc, ADULT, "shared", f"/{name}") == b"today"


def test_only_people_with_access_see_or_restore_versions(fc, files_root, snapshots):
    ok(upload(fc, ADULT, "home:adult", "/", "diary.txt", b"private"), 204)
    ok(upload(fc, OWNER, "shared", "/", "list.txt", b"milk"), 204)
    snapshot(files_root, snapshots, YESTERDAY)
    ok(upload(fc, OWNER, "shared", "/", "list.txt", b"milk, eggs", overwrite=True), 204)

    # an agent never restores on its own, even where it could read
    assert fc.get("/v1/files/versions", params={"root": "shared", "path": "/list.txt"}, headers=AGENT).status_code == 403
    r = restore(fc, AGENT, "shared", "/list.txt", YESTERDAY)
    assert r.status_code == 403 and r.json()["reason"] == "people_only"
    # Homes stay private, even from the owner
    assert fc.get("/v1/files/versions", params={"root": "home:adult", "path": "/diary.txt"}, headers=OWNER).status_code == 403
    assert restore(fc, OWNER, "home:adult", "/diary.txt", YESTERDAY).status_code == 403
    # a guest may look at Shared's versions but not write a copy into it
    assert [v["size"] for v in versions(fc, GUEST, "shared", "/list.txt")["versions"]] == [4]
    assert restore(fc, GUEST, "shared", "/list.txt", YESTERDAY).status_code == 403
    assert fc.get("/v1/files/versions", params={"root": "shared", "path": "/list.txt"}).status_code == 401


def test_versions_off_bad_input_and_symlinks(fc, files_root, snapshots):
    ok(upload(fc, ADULT, "home:adult", "/", "a.txt", b"a"), 204)
    out = versions(fc, ADULT, "home:adult", "/a.txt")
    assert out["enabled"] is False and out["versions"] == []  # no snapshot directory: versions are off
    st = ok(fc.get("/v1/files/stat", params={"root": "home:adult", "path": "/a.txt"}, headers=ADULT))
    assert st["versions_available"] is False
    assert restore(fc, ADULT, "home:adult", "/a.txt", YESTERDAY).status_code == 404

    capture = snapshot(files_root, snapshots, YESTERDAY)
    (snapshots / "manual-copy").mkdir()
    manual = "snapper-4-20261121T040000Z"
    snapshot(files_root, snapshots, manual, cleanup="number")
    assert restore(fc, ADULT, "home:adult", "/a.txt", manual).status_code == 404
    assert versions(fc, ADULT, "home:adult", "/a.txt")["versions"] == []  # equal to today's copy
    assert restore(fc, ADULT, "home:adult", "/a.txt", "manual-copy").status_code == 422
    assert restore(fc, ADULT, "home:adult", "/a.txt", "snapper-3-20261120T030000Z").status_code == 404
    assert fc.get("/v1/files/versions", params={"root": "home:adult", "path": "/"}, headers=ADULT).status_code == 409

    # a symlink inside a snapshot is never followed out of the space
    space = next((capture / "home").iterdir())
    os.symlink("/etc/passwd", space / "link.txt")
    assert versions(fc, ADULT, "home:adult", "/link.txt")["versions"] == []
    r = restore(fc, ADULT, "home:adult", "/link.txt", YESTERDAY)
    assert r.status_code in (403, 409)
    names = [e["name"] for e in ok(fc.get("/v1/files/list", params={"root": "home:adult"}, headers=ADULT))]
    assert names == ["a.txt"]

def test_household_sessions_reach_files_permissions(fc, files_root, snapshots):
    ok(upload(fc, OWNER, "shared", "/", "notes.txt", b"yesterday"), 204)
    version = YESTERDAY
    if os.environ.get("ONEMIND_TEST_SNAPPER_TIMELINE"):
        os.chown(files_root / "shared", 961, 961)
        os.chown(files_root / "shared/notes.txt", 961, 961)
        # This is the ExecStart of the Debian image's scheduled service.
        subprocess.run(["/usr/lib/snapper/systemd-helper", "--timeline"], check=True)
        entry, = (path for path in snapshots.iterdir() if path.name.isdecimal())
        metadata = ElementTree.parse(entry / "info.xml")
        assert metadata.findtext("cleanup") == "timeline"
        subvolume = entry / "snapshot"
        assert subprocess.check_output(["btrfs", "property", "get", "-ts", subvolume, "ro"]).strip() == b"ro=true"
        info = entry / "info.xml"
        capture = snapshots / ".files" / f"{entry.name}-{info.stat().st_ino}"
        assert capture.with_suffix(".info").samefile(info)
        assert subprocess.check_output(["btrfs", "property", "get", "-ts", capture, "ro"]).strip() == b"ro=true"
        content = subprocess.check_output(["runuser", "-u", "onemind", "--", "cat", capture / "shared/notes.txt"])
        assert content == b"yesterday"
        taken = datetime.strptime(metadata.findtext("date"), "%Y-%m-%d %H:%M:%S")
        version = f"snapper-{entry.name}-{taken:%Y%m%dT%H%M%SZ}"
    else:
        snapshot(files_root, snapshots, version)
    ok(upload(fc, OWNER, "shared", "/", "notes.txt", b"today", overwrite=True), 204)
    setup_owner(fc)
    adult = None
    for role in ("adult", "guest", "child", "teen"):
        member = enrol(fc, role, f"member-{role}")
        if role == "adult":
            adult = member
        params = {"root": "shared", "path": "/notes.txt"}
        ok(member.get("/v1/files/roots"))
        ok(member.get("/v1/files/list", params={"root": "shared"}))
        ok(member.get("/v1/files/preview", params=params))
        assert versions(member, {}, **params)["versions"][0]["version"] == version
        assert member.get("/v1/files/versions", params={"root": "home:adult", "path": "/notes.txt"}).status_code == 403
        if role != "adult":
            assert restore(member, csrf(member), "shared", "/notes.txt", version).status_code == 403
    assert adult is not None
    copy = ok(restore(adult, csrf(adult), "shared", "/notes.txt", version))
    assert read(adult, {}, "shared", copy["path"]) == b"yesterday"
    assert read(adult, {}, "shared", "/notes.txt") == b"today"
    token = ok(adult.post("/v1/tokens", headers=csrf(adult),
                          json={"name": "status only", "scopes": ["instance:read"]}), 201)["one_time"]["token"]
    with_token = {"Authorization": f"Bearer {token}"}
    assert adult.get("/v1/files/versions", headers=with_token, params=params).status_code == 403
    assert restore(adult, with_token, "shared", "/notes.txt", version).status_code == 403
    assert fc.app.openapi()["paths"]["/v1/files/versions"]["get"]["security"] == [{"bearer": ["files:read"]}]


def test_equal_size_and_mtime_do_not_hide_distinct_versions(fc, files_root, snapshots):
    root = "shared"
    ok(upload(fc, ADULT, root, "/", "note.txt", b"one"), 204)
    live = files_root / "shared" / "note.txt"
    timestamp = live.stat().st_mtime_ns
    snapshot(files_root, snapshots, EARLIER)
    live.write_bytes(b"two")
    os.utime(live, ns=(timestamp, timestamp))
    snapshot(files_root, snapshots, YESTERDAY)
    live.write_bytes(b"now")
    os.utime(live, ns=(timestamp, timestamp))

    assert [v["version"] for v in versions(fc, ADULT, root, "/note.txt")["versions"]] == [YESTERDAY, EARLIER]
    for name, version, data in [("two", YESTERDAY, b"two"), ("one", EARLIER, b"one")]:
        entry = ok(restore(fc, ADULT, root, "/note.txt", version, to_path=f"/{name}.txt"))
        assert read(fc, ADULT, root, entry["path"]) == data


def test_impossible_date_has_structured_validation_error(fc):
    r = restore(fc, ADULT, "shared", "/note.txt", "snapper-2-20260230T030000Z")
    assert r.status_code == 422 and r.json()["reason"] == "invalid_version"


def test_reused_snapper_number_never_exposes_the_deleted_snapshot(fc, files_root, snapshots):
    ok(upload(fc, ADULT, "shared", "/", "note.txt", b"old"), 204)
    snapshot(files_root, snapshots, YESTERDAY)
    # An old slot can expire a storage snapshot while its Files capture survives.
    (snapshots / "2").rename(snapshots / "retired")
    (snapshots / "2").mkdir()
    shutil.copyfile(snapshots / "retired/info.xml", snapshots / "2/info.xml")
    ok(upload(fc, ADULT, "shared", "/", "note.txt", b"new", overwrite=True), 204)
    assert versions(fc, ADULT, "shared", "/note.txt")["versions"] == []
    assert restore(fc, ADULT, "shared", "/note.txt", YESTERDAY).status_code == 404


def test_restore_requires_explicit_destination_when_parent_is_missing(fc, files_root, snapshots):
    mkdir(fc, ADULT, "shared", "/gone")
    ok(upload(fc, ADULT, "shared", "/gone", "notes.txt", b"yesterday"), 204)
    snapshot(files_root, snapshots, YESTERDAY)
    ok(fc.post("/v1/files/ops", headers=ADULT, json={"op": "trash", "root": "shared", "path": "/gone"}))
    assert versions(fc, ADULT, "shared", "/gone/notes.txt")["versions"][0]["version"] == YESTERDAY
    r = restore(fc, ADULT, "shared", "/gone/notes.txt", YESTERDAY)
    assert r.status_code == 404 and "choose a destination path" in r.json()["message"]
    entry = ok(restore(fc, ADULT, "shared", "/gone/notes.txt", YESTERDAY, to_path="/notes.txt"))
    assert read(fc, ADULT, "shared", entry["path"]) == b"yesterday"


@pytest.mark.parametrize("race,expected", [("name", "exists"), ("quota", "quota_exceeded")])
def test_restore_rechecks_after_unlocked_copy(fc, files_root, snapshots, monkeypatch, race, expected):
    svc = fc.app.state.files_service
    ok(upload(fc, ADULT, "shared", "/", "notes.txt", b"old"), 204)
    snapshot(files_root, snapshots, YESTERDAY)
    if race == "quota":
        monkeypatch.setattr(svc, "limit", lambda root: 6)
    synced, release = Event(), Event()
    copy = svc.versions._copy

    def pause_after_fsync(*args):
        copy(*args)
        synced.set()
        assert release.wait(10)

    monkeypatch.setattr(svc.versions, "_copy", pause_after_fsync)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(restore, fc, ADULT, "shared", "/notes.txt", YESTERDAY, to_path="/restored.txt")
        try:
            assert synced.wait(5)
            if race == "name":
                edit = pool.submit(mkdir, fc, ADULT, "shared", "/restored.txt")
            else:
                edit = pool.submit(upload, fc, ADULT, "shared", "/", "extra.txt", b"new")
            edit.result(timeout=5)
        finally:
            release.set()
        result = pending.result(timeout=5)
    assert result.status_code == (409 if race == "name" else 413)
    assert result.json()["reason"] == expected
    assert list((files_root / ".system" / "restore").iterdir()) == []


def test_concurrent_restores_reserve_space_before_copying(fc, files_root, snapshots, monkeypatch):
    svc = fc.app.state.files_service
    ok(upload(fc, ADULT, "shared", "/", "notes.txt", b"old"), 204)
    snapshot(files_root, snapshots, YESTERDAY)
    # Both 3-byte copies fit individually, but together would eat into the disk reserve.
    monkeypatch.setattr(svc, "free_bytes", lambda: svc.settings.min_free_bytes + 5)
    started, release = Event(), Event()
    copy = svc.versions._copy

    def pause_first_copy(*args):
        if not started.is_set():
            started.set()
            assert release.wait(10)
        copy(*args)

    monkeypatch.setattr(svc.versions, "_copy", pause_first_copy)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(restore, fc, ADULT, "shared", "/notes.txt", YESTERDAY, to_path="/first.txt")
        try:
            assert started.wait(5)
            second = pool.submit(restore, fc, ADULT, "shared", "/notes.txt", YESTERDAY, to_path="/second.txt")
            rejected = second.result(timeout=5)
            assert rejected.status_code == 413 and rejected.json()["reason"] == "insufficient_space"
            assert not (files_root / "shared" / "second.txt").exists()
        finally:
            release.set()
        ok(first.result(timeout=5))
    # There is room for another copy once the reservation is released.
    ok(restore(fc, ADULT, "shared", "/notes.txt", YESTERDAY, to_path="/second.txt"))


@pytest.fixture
def abandoned_restores(files_root):
    work = files_root / ".system" / "restore"
    work.mkdir(parents=True)
    (work / new_id("rst")).write_bytes(b"interrupted copy")
    live = files_root / "shared" / "published.txt"
    live.parent.mkdir()
    live.write_bytes(b"published copy")
    os.link(live, work / new_id("rst"))
    (work / "unrelated").write_bytes(b"keep")
    return work


def test_gateway_recovers_abandoned_restore_stages_at_startup(abandoned_restores, fc):
    assert sorted(p.name for p in abandoned_restores.iterdir()) == ["unrelated"]
    assert read(fc, ADULT, "shared", "/published.txt") == b"published copy"
