# SPDX-License-Identifier: Apache-2.0
"""FILES: spaces, roles, browse, preview, download with ranges, moves, trash, quotas, audit."""

from __future__ import annotations

import os
import struct
import sys
from datetime import timedelta

import pytest

from onemind_core.auth import Principal
from onemind_core.files.access import READ, READ_WRITE, NONE, Root, person_access

from files_support import ADULT, AGENT, GUEST, OWNER, audit_events, fc, files_root, files_settings, mkdir, ok, upload  # noqa: F401


def test_roles_map_to_space_access():
    kid = Principal("kid", "person", "child")
    assert person_access(kid, Root("home", "kid")) == READ_WRITE
    assert person_access(kid, Root("shared", None)) == READ
    assert person_access(Principal("g", "person", "guest"), Root("shared", None)) == READ
    assert person_access(Principal("g", "person", "guest"), Root("home", "g")) == NONE
    assert person_access(Principal("x", "person", "superhero"), Root("shared", None)) == NONE
    assert person_access(Principal("owner", "person", "owner"), Root("home", "adult")) == NONE
    assert person_access(Principal("hermes", "agent", "agent"), Root("shared", None)) == NONE


def test_roots_per_role(fc):
    owner = {r["root"]: r for r in ok(fc.get("/v1/files/roots", headers=OWNER))}
    assert set(owner) == {"home:owner", "shared"}
    assert owner["home:owner"]["access"] == "rw" and owner["home:owner"]["quota_bytes"] is None
    assert {r["root"]: r["access"] for r in ok(fc.get("/v1/files/roots", headers=GUEST))} == {"shared": "r"}
    assert ok(fc.get("/v1/files/roots", headers=AGENT)) == []
    assert fc.get("/v1/files/roots").status_code == 401


def test_homes_are_private_even_from_the_owner(fc):
    mkdir(fc, ADULT, "home:adult", "/Diary")
    r = fc.get("/v1/files/list", params={"root": "home:adult", "path": "/"}, headers=OWNER)
    assert r.status_code == 403 and r.json()["error"] == "permission_denied"
    assert fc.get("/v1/files/list", params={"root": "home:owner"}, headers=ADULT).status_code == 403
    assert fc.post("/v1/files/ops", headers=GUEST, json={"op": "mkdir", "root": "shared", "path": "/x"}).status_code == 403
    assert fc.get("/v1/files/list", params={"root": "shared"}, headers=GUEST).status_code == 200


def test_browse_stat_preview_download_and_ranges(fc):
    mkdir(fc, OWNER, "home:owner", "/Docs")
    ok(upload(fc, OWNER, "home:owner", "/Docs", "notes.txt", b"hello files\n"), 204)
    png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 640, 480) + b"\x08\x02\x00\x00\x00"
    ok(upload(fc, OWNER, "home:owner", "/Docs", "pic.png", png), 204)
    items = ok(fc.get("/v1/files/list", params={"root": "home:owner", "path": "/"}, headers=OWNER))
    assert [(i["name"], i["type"]) for i in items] == [("Docs", "dir")]
    items = ok(fc.get("/v1/files/list", params={"root": "home:owner", "path": "/Docs"}, headers=OWNER))
    assert [i["name"] for i in items] == ["notes.txt", "pic.png"]
    st = ok(fc.get("/v1/files/stat", params={"root": "home:owner", "path": "/Docs/notes.txt"}, headers=OWNER))
    assert st["size"] == 12 and st["type"] == "file" and st["mime"] == "text/plain" and st["path"] == "/Docs/notes.txt"
    pv = ok(fc.get("/v1/files/preview", params={"root": "home:owner", "path": "Docs/notes.txt"}, headers=OWNER))
    assert pv["kind"] == "text" and pv["text"] == {"excerpt": "hello files\n", "truncated": False}
    pv = ok(fc.get("/v1/files/preview", params={"root": "home:owner", "path": "Docs/pic.png"}, headers=OWNER))
    assert pv["image"] == {"width": 640, "height": 480} and pv["inline_safe"] is True

    q = {"root": "home:owner", "path": "/Docs/notes.txt"}
    r = fc.get("/v1/files/download", params=q, headers=OWNER)
    assert r.status_code == 200 and r.content == b"hello files\n"
    assert r.headers["accept-ranges"] == "bytes" and r.headers["content-type"] == "application/octet-stream"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert "sandbox" in r.headers["content-security-policy"]
    etag = r.headers["etag"]
    r = fc.get("/v1/files/download", params=q, headers={**OWNER, "Range": "bytes=6-"})
    assert r.status_code == 206 and r.content == b"files\n" and r.headers["content-range"] == "bytes 6-11/12"
    r = fc.get("/v1/files/download", params=q, headers={**OWNER, "Range": "bytes=-3"})
    assert r.status_code == 206 and r.content == b"es\n"
    r = fc.get("/v1/files/download", params=q, headers={**OWNER, "Range": "bytes=0-4", "If-Range": etag})
    assert r.status_code == 206 and r.content == b"hello"
    r = fc.get("/v1/files/download", params=q, headers={**OWNER, "Range": "bytes=0-4", "If-Range": '"stale"'})
    assert r.status_code == 200 and r.content == b"hello files\n"
    r = fc.get("/v1/files/download", params=q, headers={**OWNER, "Range": "bytes=50-"})
    assert r.status_code == 416 and r.headers["content-range"] == "bytes */12"
    r = fc.get("/v1/files/download", params={**q, "inline": "true"}, headers=OWNER)
    assert r.headers["content-type"].startswith("text/plain") and r.headers["content-disposition"].startswith("inline;")
    assert fc.get("/v1/files/download", params={"root": "home:owner", "path": "/Docs"}, headers=OWNER).status_code == 409


