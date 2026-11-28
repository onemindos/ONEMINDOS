# SPDX-License-Identifier: Apache-2.0
"""FILES-02 (#237): expiring share links. A link opens for an outside user and stops after expiry."""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from onemind_core.app import create_app
from onemind_core.files.shares import MAX_FAILED
from onemind_core.files.store import ShareRow
from onemind_core.photos import PhotosSettings

from files_support import ADULT, AGENT, GUEST, OWNER, audit_events, fc, files_root, files_settings, mkdir, ok, upload  # noqa: F401
from test_appstore import run
from test_photos import Phone, blob, sha

PASSWORD = "a long share password"


def when(clock, **delta) -> str:
    return (clock.now + timedelta(**delta)).isoformat().replace("+00:00", "Z")


def share(c, headers, clock, items, **kw):
    return c.post("/v1/files/shares", headers=headers, json={"items": items, "expires_at": when(clock, days=1), **kw})


def put(c, headers, root, folder, name, data):
    ok(upload(c, headers, root, folder, name, data), 204)
    return {"root": root, "path": f"{folder.rstrip('/')}/{name}"}


def share_rows(settings) -> list[ShareRow]:
    engine = create_engine(settings.db_url)
    with Session(engine) as s:
        return list(s.scalars(select(ShareRow)))


def test_a_link_opens_for_an_outside_user_and_stops_after_expiry(fc, settings, clock):
    mkdir(fc, OWNER, "shared", "/Trip")
    item = put(fc, OWNER, "shared", "/Trip", "notes.txt", b"day one: beach")
    out = ok(share(fc, OWNER, clock, [item], name="Trip notes"), 201)
    token = out["one_time"]["token"]
    assert out["one_time"]["url"].endswith(f"/v1/share/{token}") and out["state"] == "active"
    assert out["items"] == [{"kind": "file", "root": "shared", "path": "/Trip/notes.txt"}]

    # The outside user has no account: no Authorization header at all.
    seen = ok(fc.get(f"/v1/share/{token}"))
    assert seen["name"] == "Trip notes"
    assert seen["items"] == [{"index": 0, "available": True, "name": "notes.txt", "size": 14}]
    r = fc.get(f"/v1/share/{token}/items/0")
    assert r.status_code == 200 and r.content == b"day one: beach"
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer"
    r = fc.get(f"/v1/share/{token}/items/0", headers={"Range": "bytes=4-6"})
    assert r.status_code == 206 and r.content == b"one"
    assert fc.get(f"/v1/share/{token}/items/1").status_code == 404  # only what was picked

    # Only the hash of the secret is kept, and the secret is never shown again.
    (row,) = share_rows(settings)
    assert row.token_hash != token and token not in str(row.items)
    listed = ok(fc.get("/v1/files/shares", headers=OWNER))
    assert [s["id"] for s in listed] == [out["id"]] and "one_time" not in listed[0]
    assert listed[0]["opened_count"] == 1

    clock.advance(24 * 3600)
    for path in (f"/v1/share/{token}", f"/v1/share/{token}/items/0"):
        r = fc.get(path)
        assert r.status_code == 410 and r.json()["reason"] == "expired"
    assert ok(fc.get("/v1/files/shares", headers=OWNER))[0]["state"] == "expired"

    events = audit_events(settings)
    names = [e["event"] for e in events]
    assert {"files.share.created", "files.share.opened", "files.share.downloaded", "files.share.refused"} <= set(names)
    assert all(token not in str(e) for e in events)


def test_password_is_hashed_checked_and_limits_guessing(fc, settings, clock):
    item = put(fc, ADULT, "home:adult", "/", "secret.txt", b"psst")
    token = ok(share(fc, ADULT, clock, [item], password=PASSWORD), 201)["one_time"]["token"]
    (row,) = share_rows(settings)
    assert row.password_hash.startswith("scrypt$") and PASSWORD not in row.password_hash

    r = fc.get(f"/v1/share/{token}")
    assert r.status_code == 401 and r.json()["reason"] == "password_required"
    pw = {"OneMind-Share-Password": PASSWORD}
    assert fc.get(f"/v1/share/{token}/items/0", headers=pw).content == b"psst"
    for _ in range(MAX_FAILED):
        r = fc.get(f"/v1/share/{token}", headers={"OneMind-Share-Password": "not the password"})
        assert r.status_code == 401 and r.json()["reason"] == "wrong_password"
    r = fc.get(f"/v1/share/{token}", headers=pw)  # guessing ended the link, even for the right password
    assert r.status_code == 410 and r.json()["reason"] == "revoked"
    assert all(PASSWORD not in str(e) for e in audit_events(settings))


