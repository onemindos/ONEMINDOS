# SPDX-License-Identifier: Apache-2.0
"""Unhandled-error header slice of CORE-SEC-9 (#160), not body-limit acceptance.

The unresolved unframed-body acceptance is retained in commit a117190b and
local out/160-evidence; it is not skipped or asserted fixed by this slice.
"""

from __future__ import annotations

import pytest
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from conftest import make_client
from onemind_core.guard import SECURITY_HEADERS


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