def test_invalid_paths_are_refused(fc):
    for bad in ("../etc", "/a/../../b", "a/./b", "a\\b", "a\x00b", "x" * 300):
        r = fc.get("/v1/files/list", params={"root": "home:owner", "path": bad}, headers=OWNER)
        assert r.status_code == 422 and r.json()["reason"] == "invalid_path", bad
    r = fc.get("/v1/files/list", params={"root": "../../etc"}, headers=OWNER)
    assert r.status_code == 422 and r.json()["reason"] == "invalid_root"


def test_symlinks_are_never_followed(fc, files_root, tmp_path):
    mkdir(fc, OWNER, "home:owner", "/a")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("do not read")
    home = next((files_root / "home").iterdir())
    (home / "a" / "escape").symlink_to(outside)
    (home / "a" / "link.txt").symlink_to(outside / "secret.txt")
    r = fc.get("/v1/files/list", params={"root": "home:owner", "path": "/a/escape"}, headers=OWNER)
    assert r.status_code == 403 and r.json()["reason"] == "symlink"
    r = fc.get("/v1/files/download", params={"root": "home:owner", "path": "/a/link.txt"}, headers=OWNER)
    assert r.status_code == 403
    listed = ok(fc.get("/v1/files/list", params={"root": "home:owner", "path": "/a"}, headers=OWNER))
    assert {i["name"]: i["type"] for i in listed} == {"escape": "symlink", "link.txt": "symlink"}
    r = fc.post("/v1/files/ops", headers=OWNER, json={"op": "mkdir", "root": "home:owner", "path": "/a/escape/new"})
    assert r.status_code == 403 and not (outside / "new").exists()


def test_move_rename_and_conflicts(fc):
    mkdir(fc, OWNER, "home:owner", "/a")
    mkdir(fc, OWNER, "home:owner", "/b")
    ok(upload(fc, OWNER, "home:owner", "/a", "f.txt", b"x"), 204)
    moved = ok(fc.post("/v1/files/ops", headers=OWNER, json={
        "op": "move", "root": "home:owner", "path": "/a/f.txt", "to_path": "/b/f.txt"}))
    assert moved["path"] == "/b/f.txt"
    renamed = ok(fc.post("/v1/files/ops", headers=OWNER, json={
        "op": "rename", "root": "home:owner", "path": "/b/f.txt", "name": "g.txt"}))
    assert renamed["path"] == "/b/g.txt"
    r = fc.post("/v1/files/ops", headers=OWNER, json={"op": "move", "root": "home:owner", "path": "/a", "to_path": "/a/inner"})
    assert r.status_code == 409 and r.json()["reason"] == "into_itself"
    r = fc.post("/v1/files/ops", headers=OWNER, json={"op": "move", "root": "home:owner", "path": "/a", "to_path": "/b"})
    assert r.status_code == 409 and r.json()["reason"] == "exists"
    r = fc.post("/v1/files/ops", headers=OWNER, json={"op": "mkdir", "root": "home:owner", "path": "/a"})
    assert r.status_code == 409
    # to Shared, then the adult may see it
    ok(fc.post("/v1/files/ops", headers=OWNER, json={
        "op": "move", "root": "home:owner", "path": "/b/g.txt", "to_root": "shared", "to_path": "/g.txt"}))
    assert [i["name"] for i in ok(fc.get("/v1/files/list", params={"root": "shared"}, headers=ADULT))] == ["g.txt"]


