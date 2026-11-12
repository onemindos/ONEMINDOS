# SPDX-License-Identifier: Apache-2.0
"""OneMind Photos backup protocol, box side (docs/leap/core/PHOTOS.md; UMB-PHOTO-3 tests T1-T6).

`Phone` below speaks the protocol exactly as mobile/src/photos/protocol.ts does (same routes,
headers and order), so these tests are the server half of the phone's own test suite.
Runs on SQLite, and on PostgreSQL with ONEMIND_TEST_DB_URL.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import anyio
import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.ledger import Base
from onemind_core.photos import PhotosSettings
from onemind_core.photos.files import person_folder, safe_file_name, source_folder
from onemind_core.photos.service import new_id
from onemind_core.sections import load_section
from onemind_core.store import registered_schemas

from conftest import ADULT, AGENT, GUEST, OWNER

INTEROP = {"Upload-Draft-Interop-Version": "7"}


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def blob(seed: int, size: int) -> bytes:
    out = bytearray()
    block = hashlib.sha256(f"photo-{seed}".encode()).digest()
    while len(out) < size:
        out += block
        block = hashlib.sha256(block).digest()
    return bytes(out[:size])


class Phone:
    """The phone's side of the protocol (mobile/src/photos/protocol.ts and engine.ts)."""

    def __init__(self, c: TestClient, auth: dict, client_id: str = "install-1", name: str = "Ana's iPhone"):
        self.c, self.auth, self.client_id = c, auth, client_id
        r = c.post("/v1/photos/sources", json={"client_id": client_id, "name": name, "platform": "ios"}, headers=auth)
        assert r.status_code in (200, 201), r.text
        self.source = r.json()["id"]

    def key(self, asset_id: str) -> str:
        return hashlib.sha256(f"onemind-photos-key/v1\n{self.client_id}\n{asset_id}".encode()).hexdigest()

    def check(self, items: list[tuple[str, bytes]]) -> list[str]:
        r = self.c.post(
            f"/v1/photos/sources/{self.source}/check",
            json={"items": [{"client_key": k, "size": len(d), "hash": sha(d)} for k, d in items]}, headers=self.auth,
        )
        assert r.status_code == 200, r.text
        return [i["status"] for i in r.json()["items"]]

    def create(self, key: str, data: bytes, name: str = "IMG_0001.HEIC", created_at: str | None = None, declared=None):
        headers = {
            **self.auth, **INTEROP, "Upload-Complete": "?0", "Upload-Length": str(len(data)),
            "OneMind-Source-Id": self.source, "OneMind-Client-Key": key,
            "OneMind-Content-Hash": declared or sha(data), "OneMind-File-Name": quote(name),
        }
        if created_at:
            headers["OneMind-Created-At"] = created_at
        return self.c.post("/v1/photos/uploads", headers=headers)

    def head(self, url: str):
        return self.c.head(url, headers={**self.auth, **INTEROP})

    def patch(self, url: str, offset: int, data: bytes, last: bool):
        return self.c.patch(url, content=data, headers={
            **self.auth, **INTEROP, "Upload-Offset": str(offset), "Upload-Complete": "?1" if last else "?0",
            "Content-Type": "application/partial-upload",
        })

    def upload(self, key: str, data: bytes, chunk: int = 64 * 1024, **kw) -> dict:
        r = self.create(key, data, **kw)
        assert r.status_code == 201, r.text
        url, offset = r.headers["Location"], int(r.headers["Upload-Offset"])
        while True:
            part = data[offset:offset + chunk]
            last = offset + len(part) >= len(data)
            r = self.patch(url, offset, part, last)
            if last:
                assert r.status_code == 200, r.text
                return r.json()
            assert r.status_code == 204, r.text
            offset = int(r.headers["Upload-Offset"])

    def coverage(self) -> dict:
        r = self.c.get(f"/v1/photos/sources/{self.source}/coverage", headers=self.auth)
        assert r.status_code == 200, r.text
        return r.json()

    def levels(self, **params) -> dict:
        r = self.c.get(f"/v1/photos/sources/{self.source}/receipts", params=params, headers=self.auth)
        assert r.status_code == 200, r.text
        return r.json()


