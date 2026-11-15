# SPDX-License-Identifier: Apache-2.0
"""Real gateway regressions for CORE-SEC-9 (#160)."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from fastapi import Request
from fastapi.responses import Response, StreamingResponse
from fastapi.testclient import TestClient

from conftest import OWNER, make_client
from onemind_core.guard import SECURITY_HEADERS, LimitSettings


@pytest.mark.parametrize("http_version", ["1.1", "2"])
def test_body_limit_without_framing_headers(settings, clock, http_version):
    settings = replace(settings, sections={"limits": LimitSettings(max_body_bytes=1024)})
    with make_client(settings, clock) as client:
        messages = []
        chunks = iter([b"x" * 1024, b"x"])

        async def receive():
            chunk = next(chunks)
            return {"type": "http.request", "body": chunk, "more_body": len(chunk) == 1024}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": http_version,
            "method": "POST", "scheme": "https", "path": "/v1/actions", "raw_path": b"/v1/actions",
            "query_string": b"", "root_path": "", "server": ("testserver", 443),
            "client": ("testclient", 123),
            "headers": [(b"authorization", OWNER["Authorization"].encode()),
                        (b"content-type", b"application/json")],
        }
        asyncio.run(client.app(scope, receive, send))
        start = next(m for m in messages if m["type"] == "http.response.start")
        assert start["status"] == 413
        assert set(SECURITY_HEADERS) <= set(start["headers"])
        assert b'"error":"payload_too_large"' in b"".join(
            m.get("body", b"") for m in messages if m["type"] == "http.response.body"
        )


def test_security_headers_on_unhandled_gateway_error(settings, clock):
    with make_client(settings, clock) as client:
        @client.app.get("/guard-regression-error")
        async def fail():
            raise RuntimeError("guard regression")

        # Put this test-only route before the dashboard's catch-all route.
        client.app.router.routes.insert(0, client.app.router.routes.pop())
        with TestClient(client.app, raise_server_exceptions=False) as errors:
            response = errors.get("/guard-regression-error")
        assert response.status_code == 500
        assert response.json() == {"error": "unavailable", "message": "internal server error"}
        assert "guard regression" not in response.text
        for name, value in SECURITY_HEADERS:
            assert response.headers.get(name.decode()) == value.decode()
        # The framework must still propagate the exception for server logging.
        with pytest.raises(RuntimeError, match="guard regression"):
            client.get("/guard-regression-error")


@pytest.mark.parametrize("size", [0, 1024])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unknown_length_body_is_replayed_at_or_below_limit(settings, clock, size, method):
    settings = replace(settings, sections={"limits": LimitSettings(max_body_bytes=1024)})
    with make_client(settings, clock) as client:
        @client.app.api_route("/guard-regression-echo", methods=["GET", "POST"])
        async def echo(request: Request):
            return Response(await request.body())

        client.app.router.routes.insert(0, client.app.router.routes.pop())
        # httpx streams this without Content-Length; include an empty stream too.
        response = client.request(method, "/guard-regression-echo", content=iter([b"x" * size]))
        assert response.status_code == 200
        assert response.content == b"x" * size
        for name, value in SECURITY_HEADERS:
            assert response.headers[name.decode()] == value.decode()


def test_headers_on_gateway_rate_rejection(settings, clock):
    settings = replace(settings, sections={"limits": LimitSettings(read_burst=1, read_rate=0.001)})
    with make_client(settings, clock) as client:
        assert client.get("/v1/nodes", headers=OWNER).status_code == 200
        response = client.get("/v1/nodes", headers=OWNER)
        assert response.status_code == 429
        assert response.json()["error"] == "rate_limited"
        assert int(response.headers["retry-after"]) >= 1
        for name, value in SECURITY_HEADERS:
            assert response.headers[name.decode()] == value.decode()


def test_disabling_rate_limits_does_not_disable_body_guard(settings, clock):
    settings = replace(settings, sections={"limits": LimitSettings(enabled=False, max_body_bytes=1024)})
    with make_client(settings, clock) as client:
        response = client.post("/v1/actions", content=iter([b"x" * 1025]), headers=OWNER)
        assert response.status_code == 413
        for name, value in SECURITY_HEADERS:
            assert response.headers[name.decode()] == value.decode()


def test_stream_failure_keeps_started_response_and_headers(settings, clock):
    with make_client(settings, clock) as client:
        @client.app.get("/guard-regression-stream")
        async def stream():
            async def chunks():
                yield b"first chunk"
                raise RuntimeError("stream regression")

            return StreamingResponse(chunks(), headers={"Content-Security-Policy": "default-src 'none'"})

        client.app.router.routes.insert(0, client.app.router.routes.pop())
        with TestClient(client.app, raise_server_exceptions=False) as errors:
            response = errors.get("/guard-regression-stream")
        assert response.status_code == 200  # never replace an already-started stream with a 500
        assert response.headers["content-security-policy"] == "default-src 'none'"
        for name, value in SECURITY_HEADERS:
            if name != b"content-security-policy":
                assert response.headers[name.decode()] == value.decode()
        assert b"internal server error" not in response.content
        with pytest.raises(RuntimeError, match="stream regression"):
            client.get("/guard-regression-stream")