def test_trash_restore_and_shared_trash(fc, clock):
    mkdir(fc, OWNER, "home:owner", "/keep")
    ok(upload(fc, OWNER, "home:owner", "/keep", "a.txt", b"abc"), 204)
    item = ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "home:owner", "path": "/keep"}))
    assert item["type"] == "dir" and item["size"] == 3 and item["trash"] == "home"
    assert ok(fc.get("/v1/files/list", params={"root": "home:owner"}, headers=OWNER)) == []
    assert [t["id"] for t in ok(fc.get("/v1/files/trash", headers=OWNER))] == [item["id"]]
    assert ok(fc.get("/v1/files/trash", headers=ADULT)) == []
    r = fc.post("/v1/files/ops", headers=ADULT, json={"op": "restore_trash", "trash_id": item["id"]})
    assert r.status_code == 404  # not their trash
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "restore_trash", "trash_id": item["id"]}))
    r = fc.get("/v1/files/download", params={"root": "home:owner", "path": "/keep/a.txt"}, headers=OWNER)
    assert r.content == b"abc"
    assert ok(fc.get("/v1/files/trash", headers=OWNER)) == []

    ok(upload(fc, OWNER, "shared", "/", "s.txt", b"s"), 204)
    shared_item = ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "shared", "path": "/s.txt"}))
    assert shared_item["trash"] == "shared"
    assert [t["id"] for t in ok(fc.get("/v1/files/trash", params={"trash": "shared"}, headers=ADULT))] == [shared_item["id"]]
    assert fc.get("/v1/files/trash", params={"trash": "shared"}, headers=GUEST).status_code == 403
    assert fc.get("/v1/files/trash", headers=GUEST).status_code == 403  # a guest has no Home and no trash

    # retention: purged after 30 days
    clock.advance(timedelta(days=31).total_seconds())
    assert ok(fc.get("/v1/files/trash", params={"trash": "shared"}, headers=ADULT)) == []


def test_trash_empty_needs_owner_approval(fc):
    ok(upload(fc, ADULT, "home:adult", "/", "old.bin", b"0" * 100), 204)
    ok(fc.post("/v1/files/ops", headers=ADULT, json={"op": "trash", "root": "home:adult", "path": "/old.bin"}))
    r = fc.post("/v1/files/trash/empty", headers=ADULT, json={"reason": "need space"})
    assert r.status_code == 202 and r.headers["location"].startswith("/v1/files/requests/frq_")
    req = r.json()
    assert req["state"] == "awaiting_approval" and req["risk"] == "destructive" and req["plan"]["items"] == 1
    assert fc.post(f"/v1/files/requests/{req['id']}/approve", headers=ADULT).status_code == 403
    assert len(ok(fc.get("/v1/files/trash", headers=ADULT))) == 1
    done = ok(fc.post(f"/v1/files/requests/{req['id']}/approve", headers=OWNER))
    assert done["state"] == "succeeded" and done["result"] == {"items": 1, "bytes": 100} and done["approved_by"] == "owner"
    assert ok(fc.get("/v1/files/trash", headers=ADULT)) == []
    # the owner may file and approve their own in one step
    ok(upload(fc, OWNER, "home:owner", "/", "x", b"1"), 204)
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "home:owner", "path": "/x"}))
    r = fc.post("/v1/files/trash/empty", headers=OWNER, json={"approve": True})
    assert r.status_code == 202 and r.json()["state"] == "succeeded"


def test_quotas(fc):
    assert fc.put("/v1/files/quotas/adult", headers=ADULT, json={"limit_bytes": 10}).status_code == 403
    q = ok(fc.put("/v1/files/quotas/adult", headers=OWNER, json={"limit_bytes": 10}))
    assert q == {"person_id": "adult", "root": "home:adult", "limit_bytes": 10, "used_bytes": 0}
    ok(upload(fc, ADULT, "home:adult", "/", "a", b"12345678"), 204)
    r = fc.post("/v1/files/uploads", headers={**ADULT, "Tus-Resumable": "1.0.0", "Upload-Length": "5",
                                              "Upload-Metadata": "root aG9tZTphZHVsdA==,filename Yg=="})
    assert r.status_code == 413 and r.json()["reason"] == "quota_exceeded"
    # trashed bytes still count until purged
    ok(fc.post("/v1/files/ops", headers=ADULT, json={"op": "trash", "root": "home:adult", "path": "/a"}))
    roots = {x["root"]: x for x in ok(fc.get("/v1/files/roots", headers=ADULT))}
    assert roots["home:adult"]["used_bytes"] == 8 and roots["home:adult"]["quota_bytes"] == 10
    # moving into a full Home is refused too
    ok(upload(fc, ADULT, "shared", "/", "big", b"x" * 5), 204)
    r = fc.post("/v1/files/ops", headers=ADULT, json={"op": "move", "root": "shared", "path": "/big",
                                                      "to_root": "home:adult", "to_path": "/big"})
    assert r.status_code == 413
    rows = {x["root"]: x for x in ok(fc.get("/v1/files/quotas", headers=OWNER))}
    assert rows["home:adult"]["limit_bytes"] == 10 and rows["shared"]["used_bytes"] == 5


