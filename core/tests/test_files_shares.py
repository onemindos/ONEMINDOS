# SPDX-License-Identifier: Apache-2.0
"""FILES-02 (#237): expiring share links. A link opens for an outside user and stops after expiry."""

from __future__ import annotations

import logging
import os
import shutil
import socket
import threading
import time
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from onemind_core import serve
from onemind_core.app import create_app
from onemind_core.files.shares import MAX_FAILED
from onemind_core.files.store import ShareRow
from onemind_core.photos import PhotosSettings

from files_support import (  # noqa: F401
    ADULT, AGENT, GUEST, OWNER, approve_request, audit_events, fc, files_root, files_settings, mkdir, ok, rename, upload,
)
from test_identity import LOCAL_PEER, SoftAuthenticator, id_settings, register_passkey, setup_owner
from test_photos import Phone, blob, sha

PASSWORD = "a long share password"


def when(clock, **delta) -> str:
    return (clock.now + timedelta(**delta)).isoformat().replace("+00:00", "Z")


def share(c, headers, clock, items, **kw):
    return c.post("/v1/files/shares", headers=headers, json={"items": items, "expires_at": when(clock, days=1), **kw})


def listed_share(c, headers, share_id):
    return next(row for row in ok(c.get("/v1/files/shares", headers=headers)) if row["id"] == share_id)


def make_share(c, headers, clock, items, **kw):
    response = share(c, headers, clock, items, **kw)
    pending = ok(response, 202)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["location"] == f"/v1/files/requests/{pending['id']}"
    result = approve_request(c, pending)
    assert result["share_id"] == pending["params"]["share_id"]
    return {**listed_share(c, headers, result["share_id"]), "one_time": pending["one_time"]}


def end_share(c, headers, share_id):
    pending = ok(c.delete(f"/v1/files/shares/{share_id}", headers=headers), 202)
    assert approve_request(c, pending) == {"share_id": share_id, "state": "revoked"}
    return listed_share(c, headers, share_id)


def put(c, headers, root, folder, name, data):
    ok(upload(c, headers, root, folder, name, data), 204)
    return {"root": root, "path": f"{folder.rstrip('/')}/{name}"}


def share_rows(settings) -> list[ShareRow]:
    engine = create_engine(settings.db_url)
    with Session(engine) as s:
        return list(s.scalars(select(ShareRow)))


@pytest.mark.parametrize("operation", ["rename", "rename-as-move", "create", "revoke"])
def test_person_file_writes_wait_for_owner_approval(operation, settings, clock, executor, files_settings):
    s = id_settings(replace(settings, sections={**settings.sections, "files": files_settings}))
    with TestClient(create_app(s, clock=clock, executor=executor), client=LOCAL_PEER) as c:
        item = put(c, OWNER, "shared", "/", "original.txt", b"file")
        if operation == "revoke":
            link = make_share(c, OWNER, clock, [item])
            download = f"{link['one_time']['path']}/items/0"
        setup_owner(c)
        key = SoftAuthenticator()
        register_passkey(c, key)

        if operation in {"rename", "rename-as-move"}:
            op = ({"op": "rename", "name": "renamed.txt"} if operation == "rename"
                  else {"op": "move", "to_path": "/renamed.txt", "to_root": ""})
            r = c.post("/v1/files/ops", headers=OWNER, json=item | op)
            check_path = "/v1/files/stat?root=shared&path=/original.txt"
            before, after = 200, 404
        elif operation == "create":
            r = share(c, ADULT, clock, [item], password=PASSWORD)
            check_path = f"{r.json()['one_time']['path']}/items/0"
            before, after = 404, 200
        else:
            r = c.delete(f"/v1/files/shares/{link['id']}", headers=OWNER)
            check_path = download
            before, after = 200, 410

        pending = ok(r, 202)
        assert pending["state"] == "awaiting_approval"
        path = f"/v1/files/requests/{pending['id']}"
        approve_path = f"{path}/approve"
        headers = {**OWNER, "OneMind-Share-Password": PASSWORD}
        body = {"plan_sha256": pending["plan_sha256"]}
        assert c.get(check_path, headers=headers).status_code == before
        assert c.post(approve_path, headers=ADULT, json=body).status_code == 403
        assert c.post(approve_path, headers=OWNER, json={}).status_code == 409
        assert c.post(approve_path, headers=OWNER, json={"plan_sha256": "stale"}).status_code == 409
        if operation == "create":
            visible = ok(c.get(path, headers=OWNER))
            assert pending["one_time"]["token"] not in repr(visible)
            assert "password_hash" not in repr(visible) and "token_hash" not in repr(visible)
            assert not share_rows(s)
        if operation != "revoke":
            refused = c.post(approve_path, headers=OWNER, json=body)
            assert refused.status_code == 401 and refused.json()["reason"] == "step_up_required"
            assert c.get(check_path, headers=headers).status_code == before
            challenge = ok(c.post(f"/v1/actions/{pending['id']}/approve-options", headers=OWNER))
            assert challenge["plan_sha256"] == pending["plan_sha256"]
            body["webauthn"] = key.assert_(challenge["challenge"])
        decided = ok(c.post(approve_path, headers=OWNER, json=body))
        assert decided["state"] == "succeeded"
        assert decided["approval"] == ("token" if operation == "revoke" else "passkey")
        assert c.get(check_path, headers=headers).status_code == after