def photos_settings(settings, root: Path, **kw):
    return replace(settings, sections={**settings.sections, "photos": PhotosSettings(enabled=True, dir=root, **kw)})


@pytest.fixture
def root(tmp_path) -> Path:
    return tmp_path / "photos"


@pytest.fixture
def pc(settings, clock, root):
    with TestClient(create_app(photos_settings(settings, root), clock=clock)) as c:
        yield c


def audit_types(settings) -> list[str]:
    return [json.loads(line)["event"] for line in settings.audit_path.read_text().splitlines()]


def library_files(root: Path, person: str) -> list[Path]:
    return sorted(p for p in (root / "library" / person).rglob("*") if p.is_file())


def store_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / "library" / ".shared-store").rglob("*") if p.is_file())


def asgi_patch(c: TestClient, url: str, headers: dict, parts: list[bytes], end: str):
    """Send a PATCH whose body arrives in parts, then ends ("done"), drops ("disconnect") or stalls."""
    msgs = [{"type": "http.request", "body": p, "more_body": True} for p in parts]
    if end == "done":
        msgs.append({"type": "http.request", "body": b"", "more_body": False})
    elif end == "disconnect":
        msgs.append({"type": "http.disconnect"})
    sent: list[dict] = []

    async def receive():
        if msgs:
            return msgs.pop(0)
        if end == "disconnect":
            return {"type": "http.disconnect"}
        await anyio.sleep(3600)  # a stalled phone

    async def send(message):
        sent.append(message)

    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "PATCH", "scheme": "http",
        "path": url, "raw_path": url.encode(), "query_string": b"", "headers": raw, "root_path": "",
        "client": ("testclient", 50000), "server": ("testserver", 80), "state": {},
    }
    c.portal.call(c.app, scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]}


# ---- switched off, who may use it ---------------------------------------------------------------

def test_off_by_default_routes_404_but_documented(client):
    r = client.post("/v1/photos/sources", json={"client_id": "c1", "name": "P", "platform": "ios"}, headers=OWNER)
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/v1/photos/sources", "/v1/photos/sources/{source_id}/check", "/v1/photos/uploads",
              "/v1/photos/uploads/{upload_id}", "/v1/photos/sources/{source_id}/coverage",
              "/v1/photos/sources/{source_id}/receipts"):
        assert p in paths
    assert {"head", "patch"} <= set(paths["/v1/photos/uploads/{upload_id}"])


def test_settings_need_a_folder_when_enabled():
    with pytest.raises(ValueError, match="ONEMIND_PHOTOS_DIR"):
        load_section(PhotosSettings, {"ONEMIND_PHOTOS_ENABLED": "1"})
    s = load_section(PhotosSettings, {"ONEMIND_PHOTOS_ENABLED": "1", "ONEMIND_PHOTOS_DIR": "/srv/photos"})
    assert s.enabled and s.dir == Path("/srv/photos")
    with pytest.raises(ValueError):
        load_section(PhotosSettings, {"ONEMIND_PHOTOS_MAX_OPEN_UPLOADS": "0"})


def test_schema_and_tables_are_the_photos_feature():
    assert "photos" in {s.feature for s in registered_schemas()}
    photo_tables = [t for t in Base.metadata.tables if "photo" in t]
    assert photo_tables and all(t.startswith("photos_") for t in photo_tables)


@pytest.mark.parametrize("who,status", [(None, 401), (GUEST, 403), (AGENT, 403)])
def test_only_people_with_a_library_back_up(pc, who, status):
    r = pc.post("/v1/photos/sources", json={"client_id": "c1", "name": "P", "platform": "ios"}, headers=who or {})
    assert r.status_code == status


# ---- sources -------------------------------------------------------------------------------------

