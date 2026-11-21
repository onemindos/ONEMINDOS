# SPDX-License-Identifier: Apache-2.0
"""Body-cap boundaries on every route that reads a body (#160, H-20).

The guard counts bytes as the route pulls them. A body of unknown length that a route never reads
(a failed precondition answers first) is drained, counted and discarded before the answer goes out,
so over-cap is 413 whichever check would have answered first. Each test names the code it covers.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import timedelta

import anyio
import pytest

import onemind_core.guard as guard_mod
from files_support import AGENT, OWNER, TUS, fc, files_root, files_settings  # noqa: F401
from onemind_core.guard import GuardMiddleware, LimitSettings
from test_guard_streaming_limits import raw_request

CAP = 256 * 1024
OCTET = {"Content-Type": "application/offset+octet-stream"}


def pieces(n: int, size: int = 16 * 1024):
    left = n
    while left > 0:
        step = min(size, left)
        left -= step
        yield b"x" * step


# ---- the guard itself: unread bodies of unknown length -----------------------------------------------------------
def run_guard(app, parts, *, method="POST", headers=(), limit=1024):
    sent, reads = [], []
    queue = [{"type": "http.request", "body": p, "more_body": True} for p in parts]
    queue.append({"type": "http.request", "body": b"", "more_body": False})

    async def receive():
        reads.append(True)
        if queue:
            return queue.pop(0)
        await anyio.sleep_forever()

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": method, "path": "/", "headers": list(headers)}
    guard = GuardMiddleware(app, limits=LimitSettings(max_body_bytes=limit))
    anyio.run(guard, scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"], len(reads), sent


async def answers_without_reading(scope, receive, send):
    await send({"type": "http.response.start", "status": 412, "headers": []})
    await send({"type": "http.response.body", "body": b"precondition"})


def test_unread_over_cap_chunked_body_is_413_not_the_precondition():
    status, reads, sent = run_guard(answers_without_reading, [b"x" * 600, b"x" * 600])
    assert status == 413 and reads == 2  # stops draining at the overflow
    assert b"precondition" not in b"".join(m.get("body", b"") for m in sent)


def test_unread_in_cap_body_gets_the_routes_own_answer():
    status, reads, _ = run_guard(answers_without_reading, [b"x" * 500, b"x" * 524])  # exactly the cap
    assert status == 412 and reads == 3  # both pieces and the final empty message were drained


def test_a_route_that_reads_is_not_drained():
    async def reads_one_then_answers(scope, receive, send):
        await receive()
        await answers_without_reading(scope, receive, send)

    status, reads, _ = run_guard(reads_one_then_answers, [b"x" * 10, b"x" * 10])
    assert status == 412 and reads == 1


@pytest.mark.parametrize(("method", "headers"), [("GET", []), ("POST", [(b"content-length", b"10")])])
def test_bodyless_or_declared_requests_are_not_drained(method, headers):
    status, reads, _ = run_guard(answers_without_reading, [b"x" * 10], method=method, headers=headers)
    assert status == 412 and reads == 0


def test_a_stalled_unread_body_does_not_hold_the_answer(monkeypatch):
    monkeypatch.setattr(guard_mod, "DRAIN_TIMEOUT_S", 0.05)
    sent = []

    async def receive():
        await anyio.sleep_forever()

    async def send(message):
        sent.append(message)

    guard = GuardMiddleware(answers_without_reading, limits=LimitSettings(max_body_bytes=1024))
    anyio.run(guard, {"type": "http", "method": "PATCH", "path": "/", "headers": []}, receive, send)
    assert [m["status"] for m in sent if m["type"] == "http.response.start"] == [412]


# ---- files.py: tus PATCH streams the body to disk -----------------------------------------------------------------
def make_upload(fc, size):
    r = fc.post("/v1/files/uploads", headers={**OWNER, **TUS, "Upload-Length": str(size), "Upload-Metadata":
                "root " + base64.b64encode(b"home:owner").decode() + ",filename " + base64.b64encode(b"f.bin").decode()})
    assert r.status_code == 201, r.text
    return r.headers["location"]


@pytest.mark.parametrize("tus", [True, False], ids=["tus-headers", "no-tus-header"])
@pytest.mark.parametrize("framing", ["chunked", "unframed"])
def test_tus_patch_over_cap_is_413_and_stores_nothing(fc, framing, tus):
    loc = make_upload(fc, 2 * CAP)
    headers = {**OWNER, **OCTET, "Upload-Offset": "0", **(TUS if tus else {})}
    if framing == "chunked":
        r = fc.patch(loc, content=pieces(CAP + 1), headers=headers)
        status = r.status_code
    else:
        status, _, _ = raw_request(fc, loc, headers, list(pieces(CAP + 1)), method="PATCH")
    assert status == 413
    assert fc.head(loc, headers={**OWNER, **TUS}).headers["upload-offset"] == "0"


def test_tus_patch_chunked_at_the_cap_is_stored(fc):
    loc = make_upload(fc, 2 * CAP)
    r = fc.patch(loc, content=pieces(CAP), headers={**OWNER, **TUS, **OCTET, "Upload-Offset": "0"})
    assert r.status_code == 204 and r.headers["upload-offset"] == str(CAP)


# ---- migrate.py: the restic repository streams each blob to disk ---------------------------------------------------
@pytest.fixture
def repo(client, clock):
    store = client.app.state.migrate.store
    plan, secret = "mig_BOUNDS", secrets.token_urlsafe(16)
    store.add_user("mw-bounds", plan, "action-1", secret, "w", clock.now + timedelta(hours=1))
    auth = {"Authorization": "Basic " + base64.b64encode(f"mw-bounds:{secret}".encode()).decode()}
    assert client.post(f"/v1/migrate/repo/{plan}/?create=true", headers=auth).status_code == 200
    return client, f"/v1/migrate/repo/{plan}", auth


def test_repo_blob_over_cap_is_413_and_not_stored(repo):
    client, base, auth = repo
    data = b"x" * (CAP + 1)
    name = hashlib.sha256(data).hexdigest()
    assert client.post(f"{base}/data/{name}", headers=auth, content=pieces(len(data))).status_code == 413
    assert client.head(f"{base}/data/{name}", headers=auth).status_code == 404


def test_repo_blob_chunked_at_the_cap_is_stored(repo):
    client, base, auth = repo
    data = b"x" * CAP
    name = hashlib.sha256(data).hexdigest()
    assert client.post(f"{base}/data/{name}", headers=auth, content=pieces(len(data))).status_code == 200
    assert client.head(f"{base}/data/{name}", headers=auth).headers["content-length"] == str(CAP)


# ---- mcp/server.py: the JSON-RPC body is read with its own cap -----------------------------------------------------
MCP = {**AGENT, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def ping(pad: int) -> bytes:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "pad": ""}).encode()
    return body.replace(b'"pad": ""', b'"pad": "' + b"x" * pad + b'"')


@pytest.mark.parametrize("framing", ["chunked", "unframed"])
def test_mcp_message_at_the_cap_is_answered_and_one_over_is_413(client, framing):
    def send(body: bytes) -> int:
        if framing == "chunked":
            return client.post("/mcp", content=(body[i:i + 8192] for i in range(0, len(body), 8192)), headers=MCP).status_code
        return raw_request(client, "/mcp", MCP, [body[i:i + 8192] for i in range(0, len(body), 8192)])[0]

    fit = ping(0)
    exact = ping(CAP - len(fit))
    assert len(exact) == CAP
    assert send(exact) == 200
    assert send(ping(CAP - len(fit) + 1)) == 413


# ---- notifications.py: preferences are parsed from the request body ------------------------------------------------
@pytest.mark.parametrize("framing", ["chunked", "unframed"])
def test_preferences_put_over_cap_is_413_and_keeps_the_old_document(client, framing):
    before = client.get("/v1/notifications/preferences", headers=OWNER)
    assert before.status_code == 200
    doc = json.dumps({"version": 1, "routes": [], "pad": "x" * CAP}).encode()
    if framing == "chunked":
        status = client.put("/v1/notifications/preferences", headers={**OWNER, "Content-Type": "application/json"},
                            content=(doc[i:i + 8192] for i in range(0, len(doc), 8192))).status_code
    else:
        status = raw_request(client, "/v1/notifications/preferences", {**OWNER, "Content-Type": "application/json"},
                             [doc[i:i + 8192] for i in range(0, len(doc), 8192)], method="PUT")[0]
    assert status == 413
    assert client.get("/v1/notifications/preferences", headers=OWNER).json() == before.json()


def test_preferences_put_in_cap_chunked_is_parsed(client):
    doc = json.dumps(client.get("/v1/notifications/preferences", headers=OWNER).json()).encode()
    r = client.put("/v1/notifications/preferences", headers={**OWNER, "Content-Type": "application/json"},
                   content=(doc[i:i + 7] for i in range(0, len(doc), 7)))
    assert r.status_code == 200, r.text
