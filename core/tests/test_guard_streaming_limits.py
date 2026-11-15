# SPDX-License-Identifier: Apache-2.0
"""Real gateway ASGI boundaries (HTTP/2 scope, not a wire-level HTTP/2 test).

Only incomplete photo uploads are created: no finalize/drop/cleanup path.
"""
from __future__ import annotations

import json
from dataclasses import replace

import anyio
import pytest
from fastapi.testclient import TestClient

from conftest import OWNER
from onemind_core.app import create_app
from onemind_core.guard import SECURITY_HEADERS, GuardMiddleware, LimitSettings
from test_photos import Phone, blob, photos_settings


def raw_request(client, path, headers, parts, *, version="1.1", method="POST", end="done"):
    messages = [{"type": "http.request", "body": part, "more_body": True} for part in parts]
    if end == "done":
        messages.append({"type": "http.request", "body": b"", "more_body": False})
    elif end == "disconnect":
        messages.append({"type": "http.disconnect"})
    sent = []

    async def receive():
        if messages:
            return messages.pop(0)
        await anyio.sleep_forever()

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": version,
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "root_path": "", "client": ("testclient", 50000), "server": ("testserver", 80), "state": {},
    }

    async def invoke():
        with anyio.fail_after(3):
            await client.app(scope, receive, send)

    client.portal.call(invoke)
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return starts[0]["status"], dict(starts[0]["headers"]), body


@pytest.mark.parametrize("version", ["1.1", "2"])
def test_unframed_body_over_limit_is_413(settings, clock, version):
    settings = replace(settings, sections={**settings.sections, "limits": LimitSettings(max_body_bytes=1024)})
    with TestClient(create_app(settings, clock=clock)) as client:
        status, headers, body = raw_request(
            client, "/v1/actions", {**OWNER, "Content-Type": "application/json"},
            [b"x" * 512, b"x" * 513], version=version,
        )
    assert status == 413, (status, body)
    assert json.loads(body)["error"] == "payload_too_large"
    for name, value in SECURITY_HEADERS:
        assert headers[name] == value


def test_partial_photo_disconnect_retains_within_cap(settings, clock, tmp_path):
    """Reduced original disconnect test: retain staged bytes, never finalize/delete."""
    settings = photos_settings(settings, tmp_path / "photos")
    with TestClient(create_app(settings, clock=clock)) as client:
        phone = Phone(client, OWNER)
        data = blob(7, 3_000_000)
        url = phone.create(phone.key("video"), data).headers["Location"]
        for offset in (0, 200_000, 400_000):
            status, _, _ = raw_request(
                client, url, {**OWNER, "Upload-Offset": str(offset), "Upload-Complete": "?1"},
                [data[offset:offset + 100_000], data[offset + 100_000:offset + 200_000]],
                method="PATCH", end="disconnect",
            )
            assert status == 204
            assert phone.head(url).headers["Upload-Offset"] == str(offset + 200_000)
        staged = tmp_path / "photos" / "staging" / url.rsplit("/", 1)[1]
        assert staged.read_bytes() == data[:600_000]


def test_declared_partial_photo_obeys_global_cap(settings, clock, tmp_path):
    """Same photo path has no existing larger per-request policy for framed bodies."""
    settings = photos_settings(settings, tmp_path / "photos")
    with TestClient(create_app(settings, clock=clock)) as client:
        phone = Phone(client, OWNER)
        data = blob(7, 3_000_000)
        url = phone.create(phone.key("video"), data).headers["Location"]
        response = phone.patch(url, 0, data[:700_000], last=False)
        assert response.status_code == 413 and response.json()["error"] == "payload_too_large"
        assert phone.head(url).headers["Upload-Offset"] == "0"


@pytest.mark.parametrize("framing", ["unframed", "chunked", "declared"])
def test_partial_photo_stall_retains_offset(settings, clock, tmp_path, framing):
    """Reduced original stalled-read test: stop before finalizing the upload."""
    settings = photos_settings(settings, tmp_path / "photos", read_timeout_s=0.2)
    with TestClient(create_app(settings, clock=clock)) as client:
        phone = Phone(client, OWNER)
        data = blob(8, 50_000)
        url = phone.create(phone.key("a"), data).headers["Location"]
        request_headers = {**OWNER, "Upload-Offset": "0", "Upload-Complete": "?0"}
        if framing == "chunked":
            request_headers["Transfer-Encoding"] = "chunked"
        elif framing == "declared":
            request_headers["Content-Length"] = "50000"
        status, headers, _ = raw_request(
            client, url, request_headers,
            [data[:20_000]], method="PATCH", end="stall",
        )
        assert status == 409 and headers[b"upload-offset"] == b"20000"
        assert phone.head(url).headers["Upload-Offset"] == "20000"