def test_register_source_is_idempotent_per_person(pc, settings):
    body = {"client_id": "install-1", "name": "Ana's iPhone", "platform": "ios"}
    r1 = pc.post("/v1/photos/sources", json=body, headers=OWNER)
    r2 = pc.post("/v1/photos/sources", json={**body, "name": "Renamed"}, headers=OWNER)
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert r1.json()["id"] == r2.json()["id"] and r2.json()["name"] == "Renamed"
    assert r1.json()["id"].startswith("src_") and len(r1.json()["id"]) == 30
    other = pc.post("/v1/photos/sources", json=body, headers=ADULT)
    assert other.status_code == 201 and other.json()["id"] != r1.json()["id"]
    assert audit_types(settings).count("photos.source.registered") == 2
    bad = pc.post("/v1/photos/sources", json={**body, "platform": "symbian"}, headers=OWNER)
    assert bad.status_code == 422 and bad.json()["error"] == "conflict"


# ---- the happy path ------------------------------------------------------------------------------

def test_upload_in_parts_then_have(pc, root, clock):
    phone = Phone(pc, OWNER)
    data = blob(1, 3 * 1024 * 1024 + 17)
    key = phone.key("asset-1")
    assert phone.check([(key, data)]) == ["need"]

    r = phone.create(key, data, name="IMG_0001.HEIC", created_at="2025-07-04T10:00:00.000Z")
    assert r.status_code == 201
    url = r.headers["Location"]
    assert url.startswith("/v1/photos/uploads/upl_") and r.headers["Upload-Offset"] == "0"
    h = phone.head(url)
    assert h.status_code == 204
    assert h.headers["Upload-Offset"] == "0" and h.headers["Upload-Complete"] == "?0"
    assert h.headers["Upload-Length"] == str(len(data)) and h.headers["Cache-Control"] == "no-store"
    assert h.headers["Upload-Limit"].startswith("max-size=")

    chunk = 1024 * 1024
    for off in range(0, 3 * chunk, chunk):
        r = phone.patch(url, off, data[off:off + chunk], last=False)
        assert r.status_code == 204 and r.headers["Upload-Offset"] == str(off + chunk)
    r = phone.patch(url, 3 * chunk, data[3 * chunk:], last=True)
    assert r.status_code == 200
    assert r.json() == {"client_key": key, "hash": sha(data), "deduped": False}
    assert r.headers["Upload-Complete"] == "?1"

    files = library_files(root, "owner")
    assert len(files) == 1 and files[0].read_bytes() == data
    parts = files[0].relative_to(root / "library" / "owner").parts
    assert parts == (source_folder("Ana's iPhone", phone.source), "2025", "07", "IMG_0001.HEIC")
    assert parts[0].startswith("ana-s-iphone-")
    stored = store_files(root)
    assert len(stored) == 1 and stored[0].name == sha(data)[7:]
    assert os.stat(stored[0]).st_ino == os.stat(files[0]).st_ino  # one copy on disk
    assert not any((root / "staging").iterdir())
    assert phone.check([(key, data)]) == ["have"]
    assert phone.coverage() == {"total": 1, "on_box": 1, "backed_up": 0, "verified": 0, "as_of": "2026-11-11T22:00:00Z"}
    assert phone.head(url).headers["Upload-Complete"] == "?1"


def test_lost_final_response_replays_the_receipt(pc):
    phone = Phone(pc, OWNER)
    data = blob(2, 1000)
    key = phone.key("a")
    url = phone.create(key, data).headers["Location"]
    first = phone.patch(url, 0, data, last=True)
    assert first.status_code == 200
    # The phone never saw it: next run asks HEAD, then sends the (empty) last part again.
    h = phone.head(url)
    assert (h.headers["Upload-Offset"], h.headers["Upload-Complete"]) == ("1000", "?1")
    again = phone.patch(url, 1000, b"", last=True)
    assert again.status_code == 200 and again.json() == first.json()
    more = phone.patch(url, 0, data[:10], last=False)
    assert more.status_code == 409 and more.headers["Upload-Complete"] == "?1"