def test_who_may_share_and_what(fc, clock):
    mkdir(fc, OWNER, "shared", "/Docs")
    item = put(fc, OWNER, "shared", "/Docs", "a.txt", b"a")
    for who in (GUEST, AGENT):
        assert share(fc, who, clock, [item]).status_code == 403
    mine = put(fc, ADULT, "home:adult", "/", "mine.txt", b"m")
    assert share(fc, OWNER, clock, [mine]).status_code == 403  # a Home is private, even from the owner
    r = share(fc, OWNER, clock, [{"root": "shared", "path": "/Docs"}])
    assert r.status_code == 409  # files only, never a whole folder
    assert share(fc, OWNER, clock, [{"root": "shared", "path": "/../etc/passwd"}]).status_code in (403, 404, 422)
    for expires in (when(clock, minutes=1), when(clock, days=31), when(clock, days=-1)):
        r = fc.post("/v1/files/shares", headers=OWNER, json={"items": [item], "expires_at": expires})
        assert r.status_code == 422 and r.json()["reason"] == "invalid_expiry"
    r = fc.post("/v1/files/shares", headers=OWNER, json={"items": [item]})
    assert r.status_code == 422  # an expiry is required: no link lives forever
    assert ok(share(fc, ADULT, clock, [mine]), 201)["created_by"] == "adult"


def test_revoke_and_visibility(fc, settings, clock):
    a = ok(share(fc, ADULT, clock, [put(fc, ADULT, "home:adult", "/", "x.txt", b"x")]), 201)
    o = ok(share(fc, OWNER, clock, [put(fc, OWNER, "shared", "/", "y.txt", b"y")]), 201)
    assert [s["id"] for s in ok(fc.get("/v1/files/shares", headers=ADULT))] == [a["id"]]
    assert {s["id"] for s in ok(fc.get("/v1/files/shares", headers=OWNER))} == {a["id"], o["id"]}
    assert ok(fc.get("/v1/files/shares", headers=GUEST)) == []
    assert fc.delete(f"/v1/files/shares/{o['id']}", headers=ADULT).status_code == 404  # not theirs
    assert fc.delete(f"/v1/files/shares/{o['id']}", headers=AGENT).status_code == 404

    assert ok(fc.delete(f"/v1/files/shares/{a['id']}", headers=OWNER))["state"] == "revoked"  # an owner may end any
    r = fc.get(f"/v1/share/{a['one_time']['token']}/items/0")
    assert r.status_code == 410 and r.json()["reason"] == "revoked"
    assert fc.get(f"/v1/share/{o['one_time']['token']}/items/0").content == b"y"
    assert "files.share.revoked" in [e["event"] for e in audit_events(settings)]


def test_each_use_rechecks_the_creator_and_the_confinement(settings, clock, executor, files_settings, files_root, tmp_path):
    tokens = tmp_path / "tokens.yaml"
    shutil.copy(settings.tokens_file, tokens)
    s = replace(settings, tokens_file=tokens, sections={**settings.sections, "files": files_settings})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        one = put(c, ADULT, "home:adult", "/", "one.txt", b"1")
        two = put(c, ADULT, "home:adult", "/", "two.txt", b"2")
        token = ok(share(c, ADULT, clock, [one, two]), 201)["one_time"]["token"]

        # The file is swapped for a symlink to a host file: the confinement refuses to follow it.
        home = next((files_root / "home").iterdir())
        (home / "two.txt").unlink()
        (home / "two.txt").symlink_to("/etc/hostname")
        assert c.get(f"/v1/share/{token}/items/1").status_code == 404
        assert [i["available"] for i in ok(c.get(f"/v1/share/{token}"))["items"]] == [True, False]
        assert c.get(f"/v1/share/{token}/items/0").content == b"1"

        # The creator is demoted to guest: every link they made stops at once.
        tokens.write_text(tokens.read_text().replace("{id: adult, kind: person, role: adult}",
                                                     "{id: adult, kind: person, role: guest}"))
        st = tokens.stat()
        os.utime(tokens, (st.st_atime + 10, st.st_mtime + 10))
        r = c.get(f"/v1/share/{token}/items/0")
        assert r.status_code == 410 and r.json()["reason"] == "creator_access"


@pytest.fixture
def pfc(settings, clock, executor, files_settings, tmp_path):
    sections = {**settings.sections, "files": files_settings,
                "photos": PhotosSettings(enabled=True, dir=tmp_path / "photos")}
    with TestClient(create_app(replace(settings, sections=sections), clock=clock, executor=executor)) as c:
        yield c