def test_pagination_link_header(fc):
    for i in range(5):
        mkdir(fc, OWNER, "home:owner", f"/d{i}")
    r = fc.get("/v1/files/list", params={"root": "home:owner", "limit": 2}, headers=OWNER)
    assert [i["name"] for i in r.json()] == ["d0", "d1"] and 'rel="next"' in r.headers["link"]
    nxt = r.headers["link"].split(">")[0][1:]
    r2 = fc.get(nxt, headers=OWNER)
    assert [i["name"] for i in r2.json()] == ["d2", "d3"]
    r3 = fc.get(r2.headers["link"].split(">")[0][1:], headers=OWNER)
    assert [i["name"] for i in r3.json()] == ["d4"] and "link" not in r3.headers


def test_every_write_is_audited(fc, settings):
    mkdir(fc, OWNER, "home:owner", "/a")
    ok(upload(fc, OWNER, "home:owner", "/a", "f", b"1"), 204)
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "rename", "root": "home:owner", "path": "/a/f", "name": "g"}))
    ok(fc.post("/v1/files/ops", headers=OWNER, json={"op": "trash", "root": "home:owner", "path": "/a/g"}))
    fc.get("/v1/files/list", params={"root": "home:adult"}, headers=OWNER)
    events = [e["event"] for e in audit_events(settings)]
    for name in ("files.folder.created", "files.upload.created", "files.upload.completed", "files.renamed",
                 "files.trashed", "authz.denied"):
        assert name in events, name
    created = next(e for e in audit_events(settings) if e["event"] == "files.folder.created")
    assert created["principal"]["id"] == "owner" and created["data"]["payload"]["path"] == "/a"
    assert "files.read" not in events  # person reads are not audited, agent reads are


def test_openapi_lists_files_routes(fc):
    paths = fc.get("/openapi.json").json()["paths"]
    for p in ("/v1/files/roots", "/v1/files/list", "/v1/files/download", "/v1/files/uploads",
              "/v1/files/uploads/{upload_id}", "/v1/files/grants", "/v1/files/requests/{request_id}/approve"):
        assert p in paths, p


def test_ranges_on_an_empty_file_and_bad_cursors(fc):
    ok(upload(fc, OWNER, "home:owner", "/", "empty", b""), 201)
    q = {"root": "home:owner", "path": "/empty"}
    r = fc.get("/v1/files/download", params=q, headers={**OWNER, "Range": "bytes=-5"})
    assert r.status_code == 200 and r.content == b"" and "content-range" not in r.headers
    r = fc.get("/v1/files/download", params=q, headers={**OWNER, "Range": "bytes=0-"})
    assert r.status_code == 416 and r.headers["content-range"] == "bytes */0"
    for bad in ("bzotMQ", "!!", "bzp4"):  # "o:-1", not base64, "o:x"
        r = fc.get("/v1/files/list", params={"root": "home:owner", "cursor": bad}, headers=OWNER)
        assert r.status_code == 422 and r.json()["reason"] == "invalid_cursor", bad


@pytest.mark.skipif(sys.platform == "darwin", reason="APFS refuses file names that are not UTF-8")
def test_names_that_are_not_utf8_do_not_break_a_listing(fc, files_root):
    mkdir(fc, OWNER, "home:owner", "/mixed")
    folder = next((files_root / "home").iterdir()) / "mixed"
    os.close(os.open(os.fsencode(folder) + b"/bad-\xff-name", os.O_CREAT | os.O_WRONLY, 0o600))
    (folder / "good.txt").write_text("ok")
    items = ok(fc.get("/v1/files/list", params={"root": "home:owner", "path": "/mixed"}, headers=OWNER))
    assert [i["name"] for i in items] == ["good.txt"]