def test_a_part_that_loses_the_race_with_the_last_part(pc, root, monkeypatch):
    """A request that read the upload as open just before another request finished it."""
    phone = Phone(pc, OWNER)
    data = blob(49, 100)
    url = phone.create(phone.key("a"), data).headers["Location"]
    receipt = phone.patch(url, 0, data, last=True).json()
    upload_id = url.rsplit("/", 1)[1]
    repo = pc.app.state.photos.repo
    real = repo.get_upload
    for offset, body, last, status in ((100, b"", True, 200), (0, data[:10], False, 409)):
        (root / "staging" / upload_id).touch()  # the finished request's file, still open in this one
        reads = []

        def stale_first(uid, reads=reads):
            up = real(uid)
            reads.append(uid)
            return replace(up, state="open") if len(reads) == 1 else up

        monkeypatch.setattr(repo, "get_upload", stale_first)
        r = phone.patch(url, offset, body, last=last)
        assert r.status_code == status and r.headers["Upload-Complete"] == "?1"
        if status == 200:
            assert r.json() == receipt
    monkeypatch.setattr(repo, "get_upload", real)
    assert phone.head(url).headers["Upload-Complete"] == "?1"


def test_create_returns_the_unfinished_upload_for_the_same_item(pc):
    phone = Phone(pc, OWNER)
    data = blob(3, 5000)
    key = phone.key("a")
    url = phone.create(key, data).headers["Location"]
    assert phone.patch(url, 0, data[:2000], last=False).status_code == 204
    again = phone.create(key, data)
    assert again.headers["Location"] == url and again.headers["Upload-Offset"] == "2000"


# ---- resumable: wrong offsets, drops, stalls, restarts (T4) -----------------------------------

def test_wrong_offset_is_409_with_the_true_offset(pc):
    phone = Phone(pc, OWNER)
    data = blob(4, 10_000)
    url = phone.create(phone.key("a"), data).headers["Location"]
    assert phone.patch(url, 0, data[:4000], last=False).status_code == 204
    r = phone.patch(url, 0, data[:4000], last=False)
    assert r.status_code == 409 and r.json()["error"] == "conflict"
    assert r.headers["Upload-Offset"] == "4000" and r.headers["Upload-Complete"] == "?0"
    assert phone.head(url).headers["Upload-Offset"] == "4000"


def test_more_bytes_than_declared_are_refused_and_dropped(pc):
    phone = Phone(pc, OWNER)
    data = blob(5, 100)
    url = phone.create(phone.key("a"), data).headers["Location"]
    assert phone.patch(url, 0, data[:40], last=False).status_code == 204
    r = phone.patch(url, 40, data[40:] + b"extra", last=True)
    assert r.status_code == 409 and r.headers["Upload-Offset"] == "40"
    assert phone.head(url).headers["Upload-Offset"] == "40"
    assert phone.patch(url, 40, data[40:], last=True).json()["hash"] == sha(data)


def test_short_last_part_keeps_the_bytes(pc):
    phone = Phone(pc, OWNER)
    data = blob(6, 100)
    url = phone.create(phone.key("a"), data).headers["Location"]
    r = phone.patch(url, 0, data[:60], last=True)
    assert r.status_code == 409 and r.headers["Upload-Offset"] == "60"
    assert phone.patch(url, 60, data[60:], last=True).status_code == 200


def test_three_dropped_connections_then_one_stored_copy(pc, root):
    phone = Phone(pc, OWNER)
    data = blob(7, 3_000_000)
    key = phone.key("video")
    url = phone.create(key, data).headers["Location"]
    hdr = {**OWNER, **INTEROP, "Upload-Complete": "?1"}
    offset = 0
    for cut in (700_000, 1_400_000, 2_100_000):
        part = data[offset:cut]
        status, _ = asgi_patch(pc, url, {**hdr, "Upload-Offset": str(offset)}, [part[:100_000], part[100_000:]], "disconnect")
        h = phone.head(url)
        assert h.headers["Upload-Offset"] == str(cut)  # every byte that arrived was kept
        offset = cut
    status, headers = asgi_patch(pc, url, {**hdr, "Upload-Offset": str(offset)}, [data[offset:]], "done")
    assert status == 200 and headers["upload-complete"] == "?1"
    assert phone.check([(key, data)]) == ["have"]
    assert len(store_files(root)) == 1 and store_files(root)[0].read_bytes() == data