def test_pending_share_keeps_home_paths_private_from_other_principals(settings, clock, executor, files_settings, tmp_path):
    tokens = tmp_path / "tokens.yaml"
    tokens.write_text(settings.tokens_file.read_text().replace("id: hermes, kind: agent", "id: adult, kind: agent"))
    s = replace(settings, tokens_file=tokens, sections={**settings.sections, "files": files_settings})
    with TestClient(create_app(s, clock=clock, executor=executor)) as c:
        item = put(c, ADULT, "home:adult", "/", "private.txt", b"private")
        pending = ok(share(c, ADULT, clock, [item]), 202)
        path = f"/v1/files/requests/{pending['id']}"
        assert ok(c.get(path, headers=ADULT))["plan"]["items"][0]["path"] == item["path"]
        assert item["path"] not in repr(ok(c.get(path, headers=OWNER)))
        assert ok(c.get("/v1/files/requests", headers=AGENT)) == []
        assert c.get(path, headers=AGENT).status_code == 404
        assert c.post(f"{path}/cancel", headers=AGENT).status_code == 404


def test_a_link_opens_for_an_outside_user_and_stops_after_expiry(fc, settings, clock):
    mkdir(fc, OWNER, "shared", "/Trip")
    item = put(fc, OWNER, "shared", "/Trip", "notes.txt", b"day one: beach")
    out = make_share(fc, OWNER, clock, [item], name="Trip notes")
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


def test_renamed_file_link_does_not_serve_reused_path(fc, clock):
    item = put(fc, OWNER, "shared", "/", "selected.txt", b"original")
    path = make_share(fc, OWNER, clock, [item])["one_time"]["path"]
    assert fc.get(f"{path}/items/0").content == b"original"

    rename(fc, OWNER, item["root"], item["path"], "moved.txt")
    put(fc, OWNER, "shared", "/", "selected.txt", b"different file")

    assert ok(fc.get(path))["items"] == [{"index": 0, "available": False, "name": None, "size": None}]
    assert fc.get(f"{path}/items/0").status_code == 404