def test_photos_are_shared_by_content_from_your_own_library(pfc, clock):
    phone = Phone(pfc, ADULT)
    data = blob(1, 5000)
    phone.upload(phone.key("a1"), data, name="IMG_0001.JPG")
    out = ok(share(pfc, ADULT, clock, [{"photo": sha(data)}], name="Beach"), 201)
    token = out["one_time"]["token"]
    assert ok(pfc.get(f"/v1/share/{token}"))["items"][0]["name"] == "IMG_0001.JPG"
    assert pfc.get(f"/v1/share/{token}/items/0").content == data
    # Somebody else's photo, or one that is not on the box, cannot be shared.
    assert share(pfc, OWNER, clock, [{"photo": sha(data)}]).status_code == 404
    assert share(pfc, ADULT, clock, [{"photo": sha(b"nope")}]).status_code == 404
    assert share(pfc, ADULT, clock, [{"photo": "sha256:XYZ"}]).status_code == 422


def test_photos_switch_blocks_new_and_existing_photo_shares_only(pfc, clock):
    phone = Phone(pfc, ADULT)
    data = blob(1, 5000)
    phone.upload(phone.key("a1"), data)
    photo = {"photo": sha(data)}
    file = put(pfc, ADULT, "shared", "/", "notes.txt", b"trip notes")
    token = ok(share(pfc, ADULT, clock, [photo, file]), 201)["one_time"]["token"]
    url = f"/v1/share/{token}"
    assert pfc.get(f"{url}/items/0").content == data

    assert run(pfc, clock, "app.disable", {"app_id": "photos"}).json()["state"] == "succeeded"
    assert share(pfc, ADULT, clock, [photo]).status_code == 404
    assert pfc.get(f"{url}/items/0").status_code == 404
    assert [item["available"] for item in ok(pfc.get(url))["items"]] == [False, True]
    assert pfc.get(f"{url}/items/1").content == b"trip notes"
    assert share(pfc, ADULT, clock, [file]).status_code == 201

    assert run(pfc, clock, "app.enable", {"app_id": "photos"}).json()["state"] == "succeeded"
    assert share(pfc, ADULT, clock, [photo]).status_code == 201
    assert pfc.get(f"{url}/items/0").content == data


def test_an_owner_oversees_links_without_reading_another_persons_home(fc, settings, clock):
    """A Home is private even from the owner (files/access.py): the owner sees that an adult's
    link exists, when it expires and how often it was opened, and may revoke it, but not the
    paths or the name behind items from the adult's Home. Shared items stay visible in full."""
    mkdir(fc, ADULT, "shared", "/Trip")
    mkdir(fc, ADULT, "home:adult", "/medical")
    private = put(fc, ADULT, "home:adult", "/medical", "scan.pdf", b"private")
    public = put(fc, ADULT, "shared", "/Trip", "map.txt", b"map")
    made = ok(share(fc, ADULT, clock, [private, public], name="Medical scans", password=PASSWORD), 201)
    token = made["one_time"]["token"]

    # The creator sees everything they shared.
    mine = ok(fc.get("/v1/files/shares", headers=ADULT))[0]
    assert mine["name"] == "Medical scans" and mine["items_hidden"] == 0
    assert mine["items"][0] == {"kind": "file", "root": "home:adult", "path": "/medical/scan.pdf"}

    # The owner sees the link, but not the Home path or the typed name.
    seen = next(s for s in ok(fc.get("/v1/files/shares", headers=OWNER)) if s["id"] == made["id"])
    assert seen["created_by"] == mine["created_by"] and seen["password"] is True and seen["state"] == "active"
    assert seen["items_hidden"] == 1 and seen["name"] == "2 shared items"
    assert seen["items"] == [{"kind": "file", "hidden": True, "root": "home:adult"},
                             {"kind": "file", "root": "shared", "path": "/Trip/map.txt"}]
    flat = repr(seen)
    assert "scan.pdf" not in flat and "/medical" not in flat and "Medical" not in flat

    # A download is audited by index, never by path, so the owner-readable audit log cannot
    # reveal the Home path either.
    ok(fc.get(f"/v1/share/{token}/items/0", headers={"OneMind-Share-Password": PASSWORD}))
    downloaded = [e for e in audit_events(settings) if e["event"] == "files.share.downloaded"]
    assert downloaded and "scan.pdf" not in repr(downloaded) and "/medical" not in repr(downloaded)

    # The owner can still end the link without reading it, and still without the path.
    revoked = ok(fc.delete(f"/v1/files/shares/{made['id']}", headers=OWNER))
    assert revoked["state"] == "revoked" and revoked["items_hidden"] == 1 and "scan.pdf" not in repr(revoked)
    assert fc.get(f"/v1/share/{token}", headers={"OneMind-Share-Password": PASSWORD}).status_code == 410