def test_a_stalled_body_is_cut_off_and_resumable(settings, clock, root):
    s = photos_settings(settings, root, read_timeout_s=0.2)
    with TestClient(create_app(s, clock=clock)) as c:
        phone = Phone(c, OWNER)
        data = blob(8, 50_000)
        url = phone.create(phone.key("a"), data).headers["Location"]
        status, headers = asgi_patch(
            c, url, {**OWNER, "Upload-Offset": "0", "Upload-Complete": "?1"}, [data[:20_000]], "stall"
        )
        assert status == 409 and headers["upload-offset"] == "20000"
        assert phone.patch(url, 20_000, data[20_000:], last=True).status_code == 200


def test_resume_after_the_box_restarts(settings, clock, root):
    s = photos_settings(settings, root)
    data = blob(9, 300_000)
    with TestClient(create_app(s, clock=clock)) as c:
        phone = Phone(c, OWNER)
        key = phone.key("a")
        url = phone.create(key, data).headers["Location"]
        assert phone.patch(url, 0, data[:120_000], last=False).status_code == 204
    with TestClient(create_app(s, clock=clock)) as c:  # new process: no hash state in memory
        phone = Phone(c, OWNER)
        assert phone.head(url).headers["Upload-Offset"] == "120000"
        r = phone.patch(url, 120_000, data[120_000:], last=True)
        assert r.status_code == 200 and r.json()["hash"] == sha(data)


def test_a_second_writer_on_the_same_upload_is_refused(pc, root):
    phone = Phone(pc, OWNER)
    data = blob(10, 1000)
    url = phone.create(phone.key("a"), data).headers["Location"]
    assert phone.patch(url, 0, data[:300], last=False).status_code == 204
    upload_id = url.rsplit("/", 1)[1]
    fd = os.open(root / "staging" / upload_id, os.O_WRONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)  # what an in-flight PATCH holds
        r = phone.patch(url, 300, data[300:], last=True)
        assert r.status_code == 409 and r.headers["Upload-Offset"] == "300"
    finally:
        os.close(fd)
    assert phone.patch(url, 300, data[300:], last=True).status_code == 200


def test_idle_uploads_expire_and_are_swept(pc, root, clock):
    phone = Phone(pc, OWNER)
    data = blob(11, 1000)
    url = phone.create(phone.key("a"), data).headers["Location"]
    assert phone.patch(url, 0, data[:500], last=False).status_code == 204
    clock.advance(7 * 24 * 3600 + 1)
    assert phone.head(url).status_code == 410
    r = phone.patch(url, 500, data[500:], last=True)
    assert r.status_code == 410 and r.json()["error"] == "expired"
    assert phone.create(phone.key("b"), blob(12, 10)).status_code == 201  # creating sweeps
    staged = [p.name for p in (root / "staging").iterdir()]
    assert len(staged) == 1 and url.rsplit("/", 1)[1] not in staged
    assert phone.head(url).status_code == 404


# ---- digest verification ---------------------------------------------------------------------

def test_bytes_that_do_not_match_the_hash_get_no_receipt(pc, root, settings):
    phone = Phone(pc, OWNER)
    good, bad = blob(13, 2000), blob(14, 2000)
    key = phone.key("a")
    url = phone.create(key, bad, declared=sha(good)).headers["Location"]
    r = phone.patch(url, 0, bad, last=True)
    assert r.status_code == 409 and "do not match" in r.json()["message"]
    assert phone.head(url).status_code == 410
    assert library_files(root, "owner") == [] and store_files(root) == []
    assert not any((root / "staging").iterdir())
    assert phone.check([(key, good)]) == ["need"]
    assert "photos.upload.rejected" in audit_types(settings)