def test_share_routes_redact_bearer_in_production_access_log(settings, clock, executor, files_settings):
    s = replace(settings, sections={**settings.sections, "files": files_settings})
    server = serve._Server(uvicorn.Config(create_app(s, clock=clock, executor=executor),
                                          log_config=serve.log_config()))
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    capture = Capture()
    access = logging.getLogger("uvicorn.access")
    access.addHandler(capture)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 30
            while not server.started:
                assert thread.is_alive() and time.monotonic() < deadline, "uvicorn did not start"
                time.sleep(0.05)
            with httpx.Client(base_url=f"http://127.0.0.1:{sock.getsockname()[1]}", timeout=30) as c:
                item = put(c, OWNER, "shared", "/", "shared.txt", b"hello")
                path = make_share(c, OWNER, clock, [item])["one_time"]["path"]
                assert c.get(path).status_code == 200
                assert c.get(f"{path}/items/0?inline=true").content == b"hello"
        finally:
            server.should_exit = True
            thread.join(timeout=30)
            access.removeHandler(capture)
    lines = [r.getMessage() for r in records]
    assert any("GET /v1/share/[redacted] HTTP/" in line for line in lines), lines
    assert any("GET /v1/share/[redacted]/items/0?inline=true HTTP/" in line for line in lines), lines
    secret = path.rsplit("/", 1)[-1]
    assert all(secret not in r.getMessage() and secret not in repr(r.args) for r in records)
    assert all(secret not in h.format(r) for h in access.handlers for r in records)


def test_password_is_hashed_checked_and_limits_guessing(fc, settings, clock):
    item = put(fc, ADULT, "home:adult", "/", "secret.txt", b"psst")
    token = make_share(fc, ADULT, clock, [item], password=PASSWORD)["one_time"]["token"]
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
    assert make_share(fc, ADULT, clock, [mine])["created_by"] == "adult"


def test_revoke_and_visibility(fc, settings, clock):
    a = make_share(fc, ADULT, clock, [put(fc, ADULT, "home:adult", "/", "x.txt", b"x")])
    o = make_share(fc, OWNER, clock, [put(fc, OWNER, "shared", "/", "y.txt", b"y")])
    assert [s["id"] for s in ok(fc.get("/v1/files/shares", headers=ADULT))] == [a["id"]]
    assert {s["id"] for s in ok(fc.get("/v1/files/shares", headers=OWNER))} == {a["id"], o["id"]}
    assert ok(fc.get("/v1/files/shares", headers=GUEST)) == []
    assert fc.delete(f"/v1/files/shares/{o['id']}", headers=ADULT).status_code == 404  # not theirs
    assert fc.delete(f"/v1/files/shares/{o['id']}", headers=AGENT).status_code == 404

    assert end_share(fc, OWNER, a["id"])["state"] == "revoked"  # an owner may end any
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
        token = make_share(c, ADULT, clock, [one, two])["one_time"]["token"]

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
    out = make_share(pfc, ADULT, clock, [{"photo": sha(data)}], name="Beach")
    token = out["one_time"]["token"]
    assert ok(pfc.get(f"/v1/share/{token}"))["items"][0]["name"] == "IMG_0001.JPG"
    assert pfc.get(f"/v1/share/{token}/items/0").content == data
    # Somebody else's photo, or one that is not on the box, cannot be shared.
    assert share(pfc, OWNER, clock, [{"photo": sha(data)}]).status_code == 404
    assert share(pfc, ADULT, clock, [{"photo": sha(b"nope")}]).status_code == 404
    assert share(pfc, ADULT, clock, [{"photo": "sha256:XYZ"}]).status_code == 422


def test_an_owner_oversees_links_without_reading_another_persons_home(fc, settings, clock):
    """A Home is private even from the owner (files/access.py): the owner sees that an adult's
    link exists, when it expires and how often it was opened, and may revoke it, but not the
    paths or the name behind items from the adult's Home. Shared items stay visible in full."""
    mkdir(fc, ADULT, "shared", "/Trip")
    mkdir(fc, ADULT, "home:adult", "/medical")
    private = put(fc, ADULT, "home:adult", "/medical", "scan.pdf", b"private")
    public = put(fc, ADULT, "shared", "/Trip", "map.txt", b"map")
    made = make_share(fc, ADULT, clock, [private, public], name="Medical scans", password=PASSWORD)
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
    revoked = end_share(fc, OWNER, made["id"])
    assert revoked["state"] == "revoked" and revoked["items_hidden"] == 1 and "scan.pdf" not in repr(revoked)
    assert fc.get(f"/v1/share/{token}", headers={"OneMind-Share-Password": PASSWORD}).status_code == 410
