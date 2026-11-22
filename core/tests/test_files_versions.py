# SPDX-License-Identifier: Apache-2.0
"""FILES previous versions (BAK-04, #241): a member restores yesterday's version of a file.

A btrfs snapshot of the Files root reads like a plain copy of that tree, so these tests stand one in with
shutil.copytree (which keeps sizes and modification times, as a snapshot does). The real snapshot schedule
and its btrfs commands are tested in internal/backup/localsnapshot.
"""

from __future__ import annotations

import os
import shutil

import pytest

from onemind_core.files.settings import FilesSettings

from files_support import ADULT, AGENT, GUEST, OWNER, audit_events, fc, files_root, ok, upload  # noqa: F401

YESTERDAY = "daily-20261121T030000Z"
EARLIER = "hourly-20261121T020000Z"


@pytest.fixture
def snapshots(tmp_path):
    return tmp_path / "snapshots"


@pytest.fixture
def files_settings(files_root, snapshots):
    return FilesSettings(root=files_root, min_free_bytes=0, snapshots_dir=snapshots)


def snapshot(files_root, snapshots, name):
    snapshots.mkdir(exist_ok=True)
    shutil.copytree(files_root, snapshots / name, symlinks=True)


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
    assert [(v["version"], v["cadence"], v["size"]) for v in out["versions"]] == [(YESTERDAY, "daily", 18)]
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

    snapshot(files_root, snapshots, YESTERDAY)
    (snapshots / "manual-copy").mkdir()  # not the scheduler's: ignored
    assert versions(fc, ADULT, "home:adult", "/a.txt")["versions"] == []  # equal to today's copy
    assert restore(fc, ADULT, "home:adult", "/a.txt", "manual-copy").status_code == 422
    assert restore(fc, ADULT, "home:adult", "/a.txt", "daily-20261120T030000Z").status_code == 404
    assert fc.get("/v1/files/versions", params={"root": "home:adult", "path": "/"}, headers=ADULT).status_code == 409

    # a symlink inside a snapshot is never followed out of the space
    space = next((snapshots / YESTERDAY / "home").iterdir())
    os.symlink("/etc/passwd", space / "link.txt")
    assert versions(fc, ADULT, "home:adult", "/link.txt")["versions"] == []
    r = restore(fc, ADULT, "home:adult", "/link.txt", YESTERDAY)
    assert r.status_code in (403, 409)
    names = [e["name"] for e in ok(fc.get("/v1/files/list", params={"root": "home:adult"}, headers=ADULT))]
    assert names == ["a.txt"]