# ---- dedupe, receipts and the hash oracle (T1, T2, T6) ---------------------------------------

def test_a_duplicate_on_the_phone_is_recorded_without_an_upload(pc):
    phone = Phone(pc, OWNER)
    data = blob(15, 4000)
    k1, k2 = phone.key("a"), phone.key("copy-of-a")
    phone.upload(k1, data)
    assert phone.check([(k2, data)]) == ["have"]
    assert phone.coverage()["total"] == 2


def test_the_same_persons_other_phone_is_not_asked_again(pc, root):
    iphone = Phone(pc, OWNER, client_id="install-1")
    ipad = Phone(pc, OWNER, client_id="install-2", name="iPad")
    data = blob(16, 4000)
    iphone.upload(iphone.key("a"), data)
    assert ipad.check([(ipad.key("x"), data)]) == ["have"]
    receipt = ipad.upload(ipad.key("y"), data)  # a phone that uploads anyway keeps no second copy
    assert receipt["deduped"] is True
    assert len(library_files(root, "owner")) == 1


def test_no_hash_oracle_across_people_and_one_stored_copy(pc, root):
    ana, ben = Phone(pc, OWNER), Phone(pc, ADULT)
    data = blob(17, 10_000)
    ra = ana.upload(ana.key("a"), data)
    # Ben cannot learn that Ana holds these bytes: same answers as for bytes nobody has.
    assert ben.check([(ben.key("b"), data)]) == ["need"]
    rb = ben.upload(ben.key("b"), data)
    assert {k: rb[k] for k in ("hash", "deduped")} == {k: ra[k] for k in ("hash", "deduped")}
    assert ra["deduped"] is False
    a_file, b_file = library_files(root, "owner"), library_files(root, "adult")
    assert len(a_file) == len(b_file) == 1 and len(store_files(root)) == 1
    assert os.stat(a_file[0]).st_ino == os.stat(b_file[0]).st_ino == os.stat(store_files(root)[0]).st_ino
    assert ben.check([(ben.key("b"), data)]) == ["have"]
    assert ana.coverage()["total"] == 1 and ben.coverage()["total"] == 1


def test_another_persons_sources_and_uploads_look_missing(pc):
    ana, ben = Phone(pc, OWNER), Phone(pc, ADULT)
    data = blob(18, 100)
    url = ben.create(ben.key("b"), data).headers["Location"]
    r = pc.post(f"/v1/photos/sources/{ben.source}/check", json={"items": []}, headers=OWNER)
    assert r.status_code == 404
    assert pc.get(f"/v1/photos/sources/{ben.source}/coverage", headers=OWNER).status_code == 404
    assert ana.head(url).status_code == 404
    assert ana.patch(url, 0, data, last=True).status_code == 404
    stolen = pc.post("/v1/photos/uploads", headers={
        **OWNER, "Upload-Length": "100", "OneMind-Source-Id": ben.source, "OneMind-Client-Key": ana.key("x"),
        "OneMind-Content-Hash": sha(data),
    })
    assert stolen.status_code == 404


def test_two_people_upload_the_same_new_bytes_at_once(pc, root):
    ana, ben = Phone(pc, OWNER), Phone(pc, ADULT)
    data = blob(19, 200_000)
    urls = []
    for phone in (ana, ben):
        url = phone.create(phone.key("p"), data).headers["Location"]
        assert phone.patch(url, 0, data[:-1], last=False).status_code == 204
        urls.append((phone, url))
    results = {}

    def finish(phone, url):
        results[phone.source] = phone.patch(url, len(data) - 1, data[-1:], last=True)

    threads = [threading.Thread(target=finish, args=pair) for pair in urls]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r.status_code == 200 and r.json()["deduped"] is False for r in results.values())
    assert len(store_files(root)) == 1
    assert len(library_files(root, "owner")) == len(library_files(root, "adult")) == 1


