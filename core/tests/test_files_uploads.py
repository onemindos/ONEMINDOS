# SPDX-License-Identifier: Apache-2.0
"""FILES: tus 1.0.0 resumable uploads with chunk checksums and whole-file digest checks."""

from __future__ import annotations

import base64
import hashlib
from datetime import timedelta

from files_support import ADULT, OWNER, TUS, fc, files_root, files_settings, meta, mkdir, ok, upload  # noqa: F401

OCTET = {"Content-Type": "application/offset+octet-stream"}


def create(c, headers, data_len, **m):
    m.setdefault("root", "home:owner")
    m.setdefault("filename", "f.bin")
    return c.post("/v1/files/uploads", headers={**headers, **TUS, "Upload-Length": str(data_len), "Upload-Metadata": meta(**m)})


def patch(c, headers, loc, offset, data, checksum=None):
    h = {**headers, **TUS, **OCTET, "Upload-Offset": str(offset)}
    if checksum:
        h["Upload-Checksum"] = "sha256 " + base64.b64encode(hashlib.sha256(checksum).digest()).decode()
    return c.patch(loc, content=data, headers=h)


def test_options_advertise_tus(fc):
    r = fc.options("/v1/files/uploads")
    assert r.status_code == 204 and r.headers["tus-version"] == "1.0.0"
    assert "creation" in r.headers["tus-extension"] and r.headers["tus-checksum-algorithm"] == "sha256"


def test_chunked_upload_resumes_and_verifies(fc, files_root):
    data = bytes(range(256)) * 40  # 10240 bytes
    r = create(fc, OWNER, len(data), sha256=hashlib.sha256(data).hexdigest())
    assert r.status_code == 201 and r.headers["upload-offset"] == "0" and r.headers["tus-resumable"] == "1.0.0"
    loc = r.headers["location"]
    r = patch(fc, OWNER, loc, 0, data[:4000], checksum=data[:4000])
    assert r.status_code == 204 and r.headers["upload-offset"] == "4000"
    # a dropped connection: the client asks where to resume
    h = fc.head(loc, headers={**OWNER, **TUS})
    assert h.status_code == 200 and h.headers["upload-offset"] == "4000" and h.headers["upload-length"] == "10240"
    assert patch(fc, OWNER, loc, 0, data[:10]).json()["reason"] == "offset_mismatch"
    # a corrupted chunk is discarded (460) and the offset does not move
    r = patch(fc, OWNER, loc, 4000, b"\x00" * 1000, checksum=data[4000:5000])
    assert r.status_code == 460 and r.json()["reason"] == "checksum_mismatch"
    assert fc.head(loc, headers={**OWNER, **TUS}).headers["upload-offset"] == "4000"
    r = patch(fc, OWNER, loc, 4000, data[4000:], checksum=data[4000:])
    assert r.status_code == 204 and r.headers["onemind-file-sha256"] == hashlib.sha256(data).hexdigest()
    got = fc.get("/v1/files/download", params={"root": "home:owner", "path": "/f.bin"}, headers=OWNER)
    assert got.content == data
    status = ok(fc.get(loc, headers=OWNER))
    assert status["state"] == "done" and status["path"] == "/f.bin"
    assert list((files_root / ".system" / "uploads").iterdir()) == []


def test_whole_file_digest_mismatch_deletes_the_upload(fc):
    r = create(fc, OWNER, 3, sha256=hashlib.sha256(b"abc").hexdigest())
    loc = r.headers["location"]
    r = patch(fc, OWNER, loc, 0, b"abd")
    assert r.status_code == 409 and r.json()["reason"] == "digest_mismatch"
    assert fc.get("/v1/files/stat", params={"root": "home:owner", "path": "/f.bin"}, headers=OWNER).status_code == 404
    assert fc.head(loc, headers={**OWNER, **TUS}).status_code == 404


def test_repr_digest_header_is_accepted(fc):
    digest = base64.b64encode(hashlib.sha256(b"hello").digest()).decode()
    r = fc.post("/v1/files/uploads", headers={**OWNER, **TUS, "Upload-Length": "5", "Repr-Digest": f"sha-256=:{digest}:",
                                              "Upload-Metadata": meta(root="home:owner", filename="h.txt")})
    assert r.json()["sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert patch(fc, OWNER, r.headers["location"], 0, b"hello").status_code == 204


def test_existing_names_overwrite_and_zero_length(fc):
    ok(upload(fc, OWNER, "home:owner", "/", "a.txt", b"one"), 204)
    r = create(fc, OWNER, 3, filename="a.txt")
    assert r.status_code == 409 and r.json()["reason"] == "exists"
    ok(upload(fc, OWNER, "home:owner", "/", "a.txt", b"two", overwrite=True), 204)
    assert fc.get("/v1/files/download", params={"root": "home:owner", "path": "/a.txt"}, headers=OWNER).content == b"two"
    trash = ok(fc.get("/v1/files/trash", headers=OWNER))
    assert [t["path"] for t in trash] == ["/a.txt"]  # the replaced version is recoverable
    r = upload(fc, OWNER, "home:owner", "/", "empty", b"")
    assert r.status_code == 201 and r.json()["state"] == "done"


def test_upload_rules(fc, clock):
    assert fc.post("/v1/files/uploads", headers={**OWNER, "Upload-Length": "1",
                                                 "Upload-Metadata": meta(root="home:owner", filename="x")}).status_code == 412
    assert create(fc, OWNER, 1, filename="../x").status_code == 422
    assert create(fc, ADULT, 1, root="home:owner").status_code == 403
    r = create(fc, OWNER, 10)
    loc = r.headers["location"]
    assert fc.head(loc, headers={**ADULT, **TUS}).status_code == 404  # someone else's upload
    r = fc.patch(loc, content=b"x", headers={**OWNER, **TUS, "Upload-Offset": "0", "Content-Type": "text/plain"})
    assert r.status_code == 415
    assert patch(fc, OWNER, loc, 0, b"x" * 11).status_code == 413
    assert fc.delete(loc, headers={**OWNER, **TUS}).status_code == 204
    assert fc.head(loc, headers={**OWNER, **TUS}).status_code == 404
    loc = create(fc, OWNER, 10, filename="late").headers["location"]
    clock.advance(timedelta(hours=25).total_seconds())
    r = fc.head(loc, headers={**OWNER, **TUS})
    assert r.status_code == 404


def test_revoked_permission_fails_at_completion(fc, settings):
    """A grant revoked while bytes arrive: the file never lands."""
    mkdir(fc, OWNER, "shared", "/Inbox")
    from files_support import AGENT

    req = ok(fc.post("/v1/files/grants", headers=AGENT, json={
        "subject": {"kind": "agent", "id": "hermes"}, "root": "shared", "path": "/Inbox", "access": "rw"}), 202)
    grant = ok(fc.post(f"/v1/files/requests/{req['id']}/approve", headers=OWNER))["result"]["grant_id"]
    loc = create(fc, AGENT, 4, root="shared", path="/Inbox", filename="r.txt").headers["location"]
    assert patch(fc, AGENT, loc, 0, b"ab").status_code == 204
    ok(fc.delete(f"/v1/files/grants/{grant}", headers=OWNER))
    r = patch(fc, AGENT, loc, 2, b"cd")
    assert r.status_code == 403
    assert fc.get("/v1/files/stat", params={"root": "shared", "path": "/Inbox/r.txt"}, headers=OWNER).status_code == 404
