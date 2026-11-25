# SPDX-License-Identifier: Apache-2.0
"""Advisory sync locks with a time limit (#699): the WebDAV class 2 shape; a commit only warns."""

from __future__ import annotations

from files_support import ADULT, AGENT, GUEST, OWNER, fc, files_root, files_settings, mkdir, ok  # noqa: F401
from test_sync_transfer import blob, sync_up


def lock(c, headers, path, status=201, root="shared", **kw):
    r = c.post("/v1/sync/locks", headers=headers, json={"root": root, "path": path, **kw})
    assert r.status_code == status, r.text
    return r.json()


def test_a_lock_warns_others_until_it_expires_or_is_released(fc, clock):
    mkdir(fc, OWNER, "shared", "/Reports")
    v1 = blob(5000, 1)
    rev = ok(sync_up(fc, OWNER, "shared", "/Reports/q4.xlsx", v1, None))["revision"]

    mine = lock(fc, OWNER, "/Reports/q4.xlsx", ttl_s=60, note="Numbers on the laptop")
    assert mine["id"].startswith("lck_") and mine["holder"] == {"kind": "person", "id": "owner"}
    # someone else may not lock the file, nor the folder around it
    assert lock(fc, ADULT, "/Reports/q4.xlsx", 423)["reason"] == "locked"
    assert lock(fc, ADULT, "/Reports", 423)["reason"] == "locked"
    # the lock is advisory: the adult's commit goes through and names the lock to warn about
    done = ok(sync_up(fc, ADULT, "shared", "/Reports/q4.xlsx", v1 + b"adult", rev))
    assert [lk["id"] for lk in done["locks"]] == [mine["id"]]
    # everyone who reads Shared sees it
    assert [lk["id"] for lk in ok(fc.get("/v1/sync/locks", params={"root": "shared", "path": "/Reports"},
                                        headers=GUEST))["locks"]] == [mine["id"]]

    # only the holder refreshes; a refresh moves the expiry on
    assert fc.post(f"/v1/sync/locks/{mine['id']}/refresh", headers=ADULT, json={}).status_code == 404
    clock.advance(50)
    later = ok(fc.post(f"/v1/sync/locks/{mine['id']}/refresh", headers=OWNER, json={"ttl_s": 60}))
    assert later["expires_at"] > mine["expires_at"]
    clock.advance(50)
    assert lock(fc, ADULT, "/Reports", 423)["reason"] == "locked"
    clock.advance(11)  # expired now: it counts as gone
    assert ok(fc.get("/v1/sync/locks", params={"root": "shared"}, headers=OWNER))["locks"] == []
    theirs = lock(fc, ADULT, "/Reports")
    assert fc.post(f"/v1/sync/locks/{mine['id']}/refresh", headers=OWNER, json={}).status_code == 404

    # the holder or an owner releases; nobody else
    assert fc.delete(f"/v1/sync/locks/{theirs['id']}", headers=GUEST).status_code == 404
    assert fc.delete(f"/v1/sync/locks/{theirs['id']}", headers=OWNER).status_code == 204
    assert ok(fc.get("/v1/sync/locks", params={"root": "shared"}, headers=OWNER))["locks"] == []


def test_who_may_lock(fc):
    mkdir(fc, OWNER, "shared", "/Docs")
    assert lock(fc, GUEST, "/Docs", 403)["error"] == "permission_denied"   # read-only in Shared
    assert lock(fc, AGENT, "/Docs", 403)["error"] == "permission_denied"   # no grant
    assert lock(fc, OWNER, "/nothing-here", 404)["error"] == "not_found"
    assert lock(fc, OWNER, "/", 422)["reason"] == "invalid_path"
    assert lock(fc, ADULT, "/Docs", root="home:owner", status=403)["error"] == "permission_denied"
    own = lock(fc, OWNER, "/Docs")
    again = lock(fc, OWNER, "/Docs")  # the same holder may take another (a second app of theirs)
    assert again["id"] != own["id"]
    assert fc.get("/v1/sync/locks", params={"root": "home:adult"}, headers=OWNER).status_code == 403