@pytest.mark.parametrize("version,framing", [("1.1", "unframed"), ("1.1", "chunked"),
                                            ("1.1", "declared"), ("2", "unframed"), ("2", "declared")])
@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_photo_patch_boundary_and_offset(settings, clock, tmp_path, version, framing, delta):
    """The whole-file size does not exempt a PATCH from the 256 KiB cap."""
    cap = 256 * 1024
    settings = photos_settings(settings, tmp_path / "photos")
    with TestClient(create_app(settings, clock=clock)) as client:
        phone = Phone(client, OWNER)
        data = blob(9, 2 * cap)
        url = phone.create(phone.key("boundary"), data).headers["Location"]
        # Prior successful progress must survive a rejected PATCH.
        assert phone.patch(url, 0, data[:17], last=False).status_code == 204
        headers = {**OWNER, "Upload-Offset": "17", "Upload-Complete": "?0"}
        if framing == "declared":
            headers["Content-Length"] = str(cap + delta)
        elif framing == "chunked":
            headers["Transfer-Encoding"] = "chunked"
        status, response_headers, body = raw_request(
            client, url, headers, [data[17:100_017], data[100_017:17 + cap + delta]],
            version=version, method="PATCH",
        )
        expected_offset = 17 if delta > 0 else 17 + cap + delta
        assert status == (413 if delta > 0 else 204), (status, body)
        assert phone.head(url).headers["Upload-Offset"] == str(expected_offset)
        staged = tmp_path / "photos" / "staging" / url.rsplit("/", 1)[1]
        assert staged.read_bytes() == data[:expected_offset]
        if delta > 0:
            assert json.loads(body)["error"] == "payload_too_large"
            for name, value in SECURITY_HEADERS:
                assert response_headers[name] == value
        # Rejection/finish released the write lock; a within-cap retry can continue.
        assert phone.patch(url, expected_offset, data[expected_offset:expected_offset + 1], last=False).status_code == 204


@pytest.mark.parametrize("version", ["1.1", "2"])
@pytest.mark.parametrize("size", [1023, 1024, 1025])
def test_json_boundary_reaches_real_route(settings, clock, version, size):
    settings = replace(settings, sections={**settings.sections, "limits": LimitSettings(max_body_bytes=1024)})
    payload = json.dumps({"client_id": "boundary", "name": "Phone", "platform": "ios"}).encode()
    payload += b" " * (size - len(payload))
    settings = photos_settings(settings, settings.audit_path.parent / "photos")
    with TestClient(create_app(settings, clock=clock)) as client:
        status, _, body = raw_request(client, "/v1/photos/sources", {**OWNER, "Content-Type": "application/json"},
                                     [payload[:512], payload[512:]], version=version)
        assert status == (413 if size > 1024 else 201), (status, body)
        if size <= 1024:
            assert json.loads(body)["client_id"] == "boundary"


@pytest.mark.parametrize("started", [False, True])
def test_overflow_cannot_be_hidden_or_restart_response(started):
    """ASGI control: a parser may swallow errors; a started response cannot become 413."""
    sent, reads = [], []

    async def receive():
        reads.append(True)
        assert len(reads) == 1  # no draining an unbounded remainder
        return {"type": "http.request", "body": b"x" * 1025, "more_body": True}

    async def send(message):
        sent.append(message)

    async def parser(scope, receive, send):
        if started:
            await send({"type": "http.response.start", "status": 200, "headers": []})
        try:
            await receive()
        except Exception:
            pass  # like a body parser translating a receive error to 400
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"parser error"})

    guard = GuardMiddleware(parser, limits=LimitSettings(max_body_bytes=1024))
    scope = {"type": "http", "method": "POST", "path": "/", "headers": []}
    if started:
        with pytest.raises(Exception) as exc:
            anyio.run(guard, scope, receive, send)
        assert type(exc.value).__name__ == "_BodyTooLarge"
    else:
        anyio.run(guard, scope, receive, send)
    starts = [m for m in sent if m["type"] == "http.response.start"]
    assert len(starts) == 1 and starts[0]["status"] == (200 if started else 413)
    assert len(reads) == 1


def test_unrelated_route_exception_propagates():
    async def broken(scope, receive, send):
        raise RuntimeError("route failure")

    async def unused():
        raise AssertionError("guard must not prefetch")

    guard = GuardMiddleware(broken, limits=LimitSettings())
    with pytest.raises(RuntimeError, match="route failure"):
        anyio.run(guard, {"type": "http", "headers": []}, unused, unused)