def test_a_receipt_alone_is_no_proof(pc, root):
    phone = Phone(pc, OWNER)
    data = blob(20, 3000)
    key = phone.key("a")
    phone.upload(key, data)
    store_files(root)[0].unlink()  # the shared copy is damaged or gone
    assert phone.check([(key, data)]) == ["need"]
    assert phone.upload(key, data)["deduped"] is True  # the person's photo exists; the copy is healed
    assert store_files(root)[0].read_bytes() == data
    assert phone.check([(key, data)]) == ["have"]


def test_an_edited_photo_is_a_new_upload_for_the_same_key(pc):
    phone = Phone(pc, OWNER)
    key = phone.key("a")
    phone.upload(key, blob(21, 500))
    edited = blob(22, 500)
    assert phone.check([(key, edited)]) == ["need"]
    phone.upload(key, edited)
    assert phone.check([(key, edited)]) == ["have"]
    assert phone.levels()["items"][0]["hash"] == sha(edited)
    assert phone.coverage()["total"] == 1


def test_check_validates_its_items(pc):
    phone = Phone(pc, OWNER)
    url = f"/v1/photos/sources/{phone.source}/check"
    too_many = [{"client_key": "a" * 64, "size": 1, "hash": "sha256:" + "0" * 64}] * 501
    assert pc.post(url, json={"items": too_many}, headers=OWNER).status_code == 422
    bad = pc.post(url, json={"items": [{"client_key": "A" * 64, "size": 1, "hash": "md5:x"}]}, headers=OWNER)
    assert bad.status_code == 422 and bad.json()["error"] == "conflict"
    assert pc.post(url, json={"items": []}, headers=OWNER).json() == {"items": []}


# ---- the "in verified backup" level (B1) ------------------------------------------------------

def test_receipt_levels_follow_backup_snapshots_and_restore_checks(pc, clock):
    phone = Phone(pc, OWNER)
    events = pc.app.state.gateway.events
    old, new = blob(23, 800), blob(24, 900)
    k_old, k_new = phone.key("old"), phone.key("new")
    phone.upload(k_old, old)
    run = {"result": "succeeded", "snapshot_id": "4f2a9c", "target_id": "usb",
           "started_at": (clock.now + timedelta(minutes=1)).isoformat(), "units": ["system", "photos"]}
    clock.advance(600)
    phone.upload(k_new, new)  # arrives after the snapshot started: not in it

    events.publish_event("backup", "run.finished", {**run, "units": ["system"]})  # no photos unit
    assert phone.coverage()["backed_up"] == 0
    events.publish_event("backup", "run.finished", {**run, "result": "failed"})
    assert phone.coverage()["backed_up"] == 0
    events.publish_event("backup", "run.finished", run)
    assert {k: phone.coverage()[k] for k in ("total", "on_box", "backed_up", "verified")} == \
        {"total": 2, "on_box": 2, "backed_up": 1, "verified": 0}

    verify = {"snapshot_id": "4f2a9c", "target_id": "usb", "unit": "photos"}
    events.publish_event("backup", "verify.finished", {**verify, "result": "failed"})
    assert phone.coverage()["verified"] == 0
    events.publish_event("backup", "verify.finished", {**verify, "snapshot_id": "unknown", "result": "passed"})
    assert phone.coverage()["verified"] == 0
    events.publish_event("backup", "verify.finished", {**verify, "result": "passed"})
    assert phone.coverage()["verified"] == 1
    levels = {i["client_key"]: i["level"] for i in phone.levels()["items"]}
    assert levels == {k_old: "in_verified_backup", k_new: "on_box"}

    events.publish_event("backup", "snapshot.removed", {"snapshot_id": "4f2a9c", "target_id": "usb"})
    assert {k: phone.coverage()[k] for k in ("backed_up", "verified")} == {"backed_up": 0, "verified": 0}
    assert {i["level"] for i in phone.levels()["items"]} == {"on_box"}


