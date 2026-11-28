# SPDX-License-Identifier: Apache-2.0
"""Sync index (#698): stable file ids, revisions, hashes, GET /v1/sync/changes and the wake-up."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import time
from datetime import timedelta

import pytest

from onemind_core import eventstream
from onemind_core.auth import Principal
from onemind_core.eventstream import EventStream
from onemind_core.files.watch import Inotify

from files_support import ADULT, AGENT, GUEST, OWNER, fc, files_root, files_settings, mkdir, ok, rename, upload  # noqa: F401


def feed(c, headers, root, cursor=None, limit=None, status=200):
    params = {"root": root}
    if cursor:
        params["cursor"] = cursor
    if limit:
        params["limit"] = limit
    r = c.get("/v1/sync/changes", params=params, headers=headers)
    assert r.status_code == status, r.text
    return r.json()


def watcher(c):
    return c.app.state.files_index_watcher


def test_api_writes_smb_writes_and_a_folder_rename_give_one_change_per_file_with_the_same_id(fc, files_root):
    mkdir(fc, OWNER, "shared", "/Docs")
    ok(upload(fc, OWNER, "shared", "/Docs", "api.txt", b"written through the API\n"), 204)
    first = feed(fc, OWNER, "shared")
    assert first["has_more"] is False
    by_path = {e["path"]: e for e in first["changes"]}
    assert set(by_path) == {"/Docs", "/Docs/api.txt"}
    api = by_path["/Docs/api.txt"]
    assert api["hash"] == "sha256:" + hashlib.sha256(b"written through the API\n").hexdigest()
    assert api["parent_id"] == by_path["/Docs"]["id"] and api["size"] == 24

    # A write over SMB lands on disk without the API; the scanner (or inotify) picks it up.
    (files_root / "shared" / "Docs" / "smb.txt").write_bytes(b"written over SMB\n")
    watcher(fc).scan()
    after_smb = feed(fc, OWNER, "shared", first["next_cursor"])
    assert [(e["path"], e["deleted"]) for e in after_smb["changes"]] == [("/Docs/smb.txt", False)]
    smb = after_smb["changes"][0]
    assert smb["hash"] == "sha256:" + hashlib.sha256(b"written over SMB\n").hexdigest()

    # Rename the folder through the API: each entry appears once, keeping its id.
    rename(fc, OWNER, "shared", "/Docs", "Papers")
    watcher(fc).scan()  # the scanner sees nothing new: no second change for any file
    renamed = feed(fc, OWNER, "shared", after_smb["next_cursor"])
    got = {e["id"]: e["path"] for e in renamed["changes"]}
    assert got == {by_path["/Docs"]["id"]: "/Papers", api["id"]: "/Papers/api.txt", smb["id"]: "/Papers/smb.txt"}
    assert len(renamed["changes"]) == 3 and not any(e["deleted"] for e in renamed["changes"])

    # A rename made over SMB is followed by inode, so the ids survive it too.
    os.rename(files_root / "shared" / "Papers", files_root / "shared" / "Archive")
    watcher(fc).scan()
    moved = feed(fc, OWNER, "shared", renamed["next_cursor"])
    assert {e["id"]: e["path"] for e in moved["changes"]} == {
        by_path["/Docs"]["id"]: "/Archive", api["id"]: "/Archive/api.txt", smb["id"]: "/Archive/smb.txt"}
    # Nothing changed since: an empty page and the same revision.
    again = feed(fc, OWNER, "shared", moved["next_cursor"])
    assert again["changes"] == [] and again["revision"] == moved["revision"]


def test_stat_and_list_carry_id_revision_and_hash(fc):
    mkdir(fc, ADULT, "home:adult", "/A")
    ok(upload(fc, ADULT, "home:adult", "/A", "n.txt", b"abc"), 204)
    items = ok(fc.get("/v1/files/list", params={"root": "home:adult", "path": "/A"}, headers=ADULT))
    st = ok(fc.get("/v1/files/stat", params={"root": "home:adult", "path": "/A/n.txt"}, headers=ADULT))
    assert items[0]["id"] == st["id"] and st["id"].startswith("fil_")
    assert st["hash"] == "sha256:" + hashlib.sha256(b"abc").hexdigest() and st["revision"] >= 1
    top = ok(fc.get("/v1/files/stat", params={"root": "home:adult", "path": "/"}, headers=ADULT))
    assert top["id"] is None and top["revision"] == feed(fc, ADULT, "home:adult")["revision"]
    # Replacing the file by an upload keeps its id and gives a new revision and hash.
    ok(upload(fc, ADULT, "home:adult", "/A", "n.txt", b"abcd", overwrite=True), 204)
    st2 = ok(fc.get("/v1/files/stat", params={"root": "home:adult", "path": "/A/n.txt"}, headers=ADULT))
    assert st2["id"] == st["id"] and st2["revision"] > st["revision"] and st2["hash"] != st["hash"]


def test_trash_is_a_deletion_in_the_feed_and_a_restore_comes_back(fc):
    ok(upload(fc, OWNER, "shared", "/", "gone.txt", b"bye"), 204)
    start = feed(fc, OWNER, "shared")
    fid = start["changes"][0]["id"]
    trashed = ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "shared", "path": "/gone.txt"}))
    page = feed(fc, OWNER, "shared", start["next_cursor"])
    assert [(e["id"], e["deleted"]) for e in page["changes"]] == [(fid, True)]
    assert feed(fc, OWNER, "shared")["changes"] == []  # a fresh listing has no tombstones
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "restore_trash", "trash_id": trashed["id"]}))
    back = feed(fc, OWNER, "shared", page["next_cursor"])
    assert [(e["path"], e["deleted"]) for e in back["changes"]] == [("/gone.txt", False)]


def test_paging_returns_every_entry_once(fc):
    for i in range(5):
        ok(upload(fc, OWNER, "home:owner", "/", f"f{i}.txt", str(i).encode()), 204)
    seen, cursor = [], None
    while True:
        page = feed(fc, OWNER, "home:owner", cursor, limit=2)
        seen += [e["path"] for e in page["changes"]]
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    assert sorted(seen) == [f"/f{i}.txt" for i in range(5)]


def test_refuses_unreadable_roots_foreign_cursors_and_never_shows_host_paths(fc, files_root):
    mkdir(fc, ADULT, "home:adult", "/Diary")
    assert fc.get("/v1/sync/changes", params={"root": "home:adult"}, headers=OWNER).status_code == 403
    assert fc.get("/v1/sync/changes", params={"root": "shared"}, headers=AGENT).status_code == 403
    assert fc.get("/v1/sync/changes", params={"root": "shared"}).status_code == 401
    mine = feed(fc, ADULT, "home:adult")
    shared = feed(fc, ADULT, "shared")
    # A cursor from another root, or one issued to another person, is refused.
    r = fc.get("/v1/sync/changes", params={"root": "shared", "cursor": mine["next_cursor"]}, headers=ADULT)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_cursor"
    r = fc.get("/v1/sync/changes", params={"root": "shared", "cursor": shared["next_cursor"]}, headers=GUEST)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_cursor"
    assert fc.get("/v1/sync/changes", params={"root": "shared", "cursor": "AAAA"}, headers=ADULT).status_code == 422
    body = fc.get("/v1/sync/changes", params={"root": "home:adult"}, headers=ADULT).text
    assert str(files_root) not in body and "/home/" not in body


def test_a_cursor_older_than_the_pruned_deletions_gets_410(fc):
    ok(upload(fc, OWNER, "shared", "/", "x.txt", b"x"), 204)
    old = feed(fc, OWNER, "shared")["next_cursor"]
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "shared", "path": "/x.txt"}))
    index = watcher(fc).files.index
    assert index.prune("shared", timedelta(0)) == 1
    r = fc.get("/v1/sync/changes", params={"root": "shared", "cursor": old}, headers=OWNER)
    assert r.status_code == 410 and r.json()["reason"] == "cursor_expired"
    assert feed(fc, OWNER, "shared")["changes"] == []  # starting over works


def test_root_changed_wake_up_is_bounded_and_carries_no_changes(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(eventstream, "ROOT_POLL_S", 0.0)  # poll the roots on every loop
    revs = {"shared": 3}
    audit = tmp_path / "audit.jsonl"
    audit.write_text("")
    stream = EventStream(audit, lambda: [], lambda _id: set(), clock, root_revisions=lambda p: dict(revs))
    p = Principal("adult", "person", "adult")

    async def collect() -> list[bytes]:
        out: list[bytes] = []
        n = {"i": 0}

        async def gone():
            n["i"] += 1
            if n["i"] == 3:
                revs["shared"] = 9  # several changes between two polls: one wake-up
            return n["i"] > 8

        async for chunk in stream.stream(p, "sync.*", None, gone, poll_s=0.01, keepalive_s=60):
            out.append(chunk)
        return out

    chunks = asyncio.run(collect())
    wakes = [c for c in chunks if b"sync.root_changed" in c]
    assert len(wakes) == 1 and b'"revision":9' in wakes[0] and b'"root":"shared"' in wakes[0]
    assert b"id: " not in wakes[0] and b"path" not in wakes[0]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="inotify is Linux only")
def test_inotify_watcher_indexes_a_write_made_outside_the_api(fc, files_root):
    mkdir(fc, OWNER, "shared", "/In")
    start = feed(fc, OWNER, "shared")
    w = watcher(fc)
    w.stop()
    w.start()  # starts with a full scan, which puts a watch on every folder that now exists
    assert isinstance(w.inotify, Inotify)
    deadline = time.monotonic() + 3
    while not w.inotify.roots and time.monotonic() < deadline:
        time.sleep(0.05)
    assert w.inotify.roots, "the start scan put no watches"
    (files_root / "shared" / "In" / "dav.txt").write_bytes(b"from WebDAV")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        got = feed(fc, OWNER, "shared", start["next_cursor"])["changes"]
        if got:
            break
        time.sleep(0.2)
    assert [e["path"] for e in got] == ["/In/dav.txt"]
