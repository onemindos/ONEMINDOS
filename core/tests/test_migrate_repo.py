# SPDX-License-Identifier: Apache-2.0
"""The append-only restic REST repository at /v1/migrate/repo/<plan>/ (protocol v2)."""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import timedelta

import pytest

from onemind_core.migrate.repo import V2

PLAN = "mig_TEST"


@pytest.fixture
def repo(client, clock):
    store = client.app.state.migrate.store
    users = {}
    for mode in ("w", "r"):
        secret = secrets.token_urlsafe(16)
        store.add_user(f"m{mode}-test", PLAN, "action-1", secret, mode, clock.now + timedelta(hours=1))
        users[mode] = {"Authorization": "Basic " + base64.b64encode(f"m{mode}-test:{secret}".encode()).decode()}
    base = f"/v1/migrate/repo/{PLAN}"
    return client, base, users, store


def _blob(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_restic_round_trip(repo):
    client, base, users, _ = repo
    w, r = users["w"], users["r"]
    assert client.head(f"{base}/config", headers=w).status_code == 404
    assert client.post(f"{base}/?create=true", headers=w).status_code == 200
    assert client.post(f"{base}/config", headers=w, content=b"cfg").status_code == 200
    assert client.post(f"{base}/config", headers=w, content=b"other").status_code == 403  # never overwritten
    assert client.get(f"{base}/config", headers=r).content == b"cfg"
    data = b"x" * 1000
    name = _blob(data)
    assert client.post(f"{base}/data/{name}", headers=w, content=data).status_code == 200
    assert client.post(f"{base}/data/{name}", headers=w, content=data).status_code == 403
    assert client.head(f"{base}/data/{name}", headers=r).headers["content-length"] == "1000"
    part = client.get(f"{base}/data/{name}", headers={**r, "Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == b"x" * 10 and part.headers["content-range"] == "bytes 10-19/1000"
    listed = client.get(f"{base}/data/", headers={**r, "Accept": V2})
    assert listed.headers["content-type"].startswith(V2) and listed.json() == [{"name": name, "size": 1000}]
    assert client.get(f"{base}/data/", headers=r).json() == [name]  # protocol v1 listing
    on_disk = client.app.state.migrate.repo_dir(PLAN) / "data" / name[:2] / name
    assert on_disk.read_bytes() == data  # restic's own local layout


def test_append_only_rules(repo):
    client, base, users, _ = repo
    w, r = users["w"], users["r"]
    client.post(f"{base}/?create=true", headers=w)
    client.post(f"{base}/config", headers=w, content=b"cfg")
    bad = b"payload"
    assert client.post(f"{base}/data/{'0' * 64}", headers=w, content=bad).status_code == 400  # hash mismatch
    assert client.post(f"{base}/data/not-hex", headers=w, content=bad).status_code == 400
    assert client.post(f"{base}/secrets/{_blob(bad)}", headers=w, content=bad).status_code == 400
    lock = b"lock"
    assert client.post(f"{base}/locks/{_blob(lock)}", headers=w, content=lock).status_code == 200
    assert client.delete(f"{base}/locks/{_blob(lock)}", headers=r).status_code == 403  # read-only user
    assert client.delete(f"{base}/locks/{_blob(lock)}", headers=w).status_code == 200
    snap = b"snapshot"
    client.post(f"{base}/snapshots/{_blob(snap)}", headers=w, content=snap)
    assert client.delete(f"{base}/snapshots/{_blob(snap)}", headers=w).status_code == 403
    assert client.post(f"{base}/index/{_blob(b'i')}", headers=r, content=b"i").status_code == 403
    assert client.get(f"{base}/snapshots/{_blob(snap)}", headers=r).content == snap


def test_repo_authentication(repo, clock):
    client, base, users, store = repo
    assert client.get(f"{base}/config").status_code == 401
    assert client.get(f"{base}/config").headers["www-authenticate"].startswith("Basic")
    wrong = {"Authorization": "Basic " + base64.b64encode(b"mw-test:nope").decode()}
    assert client.get(f"{base}/config", headers=wrong).status_code == 401
    assert client.get("/v1/migrate/repo/mig_OTHER/config", headers=users["w"]).status_code == 401  # other plan
    assert client.get(f"{base}/config", headers={"Authorization": "Bearer dev-owner-token-change-me"}).status_code == 401
    clock.advance(2 * 3600)
    assert client.get(f"{base}/config", headers=users["r"]).status_code == 401  # expired
    clock.advance(-2 * 3600)
    store.revoke_users("action-1")
    assert client.get(f"{base}/config", headers=users["r"]).status_code == 401  # revoked


def test_repo_routes_not_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/v1/migrate/plans" in paths
    assert not any(p.startswith("/v1/migrate/repo") for p in paths)