def test_receipts_page_by_cursor(pc):
    phone = Phone(pc, OWNER)
    keys = sorted(phone.key(f"a{i}") for i in range(3))
    for i, k in enumerate(keys):
        phone.upload(k, blob(30 + i, 100))
    first = phone.levels(limit=2)
    assert [i["client_key"] for i in first["items"]] == keys[:2] and first["next_cursor"] == keys[1]
    rest = phone.levels(limit=2, cursor=first["next_cursor"])
    assert [i["client_key"] for i in rest["items"]] == keys[2:] and rest["next_cursor"] is None
    assert pc.get(f"/v1/photos/sources/{phone.source}/receipts?cursor=x", headers=OWNER).status_code == 422


# ---- limits and names ------------------------------------------------------------------------

def test_limits_on_size_open_uploads_and_free_space(settings, clock, root):
    s = photos_settings(settings, root, max_upload_bytes=1000, max_open_uploads=2)
    with TestClient(create_app(s, clock=clock)) as c:
        phone = Phone(c, OWNER)
        r = phone.create(phone.key("big"), blob(40, 1001))
        assert r.status_code == 409 and "up to 1000 bytes" in r.json()["message"]
        assert phone.create(phone.key("a"), blob(41, 10)).status_code == 201
        assert phone.create(phone.key("b"), blob(42, 10)).status_code == 201
        assert phone.create(phone.key("c"), blob(43, 10)).status_code == 409
    s = photos_settings(settings, root, reserve_bytes=10**18)
    with TestClient(create_app(s, clock=clock)) as c:
        phone = Phone(c, OWNER)
        r = phone.create(phone.key("d"), blob(44, 10))
        assert r.status_code == 409 and "free space" in r.json()["message"]


def test_create_validates_headers(pc):
    phone = Phone(pc, OWNER)
    data = blob(45, 10)
    assert phone.create("x" * 64, data).status_code == 422
    assert phone.create(phone.key("a"), data, declared="sha256:" + "Z" * 64).status_code == 422
    assert phone.create(phone.key("a"), data, created_at="yesterday").status_code == 422
    r = pc.post("/v1/photos/uploads", headers={
        **OWNER, "Upload-Complete": "?1", "Upload-Length": "10", "OneMind-Source-Id": phone.source,
        "OneMind-Client-Key": phone.key("a"), "OneMind-Content-Hash": sha(data),
    })
    assert r.status_code == 422
    assert phone.create(phone.key("a"), b"").status_code == 422


def test_file_names_stay_inside_the_library_and_never_overwrite(pc, root):
    phone = Phone(pc, OWNER)
    phone.upload(phone.key("a"), blob(46, 10), name="../../etc/passwd", created_at="2024-01-02T03:04:05+00:00")
    phone.upload(phone.key("b"), blob(47, 10), name="IMG_1.HEIC", created_at="2024-01-09T00:00:00Z")
    phone.upload(phone.key("c"), blob(48, 10), name="IMG_1.HEIC", created_at="2024-01-10T00:00:00Z")
    names = sorted(p.relative_to(root / "library" / "owner").as_posix().split("/", 1)[1] for p in library_files(root, "owner"))
    assert names == ["2024/01/IMG_1 (2).HEIC", "2024/01/IMG_1.HEIC", "2024/01/passwd"]


def test_name_helpers():
    assert safe_file_name("E\u0301te 1.jpg") == "\u00c9te 1.jpg"  # NFC: same bytes on macOS and Linux
    assert safe_file_name("..\\..\\x.png") == "x.png"
    assert safe_file_name("\x00\x1f") == "photo"
    assert safe_file_name(".hidden") == "hidden"
    long = safe_file_name("a" * 400 + ".HEIC")
    assert long.endswith(".HEIC") and len(long.encode()) <= 180
    assert person_folder("owner") == "owner"
    assert person_folder("Ana") != person_folder("ana") and person_folder("Ana").startswith("p-")
    assert person_folder("..").startswith("p-")
    assert source_folder("", "src_01ABCDEFGHJKMNPQRSTVWXYZ0") == "phone-vwxyz0"
    assert new_id("upl").startswith("upl_") and len(new_id("upl")) == 30
