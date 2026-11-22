# SPDX-License-Identifier: Apache-2.0
"""Hub sync transfer (#699): missing chunks, chunk upload, conditional commit (412) and versions."""

from __future__ import annotations

import hashlib
import random

from onemind_core.files.transfer import CHUNK_LIMIT, CHUNK_MAX, CHUNK_MIN, cut_point, manifest_of

from files_support import ADULT, AGENT, GUEST, OWNER, fc, files_root, files_settings, mkdir, ok  # noqa: F401


def blob(n: int, seed: int) -> bytes:
    return random.Random(seed).randbytes(n)


def missing(c, headers, root, manifest, status=200):
    r = c.post("/v1/sync/chunks/missing", headers=headers, json={"root": root, "hashes": [m["hash"] for m in manifest]})
    assert r.status_code == status, r.text
    return r.json()["missing"] if status == 200 else r.json()


def put(c, headers, root, data: bytes, digest: str | None = None, status=200):
    digest = digest or hashlib.sha256(data).hexdigest()
    r = c.put(f"/v1/sync/chunks/{digest}", params={"root": root}, content=data,
              headers={**headers, "Content-Type": "application/octet-stream"})
    assert r.status_code == status, r.text
    return r.json()


def send(c, headers, root, data: bytes, manifest=None):
    """Send every chunk the hub is missing; returns how many were sent."""
    manifest = manifest or manifest_of(data)
    offsets, at = {}, 0
    for m in manifest:
        offsets.setdefault(m["hash"], (at, m["size"]))
        at += m["size"]
    todo = missing(c, headers, root, manifest)
    for h in todo:
        start, size = offsets[h]
        put(c, headers, root, data[start:start + size])
    return len(todo)


def commit(c, headers, root, path, data: bytes, base, status=200, manifest=None, **extra):
    body = {"root": root, "path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "chunks": manifest if manifest is not None else manifest_of(data), "base_revision": base, **extra}
    r = c.post("/v1/sync/commit", headers=headers, json=body)
    assert r.status_code == status, r.text
    return r


def sync_up(c, headers, root, path, data: bytes, base, status=200):
    send(c, headers, root, data)
    return commit(c, headers, root, path, data, base, status)


def test_the_chunker_cuts_by_content_so_an_insert_moves_only_nearby_cuts():
    data = blob(3 * 1024 * 1024, 1)
    first = manifest_of(data)
    assert sum(m["size"] for m in first) == len(data)
    assert all(m["size"] <= CHUNK_MAX for m in first) and all(m["size"] >= CHUNK_MIN for m in first[:-1])
    edited = manifest_of(data[:1000] + b"an insert near the start" + data[1000:])
    shared = {m["hash"] for m in first} & {m["hash"] for m in edited}
    assert len(shared) >= len(first) - 3
    assert cut_point(b"short") == 5


def test_an_upload_killed_at_60_percent_resumes_with_only_the_missing_chunks(fc, files_root):
    mkdir(fc, OWNER, "shared", "/Videos")
    data = blob(2 * 1024 * 1024 + 12345, 2)
    manifest = manifest_of(data)
    assert len(manifest) >= 10
    todo = missing(fc, OWNER, "shared", manifest)
    assert todo == [m["hash"] for m in manifest]  # nothing there yet

    killed_at = int(len(manifest) * 0.6)
    at = 0
    for m in manifest[:killed_at]:  # ...and then the connection drops
        put(fc, OWNER, "shared", data[at:at + m["size"]])
        at += m["size"]
    # Committing now names the chunks that never arrived.
    r = commit(fc, OWNER, "shared", "/Videos/clip.bin", data, None, 409)
    assert r.json()["reason"] == "chunks_missing"
    assert {d["hash"] for d in r.json()["details"]} == {m["hash"] for m in manifest[killed_at:]}

    left = missing(fc, OWNER, "shared", manifest)
    assert left == [m["hash"] for m in manifest[killed_at:]]
    assert send(fc, OWNER, "shared", data, manifest) == len(manifest) - killed_at
    done = ok(commit(fc, OWNER, "shared", "/Videos/clip.bin", data, None))
    assert (files_root / "shared" / "Videos" / "clip.bin").read_bytes() == data
    assert done["hash"] == "sha256:" + hashlib.sha256(data).hexdigest() and done["id"].startswith("fil_")
    feed = ok(fc.get("/v1/sync/changes", params={"root": "shared"}, headers=OWNER))
    entry = next(e for e in feed["changes"] if e["path"] == "/Videos/clip.bin")
    assert entry["revision"] == done["revision"] and entry["hash"] == done["hash"]
    # A chunk sent twice is fine; nothing is written again.
    assert put(fc, OWNER, "shared", data[:manifest[0]["size"]])["stored"] is False


def test_the_second_of_two_devices_editing_the_same_file_gets_412(fc, files_root):
    v1 = blob(300_000, 3)
    base = ok(sync_up(fc, OWNER, "shared", "/plan.txt", v1, None))["revision"]
    laptop, phone = v1[:1000] + b"laptop edit" + v1[1000:], v1 + b"phone edit"

    first = ok(sync_up(fc, OWNER, "shared", "/plan.txt", laptop, base))
    assert first["revision"] > base
    r = sync_up(fc, ADULT, "shared", "/plan.txt", phone, base, 412)
    assert r.json()["error"] == "stale_precondition" and r.json()["reason"] == "stale_base"
    assert r.json()["details"] == [{"current_revision": first["revision"], "current_hash": first["hash"]}]
    assert r.headers["ETag"] == f'"{first["revision"]}"'
    assert (files_root / "shared" / "plan.txt").read_bytes() == laptop  # the first editor's change stands

    # If-Match says the same as base_revision and wins over it; create-only refuses an existing file.
    hdr = {**ADULT, "If-Match": f'"{base}"'}
    assert fc.post("/v1/sync/commit", headers=hdr, json={"root": "shared", "path": "/plan.txt", "size": len(phone),
                   "sha256": hashlib.sha256(phone).hexdigest(), "chunks": manifest_of(phone),
                   "base_revision": first["revision"]}).status_code == 412
    assert sync_up(fc, ADULT, "shared", "/plan.txt", phone, None, 412).json()["details"][0]["current_revision"] == first["revision"]
    merged = ok(sync_up(fc, ADULT, "shared", "/plan.txt", phone, first["revision"]))
    assert merged["revision"] > first["revision"]

    # An edit over SMB moves the revision on too: a commit on the old base is refused.
    (files_root / "shared" / "plan.txt").write_bytes(b"edited over SMB")
    assert sync_up(fc, OWNER, "shared", "/plan.txt", v1, merged["revision"], 412).status_code == 412


def test_versions_share_chunks_and_an_outside_edit_is_kept_before_it_is_replaced(fc, files_root):
    transfer = fc.app.state.sync_transfer
    transfer.keep = 3
    data = blob(400_000, 4)
    rev = ok(sync_up(fc, OWNER, "home:owner", "/novel.md", data, None))["revision"]
    edits = []
    for i in range(3):
        data = data + f"chapter {i}\n".encode()
        sent = send(fc, OWNER, "home:owner", data)
        assert sent <= 2  # only the tail changed: the other chunks are shared with the last version
        rev = ok(commit(fc, OWNER, "home:owner", "/novel.md", data, rev))["revision"]
        edits.append(hashlib.sha256(data).hexdigest())
    listing = ok(fc.get("/v1/sync/versions", params={"root": "home:owner", "path": "/novel.md"}, headers=OWNER))
    assert [v["sha256"] for v in listing["versions"]] == edits[::-1]  # the first one was pruned (keep 3)
    assert listing["versions"][0]["current"] is True and listing["versions"][0]["origin"] == "sync"

    space = next(p for p in (files_root / "home").iterdir() if (p / "novel.md").exists())
    (space / "novel.md").write_bytes(b"rewritten in the Files app over SMB\n" * 10)
    fc.app.state.files_index_watcher.scan()
    smb_rev = ok(fc.get("/v1/sync/changes", params={"root": "home:owner"}, headers=OWNER))
    base = next(e for e in smb_rev["changes"] if e["path"] == "/novel.md")["revision"]
    final = blob(50_000, 5)
    ok(sync_up(fc, OWNER, "home:owner", "/novel.md", final, base))
    listing = ok(fc.get("/v1/sync/versions", params={"root": "home:owner", "path": "/novel.md"}, headers=OWNER))
    origins = [(v["origin"], v["sha256"]) for v in listing["versions"]]
    assert origins[0] == ("sync", hashlib.sha256(final).hexdigest())
    assert origins[1] == ("hub", hashlib.sha256(b"rewritten in the Files app over SMB\n" * 10).hexdigest())
    assert len(origins) == 3
    # A pruned version's chunks are gone; the kept ones are still there.
    gone = manifest_of(blob(400_000, 4))[-1]["hash"]
    assert gone in missing(fc, OWNER, "home:owner", [{"hash": gone}])


def test_a_large_manifest_travels_as_chunks(fc, files_root):
    data = blob(1_500_000, 6)
    manifest = manifest_of(data)
    send(fc, OWNER, "shared", data)
    records = b"".join(bytes.fromhex(m["hash"]) + m["size"].to_bytes(4, "big") for m in manifest)
    pieces = [records[i:i + 72] for i in range(0, len(records), 72)]  # two records a piece, to prove the joining
    for piece in pieces:
        put(fc, OWNER, "shared", piece)
    r = fc.post("/v1/sync/commit", headers=OWNER, json={
        "root": "shared", "path": "/big.bin", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "manifest_chunks": [hashlib.sha256(p).hexdigest() for p in pieces], "base_revision": None})
    assert r.status_code == 200, r.text
    assert (files_root / "shared" / "big.bin").read_bytes() == data


def test_refusals(fc, files_root):
    data = b"twelve bytes"
    digest = hashlib.sha256(data).hexdigest()
    # a chunk whose bytes do not match its name; a chunk over the limit
    assert put(fc, OWNER, "shared", b"other bytes", digest, 422)["reason"] == "hash_mismatch"
    assert put(fc, OWNER, "shared", b"x" * (CHUNK_LIMIT + 1), status=413)["error"] == "payload_too_large"
    # a read-only role (a guest in Shared), a child and an agent without a grant
    for who in (GUEST, AGENT):
        assert missing(fc, who, "shared", [{"hash": digest}], 403)["error"] == "permission_denied"
        put(fc, who, "shared", data, status=403)
        assert commit(fc, who, "shared", "/a.txt", data, None, 403).json()["error"] == "permission_denied"
    # an agent with a read-only grant may not commit; a read-write grant may, inside the folder only
    mkdir(fc, OWNER, "shared", "/Inbox")
    grant = {"subject": {"kind": "agent", "id": "hermes"}, "root": "shared", "path": "/Inbox", "access": "r", "approve": True}
    assert ok(fc.post("/v1/files/grants", headers=OWNER, json=grant), 202)["state"] == "succeeded"
    assert missing(fc, AGENT, "shared", [{"hash": digest}], 403)["reason"] == "no_grant"
    assert commit(fc, AGENT, "shared", "/Inbox/a.txt", data, None, 403).status_code == 403
    ok(fc.post("/v1/files/grants", headers=OWNER, json={**grant, "access": "rw"}), 202)
    assert send(fc, AGENT, "shared", data) == 1
    ok(commit(fc, AGENT, "shared", "/Inbox/a.txt", data, None))
    assert commit(fc, AGENT, "shared", "/outside.txt", data, None, 403).status_code == 403
    # a manifest that does not add up, or whose joined bytes do not hash to the file's sha256
    bad = commit(fc, OWNER, "shared", "/b.txt", data, None, 422, manifest=[{"hash": digest, "size": 11}])
    assert bad.json()["reason"] == "invalid_manifest"
    r = fc.post("/v1/sync/commit", headers=OWNER, json={"root": "shared", "path": "/b.txt", "size": len(data),
                "sha256": "0" * 64, "chunks": manifest_of(data), "base_revision": None})
    assert r.status_code == 422 and r.json()["reason"] == "hash_mismatch"
    assert not (files_root / "shared" / "b.txt").exists()
    # a commit over the quota
    ok(fc.put("/v1/files/quotas/owner", headers=OWNER, json={"limit_bytes": 200_000}))
    big = blob(250_000, 7)
    r = sync_up(fc, OWNER, "home:owner", "/too-big.bin", big, None, 413)
    assert r.json()["reason"] == "quota_exceeded"
    # a commit into a folder that is not there; onto a folder
    assert sync_up(fc, OWNER, "shared", "/nowhere/a.txt", data, None, 404).status_code == 404
    assert sync_up(fc, OWNER, "shared", "/Inbox", data, None, 409).json()["reason"] == "not_a_file"
    leftovers = list((files_root / ".system" / "uploads").glob("sync-*")) if (files_root / ".system" / "uploads").exists() else []
    assert leftovers == []
    # a bad If-Match
    r = fc.post("/v1/sync/commit", headers={**OWNER, "If-Match": "*"}, json={"root": "shared", "path": "/c.txt",
                "size": len(data), "sha256": digest, "chunks": manifest_of(data)})
    assert r.status_code == 422 and r.json()["reason"] == "invalid_precondition"
